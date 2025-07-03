import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from queue import Queue, Empty
from enum import Enum
import traceback
import json

logger = logging.getLogger(__name__)

class MessageStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"

class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class QueuedMessage:
    id: str
    phone: str
    message: str
    client_id: str
    client_name: str
    message_type: str  # '3days', 'payment', 'renewal', 'manual'
    priority: MessagePriority
    scheduled_time: datetime
    max_retries: int = 3
    retry_count: int = 0
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class MessageQueue:
    def __init__(self):
        self.queue = Queue()
        self.processing = False
        self.worker_thread = None
        self.messages_history: List[QueuedMessage] = []
        self.failed_messages: List[QueuedMessage] = []
        self.retry_queue = Queue()
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'total_retries': 0,
            'last_sent': None,
            'queue_size': 0
        }
        self.delay_between_messages = 60  # 1 minuto em segundos
        self.max_queue_size = 1000
        self.message_callbacks: Dict[str, Callable] = {}
        
    def add_message(self, message: QueuedMessage) -> bool:
        """Add message to queue with validation"""
        try:
            # Validate message
            if not self._validate_message(message):
                logger.error(f"Invalid message for client {message.client_name}: {message.error_message}")
                return False
            
            # Check queue size
            if self.queue.qsize() >= self.max_queue_size:
                logger.error(f"Queue is full ({self.max_queue_size}). Cannot add message for {message.client_name}")
                return False
            
            # Add to queue
            self.queue.put(message)
            self.stats['queue_size'] = self.queue.qsize()
            
            logger.info(f"Message queued for {message.client_name} ({message.phone}) - Type: {message.message_type}, Priority: {message.priority.name}")
            
            # Start processing if not already running
            if not self.processing:
                self.start_processing()
                
            return True
            
        except Exception as e:
            logger.error(f"Error adding message to queue: {str(e)}")
            return False
    
    def _validate_message(self, message: QueuedMessage) -> bool:
        """Validate message before queuing"""
        try:
            # Check required fields
            if not message.phone or not message.message or not message.client_id:
                message.error_message = "Missing required fields (phone, message, client_id)"
                return False
            
            # Validate phone number
            if not self._validate_phone(message.phone):
                message.error_message = f"Invalid phone number: {message.phone}"
                return False
            
            # Check message length
            if len(message.message) > 4096:  # WhatsApp message limit
                message.error_message = "Message too long (max 4096 characters)"
                return False
            
            # Check if message is not empty after stripping
            if not message.message.strip():
                message.error_message = "Message is empty"
                return False
                
            return True
            
        except Exception as e:
            message.error_message = f"Validation error: {str(e)}"
            return False
    
    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format"""
        try:
            # Remove all non-digits
            digits_only = ''.join(filter(str.isdigit, phone))
            
            # Check length (10-15 digits for international format)
            if len(digits_only) < 10 or len(digits_only) > 15:
                return False
                
            # Additional validation can be added here
            return True
            
        except Exception:
            return False
    
    def start_processing(self):
        """Start the message processing worker"""
        if self.processing:
            logger.warning("Message processing already running")
            return
            
        self.processing = True
        self.worker_thread = threading.Thread(target=self._process_messages, daemon=True)
        self.worker_thread.start()
        logger.info("Message queue processing started")
    
    def stop_processing(self):
        """Stop the message processing worker"""
        self.processing = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("Message queue processing stopped")
    
    def _process_messages(self):
        """Main message processing loop"""
        last_sent_time = 0
        
        while self.processing:
            try:
                # Process retry queue first
                self._process_retry_queue()
                
                # Get next message from main queue
                try:
                    message = self.queue.get(timeout=1)
                except Empty:
                    continue
                
                # Check if enough time has passed since last message
                current_time = time.time()
                time_since_last = current_time - last_sent_time
                
                if time_since_last < self.delay_between_messages:
                    wait_time = self.delay_between_messages - time_since_last
                    logger.info(f"Waiting {wait_time:.1f}s before sending next message...")
                    time.sleep(wait_time)
                
                # Process the message
                success = self._send_message(message)
                
                if success:
                    message.status = MessageStatus.SENT
                    message.sent_at = datetime.now()
                    self.stats['total_sent'] += 1
                    self.stats['last_sent'] = datetime.now()
                    last_sent_time = time.time()
                    
                    logger.info(f"Message sent successfully to {message.client_name} ({message.phone})")
                    
                    # Call success callback if exists
                    if message.message_type in self.message_callbacks:
                        try:
                            self.message_callbacks[message.message_type](message, True)
                        except Exception as e:
                            logger.error(f"Error in success callback: {str(e)}")
                            
                else:
                    # Handle failure
                    if message.retry_count < message.max_retries:
                        message.retry_count += 1
                        message.status = MessageStatus.RETRYING
                        
                        # Add to retry queue with exponential backoff
                        retry_delay = min(300, 60 * (2 ** message.retry_count))  # Max 5 minutes
                        message.scheduled_time = datetime.now() + timedelta(seconds=retry_delay)
                        
                        self.retry_queue.put(message)
                        self.stats['total_retries'] += 1
                        
                        logger.warning(f"Message failed, scheduled for retry {message.retry_count}/{message.max_retries} in {retry_delay}s")
                        
                    else:
                        message.status = MessageStatus.FAILED
                        self.failed_messages.append(message)
                        self.stats['total_failed'] += 1
                        
                        logger.error(f"Message failed permanently to {message.client_name} after {message.max_retries} retries")
                        
                        # Call failure callback if exists
                        if message.message_type in self.message_callbacks:
                            try:
                                self.message_callbacks[message.message_type](message, False)
                            except Exception as e:
                                logger.error(f"Error in failure callback: {str(e)}")
                
                # Add to history
                self.messages_history.append(message)
                self.stats['queue_size'] = self.queue.qsize()
                
                # Cleanup old history (keep last 1000 messages)
                if len(self.messages_history) > 1000:
                    self.messages_history = self.messages_history[-1000:]
                
            except Exception as e:
                logger.error(f"Error in message processing loop: {str(e)}")
                logger.error(traceback.format_exc())
                time.sleep(5)  # Wait before continuing
    
    def _process_retry_queue(self):
        """Process messages in retry queue"""
        retry_messages = []
        
        # Get all messages from retry queue
        while True:
            try:
                message = self.retry_queue.get_nowait()
                retry_messages.append(message)
            except Empty:
                break
        
        # Check which messages are ready for retry
        now = datetime.now()
        for message in retry_messages:
            if message.scheduled_time <= now:
                # Ready for retry - add back to main queue
                self.queue.put(message)
            else:
                # Not ready yet - put back in retry queue
                self.retry_queue.put(message)
    
    def _send_message(self, message: QueuedMessage) -> bool:
        """Send individual message with error handling"""
        try:
            from whatsapp_integration import send_whatsapp_message, is_whatsapp_connected
            
            # Check WhatsApp connection
            if not is_whatsapp_connected():
                message.error_message = "WhatsApp not connected"
                logger.error(f"Cannot send message to {message.client_name}: WhatsApp not connected")
                return False
            
            # Attempt to send message
            success = send_whatsapp_message(message.phone, message.message)
            
            if not success:
                message.error_message = "WhatsApp send failed"
                
            return success
            
        except Exception as e:
            error_msg = f"Error sending message: {str(e)}"
            message.error_message = error_msg
            logger.error(f"Error sending message to {message.client_name}: {error_msg}")
            return False
    
    def add_callback(self, message_type: str, callback: Callable):
        """Add callback for message type"""
        self.message_callbacks[message_type] = callback
    
    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            'processing': self.processing,
            'queue_size': self.queue.qsize(),
            'retry_queue_size': self.retry_queue.qsize(),
            'history_size': len(self.messages_history),
            'failed_count': len(self.failed_messages),
            'stats': self.stats.copy()
        }
    
    def get_recent_messages(self, limit: int = 50) -> List[Dict]:
        """Get recent messages for monitoring"""
        recent = self.messages_history[-limit:] if limit > 0 else self.messages_history
        
        return [{
            'id': msg.id,
            'client_name': msg.client_name,
            'phone': msg.phone,
            'message_type': msg.message_type,
            'status': msg.status.value,
            'priority': msg.priority.name,
            'created_at': msg.created_at.isoformat() if msg.created_at else None,
            'sent_at': msg.sent_at.isoformat() if msg.sent_at else None,
            'retry_count': msg.retry_count,
            'error_message': msg.error_message
        } for msg in reversed(recent)]
    
    def cancel_messages_for_client(self, client_id: str) -> int:
        """Cancel all pending messages for a specific client"""
        cancelled_count = 0
        
        # Create new queue without messages for this client
        new_queue = Queue()
        
        while True:
            try:
                message = self.queue.get_nowait()
                if message.client_id == client_id:
                    message.status = MessageStatus.CANCELLED
                    self.messages_history.append(message)
                    cancelled_count += 1
                else:
                    new_queue.put(message)
            except Empty:
                break
        
        self.queue = new_queue
        self.stats['queue_size'] = self.queue.qsize()
        
        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} pending messages for client {client_id}")
        
        return cancelled_count
    
    def clear_failed_messages(self):
        """Clear failed messages history"""
        count = len(self.failed_messages)
        self.failed_messages.clear()
        logger.info(f"Cleared {count} failed messages from history")
    
    def save_state(self) -> Dict:
        """Save queue state for persistence"""
        try:
            state = {
                'stats': self.stats,
                'failed_messages_count': len(self.failed_messages),
                'queue_size': self.queue.qsize(),
                'timestamp': datetime.now().isoformat()
            }
            return state
        except Exception as e:
            logger.error(f"Error saving queue state: {str(e)}")
            return {}

# Global message queue instance
message_queue = MessageQueue()

def queue_reminder_message(client_id: str, client_name: str, phone: str, 
                          message: str, message_type: str, 
                          priority: MessagePriority = MessagePriority.NORMAL,
                          scheduled_time: Optional[datetime] = None) -> bool:
    """Helper function to queue a reminder message"""
    try:
        import uuid
        
        if scheduled_time is None:
            scheduled_time = datetime.now()
        
        queued_message = QueuedMessage(
            id=str(uuid.uuid4()),
            phone=phone,
            message=message,
            client_id=client_id,
            client_name=client_name,
            message_type=message_type,
            priority=priority,
            scheduled_time=scheduled_time
        )
        
        return message_queue.add_message(queued_message)
        
    except Exception as e:
        logger.error(f"Error queuing reminder message: {str(e)}")
        return False

def get_queue_status() -> Dict:
    """Get current queue status"""
    return message_queue.get_queue_status()

def get_recent_messages(limit: int = 50) -> List[Dict]:
    """Get recent messages"""
    return message_queue.get_recent_messages(limit)

def start_message_queue():
    """Start the message queue processing"""
    message_queue.start_processing()

def stop_message_queue():
    """Stop the message queue processing"""
    message_queue.stop_processing()