"""
Utility Functions for Graph-RAG System
"""

import hashlib
import json
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
from loguru import logger


def generate_id(text: str, prefix: str = "") -> str:
    """
    Generate a unique ID from text using MD5 hash

    Args:
        text: Input text to hash
        prefix: Optional prefix for the ID

    Returns:
        Unique ID string
    """
    hash_obj = hashlib.md5(text.encode('utf-8'))
    hash_id = hash_obj.hexdigest()[:16]
    return f"{prefix}{hash_id}" if prefix else hash_id


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent processing

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove special characters but keep punctuation
    text = re.sub(r'[^\w\s.,!?;:()\[\]{}\-\'\"]+', '', text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def normalize_entity_name(name: str) -> str:
    """
    Normalize entity names for deduplication

    Args:
        name: Entity name

    Returns:
        Normalized name
    """
    # Remove honorifics
    name = re.sub(r'\b(Dr|Mr|Mrs|Ms|Prof|Sir|Dr\.)\s+', '', name, flags=re.IGNORECASE)

    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name)

    # Title case
    name = name.strip().title()

    return name


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score (0-1)
    """
    if len(vec1) == 0 or len(vec2) == 0:
        return 0.0

    # Ensure numpy arrays
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)

    # Calculate cosine similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """
    L2 normalize a vector

    Args:
        vector: Input vector

    Returns:
        L2 normalized vector
    """
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def batch_iterator(items: List[Any], batch_size: int):
    """
    Iterate over items in batches

    Args:
        items: List of items
        batch_size: Size of each batch

    Yields:
        Batches of items
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def load_json(file_path: Path) -> Dict[str, Any]:
    """
    Load JSON file with error handling

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON from {file_path}: {e}")
        return {}


def save_json(data: Dict[str, Any], file_path: Path, indent: int = 2) -> bool:
    """
    Save data to JSON file with error handling

    Args:
        data: Data to save
        file_path: Path to save to
        indent: JSON indentation

    Returns:
        True if successful, False otherwise
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {file_path}: {e}")
        return False


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length

    Args:
        text: Input text
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def extract_json_from_text(text: str) -> Optional[Any]:
    """
    Extract JSON from text that may contain other content

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON data or None
    """
    # Try to find JSON array
    array_match = re.search(r'\[.*\]', text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object
    object_match = re.search(r'\{.*\}', text, re.DOTALL)
    if object_match:
        try:
            return json.loads(object_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try parsing the entire text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Could not extract JSON from text: {truncate_text(text, 100)}")
        return None


def count_tokens(text: str) -> int:
    """
    Estimate token count (simple approximation)

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    # Simple approximation: ~4 characters per token
    return len(text) // 4


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def clean_text_for_embedding(text: str) -> str:
    """
    Clean text specifically for embedding generation

    Args:
        text: Input text

    Returns:
        Cleaned text
    """
    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

    # Remove emails
    text = re.sub(r'\S+@\S+', '', text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove very long words (likely corrupted or encoded data)
    words = text.split()
    words = [w for w in words if len(w) < 50]
    text = ' '.join(words)

    return text.strip()


def merge_overlapping_chunks(chunks: List[str], overlap_threshold: float = 0.8) -> List[str]:
    """
    Merge chunks with high overlap

    Args:
        chunks: List of text chunks
        overlap_threshold: Similarity threshold for merging

    Returns:
        Merged chunks
    """
    if not chunks:
        return []

    merged = [chunks[0]]

    for chunk in chunks[1:]:
        # Check overlap with last merged chunk
        last_chunk = merged[-1]
        overlap = len(set(chunk.split()) & set(last_chunk.split()))
        total = len(set(chunk.split()) | set(last_chunk.split()))

        if total > 0 and overlap / total > overlap_threshold:
            # Merge
            merged[-1] = last_chunk + " " + chunk
        else:
            merged.append(chunk)

    return merged


def get_file_info(file_path: Path) -> Dict[str, Any]:
    """
    Get file information

    Args:
        file_path: Path to file

    Returns:
        Dictionary with file info
    """
    if not file_path.exists():
        return {}

    stat = file_path.stat()

    return {
        "filename": file_path.name,
        "file_path": str(file_path),
        "file_type": file_path.suffix.lower().lstrip('.'),
        "file_size": stat.st_size,
        "file_size_formatted": format_file_size(stat.st_size),
        "modified_time": stat.st_mtime,
    }


def setup_logging(log_file: Optional[Path] = None, level: str = "INFO"):
    """
    Setup logging configuration

    Args:
        log_file: Optional log file path
        level: Logging level
    """
    logger.remove()  # Remove default handler

    # Console handler
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True
    )

    # File handler (if specified)
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=level,
            rotation="10 MB",
            retention="7 days"
        )


def validate_json_structure(data: Any, expected_keys: List[str]) -> bool:
    """
    Validate JSON structure has expected keys

    Args:
        data: JSON data to validate
        expected_keys: List of expected keys

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False

    return all(key in data for key in expected_keys)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if division fails

    Returns:
        Result of division or default
    """
    if denominator == 0:
        return default
    return numerator / denominator
