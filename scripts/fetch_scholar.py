#!/usr/bin/env python3
"""
Automated Google Scholar publications fetcher script.
Retrieves citation profile data for User ID: bhmuN8YAAAAJ
Updates publications.json with updated citation metrics and details.
"""

import json
import urllib.request
import re
import os

SCHOLAR_ID = "bhmuN8YAAAAJ"
SCHOLAR_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en"
PUBLICATIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "publications.json")

def fetch_scholar_html():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(SCHOLAR_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Warning: Could not fetch direct Scholar HTML: {e}")
        return None

def update_publications():
    html = fetch_scholar_html()
    if not html:
        print("Using existing publications.json without network update.")
        return

    # Load existing publications
    if os.path.exists(PUBLICATIONS_FILE):
        with open(PUBLICATIONS_FILE, 'r', encoding='utf-8') as f:
            pubs = json.load(f)
    else:
        pubs = []

    # Simple regex parsing for citation counts in Scholar profile table
    # Matches: <a class="gsc_a_ac..." ...>NUM</a>
    citation_matches = re.findall(r'class="gsc_a_ac[^"]*"[^>]*>(\d+)</a>', html)
    title_matches = re.findall(r'class="gsc_a_at"[^>]*>([^<]+)</a>', html)

    print(f"Found {len(title_matches)} publications on Google Scholar profile.")

    # Match and update citation counts
    for i, title in enumerate(title_matches):
        c_count = int(citation_matches[i]) if i < len(citation_matches) else 0
        cleaned_title = title.strip().lower()

        # Update in existing list
        matched = False
        for p in pubs:
            if p["title"].strip().lower() in cleaned_title or cleaned_title in p["title"].strip().lower():
                p["citations"] = c_count
                p["link"] = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en"
                matched = True
                break

    # Save updated file
    with open(PUBLICATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(pubs, f, indent=2, ensure_ascii=False)
    print("Successfully updated publications.json!")

if __name__ == "__main__":
    update_publications()
