#!/usr/bin/env python3
"""
CORS-free Proxy Server

Usage:
    # Development
    python proxy.py [--port PORT]

    # Production (Gunicorn)
    gunicorn proxy:application -b 0.0.0.0:8080 -w 4

Example requests:
    GET http://localhost:8080/proxy?url=https://api.example.com/data
    GET http://localhost:8080/proxy/https://api.example.com/data
"""

import argparse
import urllib.request
import urllib.parse
import urllib.error
from flask import Flask, request, Response, jsonify

app = Flask(__name__)
application = app  # WSGI standard

# Allowed origins (only these can use the proxy)
ALLOWED_ORIGINS = [
    "https://pltchuong.github.io",
    "http://localhost",
    "http://127.0.0.1",
]


def is_origin_allowed(origin: str) -> bool:
    """Check if the request origin is allowed."""
    if not origin:
        return False
    for allowed in ALLOWED_ORIGINS:
        # Exact match, path match, or port match (e.g. localhost:3000)
        if origin == allowed or origin.startswith(allowed + "/") or origin.startswith(allowed + ":"):
            return True
    return False


def get_target_url(path: str, query_url: str = None) -> str | None:
    """Extract target URL from path or query parameter."""
    if query_url:
        return query_url
    if path.startswith("/proxy/"):
        return path[7:]
    return None


def get_forward_headers() -> dict:
    """Get headers to forward to the target server."""
    headers = {}
    for header in ["Content-Type", "Accept", "Authorization", "User-Agent", "X-Requested-With"]:
        value = request.headers.get(header)
        if value:
            headers[header] = value
    if "User-Agent" not in headers:
        headers["User-Agent"] = "CORS-Proxy/1.0"
    return headers


@app.after_request
def after_request(response: Response) -> Response:
    """Add CORS headers to all responses."""
    origin = request.headers.get("Origin", "")
    if is_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
        response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.route("/proxy", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.route("/proxy/<path:url>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def proxy(url: str = None):
    """Proxy endpoint."""
    origin = request.headers.get("Origin", "")
    
    # Allow preflight but still check origin for actual requests
    if request.method == "OPTIONS":
        if is_origin_allowed(origin):
            return Response(status=200)
        return Response(status=403)

    # Block requests from non-allowed origins
    if not is_origin_allowed(origin):
        return jsonify({"error": "Forbidden", "message": "Origin not allowed"}), 403

    target_url = get_target_url(request.path, request.args.get("url"))

    if not target_url:
        return jsonify({
            "error": "Missing target URL",
            "usage": "/proxy?url=<encoded_url> or /proxy/<url>",
            "example": "/proxy?url=https://api.example.com/data"
        }), 400

    try:
        parsed_url = urllib.parse.urlparse(target_url)
        if parsed_url.scheme not in ("http", "https"):
            return jsonify({"error": "URL must start with http:// or https://"}), 400
    except Exception:
        return jsonify({"error": "Invalid URL format"}), 400

    body = request.get_data() if request.method in ("POST", "PUT", "PATCH") else None

    try:
        req = urllib.request.Request(
            target_url,
            data=body,
            headers=get_forward_headers(),
            method=request.method
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            return Response(
                response.read(),
                status=response.status,
                content_type=response.headers.get("Content-Type", "application/octet-stream")
            )

    except urllib.error.HTTPError as e:
        return Response(
            e.read() if e.fp else b"",
            status=e.code,
            content_type=e.headers.get("Content-Type", "application/octet-stream")
        )

    except urllib.error.URLError as e:
        return jsonify({"error": "Failed to connect", "message": str(e.reason)}), 502

    except Exception as e:
        return jsonify({"error": "Proxy error", "message": str(e)}), 500


@app.route("/")
def index():
    """Health check."""
    return jsonify({"status": "ok", "usage": "/proxy?url=<encoded_url>"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CORS-free Proxy Server")
    parser.add_argument("--port", "-p", type=int, default=8080)
    args = parser.parse_args()

    print(f"\n  CORS Proxy running at http://localhost:{args.port}")
    print(f"  Usage: /proxy?url=<encoded_url>\n")

    app.run(host="0.0.0.0", port=args.port, debug=True)
