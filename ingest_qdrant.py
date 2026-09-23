import json
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

OUTPUT_DIR = Path("output")
QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "veloit_handbook_chunks"
MODEL_NAME = "intfloat/multilingual-e5-base"
MODEL_CACHE = "models"
BATCH_SIZE = 32


def load_chunks():
    chunks = []
    for path in sorted(OUTPUT_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                obj["source_file"] = path.name
                obj["line_no"] = line_no
                obj["text"] = " ".join(obj.get("text", "").split())
                chunks.append(obj)
    return chunks


def main():
    print("Loading model...")
    model = SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE)

    print("Loading chunks...")
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks")

    print("Starting local Qdrant...")
    client = QdrantClient(path=QDRANT_PATH)

    print("Creating collection...")
    sample_vec = model.encode(["passage: test"], normalize_embeddings=True)[0]
    dim = len(sample_vec)

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    print("Ingesting chunks...")
    global_idx = 0

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [f"passage: {item['text']}" for item in batch]
        vectors = model.encode(texts, normalize_embeddings=True)

        points = []
        for item, vector in zip(batch, vectors):
            global_idx += 1

            payload = {
                "chunk_id": item.get("chunk_id"),
                "chunk_kind": item.get("chunk_kind"),
                "section_title": item.get("section_title"),
                "subsection_title": item.get("subsection_title"),
                "topic_tags": item.get("topic_tags", []),
                "intent_type": item.get("intent_type"),
                "entity_tags": item.get("entity_tags", []),
                "base_language": item.get("base_language"),
                "source_file": item.get("source_file"),
                "line_no": item.get("line_no"),
                "text": item.get("text"),
            }

            points.append(
                PointStruct(
                    id=global_idx,
                    vector=vector.tolist(),
                    payload=payload,
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Ingested {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)}")

    print("Done.")


if __name__ == "__main__":
    main()
