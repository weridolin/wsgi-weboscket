from flask import Flask
from flask_.middleware import SimpleWebsocketMiddleWare



def on_message(ws, message):
    print('Received message: ' + message)

def on_connect(ws):
    print('Connected')

def on_error(ws, error):
    print('Error: ' + error)

def on_ping(ws):
    print('Ping')

def on_pong(ws):
    print('Pong')

def on_close(ws):
    print('Closed') 



def create_app():
    app = Flask(__name__)
    app.wsgi_app = SimpleWebsocketMiddleWare(
        app.wsgi_app,
        on_pong=on_pong,
        on_ping=on_ping,
        on_error=on_error,
        on_connect=on_connect,
        on_message=on_message,
        on_close=on_close
    )
    return app



app = create_app()

@app.route('/test')
def test():
    return 'Hello World'
