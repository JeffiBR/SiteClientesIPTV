import os
import sys
import atexit
import logging
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

# Configuração básica de logging ANTES de importar outros módulos
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configurar ambiente
app.config['ENV'] = os.environ.get('FLASK_ENV', 'production')
app.config['DEBUG'] = os.environ.get('DEBUG', 'False').lower() == 'true'

# Verificar variáveis de ambiente críticas
required_env_vars = ['CL_TOKEN', 'CL_REPO', 'CL_BRANCH']
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]

if missing_vars:
    logger.error(f"Missing required environment variables: {missing_vars}")
    logger.error("The application needs these environment variables to function properly:")
    for var in missing_vars:
        logger.error(f"  - {var}")
    # Não abortar em produção, deixar tentar continuar
    if app.config['ENV'] == 'development':
        sys.exit(1)

# Inicializar scheduler de forma segura
scheduler = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    logger.info("Background scheduler initialized")
except Exception as e:
    logger.error(f"Failed to initialize scheduler: {e}")

# Configurar melhorias implementadas de forma segura
try:
    # Configurar logging estruturado se possível
    try:
        from logger_config import setup_logging
        logger = setup_logging(log_level='INFO', enable_file_logging=False)  # Desabilitar arquivo em produção
        logger.info("Structured logging configured")
    except Exception as e:
        logger.warning(f"Failed to setup structured logging: {e}")
    
    # Configurar rate limiting se possível
    try:
        from rate_limiter import RateLimitMiddleware
        rate_limit_middleware = RateLimitMiddleware(app, global_limit=200)
        logger.info("Rate limiting middleware configured")
    except Exception as e:
        logger.warning(f"Failed to setup rate limiting: {e}")
    
    # Configurar serviços de background se possível
    try:
        from simple_cache import schedule_cache_cleanup, warm_cache
        from backup_utils import schedule_automatic_backups
        
        schedule_cache_cleanup()
        schedule_automatic_backups()
        logger.info("Background services configured")
    except Exception as e:
        logger.warning(f"Failed to setup background services: {e}")

except Exception as e:
    logger.error(f"Error during improvements setup: {e}")
    # Continuar sem as melhorias se necessário

# Função de limpeza ao sair
def cleanup():
    try:
        if scheduler:
            scheduler.shutdown()
        logger.info("Application cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

atexit.register(cleanup)

# Import routes de forma segura
try:
    from routes import *
    logger.info("Routes imported successfully")
except Exception as e:
    logger.error(f"Failed to import routes: {e}")
    # Adicionar rotas básicas de emergência
    @app.route('/')
    def emergency_home():
        return """
        <h1>Sistema de Gestão de Clientes</h1>
        <p>O sistema está em modo de emergência. Algumas funcionalidades podem estar indisponíveis.</p>
        <p>Entre em contato com o administrador se este problema persistir.</p>
        """
    
    @app.route('/health')
    def emergency_health():
        return {'status': 'emergency', 'message': 'System in emergency mode'}

# Setup reminder scheduling de forma segura
if scheduler:
    try:
        with app.app_context():
            from reminder_scheduler import setup_reminders
            setup_reminders(scheduler)
            logger.info("Reminder scheduler configured successfully")
    except Exception as e:
        logger.error(f"Failed to setup reminders: {e}")

# Aquecer cache de forma segura
try:
    from simple_cache import warm_cache
    warm_cache()
    logger.info("Cache warmed successfully")
except Exception as e:
    logger.warning(f"Failed to warm cache: {e}")

# Adicionar rota de health check básica se não existir
@app.route('/ping')
def ping():
    return {'status': 'ok', 'message': 'Application is running'}

# Configurações específicas para Railway
if os.environ.get('RAILWAY_ENVIRONMENT'):
    logger.info(f"Running on Railway in {app.config['ENV']} mode")
    
    # Configurações específicas do Railway
    app.config['SERVER_NAME'] = None  # Deixar Railway gerenciar
    
    # Log de informações úteis para debug
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Flask debug mode: {app.config['DEBUG']}")
    logger.info(f"Environment variables loaded: {len(os.environ)}")

logger.info("Application initialized successfully")

# Garantir que a aplicação seja exportada corretamente
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    logger.info(f"Starting application on {host}:{port}")
    app.run(host=host, port=port, debug=app.config['DEBUG'])
