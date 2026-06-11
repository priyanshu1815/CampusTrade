import os
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'campustrade_super_secure_key_2026'

# Configuration for Image Uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

DATABASE = 'database.db'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Initialize Database with Users, Items, and Private Messages Tables
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # 1. Users Table (No changes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                city TEXT NOT NULL,
                role TEXT DEFAULT 'Student'
            )
        ''')
        
        # 2. Items Table (No changes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                city TEXT NOT NULL,
                description TEXT,
                image_url TEXT,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        # 3. Private Messages Table (New Secure DM Table)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                item_id INTEGER,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
        ''')
        db.commit()

init_db()

@app.context_processor
def inject_locations():
    cities = []
    try:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT city FROM items")
        cities = [row['city'] for row in cursor.fetchall()]
        db.close()
    except:
        pass
    
    if not cities:
        cities = ["Delhi", "Mumbai", "Bangalore", "Pune", "Kota", "Patna"]
    return dict(available_cities=sorted(cities))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- AUTH ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        mobile = request.form.get('mobile').strip()
        password = request.form.get('password')
        city = request.form.get('city').strip()
        role = request.form.get('role')
        
        if not name or not mobile or not password or not city:
            flash("All fields are required!", "danger")
            return redirect(url_for('register'))
            
        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (name, mobile, password, city, role) VALUES (?, ?, ?, ?, ?)',
                (name, mobile, password, city, role)
            )
            db.commit()
            flash("Registration Successful! Please Sign In.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Mobile number already registered!", "danger")
            return redirect(url_for('register'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        password = request.form.get('password')
        
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE name = ? AND password = ?', 
            (name, password)
        ).fetchone()
        
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_mobile'] = user['mobile']
            session['user_role'] = user['role']
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid Name or Password!", "danger")
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))


# --- UPLOAD SYSTEM ROUTES ---

@app.route('/upload/<category>', methods=['GET', 'POST'])
def upload_item(category):
    cat_map = {'book': 'Book', 'essential': 'Essential', 'room': 'Room', 'tiffin': 'Tiffin'}
    mapped_category = cat_map.get(category.lower())
    if not mapped_category:
        flash("Invalid Category Selection!", "danger")
        return redirect(url_for('index'))

    if not session.get('user_id'):
        flash("Please login first to list items!", "danger")
        return redirect(url_for('login'))
        
    user_role = session.get('user_role', 'Student')
    if user_role == 'Student' and mapped_category in ['Room', 'Tiffin']:
        flash("Unauthorized! Students can only sell Books or Essentials.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title').strip()
        price = request.form.get('price').strip()
        city = request.form.get('city').strip()
        description = request.form.get('description').strip()
        file = request.files.get('image')
        
        if not title or not price or not city:
            flash("Title, Price, and City are required!", "danger")
            return render_template('upload.html', category=mapped_category)
            
        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"user_{session['user_id']}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        db = get_db()
        db.execute('''
            INSERT INTO items (title, category, price, city, description, image_url, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, mapped_category, price, city, description, filename, session['user_id']))
        db.commit()
        
        flash(f"{mapped_category} has been posted successfully!", "success")
        
        if category.lower() == 'book':
            return redirect(url_for('bookstore'))
        elif category.lower() == 'essential':
            return redirect(url_for('essentials'))
        else:
            return redirect(url_for(f"{category.lower()}s"))

    return render_template('upload.html', category=mapped_category)

@app.route('/upload_book')
def upload_book(): return redirect(url_for('upload_item', category='book'))
@app.route('/upload_essential')
def upload_essential(): return redirect(url_for('upload_item', category='essential'))
@app.route('/upload_room')
def upload_room(): return redirect(url_for('upload_item', category='room'))
@app.route('/upload_tiffin')
def upload_tiffin(): return redirect(url_for('upload_item', category='tiffin'))


# --- CONTENT LISTING VIEWS (Privacy Protected) ---

@app.route('/bookstore')
def bookstore():
    db = get_db()
    # Number (users.mobile) select query se hata diya hai taaki grid me leak na ho
    items = db.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Book' ORDER BY items.id DESC").fetchall()
    return render_template('bookstore.html', items=items, title="Campus Bookstore")

@app.route('/rooms')
def rooms():
    db = get_db()
    items = db.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Room' ORDER BY items.id DESC").fetchall()
    return render_template('rooms.html', items=items, title="Verified Rooms / PGs")

@app.route('/tiffin')
def tiffin():
    db = get_db()
    items = db.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Tiffin' ORDER BY items.id DESC").fetchall()
    return render_template('tiffin.html', items=items, title="Tiffin / Mess Services")

@app.route('/essentials')
def essentials():
    db = get_db()
    items = db.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Essential' ORDER BY items.id DESC").fetchall()
    # Explicitly fixed to seek essential.html (singular) template
    return render_template('essential.html', items=items, title="Student Essentials")


# --- NEW PRIVACY-SAFE DIRECT CHAT SYSTEM ---

# 1. Personal DM Chat Screen between Buyer and Seller for a specific item
@app.route('/chat/<int:item_id>/<int:receiver_id>', methods=['GET', 'POST'])
def private_chat(item_id, receiver_id):
    if not session.get('user_id'):
        flash("Please login to message the seller!", "danger")
        return redirect(url_for('login'))
        
    current_user = session['user_id']
    db = get_db()
    
    # Send message logic
    if request.method == 'POST':
        msg_text = request.form.get('message', '').strip()
        if msg_text:
            db.execute('''
                INSERT INTO private_messages (sender_id, receiver_id, item_id, message)
                VALUES (?, ?, ?, ?)
            ''', (current_user, receiver_id, item_id, msg_text))
            db.commit()
            return redirect(url_for('private_chat', item_id=item_id, receiver_id=receiver_id))

    # Fetch Item Info
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        flash("Item not found!", "danger")
        return redirect(url_for('index'))
        
    # Fetch chat partner profile info
    chat_partner = db.execute("SELECT name, role FROM users WHERE id = ?", (receiver_id,)).fetchone()

    # Load shared conversation history between these two users for this product
    messages = db.execute('''
        SELECT private_messages.*, users.name as sender_name 
        FROM private_messages 
        JOIN users ON private_messages.sender_id = users.id
        WHERE item_id = ? AND 
        ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
        ORDER BY private_messages.id ASC
    ''', (item_id, current_user, receiver_id, receiver_id, current_user)).fetchall()
    
    return render_template('chat.html', chat_messages=messages, item=item, partner=chat_partner, receiver_id=receiver_id)

# 2. Inbox Dashboard list showing who you are talking to
@app.route('/inbox')
def inbox():
    if not session.get('user_id'):
        flash("Please login to view your inbox!", "danger")
        return redirect(url_for('login'))
        
    current_user = session['user_id']
    db = get_db()
    
    # Subquery fetches unique active threads for recent chat list summary maps
    threads = db.execute('''
        SELECT DISTINCT pm.item_id, pm.sender_id, pm.receiver_id, items.title, items.category,
        (SELECT name FROM users WHERE id = (CASE WHEN pm.sender_id = ? THEN pm.receiver_id ELSE pm.sender_id END)) as partner_name,
        (CASE WHEN pm.sender_id = ? THEN pm.receiver_id ELSE pm.sender_id END) as partner_id
        FROM private_messages pm
        JOIN items ON pm.item_id = items.id
        WHERE pm.sender_id = ? OR pm.receiver_id = ?
        ORDER BY pm.id DESC
    ''', (current_user, current_user, current_user, current_user)).fetchall()
    
    return render_template('inbox.html', threads=threads)

# ... aapke purane routes upar khatam ho jayenge ...

@app.route('/delete_item/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    # Check aur delete karo
    db.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, session['user_id']))
    db.execute("DELETE FROM private_messages WHERE item_id = ?", (item_id,))
    db.commit()
    
    flash("Listing deleted successfully!", "success")
    return redirect(url_for('index'))

# YEH SABSE NEECHE HONA CHAHIYE
if __name__ == '__main__':
    app.run(debug=True)