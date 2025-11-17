"""
Graph-RAG Engine
Main orchestration for query processing and answer generation
"""

import time
from typing import Dict, List, Optional
from loguru import logger
import numpy as np

from shared.models import QueryResult, GraphContext, RetrievalResult, TextChunk
from shared.config import get_query_config
from shared.utils import count_tokens, truncate_text

from query_phase.graph_loader import GraphLoader
from query_phase.hybrid_retriever import HybridRetriever
from query_phase.ollama_interface import OllamaInterface
from build_phase.indexer import FAISSIndexer
from build_phase.embedder import Embedder


class GraphRAGEngine:
    """Main Graph-RAG engine for query answering"""

    def __init__(self, graph_path=None, index_path=None):
        self.config = get_query_config()

        logger.info("Initializing Graph-RAG Engine...")

        # Load graph
        self.graph_loader = GraphLoader()
        self.graph_loader.load_graph(graph_path)

        if self.graph_loader.shared_config.metadata_path.exists():
            self.graph_loader.load_metadata()

        # Load index
        self.indexer = FAISSIndexer()
        self.indexer.load_chunk_index(index_path)

        # Initialize embedder
        self.embedder = Embedder()

        # Initialize retriever
        self.retriever = HybridRetriever(
            self.graph_loader,
            self.indexer,
            self.embedder
        )

        # Initialize Ollama
        self.ollama = OllamaInterface()

        # Check Ollama connection
        if not self.ollama.check_connection():
            logger.warning("Cannot connect to Ollama. Answer generation may fail.")

        # Load chunk texts (for context assembly)
        self.chunk_texts: Dict[str, str] = {}

        logger.info("Graph-RAG Engine initialized successfully")

    def query(self, question: str) -> QueryResult:
        """
        Process a query and generate answer

        Args:
            question: User question

        Returns:
            QueryResult with answer and context
        """
        start_time = time.time()

        logger.info(f"Processing query: {question}")

        # Step 1: Retrieve relevant context
        retrieval_results = self.retriever.retrieve(question)

        # Step 2: Get chunk texts
        self._populate_chunk_texts(retrieval_results)

        # Step 3: Assemble context
        context = self._assemble_context(question, retrieval_results)

        # Step 4: Generate answer
        answer = self._generate_answer(question, context, retrieval_results)

        # Step 5: Extract citations
        citations = self._extract_citations(context)

        processing_time = time.time() - start_time

        # Create result
        result = QueryResult(
            query=question,
            answer=answer,
            context=context,
            retrieval_results=retrieval_results,
            citations=citations,
            processing_time=processing_time,
            metadata={
                'num_chunks': len(retrieval_results),
                'num_entities': len(context.entities),
                'num_relationships': len(context.relationships)
            }
        )

        logger.info(f"Query processed in {processing_time:.2f}s")

        return result

    def _populate_chunk_texts(self, retrieval_results: List[RetrievalResult]) -> None:
        """
        Populate chunk texts from graph data

        Args:
            retrieval_results: List of retrieval results
        """
        for result in retrieval_results:
            if result.chunk_id not in self.chunk_texts:
                # Try to get chunk text from graph node attributes
                # In a full implementation, chunk texts would be stored separately
                # For now, we'll use a placeholder
                self.chunk_texts[result.chunk_id] = f"[Chunk {result.chunk_id}]"

            # Update result with text
            result.text = self.chunk_texts.get(result.chunk_id, "")

    def _assemble_context(
        self,
        query: str,
        retrieval_results: List[RetrievalResult]
    ) -> GraphContext:
        """
        Assemble context from retrieval results

        Args:
            query: User query
            retrieval_results: Retrieved chunks and entities

        Returns:
            GraphContext object
        """
        logger.debug("Assembling context")

        context = GraphContext()

        # Collect entities from retrieval results
        entity_ids = set()

        for result in retrieval_results:
            # Get entities from chunks
            # Note: In full implementation, we'd have chunk->entity mapping
            # For now, extract from graph based on chunk relationships
            pass

        # Extract entities from query
        query_entities = self.retriever._extract_query_entities(query)
        entity_ids.update(query_entities)

        # Get entity context
        if entity_ids:
            entity_context = self.retriever.get_entity_context(list(entity_ids))

            # Add entities
            for entity_info in entity_context['entities']:
                # Create Entity object (simplified)
                context.entities.append(entity_info)

            # Add relationships
            context.relationships = entity_context['relationships']

        # Add chunks
        for result in retrieval_results[:self.config.top_k_vector]:
            # Create simplified TextChunk
            chunk = TextChunk(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                text=result.text,
                start_char=0,
                end_char=len(result.text),
                chunk_index=0,
                token_count=count_tokens(result.text)
            )
            context.chunks.append(chunk)

        logger.debug(f"Context assembled: {len(context.entities)} entities, {len(context.chunks)} chunks")

        return context

    def _generate_answer(
        self,
        question: str,
        context: GraphContext,
        retrieval_results: List[RetrievalResult]
    ) -> str:
        """
        Generate answer using Ollama

        Args:
            question: User question
            context: Assembled context
            retrieval_results: Retrieval results

        Returns:
            Generated answer
        """
        logger.debug("Generating answer")

        # Build context string
        context_parts = []

        # Add entity information
        if context.entities:
            entity_info = "Entities mentioned:\n"
            for entity in context.entities[:10]:  # Limit to top 10
                entity_info += f"- {entity.get('name', 'Unknown')} ({entity.get('type', 'Unknown')})\n"
            context_parts.append(entity_info)

        # Add relationships
        if context.relationships:
            rel_info = "Relationships:\n"
            for source, target, rel_type in context.relationships[:10]:
                source_name = self.graph_loader.get_entity(source)
                target_name = self.graph_loader.get_entity(target)

                if source_name and target_name:
                    rel_info += f"- {source_name.get('name', '?')} --[{rel_type}]--> {target_name.get('name', '?')}\n"

            context_parts.append(rel_info)

        # Add chunk texts
        if context.chunks:
            chunk_info = "Relevant information:\n"
            for i, chunk in enumerate(context.chunks[:5], 1):  # Limit to top 5
                chunk_info += f"{i}. {chunk.text}\n\n"
            context_parts.append(chunk_info)

        context_str = "\n\n".join(context_parts)

        # Limit context to token budget
        max_tokens = self.config.max_context_tokens
        while count_tokens(context_str) > max_tokens:
            # Reduce context
            if len(context_parts) > 1:
                context_parts = context_parts[:-1]
                context_str = "\n\n".join(context_parts)
            else:
                # Truncate the last part
                context_str = truncate_text(context_str, max_length=max_tokens * 4)
                break

        # Extract entity names for citations
        entity_names = [e.get('name', '') for e in context.entities if e.get('name')]

        # Generate answer
        answer = self.ollama.generate_answer(
            question,
            context_str,
            entities=entity_names,
            include_citations=self.config.enable_citations
        )

        return answer

    def _extract_citations(self, context: GraphContext) -> List[str]:
        """
        Extract citations from context

        Args:
            context: GraphContext

        Returns:
            List of citation strings
        """
        citations = []

        # Add entity citations
        for entity in context.entities:
            name = entity.get('name', '')
            entity_type = entity.get('type', '')
            if name:
                citations.append(f"{name} ({entity_type})")

        # Deduplicate
        citations = list(set(citations))

        return citations[:10]  # Limit to top 10

    def get_statistics(self) -> Dict:
        """
        Get engine statistics

        Returns:
            Dictionary of statistics
        """
        stats = {
            'graph_loaded': self.graph_loader.is_loaded(),
            'num_entities': len(self.graph_loader.entity_index),
            'num_chunks_indexed': len(self.indexer.chunk_id_map) if self.indexer.chunk_id_map else 0,
            'ollama_connected': self.ollama.check_connection(),
            'config': {
                'top_k_vector': self.config.top_k_vector,
                'top_k_graph': self.config.top_k_graph,
                'graph_hops': self.config.graph_hops,
                'answer_model': self.config.answer_model
            }
        }

        return stats


if __name__ == "__main__":
    # Test Graph-RAG engine
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    try:
        # Initialize engine
        engine = GraphRAGEngine()

        # Print statistics
        stats = engine.get_statistics()

        print("\n=== Graph-RAG Engine Statistics ===")
        print(f"Graph loaded: {stats['graph_loaded']}")
        print(f"Entities: {stats['num_entities']}")
        print(f"Chunks indexed: {stats['num_chunks_indexed']}")
        print(f"Ollama connected: {stats['ollama_connected']}")

        # Test query
        if stats['graph_loaded'] and stats['ollama_connected']:
            print("\n=== Test Query ===")
            query = "What information do you have?"

            result = engine.query(query)

            print(f"\nQuery: {result.query}")
            print(f"Answer: {result.answer}")
            print(f"Processing time: {result.processing_time:.2f}s")
            print(f"Retrieved chunks: {len(result.retrieval_results)}")
            print(f"Citations: {', '.join(result.citations)}")

    except Exception as e:
        logger.error(f"Error initializing engine: {e}")
        print(f"\n✗ Error: {e}")
        print("\nPlease ensure:")
        print("1. Knowledge graph has been built (run build script)")
        print("2. Ollama is running (ollama serve)")
        print("3. Model is available (ollama pull gemma2:2b)")
