from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Shipment, ShipmentStatus, Order
from utils import require_role, can_access_order, log_action
from datetime import datetime

shipments_bp = Blueprint('shipments', __name__, url_prefix='/shipments')

@shipments_bp.route('/')
@login_required
def list_shipments():
    """List all accessible shipments"""
    if current_user.is_admin():
        shipments = Shipment.query.all()
    elif current_user.is_supplier():
        shipments = Shipment.query.filter(Shipment.creator_id == current_user.id).all()
    else:
        # Buyers see shipments for their orders
        shipments = db.session.query(Shipment).join(Order).filter(
            Order.creator_id == current_user.id
        ).all()
    
    return render_template('shipments/list.html', shipments=shipments)

@shipments_bp.route('/create/<int:order_id>', methods=['GET', 'POST'])
@login_required
@require_role('supplier', 'admin')
def create_shipment(order_id):
    """Create shipment for an order"""
    order = Order.query.get_or_404(order_id)
    
    if request.method == 'POST':
        tracking_id = request.form.get('tracking_id', '').strip()
        carrier = request.form.get('carrier', '').strip()
        items_description = request.form.get('items_description', '').strip()
        quantity = request.form.get('quantity', type=int)
        weight_kg = request.form.get('weight_kg', type=float)
        expected_delivery = request.form.get('expected_delivery')
        notes = request.form.get('notes', '').strip()
        
        # Validation
        errors = []
        if not tracking_id or len(tracking_id) < 3:
            errors.append('Tracking ID must be at least 3 characters')
        if Shipment.query.filter_by(tracking_id=tracking_id).first():
            errors.append('Tracking ID already exists')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('shipments.create_shipment', order_id=order_id))
        
        shipment = Shipment(
            tracking_id=tracking_id,
            carrier=carrier,
            items_description=items_description,
            quantity=quantity,
            weight_kg=weight_kg,
            expected_delivery=datetime.fromisoformat(expected_delivery) if expected_delivery else None,
            notes=notes,
            order_id=order_id,
            creator_id=current_user.id,
            status=ShipmentStatus.PENDING.value
        )
        
        try:
            db.session.add(shipment)
            db.session.commit()
            log_action('created', 'Shipment', shipment.id, f'Tracking: {tracking_id}')
            flash('Shipment created successfully!', 'success')
            return redirect(url_for('shipments.view_shipment', shipment_id=shipment.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating shipment: {str(e)}', 'danger')
            return redirect(url_for('shipments.create_shipment', order_id=order_id))
    
    return render_template('shipments/create.html', order=order)

@shipments_bp.route('/<int:shipment_id>')
@login_required
def view_shipment(shipment_id):
    """View shipment details"""
    shipment = Shipment.query.get_or_404(shipment_id)
    
    # Check access
    if not (current_user.is_admin() or 
            shipment.creator_id == current_user.id or 
            shipment.order.creator_id == current_user.id):
        flash('Permission denied', 'danger')
        return redirect(url_for('shipments.list_shipments'))
    
    log_action('accessed', 'Shipment', shipment.id, f'Tracking: {shipment.tracking_id}')
    
    return render_template('shipments/detail.html', shipment=shipment)

@shipments_bp.route('/<int:shipment_id>/update-status', methods=['POST'])
@login_required
def update_shipment_status(shipment_id):
    """Update shipment status"""
    shipment = Shipment.query.get_or_404(shipment_id)
    
    if shipment.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('shipments.view_shipment', shipment_id=shipment_id))
    
    status = request.form.get('status', 'pending')
    valid_statuses = [s.value for s in ShipmentStatus]
    
    if status in valid_statuses:
        shipment.status = status
        
        if status == ShipmentStatus.DELIVERED.value:
            shipment.actual_delivery = datetime.utcnow()
        
        db.session.commit()
        log_action('updated', 'Shipment', shipment.id, f'Status: {status}')
        flash('Shipment status updated!', 'success')
    
    return redirect(url_for('shipments.view_shipment', shipment_id=shipment_id))

@shipments_bp.route('/<int:shipment_id>/delete', methods=['POST'])
@login_required
def delete_shipment(shipment_id):
    """Delete shipment"""
    shipment = Shipment.query.get_or_404(shipment_id)
    order_id = shipment.order_id
    
    if shipment.creator_id != current_user.id and not current_user.is_admin():
        flash('Permission denied', 'danger')
        return redirect(url_for('shipments.list_shipments'))
    
    try:
        tracking_id = shipment.tracking_id
        db.session.delete(shipment)
        db.session.commit()
        log_action('deleted', 'Shipment', shipment_id, f'Tracking: {tracking_id}')
        flash('Shipment deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting shipment: {str(e)}', 'danger')
    
    return redirect(url_for('orders.view_order', order_id=order_id))
