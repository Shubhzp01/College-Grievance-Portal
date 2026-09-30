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
    
    # Detect serverless environment (e.g. Vercel, AWS Lambda) where root is read-only
    IS_SERVERLESS = bool(
        os.environ.get('VERCEL') or
        os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or
        os.environ.get('LAMBDA_TASK_ROOT') or
        not os.access(BASE_DIR, os.W_OK)
    )
    
    # Database and uploads path
    # On serverless platforms, only /tmp is writable
    if IS_SERVERLESS:
        DATABASE_PATH = '/tmp/complaints.db'
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'complaints.db'))
        UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    
    # File upload configurations
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 Megabytes maximum upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
    # Pagination settings
    COMPLAINTS_PER_PAGE = 10
