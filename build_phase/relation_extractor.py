"""
Relationship Extraction using Ollama LLM
Extracts relationships between entities from text
"""

import time
from typing import List, Dict
from loguru import logger

from shared.models import Relationship, RelationType, Entity, TextChunk, RelationshipExtractionResult
from shared.utils import generate_id, extract_json_from_text
from shared.prompts import format_relationship_extraction_prompt
from shared.config import get_build_config
from build_phase.entity_extractor import OllamaClient


class RelationshipExtractor:
    """Extract relationships between entities using LLM"""

    def __init__(self):
        self.config = get_build_config()
        self.ollama = OllamaClient(
            host=self.config.ollama_host,
            model=self.config.extraction_model
        )

        logger.info("RelationshipExtractor initialized")

    def extract_relationships(
        self,
        chunk: TextChunk,
        entities: List[Entity]
    ) -> RelationshipExtractionResult:
        """
        Extract relationships from a chunk given its entities

        Args:
            chunk: TextChunk object
            entities: List of entities found in this chunk

        Returns:
            RelationshipExtractionResult with extracted relationships
        """
        if len(entities) < 2:
            # Need at least 2 entities for a relationship
            return RelationshipExtractionResult(
                chunk_id=chunk.chunk_id,
                relationships=[],
                extraction_time=0.0,
                model_used=self.config.extraction_model
            )

        start_time = time.time()

        # Format entities for prompt
        entity_dicts = [
            {
                "entity": e.name,
                "type": e.entity_type.value
            }
            for e in entities
        ]

        # Format prompt
        prompt = format_relationship_extraction_prompt(chunk.text, entity_dicts)

        # Generate response
        response = self.ollama.generate(
            prompt=prompt,
            max_tokens=self.config.max_extraction_tokens,
            temperature=self.config.temperature
        )

        # Parse relationships
        relationships = self._parse_relationship_response(response, chunk, entities)

        extraction_time = time.time() - start_time

        logger.debug(f"Extracted {len(relationships)} relationships from chunk {chunk.chunk_id} in {extraction_time:.2f}s")

        return RelationshipExtractionResult(
            chunk_id=chunk.chunk_id,
            relationships=relationships,
            extraction_time=extraction_time,
            model_used=self.config.extraction_model
        )

    def extract_relationships_batch(
        self,
        chunks: List[TextChunk],
        chunk_entities: Dict[str, List[Entity]]
    ) -> List[RelationshipExtractionResult]:
        """
        Extract relationships from multiple chunks

        Args:
            chunks: List of TextChunk objects
            chunk_entities: Dict mapping chunk_id to list of entities

        Returns:
            List of RelationshipExtractionResult objects
        """
        logger.info(f"Extracting relationships from {len(chunks)} chunks")

        results = []

        for i, chunk in enumerate(chunks):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(chunks)} chunks processed")

            try:
                # Get entities for this chunk
                entities = chunk_entities.get(chunk.chunk_id, [])

                result = self.extract_relationships(chunk, entities)
                results.append(result)

            except Exception as e:
                logger.error(f"Error extracting relationships from chunk {chunk.chunk_id}: {e}")
                # Add empty result
                results.append(RelationshipExtractionResult(
                    chunk_id=chunk.chunk_id,
                    relationships=[],
                    extraction_time=0.0,
                    model_used=self.config.extraction_model
                ))

        total_relations = sum(len(r.relationships) for r in results)
        logger.info(f"Completed relationship extraction. Total relationships: {total_relations}")

        return results

    def _parse_relationship_response(
        self,
        response: str,
        chunk: TextChunk,
        entities: List[Entity]
    ) -> List[Relationship]:
        """
        Parse LLM response into Relationship objects

        Args:
            response: LLM response text
            chunk: Source chunk
            entities: Entities in the chunk

        Returns:
            List of Relationship objects
        """
        # Extract JSON from response
        json_data = extract_json_from_text(response)

        if not json_data or not isinstance(json_data, list):
            logger.warning(f"Could not parse relationship response for chunk {chunk.chunk_id}")
            return []

        # Create entity name to ID mapping
        entity_map = {e.name.lower(): e.entity_id for e in entities}

        relationships = []

        for item in json_data[:self.config.max_relations_per_pair * len(entities)]:
            try:
                # Validate required fields
                if not isinstance(item, dict):
                    continue

                required_fields = ["source", "relation", "target"]
                if not all(field in item for field in required_fields):
                    continue

                source_name = item["source"].strip().lower()
                target_name = item["target"].strip().lower()
                relation_str = item["relation"].upper()

                # Find entity IDs
                source_id = None
                target_id = None

                # Try exact match first
                source_id = entity_map.get(source_name)
                target_id = entity_map.get(target_name)

                # Try fuzzy match if exact match fails
                if not source_id:
                    source_id = self._fuzzy_find_entity(source_name, entities)
                if not target_id:
                    target_id = self._fuzzy_find_entity(target_name, entities)

                if not source_id or not target_id:
                    logger.debug(f"Could not find entity IDs for relation: {source_name} -> {target_name}")
                    continue

                # Skip self-relationships
                if source_id == target_id:
                    continue

                # Validate relation type
                try:
                    relation_type = RelationType[relation_str]
                except KeyError:
                    # Default to RELATED_TO if unknown type
                    relation_type = RelationType.RELATED_TO

                # Create relationship
                relation_id = generate_id(f"{source_id}_{target_id}_{relation_type.value}", prefix="rel_")

                relationship = Relationship(
                    relation_id=relation_id,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relation_type=relation_type,
                    context=item.get("context", "")[:200],  # Limit context length
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    confidence=1.0
                )

                relationships.append(relationship)

            except Exception as e:
                logger.warning(f"Error parsing relationship item {item}: {e}")
                continue

        return relationships

    def _fuzzy_find_entity(self, name: str, entities: List[Entity]) -> str:
        """
        Find entity ID using fuzzy matching

        Args:
            name: Entity name to find
            entities: List of entities

        Returns:
            Entity ID or None
        """
        name_lower = name.lower()

        # Try partial match
        for entity in entities:
            if name_lower in entity.name.lower() or entity.name.lower() in name_lower:
                return entity.entity_id

            # Check mentions
            for mention in entity.mentions:
                if name_lower in mention.lower() or mention.lower() in name_lower:
                    return entity.entity_id

        return None

    def deduplicate_relationships(self, all_relationships: List[Relationship]) -> List[Relationship]:
        """
        Deduplicate relationships

        Args:
            all_relationships: List of all extracted relationships

        Returns:
            Deduplicated list of relationships
        """
        logger.info(f"Deduplicating {len(all_relationships)} relationships")

        # Group by (source, target, relation_type)
        rel_groups: Dict[tuple, List[Relationship]] = {}

        for rel in all_relationships:
            key = (rel.source_entity_id, rel.target_entity_id, rel.relation_type.value)

            if key not in rel_groups:
                rel_groups[key] = []
            rel_groups[key].append(rel)

        # Merge relationships with same key
        deduplicated = []

        for key, group in rel_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Merge relationships
                merged = self._merge_relationships(group)
                deduplicated.append(merged)

        logger.info(f"Deduplicated to {len(deduplicated)} unique relationships")

        return deduplicated

    def _merge_relationships(self, relationships: List[Relationship]) -> Relationship:
        """
        Merge multiple relationships with same source/target/type

        Args:
            relationships: List of relationships to merge

        Returns:
            Merged relationship
        """
        # Use first relationship as base
        merged = relationships[0].model_copy()

        # Use longest context
        contexts = [r.context for r in relationships if r.context]
        if contexts:
            merged.context = max(contexts, key=len)

        # Average confidence
        merged.confidence = sum(r.confidence for r in relationships) / len(relationships)

        return merged


if __name__ == "__main__":
    # Test the relationship extractor
    from shared.utils import setup_logging
    from build_phase.document_loader import TextChunker
    from build_phase.entity_extractor import EntityExtractor

    setup_logging(level="INFO")

    # Test sample
    sample_text = """
    Dr. Jane Smith works for Google in Mountain View, California.
    She developed a new AI technology called DeepMind Assistant in 2024.
    Google is located in Mountain View and specializes in AI research.
    """

    # Extract entities first
    chunker = TextChunker()
    chunks = chunker.chunk_text(sample_text, "test_doc")

    entity_extractor = EntityExtractor()
    entity_result = entity_extractor.extract_entities(chunks[0])

    print(f"Extracted {len(entity_result.entities)} entities:")
    for entity in entity_result.entities:
        print(f"  - {entity.name} ({entity.entity_type.value})")

    # Extract relationships
    relation_extractor = RelationshipExtractor()
    relation_result = relation_extractor.extract_relationships(
        chunks[0],
        entity_result.entities
    )

    print(f"\nExtracted {len(relation_result.relationships)} relationships:")
    for rel in relation_result.relationships:
        source = next((e.name for e in entity_result.entities if e.entity_id == rel.source_entity_id), "?")
        target = next((e.name for e in entity_result.entities if e.entity_id == rel.target_entity_id), "?")
        print(f"  - {source} --[{rel.relation_type.value}]--> {target}")
