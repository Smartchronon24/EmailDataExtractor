from flask import Flask, render_template, jsonify, request
from main import EmailController
import os
import json

app = Flask(__name__)
app.secret_key = os.urandom(24)
controller = EmailController()

SETTINGS_FILE = "settings.json"

def get_current_settings():
    import config
    # Default from config.py
    base = {
        "STAGE1_MODEL": getattr(config, 'STAGE1_MODEL', 'mistral'),
        "STAGE2_MODEL": getattr(config, 'STAGE2_MODEL', 'llama3'),
        "STAGE3_MODEL": getattr(config, 'STAGE3_MODEL', 'mistral'),
        "THEME": getattr(config, 'THEME', 'dark'),
        "ENABLE_STAGE1": getattr(config, 'ENABLE_STAGE1', True),
        "OPTIMIZE_STAGE1": getattr(config, 'OPTIMIZE_STAGE1', True),
        "ENABLE_RAG": getattr(config, 'ENABLE_RAG', True),
        "RAG_TOP_K": getattr(config, 'RAG_TOP_K', 3),
        "INVOICE_PREFIXES": getattr(config, 'INVOICE_PREFIXES', ["INV"]),
        "TRACKING_PREFIXES": getattr(config, 'TRACKING_PREFIXES', ["TRK"]),
        "MAX_WORKERS": getattr(config, 'MAX_WORKERS', 1),
        "MAX_RETRIES": getattr(config, 'MAX_RETRIES', 2)
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                base.update(json.load(f))
        except: pass
    return base

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'GET':
        return jsonify(get_current_settings())
    
    new_settings = request.json
    with open(SETTINGS_FILE, "w") as f:
        json.dump(new_settings, f, indent=4)
    
    # Reload controller with new config
    controller.reload_config()
    return jsonify({"status": "success"})

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
        # 0. Fetch Attachments if any
        attachments = []
        if msg.get('hasAttachments'):
            access_token = controller.fetcher.get_access_token()
            if access_token:
                attachments = controller.fetcher.fetch_attachments(access_token, msg.get('id'))

        # 1. AI Extraction (Stage 1 & 2)
        record = controller.processor.process_single_email(msg, attachments)
        extraction = record.get("extraction", {})
        
        # 2. DB Context (Fact-Checking against MySQL)
        db_context = {"invoice": None, "shipment": None, "customer": None}
        
        # Priority 1: Lookup by Invoice (Most Accurate for Billing/Support)
        inv_id = extraction.get("entities", {}).get("invoice_number")
        if inv_id:
            db_context["invoice"] = controller.db.lookup_invoice(inv_id)
            if db_context["invoice"]:
                db_context["customer"] = {
                    "name": db_context["invoice"]["customer_name"],
                    "loyalty_level": db_context["invoice"].get("loyalty_level", "Standard"),
                    "email": db_context["invoice"].get("customer_email")
                }

        # Priority 2: Lookup by Shipment (If no invoice found)
        if not db_context["customer"]:
            trk_id = extraction.get("entities", {}).get("tracking_id")
            if trk_id:
                db_context["shipment"] = controller.db.lookup_shipment(trk_id)
                if db_context["shipment"]:
                    db_context["customer"] = {
                        "name": db_context["shipment"]["customer_name"],
                        "loyalty_level": db_context["shipment"].get("loyalty_level", "Standard")
                    }

        # Priority 3: Fallback to Sender Email (Only if no Order ID is present)
        if not db_context["customer"]:
            sender_email = record['metadata']['sender']
            db_context["customer"] = controller.db.lookup_customer(sender_email)

        # FINAL FALLBACK: If still nothing, use a generic label (NO HALLUCINATIONS)
        if not db_context["customer"]:
            db_context["customer"] = {"name": "Unverified Customer", "loyalty_level": "Standard"}

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

@app.route('/api/process-email-stream', methods=['POST'])
def process_email_stream():
    """Phase 1: Stream AI extraction to frontend (Server-Sent Events)"""
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400
        
    data = request.get_json()
    msg = data.get('email')
    if not msg:
        return jsonify({"error": "No email object provided"}), 400

    def generate():
        import json
        from flask import current_app
        print(f"PIPELINE: Starting stream for email ID {msg.get('id')}")
        try:
            # Re-fetch attachments if needed
            attachments = msg.get('attachments', [])
            if msg.get('hasAttachments') and not attachments:
                access_token = request.headers.get('Authorization', '').replace('Bearer ', '')
                if access_token:
                    attachments = controller.fetcher.fetch_attachments(access_token, msg.get('id'))
            print("PIPELINE: Context sources initialized.")

            # Iterate over the generator from processor
            generator = controller.processor.process_single_email_stream(msg, attachments)
            
            for item in generator:
                if item["type"] == "metadata":
                    print("PIPELINE: Metadata yielded.")
                    yield f"data: {json.dumps(item)}\n\n"
                    
                elif item["type"] == "chunk":
                    # Stream raw token chunks for the frontend to accumulate
                    yield f"data: {json.dumps(item)}\n\n"
                    
                elif item["type"] == "final_record":
                    print("PIPELINE: Stage 2 Complete. Running DB & RAG logic...")
                    record = item["record"]
                    extraction = record.get("extraction", {})
                    
                    # Do DB Context and RAG synchronously once extraction finishes
                    db_context = {"invoice": None, "shipment": None, "customer": None}
                    inv_id = extraction.get("entities", {}).get("invoice_number")
                    if inv_id:
                        db_context["invoice"] = controller.db.lookup_invoice(inv_id)
                        if db_context["invoice"]:
                            db_context["customer"] = {
                                "name": db_context["invoice"]["customer_name"],
                                "loyalty_level": db_context["invoice"].get("loyalty_level", "Standard"),
                                "email": db_context["invoice"].get("customer_email")
                            }

                    if not db_context["customer"]:
                        trk_id = extraction.get("entities", {}).get("tracking_id")
                        if trk_id:
                            db_context["shipment"] = controller.db.lookup_shipment(trk_id)
                            if db_context["shipment"]:
                                db_context["customer"] = {
                                    "name": db_context["shipment"]["customer_name"],
                                    "loyalty_level": db_context["shipment"].get("loyalty_level", "Standard")
                                }

                    if not db_context["customer"]:
                        sender_email = record['metadata']['sender']
                        db_context["customer"] = controller.db.lookup_customer(sender_email)

                    if not db_context["customer"]:
                        db_context["customer"] = {"name": "Unverified Customer", "loyalty_level": "Standard"}

                    rag_context = []
                    if controller.vectorstore:
                        query_text = f"{msg.get('subject')} {extraction.get('summary', '')}"
                        rag_context = controller.vectorstore.query(query_text)

                    # Send final completed payload
                    final_payload = {
                        "type": "complete",
                        "record": record,
                        "db_context": db_context,
                        "rag_context": rag_context
                    }
                    yield f"data: {json.dumps(final_payload)}\n\n"
                    
                elif item["type"] == "error":
                    yield f"data: {json.dumps(item)}\n\n"

        except Exception as e:
            print(f"ERROR IN PROCESS_EMAIL_STREAM: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    from flask import Response, stream_with_context
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/generate-reply', methods=['POST'])
def generate_reply():
    """Phase 2: Generate the reply based on previously extracted context."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400
        
    data = request.get_json()
    extraction = data.get('extraction')
    db_context = data.get('db_context')
    rag_context = data.get('rag_context')
    
    try:
        # Use the Stage 3 model from config
        import config
        model = getattr(config, 'STAGE3_MODEL', 'mistral')
        draft_data = controller.processor.generate_reply_llama(extraction, db_context, rag_context, model=model)
        
        # Ensure it's a dict
        if not isinstance(draft_data, dict):
            draft_data = {"draft": str(draft_data), "thought_process": "Format error in processor."}
            
        return jsonify(draft_data)
    except Exception as e:
        print(f"CRITICAL ERROR IN GENERATE_REPLY: {e}")
        return jsonify({
            "error": str(e),
            "draft": "Error: Pipeline crashed.",
            "thought_process": f"Crash: {str(e)}"
        }), 500

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
