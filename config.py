# Configuration for Email Data Extractor

# Number of emails to fetch in each run
EMAILS_TO_FETCH = 1

# LLM Models to use (Ollama)
STAGE1_MODEL = "mistral"
STAGE2_MODEL = "llama3"

# Pipeline Controls (Killswitches)
ENABLE_STAGE1 = False
ENABLE_STAGE2 = True
ENABLE_REPLY_GENERATION = True

# Parallel processing workers
MAX_WORKERS = 1

# Max JSON parsing retries
MAX_RETRIES = 2

# Data Storage Paths
RAW_DATA_PATH = "EmailDataExtractor/Mailcontents.json"              #Let the path be as it is dont change this
PROCESSED_DATA_PATH = "EmailDataExtractor/processed_emails.json"    #Let the path be as it is dont change this

# Database Configuration (MySQL)
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "Navan123#" 
DB_NAME = "email_extraction_db"
