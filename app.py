import os
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.utils import secure_filename 

app = Flask(__name__)
app.secret_key = 'campustrade_super_secure_key_2026'

# Configuration for Image Uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- ISKO EXACT COPY-PASTE KARO APNE APP.PY MEIN ---
EXTERNAL_DATABASE = 'postgresql://postgres.ovgfbumulchtzyjimgdt:%40Pksm887314@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require'
DATABASE = EXTERNAL_DATABASE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = psycopg2.connect(DATABASE, cursor_factory=DictCursor)
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
        
        # 1. Users Table (University aur Course columns default ke sath ready hain)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                mobile TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                city TEXT NOT NULL,
                role TEXT DEFAULT 'Student',
                university_name TEXT DEFAULT 'Not Provided',
                course_name TEXT DEFAULT 'Not Provided'
            )
        ''')
        
        # 2. Items Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
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

        # 3. Private Messages Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id SERIAL PRIMARY KEY,
                sender_id INTEGER,
                receiver_id INTEGER,
                item_id INTEGER,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(receiver_id) REFERENCES users(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            )
        ''')
        db.commit()
        cursor.close()

# <--- IMPROVEMENT 1: Render timeout se bachne ke liye yahan se init_db() hata diya hai --->

@app.context_processor
def inject_locations():
    cities = []
    try:
        db = psycopg2.connect(DATABASE, cursor_factory=DictCursor)
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT city FROM items")
        cities = [row['city'] for row in cursor.fetchall()]
        cursor.close()
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
        
        # Form se aa rha data catch karo
        university_name = request.form.get('university_name', '').strip()
        course_name = request.form.get('course_name', '').strip()
        
        # Pehle common fields check karo jo sabke liye required hain
        if not name or not mobile or not password or not city or not role:
            flash("All common fields are required!", "danger")
            return redirect(url_for('register'))
            
        # --- SMART VALIDATION BASED ON ROLE ---
        if role == 'Student':
            # Agar Student hai, toh University aur Course ka hona pakka zaroori hai
            if not university_name or not course_name:
                flash("University and Course details are required for Students!", "danger")
                return redirect(url_for('register'))
        else:
            # YAHAN BADAL DIYA BHAI: Ab Property Owner ki jagah Vendor/Seller save hoga
            university_name = "N/A (Vendor / Seller)"
            course_name = "N/A (Vendor / Seller)"
            
        db = get_db()
        cursor = db.cursor()
        try:
            # Table mein data save karwao
            cursor.execute(
                'INSERT INTO users (name, mobile, password, city, role, university_name, course_name) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (name, mobile, password, city, role, university_name, course_name)
            )
            db.commit()
            cursor.close()
            flash("Registration Successful! Please Sign In.", "success")
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            db.rollback()
            cursor.close()
            flash("Mobile number already registered!", "danger")
            return redirect(url_for('register'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        password = request.form.get('password')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'SELECT * FROM users WHERE name = %s AND password = %s', 
            (name, password)
        )
        user = cursor.fetchone()
        cursor.close()
        
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
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO items (title, category, price, city, description, image_url, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (title, mapped_category, price, city, description, filename, session['user_id']))
        db.commit()
        cursor.close()
        
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


# --- CONTENT LISTING VIEWS ---

@app.route('/bookstore')
def bookstore():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Book' ORDER BY items.id DESC")
    items = cursor.fetchall()
    cursor.close()
    return render_template('bookstore.html', items=items, title="Campus Bookstore")

@app.route('/rooms')
def rooms():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Room' ORDER BY items.id DESC")
    items = cursor.fetchall()
    cursor.close()
    return render_template('rooms.html', items=items, title="Verified Rooms / PGs")

@app.route('/tiffin')
def tiffin():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Tiffin' ORDER BY items.id DESC")
    items = cursor.fetchall()
    cursor.close()
    return render_template('tiffin.html', items=items, title="Tiffin / Mess Services")

@app.route('/essentials')
def essentials():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT items.*, users.name FROM items JOIN users ON items.user_id = users.id WHERE category='Essential' ORDER BY items.id DESC")
    items = cursor.fetchall()
    cursor.close()
    return render_template('essential.html', items=items, title="Student Essentials")


# --- CHAT SYSTEM ROUTES ---

@app.route('/chat/<int:item_id>/<int:receiver_id>', methods=['GET', 'POST'])
def private_chat(item_id, receiver_id):
    if not session.get('user_id'):
        flash("Please login to message the seller!", "danger")
        return redirect(url_for('login'))
        
    current_user = session['user_id']
    db = get_db()
    cursor = db.cursor()
    
    if request.method == 'POST':
        msg_text = request.form.get('message', '').strip()
        if msg_text:
            cursor.execute('''
                INSERT INTO private_messages (sender_id, receiver_id, item_id, message)
                VALUES (%s, %s, %s, %s)
            ''', (current_user, receiver_id, item_id, msg_text))
            db.commit()
            cursor.close()
            return redirect(url_for('private_chat', item_id=item_id, receiver_id=receiver_id))

    cursor.execute("SELECT * FROM items WHERE id = %s", (item_id,))
    item = cursor.fetchone()
    if not item:
        cursor.close()
        flash("Item not found!", "danger")
        return redirect(url_for('index'))
        
    cursor.execute("SELECT name, role FROM users WHERE id = %s", (receiver_id,))
    chat_partner = cursor.fetchone()

    cursor.execute('''
        SELECT private_messages.*, users.name as sender_name 
        FROM private_messages 
        JOIN users ON private_messages.sender_id = users.id
        WHERE item_id = %s AND 
        ((sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s))
        ORDER BY private_messages.id ASC
    ''', (item_id, current_user, receiver_id, receiver_id, current_user))
    messages = cursor.fetchall()
    cursor.close()
    
    return render_template('chat.html', chat_messages=messages, item=item, partner=chat_partner, receiver_id=receiver_id)

@app.route('/inbox')
def inbox():
    if not session.get('user_id'):
        flash("Please login to view your inbox!", "danger")
        return redirect(url_for('login'))
        
    current_user = session['user_id']
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT DISTINCT pm.item_id, pm.sender_id, pm.receiver_id, items.title, items.category,
        (SELECT name FROM users WHERE id = (CASE WHEN pm.sender_id = %s THEN pm.receiver_id ELSE pm.sender_id END)) as partner_name,
        (CASE WHEN pm.sender_id = %s THEN pm.receiver_id ELSE pm.sender_id END) as partner_id
        FROM private_messages pm
        JOIN items ON pm.item_id = items.id
        WHERE pm.sender_id = %s OR pm.receiver_id = %s
        ORDER BY pm.item_id DESC
    ''', (current_user, current_user, current_user, current_user))
    threads = cursor.fetchall()
    cursor.close()
    
    return render_template('inbox.html', threads=threads)

@app.route('/delete_item/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
    cursor.execute("DELETE FROM private_messages WHERE item_id = %s", (item_id,))
    db.commit()
    cursor.close()
    
    flash("Listing deleted successfully!", "success")
    return redirect(url_for('index'))

# --- ADMIN DATABASE CHECKER ---
@app.route('/secret-db-check')
def secret_db_check():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, mobile, city, role, university_name, course_name FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    cursor.close()
    
    # HTML Table with Beautiful Styling
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f6f9; }}
            h1 {{ color: #333; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #4CAF50; color: white; }}
            tr:hover {{ background-color: #f5f5f5; }}
        </style>
    </head>
    <body>
        <h1>Registered Users List</h1>
        <h3>Total Users Registered: {len(users)}</h3>
        <table>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Mobile</th>
                <th>City</th>
                <th>Role</th>
                <th>University / School</th>
                <th>Course / Class</th>
            </tr>
    """
    
    for u in users:
        html += f"""
            <tr>
                <td>{u['id']}</td>
                <td>{u['name']}</td>
                <td>{u['mobile']}</td>
                <td>{u['city']}</td>
                <td>{u['role']}</td>
                <td>{u['university_name']}</td>
                <td>{u['course_name']}</td>
            </tr>
        """
        
    html += """
        </table>
    </body>
    </html>
    """
    return html

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# --- PURANE IF __NAME__ WALE HISSE KO HATAKAR YEH LIKHO ---

# Gunicorn ho ya local system, app start hote hi yeh hamesha chalega aur tables bana dega
# --- APNE APP.PY KE SABSE NICHE YEH WAAL BLOCK UPDATE KAR DO ---
with app.app_context():
    try:
        init_db()
        print("Database Tables Initialized Successfully! 🎉")
    except Exception as e:
        print(f"Database Initialization skipped or failed: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)