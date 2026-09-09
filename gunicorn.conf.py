import os

port = os.environ.get("PORT", "").strip()
if not port:
    port = "8000"

bind = f"0.0.0.0:{port}"
workers = 2
timeout = 120
accesslog = "-"
errorlog = "-"
