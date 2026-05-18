import json
import re
from bs4 import BeautifulSoup
import ollama
import concurrent.futures
import asyncio
from config import STAGE1_MODEL, STAGE2_MODEL, STAGE3_MODEL, MAX_WORKERS, MAX_RETRIES, ENABLE_STAGE1, ENABLE_STAGE2
from agent_utils import TOOL_MAP, OLLAMA_TOOL_SCHEMAS

class EmailProcessor:
    """
    Handles parsing HTML and extracting structured data using a Fully Agentic Pipeline.
    Each stage is an autonomous agent that uses tools to fulfill its goal.
    """
    
    def __init__(self, stage1_model=STAGE1_MODEL, stage2_model=STAGE2_MODEL, stage3_model=STAGE3_MODEL, max_workers=MAX_WORKERS):
        self.stage1_model = stage1_model
        self.stage2_model = stage2_model
        self.stage3_model = stage3_model
        self.max_workers = max_workers
        self.max_retries = MAX_RETRIES
        self.enable_stage1 = ENABLE_STAGE1
        self.enable_stage2 = ENABLE_STAGE2

    def clean_html(self, html_content):
        """Converts HTML content to clean plain text."""
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text

    def _safe_parse_json(self, content):
        """Robustly extracts and parses JSON from a string."""
        if not content: return None
        try:
            start = content.find('{')
            end = content.rindex('}') + 1
            if start == -1 or end == 0:
                # Try finding any JSON-like structure or just return as is if it's already JSON
                return json.loads(content)
            return json.loads(content[start:end])
        except Exception:
            # Fallback: try to find anything between { and } using regex
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
            return None

    async def analyze_email_llama(self, subject, body, sender):
        """STAGE 1: Strategic Analysis Agent."""
        if not self.enable_stage1:
            return {"intent": "general", "priority_level": "normal"}

        system_prompt = f"""
        You are a Strategic Email Analyst. Goal: determine intent and priority.
        TOOLS: `lookup_customer`, `get_semantic_similarities`.
        OUTPUT JSON ONLY: {{"intent": "...", "priority": "...", "reasoning": "..."}}
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Subject: {subject}\nSender: {sender}\nBody: {body[:2000]}"}
        ]
        try:
            client = ollama.AsyncClient()
            print(f"\n>>> [STAGE 1 AGENT] Analyzing Strategy...")
            for turn in range(3):
                response = await client.chat(model=self.stage1_model, messages=messages, tools=OLLAMA_TOOL_SCHEMAS)
                message = response['message']
                if message.get('tool_calls'):
                    messages.append(message)
                    for call in message['tool_calls']:
                        name, args = call['function']['name'], call['function']['arguments']
                        print(f"    🛠️ [S1 TOOL]: {name}...")
                        fn = TOOL_MAP.get(name)
                        output = fn(**args) if fn else "Error"
                        messages.append({'role': 'tool', 'content': str(output), 'name': name})
                    continue
                
                content = message.get('content', '').strip()
                result = self._safe_parse_json(content)
                return result if result else {"intent": "general", "priority": "medium"}
        except Exception as e:
            print(f"S1 Error: {e}")
            return {"intent": "general", "priority_level": "medium"}

    async def extract_entities_llama(self, body, stage1_output, attachments=None):
        """STAGE 2: Autonomous Extraction Agent."""
        if not self.enable_stage2: return {"intent": "skipped"}
        
        system_prompt = f"""
        You are a Data Extraction Agent. Extract IDs and summary.
        TOOLS: `extract_document_text`, `lookup_invoice`, `lookup_shipment`.
        ATTACHMENTS AVAILABLE: {[a.get('name') for a in attachments] if attachments else "None"}
        OUTPUT JSON ONLY: {{"intent": "...", "category": "...", "entities": {{"invoice_number": "...", "tracking_number": "..."}}, "summary": "...", "thought_process": "..."}}
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Strategy: {stage1_output}\nBody: {body[:3000]}"}
        ]
        try:
            client = ollama.AsyncClient()
            print(f">>> [STAGE 2 AGENT] Extracting Entities...")
            
            # Dynamically filter tools to only include extract_document_text if attachments are actually present
            s2_tools = OLLAMA_TOOL_SCHEMAS
            if not attachments:
                s2_tools = [t for t in OLLAMA_TOOL_SCHEMAS if t['function']['name'] != 'extract_document_text']

            for turn in range(4):
                response = await client.chat(model=self.stage2_model, messages=messages, tools=s2_tools)
                message = response['message']
                if message.get('tool_calls'):
                    messages.append(message)
                    for call in message['tool_calls']:
                        name, args = call['function']['name'], call['function']['arguments']
                        if name == "extract_document_text" and attachments:
                            att = attachments[0]
                            base64_data = att.get('contentBytes') or att.get('base64')
                            args = {"base64_content": base64_data, "file_type": att.get('name', '').split('.')[-1]}
                        print(f"    🛠️ [S2 TOOL]: {name}...")
                        fn = TOOL_MAP.get(name)
                        output = fn(**args) if fn else "Error"
                        messages.append({'role': 'tool', 'content': str(output), 'name': name})
                    continue
                
                content = message.get('content', '').strip()
                result = self._safe_parse_json(content)
                if result:
                    print(f"    ✅ [S2 COMPLETE] Intent: {result.get('intent')} | Category: {result.get('category')}")
                    return result
            return {"intent": "unknown", "summary": "Extraction timed out."}
        except Exception as e:
            print(f"S2 Error: {e}")
            return {"intent": "error", "summary": f"Extraction failed: {str(e)}"}

    # --- COMPATIBILITY WRAPPERS FOR main.py ---
    def process_single_email(self, msg, attachments=None):
        """Sync wrapper for legacy main.py calls."""
        return asyncio.run(self.process_single_email_async(msg, attachments))

    async def process_single_email_async(self, msg, attachments=None):
        """Actual logic used by both sync and stream methods."""
        subject = msg.get('subject', 'No Subject')
        sender = msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
        recipient = msg.get('toRecipients', [{}])[0].get('emailAddress', {}).get('address', 'Unknown')
        received_at = msg.get('receivedDateTime', '')
        
        body_content = msg.get('body', {}).get('content', '')
        clean_text = self.clean_html(body_content)
        
        analysis_result = await self.analyze_email_llama(subject, clean_text, sender)
        extraction_result = await self.extract_entities_llama(clean_text, analysis_result, attachments)
        
        return {
            "metadata": {
                "sender": sender,
                "recipient": recipient,
                "timestamp": received_at,
                "subject": subject
            },
            "analysis": analysis_result,
            "extraction": extraction_result,
            "full_context": clean_text
        }

    async def process_single_email_stream(self, msg, attachments=None):
        """Processes an email but yields chunks for the Dashboard UI."""
        subject = msg.get('subject', 'No Subject')
        sender = msg.get('from', {}).get('emailAddress', {}).get('address', 'Unknown')
        recipient = msg.get('toRecipients', [{}])[0].get('emailAddress', {}).get('address', 'Unknown')
        received_at = msg.get('receivedDateTime', '')
        
        body_content = msg.get('body', {}).get('content', '')
        yield {"type": "status", "message": "Cleaning HTML body structure..."}
        clean_text = self.clean_html(body_content)
        
        yield {"type": "status", "message": "🤖 Stage 1: Strategic Agent Thinking..."}
        analysis_result = await self.analyze_email_llama(subject, clean_text, sender)
            
        metadata = {"sender": sender, "recipient": recipient, "timestamp": received_at, "subject": subject}
        yield {"type": "metadata", "metadata": metadata, "analysis": analysis_result}
        
        yield {"type": "status", "message": "🤖 Stage 2: Autonomous Extraction Agent Running..."}
        extraction_result = await self.extract_entities_llama(clean_text, analysis_result, attachments)
        
        record = {
            "metadata": metadata,
            "analysis": analysis_result,
            "extraction": extraction_result,
            "full_context": clean_text
        }
        yield {"type": "final_record", "record": record}

    async def generate_reply_llama(self, extraction_result, db_context, rag_context=None):
        """STAGE 3: Agentic reply generation."""
        intent = extraction_result.get("intent", "general")
        system_prompt = f"""You are a professional Customer Support Agent. Write a helpful email reply to the customer based on the facts provided. DO NOT ask for information that is already provided in the facts. NO HALLUCINATION. OUTPUT JSON ONLY: {{"draft": "your email text", "thought_process": "your reasoning"}}"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Intent: {intent}\nFacts: {json.dumps(db_context)}\nPast Emails: {json.dumps(rag_context)}"}
        ]
        try:
            client = ollama.AsyncClient()
            print(f"\n>>> [STAGE 3 AGENT] Drafting Reply...")
            response = await client.chat(model=self.stage3_model, messages=messages)
            content = response['message'].get('content', '').strip()
            result = self._safe_parse_json(content)
            return {"draft": result.get("draft", content) if result else content, "thought_process": result.get("thought_process", "Thinking complete.") if result else "N/A"}
        except Exception as e:
            return {"draft": "Error in generation.", "thought_process": str(e)}

    async def generate_reply_llama_stream(self, extraction, db_context, rag_context=None):
        """Phase 2 (STREAMING): Agentic reply generation."""
        intent = extraction.get('intent', 'General')
        system_prompt = f"""You are a professional Customer Support Agent. Write a helpful email reply to the customer based on the facts provided. DO NOT ask for information that is already provided in the facts. NO HALLUCINATION. OUTPUT JSON ONLY: {{"draft": "your email text", "thought_process": "your reasoning"}}"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Facts: {json.dumps(db_context)}\nPast Emails: {json.dumps(rag_context)}\nIntent: {intent}"}
        ]
        try:
            client = ollama.AsyncClient()
            print(f"\n>>> [STREAMING AGENT] Thinking...")
            stream_response = await client.chat(model=self.stage3_model, messages=messages, stream=True, format='json')
            async for chunk in stream_response:
                yield chunk['message']['content']
        except Exception as e:
            yield json.dumps({"error": str(e)})

    def process_emails(self, messages):
        """ Processes a list of email messages concurrently (Legacy Sync Method) """
        processed_data = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = executor.map(lambda m: self.process_single_email(m), messages)
            for result in results:
                processed_data.append(result)
        return processed_data
