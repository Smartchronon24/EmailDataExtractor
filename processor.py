import json
from bs4 import BeautifulSoup
import ollama
import concurrent.futures
from config import MODEL_NAME, MAX_WORKERS

class EmailProcessor:
    """
    Handles parsing HTML and extracting structured data using an LLM.
    Acts as the data transformation service in the MVC architecture.
    """
    
    def __init__(self, model_name=MODEL_NAME, max_workers=MAX_WORKERS):
        self.model_name = model_name
        self.max_workers = max_workers

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

    def extract_email_info(self, email_text):
        """Uses Ollama to extract the intent and details from the email text."""
        
        prompt = f"""
        You are a universal Data Extraction API. Analyze the content below and extract ALL meaningful information into the EXACT JSON format specified.

        ### RULES:
        1. **Domain Agnostic**: Extract any relevant nouns/data (Names, IDs, Dates, Tasks, Hardware, Prices, etc.).
        2. **Dynamic Entities**: Use descriptive snake_case keys in the "entities" dictionary (e.g., "lab_tasks", "invoice_number").
        3. **No Conversational Text**: Output ONLY raw JSON. No explanations or markdown blocks.
        4. **Schema Strictness**: Ensure the "confidence_score" is a float at the ROOT level, not inside entities.

        ### REQUIRED SCHEMA:
        {{
            "intent": "string",
            "category": "string",
            "key_topics": ["string"],
            "more_details": ["string"],
            "entities": {{
                "key_name": ["value"]
            }},
            "confidence_score": 0.0
        }}

        ### CONTENT:
        {email_text}

        ### JSON OUTPUT:
        """
        
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt,
                    },
                ],
                stream=False,
                format='json'
            )
            
            content = response['message']['content']
            return json.loads(content)
        except Exception as e:
            print(f"Ollama Error: {e}")
            return {"error": str(e), "intent": f"Error: {str(e)}", "more_details": []}

    def process_single_email(self, msg):
        """Worker function to process a single email message."""
        subject = msg.get('subject', 'No Subject')
        received_at = msg.get('receivedDateTime', '')
        sender = msg.get('sender', {}).get('emailAddress', {}).get('address', 'Unknown')
        
        to_recipients = msg.get('toRecipients', [])
        recipient = "Unknown"
        if to_recipients:
            recipient = to_recipients[0].get('emailAddress', {}).get('address', 'Unknown')
        
        # 1. Clean email body text
        html_body = msg.get('body', {}).get('content', '')
        clean_text = self.clean_html(html_body)
        
        # 2. Use extracted text from documents (processed in main.py)
        doc_text = msg.get('extracted_text_from_docs', '')
        docs = msg.get('extracted_docs', [])
        
        # 3. Combine for LLM
        full_context = clean_text
        if doc_text:
            full_context += "\n" + doc_text
            
        print(f"Processing: {subject} (with {len(docs)} documents)")
        
        # 4. Extract insights using LLM
        extracted_info = self.extract_email_info(full_context)
        
        # Extract images passed from the fetcher
        images = msg.get('extracted_images', [])
        
        silver_record = {
            "sender email": sender,
            "recipient email": recipient,
            "recieved at": received_at,
            "Subject (of the email)": subject,
            "Intent": extracted_info.get("intent", ""),
            "Category": extracted_info.get("category", "General"),
            "Key Topics": extracted_info.get("key_topics", []),
            "more details": extracted_info.get("more_details", []),
            "Entities": extracted_info.get("entities", {}),
            "Confidence Score": extracted_info.get("confidence_score", -1.0),
            "images": images,
            "documents": [d.get("name") for d in docs],
            "processing_error": extracted_info.get("error", None)
        }
        
        return silver_record

    def process_emails(self, messages):
        """Processes a list of email messages concurrently."""
        processed_data = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = executor.map(self.process_single_email, messages)
            for result in results:
                processed_data.append(result)
        return processed_data
