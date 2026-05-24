"""
search_agent.py — CivicDigest Web Retrieval Layer
Takes a natural language query → finds city council meeting minutes → feeds into broadcast pipeline

Strategy:
  1. Parse query to extract city name
  2. Try Tavily web search for recent meeting content
  3. If Tavily returns thin results, fall back to Legistar API directly
  4. Extract and clean meeting content for the broadcast pipeline

Requirements:
    pip install tavily-python anthropic requests

Environment variables:
    TAVILY_API_KEY=your_key
    ANTHROPIC_API_KEY=your_key
"""

import os
import re
import time
import json
import requests
import argparse
from datetime import datetime
from anthropic import Anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_API_KEY    = os.environ.get("TAVILY_API_KEY")

CURRENT_YEAR = datetime.now().year

HEADERS = {
    "User-Agent": "CivicDigest/1.0 (civic intelligence tool; public data only)"
}

# ── Known Legistar client names ────────────────────────────────────────────────
# Maps lowercase city name → Legistar API client slug
LEGISTAR_CLIENTS = {
    "chicago":      "chicago",
    "seattle":      "seattle",
    "boston":       "boston",
    "denver":       "denver",
    "raleigh":      "raleigh",
    "las vegas":    "lasvegas",
    "phoenix":      "phoenix",
    "portland":     "portland",
    "miami":        "miami",
    "atlanta":      "atlanta",
    "detroit":      "detroit",
    "minneapolis":  "minneapolis",
    "oakland":      "oakland",
    "richmond":     "richmond",
    "charlotte":    "charlotte",
    "nashville":    "nashville",
    "san jose":     "sanjose",
    "austin":       "austin",
    "columbus":     "columbus",
    "fort worth":   "fortworth",
    "memphis":      "memphis",
    "louisville":   "louisville",
    "baltimore":    "baltimore",
    "milwaukee":    "milwaukee",
    "albuquerque":  "albuquerque",
    "tucson":       "tucson",
    "fresno":       "fresno",
    "sacramento":   "sacramento",
    "kansas city":  "kansascity",
    "mesa":         "mesa",
    "omaha":        "omaha",
    "cleveland":    "cleveland",
    "virginia beach": "virginiabeach",
    "new orleans":  "neworleans",
    "tampa":        "tampa",
    "arlington":    "arlington",
    "honolulu":     "honolulu",
    "anaheim":      "anaheim",
    "aurora":       "aurora",
    "corpus christi": "corpuschristi",
    "riverside":    "riverside",
    "st. louis":    "stlouis",
    "lexington":    "lexington",
    "pittsburgh":   "pittsburgh",
    "anchorage":    "anchorage",
    "stockton":     "stockton",
    "cincinnati":   "cincinnati",
    "st. paul":     "stpaul",
    "greensboro":   "greensboro",
    "toledo":       "toledo",
    "newark":       "newark",
    "plano":        "plano",
    "henderson":    "henderson",
    "orlando":      "orlando",
    "jersey city":  "jerseycity",
    "chandler":     "chandler",
    "laredo":       "laredo",
    "madison":      "madison",
    "durham":       "durham",
    "lubbock":      "lubbock",
    "winston-salem": "winstonsalem",
    "garland":      "garland",
    "glendale":     "glendale",
    "hialeah":      "hialeah",
    "reno":         "reno",
    "baton rouge":  "batonrouge",
    "irvine":       "irvine",
    "chesapeake":   "chesapeake",
    "scottsdale":   "scottsdale",
    "north las vegas": "northlasvegas",
    "fremont":      "fremont",
    "gilbert":      "gilbert",
    "san bernardino": "sanbernardino",
    "birmingham":   "birmingham",
    "rochester":    "rochester",
    "richmond":     "richmond",
    "spokane":      "spokane",
    "des moines":   "desmoines",
    "montgomery":   "montgomery",
    "modesto":      "modesto",
    "fayetteville": "fayetteville",
    "tacoma":       "tacoma",
    "akron":        "akron",
    "aurora":       "aurora",
    "yonkers":      "yonkers",
    "little rock":  "littlerock",
    "columbus":     "columbus",
    "worcester":    "worcester",
    "knoxville":    "knoxville",
    "grand rapids": "grandrapids",
    "huntsville":   "huntsville",
    "salt lake city": "saltlakecity",
    "tallahassee":  "tallahassee",
    "huntington beach": "huntingtonbeach",
    "providence":   "providence",
    "brownsville":  "brownsville",
    "santa ana":    "santaana",
    "garden grove": "gardengrove",
    "oceanside":    "oceanside",
    "fort lauderdale": "fortlauderdale",
    "elk grove":    "elkgrove",
    "vancouver":    "vancouver",
    "ontario":      "ontario",
    "peoria":       "peoria",
    "cape coral":   "capecoral",
    "springfield":  "springfield",
    "chattanooga":  "chattanooga",
    "tempe":        "tempe",
    "overland park": "overlandpark",
    "fort collins": "fortcollins",
    "eugene":       "eugene",
    "santa rosa":   "santarosa",
    "rancho cucamonga": "ranchocucamonga",
    "pembroke pines": "pembrokepines",
    "salt lake":    "saltlakecity",
    "new york":     "nyc",
    "nyc":          "nyc",
    "los angeles":  "losangeles",
    "la":           "losangeles",
    "san francisco": "sanfrancisco",
    "sf":           "sanfrancisco",
    "san diego":    "sandiego",
    "dallas":       "dallas",
    "houston":      "houston",
    "philadelphia": "philadelphia",
    "washington":   "dc",
    "dc":           "dc",
    "indianapolis": "indianapolis",
    "jacksonville": "jacksonville",
}

# ── Step 1: Parse query ────────────────────────────────────────────────────────

QUERY_PARSE_PROMPT = """Extract the city name and topic from this query about city council news.
The current year is {current_year}.
Return ONLY valid JSON:
{{
  "city": "full city name (e.g. Chicago, Seattle, Denver), or null if no real city is mentioned",
  "state": "2-letter state code if mentioned or inferable, or null",
  "topic": "specific topic if mentioned, or null",
  "search_query": "optimized web search query to find the most recent city council meeting minutes or decisions. Include city name and 'city council'. Include {current_year} or {prev_year} only if helpful.",
  "is_valid_civic_query": true or false
}}

A valid civic query must reference a real city and something related to local government.
If the query is not about a real city's local government, set is_valid_civic_query to false.

Query: {query}
Return ONLY the JSON."""

def parse_query(query: str) -> dict:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": QUERY_PARSE_PROMPT.format(
            query=query,
            current_year=CURRENT_YEAR,
            prev_year=CURRENT_YEAR - 1
        )}]
    )
    raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
    return json.loads(raw)


# ── Step 2a: Tavily search ─────────────────────────────────────────────────────

def search_tavily(search_query: str) -> list:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        results = client.search(
            query=search_query,
            search_depth="advanced",
            max_results=5,
            include_raw_content=True
        )
        return results.get("results", [])
    except Exception as e:
        print(f"   ⚠️  Tavily error: {e}")
        return []


# ── Step 2b: Legistar API fallback ────────────────────────────────────────────

def fetch_legistar(city: str) -> str:
    """
    Directly query Legistar API for the most recent meeting minutes.
    Returns concatenated meeting content or empty string if city not on Legistar.
    """
    city_key = city.lower().strip()
    client_slug = LEGISTAR_CLIENTS.get(city_key)

    if not client_slug:
        # Try partial match
        for k, v in LEGISTAR_CLIENTS.items():
            if k in city_key or city_key in k:
                client_slug = v
                break

    if not client_slug:
        print(f"   ℹ️  {city} not in Legistar client list — skipping Legistar fallback")
        return ""

    print(f"   🏛️  Trying Legistar API: {client_slug}")
    base = f"https://webapi.legistar.com/v1/{client_slug}"

    try:
        resp = requests.get(
            f"{base}/events",
            params={"$top": 5, "$orderby": "EventDate desc"},
            headers=HEADERS,
            timeout=15
        )
        if resp.status_code != 200:
            print(f"   ⚠️  Legistar HTTP {resp.status_code} for {client_slug}")
            return ""

        events = resp.json()
        if not events:
            return ""

        print(f"   ✅ Legistar found {len(events)} recent events")
        text_chunks = []

        for event in events[:3]:  # top 3 most recent
            event_id = event.get("EventId")
            event_date = event.get("EventDate", "")[:10]
            event_body = event.get("EventBodyName", "City Council")

            text_chunks.append(f"MEETING: {event_body} — {event_date}")

            items_resp = requests.get(
                f"{base}/events/{event_id}/eventitems",
                params={"AgendaNote": 1, "MinutesNote": 1},
                headers=HEADERS,
                timeout=15
            )
            if items_resp.status_code != 200:
                continue

            items = items_resp.json()
            for item in items[:20]:  # cap per meeting
                title  = item.get("EventItemTitle", "")
                action = item.get("EventItemActionText", "") or ""
                notes  = item.get("EventItemMinutesNote", "") or ""

                if title:
                    text_chunks.append(f"ITEM: {title}")
                if action:
                    text_chunks.append(f"ACTION: {action}")
                if notes:
                    text_chunks.append(f"NOTES: {notes}")

            time.sleep(0.3)

        return "\n\n".join(text_chunks)

    except Exception as e:
        print(f"   ⚠️  Legistar error for {client_slug}: {e}")
        return ""


# ── Step 3: Extract meeting content ───────────────────────────────────────────

EXTRACT_PROMPT = """Below are web search results about a city council meeting.
Extract and consolidate the actual meeting content — decisions made, votes taken, items discussed, outcomes.
Focus only on substantive government actions that affect residents.
Ignore navigation text, ads, headers, footers.
Write as if you are summarizing raw meeting minutes.
If multiple results cover the same meeting, combine them.
Prioritize content from {current_year} or {prev_year}, but include older content if nothing recent is available.

Query that triggered this search: {query}

Search results:
{results}

Extracted meeting content (write as raw minutes-style text):"""

def extract_from_tavily(query: str, results: list) -> str:
    results_text = ""
    for i, r in enumerate(results[:4]):
        content = r.get("raw_content") or r.get("content", "")
        results_text += f"\n--- Result {i+1}: {r.get('url', '')} ---\n{content[:2000]}\n"

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": EXTRACT_PROMPT.format(
            query=query,
            results=results_text,
            current_year=CURRENT_YEAR,
            prev_year=CURRENT_YEAR - 1
        )}]
    )
    return msg.content[0].text.strip()


def is_content_sufficient(text: str) -> bool:
    """Check if extracted content has enough substance to summarize."""
    if not text or len(text.split()) < 40:
        return False
    # Reject content that looks like interface/navigation pages
    junk_phrases = [
        "unable to extract", "navigation elements", "loading screen",
        "system interface", "no actual meeting", "minutes have not been finalized",
        "not been finalized", "interface pages"
    ]
    text_lower = text.lower()
    if any(phrase in text_lower for phrase in junk_phrases):
        return False
    civic_keywords = ["motion", "seconded", "approved", "council", "mayor",
                      "resolution", "ordinance", "vote", "budget", "zoning",
                      "council member", "alderman", "amendment", "passed"]
    hits = sum(1 for kw in civic_keywords if kw in text_lower)
    return hits >= 2


# ── Main function ──────────────────────────────────────────────────────────────

def find_minutes(query: str) -> tuple[str, str]:
    """
    Takes a natural language query.
    Returns (minutes_text, city_name) ready for the broadcast pipeline.
    """
    print(f"🔍 Searching: '{query}'")

    parsed = parse_query(query)
    city = parsed.get("city")
    is_valid = parsed.get("is_valid_civic_query", True)
    search_query = parsed.get("search_query")

    # Guard: reject non-civic queries before hitting any API
    if not is_valid or not city or not search_query:
        raise ValueError(
            "Please enter a US city and topic — for example: "
            "\"Chicago budget vote\" or \"Seattle zoning decisions\" or \"Denver city council this week\"."
        )

    print(f"   📍 City: {city}")
    print(f"   🔎 Search: {search_query}")

    # Step 1: Try Tavily
    results = search_tavily(search_query)
    minutes_text = ""

    if results:
        print(f"   ✅ Found {len(results)} Tavily sources")
        minutes_text = extract_from_tavily(query, results)

    # Step 2: Check if Tavily content is sufficient
    if not is_content_sufficient(minutes_text):
        print(f"   ⚠️  Tavily content thin — trying Legistar API...")
        legistar_text = fetch_legistar(city)

        if legistar_text and is_content_sufficient(legistar_text):
            print(f"   ✅ Legistar content found")
            minutes_text = legistar_text
        elif legistar_text and minutes_text:
            # Combine both
            minutes_text = minutes_text + "\n\n" + legistar_text
            print(f"   ✅ Combined Tavily + Legistar content")
        elif legistar_text:
            minutes_text = legistar_text
        else:
            # Both thin — try broader Tavily search without date
            broad_query = f"{city} city council meeting decisions"
            print(f"   🔄 Trying broader search: {broad_query}")
            broad_results = search_tavily(broad_query)
            if broad_results:
                minutes_text = extract_from_tavily(broad_query, broad_results)

    if not is_content_sufficient(minutes_text):
        raise ValueError(
            f"We couldn't find recent council records for {city}. "
            "Try a major US city like Chicago, Seattle, or Denver — "
            "or add more detail like \"Boston city council budget 2026\"."
        )

    print(f"   ✅ Extracted {len(minutes_text.split())} words of meeting content")
    return minutes_text, city


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicDigest Search Agent")
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    minutes, city = find_minutes(args.query)
    print(f"\n--- EXTRACTED MINUTES ({city}) ---")
    print(minutes)
