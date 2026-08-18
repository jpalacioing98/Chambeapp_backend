"""Entrypoint de la aplicación (SocketIO)."""

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    # socketio.run habilita el servidor WS; mantiene compat con Flask dev.
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
