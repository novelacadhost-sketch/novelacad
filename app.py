import sqlite3
print("--- APP STARTING ---")
import os
import time
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify, g, session, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message

# Ensure Flask uses the correct template folder
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')  # Required for flashing messages
s = URLSafeTimedSerializer(app.secret_key)

# Initialize CSRF Protection
csrf = CSRFProtect(app)


@app.route('/health-check')
def health_check():
    return "OK", 200

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'novelsolaracademy@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '') # Set this in cPanel
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'info@novel-academy.com')

# Initialize Flask-Mail
mail = Mail(app)

# Initialize Rate Limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Error handler for CSRF validation failures
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF token validation errors"""
    if request.is_json or request.path.startswith('/submit_'):
        return jsonify({"status": "error", "message": "CSRF token missing or invalid. Please refresh the page and try again."}), 400
    flash("CSRF token missing or invalid. Please try again.", "error")
    return redirect(request.url or '/')

# Error handler for rate limit exceeded
from flask_limiter.errors import RateLimitExceeded

@app.errorhandler(RateLimitExceeded)
def handle_rate_limit_exceeded(e):
    """Handle rate limit exceeded errors"""
    retry_after = getattr(e, 'retry_after', 60)
    if request.is_json or request.path.startswith('/submit_'):
        return jsonify({
            "status": "error", 
            "message": f"Too many requests. Please wait {retry_after} seconds before trying again."
        }), 429
    flash(f"Too many requests. Please wait a moment before trying again.", "error")
    return redirect(request.url or '/'), 429

DATABASE = 'database.db'

def init_database():
    """Initialize database if it doesn't exist or if tables are missing"""
    import os
    
    # Check if database file exists
    db_exists = os.path.exists(DATABASE)
    
    if not db_exists:
        print(f"Database '{DATABASE}' not found. Initializing...")
        try:
            db = sqlite3.connect(DATABASE, timeout=20)
            with open('schema.sql', 'r') as f:
                db.executescript(f.read())
            db.commit()
            db.close()
            print(f"Database '{DATABASE}' initialized successfully.")
        except FileNotFoundError:
            print(f"ERROR: schema.sql file not found. Cannot initialize database.")
            raise
        except Exception as e:
            print(f"ERROR: Failed to initialize database: {e}")
            raise
    else:
        # Database exists, but check if tables are present
        try:
            db = sqlite3.connect(DATABASE, timeout=20)
            cursor = db.cursor()
            
            # Check if required tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            required_tables = ['registrations', 'messages', 'admins']
            missing_tables = [table for table in required_tables if table not in existing_tables]
            
            if missing_tables:
                print(f"Missing tables detected: {missing_tables}. Initializing missing tables...")
                with open('schema.sql', 'r') as f:
                    db.executescript(f.read())
                db.commit()
                print("Missing tables created successfully.")
            
            # Check for missing columns in existing tables (Migration Logic)
            # Check 'registrations' table for 'duration' column
            cursor.execute("PRAGMA table_info(registrations)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'duration' not in columns:
                print("Migrating database: Adding 'duration' column to 'registrations' table...")
                cursor.execute("ALTER TABLE registrations ADD COLUMN duration TEXT")
                db.commit()
                print("Migration successful.")
            
            # Check 'admins' table for 'created_at' column
            cursor.execute("PRAGMA table_info(admins)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'created_at' not in columns:
                print("Migrating database: Adding 'created_at' column to 'admins' table...")
                cursor.execute("ALTER TABLE admins ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                db.commit()
                print("Migration successful.")
            
            # Ensure at least one master admin exists
            cursor.execute("SELECT COUNT(*) FROM admins WHERE role = 'master'")
            master_count = cursor.fetchone()[0]
            if master_count == 0:
                cursor.execute("SELECT id FROM admins LIMIT 1")
                first_admin = cursor.fetchone()
                if first_admin:
                    print("No master admin found. Promoting first admin to master...")
                    cursor.execute("UPDATE admins SET role = 'master' WHERE id = ?", (first_admin[0],))
                    db.commit()
                    print("First admin promoted to master role.")

            db.close()
        except Exception as e:
            print(f"WARNING: Could not verify database tables: {e}")
            # Don't raise - let the app continue, errors will show when trying to use DB

# Initialize database on app startup
init_database()

# Anti-bot protection
def validate_anti_bot(form_data, is_json=False):
    """Validate anti-bot protections. Returns (is_valid, error_message)"""
    # Extract honeypot fields (same for JSON and form submissions)
    honeypot_field = form_data.get('website', '').strip()
    honeypot_field2 = form_data.get('email_confirm', '').strip()
    form_start = form_data.get('_form_start_time', '0')
    
    # Check honeypot fields (if filled, it's a bot)
    if honeypot_field:
        app.logger.warning(f"Bot detected: Honeypot 'website' filled with: {honeypot_field}")
        return False, "Invalid submission detected."
    if honeypot_field2:
        app.logger.warning(f"Bot detected: Honeypot 'email_confirm' filled with: {honeypot_field2}")
        return False, "Invalid submission detected."
    
    # Check timing - form should take at least 5 seconds to fill out
    try:
        start_time = float(form_start)
        if start_time == 0:
            return False, "Form timing validation failed. Please refresh and try again."
        
        elapsed_time = time.time() - start_time
        
        # Too fast (less than 2 seconds) - likely a bot
        if elapsed_time < 2:
            app.logger.warning(f"Bot suspected: Form submitted in {elapsed_time:.2f}s (too fast)")
            return False, "Form submitted too quickly. Please take your time filling out all fields carefully."
        
        # Suspiciously fast for registration form (less than 3 seconds for complex forms)
        if elapsed_time < 3 and 'fullName' in str(form_data):
            app.logger.warning(f"Bot suspected: Registration form submitted in {elapsed_time:.2f}s")
            return False, "Form submitted too quickly. Please ensure all fields are completed accurately."
        
        # Too slow (more than 1 hour) - session might be stale
        if elapsed_time > 3600:
            return False, "Form session expired. Please refresh the page and try again."
    except (ValueError, TypeError):
        app.logger.warning(f"Invalid form timing data: {form_start}")
        return False, "Invalid form submission. Please refresh the page and try again."
    
    # Additional checks for JSON submissions
    if is_json and 'fullName' in form_data and 'email' in form_data:
        name = form_data.get('fullName', '').strip()
        email = form_data.get('email', '').strip()
        if name and email and name.lower() == email.lower():
            app.logger.warning("Bot suspected: Name and email are identical")
            return False, "Invalid form data detected."
    
    # Basic user agent check (log only, don't reject)
    user_agent = request.headers.get('User-Agent', '')
    if not user_agent or len(user_agent) < 10:
        app.logger.warning(f"Suspicious user agent: {user_agent}")
    
    return True, None

def get_db():
    """Get database connection from Flask g object"""
    if not hasattr(g, '_database'):
        g._database = sqlite3.connect(DATABASE, timeout=20)
        g._database.row_factory = sqlite3.Row
    return g._database

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection at end of request"""
    if hasattr(g, '_database'):
        g._database.close()

# Admin authentication decorator
def require_admin(master_only=False):
    """Decorator to require admin authentication and optionally master role"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not session.get('admin_logged_in'):
                flash("Please log in to access this page.", "error")
                return redirect(url_for('admin_login'))
            if master_only and session.get('admin_role') != 'master':
                flash("Unauthorized: Only Master Admins can access this.", "error")
                return redirect(url_for('admin_dashboard'))
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# Database helper for registration insertion
def insert_registration(data):
    """Insert registration data into database. Accepts dict with snake_case or camelCase keys"""
    db = get_db()
    db.execute('''INSERT INTO registrations 
                  (full_name, email, phone, dob, address, sex, nationality, state, course, duration, 
                   level, qualification, goals, experience, info_source, submitted_at) 
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+1 hours'))''',
               (data.get('full_name') or data.get('fullName'), 
                data.get('email'), 
                data.get('phone') or data.get('phoneNumber'), 
                data.get('dob'), 
                data.get('address'), 
                data.get('sex'), 
                data.get('nationality'), 
                data.get('state'), 
                data.get('course'), 
                data.get('duration'),
                data.get('level') or data.get('educationLevel'), 
                data.get('qualification'), 
                data.get('goals') or data.get('courseGoals'), 
                data.get('experience'), 
                data.get('info_source') or data.get('infoSource')))
    db.commit()

# SPA Routing Configuration
PAGE_MAP = {
    'home': 'index.html',
    'courses': 'course.html',
    'testimonial': 'testimonial.html',
    'registration': 'registration.html',
    'thank-you': 'thank_you.html',
}

COURSE_MAP = {
    'solar-design-installation': ('solar-design-installation.html', 'Solar Design & Installation'),
    'solarpreneurship': ('solarpreneurship.html', 'Solarpreneurship'),
    'repair-maintenance': ('repair-maintenance.html', 'Repair & Maintenance'),
    'hse-management': ('hse-management.html', 'HSE Management'),
    'ai-robotics': ('ai-robotics.html', 'AI & Robotics'),
    'web-development': ('web-development.html', 'Web Development'),
    'digital-marketing': ('digital-marketing.html', 'Digital Marketing'),
}

# API endpoint to get CSRF token for AJAX requests
@csrf.exempt
@app.route("/api/csrf-token")
def get_csrf_token():
    """Return CSRF token for AJAX requests"""
    from flask_wtf.csrf import generate_csrf
    return jsonify({"csrf_token": generate_csrf()})

# API endpoints to fetch page content dynamically
# Exclude API endpoints from CSRF protection as they're used by SPA
@csrf.exempt
@app.route("/api/page/<page_name>")
def get_page(page_name):
    """Fetch page content as JSON for SPA loading"""
    if page_name not in PAGE_MAP:
        # Check if it's a course name
        if page_name in COURSE_MAP:
             return get_course(page_name)
        app.logger.warning(f"Page not found: {page_name}")
        return jsonify({"error": "Page not found"}), 404

    try:
        content = render_template(f"pages/{PAGE_MAP[page_name]}")
        return jsonify({"content": content, "page": page_name})
    except Exception as e:
        app.logger.error(f"Error rendering page '{page_name}': {e}")
        return jsonify({"error": str(e)}), 500

@csrf.exempt
@app.route("/api/course/<course_slug>")
def get_course(course_slug):
    """Fetch course content dynamically"""
    if course_slug not in COURSE_MAP:
        return jsonify({"error": "Course not found"}), 404
    
    try:
        template_file, course_name = COURSE_MAP[course_slug]
        content = render_template(f"pages/{template_file}")
        return jsonify({"content": content, "page": f"course-{course_slug}", "title": course_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        db = get_db()
        user = db.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_role'] = user['role']
            session['admin_username'] = user['username'] 
            flash("Successfully logged in!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid username or password.", "error")
            
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('admin_login'))

@app.route("/admin/export/csv", methods=["POST"])
@require_admin()
def export_registrations_csv():
    """Export registrations to CSV with filtering options"""
    db = get_db()
    
    # Get filter parameters
    export_type = request.form.get('export_type', 'all')  # all, selected, date_range
    selected_ids = request.form.getlist('selected_ids')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # Build query based on export type
    query = 'SELECT id, full_name, email, phone, course, submitted_at FROM registrations'
    params = []
    
    if export_type == 'selected' and selected_ids:
        placeholders = ','.join('?' * len(selected_ids))
        query += f' WHERE id IN ({placeholders})'
        params = [int(id) for id in selected_ids]
    elif export_type == 'date_range':
        query += ' WHERE submitted_at >= ? AND submitted_at < ?'
        params = [start_date, end_date]
    
    query += ' ORDER BY submitted_at DESC'
    
    registrations = db.execute(query, params).fetchall()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Full Name', 'Email', 'Phone', 'Course', 'Submitted At'])
    
    # Write data
    for reg in registrations:
        writer.writerow([reg['id'], reg['full_name'], reg['email'], reg['phone'], reg['course'], reg['submitted_at']])
    
    # Create response
    output.seek(0)
    mem = io.BytesIO(output.getvalue().encode('utf-8'))
    mem.seek(0)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'registrations_{timestamp}.csv'
    
    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route("/admin/export/pdf", methods=["POST"])
@require_admin()
def export_registrations_pdf():
    """Export registrations to PDF with filtering options"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
    except ImportError:
        return jsonify({'error': 'PDF export requires reportlab. Install it with: pip install reportlab'}), 400
    
    db = get_db()
    
    # Get filter parameters
    export_type = request.form.get('export_type', 'all')
    selected_ids = request.form.getlist('selected_ids')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    # Build query based on export type
    query = 'SELECT id, full_name, email, phone, course, submitted_at FROM registrations'
    params = []
    
    if export_type == 'selected' and selected_ids:
        placeholders = ','.join('?' * len(selected_ids))
        query += f' WHERE id IN ({placeholders})'
        params = [int(id) for id in selected_ids]
    elif export_type == 'date_range':
        query += ' WHERE submitted_at >= ? AND submitted_at < ?'
        params = [start_date, end_date]
    
    query += ' ORDER BY submitted_at DESC'
    
    registrations = db.execute(query, params).fetchall()
    
    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Title
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#2878EB'),
        spaceAfter=20,
    )
    
    elements.append(Paragraph("Course Registrations Report", title_style))
    elements.append(Spacer(1, 0.3*inch))
    
    # Create table data
    table_data = [['ID', 'Full Name', 'Email', 'Phone', 'Course', 'Submitted At']]
    
    for reg in registrations:
        table_data.append([
            str(reg['id']),
            reg['full_name'],
            reg['email'],
            reg['phone'],
            reg['course'],
            reg['submitted_at']
        ])
    
    # Create table
    table = Table(table_data, colWidths=[0.5*inch, 1.2*inch, 1.2*inch, 0.9*inch, 1.2*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2878EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'registrations_{timestamp}.pdf'
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


@app.route("/admin/dashboard")
@require_admin()
def admin_dashboard():
    db = get_db()
    registrations = db.execute('SELECT id, full_name, email, phone, course, submitted_at FROM registrations ORDER BY submitted_at DESC').fetchall()
    messages = db.execute('SELECT * FROM messages ORDER BY submitted_at DESC').fetchall()
    admins = db.execute('SELECT id, username, email, role, created_at FROM admins ORDER BY created_at DESC').fetchall()
    is_master_admin = session.get('admin_role') == 'master'
    return render_template("admin/dashboard.html", registrations=registrations, messages=messages, admins=admins, is_master_admin=is_master_admin)

@app.route("/admin/registration/<int:reg_id>")
@require_admin()
def registration_details(reg_id):
    db = get_db()
    registration = db.execute('SELECT * FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    if not registration:
        flash("Registration not found.", "error")
        return redirect(url_for('admin_dashboard'))
    return render_template("admin/registration_details.html", registration=registration)

@app.route("/admin/create", methods=["POST"])
@require_admin(master_only=True)
def create_admin():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role", "admin")  # Default to 'admin', but allow 'master' too
    
    if not all([username, email, password]):
        flash("All fields are required.", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Validate role
    if role not in ['admin', 'master']:
        role = 'admin'
    
    try:
        db = get_db()
        db.execute('INSERT INTO admins (username, email, role, password_hash) VALUES (?, ?, ?, ?)',
                   (username, email, role, generate_password_hash(password)))
        db.commit()
        flash(f"Admin '{username}' ({role.title()}) successfully created.", "success")
    except sqlite3.IntegrityError:
        flash("Username or Email already exists.", "error")
    
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete/<int:admin_id>", methods=["POST"])
@require_admin(master_only=True)
def delete_admin(admin_id):
    db = get_db()
    # Prevent deletion of self
    current_user = db.execute('SELECT id FROM admins WHERE username = ?', (session.get('admin_username'),)).fetchone()
    if current_user and current_user['id'] == admin_id:
        flash("Operation failed: You cannot delete your own account.", "error")
        return redirect(url_for('admin_dashboard'))
    
    db.execute('DELETE FROM admins WHERE id = ?', (admin_id,))
    db.commit()
    flash("Admin user deleted successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        db = get_db()
        user = db.execute('SELECT * FROM admins WHERE email = ?', (email,)).fetchone()
        
        if user:
            token = s.dumps(email, salt='email-confirm')
            link = url_for('reset_password', token=token, _external=True)
            
            try:
                msg = Message(
                    subject="Password Reset Request - Novel Academy",
                    recipients=[email]
                )
                msg.body = f'''To reset your password, visit the following link:

{link}

If you did not make this request then simply ignore this email and no changes will be made.
'''
                mail.send(msg)
                flash("A password reset link has been sent to your email.", "success")
            except Exception as e:
                app.logger.error(f"Failed to send password reset email: {e}")
                print(f"FAILED TO SEND EMAIL. LINK WAS: {link}")
                flash("Failed to send the reset email. Please contact the system administrator.", "error")
        else:
            flash("Email not found.", "error")
            
    return render_template("admin/forgot_password.html")

@app.route("/admin/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except:
        flash("The reset link is invalid or has expired.", "error")
        return redirect(url_for('admin_login'))
        
    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for('reset_password', token=token))
            
        password_hash = generate_password_hash(password)
        db = get_db()
        db.execute('UPDATE admins SET password_hash = ? WHERE email = ?', (password_hash, email))
        db.commit()
        flash("Your password has been reset successfully. Please login.", "success")
        return redirect(url_for('admin_login'))

    return render_template("admin/reset_password.html", token=token)

# Contact Form Submission
@limiter.limit("5 per minute")  # Rate limit: 5 submissions per minute per IP
@app.route("/submit_contact", methods=["POST"])
def submit_contact():
    # Anti-bot validation
    is_valid, error_msg = validate_anti_bot(request.form, is_json=False)
    if not is_valid:
        flash(error_msg or "Invalid submission detected.", "error")
        return redirect('/')
    
    name = request.form.get("name")
    email = request.form.get("email")
    subject = request.form.get("subject")
    message = request.form.get("message")
    
    # Basic validation
    if not name or not email or not message:
        flash("Please fill in all required fields.", "error")
        return redirect('/')
    
    # Save to DB
    try:
        db = get_db()
        db.execute("INSERT INTO messages (name, email, subject, message, submitted_at) VALUES (?, ?, ?, ?, datetime('now', '+1 hours'))",
                   (name, email, subject, message))
        db.commit()
        print(f"Contact Form Submission Saved: {name}, {email}")
        flash("Your message has been sent successfully!", "success")
    except Exception as e:
        app.logger.error(f"Error saving contact form: {e}")
        flash("An error occurred. Please try again later.", "error")
    
    return redirect('/')


@limiter.limit("3 per hour")  # Rate limit: 3 registrations per hour per IP
@app.route("/submit_registration", methods=["POST"])
def submit_registration():
    if request.is_json:
        data = request.get_json()
        
        # Anti-bot validation
        is_valid, error_msg = validate_anti_bot(data, is_json=True)
        if not is_valid:
            return jsonify({"status": "error", "message": error_msg or "Invalid submission detected."}), 400
        
        # Basic validation
        required_fields = ['fullName', 'email', 'phoneNumber', 'dob', 'sex', 'nationality', 'state', 'course', 'educationLevel', 'qualification', 'courseGoals', 'infoSource']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({"status": "error", "message": "Please fill in all required fields."}), 400
        
        # Save to DB
        try:
            insert_registration(data)
            print(f"Registration Submission Saved (JSON): {data.get('fullName')}")
            
            # Send Thank You Email
            try:
                full_name = data.get('fullName', '')
                first_name = full_name.split()[0] if full_name else 'Applicant'
                email = data.get('email')
                
                msg = Message(
                    subject="Novel Academy: Application Received",
                    recipients=[email]
                )
                msg.body = f'''Hi {first_name},

Thank you for submitting your details to Novel Academy. We have successfully received your application.

Our team will review your information shortly. We will be in touch soon to outline the next steps in the admissions process and let you know if we need anything else from you.

If you have any immediate questions, feel free to reply directly to this email.

Best regards,

The Novel Academy Team
'''
                mail.send(msg)
            except Exception as e:
                app.logger.error(f"Failed to send registration thank you email (JSON): {e}")

            return jsonify({"status": "success", "message": "Registration received", "redirect": "/thank-you"})
        except Exception as e:
            app.logger.error(f"Error saving registration: {e}")
            return jsonify({"status": "error", "message": "An error occurred. Please try again later."}), 500
    
    # Fallback for standard form submission (if JS fails or is disabled)
    is_valid, error_msg = validate_anti_bot(request.form, is_json=False)
    if not is_valid:
        flash(error_msg or "Invalid submission detected.", "error")
        return redirect('/registration')
    
    try:
        # Convert form data to dict for insert_registration
        data = {
            'full_name': request.form.get('fullName'),
            'email': request.form.get('email'),
            'phone': request.form.get('phoneNumber'),
            'dob': request.form.get('dob'),
            'address': request.form.get('address'),
            'sex': request.form.get('sex'),
            'nationality': request.form.get('nationality'),
            'state': request.form.get('state'),
            'course': request.form.get('course'),
            'duration': request.form.get('duration'),
            'level': request.form.get('educationLevel'),
            'qualification': request.form.get('qualification'),
            'goals': request.form.get('courseGoals'),
            'experience': request.form.get('experience'),
            'info_source': request.form.get('infoSource')
        }
        insert_registration(data)
        print(f"Registration Submission Saved (Form): {data['full_name']}")
        
        # Send Thank You Email
        try:
            full_name = data.get('full_name', '')
            first_name = full_name.split()[0] if full_name else 'Applicant'
            email = data.get('email')
            
            msg = Message(
                subject="Novel Academy: Application Received",
                recipients=[email]
            )
            msg.body = f'''Hi {first_name},

Thank you for submitting your details to Novel Academy. We have successfully received your application.

Our team will review your information shortly. We will be in touch soon to outline the next steps in the admissions process and let you know if we need anything else from you.

If you have any immediate questions, feel free to reply directly to this email.

Best regards,

The Novel Academy Team
'''
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send registration thank you email (Form): {e}")

        flash("Registration submitted successfully!", "success")
    except Exception as e:
        app.logger.error(f"Error saving registration: {e}")
        flash("An error occurred. Please try again later.", "error")
        return redirect('/registration')
    
    return redirect('/thank-you')


# Registration Management Routes
@app.route("/admin/registration/<int:reg_id>/delete", methods=["POST"])
@require_admin()
def delete_registration(reg_id):
    """Delete a registration"""
    try:
        db = get_db()
        db.execute('DELETE FROM registrations WHERE id = ?', (reg_id,))
        db.commit()
        flash(f"Registration #{reg_id} deleted successfully.", "success")
    except Exception as e:
        app.logger.error(f"Error deleting registration: {e}")
        flash("Error deleting registration.", "error")
    
    return redirect(url_for('admin_dashboard'))


@app.route("/admin/registration/<int:reg_id>/edit", methods=["GET", "POST"])
@require_admin()
def edit_registration(reg_id):
    """Edit a registration"""
    db = get_db()
    registration = db.execute('SELECT * FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    
    if not registration:
        flash("Registration not found.", "error")
        return redirect(url_for('admin_dashboard'))
    
    if request.method == "POST":
        try:
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            course = request.form.get('course')
            level = request.form.get('level')
            dob = request.form.get('dob')
            address = request.form.get('address')
            sex = request.form.get('sex')
            nationality = request.form.get('nationality')
            state = request.form.get('state')
            duration = request.form.get('duration')
            qualification = request.form.get('qualification')
            goals = request.form.get('goals')
            experience = request.form.get('experience')
            info_source = request.form.get('info_source')
            
            db.execute('''UPDATE registrations 
                         SET full_name=?, email=?, phone=?, course=?, level=?, dob=?, 
                             address=?, sex=?, nationality=?, state=?, duration=?, 
                             qualification=?, goals=?, experience=?, info_source=?
                         WHERE id = ?''',
                      (full_name, email, phone, course, level, dob, address, sex, 
                       nationality, state, duration, qualification, goals, experience, info_source, reg_id))
            db.commit()
            flash(f"Registration for {full_name} updated successfully.", "success")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            app.logger.error(f"Error updating registration: {e}")
            flash("Error updating registration.", "error")
    
    return render_template("admin/edit_registration.html", registration=registration)


# Unified route to serve SPA shell for all frontend paths
@app.route("/", defaults={'path': ''})
@app.route("/<path:path>")
def home(path):
    # Exclude Static files from catch-all if they fall through
    if path.startswith('static/'):
        return None
        
    return render_template("app.html")

if __name__ == "__main__":
    app.run(debug=os.environ.get('FLASK_DEBUG', False))
