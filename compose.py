"""
compose.py — CivicDigest Broadcast Compositor v2
Fixes: ticker clipping, video wall background, larger OTS with real image,
       better layout, anchor scaling.

Requirements:
    pip install anthropic requests pillow

Usage:
    python compose.py --input civicdigest_broadcast.mp4 --script "..." --output final_broadcast.mp4
"""

import os
import re
import json
import argparse
import subprocess
import requests
import tempfile
from pathlib import Path
from anthropic import Anthropic
from PIL import Image, ImageDraw, ImageFont

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H = 1920, 1080

# ── Paths ─────────────────────────────────────────────────────────────────────
ASSETS_DIR    = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)
VIDEO_WALL    = Path("video_wall.png")          # user-provided background
OTS_IMAGE     = ASSETS_DIR / "ots_graphic.jpg"

# ── Colors ────────────────────────────────────────────────────────────────────
NAVY       = (15,  15,  40, 220)
NAVY_SOLID = (15,  15,  40)
RED        = (196, 30,  58)
DARK_RED   = (120,  0,  20)
WHITE      = (255, 255, 255)
GREY       = (180, 180, 180)

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]

def font(size):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

# ── Metadata ──────────────────────────────────────────────────────────────────
METADATA_PROMPT = """Given this broadcast news script, return ONLY valid JSON:
{{
  "headline": "5-7 word ALL CAPS breaking news headline",
  "lower_third_name": "CIVICDIGEST AI",
  "lower_third_title": "Local Government Reporter",
  "ticker_items": ["item under 60 chars", "item under 60 chars", "item under 60 chars"],
  "ots_search_query": "2-3 word Unsplash photo search (city hall, housing construction, road repair)",
  "location": "City name",
  "topic_tag": "ONE WORD (BUDGET, HOUSING, SAFETY, ZONING, TRANSIT)"
}}
Script: {script}
Return ONLY the JSON."""

def generate_metadata(script):
    print("🧠 Generating broadcast metadata...")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": METADATA_PROMPT.format(script=script)}]
    )
    raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
    meta = json.loads(raw)
    print(f"   ✅ Headline: {meta['headline']}")
    print(f"   ✅ OTS query: {meta['ots_search_query']}")
    return meta

# ── Image fetching ─────────────────────────────────────────────────────────────
def fetch_image(url, path):
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            Path(path).write_bytes(r.content)
            return True
    except Exception as e:
        print(f"   ⚠️  {e}")
    return False

def fetch_ots_image(query):
    print(f"🖼️  Fetching OTS image: '{query}'...")
    pexels_key = os.environ.get("PEXELS_API_KEY")
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": pexels_key},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=15
        )
        if r.status_code == 200:
            results = r.json().get("photos", [])
            if results:
                img_url = results[0]["src"]["large"]
                if fetch_image(img_url, OTS_IMAGE):
                    print(f"   ✅ OTS image ready")
                    return OTS_IMAGE
    except Exception as e:
        print(f"   ⚠️  Pexels error: {e}")
    img = Image.new("RGB", (600, 400), NAVY_SOLID)
    img.save(OTS_IMAGE)
    return OTS_IMAGE

def load_background():
    """Load user-provided video wall or fallback."""
    if VIDEO_WALL.exists():
        print(f"🖼️  Using video wall: {VIDEO_WALL}")
        return Image.open(VIDEO_WALL).convert("RGBA").resize((W, H))
    # Dark fallback
    print("⚠️  video_wall.png not found — using dark background")
    return Image.new("RGBA", (W, H), (10, 10, 26, 255))

# ── Green screen key ──────────────────────────────────────────────────────────
def key_green_screen(img: Image.Image) -> Image.Image:
    """Remove green pixels from an RGBA image."""
    img = img.convert("RGBA")
    pixels = list(img.getdata())
    new_pixels = []
    for r, g, b, a in pixels:
        if g > r + 35 and g > b + 35 and g > 70:
            new_pixels.append((r, g, b, 0))
        else:
            new_pixels.append((r, g, b, a))
    img.putdata(new_pixels)
    return img

# ── Overlay builder ───────────────────────────────────────────────────────────
def build_overlay(meta, ots_path, frame_num):
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    headline  = meta["headline"]
    name      = meta["lower_third_name"]
    title_loc = f"{meta['lower_third_title']}  —  {meta['location']}"
    topic     = meta["topic_tag"]
    ticker_raw = "   •   ".join(meta["ticker_items"])
    ticker_txt = (ticker_raw + "       ") * 5

    # ── OTS box (upper right, 3x larger) ─────────────────────────────────────
    ots_w, ots_h = 560, 380          # 3x larger than before
    ots_x = W - ots_w - 30
    ots_y = 20

    # Border (red accent)
    draw.rectangle([ots_x - 4, ots_y - 4, ots_x + ots_w + 4, ots_y + ots_h + 36], fill=(*RED, 255))
    # OTS image
    try:
        ots_img = Image.open(ots_path).convert("RGBA").resize((ots_w, ots_h))
        overlay.paste(ots_img, (ots_x, ots_y), ots_img)
    except Exception:
        draw.rectangle([ots_x, ots_y, ots_x + ots_w, ots_y + ots_h], fill=(*NAVY_SOLID, 255))
    # Topic tag bar below OTS image
    draw.rectangle([ots_x, ots_y + ots_h, ots_x + ots_w, ots_y + ots_h + 36], fill=(*RED, 255))
    draw.text((ots_x + 12, ots_y + ots_h + 6), topic, fill=WHITE, font=font(22))

    # ── Headline bar ──────────────────────────────────────────────────────────
    hl_y = 820
    hl_w = ots_x - 40          # spans from left to just before OTS column
    draw.rectangle([30, hl_y, hl_w, hl_y + 52], fill=(*NAVY_SOLID, 215))
    draw.text((50, hl_y + 10), headline, fill=WHITE, font=font(30))

    # ── Lower thirds ─────────────────────────────────────────────────────────
    lt_y = 878
    draw.rectangle([30, lt_y, 680, lt_y + 5], fill=(*RED, 255))      # red line
    draw.rectangle([30, lt_y + 5, 680, lt_y + 78], fill=(*NAVY_SOLID, 218))
    draw.text((48, lt_y + 10), name,      fill=WHITE, font=font(32))
    draw.text((48, lt_y + 50), title_loc, fill=(*GREY, 255), font=font(20))

    # ── Ticker bar ────────────────────────────────────────────────────────────
    ticker_y = H - 44
    ticker_h = 44

    # Full red bar
    draw.rectangle([0, ticker_y, W, H], fill=(*RED, 245))

    # BREAKING label box — solid dark red, sits on top, clips ticker text
    breaking_w = 170
    draw.rectangle([0, ticker_y, breaking_w, H], fill=(*DARK_RED, 255))
    draw.text((12, ticker_y + 10), "BREAKING", fill=WHITE, font=font(22))

    # Scrolling ticker — starts AFTER the BREAKING box
    scroll_speed = 4
    ticker_start_x = breaking_w + 10
    offset = (frame_num * scroll_speed) % (W * 3)
    tx = ticker_start_x + (W - offset)

    # Clip ticker text to only draw right of breaking_w
    # We do this by creating a sub-image for the ticker region
    ticker_region = Image.new("RGBA", (W - breaking_w, ticker_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(ticker_region)
    tdraw.text((tx - ticker_start_x, 8), ticker_txt, fill=WHITE, font=font(20))
    overlay.paste(ticker_region, (breaking_w, ticker_y), ticker_region)

    return overlay

# ── Video info ────────────────────────────────────────────────────────────────
def get_video_info(path):
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    for s in data["streams"]:
        if s.get("codec_type") == "video":
            fps_str = s.get("r_frame_rate", "25/1").split("/")
            fps = int(fps_str[0]) / int(fps_str[1])
            return duration, fps, s.get("width", 960), s.get("height", 1080)
    return duration, 25, 960, 1080

# ── Main compositor ───────────────────────────────────────────────────────────
def composite_broadcast(anchor_video, ots_path, meta, output_path):
    print("🎬 Compositing broadcast video...")

    duration, fps, aw, ah = get_video_info(anchor_video)
    total = int(duration * fps)
    print(f"   {duration:.1f}s | {fps}fps | {total} frames")

    # Extract anchor frames
    anchor_dir = Path(tempfile.mkdtemp())
    print("   Extracting anchor frames...")
    subprocess.run([
        "ffmpeg", "-y", "-i", anchor_video,
        f"{anchor_dir}/%05d.png"
    ], capture_output=True, check=True)

    # Load background (video wall)
    bg = load_background()

    # Scale avatar to 85% of canvas height, maintain source ratio, pin to bottom
    anchor_target_h = int(H * 0.85)
    anchor_target_w = int(anchor_target_h * 1920 / 1080)
    anchor_x_offset = int(anchor_target_w * -0.28)  # shift left to center person
    anchor_y_offset = H - anchor_target_h

    # Compose frames
    out_dir = Path(tempfile.mkdtemp())
    frames  = sorted(anchor_dir.glob("*.png"))
    print(f"   Compositing {len(frames)} frames...")

    for i, f in enumerate(frames):
        if i % 50 == 0:
            print(f"   ... {i}/{len(frames)}")

        canvas = bg.copy()

        # Anchor
        af = Image.open(f).convert("RGBA")
        af = key_green_screen(af)
        af = af.resize((anchor_target_w, anchor_target_h), Image.LANCZOS)
        canvas.paste(af, (anchor_x_offset, anchor_y_offset), af)

        # Overlay
        ov = build_overlay(meta, ots_path, i)
        canvas = Image.alpha_composite(canvas, ov)

        canvas.convert("RGB").save(out_dir / f"{i:05d}.png")

    # Encode
    print("   Encoding final video...")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(int(fps)),
        "-i", f"{out_dir}/%05d.png",
        "-i", anchor_video,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", "-shortest",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Encode failed:\n{result.stderr[-800:]}")

    print(f"   ✅ Final video: {output_path}")
    return output_path

# ── Entry point ───────────────────────────────────────────────────────────────
def compose(anchor_video, script, output_path="final_broadcast.mp4"):
    print("\n🎨 CivicDigest Broadcast Compositor v2")
    print("=" * 50)
    meta     = generate_metadata(script)
    ots_path = fetch_ots_image(meta["ots_search_query"])
    output   = composite_broadcast(anchor_video, ots_path, meta, output_path)
    print(f"\n✅ Done: {output}")
    return output

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--output", default="final_broadcast.mp4")
    args = parser.parse_args()
    compose(args.input, args.script, args.output)
