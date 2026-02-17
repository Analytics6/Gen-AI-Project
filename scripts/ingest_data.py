from pathlib import Path

from pypdf import PdfReader

from app.chroma_store import store
from app.rag import RAGService


def split_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    chunks = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk.strip()]


def ingest_directory(data_dir: Path):
    rag = RAGService()
    store.clear_documents()

    files = [p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    total_chunks = 0

    for file_path in files:
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join([page.strip() for page in pages if page.strip()])
        if not text.strip():
            continue

        for chunk in split_text(text):
            emb = rag.embed_text(chunk)
            store.add_document_chunk(
                source=str(file_path.relative_to(data_dir.parent)),
                chunk_text=chunk,
                embedding=emb,
            )
            total_chunks += 1

    print(f"Ingestion complete. Indexed {len(files)} PDF files and {total_chunks} chunks.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest PDF files from data directory into ChromaDB.")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    ingest_directory(Path(args.data_dir).resolve())
