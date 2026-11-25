"""Local dev server: serves the frontend AND runs the real Lambda handler against an
in-memory mocked DynamoDB (moto). No AWS account or network needed.

    pip install -r backend/requirements-dev.txt
    python backend/dev_server.py          # then open http://127.0.0.1:8787
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
os.environ.update(AWS_DEFAULT_REGION="ap-south-1", AWS_ACCESS_KEY_ID="local", AWS_SECRET_ACCESS_KEY="local",
                  TABLE_NAME="campuspilot-local", AWS_SESSION_TOKEN="local")

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

FRONTEND = os.path.realpath(os.path.join(HERE, "..", "frontend"))
PORT = int(os.environ.get("PORT", "8787"))
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        # Same policy family that deploy.sh applies on Amplify (there connect-src also lists the API address)
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
                                                    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method, url):
        import app
        length = int(self.headers.get("Content-Length") or 0)
        event = {"requestContext": {"http": {"method": method}}, "rawPath": url.path,
                 "queryStringParameters": {k: v[0] for k, v in parse_qs(url.query).items()} or None,
                 "body": self.rfile.read(length).decode() if length else None}
        r = app.handler(event, None)
        self._send(r["statusCode"], r["body"])

    def do_OPTIONS(self):
        self._send(204, b"")

    def _is_api(self, method, path):
        import app
        return f"{method} {path}" in app.ROUTES

    def do_POST(self):
        url = urlparse(self.path)
        self._api("POST", url) if self._is_api("POST", url.path) else self._send(404, '{"error":"Not found"}')

    def do_GET(self):
        url = urlparse(self.path)
        if self._is_api("GET", url.path):
            return self._api("GET", url)
        if url.path == "/config.js":  # point the UI at this server instead of AWS
            return self._send(200, f'window.CAMPUSPILOT_API = "http://127.0.0.1:{PORT}";', "text/javascript")
        rel = "index.html" if url.path == "/" else url.path.lstrip("/")
        full = os.path.realpath(os.path.join(FRONTEND, rel))
        if not full.startswith(FRONTEND + os.sep) or not os.path.isfile(full):
            return self._send(404, "Not found", "text/plain")
        self._send(200, open(full, "rb").read(), TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def log_message(self, fmt, *args):
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


if __name__ == "__main__":
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=os.environ["TABLE_NAME"], BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}])
        print(f"CampusPilot dev server: http://127.0.0.1:{PORT}  (data is in memory and resets on restart)")
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
