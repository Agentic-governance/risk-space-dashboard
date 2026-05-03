#!/usr/bin/env python3
"""Enrich fushinsha_5years.json articles with dates from meta[name=pubdate].
Processes in batches of 100, saves progress periodically.
"""
import json
import os
import time
import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'historical', 'fushinsha_5years.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

session = requests.Session()
session.headers.update(HEADERS)


def get_pubdate(url):
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        meta = soup.find('meta', attrs={'name': 'pubdate'})
        if meta and meta.get('content'):
            return meta['content']
        meta = soup.find('meta', attrs={'property': 'article:published_time'})
        if meta and meta.get('content'):
            return meta['content']
        return None
    except Exception:
        return None


def main():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    articles = data.get('articles', [])
    missing = [i for i, a in enumerate(articles) if not a.get('published_at')]
    print(f"Total articles: {len(articles)}, missing dates: {len(missing)}")

    enriched = 0
    for batch_start in range(0, len(missing), 100):
        batch = missing[batch_start:batch_start + 100]
        for idx in batch:
            url = articles[idx]['url']
            pubdate = get_pubdate(url)
            if pubdate:
                articles[idx]['published_at'] = pubdate
                enriched += 1
            time.sleep(0.5)

        # Save progress every 100
        data['articles'] = articles
        data['enriched_count'] = enriched
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Batch {batch_start//100 + 1}: enriched {enriched}/{len(missing)}")

    print(f"[DONE] Enriched {enriched} articles with dates")


if __name__ == "__main__":
    main()
