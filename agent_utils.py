import json
import re
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import InvoiceDB, EmailStore
from doc_processor import DocumentProcessor
from vectorstore import VectorStore
from config import INVOICE_PREFIXES, TRACKING_PREFIXES, PROCESSED_DATA_PATH

# --- TOOL IMPLEMENTATIONS ---

def lookup_invoice(invoice_id: str = None, **kwargs) -> str:
    if not invoice_id:
        invoice_id = kwargs.get('invoice_number') or kwargs.get('id') or kwargs.get('invoice_id')
    if not invoice_id:
        return "Error: Missing required argument 'invoice_id'"
    print(f"    [TOOL]: lookup_invoice({invoice_id})")
    try:
        db = InvoiceDB()
        result = db.lookup_invoice(invoice_id)
        return json.dumps(result) if result else f"No invoice found for ID: {invoice_id}"
    except Exception as e:
        return f"Error: {str(e)}"

def lookup_shipment(tracking_id: str = None, **kwargs) -> str:
    if not tracking_id:
        tracking_id = kwargs.get('tracking_number') or kwargs.get('id') or kwargs.get('tracking_id')
    if not tracking_id:
        return "Error: Missing required argument 'tracking_id'"
    print(f"    [TOOL]: lookup_shipment({tracking_id})")
    try:
        db = InvoiceDB()
        result = db.lookup_shipment(tracking_id)
        return json.dumps(result) if result else f"No shipment found for ID: {tracking_id}"
    except Exception as e:
        return f"Error: {str(e)}"

def lookup_customer(email: str = None, **kwargs) -> str:
    if not email:
        email = kwargs.get('email_address') or kwargs.get('sender_email') or kwargs.get('email')
    if not email:
        return "Error: Missing required argument 'email'"
    print(f"    [TOOL]: lookup_customer({email})")
    try:
        db = InvoiceDB()
        result = db.lookup_customer(email)
        return json.dumps(result) if result else f"No customer record found for: {email}"
    except Exception as e:
        return f"Error: {str(e)}"

def check_thread_status(conversation_id: str, sender_email: str, message_id: str, **kwargs) -> str:
    print(f"    [TOOL]: check_thread_status({conversation_id})")
    try:
        db = InvoiceDB()
        store = EmailStore(db)
        result = store.check_duplicate(conversation_id, sender_email, message_id)
        return result if result else "NEW"
    except Exception as e:
        return f"Error: {str(e)}"

def extract_document_text(base64_content: str, file_type: str, **kwargs) -> str:
    print(f"    [TOOL]: extract_document_text({file_type})")
    try:
        if file_type.lower() == 'pdf':
            return DocumentProcessor.extract_text_from_pdf(base64_content)
        elif file_type.lower() in ['docx', 'doc']:
            return DocumentProcessor.extract_text_from_docx(base64_content)
        return f"Unsupported file type: {file_type}"
    except Exception as e:
        return f"Error: {str(e)}"

def get_customer_invoices(email: str = None, **kwargs) -> str:
    if not email:
        email = kwargs.get('email_address') or kwargs.get('sender_email') or kwargs.get('email')
    if not email:
        return "Error: Missing required argument 'email'"
    print(f"    [TOOL]: get_customer_invoices({email})")
    try:
        db = InvoiceDB()
        conn = db.get_db_connection()
        if not conn:
            return "Error: Database connection failed."
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT i.invoice_id, i.invoice_date, i.total_amount, i.balance_amount, i.status 
            FROM invoices i
            JOIN customers c ON i.customer_id = c.customer_id
            WHERE c.email = %s
            ORDER BY i.invoice_date DESC
        """
        cursor.execute(query, (email,))
        invoices = cursor.fetchall()
        cleaned_invoices = [db._clean_result(inv) for inv in invoices]
        return json.dumps(cleaned_invoices) if cleaned_invoices else f"No invoice history found for customer email: {email}"
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def check_thread_history(conversation_id: str = None, **kwargs) -> str:
    if not conversation_id:
        conversation_id = kwargs.get('conversation_id')
    if not conversation_id:
        return "Error: Missing required argument 'conversation_id'"
    print(f"    [TOOL]: check_thread_history({conversation_id})")
    try:
        db = InvoiceDB()
        conn = db.get_db_connection()
        if not conn:
            return "Error: Database connection failed."
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT subject, received_at, intent, status 
            FROM processed_emails 
            WHERE conversation_id = %s 
            ORDER BY received_at ASC
        """
        cursor.execute(query, (conversation_id,))
        records = cursor.fetchall()
        cleaned_records = [db._clean_result(rec) for rec in records]
        return json.dumps(cleaned_records) if cleaned_records else "No previous interactions logged in this thread."
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


def export_processed_emails_to_csv() -> str:
    try:
        from JSON_to_CSV import convert_json_to_csv
        filename = os.path.basename(PROCESSED_DATA_PATH)
        convert_json_to_csv(filename)
        return f"Successfully converted {filename} to CSV."
    except Exception as e:
        return f"Error: {str(e)}"

def get_semantic_similarities(subject: str, body: str, sender_email: str) -> str:
    try:
        vs = VectorStore()
        match = vs.find_semantic_duplicate(subject, body, sender_email, threshold=0.6)
        return json.dumps(match) if match else "No similar emails found."
    except Exception as e:
        return f"Error: {str(e)}"

def extract_ids_regex(text: str) -> str:
    def get_pattern(prefixes):
        pattern = "|".join(prefixes)
        return rf"\b(?:{pattern})\s*-?\d+\b"
    inv_matches = re.findall(get_pattern(INVOICE_PREFIXES), text, re.IGNORECASE)
    trk_matches = re.findall(get_pattern(TRACKING_PREFIXES), text, re.IGNORECASE)
    return json.dumps({
        "invoice_ids": [m.upper() for m in inv_matches],
        "tracking_ids": [m.upper() for m in trk_matches]
    })

# Map tool names to functions for LLM orchestration
TOOL_MAP = {
    "lookup_invoice": lookup_invoice,
    "lookup_shipment": lookup_shipment,
    "lookup_customer": lookup_customer,
    "check_thread_status": check_thread_status,
    "extract_document_text": extract_document_text,
    "export_processed_emails_to_csv": export_processed_emails_to_csv,
    "get_semantic_similarities": get_semantic_similarities,
    "extract_ids": extract_ids_regex,
    "get_customer_invoices": get_customer_invoices,
    "check_thread_history": check_thread_history,
}

# Standardized Ollama Tool Schemas
OLLAMA_TOOL_SCHEMAS = [
    {
        'type': 'function',
        'function': {
            'name': 'lookup_invoice',
            'description': 'Lookup invoice, customer, and shipment details from MySQL by Invoice ID.',
            'parameters': {
                'type': 'object',
                'properties': {'invoice_id': {'type': 'string'}},
                'required': ['invoice_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lookup_shipment',
            'description': 'Lookup shipment status and customer profile by Tracking ID.',
            'parameters': {
                'type': 'object',
                'properties': {'tracking_id': {'type': 'string'}},
                'required': ['tracking_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'lookup_customer',
            'description': 'Lookup customer profile and loyalty by email.',
            'parameters': {
                'type': 'object',
                'properties': {'email': {'type': 'string'}},
                'required': ['email'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_semantic_similarities',
            'description': 'Check for past emails from the same sender to understand context.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'subject': {'type': 'string'},
                    'body': {'type': 'string'},
                    'sender_email': {'type': 'string'}
                },
                'required': ['subject', 'body', 'sender_email'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'extract_document_text',
            'description': 'Extract plain text from a base64 encoded PDF or DOCX file.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'base64_content': {'type': 'string'},
                    'file_type': {'type': 'string', 'enum': ['pdf', 'docx']}
                },
                'required': ['base64_content', 'file_type'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_customer_invoices',
            'description': 'Get all historical invoices and billing/payment statuses for a customer email.',
            'parameters': {
                'type': 'object',
                'properties': {'email': {'type': 'string'}},
                'required': ['email'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'check_thread_history',
            'description': 'Check previous interactions, intents, and statuses chronological log for this conversation thread.',
            'parameters': {
                'type': 'object',
                'properties': {'conversation_id': {'type': 'string'}},
                'required': ['conversation_id'],
            },
        },
    }
]
