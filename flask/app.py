from flask import Flask
from .middleware import WebsocketMiddleWare



def create_app():
    app = Flask(__name__)
    app.wsgi_app = WebsocketMiddleWare(app.wsgi_app)
    return app