from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

client = QdrantClient(path="qdrant_data")
model = SentenceTransformer("intfloat/multilingual-e5-base", cache_folder="models")

query = "What should I do in my first days in Germany?"
query_vec = model.encode([f"query: {query}"], normalize_embeddings=True)[0]

response = client.query_points(
    collection_name="veloit_handbook_chunks",
    query=query_vec.tolist(),
    limit=5,
)

for point in response.points:
    print("-" * 80)
    print("score:", point.score)
    print("chunk_id:", point.payload.get("chunk_id"))
    print("section:", point.payload.get("section_title"))
    print("subsection:", point.payload.get("subsection_title"))
    print("file:", point.payload.get("source_file"))
    print("text:", point.payload.get("text", "")[:300])
