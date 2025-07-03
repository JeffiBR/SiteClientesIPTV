import os
import atexit
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Configurar logging estruturado ANTES de importar outros módulos
from logger_config import setup_logging
logger = setup_logging(log_level='INFO', enable_file_logging=True)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configurar ambiente
app.config['ENV'] = os.environ.get('FLASK_ENV', 'development')

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Configurar melhorias implementadas
from rate_limiter import RateLimitMiddleware
from simple_cache import schedule_cache_cleanup, warm_cache
from backup_utils import schedule_automatic_backups

# Aplicar middleware de rate limiting global
rate_limit_middleware = RateLimitMiddleware(app, global_limit=200)

# Iniciar serviços de background
schedule_cache_cleanup()
schedule_automatic_backups()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

# Import routes after app creation to avoid circular imports
from routes import *
from reminder_scheduler import setup_reminders

# Setup reminder scheduling
with app.app_context():
    try:
        setup_reminders(scheduler)
        logger.info("Reminder scheduler configured successfully")
    except Exception as e:
        logger.error(f"Failed to setup reminders: {str(e)}")

# Aquecer cache na inicialização
try:
    warm_cache()
    logger.info("Cache warmed successfully")
except Exception as e:
    logger.warning(f"Failed to warm cache: {str(e)}")

logger.info("Application initialized with all improvements")
