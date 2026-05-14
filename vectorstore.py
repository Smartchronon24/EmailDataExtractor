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

    def _build_document_text(self, subject: str, body: str) -> str:
        """
        Standardizes the text format used for both storage and duplicate checking.
        Ensures we are always comparing 'apples to apples'.
        """
        return f"SUBJECT: {subject}\n\nBODY: {body[:2000]}"

    def store(self, message_id: str, raw_email: dict, extraction: dict, db_context: dict = None, clean_body: str = None):
        """
        Store raw email + extracted entities into ChromaDB after Stage 2.
        """
        try:
            subject = raw_email.get("subject", "")
            # Use provided clean_body if available, otherwise fallback
            body = clean_body if clean_body else raw_email.get("body", {}).get("content", "")
            doc_text = self._build_document_text(subject, body)

            # Store metadata alongside the embedding for inspection
            metadata = {
                "subject":      raw_email.get("subject", ""),
                "sender":       raw_email.get("from", {}).get("emailAddress", {}).get("address", ""),
                "intent":       extraction.get("intent", "unknown") if extraction else "unknown",
                "invoice_id":   extraction.get("entities", {}).get("invoice_id", ""),
                "tracking_id":  extraction.get("entities", {}).get("tracking_id", ""),
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

    def find_semantic_duplicate(self, subject: str, body: str, sender_email: str, threshold: float = 0.15) -> dict:
        """
        Checks if a highly similar email from the same sender exists.
        Returns the most similar metadata if distance < threshold.
        Distance 0.0 = identical, 1.0 = completely different (Cosine).
        """
        try:
            query_text = self._build_document_text(subject, body)
            results = self.collection.query(
                query_texts=[query_text],
                n_results=1,
                where={"sender": sender_email},
                include=["metadatas", "distances"]
            )
            
            if results["distances"] and results["distances"][0]:
                dist = results["distances"][0][0]
                if dist < threshold:
                    return {
                        "metadata": results["metadatas"][0][0],
                        "similarity": round((1 - dist) * 100, 1)
                    }
            return None
        except Exception as e:
            print(f"[VectorDB] Duplicate check failed: {e}")
            return None

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
