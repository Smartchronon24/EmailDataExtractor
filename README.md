# EmailDataExtractor 📧🤖

An intelligent, automated email processing pipeline that fetches emails from Microsoft Outlook (via Graph API), extracts structured insights using a Local LLM (Ollama), and converts them into analysis-ready formats (JSON/CSV).

## 🚀 Key Features

- **Automated Fetching**: Connects to Microsoft Graph API to fetch the latest emails and their attachments.
- **AI-Powered Extraction**: Uses **Llama 3** (via Ollama) to intelligently identify:
    - **Intent**: The primary purpose of the email.
    - **Category**: Automatic classification (Invoice, Reminder, Meeting, etc.).
    - **Entities**: High-precision extraction of Invoice Numbers, Dates, Amounts, and Balances.
- **Parallel Processing**: Utilizes concurrent workers to process multiple emails simultaneously for speed and efficiency.
- **Data Layering**:
    - **Bronze Layer**: Raw JSON data fetched from the API.
    - **Silver Layer**: Structured, AI-processed JSON data.
- **CSV Conversion**: A dedicated script to transform processed data into CSV format for easy reporting.
- **Security First**: Separated credentials and configurations to ensure safety when using version control.

## 🏗️ Architecture

The project follows a modular **MVC-inspired** structure:
- **`main.py`**: The Controller. Orchestrates the pipeline and handles the API communication.
- **`processor.py`**: The Data Transformation Service. Handles HTML cleaning and LLM extraction logic.
- **`config.py`**: The Configuration Layer. Centralized settings for model names, thread counts, and paths.
- **`KEYS.py`**: The Security Layer (Ignored by Git). Stores sensitive API credentials.
- **`JSON-to-CSV.py`**: Utility script for data conversion and verification.

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.8+
- [Ollama](https://ollama.com/) installed and running locally with the `llama3` model.
- A Microsoft Azure App registration for Graph API access.

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Smartchronon24/EmailDataExtractor.git
cd EmailDataExtractor

# Install dependencies
pip install msal requests beautifulsoup4 ollama pandas
```

### 3. Configuration
1. **Credentials**: Create a `KEYS.py` file (if not present) and add your MS Graph credentials:
   ```python
   CLIENT_ID = "your-client-id"
   AUTHORITY = "https://login.microsoftonline.com/common"
   SCOPES = ["Mail.Read"]
   ```
2. **Settings**: Adjust settings in `config.py`:
   ```python
   EMAILS_TO_FETCH = 5
   MODEL_NAME = "llama3"
   MAX_WORKERS = 5
   ```

## 📂 Usage

### Run the Pipeline
Fetches emails, cleans them, and extracts AI insights:
```bash
python main.py
```

### Convert to CSV
Transform the processed results into a spreadsheet:
```bash
python test.py
```

## 🛡️ Security
This project uses a `.gitignore` file to ensure that:
- `KEYS.py` (Secrets) are never pushed to GitHub.
- Local data files (`.json`, `.csv`) are kept private.
- Python temporary files (`__pycache__`) are ignored.

## 📊 Sample Output
The AI extracts data with high precision, distinguishing between different financial entities:
```json
{
  "Intent": "Payment reminder for past due account",
  "Category": "Invoice",
  "Entities": {
    "invoice_number": ["INV10688", "INV00688"],
    "total_balance": ["9345.00"]
  },
  "Confidence Score": 1.0
}
```

---
*Created by [Smartchronon24](https://github.com/Smartchronon24)*
