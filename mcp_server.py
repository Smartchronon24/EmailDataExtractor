import os
import json
import re
import sys
from typing import Any
from mcp.server.fastmcp import FastMCP

# Add current dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import InvoiceDB, EmailStore
from doc_processor import DocumentProcessor
from vectorstore import VectorStore
from config import INVOICE_PREFIXES, TRACKING_PREFIXES, PROCESSED_DATA_PATH

# Initialize MCP Server
mcp = FastMCP("EmailIntelligence")

# --- DATABASE TOOLS ---

@mcp.tool()
def lookup_invoice(invoice_id: str) -> str:
    """Looks up invoice details, customer info, and shipment status by Invoice ID."""
    try:
        db = InvoiceDB()
        result = db.lookup_invoice(invoice_id)
        return json.dumps(result) if result else f"No invoice found for ID: {invoice_id}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def lookup_shipment(tracking_id: str) -> str:
    """Looks up shipment status and linked customer profile by Tracking ID."""
    try:
        db = InvoiceDB()
        result = db.lookup_shipment(tracking_id)
        return json.dumps(result) if result else f"No shipment found for ID: {tracking_id}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def lookup_customer(email: str) -> str:
    """Looks up customer profile and loyalty level by email address."""
    try:
        db = InvoiceDB()
        result = db.lookup_customer(email)
        return json.dumps(result) if result else f"No customer record found for: {email}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def check_thread_status(conversation_id: str, sender_email: str, message_id: str) -> str:
    """Checks MySQL for exact message matches or already-replied threads."""
    try:
        db = InvoiceDB()
        store = EmailStore(db)
        result = store.check_duplicate(conversation_id, sender_email, message_id)
        return result if result else "NEW"
    except Exception as e:
        return f"Error: {str(e)}"

# --- DOCUMENT & DATA TOOLS ---

@mcp.tool()
def extract_document_text(base64_content: str, file_type: str) -> str:
    """Extracts plain text from a base64 encoded PDF or DOCX file."""
    try:
        if file_type.lower() == 'pdf':
            return DocumentProcessor.extract_text_from_pdf(base64_content)
        elif file_type.lower() in ['docx', 'doc']:
            return DocumentProcessor.extract_text_from_docx(base64_content)
        return f"Unsupported file type: {file_type}"
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def export_processed_emails_to_csv() -> str:
    """Converts the processed_emails.json file to a CSV format for export."""
    try:
        from JSON_to_CSV import convert_json_to_csv
        # Using the actual filename to ensure it's found
        filename = os.path.basename(PROCESSED_DATA_PATH)
        convert_json_to_csv(filename)
        return f"Successfully converted {filename} to CSV."
    except Exception as e:
        return f"Error: {str(e)}"

# --- VECTOR & UTILITY TOOLS ---

@mcp.tool()
def get_semantic_similarities(subject: str, body: str, sender_email: str) -> str:
    """Queries ChromaDB for similar past emails from the same sender."""
    try:
        vs = VectorStore()
        match = vs.find_semantic_duplicate(subject, body, sender_email, threshold=0.6)
        if match:
            return json.dumps(match)
        return "No similar emails found for this sender."
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def extract_ids(text: str) -> str:
    """Extracts Invoice (INV) and Tracking (TRK) IDs from text using regex."""
    def get_pattern(prefixes):
        pattern = "|".join(prefixes)
        return rf"\b(?:{pattern})\s*-?\d+\b"
    inv_matches = re.findall(get_pattern(INVOICE_PREFIXES), text, re.IGNORECASE)
    trk_matches = re.findall(get_pattern(TRACKING_PREFIXES), text, re.IGNORECASE)
    found = {
        "invoice_ids": [m.upper() for m in inv_matches],
        "tracking_ids": [m.upper() for m in trk_matches]
    }
    return json.dumps(found)

if __name__ == "__main__":
    mcp.run()
