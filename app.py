from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "super_secret_key_for_campus_trade"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ek naya chaka-chak database taaki sabhi tables fresh aur sahi memory ke sath banein
DB_NAME = "campustrade_global_final.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Items Table (Essentials)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, price INTEGER NOT NULL,
            city TEXT NOT NULL, description TEXT, phone TEXT NOT NULL, owner_username TEXT, image TEXT
        )
    ''')
    
    # 2. Books Table (Book Store)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT, book_title TEXT NOT NULL, author TEXT,
            price INTEGER NOT NULL, city TEXT NOT NULL, shop_name TEXT NOT NULL, phone TEXT NOT NULL, image TEXT
        )
    ''')
    
    # 3. Users Table (With permanent phone number)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, 
            phone TEXT NOT NULL, subscribed INTEGER DEFAULT 0, referred_by TEXT
        )
    ''')

    # 4. Messages Table (Chat System)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, receiver TEXT NOT NULL, msg_text TEXT NOT NULL, item_id INTEGER
        )
    ''')

    # 5. PG/Rooms Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT, room_type TEXT NOT NULL, price INTEGER NOT NULL,
            city TEXT NOT NULL, address TEXT NOT NULL, owner_name TEXT NOT NULL, phone TEXT NOT NULL, image TEXT
        )
    ''')

    # 6. Tiffin Service Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tiffin (
            id INTEGER PRIMARY KEY AUTOINCREMENT, service_name TEXT NOT NULL, price INTEGER NOT NULL,
            city TEXT NOT NULL, menu_details TEXT NOT NULL, phone TEXT NOT NULL, image TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 1. HOME & MARKETPLACE (ESSENTIALS) WITH SESSION FILTER ---
@app.route("/")
def home():
    selected_city = request.args.get('city')
    
    # Global Session Memory Logic
    if selected_city is not None:
        session['global_city'] = selected_city
    else:
        selected_city = session.get('global_city', '')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if selected_city:
        cursor.execute("SELECT * FROM items WHERE city = ?", (selected_city,))
    else:
        cursor.execute("SELECT * FROM items")
    all_items = cursor.fetchall()
    
    # Saari unique cities nikalne ke liye jo dropdown me dikhengi
    cursor.execute("SELECT DISTINCT city FROM items UNION SELECT DISTINCT city FROM books UNION SELECT DISTINCT city FROM rooms UNION SELECT DISTINCT city FROM tiffin")
    all_cities = [row[0] for row in cursor.fetchall() if row[0]]
    
    ref_count = 0
    is_premium = 0
    logged_in_user = session.get("username", None) # Safe way to get logged in user

    if logged_in_user:
        cursor.execute("SELECT subscribed FROM users WHERE username = ?", (logged_in_user,))
        res = cursor.fetchone()
        if res: is_premium = res[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (logged_in_user,))
        ref_count = cursor.fetchone()[0]
        
        if ref_count >= 3 and is_premium == 0:
            cursor.execute("UPDATE users SET subscribed = 1 WHERE username = ?", (logged_in_user,))
            conn.commit()
            is_premium = 1
            
    conn.close()
    
    # Pass direct variables to avoid undefined errors in index.html
    return render_template("index.html", 
                           items=all_items, 
                           cities=all_cities, 
                           selected_city=selected_city, 
                           ref_count=ref_count, 
                           is_premium=is_premium,
                           logged_in_user=logged_in_user,
                           user_image=None) # Abhi ke liye default image template handle karega

# --- 2. SIMPLE REGISTER WITH PHONE ---
@app.route("/register", methods=["GET", "POST"])
def register():
    ref = request.args.get('ref', '')
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        phone = request.form["phone"]
        referred_by = request.form["referred_by"] if request.form["referred_by"] else None
        
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password, phone, referred_by) VALUES (?, ?, ?, ?)", 
                           (username, password, phone, referred_by))
            conn.commit()
            conn.close()
            return redirect("/login")
        except:
            return "Username already exists! Try another one."
            
    return render_template("register.html", ref=ref)

# --- 3. LOGIN & LOGOUT ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        if user:
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect("/")
        else: 
            return "Wrong username or password!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# --- 4. USER PROFILE DASHBOARD ---
@app.route("/profile")
def profile():
    if "username" not in session: 
        return redirect("/login")
    
    username = session["username"]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT subscribed, phone FROM users WHERE username = ?", (username,))
    res = cursor.fetchone()
    is_premium = res[0] if res else 0
    phone = res[1] if res else "Not Available"
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (username,))
    ref_count = cursor.fetchone()[0]
        
    conn.close()
    return render_template("profile.html", username=username, is_premium=is_premium, ref_count=ref_count, phone=phone)

# --- 5. UPLOAD ITEMS (ESSENTIALS) ---
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "username" not in session: return redirect("/login")
    if request.method == "POST":
        title = request.form["title"]
        price = request.form["price"]
        city = request.form["city"]
        description = request.form["description"]
        phone = request.form["phone"]
        owner = session["username"]
        file = request.files['image']
        filename = file.filename if file else "default.jpg"
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO items (title, price, city, description, phone, owner_username, image) VALUES (?, ?, ?, ?, ?, ?, ?)", (title, price, city, description, phone, owner, filename))
        conn.commit()
        conn.close()
        return redirect("/")
    return render_template("upload.html")

# --- 6. CHAT SYSTEM ---
@app.route("/chat/<receiver>/<int:item_id>", methods=["GET", "POST"])
def chat(receiver, item_id):
    if "username" not in session: return redirect("/login")
    sender = session["username"]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if request.method == "POST":
        msg_text = request.form["msg_text"]
        cursor.execute("INSERT INTO messages (sender, receiver, msg_text, item_id) VALUES (?, ?, ?, ?)", (sender, receiver, msg_text, item_id))
        conn.commit()
    cursor.execute("SELECT * FROM messages WHERE (sender = ? AND receiver = ? AND item_id = ?) OR (sender = ? AND receiver = ? AND item_id = ?)", (sender, receiver, item_id, receiver, sender, item_id))
    chat_history = cursor.fetchall()
    conn.close()
    return render_template("chat.html", receiver=receiver, chat_history=chat_history, item_id=item_id)

# --- 7. BOOKSTORE CATEGORY WITH SESSION FILTER ---
@app.route("/bookstore")
def bookstore():
    selected_city = request.args.get('city')
    if selected_city is not None:
        session['global_city'] = selected_city
    else:
        selected_city = session.get('global_city', '')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if selected_city: 
        cursor.execute("SELECT * FROM books WHERE city = ?", (selected_city,))
    else: 
        cursor.execute("SELECT * FROM books")
    all_books = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT city FROM books")
    all_cities = [row[0] for row in cursor.fetchall() if row[0]]
    
    is_premium = 0
    if "username" in session:
        cursor.execute("SELECT subscribed FROM users WHERE username = ?", (session["username"],))
        res = cursor.fetchone()
        if res: is_premium = res[0]
    conn.close()
    return render_template("bookstore.html", books=all_books, cities=all_cities, selected_city=selected_city, is_premium=is_premium)

@app.route("/upload-book", methods=["GET", "POST"])
def upload_book():
    if request.method == "POST":
        book_title = request.form["book_title"]
        author = request.form["author"]
        price = request.form["price"]
        city = request.form["city"]
        shop_name = request.form["shop_name"]
        phone = request.form["phone"]
        file = request.files['image']
        filename = file.filename if file else "default_book.jpg"
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO books (book_title, author, price, city, shop_name, phone, image) VALUES (?, ?, ?, ?, ?, ?, ?)", (book_title, author, price, city, shop_name, phone, filename))
        conn.commit()
        conn.close()
        return redirect("/bookstore")
    return render_template("upload_book.html")

# --- 8. PG ROOMS CATEGORY WITH SESSION FILTER ---
@app.route("/rooms")
def rooms():
    selected_city = request.args.get('city')
    if selected_city is not None:
        session['global_city'] = selected_city
    else:
        selected_city = session.get('global_city', '')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if selected_city: 
        cursor.execute("SELECT * FROM rooms WHERE city = ?", (selected_city,))
    else: 
        cursor.execute("SELECT * FROM rooms")
    all_rooms = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT city FROM rooms")
    all_cities = [row[0] for row in cursor.fetchall() if row[0]]
    
    is_premium = 0
    if "username" in session:
        cursor.execute("SELECT subscribed FROM users WHERE username = ?", (session["username"],))
        res = cursor.fetchone()
        if res: is_premium = res[0]
    conn.close()
    return render_template("rooms.html", rooms=all_rooms, cities=all_cities, selected_city=selected_city, is_premium=is_premium)

@app.route("/upload-room", methods=["GET", "POST"])
def upload_room():
    if request.method == "POST":
        room_type = request.form["room_type"]
        price = request.form["price"]
        city = request.form["city"]
        address = request.form["address"]
        owner_name = request.form["owner_name"]
        phone = request.form["phone"]
        file = request.files['image']
        filename = file.filename if file else "default.jpg"
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO rooms (room_type, price, city, address, owner_name, phone, image) VALUES (?, ?, ?, ?, ?, ?, ?)", (room_type, price, city, address, owner_name, phone, filename))
        conn.commit()
        conn.close()
        return redirect("/rooms")
    return render_template("upload_room.html")

# --- 9. TIFFIN SERVICES CATEGORY WITH SESSION FILTER ---
@app.route("/tiffin")
def tiffin():
    selected_city = request.args.get('city')
    if selected_city is not None:
        session['global_city'] = selected_city
    else:
        selected_city = session.get('global_city', '')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if selected_city: 
        cursor.execute("SELECT * FROM tiffin WHERE city = ?", (selected_city,))
    else: 
        cursor.execute("SELECT * FROM tiffin")
    all_tiffin = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT city FROM tiffin")
    all_cities = [row[0] for row in cursor.fetchall() if row[0]]
    
    is_premium = 0
    if "username" in session:
        cursor.execute("SELECT subscribed FROM users WHERE username = ?", (session["username"],))
        res = cursor.fetchone()
        if res: is_premium = res[0]
    conn.close()
    return render_template("tiffin.html", tiffins=all_tiffin, cities=all_cities, selected_city=selected_city, is_premium=is_premium)

@app.route("/upload-tiffin", methods=["GET", "POST"])
def upload_tiffin():
    if request.method == "POST":
        service_name = request.form["service_name"]
        price = request.form["price"]
        city = request.form["city"]
        menu_details = request.form["menu_details"]
        phone = request.form["phone"]
        file = request.files['image']
        filename = file.filename if file else "default.jpg"
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tiffin (service_name, price, city, menu_details, phone, image) VALUES (?, ?, ?, ?, ?, ?)", (service_name, price, city, menu_details, phone, filename))
        conn.commit()
        conn.close()
        return redirect("/tiffin")
    return render_template("upload_tiffin.html")

# --- 10. MOCK PREMIUM ACTIVATION ---
@app.route("/buy-premium")
def buy_premium():
    if "username" in session:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET subscribed = 1 WHERE username = ?", (session["username"],))
        conn.commit()
        conn.close()
        return "<h3>Success! You are now a Premium Member. Go back and check the lock features!</h3>"
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)
