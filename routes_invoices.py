from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Invoice, Order, OrderStatus
from utils import require_role, can_access_order, log_action, get_encryption_service, validate_invoice_number, validate_amount
from datetime import datetime

invoices_bp = Blueprint('invoices', __name__, url_prefix='/invoices')

@invoices_bp.route('/')
@login_required
def list_invoices():
    """List all accessible invoices"""
    if current_user.is_admin():
        invoices = Invoice.query.all()
    else:
        invoices = Invoice.query.filter(Invoice.creator_id == current_user.id).all()
    
    return render_template('invoices/list.html', invoices=invoices)

@invoices_bp.route('/create/<int:order_id>', methods=['GET', 'POST'])
@login_required
@require_role('buyer', 'supplier', 'admin')
def create_invoice(order_id):
    """Create invoice for an order"""
    order = Order.query.get_or_404(order_id)
    
    if not can_access_order(order):
        flash('You do not have access to this order.', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    if request.method == 'POST':
        invoice_number = request.form.get('invoice_number', '').strip()
        amount = request.form.get('amount', '').strip()
        currency = request.form.get('currency', 'USD')
        due_date = request.form.get('due_date')
        description = request.form.get('description', '').strip()
        
        # Validation
        errors = []
        if not validate_invoice_number(invoice_number):
            errors.append('Invoice number must be at least 3 characters')
        if not validate_amount(amount):
            errors.append('Amount must be a positive number')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('invoices.create_invoice', order_id=order_id))
        
        # Encrypt sensitive data
        enc_service = get_encryption_service()
        invoice_number_encrypted = enc_service.encrypt(invoice_number)
        amount_encrypted = enc_service.encrypt(amount)
        
        invoice = Invoice(
            invoice_number_encrypted=invoice_number_encrypted,
            amount_encrypted=amount_encrypted,
            currency=currency,
            due_date=datetime.fromisoformat(due_date) if due_date else None,
            description=description,
            order_id=order_id,
            creator_id=current_user.id,
            payment_status='pending'
        )
        
        try:
            db.session.add(invoice)
            db.session.commit()
            log_action('created', 'Invoice', invoice.id, f'For Order {order.po_number}')
            flash('Invoice created successfully!', 'success')
            return redirect(url_for('invoices.view_invoice', invoice_id=invoice.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating invoice: {str(e)}', 'danger')
            return redirect(url_for('invoices.create_invoice', order_id=order_id))
    
    return render_template('invoices/create.html', order=order)

@invoices_bp.route('/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    """View invoice details"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('invoices.list_invoices'))
    
    # Decrypt sensitive data
    enc_service = get_encryption_service()
    invoice.invoice_number = enc_service.decrypt(invoice.invoice_number_encrypted) if invoice.invoice_number_encrypted else 'N/A'
    invoice.amount = enc_service.decrypt(invoice.amount_encrypted) if invoice.amount_encrypted else 'N/A'
    
    log_action('accessed', 'Invoice', invoice.id, f'Viewed invoice')
    
    return render_template('invoices/detail.html', invoice=invoice)

@invoices_bp.route('/<int:invoice_id>/update-status', methods=['POST'])
@login_required
def update_payment_status(invoice_id):
    """Update invoice payment status"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if invoice.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('invoices.view_invoice', invoice_id=invoice_id))
    
    status = request.form.get('payment_status', 'pending')
    if status in ['pending', 'paid', 'overdue', 'cancelled']:
        invoice.payment_status = status
        db.session.commit()
        log_action('updated', 'Invoice', invoice.id, f'Status changed to {status}')
        flash('Payment status updated!', 'success')
    
    return redirect(url_for('invoices.view_invoice', invoice_id=invoice_id))

@invoices_bp.route('/<int:invoice_id>/delete', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    """Delete invoice"""
    invoice = Invoice.query.get_or_404(invoice_id)
    order_id = invoice.order_id
    
    if invoice.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('invoices.list_invoices'))
    
    try:
        db.session.delete(invoice)
        db.session.commit()
        log_action('deleted', 'Invoice', invoice_id, f'Deleted invoice')
        flash('Invoice deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting invoice: {str(e)}', 'danger')
    
    return redirect(url_for('orders.view_order', order_id=order_id))
