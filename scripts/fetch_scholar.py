#!/usr/bin/env python3
"""
Automated zero-hardcode Google Scholar publications fetcher with:
1. Updated priority-based publication categorization (assign_category)
2. Crossref REST API DOI resolution using query.bibliographic & author matching
3. Detailed debug logs
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
DEVELOPER_EMAIL = "Ming.Chen@bristol.ac.uk"

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

def assign_category(title, venue):
    # 将标题和来源转换为小写，方便做不区分大小写的匹配
    title_lower = title.lower().strip()
    # 谷歌学术有时抓不到 venue，需要做空值保护
    venue_lower = venue.lower().strip() if venue else ""

    # 优先级 1：Scholarship Synthesis (文献综述类)
    synthesis_keywords = ['systematic review', 'meta-analysis', 'meta analysis', 'scoping review']
    if any(kw in title_lower or kw in venue_lower for kw in synthesis_keywords):
        return "Scholarship Synthesis"

    # 优先级 2：Book Review (书评)
    if title_lower.startswith('review of') or 'book review' in title_lower or 'book review' in venue_lower:
        return "Book Review"

    # 优先级 3：Book Chapter (书籍章节)
    # 只要来源中包含编者、手册、出版社等典型书籍词汇
    book_keywords = ['ed.', 'eds.', 'edited by', 'handbook', 'encyclopedia', 'chapter', 'press']
    if any(kw in venue_lower for kw in book_keywords):
        return "Book Chapter"

    # 优先级 4：默认归类 (期刊论文)
    return "Journal Paper"

def extract_first_author_lastname(authors_str):
    if not authors_str:
        return ""
    first_author = authors_str.split(',')[0].strip()
    parts = first_author.split()
    return parts[-1] if parts else ""

def fetch_doi_from_crossref(title, first_author_lastname):
    # 必须加上 User-Agent 和邮箱，否则 Crossref 会拒绝请求
    headers = {
        "User-Agent": f"ScholarSyncScript/1.0 (mailto:{DEVELOPER_EMAIL})"
    }
    
    # 联合标题和作者姓氏进行搜索，提高准确度
    query = f"{title} {first_author_lastname}".strip()
    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(query)}&rows=1"
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                items = data.get('message', {}).get('items', [])
                
                if items:
                    first_item = items[0]
                    crossref_title = first_item.get('title', [''])[0]
                    
                    # 计算标题相似度
                    similarity = difflib.SequenceMatcher(None, title.lower(), crossref_title.lower()).ratio()
                    
                    # 如果相似度大于 0.65，我们认为是同一篇文章
                    if similarity > 0.65:
                        return first_item.get('DOI', '')
        
        # 增加轻微延时，防止请求过快被封
        time.sleep(0.5)
    except Exception as e:
        print(f"DOI fetch error for '{title}': {e}")
        
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

    print(f"Successfully fetched {len(parser.pubs)} publications directly from Google Scholar.\n")

    for i, pub in enumerate(parser.pubs):
        # 1. 自动归类
        pub['category'] = assign_category(pub['title'], pub['venue'])
        
        # 加入调试日志
        print(f"Title: [{pub['title']}] | Venue: [{pub['venue']}] | Assigned Category: [{pub['category']}]")
        
        # 2. DOI 自动获取
        first_author_last = extract_first_author_lastname(pub['authors'])
        doi = fetch_doi_from_crossref(pub['title'], first_author_last)
        pub['doi'] = doi
        if doi:
            print(f"  -> Crossref DOI Matched: {doi}")
        else:
            print(f"  -> No Crossref DOI match found.")
        print("-" * 70)

    out_path = os.path.abspath(PUBLICATIONS_FILE)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(parser.pubs, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(parser.pubs)} categorized publications to {out_path}")

if __name__ == "__main__":
    fetch_and_save()
