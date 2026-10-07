#!/usr/bin/env python3
"""
Demo Application - Simple REST API

A minimal Flask application that serves as a learning tool for platform
deployment and operational concerns.

Features:
- REST API with health check endpoint
- CRUD operations for managing items
- JSON request/response handling
- Error handling and validation

This app is designed to be deployed to Docker, Kubernetes, or run locally
for evaluating deployment and platform UX.
"""

import instrumentation  # noqa: F401, I001 — must be first: initialises the OTel SDK before Flask loads

import json
import time
import uuid
from typing import Any
from datetime import UTC, datetime

from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode

tracer = trace.get_tracer("demo-app", "1.0.0")
meter  = metrics.get_meter("demo-app", "1.0.0")

# ── Custom metrics ─────────────────────────────────────────────────────────────
# Only functional when instrumentation.py is imported first and a
# PeriodicExportingMetricReader is registered — same gotcha as the Node.js version.
request_counter  = meter.create_counter(
    "http_requests_total",
    description="Total number of HTTP requests",
)
request_duration = meter.create_histogram(
    "http_request_duration_ms",
    description="HTTP request duration in milliseconds",
    unit="ms",
)


class InMemoryStore:
    """Simple in-memory data store for demo purposes."""

    def __init__(self):
        """Initialize empty item storage."""
        self.items: dict[str, dict[str, Any]] = {}

    def create(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new item."""
        item_id = str(uuid.uuid4())[:8]
        item = {
            "id": item_id,
            "name": name,
            "description": description,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.items[item_id] = item
        return item

    def read(self, item_id: str) -> dict[str, Any] | None:
        """Read a single item by ID."""
        return self.items.get(item_id)

    def list_all(self) -> list[dict[str, Any]]:
        """List all items."""
        return list(self.items.values())

    def update(self, item_id: str, **kwargs) -> dict[str, Any] | None:
        """Update an item's fields."""
        if item_id not in self.items:
            return None
        self.items[item_id].update(kwargs)
        return self.items[item_id]

    def delete(self, item_id: str) -> bool:
        """Delete an item."""
        if item_id in self.items:
            del self.items[item_id]
            return True
        return False


# Global store instance
store = InMemoryStore()


def parse_json_body(body: str) -> dict[str, Any]:
    """
    Parse JSON request body.

    Args:
        body: Raw request body string

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If JSON is invalid
    """
    if not body:
        raise ValueError("Empty request body")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")


def create_response(
    data: Any = None, status_code: int = 200, error: str | None = None
) -> tuple[str, int]:
    """
    Create a JSON response.

    Args:
        data: Response payload
        status_code: HTTP status code
        error: Error message if applicable

    Returns:
        Tuple of (JSON response body, status code)
    """
    if error:
        response = {"error": error, "status": status_code}
    else:
        response = {"data": data, "status": status_code}

    return json.dumps(response) + "\n", status_code


class Application:
    """Simple WSGI-compatible web application."""

    def __call__(self, environ: dict[str, Any], start_response) -> list[str]:
        """
        WSGI application entry point.

        Args:
            environ: WSGI environment dictionary
            start_response: WSGI callback function

        Returns:
            Response body as list of strings
        """
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/").lower()
        content_length = int(environ.get("CONTENT_LENGTH", 0))
        body = environ.get("wsgi.input").read(content_length).decode("utf-8") if content_length > 0 else ""

        try:
            # Health check endpoint
            if path == "/health" and method == "GET":
                response, status = create_response({"status": "healthy"}, 200)

            # List items
            elif path == "/items" and method == "GET":
                items = store.list_all()
                response, status = create_response(items, 200)

            # Create item
            elif path == "/items" and method == "POST":
                try:
                    data = parse_json_body(body)
                    name = data.get("name", "")
                    if not name:
                        response, status = create_response(
                            status_code=400, error="Field 'name' is required"
                        )
                    else:
                        item = store.create(name, data.get("description", ""))
                        response, status = create_response(item, 201)
                except ValueError as e:
                    response, status = create_response(status_code=400, error=str(e))

            # Get item by ID
            elif path.startswith("/items/") and method == "GET":
                item_id = path.split("/")[-1]
                item = store.read(item_id)
                if item:
                    response, status = create_response(item, 200)
                else:
                    response, status = create_response(
                        status_code=404, error=f"Item {item_id} not found"
                    )

            # Update item
            elif path.startswith("/items/") and method == "PUT":
                item_id = path.split("/")[-1]
                try:
                    data = parse_json_body(body)
                    item = store.update(item_id, **data)
                    if item:
                        response, status = create_response(item, 200)
                    else:
                        response, status = create_response(
                            status_code=404, error=f"Item {item_id} not found"
                        )
                except ValueError as e:
                    response, status = create_response(status_code=400, error=str(e))

            # Delete item
            elif path.startswith("/items/") and method == "DELETE":
                item_id = path.split("/")[-1]
                if store.delete(item_id):
                    response, status = create_response({"deleted": item_id}, 200)
                else:
                    response, status = create_response(
                        status_code=404, error=f"Item {item_id} not found"
                    )

            # 404 Not Found
            else:
                response, status = create_response(
                    status_code=404, error=f"Endpoint {path} not found"
                )

        except Exception as e:  # noqa: BLE001 — top-level WSGI handler must return a 500
            response, status = create_response(
                status_code=500, error=f"Internal server error: {e}"
            )

        # Send response
        start_response(f"{status} OK", [("Content-Type", "application/json")])
        return [response.encode("utf-8")]


def create_flask_app():
    """
    Create a Flask-based application (optional, more user-friendly).

    Returns Flask app if available, otherwise raw WSGI app.
    """
    try:
        from flask import Flask, jsonify, request
        from opentelemetry.instrumentation.flask import FlaskInstrumentor

        app = Flask(__name__)

        @app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "healthy"}), 200

        @app.route("/items", methods=["GET"])
        def list_items():
            start = time.time()
            # startActiveSpan equivalent — span is the active span; any child span
            # started inside this block is automatically parented to it.
            with tracer.start_as_current_span("store.list_all") as span:
                items = store.list_all()
                span.set_attribute("app.items.count", len(items))
            request_counter.add(1, {"endpoint": "/items", "method": "GET", "status": "200"})
            request_duration.record((time.time() - start) * 1000, {"endpoint": "/items"})
            return jsonify(items), 200

        @app.route("/items", methods=["POST"])
        def create_item():
            start = time.time()
            data = request.get_json() or {}
            name = data.get("name")
            if not name:
                request_counter.add(1, {"endpoint": "/items", "method": "POST", "status": "400"})
                request_duration.record((time.time() - start) * 1000, {"endpoint": "/items"})
                return jsonify({"error": "Field 'name' is required"}), 400

            with tracer.start_as_current_span("store.create") as span:
                span.set_attribute("app.item.name", name)
                # Nested child span — auto-parented because store.create is the active span.
                with tracer.start_as_current_span("store.write") as child:
                    child.set_attribute("db.system", "in-memory")
                    item = store.create(name, data.get("description", ""))
                span.set_attribute("app.item.id", item["id"])
                span.set_status(StatusCode.OK)

            request_counter.add(1, {"endpoint": "/items", "method": "POST", "status": "201"})
            request_duration.record((time.time() - start) * 1000, {"endpoint": "/items"})
            return jsonify(item), 201

        @app.route("/items/<item_id>", methods=["GET"])
        def get_item(item_id):
            start = time.time()
            with tracer.start_as_current_span("store.read") as span:
                span.set_attribute("app.item.id", item_id)
                item = store.read(item_id)
                if item:
                    span.set_status(StatusCode.OK)
                    request_counter.add(1, {"endpoint": "/items/{id}", "method": "GET", "status": "200"})
                    request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
                    return jsonify(item), 200
                span.set_status(StatusCode.ERROR, f"Item {item_id} not found")
            request_counter.add(1, {"endpoint": "/items/{id}", "method": "GET", "status": "404"})
            request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
            return jsonify({"error": f"Item {item_id} not found"}), 404

        @app.route("/items/<item_id>", methods=["PUT"])
        def update_item(item_id):
            start = time.time()
            data = request.get_json() or {}
            with tracer.start_as_current_span("store.update") as span:
                span.set_attribute("app.item.id", item_id)
                item = store.update(item_id, **data)
                if item:
                    span.set_status(StatusCode.OK)
                    request_counter.add(1, {"endpoint": "/items/{id}", "method": "PUT", "status": "200"})
                    request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
                    return jsonify(item), 200
                span.set_status(StatusCode.ERROR, f"Item {item_id} not found")
            request_counter.add(1, {"endpoint": "/items/{id}", "method": "PUT", "status": "404"})
            request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
            return jsonify({"error": f"Item {item_id} not found"}), 404

        @app.route("/items/<item_id>", methods=["DELETE"])
        def delete_item(item_id):
            start = time.time()
            with tracer.start_as_current_span("store.delete") as span:
                span.set_attribute("app.item.id", item_id)
                if store.delete(item_id):
                    span.set_status(StatusCode.OK)
                    request_counter.add(1, {"endpoint": "/items/{id}", "method": "DELETE", "status": "200"})
                    request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
                    return jsonify({"deleted": item_id}), 200
                span.set_status(StatusCode.ERROR, f"Item {item_id} not found")
            request_counter.add(1, {"endpoint": "/items/{id}", "method": "DELETE", "status": "404"})
            request_duration.record((time.time() - start) * 1000, {"endpoint": "/items/{id}"})
            return jsonify({"error": f"Item {item_id} not found"}), 404

        # Auto-instruments all Flask routes — creates a span per HTTP request
        # and propagates trace context from incoming headers.
        FlaskInstrumentor().instrument_app(app)

        return app

    except ImportError:
        return None


# Module-level Flask app for Flask CLI discovery (FLASK_APP=app.py)
app = create_flask_app()

if __name__ == "__main__":
    if app:
        print("Starting Flask application on http://0.0.0.0:5000")
        app.run(host="0.0.0.0", port=5000, debug=False)
    else:
        print("Flask not installed. Install with: pip install flask")
        print("Attempting to run with wsgiref (WSGI reference server)...")
        from wsgiref.simple_server import make_server

        wsgi_app = Application()
        server = make_server("0.0.0.0", 5000, wsgi_app)
        print("Starting application on http://0.0.0.0:5000")
        server.serve_forever()
