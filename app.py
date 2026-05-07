from flask import Flask, render_template, jsonify, request
from main import EmailController
import os

app = Flask(__name__)
controller = EmailController()

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')

@app.route('/api/fetch-emails')
def fetch_emails():
    """Endpoint to trigger the MS Graph fetch."""
    try:
        # We use a small hack here: get the access token using the controller's existing logic
        # For the UI, we'll just fetch the list first without processing
        access_token = controller.fetcher.get_access_token()
        if not access_token:
            return jsonify({"error": "Authentication failed"}), 401
            
        emails = controller.fetcher.fetch_emails(access_token, top=10, only_unread=True)
        return jsonify(emails.get('value', []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/process-email', methods=['POST'])
def process_email():
    """Endpoint to run Stage 1, 2 and Vector RAG for a specific email."""
    data = request.json
    msg = data.get('email')
    
    try:
        # 1. AI Extraction (Stage 1 & 2)
        record = controller.processor.process_single_email(msg)
        
        # 2. DB Context (Mirroring main.py logic)
        db_context = {"invoice": None, "shipment": None, "customer": None}
        extraction = record.get("extraction", {})
        entities = extraction.get("entities", {})
        
        # Regex Scan for safety (from main.py)
        import re
        from config import INVOICE_PREFIXES, TRACKING_PREFIXES
        body_text = msg.get('body', {}).get('content', '')
        
        def get_pattern(prefixes):
            pattern = "|".join(prefixes)
            return rf"(?:{pattern})-?\d+"

        inv_ids = set([entities.get("invoice_number")]) if entities.get("invoice_number") else set()
        for m in re.findall(get_pattern(INVOICE_PREFIXES), body_text, re.IGNORECASE): inv_ids.add(m.upper())
        
        if inv_ids:
            inv_id = list(inv_ids)[0]
            db_context["invoice"] = controller.db.lookup_invoice(inv_id)
            
        # Customer lookup
        sender_email = record['metadata']['sender']
        db_context["customer"] = controller.db.lookup_customer(sender_email)
        if not db_context["customer"]:
            db_context["customer"] = {"name": extraction.get("customer_name") or "Valued Customer"}

        # 3. Vector DB / RAG Query
        rag_context = []
        if controller.vectorstore:
            query_text = f"{msg.get('subject')} {extraction.get('summary', '')}"
            rag_context = controller.vectorstore.query(query_text)
            
        # 4. Generate Draft (REMOVED - Now a separate step)
        # draft = controller.processor.generate_reply_llama(extraction, db_context, rag_context)
        
        return jsonify({
            "record": record,
            "db_context": db_context,
            "rag_context": rag_context
        })
    except Exception as e:
        print(f"ERROR IN PROCESS_EMAIL: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-reply', methods=['POST'])
def generate_reply():
    """Phase 2: Generate the reply based on previously extracted context."""
    data = request.json
    extraction = data.get('extraction')
    db_context = data.get('db_context')
    rag_context = data.get('rag_context')
    
    try:
        draft = controller.processor.generate_reply_llama(extraction, db_context, rag_context)
        return jsonify({"draft": draft})
    except Exception as e:
        print(f"ERROR IN GENERATE_REPLY: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/send-email', methods=['POST'])
def send_email():
    """Endpoint to send the final draft via MS Graph."""
    data = request.json
    message_id = data.get('message_id')
    content = data.get('content')
    
    try:
        access_token = controller.fetcher.get_access_token()
        if not access_token:
            return jsonify({"error": "Auth failed"}), 401
            
        # Format for Outlook
        formatted_content = content.replace("\n", "<br>")
        
        success = controller.fetcher.send_reply(access_token, message_id, formatted_content)
        if success:
            controller.fetcher.mark_as_read(access_token, message_id)
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to send email"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Create required folders if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    app.run(debug=True, port=5000)
