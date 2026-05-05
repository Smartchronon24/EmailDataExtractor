# EmailDataExtractor 📧🤖

An intelligent, automated email processing pipeline that fetches emails from Microsoft Outlook, extracts structured insights using a Two-Stage Local LLM pipeline, verifies data against a MySQL database, and facilitates human-in-the-loop reviews before sending automated replies.

## 📊 Project Workflow

![Project Workflow](workflow.png)

## 🚀 Key Features

- **Two-Stage AI Pipeline**: 
    - **Stage 1 (Mistral)**: Intent classification and routing.
    - **Stage 2 (Llama 3)**: Deep entity extraction (Invoices, Shipments, Feedback).
- **MySQL Database Integration**: Real-time verification of invoice status, customer loyalty levels, and shipment tracking.
- **Human-in-the-Loop (HITL)**: Interactive terminal review loop with **Notepad integration** for editing AI-generated drafts.
- **Automated Fetching & Dispatch**: Fetches unread emails from the Inbox and sends threaded replies via Microsoft Graph API.
- **Security Hardened**: Protected against **Prompt Injection** attacks using XML-style delimiters and strict system rules.
- **Data Layering**:
    - **Bronze Layer**: Raw JSON fetched from API.
    - **Silver Layer**: Structured extraction results.
    - **Gold Layer**: Verified records and dispatched replies.

## 🏗️ Architecture

The project follows a modular **MVC-inspired** structure, separating API communication, AI processing, and data persistence.

### 1. System Overview
```mermaid
graph TD
    subgraph External
        Outlook[MS Outlook / Graph API]
    end

    subgraph "Local Backend (Python)"
        Main[main.py: Controller]
        Processor[processor.py: AI Engine]
        DB[database.py: Data Layer]
        Docs[doc_processor.py: Attachment Service]
    end

    subgraph "Local Intelligence"
        Mistral[Mistral: Intent Analysis]
        Llama[Llama 3: Deep Extraction]
    end

    subgraph Persistence
        MySQL[(MySQL Database)]
    end

    Outlook -- Fetch Unread --> Main
    Main -- Extract Text --> Docs
    Main -- Stage 1 Analysis --> Mistral
    Main -- Stage 2 Extraction --> Llama
    Main -- Verify Records --> MySQL
    MySQL -- Contextual Data --> Main
    Main -- Human Review --> Notepad[Notepad Editor]
    Notepad -- Approved Reply --> Outlook
```

### 2. Two-Stage AI Pipeline
To ensure high accuracy and security, extraction is handled in two distinct phases:

```mermaid
graph LR
    A[Raw Email + Docs] --> B[Stage 1: Mistral]
    B -- "Intent: Invoice/Shipment" --> C[Stage 2: Llama 3]
    C -- "Strict JSON Schema" --> D[Structured Output]
    D -- "Prompt Injection Guard" --> E[Verified Data]
```

### 3. Database Schema (ERD)
The system uses a relational model to link billing data with logistics and customer profiles:

```mermaid
erDiagram
    CUSTOMERS ||--o{ INVOICES : "has"
    SHIPMENTS ||--o{ INVOICES : "linked to"
    CUSTOMERS ||--o{ SHIPMENTS : "belongs to"

    CUSTOMERS {
        int customer_id PK
        string name
        string email
        string loyalty_level
    }
    INVOICES {
        string invoice_id PK
        int customer_id FK
        string tracking_id FK
        decimal balance
        string status
    }
    SHIPMENTS {
        string tracking_id PK
        int customer_id FK
        string status
        text delay_reason
    }
```

## 🛠️ Setup Instructions

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) with `llama3` and `mistral` models.
- MySQL Server (local or remote).
- Microsoft Azure App registration (`Mail.Read`, `Mail.Send`, `Mail.ReadWrite`).

### 2. Installation
```bash
git clone https://github.com/Smartchronon24/EmailDataExtractor.git
cd EmailDataExtractor
pip install msal requests beautifulsoup4 ollama mysql-connector-python pandas
```

### 3. Database Setup
Run the provided SQL scripts in MySQL Workbench to create the `customers`, `invoices`, and `shipments` tables.

## 📂 Usage

### Run the Pipeline
```bash
python main.py
```
- The script will fetch unread emails.
- It will perform database lookups for any detected Invoice IDs or Tracking Numbers.
- If `ENABLE_REPLY_GENERATION` is True, it will prompt you to **Approve**, **Skip**, or **Edit** (via Notepad) the reply.

## 🛡️ Security
This project uses multi-layer security:
- **Prompt Injection Guards**: Strict rules prevent the LLM from obeying instructions embedded in email bodies.
- **Local Inference**: All data processing stays on your machine via Ollama.
- **Credential Isolation**: `KEYS.py` is excluded from version control to protect your API secrets.

---
*Created by [Smartchronon24](https://github.com/Smartchronon24)*
