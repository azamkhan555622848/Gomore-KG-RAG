#!/usr/bin/env python3
"""
Query CLI for Graph-RAG
Interactive command-line interface for querying the knowledge graph
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from shared.utils import setup_logging
from query_phase.graph_rag_engine import GraphRAGEngine


def print_banner():
    """Print welcome banner"""
    print("\n" + "=" * 60)
    print("Graph-RAG Query Interface")
    print("=" * 60)
    print("Ask questions about your documents!")
    print("Commands: /help, /stats, /exit")
    print("=" * 60 + "\n")


def print_help():
    """Print help message"""
    print("\nAvailable commands:")
    print("  /help   - Show this help message")
    print("  /stats  - Show system statistics")
    print("  /exit   - Exit the program")
    print("  <question> - Ask a question\n")


def print_stats(engine: GraphRAGEngine):
    """Print system statistics"""
    stats = engine.get_statistics()

    print("\n" + "=" * 60)
    print("System Statistics")
    print("=" * 60)
    print(f"Graph loaded: {stats['graph_loaded']}")
    print(f"Entities: {stats['num_entities']}")
    print(f"Chunks indexed: {stats['num_chunks_indexed']}")
    print(f"Ollama connected: {stats['ollama_connected']}")
    print(f"\nConfiguration:")
    print(f"  Top-K (vector): {stats['config']['top_k_vector']}")
    print(f"  Top-K (graph): {stats['config']['top_k_graph']}")
    print(f"  Graph hops: {stats['config']['graph_hops']}")
    print(f"  Answer model: {stats['config']['answer_model']}")
    print("=" * 60 + "\n")


def print_result(result):
    """Print query result"""
    print("\n" + "-" * 60)
    print(f"Answer:")
    print("-" * 60)
    print(result.answer)

    if result.citations:
        print("\n" + "-" * 60)
        print(f"Sources:")
        print("-" * 60)
        for citation in result.citations[:5]:
            print(f"  • {citation}")

    print("\n" + "-" * 60)
    print(f"Metadata:")
    print("-" * 60)
    print(f"  Retrieved chunks: {len(result.retrieval_results)}")
    print(f"  Entities found: {result.metadata.get('num_entities', 0)}")
    print(f"  Relationships: {result.metadata.get('num_relationships', 0)}")
    print(f"  Processing time: {result.processing_time:.2f}s")
    print("-" * 60 + "\n")


def main():
    """Main CLI loop"""

    # Setup logging (quiet mode for CLI)
    setup_logging(level="WARNING")

    print_banner()

    # Initialize engine
    print("Loading knowledge graph...")

    try:
        engine = GraphRAGEngine()
        print("✓ Knowledge graph loaded successfully!\n")
    except Exception as e:
        print(f"\n✗ Error loading knowledge graph: {e}")
        print("\nPlease ensure:")
        print("1. Knowledge graph has been built (run: python scripts/build_graph.py)")
        print("2. Graph files exist in data/graph_export/")
        print("3. Index files exist in data/indexes/\n")
        return 1

    # Check Ollama
    if not engine.ollama.check_connection():
        print("\n⚠ Warning: Cannot connect to Ollama")
        print("Please ensure Ollama is running:")
        print("  1. Start Ollama: ollama serve")
        print("  2. Pull model: ollama pull gemma3:1b\n")
        return 1

    # Main loop
    while True:
        try:
            # Get user input
            query = input("You: ").strip()

            if not query:
                continue

            # Handle commands
            if query.startswith('/'):
                command = query.lower()

                if command == '/exit' or command == '/quit':
                    print("\nGoodbye!\n")
                    break
                elif command == '/help':
                    print_help()
                elif command == '/stats':
                    print_stats(engine)
                else:
                    print(f"\nUnknown command: {query}")
                    print("Type /help for available commands\n")

                continue

            # Process query
            print("\nProcessing...")

            result = engine.query(query)

            print_result(result)

        except KeyboardInterrupt:
            print("\n\nGoodbye!\n")
            break
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            print(f"\n✗ Error: {e}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
