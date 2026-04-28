from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user, login_required
from flask_socketio import SocketIO
from config import Config
from app.models import db, User, AuditLog
from auth import auth_bp
from routes import orders_bp, invoices_bp, shipments_bp, files_bp, main_bp
from socket_events import register_socket_events
import os

# ============================================================
# APP INITIALIZATION
# ============================================================

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")
register_socket_events(socketio)

# ============================================================
# BLUEPRINT REGISTRATION
# ============================================================

# Auth blueprint
app.register_blueprint(auth_bp)

# Core routes
app.register_blueprint(main_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(invoices_bp)
app.register_blueprint(shipments_bp)
app.register_blueprint(files_bp)

# ============================================================
# INITIALIZATION HELPERS
# ============================================================

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Load user from database"""
    return User.query.get(int(user_id))

# Create database tables on app context
with app.app_context():
    db.create_all()

# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    from flask import render_template
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors"""
    from flask import render_template
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    from flask import render_template
    return render_template('errors/500.html'), 500

# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)