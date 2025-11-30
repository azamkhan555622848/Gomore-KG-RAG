"""
Shared Configuration for Graph-RAG System
Optimized for mobile deployment with build-once, deploy-many strategy
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCUMENTS_DIR = PROJECT_ROOT / "documents"  # Updated to use documents/ directory
GRAPH_EXPORT_DIR = DATA_DIR / "graph_export"
INDEXES_DIR = DATA_DIR / "indexes"

# Ensure directories exist
for dir_path in [DATA_DIR, DOCUMENTS_DIR, GRAPH_EXPORT_DIR, INDEXES_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


@dataclass
class BuildPhaseConfig:
    """Configuration for build phase (PC/Server)"""

    # Document processing
    chunk_size: int = 512
    chunk_overlap: int = 50
    supported_formats: List[str] = field(default_factory=lambda: ['.pdf', '.docx', '.txt', '.md', '.csv'])

    # Entity extraction
    ollama_host: str = "http://localhost:11434"
    extraction_model: str = "gemma3:1b"  # Model for entity/relation extraction
    max_extraction_tokens: int = 2048
    temperature: float = 0.3  # Lower for more deterministic extraction

    # Entity extraction prompts
    max_entities_per_chunk: int = 20
    entity_types: List[str] = field(default_factory=lambda: [
        "PERSON", "ORGANIZATION", "LOCATION", "DATE",
        "PRODUCT", "CONCEPT", "EVENT", "TECHNOLOGY"
    ])

    # Relationship extraction
    max_relations_per_pair: int = 3
    relation_types: List[str] = field(default_factory=lambda: [
        "RELATED_TO", "PART_OF", "LOCATED_IN", "WORKS_FOR",
        "CREATED_BY", "OCCURRED_AT", "USES", "CAUSES"
    ])

    # Embedding model
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # 80MB, good accuracy
    embedding_dim: int = 384
    batch_size: int = 32

    # Graph construction
    entity_similarity_threshold: float = 0.85  # For entity deduplication
    min_entity_mentions: int = 1  # Minimum mentions to keep entity
    max_graph_nodes: int = 50000  # Limit for mobile optimization

    # FAISS indexing
    faiss_metric: str = "cosine"  # or "l2", "ip"
    normalize_embeddings: bool = True

    # Export settings
    graph_format: str = "json"  # "json", "graphml", "pickle"
    compress_export: bool = True
    target_package_size_mb: int = 50


@dataclass
class QueryPhaseConfig:
    """Configuration for query phase (Mobile deployment)"""

    # Ollama configuration
    ollama_host: str = "http://localhost:11434"
    answer_model: str = "gemma3:1b"  # Model for answer generation
    max_answer_tokens: int = 512
    temperature: float = 0.7

    # Retrieval settings
    top_k_vector: int = 10  # Top K chunks from vector search
    top_k_graph: int = 5  # Top K entities from graph
    graph_hops: int = 2  # Number of hops for graph traversal

    # Hybrid retrieval weights
    vector_weight: float = 0.6
    graph_weight: float = 0.4

    # Context assembly
    max_context_tokens: int = 2048  # For gemma2:2b context window
    include_entity_context: bool = True
    include_relationships: bool = True

    # Performance optimization
    lazy_load_graph: bool = True
    cache_embeddings: bool = True
    max_memory_mb: int = 500  # Mobile memory constraint

    # Answer generation
    enable_citations: bool = True
    stream_response: bool = False


@dataclass
class SharedConfig:
    """Shared configuration for both phases"""

    # Paths (will be set at runtime)
    graph_path: Path = GRAPH_EXPORT_DIR / "knowledge_graph.json.gz"
    index_path: Path = INDEXES_DIR / "faiss_index.bin"
    metadata_path: Path = GRAPH_EXPORT_DIR / "metadata.json"
    entity_embeddings_path: Path = INDEXES_DIR / "entity_embeddings.npy"
    chunk_embeddings_path: Path = INDEXES_DIR / "chunk_embeddings.npy"

    # Logging
    log_level: str = "INFO"
    log_file: Path = PROJECT_ROOT / "graph_rag.log"

    # Environment
    use_gpu: bool = False  # Set to True if GPU available for build phase
    random_seed: int = 42


# Global config instances
build_config = BuildPhaseConfig()
query_config = QueryPhaseConfig()
shared_config = SharedConfig()


def get_build_config() -> BuildPhaseConfig:
    """Get build phase configuration"""
    return build_config


def get_query_config() -> QueryPhaseConfig:
    """Get query phase configuration"""
    return query_config


def get_shared_config() -> SharedConfig:
    """Get shared configuration"""
    return shared_config


def update_config(phase: str, **kwargs) -> None:
    """
    Update configuration dynamically

    Args:
        phase: "build" or "query"
        **kwargs: Configuration parameters to update
    """
    global build_config, query_config

    if phase == "build":
        for key, value in kwargs.items():
            if hasattr(build_config, key):
                setattr(build_config, key, value)
    elif phase == "query":
        for key, value in kwargs.items():
            if hasattr(query_config, key):
                setattr(query_config, key, value)
    else:
        raise ValueError(f"Unknown phase: {phase}. Use 'build' or 'query'")


# Environment variable overrides
if os.getenv("OLLAMA_HOST"):
    build_config.ollama_host = os.getenv("OLLAMA_HOST")
    query_config.ollama_host = os.getenv("OLLAMA_HOST")

if os.getenv("EXTRACTION_MODEL"):
    build_config.extraction_model = os.getenv("EXTRACTION_MODEL")

if os.getenv("ANSWER_MODEL"):
    query_config.answer_model = os.getenv("ANSWER_MODEL")
