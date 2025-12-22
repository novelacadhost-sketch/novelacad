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
            role TEXT DEFAULT 'admin',
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Check for email and role columns (migration)
    c.execute("PRAGMA table_info(admins)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'email' not in columns:
        print("Migrating: Adding email column...")
        try: c.execute('ALTER TABLE admins ADD COLUMN email TEXT')
        except: pass
            
    if 'role' not in columns:
        print("Migrating: Adding role column...")
        try: 
            c.execute("ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'admin'")
            # Set existing users to admin by default
            c.execute("UPDATE admins SET role = 'admin' WHERE role IS NULL")
        except: pass

    conn.commit()
    conn.close()
    print("Admin table verified/updated.")

def add_admin(username, email, password, role='admin'):
    """Adds a new admin user."""
    password_hash = generate_password_hash(password)
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO admins (username, email, role, password_hash) VALUES (?, ?, ?, ?)', 
                 (username, email, role, password_hash))
        conn.commit()
        print(f"Admin user '{username}' ({email}) [{role}] added successfully.")
    except sqlite3.IntegrityError as e:
        print(f"Error: User or Email already exists. ({e})")
    finally:
        conn.close()

def promote_to_master(username):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE admins SET role = 'master' WHERE username = ?", (username,))
    if c.rowcount > 0:
        print(f"User '{username}' is now a Master Admin.")
    else:
        print(f"User '{username}' not found. Please create them first.")
    conn.commit()
    conn.close()

def main():
    init_admin_table()
    
    print("\n1. Add New Admin")
    print("2. Promote User to Master")
    choice = input("Select option (1/2): ").strip()
    
    if choice == '2':
        user = input("Enter username to promote: ").strip()
        promote_to_master(user)
        return

    print("\n--- Add New Admin User ---")
    username = input("Username: ").strip()
    if not username: return
    
    email = input("Email: ").strip()
    if not email: return
        
    role = input("Role (admin/master) [default: admin]: ").strip().lower()
    if role not in ['admin', 'master']: role = 'admin'

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm Password: ")
    
    if password != confirm:
        print("Passwords do not match.")
        return
        
    add_admin(username, email, password, role)

if __name__ == "__main__":
    main()
