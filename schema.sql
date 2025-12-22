DROP TABLE IF EXISTS registrations;
DROP TABLE IF EXISTS messages;

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
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    subject TEXT NOT NULL,
    message TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);
