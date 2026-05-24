"""
server.py — CivicDigest API Server
SSE stream handles Steps 1-4 (audio, instant).
Video generation runs in a background thread (Steps 5-6).
Frontend polls /job/<job_id> for video status.
Subscribers stored in Cloudflare R2 (persistent across deploys).
"""

import os
import json
import time
import uuid
import threading
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
CORS(app)

CIVICDIGEST_DIR = Path(__file__).parent

# ── In-memory job store ────────────────────────────────────────────────────────
JOBS = {}
JOBS_LOCK = threading.Lock()

# ── R2 subscriber storage ──────────────────────────────────────────────────────

SUBSCRIBERS_KEY = "civicdigest-subscribers.json"

def r2_get_subscribers() -> list:
    """Load subscriber list from R2."""
    try:
        import boto3
        from botocore.config import Config
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        obj = client.get_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=SUBSCRIBERS_KEY)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return []

def r2_save_subscriber(email: str, city: str, job_id: str):
    """Append a subscriber to R2 storage."""
    try:
        import boto3
        from botocore.config import Config
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        bucket = os.environ["R2_BUCKET_NAME"]

        # Load existing
        try:
            obj = client.get_object(Bucket=bucket, Key=SUBSCRIBERS_KEY)
            subscribers = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception:
            subscribers = []

        subscribers.append({
            "email": email,
            "city": city,
            "job_id": job_id,
            "created_at": datetime.utcnow().isoformat()
        })

        client.put_object(
            Bucket=bucket,
            Key=SUBSCRIBERS_KEY,
            Body=json.dumps(subscribers, indent=2).encode("utf-8"),
            ContentType="application/json"
        )
        print(f"[subscribe] saved {email} ({city}) to R2")
    except Exception as e:
        print(f"[subscribe] R2 save error: {e}")


# ── Background video job ───────────────────────────────────────────────────────

def run_video_job(job_id: str, audio_r2_url: str, script: str, city: str):
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "rendering"

    try:
        from broadcast import generate_anchor_video, download_video
        from compose import compose
        from emailer import send_video_notification
        from r2_upload import upload_audio as r2_upload

        print(f"[job:{job_id}] 🎬 Generating HeyGen video for {city}...")
        video_url = generate_anchor_video(audio_r2_url, script)

        ts = int(time.time())
        video_filename = f"civicdigest_{city.lower().replace(' ', '_')}_{ts}.mp4"
        video_path = str(CIVICDIGEST_DIR / video_filename)
        download_video(video_url, video_path)

        print(f"[job:{job_id}] 🎨 Compositing...")
        final_filename = f"final_{video_filename}"
        final_path = str(CIVICDIGEST_DIR / final_filename)

        try:
            compose(video_path, script, final_path)
            serve_filename = final_filename
        except Exception as e:
            print(f"[job:{job_id}] ⚠️  Compositor failed: {e} — serving raw video")
            serve_filename = video_filename

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

        for email in emails:
            send_video_notification(email, city, final_r2_url)

    except Exception as e:
        print(f"[job:{job_id}] ❌ Failed: {e}")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"]  = str(e)


# ── SSE pipeline (Steps 1-4) ───────────────────────────────────────────────────

def run_pipeline_stream(query: str, job_id: str):
    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        yield event({"step": 1, "state": "active"})
        from search_agent import find_minutes
        minutes_text, city = find_minutes(query)
        yield event({"step": 1, "state": "done"})

        yield event({"step": 2, "state": "active"})
        from broadcast import summarize_minutes
        summary = summarize_minutes(minutes_text)
        yield event({"step": 2, "state": "done", "summary": summary})

        yield event({"step": 3, "state": "active"})
        from broadcast import format_broadcast_script
        script = format_broadcast_script(summary)
        yield event({"step": 3, "state": "done", "script": script})

        yield event({"step": 4, "state": "active"})
        from broadcast import generate_audio
        ts = int(time.time())
        audio_filename = f"civicdigest_{city.lower().replace(' ','_')}_{ts}.mp3"
        audio_path = str(CIVICDIGEST_DIR / audio_filename)
        generate_audio(script, output_path=audio_path)
        yield event({"step": 4, "state": "done"})

        from r2_upload import upload_audio as r2_upload
        audio_r2_url = r2_upload(audio_path, object_key=audio_filename)

        with JOBS_LOCK:
            JOBS[job_id].update({
                "status":  "queued",
                "city":    city,
                "script":  script,
                "summary": summary,
                "emails":  []
            })

        t = threading.Thread(
            target=run_video_job,
            args=(job_id, audio_r2_url, script, city),
            daemon=True
        )
        t.start()

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
    data   = request.get_json()
    email  = (data.get('email') or '').strip().lower()
    city   = (data.get('city')  or '').strip()
    job_id = (data.get('job_id') or '').strip()

    if not email or '@' not in email:
        return jsonify({"error": "Valid email required"}), 400

    if job_id:
        with JOBS_LOCK:
            if job_id in JOBS:
                if email not in JOBS[job_id]["emails"]:
                    JOBS[job_id]["emails"].append(email)
                if JOBS[job_id]["status"] == "done" and JOBS[job_id].get("video_url"):
                    from emailer import send_video_notification
                    threading.Thread(
                        target=send_video_notification,
                        args=(email, city, JOBS[job_id]["video_url"]),
                        daemon=True
                    ).start()

    # Persist to R2
    threading.Thread(
        target=r2_save_subscriber,
        args=(email, city, job_id),
        daemon=True
    ).start()

    print(f"[subscribe] {email} ({city}) job={job_id}")
    return jsonify({"ok": True})


@app.route('/subscribers', methods=['GET'])
def list_subscribers():
    """Admin endpoint to view all subscribers."""
    secret = request.args.get('key', '')
    if secret != os.environ.get('ADMIN_KEY', ''):
        return jsonify({"error": "Unauthorized"}), 401
    subscribers = r2_get_subscribers()
    return jsonify({"count": len(subscribers), "subscribers": subscribers})

@app.route('/upload', methods=['POST'])
def upload_minutes():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if file.content_length and file.content_length > 5 * 1024 * 1024:
        return jsonify({"error": "File too large. Maximum 5MB."}), 400
    filename = file.filename.lower()
    try:
        if filename.endswith('.pdf'):
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                text = '\n\n'.join(p.extract_text() or '' for p in pdf.pages)
        else:
            text = file.read().decode('utf-8', errors='ignore')
        if len(text.strip()) < 100:
            return jsonify({"error": "File appears empty or unreadable."}), 400
        # Try to extract city name from content
        city = "Uploaded Document"
        import re
        city_match = re.search(r'CITY[:\s]+([A-Z][a-zA-Z\s]+)', text)
        if city_match:
            city = city_match.group(1).strip()
        return jsonify({"minutes_text": text[:8000], "city": city})
    except Exception as e:
        return jsonify({"error": f"Could not read file: {str(e)}"}), 400

@app.route('/video/<path:filename>')
def serve_video(filename):
    return send_from_directory(str(CIVICDIGEST_DIR), filename)


@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory(str(CIVICDIGEST_DIR), filename)


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(str(CIVICDIGEST_DIR / 'assets'), filename)


@app.route('/')
def index():
    return send_from_directory(str(CIVICDIGEST_DIR), 'app.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/debug/env')
def debug_env():
    import subprocess, glob
    ffmpeg = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True).stdout.strip()
    fonts = glob.glob('/usr/share/fonts/**/*.ttf', recursive=True) + \
            glob.glob('/nix/store/*/share/fonts/**/*.ttf', recursive=True)
    return jsonify({"ffmpeg": ffmpeg, "fonts": fonts[:20]})


# ── Start ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    print("\n🏛️  CivicDigest Server")
    print("=" * 40)
    print(f"   http://0.0.0.0:{port}")
    print("=" * 40)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
