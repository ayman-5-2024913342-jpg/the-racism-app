"""Production ASGI server: Gunicorn managing Uvicorn workers.

Behind a reverse proxy / platform router, set FORWARDED_ALLOW_IPS to the proxy's address so client IPs
and the https scheme are trusted only from it.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"  # request lines only (no bodies, no images)
errorlog = "-"
