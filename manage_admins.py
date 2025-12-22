import sqlite3
import getpass
from werkzeug.security import generate_password_hash

DATABASE = 'database.db'

def get_db():
    return sqlite3.connect(DATABASE)

def init_admin_table():
    """Creates the admins table if it doesn't exist, and adds email column if missing."""
    conn = get_db()
    c = conn.cursor()
    
    # Create table if not exists with new schema
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Check if email column exists (migration for existing table)
    c.execute("PRAGMA table_info(admins)")
    columns = [column[1] for column in c.fetchall()]
    if 'email' not in columns:
        print("Migrating: Adding email column to admins table...")
        try:
            c.execute('ALTER TABLE admins ADD COLUMN email TEXT')
            # Note: We can't easily enforce NOT NULL on existing rows without a default, 
            # so we add it as nullable first or just TEXT. 
            # ideally, we'd update existing rows, but for now we'll leave it simple.
            # SQLite doesn't strictly enforce types/nulls on ALTER ADD COLUMN unless strict.
        except sqlite3.OperationalError as e:
            print(f"Migration warning: {e}")

    conn.commit()
    conn.close()
    print("Admin table verified/updated.")

def add_admin(username, email, password):
    """Adds a new admin user."""
    password_hash = generate_password_hash(password)
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO admins (username, email, password_hash) VALUES (?, ?, ?)', 
                 (username, email, password_hash))
        conn.commit()
        print(f"Admin user '{username}' ({email}) added successfully.")
    except sqlite3.IntegrityError as e:
        print(f"Error: User or Email already exists. ({e})")
    finally:
        conn.close()

def main():
    init_admin_table()
    
    print("\n--- Add New Admin User ---")
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
    
    email = input("Email: ").strip()
    if not email:
        print("Email cannot be empty.")
        return
        
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm Password: ")
    
    if password != confirm:
        print("Passwords do not match.")
        return
        
    add_admin(username, email, password)

if __name__ == "__main__":
    main()
