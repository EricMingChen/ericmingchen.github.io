#!/usr/bin/env python3
"""
Automated zero-hardcode Google Scholar publications fetcher.
Fetches live publication profile for User ID: bhmuN8YAAAAJ
Saves parsed profile items directly to publications.json.
"""

import json
import urllib.request
import os
from html.parser import HTMLParser

SCHOLAR_ID = "bhmuN8YAAAAJ"
SCHOLAR_URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&pagesize=100"
PUBLICATIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "publications.json")

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

    out_path = os.path.abspath(PUBLICATIONS_FILE)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(parser.pubs, f, indent=2, ensure_ascii=False)
    
    print(f"Saved publications data to {out_path}")

if __name__ == "__main__":
    fetch_and_save()
