"""
LLM Prompt Templates for Graph-RAG
Optimized for entity and relationship extraction
"""

# Entity Extraction Prompt
ENTITY_EXTRACTION_PROMPT = """You are an expert at extracting structured entities from text.

Extract ALL entities from the following text and classify them into these types:
- PERSON: People, characters, names
- ORGANIZATION: Companies, institutions, groups
- LOCATION: Places, cities, countries, geographical locations
- DATE: Dates, times, temporal expressions
- PRODUCT: Products, services, items
- CONCEPT: Abstract concepts, ideas, theories
- EVENT: Events, occurrences, happenings
- TECHNOLOGY: Technologies, tools, methods, systems

Text to analyze:
\"\"\"
{text}
\"\"\"

Return ONLY a valid JSON array with this exact format:
[
  {{"entity": "entity name", "type": "ENTITY_TYPE", "context": "surrounding context"}},
  ...
]

Requirements:
- Extract ALL mentioned entities (up to 20 most important)
- Normalize entity names (e.g., "Dr. Smith" → "Smith")
- Include brief context for disambiguation
- Return ONLY the JSON array, no other text
- If no entities found, return []

JSON output:"""


# Relationship Extraction Prompt
RELATIONSHIP_EXTRACTION_PROMPT = """You are an expert at extracting relationships between entities from text.

Given the following text and entities, extract relationships between entity pairs.

Text:
\"\"\"
{text}
\"\"\"

Entities found:
{entities}

Extract relationships using these types:
- RELATED_TO: General association
- PART_OF: Component or membership
- LOCATED_IN: Spatial relationship
- WORKS_FOR: Employment relationship
- CREATED_BY: Authorship or creation
- OCCURRED_AT: Temporal relationship
- USES: Usage or application
- CAUSES: Causal relationship

Return ONLY a valid JSON array with this exact format:
[
  {{
    "source": "entity1",
    "relation": "RELATION_TYPE",
    "target": "entity2",
    "context": "sentence showing relationship"
  }},
  ...
]

Requirements:
- Only extract relationships explicitly stated in the text
- Focus on the most important relationships (up to 15)
- Include context sentence that shows the relationship
- Return ONLY the JSON array, no other text
- If no relationships found, return []

JSON output:"""


# Query Entity Extraction Prompt (for query phase)
QUERY_ENTITY_EXTRACTION_PROMPT = """Extract key entities from this user query.

Query: {query}

Return ONLY a JSON array of entity names mentioned in the query:
["entity1", "entity2", ...]

If no entities found, return []

JSON output:"""


# Answer Generation Prompt
ANSWER_GENERATION_PROMPT = """You are a helpful assistant that answers questions based on provided context from a knowledge graph.

Context from knowledge graph:
{context}

User question: {question}

Instructions:
- Answer the question using ONLY the information from the provided context
- Be concise and accurate
- If the context doesn't contain enough information, say "I don't have enough information to answer that question."
- Include specific details and facts from the context
- Cite relevant entities or sources when possible

Answer:"""


# Answer Generation with Citations Prompt
ANSWER_GENERATION_WITH_CITATIONS_PROMPT = """You are a helpful assistant that answers questions based on provided context from a knowledge graph.

Context from knowledge graph:
{context}

Entities in context:
{entities}

User question: {question}

Instructions:
- Answer the question using ONLY the information from the provided context
- Be concise and accurate
- Include citations to specific entities, documents, or facts in [square brackets]
- If the context doesn't contain enough information, say "I don't have enough information to answer that question."
- Cite relevant sources for key claims

Answer with citations:"""


# Entity Resolution Prompt (for deduplication)
ENTITY_RESOLUTION_PROMPT = """Determine if these two entity mentions refer to the same real-world entity.

Entity 1: "{entity1}"
Context 1: {context1}

Entity 2: "{entity2}"
Context 2: {context2}

Are these the same entity? Consider:
- Name variations (nicknames, abbreviations, full names)
- Context similarity
- Type consistency

Return ONLY: "YES" or "NO"

Answer:"""


# Graph Summary Prompt (for debugging/stats)
GRAPH_SUMMARY_PROMPT = """Summarize the key information in this knowledge graph.

Graph statistics:
- Nodes: {num_nodes}
- Edges: {num_edges}
- Top entities: {top_entities}
- Top relationships: {top_relations}

Provide a brief (3-5 sentences) summary of what this knowledge graph contains.

Summary:"""


def format_entity_extraction_prompt(text: str) -> str:
    """Format entity extraction prompt with text"""
    return ENTITY_EXTRACTION_PROMPT.format(text=text)


def format_relationship_extraction_prompt(text: str, entities: list) -> str:
    """Format relationship extraction prompt with text and entities"""
    entities_str = "\n".join([f"- {e['entity']} ({e['type']})" for e in entities])
    return RELATIONSHIP_EXTRACTION_PROMPT.format(text=text, entities=entities_str)


def format_query_entity_extraction_prompt(query: str) -> str:
    """Format query entity extraction prompt"""
    return QUERY_ENTITY_EXTRACTION_PROMPT.format(query=query)


def format_answer_generation_prompt(context: str, question: str) -> str:
    """Format answer generation prompt"""
    return ANSWER_GENERATION_PROMPT.format(context=context, question=question)


def format_answer_generation_with_citations_prompt(
    context: str, entities: list, question: str
) -> str:
    """Format answer generation prompt with citations"""
    entities_str = ", ".join(entities)
    return ANSWER_GENERATION_WITH_CITATIONS_PROMPT.format(
        context=context, entities=entities_str, question=question
    )


def format_entity_resolution_prompt(
    entity1: str, context1: str, entity2: str, context2: str
) -> str:
    """Format entity resolution prompt"""
    return ENTITY_RESOLUTION_PROMPT.format(
        entity1=entity1, context1=context1, entity2=entity2, context2=context2
    )


def format_graph_summary_prompt(
    num_nodes: int, num_edges: int, top_entities: list, top_relations: list
) -> str:
    """Format graph summary prompt"""
    return GRAPH_SUMMARY_PROMPT.format(
        num_nodes=num_nodes,
        num_edges=num_edges,
        top_entities=", ".join(top_entities[:10]),
        top_relations=", ".join(top_relations[:10]),
    )
