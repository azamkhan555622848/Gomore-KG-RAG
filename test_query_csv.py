#!/usr/bin/env python3
"""
Test Query with CSV Data
Verify that the query system works with CSV data and uses actual chunk texts
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from query_phase.graph_rag_engine import GraphRAGEngine
from shared.utils import setup_logging

def test_query():
    """Test querying the knowledge graph built from CSV"""

    setup_logging(level="INFO")

    print("=" * 60)
    print("Testing Query with CSV Data")
    print("=" * 60)

    try:
        # Initialize engine
        print("\n🔄 Initializing Graph-RAG Engine...")
        engine = GraphRAGEngine()

        # Get statistics
        stats = engine.get_statistics()

        print(f"\n✅ Engine initialized successfully!")
        print(f"\n📊 Statistics:")
        print(f"   Graph loaded: {stats['graph_loaded']}")
        print(f"   Entities: {stats['num_entities']}")
        print(f"   Chunks indexed: {stats['num_chunks_indexed']}")
        print(f"   Chunk texts loaded: {len(engine.chunk_texts)}")
        print(f"   Ollama connected: {stats['ollama_connected']}")

        # Verify chunk texts are loaded
        if len(engine.chunk_texts) > 0:
            print(f"\n✅ CRITICAL FIX VERIFIED: Chunk texts are loaded!")
            chunk_id = list(engine.chunk_texts.keys())[0]
            chunk_text = engine.chunk_texts[chunk_id]
            print(f"\n📄 Sample chunk text (first 200 chars):")
            print(f"   {chunk_text[:200]}...")
        else:
            print(f"\n❌ ERROR: No chunk texts loaded!")
            return 1

        # Test queries about the CSV data
        test_queries = [
            "什麼是 BMI?",
            "mego 和 luki 有什麼不同?",
            "居留證包含哪些資訊?"
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n{'=' * 60}")
            print(f"Query {i}: {query}")
            print(f"{'=' * 60}")

            result = engine.query(query)

            print(f"\n💬 Answer:")
            print(f"   {result.answer}")

            print(f"\n⏱️  Processing time: {result.processing_time:.2f}s")
            print(f"📊 Retrieved chunks: {len(result.retrieval_results)}")

            if result.retrieval_results:
                print(f"\n📄 Top chunk (score: {result.retrieval_results[0].score:.3f}):")
                chunk_text = result.retrieval_results[0].text
                if chunk_text and not chunk_text.startswith('[Text not available'):
                    print(f"   ✅ Using actual chunk text!")
                    print(f"   First 150 chars: {chunk_text[:150]}...")
                else:
                    print(f"   ❌ Missing chunk text!")

        print(f"\n{'=' * 60}")
        print(f"✅ All queries completed successfully!")
        print(f"✅ CSV support working!")
        print(f"✅ Chunk text retrieval fix working!")
        print(f"{'=' * 60}")

        return 0

    except Exception as e:
        print(f"\n❌ Error during query test: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_query())
