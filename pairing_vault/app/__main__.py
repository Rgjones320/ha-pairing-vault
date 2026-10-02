import logging
import os

from waitress import serve

from .server import create_app

logging.basicConfig(level=logging.INFO)
# Only Home Assistant's Ingress proxy may connect unless told otherwise; set
# ALLOWED_CLIENTS to an empty string to accept any client (local testing only).
os.environ.setdefault("ALLOWED_CLIENTS", "172.30.32.2")
serve(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8099")))
