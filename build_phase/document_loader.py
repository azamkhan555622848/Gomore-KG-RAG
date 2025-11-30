"""
Document Loader and Text Chunker for Graph-RAG
Supports PDF, DOCX, TXT, MD with graph-aware chunking
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from loguru import logger
import tiktoken
import pandas as pd

# Document parsing libraries
from PyPDF2 import PdfReader
from docx import Document
import markdown

from shared.models import DocumentMetadata, TextChunk
from shared.utils import generate_id, normalize_text, get_file_info, count_tokens
from shared.config import get_build_config


class DocumentLoader:
    """Load documents from various formats"""

    def __init__(self):
        self.config = get_build_config()
        self.supported_formats = self.config.supported_formats
        logger.info(f"DocumentLoader initialized. Supported formats: {self.supported_formats}")

    def load_document(self, file_path: Path) -> Tuple[str, DocumentMetadata]:
        """
        Load a document and extract text

        Args:
            file_path: Path to document file

        Returns:
            Tuple of (extracted_text, document_metadata)
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_type = file_path.suffix.lower()

        if file_type not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_type}. Supported: {self.supported_formats}")

        logger.info(f"Loading document: {file_path.name}")

        # Extract text based on file type
        if file_type == '.pdf':
            text = self._load_pdf(file_path)
        elif file_type == '.docx':
            text = self._load_docx(file_path)
        elif file_type == '.txt':
            text = self._load_txt(file_path)
        elif file_type == '.md':
            text = self._load_markdown(file_path)
        elif file_type == '.csv':
            text = self._load_csv(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        # Create metadata
        file_info = get_file_info(file_path)
        doc_id = generate_id(str(file_path), prefix="doc_")

        metadata = DocumentMetadata(
            doc_id=doc_id,
            filename=file_info['filename'],
            file_path=file_info['file_path'],
            file_type=file_info['file_type'],
            file_size=file_info['file_size']
        )

        logger.info(f"Loaded {len(text)} characters from {file_path.name}")

        return text, metadata

    def _load_pdf(self, file_path: Path) -> str:
        """Load PDF file"""
        try:
            reader = PdfReader(str(file_path))
            text = ""

            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"

            return normalize_text(text)

        except Exception as e:
            logger.error(f"Error loading PDF {file_path}: {e}")
            raise

    def _load_docx(self, file_path: Path) -> str:
        """Load DOCX file"""
        try:
            doc = Document(str(file_path))
            text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            return normalize_text(text)

        except Exception as e:
            logger.error(f"Error loading DOCX {file_path}: {e}")
            raise

    def _load_txt(self, file_path: Path) -> str:
        """Load TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            return normalize_text(text)

        except Exception as e:
            logger.error(f"Error loading TXT {file_path}: {e}")
            raise

    def _load_markdown(self, file_path: Path) -> str:
        """Load Markdown file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                md_text = f.read()

            # Convert markdown to plain text (remove markdown syntax)
            # First convert to HTML, then strip HTML tags
            html = markdown.markdown(md_text)

            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', html)

            return normalize_text(text)

        except Exception as e:
            logger.error(f"Error loading Markdown {file_path}: {e}")
            raise

    def _load_csv(self, file_path: Path) -> str:
        """
        Load CSV file and convert to structured text

        Each row is converted to a readable sentence format.
        Column headers are used to create meaningful text.
        """
        try:
            # Read CSV file
            df = pd.read_csv(file_path, encoding='utf-8', on_bad_lines='skip')

            if df.empty:
                logger.warning(f"CSV file is empty: {file_path}")
                return ""

            # Convert DataFrame to text
            text_parts = []

            # Add header information
            text_parts.append(f"CSV Document: {file_path.name}")
            text_parts.append(f"Columns: {', '.join(df.columns.tolist())}")
            text_parts.append("")  # Blank line

            # Convert each row to readable text
            for idx, row in df.iterrows():
                row_text_parts = []
                for col in df.columns:
                    value = row[col]
                    # Skip NaN values
                    if pd.notna(value):
                        # Create readable format: "Column: value"
                        row_text_parts.append(f"{col}: {value}")

                # Join row parts with semicolons
                if row_text_parts:
                    row_text = "; ".join(row_text_parts)
                    text_parts.append(f"Row {idx + 1}: {row_text}")

            # Join all parts
            full_text = "\n".join(text_parts)

            logger.info(f"Loaded CSV with {len(df)} rows and {len(df.columns)} columns")

            return normalize_text(full_text)

        except Exception as e:
            logger.error(f"Error loading CSV {file_path}: {e}")
            # Try alternative encoding
            try:
                df = pd.read_csv(file_path, encoding='latin-1', on_bad_lines='skip')
                text_parts = []
                text_parts.append(f"CSV Document: {file_path.name}")
                text_parts.append(f"Columns: {', '.join(df.columns.tolist())}")
                text_parts.append("")

                for idx, row in df.iterrows():
                    row_text_parts = []
                    for col in df.columns:
                        value = row[col]
                        if pd.notna(value):
                            row_text_parts.append(f"{col}: {value}")

                    if row_text_parts:
                        row_text = "; ".join(row_text_parts)
                        text_parts.append(f"Row {idx + 1}: {row_text}")

                full_text = "\n".join(text_parts)
                return normalize_text(full_text)
            except:
                raise

    def load_directory(self, directory_path: Path) -> List[Tuple[str, DocumentMetadata]]:
        """
        Load all supported documents from a directory

        Args:
            directory_path: Path to directory

        Returns:
            List of (text, metadata) tuples
        """
        directory_path = Path(directory_path)

        if not directory_path.exists() or not directory_path.is_dir():
            raise ValueError(f"Invalid directory: {directory_path}")

        documents = []

        for file_path in directory_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                try:
                    text, metadata = self.load_document(file_path)
                    documents.append((text, metadata))
                except Exception as e:
                    logger.error(f"Failed to load {file_path}: {e}")
                    continue

        logger.info(f"Loaded {len(documents)} documents from {directory_path}")
        return documents


class TextChunker:
    """Chunk text into graph-aware segments"""

    def __init__(self):
        self.config = get_build_config()
        self.chunk_size = self.config.chunk_size
        self.chunk_overlap = self.config.chunk_overlap

        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Could not load tiktoken, using simple tokenization: {e}")
            self.tokenizer = None

        logger.info(f"TextChunker initialized. Chunk size: {self.chunk_size}, Overlap: {self.chunk_overlap}")

    def chunk_text(self, text: str, doc_id: str) -> List[TextChunk]:
        """
        Chunk text into overlapping segments

        Args:
            text: Input text
            doc_id: Document ID

        Returns:
            List of TextChunk objects
        """
        # Split into sentences first (helps preserve context)
        sentences = self._split_into_sentences(text)

        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        char_position = 0

        for sentence in sentences:
            sentence_tokens = self._count_tokens(sentence)

            # If adding this sentence exceeds chunk size, create new chunk
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                # Create chunk
                chunk_text = " ".join(current_chunk)
                chunk_obj = self._create_chunk(
                    chunk_text, doc_id, chunk_index, char_position
                )
                chunks.append(chunk_obj)

                # Prepare for next chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = [overlap_text, sentence] if overlap_text else [sentence]
                current_tokens = self._count_tokens(" ".join(current_chunk))
                chunk_index += 1
                char_position += len(chunk_text)
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens

        # Add final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunk_obj = self._create_chunk(
                chunk_text, doc_id, chunk_index, char_position
            )
            chunks.append(chunk_obj)

        logger.info(f"Created {len(chunks)} chunks for document {doc_id}")
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitting (can be improved with NLTK/spaCy)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except:
                pass

        # Fallback: simple approximation
        return count_tokens(text)

    def _get_overlap_text(self, chunk_sentences: List[str]) -> str:
        """Get overlap text from previous chunk"""
        if not chunk_sentences:
            return ""

        # Take last few sentences for overlap
        overlap_tokens = 0
        overlap_sentences = []

        for sentence in reversed(chunk_sentences):
            sentence_tokens = self._count_tokens(sentence)

            if overlap_tokens + sentence_tokens <= self.chunk_overlap:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break

        return " ".join(overlap_sentences)

    def _create_chunk(self, text: str, doc_id: str, chunk_index: int, start_char: int) -> TextChunk:
        """Create TextChunk object"""
        chunk_id = generate_id(f"{doc_id}_{chunk_index}", prefix="chunk_")
        token_count = self._count_tokens(text)

        return TextChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            text=text,
            start_char=start_char,
            end_char=start_char + len(text),
            chunk_index=chunk_index,
            token_count=token_count
        )


class DocumentProcessor:
    """Combined document processing pipeline"""

    def __init__(self):
        self.loader = DocumentLoader()
        self.chunker = TextChunker()

    def process_document(self, file_path: Path) -> Tuple[DocumentMetadata, List[TextChunk]]:
        """
        Process a single document: load and chunk

        Args:
            file_path: Path to document

        Returns:
            Tuple of (metadata, chunks)
        """
        # Load document
        text, metadata = self.loader.load_document(file_path)

        # Chunk text
        chunks = self.chunker.chunk_text(text, metadata.doc_id)

        # Update metadata
        metadata.num_chunks = len(chunks)

        return metadata, chunks

    def process_directory(self, directory_path: Path) -> Tuple[List[DocumentMetadata], List[TextChunk]]:
        """
        Process all documents in a directory

        Args:
            directory_path: Path to directory

        Returns:
            Tuple of (metadata_list, all_chunks)
        """
        logger.info(f"Processing documents from directory: {directory_path}")

        all_metadata = []
        all_chunks = []

        # Load all documents
        documents = self.loader.load_directory(directory_path)

        # Process each document
        for text, metadata in documents:
            chunks = self.chunker.chunk_text(text, metadata.doc_id)
            metadata.num_chunks = len(chunks)

            all_metadata.append(metadata)
            all_chunks.extend(chunks)

        logger.info(f"Processed {len(all_metadata)} documents, created {len(all_chunks)} chunks")

        return all_metadata, all_chunks


if __name__ == "__main__":
    # Test the document processor
    from shared.config import DOCUMENTS_DIR
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    processor = DocumentProcessor()

    # Test with a directory
    if DOCUMENTS_DIR.exists():
        metadata_list, chunks = processor.process_directory(DOCUMENTS_DIR)

        print(f"\nProcessed {len(metadata_list)} documents")
        print(f"Created {len(chunks)} chunks")

        if chunks:
            print(f"\nSample chunk:")
            print(f"  ID: {chunks[0].chunk_id}")
            print(f"  Text: {chunks[0].text[:200]}...")
            print(f"  Tokens: {chunks[0].token_count}")
    else:
        print(f"Documents directory not found: {DOCUMENTS_DIR}")
        print("Please add documents to data/documents/ directory")
