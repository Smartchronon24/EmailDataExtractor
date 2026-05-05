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
        """Looks up invoice details including linked customer and shipment info."""
        conn = self.get_db_connection()
        if not conn: return None
        try:
            cursor = conn.cursor(dictionary=True)
            # Use JOINs to get linked data automatically
            query = """
                SELECT 
                    i.*, 
                    c.name as customer_name, c.loyalty_level,
                    s.status as shipment_status, s.estimated_delivery, s.delay_reason
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
                SELECT s.*, c.name as customer_name, c.loyalty_level
                FROM shipments s
                LEFT JOIN customers c ON s.customer_id = c.customer_id
                WHERE s.tracking_id = %s
            """
            cursor.execute(query, (tracking_id,))
            result = cursor.fetchone()
            return self._clean_result(result)
        finally:
            if conn.is_connected(): cursor.close(); conn.close()

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

if __name__ == "__main__":
    # Test connection
    db = InvoiceDB()
    test_id = "INV10688"
    print(f"Testing lookup for {test_id}...")
    result = db.lookup_invoice(test_id)
    if result:
        print(f"Found: {result}")
    else:
        print("Not found or connection error.")
