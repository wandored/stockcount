import uvicorn
from asgiref.wsgi import WsgiToAsgi
import logging

from stockcount import create_app

app = create_app()
asgi_app = WsgiToAsgi(app)
asgi_app.logger = logging.getLogger("uvicorn.error")
asgi_app.logger.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

if __name__ == "__main__":
    uvicorn.run(asgi_app, host="0.0.0.0", port=5001)
