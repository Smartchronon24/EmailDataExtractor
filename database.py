import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

class InvoiceDB:
    """
    Handles connections and queries to the MySQL Invoice Database.
    """
    def __init__(self):
        self.config = {
            'host': DB_HOST,
            'user': DB_USER,
            'password': DB_PASSWORD,
            'database': DB_NAME
        }

    def get_db_connection(self):
        """Returns a new MySQL database connection."""
        try:
            return mysql.connector.connect(**self.config)
        except mysql.connector.Error as err:
            print(f"Database Error: {err}")
            return None

    def lookup_invoice(self, invoice_id):
        """
        Looks up invoice details using a JOIN to pull customer 
        and shipment data from their respective source-of-truth tables.
        """
        conn = self.get_db_connection()
        if not conn: return None
        try:
            cursor = conn.cursor(dictionary=True)
            # We fetch specific columns for efficiency
            query = """
                SELECT 
                    i.invoice_id, i.invoice_date, i.total_amount, i.balance_amount, i.status,
                    c.name as customer_name, c.loyalty_level, c.email as customer_email,
                    s.status as shipment_status, s.estimated_delivery, s.progress, s.tracking_id
                FROM invoices i
                LEFT JOIN customers c ON i.customer_id = c.customer_id
                LEFT JOIN shipments s ON i.tracking_id = s.tracking_id
                WHERE i.invoice_id = %s
            """
            cursor.execute(query, (invoice_id,))
            result = cursor.fetchone()
            return self._clean_result(result)
        except mysql.connector.Error as err:
            print(f"Query Error: {err}")
            return None
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    def lookup_shipment(self, tracking_id):
        """Looks up shipment status and linked customer profile by tracking ID."""
        conn = self.get_db_connection()
        if not conn: return None
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT 
                    s.tracking_id, s.status, s.estimated_delivery, s.progress,
                    c.name as customer_name, c.loyalty_level
                FROM shipments s
                LEFT JOIN customers c ON s.customer_id = c.customer_id
                WHERE s.tracking_id = %s
            """
            cursor.execute(query, (tracking_id,))
            result = cursor.fetchone()
            return self._clean_result(result)
        except mysql.connector.Error as err:
            print(f"Query Error: {err}")
            return None
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

    def lookup_customer(self, email):
        """Looks up customer profile by email."""
        conn = self.get_db_connection()
        if not conn: return None
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM customers WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return self._clean_result(result)
        finally:
            if conn.is_connected(): cursor.close(); conn.close()

    def _clean_result(self, result):
        """Helper to convert MySQL objects to JSON-serializable formats."""
        if result:
            for key, value in result.items():
                if hasattr(value, 'isoformat'):
                    result[key] = value.isoformat()
                elif hasattr(value, 'to_eng_string') or isinstance(value, float):
                    result[key] = float(value)
        return result

class EmailStore:
    """
    Handles tracking of processed emails to prevent duplicate replies.
    """
    def __init__(self, db_manager):
        self.db = db_manager

    def initialize_table(self):
        """Creates the emails table if it doesn't exist."""
        conn = self.db.get_db_connection()
        if not conn: return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_emails (
                    message_id VARCHAR(255) PRIMARY KEY,
                    conversation_id VARCHAR(255),
                    sender_email VARCHAR(255),
                    subject TEXT,
                    received_at DATETIME,
                    intent VARCHAR(100),
                    status ENUM('PENDING', 'REPLIED', 'SKIPPED', 'DUPLICATE') DEFAULT 'PENDING',
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX (conversation_id),
                    INDEX (sender_email)
                )
            """)
            conn.commit()
            print("[Database] Emails table initialized.")
        finally:
            if conn.is_connected(): cursor.close(); conn.close()

    def check_duplicate(self, conversation_id, sender_email, current_message_id):
        """
        Checks if we've already replied to this thread or sender recently.
        Returns 'DUPLICATE' if a recent reply exists.
        """
        conn = None
        try:
            conn = self.db.get_db_connection()
            if not conn: 
                print("[Database] Skip duplicate check: No connection.")
                return None
                
            cursor = conn.cursor(dictionary=True)
            # 1. Check exact message ID
            cursor.execute("SELECT status FROM processed_emails WHERE message_id = %s", (current_message_id,))
            if cursor.fetchone(): return "EXACT_MATCH"

            # 2. Check Conversation Thread
            if conversation_id:
                query = "SELECT status FROM processed_emails WHERE conversation_id = %s AND status = 'REPLIED' LIMIT 1"
                cursor.execute(query, (conversation_id,))
                if cursor.fetchone(): return "THREAD_REPLIED"

            return None
        except Exception as e:
            print(f"[Database] Warning: Duplicate check skipped due to error: {e}")
            return None
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()

    def update_status(self, message_id, status):
        """Surgically updates the status of an email."""
        conn = None
        try:
            conn = self.db.get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            cursor.execute("UPDATE processed_emails SET status = %s WHERE message_id = %s", (status, message_id))
            conn.commit()
        except Exception as e:
            print(f"[Database] Warning: Failed to update status: {e}")
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()

    def log_email(self, msg_id, conv_id, sender, subject, received_at, intent, status='PENDING'):
        """Logs a new email into the database."""
        conn = None
        try:
            conn = self.db.get_db_connection()
            if not conn: return
            cursor = conn.cursor()
            query = """
                INSERT INTO processed_emails 
                (message_id, conversation_id, sender_email, subject, received_at, intent, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE status = VALUES(status)
            """
            # Outlook timestamps are often '2024-05-12T13:34:17Z'
            if received_at:
                received_at = received_at.replace('T', ' ').replace('Z', '')
            cursor.execute(query, (msg_id, conv_id, sender, subject, received_at, intent, status))
            conn.commit()
        except Exception as e:
            print(f"[Database] Warning: Failed to log email: {e}")
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()

if __name__ == "__main__":
    # Test connection and init
    db = InvoiceDB()
    store = EmailStore(db)
    store.initialize_table()
    
    test_id = "INV10688"
    print(f"Testing lookup for {test_id}...")
    result = db.lookup_invoice(test_id)
    if result:
        print(f"Found: {result}")
    else:
        print("Not found or connection error.")
