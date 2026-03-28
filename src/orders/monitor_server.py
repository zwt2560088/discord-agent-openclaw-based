"""
Order Monitoring Dashboard Server
Web interface for monitoring all orders
"""
import json
import logging
import os
import sqlite3
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
DB_PATH = os.path.join(PROJECT_DIR, "data", "orders", "orders.db")


class OrderMonitorHandler(SimpleHTTPRequestHandler):
    """HTTP handler for order monitoring API"""

    def __init__(self, *args, **kwargs):
        self.monitor_dir = BASE_DIR
        super().__init__(*args, directory=self.monitor_dir, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/orders':
            self._handle_get_orders()
        elif path == '/api/stats':
            self._handle_get_stats()
        elif path == '/api/order/':
            order_id = path.split('/')[-1]
            self._handle_get_order(order_id)
        elif path == '/':
            self.path = '/monitor.html'
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        if path == '/api/update-status':
            self._handle_update_status(body)
        elif path == '/api/assign':
            self._handle_assign(body)
        else:
            self._send_error(404, "Not Found")

    def _send_json(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _send_error(self, code, message):
        """Send error response"""
        self._send_json({"error": message}, code)

    def _get_db_connection(self):
        """Get database connection"""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return sqlite3.connect(DB_PATH)

    def _handle_get_orders(self):
        """Get all orders"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
            rows = cursor.fetchall()
            conn.close()

            orders = []
            for row in rows:
                orders.append({
                    "id": row[0],
                    "customer_id": row[1],
                    "customer_name": row[2],
                    "worker_id": row[3],
                    "worker_name": row[4],
                    "service_type": row[5],
                    "current_level": row[6],
                    "target_level": row[7],
                    "price": row[11],
                    "status": row[12],
                    "platform": row[10],
                    "urgent": bool(row[13]),
                    "created_at": row[17]
                })

            self._send_json({"orders": orders})
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_get_stats(self):
        """Get order statistics"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            stats = {}

            # Total orders
            cursor.execute("SELECT COUNT(*) FROM orders")
            stats['total'] = cursor.fetchone()[0]

            # By status
            statuses = ['pending', 'paid', 'assigned', 'in_progress', 'completed', 'delivered', 'cancelled']
            for status in statuses:
                cursor.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (status,))
                stats[status] = cursor.fetchone()[0]

            # Today's orders
            cursor.execute("SELECT COUNT(*) FROM orders WHERE date(created_at) = date('now')")
            stats['today'] = cursor.fetchone()[0]

            # Total revenue
            cursor.execute("SELECT SUM(price) FROM orders WHERE status IN ('completed', 'delivered')")
            stats['revenue'] = cursor.fetchone()[0] or 0

            conn.close()
            self._send_json(stats)
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_get_order(self, order_id):
        """Get single order with messages"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()

            if not row:
                self._send_error(404, "Order not found")
                return

            order = {
                "id": row[0],
                "customer_id": row[1],
                "customer_name": row[2],
                "worker_id": row[3],
                "worker_name": row[4],
                "service_type": row[5],
                "current_level": row[6],
                "target_level": row[7],
                "current_percent": row[8],
                "target_percent": row[9],
                "platform": row[10],
                "price": row[11],
                "status": row[12],
                "urgent": bool(row[13]),
                "live_stream": bool(row[14]),
                "created_at": row[17],
                "updated_at": row[18]
            }

            # Get messages
            cursor.execute("SELECT * FROM messages WHERE order_id = ? ORDER BY timestamp", (order_id,))
            messages = []
            for msg in cursor.fetchall():
                messages.append({
                    "id": msg[0],
                    "type": msg[2],
                    "original": msg[3],
                    "translated": msg[4],
                    "timestamp": msg[9]
                })

            order['messages'] = messages
            conn.close()

            self._send_json(order)
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_update_status(self, body):
        """Update order status"""
        try:
            data = json.loads(body)
            order_id = data.get('order_id')
            new_status = data.get('status')

            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, datetime.now().isoformat(), order_id)
            )
            conn.commit()
            conn.close()

            self._send_json({"success": True, "message": "Status updated"})
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_assign(self, body):
        """Assign order to worker"""
        try:
            data = json.loads(body)
            order_id = data.get('order_id')
            worker_id = data.get('worker_id')
            worker_name = data.get('worker_name')

            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET worker_id = ?, worker_name = ?, status = 'assigned', updated_at = ? WHERE id = ?",
                (worker_id, worker_name, datetime.now().isoformat(), order_id)
            )
            conn.commit()
            conn.close()

            self._send_json({"success": True, "message": "Worker assigned"})
        except Exception as e:
            self._send_error(500, str(e))


def run_server(port=8081):
    """Run the monitoring server"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, OrderMonitorHandler)
    logger.info(f"📊 Order Monitor running at http://localhost:{port}")
    logger.info("Press Ctrl+C to stop")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()

