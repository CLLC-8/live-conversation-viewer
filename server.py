from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import os
import time
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_clé_secrète'  # À changer pour une vraie clé
socketio = SocketIO(app, cors_allowed_origins="*")

# Récupérer l'URL de la base de données depuis les variables d'environnement
DATABASE_URL = os.environ.get('DATABASE_URL')

# Initialisation de la base de données
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP,
            type VARCHAR(50),
            content TEXT
        )
        ''')
        conn.commit()
        conn.close()
        print("Base de données initialisée avec succès")
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données: {e}")

# Fonction pour ajouter un message à la base de données
def add_message_to_db(message_type, content):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (timestamp, type, content) VALUES (%s, %s, %s)",
            (datetime.now(), message_type, content)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erreur lors de l'ajout du message à la base de données: {e}")
        return False

# Fonction pour récupérer l'historique des messages
def get_message_history(limit=100):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute(
            "SELECT timestamp, type, content FROM messages ORDER BY timestamp DESC LIMIT %s",
            (limit,)
        )
        messages = [dict(row) for row in cur.fetchall()]
        conn.close()
        return messages[::-1]  # Inverser pour ordre chronologique
    except Exception as e:
        print(f"Erreur lors de la récupération de l'historique des messages: {e}")
        return []

@app.route('/')
def index():
    history = get_message_history()
    return render_template('index.html', history=history)

@app.route('/api/message', methods=['POST'])
def receive_message():
    if request.json:
        message_type = request.json.get('type', 'info')
        content = request.json.get('content', '')
        
        # Stocker dans la base de données
        add_message_to_db(message_type, content)
        
        # Émettre aux clients connectés
        socketio.emit('new_message', {
            'type': message_type,
            'content': content,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
        
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@socketio.on('connect')
def handle_connect():
    print("Client connecté")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
