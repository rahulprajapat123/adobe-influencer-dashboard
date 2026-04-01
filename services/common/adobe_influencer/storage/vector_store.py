from __future__ import annotations

import math
import re
from collections import Counter

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings


class LocalHashEmbeddingFunction:
    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in input:
            tokens = re.findall(r"[a-z0-9]+", text.lower())
            counter = Counter(tokens)
            vector = [0.0] * 32
            for token, count in counter.items():
                bucket = hash(token) % 32
                vector[bucket] += float(count)
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class VectorStore:
    def __init__(self, persist_directory: str, collection_name: str) -> None:
        self.client = chromadb.PersistentClient(path=persist_directory, settings=Settings(anonymized_telemetry=False))
        self.collection: Collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=LocalHashEmbeddingFunction(),
        )

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> None:
        if not ids:
            return
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def semantic_search(self, query: str, limit: int = 5) -> list[dict]:
        result = self.collection.query(query_texts=[query], n_results=limit)
        matches: list[dict] = []
        for idx, doc_id in enumerate(result.get("ids", [[]])[0]):
            matches.append(
                {
                    "id": doc_id,
                    "document": result.get("documents", [[]])[0][idx],
                    "metadata": result.get("metadatas", [[]])[0][idx],
                    "distance": result.get("distances", [[]])[0][idx] if result.get("distances") else None,
                }
            )
        return matches
