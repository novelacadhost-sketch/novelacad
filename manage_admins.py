import sqlite3
import getpass
from werkzeug.security import generate_password_hash

DATABASE = 'database.db'

def get_db():
    return sqlite3.connect(DATABASE)

def init_admin_table():
    """Creates the admins table if it doesn't exist, preserving other data."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("Admin table verified/created.")

def add_admin(username, password):
    """Adds a new admin user."""
    password_hash = generate_password_hash(password)
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO admins (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        print(f"Admin user '{username}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: User '{username}' already exists.")
    finally:
        conn.close()

def main():
    init_admin_table()
    
    print("\n--- Add New Admin User ---")
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm Password: ")
    
    if password != confirm:
        print("Passwords do not match.")
        return
        
    add_admin(username, password)

if __name__ == "__main__":
    main()
