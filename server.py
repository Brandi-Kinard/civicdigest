"""
server.py — CivicDigest Local API Server
Connects the web UI to the full pipeline via Server-Sent Events (SSE).

Requirements:
    pip install flask flask-cors

Usage:
    python server.py
    Then open app.html in browser (or serve with: python -m http.server 8090)
"""

import os
import json
import time
import threading
from flask import Flask, request, Response, send_from_directory
from flask_cors import CORS
from pathlib import Path

app = Flask(__name__)
CORS(app)

CIVICDIGEST_DIR = Path(__file__).parent

def run_pipeline_stream(query: str):
    """Generator that runs the full pipeline and yields SSE events."""

    def event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    try:
        # ── Step 1: Search ────────────────────────────────────────────────────
        yield event({"step": 1, "state": "active"})
        from search_agent import find_minutes
        minutes_text, city = find_minutes(query)
        yield event({"step": 1, "state": "done"})

        # ── Step 2: Summarize ─────────────────────────────────────────────────
        yield event({"step": 2, "state": "active"})
        from broadcast import summarize_minutes
        summary = summarize_minutes(minutes_text)
        yield event({"step": 2, "state": "done", "summary": summary})

        # ── Step 3: Broadcast script ──────────────────────────────────────────
        yield event({"step": 3, "state": "active"})
        from broadcast import format_broadcast_script
        script = format_broadcast_script(summary)
        yield event({"step": 3, "state": "done", "script": script})

        # ── Step 4: ElevenLabs audio ──────────────────────────────────────────
        yield event({"step": 4, "state": "active"})
        from broadcast import generate_audio
        audio_path = generate_audio(script)
        yield event({"step": 4, "state": "done"})

        # ── Step 5: D-ID anchor video ─────────────────────────────────────────
        yield event({"step": 5, "state": "active"})
        from broadcast import upload_audio_to_did, generate_anchor_video, download_video
        audio_url  = upload_audio_to_did(audio_path)
        video_url = generate_anchor_video(audio_url, script)
        anchor_vid = download_video(video_url, "civicdigest_broadcast.mp4")
        yield event({"step": 5, "state": "done"})

        # ── Step 6: Compose broadcast ─────────────────────────────────────────
        yield event({"step": 6, "state": "active"})
        from compose import compose
        final = compose(anchor_vid, script, "final_broadcast.mp4")
        yield event({"step": 6, "state": "done"})

        # ── Done ──────────────────────────────────────────────────────────────
        video_serve_url = f"http://127.0.0.1:5050/video/final_broadcast.mp4"
        yield event({
            "done": True,
            "city": city,
            "video_url": video_serve_url,
            "summary": summary,
            "script": script
        })

    except Exception as e:
        yield event({"error": str(e)})


@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return {"error": "No query provided"}, 400

    return Response(
        run_pipeline_stream(query),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/video/<path:filename>')
def serve_video(filename):
    return send_from_directory(str(CIVICDIGEST_DIR), filename)


@app.route('/')
def index():
    return send_from_directory(str(CIVICDIGEST_DIR), 'app.html')


if __name__ == '__main__':
    print("\n🏛️  CivicDigest Server")
    print("=" * 40)
    print("   API: http://127.0.0.1:5050")
    print("   UI:  http://127.0.0.1:5050")
    print("=" * 40)
    app.run(host='127.0.0.1', port=5050, debug=False, threaded=True)
