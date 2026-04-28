from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from models import db, File, Order
from utils import require_role, allowed_file, get_file_size_mb, log_action, can_access_order
from datetime import datetime
from werkzeug.utils import secure_filename
import os

files_bp = Blueprint('files', __name__, url_prefix='/files')

@files_bp.route('/')
@login_required
def list_files():
    """List all accessible files"""
    if current_user.is_admin():
        files = File.query.all()
    else:
        files = File.query.filter(
            (File.uploader_id == current_user.id) |
            (File.shared_with_users.contains(current_user))
        ).all()
    
    return render_template('files/list.html', files=files)

@files_bp.route('/upload/<int:order_id>', methods=['GET', 'POST'])
@login_required
def upload_file(order_id):
    """Upload file to an order"""
    order = Order.query.get_or_404(order_id)
    
    if not can_access_order(order):
        flash('You do not have access to this order.', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('files.upload_file', order_id=order_id))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('files.upload_file', order_id=order_id))
        
        if not allowed_file(file.filename):
            flash(f'File type not allowed. Allowed types: {", ".join(["pdf", "docx", "xlsx", "csv", "txt", "jpg", "png", "zip"])}', 'danger')
            return redirect(url_for('files.upload_file', order_id=order_id))
        
        # Check file size
        file_size_mb = get_file_size_mb(file)
        if file_size_mb > 50:
            flash('File size exceeds 50MB limit', 'danger')
            return redirect(url_for('files.upload_file', order_id=order_id))
        
        try:
            original_filename = secure_filename(file.filename)
            # Create unique filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + original_filename
            
            # Create uploads directory if needed
            os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            file_type = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'unknown'
            
            file_obj = File(
                filename=filename,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                file_type=file_type,
                uploader_id=current_user.id,
                order_id=order_id
            )
            
            db.session.add(file_obj)
            db.session.commit()
            log_action('uploaded', 'File', file_obj.id, f'File: {original_filename}')
            flash('File uploaded successfully!', 'success')
            return redirect(url_for('orders.view_order', order_id=order_id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error uploading file: {str(e)}', 'danger')
            return redirect(url_for('files.upload_file', order_id=order_id))
    
    return render_template('files/upload.html', order=order)

@files_bp.route('/<int:file_id>/download')
@login_required
def download_file(file_id):
    """Download a file"""
    file_obj = File.query.get_or_404(file_id)
    
    # Check access
    if not (current_user.is_admin() or 
            file_obj.uploader_id == current_user.id or 
            current_user in file_obj.shared_with_users):
        flash('Permission denied', 'danger')
        return redirect(url_for('files.list_files'))
    
    log_action('downloaded', 'File', file_obj.id, f'File: {file_obj.original_filename}')
    
    return send_file(file_obj.file_path, as_attachment=True, download_name=file_obj.original_filename)

@files_bp.route('/<int:file_id>/share', methods=['POST'])
@login_required
def share_file(file_id):
    """Share file with another user"""
    file_obj = File.query.get_or_404(file_id)
    
    if file_obj.uploader_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('files.list_files'))
    
    user_id = request.form.get('user_id', type=int)
    from models import User
    user = User.query.get(user_id)
    
    if not user or user == current_user:
        flash('Invalid user', 'danger')
        return redirect(url_for('orders.view_order', order_id=file_obj.order_id))
    
    if user not in file_obj.shared_with_users:
        file_obj.shared_with_users.append(user)
        db.session.commit()
        log_action('shared', 'File', file_obj.id, f'Shared with {user.username}')
        flash(f'File shared with {user.full_name}', 'success')
    else:
        flash('File already shared with this user', 'info')
    
    return redirect(url_for('orders.view_order', order_id=file_obj.order_id))

@files_bp.route('/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_file(file_id):
    """Delete file"""
    file_obj = File.query.get_or_404(file_id)
    order_id = file_obj.order_id
    
    if file_obj.uploader_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('files.list_files'))
    
    try:
        # Delete file from filesystem
        if os.path.exists(file_obj.file_path):
            os.remove(file_obj.file_path)
        
        db.session.delete(file_obj)
        db.session.commit()
        log_action('deleted', 'File', file_id, f'File: {file_obj.original_filename}')
        flash('File deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting file: {str(e)}', 'danger')
    
    return redirect(url_for('orders.view_order', order_id=order_id))
