"""
News Bench - Article Clusterer
==============================
Generates embeddings via Jina AI API and clusters related stories using cosine similarity.
"""

import pickle
import os
import time
import numpy as np
import requests
from typing import List, Dict, Optional

# =============================================================================
# CLUSTERING CONFIG
# =============================================================================
from config import (
    SIMILARITY_THRESHOLD,
    MIN_SOURCES_FOR_STORY,
    MAX_ARTICLES_FOR_CLUSTERING,
    CLUSTERING_WINDOW_HOURS
)
import database

# Jina AI API config (free tier: 1M tokens/month)
JINA_API_KEY = os.environ.get('JINA_API_KEY', '')
JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
EMBEDDING_BATCH_SIZE = 100  # Jina allows up to 2048 per request

# =============================================================================
# JINA AI EMBEDDING FUNCTIONS
# =============================================================================

def generate_embeddings_batch(texts: List[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> Optional[np.ndarray]:
    """Generate embeddings using Jina AI API."""
    if not JINA_API_KEY:
        print("ERROR: JINA_API_KEY not set!")
        print("Get a free API key at: https://jina.ai/embeddings/")
        return None

    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} ({len(batch)} texts)...")

        try:
            response = requests.post(
                JINA_API_URL,
                headers={
                    "Authorization": f"Bearer {JINA_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": JINA_MODEL,
                    "task": "text-matching",
                    "dimensions": 512,
                    "input": batch
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            # Extract embeddings in order
            batch_embeddings = [item['embedding'] for item in data['data']]
            all_embeddings.extend(batch_embeddings)

            # Rate limiting - be nice to the API
            if i + batch_size < len(texts):
                time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            print(f"  Jina API error: {e}")
            return None
        except (KeyError, IndexError) as e:
            print(f"  Error parsing Jina response: {e}")
            return None

    return np.array(all_embeddings)


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
    # Limit text length to save API tokens
    combined = f"{headline}. {lede[:500]}" if lede else headline
    return combined[:1000]


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

    # Generate embeddings via API
    embeddings = generate_embeddings_batch(texts)

    if embeddings is None:
        print("Failed to generate embeddings")
        return 0

    # Store embeddings
    for article, embedding in zip(articles, embeddings):
        database.update_article_embedding(article['id'], embedding_to_bytes(embedding))

    print(f"Generated embeddings for {len(articles)} articles")
    return len(articles)


# =============================================================================
# CLUSTERING FUNCTIONS
# =============================================================================

def build_similarity_matrix(embeddings: List[np.ndarray]) -> np.ndarray:
    """Build a pairwise cosine similarity matrix."""
    # Normalize embeddings for faster computation
    normalized = np.array([e / np.linalg.norm(e) for e in embeddings])
    # Compute similarity matrix
    return np.dot(normalized, normalized.T)


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
    1. Embed new articles via Jina AI API
    2. Get recent articles with embeddings
    3. Filter to unclustered articles
    4. Cluster them
    """
    print("\n" + "="*60)
    print("NEWS BENCH - Article Clustering (Jina AI)")
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
        clusters = cluster_articles(
            database.get_articles_with_embeddings(hours=CLUSTERING_WINDOW_HOURS),
            similarity_threshold=args.threshold,
            min_sources=args.min_sources
        )
