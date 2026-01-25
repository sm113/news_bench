"""
News Bench - Article Clusterer
==============================
Generates embeddings for articles and clusters related stories using cosine similarity.
"""

import pickle
import numpy as np
from typing import List, Dict, Tuple, Set
from collections import defaultdict

# =============================================================================
# CLUSTERING CONFIG (can override config.py settings here)
# =============================================================================
from config import (
    EMBEDDING_MODEL,
    SIMILARITY_THRESHOLD,
    MIN_SOURCES_FOR_STORY,
    MAX_ARTICLES_FOR_CLUSTERING,
    CLUSTERING_WINDOW_HOURS
)
import database

# Lazy load the sentence transformer model
_model = None

def get_model():
    """Lazy load the sentence transformer model."""
    global _model
    if _model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL}...")
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBEDDING_MODEL)
            print("Model loaded!")
        except ImportError:
            print("ERROR: sentence-transformers not installed!")
            print("Run: pip install sentence-transformers")
            raise SystemExit(1)
        except Exception as e:
            print(f"ERROR loading model: {e}")
            raise
    return _model


# =============================================================================
# EMBEDDING FUNCTIONS
# =============================================================================

def generate_embedding(text: str) -> np.ndarray:
    """Generate embedding for a single text."""
    model = get_model()
    return model.encode(text, convert_to_numpy=True)


def generate_embeddings_batch(texts: List[str], batch_size: int = 32) -> np.ndarray:
    """Generate embeddings for multiple texts efficiently."""
    model = get_model()
    return model.encode(texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=True)


def embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Convert numpy array to bytes for storage."""
    return pickle.dumps(embedding)


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Convert stored bytes back to numpy array."""
    return pickle.loads(data)


def compute_article_text(article: Dict) -> str:
    """Combine headline and lede for embedding."""
    headline = article.get('headline', '')
    lede = article.get('lede', '')
    return f"{headline}. {lede}" if lede else headline


# =============================================================================
# EMBEDDING STORAGE
# =============================================================================

def embed_new_articles():
    """Generate and store embeddings for articles that don't have them."""
    print("\nGenerating embeddings for new articles...")

    articles = database.get_articles_without_embedding(limit=MAX_ARTICLES_FOR_CLUSTERING)
    if not articles:
        print("No new articles to embed")
        return 0

    print(f"Found {len(articles)} articles without embeddings")

    # Prepare texts
    texts = [compute_article_text(a) for a in articles]

    # Generate embeddings in batch
    embeddings = generate_embeddings_batch(texts)

    # Store embeddings
    for article, embedding in zip(articles, embeddings):
        database.update_article_embedding(article['id'], embedding_to_bytes(embedding))

    print(f"Generated embeddings for {len(articles)} articles")
    return len(articles)


# =============================================================================
# CLUSTERING FUNCTIONS
# =============================================================================

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def build_similarity_matrix(embeddings: List[np.ndarray]) -> np.ndarray:
    """Build a pairwise cosine similarity matrix."""
    n = len(embeddings)
    matrix = np.zeros((n, n))

    # Normalize embeddings for faster computation
    normalized = np.array([e / np.linalg.norm(e) for e in embeddings])

    # Compute similarity matrix
    matrix = np.dot(normalized, normalized.T)

    return matrix


def cluster_articles(
    articles: List[Dict],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_sources: int = MIN_SOURCES_FOR_STORY
) -> List[List[Dict]]:
    """
    Cluster articles by similarity.
    Returns list of clusters, each cluster is a list of related articles.
    """
    if not articles:
        return []

    print(f"\nClustering {len(articles)} articles...")
    print(f"  Similarity threshold: {similarity_threshold}")
    print(f"  Min sources per story: {min_sources}")

    # Extract embeddings
    embeddings = []
    valid_articles = []
    for article in articles:
        if article.get('embedding'):
            try:
                emb = bytes_to_embedding(article['embedding'])
                embeddings.append(emb)
                valid_articles.append(article)
            except Exception as e:
                print(f"  Warning: Could not load embedding for article {article['id']}: {e}")

    if len(valid_articles) < 2:
        print("  Not enough articles with embeddings to cluster")
        return []

    print(f"  {len(valid_articles)} articles have valid embeddings")

    # Build similarity matrix
    similarity_matrix = build_similarity_matrix(embeddings)

    # Greedy clustering
    n = len(valid_articles)
    clustered = set()
    clusters = []

    # Sort article pairs by similarity (highest first)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if similarity_matrix[i, j] >= similarity_threshold:
                pairs.append((i, j, similarity_matrix[i, j]))

    pairs.sort(key=lambda x: -x[2])  # Sort by similarity descending

    # Build clusters greedily
    article_to_cluster = {}

    for i, j, sim in pairs:
        cluster_i = article_to_cluster.get(i)
        cluster_j = article_to_cluster.get(j)

        if cluster_i is None and cluster_j is None:
            # Start new cluster
            new_cluster_idx = len(clusters)
            clusters.append({i, j})
            article_to_cluster[i] = new_cluster_idx
            article_to_cluster[j] = new_cluster_idx
        elif cluster_i is not None and cluster_j is None:
            # Add j to i's cluster
            clusters[cluster_i].add(j)
            article_to_cluster[j] = cluster_i
        elif cluster_i is None and cluster_j is not None:
            # Add i to j's cluster
            clusters[cluster_j].add(i)
            article_to_cluster[i] = cluster_j
        elif cluster_i != cluster_j:
            # Merge clusters (add smaller to larger)
            if len(clusters[cluster_i]) >= len(clusters[cluster_j]):
                clusters[cluster_i].update(clusters[cluster_j])
                for idx in clusters[cluster_j]:
                    article_to_cluster[idx] = cluster_i
                clusters[cluster_j] = set()  # Mark as merged
            else:
                clusters[cluster_j].update(clusters[cluster_i])
                for idx in clusters[cluster_i]:
                    article_to_cluster[idx] = cluster_j
                clusters[cluster_i] = set()  # Mark as merged

    # Filter and convert clusters
    result_clusters = []
    for cluster_indices in clusters:
        if not cluster_indices:
            continue

        cluster_articles = [valid_articles[i] for i in cluster_indices]

        # Check minimum sources requirement
        unique_sources = set(a['source_name'] for a in cluster_articles)
        if len(unique_sources) >= min_sources:
            result_clusters.append(cluster_articles)

    # Sort clusters by size (largest first)
    result_clusters.sort(key=lambda x: -len(x))

    print(f"  Found {len(result_clusters)} clusters meeting criteria")

    return result_clusters


# =============================================================================
# MAIN CLUSTERING PIPELINE
# =============================================================================

def run_clustering() -> List[List[Dict]]:
    """
    Main clustering pipeline:
    1. Embed new articles
    2. Get recent articles with embeddings
    3. Filter to unclustered articles
    4. Cluster them
    """
    print("\n" + "="*60)
    print("NEWS BENCH - Article Clustering")
    print("="*60)

    # Step 1: Embed any new articles
    embed_new_articles()

    # Step 2: Get unclustered article IDs
    unclustered_ids = set(database.get_unclustered_article_ids(hours=CLUSTERING_WINDOW_HOURS))
    print(f"\nFound {len(unclustered_ids)} unclustered articles")

    if not unclustered_ids:
        print("No new articles to cluster")
        return []

    # Step 3: Get articles with embeddings
    all_articles = database.get_articles_with_embeddings(hours=CLUSTERING_WINDOW_HOURS)

    # Filter to only unclustered
    articles_to_cluster = [a for a in all_articles if a['id'] in unclustered_ids]
    print(f"Processing {len(articles_to_cluster)} articles for clustering")

    # Step 4: Cluster
    clusters = cluster_articles(articles_to_cluster)

    print("\n" + "="*60)
    print(f"Clustering complete! Found {len(clusters)} story clusters")
    print("="*60 + "\n")

    # Print cluster summaries
    for i, cluster in enumerate(clusters[:10]):  # Show first 10
        sources = set(a['source_name'] for a in cluster)
        print(f"\nCluster {i+1} ({len(cluster)} articles from {len(sources)} sources):")
        print(f"  Sources: {', '.join(sorted(sources))}")
        print(f"  Sample headline: {cluster[0]['headline'][:80]}...")

    return clusters


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cluster related news articles")
    parser.add_argument('--embed-only', action='store_true', help="Only generate embeddings, don't cluster")
    parser.add_argument('--threshold', type=float, default=SIMILARITY_THRESHOLD,
                        help=f"Similarity threshold (default: {SIMILARITY_THRESHOLD})")
    parser.add_argument('--min-sources', type=int, default=MIN_SOURCES_FOR_STORY,
                        help=f"Minimum sources per story (default: {MIN_SOURCES_FOR_STORY})")
    args = parser.parse_args()

    database.init_database()

    if args.embed_only:
        embed_new_articles()
    else:
        # Override config if specified
        clusters = cluster_articles(
            database.get_articles_with_embeddings(hours=CLUSTERING_WINDOW_HOURS),
            similarity_threshold=args.threshold,
            min_sources=args.min_sources
        )
