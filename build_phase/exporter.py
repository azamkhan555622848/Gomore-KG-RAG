"""
Export Pipeline for Mobile Deployment
Packages the knowledge graph and indexes for mobile
"""

import json
import gzip
from pathlib import Path
from typing import Dict
import numpy as np
import networkx as nx
from loguru import logger
from datetime import datetime

from shared.models import GraphExportMetadata, DocumentMetadata
from shared.utils import format_file_size
from shared.config import get_build_config, get_shared_config


class GraphExporter:
    """Export knowledge graph for mobile deployment"""

    def __init__(self):
        self.config = get_build_config()
        self.shared_config = get_shared_config()
        logger.info("GraphExporter initialized")

    def export_graph(
        self,
        graph: nx.MultiDiGraph,
        output_path: Path = None
    ) -> Path:
        """
        Export NetworkX graph to compressed JSON

        Args:
            graph: NetworkX graph
            output_path: Output file path

        Returns:
            Path to exported file
        """
        if output_path is None:
            output_path = self.shared_config.graph_path

        logger.info(f"Exporting graph to {output_path}")

        # Convert graph to JSON-serializable format
        graph_data = nx.node_link_data(graph)

        # Save as compressed JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config.compress_export:
            with gzip.open(output_path, 'wt', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False)
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)

        file_size = output_path.stat().st_size
        logger.info(f"Graph exported. Size: {format_file_size(file_size)}")

        return output_path

    def export_chunk_texts(self, chunks: list) -> None:
        """
        Export chunk texts to compressed JSON file

        Args:
            chunks: List of TextChunk objects
        """
        logger.info("Exporting chunk texts")

        chunk_texts_path = self.shared_config.graph_path.parent / "chunk_texts.json.gz"
        chunk_texts_path.parent.mkdir(parents=True, exist_ok=True)

        # Create chunk data dictionary
        chunk_data = {}
        for chunk in chunks:
            chunk_data[chunk.chunk_id] = {
                "text": chunk.text,
                "doc_id": chunk.doc_id,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "tags": chunk.tags,
                "notes": chunk.notes
            }

        # Save as compressed JSON
        with gzip.open(chunk_texts_path, 'wt', encoding='utf-8') as f:
            json.dump(chunk_data, f, ensure_ascii=False)

        file_size = chunk_texts_path.stat().st_size
        logger.info(f"Chunk texts exported: {format_file_size(file_size)} ({len(chunk_data)} chunks)")

    def export_embeddings(
        self,
        chunk_embeddings: Dict[str, np.ndarray],
        entity_embeddings: Dict[str, np.ndarray] = None
    ) -> None:
        """
        Export embeddings to numpy files

        Args:
            chunk_embeddings: Chunk embeddings
            entity_embeddings: Optional entity embeddings
        """
        logger.info("Exporting embeddings")

        # Export chunk embeddings
        chunk_path = self.shared_config.chunk_embeddings_path
        chunk_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert dict to arrays
        chunk_ids = list(chunk_embeddings.keys())
        chunk_vectors = np.array([chunk_embeddings[cid] for cid in chunk_ids])

        # Save
        np.save(chunk_path, chunk_vectors)
        np.save(chunk_path.parent / "chunk_ids.npy", np.array(chunk_ids))

        logger.info(f"Chunk embeddings exported: {format_file_size(chunk_path.stat().st_size)}")

        # Export entity embeddings if provided
        if entity_embeddings:
            entity_path = self.shared_config.entity_embeddings_path
            entity_path.parent.mkdir(parents=True, exist_ok=True)

            entity_ids = list(entity_embeddings.keys())
            entity_vectors = np.array([entity_embeddings[eid] for eid in entity_ids])

            np.save(entity_path, entity_vectors)
            np.save(entity_path.parent / "entity_ids.npy", np.array(entity_ids))

            logger.info(f"Entity embeddings exported: {format_file_size(entity_path.stat().st_size)}")

    def create_metadata(
        self,
        num_documents: int,
        num_chunks: int,
        num_entities: int,
        num_relationships: int,
        graph_stats: Dict = None
    ) -> GraphExportMetadata:
        """
        Create export metadata

        Args:
            num_documents: Number of documents
            num_chunks: Number of chunks
            num_entities: Number of entities
            num_relationships: Number of relationships
            graph_stats: Optional graph statistics

        Returns:
            GraphExportMetadata
        """
        # Calculate file sizes
        graph_size = 0
        if self.shared_config.graph_path.exists():
            graph_size = self.shared_config.graph_path.stat().st_size / (1024 * 1024)

        index_size = 0
        if self.shared_config.index_path.exists():
            index_size = self.shared_config.index_path.stat().st_size / (1024 * 1024)

        metadata = GraphExportMetadata(
            version="1.0",
            created_at=datetime.now(),
            graph_format=self.config.graph_format,
            compression="gzip" if self.config.compress_export else "none",
            num_documents=num_documents,
            num_chunks=num_chunks,
            num_entities=num_entities,
            num_relationships=num_relationships,
            embedding_model=self.config.embedding_model,
            embedding_dim=self.config.embedding_dim,
            config={
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
                "entity_types": self.config.entity_types,
                "relation_types": self.config.relation_types
            },
            graph_size_mb=graph_size,
            index_size_mb=index_size,
            total_size_mb=graph_size + index_size
        )

        if graph_stats:
            metadata.config["graph_stats"] = graph_stats

        return metadata

    def save_metadata(self, metadata: GraphExportMetadata) -> None:
        """
        Save metadata to JSON file

        Args:
            metadata: GraphExportMetadata object
        """
        metadata_path = self.shared_config.metadata_path
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata.model_dump(), f, indent=2, default=str)

        logger.info(f"Metadata saved to {metadata_path}")

    def get_package_size(self) -> float:
        """
        Calculate total package size in MB

        Returns:
            Total size in MB
        """
        total_size = 0

        paths_to_check = [
            self.shared_config.graph_path,
            self.shared_config.index_path,
            self.shared_config.metadata_path,
            self.shared_config.chunk_embeddings_path,
            self.shared_config.entity_embeddings_path
        ]

        for path in paths_to_check:
            if path.exists():
                total_size += path.stat().st_size

        return total_size / (1024 * 1024)


if __name__ == "__main__":
    # Test the exporter
    from shared.utils import setup_logging
    import networkx as nx

    setup_logging(level="INFO")

    # Create sample graph
    G = nx.MultiDiGraph()
    G.add_node("ent_001", name="Jane Smith", type="PERSON")
    G.add_node("ent_002", name="Google", type="ORGANIZATION")
    G.add_edge("ent_001", "ent_002", relation_type="WORKS_FOR")

    # Export
    exporter = GraphExporter()

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir) / "test_graph.json.gz"
        exporter.export_graph(G, tmppath)

        # Check file size
        print(f"Exported graph size: {format_file_size(tmppath.stat().st_size)}")

        # Create metadata
        metadata = exporter.create_metadata(
            num_documents=10,
            num_chunks=100,
            num_entities=50,
            num_relationships=75
        )

        print(f"\nMetadata:")
        print(f"  Documents: {metadata.num_documents}")
        print(f"  Chunks: {metadata.num_chunks}")
        print(f"  Entities: {metadata.num_entities}")
        print(f"  Relationships: {metadata.num_relationships}")
