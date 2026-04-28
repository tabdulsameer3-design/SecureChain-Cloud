from flask_socketio import SocketIO
from socket_events import register_socket_events
from app import create_app

app = create_app()
socketio = SocketIO(app, cors_allowed_origins="*")
register_socket_events(socketio)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
