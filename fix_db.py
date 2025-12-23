import sqlite3

DATABASE = 'database.db'

def fix_registrations():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    print("Dropping old registrations table...")
    c.execute("DROP TABLE IF EXISTS registrations")
    
    print("Creating new registrations table...")
    c.execute("""
    CREATE TABLE registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL,
        dob TEXT NOT NULL,
        address TEXT NOT NULL,
        sex TEXT NOT NULL,
        nationality TEXT NOT NULL,
        state TEXT NOT NULL,
        course TEXT NOT NULL,
        level TEXT NOT NULL,
        shift TEXT NOT NULL,
        goals TEXT,
        experience TEXT,
        info_source TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()
    print("Registrations table fixed.")

if __name__ == "__main__":
    fix_registrations()
