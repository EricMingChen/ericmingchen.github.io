#!/usr/bin/env python3
"""
Automated zero-hardcode Google Scholar publications fetcher with:
1. Automated priority-based publication categorization
2. Crossref REST API DOI resolution with string similarity matching
3. Direct JSON output for website rendering
"""

import json
import urllib.request
import urllib.parse
import os
import re
import difflib
import time
from html.parser import HTMLParser

SCHOLAR_ID = "bhmuN8YAAAAJ"
SCHOLAR_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&pagesize=100"
PUBLICATIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "publications.json")
CONTACT_EMAIL = "Ming.Chen@bristol.ac.uk"

class ScholarHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pubs = []
        self.cur = None
        self.current_field = None
        self.grays = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = d.get('class', '')
        if tag == 'tr' and 'gsc_a_tr' in cls:
            self.cur = {'title': '', 'authors': '', 'venue': '', 'year': '', 'citations': 0, 'link': ''}
            self.grays = []
        elif self.cur is not None:
            if tag == 'a' and 'gsc_a_at' in cls:
                self.current_field = 'title'
                if 'href' in d:
                    href = d['href']
                    if not href.startswith('http'):
                        href = 'https://scholar.google.com' + href
                    self.cur['link'] = href
            elif tag == 'div' and 'gs_gray' in cls:
                self.current_field = 'gray'
            elif tag == 'a' and 'gsc_a_ac' in cls:
                self.current_field = 'citations'
            elif tag == 'span' and 'gsc_a_h' in cls:
                self.current_field = 'year'

    def handle_endtag(self, tag):
        if tag == 'tr' and self.cur is not None:
            if len(self.grays) > 0:
                self.cur['authors'] = self.grays[0]
            if len(self.grays) > 1:
                self.cur['venue'] = self.grays[1]
            self.pubs.append(self.cur)
            self.cur = None
            self.grays = []
        self.current_field = None

    def handle_data(self, data):
        if self.cur is None or not self.current_field:
            return
        t = data.strip()
        if not t:
            return
        if self.current_field == 'title':
            if self.cur['title']:
                self.cur['title'] += ' ' + t
            else:
                self.cur['title'] = t
        elif self.current_field == 'gray':
            self.grays.append(t)
        elif self.current_field == 'citations':
            try:
                self.cur['citations'] = int(t)
            except ValueError:
                self.cur['citations'] = 0
        elif self.current_field == 'year':
            self.cur['year'] = t

def categorize_pub(title, venue):
    """
    Categorizes publication based on title and venue using strict priority:
    1. Scholarship Synthesis (systematic review, meta-analysis, scoping review)
    2. Book Review (Review of..., Book Review)
    3. Book Chapter (ed., eds., Handbook of, In: [Editor], Press + pp.)
    4. Journal Paper (Default)
    """
    t_lower = title.lower()
    v_lower = venue.lower()

    # Priority 1: Scholarship Synthesis
    synthesis_keywords = ['systematic review', 'meta-analysis', 'scoping review', 'systematic literature review']
    if any(k in t_lower or k in v_lower for k in synthesis_keywords):
        return 'Scholarship Synthesis'

    # Priority 2: Book Review (MUST be after Rule 1)
    if t_lower.startswith('review of') or 'book review' in t_lower or 'book review' in v_lower:
        return 'Book Review'

    # Priority 3: Book Chapter
    editor_markers = ['ed.', 'eds.', 'edited by', '(ed)', '(eds)']
    collection_markers = ['handbook of', 'encyclopedia of', 'companion to']
    
    has_editor = any(e in v_lower for e in editor_markers)
    has_collection = any(c in t_lower or c in v_lower for c in collection_markers)
    # Match "In: Editor Name" or "In Editor Name" (e.g. In A. M. Riazi (Ed.))
    has_in_format = bool(re.search(r'\bin\s*:\s*|\bin\s+[a-z]\.\s*[a-z]', v_lower))
    # Check Press + pp. without typical journal volume/issue (e.g. 4(2) or 155-176)
    has_press_pp = ('press' in v_lower and ('pp.' in v_lower or 'p.' in v_lower)) and not bool(re.search(r'\d+\s*\(\d+\)', v_lower))

    if has_editor or has_collection or has_in_format or has_press_pp:
        return 'Book Chapter'

    # Priority 4: Journal Paper (Default)
    return 'Journal Paper'

def resolve_doi_from_crossref(title):
    """
    Queries Crossref API politely to find DOI for a given paper title.
    Returns DOI string if match ratio >= 0.75, else empty string.
    """
    if not title:
        return ""
    
    clean_title = re.sub(r'^[^\w]+|[^\w]+$', '', title)
    encoded = urllib.parse.quote(clean_title)
    url = f"https://api.crossref.org/works?query.title={encoded}&rows=1"
    
    headers = {
        'User-Agent': f'ScholarSiteSync/1.0 (mailto:{CONTACT_EMAIL})'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('message', {}).get('items', [])
            if items:
                item = items[0]
                cr_title = item.get('title', [''])[0]
                doi = item.get('DOI', '')
                ratio = difflib.SequenceMatcher(None, clean_title.lower(), cr_title.lower()).ratio()
                if ratio >= 0.75 and doi:
                    return doi
    except Exception as e:
        print(f"  Crossref lookup skipped for '{clean_title[:30]}...': {e}")
    
    return ""

def fetch_and_save():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(SCHOLAR_URL, headers=headers)
    
    print(f"Fetching Google Scholar profile for ID: {SCHOLAR_ID}...")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_content = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching Google Scholar profile: {e}")
        return

    parser = ScholarHTMLParser()
    parser.feed(html_content)

    print(f"Successfully fetched {len(parser.pubs)} publications directly from Google Scholar.")

    for i, pub in enumerate(parser.pubs):
        # Apply automatic categorization
        pub['category'] = categorize_pub(pub['title'], pub['venue'])
        
        # Apply Crossref DOI resolution
        print(f"[{i+1}/{len(parser.pubs)}] Resolving DOI for: {pub['title'][:40]}...")
        doi = resolve_doi_from_crossref(pub['title'])
        pub['doi'] = doi
        if doi:
            print(f"  -> Found DOI: {doi}")
        else:
            print(f"  -> No DOI matched.")
        time.sleep(0.4)  # Polite delay for Crossref API

    out_path = os.path.abspath(PUBLICATIONS_FILE)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(parser.pubs, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(parser.pubs)} categorized publications to {out_path}")

if __name__ == "__main__":
    fetch_and_save()
