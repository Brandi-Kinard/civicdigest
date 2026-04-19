"""
generate_pairs.py — CivicDigest synthetic pair generation (v2)
Looser quality filter to handle Legistar-structured text alongside PDF prose.

Run: python scripts/generate_pairs.py
"""

import os
import json
import time
from pathlib import Path
from tqdm import tqdm
import anthropic

RAW_DIR    = Path("data/raw")
PAIRS_FILE = Path("data/pairs.jsonl")

MODEL         = "claude-haiku-4-5-20251001"
MAX_TOKENS    = 400
CHUNK_SIZE    = 800   # smaller chunks → more pairs from same data
CHUNK_OVERLAP = 50
MAX_PAIRS     = 1500
SLEEP_BETWEEN = 0.3

PROMPT_TEMPLATE = """\
Below is text from a city council or government committee meeting. Summarize it in 2 short paragraphs.

Cover only what's actually present:
- What was decided or voted on
- What was proposed or discussed  
- What directly affects residents (taxes, zoning, roads, services, public safety)

Rules:
- Plain language. Write for a busy resident who skipped the meeting.
- No jargon. No legalese.
- Start with the substance — no intro like "This meeting covered..."
- If the text contains no real meeting content (just headers, signatures, or procedural boilerplate), reply with exactly: SKIP

Meeting text:
{chunk}

Summary:"""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start = end - overlap
    return chunks


def is_usable_chunk(text: str) -> bool:
    """
    Looser filter — accepts Legistar structured text AND PDF prose.
    Only rejects truly empty or header-only content.
    """
    words = text.split()
    if len(words) < 40:
        return False

    civic_keywords = [
        "motion", "seconded", "approved", "denied", "council", "mayor",
        "resolution", "ordinance", "vote", "ayes", "nays", "agenda",
        "public", "commissioner", "alderman", "zoning", "budget",
        "amendment", "hearing", "committee", "action", "item",
        "minutes", "meeting", "board", "department", "city", "municipal",
        "proposal", "legislation", "passed", "failed",
        "discussion", "report", "recommendation", "staff", "director",
    ]
    text_lower = text.lower()
    hits = sum(1 for kw in civic_keywords if kw in text_lower)
    return hits >= 1


def generate_summary(client: anthropic.Anthropic, chunk: str) -> str | None:
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(chunk=chunk.strip())}]
        )
        response = message.content[0].text.strip()
        if response.upper().startswith("SKIP") or len(response.split()) < 20:
            return None
        return response

    except anthropic.RateLimitError:
        print("   ⏳ Rate limit — sleeping 60s")
        time.sleep(60)
        return generate_summary(client, chunk)
    except Exception as e:
        print(f"   ❌ API error: {e}")
        return None


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=api_key)

    existing_pairs = []
    if PAIRS_FILE.exists():
        with open(PAIRS_FILE) as f:
            existing_pairs = [json.loads(line) for line in f if line.strip()]
        print(f"♻️  Resuming — {len(existing_pairs)} pairs already exist")

    existing_chunks = {p["input"][:100] for p in existing_pairs}

    txt_files = sorted(RAW_DIR.glob("*.txt"))
    print(f"\n📂 Found {len(txt_files)} source files")
    print(f"🎯 Target: {MAX_PAIRS} pairs\n")

    pairs_written = len(existing_pairs)
    skipped = 0

    with open(PAIRS_FILE, "a") as out_f:
        for txt_path in tqdm(txt_files, desc="Files"):
            if pairs_written >= MAX_PAIRS:
                break

            text = txt_path.read_text(encoding="utf-8", errors="ignore")
            chunks = chunk_text(text)

            for chunk in chunks:
                if pairs_written >= MAX_PAIRS:
                    break
                if not is_usable_chunk(chunk):
                    skipped += 1
                    continue
                if chunk[:100] in existing_chunks:
                    continue

                summary = generate_summary(client, chunk)
                if summary is None:
                    skipped += 1
                    continue

                pair = {"input": chunk, "output": summary, "source": txt_path.name}
                out_f.write(json.dumps(pair) + "\n")
                out_f.flush()
                pairs_written += 1
                existing_chunks.add(chunk[:100])
                time.sleep(SLEEP_BETWEEN)

    print(f"\n{'='*60}")
    print(f"✅ Done. Pairs written: {pairs_written} (includes previous run)")
    print(f"   Skipped: {skipped}")
    print(f"\nNext: python scripts/format_for_mlx.py")


if __name__ == "__main__":
    main()
