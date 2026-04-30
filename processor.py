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
        You are a high-precision Data Extraction API specializing in financial and business emails. 
        Analyze the email content and extract structured data into the EXACT JSON format specified below.

        ### REQUIRED JSON SCHEMA:
        {{
            "intent": "Short summary of why the email was sent",
            "category": "One of: Invoice, Claim, Reminder, Meeting, Announcement, Personal, Other",
            "more_details": ["Detail 1", "Detail 2", "..."],
            "entities": {{
                "invoice_number": ["INV-123"],
                "invoice_amount": ["100.00"],
                "outstanding_balance": ["50.00"],
                "total_due": ["150.00"],
                "dates": ["2026-01-01"],
                "...": ["..."]
            }},
            "confidence_score": 0.0 to 1.0
        }}

        ### EXTRACTION RULES:
        1. **Contextual Keys**: Do NOT group all numbers into "Amount". Use specific keys like `invoice_amount`, `outstanding_balance`, `total_due`, or `tax` based on the email context.
        2. **Multi-values**: Extract every instance. If there are multiple invoices, list all their numbers and amounts.
        3. **Normalization**: Return dates in a consistent format if possible, but prioritize accuracy.
        4. **NO TEXT**: Output ONLY raw JSON. No markdown blocks, no conversational filler.
        
        EXTRACTION LOGIC:

        - Identify intent from tone and keywords (e.g., reminder, complaint, update).
        - Classify category based on context (finance, operations, personal, etc.).
        - Extract ALL possible entities into the correct groups.
        - If entity type is unknown, place it in "custom".
        - Preserve duplicates when they appear multiple times.
        - DO NOT drop partial values.
        
        ### EXAMPLE:
        Email: "Invoice INV001 for $500 is due. Your total balance is $1200."
        Output: {{
            "intent": "Invoice notification and balance reminder",
            "category": "Invoice",
            "more_details": ["Invoice INV001 issued", "Total balance is $1200"],
            "entities": {{
                "invoice_number": ["INV001"],
                "invoice_amount": ["500"],
                "total_balance": ["1200"]
            }},
            "confidence_score": 1.0
        }}

        ### EMAIL CONTENT:
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
        
        html_body = msg.get('body', {}).get('content', '')
        clean_text = self.clean_html(html_body)
        
        print(f"Processing: {subject}")
        
        extracted_info = self.extract_email_info(clean_text)
        
        # Extract images passed from the fetcher
        images = msg.get('extracted_images', [])
        
        silver_record = {
            "sender email": sender,
            "recipient email": recipient,
            "recieved at": received_at,
            "Subject (of the email)": subject,
            "Intent": extracted_info.get("intent", ""),
            "Category": extracted_info.get("category", "General"),
            "more details": extracted_info.get("more_details", []),
            "Entities": extracted_info.get("entities", {}),
            "Confidence Score": extracted_info.get("confidence_score", -1.0),
            "images": images,
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
