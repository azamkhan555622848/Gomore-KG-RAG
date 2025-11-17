#!/usr/bin/env python3
"""
Simple test script to query the knowledge graph
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from shared.utils import setup_logging
from query_phase.graph_rag_engine import GraphRAGEngine


def main():
    # Setup logging
    setup_logging()

    print("\n" + "=" * 60)
    print("Loading Knowledge Graph...")
    print("=" * 60 + "\n")

    # Initialize engine
    engine = GraphRAGEngine()

    # Print stats
    stats = engine.get_statistics()
    print(f"✓ Graph loaded successfully!")
    print(f"  - Entities: {stats['num_entities']}")
    print(f"  - Chunks indexed: {stats['num_chunks_indexed']}")
    print(f"  - Ollama connected: {stats['ollama_connected']}")

    # Example queries
    test_queries = [
        "What are the benefits of exercise?",
        "Tell me about muscle recovery",
        "What courses are available?"
    ]

    print("\n" + "=" * 60)
    print("Running Test Queries")
    print("=" * 60 + "\n")

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─' * 60}")
        print(f"Query {i}: {query}")
        print(f"{'─' * 60}\n")

        result = engine.query(query)

        print(f"Answer:\n{result.answer}\n")

        if result.retrieval_results:
            print(f"Sources ({len(result.retrieval_results)} chunks):")
            for j, source in enumerate(result.retrieval_results[:3], 1):
                print(f"  {j}. Score: {source.score:.3f} - {source.text[:80]}...")

        if result.context and result.context.entities:
            entities = [e['name'] if isinstance(e, dict) else e.name for e in result.context.entities[:5]]
            print(f"\nRelated entities: {', '.join(entities)}")

        print(f"\nProcessing time: {result.processing_time:.2f}s")

        print()

    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print("\nTo use interactively, run: python scripts/query_cli.py")
    print()


if __name__ == "__main__":
    main()
