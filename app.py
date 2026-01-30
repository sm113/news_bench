"""
Lucid - Flask Web Application
============================
Simple web interface for browsing synthesized news stories.
"""

from flask import Flask, render_template, jsonify, request, make_response
from flask_cors import CORS
from datetime import datetime
import os
import atexit

from config import (
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG, STORIES_PER_PAGE, REFRESH_INTERVAL_HOURS,
    RELEVANCE_WEIGHT_SOURCES, RELEVANCE_WEIGHT_DIVERSITY, RELEVANCE_WEIGHT_RECENCY, RELEVANCE_BASE_SCORE
)
import database

# =============================================================================
# FLASK APP SETUP
# =============================================================================

app = Flask(__name__)
CORS(app)

# =============================================================================
# BACKGROUND SCHEDULER (for periodic pipeline runs)
# =============================================================================

scheduler = None

def run_pipeline_job():
    """Background job to run the news pipeline."""
    print("[SCHEDULER] Starting scheduled pipeline run...")
    try:
        import scraper
        import clusterer
        import synthesizer

        scraper.scrape_all_sources()
        clusters = clusterer.run_clustering()
        if clusters:
            synthesizer.run_synthesis(clusters)

        stats = database.get_stats()
        print(f"[SCHEDULER] Pipeline complete: {stats['total_articles']} articles, {stats['total_stories']} stories")
    except Exception as e:
        print(f"[SCHEDULER] Pipeline error: {e}")

def init_scheduler():
    """Initialize the background scheduler if enabled."""
    global scheduler
    if os.environ.get('ENABLE_SCHEDULER', '').lower() != 'true':
        print("[SCHEDULER] Disabled (set ENABLE_SCHEDULER=true to enable)")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime, timedelta

        scheduler = BackgroundScheduler()

        # Run pipeline 60 seconds after startup (gives time for health check)
        scheduler.add_job(
            run_pipeline_job,
            'date',
            run_date=datetime.now() + timedelta(seconds=60),
            id='initial_pipeline'
        )

        # Then run every REFRESH_INTERVAL_HOURS
        scheduler.add_job(
            run_pipeline_job,
            'interval',
            hours=REFRESH_INTERVAL_HOURS,
            id='news_pipeline',
            replace_existing=True
        )

        scheduler.start()
        print(f"[SCHEDULER] Started - initial run in 60s, then every {REFRESH_INTERVAL_HOURS} hours")
        atexit.register(lambda: scheduler.shutdown())
    except Exception as e:
        print(f"[SCHEDULER] Failed to start: {e}")

# Initialize scheduler when app starts
init_scheduler()

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
    grouped = {'left': [], 'center': [], 'right': [], 'international': []}
    for source in sources:
        lean = source.get('source_lean', 'center')
        if lean in grouped:
            grouped[lean].append(source)
        else:
            grouped['center'].append(source)
    return grouped


def calculate_relevance_score(story: dict, sources: list) -> int:
    """
    Calculate relevance score for a story based on:
    - Number of sources covering it
    - Diversity of political leans
    - Recency
    """
    score = RELEVANCE_BASE_SCORE

    # Source count bonus (more sources = bigger story)
    source_count = len(sources)
    score += source_count * RELEVANCE_WEIGHT_SOURCES

    # Lean diversity bonus (coverage across spectrum = significant story)
    unique_leans = set(s.get('source_lean', 'center') for s in sources)
    score += len(unique_leans) * RELEVANCE_WEIGHT_DIVERSITY

    # Recency penalty (older stories rank lower)
    try:
        created = datetime.fromisoformat(story.get('created_at', ''))
        hours_old = (datetime.now() - created).total_seconds() / 3600
        score -= int(hours_old * RELEVANCE_WEIGHT_RECENCY)
    except (ValueError, TypeError):
        pass

    return max(0, min(100, score))  # Clamp between 0-100


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
    total_pages = (total_stories + STORIES_PER_PAGE - 1) // STORIES_PER_PAGE if total_stories > 0 else 1

    for story in stories:
        story['sources'] = database.get_sources_for_story(story['id'])
        story['sources_grouped'] = group_sources_by_lean(story['sources'])
        story['time_ago'] = format_timestamp(story['created_at'])
        story['relevance_score'] = calculate_relevance_score(story, story['sources'])

    # Sort by relevance score (highest first)
    stories.sort(key=lambda s: s['relevance_score'], reverse=True)

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
    """API endpoint for stories."""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', STORIES_PER_PAGE, type=int)
    offset = (page - 1) * limit

    # Get more stories than requested so we can sort by relevance, then paginate
    all_stories = database.get_stories(limit=1000, offset=0)
    for story in all_stories:
        story['sources'] = database.get_sources_for_story(story['id'])
        story['time_ago'] = format_timestamp(story['created_at'])
        story['relevance_score'] = calculate_relevance_score(story, story['sources'])

    # Sort by relevance score (highest first)
    all_stories.sort(key=lambda s: s['relevance_score'], reverse=True)

    # Paginate after sorting
    stories = all_stories[offset:offset + limit]

    return jsonify({
        'stories': stories,
        'page': page,
        'total': database.get_stories_count()
    })


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


@app.route('/api/last-updated')
def api_last_updated():
    """API endpoint for last update timestamp."""
    stats = database.get_stats()
    return jsonify({'last_story_at': stats.get('last_story_at')})


@app.route('/api/health')
def api_health():
    """Health check endpoint."""
    try:
        stats = database.get_stats()
        return jsonify({
            'status': 'healthy',
            'articles': stats['total_articles'],
            'stories': stats['total_stories']
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Manually trigger the news pipeline."""
    try:
        # Import and run pipeline components
        import scraper
        import clusterer
        import synthesizer

        print("[REFRESH] Starting manual pipeline...")
        scraper.scrape_all_sources()

        clusters = clusterer.run_clustering()
        if clusters:
            synthesizer.run_synthesis(clusters)

        stats = database.get_stats()
        print(f"[REFRESH] Complete! Articles: {stats['total_articles']}, Stories: {stats['total_stories']}")

        return jsonify({
            'status': 'completed',
            'articles': stats['total_articles'],
            'stories': stats['total_stories']
        })
    except Exception as e:
        print(f"[REFRESH] Error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


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
        'left': '#5dade2',
        'center': '#95a5a6',
        'right': '#e74c3c',
        'international': '#58d68d'
    }
    return dots.get(lean, '#95a5a6')


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    database.init_database()
    host = os.environ.get('HOST', FLASK_HOST)
    port = int(os.environ.get('PORT', FLASK_PORT))
    app.run(host=host, port=port, debug=FLASK_DEBUG)
