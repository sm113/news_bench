"""
News Bench - Central Configuration
===================================
All configuration variables in one place. Edit these to customize behavior.
"""

# =============================================================================
# NEWS SOURCES CONFIG
# =============================================================================
# Easy to add/remove sources. Each source needs:
#   - name: Display name
#   - url: RSS feed URL
#   - lean: Political lean ("left", "center", "right", "international")
#
# Note: Some RSS feeds may require different parsing. Test after adding new sources.

NEWS_SOURCES = [
    # === Wire Services / Center ===
    {"name": "AP News", "url": "https://rsshub.app/apnews/topics/apf-topnews", "lean": "center"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best", "lean": "center"},
    {"name": "PBS NewsHour", "url": "https://www.pbs.org/newshour/feeds/rss/headlines", "lean": "center"},
    {"name": "The Hill", "url": "https://thehill.com/feed/", "lean": "center"},
    {"name": "Axios", "url": "https://api.axios.com/feed/", "lean": "center"},
    {"name": "USA Today", "url": "https://rssfeeds.usatoday.com/usatoday-NewsTopStories", "lean": "center"},

    # === Left-leaning ===
    {"name": "NPR", "url": "https://feeds.npr.org/1001/rss.xml", "lean": "left"},
    {"name": "The Guardian", "url": "https://www.theguardian.com/us-news/rss", "lean": "left"},
    {"name": "MSNBC", "url": "https://www.msnbc.com/feeds/latest", "lean": "left"},
    {"name": "Washington Post", "url": "https://feeds.washingtonpost.com/rss/politics", "lean": "left"},
    {"name": "NY Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "lean": "left"},
    {"name": "Vox", "url": "https://www.vox.com/rss/index.xml", "lean": "left"},
    {"name": "HuffPost", "url": "https://www.huffpost.com/section/politics/feed", "lean": "left"},
    {"name": "Slate", "url": "https://slate.com/feeds/all.rss", "lean": "left"},

    # === Right-leaning ===
    {"name": "Fox News", "url": "https://moxie.foxnews.com/google-publisher/politics.xml", "lean": "right"},
    {"name": "NY Post", "url": "https://nypost.com/news/feed/", "lean": "right"},
    {"name": "Washington Times", "url": "https://www.washingtontimes.com/rss/headlines/news/politics/", "lean": "right"},
    {"name": "Daily Wire", "url": "https://www.dailywire.com/feeds/rss.xml", "lean": "right"},
    {"name": "Breitbart", "url": "https://feeds.feedburner.com/breitbart", "lean": "right"},
    {"name": "The Federalist", "url": "https://thefederalist.com/feed/", "lean": "right"},
    {"name": "National Review", "url": "https://www.nationalreview.com/feed/", "lean": "right"},
    {"name": "Washington Examiner", "url": "https://www.washingtonexaminer.com/feed", "lean": "right"},

    # === International ===
    {"name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "lean": "international"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "lean": "international"},
    {"name": "DW News", "url": "https://rss.dw.com/rdf/rss-en-all", "lean": "international"},
    {"name": "France24", "url": "https://www.france24.com/en/rss", "lean": "international"},
    {"name": "The Economist", "url": "https://www.economist.com/united-states/rss.xml", "lean": "international"},
    {"name": "Sky News", "url": "https://feeds.skynews.com/feeds/rss/world.xml", "lean": "international"},
]

# =============================================================================
# CLUSTERING CONFIG
# =============================================================================
# Controls how articles are grouped into stories

# Sentence transformer model for generating embeddings
# Options: "all-MiniLM-L6-v2" (fast), "all-mpnet-base-v2" (better), "bge-base-en-v1.5"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Cosine similarity threshold for clustering (0.0 - 1.0)
# Higher = stricter matching, fewer clusters
# Lower = looser matching, more articles grouped together
SIMILARITY_THRESHOLD = 0.60  # Slightly looser to catch more related articles

# Minimum number of different sources required for a story to be included
# Helps filter out stories only covered by one outlet
MIN_SOURCES_FOR_STORY = 2

# Maximum articles to consider for clustering (performance)
MAX_ARTICLES_FOR_CLUSTERING = 1000  # Doubled capacity

# How many hours back to look for articles to cluster
CLUSTERING_WINDOW_HOURS = 96  # 4 days instead of 2

# =============================================================================
# SYNTHESIS CONFIG
# =============================================================================
# Controls LLM-based summary generation

# LLM model to use
# For Ollama: "llama3.1:8b", "llama3.1:70b", "mistral:7b", "mixtral:8x7b"
# For Groq: "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"
# For Together: "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
LLM_MODEL = "llama-3.3-70b-versatile"

# LLM provider: "ollama" (local), "groq", "together"
LLM_PROVIDER = "groq"

# API keys (only needed for cloud providers)
# Get your free Groq key at: https://console.groq.com/keys
# In production, set GROQ_API_KEY environment variable instead
import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # Set via environment variable
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")  # Get from https://api.together.xyz/

# Ollama settings
OLLAMA_HOST = "http://localhost:11434"

# Generation parameters
MAX_TOKENS = 3000  # Max length of generated summaries (doubled for deeper analysis)
TEMPERATURE = 0.3  # Lower = more deterministic (0.0 - 1.0)

# Retry settings for API calls
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 2  # seconds

# =============================================================================
# APP CONFIG
# =============================================================================
# Web application settings

# How often to automatically refresh data (in hours)
REFRESH_INTERVAL_HOURS = 6

# Maximum stories to keep in the database
MAX_STORIES_IN_FEED = 100  # More stories in the feed

# Stories per page for pagination
STORIES_PER_PAGE = 12  # More per page

# Flask settings
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = True

# =============================================================================
# DATABASE CONFIG
# =============================================================================
# SQLite database settings
# In production (Render), uses /data mount for persistence

# Check for Render disk mount first, then fall back to local
if os.path.exists("/data"):
    DATABASE_PATH = "/data/news_bench.db"
else:
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), "news_bench.db")

# =============================================================================
# SCRAPING CONFIG
# =============================================================================
# RSS feed scraping settings

# Request timeout in seconds
REQUEST_TIMEOUT = 15

# User agent for requests
USER_AGENT = "NewsBench/1.0 (News Aggregator; +https://github.com/news-bench)"

# Delay between requests to same domain (seconds)
REQUEST_DELAY = 1.0

# Maximum age of articles to scrape (hours)
MAX_ARTICLE_AGE_HOURS = 120  # 5 days for more comprehensive coverage
