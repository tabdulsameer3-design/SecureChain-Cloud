from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Order, OrderStatus, Invoice, Shipment, AuditLog
from utils import require_role, can_access_order, log_action, get_encryption_service, validate_po_number, validate_amount
from datetime import datetime

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')

# ============================================================
# ORDER ROUTES
# ============================================================

@orders_bp.route('/')
@login_required
def list_orders():
    """List all accessible orders"""
    if current_user.is_admin():
        orders = Order.query.all()
    elif current_user.is_buyer():
        orders = Order.query.filter(
            (Order.creator_id == current_user.id) |
            (Order.shared_with.contains(current_user))
        ).all()
    else:
        orders = Order.query.filter(Order.shared_with.contains(current_user)).all()
    
    return render_template('orders/list.html', orders=orders)

@orders_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_role('buyer', 'admin')
def create_order():
    """Create a new order"""
    if request.method == 'POST':
        po_number = request.form.get('po_number', '').strip()
        vendor_name = request.form.get('vendor_name', '').strip()
        vendor_contact = request.form.get('vendor_contact', '').strip()
        amount = request.form.get('amount', '').strip()
        currency = request.form.get('currency', 'USD')
        description = request.form.get('description', '').strip()
        expected_delivery = request.form.get('expected_delivery')
        
        # Validation
        errors = []
        if not validate_po_number(po_number):
            errors.append('PO number must be at least 3 characters')
        if Order.query.filter_by(po_number=po_number).first():
            errors.append('PO number already exists')
        if not vendor_name:
            errors.append('Vendor name is required')
        if not validate_amount(amount):
            errors.append('Amount must be a positive number')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('orders.create_order'))
        
        # Encrypt sensitive data
        enc_service = get_encryption_service()
        amount_encrypted = enc_service.encrypt(amount)
        vendor_contact_encrypted = enc_service.encrypt(vendor_contact) if vendor_contact else None
        
        order = Order(
            po_number=po_number,
            vendor_name=vendor_name,
            vendor_contact=vendor_contact_encrypted,
            amount_encrypted=amount_encrypted,
            currency=currency,
            description=description,
            expected_delivery=datetime.fromisoformat(expected_delivery) if expected_delivery else None,
            creator_id=current_user.id,
            status=OrderStatus.PENDING.value
        )
        
        try:
            db.session.add(order)
            db.session.commit()
            log_action('created', 'Order', order.id, f'PO: {po_number}')
            flash('Order created successfully!', 'success')
            return redirect(url_for('orders.view_order', order_id=order.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating order: {str(e)}', 'danger')
            return redirect(url_for('orders.create_order'))
    
    return render_template('orders/create.html')

@orders_bp.route('/<int:order_id>')
@login_required
def view_order(order_id):
    """View order details"""
    order = Order.query.get_or_404(order_id)
    if not can_access_order(order):
        flash('You do not have access to this order.', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    # Decrypt sensitive data
    enc_service = get_encryption_service()
    order.amount = enc_service.decrypt(order.amount_encrypted) if order.amount_encrypted else 'N/A'
    order.vendor_contact = enc_service.decrypt(order.vendor_contact) if order.vendor_contact else 'N/A'
    
    log_action('accessed', 'Order', order.id, f'PO: {order.po_number}')
    
    return render_template('orders/detail.html', order=order)

@orders_bp.route('/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    """Edit order"""
    order = Order.query.get_or_404(order_id)
    
    if order.creator_id != current_user.id and not current_user.is_admin():
        flash('You do not have permission to edit this order.', 'danger')
        return redirect(url_for('orders.view_order', order_id=order.id))
    
    if request.method == 'POST':
        order.vendor_name = request.form.get('vendor_name', order.vendor_name)
        order.description = request.form.get('description', order.description)
        status = request.form.get('status', order.status)
        
        if status in [s.value for s in OrderStatus]:
            order.status = status
        
        try:
            db.session.commit()
            log_action('updated', 'Order', order.id, f'Updated order')
            flash('Order updated successfully!', 'success')
            return redirect(url_for('orders.view_order', order_id=order.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating order: {str(e)}', 'danger')
    
    return render_template('orders/edit.html', order=order, statuses=OrderStatus)

@orders_bp.route('/<int:order_id>/share', methods=['POST'])
@login_required
def share_order(order_id):
    """Share order with another user"""
    order = Order.query.get_or_404(order_id)
    
    if order.creator_id != current_user.id and not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    user_id = request.form.get('user_id', type=int)
    from models import User
    user = User.query.get(user_id)
    
    if not user or user == current_user:
        return jsonify({'success': False, 'message': 'Invalid user'}), 400
    
    if user not in order.shared_with:
        order.shared_with.append(user)
        db.session.commit()
        log_action('shared', 'Order', order.id, f'Shared with {user.username}')
        flash(f'Order shared with {user.full_name}', 'success')
    else:
        flash('Order already shared with this user', 'info')
    
    return redirect(url_for('orders.view_order', order_id=order.id))

@orders_bp.route('/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    """Delete order"""
    order = Order.query.get_or_404(order_id)
    
    if order.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    try:
        po_number = order.po_number
        db.session.delete(order)
        db.session.commit()
        log_action('deleted', 'Order', order_id, f'PO: {po_number}')
        flash('Order deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting order: {str(e)}', 'danger')
    
    return redirect(url_for('orders.list_orders'))
