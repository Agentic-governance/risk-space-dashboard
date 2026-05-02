#!/usr/bin/env python3
"""Backfill 5 years of fushinsha articles from Nordot/news.jp using Playwright.
Output: data/historical/fushinsha_5years.json

Nordot uses client-side JS pagination - static HTML only shows 10 articles.
This script uses Playwright to scroll/paginate through the full archive.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, 'data', 'historical', 'fushinsha_5years.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

UNITS = {
    "fushinsha": "https://news.jp/i/-/units/133089874031904245",
    "kiken_doubutsu": "https://news.jp/i/-/units/402299803402830945",
}

CUTOFF = datetime.now(timezone.utc) - timedelta(days=365 * 5)


def crawl_unit_playwright(page, name, url):
    """Use Playwright to scroll through unit page and collect all article links."""
    articles = []
    print(f"  [{name}] Navigating to {url}")
    page.goto(url, wait_until='networkidle', timeout=30000)
    time.sleep(2)

    prev_count = 0
    stale_rounds = 0
    max_scrolls = 500  # safety limit

    for scroll in range(max_scrolls):
        # Scroll to bottom to trigger lazy loading
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

        # Also try clicking "もっと見る" / "Load more" button if present
        try:
            more_btn = page.query_selector('button:has-text("もっと"), a:has-text("もっと"), [class*="more"], [class*="load"]')
            if more_btn and more_btn.is_visible():
                more_btn.click()
                time.sleep(2)
        except Exception:
            pass

        # Extract all article links currently in DOM
        links = page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href*="/i/"]').forEach(a => {
                const href = a.href;
                if (/\\/i\\/\\d{10,}/.test(href)) {
                    // Try to find date nearby
                    const time_el = a.closest('article, li, div')?.querySelector('time');
                    const date = time_el?.getAttribute('datetime') || time_el?.textContent || null;
                    links.push({url: href, date: date});
                }
            });
            return links;
        }""")

        current_count = len(links)
        if current_count == prev_count:
            stale_rounds += 1
            if stale_rounds >= 5:
                print(f"    Scroll {scroll}: no new articles after 5 rounds, stopping")
                break
        else:
            stale_rounds = 0

        prev_count = current_count

        if scroll % 20 == 0:
            print(f"    Scroll {scroll}: {current_count} articles in DOM")

        # Check if oldest article is past cutoff
        if links:
            dates = [l['date'] for l in links if l.get('date')]
            if dates:
                try:
                    oldest = min(dates)
                    oldest_dt = datetime.fromisoformat(oldest.replace('Z', '+00:00'))
                    if oldest_dt < CUTOFF:
                        print(f"    Reached 5yr cutoff at scroll {scroll}")
                        break
                except (ValueError, TypeError):
                    pass

    # Final extraction
    all_links = page.evaluate("""() => {
        const links = [];
        document.querySelectorAll('a[href*="/i/"]').forEach(a => {
            const href = a.href;
            if (/\\/i\\/\\d{10,}/.test(href)) {
                const time_el = a.closest('article, li, div')?.querySelector('time');
                const date = time_el?.getAttribute('datetime') || null;
                links.push({url: href, date: date});
            }
        });
        return links;
    }""")

    # Dedup
    seen = set()
    for l in all_links:
        if l['url'] not in seen:
            seen.add(l['url'])
            pub = l.get('date')
            articles.append({
                'url': l['url'],
                'published_at': pub,
                'unit': name,
            })

    print(f"  [{name}] Total unique: {len(articles)}")
    return articles


def main():
    print(f"Fetching 5yr fushinsha (cutoff: {CUTOFF.date()}) via Playwright")
    all_articles = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = context.new_page()

        for unit_name, unit_url in UNITS.items():
            try:
                articles = crawl_unit_playwright(page, unit_name, unit_url)
                all_articles.extend(articles)
            except Exception as e:
                errors.append(f"{unit_name}: {e}")
                print(f"  [{unit_name}] ERROR: {e}")

        browser.close()

    # Dedup and sort
    seen = set()
    dedup = []
    for a in all_articles:
        if a['url'] not in seen:
            seen.add(a['url'])
            dedup.append(a)
    dedup.sort(key=lambda x: x.get('published_at') or '0000', reverse=True)

    out = {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_units': UNITS,
        'period_days': 365 * 5,
        'cutoff_date': CUTOFF.strftime('%Y-%m-%d'),
        'count': len(dedup),
        'by_unit': {name: sum(1 for a in dedup if a.get('unit') == name) for name in UNITS},
        'errors': errors,
        'articles': dedup,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {OUT}: {len(dedup)} articles")


if __name__ == "__main__":
    main()
