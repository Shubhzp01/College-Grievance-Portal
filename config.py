import os

class Config:
    """
    Application Configuration Class
    Holds basic application parameters, secret keys, file upload restrictions,
    and database paths.
    """
    # Secret key for session management and CSRF protection
    SECRET_KEY = os.environ.get('SECRET_KEY', 'college_complaint_portal_secret_key_2026_!@#$%')
    
    # Base directory of the project
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Database configuration (SQLite)
    DATABASE_PATH = os.path.join(BASE_DIR, 'complaints.db')
    
    # File upload configurations
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 Megabytes maximum upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
    # Pagination settings
    COMPLAINTS_PER_PAGE = 10
