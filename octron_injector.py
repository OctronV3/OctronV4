"""
Octron File Injector
Scans the upload folder, reads files, chunks them, and stores them in memory.
Supports: .txt, .md, .pdf, .py
Includes duplicate detection and semantic chunking with overlap.
"""

import os
import re
from pathlib import Path

from tqdm import tqdm
from qdrant_client import models

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:
    pdf_extract_text = None

from V4octron_memory import store_memory, memory_count, client, COLLECTION_NAME

# === CONFIGURATION ===
UPLOAD_FOLDER = "upload_here"
ACCEPTED_EXTENSIONS = [".txt", ".md", ".pdf", ".py"]


def semantic_chunk(text: str, filename: str, max_length: int = 800, overlap: int = 150) -> list:
    """
    Breaks long documents into smaller chunks with overlap so the AI
    doesn't lose context mid-sentence.
    """
    # Clean PDF footers
    text = re.sub(r"Page \d+ of \d+", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + max_length

        if end < len(text):
            # Find a natural break point (sentence end or newline)
            search_start = max(start, end - 200)
            chunk_slice = text[search_start:end]
            last_break = max(chunk_slice.rfind(". "), chunk_slice.rfind("\n"))
            if last_break != -1:
                end = search_start + last_break + 1

        chunk_content = text[start:end].strip()
        if chunk_content:
            labeled_chunk = f"[SOURCE: {filename}]\n{chunk_content}"
            chunks.append(labeled_chunk)

        # Slide forward with overlap
        next_start = end - overlap
        start = end + 1 if next_start <= start else next_start

    return chunks


def _detect_topic(filename: str, text: str) -> str:
    """Auto-detect a topic tag based on filename and content."""
    name_lower = filename.lower()

    if any(ext in name_lower for ext in [".py", ".js", ".ts", ".go", ".rs"]):
        return "code"
    if "manual" in name_lower or "guide" in name_lower or "doc" in name_lower:
        return "documentation"
    if "law" in name_lower or "rule" in name_lower or "policy" in name_lower:
        return "rules"
    if "report" in name_lower or "intel" in name_lower:
        return "intelligence"
    if "note" in name_lower or "journal" in name_lower:
        return "notes"

    return "general"


def inject_file_to_memory(file_path: str) -> bool:
    """
    Reads a file, chunks it, and stores it in memory.
    Skips files that are already in the database (by source name).
    """
    try:
        filename = Path(file_path).name

        # Duplicate check: skip if this filename is already stored
        existing_points, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.source",
                        match=models.MatchValue(value=filename),
                    )
                ]
            ),
            limit=1,
        )

        if existing_points:
            print(f"  Skipping '{filename}': Already in memory.")
            return True

        # Read file content
        if file_path.lower().endswith(".pdf"):
            if pdf_extract_text is None:
                print(f"  ERROR: pdfminer not installed. Cannot read '{filename}'.")
                return False
            text = pdf_extract_text(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        if not text or not text.strip():
            print(f"  WARNING: '{filename}' is empty. Skipping.")
            return False

        # Detect topic and chunk
        topic = _detect_topic(filename, text)
        chunks = semantic_chunk(text, filename)
        print(f"  Injecting {len(chunks)} chunks from '{filename}' [topic: {topic}]...")

        stored = 0
        for chunk in chunks:
            if store_memory(chunk, source_name=filename, topic=topic):
                stored += 1

        print(f"  Done. {stored} new chunks stored. Brain: {memory_count()} total.")
        return True

    except Exception as e:
        print(f"\n  FAILED to inject {file_path}: {e}")
        return False


def inject_all_from_folder(folder_path: str = UPLOAD_FOLDER):
    """Scans the upload folder and injects each valid file into memory."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"Created '{folder_path}/' folder. Drop your files there!")
        return

    files = [
        f
        for f in os.listdir(folder_path)
        if any(f.lower().endswith(ext) for ext in ACCEPTED_EXTENSIONS)
    ]

    if not files:
        print(f"No valid files found in '{folder_path}/'.")
        return

    print(f"Starting injection for {len(files)} files...\n")

    for file in tqdm(files, desc="Processing", unit="file"):
        full_path = os.path.join(folder_path, file)
        inject_file_to_memory(full_path)

    print("\nFinished. Octron's knowledge base is updated.")


if __name__ == "__main__":
    inject_all_from_folder()
