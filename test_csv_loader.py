#!/usr/bin/env python3
"""
Test CSV Loading Functionality
Quick test to verify CSV files can be loaded and processed
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from build_phase.document_loader import DocumentLoader
from shared.utils import setup_logging

def test_csv_loading():
    """Test loading the module3.csv file"""

    setup_logging(level="INFO")

    print("=" * 60)
    print("Testing CSV Loading Functionality")
    print("=" * 60)

    csv_file = Path("documents/module3.csv")

    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return 1

    print(f"\n📄 Testing file: {csv_file}")
    print(f"   Size: {csv_file.stat().st_size:,} bytes")

    # Initialize document loader
    loader = DocumentLoader()

    try:
        # Load the CSV file
        print("\n🔄 Loading CSV file...")
        text, metadata = loader.load_document(csv_file)

        print(f"\n✅ CSV loaded successfully!")
        print(f"\n📊 Metadata:")
        print(f"   Document ID: {metadata.doc_id}")
        print(f"   Filename: {metadata.filename}")
        print(f"   File type: {metadata.file_type}")
        print(f"   File size: {metadata.file_size:,} bytes")

        print(f"\n📝 Extracted Text Stats:")
        print(f"   Total characters: {len(text):,}")
        print(f"   Total lines: {text.count(chr(10)) + 1}")

        # Show first 500 characters of converted text
        print(f"\n📄 First 500 characters of converted text:")
        print("-" * 60)
        print(text[:500])
        print("-" * 60)

        # Show last 300 characters
        print(f"\n📄 Last 300 characters of converted text:")
        print("-" * 60)
        print(text[-300:])
        print("-" * 60)

        # Test chunking
        from build_phase.document_loader import TextChunker

        print(f"\n🔪 Testing text chunking...")
        chunker = TextChunker()
        chunks = chunker.chunk_text(text, metadata.doc_id)

        print(f"\n✅ Chunking successful!")
        print(f"   Number of chunks: {len(chunks)}")

        if chunks:
            print(f"\n📦 First chunk details:")
            print(f"   Chunk ID: {chunks[0].chunk_id}")
            print(f"   Token count: {chunks[0].token_count}")
            print(f"   Text length: {len(chunks[0].text)} chars")
            print(f"\n   First 200 chars:")
            print(f"   {chunks[0].text[:200]}...")

        print(f"\n{'=' * 60}")
        print(f"✅ All tests passed successfully!")
        print(f"{'=' * 60}")

        return 0

    except Exception as e:
        print(f"\n❌ Error loading CSV: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_csv_loading())
