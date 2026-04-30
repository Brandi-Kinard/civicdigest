"""
search_agent.py — CivicDigest Web Retrieval Layer
Takes a natural language query → finds city council meeting minutes → feeds into broadcast pipeline

Requirements:
    pip install tavily-python anthropic requests

Environment variables:
    TAVILY_API_KEY=your_key
    ANTHROPIC_API_KEY=your_key

Usage:
    python search_agent.py --query "What did the Chicago city council decide last week?"
    
    Or import and use in pipeline:
    from search_agent import find_minutes
    minutes_text = find_minutes("What did Chicago city council decide this week?")
"""

import os
import argparse
from anthropic import Anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_API_KEY    = os.environ.get("TAVILY_API_KEY")

# ── Step 1: Extract city and intent from natural language query ───────────────

QUERY_PARSE_PROMPT = """Extract the city name and topic from this query about city council news.
Return ONLY valid JSON:
{{
  "city": "full city name (e.g. Chicago, Seattle, Denver)",
  "topic": "specific topic if mentioned, or null",
  "search_query": "optimized web search query to find recent city council meeting minutes or decisions (include city name, 'city council', current year)"
}}

Query: {query}
Return ONLY the JSON."""

def parse_query(query: str) -> dict:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": QUERY_PARSE_PROMPT.format(query=query)}]
    )
    import re, json
    raw = re.sub(r"```json|```", "", msg.content[0].text.strip()).strip()
    return json.loads(raw)

# ── Step 2: Search for meeting minutes via Tavily ─────────────────────────────

def search_minutes(search_query: str) -> list:
    """Search for city council meeting minutes using Tavily."""
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

# ── Step 3: Extract relevant meeting content from search results ──────────────

EXTRACT_PROMPT = """Below are web search results about a city council meeting.
Extract and consolidate the actual meeting content — decisions made, votes taken, items discussed, outcomes.
Focus only on substantive government actions that affect residents.
Ignore navigation text, ads, headers, footers.
Write as if you are summarizing raw meeting minutes.
If multiple results cover the same meeting, combine them.

Query that triggered this search: {query}

Search results:
{results}

Extracted meeting content (write as raw minutes-style text):"""

def extract_meeting_content(query: str, results: list) -> str:
    """Use Claude to extract clean meeting content from messy web results."""
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
            results=results_text
        )}]
    )
    return msg.content[0].text.strip()

# ── Main function: query → meeting minutes text ───────────────────────────────

def find_minutes(query: str) -> tuple[str, str]:
    """
    Takes a natural language query.
    Returns (minutes_text, city_name) ready for the broadcast pipeline.
    """
    print(f"🔍 Searching: '{query}'")
    
    # Parse query
    parsed = parse_query(query)
    city = parsed.get("city", "Unknown City")
    search_query = parsed.get("search_query", query)
    print(f"   📍 City: {city}")
    print(f"   🔎 Search: {search_query}")
    
    # Search web
    results = search_minutes(search_query)
    if not results:
        raise ValueError(f"No results found for: {search_query}")
    print(f"   ✅ Found {len(results)} sources")
    
    # Extract content
    minutes_text = extract_meeting_content(query, results)
    print(f"   ✅ Extracted {len(minutes_text.split())} words of meeting content")
    
    return minutes_text, city


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicDigest Search Agent")
    parser.add_argument("--query", required=True, help="Natural language query about city council")
    args = parser.parse_args()
    
    minutes, city = find_minutes(args.query)
    print(f"\n--- EXTRACTED MINUTES ({city}) ---")
    print(minutes)
