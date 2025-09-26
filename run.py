import uvicorn
from asgiref.wsgi import WsgiToAsgi
import logging
import sys

from stockcount import create_app

app = create_app()
asgi_app = WsgiToAsgi(app)
# asgi_app.logger = logging.getLogger("uvicorn.error")
# asgi_app.logger.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,  # show DEBUG, INFO, WARNING, ERROR, CRITICAL
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.INFO)

if __name__ == "__main__":
    uvicorn.run(asgi_app, host="0.0.0.0", port=5001, log_level="debug")
