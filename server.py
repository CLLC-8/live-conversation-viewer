from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import os
import time
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_clé_secrète'
socketio = SocketIO(app, cors_allowed_origins="*")

# Récupérer l'URL de la base de données depuis les variables d'environnement
DATABASE_URL = os.environ.get('DATABASE_URL')

# Initialisation de la base de données - Version améliorée
def init_db():
    try:
        print("Tentative de connexion à la base de données...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print("Connexion réussie, création de la table messages...")
        
        cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP,
            type VARCHAR(50),
            content TEXT
        )
        ''')
        conn.commit()
        
        # Vérifier que la table existe réellement
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'messages')")
        table_exists = cur.fetchone()[0]
        
        if table_exists:
            print("Table 'messages' créée avec succès!")
        else:
            print("ERREUR: La table 'messages' n'a pas été créée!")
            
        conn.close()
    except Exception as e:
        print(f"ERREUR d'initialisation de la base de données: {e}")

# Fonction pour ajouter un message à la base de données - Version corrigée
def add_message_to_db(message_type, content):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # S'assurer que la table existe
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'messages')")
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("La table n'existe pas, tentative de création...")
            cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                type VARCHAR(50),
                content TEXT
            )
            ''')
            conn.commit()
        
        # Insérer le message
        cur.execute(
            "INSERT INTO messages (timestamp, type, content) VALUES (%s, %s, %s)",
            (datetime.now(), message_type, content)
        )
        conn.commit()
        print(f"Message ajouté à la base de données: {message_type} - {content[:20]}...")
        conn.close()
        return True
    except Exception as e:
        print(f"ERREUR lors de l'ajout du message: {e}")
        return False

# Fonction pour récupérer l'historique des messages - Version corrigée
def get_message_history(limit=100):
    try:
        messages = []
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Vérifier que la table existe
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'messages')")
        table_exists = cur.fetchone()[0]
        
        if table_exists:
            cur.execute(
                "SELECT timestamp, type, content FROM messages ORDER BY timestamp ASC LIMIT %s",
                (limit,)
            )
            messages = [dict(row) for row in cur.fetchall()]
            print(f"Récupération de {len(messages)} messages de l'historique")
        else:
            print("La table 'messages' n'existe pas encore!")
            
        conn.close()
        return messages
    except Exception as e:
        print(f"ERREUR lors de la récupération de l'historique: {e}")
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

# Initialiser la base de données au démarrage
print("Démarrage de l'application...")
init_db()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
