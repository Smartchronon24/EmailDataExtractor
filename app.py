import os
import json
import time
import asyncio
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from main import EmailController
from stage0_agent import stage0_deduplicate

app = Flask(__name__)

try:
    controller = EmailController()
    print(">>> [INIT] EmailController initialized successfully.")
except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}")
    controller = None

@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy", "controller": controller is not None})

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/fetch-emails')
def get_emails():
    if not controller:
        return jsonify({"error": "Controller failed to initialize."}), 500
    try:
        print(">>> [API] Fetching access token...")
        access_token = controller.fetcher.get_access_token()
        if not access_token:
            print(">>> [API] Auth Failed: No token returned.")
            return jsonify({"error": "Auth failed"}), 401
        
        print(">>> [API] Fetching emails...")
        from config import ONLY_UNREAD, EMAILS_TO_FETCH
        emails = controller.fetcher.fetch_emails(access_token, top=EMAILS_TO_FETCH, only_unread=ONLY_UNREAD)
        return jsonify(emails)
    except Exception as e:
        print(f">>> [API] ERROR in get_emails: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/process-stream', methods=['POST'])
@app.route('/api/process-email-stream', methods=['POST'])
def process_email_stream():
    """Phase 1: Extraction with real-time status updates."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON"}), 400
    
    payload = request.get_json()
    msg = payload.get('email', payload) # Support both {email: {}} and direct {}
    attachments = msg.get('attachments', [])

    def generate():
        # Setup the event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            with app.app_context():
                # 1. SETUP & STAGE 0 (Deduplication)
                subject = msg.get('subject', 'No Subject')
                body_raw = msg.get('body', {}).get('content', '')
                sender = msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
                conv_id = msg.get('conversationId')
                msg_id = msg.get('id')
                
                yield f"data: {json.dumps({'type': 'status', 'message': 'Running Stage 0: Intelligent Duplication Check...'})}\n\n"
                
                agent_result = loop.run_until_complete(stage0_deduplicate(subject, body_raw, sender, conv_id, msg_id))
                decision = agent_result.get("decision")
                reason = agent_result.get("reasoning", "")

                if "MATCH_REPLIED" in reason or "THREAD_REPLIED" in reason:
                    yield f"data: {json.dumps({'type': 'status', 'message': 'ℹ️ Already replied to this thread. Viewing history only.'})}\n\n"
                elif "MATCH_PENDING" in reason:
                    yield f"data: {json.dumps({'type': 'status', 'message': '⚠️ Processed previously (No reply sent). Re-extracting data...'})}\n\n"
                elif decision == "DUPLICATE":
                    yield f"data: {json.dumps({'type': 'status', 'message': f'⚠️ Potential duplicate: {reason}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'status', 'message': '✅ Stage 0: New inquiry confirmed.'})}\n\n"

                # If DUPLICATE is detected and we have the matched message ID, bypass Llama entirely
                matched_msg_id = agent_result.get("matched_msg_id")
                if decision == "DUPLICATE" and matched_msg_id and controller.vectorstore:
                    yield f"data: {json.dumps({'type': 'status', 'message': '⚡ Bypassing AI Extraction: Using matched historical data...'})}\n\n"
                    try:
                        res = controller.vectorstore.collection.get(ids=[matched_msg_id], include=["metadatas"])
                        if res and res.get("metadatas") and res["metadatas"][0]:
                            old_meta = res["metadatas"][0]
                            extraction = {
                                "intent": old_meta.get("intent", "general"),
                                "category": "Duplicate Inquiry",
                                "entities": {
                                    "invoice_number": old_meta.get("invoice_id", ""),
                                    "tracking_number": old_meta.get("tracking_id", "")
                                },
                                "summary": "Stage 0 successfully identified this as a duplicate inquiry. Skipped redundant LLM processing."
                            }
                            db_context = {
                                "invoice": controller.db.lookup_invoice(old_meta.get("invoice_id")) if old_meta.get("invoice_id") else None,
                                "shipment": controller.db.lookup_shipment(old_meta.get("tracking_id")) if old_meta.get("tracking_id") else None,
                                "customer": controller.db.lookup_customer(sender)
                            }
                            query_text = f"SUBJECT: {subject}\n\nBODY: {body_raw[:2000]}"
                            rag_context = controller.vectorstore.query(query_text)
                            
                            final_payload = {
                                "type": "complete",
                                "record": {
                                    "metadata": {"sender": sender, "subject": subject},
                                    "extraction": extraction,
                                    "full_context": body_raw
                                },
                                "db_context": db_context,
                                "rag_context": rag_context,
                                "duplicate_info": agent_result
                            }
                            
                            # MUST log this new email in the DB so that if the user clicks "Send", it can be marked as REPLIED
                            try:
                                controller.email_store.log_email(
                                    msg_id=msg_id,
                                    conv_id=conv_id,
                                    sender=sender,
                                    subject=subject,
                                    received_at=msg.get('receivedDateTime'),
                                    intent=extraction.get('intent', 'general'),
                                    status='PENDING'
                                )
                                print(f"[Database] Logged duplicate bypass email {msg_id} as PENDING.")
                            except Exception as db_err:
                                print(f"[Database] Warning: Failed to log duplicate email: {db_err}")

                            yield f"data: {json.dumps(final_payload)}\n\n"
                            return  # Early exit (skip Stages 1 & 2)
                    except Exception as e:
                        print(f"Failed to fetch duplicate from VectorDB: {e}")
                        yield f"data: {json.dumps({'type': 'status', 'message': '⚠️ Failed to load historical context. Falling back to re-extraction.'})}\n\n"

                # 2. RUN PIPELINE (Stages 1 & 2)
                email_attachments = attachments
                if msg.get('hasAttachments') and not email_attachments:
                    yield f"data: {json.dumps({'type': 'status', 'message': '📎 Email has attachments. Fetching from Outlook...'})}\n\n"
                    try:
                        access_token = controller.fetcher.get_access_token()
                        email_attachments = controller.fetcher.fetch_attachments(access_token, msg_id)
                        yield f"data: {json.dumps({'type': 'status', 'message': f'📎 Successfully fetched {len(email_attachments)} attachment(s).'})}\n\n"
                    except Exception as att_err:
                        print(f"Failed to fetch attachments: {att_err}")
                        yield f"data: {json.dumps({'type': 'status', 'message': f'⚠️ Attachment fetch failed: {str(att_err)}'})}\n\n"

                async_gen = controller.processor.process_single_email_stream(msg, email_attachments)
                it = async_gen.__aiter__()
                
                while True:
                    try:
                        item = loop.run_until_complete(it.__anext__())
                        
                        if item["type"] == "final_record":
                            record = item["record"]
                            extraction = record["extraction"]
                            
                            # Deterministic regex fallback for matching IDs if LLM fails or keys differ
                            from agent_utils import extract_ids_regex
                            regex_ids = {}
                            try:
                                regex_ids = json.loads(extract_ids_regex(record.get("full_context", "")))
                            except Exception:
                                pass
                                
                            inv_id = extraction.get('entities', {}).get('invoice_number') or extraction.get('entities', {}).get('invoice_id')
                            if not inv_id and regex_ids.get('invoice_ids'):
                                inv_id = regex_ids['invoice_ids'][0]
                                
                            trk_id = extraction.get('entities', {}).get('tracking_number') or extraction.get('entities', {}).get('tracking_id')
                            if not trk_id and regex_ids.get('tracking_ids'):
                                trk_id = regex_ids['tracking_ids'][0]

                            db_context = {
                                "invoice": controller.db.lookup_invoice(inv_id) if inv_id else None,
                                "shipment": controller.db.lookup_shipment(trk_id) if trk_id else None,
                                "customer": controller.db.lookup_customer(sender)
                            }
                            
                            # Retrieve RAG context from VectorStore if enabled
                            rag_context = []
                            clean_text = record.get("full_context", "")
                            if controller.vectorstore:
                                try:
                                    query_text = f"SUBJECT: {subject}\n\nBODY: {clean_text[:2000]}"
                                    rag_context = controller.vectorstore.query(query_text)
                                except Exception as rag_err:
                                    print(f"[VectorDB] Warning: Failed to query RAG: {rag_err}")

                            # Ingest the newly processed record into VectorStore for future queries
                            if controller.vectorstore:
                                try:
                                    controller.vectorstore.store(
                                        message_id=msg_id,
                                        raw_email=msg,
                                        extraction=extraction,
                                        db_context=db_context,
                                        clean_body=clean_text
                                    )
                                except Exception as store_err:
                                    print(f"[VectorDB] Warning: Failed to ingest email into VectorDB: {store_err}")
                            
                            # Log processed email in database
                            try:
                                controller.email_store.log_email(
                                    msg_id=msg_id,
                                    conv_id=conv_id,
                                    sender=sender,
                                    subject=subject,
                                    received_at=msg.get('receivedDateTime'),
                                    intent=extraction.get('intent', 'general'),
                                    status='PENDING'
                                )
                                print(f"[Database] Logged email {msg_id} as PENDING.")
                            except Exception as db_err:
                                print(f"[Database] Warning: Failed to log processed email: {db_err}")

                            final_payload = {
                                "type": "complete",
                                "record": record,
                                "db_context": db_context,
                                "rag_context": rag_context,
                                "duplicate_info": agent_result if decision == "DUPLICATE" else None
                            }
                            yield f"data: {json.dumps(final_payload)}\n\n"
                            break
                        else:
                            yield f"data: {json.dumps(item)}\n\n"
                    except StopAsyncIteration:
                        break

        except Exception as e:
            print(f"PIPELINE CRITICAL ERROR: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            loop.close()

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/generate-reply', methods=['POST'])
def generate_reply():
    """Phase 2: Generate the final draft."""
    data = request.json
    extraction = data.get('extraction')
    db_context = data.get('db_context')
    rag_context = data.get('rag_context')
    
    try:
        import asyncio
        draft_data = asyncio.run(controller.processor.generate_reply_llama(extraction, db_context, rag_context))
        return jsonify(draft_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/send-email', methods=['POST'])
def send_email():
    data = request.json
    message_id = data.get('message_id')
    content = data.get('content')
    try:
        access_token = controller.fetcher.get_access_token()
        if not access_token: return jsonify({"error": "Auth failed"}), 401
        formatted_content = content.replace("\n", "<br>")
        success = controller.fetcher.send_reply(access_token, message_id, formatted_content)
        if success:
            controller.fetcher.mark_as_read(access_token, message_id)
            controller.email_store.update_status(message_id, 'REPLIED')
            return jsonify({"success": True})
        return jsonify({"error": "Failed to send"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    import config
    if request.method == 'GET':
        return jsonify({
            "STAGE1_MODEL": config.STAGE1_MODEL,
            "STAGE2_MODEL": config.STAGE2_MODEL,
            "STAGE3_MODEL": config.STAGE3_MODEL,
            "THEME": getattr(config, 'THEME', 'dark'),
            "ENABLE_STAGE1": config.ENABLE_STAGE1,
            "OPTIMIZE_STAGE1": config.OPTIMIZE_STAGE1,
            "ENABLE_RAG": config.ENABLE_RAG,
            "INVOICE_PREFIXES": config.INVOICE_PREFIXES,
            "TRACKING_PREFIXES": config.TRACKING_PREFIXES,
            "MAX_WORKERS": config.MAX_WORKERS,
            "MAX_RETRIES": config.MAX_RETRIES,
            "EMAILS_TO_FETCH": config.EMAILS_TO_FETCH,
            "ONLY_UNREAD": config.ONLY_UNREAD
        })
    
    new_settings = request.json
    config_path = os.path.join(os.path.dirname(__file__), 'config.py')
    
    with open(config_path, 'r') as f:
        lines = f.readlines()
    
    with open(config_path, 'w') as f:
        for line in lines:
            updated = False
            for key, val in new_settings.items():
                if line.startswith(f"{key} ="):
                    if isinstance(val, str): f.write(f"{key} = '{val}'\n")
                    else: f.write(f"{key} = {val}\n")
                    updated = True
                    break
            if not updated: f.write(line)
            
    controller.reload_config()
    return jsonify({"success": True})

@app.route('/api/generate-reply-stream', methods=['POST'])
def generate_reply_stream():
    data = request.get_json()
    def generate():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = controller.processor.generate_reply_llama_stream(data.get('extraction'), data.get('db_context'), data.get('rag_context'))
            it = async_gen.__aiter__()
            while True:
                try:
                    chunk = loop.run_until_complete(it.__anext__())
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                except StopAsyncIteration: break
            yield "data: {\"type\": \"complete\"}\n\n"
        finally: loop.close()
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
