#!/usr/bin/env python3
"""
Startup script for Render deployment.
Starts gunicorn immediately - app.py handles background pipeline if needed.
"""
import os

def main():
    # Start gunicorn IMMEDIATELY so Render sees the port
    # app.py handles database init and background pipeline
    port = os.environ.get('PORT', '10000')
    print(f"[STARTUP] Starting gunicorn on port {port}...")

    cmd = [
        'gunicorn', 'app:app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '1',      # Single worker to avoid duplicate pipelines/schedulers
        '--threads', '4',
        '--timeout', '120',
        '--preload'            # Load app once before forking
    ]

    os.execvp('gunicorn', cmd)

if __name__ == '__main__':
    main()
