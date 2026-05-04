import io
import base64
from pypdf import PdfReader
from docx import Document

class DocumentProcessor:
    """
    Utility class to extract text from document attachments.
    Supports PDF and DOCX formats.
    """

    @staticmethod
    def extract_text_from_pdf(base64_content):
        """Extracts text from a base64 encoded PDF file."""
        try:
            pdf_bytes = base64.b64decode(base64_content)
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)
            
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            return text.strip()
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
            return f"[Error extracting text from PDF: {str(e)}]"

    @staticmethod
    def extract_text_from_docx(base64_content):
        """Extracts text from a base64 encoded DOCX file."""
        try:
            docx_bytes = base64.b64decode(base64_content)
            docx_file = io.BytesIO(docx_bytes)
            doc = Document(docx_file)
            
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            
            return text.strip()
        except Exception as e:
            print(f"Error extracting DOCX text: {e}")
            return f"[Error extracting text from DOCX: {str(e)}]"

    @classmethod
    def process_docs(cls, docs):
        """Processes a list of docs and returns combined extracted text."""
        combined_text = ""
        for doc in docs:
            doc_name = doc.get("name", "Unknown")
            doc_type = doc.get("type")
            base64_data = doc.get("base64")
            
            if not base64_data:
                continue
                
            print(f"  - Extracting text from: {doc_name}")
            
            extracted = ""
            if doc_type == "pdf":
                extracted = cls.extract_text_from_pdf(base64_data)
            elif doc_type == "docx":
                extracted = cls.extract_text_from_docx(base64_data)
            
            if extracted:
                combined_text += f"\n--- CONTENT OF ATTACHMENT: {doc_name} ---\n{extracted}\n"
        
        return combined_text
