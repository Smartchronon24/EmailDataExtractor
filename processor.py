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
        You are an intelligent Email Information Extraction Engine.

        Analyze the email and extract structured data.

        STRICT RULES:
        1. ONLY return valid JSON. No explanation.
        2. DO NOT hallucinate.
        3. DO NOT skip values — extract everything meaningful.
        4. DO NOT merge multiple values into one.
        5. ALL entity values MUST be returned as LISTS.
        6. Entity keys MUST be meaningful, lowercase, and snake_case.
        7. If multiple values exist for the same entity, include ALL of them.
        8. DO NOT force entities into predefined categories.
        9. Dynamically create entity names based on content.
        10. If unsure about an entity name, use a generic but meaningful label.

        ----------------------------------

        ENTITY EXTRACTION GUIDELINES:

        - Extract ANY useful structured information:
        Examples:
        - invoice_number
        - invoice_date
        - due_date
        - amount
        - total_balance
        - customer_name
        - product_name
        - order_id
        - meeting_date
        - location
        - email
        - phone_number

        - DO NOT restrict to these examples.
        - Adapt entity names based on email content.

        ----------------------------------

        IMPORTANT:

        - If the email contains repeated structures (like tables),
        extract each field as a list maintaining order.
        
        
        
        
        Email Content:
        {email_text}
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
