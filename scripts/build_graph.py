#!/usr/bin/env python3
"""
Build Knowledge Graph Script
Main pipeline for building the knowledge graph from documents
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from tqdm import tqdm

from shared.config import get_build_config, get_shared_config, DOCUMENTS_DIR
from shared.utils import setup_logging, format_file_size
from shared.models import BuildPhaseOutput

from build_phase.document_loader import DocumentProcessor
from build_phase.entity_extractor import EntityExtractor
from build_phase.relation_extractor import RelationshipExtractor
from build_phase.graph_builder import GraphBuilder
from build_phase.embedder import Embedder
from build_phase.indexer import FAISSIndexer
from build_phase.exporter import GraphExporter


def main():
    """Main build pipeline"""

    print("=" * 60)
    print("Graph-RAG Knowledge Graph Builder")
    print("=" * 60)

    # Setup logging
    setup_logging(level="INFO")

    config = get_build_config()
    shared_config = get_shared_config()

    start_time = time.time()

    # Check Ollama connection
    from build_phase.entity_extractor import OllamaClient
    ollama = OllamaClient(host=config.ollama_host, model=config.extraction_model)

    if not ollama.check_connection():
        logger.error(f"Cannot connect to Ollama at {config.ollama_host}")
        print(f"\n✗ Error: Ollama is not running or not accessible")
        print(f"  Please start Ollama: ollama serve")
        print(f"  Then pull the model: ollama pull {config.extraction_model}")
        return 1

    logger.info(f"✓ Connected to Ollama at {config.ollama_host}")

    # Step 1: Load and process documents
    print(f"\n[Step 1/7] Loading documents from {DOCUMENTS_DIR}")

    if not DOCUMENTS_DIR.exists():
        logger.error(f"Documents directory not found: {DOCUMENTS_DIR}")
        print(f"\n✗ Error: Please create {DOCUMENTS_DIR} and add documents")
        return 1

    processor = DocumentProcessor()
    all_metadata, all_chunks = processor.process_directory(DOCUMENTS_DIR)

    if not all_metadata:
        logger.error("No documents found")
        print(f"\n✗ Error: No supported documents found in {DOCUMENTS_DIR}")
        print(f"  Supported formats: {config.supported_formats}")
        return 1

    print(f"  ✓ Loaded {len(all_metadata)} documents")
    print(f"  ✓ Created {len(all_chunks)} chunks")

    # Step 2: Extract entities
    print(f"\n[Step 2/7] Extracting entities using {config.extraction_model}")

    entity_extractor = EntityExtractor()
    entity_results = entity_extractor.extract_entities_batch(all_chunks)

    # Collect all entities
    all_entities = []
    for result in entity_results:
        all_entities.extend(result.entities)

    print(f"  ✓ Extracted {len(all_entities)} entity mentions")

    # Deduplicate entities
    unique_entities = entity_extractor.deduplicate_entities(all_entities)
    print(f"  ✓ Deduplicated to {len(unique_entities)} unique entities")

    # Step 3: Extract relationships
    print(f"\n[Step 3/7] Extracting relationships")

    relation_extractor = RelationshipExtractor()

    # Create chunk -> entities mapping
    chunk_entities = {}
    for result in entity_results:
        chunk_entities[result.chunk_id] = result.entities

    relation_results = relation_extractor.extract_relationships_batch(
        all_chunks,
        chunk_entities
    )

    # Collect all relationships
    all_relationships = []
    for result in relation_results:
        all_relationships.extend(result.relationships)

    print(f"  ✓ Extracted {len(all_relationships)} relationship mentions")

    # Deduplicate relationships
    unique_relationships = relation_extractor.deduplicate_relationships(all_relationships)
    print(f"  ✓ Deduplicated to {len(unique_relationships)} unique relationships")

    # Step 4: Build graph
    print(f"\n[Step 4/7] Building knowledge graph")

    graph_builder = GraphBuilder()
    graph_builder.add_entities(unique_entities)
    graph_builder.add_relationships(unique_relationships)
    graph_builder.add_chunks(all_chunks)

    # Compute graph metrics
    graph_builder.compute_centrality_scores()
    graph_builder.detect_communities()

    stats = graph_builder.get_statistics()

    print(f"  ✓ Graph constructed:")
    print(f"    - Nodes: {stats['num_nodes']}")
    print(f"    - Edges: {stats['num_edges']}")
    print(f"    - Density: {stats['density']:.4f}")

    # Step 5: Generate embeddings
    print(f"\n[Step 5/7] Generating embeddings using {config.embedding_model}")

    embedder = Embedder()

    chunk_embeddings = embedder.embed_chunks(all_chunks)
    print(f"  ✓ Generated {len(chunk_embeddings)} chunk embeddings")

    entity_embeddings = embedder.embed_entities(unique_entities)
    print(f"  ✓ Generated {len(entity_embeddings)} entity embeddings")

    # Step 6: Build FAISS index
    print(f"\n[Step 6/7] Building FAISS index")

    indexer = FAISSIndexer()
    indexer.build_chunk_index(chunk_embeddings)

    print(f"  ✓ FAISS index built with {len(chunk_embeddings)} vectors")

    # Save index
    indexer.save_chunk_index()
    print(f"  ✓ Index saved to {shared_config.index_path}")

    # Step 7: Export for deployment
    print(f"\n[Step 7/7] Exporting for deployment")

    exporter = GraphExporter()

    # Export graph
    graph = graph_builder.export_graph()
    exporter.export_graph(graph)
    print(f"  ✓ Graph exported to {shared_config.graph_path}")

    # Export embeddings
    exporter.export_embeddings(chunk_embeddings, entity_embeddings)
    print(f"  ✓ Embeddings exported")

    # Create and save metadata
    metadata = exporter.create_metadata(
        num_documents=len(all_metadata),
        num_chunks=len(all_chunks),
        num_entities=len(unique_entities),
        num_relationships=len(unique_relationships),
        graph_stats=stats
    )

    exporter.save_metadata(metadata)
    print(f"  ✓ Metadata saved")

    # Calculate package size
    package_size = exporter.get_package_size()

    build_time = time.time() - start_time

    # Print summary
    print("\n" + "=" * 60)
    print("Build Complete!")
    print("=" * 60)
    print(f"\nStatistics:")
    print(f"  Documents: {len(all_metadata)}")
    print(f"  Chunks: {len(all_chunks)}")
    print(f"  Entities: {len(unique_entities)}")
    print(f"  Relationships: {len(unique_relationships)}")
    print(f"  Package size: {format_file_size(int(package_size * 1024 * 1024))}")
    print(f"  Build time: {build_time:.2f}s")

    print(f"\nOutput files:")
    print(f"  Graph: {shared_config.graph_path}")
    print(f"  Index: {shared_config.index_path}")
    print(f"  Metadata: {shared_config.metadata_path}")

    print(f"\nNext steps:")
    print(f"  1. Start Ollama: ollama serve")
    print(f"  2. Pull answer model: ollama pull gemma3:1b")
    print(f"  3. Run query interface: python scripts/query_cli.py")

    print("\n✓ Build pipeline completed successfully!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
