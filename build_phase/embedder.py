"""
Embedding Generation using Sentence Transformers
Generates embeddings for text chunks and entities
"""

from typing import List, Dict
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from shared.models import TextChunk, Entity
from shared.utils import l2_normalize, batch_iterator, clean_text_for_embedding
from shared.config import get_build_config


class Embedder:
    """Generate embeddings for text and entities"""

    def __init__(self):
        self.config = get_build_config()
        self.model_name = self.config.embedding_model
        self.embedding_dim = self.config.embedding_dim
        self.batch_size = self.config.batch_size
        self.normalize = self.config.normalize_embeddings

        logger.info(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded. Embedding dimension: {self.embedding_dim}")

    def embed_chunks(self, chunks: List[TextChunk]) -> Dict[str, np.ndarray]:
        """
        Generate embeddings for text chunks

        Args:
            chunks: List of TextChunk objects

        Returns:
            Dict mapping chunk_id to embedding vector
        """
        logger.info(f"Generating embeddings for {len(chunks)} chunks")

        chunk_embeddings = {}

        # Create a richer text representation for each chunk
        texts_to_embed = []
        for chunk in chunks:
            # For chunks from CSVs that have a 'notes' summary, use that for embedding.
            # This should provide a cleaner, more semantically focused vector.
            if chunk.notes:
                text_for_embedding = chunk.notes
            else:
                # Fallback for chunks without notes (e.g., from other document types)
                text_for_embedding = chunk.text
            
            texts_to_embed.append(clean_text_for_embedding(text_for_embedding))

        chunk_ids = [chunk.chunk_id for chunk in chunks]

        # Generate embeddings in batches
        all_embeddings = []

        for batch_texts in tqdm(
            list(batch_iterator(texts_to_embed, self.batch_size)),
            desc="Embedding chunks"
        ):
            batch_embeddings = self.model.encode(
                batch_texts,
                show_progress_bar=False,
                convert_to_numpy=True
            )

            all_embeddings.extend(batch_embeddings)

        # Normalize if configured
        if self.normalize:
            all_embeddings = [l2_normalize(emb) for emb in all_embeddings]

        # Create mapping
        for chunk_id, embedding in zip(chunk_ids, all_embeddings):
            chunk_embeddings[chunk_id] = embedding

        logger.info(f"Generated {len(chunk_embeddings)} chunk embeddings")

        return chunk_embeddings

    def embed_entities(self, entities: List[Entity]) -> Dict[str, np.ndarray]:
        """
        Generate embeddings for entities

        Args:
            entities: List of Entity objects

        Returns:
            Dict mapping entity_id to embedding vector
        """
        logger.info(f"Generating embeddings for {len(entities)} entities")

        entity_embeddings = {}

        # Create entity texts (name + context)
        entity_texts = []
        entity_ids = []

        for entity in entities:
            # Combine name, type, and context
            text = f"{entity.name} ({entity.entity_type.value})"
            if entity.context:
                text += f" - {entity.context[:200]}"

            entity_texts.append(clean_text_for_embedding(text))
            entity_ids.append(entity.entity_id)

        # Generate embeddings in batches
        all_embeddings = []

        for batch_texts in tqdm(
            list(batch_iterator(entity_texts, self.batch_size)),
            desc="Embedding entities"
        ):
            batch_embeddings = self.model.encode(
                batch_texts,
                show_progress_bar=False,
                convert_to_numpy=True
            )

            all_embeddings.extend(batch_embeddings)

        # Normalize if configured
        if self.normalize:
            all_embeddings = [l2_normalize(emb) for emb in all_embeddings]

        # Create mapping
        for entity_id, embedding in zip(entity_ids, all_embeddings):
            entity_embeddings[entity_id] = embedding

        logger.info(f"Generated {len(entity_embeddings)} entity embeddings")

        return entity_embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Generate embedding for a query

        Args:
            query: Query text

        Returns:
            Embedding vector
        """
        query_clean = clean_text_for_embedding(query)

        embedding = self.model.encode(
            query_clean,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        if self.normalize:
            embedding = l2_normalize(embedding)

        return embedding


if __name__ == "__main__":
    # Test the embedder
    from shared.utils import setup_logging
    from shared.models import EntityType

    setup_logging(level="INFO")

    # Create sample chunks
    sample_chunks = [
        TextChunk(
            chunk_id="chunk_001",
            doc_id="doc_001",
            text="Dr. Jane Smith works for Google in Mountain View.",
            start_char=0,
            end_char=50,
            chunk_index=0,
            token_count=10
        )
    ]

    # Create sample entities
    sample_entities = [
        Entity(
            entity_id="ent_001",
            name="Jane Smith",
            entity_type=EntityType.PERSON,
            mentions=["Jane Smith"],
            context="works for Google",
            chunk_ids=["chunk_001"],
            doc_ids=["doc_001"],
            mention_count=1
        )
    ]

    # Test embedder
    embedder = Embedder()

    chunk_embeddings = embedder.embed_chunks(sample_chunks)
    print(f"\nGenerated {len(chunk_embeddings)} chunk embeddings")
    print(f"Embedding shape: {chunk_embeddings['chunk_001'].shape}")

    entity_embeddings = embedder.embed_entities(sample_entities)
    print(f"\nGenerated {len(entity_embeddings)} entity embeddings")
    print(f"Embedding shape: {entity_embeddings['ent_001'].shape}")

    # Test query embedding
    query = "Who works at Google?"
    query_emb = embedder.embed_query(query)
    print(f"\nQuery embedding shape: {query_emb.shape}")
