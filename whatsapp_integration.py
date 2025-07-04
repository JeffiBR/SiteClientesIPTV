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

# Try to import qrcode with fallback
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logging.warning("qrcode module not available - QR code generation will be disabled")

logger = logging.getLogger(__name__)

class WhatsAppConnectionStatus:
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"
    QRCODE_READY = "qrcode_ready"


class EvolutionAPIError(Exception):
    """Exceção personalizada para erros da Evolution API"""
    pass

class WhatsAppIntegration:
    def __init__(self):
        # Evolution API Configuration
        self.api_url = os.getenv('EVOLUTION_API_URL', 'http://localhost:8080')
        self.api_key = os.getenv('EVOLUTION_API_KEY', '')
        self.instance_name = os.getenv('EVOLUTION_INSTANCE', 'clientmanager')
        
        # Connection state
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
        self.heartbeat_thread = None
        self.monitor_thread = None
        self.heartbeat_interval = 30  # seconds
        self.connection_timeout = 300  # 5 minutes without heartbeat = disconnected
        self.last_heartbeat = None
        self.auto_reconnect = True
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.webhook_url = None
        self.message_queue = []
        
        # Load previous connection state
        self._load_connection_state()
        
        # Start background services if connected
        if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
            self._start_heartbeat()
            self._start_connection_monitor()
    
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
                self.api_url = content.get('api_url', self.api_url)
                self.api_key = content.get('api_key', self.api_key)
                self.instance_name = content.get('instance_name', self.instance_name)
                
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
                'api_url': self.api_url,
                'api_key': self.api_key,
                'instance_name': self.instance_name,
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

    def configure_evolution_api(self, api_url: str, api_key: str = None, instance_name: str = None):
        """Configure Evolution API parameters"""
        self.api_url = api_url.rstrip('/')
        if api_key:
            self.api_key = api_key
        if instance_name:
            self.instance_name = instance_name
        
        self._save_connection_state()
        logger.info(f"Evolution API configured: {self.api_url} - Instance: {self.instance_name}")

    def _make_api_request(self, endpoint: str, method: str = 'GET', data: Dict = None, timeout: int = 30) -> Dict:
        """Make request to Evolution API"""
        try:
            url = f"{self.api_url}/{endpoint.lstrip('/')}"
            headers = {
                'Content-Type': 'application/json'
            }
            
            # Add API key if available
            if self.api_key:
                headers['apikey'] = self.api_key
            
            logger.debug(f"Making {method} request to: {url}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                raise EvolutionAPIError(f"Unsupported HTTP method: {method}")
            
            logger.debug(f"Response status: {response.status_code}")
            
            if response.status_code == 200 or response.status_code == 201:
                return response.json() if response.content else {}
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise EvolutionAPIError(error_msg)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            logger.error(error_msg)
            raise EvolutionAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            raise EvolutionAPIError(error_msg)

    def create_instance(self) -> bool:
        """Create or recreate WhatsApp instance"""
        try:
            logger.info(f"Creating Evolution API instance: {self.instance_name}")
            
            data = {
                "instanceName": self.instance_name,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS"
            }
            
            # Add webhook if configured
            if self.webhook_url:
                data["webhook"] = self.webhook_url
            
            response = self._make_api_request('instance/create', 'POST', data)
            
            if response.get('instance'):
                logger.info("Instance created successfully")
                self.session_id = response['instance'].get('instanceName', self.instance_name)
                return True
            else:
                logger.error("Failed to create instance")
                return False
                
        except EvolutionAPIError as e:
            logger.error(f"Error creating instance: {str(e)}")
            self.connection_error = str(e)
            return False

    def get_qr_code(self) -> Optional[str]:
        """Get QR code from Evolution API"""
        try:
            logger.info("Fetching QR code from Evolution API")
            
            response = self._make_api_request(f'instance/connect/{self.instance_name}')
            
            if 'qrcode' in response:
                qr_data = response['qrcode']
                
                # Evolution API pode retornar QR code em diferentes formatos
                if isinstance(qr_data, dict):
                    # Se vier como objeto com base64
                    if 'base64' in qr_data:
                        self.qr_code = f"data:image/png;base64,{qr_data['base64']}"
                    elif 'pngData' in qr_data:
                        self.qr_code = f"data:image/png;base64,{qr_data['pngData']}"
                    else:
                        # Tentar usar o primeiro valor que parecer base64
                        for key, value in qr_data.items():
                            if isinstance(value, str) and len(value) > 100:
                                self.qr_code = f"data:image/png;base64,{value}"
                                break
                elif isinstance(qr_data, str):
                    # Se vier como string base64 direta
                    if qr_data.startswith('data:image'):
                        self.qr_code = qr_data
                    else:
                        self.qr_code = f"data:image/png;base64,{qr_data}"
                
                if self.qr_code:
                    self.connection_status = WhatsAppConnectionStatus.QRCODE_READY
                    self.connection_error = None
                    self._save_connection_state()
                    logger.info("QR code obtained successfully")
                    return self.qr_code
                else:
                    logger.error("QR code data not found in response")
                    return None
            else:
                logger.error("No QR code in API response")
                return None
                
        except EvolutionAPIError as e:
            logger.error(f"Error getting QR code: {str(e)}")
            self.connection_error = str(e)
            return None

    def generate_qr_code(self) -> Optional[str]:
        """Generate QR code for WhatsApp connection using Evolution API"""
        try:
            if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
                logger.info("Already connected to WhatsApp")
                return self.qr_code
            
            # Validate API configuration
            if not self.api_url:
                self.connection_error = "Evolution API URL not configured"
                logger.error(self.connection_error)
                return None
            
            if not self.instance_name:
                self.connection_error = "Instance name not configured"
                logger.error(self.connection_error)
                return None
            
            self.connection_status = WhatsAppConnectionStatus.CONNECTING
            self.connection_error = None
            self._save_connection_state()
            
            # Check if instance exists, create if not
            try:
                instance_info = self._make_api_request(f'instance/connectionState/{self.instance_name}')
                logger.info(f"Instance status: {instance_info}")
            except EvolutionAPIError:
                logger.info("Instance not found, creating new one")
                if not self.create_instance():
                    self.connection_status = WhatsAppConnectionStatus.ERROR
                    self.connection_error = "Failed to create instance"
                    self._save_connection_state()
                    return None
            
            # Get QR code
            qr_code = self.get_qr_code()
            
            if qr_code:
                # Start connection monitoring
                self._start_connection_monitor()
                return qr_code
            else:
                self.connection_status = WhatsAppConnectionStatus.ERROR
                self.connection_error = "Failed to get QR code"
                self._save_connection_state()
                return None
                
        except Exception as e:
            logger.error(f"Error in generate_qr_code: {str(e)}")
            self.connection_error = f"QR code generation error: {str(e)}"
            self.connection_status = WhatsAppConnectionStatus.ERROR
            self._save_connection_state()
            return None

    def check_connection_status(self) -> bool:
        """Check WhatsApp connection status via Evolution API"""
        try:
            # Rate limit connection checks
            now = time.time()
            if self.last_connection_check and (now - self.last_connection_check) < 10:
                return self.connection_status == WhatsAppConnectionStatus.CONNECTED
            
            self.last_connection_check = now
            
            if not self.instance_name:
                return False
            
            response = self._make_api_request(f'instance/connectionState/{self.instance_name}')
            
            if response.get('instance'):
                state = response['instance'].get('state', 'close')
                
                if state == 'open':
                    if self.connection_status != WhatsAppConnectionStatus.CONNECTED:
                        self.set_connected(True)
                    return True
                elif state == 'connecting':
                    self.connection_status = WhatsAppConnectionStatus.CONNECTING
                    return False
                else:
                    if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
                        self.set_connected(False, f"Connection state: {state}")
                    return False
            else:
                return False
                
        except EvolutionAPIError as e:
            logger.error(f"Error checking connection status: {str(e)}")
            if self.connection_status == WhatsAppConnectionStatus.CONNECTED:
                self.set_connected(False, str(e))
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking connection: {str(e)}")
            return False

    def set_connected(self, status: bool, error_message: Optional[str] = None):
        """Set connection status"""
        try:
            if status:
                if self.connection_status != WhatsAppConnectionStatus.CONNECTED:
                    self.connection_status = WhatsAppConnectionStatus.CONNECTED
                    self.connection_error = None
                    self.connection_attempts = 0
                    self.message_sending_enabled = True
                    logger.info("WhatsApp connected successfully via Evolution API")
                    
                    # Start heartbeat monitoring
                    self._start_heartbeat()
                    
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
            if self.instance_name:
                try:
                    self._make_api_request(f'instance/logout/{self.instance_name}', 'DELETE')
                    logger.info("Instance logged out successfully")
                except EvolutionAPIError as e:
                    logger.warning(f"Error logging out instance: {str(e)}")
            
            self.set_connected(False, reason)
            self.session_id = None
            self.qr_code = None
            logger.info(f"Disconnected from WhatsApp: {reason}")
        except Exception as e:
            logger.error(f"Error disconnecting: {str(e)}")

    def send_message(self, phone: str, message: str, retry_count: int = 0) -> bool:
        """Send WhatsApp message via Evolution API"""
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
            
            # Format phone number
            formatted_phone = self._format_phone_number(phone)
            if not formatted_phone:
                logger.error(f"Invalid phone number: {phone}")
                return False
            
            # Send message via Evolution API
            data = {
                "number": formatted_phone,
                "text": message
            }
            
            response = self._make_api_request(f'message/sendText/{self.instance_name}', 'POST', data)
            
            if response.get('key'):
                # Update rate limit counter
                self.rate_limit['current_count'] += 1
                logger.info(f"Message sent successfully to {phone}")
                return True
            else:
                logger.error(f"Failed to send message to {phone}")
                return False
                
        except EvolutionAPIError as e:
            logger.error(f"Error sending WhatsApp message: {str(e)}")
            # Record failed send
            error_info = {
                'phone': phone,
                'message': message[:100] + '...' if len(message) > 100 else message,
                'timestamp': datetime.now().isoformat(),
                'retry_count': retry_count,
                'error': str(e)
            }
            self.failed_sends.append(error_info)
            
            # Keep only last 100 failed sends
            if len(self.failed_sends) > 100:
                self.failed_sends = self.failed_sends[-100:]
            
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message: {str(e)}")
            return False

    def _format_phone_number(self, phone: str) -> Optional[str]:
        """Format phone number for Evolution API"""
        try:
            # Remove all non-digits
            digits_only = ''.join(filter(str.isdigit, phone))
            
            # Validate length
            if len(digits_only) < 10 or len(digits_only) > 15:
                return None
            
            # Add @s.whatsapp.net suffix if needed
            if not phone.endswith('@s.whatsapp.net'):
                return f"{digits_only}@s.whatsapp.net"
            
            return phone
            
        except Exception:
            return None

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
            'api_url': self.api_url,
            'instance_name': self.instance_name,
            'api_configured': bool(self.api_url and self.instance_name),
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

    def _start_connection_monitor(self):
        """Start the connection monitoring thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.monitor_thread = threading.Thread(target=self._connection_monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Connection monitor started")

    def _connection_monitor_loop(self):
        """Monitor connection status and handle reconnection"""
        while True:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                # Check connection status
                self.check_connection_status()
                
                # Auto-reconnect if needed
                if (self.connection_status == WhatsAppConnectionStatus.DISCONNECTED and 
                    self.auto_reconnect and 
                    self.reconnect_attempts < self.max_reconnect_attempts):
                    
                    logger.info("Attempting auto-reconnect...")
                    self._attempt_reconnect()
                
            except Exception as e:
                logger.error(f"Error in connection monitor: {str(e)}")
                time.sleep(60)  # Wait longer on error

    def _start_heartbeat(self):
        """Start the heartbeat thread"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logger.info("Heartbeat monitor started")

    def _heartbeat_loop(self):
        """Send periodic heartbeat to maintain connection"""
        while self.connection_status == WhatsAppConnectionStatus.CONNECTED:
            try:
                time.sleep(self.heartbeat_interval)
                
                if self._send_heartbeat():
                    self.last_heartbeat = datetime.now()
                else:
                    logger.warning("Heartbeat failed")
                    
            except Exception as e:
                logger.error(f"Error in heartbeat: {str(e)}")
                time.sleep(60)

    def _send_heartbeat(self) -> bool:
        """Send heartbeat to Evolution API"""
        try:
            response = self._make_api_request(f'instance/connectionState/{self.instance_name}')
            return response.get('instance', {}).get('state') == 'open'
        except Exception as e:
            logger.error(f"Heartbeat error: {str(e)}")
            return False

    def _attempt_reconnect(self):
        """Attempt to reconnect to WhatsApp"""
        try:
            self.reconnect_attempts += 1
            self.connection_status = WhatsAppConnectionStatus.RECONNECTING
            self._save_connection_state()
            
            logger.info(f"Reconnection attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
            
            # Try to reconnect
            qr_code = self.generate_qr_code()
            if qr_code:
                logger.info("Reconnection QR code generated, waiting for scan...")
            else:
                logger.error("Failed to generate reconnection QR code")
                
        except Exception as e:
            logger.error(f"Error during reconnection: {str(e)}")

    def force_reconnect(self):
        """Force a reconnection attempt"""
        self.reconnect_attempts = 0
        self.disconnect("Forced reconnect")
        time.sleep(2)
        self.generate_qr_code()

# Global WhatsApp integration instance
whatsapp = WhatsAppIntegration()

# Helper functions for backward compatibility
def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send WhatsApp message using Evolution API"""
    return whatsapp.send_message(phone, message)

def get_whatsapp_qr_code() -> Optional[str]:
    """Get WhatsApp QR code"""
    return whatsapp.generate_qr_code()

def is_whatsapp_connected() -> bool:
    """Check if WhatsApp is connected"""
    return whatsapp.check_connection_status()

def connect_whatsapp():
    """Mark WhatsApp as connected"""
    whatsapp.set_connected(True)

def disconnect_whatsapp(reason: str = "Manual disconnect"):
    """Disconnect WhatsApp"""
    whatsapp.disconnect(reason)

def get_whatsapp_status() -> Dict:
    """Get WhatsApp status information"""
    return whatsapp.get_status_info()

def configure_evolution_api(api_url: str, api_key: str = None, instance_name: str = None):
    """Configure Evolution API settings"""
    whatsapp.configure_evolution_api(api_url, api_key, instance_name)

def get_failed_sends(limit: int = 20) -> List[Dict]:
    """Get failed message sends"""
    return whatsapp.get_failed_sends(limit)

def clear_failed_sends():
    """Clear failed sends history"""
    whatsapp.clear_failed_sends()

def force_whatsapp_reconnect():
    """Force reconnection"""
    whatsapp.force_reconnect()

def enable_message_sending(enabled: bool = True):
    """Enable or disable message sending"""
    whatsapp.enable_message_sending(enabled)
