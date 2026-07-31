#!/usr/bin/env python3
"""
Automated ORCID Public API Publications Fetcher with Strict Web of Science Index Tagging:
1. Loads strict WoS (SSCI, SCIE, AHCI, ESCI) dataset from data/journal_index.csv
2. Performs strict exact and high-threshold (>=0.88) fuzzy matching
3. Queries ORCID Public API v3.0 for 100% structured DOIs, titles, venues, and authors
4. Applies priority-based categorization
5. Outputs structured data to publications.json
"""

import json
import urllib.request
import os
import re
import csv
import difflib

ORCID_ID = "0000-0003-4099-1606"
ORCID_WORKS_URL = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
ORCID_WORK_DETAIL_URL = f"https://pub.orcid.org/v3.0/{ORCID_ID}/work/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLICATIONS_FILE = os.path.join(SCRIPT_DIR, "..", "publications.json")
JOURNAL_INDEX_FILE = os.path.join(SCRIPT_DIR, "..", "data", "journal_index.csv")

def load_journal_index():
    index_dict = {}
    if not os.path.exists(JOURNAL_INDEX_FILE):
        print(f"Warning: Journal index dataset not found at {JOURNAL_INDEX_FILE}")
        return index_dict

    try:
        with open(JOURNAL_INDEX_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    j_name = row[0].strip().lower()
                    j_cat = row[1].strip()
                    if j_name:
                        index_dict[j_name] = j_cat
        print(f"Successfully loaded {len(index_dict)} strict WoS journal index records into memory.")
    except Exception as e:
        print(f"Error loading journal index CSV: {e}")

    return index_dict

JOURNAL_INDEX = load_journal_index()
JOURNAL_INDEX_KEYS = list(JOURNAL_INDEX.keys())

def match_journal_index(venue):
    """
    Matches venue string against Web of Science journal_index database.
    Returns matched Index_Category (e.g. 'SSCI', 'ESCI') if exact or high-threshold similarity >= 0.88, else ''.
    """
    if not venue or not JOURNAL_INDEX:
        return ""

    # Clean venue by removing volume, issue, page numbers, e.g. "Journal Name 4 (1), 18-31" -> "Journal Name"
    v_clean = re.sub(r'\s*\d+.*$', '', venue).strip().lower()
    if not v_clean:
        return ""

    # Direct exact lookup
    if v_clean in JOURNAL_INDEX:
        return JOURNAL_INDEX[v_clean]

    # Strict fuzzy matching using difflib with high cutoff (0.88)
    matches = difflib.get_close_matches(v_clean, JOURNAL_INDEX_KEYS, n=1, cutoff=0.88)
    if matches:
        matched_key = matches[0]
        return JOURNAL_INDEX[matched_key]

    return ""

def assign_category(title, venue, orcid_type):
    """
    Priority-based publication categorization combining ORCID native types and keywords:
    1. Scholarship Synthesis (systematic review, meta-analysis, scoping review)
    2. Book Review (ORCID type 'book-review', title starts with 'review of' or contains 'book review', or venue contains 'book review')
    3. Book Chapter (ORCID type 'book-chapter')
    4. Journal Paper (Default for 'journal-article' or unrecognized types)
    """
    t_lower = (title or "").lower().strip()
    v_lower = (venue or "").lower().strip()
    o_type = (orcid_type or "").lower().strip()

    # Priority 1: Scholarship Synthesis (文献综述/合成类，包含 systematic review, meta-analysis, scoping review 等)
    synthesis_keywords = [
        'systematic review', 'meta-analysis', 'meta analysis', 
        'scoping review', 'scoping literature review', 'scoping study', 'scoping synthesis',
        'systematic literature review', 'systematic synthesis'
    ]
    if any(kw in t_lower or kw in v_lower for kw in synthesis_keywords):
        return "Scholarship Synthesis"

    # Priority 2: Book Review
    if o_type == 'book-review' or t_lower.startswith('review of') or 'book review' in t_lower or 'book review' in v_lower:
        return "Book Review"

    # Priority 3: Book Chapter
    if o_type == 'book-chapter':
        return "Book Chapter"

    # Priority 4: Journal Paper (Default)
    return "Journal Paper"

def fetch_orcid_data():
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'ScholarSyncScript/1.0 (mailto:Ming.Chen@bristol.ac.uk)'
    }
    
    print(f"Fetching ORCID works profile for ID: {ORCID_ID}...")
    req = urllib.request.Request(ORCID_WORKS_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"Error requesting ORCID Public API: {e}")
        return []

    groups = data.get('group', [])
    print(f"Found {len(groups)} publication records on ORCID Profile.\n")
    
    parsed_pubs = []

    for idx, g in enumerate(groups):
        summaries = g.get('work-summary', [])
        if not summaries:
            continue
        
        s = summaries[0]
        title = s.get('title', {}).get('title', {}).get('value', '').strip()
        venue = s.get('journal-title', {}).get('value', '').strip() if s.get('journal-title') else ''
        orcid_type = s.get('type', '')
        
        pub_date = s.get('publication-date')
        year = ''
        if pub_date and pub_date.get('year'):
            year = pub_date.get('year', {}).get('value', '').strip()

        # Extract native DOI from external-ids
        doi = ''
        ext_ids = s.get('external-ids', {}).get('external-id', [])
        for ext in ext_ids:
            if ext.get('external-id-type') == 'doi':
                doi = ext.get('external-id-value', '').strip()
                break

        # Fetch detailed work record to extract author/contributor list
        authors_str = ""
        put_code = s.get('put-code')
        if put_code:
            try:
                detail_url = f"{ORCID_WORK_DETAIL_URL}{put_code}"
                req_detail = urllib.request.Request(detail_url, headers=headers)
                with urllib.request.urlopen(req_detail, timeout=10) as d_resp:
                    d_data = json.loads(d_resp.read().decode('utf-8'))
                    contribs = d_data.get('contributors', {}).get('contributor', [])
                    author_names = []
                    for c in contribs:
                        c_name = c.get('credit-name', {}).get('value', '').strip()
                        if c_name:
                            author_names.append(c_name)
                    if author_names:
                        authors_str = ", ".join(author_names)
            except Exception as ex:
                print(f"  Note: Could not fetch detail contributors for work {put_code}: {ex}")

        link = f"https://doi.org/{doi}" if doi else (s.get('url', {}).get('value', '') if s.get('url') else '')
        if not link:
            link = f"https://orcid.org/{ORCID_ID}"

        # Assign category
        category = assign_category(title, venue, orcid_type)

        # Match journal index tag (e.g. SSCI)
        index_tag = match_journal_index(venue)

        pub_obj = {
            "title": title,
            "authors": authors_str,
            "venue": venue,
            "year": year,
            "category": category,
            "index_tag": index_tag,
            "doi": doi,
            "link": link,
            "orcid_type": orcid_type
        }

        parsed_pubs.append(pub_obj)

        print(f"[{idx+1}/{len(groups)}] Title: [{title}]")
        print(f"       Venue: [{venue}] | Year: [{year}] | ORCID Type: [{orcid_type}]")
        print(f"       Category: [{category}] | Index Tag: [{index_tag or 'N/A'}] | DOI: [{doi}]")
        print("-" * 75)

    return parsed_pubs

def main():
    pubs = fetch_orcid_data()
    if not pubs:
        print("Warning: No publications retrieved from ORCID.")
        return

    out_path = os.path.abspath(PUBLICATIONS_FILE)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(pubs, f, indent=2, ensure_ascii=False)

    print(f"\nSuccessfully saved {len(pubs)} structured publications to {out_path}")

if __name__ == "__main__":
    main()
