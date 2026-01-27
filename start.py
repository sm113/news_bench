#!/usr/bin/env python3
"""
Startup script for Render deployment.
Runs the pipeline if database is empty, then starts gunicorn.
"""
import os
import subprocess
import sys

import database

def main():
    print("[STARTUP] Initializing database...")
    database.init_database()

    stats = database.get_stats()
    print(f"[STARTUP] Current stats: {stats['total_stories']} stories")

    if stats['total_stories'] == 0:
        print("[STARTUP] No data found - running pipeline...")
        print("[STARTUP] This will take several minutes on first deploy.")

        import run
        run.run_pipeline()

        print("[STARTUP] Pipeline complete!")
    else:
        print("[STARTUP] Data exists, skipping pipeline.")

    # Start gunicorn
    port = os.environ.get('PORT', '10000')
    print(f"[STARTUP] Starting gunicorn on port {port}...")

    cmd = [
        'gunicorn', 'app:app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '2',
        '--threads', '4',
        '--timeout', '120'
    ]

    os.execvp('gunicorn', cmd)

if __name__ == '__main__':
    main()
