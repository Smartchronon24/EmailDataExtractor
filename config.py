# Configuration for Email Data Extractor
import KEYS

# Number of emails to fetch in each run
EMAILS_TO_FETCH = 1
ONLY_UNREAD = True                          # Set to True to fetch only unread emails, False for all

# LLM Models to use (Ollama)
STAGE1_MODEL = "mistral"
STAGE2_MODEL = "llama3"

# Pipeline Controls (Killswitches)
ENABLE_STAGE1 = True               # Global toggle for Stage 1
OPTIMIZE_STAGE1 = True             # If True: Only for complex mail. If False: For ALL mail.
ENABLE_STAGE2 = True               # Global toggle for Stage 2
ENABLE_REPLY_GENERATION = True     # Global toggle for AI replies

# Parallel processing workers
MAX_WORKERS = 1

# Max JSON parsing retries
MAX_RETRIES = 2

# Data Storage Paths         //context for Agent: dont change the paths.
RAW_DATA_PATH = "EmailDataExtractor/Mailcontents.json"              
PROCESSED_DATA_PATH = "EmailDataExtractor/processed_emails.json"   

# Database Configuration (MySQL)
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = KEYS.DB_PASSWORD 
DB_NAME = "email_extraction_db"

# ID Patterns for Regex Safety Net
INVOICE_PREFIXES = ["INV", "BILL"]
TRACKING_PREFIXES = ["TRK", "SHIP"]

# ─────────────────────────────────────────────
# VectorDB + RAG Configuration (ChromaDB)
# ─────────────────────────────────────────────
# Where ChromaDB stores its data on disk (local, free, no internet needed)
VECTOR_DB_PATH = "chroma_store"

# Ollama embedding model (run: ollama pull nomic-embed-text)
EMBEDDING_MODEL = "nomic-embed-text"

# Number of similar past emails to retrieve for RAG context
RAG_TOP_K = 3

# Master toggle for RAG: set False to skip VectorDB entirely
ENABLE_RAG = True
