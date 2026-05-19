"""
server.py — CivicDigest API Server
SSE stream handles Steps 1-4 (audio, instant).
Video generation runs in a background thread (Steps 5-6).
Frontend polls /job/<job_id> for video status.

Requirements:
    pip install flask flask-cors sendgrid
"""

import os
import json
import time
import uuid
import sqlite3
import threading
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
CORS(app)

CIVICDIGEST_DIR = Path(__file__).parent
DB_PATH         = CIVICDIGEST_DIR / "subscribers.db"

# ── In-memory job store ────────────────────────────────────────────────────────
# { job_id: { status, video_url, error, city, emails } }
JOBS = {}
JOBS_LOCK = threading.Lock()


# ── Database ───────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            city       TEXT,
            job_id     TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Background video job ───────────────────────────────────────────────────────

def run_video_job(job_id: str, audio_r2_url: str, script: str, city: str):
    """
    Runs HeyGen + compositor in a background thread.
    Updates JOBS[job_id] when done or failed.
    Emails all subscribers for this job when complete.
    """
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "rendering"

    try:
        from broadcast import generate_anchor_video, download_video
        from compose import compose
        from emailer import send_video_notification
        from r2_upload import upload_audio as r2_upload

        # Step 5: HeyGen
        print(f"[job:{job_id}] 🎬 Generating HeyGen video for {city}...")
        video_url = generate_anchor_video(audio_r2_url, script)

        # Download
        ts = int(time.time())
        video_filename = f"civicdigest_{city.lower().replace(' ', '_')}_{ts}.mp4"
        video_path = str(CIVICDIGEST_DIR / video_filename)
        download_video(video_url, video_path)

        # Step 6: Compositor
        print(f"[job:{job_id}] 🎨 Compositing...")
        final_filename = f"final_{video_filename}"
        final_path = str(CIVICDIGEST_DIR / final_filename)

        try:
            compose(video_path, script, final_path)
            serve_filename = final_filename
        except Exception as e:
            print(f"[job:{job_id}] ⚠️  Compositor failed: {e} — serving raw video")
            serve_filename = video_filename

        # Upload final video to R2 for stable public URL
        print(f"[job:{job_id}] ☁️  Uploading final video to R2...")
        final_r2_url = r2_upload(
            str(CIVICDIGEST_DIR / serve_filename),
            object_key=serve_filename
        )

        with JOBS_LOCK:
            JOBS[job_id]["status"]    = "done"
            JOBS[job_id]["video_url"] = final_r2_url
            emails = list(JOBS[job_id].get("emails", []))

        print(f"[job:{job_id}] ✅ Done: {final_r2_url}")

        # Email all subscribers
        for email in emails:
            send_video_notification(email, city, final_r2_url)

    except Exception as e:
        print(f"[job:{job_id}] ❌ Failed: {e}")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"]  = str(e)


# ── SSE pipeline (Steps 1-4 only) ─────────────────────────────────────────────

def run_pipeline_stream(query: str, job_id: str):
    """
    Runs Steps 1-4 synchronously, yields SSE events.
    Kicks off video job in background thread after audio is ready.
    """

    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # Step 1: Search
        yield event({"step": 1, "state": "active"})
        from search_agent import find_minutes
        minutes_text, city = find_minutes(query)
        yield event({"step": 1, "state": "done"})

        # Step 2: Summarize
        yield event({"step": 2, "state": "active"})
        from broadcast import summarize_minutes
        summary = summarize_minutes(minutes_text)
        yield event({"step": 2, "state": "done", "summary": summary})

        # Step 3: Script
        yield event({"step": 3, "state": "active"})
        from broadcast import format_broadcast_script
        script = format_broadcast_script(summary)
        yield event({"step": 3, "state": "done", "script": script})

        # Step 4: ElevenLabs audio
        yield event({"step": 4, "state": "active"})
        from broadcast import generate_audio
        ts = int(time.time())
        audio_filename = f"civicdigest_{city.lower().replace(' ','_')}_{ts}.mp3"
        audio_path = str(CIVICDIGEST_DIR / audio_filename)
        generate_audio(script, output_path=audio_path)
        yield event({"step": 4, "state": "done"})

        # Upload audio to R2
        from r2_upload import upload_audio as r2_upload
        audio_r2_url = r2_upload(audio_path, object_key=audio_filename)

        # Store job metadata
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status":  "queued",
                "city":    city,
                "script":  script,
                "summary": summary,
                "emails":  []
            })

        # Fire background video job
        t = threading.Thread(
            target=run_video_job,
            args=(job_id, audio_r2_url, script, city),
            daemon=True
        )
        t.start()

        # Send audio_ready — frontend loads player immediately
        yield event({
            "audio_ready": True,
            "audio_url":   audio_r2_url,
            "city":        city,
            "summary":     summary,
            "script":      script,
            "job_id":      job_id
        })

    except Exception as e:
        yield event({"error": str(e)})


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/generate', methods=['POST'])
def generate():
    data  = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return {"error": "No query provided"}, 400

    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "starting", "video_url": None, "error": None, "emails": []}

    return Response(
        run_pipeline_stream(query, job_id),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/job/<job_id>', methods=['GET'])
def job_status(job_id):
    """Frontend polls this to check video render progress."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status":    job.get("status"),
        "video_url": job.get("video_url"),
        "error":     job.get("error")
    })


@app.route('/subscribe', methods=['POST'])
def subscribe():
    """Capture email + city. Associate with job_id if provided."""
    data   = request.get_json()
    email  = (data.get('email') or '').strip().lower()
    city   = (data.get('city')  or '').strip()
    job_id = (data.get('job_id') or '').strip()

    if not email or '@' not in email:
        return jsonify({"error": "Valid email required"}), 400

    # Add email to job's notification list
    if job_id:
        with JOBS_LOCK:
            if job_id in JOBS:
                if email not in JOBS[job_id]["emails"]:
                    JOBS[job_id]["emails"].append(email)

                # If video already done by the time they subscribed, send immediately
                if JOBS[job_id]["status"] == "done" and JOBS[job_id].get("video_url"):
                    from emailer import send_video_notification
                    threading.Thread(
                        target=send_video_notification,
                        args=(email, city, JOBS[job_id]["video_url"]),
                        daemon=True
                    ).start()

    # Persist to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO subscribers (email, city, job_id, created_at) VALUES (?, ?, ?, ?)",
            (email, city, job_id, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[subscribe] DB error: {e}")

    print(f"[subscribe] {email} ({city}) job={job_id}")
    return jsonify({"ok": True})


@app.route('/video/<path:filename>')
def serve_video(filename):
    return send_from_directory(str(CIVICDIGEST_DIR), filename)

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(str(CIVICDIGEST_DIR / 'assets'), filename)

@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory(str(CIVICDIGEST_DIR), filename)


@app.route('/')
def index():
    return send_from_directory(str(CIVICDIGEST_DIR), 'app.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/debug/ffmpeg')
def debug_ffmpeg():
    import subprocess
    result = subprocess.run(['find', '/', '-name', 'ffprobe', '-type', 'f'], 
                          capture_output=True, text=True, timeout=15)
    return jsonify({"stdout": result.stdout, "stderr": result.stderr[:500]})

# ── Start ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5050))
    print("\n🏛️  CivicDigest Server")
    print("=" * 40)
    print(f"   http://0.0.0.0:{port}")
    print("=" * 40)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
