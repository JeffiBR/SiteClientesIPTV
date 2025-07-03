import logging
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger
from github_storage import storage
from message_queue import queue_reminder_message, MessagePriority, start_message_queue
from ai_integration import ai_generator
import traceback
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

def send_reminder(client_id: str, reminder_type: str):
    """Send reminder message to client using message queue"""
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            logger.error(f"Client not found: {client_id}")
            return
        
        # Check if client should receive reminders
        if not client.should_send_reminder:
            logger.info(f"Skipping reminder for {client.name} - marked as paid")
            return
        
        # Get message content
        message = get_reminder_message(client, reminder_type)
        if not message:
            logger.error(f"Failed to generate message for {client.name}")
            return
        
        # Determine priority based on reminder type and client status
        priority = MessagePriority.NORMAL
        if reminder_type == 'payment':
            priority = MessagePriority.HIGH
        elif client.status == 'expirado':
            priority = MessagePriority.URGENT
        
        # Queue the message
        success = queue_reminder_message(
            client_id=client.id,
            client_name=client.name,
            phone=client.phone,
            message=message,
            message_type=reminder_type,
            priority=priority
        )
        
        if success:
            logger.info(f"Reminder queued for {client.name} ({client.phone}) - Type: {reminder_type}")
        else:
            logger.error(f"Failed to queue reminder for {client.name}")
            
    except Exception as e:
        logger.error(f"Error sending reminder: {str(e)}")
        logger.error(traceback.format_exc())

def get_reminder_message(client, reminder_type: str) -> str:
    """Get reminder message with error handling"""
    try:
        # Check for custom messages first
        if reminder_type == '3days' and client.custom_message_3days:
            return format_message(client.custom_message_3days, client)
        elif reminder_type == 'payment' and client.custom_message_payment:
            return format_message(client.custom_message_payment, client)
        
        # Use AI to generate personalized message
        try:
            message = ai_generator.generate_reminder_message(client, reminder_type)
            if message:
                return message
        except Exception as ai_error:
            logger.warning(f"AI message generation failed: {str(ai_error)}")
        
        # Fallback to default templates
        return get_default_message(client, reminder_type)
        
    except Exception as e:
        logger.error(f"Error getting reminder message: {str(e)}")
        return get_default_message(client, reminder_type)

def format_message(template: str, client) -> str:
    """Format message template with client data"""
    try:
        return template.format(
            name=client.name,
            plan_type=client.plan_type,
            value=client.value,
            payment_day=client.payment_day,
            plan_duration=client.plan_duration,
            days_until_expiration=client.days_until_expiration
        )
    except Exception as e:
        logger.error(f"Error formatting message: {str(e)}")
        return template  # Return unformatted if error

def get_default_message(client, reminder_type: str) -> str:
    """Get default message templates"""
    try:
        if reminder_type == '3days':
            return f"Olá {client.name}! Seu plano {client.plan_type} no valor de R$ {client.value:.2f} vence em 3 dias. Não esqueça de renovar!"
        elif reminder_type == 'payment':
            return f"Olá {client.name}! Hoje é o dia do vencimento do seu plano {client.plan_type} no valor de R$ {client.value:.2f}. Por favor, realize o pagamento para manter o serviço ativo."
        else:
            return f"Olá {client.name}! Lembrete sobre seu plano {client.plan_type}."
    except Exception as e:
        logger.error(f"Error creating default message: {str(e)}")
        return "Lembrete sobre seu plano de serviço."

def group_clients_by_reminder_date(clients: List) -> Dict[str, Dict[str, List]]:
    """Group clients by reminder date to implement 1-minute delay"""
    try:
        grouped = {}
        
        for client in clients:
            try:
                plan_date = datetime.strptime(client.plan_duration, '%Y-%m-%d').date()
                reminder_3days_date = plan_date - timedelta(days=3)
                
                # Group by reminder dates
                for date_key, reminder_type in [
                    (reminder_3days_date.strftime('%Y-%m-%d'), '3days'),
                    (plan_date.strftime('%Y-%m-%d'), 'payment')
                ]:
                    if date_key not in grouped:
                        grouped[date_key] = {'3days': [], 'payment': []}
                    
                    grouped[date_key][reminder_type].append(client)
                    
            except Exception as e:
                logger.error(f"Error processing client {client.name}: {str(e)}")
                continue
        
        return grouped
        
    except Exception as e:
        logger.error(f"Error grouping clients by reminder date: {str(e)}")
        return {}

def schedule_batch_reminders(clients_for_date: List, reminder_type: str, base_time: Tuple[int, int], date_obj: datetime):
    """Schedule reminders with 1-minute intervals for same-date clients"""
    try:
        hour, minute = base_time
        
        for index, client in enumerate(clients_for_date):
            try:
                # Calculate send time with 1-minute intervals
                send_minute = minute + index
                send_hour = hour
                
                # Handle minute overflow
                while send_minute >= 60:
                    send_minute -= 60
                    send_hour += 1
                
                # Handle hour overflow
                if send_hour >= 24:
                    send_hour = 0
                    date_obj = date_obj + timedelta(days=1)
                
                # Create unique job ID
                job_id = f'reminder_{reminder_type}_{client.id}_{date_obj.strftime("%Y%m%d")}_{send_hour}{send_minute:02d}'
                
                # Schedule the job
                from app import scheduler
                scheduler.add_job(
                    func=send_reminder,
                    args=[client.id, reminder_type],
                    trigger=CronTrigger(
                        year=date_obj.year,
                        month=date_obj.month,
                        day=date_obj.day,
                        hour=send_hour,
                        minute=send_minute
                    ),
                    id=job_id,
                    replace_existing=True,
                    max_instances=1
                )
                
                logger.info(f"Scheduled {reminder_type} reminder for {client.name} at {send_hour:02d}:{send_minute:02d} on {date_obj.strftime('%Y-%m-%d')}")
                
            except Exception as e:
                logger.error(f"Error scheduling reminder for client {client.name}: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Error in schedule_batch_reminders: {str(e)}")

def setup_reminders(scheduler):
    """Setup reminder jobs for all clients with 1-minute intervals for same dates"""
    try:
        # Start message queue if not already running
        start_message_queue()
        
        # Clear existing reminder jobs
        try:
            # Remove only reminder jobs, not other system jobs
            jobs_to_remove = [job.id for job in scheduler.get_jobs() if job.id.startswith('reminder_')]
            for job_id in jobs_to_remove:
                scheduler.remove_job(job_id)
            logger.info(f"Removed {len(jobs_to_remove)} existing reminder jobs")
        except Exception as e:
            logger.warning(f"Error clearing existing jobs: {str(e)}")
        
        clients = storage.get_clients()
        if not clients:
            logger.info("No clients found, no reminders to schedule")
            return
        
        # Group clients by reminder dates
        grouped_clients = group_clients_by_reminder_date(clients)
        
        total_jobs = 0
        for date_str, reminder_groups in grouped_clients.items():
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                
                # Skip past dates
                if date_obj.date() < datetime.now().date():
                    continue
                
                # Schedule 3-day reminders
                if reminder_groups['3days']:
                    clients_3days = reminder_groups['3days']
                    # Get the base time from the first client
                    base_time = tuple(map(int, clients_3days[0].reminder_time_3days.split(':')))
                    schedule_batch_reminders(clients_3days, '3days', base_time, date_obj)
                    total_jobs += len(clients_3days)
                
                # Schedule payment day reminders
                if reminder_groups['payment']:
                    clients_payment = reminder_groups['payment']
                    # Get the base time from the first client
                    base_time = tuple(map(int, clients_payment[0].reminder_time_payment.split(':')))
                    schedule_batch_reminders(clients_payment, 'payment', base_time, date_obj)
                    total_jobs += len(clients_payment)
                    
            except Exception as e:
                logger.error(f"Error processing reminders for date {date_str}: {str(e)}")
                continue
        
        logger.info(f"Successfully scheduled {total_jobs} reminder jobs for {len(clients)} clients")
        
        # Schedule daily cleanup job
        schedule_daily_cleanup(scheduler)
        
    except Exception as e:
        logger.error(f"Error setting up reminders: {str(e)}")
        logger.error(traceback.format_exc())

def schedule_daily_cleanup(scheduler):
    """Schedule daily cleanup job for expired reminders"""
    try:
        scheduler.add_job(
            func=cleanup_expired_jobs,
            trigger=CronTrigger(hour=2, minute=0),  # Run at 2 AM daily
            id='daily_cleanup',
            replace_existing=True,
            max_instances=1
        )
        logger.info("Scheduled daily cleanup job")
    except Exception as e:
        logger.error(f"Error scheduling daily cleanup: {str(e)}")

def cleanup_expired_jobs():
    """Clean up expired reminder jobs"""
    try:
        from app import scheduler
        
        removed_count = 0
        today = datetime.now().date()
        
        for job in scheduler.get_jobs():
            if job.id.startswith('reminder_'):
                try:
                    # Extract date from job trigger
                    if hasattr(job.trigger, 'fields'):
                        year = job.trigger.fields[0].expressions[0].value
                        month = job.trigger.fields[1].expressions[0].value
                        day = job.trigger.fields[2].expressions[0].value
                        job_date = datetime(year, month, day).date()
                        
                        # Remove if job is more than 1 day old
                        if job_date < today - timedelta(days=1):
                            scheduler.remove_job(job.id)
                            removed_count += 1
                            
                except Exception as e:
                    logger.warning(f"Error processing job {job.id}: {str(e)}")
                    continue
        
        logger.info(f"Cleaned up {removed_count} expired reminder jobs")
        
    except Exception as e:
        logger.error(f"Error in cleanup_expired_jobs: {str(e)}")

def get_upcoming_reminders():
    """Get list of upcoming reminders for dashboard with error handling"""
    try:
        clients = storage.get_clients()
        upcoming = []
        
        now = datetime.now().date()
        week_from_now = now + timedelta(days=7)
        
        for client in clients:
            try:
                plan_date = datetime.strptime(client.plan_duration, '%Y-%m-%d').date()
                reminder_3days_date = plan_date - timedelta(days=3)
                
                # Check 3-day reminder
                if now <= reminder_3days_date <= week_from_now:
                    upcoming.append({
                        'client': client.name,
                        'type': 'Lembrete 3 dias',
                        'date': reminder_3days_date.strftime('%d/%m'),
                        'time': client.reminder_time_3days,
                        'plan_type': client.plan_type,
                        'value': client.value,
                        'phone': client.phone,
                        'status': client.status,
                        'days_until': (reminder_3days_date - now).days,
                        'will_send': client.should_send_reminder,
                        'payment_status': getattr(client, 'payment_status', 'pending')
                    })
                
                # Check payment day reminder
                if now <= plan_date <= week_from_now:
                    upcoming.append({
                        'client': client.name,
                        'type': 'Dia do pagamento',
                        'date': plan_date.strftime('%d/%m'),
                        'time': client.reminder_time_payment,
                        'plan_type': client.plan_type,
                        'value': client.value,
                        'phone': client.phone,
                        'status': client.status,
                        'days_until': (plan_date - now).days,
                        'will_send': client.should_send_reminder,
                        'payment_status': getattr(client, 'payment_status', 'pending')
                    })
                    
            except Exception as e:
                logger.error(f"Error processing reminders for client {client.name}: {str(e)}")
                continue
        
        # Sort by days until reminder
        upcoming.sort(key=lambda x: x['days_until'])
        
        return upcoming
        
    except Exception as e:
        logger.error(f"Error getting upcoming reminders: {str(e)}")
        return []

def get_reminder_statistics() -> Dict:
    """Get comprehensive reminder statistics"""
    try:
        from message_queue import get_queue_status, get_recent_messages
        
        # Get queue status
        queue_status = get_queue_status()
        
        # Get recent messages
        recent_messages = get_recent_messages(100)
        
        # Calculate statistics
        sent_count = sum(1 for msg in recent_messages if msg['status'] == 'sent')
        failed_count = sum(1 for msg in recent_messages if msg['status'] == 'failed')
        pending_count = sum(1 for msg in recent_messages if msg['status'] == 'pending')
        
        # Get upcoming reminders
        upcoming = get_upcoming_reminders()
        
        return {
            'queue_status': queue_status,
            'recent_stats': {
                'sent': sent_count,
                'failed': failed_count,
                'pending': pending_count,
                'total': len(recent_messages)
            },
            'upcoming_count': len(upcoming),
            'upcoming_today': len([r for r in upcoming if r['days_until'] == 0]),
            'upcoming_3days': len([r for r in upcoming if r['days_until'] <= 3])
        }
        
    except Exception as e:
        logger.error(f"Error getting reminder statistics: {str(e)}")
        return {
            'queue_status': {'processing': False, 'queue_size': 0},
            'recent_stats': {'sent': 0, 'failed': 0, 'pending': 0, 'total': 0},
            'upcoming_count': 0,
            'upcoming_today': 0,
            'upcoming_3days': 0
        }

def force_send_reminder(client_id: str, reminder_type: str) -> bool:
    """Force send a reminder immediately"""
    try:
        logger.info(f"Force sending {reminder_type} reminder for client {client_id}")
        send_reminder(client_id, reminder_type)
        return True
    except Exception as e:
        logger.error(f"Error force sending reminder: {str(e)}")
        return False

def pause_reminders_for_client(client_id: str) -> bool:
    """Pause all reminders for a specific client"""
    try:
        from message_queue import message_queue
        
        # Cancel pending messages
        cancelled = message_queue.cancel_messages_for_client(client_id)
        
        # Remove scheduled jobs
        from app import scheduler
        removed_jobs = 0
        
        for job in scheduler.get_jobs():
            if job.id.startswith('reminder_') and client_id in job.id:
                scheduler.remove_job(job.id)
                removed_jobs += 1
        
        logger.info(f"Paused reminders for client {client_id}: {cancelled} messages cancelled, {removed_jobs} jobs removed")
        return True
        
    except Exception as e:
        logger.error(f"Error pausing reminders for client {client_id}: {str(e)}")
        return False

def resume_reminders_for_client(client_id: str) -> bool:
    """Resume reminders for a specific client"""
    try:
        # Re-setup reminders for this client
        from app import scheduler
        setup_reminders(scheduler)
        
        logger.info(f"Resumed reminders for client {client_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error resuming reminders for client {client_id}: {str(e)}")
        return False
