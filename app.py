# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta

# Import configuration
from config import MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Database connection function
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

# Homepage and Login
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users WHERE username = %s AND status = "active"', (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Incorrect username or password!', 'danger')
    
    return render_template('login.html')

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'INSERT INTO users (full_name, username, email, password, status) VALUES (%s, %s, %s, %s, "pending")',
                    (full_name, username, email, hashed_password)
                )
                conn.commit()
                flash('Registration successful. Please wait for admin approval.', 'success')
            except mysql.connector.IntegrityError:
                flash('This username or email is already in use.', 'danger')
            finally:
                cursor.close()
                conn.close()
        
        return redirect(url_for('login'))

    return render_template('register.html')

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

# Student Dashboard
@app.route('/student/dashboard')
def student_dashboard():
    if 'loggedin' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    return render_template('student_dashboard.html')

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

# Browse Books
@app.route('/books')
def browse_books():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT b.id, b.title, a.name as author, c.name as category, b.available_copies
            FROM books b
            LEFT JOIN authors a ON b.author_id = a.id
            LEFT JOIN categories c ON b.category_id = c.id
        """
        search = request.args.get('search')
        if search:
            query += " WHERE b.title LIKE %s OR a.name LIKE %s OR c.name LIKE %s"
            search_term = f"%{search}%"
            cursor.execute(query, (search_term, search_term, search_term))
        else:
            cursor.execute(query)
        
        books = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('browse_books.html', books=books)
    return "Database connection error!", 500

# Borrow Book Request
@app.route('/borrow/<int:book_id>')
def borrow_book(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session['id']
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT available_copies FROM books WHERE id = %s", (book_id,))
        book = cursor.fetchone()

        if book and book['available_copies'] > 0:
            borrow_date = date.today()
            due_date = borrow_date + timedelta(days=14)
            
            cursor.execute(
                "INSERT INTO borrowing_records (user_id, book_id, borrow_date, due_date, status) VALUES (%s, %s, %s, %s, 'requested')",
                (user_id, book_id, borrow_date, due_date)
            )
            conn.commit()
            flash('Book borrow request sent.', 'success')
        else:
            flash('Sorry, this book is not available right now.', 'warning')
            
        cursor.close()
        conn.close()

    return redirect(url_for('browse_books'))

# Borrow History
@app.route('/history')
def borrow_history():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    user_id = session['id']
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT b.title, br.borrow_date, br.due_date, br.return_date, br.status
            FROM borrowing_records br
            JOIN books b ON br.book_id = b.id
            WHERE br.user_id = %s
            ORDER BY br.borrow_date DESC
        """
        cursor.execute(query, (user_id,))
        history = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('borrow_history.html', history=history)
    return "Database connection error!", 500

# Admin: User Management
@app.route('/admin/users')
def manage_users():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, full_name, username, email, role, status FROM users")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('admin_manage_users.html', users=users)
    return "Database connection error!", 500

# Admin: Approve User
@app.route('/admin/approve_user/<int:user_id>')
def approve_user(user_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'active' WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('User has been approved.', 'success')
    return redirect(url_for('manage_users'))

# Admin: Deactivate User
@app.route('/admin/deactivate_user/<int:user_id>')
def deactivate_user(user_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if user_id == session['id']:
        flash('You cannot deactivate yourself.', 'danger')
        return redirect(url_for('manage_users'))

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'inactive' WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('User has been deactivated successfully.', 'warning')
    return redirect(url_for('manage_users'))

# Admin: Activate User
@app.route('/admin/activate_user/<int:user_id>')
def activate_user(user_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'active' WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('User has been activated successfully.', 'success')
    return redirect(url_for('manage_users'))

# Admin: Edit User
@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection error!', 'danger')
        return redirect(url_for('manage_users'))
    
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        role = request.form['role']

        try:
            cursor.execute("""
                UPDATE users 
                SET full_name = %s, username = %s, email = %s, role = %s 
                WHERE id = %s
            """, (full_name, username, email, role, user_id))
            conn.commit()
            flash('User information updated successfully.', 'success')
        except mysql.connector.Error as err:
            flash(f'Could not update information: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('manage_users'))

    cursor.execute('SELECT id, full_name, username, email, role FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('manage_users'))

    return render_template('admin_edit_user.html', user=user)

# Helper function to get or create related records
def get_or_create_id(cursor, table_name, name):
    # Check if the name exists
    query = f"SELECT id FROM {table_name} WHERE name = %s"
    cursor.execute(query, (name,))
    result = cursor.fetchone()
    
    if result:
        return result['id']
    else:
        # If not, insert it and get the new id
        insert_query = f"INSERT INTO {table_name} (name) VALUES (%s)"
        cursor.execute(insert_query, (name,))
        return cursor.lastrowid

# Admin: Book Management
@app.route('/admin/books', methods=['GET', 'POST'])
def manage_books():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database connection error!", 500

    if request.method == 'POST':
        cursor = conn.cursor(dictionary=True)
        try:
            title = request.form['title']
            author_name = request.form['author_name'].strip()
            category_name = request.form['category_name'].strip()
            publisher_name = request.form['publisher_name'].strip()
            total_copies = request.form['total_copies']

            author_id = get_or_create_id(cursor, 'authors', author_name)
            category_id = get_or_create_id(cursor, 'categories', category_name)
            publisher_id = get_or_create_id(cursor, 'publishers', publisher_name)

            cursor.execute(
                "INSERT INTO books (title, author_id, category_id, publisher_id, total_copies, available_copies) VALUES (%s, %s, %s, %s, %s, %s)",
                (title, author_id, category_id, publisher_id, total_copies, total_copies)
            )
            
            conn.commit()
            flash('New book added successfully.', 'success')

        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'An error occurred: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('manage_books'))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.id, b.title, a.name as author, c.name as category, p.name as publisher, b.total_copies, b.available_copies
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.id
        LEFT JOIN categories c ON b.category_id = c.id
        LEFT JOIN publishers p ON b.publisher_id = p.id
        ORDER BY b.id DESC
    """)
    books = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return render_template('admin_manage_books.html', books=books)

# Admin: Edit Book
@app.route('/admin/edit_book/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection error!', 'danger')
        return redirect(url_for('manage_books'))
    
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        try:
            title = request.form['title']
            author_name = request.form['author_name'].strip()
            category_name = request.form['category_name'].strip()
            publisher_name = request.form['publisher_name'].strip()
            total_copies = request.form['total_copies']

            # Get or create IDs for author, category, and publisher
            author_id = get_or_create_id(cursor, 'authors', author_name)
            category_id = get_or_create_id(cursor, 'categories', category_name)
            publisher_id = get_or_create_id(cursor, 'publishers', publisher_name)

            # Update the book details
            cursor.execute("""
                UPDATE books 
                SET title = %s, author_id = %s, category_id = %s, publisher_id = %s, total_copies = %s
                WHERE id = %s
            """, (title, author_id, category_id, publisher_id, total_copies, book_id))
            
            conn.commit()
            flash('Book information updated successfully.', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Could not update information: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('manage_books'))

    # GET request: Fetch book details to populate the form
    cursor.execute("""
        SELECT b.id, b.title, a.name as author, c.name as category, p.name as publisher, b.total_copies
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.id
        LEFT JOIN categories c ON b.category_id = c.id
        LEFT JOIN publishers p ON b.publisher_id = p.id
        WHERE b.id = %s
    """, (book_id,))
    book = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('manage_books'))

    return render_template('admin_edit_book.html', book=book)

# Admin: Delete Book
@app.route('/admin/delete_book/<int:book_id>')
def delete_book(book_id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection error!', 'danger')
        return redirect(url_for('manage_books'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if the book is part of any borrowing record
        cursor.execute("SELECT id FROM borrowing_records WHERE book_id = %s", (book_id,))
        borrow_record = cursor.fetchone()

        if borrow_record:
            flash('This book cannot be deleted as it has a borrowing history.', 'danger')
            return redirect(url_for('manage_books'))

        # If no borrowing history, delete the book
        cursor.execute("DELETE FROM books WHERE id = %s", (book_id,))
        conn.commit()
        flash('Book deleted successfully.', 'success')

    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'An error occurred while deleting the book: {err}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('manage_books'))

# Logout
@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    session.pop('role', None)
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
