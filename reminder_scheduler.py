import logging
from datetime import datetime, timedelta
from apscheduler.triggers.cron import CronTrigger
from github_storage import storage
from whatsapp_integration import send_whatsapp_message
from ai_integration import ai_generator

logger = logging.getLogger(__name__)

def send_reminder(client_id: str, reminder_type: str):
    """Send reminder message to client"""
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            logger.error(f"Client not found: {client_id}")
            return
        
        # Get message content
        if reminder_type == '3days' and client.custom_message_3days:
            message = client.custom_message_3days
        elif reminder_type == 'payment' and client.custom_message_payment:
            message = client.custom_message_payment
        else:
            # Use AI to generate personalized message
            message = ai_generator.generate_reminder_message(client, reminder_type)
        
        # Send WhatsApp message
        if client.phone:
            success = send_whatsapp_message(client.phone, message)
            if success:
                logger.info(f"Reminder sent to {client.name} ({client.phone})")
            else:
                logger.error(f"Failed to send reminder to {client.name} ({client.phone})")
        else:
            logger.warning(f"No phone number for client {client.name}")
            
    except Exception as e:
        logger.error(f"Error sending reminder: {str(e)}")

def setup_reminders(scheduler):
    """Setup reminder jobs for all clients"""
    try:
        # Clear existing jobs
        scheduler.remove_all_jobs()
        
        clients = storage.get_clients()
        
        for client in clients:
            try:
                # Parse plan duration date
                plan_date = datetime.strptime(client.plan_duration, '%Y-%m-%d')
                
                # Calculate 3-day reminder date
                reminder_3days_date = plan_date - timedelta(days=3)
                
                # Schedule 3-day reminder
                hour_3days, minute_3days = map(int, client.reminder_time_3days.split(':'))
                
                scheduler.add_job(
                    func=send_reminder,
                    args=[client.id, '3days'],
                    trigger=CronTrigger(
                        year=reminder_3days_date.year,
                        month=reminder_3days_date.month,
                        day=reminder_3days_date.day,
                        hour=hour_3days,
                        minute=minute_3days
                    ),
                    id=f'reminder_3days_{client.id}',
                    replace_existing=True
                )
                
                # Schedule payment day reminder
                hour_payment, minute_payment = map(int, client.reminder_time_payment.split(':'))
                
                scheduler.add_job(
                    func=send_reminder,
                    args=[client.id, 'payment'],
                    trigger=CronTrigger(
                        year=plan_date.year,
                        month=plan_date.month,
                        day=plan_date.day,
                        hour=hour_payment,
                        minute=minute_payment
                    ),
                    id=f'reminder_payment_{client.id}',
                    replace_existing=True
                )
                
            except Exception as e:
                logger.error(f"Erro ao agendar lembretes para cliente {client.name}: {str(e)}")
                continue
        
        logger.info(f"Setup {len(clients) * 2} reminder jobs")
        
    except Exception as e:
        logger.error(f"Error setting up reminders: {str(e)}")

def get_upcoming_reminders():
    """Get list of upcoming reminders for dashboard"""
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
                        'days_until': (reminder_3days_date - now).days
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
                        'days_until': (plan_date - now).days
                    })
                    
            except Exception as e:
                logger.error(f"Erro ao processar lembretes do cliente {client.name}: {str(e)}")
                continue
        
        # Sort by days until reminder
        upcoming.sort(key=lambda x: x['days_until'])
        
        return upcoming
        
    except Exception as e:
        logger.error(f"Error getting upcoming reminders: {str(e)}")
        return []
