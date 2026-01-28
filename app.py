"""
News Bench - Flask Web Application
==================================
Simple web interface for browsing synthesized news stories.
"""

from flask import Flask, render_template, jsonify, request, make_response
from flask_cors import CORS
from datetime import datetime
import os

from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG, STORIES_PER_PAGE
import database

# =============================================================================
# FLASK APP SETUP
# =============================================================================

app = Flask(__name__)
CORS(app)

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

    stories = database.get_stories(limit=limit, offset=offset)
    for story in stories:
        story['sources'] = database.get_sources_for_story(story['id'])
        story['time_ago'] = format_timestamp(story['created_at'])

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
