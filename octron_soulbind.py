"""
Octron Soulbind
Ingests PDF documents (like manuals) page-by-page into the memory system.
Uses PyPDF2 for extraction.
"""



from V4octron_memory import store_memory

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


def soulbind_pdf(pdf_path: str, topic: str = "documentation") -> bool:
    """
    Reads a PDF page-by-page and stores each page as a memory shard.
    Uses store_memory for deduplication.
    """
    if PdfReader is None:
        print("ERROR: PyPDF2 not installed. Run: pip install PyPDF2")
        return False

    try:
        reader = PdfReader(pdf_path)
        print(f"Reading {pdf_path} ({len(reader.pages)} pages)...")

        stored = 0
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text or not text.strip():
                continue

            labeled = f"[SOURCE: {pdf_path} | Page {i + 1}]\n{text.strip()}"
            if store_memory(labeled, source_name=pdf_path, topic=topic):
                stored += 1

        print(f"Soulbind complete. {stored} new shards stored from {pdf_path}.")
        return True

    except FileNotFoundError:
        print(f"ERROR: '{pdf_path}' not found.")
        return False
    except Exception as e:
        print(f"ERROR during soulbind: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python octron_soulbind.py <path_to_pdf>")
    else:
        soulbind_pdf(sys.argv[1])
