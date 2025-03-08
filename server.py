from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import os
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_clé_secrète'  # À changer
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/message', methods=['POST'])
def receive_message():
    if request.json:
        message_type = request.json.get('type', 'info')
        content = request.json.get('content', '')
        
        socketio.emit('new_message', {
            'type': message_type,
            'content': content,
            'timestamp': time.strftime('%H:%M:%S')
        })
        
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@socketio.on('connect')
def handle_connect():
    print("Client connecté")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)