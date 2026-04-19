"""
scrape_minutes.py — CivicDigest data collection
Targets: Legistar (API), direct .gov sites, and a manual PDF drop folder.

Strategy:
  1. Legistar API  → structured JSON → download linked PDFs/HTML
  2. Direct sites  → HTML minutes → extract text
  3. Manual folder → any PDFs you download yourself

All raw text lands in data/raw/ as .txt files.
Run: python scripts/scrape_minutes.py
"""

import os
import re
import time
import json
import requests
from pathlib import Path
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "CivicDigest-Research-Bot/1.0 (civic data research; contact: your@email.com)"
}

# ---------------------------------------------------------------------------
# 1. LEGISTAR API — best structured source
#    Find your city's Legistar client name at:
#    https://webapi.legistar.com/v1/{client}/meetings
#    Common clients: gastonia, charlotte, raleigh, chicago, seattle, boston
# ---------------------------------------------------------------------------

LEGISTAR_CLIENTS = [
    "raleigh",
    "chicago",
    "seattle",
    "boston",
    "denver",
    "lasvegas",
    "phoenix",
    "portland",
    "miami",
    "atlanta",
    "detroit",
    "minneapolis",
    "oakland",
    "richmond",
]

def fetch_legistar_minutes(client: str, max_meetings: int = 30) -> int:
    """Pull meeting minutes from Legistar Web API."""
    base = f"https://webapi.legistar.com/v1/{client}"
    saved = 0

    print(f"\n📡 Legistar: {client}")
    try:
        resp = requests.get(
            f"{base}/events",
            params={"$top": max_meetings, "$orderby": "EventDate desc"},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"   ⚠️  HTTP {resp.status_code} — client '{client}' may not exist on Legistar")
            return 0

        events = resp.json()
        print(f"   Found {len(events)} events")

        for event in events:
            event_id = event.get("EventId")
            event_date = event.get("EventDate", "")[:10]
            event_body = event.get("EventBodyName", "unknown").replace(" ", "_")

            # Get agenda items with attachments
            items_resp = requests.get(
                f"{base}/events/{event_id}/eventitems",
                params={"AgendaNote": 1, "MinutesNote": 1},
                headers=HEADERS,
                timeout=15,
            )
            if items_resp.status_code != 200:
                continue

            items = items_resp.json()
            text_chunks = []

            for item in items:
                title = item.get("EventItemTitle", "")
                minutes_note = item.get("EventItemMinutesNote", "") or ""
                agenda_note = item.get("EventItemAgendaNote", "") or ""
                action = item.get("EventItemActionText", "") or ""

                if title:
                    text_chunks.append(f"AGENDA ITEM: {title}")
                if action:
                    text_chunks.append(f"ACTION: {action}")
                if minutes_note:
                    text_chunks.append(f"MINUTES: {minutes_note}")
                if agenda_note:
                    text_chunks.append(f"NOTES: {agenda_note}")

            if text_chunks:
                filename = RAW_DIR / f"legistar_{client}_{event_date}_{event_body}_{event_id}.txt"
                content = f"CITY: {client.title()}\nDATE: {event_date}\nBODY: {event_body}\n\n"
                content += "\n\n".join(text_chunks)
                filename.write_text(content, encoding="utf-8")
                saved += 1
                print(f"   ✅ {event_date} {event_body} ({len(text_chunks)} items)")

            time.sleep(0.5)  # be a good citizen

    except Exception as e:
        print(f"   ❌ Error: {e}")

    return saved


# ---------------------------------------------------------------------------
# 2. DIRECT .GOV SCRAPING — HTML minutes pages
#    These are handpicked URLs that consistently post minutes as HTML.
#    Format: (city_name, url, css_selector_for_minutes_content)
# ---------------------------------------------------------------------------

DIRECT_SITES = [
    (
        "durham_nc",
        "https://www.durhamnc.gov/AgendaCenter/City-Council-4",
        "div.agendaItem",
    ),
]

def scrape_direct_site(city: str, url: str, selector: str) -> int:
    """Scrape a single HTML minutes page."""
    saved = 0
    print(f"\n🌐 Direct scrape: {city}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"   ⚠️  HTTP {resp.status_code}")
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find links to individual minutes documents
        links = soup.find_all("a", href=True)
        minutes_links = [
            a for a in links
            if any(kw in a.get_text().lower() for kw in ["minutes", "meeting"])
            and any(kw in a["href"].lower() for kw in ["minutes", "agenda", "meeting", ".pdf", ".htm"])
        ]

        print(f"   Found {len(minutes_links)} potential minutes links")

        for link in minutes_links[:20]:  # cap at 20 per site
            href = link["href"]
            if not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(url, href)

            if href.endswith(".pdf"):
                # Download PDF for later extraction
                pdf_path = RAW_DIR / f"{city}_{Path(href).stem}.pdf"
                if not pdf_path.exists():
                    try:
                        pdf_resp = requests.get(href, headers=HEADERS, timeout=20)
                        pdf_path.write_bytes(pdf_resp.content)
                        print(f"   📄 PDF saved: {pdf_path.name}")
                        saved += 1
                    except Exception as e:
                        print(f"   ⚠️  PDF failed: {e}")
                time.sleep(1)

            else:
                # HTML page — extract text
                try:
                    page_resp = requests.get(href, headers=HEADERS, timeout=15)
                    page_soup = BeautifulSoup(page_resp.text, "html.parser")
                    content_div = page_soup.select_one(selector) or page_soup.find("main") or page_soup.find("article")
                    if content_div:
                        text = content_div.get_text(separator="\n", strip=True)
                        if len(text) > 200:  # skip near-empty pages
                            slug = re.sub(r"[^\w-]", "_", link.get_text(strip=True))[:50]
                            out_path = RAW_DIR / f"{city}_{slug}.txt"
                            out_path.write_text(text, encoding="utf-8")
                            print(f"   ✅ HTML: {out_path.name}")
                            saved += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"   ⚠️  HTML failed: {href} — {e}")

    except Exception as e:
        print(f"   ❌ {e}")

    return saved


# ---------------------------------------------------------------------------
# 3. EXTRACT TEXT FROM ANY PDFs in data/raw/
#    Run this after scraping, or drop your own PDFs into data/raw/ manually.
# ---------------------------------------------------------------------------

def extract_pdfs() -> int:
    """Extract text from all PDFs in data/raw/ → .txt files."""
    try:
        import pdfplumber
    except ImportError:
        print("⚠️  pdfplumber not installed. Run: pip install pdfplumber")
        return 0

    pdfs = list(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print("\n📂 No PDFs found in data/raw/")
        return 0

    print(f"\n📑 Extracting text from {len(pdfs)} PDFs...")
    extracted = 0

    for pdf_path in pdfs:
        txt_path = pdf_path.with_suffix(".txt")
        if txt_path.exists():
            print(f"   ⏭️  Already extracted: {txt_path.name}")
            continue

        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text.strip())

            full_text = "\n\n".join(pages_text)
            if len(full_text) > 200:
                txt_path.write_text(full_text, encoding="utf-8")
                print(f"   ✅ {pdf_path.name} → {len(full_text):,} chars")
                extracted += 1
            else:
                print(f"   ⚠️  Skipped (too short / scanned): {pdf_path.name}")

        except Exception as e:
            print(f"   ❌ {pdf_path.name}: {e}")

    return extracted


# ---------------------------------------------------------------------------
# 4. QUALITY FILTER — remove junk files before pair generation
# ---------------------------------------------------------------------------

MIN_CHARS = 500    # minimum characters to be useful
MIN_WORDS = 80     # minimum words

def filter_raw_files():
    """Print a quality report on everything in data/raw/."""
    txt_files = list(RAW_DIR.glob("*.txt"))
    print(f"\n🔍 Quality report — {len(txt_files)} .txt files in data/raw/")
    print("-" * 60)

    good, bad = [], []
    for f in txt_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        words = len(text.split())
        chars = len(text)
        civic_keywords = ["motion", "seconded", "approved", "council", "mayor",
                          "resolution", "ordinance", "vote", "agenda", "public"]
        relevance = sum(1 for kw in civic_keywords if kw.lower() in text.lower())

        status = "✅" if chars >= MIN_CHARS and relevance >= 2 else "⚠️ "
        if chars >= MIN_CHARS and relevance >= 2:
            good.append(f)
        else:
            bad.append(f)

        print(f"   {status} {f.name[:55]:<55} {chars:>7,} chars  {relevance}/10 civic terms")

    print("-" * 60)
    print(f"   GOOD: {len(good)} files ready for pair generation")
    print(f"   WEAK: {len(bad)} files — review or delete")
    return good, bad


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    total = 0

    # 1. Legistar API
    for client in LEGISTAR_CLIENTS:
        total += fetch_legistar_minutes(client, max_meetings=100)

    # 2. Direct .gov sites
    for city, url, selector in DIRECT_SITES:
        total += scrape_direct_site(city, url, selector)

    # 3. Extract any PDFs (including ones you dropped in manually)
    total += extract_pdfs()

    # 4. Quality report
    good, bad = filter_raw_files()

    print(f"\n{'='*60}")
    print(f"🏛️  Data collection complete.")
    print(f"   Total files saved/extracted: {total}")
    print(f"   Files ready for training:    {len(good)}")
    print(f"\nNext: python scripts/generate_pairs.py")
