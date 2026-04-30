"""
broadcast.py — CivicDigest Sprint 2.5
Pipeline: meeting minutes → summary → broadcast script → ElevenLabs audio → D-ID/HeyGen video

Requirements:
    pip install anthropic requests python-dotenv

Environment variables (set in ~/.zshrc):
    ANTHROPIC_API_KEY=your_key
    ELEVENLABS_API_KEY=your_key
    DID_API_KEY=your_key
    HEYGEN_API_KEY=your_key
    NGROK_URL=your_ngrok_url

Usage:
    python broadcast.py --minutes "path/to/minutes.txt"
    python broadcast.py --text "paste minutes text here"
"""

import os
import json
import time
import argparse
import requests
from pathlib import Path
from anthropic import Anthropic

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY")
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY")
DID_API_KEY         = os.environ.get("DID_API_KEY")
HEYGEN_API_KEY      = os.environ.get("HEYGEN_API_KEY")

ELEVENLABS_VOICE_ID = "FyrYFW3P9GUxA348YGWu"  # Madison Ray
ELEVENLABS_API_URL  = "https://api.elevenlabs.io/v1/text-to-speech"

DID_API_URL         = "https://api.d-id.com"
DID_PRESENTER_ID    = "v2_public_diana_purple_shirt_1_green_screen@HiT0penpLE"

HEYGEN_AVATAR_ID = "8c0d8e7619a740bcb2b24d921eee6b60"  # Brandi's avatar
HEYGEN_VOICE_ID     = "e4e7a92b410540b8845e1bf656aee40c"  # Brandi's cloned voice

SUMMARIZE_MODEL     = "claude-haiku-4-5-20251001"
SCRIPT_MODEL        = "claude-haiku-4-5-20251001"

# ── Prompts ───────────────────────────────────────────────────────────────────

SUMMARIZE_PROMPT = """Below is text from a city council or government committee meeting. Summarize it in 2 short paragraphs.

Cover only what's actually present:
- What was decided or voted on
- What was proposed or discussed
- What directly affects residents (taxes, zoning, roads, services, public safety)

Rules:
- Plain language. Write for a busy resident who skipped the meeting.
- No jargon. No legalese.
- Start with the substance — no intro like "This meeting covered..."
- If the text contains no real meeting content, reply with exactly: SKIP

Meeting text:
{minutes}

Summary:"""

BROADCAST_SCRIPT_PROMPT = """You are a local TV news writer. Rewrite the following city council meeting summary as a 60-second broadcast news script.

STRICT RULES — follow every one:
- Lead sentence must answer: Who, What, When, Where, Why (5 Ws) in plain language
- Use inverted pyramid: most important fact first, supporting details second, context last
- Write for the ear, not the eye — short sentences, no complex clauses
- Use present tense for recent decisions ("The council approves..." not "approved")
- Never use: "aforementioned," "pursuant to," "heretofore," or any legalese
- Never use passive voice if active voice is possible
- Maximum 160 words — this must read aloud in 55-60 seconds
- No anchor intro like "Good evening" or "I'm reporting" — start directly with the news
- End with one sentence about what residents should do or expect next
- Output plain text only — no markdown, no headers, no asterisks

Summary to rewrite:
{summary}

Broadcast script:"""

# ── Step 1: Summarize meeting minutes ─────────────────────────────────────────

def summarize_minutes(minutes_text: str) -> str:
    print("📋 Step 1: Summarizing meeting minutes...")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=SUMMARIZE_MODEL,
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": SUMMARIZE_PROMPT.format(minutes=minutes_text.strip())
        }]
    )
    summary = message.content[0].text.strip()
    if summary.upper() == "SKIP":
        raise ValueError("No real meeting content found in input.")
    print(f"   ✅ Summary generated ({len(summary.split())} words)")
    return summary


# ── Step 2: Format as broadcast script ────────────────────────────────────────

def format_broadcast_script(summary: str) -> str:
    print("📺 Step 2: Formatting broadcast script...")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": BROADCAST_SCRIPT_PROMPT.format(summary=summary)
        }]
    )
    script = message.content[0].text.strip()
    script = script.replace("**", "").replace("##", "").replace("#", "").strip()
    word_count = len(script.split())
    print(f"   ✅ Script formatted ({word_count} words, ~{word_count // 2.5:.0f} seconds)")
    print(f"\n   --- SCRIPT ---")
    print(f"   {script}")
    print(f"   --------------\n")
    return script


# ── Step 3: Generate voice audio via ElevenLabs ───────────────────────────────

def generate_audio(script: str, output_path: str = "anchor_audio.mp3") -> str:
    print("🎙️  Step 3: Generating anchor voice via ElevenLabs...")
    url = f"{ELEVENLABS_API_URL}/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.80,
            "style": 0.20,
            "use_speaker_boost": True,
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {response.status_code}: {response.text}")

    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"   ✅ Audio saved to {output_path}")
    return output_path


# ── Step 4: Host audio for video providers ────────────────────────────────────

def upload_audio_to_did(audio_path: str) -> str:
    print("☁️  Step 4: Hosting audio...")
    import http.server
    import threading

    audio_dir = str(Path(audio_path).parent.absolute())
    audio_filename = Path(audio_path).name

    httpd = http.server.HTTPServer(
        ("0.0.0.0", 8888),
        lambda *args: http.server.SimpleHTTPRequestHandler(
            *args, directory=audio_dir
        )
    )
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    ngrok_url = os.environ.get("NGROK_URL", "").rstrip("/")
    if not ngrok_url:
        raise RuntimeError("Set NGROK_URL in ~/.zshrc to your ngrok public URL")

    audio_url = f"{ngrok_url}/{audio_filename}"
    print(f"   ✅ Audio URL: {audio_url}")
    return audio_url


# ── Step 5a: Generate anchor video via D-ID ───────────────────────────────────

def generate_anchor_video_did(audio_url: str) -> str:
    print("🎬 Step 5: Generating anchor video via D-ID Clips...")
    url = f"{DID_API_URL}/clips"
    headers = {
        "Authorization": f"Basic {DID_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "presenter_id": DID_PRESENTER_ID,
        "script": {
            "type": "audio",
            "audio_url": audio_url,
        },
        "config": {
            "fluent": True,
            "pad_audio": 0.0,
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"D-ID clips error {response.status_code}: {response.text}")

    clip_id = response.json().get("id")
    print(f"   ⏳ Video rendering... (clip ID: {clip_id})")

    for attempt in range(30):
        time.sleep(5)
        poll = requests.get(
            f"{DID_API_URL}/clips/{clip_id}",
            headers={"Authorization": f"Basic {DID_API_KEY}"}
        )
        data = poll.json()
        status = data.get("status")
        result_url = data.get("result_url")
        print(f"   ... status: {status}")
        if status == "done" and result_url:
            print(f"   ✅ D-ID video ready: {result_url}")
            return result_url
        elif status == "error":
            raise RuntimeError(f"D-ID rendering failed: {data}")

    raise TimeoutError("D-ID video did not complete in time.")


# ── Step 5b: Generate anchor video via HeyGen (fallback) ─────────────────────

def generate_anchor_video_heygen(script: str) -> str:
    print("🎬 Step 5: Generating anchor video via HeyGen...")

    response = requests.post(
        "https://api.heygen.com/v2/video/generate",
        headers={
            "X-Api-Key": HEYGEN_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "video_inputs": [{
                "character": {
                    "type": "avatar",
                    "avatar_id": HEYGEN_AVATAR_ID,
                    "avatar_style": "normal"
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": HEYGEN_VOICE_ID,
                    "speed": 1.0
                },
                "background": {
                    "type": "color",
                    "value": "#00FF00"
                }
            }],
            "dimension": {"width": 1920, "height": 1080},
            "aspect_ratio": "16:9"
        }
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(f"HeyGen error {response.status_code}: {response.text}")

    video_id = response.json().get("data", {}).get("video_id")
    print(f"   ⏳ HeyGen rendering... (video ID: {video_id})")

    for attempt in range(60):
        time.sleep(5)
        poll = requests.get(
            f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
            headers={"X-Api-Key": HEYGEN_API_KEY}
        )
        data = poll.json().get("data", {})
        status = data.get("status")
        print(f"   ... status: {status}")
        if status == "completed":
            video_url = data.get("video_url")
            print(f"   ✅ HeyGen video ready: {video_url}")
            return video_url
        elif status == "failed":
            raise RuntimeError(f"HeyGen rendering failed: {data}")

    raise TimeoutError("HeyGen video did not complete in time.")

# ── Step 5: Smart router — tries D-ID, falls back to HeyGen ──────────────────

def generate_anchor_video(audio_url: str, script: str = "") -> str:
    try:
        return generate_anchor_video_did(audio_url)
    except Exception as e:
        print(f"   ⚠️  D-ID failed: {e}")
        print("   🔄 Falling back to HeyGen...")
        return generate_anchor_video_heygen(script)


# ── Step 6: Download final video ──────────────────────────────────────────────

def download_video(video_url: str, output_path: str = "civicdigest_broadcast.mp4") -> str:
    print(f"⬇️  Step 6: Downloading final video...")
    response = requests.get(video_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"   ✅ Video saved to {output_path}")
    return output_path


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(minutes_text: str) -> str:
    print("\n🏛️  CivicDigest Broadcast Pipeline")
    print("=" * 50)

    summary   = summarize_minutes(minutes_text)
    script    = format_broadcast_script(summary)
    audio     = generate_audio(script)
    audio_url = upload_audio_to_did(audio)
    video_url = generate_anchor_video(audio_url, script)
    video     = download_video(video_url)

    print("\n" + "=" * 50)
    print(f"✅ Pipeline complete.")
    print(f"   Video: {video}")
    return video, script


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicDigest Broadcast Pipeline")
    parser.add_argument("--text", type=str, help="Meeting minutes text")
    parser.add_argument("--minutes", type=str, help="Path to minutes .txt file")
    args = parser.parse_args()

    if args.minutes:
        text = Path(args.minutes).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Paste meeting minutes below (Ctrl+D when done):")
        import sys
        text = sys.stdin.read()

    run_pipeline(text)
