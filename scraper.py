"""
News Bench - RSS Scraper (Upgraded)
===================================
Scrapes RSS feeds and extracts FULL article text using Newspaper3k.
"""

import time
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from email.utils import parsedate_to_datetime
import html
import re

# New dependency for full text extraction
try:
    from newspaper import Article
except ImportError:
    print("ERROR: newspaper3k not installed. Run: pip install newspaper3k")
    raise

# =============================================================================
# SCRAPER CONFIG
# =============================================================================
from config import (
    NEWS_SOURCES,
    REQUEST_TIMEOUT,
    USER_AGENT,
    REQUEST_DELAY,
    MAX_ARTICLE_AGE_HOURS
)
import database

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def clean_text(text: str) -> str:
    """Clean HTML entities and extra whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = ' '.join(text.split())
    return text.strip()

def parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to ISO format."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except (TypeError, ValueError):
        pass
    
    # Common fallback formats
    formats = ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return None

def is_article_recent(published_at: str, max_age_hours: int = MAX_ARTICLE_AGE_HOURS) -> bool:
    """Check if article is within acceptable age range."""
    if not published_at:
        return True
    try:
        date_str = published_at.replace('Z', '+00:00')
        pub_date = datetime.fromisoformat(date_str)
        if pub_date.tzinfo:
            from datetime import timezone
            pub_date = pub_date.astimezone(timezone.utc).replace(tzinfo=None)
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        return pub_date > cutoff
    except (ValueError, TypeError):
        return True

# =============================================================================
# CONTENT EXTRACTION
# =============================================================================

def fetch_full_article_text(url: str, rss_description: str = "") -> str:
    """
    Visit the URL and extract the full article text.
    Falls back to RSS description if extraction fails.
    """
    try:
        # We use newspaper3k to download and parse the article
        article = Article(url)
        article.download()
        article.parse()
        
        text = article.text.strip()
        
        # If scraper returned very little text, it might be a paywall/error
        if len(text) < 200:
            return clean_text(rss_description)
            
        return text
    except Exception as e:
        # print(f"    Failed to scrape {url}: {e} (using RSS summary)")
        return clean_text(rss_description)

# =============================================================================
# MAIN SCRAPING FUNCTIONS
# =============================================================================

def fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    """Fetch and parse an RSS feed."""
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None

def scrape_source(source: Dict) -> int:
    """Scrape a single news source."""
    name = source['name']
    url = source['url']
    lean = source['lean']

    print(f"Scraping {name}...")
    feed = fetch_feed(url)
    if not feed or not feed.entries:
        return 0

    new_count = 0
    for entry in feed.entries:
        try:
            headline = clean_text(entry.get('title', ''))
            if not headline:
                continue

            article_url = entry.get('link', '')
            if not article_url:
                continue

            # Check if URL exists before doing the heavy scraping work
            # (Note: You might need a check_if_exists function in database.py 
            # to avoid scraping body text for articles we already have)
            
            published_at = parse_date(entry.get('published') or entry.get('updated'))
            if not is_article_recent(published_at):
                continue

            # Extract RSS summary as backup
            rss_summary = (entry.get('summary') or entry.get('description') or '')

            # --- KEY CHANGE: Fetch Full Text ---
            # This slows down scraping but vastly improves analysis quality
            full_text = fetch_full_article_text(article_url, rss_summary)
            
            # Truncate if absolutely massive to save DB space/LLM tokens
            # Keep more text for deeper analysis
            if len(full_text) > 12000:
                full_text = full_text[:12000] + "..."

            # Insert into database (We use the full text as the 'lede' now, or add a body column)
            # For backward compatibility with your DB, we store it in 'lede'
            article_id = database.insert_article(
                source_name=name,
                source_lean=lean,
                headline=headline,
                lede=full_text, 
                url=article_url,
                published_at=published_at
            )

            if article_id:
                new_count += 1
                # Politeness delay between articles from same source
                time.sleep(0.5) 

        except Exception as e:
            print(f"  Error processing entry: {e}")
            continue

    print(f"  Added {new_count} new articles from {name}")
    return new_count

def scrape_all_sources() -> Dict[str, int]:
    """Scrape all configured news sources."""
    print("\n" + "="*60)
    print("NEWS BENCH - Full Text Scraper")
    print("="*60 + "\n")

    database.init_database()
    results = {}
    total_new = 0

    for source in NEWS_SOURCES:
        try:
            count = scrape_source(source)
            results[source['name']] = count
            total_new += count
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            print(f"Error scraping {source['name']}: {e}")

    print(f"\nScrape complete! Added {total_new} new articles.")
    return results

if __name__ == "__main__":
    scrape_all_sources()