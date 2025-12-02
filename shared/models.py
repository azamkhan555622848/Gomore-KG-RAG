"""
Data Models for Graph-RAG System
Using Pydantic for type safety and validation
"""

from typing import List, Dict, Optional, Any, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class EntityType(str, Enum):
    """Supported entity types"""
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    DATE = "DATE"
    PRODUCT = "PRODUCT"
    CONCEPT = "CONCEPT"
    EVENT = "EVENT"
    TECHNOLOGY = "TECHNOLOGY"


class RelationType(str, Enum):
    """Supported relationship types"""
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    LOCATED_IN = "LOCATED_IN"
    WORKS_FOR = "WORKS_FOR"
    CREATED_BY = "CREATED_BY"
    OCCURRED_AT = "OCCURRED_AT"
    USES = "USES"
    CAUSES = "CAUSES"


class DocumentMetadata(BaseModel):
    """Metadata for a source document"""
    doc_id: str
    filename: str
    file_path: str
    file_type: str  # pdf, docx, txt, md
    file_size: int  # in bytes
    processed_at: datetime = Field(default_factory=datetime.now)
    num_chunks: int = 0
    num_entities: int = 0


class TextChunk(BaseModel):
    """Represents a chunk of text from a document"""
    chunk_id: str
    doc_id: str
    text: str
    start_char: int
    end_char: int
    chunk_index: int
    token_count: int
    tags: Optional[str] = None
    notes: Optional[str] = None


class Entity(BaseModel):
    """An entity extracted from text"""
    entity_id: str
    name: str  # Normalized entity name
    entity_type: EntityType
    mentions: List[str] = Field(default_factory=list)  # Different ways it's mentioned
    context: str = ""  # Context where first found
    chunk_ids: List[str] = Field(default_factory=list)  # Chunks containing this entity
    doc_ids: List[str] = Field(default_factory=list)  # Source documents
    mention_count: int = 0
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A relationship between two entities"""
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: RelationType
    context: str = ""  # Sentence showing the relationship
    chunk_id: str
    doc_id: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraph(BaseModel):
    """Complete knowledge graph structure"""
    graph_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    documents: List[DocumentMetadata] = Field(default_factory=list)
    chunks: List[TextChunk] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)

    # Statistics
    num_documents: int = 0
    num_chunks: int = 0
    num_entities: int = 0
    num_relationships: int = 0

    # Index mappings (for fast lookup)
    entity_index: Dict[str, Entity] = Field(default_factory=dict)
    chunk_index: Dict[str, TextChunk] = Field(default_factory=dict)
    doc_index: Dict[str, DocumentMetadata] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Represents a single retrieved item"""
    chunk_id: str
    doc_id: str
    score: float
    text: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None


class GraphContext(BaseModel):
    """Context assembled from graph traversal"""
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    chunks: List[TextChunk] = Field(default_factory=list)
    entity_graph: Dict[str, List[Tuple[str, str]]] = Field(default_factory=dict)  # entity_id -> [(relation, neighbor_id)]


class QueryResult(BaseModel):
    """Final query result"""
    query: str
    answer: str
    context: GraphContext
    retrieval_results: List[RetrievalResult] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    processing_time: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BuildPhaseOutput(BaseModel):
    """Output from build phase"""
    graph_file: str
    index_file: str
    metadata_file: str
    entity_embeddings_file: str
    chunk_embeddings_file: str

    num_documents: int
    num_chunks: int
    num_entities: int
    num_relationships: int

    build_time: float
    package_size_mb: float

    statistics: Dict[str, Any] = Field(default_factory=dict)


# Ollama API Models
class OllamaMessage(BaseModel):
    """Message for Ollama chat API"""
    role: str  # "system", "user", "assistant"
    content: str


class OllamaRequest(BaseModel):
    """Request to Ollama API"""
    model: str
    messages: List[OllamaMessage]
    stream: bool = False
    options: Dict[str, Any] = Field(default_factory=dict)


class OllamaResponse(BaseModel):
    """Response from Ollama API"""
    model: str
    message: OllamaMessage
    done: bool
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_duration: Optional[int] = None
    eval_duration: Optional[int] = None


# Export Format Models
class GraphExportMetadata(BaseModel):
    """Metadata for exported graph package"""
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.now)
    graph_format: str = "json"  # json, graphml, pickle
    compression: str = "gzip"  # gzip, none

    num_documents: int
    num_chunks: int
    num_entities: int
    num_relationships: int

    embedding_model: str
    embedding_dim: int

    config: Dict[str, Any] = Field(default_factory=dict)

    # File sizes
    graph_size_mb: float = 0.0
    index_size_mb: float = 0.0
    total_size_mb: float = 0.0


class EntityExtractionResult(BaseModel):
    """Result from entity extraction"""
    chunk_id: str
    entities: List[Entity]
    extraction_time: float = 0.0
    model_used: str = ""


class RelationshipExtractionResult(BaseModel):
    """Result from relationship extraction"""
    chunk_id: str
    relationships: List[Relationship]
    extraction_time: float = 0.0
    model_used: str = ""
