# ============================================
# Service - Topic Clustering
# ============================================

from __future__ import annotations

import time
from typing import Dict, List, Optional

import numpy as np
import structlog
from sklearn.cluster import KMeans

from app.ai_models.embedding_model import get_embedding_model
from app.database.prisma_client import get_db

logger = structlog.get_logger()


class ClusteringService:
    """
    Topic clustering service for research papers.
    Groups papers into semantic clusters using KMeans or HDBSCAN.
    Automatically labels clusters based on keyword extraction.
    """

    def __init__(self):
        self.embedding_model = get_embedding_model()
        self.db = get_db()

    async def run_clustering(
        self,
        algorithm: str = "kmeans",
        n_clusters: int = 5,
        min_cluster_size: int = 3,
        user_id: str | None = None,
    ) -> Dict:
        """
        Run topic clustering on all papers.

        Args:
            algorithm: Clustering algorithm ('kmeans' or 'hdbscan').
            n_clusters: Number of clusters (for kmeans).
            min_cluster_size: Minimum cluster size (for hdbscan).

        Returns:
            Dict with cluster info and assignments.
        """
        start_time = time.time()

        # Get average embeddings for each paper (scoped to user)
        paper_embeddings = await self._get_paper_embeddings(user_id=user_id)

        if len(paper_embeddings) < 2:
            raise ValueError("Need at least 2 papers for clustering")

        paper_ids = list(paper_embeddings.keys())
        embeddings = np.array(list(paper_embeddings.values()))

        # Run clustering
        if algorithm == "hdbscan":
            labels, cluster_centers = self._run_hdbscan(embeddings, min_cluster_size)
        else:
            n_clusters = min(n_clusters, len(paper_ids))
            labels, cluster_centers = self._run_kmeans(embeddings, n_clusters)

        # Clear existing clusters
        await self.db.papercluster.delete_many()
        await self.db.topiccluster.delete_many()

        # Create clusters and assign papers
        unique_labels = set(labels)
        unique_labels.discard(-1)  # Remove noise label from HDBSCAN

        clusters = []
        for cluster_idx in unique_labels:
            cluster_paper_indices = [i for i, l in enumerate(labels) if l == cluster_idx]
            cluster_paper_ids = [paper_ids[i] for i in cluster_paper_indices]

            # Generate cluster name and keywords
            cluster_texts = await self._get_paper_texts(cluster_paper_ids)
            cluster_name, keywords = self._generate_cluster_label(cluster_texts, cluster_idx)

            # Create cluster record
            cluster_record = await self.db.topiccluster.create(
                data={
                    "name": cluster_name,
                    "description": f"Topic cluster containing {len(cluster_paper_ids)} papers",
                    "keywords": keywords,
                    "paper_count": len(cluster_paper_ids),
                    "algorithm": algorithm,
                }
            )

            # Assign papers to cluster
            for pid in cluster_paper_ids:
                paper_index = paper_ids.index(pid)
                distance = None
                if cluster_centers is not None and cluster_idx < len(cluster_centers):
                    distance = float(np.linalg.norm(
                        embeddings[paper_index] - cluster_centers[cluster_idx]
                    ))

                await self.db.papercluster.create(
                    data={
                        "paper_id": pid,
                        "cluster_id": cluster_record.id,
                        "distance": distance,
                    }
                )

            clusters.append({
                "id": cluster_record.id,
                "name": cluster_name,
                "description": cluster_record.description,
                "keywords": keywords,
                "paper_count": len(cluster_paper_ids),
                "paper_ids": cluster_paper_ids,
            })

        elapsed = round(time.time() - start_time, 3)
        logger.info(
            "clustering_completed",
            algorithm=algorithm,
            clusters=len(clusters),
            papers=len(paper_ids),
            time=elapsed,
        )

        return {
            "clusters": clusters,
            "total_papers": len(paper_ids),
            "algorithm": algorithm,
            "processing_time": elapsed,
        }

    async def get_clusters(self, user_id: str | None = None) -> List[Dict]:
        """Get all existing clusters with their papers, scoped to user when provided."""
        clusters = await self.db.topiccluster.find_many(
            include={"papers": {"include": {"paper": True}}},
            order={"paper_count": "desc"},
        )

        # If user_id is provided, filter cluster papers to only include user's papers
        if user_id:
            filtered_clusters = []
            for cluster in clusters:
                user_papers = [pc for pc in (cluster.papers or []) if pc.paper and pc.paper.uploaded_by == user_id]
                if user_papers:
                    cluster.papers = user_papers
                    filtered_clusters.append(cluster)
            clusters = filtered_clusters

        result = []
        for cluster in clusters:
            result.append({
                "id": cluster.id,
                "name": cluster.name,
                "description": cluster.description,
                "keywords": cluster.keywords,
                "paper_count": cluster.paper_count,
                "papers": [
                    {
                        "paper_id": pc.paper_id,
                        "title": pc.paper.title if pc.paper else "Unknown",
                        "distance": pc.distance,
                    }
                    for pc in (cluster.papers or [])
                ],
            })

        return result

    def _run_kmeans(self, embeddings: np.ndarray, n_clusters: int):
        """Run KMeans clustering."""
        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10,
            max_iter=300,
        )
        labels = kmeans.fit_predict(embeddings)
        return labels.tolist(), kmeans.cluster_centers_

    def _run_hdbscan(self, embeddings: np.ndarray, min_cluster_size: int):
        """Run HDBSCAN clustering."""
        try:
            import hdbscan

            # Ensure min_cluster_size is valid for the dataset
            effective_min_cluster_size = max(2, min(min_cluster_size, len(embeddings) // 2))

            clusterer = hdbscan.HDBSCAN(
                min_cluster_size=effective_min_cluster_size,
                min_samples=max(1, effective_min_cluster_size - 1),
                metric="euclidean",
                cluster_selection_method="eom",
            )
            labels = clusterer.fit_predict(embeddings)

            # Check if HDBSCAN found any clusters (not just noise)
            unique_labels = set(labels)
            unique_labels.discard(-1)

            if len(unique_labels) == 0:
                # HDBSCAN found no clusters, fall back to KMeans
                logger.warning("hdbscan_no_clusters_found_falling_back_to_kmeans")
                return self._run_kmeans(embeddings, min(5, len(embeddings)))

            # Compute centroids for each cluster
            centers = []
            for label in sorted(unique_labels):
                mask = labels == label
                centers.append(embeddings[mask].mean(axis=0))

            return labels.tolist(), np.array(centers) if centers else None

        except ImportError:
            logger.warning("hdbscan_not_installed_falling_back_to_kmeans")
            return self._run_kmeans(embeddings, min(5, len(embeddings)))
        except Exception as e:
            logger.warning("hdbscan_failed_falling_back_to_kmeans", error=str(e))
            return self._run_kmeans(embeddings, min(5, len(embeddings)))

    async def _get_paper_embeddings(self, user_id: str | None = None) -> Dict[str, List[float]]:
        """Get average embeddings for each paper by fetching all chunk embeddings
        and computing the mean per paper in Python.
        Scoped to user_id when provided.
        This avoids relying on SQL AVG() for pgvector types which may not work
        in all PostgreSQL / pgvector versions."""
        from collections import defaultdict

        if user_id:
            results = await self.db.query_raw(
                """
                SELECT
                    pc.paper_id,
                    pc.embedding::text as embedding_text
                FROM paper_chunks pc
                JOIN papers p ON pc.paper_id = p.id
                WHERE pc.embedding IS NOT NULL
                    AND p.uploaded_by = $1
                """,
                user_id,
            )
        else:
            results = await self.db.query_raw(
                """
                SELECT
                    paper_id,
                    embedding::text as embedding_text
                FROM paper_chunks
                WHERE embedding IS NOT NULL
                """
            )

        paper_vectors: Dict[str, list] = defaultdict(list)
        for row in results:
            paper_id = row["paper_id"]
            emb_str = row.get("embedding_text", "")
            if emb_str:
                try:
                    emb_values = [float(x) for x in emb_str.strip("[]").split(",")]
                    paper_vectors[paper_id].append(emb_values)
                except (ValueError, AttributeError):
                    continue

        paper_embeddings: Dict[str, List[float]] = {}
        for paper_id, vectors in paper_vectors.items():
            if vectors:
                avg = np.mean(vectors, axis=0).tolist()
                paper_embeddings[paper_id] = avg

        return paper_embeddings

    async def _get_paper_texts(self, paper_ids: List[str]) -> List[str]:
        """Get title + abstract text for papers."""
        papers = await self.db.paper.find_many(
            where={"id": {"in": paper_ids}},
        )
        texts = []
        for p in papers:
            text = p.title or ""
            if p.abstract:
                text += " " + p.abstract
            if p.keywords:
                text += " " + " ".join(p.keywords)
            texts.append(text)
        return texts

    def _generate_cluster_label(
        self, texts: List[str], cluster_idx: int
    ) -> tuple:
        """Generate a cluster name and keywords from paper texts."""
        from collections import Counter
        import re

        # Combine all texts
        combined = " ".join(texts).lower()

        # Extract meaningful words (ignore stopwords)
        stopwords = {
            "the", "a", "an", "in", "of", "and", "or", "to", "for", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
            "did", "will", "would", "shall", "should", "may", "might", "can", "could",
            "this", "that", "these", "those", "it", "its", "with", "from", "by", "on",
            "at", "as", "but", "not", "no", "we", "our", "us", "their", "they",
            "which", "who", "whom", "what", "when", "where", "how", "than", "also",
            "about", "into", "over", "such", "each", "between", "through", "after",
            "using", "based", "paper", "study", "research", "results", "method",
            "proposed", "approach", "model", "data", "used", "show", "work",
        }

        words = re.findall(r"\b[a-z]{3,}\b", combined)
        meaningful_words = [w for w in words if w not in stopwords]

        # Get top keywords
        word_counts = Counter(meaningful_words)
        top_keywords = [word for word, _ in word_counts.most_common(8)]

        # Generate name from top 3 keywords
        name_keywords = top_keywords[:3]
        cluster_name = " & ".join(w.capitalize() for w in name_keywords) if name_keywords else f"Cluster {cluster_idx + 1}"

        return cluster_name, top_keywords


def get_clustering_service() -> ClusteringService:
    return ClusteringService()
