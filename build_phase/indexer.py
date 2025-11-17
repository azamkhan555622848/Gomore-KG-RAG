"""
FAISS Vector Indexer
Creates and manages FAISS indexes for fast similarity search
"""

from typing import Dict, List, Tuple
import numpy as np
import faiss
from loguru import logger
from pathlib import Path

from shared.config import get_build_config, get_shared_config


class FAISSIndexer:
    """Build and manage FAISS indexes"""

    def __init__(self):
        self.config = get_build_config()
        self.shared_config = get_shared_config()
        self.dimension = self.config.embedding_dim

        self.chunk_index = None
        self.chunk_id_map: List[str] = []  # Map index position to chunk_id

        logger.info(f"FAISSIndexer initialized. Dimension: {self.dimension}")

    def build_index(self, embeddings: Dict[str, np.ndarray]) -> faiss.Index:
        """
        Build FAISS index from embeddings

        Args:
            embeddings: Dict mapping ID to embedding vector

        Returns:
            FAISS index
        """
        logger.info(f"Building FAISS index for {len(embeddings)} vectors")

        # Extract embeddings and create ID mapping
        vectors = []
        ids = []

        for id, embedding in embeddings.items():
            vectors.append(embedding)
            ids.append(id)

        # Convert to numpy array
        vectors_array = np.array(vectors).astype('float32')

        logger.info(f"Vectors array shape: {vectors_array.shape}")

        # Create FAISS index
        # Using IndexFlatIP for cosine similarity (vectors should be normalized)
        index = faiss.IndexFlatIP(self.dimension)

        # Add vectors to index
        index.add(vectors_array)

        logger.info(f"FAISS index built. Total vectors: {index.ntotal}")

        return index, ids

    def build_chunk_index(self, chunk_embeddings: Dict[str, np.ndarray]) -> None:
        """
        Build index for text chunks

        Args:
            chunk_embeddings: Dict mapping chunk_id to embedding
        """
        self.chunk_index, self.chunk_id_map = self.build_index(chunk_embeddings)
        logger.info("Chunk index built successfully")

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10,
        index: faiss.Index = None,
        id_map: List[str] = None
    ) -> List[Tuple[str, float]]:
        """
        Search for similar vectors

        Args:
            query_embedding: Query vector
            k: Number of results to return
            index: FAISS index to search (defaults to chunk_index)
            id_map: ID mapping (defaults to chunk_id_map)

        Returns:
            List of (id, score) tuples
        """
        if index is None:
            index = self.chunk_index
            id_map = self.chunk_id_map

        if index is None or id_map is None:
            logger.error("Index not built yet")
            return []

        # Ensure query is 2D array
        if len(query_embedding.shape) == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Ensure float32
        query_embedding = query_embedding.astype('float32')

        # Search
        scores, indices = index.search(query_embedding, k)

        # Convert to (id, score) tuples
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(id_map):
                results.append((id_map[idx], float(score)))

        return results

    def search_chunks(
        self,
        query_embedding: np.ndarray,
        k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Search for similar chunks

        Args:
            query_embedding: Query vector
            k: Number of results

        Returns:
            List of (chunk_id, score) tuples
        """
        return self.search(query_embedding, k, self.chunk_index, self.chunk_id_map)

    def save_index(
        self,
        index: faiss.Index,
        id_map: List[str],
        filepath: Path
    ) -> None:
        """
        Save FAISS index and ID mapping

        Args:
            index: FAISS index
            id_map: ID mapping
            filepath: Path to save to
        """
        logger.info(f"Saving index to {filepath}")

        # Save FAISS index
        faiss.write_index(index, str(filepath))

        # Save ID mapping
        id_map_file = filepath.parent / f"{filepath.stem}_ids.npy"
        np.save(id_map_file, np.array(id_map))

        logger.info(f"Index saved successfully")

    def load_index(self, filepath: Path) -> Tuple[faiss.Index, List[str]]:
        """
        Load FAISS index and ID mapping

        Args:
            filepath: Path to index file

        Returns:
            Tuple of (index, id_map)
        """
        logger.info(f"Loading index from {filepath}")

        # Load FAISS index
        index = faiss.read_index(str(filepath))

        # Load ID mapping
        id_map_file = filepath.parent / f"{filepath.stem}_ids.npy"
        id_map = np.load(id_map_file, allow_pickle=True).tolist()

        logger.info(f"Index loaded. Total vectors: {index.ntotal}")

        return index, id_map

    def save_chunk_index(self, filepath: Path = None) -> None:
        """
        Save chunk index

        Args:
            filepath: Optional custom path (defaults to config path)
        """
        if self.chunk_index is None:
            logger.error("Chunk index not built yet")
            return

        if filepath is None:
            filepath = self.shared_config.index_path

        self.save_index(self.chunk_index, self.chunk_id_map, filepath)

    def load_chunk_index(self, filepath: Path = None) -> None:
        """
        Load chunk index

        Args:
            filepath: Optional custom path (defaults to config path)
        """
        if filepath is None:
            filepath = self.shared_config.index_path

        self.chunk_index, self.chunk_id_map = self.load_index(filepath)


if __name__ == "__main__":
    # Test the indexer
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    # Create sample embeddings
    dim = 384
    num_vectors = 100

    sample_embeddings = {
        f"chunk_{i:03d}": np.random.randn(dim).astype('float32')
        for i in range(num_vectors)
    }

    # Normalize vectors (for cosine similarity)
    for chunk_id in sample_embeddings:
        norm = np.linalg.norm(sample_embeddings[chunk_id])
        if norm > 0:
            sample_embeddings[chunk_id] /= norm

    # Build index
    indexer = FAISSIndexer()
    indexer.build_chunk_index(sample_embeddings)

    # Test search
    query_vector = np.random.randn(dim).astype('float32')
    query_vector /= np.linalg.norm(query_vector)

    results = indexer.search_chunks(query_vector, k=5)

    print(f"\nSearch results:")
    for chunk_id, score in results:
        print(f"  {chunk_id}: {score:.4f}")

    # Test save/load
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir) / "test_index.bin"
        indexer.save_chunk_index(tmppath)

        # Load it back
        indexer2 = FAISSIndexer()
        indexer2.load_chunk_index(tmppath)

        # Verify
        results2 = indexer2.search_chunks(query_vector, k=5)
        print(f"\nAfter save/load:")
        for chunk_id, score in results2:
            print(f"  {chunk_id}: {score:.4f}")
