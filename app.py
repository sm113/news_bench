"""
News Bench - Flask Web Application
==================================
Web interface for browsing synthesized news stories.
Includes automatic scheduled updates for mobile deployment.
"""

from flask import Flask, render_template, jsonify, request, make_response
from datetime import datetime
import threading
import os
import atexit

# =============================================================================
# APP CONFIG (can override config.py settings here)
# =============================================================================
from config import (
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    STORIES_PER_PAGE,
    MAX_STORIES_IN_FEED
)
import database

# =============================================================================
# FLASK APP SETUP
# =============================================================================

app = Flask(__name__)

# =============================================================================
# SCHEDULED TASKS (APScheduler)
# =============================================================================

scheduler = None

def run_pipeline_job():
    """Background job to refresh news data."""
    print(f"\n[SCHEDULER] Starting pipeline job at {datetime.now().isoformat()}")
    try:
        import scraper
        import clusterer
        import synthesizer

        scraper.scrape_all_sources()
        clusters = clusterer.run_clustering()
        synthesizer.run_synthesis(clusters)

        print(f"[SCHEDULER] Pipeline completed at {datetime.now().isoformat()}")
    except Exception as e:
        print(f"[SCHEDULER] Pipeline error: {e}")

def init_scheduler():
    """Initialize APScheduler for periodic updates."""
    global scheduler

    # Only run scheduler in production or if explicitly enabled
    if os.environ.get('ENABLE_SCHEDULER', 'false').lower() != 'true':
        print("[SCHEDULER] Disabled (set ENABLE_SCHEDULER=true to enable)")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BackgroundScheduler()

        # Run pipeline every 12 hours
        scheduler.add_job(
            func=run_pipeline_job,
            trigger=IntervalTrigger(hours=12),
            id='news_pipeline',
            name='Refresh news pipeline',
            replace_existing=True
        )

        scheduler.start()
        print("[SCHEDULER] Started - pipeline will run every 12 hours")

        # Shut down scheduler when app exits
        atexit.register(lambda: scheduler.shutdown())

    except ImportError:
        print("[SCHEDULER] APScheduler not installed - run: pip install apscheduler")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_timestamp(iso_string: str) -> str:
    """Format ISO timestamp to human-readable string."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string)
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                minutes = diff.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "Just now"
            return f"{hours}h ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def group_sources_by_lean(sources: list) -> dict:
    """Group source articles by political lean."""
    grouped = {
        'left': [],
        'center': [],
        'right': [],
        'international': []
    }
    for source in sources:
        lean = source.get('source_lean', 'center')
        if lean in grouped:
            grouped[lean].append(source)
        else:
            grouped['center'].append(source)
    return grouped


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Main feed page."""
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * STORIES_PER_PAGE

    stories = database.get_stories(limit=STORIES_PER_PAGE, offset=offset)
    total_stories = database.get_stories_count()
    total_pages = (total_stories + STORIES_PER_PAGE - 1) // STORIES_PER_PAGE

    # Add sources and formatting to each story
    for story in stories:
        story['sources'] = database.get_sources_for_story(story['id'])
        story['sources_grouped'] = group_sources_by_lean(story['sources'])
        story['time_ago'] = format_timestamp(story['created_at'])

    stats = database.get_stats()
    stats['last_updated'] = format_timestamp(stats.get('last_story_at'))

    return render_template('index.html',
                           stories=stories,
                           page=page,
                           total_pages=total_pages,
                           stats=stats)


@app.route('/story/<int:story_id>')
def story_detail(story_id: int):
    """Single story detail view."""
    story = database.get_story_with_sources(story_id)
    if not story:
        return "Story not found", 404

    story['sources_grouped'] = group_sources_by_lean(story['sources'])
    story['time_ago'] = format_timestamp(story['created_at'])

    return render_template('index.html',
                           story=story,
                           single_view=True,
                           stats=database.get_stats())


@app.route('/api/stories')
def api_stories():
    """API endpoint for stories with cache headers for mobile."""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', STORIES_PER_PAGE, type=int)
    offset = (page - 1) * limit

    stories = database.get_stories(limit=limit, offset=offset)
    for story in stories:
        story['sources'] = database.get_sources_for_story(story['id'])
        story['time_ago'] = format_timestamp(story['created_at'])

    stats = database.get_stats()

    response = make_response(jsonify({
        'stories': stories,
        'page': page,
        'total': database.get_stories_count(),
        'last_updated': stats.get('last_story_at')
    }))

    # Cache for 5 minutes on mobile to reduce API calls
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@app.route('/api/story/<int:story_id>')
def api_story(story_id: int):
    """API endpoint for single story."""
    story = database.get_story_with_sources(story_id)
    if not story:
        return jsonify({'error': 'Not found'}), 404
    story['time_ago'] = format_timestamp(story['created_at'])
    return jsonify(story)


@app.route('/api/stats')
def api_stats():
    """API endpoint for database stats."""
    stats = database.get_stats()
    stats['last_updated'] = format_timestamp(stats.get('last_story_at'))
    return jsonify(stats)


@app.route('/api/health')
def api_health():
    """Health check endpoint for deployment monitoring."""
    try:
        stats = database.get_stats()
        return jsonify({
            'status': 'healthy',
            'stories': stats['total_stories'],
            'last_update': stats.get('last_story_at'),
            'scheduler_enabled': scheduler is not None and scheduler.running if scheduler else False
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/api/last-updated')
def api_last_updated():
    """Lightweight endpoint for mobile to check if data changed."""
    stats = database.get_stats()
    response = make_response(jsonify({
        'last_story_at': stats.get('last_story_at'),
        'total_stories': stats['total_stories']
    }))
    # Very short cache - just to debounce rapid requests
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Trigger a background refresh."""
    def background_refresh():
        import scraper
        import clusterer
        import synthesizer
        scraper.scrape_all_sources()
        clusters = clusterer.run_clustering()
        synthesizer.run_synthesis(clusters)

    thread = threading.Thread(target=background_refresh)
    thread.start()

    return jsonify({'status': 'Refresh started'})


# =============================================================================
# TEMPLATE FILTERS
# =============================================================================

@app.template_filter('lean_color')
def lean_color(lean: str) -> str:
    """Return CSS class for political lean."""
    colors = {
        'left': 'lean-left',
        'center': 'lean-center',
        'right': 'lean-right',
        'international': 'lean-international'
    }
    return colors.get(lean, 'lean-center')


@app.template_filter('lean_dot')
def lean_dot(lean: str) -> str:
    """Return dot color for political lean."""
    dots = {
        'left': '#5dade2',      # Light blue
        'center': '#95a5a6',    # Gray
        'right': '#e74c3c',     # Light red
        'international': '#58d68d'  # Light green
    }
    return dots.get(lean, '#95a5a6')


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run the Flask application."""
    database.init_database()
    init_scheduler()

    # Get host/port from environment for deployment flexibility
    host = os.environ.get('HOST', FLASK_HOST)
    port = int(os.environ.get('PORT', FLASK_PORT))
    debug = os.environ.get('DEBUG', str(FLASK_DEBUG)).lower() == 'true'

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   📰 NEWS BENCH                                           ║
║   Neutral News Aggregator                                 ║
║                                                           ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║   Server: http://{host}:{port}
║   Scheduler: {'ENABLED' if os.environ.get('ENABLE_SCHEDULER') == 'true' else 'DISABLED'}
║                                                           ║
║   API Endpoints:                                          ║
║     GET /api/stories      - Fetch stories                 ║
║     GET /api/last-updated - Check for new content         ║
║     GET /api/health       - Health check                  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

    stats = database.get_stats()
    if stats['total_stories'] == 0:
        print("⚠️  No stories yet! Run: python run.py")

    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
