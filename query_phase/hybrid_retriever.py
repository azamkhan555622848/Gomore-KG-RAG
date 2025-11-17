"""
Hybrid Retriever combining Vector Search and Graph Traversal
Retrieves relevant context using both FAISS and knowledge graph
"""

from typing import List, Dict, Tuple, Set
import numpy as np
from loguru import logger
from collections import defaultdict

from shared.models import RetrievalResult
from shared.config import get_query_config
from query_phase.graph_loader import GraphLoader
from build_phase.indexer import FAISSIndexer
from build_phase.embedder import Embedder


class HybridRetriever:
    """Hybrid retrieval using vector search + graph traversal"""

    def __init__(
        self,
        graph_loader: GraphLoader,
        indexer: FAISSIndexer,
        embedder: Embedder = None
    ):
        self.config = get_query_config()
        self.graph_loader = graph_loader
        self.indexer = indexer
        self.embedder = embedder

        # Initialize embedder if not provided (for query embedding)
        if self.embedder is None:
            self.embedder = Embedder()

        logger.info("HybridRetriever initialized")

    def retrieve(self, query: str, top_k: int = None) -> List[RetrievalResult]:
        """
        Retrieve relevant context for query

        Args:
            query: User query
            top_k: Number of results to return

        Returns:
            List of RetrievalResult objects
        """
        if top_k is None:
            top_k = max(self.config.top_k_vector, self.config.top_k_graph)

        logger.info(f"Retrieving context for query: {query[:100]}...")

        # Step 1: Vector search
        vector_results = self._vector_search(query, self.config.top_k_vector)

        # Step 2: Extract entities from query
        query_entities = self._extract_query_entities(query)

        # Step 3: Graph traversal
        graph_results = self._graph_search(query_entities, self.config.top_k_graph)

        # Step 4: Merge and rank results
        merged_results = self._merge_results(vector_results, graph_results, top_k)

        logger.info(f"Retrieved {len(merged_results)} results")

        return merged_results

    def _vector_search(self, query: str, top_k: int) -> Dict[str, float]:
        """
        Perform vector search

        Args:
            query: Query text
            top_k: Number of results

        Returns:
            Dict mapping chunk_id to score
        """
        logger.debug(f"Vector search for top {top_k} chunks")

        # Embed query
        query_embedding = self.embedder.embed_query(query)

        # Search FAISS index
        results = self.indexer.search_chunks(query_embedding, k=top_k)

        # Convert to dict
        return {chunk_id: score for chunk_id, score in results}

    def _extract_query_entities(self, query: str) -> List[str]:
        """
        Extract entity names from query (simple keyword matching)

        Args:
            query: Query text

        Returns:
            List of entity IDs
        """
        # Get all entities from graph
        all_entities = self.graph_loader.entity_index

        # Find entities mentioned in query
        query_lower = query.lower()
        mentioned_entities = []

        for entity_id, data in all_entities.items():
            entity_name = data.get('name', '').lower()

            # Check if entity name appears in query
            if entity_name and entity_name in query_lower:
                mentioned_entities.append(entity_id)
                continue

            # Check mentions
            mentions = data.get('mentions', [])
            for mention in mentions:
                if mention.lower() in query_lower:
                    mentioned_entities.append(entity_id)
                    break

        logger.debug(f"Found {len(mentioned_entities)} entities in query")

        return mentioned_entities

    def _graph_search(self, entity_ids: List[str], top_k: int) -> Dict[str, float]:
        """
        Perform graph-based search

        Args:
            entity_ids: List of query entity IDs
            top_k: Number of results

        Returns:
            Dict mapping chunk_id to score
        """
        if not entity_ids:
            return {}

        logger.debug(f"Graph search from {len(entity_ids)} entities")

        # Collect all relevant chunks through graph traversal
        chunk_scores = defaultdict(float)

        for entity_id in entity_ids:
            # Get neighbors
            neighbors = self.graph_loader.get_neighbors(
                entity_id,
                hops=self.config.graph_hops
            )

            # Get chunks for each neighbor
            for neighbor_id in neighbors:
                entity_data = self.graph_loader.get_entity(neighbor_id)

                if not entity_data:
                    continue

                chunk_ids = entity_data.get('chunk_ids', [])

                # Calculate score based on distance from query entity
                if neighbor_id == entity_id:
                    score = 1.0  # Query entity itself
                elif neighbor_id in self.graph_loader.get_neighbors(entity_id, hops=1):
                    score = 0.7  # Direct neighbor
                else:
                    score = 0.4  # 2-hop neighbor

                # Add entity centrality if available
                centrality = entity_data.get('centrality', 0)
                score *= (1 + centrality)

                # Distribute score to chunks
                for chunk_id in chunk_ids:
                    chunk_scores[chunk_id] += score

        # Normalize scores
        if chunk_scores:
            max_score = max(chunk_scores.values())
            chunk_scores = {cid: score / max_score for cid, score in chunk_scores.items()}

        # Get top K
        top_chunks = sorted(
            chunk_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        return dict(top_chunks)

    def _merge_results(
        self,
        vector_results: Dict[str, float],
        graph_results: Dict[str, float],
        top_k: int
    ) -> List[RetrievalResult]:
        """
        Merge vector and graph results

        Args:
            vector_results: Chunk scores from vector search
            graph_results: Chunk scores from graph search
            top_k: Number of final results

        Returns:
            List of RetrievalResult objects
        """
        # Combine chunk IDs
        all_chunk_ids = set(vector_results.keys()) | set(graph_results.keys())

        # Calculate hybrid scores
        results = []

        for chunk_id in all_chunk_ids:
            vector_score = vector_results.get(chunk_id, 0)
            graph_score = graph_results.get(chunk_id, 0)

            # Weighted combination
            hybrid_score = (
                self.config.vector_weight * vector_score +
                self.config.graph_weight * graph_score
            )

            result = RetrievalResult(
                chunk_id=chunk_id,
                text="",  # Will be filled in later
                score=hybrid_score,
                vector_score=vector_score,
                graph_score=graph_score,
                doc_id=""
            )

            results.append(result)

        # Sort by hybrid score
        results.sort(key=lambda x: x.score, reverse=True)

        # Return top K
        return results[:top_k]

    def get_entity_context(self, entity_ids: List[str]) -> Dict:
        """
        Get context for a list of entities

        Args:
            entity_ids: List of entity IDs

        Returns:
            Dict with entity information and relationships
        """
        context = {
            'entities': [],
            'relationships': [],
            'neighbors': set()
        }

        for entity_id in entity_ids:
            # Get entity data
            entity_data = self.graph_loader.get_entity(entity_id)
            if entity_data:
                context['entities'].append({
                    'entity_id': entity_id,
                    'name': entity_data.get('name', ''),
                    'type': entity_data.get('type', ''),
                    'context': entity_data.get('context', '')
                })

            # Get relationships
            relationships = self.graph_loader.get_relationships(entity_id)
            context['relationships'].extend(relationships)

            # Get neighbors
            neighbors = self.graph_loader.get_neighbors(entity_id, hops=1)
            context['neighbors'].update(neighbors)

        return context


if __name__ == "__main__":
    # Test hybrid retriever
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    # Load graph and index
    graph_loader = GraphLoader()

    if graph_loader.shared_config.graph_path.exists():
        graph_loader.load_graph()

        # Load index
        indexer = FAISSIndexer()
        if graph_loader.shared_config.index_path.exists():
            indexer.load_chunk_index()

            # Create retriever
            retriever = HybridRetriever(graph_loader, indexer)

            # Test retrieval
            query = "Who works at Google?"
            results = retriever.retrieve(query, top_k=5)

            print(f"\nQuery: {query}")
            print(f"Retrieved {len(results)} results:")

            for i, result in enumerate(results, 1):
                print(f"\n{i}. Chunk ID: {result.chunk_id}")
                print(f"   Hybrid Score: {result.score:.4f}")
                print(f"   Vector Score: {result.vector_score:.4f}")
                print(f"   Graph Score: {result.graph_score:.4f}")
        else:
            print("Index not found. Please run build phase first.")
    else:
        print("Graph not found. Please run build phase first.")
