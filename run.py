#!/usr/bin/env python3
"""
News Bench - Pipeline Orchestrator
==================================
Runs the full news processing pipeline: scrape -> cluster -> synthesize

Usage:
    python run.py              # Run full pipeline
    python run.py --scrape     # Only scrape
    python run.py --cluster    # Only cluster
    python run.py --synthesize # Only synthesize
    python run.py --serve      # Start web server
    python run.py --full       # Run pipeline then start server
"""

import argparse
import sys
import time
from datetime import datetime

# =============================================================================
# PIPELINE CONFIG (can override config.py settings here)
# =============================================================================
from config import REFRESH_INTERVAL_HOURS

import database
import scraper
import clusterer
import synthesizer

# =============================================================================
# PIPELINE FUNCTIONS
# =============================================================================

def print_banner():
    """Print startup banner."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   📰 NEWS BENCH                                           ║
║   Neutral News Aggregator & Analyzer                      ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


def run_scrape():
    """Run the scraping step."""
    print("\n📥 STEP 1: Scraping news sources...")
    print("-" * 50)
    scraper.scrape_all_sources()


def run_cluster():
    """Run the clustering step."""
    print("\n🔗 STEP 2: Clustering related articles...")
    print("-" * 50)
    return clusterer.run_clustering()


def run_synthesize(clusters=None):
    """Run the synthesis step."""
    print("\n✍️  STEP 3: Synthesizing stories with AI...")
    print("-" * 50)
    synthesizer.run_synthesis(clusters)


def run_pipeline():
    """Run the full pipeline: scrape -> cluster -> synthesize."""
    start_time = time.time()
    print_banner()

    print(f"Starting pipeline at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize database
    database.init_database()

    # Step 1: Scrape
    run_scrape()

    # Step 2: Cluster
    clusters = run_cluster()

    # Step 3: Synthesize (if we have clusters)
    if clusters:
        run_synthesize(clusters)
    else:
        print("\n⚠️  No new clusters to synthesize")

    # Summary
    elapsed = time.time() - start_time
    stats = database.get_stats()

    print("\n" + "=" * 60)
    print("📊 PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Total articles: {stats['total_articles']}")
    print(f"  Total stories:  {stats['total_stories']}")
    print(f"  Sources:        {stats['unique_sources']}")
    print(f"  Time elapsed:   {elapsed:.1f} seconds")
    print("=" * 60)
    print("\n✅ Done! Run 'python app.py' to start the web interface.\n")


def run_server():
    """Start the Flask web server."""
    import app
    app.main()


def run_full():
    """Run pipeline then start server."""
    run_pipeline()
    print("\n🌐 Starting web server...")
    run_server()


def show_stats():
    """Show current database statistics."""
    database.init_database()
    stats = database.get_stats()

    print("\n📊 News Bench Statistics")
    print("-" * 40)
    print(f"  Total articles:     {stats['total_articles']}")
    print(f"  Total stories:      {stats['total_stories']}")
    print(f"  Unique sources:     {stats['unique_sources']}")
    print(f"  Last article:       {stats['last_article_at'] or 'Never'}")
    print(f"  Last story:         {stats['last_story_at'] or 'Never'}")
    print()


def cleanup(days: int = 7):
    """Clean up old data."""
    database.init_database()
    print(f"\n🗑️  Cleaning up data older than {days} days...")
    database.cleanup_old_data(days=days)
    print("Done!")


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="News Bench - Neutral News Aggregator Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                 Run full pipeline (scrape + cluster + synthesize)
  python run.py --serve         Start the web server only
  python run.py --full          Run pipeline then start server
  python run.py --scrape        Only scrape news sources
  python run.py --cluster       Only cluster recent articles
  python run.py --synthesize    Only synthesize new clusters
  python run.py --stats         Show database statistics
  python run.py --cleanup 7     Remove data older than 7 days
        """
    )

    parser.add_argument('--scrape', action='store_true', help='Only run scraping step')
    parser.add_argument('--cluster', action='store_true', help='Only run clustering step')
    parser.add_argument('--synthesize', action='store_true', help='Only run synthesis step')
    parser.add_argument('--serve', action='store_true', help='Start web server')
    parser.add_argument('--full', action='store_true', help='Run pipeline then start server')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    parser.add_argument('--cleanup', type=int, metavar='DAYS', help='Remove data older than N days')

    args = parser.parse_args()

    # Handle specific commands
    if args.stats:
        show_stats()
    elif args.cleanup:
        cleanup(args.cleanup)
    elif args.scrape:
        print_banner()
        database.init_database()
        run_scrape()
    elif args.cluster:
        print_banner()
        database.init_database()
        run_cluster()
    elif args.synthesize:
        print_banner()
        database.init_database()
        run_synthesize()
    elif args.serve:
        run_server()
    elif args.full:
        run_full()
    else:
        # Default: run full pipeline
        run_pipeline()


if __name__ == "__main__":
    main()
