from flask import Flask, render_template, jsonify, request, url_for, session, redirect, flash
from flask_socketio import SocketIO
import csv
import io
from flask import Response
import os
import time
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import traceback
from functools import wraps

from datetime import datetime

@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'une_clé_secrète_très_longue_et_aléatoire')
socketio = SocketIO(app, cors_allowed_origins="*")

# Récupérer l'URL de la base de données depuis les variables d'environnement
DATABASE_URL = os.environ.get('DATABASE_URL')

# Définir un mot de passe pour l'admin (idéalement, stockez-le dans une variable d'environnement)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'oracle2025')  # mot de passe par défaut si non défini

# Fonction décorateur pour protéger les routes admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Initialisation de la base de données
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

# Fonction pour ajouter un message à la base de données
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

# Fonction pour récupérer l'historique des messages
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

# Route principale pour afficher le chat
@app.route('/')
def index():
    history = get_message_history()
    return render_template('index.html', history=history, active_page='index')

# Route API pour recevoir les messages
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

# Gestion des connexions Socket.IO
@socketio.on('connect')
def handle_connect():
    print("Client connecté")

# Route de login admin
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    next_url = request.args.get('next', url_for('admin'))
    
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(next_url)
        else:
            error = 'Mot de passe incorrect'
    
    return render_template('admin_login.html', error=error)

# Route déconnexion
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# Route admin protégée
@app.route('/admin')
@admin_required
def admin():
    debug_info = ""
    try:
        # Vérifier que la connexion à la base de données fonctionne
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Vérifier si la table messages existe
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'messages')")
        table_exists = cur.fetchone()[0]
        debug_info += f"Table 'messages' existe: {table_exists}\n"
        
        if not table_exists:
            # Créer la table si elle n'existe pas
            cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                type VARCHAR(50),
                content TEXT
            )
            ''')
            conn.commit()
            debug_info += "Table 'messages' créée\n"
            
            # Vérifier à nouveau
            cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'messages')")
            table_exists = cur.fetchone()[0]
            debug_info += f"Table 'messages' existe après création: {table_exists}\n"
            
            # Si la table n'existe toujours pas
            if not table_exists:
                conn.close()
                return render_template('admin.html', messages=[], error="Impossible de créer la table 'messages'", debug_info=debug_info)
        
        # Vérifier les colonnes de la table
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'")
        columns = [col[0] for col in cur.fetchall()]
        debug_info += f"Colonnes dans la table 'messages': {', '.join(columns)}\n"
        
        # Si la structure est correcte, récupérer les messages
        # Adapter la requête en fonction des colonnes disponibles
        if 'id' in columns:
            query = "SELECT id, timestamp, type, content FROM messages ORDER BY timestamp DESC"
        else:
            query = "SELECT timestamp, type, content FROM messages ORDER BY timestamp DESC"
        
        debug_info += f"Requête utilisée: {query}\n"
        
        cur.execute(query)
        
        # Utiliser DictCursor pour les résultats
        messages = []
        column_names = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        
        for row in rows:
            message = {}
            for i, col_name in enumerate(column_names):
                message[col_name] = row[i]
            messages.append(message)
        
        debug_info += f"Nombre de messages récupérés: {len(messages)}\n"
        
        # S'il y a des messages, afficher un exemple
        if messages and len(messages) > 0:
            debug_info += f"Exemple de message: {str(messages[0])}\n"
        
        conn.close()
        return render_template('admin.html', messages=messages, debug_info=debug_info)
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        debug_info += f"Exception: {str(e)}\n\nTraceback:\n{error_traceback}"
        return render_template('admin.html', messages=[], error=f"Erreur: {str(e)}", debug_info=debug_info)

# Route pour supprimer un message
@app.route('/admin/delete/<int:message_id>', methods=['POST'])
@admin_required
def delete_message(message_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Vérifier si le message existe
        cur.execute("SELECT EXISTS(SELECT 1 FROM messages WHERE id = %s)", (message_id,))
        message_exists = cur.fetchone()[0]
        
        if not message_exists:
            conn.close()
            return jsonify({"status": "error", "message": f"Message avec ID {message_id} introuvable"}), 404
        
        # Supprimer le message
        cur.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Erreur lors de la suppression du message {message_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Route pour mettre à jour un message
@app.route('/admin/update/<int:message_id>', methods=['POST'])
@admin_required
def update_message(message_id):
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Aucune donnée reçue"}), 400
            
        type_value = data.get('type')
        content = data.get('content')
        
        if not type_value or not content:
            return jsonify({"status": "error", "message": "Type et contenu requis"}), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Vérifier si le message existe
        cur.execute("SELECT EXISTS(SELECT 1 FROM messages WHERE id = %s)", (message_id,))
        message_exists = cur.fetchone()[0]
        
        if not message_exists:
            conn.close()
            return jsonify({"status": "error", "message": f"Message avec ID {message_id} introuvable"}), 404
        
        # Mettre à jour le message
        cur.execute(
            "UPDATE messages SET type = %s, content = %s WHERE id = %s",
            (type_value, content, message_id)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Erreur lors de la mise à jour du message {message_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Route pour supprimer tous les messages
@app.route('/admin/clear_all', methods=['POST'])
@admin_required
def clear_all_messages():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("DELETE FROM messages")
        rows_deleted = cur.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "deleted": rows_deleted}), 200
    except Exception as e:
        print(f"Erreur lors de la suppression de tous les messages: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Route pour exporter les données en CSV
@app.route('/export')
@admin_required
def export_data():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Déterminer les colonnes disponibles
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'")
        columns = [col[0] for col in cur.fetchall()]
        
        # Adapter la requête selon les colonnes disponibles
        if 'id' in columns:
            select_clause = "id, timestamp, type, content"
        else:
            select_clause = "timestamp, type, content"
        
        cur.execute(f"SELECT {select_clause} FROM messages ORDER BY timestamp")
        rows = cur.fetchall()
        
        conn.close()
        
        # Créer un CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Écrire les en-têtes
        headers = select_clause.split(', ')
        writer.writerow(headers)
        
        # Écrire les données
        for row in rows:
            writer.writerow(row)
        
        # Renvoyer le CSV
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=oracle_conversations.csv"}
        )
    except Exception as e:
        print(f"Erreur lors de l'exportation des données: {e}")
        traceback_text = traceback.format_exc()
        return f"Erreur lors de l'exportation des données: {str(e)}<br><pre>{traceback_text}</pre>", 500
####
@app.route('/concept')
def concept():
    return render_template('concept.html', active_page='concept')

@app.route('/conscience')
def conscience():
    return render_template('conscience.html', active_page='conscience')

@app.route('/experience')
def experience():
    return render_template('experience.html', active_page='experience')

@app.route('/galerie')
def galerie():
    return render_template('galerie.html', active_page='galerie')

@app.route('/bio')
def bio():
    return render_template('bio.html', active_page='bio')

@app.route('/contact')
def contact():
    return render_template('contact.html', active_page='contact')
####
# Initialiser la base de données au démarrage
print("Démarrage de l'application...")
init_db()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
