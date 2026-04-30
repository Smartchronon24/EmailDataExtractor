import msal
import requests
import json
from processor import EmailProcessor
from KEYS import CLIENT_ID, AUTHORITY, SCOPES
from config import EMAILS_TO_FETCH, RAW_DATA_PATH, PROCESSED_DATA_PATH

class EmailFetcher:
    """
    Handles authentication and fetching data from Microsoft Graph API.
    Acts as the Data Model/Service in the MVC architecture.
    """
    def __init__(self, client_id, authority):
        self.client_id = client_id
        self.authority = authority
        self.app = msal.PublicClientApplication(self.client_id, authority=self.authority)

    def fetch_emails(self, access_token, top=1):
        """Fetches emails from Microsoft Graph API using the provided access token."""
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top}"
        response = requests.get(url, headers=headers)
        
        print("API STATUS:", response.status_code)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching emails: {response.text}")
            return None

    def fetch_attachments(self, access_token, message_id):
        """Fetches attachments for a specific message."""
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json().get('value', [])
        return []

class EmailController:
    """
    Controller that orchestrates the fetching and processing of emails.
    Links the EmailFetcher with the EmailProcessor.
    """
    def __init__(self):
        self.client_id = CLIENT_ID
        self.authority = AUTHORITY
        self.scopes = SCOPES
        
        self.fetcher = EmailFetcher(self.client_id, self.authority)
        self.processor = EmailProcessor()

    def run_pipeline(self, emails_to_fetch=2):
        print(f"Starting pipeline to fetch and process {emails_to_fetch} emails...")
        
        # 1. Fetch raw emails
        result = self.fetcher.app.acquire_token_interactive(scopes=self.scopes)
        if "access_token" not in result:
            print("Authentication failed.")
            return
        
        access_token = result["access_token"]
        raw_data = self.fetcher.fetch_emails(access_token, top=emails_to_fetch)
        
        if not raw_data:
            print("Pipeline aborted: Failed to fetch emails.")
            return
            
        messages = raw_data.get('value', [])
        for msg in messages:
            if msg.get('hasAttachments'):
                print(f"Fetching attachments for: {msg.get('subject')}")
                attachments = self.fetcher.fetch_attachments(access_token, msg.get('id'))
                # Store images as base64 in the message object
                msg['extracted_images'] = [
                    {
                        "name": att.get("name"),
                        "contentType": att.get("contentType"),
                        "base64": att.get("contentBytes")
                    }
                    for att in attachments 
                    if att.get("contentType", "").startswith("image/")
                ]
            else:
                msg['extracted_images'] = []

        # Save raw data (Bronze Layer)
        with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2)
        print(f"Raw emails (with images) saved to {RAW_DATA_PATH}")
            
        # 2. Process emails
        messages = raw_data.get('value', [])
        if not messages:
            print("No messages found in the raw data.")
            return
            
        processed_data = self.processor.process_emails(messages)
        
        # Save processed data (Silver Layer)
        with open(PROCESSED_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_data, f, indent=2)
        print(f"Successfully processed {len(processed_data)} emails. Results saved to {PROCESSED_DATA_PATH}")

if __name__ == "__main__":
    controller = EmailController()
    controller.run_pipeline(emails_to_fetch=EMAILS_TO_FETCH)
