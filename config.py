# Configuration for Email Data Extractor

# Number of emails to fetch in each run
EMAILS_TO_FETCH = 2

# LLM Model to use (Ollama)
MODEL_NAME = "llama3"

# Parallel processing workers
MAX_WORKERS = 1

# Data Storage Paths
RAW_DATA_PATH = "EmailDataExtractor/Mailcontents.json"
PROCESSED_DATA_PATH = "EmailDataExtractor/processed_emails.json"

