import json
from pathlib import Path

from app.db import Base, SessionLocal, engine
from app.models import DocumentChunk
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
    Base.metadata.create_all(bind=engine)
    rag = RAGService()
    db = SessionLocal()

    try:
        db.query(DocumentChunk).delete()
        db.commit()

        files = [
            p
            for p in data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".txt", ".md", ".csv", ".json"}
        ]

        for file_path in files:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for chunk in split_text(text):
                emb = rag.embed_text(chunk)
                row = DocumentChunk(
                    source=str(file_path.relative_to(data_dir.parent)),
                    chunk_text=chunk,
                    embedding_json=json.dumps(emb),
                )
                db.add(row)

        db.commit()
        print(f"Ingestion complete. Indexed {len(files)} files.")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest files from data directory into embeddings table.")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    ingest_directory(Path(args.data_dir).resolve())
