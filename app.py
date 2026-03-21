import os

from flask import Flask, render_template
from loguru import logger

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)
