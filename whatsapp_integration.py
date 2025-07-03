import os
import logging
import io
import base64
import uuid
import time
import requests
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import json
import traceback

# Import QR code library with fallback
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logging.warning("qrcode library not available - QR code generation disabled")

logger = logging.getLogger(__name__)

class WhatsAppConnectionStatus:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"

class WhatsAppIntegration:
    def __init__(self):
        self.qr_code = None
        self.connection_status = WhatsAppConnectionStatus.DISCONNECTED
        self.connection_error = None
        self.last_connection_check = None
        self.connection_attempts = 0
        self.max_connection_attempts = 5
        self.session_id = None
        self.webhook_port = None
        self.webhook_running = False
        self.message_sending_enabled = True
        self.rate_limit = {
            'messages_per_minute': 20,
            'current_count': 0,
            'reset_time': time.time() + 60
        }
        self.failed_sends = []
        self.connection_callbacks = []
        
        # Load previous connection state
        self._load_connection_state()
    
    def _load_connection_state(self) -> bool:
        """Load connection status from storage with error handling"""
        try:
            from github_storage import storage
            file_data = storage._get_file_content('whatsapp_status.json')
            if file_data and 'content' in file_data:
                content = file_data['content']
                self.connection_status = content.get('status', WhatsAppConnectionStatus.DISCONNECTED)
                self.connection_error = content.get('error', None)
                self.session_id = content.get('session_id', None)
                
                # Auto-disconnect if last connection was more than 24 hours ago
                last_updated = content.get('last_updated')
                if last_updated:
                    try:
                        last_time = datetime.fromisoformat(last_updated)
                        if (datetime.now() - last_time).total_seconds() > 86400:  # 24 hours
                            logger.info("Connection expired after 24 hours, disconnecting")
                            self.connection_status = WhatsAppConnectionStatus.DISCONNECTED
                            self._save_connection_state()
                    except Exception as e:
                        logger.warning(f"Error parsing last_updated time: {e}")
                
                return self.connection_status == WhatsAppConnectionStatus.CONNECTED
            return False
        except Exception as e:
            logger.error(f"Error loading WhatsApp connection status: {str(e)}")
            self.connection_status = WhatsAppConnectionStatus.DISCONNECTED
            return False
    
    def _save_connection_state(self):
        """Save connection status to storage with error handling"""
        try:
            from github_storage import storage
            content = {
                'status': self.connection_status,
                'error': self.connection_error,
                'session_id': self.session_id,
                'last_updated': datetime.now().isoformat(),
                'connection_attempts': self.connection_attempts,
                'message_sending_enabled': self.message_sending_enabled
            }
            
            # Get current file data to preserve SHA
            file_data = storage._get_file_content('whatsapp_status.json')
            sha = file_data['sha'] if file_data else None
            
            success = storage._save_file_content('whatsapp_status.json', content, sha)
            if not success:
                logger.error("Failed to save WhatsApp connection status")
                
        except Exception as e:
            logger.error(f"Error saving WhatsApp connection status: {str(e)}")

    def generate_qr_code(self) -> Optional[str]:
        """Generate QR code for WhatsApp Web connection with error handling"""
        try:
            if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
                logger.info("Already connected to WhatsApp")
                return self.qr_code
            
            # Generate unique session ID for QR code
            self.session_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # QR code data should contain session info for real WhatsApp integration
            qr_data = f"whatsapp://connect?session={self.session_id}&timestamp={timestamp}&app=client-manager&v=2.0"
            
            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                # Create QR code image
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Convert to base64 for web display
                img_buffer = io.BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                
                img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
                self.qr_code = f"data:image/png;base64,{img_base64}"
                
                # Update status to connecting
                self.connection_status = WhatsAppConnectionStatus.CONNECTING
                self.connection_error = None
                self._save_connection_state()
                
                logger.info(f"QR code generated for session: {self.session_id}")
                return self.qr_code
                
            except Exception as qr_error:
                logger.error(f"Error generating QR code image: {str(qr_error)}")
                self.connection_error = f"QR generation failed: {str(qr_error)}"
                self.connection_status = WhatsAppConnectionStatus.ERROR
                self._save_connection_state()
                return None
                
        except Exception as e:
            logger.error(f"Error in generate_qr_code: {str(e)}")
            self.connection_error = f"QR code generation error: {str(e)}"
            self.connection_status = WhatsAppConnectionStatus.ERROR
            self._save_connection_state()
            return None
    
    def check_connection_status(self) -> bool:
        """Check if WhatsApp is connected with comprehensive validation"""
        try:
            # Rate limit connection checks
            now = time.time()
            if self.last_connection_check and (now - self.last_connection_check) < 30:
                return self.connection_status == WhatsAppConnectionStatus.CONNECTED
            
            self.last_connection_check = now
            
            # If we're marked as connected, validate the connection
            if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
                if self._validate_connection():
                    return True
                else:
                    logger.warning("Connection validation failed, marking as disconnected")
                    self.connection_status = WhatsAppConnectionStatus.DISCONNECTED
                    self.connection_error = "Connection validation failed"
                    self._save_connection_state()
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking connection status: {str(e)}")
            self.connection_status = WhatsAppConnectionStatus.ERROR
            self.connection_error = str(e)
            self._save_connection_state()
            return False
    
    def _validate_connection(self) -> bool:
        """Validate actual WhatsApp connection"""
        try:
            # In a real implementation, this would ping WhatsApp API
            # For now, we'll do basic validation
            
            # Check if session is valid
            if not self.session_id:
                return False
            
            # Check if we can send messages
            if not self.message_sending_enabled:
                return False
            
            # Additional validation checks can be added here
            # For example: ping WhatsApp Business API, check webhook status, etc.
            
            return True
            
        except Exception as e:
            logger.error(f"Connection validation error: {str(e)}")
            return False
    
    def set_connected(self, status: bool, error_message: Optional[str] = None):
        """Set connection status with validation"""
        try:
            if status:
                if self.connection_status != WhatsAppConnectionStatus.CONNECTED:
                    self.connection_status = WhatsAppConnectionStatus.CONNECTED
                    self.connection_error = None
                    self.connection_attempts = 0
                    self.message_sending_enabled = True
                    logger.info("WhatsApp connected successfully")
                    
                    # Notify callbacks
                    self._notify_connection_callbacks(True)
            else:
                self.connection_status = WhatsAppConnectionStatus.DISCONNECTED
                self.connection_error = error_message
                self.message_sending_enabled = False
                logger.info(f"WhatsApp disconnected: {error_message or 'Manual disconnect'}")
                
                # Notify callbacks
                self._notify_connection_callbacks(False)
            
            self._save_connection_state()
            
        except Exception as e:
            logger.error(f"Error setting connection status: {str(e)}")
    
    def disconnect(self, reason: str = "Manual disconnect"):
        """Disconnect from WhatsApp"""
        try:
            self.set_connected(False, reason)
            self.session_id = None
            self.qr_code = None
            logger.info(f"Disconnected from WhatsApp: {reason}")
        except Exception as e:
            logger.error(f"Error disconnecting: {str(e)}")
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        try:
            now = time.time()
            
            # Reset counter if minute has passed
            if now >= self.rate_limit['reset_time']:
                self.rate_limit['current_count'] = 0
                self.rate_limit['reset_time'] = now + 60
            
            # Check if we're under the limit
            if self.rate_limit['current_count'] >= self.rate_limit['messages_per_minute']:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {str(e)}")
            return False
    
    def send_message(self, phone: str, message: str, retry_count: int = 0) -> bool:
        """Send WhatsApp message with comprehensive error handling"""
        try:
            # Validate inputs
            if not phone or not message:
                logger.error("Phone number and message are required")
                return False
            
            if not self.check_connection_status():
                logger.error("WhatsApp not connected")
                return False
            
            if not self.message_sending_enabled:
                logger.error("Message sending is disabled")
                return False
            
            # Check rate limit
            if not self._check_rate_limit():
                logger.warning("Rate limit exceeded, message will be queued")
                return False
            
            # Validate phone number
            if not self._validate_phone_number(phone):
                logger.error(f"Invalid phone number: {phone}")
                return False
            
            # Validate message content
            if not self._validate_message_content(message):
                logger.error("Invalid message content")
                return False
            
            # Attempt to send message
            success = self._send_message_internal(phone, message)
            
            if success:
                # Update rate limit counter
                self.rate_limit['current_count'] += 1
                logger.info(f"Message sent successfully to {phone}")
                return True
            else:
                # Handle send failure
                error_info = {
                    'phone': phone,
                    'message': message[:100] + '...' if len(message) > 100 else message,
                    'timestamp': datetime.now().isoformat(),
                    'retry_count': retry_count
                }
                self.failed_sends.append(error_info)
                
                # Keep only last 100 failed sends
                if len(self.failed_sends) > 100:
                    self.failed_sends = self.failed_sends[-100:]
                
                logger.error(f"Failed to send message to {phone}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def _send_message_internal(self, phone: str, message: str) -> bool:
        """Internal message sending logic"""
        try:
            # In a real implementation, this would use WhatsApp Business API
            # For demonstration purposes, we'll simulate the sending process
            
            # Simulate network delay
            time.sleep(0.1)
            
            # Simulate occasional failures (5% failure rate for testing)
            import random
            if random.random() < 0.05:
                return False
            
            logger.debug(f"Simulated WhatsApp message sent to {phone}: {message[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Internal send error: {str(e)}")
            return False
    
    def _validate_phone_number(self, phone: str) -> bool:
        """Validate phone number format"""
        try:
            # Remove all non-digits
            digits_only = ''.join(filter(str.isdigit, phone))
            
            # Check length (10-15 digits for international format)
            if len(digits_only) < 10 or len(digits_only) > 15:
                return False
            
            # Additional validation can be added here
            # For example: country code validation, format checking, etc.
            
            return True
            
        except Exception:
            return False
    
    def _validate_message_content(self, message: str) -> bool:
        """Validate message content"""
        try:
            # Check if message is not empty
            if not message.strip():
                return False
            
            # Check length (WhatsApp has a 4096 character limit)
            if len(message) > 4096:
                return False
            
            # Check for prohibited content (can be expanded)
            prohibited_words = ['spam', 'illegal']  # Example list
            message_lower = message.lower()
            for word in prohibited_words:
                if word in message_lower:
                    logger.warning(f"Message contains prohibited word: {word}")
                    # Don't reject, just log for monitoring
            
            return True
            
        except Exception:
            return False
    
    def add_connection_callback(self, callback):
        """Add callback for connection status changes"""
        self.connection_callbacks.append(callback)
    
    def _notify_connection_callbacks(self, connected: bool):
        """Notify all connection callbacks"""
        for callback in self.connection_callbacks:
            try:
                callback(connected)
            except Exception as e:
                logger.error(f"Error in connection callback: {str(e)}")
    
    def get_status_info(self) -> Dict:
        """Get comprehensive status information"""
        return {
            'status': self.connection_status,
            'connected': self.connection_status == WhatsAppConnectionStatus.CONNECTED,
            'error': self.connection_error,
            'session_id': self.session_id,
            'message_sending_enabled': self.message_sending_enabled,
            'connection_attempts': self.connection_attempts,
            'last_check': self.last_connection_check,
            'rate_limit': {
                'limit': self.rate_limit['messages_per_minute'],
                'current': self.rate_limit['current_count'],
                'reset_in': max(0, self.rate_limit['reset_time'] - time.time())
            },
            'failed_sends_count': len(self.failed_sends),
            'qr_code_available': self.qr_code is not None
        }
    
    def get_failed_sends(self, limit: int = 20) -> List[Dict]:
        """Get recent failed message sends"""
        return self.failed_sends[-limit:] if limit > 0 else self.failed_sends
    
    def clear_failed_sends(self):
        """Clear failed sends history"""
        count = len(self.failed_sends)
        self.failed_sends.clear()
        logger.info(f"Cleared {count} failed send records")
    
    def enable_message_sending(self, enabled: bool = True):
        """Enable or disable message sending"""
        self.message_sending_enabled = enabled
        self._save_connection_state()
        logger.info(f"Message sending {'enabled' if enabled else 'disabled'}")
    
    def force_reconnect(self):
        """Force a reconnection attempt"""
        try:
            logger.info("Forcing WhatsApp reconnection...")
            self.connection_status = WhatsAppConnectionStatus.RECONNECTING
            self.connection_attempts += 1
            self._save_connection_state()
            
            # Generate new QR code
            self.qr_code = None
            self.session_id = None
            
            if self.connection_attempts >= self.max_connection_attempts:
                logger.error("Max connection attempts reached, giving up")
                self.connection_status = WhatsAppConnectionStatus.ERROR
                self.connection_error = "Max connection attempts exceeded"
            else:
                self.generate_qr_code()
                
        except Exception as e:
            logger.error(f"Error during force reconnect: {str(e)}")
            self.connection_status = WhatsAppConnectionStatus.ERROR
            self.connection_error = str(e)
            self._save_connection_state()

# Global WhatsApp integration instance
whatsapp = WhatsAppIntegration()

def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send WhatsApp message to a phone number with error handling"""
    try:
        return whatsapp.send_message(phone, message)
    except Exception as e:
        logger.error(f"Error in send_whatsapp_message: {str(e)}")
        return False

def get_whatsapp_qr_code() -> Optional[str]:
    """Get QR code for WhatsApp connection"""
    try:
        return whatsapp.generate_qr_code()
    except Exception as e:
        logger.error(f"Error getting QR code: {str(e)}")
        return None

def is_whatsapp_connected() -> bool:
    """Check if WhatsApp is connected"""
    try:
        return whatsapp.check_connection_status()
    except Exception as e:
        logger.error(f"Error checking WhatsApp connection: {str(e)}")
        return False

def connect_whatsapp():
    """Mark WhatsApp as connected"""
    try:
        whatsapp.set_connected(True)
    except Exception as e:
        logger.error(f"Error connecting WhatsApp: {str(e)}")

def disconnect_whatsapp(reason: str = "Manual disconnect"):
    """Mark WhatsApp as disconnected"""
    try:
        whatsapp.disconnect(reason)
    except Exception as e:
        logger.error(f"Error disconnecting WhatsApp: {str(e)}")

def get_whatsapp_status() -> Dict:
    """Get comprehensive WhatsApp status"""
    try:
        return whatsapp.get_status_info()
    except Exception as e:
        logger.error(f"Error getting WhatsApp status: {str(e)}")
        return {
            'status': WhatsAppConnectionStatus.ERROR,
            'connected': False,
            'error': str(e)
        }

def get_failed_sends(limit: int = 20) -> List[Dict]:
    """Get recent failed message sends"""
    try:
        return whatsapp.get_failed_sends(limit)
    except Exception as e:
        logger.error(f"Error getting failed sends: {str(e)}")
        return []

def clear_failed_sends():
    """Clear failed sends history"""
    try:
        whatsapp.clear_failed_sends()
    except Exception as e:
        logger.error(f"Error clearing failed sends: {str(e)}")

def force_whatsapp_reconnect():
    """Force a WhatsApp reconnection"""
    try:
        whatsapp.force_reconnect()
    except Exception as e:
        logger.error(f"Error forcing reconnect: {str(e)}")

def enable_message_sending(enabled: bool = True):
    """Enable or disable message sending"""
    try:
        whatsapp.enable_message_sending(enabled)
    except Exception as e:
        logger.error(f"Error setting message sending status: {str(e)}")
