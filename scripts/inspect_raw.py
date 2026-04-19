"""
inspect_raw.py — Quick sanity check on your raw data before generating pairs.
Run this after scraping to see what you actually have.

Run: python scripts/inspect_raw.py
"""

from pathlib import Path

RAW_DIR = Path("data/raw")

def main():
    files = sorted(RAW_DIR.glob("*.txt"))
    if not files:
        print("❌ No files in data/raw/ yet.")
        print("   Run scrape_minutes.py, or drop PDFs into data/raw/ and run it again.")
        return

    print(f"\n{'='*70}")
    print(f"  RAW DATA INSPECTION — {len(files)} files")
    print(f"{'='*70}\n")

    total_words = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        words = text.split()
        total_words += len(words)

        # Preview first 200 chars
        preview = text[:200].replace("\n", " ").strip()

        print(f"📄 {f.name}")
        print(f"   {len(words):,} words | {len(text):,} chars")
        print(f"   Preview: {preview}...")
        print()

    avg_words = total_words // len(files) if files else 0
    estimated_chunks = total_words // 1200  # CHUNK_SIZE from generate_pairs.py
    estimated_pairs  = min(estimated_chunks, 1500)

    print(f"{'='*70}")
    print(f"  TOTALS")
    print(f"{'='*70}")
    print(f"  Files:             {len(files)}")
    print(f"  Total words:       {total_words:,}")
    print(f"  Avg words/file:    {avg_words:,}")
    print(f"  Est. chunks:       ~{estimated_chunks}")
    print(f"  Est. pairs (cap):  ~{estimated_pairs}")
    print()

    if estimated_pairs < 500:
        print("  ⚠️  Low pair count estimated. Scrape more cities or add more PDFs.")
        print("     Goal: 1,000–1,500 pairs. Add more Legistar clients or direct sites.")
    elif estimated_pairs >= 1000:
        print("  ✅ Looks like enough data. Proceed to generate_pairs.py")
    else:
        print("  🟡 Borderline. Proceed but consider scraping 2–3 more cities.")

    print()
    print("  Good cities to add to LEGISTAR_CLIENTS in scrape_minutes.py:")
    print("  raleigh, durham, greensboro, asheville, wilmington,")
    print("  chicago, seattle, boston, denver, phoenix, losangeles")
    print()

if __name__ == "__main__":
    main()
