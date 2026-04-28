from flask import request, session
from flask_socketio import emit, join_room, leave_room, disconnect
from flask_login import current_user
from app.models import db, Order, User
from utils import log_action
from datetime import datetime

def register_socket_events(socketio):
    """Register WebSocket event handlers"""
    
    @socketio.on('connect')
    def on_connect():
        """Handle client connection"""
        try:
            if current_user.is_authenticated:
                print(f'[Socket.IO] User {current_user.username} connected (SID: {request.sid})')
                return True
            else:
                print(f'[Socket.IO] Unauthenticated connection attempt (SID: {request.sid})')
                disconnect()
                return False
        except Exception as e:
            print(f'[Socket.IO] Connection error: {str(e)}')
            disconnect()
            return False
    
    @socketio.on('disconnect')
    def on_disconnect():
        """Handle client disconnection"""
        try:
            if current_user.is_authenticated:
                print(f'[Socket.IO] User {current_user.username} disconnected (SID: {request.sid})')
        except Exception as e:
            print(f'[Socket.IO] Disconnect error: {str(e)}')
    
    @socketio.on('join_order_chat')
    def on_join_order_chat(data):
        """User joins order chat room"""
        try:
            if not current_user.is_authenticated:
                emit('error', {'message': 'Not authenticated'})
                return
            
            order_id = data.get('order_id')
            order = Order.query.get(order_id)
            
            if not order:
                emit('error', {'message': 'Order not found'})
                return
            
            # Check if user has access to this order
            if not (current_user.is_admin() or 
                    order.creator_id == current_user.id or 
                    current_user in order.shared_with):
                emit('error', {'message': 'Access denied'})
                return
            
            room = f'order_{order_id}'
            join_room(room)
            
            # Notify others
            emit('user_joined', {
                'username': current_user.full_name or current_user.username,
                'message': f'{current_user.full_name or current_user.username} joined the chat',
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
            
            print(f'[Socket.IO] {current_user.username} joined order {order_id} chat')
        except Exception as e:
            print(f'[Socket.IO] join_order_chat error: {str(e)}')
            emit('error', {'message': 'Server error'})
    
    @socketio.on('leave_order_chat')
    def on_leave_order_chat(data):
        """User leaves order chat room"""
        order_id = data.get('order_id')
        room = f'order_{order_id}'
        
        leave_room(room)
        
        emit('user_left', {
            'username': current_user.full_name,
            'message': f'{current_user.full_name} left the chat',
            'timestamp': datetime.utcnow().isoformat()
        }, room=room)
        
        print(f'{current_user.username} left order {order_id} chat')
    
    @socketio.on('send_message')
    def on_send_message(data):
        """Handle incoming message"""
        try:
            if not current_user.is_authenticated:
                emit('error', {'message': 'Not authenticated'})
                return
            
            order_id = data.get('order_id')
            message_text = data.get('message', '').strip()
            
            if not message_text:
                return
            
            order = Order.query.get(order_id)
            if not order:
                emit('error', {'message': 'Order not found'})
                return
            
            # Verify access
            if not (current_user.is_admin() or 
                    order.creator_id == current_user.id or 
                    current_user in order.shared_with):
                emit('error', {'message': 'Access denied'})
                return
            
            room = f'order_{order_id}'
            
            message_data = {
                'username': current_user.full_name or current_user.username,
                'user_role': current_user.role,
                'message': message_text,
                'timestamp': datetime.utcnow().isoformat(),
                'user_id': current_user.id
            }
            
            # Broadcast message to room
            emit('new_message', message_data, room=room)
            
            # Log action
            log_action('messaged', 'Order', order_id, f'Message: {message_text[:50]}...')
            
            print(f'[Socket.IO] {current_user.username}: {message_text[:30]}...')
        except Exception as e:
            print(f'[Socket.IO] send_message error: {str(e)}')
            emit('error', {'message': 'Failed to send message'})
    
    @socketio.on('typing')
    def on_typing(data):
        """User is typing notification"""
        try:
            if not current_user.is_authenticated:
                return
            
            order_id = data.get('order_id')
            room = f'order_{order_id}'
            
            emit('user_typing', {
                'username': current_user.full_name or current_user.username,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room, skip_sid=True)
        except Exception as e:
            print(f'[Socket.IO] typing error: {str(e)}')
    
    @socketio.on_error_default
    def default_error_handler(e):
        """Handle errors"""
        print(f'[Socket.IO] Unhandled error: {str(e)}')
        try:
            emit('error', {'message': 'An error occurred on the server'})
        except:
            pass
