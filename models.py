"""
Compatibility shim for legacy root-level imports.
For new code, import from app.models instead.
"""

from app.models import (
    db,
    User,
    UserRole,
    Order,
    OrderStatus,
    order_shared_with,
    Invoice,
    Shipment,
    ShipmentStatus,
    File,
    file_shared_with,
    AuditLog,
)

__all__ = [
    'db',
    'User', 'UserRole',
    'Order', 'OrderStatus', 'order_shared_with',
    'Invoice',
    'Shipment', 'ShipmentStatus',
    'File', 'file_shared_with',
    'AuditLog'
]

