#!/bin/bash
# ============================================
# Worker Entrypoint
# Runs Celery worker + lightweight HTTP health server
# Cloud Run requires a listening HTTP port
# ============================================

set -e

PORT="${PORT:-8080}"

# Start a simple health check HTTP server in the background
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading, os

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{\"status\": \"healthy\", \"service\": \"celery-worker\"}')
    def log_message(self, format, *args):
        pass  # Suppress access logs

server = HTTPServer(('0.0.0.0', int(os.environ.get('PORT', $PORT))), HealthHandler)
print(f'Health check server listening on port {os.environ.get(\"PORT\", $PORT)}')
server.serve_forever()
" &

# Start Celery worker in the foreground
exec celery -A app.workers.celery_worker:celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --max-tasks-per-child=50 \
    -Q paper_processing,embedding,ai_tasks,celery
