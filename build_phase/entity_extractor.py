"""
Entity Extraction using Ollama LLM
Extracts structured entities from text chunks
"""

import json
import time
from typing import List, Dict, Optional
from loguru import logger
import requests

from shared.models import Entity, EntityType, TextChunk, EntityExtractionResult
from shared.utils import generate_id, normalize_entity_name, extract_json_from_text
from shared.prompts import format_entity_extraction_prompt
from shared.config import get_build_config


class OllamaClient:
    """Client for interacting with Ollama API"""

    def __init__(self, host: str = "http://localhost:11434", model: str = "gemma2:2b"):
        self.host = host.rstrip('/')
        self.model = model
        self.chat_endpoint = f"{self.host}/api/chat"
        self.generate_endpoint = f"{self.host}/api/generate"

        logger.info(f"OllamaClient initialized. Host: {host}, Model: {model}")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        system: Optional[str] = None
    ) -> str:
        """
        Generate response from Ollama

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            system: Optional system message

        Returns:
            Generated text
        """
        try:
            # Prepare messages
            messages = []

            if system:
                messages.append({"role": "system", "content": system})

            messages.append({"role": "user", "content": prompt})

            # Make request
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }

            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=120
            )

            response.raise_for_status()

            # Extract response
            result = response.json()

            if "message" in result and "content" in result["message"]:
                return result["message"]["content"]
            else:
                logger.error(f"Unexpected response format: {result}")
                return ""

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return ""

    def check_connection(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False


class EntityExtractor:
    """Extract entities from text using LLM"""

    def __init__(self):
        self.config = get_build_config()
        self.ollama = OllamaClient(
            host=self.config.ollama_host,
            model=self.config.extraction_model
        )

        # Check Ollama connection
        if not self.ollama.check_connection():
            logger.warning(f"Cannot connect to Ollama at {self.config.ollama_host}")
            logger.warning("Make sure Ollama is running and accessible")

        logger.info("EntityExtractor initialized")

    def extract_entities(self, chunk: TextChunk) -> EntityExtractionResult:
        """
        Extract entities from a text chunk

        Args:
            chunk: TextChunk object

        Returns:
            EntityExtractionResult with extracted entities
        """
        start_time = time.time()

        # Format prompt
        prompt = format_entity_extraction_prompt(chunk.text)

        # Generate response
        response = self.ollama.generate(
            prompt=prompt,
            max_tokens=self.config.max_extraction_tokens,
            temperature=self.config.temperature
        )

        # Parse entities
        entities = self._parse_entity_response(response, chunk)

        extraction_time = time.time() - start_time

        logger.debug(f"Extracted {len(entities)} entities from chunk {chunk.chunk_id} in {extraction_time:.2f}s")

        return EntityExtractionResult(
            chunk_id=chunk.chunk_id,
            entities=entities,
            extraction_time=extraction_time,
            model_used=self.config.extraction_model
        )

    def extract_entities_batch(self, chunks: List[TextChunk]) -> List[EntityExtractionResult]:
        """
        Extract entities from multiple chunks

        Args:
            chunks: List of TextChunk objects

        Returns:
            List of EntityExtractionResult objects
        """
        logger.info(f"Extracting entities from {len(chunks)} chunks")

        results = []

        for i, chunk in enumerate(chunks):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(chunks)} chunks processed")

            try:
                result = self.extract_entities(chunk)
                results.append(result)
            except Exception as e:
                logger.error(f"Error extracting entities from chunk {chunk.chunk_id}: {e}")
                # Add empty result
                results.append(EntityExtractionResult(
                    chunk_id=chunk.chunk_id,
                    entities=[],
                    extraction_time=0.0,
                    model_used=self.config.extraction_model
                ))

        logger.info(f"Completed entity extraction. Total entities: {sum(len(r.entities) for r in results)}")

        return results

    def _parse_entity_response(self, response: str, chunk: TextChunk) -> List[Entity]:
        """
        Parse LLM response into Entity objects

        Args:
            response: LLM response text
            chunk: Source chunk

        Returns:
            List of Entity objects
        """
        # Extract JSON from response
        json_data = extract_json_from_text(response)

        if not json_data or not isinstance(json_data, list):
            logger.warning(f"Could not parse entity response for chunk {chunk.chunk_id}")
            return []

        entities = []

        for item in json_data[:self.config.max_entities_per_chunk]:
            try:
                # Validate required fields
                if not isinstance(item, dict) or "entity" not in item or "type" not in item:
                    continue

                entity_name = item["entity"].strip()
                entity_type_str = item["type"].upper()

                # Normalize entity name
                normalized_name = normalize_entity_name(entity_name)

                # Validate entity type
                try:
                    entity_type = EntityType[entity_type_str]
                except KeyError:
                    # Default to CONCEPT if unknown type
                    entity_type = EntityType.CONCEPT

                # Create entity
                entity_id = generate_id(normalized_name, prefix="ent_")

                entity = Entity(
                    entity_id=entity_id,
                    name=normalized_name,
                    entity_type=entity_type,
                    mentions=[entity_name],
                    context=item.get("context", "")[:200],  # Limit context length
                    chunk_ids=[chunk.chunk_id],
                    doc_ids=[chunk.doc_id],
                    mention_count=1
                )

                entities.append(entity)

            except Exception as e:
                logger.warning(f"Error parsing entity item {item}: {e}")
                continue

        return entities

    def deduplicate_entities(self, all_entities: List[Entity]) -> List[Entity]:
        """
        Deduplicate entities by name

        Args:
            all_entities: List of all extracted entities

        Returns:
            Deduplicated list of entities
        """
        logger.info(f"Deduplicating {len(all_entities)} entities")

        # Group by normalized name
        entity_groups: Dict[str, List[Entity]] = {}

        for entity in all_entities:
            if entity.name not in entity_groups:
                entity_groups[entity.name] = []
            entity_groups[entity.name].append(entity)

        # Merge entities with same name
        deduplicated = []

        for name, group in entity_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Merge entities
                merged = self._merge_entities(group)
                deduplicated.append(merged)

        logger.info(f"Deduplicated to {len(deduplicated)} unique entities")

        return deduplicated

    def _merge_entities(self, entities: List[Entity]) -> Entity:
        """
        Merge multiple entities with same name

        Args:
            entities: List of entities to merge

        Returns:
            Merged entity
        """
        # Use first entity as base
        merged = entities[0].model_copy()

        # Combine mentions
        all_mentions = set()
        all_chunk_ids = set()
        all_doc_ids = set()

        for entity in entities:
            all_mentions.update(entity.mentions)
            all_chunk_ids.update(entity.chunk_ids)
            all_doc_ids.update(entity.doc_ids)

        merged.mentions = list(all_mentions)
        merged.chunk_ids = list(all_chunk_ids)
        merged.doc_ids = list(all_doc_ids)
        merged.mention_count = len(all_chunk_ids)

        # Use longest context
        contexts = [e.context for e in entities if e.context]
        if contexts:
            merged.context = max(contexts, key=len)

        return merged


if __name__ == "__main__":
    # Test the entity extractor
    from shared.utils import setup_logging
    from build_phase.document_loader import TextChunker

    setup_logging(level="INFO")

    # Test Ollama connection
    ollama = OllamaClient()

    if ollama.check_connection():
        print("✓ Ollama connection successful")

        # Test entity extraction
        sample_text = """
        Dr. Jane Smith works for Google in Mountain View, California.
        She developed a new AI technology called DeepMind Assistant in 2024.
        The project aims to revolutionize natural language processing.
        """

        chunker = TextChunker()
        chunks = chunker.chunk_text(sample_text, "test_doc")

        extractor = EntityExtractor()
        result = extractor.extract_entities(chunks[0])

        print(f"\nExtracted {len(result.entities)} entities:")
        for entity in result.entities:
            print(f"  - {entity.name} ({entity.entity_type.value})")

    else:
        print("✗ Cannot connect to Ollama")
        print(f"  Make sure Ollama is running at {ollama.host}")
        print("  Start Ollama: ollama serve")
