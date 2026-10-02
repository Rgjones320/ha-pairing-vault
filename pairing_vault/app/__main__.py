import logging
import os

from waitress import serve

from .server import create_app

logging.basicConfig(level=logging.INFO)
serve(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8099")))
