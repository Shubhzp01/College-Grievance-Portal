import os
import csv
import io
import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, g, send_from_directory,
    jsonify, Response, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from database import (
    get_db, close_db, init_db, seed_db, ensure_db_initialized,
    query_db, execute_db, generate_complaint_code
)

# Initialize Flask Application with explicit static configuration
app = Flask(
    __name__,
    static_folder=os.path.join(Config.BASE_DIR, 'static'),
    static_url_path='/static'
)
app.config.from_object(Config)

# Register teardown function to close SQLite connection per request
app.teardown_appcontext(close_db)

# Ensure upload directory exists safely
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except Exception:
    pass

# Initialize database on application startup (essential for serverless environments)
try:
    with app.app_context():
        ensure_db_initialized()
except Exception:
    pass

@app.before_request
def ensure_serverless_db_ready():
    """Self-healing database check for serverless lambda cold starts."""
    try:
        ensure_db_initialized()
    except Exception:
        pass


# ==========================================================
# CUSTOM TEMPLATE FILTERS & CONTEXT PROCESSORS
# ==========================================================

@app.context_processor
def inject_global_context():
    """Injects current logged in user details and current year into all templates."""
    user = None
    if 'user_id' in session:
        user = query_db("SELECT id, name, email, role, department, roll_no FROM users WHERE id = ?", (session['user_id'],), one=True)
    return {
        'current_year': datetime.datetime.now().year,
        'current_user': user,
        'is_logged_in': 'user_id' in session,
        'user_role': session.get('role')
    }

@app.template_filter('status_badge')
def status_badge_filter(status):
    """Returns Bootstrap badge class corresponding to complaint status."""
    badges = {
        'Pending': 'bg-warning text-dark',
        'Under Review': 'bg-info text-dark',
        'In Progress': 'bg-primary text-white',
        'Resolved': 'bg-success text-white',
        'Rejected': 'bg-danger text-white'
    }
    return badges.get(status, 'bg-secondary text-white')

@app.template_filter('priority_badge')
def priority_badge_filter(priority):
    """Returns Bootstrap badge class corresponding to priority level."""
    badges = {
        'Low': 'bg-secondary text-white',
        'Medium': 'bg-info text-dark',
        'High': 'bg-warning text-dark',
        'Urgent': 'bg-danger text-white'
    }
    return badges.get(priority, 'bg-light text-dark')

@app.template_filter('format_datetime')
def format_datetime_filter(value):
    """Formats timestamp string into human readable format."""
    if not value:
        return ''
    try:
        if isinstance(value, str):
            dt = datetime.datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
        else:
            dt = value
        return dt.strftime('%d %b %Y, %I:%M %p')
    except Exception:
        return str(value)


# ==========================================================
# AUTHENTICATION & ACCESS CONTROL DECORATORS
# ==========================================================

def login_required(f):
    """Decorator to ensure user is logged in before accessing route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to restrict access only to users with role='admin'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in as Administrator to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        if session.get('role') != 'admin':
            flash('Access denied. Administrator privileges required.', 'danger')
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """Decorator to restrict access only to users with role='student'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.url))
        if session.get('role') != 'student':
            flash('Access redirected to Admin dashboard.', 'info')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    """Check if uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# ==========================================================
# PUBLIC & GENERAL ROUTES
# ==========================================================

@app.route('/')
def index():
    """
    Landing page showcasing portal overview, key features,
    quick tracking search bar, and live statistics.
    """
    # Fetch live stats for public landing display
    stats = {
        'total': query_db("SELECT COUNT(*) as count FROM complaints", one=True)['count'],
        'resolved': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'Resolved'", one=True)['count'],
        'in_progress': query_db("SELECT COUNT(*) as count FROM complaints WHERE status IN ('In Progress', 'Under Review')", one=True)['count'],
        'students': query_db("SELECT COUNT(*) as count FROM users WHERE role = 'student'", one=True)['count'],
    }
    
    # Calculate resolution percentage
    if stats['total'] > 0:
        stats['res_rate'] = round((stats['resolved'] / stats['total']) * 100, 1)
    else:
        stats['res_rate'] = 100.0

    departments = query_db("SELECT * FROM departments ORDER BY name ASC")
    
    # Recent resolved complaints for public showcase (anonymous or public title)
    recent_resolved = query_db("""
        SELECT complaint_code, category, title, updated_at 
        FROM complaints 
        WHERE status = 'Resolved' 
        ORDER BY updated_at DESC LIMIT 4
    """)
    
    return render_template('index.html', stats=stats, departments=departments, recent_resolved=recent_resolved)


@app.route('/track', methods=['GET', 'POST'])
def track_complaint():
    """
    Public/Student Tracking Route:
    Allows tracking of any complaint by its unique Complaint Code (e.g. CMP-2026-0001).
    Renders status timeline stepper and resolution history.
    """
    code = request.args.get('code', '').strip().upper()
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        if code:
            return redirect(url_for('track_complaint', code=code))

    complaint = None
    timeline = []
    feedback_data = None
    searched = bool(code)

    if code:
        complaint = query_db("""
            SELECT c.*, u.name as student_name, u.roll_no as student_roll, u.department as student_dept
            FROM complaints c
            JOIN users u ON c.user_id = u.id
            WHERE c.complaint_code = ?
        """, (code,), one=True)

        if complaint:
            timeline = query_db("""
                SELECT * FROM complaint_updates
                WHERE complaint_id = ?
                ORDER BY updated_at ASC
            """, (complaint['id'],))

            feedback_data = query_db("""
                SELECT * FROM feedback
                WHERE complaint_id = ?
            """, (complaint['id'],), one=True)
        else:
            flash(f"No complaint found matching ID: '{code}'. Please double check the ID.", "warning")

    return render_template('track.html', code=code, complaint=complaint, timeline=timeline, feedback=feedback_data, searched=searched)


@app.route('/about')
def about():
    """About Page: Redressal mechanism, SLA guidelines, Committee details."""
    departments = query_db("SELECT * FROM departments ORDER BY name ASC")
    return render_template('about.html', departments=departments)


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact & Helpdesk Page with contact details and inquiry form."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if not name or not email or not message:
            flash('Please fill out all required inquiry fields.', 'danger')
        else:
            flash('Thank you for reaching out! The Grievance Cell has received your inquiry and will respond within 24 hours.', 'success')
            return redirect(url_for('contact'))
            
    return render_template('contact.html')


# ==========================================================
# AUTHENTICATION ROUTES (LOGIN, REGISTER, LOGOUT)
# ==========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Student Registration:
    Validates form data, checks for duplicate email or roll number,
    hashes password, and stores new student record.
    """
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))

    departments = query_db("SELECT * FROM departments ORDER BY name ASC")

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        roll_no = request.form.get('roll_no', '').strip().upper()
        department = request.form.get('department', '').strip()

        # Validation checks
        errors = []
        if not name or len(name) < 2:
            errors.append("Please enter a valid full name.")
        if not email or '@' not in email:
            errors.append("Please enter a valid email address.")
        if not roll_no:
            errors.append("Roll number is mandatory for student registration.")
        if not department:
            errors.append("Please select your academic department.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('auth/register.html', departments=departments, form=request.form)

        # Check existing user
        existing_user = query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
        if existing_user:
            flash("An account with this email already exists. Please log in.", "danger")
            return render_template('auth/register.html', departments=departments, form=request.form)

        # Check existing roll number
        existing_roll = query_db("SELECT id FROM users WHERE roll_no = ?", (roll_no,), one=True)
        if existing_roll:
            flash(f"Roll Number '{roll_no}' is already registered. Please check or contact support.", "danger")
            return render_template('auth/register.html', departments=departments, form=request.form)

        # Hash password and insert
        pw_hash = generate_password_hash(password)
        try:
            execute_db("""
                INSERT INTO users (name, email, password_hash, role, roll_no, department, is_active)
                VALUES (?, ?, ?, 'student', ?, ?, 1)
            """, (name, email, pw_hash, roll_no, department))
            
            flash("Account registered successfully! You can now log in.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Error registering account: {str(e)}", "danger")

    return render_template('auth/register.html', departments=departments, form={})


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Session-based User Login:
    Handles authentication for both Students and Admins.
    Validates credentials and active account status.
    """
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember')

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template('auth/login.html', email=email)

        user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)

        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                flash("Your account has been deactivated or blocked. Please contact the administrator.", "danger")
                return render_template('auth/login.html', email=email)

            # Establish Session
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['role'] = user['role']
            session['department'] = user['department']

            # Make session permanent if remember me is checked
            if remember:
                session.permanent = True

            flash(f"Welcome back, {user['name']}!", "success")
            
            # Check redirect url if any
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid email address or password.", "danger")

    return render_template('auth/login.html')


@app.route('/logout')
def logout():
    """Clears user session and logs out."""
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for('login'))


# ==========================================================
# STUDENT PORTAL ROUTES
# ==========================================================

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    """
    Student Dashboard:
    Shows summary metrics of student's complaints, quick action links,
    and the latest submitted complaints.
    """
    student_id = session['user_id']
    
    # Counts
    stats = {
        'total': query_db("SELECT COUNT(*) as count FROM complaints WHERE user_id = ?", (student_id,), one=True)['count'],
        'pending': query_db("SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'Pending'", (student_id,), one=True)['count'],
        'in_progress': query_db("SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status IN ('Under Review', 'In Progress')", (student_id,), one=True)['count'],
        'resolved': query_db("SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'Resolved'", (student_id,), one=True)['count'],
        'rejected': query_db("SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'Rejected'", (student_id,), one=True)['count'],
    }

    # Recent complaints
    recent_complaints = query_db("""
        SELECT c.*, f.rating as feedback_rating
        FROM complaints c
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC LIMIT 5
    """, (student_id,))

    return render_template('student/dashboard.html', stats=stats, recent_complaints=recent_complaints)


@app.route('/student/complaint/new', methods=['GET', 'POST'])
@student_required
def submit_complaint():
    """
    Complaint Submission Page:
    Accepts title, category, description, priority, optional file attachment,
    and anonymous toggle. Generates unique Complaint ID.
    """
    departments = query_db("SELECT * FROM departments ORDER BY name ASC")

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        priority = request.form.get('priority', 'Medium').strip()
        description = request.form.get('description', '').strip()
        is_anonymous = 1 if request.form.get('is_anonymous') == '1' else 0

        # Validations
        errors = []
        if not title or len(title) < 5:
            errors.append("Complaint title must be at least 5 characters long.")
        if not category:
            errors.append("Please select a relevant category.")
        if priority not in ['Low', 'Medium', 'High', 'Urgent']:
            errors.append("Invalid priority level.")
        if not description or len(description) < 15:
            errors.append("Please describe your issue in detail (at least 15 characters).")

        # File upload handling
        attachment_filename = None
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    original_name = secure_filename(file.filename)
                    timestamp_prefix = datetime.datetime.now().strftime('%Y%m%d%H%M%S_')
                    attachment_filename = f"{timestamp_prefix}{original_name}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], attachment_filename)
                    file.save(file_path)
                else:
                    errors.append("Invalid file format. Only JPG, PNG, and PDF files are allowed.")

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('student/submit_complaint.html', departments=departments, form=request.form)

        # Auto-generate unique Complaint Code
        complaint_code = generate_complaint_code()
        user_id = session['user_id']
        user_name = session.get('user_name', 'Student')

        # Insert Complaint Record
        complaint_id = execute_db("""
            INSERT INTO complaints (
                complaint_code, user_id, title, category, description,
                priority, status, attachment, is_anonymous, assigned_to,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?, ?, 'Grievance Cell', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (complaint_code, user_id, title, category, description, priority, attachment_filename, is_anonymous))

        # Insert Initial Update in Timeline
        initial_remark = "Complaint registered by student." if not is_anonymous else "Complaint submitted anonymously."
        execute_db("""
            INSERT INTO complaint_updates (complaint_id, status, remark, updated_by, updated_at)
            VALUES (?, 'Pending', ?, ?, CURRENT_TIMESTAMP)
        """, (complaint_id, initial_remark, user_name if not is_anonymous else 'Anonymous Student'))

        flash(f"Complaint submitted successfully! Your tracking code is: {complaint_code}", "success")
        return redirect(url_for('student_complaint_detail', id=complaint_id))

    return render_template('student/submit_complaint.html', departments=departments, form={})


@app.route('/student/complaints')
@student_required
def student_complaints():
    """
    My Complaints list for the logged-in student:
    Supports filtering by status, category, keyword search, and pagination.
    """
    student_id = session['user_id']
    status_filter = request.args.get('status', '').strip()
    category_filter = request.args.get('category', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 8

    query = """
        SELECT c.*, f.rating as feedback_rating
        FROM complaints c
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE c.user_id = ?
    """
    params = [student_id]

    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)

    if category_filter:
        query += " AND c.category = ?"
        params.append(category_filter)

    if search:
        query += " AND (c.complaint_code LIKE ? OR c.title LIKE ? OR c.description LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    # Count total for pagination
    count_query = f"SELECT COUNT(*) as count FROM ({query})"
    total_count = query_db(count_query, params, one=True)['count']
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    # Paginated query
    query += " ORDER BY c.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    complaints = query_db(query, params)
    departments = query_db("SELECT * FROM departments ORDER BY name ASC")

    return render_template(
        'student/my_complaints.html',
        complaints=complaints,
        departments=departments,
        status_filter=status_filter,
        category_filter=category_filter,
        search=search,
        page=page,
        total_pages=total_pages,
        total_count=total_count
    )


@app.route('/student/complaint/<int:id>')
@student_required
def student_complaint_detail(id):
    """
    Detailed view of a student's own complaint:
    Displays complaint specifications, attachment preview link,
    complete resolution timeline stepper, and feedback block.
    """
    student_id = session['user_id']
    complaint = query_db("""
        SELECT c.*, u.name as student_name, u.roll_no as student_roll, u.department as student_dept
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = ? AND c.user_id = ?
    """, (id, student_id), one=True)

    if not complaint:
        flash("Complaint not found or you do not have permission to view it.", "danger")
        return redirect(url_for('student_complaints'))

    timeline = query_db("""
        SELECT * FROM complaint_updates
        WHERE complaint_id = ?
        ORDER BY updated_at ASC
    """, (id,))

    feedback_data = query_db("""
        SELECT * FROM feedback
        WHERE complaint_id = ?
    """, (id,), one=True)

    return render_template('student/complaint_detail.html', complaint=complaint, timeline=timeline, feedback=feedback_data)


@app.route('/student/complaint/<int:id>/feedback', methods=['POST'])
@student_required
def submit_feedback(id):
    """
    Student submits 1-5 star rating and feedback comment for a Resolved complaint.
    """
    student_id = session['user_id']
    complaint = query_db("SELECT * FROM complaints WHERE id = ? AND user_id = ?", (id, student_id), one=True)

    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for('student_complaints'))

    if complaint['status'] != 'Resolved':
        flash("Feedback can only be submitted once the complaint is Resolved.", "warning")
        return redirect(url_for('student_complaint_detail', id=id))

    existing_feedback = query_db("SELECT id FROM feedback WHERE complaint_id = ?", (id,), one=True)
    if existing_feedback:
        flash("You have already submitted feedback for this complaint.", "info")
        return redirect(url_for('student_complaint_detail', id=id))

    try:
        rating = int(request.form.get('rating', 0))
        comment = request.form.get('comment', '').strip()

        if rating < 1 or rating > 5:
            flash("Please choose a rating between 1 and 5 stars.", "danger")
            return redirect(url_for('student_complaint_detail', id=id))

        execute_db("""
            INSERT INTO feedback (complaint_id, rating, comment, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (id, rating, comment))

        flash("Thank you for your feedback! It helps improve college services.", "success")
    except Exception as e:
        flash(f"Error saving feedback: {str(e)}", "danger")

    return redirect(url_for('student_complaint_detail', id=id))


# ==========================================================
# ADMIN PORTAL ROUTES
# ==========================================================

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """
    Administrator Dashboard:
    Provides high-level KPIs, summary statistics, chart feeds,
    and recent activity timeline.
    """
    stats = {
        'total': query_db("SELECT COUNT(*) as count FROM complaints", one=True)['count'],
        'pending': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'Pending'", one=True)['count'],
        'under_review': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'Under Review'", one=True)['count'],
        'in_progress': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'In Progress'", one=True)['count'],
        'resolved': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'Resolved'", one=True)['count'],
        'rejected': query_db("SELECT COUNT(*) as count FROM complaints WHERE status = 'Rejected'", one=True)['count'],
        'total_users': query_db("SELECT COUNT(*) as count FROM users WHERE role = 'student'", one=True)['count'],
    }

    # Calculate average satisfaction rating
    avg_rating_row = query_db("SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM feedback", one=True)
    stats['avg_rating'] = round(avg_rating_row['avg_rating'], 1) if avg_rating_row['avg_rating'] else 0.0
    stats['total_feedbacks'] = avg_rating_row['count']

    # Urgent and high priority complaints requiring attention
    urgent_complaints = query_db("""
        SELECT c.*, u.name as student_name
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.priority IN ('Urgent', 'High') AND c.status NOT IN ('Resolved', 'Rejected')
        ORDER BY CASE c.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 ELSE 3 END, c.created_at ASC
        LIMIT 5
    """)

    # Recent complaints
    recent_complaints = query_db("""
        SELECT c.*, u.name as student_name, u.roll_no as student_roll
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at DESC LIMIT 6
    """)

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        urgent_complaints=urgent_complaints,
        recent_complaints=recent_complaints
    )


@app.route('/admin/api/chart-data')
@admin_required
def admin_chart_data():
    """
    JSON API for Chart.js rendering on the admin dashboard:
    Returns status distribution, category breakdown, and priority split.
    """
    # 1. Complaints by Status
    status_rows = query_db("""
        SELECT status, COUNT(*) as count
        FROM complaints
        GROUP BY status
    """)
    status_dict = {'Pending': 0, 'Under Review': 0, 'In Progress': 0, 'Resolved': 0, 'Rejected': 0}
    for r in status_rows:
        status_dict[r['status']] = r['count']

    # 2. Complaints by Category
    cat_rows = query_db("""
        SELECT category, COUNT(*) as count
        FROM complaints
        GROUP BY category
        ORDER BY count DESC
    """)
    categories = [r['category'] for r in cat_rows]
    category_counts = [r['count'] for r in cat_rows]

    # 3. Complaints by Priority
    prio_rows = query_db("""
        SELECT priority, COUNT(*) as count
        FROM complaints
        GROUP BY priority
    """)
    prio_dict = {'Low': 0, 'Medium': 0, 'High': 0, 'Urgent': 0}
    for r in prio_rows:
        prio_dict[r['priority']] = r['count']

    return jsonify({
        'status': {
            'labels': list(status_dict.keys()),
            'data': list(status_dict.values())
        },
        'category': {
            'labels': categories,
            'data': category_counts
        },
        'priority': {
            'labels': list(prio_dict.keys()),
            'data': list(prio_dict.values())
        }
    })


@app.route('/admin/complaints')
@admin_required
def admin_complaints():
    """
    Admin Manage Complaints Page:
    Full searchable, filterable, and paginated complaint table.
    """
    status_filter = request.args.get('status', '').strip()
    category_filter = request.args.get('category', '').strip()
    priority_filter = request.args.get('priority', '').strip()
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10

    query = """
        SELECT c.*, u.name as student_name, u.roll_no as student_roll, u.department as student_dept,
               f.rating as feedback_rating
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE 1=1
    """
    params = []

    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)

    if category_filter:
        query += " AND c.category = ?"
        params.append(category_filter)

    if priority_filter:
        query += " AND c.priority = ?"
        params.append(priority_filter)

    if search:
        query += " AND (c.complaint_code LIKE ? OR c.title LIKE ? OR c.description LIKE ? OR u.name LIKE ? OR u.roll_no LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term, term])

    # Count total for pagination
    count_query = f"SELECT COUNT(*) as count FROM ({query})"
    total_count = query_db(count_query, params, one=True)['count']
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    # Paginated query
    query += " ORDER BY c.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    complaints = query_db(query, params)
    departments = query_db("SELECT * FROM departments ORDER BY name ASC")

    return render_template(
        'admin/manage_complaints.html',
        complaints=complaints,
        departments=departments,
        status_filter=status_filter,
        category_filter=category_filter,
        priority_filter=priority_filter,
        search=search,
        page=page,
        total_pages=total_pages,
        total_count=total_count
    )


@app.route('/admin/complaint/<int:id>')
@admin_required
def admin_complaint_detail(id):
    """
    Admin Complaint Review and Action Page:
    Inspects full complaint details, attachments, history timeline,
    and provides the interface to assign staff and update status with remarks.
    """
    complaint = query_db("""
        SELECT c.*, u.name as student_name, u.email as student_email,
               u.roll_no as student_roll, u.department as student_dept, u.is_active as student_active
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = ?
    """, (id,), one=True)

    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for('admin_complaints'))

    timeline = query_db("""
        SELECT * FROM complaint_updates
        WHERE complaint_id = ?
        ORDER BY updated_at ASC
    """, (id,))

    feedback_data = query_db("""
        SELECT * FROM feedback
        WHERE complaint_id = ?
    """, (id,), one=True)

    departments = query_db("SELECT * FROM departments ORDER BY name ASC")

    return render_template(
        'admin/complaint_detail.html',
        complaint=complaint,
        timeline=timeline,
        feedback=feedback_data,
        departments=departments
    )


@app.route('/admin/complaint/<int:id>/update', methods=['POST'])
@admin_required
def admin_update_complaint(id):
    """
    Process Admin Complaint Status Update:
    Transitions status, updates assigned department/staff,
    and appends remark to complaint_updates timeline.
    """
    complaint = query_db("SELECT * FROM complaints WHERE id = ?", (id,), one=True)
    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for('admin_complaints'))

    new_status = request.form.get('status', '').strip()
    assigned_to = request.form.get('assigned_to', '').strip()
    remark = request.form.get('remark', '').strip()

    valid_statuses = ['Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected']
    if new_status not in valid_statuses:
        flash("Invalid status selected.", "danger")
        return redirect(url_for('admin_complaint_detail', id=id))

    if not remark:
        flash("Please provide an action remark explaining this update.", "danger")
        return redirect(url_for('admin_complaint_detail', id=id))

    admin_name = session.get('user_name', 'Administrator')

    # Update complaint master table
    execute_db("""
        UPDATE complaints
        SET status = ?, assigned_to = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_status, assigned_to or complaint['assigned_to'], id))

    # Append timeline step
    execute_db("""
        INSERT INTO complaint_updates (complaint_id, status, remark, updated_by, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (id, new_status, remark, admin_name))

    flash(f"Complaint {complaint['complaint_code']} updated to '{new_status}' successfully.", "success")
    return redirect(url_for('admin_complaint_detail', id=id))


@app.route('/admin/complaint/<int:id>/delete', methods=['POST'])
@admin_required
def admin_delete_complaint(id):
    """Admin Delete Complaint Action."""
    complaint = query_db("SELECT * FROM complaints WHERE id = ?", (id,), one=True)
    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for('admin_complaints'))

    code = complaint['complaint_code']
    
    # Delete attachment file if exists
    if complaint['attachment']:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], complaint['attachment'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass

    execute_db("DELETE FROM complaints WHERE id = ?", (id,))
    flash(f"Complaint {code} has been deleted permanently.", "info")
    return redirect(url_for('admin_complaints'))


@app.route('/admin/export/complaints.csv')
@admin_required
def admin_export_csv():
    """
    Exports all or filtered complaints as a downloadable CSV spreadsheet.
    """
    status_filter = request.args.get('status', '').strip()
    category_filter = request.args.get('category', '').strip()

    query = """
        SELECT c.complaint_code, c.title, c.category, c.priority, c.status,
               CASE WHEN c.is_anonymous = 1 THEN 'Anonymous' ELSE u.name END as student_name,
               CASE WHEN c.is_anonymous = 1 THEN 'N/A' ELSE u.roll_no END as student_roll,
               CASE WHEN c.is_anonymous = 1 THEN 'N/A' ELSE u.department END as student_dept,
               c.assigned_to, c.created_at, c.updated_at,
               f.rating as feedback_rating, f.comment as feedback_comment
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE 1=1
    """
    params = []
    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)
    if category_filter:
        query += " AND c.category = ?"
        params.append(category_filter)

    query += " ORDER BY c.created_at DESC"
    records = query_db(query, params)

    # Generate CSV in-memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # CSV Header Row
    writer.writerow([
        'Complaint ID', 'Title', 'Category', 'Priority', 'Status',
        'Student Name', 'Roll Number', 'Department', 'Assigned To',
        'Date Registered', 'Last Updated', 'Feedback Rating (1-5)', 'Feedback Comment'
    ])

    for row in records:
        writer.writerow([
            row['complaint_code'],
            row['title'],
            row['category'],
            row['priority'],
            row['status'],
            row['student_name'],
            row['student_roll'],
            row['student_dept'],
            row['assigned_to'] or 'Unassigned',
            row['created_at'],
            row['updated_at'],
            row['feedback_rating'] if row['feedback_rating'] else 'N/A',
            row['feedback_comment'] if row['feedback_comment'] else ''
        ])

    csv_data = output.getvalue()
    output.close()

    filename = f"Complaints_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@app.route('/admin/users')
@admin_required
def admin_users():
    """
    User Management:
    View all registered student and admin profiles, active status,
    and toggle account active/blocked status.
    """
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()

    query = """
        SELECT u.*, COUNT(c.id) as complaints_count
        FROM users u
        LEFT JOIN complaints c ON u.id = c.user_id
        WHERE 1=1
    """
    params = []

    if role_filter:
        query += " AND u.role = ?"
        params.append(role_filter)

    if search:
        query += " AND (u.name LIKE ? OR u.email LIKE ? OR u.roll_no LIKE ? OR u.department LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " GROUP BY u.id ORDER BY u.created_at DESC"
    users = query_db(query, params)

    return render_template('admin/manage_users.html', users=users, search=search, role_filter=role_filter)


@app.route('/admin/user/<int:id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_user_status(id):
    """
    Toggle user active/blocked status. Prevents blocking the main default admin.
    """
    user = query_db("SELECT * FROM users WHERE id = ?", (id,), one=True)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin_users'))

    if user['email'] == 'admin@college.com':
        flash("Cannot deactivate root administrator account.", "danger")
        return redirect(url_for('admin_users'))

    new_status = 0 if user['is_active'] == 1 else 1
    execute_db("UPDATE users SET is_active = ? WHERE id = ?", (new_status, id))

    action_text = "activated" if new_status == 1 else "blocked/deactivated"
    flash(f"User account '{user['name']}' has been {action_text}.", "success")
    return redirect(url_for('admin_users'))


@app.route('/admin/departments', methods=['GET', 'POST'])
@admin_required
def admin_departments():
    """
    Manage College Departments:
    View existing complaint categories / departments, add new ones, or delete.
    """
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            if not name:
                flash("Department name cannot be empty.", "danger")
            else:
                try:
                    execute_db("INSERT INTO departments (name) VALUES (?)", (name,))
                    flash(f"Department '{name}' added successfully.", "success")
                except Exception:
                    flash(f"Department '{name}' already exists.", "warning")
        elif action == 'delete':
            dept_id = request.form.get('department_id')
            if dept_id:
                execute_db("DELETE FROM departments WHERE id = ?", (dept_id,))
                flash("Department deleted.", "info")
        return redirect(url_for('admin_departments'))

    departments = query_db("""
        SELECT d.*, COUNT(c.id) as complaints_count
        FROM departments d
        LEFT JOIN complaints c ON d.name = c.category
        GROUP BY d.id
        ORDER BY d.name ASC
    """)

    return render_template('admin/departments.html', departments=departments)


# ==========================================================
# FILE DOWNLOAD & ERROR HANDLING ROUTES
# ==========================================================

@app.route('/static/<path:filename>')
def serve_static_asset(filename):
    """Explicitly serves static CSS/JS/images on serverless cloud platforms."""
    static_dir = os.path.join(Config.BASE_DIR, 'static')
    return send_from_directory(static_dir, filename)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Safely serves uploaded attachments."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.errorhandler(404)
def page_not_found(e):
    """Custom 404 Error Page."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    """Custom 500 Error Page."""
    return render_template('500.html'), 500


@app.errorhandler(403)
def access_forbidden(e):
    """Custom 403 Error Page."""
    return render_template('404.html', message="Access Forbidden"), 403


# ==========================================================
# APPLICATION BOOTSTRAPPER & ENTRY POINT
# ==========================================================

if __name__ == '__main__':
    # Initialize DB & Seed default credentials + sample data
    with app.app_context():
        init_db()
        seed_db()
    print("=" * 65)
    print(" COLLEGE COMPLAINT REGISTRATION & RESOLUTION PORTAL ")
    print("=" * 65)
    print(" Server running on: http://127.0.0.1:5000")
    print(" Default Admin: admin@college.com | Password: Admin@123")
    print(" Sample Student: rahul.sharma@college.com | Password: Student@123")
    print("=" * 65)
    app.run(debug=True, host='127.0.0.1', port=5000)
