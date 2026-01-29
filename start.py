#!/usr/bin/env python3
"""
Startup script for Render deployment.
Runs the full pipeline if no stories exist, then starts gunicorn.
"""
import os
import sys

def main():
    port = os.environ.get('PORT', '10000')

    # Initialize database
    print("[START] Initializing database...")
    import database
    database.init_database()

    # Check if we have data
    stats = database.get_stats()
    print(f"[START] Current: {stats['total_articles']} articles, {stats['total_stories']} stories")

    # If no stories exist, run the FULL pipeline
    if stats['total_stories'] == 0:
        print("[START] No stories - running full pipeline...")
        try:
            # Step 1: Scrape articles (if needed)
            if stats['total_articles'] == 0:
                print("[START] Step 1: Scraping articles...")
                import scraper
                scraper.scrape_all_sources()
                stats = database.get_stats()
                print(f"[START] Scraper done: {stats['total_articles']} articles")
            else:
                print(f"[START] Step 1: Skipped scraping ({stats['total_articles']} articles exist)")

            # Step 2: Cluster articles
            print("[START] Step 2: Clustering articles...")
            import clusterer
            clusters = clusterer.run_clustering()
            print(f"[START] Clustering done: {len(clusters) if clusters else 0} clusters")

            # Step 3: Synthesize stories
            if clusters:
                print("[START] Step 3: Synthesizing stories...")
                import synthesizer
                story_ids = synthesizer.run_synthesis(clusters)
                print(f"[START] Synthesis done: {len(story_ids)} stories created")
            else:
                print("[START] Step 3: Skipped synthesis (no clusters)")

            stats = database.get_stats()
            print(f"[START] Pipeline complete: {stats['total_articles']} articles, {stats['total_stories']} stories")

        except Exception as e:
            import traceback
            print(f"[START] Pipeline error: {e}")
            traceback.print_exc()
            print("[START] Continuing with server startup...")

    # Start gunicorn with longer timeout for refresh requests
    print(f"[START] Starting gunicorn on port {port}...")
    os.execvp('gunicorn', [
        'gunicorn', 'app:app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '1',
        '--threads', '2',
        '--timeout', '300'  # 5 minutes for heavy operations
    ])

if __name__ == '__main__':
    main()
