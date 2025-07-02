import os
import logging
import qrcode
import io
import base64
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class WhatsAppIntegration:
    def __init__(self):
        self.qr_code = None
        self.connection_file = 'whatsapp_connection.json'
        self.is_connected = self._load_connection_status()
    
    def _load_connection_status(self) -> bool:
        """Load connection status from storage"""
        try:
            from github_storage import storage
            file_data = storage._get_file_content('whatsapp_status.json')
            if file_data:
                return file_data['content'].get('connected', False)
            return False
        except Exception as e:
            logger.debug(f"No previous WhatsApp connection status found: {str(e)}")
            return False
    
    def _save_connection_status(self, status: bool):
        """Save connection status to storage"""
        try:
            from github_storage import storage
            content = {
                'connected': status,
                'last_updated': datetime.now().isoformat()
            }
            storage._save_file_content('whatsapp_status.json', content)
        except Exception as e:
            logger.error(f"Error saving WhatsApp connection status: {str(e)}")

    def generate_qr_code(self) -> Optional[str]:
        """Generate QR code for WhatsApp Web connection"""
        try:
            # Generate unique session ID for QR code
            session_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # QR code data should contain session info for real WhatsApp integration
            qr_data = f"whatsapp://connect?session={session_id}&timestamp={timestamp}&app=client-manager"
            
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
            
            logger.info(f"QR code generated for session: {session_id}")
            return self.qr_code
            
        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            return None
    
    def check_connection_status(self) -> bool:
        """Check if WhatsApp is connected"""
        # In a real implementation, this would check the actual connection
        # For demo purposes, we'll simulate connection after QR code scan
        return self.is_connected
    
    def set_connected(self, status: bool):
        """Set connection status"""
        self.is_connected = status
        self._save_connection_status(status)
        if status:
            logger.info("WhatsApp connected successfully")
        else:
            logger.info("WhatsApp disconnected")

# Global WhatsApp integration instance
whatsapp = WhatsAppIntegration()

def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send WhatsApp message to a phone number"""
    try:
        if not whatsapp.is_connected:
            logger.warning("WhatsApp not connected. Cannot send message.")
            return False
        
        # In a real implementation, this would use WhatsApp Business API
        # or a WhatsApp automation library
        logger.info(f"Sending WhatsApp message to {phone}: {message}")
        
        # Simulate successful sending
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return False

def get_whatsapp_qr_code() -> Optional[str]:
    """Get QR code for WhatsApp connection"""
    return whatsapp.generate_qr_code()

def is_whatsapp_connected() -> bool:
    """Check if WhatsApp is connected"""
    return whatsapp.check_connection_status()

def connect_whatsapp():
    """Mark WhatsApp as connected"""
    whatsapp.set_connected(True)

def disconnect_whatsapp():
    """Mark WhatsApp as disconnected"""
    whatsapp.set_connected(False)
