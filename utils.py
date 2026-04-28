from functools import wraps
from flask import abort, current_app
from flask_login import current_user
from app.models import db, AuditLog
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import hashlib

# ============================================================
# RBAC & ACCESS CONTROL
# ============================================================

def require_role(*roles):
    """Decorator to restrict access by role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def can_access_order(order):
    """Check if current user can access an order"""
    if current_user.is_admin():
        return True
    return order.creator_id == current_user.id or current_user in order.shared_with

def can_access_resource(resource, user_id_field='creator_id'):
    """Generic resource access check"""
    if current_user.is_admin():
        return True
    if getattr(resource, user_id_field) == current_user.id:
        return True
    if hasattr(resource, 'shared_with') and current_user in resource.shared_with:
        return True
    return False

# ============================================================
# ENCRYPTION UTILITIES
# ============================================================

class EncryptionService:
    """Service for encrypting/decrypting sensitive data"""
    
    def __init__(self):
        """Initialize encryption with app key"""
        key = current_app.config.get('ENCRYPTION_KEY', 'dev-encryption-key-32-chars-long!!')
        # Ensure key is 32 bytes for Fernet
        key_hash = hashlib.sha256(key.encode()).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(key_hash))
    
    def encrypt(self, plaintext):
        """Encrypt plaintext string"""
        if not plaintext:
            return None
        return self.cipher.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext):
        """Decrypt ciphertext string"""
        if not ciphertext:
            return None
        try:
            return self.cipher.decrypt(ciphertext.encode()).decode()
        except:
            return None

def get_encryption_service():
    """Get encryption service instance"""
    return EncryptionService()

# ============================================================
# AUDIT LOGGING
# ============================================================

def log_action(action, resource_type, resource_id, details=None):
    """Log an action for audit trail"""
    try:
        audit_entry = AuditLog(
            action=action,
            user_id=current_user.id if current_user.is_authenticated else None,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            timestamp=datetime.utcnow()
        )
        db.session.add(audit_entry)
        db.session.commit()
    except Exception as e:
        print(f"Audit logging error: {e}")

# ============================================================
# FILE UTILITIES
# ============================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = current_app.config.get('ALLOWED_EXTENSIONS', {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'jpg', 'jpeg', 'png', 'zip'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_size_mb(file):
    """Get file size in MB"""
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    return size / (1024 * 1024)

# ============================================================
# DATA VALIDATION
# ============================================================

def validate_po_number(po_number):
    """Validate PO number format"""
    return len(po_number.strip()) >= 3

def validate_invoice_number(invoice_number):
    """Validate invoice number format"""
    return len(invoice_number.strip()) >= 3

def validate_amount(amount):
    """Validate monetary amount"""
    try:
        val = float(amount)
        return val > 0
    except:
        return False
