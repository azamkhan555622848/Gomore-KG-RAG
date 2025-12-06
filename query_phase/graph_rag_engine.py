"""
Graph-RAG Engine
Main orchestration for query processing and answer generation
"""

import time
import json
import gzip
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

# Import character prompts
from shared.character_prompts import (
    format_mego_answer_prompt,
    format_luki_answer_prompt,
    format_mego_health_advice,
    format_luki_health_advice,
    format_residence_card_mego,
    format_residence_card_luki,
    translate_activity_level
)


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

        # Load chunk data (for context assembly)
        self.chunk_data: Dict[str, Dict] = {}
        self._load_chunk_texts()

        logger.info("Graph-RAG Engine initialized successfully")

    def _load_chunk_texts(self) -> None:
        """
        Load chunk data from exported file
        """
        chunk_texts_path = self.graph_loader.shared_config.graph_path.parent / "chunk_texts.json.gz"

        if not chunk_texts_path.exists():
            logger.warning(f"Chunk data file not found: {chunk_texts_path}")
            logger.warning("Chunk data will not be available for context assembly")
            return

        try:
            logger.info(f"Loading chunk data from {chunk_texts_path}")
            with gzip.open(chunk_texts_path, 'rt', encoding='utf-8') as f:
                self.chunk_data = json.load(f)

            logger.info(f"Loaded data for {len(self.chunk_data)} chunks")

        except Exception as e:
            logger.error(f"Error loading chunk data: {e}")
            logger.warning("Proceeding without chunk data")

    def query(self, question: str, character: str = "mego", user_data: Optional[Dict] = None, case: Optional[str] = None) -> QueryResult:
        """
        Process a query and generate answer

        Args:
            question: User question
            character: Character style ("mego" or "luki")
            user_data: Optional user data for personalized responses (age, bmi, etc.)
            case: Optional case for specific query types

        Returns:
            QueryResult with answer and context
        """
        start_time = time.time()

        logger.info(f"Processing query: {question} (Case: {case})")

        # Handle case-specific logic that doesn't require standard retrieval/answer flow
        if case == "島民居留證摘要":
            if not user_data:
                raise ValueError("user_data is required for 島民居留證摘要 case")
            
            answer = self.generate_residence_card(user_data, character)
            
            return QueryResult(
                query=question,
                answer=answer,
                context=GraphContext(),
                retrieval_results=[],
                citations=[],
                processing_time=time.time() - start_time
            )

        # Standard RAG flow for other cases
        # Step 1: Retrieve relevant context
        retrieval_results = self.retriever.retrieve(question)

        # Step 2: Get chunk texts
        self._populate_chunk_texts(retrieval_results)

        # Step 3: Assemble context
        context = self._assemble_context(question, retrieval_results)

        # Step 4: Generate answer
        answer = self._generate_answer(question, context, retrieval_results, character, user_data, case)

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
        Populate chunk texts, tags, and notes from loaded chunk data

        Args:
            retrieval_results: List of retrieval results
        """
        for result in retrieval_results:
            # Get chunk data from loaded data
            chunk_data = self.chunk_data.get(result.chunk_id, {})

            if not chunk_data:
                logger.warning(f"Chunk data not found for {result.chunk_id}")
                result.text = f"[Text not available for {result.chunk_id}]"
                result.tags = None
                result.notes = None
            else:
                result.text = chunk_data.get('text', '')
                result.tags = chunk_data.get('tags')
                result.notes = chunk_data.get('notes')

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
                text=result.text or "",
                tags=result.tags,
                notes=result.notes,
                start_char=0,
                end_char=len(result.text or ""),
                chunk_index=0,
                token_count=count_tokens(result.text or "")
            )
            context.chunks.append(chunk)

        logger.debug(f"Context assembled: {len(context.entities)} entities, {len(context.chunks)} chunks")

        return context

    def _generate_answer(
        self,
        question: str,
        context: GraphContext,
        retrieval_results: List[RetrievalResult],
        character: str = "mego",
        user_data: Optional[Dict] = None,
        case: Optional[str] = None
    ) -> str:
        """
        Generate answer using Ollama with character-specific prompts

        Args:
            question: User question
            context: Assembled context
            retrieval_results: Retrieval results
            character: Character style ("mego" or "luki")
            user_data: Optional user data for personalized responses
            case: Optional case for specific prompt routing

        Returns:
            Generated answer
        """
        logger.debug(f"Generating answer for case: {case}")

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
                chunk_info += f"--- Start of Document {i} ---\n"
                if chunk.tags:
                    chunk_info += f"Tags: {chunk.tags}\n"
                if chunk.notes:
                    chunk_info += f"Summary Note: {chunk.notes}\n"
                chunk_info += f"Content: {chunk.text}\n"
                chunk_info += f"--- End of Document {i} ---\n\n"
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

        # Validate character
        character = character.lower()
        if character not in ["mego", "luki"]:
            logger.warning(f"Invalid character '{character}', defaulting to 'mego'")
            character = "mego"

        # Check if this is a health advice query with user data
        if user_data and self._is_health_advice_query(user_data):
            # Use health advice prompts
            answer = self._generate_health_advice(
                question, context_str, character, user_data
            )
        else:
            # Use general answer prompts
            answer = self._generate_general_answer(
                question, context_str, entity_names, character
            )
        
        # This logic is now handled by the case router, but as a fallback, we ensure TC.
        # This part of the code might be refactored further based on case handling.
        if not case: # Add instruction for non-case-based queries
             answer += "\n\n(請務必使用繁體中文回答)"


        return answer

    def _is_health_advice_query(self, user_data: Dict) -> bool:
        """
        Check if query requires health advice based on user data

        Args:
            user_data: User data dictionary

        Returns:
            True if all required fields are present
        """
        required_fields = ['age', 'gender', 'bmi', 'waist', 'activity_level', 'tdee', 'main_goal']
        return all(field in user_data for field in required_fields)

    def _generate_general_answer(
        self,
        question: str,
        context_str: str,
        entity_names: List[str],
        character: str
    ) -> str:
        """
        Generate general answer using character-specific prompts

        Args:
            question: User question
            context_str: Context string
            entity_names: List of entity names
            character: Character style ("mego" or "luki")

        Returns:
            Generated answer
        """
        # Format character-specific prompt
        if character == "mego":
            prompt = format_mego_answer_prompt(context_str, entity_names, question)
        else:  # luki
            prompt = format_luki_answer_prompt(context_str, entity_names, question)

        # Generate using Ollama directly (bypass the existing generate_answer)
        response = self.ollama._chat(
            prompt,
            max_tokens=self.config.max_answer_tokens,
            temperature=self.config.temperature
        )

        return response

    def _generate_health_advice(
        self,
        question: str,
        context_str: str,
        character: str,
        user_data: Dict
    ) -> str:
        """
        Generate personalized health advice using character-specific prompts

        Args:
            question: User question
            context_str: Context string
            character: Character style ("mego" or "luki")
            user_data: User data with health metrics

        Returns:
            Generated health advice
        """
        # Translate activity level to Chinese
        activity_level_zh = translate_activity_level(user_data.get('activity_level', 'medium'))

        # Format character-specific health advice prompt
        if character == "mego":
            prompt = format_mego_health_advice(
                age=user_data['age'],
                gender=user_data['gender'],
                bmi=user_data['bmi'],
                waist=user_data['waist'],
                activity_level=activity_level_zh,
                tdee=user_data['tdee'],
                main_goals=user_data['main_goal'],
                context=context_str,
                question=question
            )
        else:  # luki
            prompt = format_luki_health_advice(
                age=user_data['age'],
                gender=user_data['gender'],
                bmi=user_data['bmi'],
                waist=user_data['waist'],
                activity_level=activity_level_zh,
                tdee=user_data['tdee'],
                main_goals=user_data['main_goal'],
                context=context_str,
                question=question
            )

        # Generate using Ollama
        response = self.ollama._chat(
            prompt,
            max_tokens=self.config.max_answer_tokens,
            temperature=self.config.temperature
        )

        return response

    def generate_residence_card(
        self,
        user_data: Dict,
        character: str = "mego"
    ) -> str:
        """
        Generate personalized residence card summary for onboarding.
        This method now bypasses RAG and uses a direct-to-LLM approach
        with improved prompts to prevent goal hallucination.

        Args:
            user_data: User data with all required fields
            character: Character style ("mego" or "luki")

        Returns:
            Residence card summary text
        """
        # Validate character
        character = character.lower()
        if character not in ["mego", "luki"]:
            logger.warning(f"Invalid character '{character}', defaulting to 'mego'")
            character = "mego"

        # --- FIX: Bypass RAG and Goal Hallucination ---
        # The RAG retrieval was providing irrelevant context, causing the LLM to
        # ignore the user's actual goals and hallucinate new ones.
        # As per the analysis in module3, we now bypass retrieval entirely
        # and rely on the improved prompt structure.
        context_str = ""
        logger.debug("Bypassing RAG for residence card generation to prevent goal hallucination.")
        # --- END FIX ---

        # Translate activity level to Chinese
        activity_level_zh = translate_activity_level(user_data.get('activity_level', 'medium'))

        # Corrected user_data access from 'main_goal' to 'main_goals'
        main_goals = user_data.get('main_goals', [])

        # Format character-specific residence card prompt
        if character == "mego":
            prompt = format_residence_card_mego(
                user_id=user_data.get('user_id', 0),
                age=user_data.get('age'),
                gender=user_data.get('gender'),
                height=user_data.get('height'),
                weight=user_data.get('weight'),
                bmi=user_data.get('bmi'),
                waist=user_data.get('waist'),
                activity_level=activity_level_zh,
                tdee=user_data.get('tdee'),
                main_goals=main_goals,
                context=context_str
            )
        else:  # luki
            prompt = format_residence_card_luki(
                user_id=user_data.get('user_id', 0),
                age=user_data.get('age'),
                gender=user_data.get('gender'),
                height=user_data.get('height'),
                weight=user_data.get('weight'),
                bmi=user_data.get('bmi'),
                waist=user_data.get('waist'),
                activity_level=activity_level_zh,
                tdee=user_data.get('tdee'),
                main_goals=main_goals,
                context=context_str
            )

        # Generate using Ollama
        logger.info(f"Generating residence card for user {user_data.get('user_id', '?')} with character: {character}")
        summary = self.ollama._chat(
            prompt,
            max_tokens=512,  # Residence card summaries are shorter
            temperature=0.7  # Slightly more creative for engaging summaries
        )

        return summary

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
