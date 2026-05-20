"""
search_agent.py — CivicDigest Web Retrieval Layer
Takes a natural language query → finds city council meeting minutes → feeds into broadcast pipeline

Requirements:
    pip install tavily-python anthropic requests

Environment variables:
    TAVILY_API_KEY=your_key
    ANTHROPIC_API_KEY=your_key
"""

import os
import argparse
from datetime import datetime
from anthropic import Anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_API_KEY    = os.environ.get("TAVILY_API_KEY")

CURRENT_YEAR = datetime.now().year

# ── Step 1: Extract city and intent ───────────────────────────────────────────

QUERY_PARSE_PROMPT = """Extract the city name and topic from this query about city council news.
The current year is {current_year}. Always use {current_year} or {prev_year} in the search query — never older years.
Return ONLY valid JSON:
{{
  "city": "full city name (e.g. Chicago, Seattle, Denver), or null if no real city is mentioned",
  "topic": "specific topic if mentioned, or null",
  "search_query": "optimized web search query to find the most recent city council meeting minutes or decisions. Must include city name, 'city council', and {current_year} or {prev_year}",
  "is_valid_civic_query": true or false
}}

A valid civic query must reference a real city and something related to local government, city council, budget, zoning, housing, roads, taxes, public safety, or similar civic topics.
If the query is not about a real city's local government (e.g. it's a general question, a random phrase, or a non-existent place), set is_valid_civic_query to false.

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
    import re, json
    raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
    return json.loads(raw)

# ── Step 2: Search for meeting minutes via Tavily ─────────────────────────────

def search_minutes(search_query: str) -> list:
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
    except ImportError:
        raise ImportError("tavily-python not installed. Run: pip install tavily-python")

# ── Step 3: Extract meeting content from search results ───────────────────────

EXTRACT_PROMPT = """Below are web search results about a city council meeting.
Extract and consolidate the actual meeting content — decisions made, votes taken, items discussed, outcomes.
Focus only on substantive government actions that affect residents.
Ignore navigation text, ads, headers, footers.
Write as if you are summarizing raw meeting minutes.
If multiple results cover the same meeting, combine them.
Only include content from {current_year} or {prev_year} — ignore anything older.

Query that triggered this search: {query}

Search results:
{results}

Extracted meeting content (write as raw minutes-style text):"""

def extract_meeting_content(query: str, results: list) -> str:
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

# ── Main: query → meeting minutes text ───────────────────────────────────────

def find_minutes(query: str) -> tuple[str, str]:
    """
    Takes a natural language query.
    Returns (minutes_text, city_name) ready for the broadcast pipeline.
    Raises ValueError if the query is not a valid civic query.
    """
    print(f"🔍 Searching: '{query}'")

    parsed = parse_query(query)
    city = parsed.get("city")
    is_valid = parsed.get("is_valid_civic_query", True)
    search_query = parsed.get("search_query", query)

    # Guard: reject non-civic queries
    if not is_valid or not city:
        raise ValueError(
            "Please enter a US city and topic — for example: "
            "\"Chicago budget vote\" or \"Seattle zoning decisions\" or \"Denver city council this week\"."
        )

    print(f"   📍 City: {city}")
    print(f"   🔎 Search: {search_query}")

    results = search_minutes(search_query)
    if not results:
        raise ValueError(
            f"No recent city council records found for {city}. "
            "Try a larger city or a more specific topic."
        )
    print(f"   ✅ Found {len(results)} sources")

    minutes_text = extract_meeting_content(query, results)
    print(f"   ✅ Extracted {len(minutes_text.split())} words of meeting content")

    return minutes_text, city


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicDigest Search Agent")
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    minutes, city = find_minutes(args.query)
    print(f"\n--- EXTRACTED MINUTES ({city}) ---")
    print(minutes)
