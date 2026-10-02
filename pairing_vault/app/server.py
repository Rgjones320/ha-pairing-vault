"""HTTP API and static UI, served behind Home Assistant Ingress."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from .db import Store, ValidationError
from .payloads import PayloadError, decode

STATIC_DIR = Path(__file__).parent / "static"

# Everything the UI needs is served from this add-on; nothing loads from
# elsewhere. blob: and data: cover photos being scanned and the camera preview.
CSP = "; ".join((
    "default-src 'self'",
    "img-src 'self' blob: data:",
    "media-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'self'",
))


def create_app(data_dir: str | None = None) -> Flask:
    data_dir = data_dir or os.environ.get("DATA_DIR", "./data")
    app = Flask(__name__, static_folder=None)
    # Device entries are a few KB at most.
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    store = Store(Path(data_dir) / "pairing_vault.db")
    app.config["STORE"] = store
    # In the add-on only the Supervisor's Ingress proxy may talk to us.
    allowed = {a.strip() for a in os.environ.get("ALLOWED_CLIENTS", "").split(",") if a.strip()}

    @app.before_request
    def _only_ingress():
        if allowed and request.remote_addr not in allowed:
            abort(403)

    @app.before_request
    def _same_origin_writes():
        # The API only takes JSON, which a cross-site form can't send, but a
        # page on another site shouldn't be able to change data either way.
        site = request.headers.get("Sec-Fetch-Site")
        if request.method not in ("GET", "HEAD", "OPTIONS") and site not in (None, "same-origin", "none"):
            abort(403)

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.errorhandler(ValidationError)
    def _invalid(err: ValidationError):
        return jsonify(error="invalid", fields=err.errors), 400

    @app.errorhandler(404)
    def _not_found(_err):
        return jsonify(error="not found"), 404

    @app.get("/")
    def index():
        resp = send_from_directory(STATIC_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/static/<path:name>")
    def static_file(name: str):
        return send_from_directory(STATIC_DIR, name)

    @app.get("/api/devices")
    def list_devices():
        return jsonify(store.list(request.args.get("q", "").strip()))

    @app.post("/api/devices")
    def create_device():
        return jsonify(store.create(_json_body())), 201

    @app.get("/api/devices/<int:device_id>")
    def get_device(device_id: int):
        return jsonify(store.get(device_id) or abort(404))

    @app.put("/api/devices/<int:device_id>")
    def update_device(device_id: int):
        return jsonify(store.update(device_id, _json_body()) or abort(404))

    @app.delete("/api/devices/<int:device_id>")
    def delete_device(device_id: int):
        if not store.delete(device_id):
            abort(404)
        return "", 204

    @app.post("/api/decode")
    def decode_payload():
        payload = _json_body().get("payload")
        if not isinstance(payload, str) or not payload.strip():
            raise ValidationError({"payload": "is required"})
        try:
            return jsonify(decode(payload))
        except PayloadError as err:
            return jsonify(error=str(err)), 400

    return app


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError({"body": "must be a JSON object"})
    return body
