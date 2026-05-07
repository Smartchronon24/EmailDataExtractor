"""
vectorstore.py
--------------
ChromaDB Vector Store for the EmailDataExtractor pipeline.

Responsibilities:
  - Store: Raw email JSON + extracted entities after Stage 2
  - Query: Retrieve top-K similar past emails before Stage 3 (RAG)

Uses Ollama's 'nomic-embed-text' model for local, free, offline embeddings.
"""

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
import json
import os
from config import VECTOR_DB_PATH, RAG_TOP_K


class VectorStore:
    """
    Manages the ChromaDB collection for email RAG.
    Persists data to disk at VECTOR_DB_PATH.
    """

    COLLECTION_NAME = "email_pipeline"

    def __init__(self):
        # PersistentClient saves to disk automatically
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)

        # Use ChromaDB's built-in embedding function (all-MiniLM-L6-v2 via ONNX)
        # This runs independently of Ollama — no model conflicts
        self.ef = DefaultEmbeddingFunction()

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}  # cosine similarity for text
        )
        print(f"[VectorDB] Initialized. Collection '{self.COLLECTION_NAME}' "
              f"has {self.collection.count()} document(s).")

    def _build_document_text(self, raw_email: dict, extraction: dict) -> str:
        """
        Builds a single text blob that combines the most important info
        from both the raw email and the extracted entities.
        This is what gets embedded and stored.
        """
        subject = raw_email.get("subject", "")
        body = raw_email.get("body", {}).get("content", "")[:2000]  # Cap at 2000 chars
        entities_text = json.dumps(extraction, indent=2) if extraction else ""

        return f"SUBJECT: {subject}\n\nEMAIL BODY:\n{body}\n\nEXTRACTED ENTITIES:\n{entities_text}"

    def store(self, message_id: str, raw_email: dict, extraction: dict, db_context: dict = None):
        """
        Store raw email + extracted entities into ChromaDB after Stage 2.
        ChromaDB handles embedding automatically using its built-in function.
        """
        try:
            doc_text = self._build_document_text(raw_email, extraction)

            # Store metadata alongside the embedding for inspection
            metadata = {
                "subject":      raw_email.get("subject", ""),
                "sender":       raw_email.get("from", {}).get("emailAddress", {}).get("address", ""),
                "intent":       extraction.get("intent", "unknown") if extraction else "unknown",
                "timestamp":    raw_email.get("receivedDateTime", ""),
                "has_invoice":  str(bool(db_context and db_context.get("invoice"))),
                "has_shipment": str(bool(db_context and db_context.get("shipment"))),
            }

            self.collection.add(
                ids=[message_id],
                documents=[doc_text],   # ChromaDB auto-embeds this
                metadatas=[metadata]
            )
            print(f"[VectorDB] ✓ Stored: '{metadata['subject']}' (ID: {message_id[:12]}...)")

        except Exception as e:
            print(f"[VectorDB] WARNING: Failed to store email: {e}")

    def query(self, query_text: str, top_k: int = RAG_TOP_K) -> list[str]:
        """
        Query ChromaDB for the most similar past emails (RAG).
        ChromaDB handles embedding automatically.
        Returns a list of document text strings to inject into the LLM prompt.
        """
        try:
            count = self.collection.count()
            if count == 0:
                print("[VectorDB] Collection is empty — skipping RAG.")
                return []

            effective_k = min(top_k, count)

            results = self.collection.query(
                query_texts=[query_text],   # ChromaDB auto-embeds this
                n_results=effective_k,
                include=["documents", "metadatas", "distances"]
            )

            docs  = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            print(f"[VectorDB] RAG: Retrieved {len(docs)} similar past email(s).")
            for i, (meta, dist) in enumerate(zip(metas, distances)):
                similarity = round((1 - dist) * 100, 1)
                print(f"  [{i+1}] Subject: '{meta.get('subject', 'N/A')}' | "
                      f"Intent: {meta.get('intent', 'N/A')} | "
                      f"Similarity: {similarity}%")

            return docs

        except Exception as e:
            print(f"[VectorDB] WARNING: RAG query failed: {e}")
            return []
