import msal
import requests
import json
from processor import EmailProcessor
from doc_processor import DocumentProcessor
from database import InvoiceDB
from KEYS import CLIENT_ID, AUTHORITY, SCOPES
from config import EMAILS_TO_FETCH, RAW_DATA_PATH, PROCESSED_DATA_PATH, ENABLE_REPLY_GENERATION, ONLY_UNREAD

class EmailFetcher:
    """
    Handles authentication and fetching data from Microsoft Graph API.
    Acts as the Data Model/Service in the MVC architecture.
    """
    def __init__(self, client_id, authority):
        self.client_id = client_id
        self.authority = authority
        self.app = msal.PublicClientApplication(self.client_id, authority=self.authority)

    def fetch_emails(self, access_token, top=1, only_unread=True):
        """Fetches emails from the Inbox folder."""
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        # Build the URL with optional filter
        base_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$top={top}"
        if only_unread:
            base_url += "&$filter=isRead eq false"
            
        response = requests.get(base_url, headers=headers)
        
        print("API STATUS:", response.status_code)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching emails: {response.text}")
            return None

    def mark_as_read(self, access_token, message_id):
        """Marks a specific message as read in Outlook."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
        payload = {"isRead": True}
        requests.patch(url, headers=headers, json=payload)

    def fetch_attachments(self, access_token, message_id):
        """Fetches attachments for a specific message."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json().get('value', [])
        return []

    def send_reply(self, access_token, message_id, reply_content):
        """Sends a reply to a specific email message using Graph API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Endpoint to create a reply draft and send it in one go
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply"
        
        payload = {
            "comment": reply_content
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 202:
            print(">>> SUCCESS: Email successfully sent via Microsoft Graph!")
            return True
        else:
            print(f">>> FAILED to send email: {response.status_code} - {response.text}")
            return False

class EmailController:
    """
    Controller that orchestrates the fetching and processing of emails.
    Links the EmailFetcher with the EmailProcessor and Database.
    """
    def __init__(self):
        self.client_id = CLIENT_ID
        self.authority = AUTHORITY
        self.scopes = SCOPES
        
        self.fetcher = EmailFetcher(self.client_id, self.authority)
        self.processor = EmailProcessor()
        self.db = InvoiceDB()
        self.enable_reply = ENABLE_REPLY_GENERATION

    def run_pipeline(self, emails_to_fetch=2):
        print(f"Starting pipeline to fetch and process {emails_to_fetch} emails...")
        
        # 1. Fetch raw emails
        result = self.fetcher.app.acquire_token_interactive(scopes=self.scopes)
        if "access_token" not in result:
            print("Authentication failed.")
            return
        
        access_token = result["access_token"]
        raw_data = self.fetcher.fetch_emails(access_token, top=emails_to_fetch, only_unread=ONLY_UNREAD)
        
        if not raw_data:
            print("Pipeline aborted: Failed to fetch emails.")
            return
            
        messages = raw_data.get('value', [])
        if not messages:
            msg_type = "Unread " if ONLY_UNREAD else ""
            print(f"\n[INFO] No {msg_type}Email available to process. Pipeline stopping.")
            return
        for msg in messages:
            msg['extracted_text_from_docs'] = ""
            if msg.get('hasAttachments'):
                print(f"Fetching attachments for: {msg.get('subject')}")
                attachments = self.fetcher.fetch_attachments(access_token, msg.get('id'))
                
                doc_attachments = []
                for att in attachments:
                    name = att.get("name", "")
                    content_bytes = att.get("contentBytes")
                    if name.endswith(".pdf"):
                        doc_attachments.append({"name": name, "type": "pdf", "base64": content_bytes})
                    elif name.endswith(".docx"):
                        doc_attachments.append({"name": name, "type": "docx", "base64": content_bytes})
                
                msg['extracted_text_from_docs'] = DocumentProcessor.process_docs(doc_attachments)

        # 2. Process emails and generate actions
        processed_data = []
        for msg in messages:
            # Stage 1 & 2: Extraction
            record = self.processor.process_single_email(msg)
            
            # --- MULTI-TABLE DB LOOKUP ---
            db_context = {"invoice": None, "shipment": None, "customer": None}
            extraction = record.get("extraction", {})
            entities = extraction.get("entities", {})
            
            # 1. GREEDY ID COLLECTION (AI + Regex Safety Net)
            all_possible_inv_ids = set()
            all_possible_trk_ids = set()

            # Path A: Explicit AI Extraction
            if entities.get("invoice_number"): all_possible_inv_ids.add(entities["invoice_number"])
            if entities.get("tracking_number"): all_possible_trk_ids.add(entities["tracking_number"])
            
            # Path B: Regex Scan (The "Production Safety Net")
            import re
            from config import INVOICE_PREFIXES, TRACKING_PREFIXES
            
            body_text = msg.get('body', {}).get('content', '')
            
            # Helper to build dynamic regex pattern
            def get_pattern(prefixes):
                if isinstance(prefixes, str): prefixes = [prefixes]
                pattern = "|".join(prefixes)
                return rf"(?:{pattern})-?\d+"

            inv_matches = re.findall(get_pattern(INVOICE_PREFIXES), body_text, re.IGNORECASE)
            trk_matches = re.findall(get_pattern(TRACKING_PREFIXES), body_text, re.IGNORECASE)
            
            for m in inv_matches: all_possible_inv_ids.add(m.upper())
            for m in trk_matches: all_possible_trk_ids.add(m.upper())

            # 2. DATABASE SEARCH
            inv_id = None
            if all_possible_inv_ids:
                inv_id = list(all_possible_inv_ids)[0]
                print(f"Searching database for Invoice: {inv_id}...")
                db_context["invoice"] = self.db.lookup_invoice(inv_id)
            
            trk_id = None
            if all_possible_trk_ids:
                trk_id = list(all_possible_trk_ids)[0]
            elif db_context["invoice"]:
                # Fallback: Get tracking from invoice record if not in email
                trk_id = db_context["invoice"].get("tracking_id")
            
            if trk_id:
                print(f"Searching database for Shipment: {trk_id}...")
                db_context["shipment"] = self.db.lookup_shipment(trk_id)
            
            # 3. CUSTOMER CONTEXT
            sender_email = record['metadata']['sender']
            db_context["customer"] = self.db.lookup_customer(sender_email)
            
            # Final touch: If DB lookup failed to find a customer, 
            # use the name Llama 3 might have found in the email!
            if not db_context["customer"]:
                db_context["customer"] = {"name": extraction.get("customer_name") or "Valued Customer"}
            
            # Stage 4 & 5: Reply Generation & Review (Respecting Killswitch)
            if self.enable_reply:
                draft_reply = self.processor.generate_reply_llama(record.get("extraction", {}), db_context)
                current_draft = draft_reply
                
                while True:
                    print("\n" + "="*50)
                    print(f"REVIEW DRAFT FOR: {record['metadata']['subject']}")
                    print(f"CONTEXT: " + ", ".join([k for k,v in db_context.items() if v]))
                    print("-"*50)
                    print(f"CURRENT DRAFT:\n{current_draft}")
                    print("-" * 50)
                    
                    choice = input("\nAction: [Y]es, send | [N]o, skip | [E]dit: ").lower()
                    
                    if choice == 'y':
                        # Convert newlines to <br> to ensure Outlook shows spacing
                        formatted_reply = current_draft.replace("\n", "<br>")
                        if self.fetcher.send_reply(access_token, msg.get('id'), formatted_reply):
                            record["action_taken"] = "Sent"
                            record["final_reply"] = current_draft
                            # Mark as read so it doesn't appear in the next run
                            self.fetcher.mark_as_read(access_token, msg.get('id'))
                        else:
                            record["action_taken"] = "Failed to Send"
                        break
                    elif choice == 'e':
                        current_draft = self.open_in_notepad(current_draft)
                        # Loop continues to show the new draft
                    else:
                        print(">>> SKIPPED: No email sent.")
                        record["action_taken"] = "Skipped"
                        break
            else:
                print(f">>> Extraction complete for: {record['metadata']['subject']} (Reply Generation Disabled)")
                record["action_taken"] = "Reply Generation Disabled"
                record["db_status"] = db_context
            
            processed_data.append(record)

        # 3. Save processed data (Silver Layer) - ALWAYS RUNS
        with open(PROCESSED_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_data, f, indent=2)
        print(f"\nPipeline complete! Results saved to {PROCESSED_DATA_PATH}")

    def open_in_notepad(self, content):
        """Helper to open a draft in Notepad and read it back after saving."""
        import subprocess
        import os
        
        temp_file = "edit_draft.txt"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"Opening Notepad... Please Edit, Save, and Close it to continue.")
        subprocess.run(["notepad.exe", temp_file])
        
        with open(temp_file, "r", encoding="utf-8") as f:
            updated_content = f.read()
            
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return updated_content

if __name__ == "__main__":
    controller = EmailController()
    controller.run_pipeline(emails_to_fetch=EMAILS_TO_FETCH)
