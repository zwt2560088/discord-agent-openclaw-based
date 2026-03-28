"""
NBA2k26 Pricing Management Server
Web interface for managing reputation boosting pricing
"""
import json
import logging
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))


class PricingAPIHandler(SimpleHTTPRequestHandler):
    """HTTP handler for pricing API"""

    def __init__(self, *args, **kwargs):
        self.pricing_dir = BASE_DIR
        super().__init__(*args, directory=self.pricing_dir, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/levels':
            self._handle_get_levels()
        elif path == '/api/config':
            self._handle_get_config()
        elif path == '/':
            self.path = '/index.html'
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        if path == '/api/calculate':
            self._handle_calculate(body)
        elif path == '/api/update-config':
            self._handle_update_config(body)
        elif path == '/api/add-level':
            self._handle_add_level(body)
        elif path == '/api/update-level':
            self._handle_update_level(body)
        elif path == '/api/delete-level':
            self._handle_delete_level(body)
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

    def _handle_get_levels(self):
        """Get all levels"""
        try:
            from reputation_calculator import get_calculator
            calc = get_calculator()
            self._send_json({"levels": calc.get_all_levels()})
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_get_config(self):
        """Get full config"""
        try:
            config_path = os.path.join(BASE_DIR, "level_config.json")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self._send_json(config)
        except Exception as e:
            self._send_error(500, str(e))

    def _handle_calculate(self, body):
        """Calculate price"""
        try:
            data = json.loads(body)
            from reputation_calculator import get_calculator
            calc = get_calculator()

            result = calc.calculate_price(
                current_level=data.get('current_level'),
                current_percent=float(data.get('current_percent', 0)),
                target_level=data.get('target_level'),
                target_percent=float(data.get('target_percent', 0)),
                platform=data.get('platform', 'PC'),
                urgent=data.get('urgent', False),
                live_stream=data.get('live_stream', False),
                bulk_count=int(data.get('bulk_count', 1))
            )

            self._send_json({
                "success": True,
                "result": {
                    "total_reputation": result.total_reputation,
                    "base_price": result.base_price,
                    "urgent_fee": result.urgent_fee,
                    "live_stream_fee": result.live_stream_fee,
                    "platform_multiplier": result.platform_multiplier,
                    "bulk_discount": result.bulk_discount,
                    "final_price": result.final_price,
                    "level_breakdown": result.level_breakdown
                }
            })
        except Exception as e:
            self._send_error(400, str(e))

    def _handle_update_config(self, body):
        """Update config"""
        try:
            data = json.loads(body)
            from reputation_calculator import get_calculator
            calc = get_calculator()

            if calc.update_config(data):
                self._send_json({"success": True, "message": "Config updated"})
            else:
                self._send_error(500, "Failed to update config")
        except Exception as e:
            self._send_error(400, str(e))

    def _handle_add_level(self, body):
        """Add new level"""
        try:
            data = json.loads(body)
            from reputation_calculator import get_calculator
            calc = get_calculator()

            if calc.add_level(data):
                self._send_json({"success": True, "message": "Level added"})
            else:
                self._send_error(500, "Failed to add level")
        except Exception as e:
            self._send_error(400, str(e))

    def _handle_update_level(self, body):
        """Update level"""
        try:
            data = json.loads(body)
            from reputation_calculator import get_calculator
            calc = get_calculator()

            level_id = data.pop('id', None)
            if not level_id:
                self._send_error(400, "Level ID required")
                return

            if calc.update_level(level_id, data):
                self._send_json({"success": True, "message": "Level updated"})
            else:
                self._send_error(500, "Failed to update level")
        except Exception as e:
            self._send_error(400, str(e))

    def _handle_delete_level(self, body):
        """Delete level"""
        try:
            data = json.loads(body)
            from reputation_calculator import get_calculator
            calc = get_calculator()

            level_id = data.get('id')
            if not level_id:
                self._send_error(400, "Level ID required")
                return

            if calc.delete_level(level_id):
                self._send_json({"success": True, "message": "Level deleted"})
            else:
                self._send_error(500, "Failed to delete level")
        except Exception as e:
            self._send_error(400, str(e))


def run_server(port=8080):
    """Run the pricing server"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, PricingAPIHandler)
    logger.info(f"🎮 NBA2K Pricing Server running at http://localhost:{port}")
    logger.info("Press Ctrl+C to stop")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()

