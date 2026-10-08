import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.secret_key = 'super_secret_barter_key'  # სესიების სამართავად
DATABASE = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # მომხმარებლების ცხრილი
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # განცხადებების ცხრილი (ავტორის მითითებით)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT DEFAULT 'სხვა',
            image_filename TEXT,
            username TEXT
        )
    ''')
    
    # კომენტარების ცხრილი
    conn.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            content TEXT NOT NULL,
            username TEXT,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

# მთავარი გვერდი (კატეგორიების ფილტრაციით)
@app.route('/')
def index():
    category = request.args.get('category', '')
    conn = get_db_connection()
    if category and category != 'ყველა':
        items = conn.execute('SELECT * FROM items WHERE category = ? ORDER BY id DESC', (category,)).fetchall()
    else:
        items = conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('index.html', items=items, selected_category=category)

# რეგისტრაცია
@app.route('/register', methods=('GET', 'POST'))
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        if not username or not password:
            error = 'გთხოვთ შეავსოთ ყველა ველი.'
        else:
            conn = get_db_connection()
            existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if existing_user:
                error = 'ეს მომხმარებლის სახელი უკვე დაკავებულია.'
            else:
                hashed_password = generate_password_hash(password)
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
            conn.close()
            
    return render_template('register.html', error=error)

# ავტორიზაცია (შესვლა)
@app.route('/login', methods=('GET', 'POST'))
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user'] = user['username']
            return redirect(url_for('index'))
        else:
            error = 'არასწორი სახელი ან პაროლი.'
            
    return render_template('login.html', error=error)

# გამოსვლა (Logout)
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# განცხადების დამატება
@app.route('/add', methods=('GET', 'POST'))
def add_item():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form.get('category', 'სხვა')
        image_filename = None

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_filename = unique_filename

        conn = get_db_connection()
        conn.execute('INSERT INTO items (title, description, category, image_filename, username) VALUES (?, ?, ?, ?, ?)',
                     (title, description, category, image_filename, session['user']))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    return render_template('add_item.html')

# განცხადების წაშლა
@app.route('/delete/<int:item_id>', methods=('POST',))
def delete_item(item_id):
    if 'user' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
    
    # შევამოწმოთ, რომ წაშლას ცდილობს თავად ავტორი
    if item and item['username'] == session['user']:
        if item['image_filename']:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], item['image_filename'])
            if os.path.exists(img_path):
                os.remove(img_path)

        conn.execute('DELETE FROM items WHERE id = ?', (item_id,))
        conn.execute('DELETE FROM comments WHERE item_id = ?', (item_id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for('index'))

# დეტალური გვერდი და კომენტარები/შემოთავაზებები
@app.route('/item/<int:item_id>', methods=('GET', 'POST'))
def item_detail(item_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        if 'user' not in session:
            return redirect(url_for('login'))
        content = request.form['content']
        if content.strip():
            conn.execute('INSERT INTO comments (item_id, content, username) VALUES (?, ?, ?)',
                         (item_id, content, session['user']))
            conn.commit()
        return redirect(url_for('item_detail', item_id=item_id))

    item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
    comments = conn.execute('SELECT * FROM comments WHERE item_id = ?', (item_id,)).fetchall()
    conn.close()
    
    if item is None:
        return "განცხადება ვერ მოიძებნა", 404

    return render_template('item_detail.html', item=item, comments=comments)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)