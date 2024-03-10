import uvicorn
from asgiref.wsgi import WsgiToAsgi

from stockcount import create_app

app = create_app()
asgi_app = WsgiToAsgi(app)

if __name__ == "__main__":
    uvicorn.run(asgi_app, host="0.0.0.0", port=5001)
