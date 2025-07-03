import logging
import logging.config
import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from functools import wraps
import traceback

class JSONFormatter(logging.Formatter):
    """Formatter que produz logs em formato JSON estruturado"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Adicionar informações extras se disponíveis
        if hasattr(record, 'client_id'):
            log_entry['client_id'] = record.client_id
        
        if hasattr(record, 'user_ip'):
            log_entry['user_ip'] = record.user_ip
        
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        
        if hasattr(record, 'action'):
            log_entry['action'] = record.action
        
        if hasattr(record, 'duration'):
            log_entry['duration'] = record.duration
        
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = record.status_code
        
        # Adicionar stack trace se for erro
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info)
            }
        
        # Adicionar informações extras personalizadas
        if hasattr(record, 'extra_data'):
            log_entry['extra'] = record.extra_data
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)

class ColoredFormatter(logging.Formatter):
    """Formatter com cores para console"""
    
    COLORS = {
        'DEBUG': '\033[94m',     # Blue
        'INFO': '\033[92m',      # Green
        'WARNING': '\033[93m',   # Yellow
        'ERROR': '\033[91m',     # Red
        'CRITICAL': '\033[95m'   # Magenta
    }
    
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        
        # Formato colorido para console
        formatter = logging.Formatter(
            f'{color}%(asctime)s{self.RESET} - %(name)s - {color}%(levelname)s{self.RESET} - %(message)s'
        )
        
        return formatter.format(record)

def setup_logging(log_level: str = 'INFO', enable_file_logging: bool = True) -> logging.Logger:
    """
    Configura logging estruturado para a aplicação
    
    Args:
        log_level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_file_logging: Se deve salvar logs em arquivo
    """
    
    # Criar diretório de logs se não existir
    if enable_file_logging:
        os.makedirs('logs', exist_ok=True)
    
    # Logger principal
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove handlers existentes para evitar duplicação
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Handler para console com cores
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Usar formatter colorido apenas se for terminal interativo
    if sys.stdout.isatty():
        console_handler.setFormatter(ColoredFormatter())
    else:
        console_handler.setFormatter(JSONFormatter())
    
    logger.addHandler(console_handler)
    
    if enable_file_logging:
        # Handler para arquivo de aplicação (INFO e acima)
        info_handler = logging.FileHandler('logs/app.log', encoding='utf-8')
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(JSONFormatter())
        logger.addHandler(info_handler)
        
        # Handler para arquivo de erro (ERROR e acima)
        error_handler = logging.FileHandler('logs/error.log', encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
        
        # Handler para arquivo de debug (apenas em desenvolvimento)
        if log_level.upper() == 'DEBUG':
            debug_handler = logging.FileHandler('logs/debug.log', encoding='utf-8')
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(JSONFormatter())
            logger.addHandler(debug_handler)
    
    # Configurar loggers específicos
    setup_specific_loggers()
    
    return logger

def setup_specific_loggers():
    """Configura loggers específicos para componentes do sistema"""
    
    # Logger para validações
    validation_logger = logging.getLogger('validation')
    validation_logger.setLevel(logging.INFO)
    
    # Logger para rate limiting
    rate_limit_logger = logging.getLogger('rate_limit')
    rate_limit_logger.setLevel(logging.WARNING)
    
    # Logger para GitHub storage
    github_logger = logging.getLogger('github_storage')
    github_logger.setLevel(logging.INFO)
    
    # Logger para WhatsApp
    whatsapp_logger = logging.getLogger('whatsapp')
    whatsapp_logger.setLevel(logging.INFO)
    
    # Logger para message queue
    queue_logger = logging.getLogger('message_queue')
    queue_logger.setLevel(logging.INFO)

class LogContext:
    """Context manager para logs com contexto adicional"""
    
    def __init__(self, **context):
        self.context = context
        self.old_factory = logging.getLogRecordFactory()
    
    def __enter__(self):
        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)

class StructuredLogger:
    """Wrapper para logging estruturado"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_action(self, action: str, level: str = 'INFO', **kwargs):
        """Log de ação estruturada"""
        extra_data = {
            'action': action,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        extra_data.update(kwargs)
        
        message = f"Action: {action}"
        if 'message' in kwargs:
            message = kwargs['message']
        
        getattr(self.logger, level.lower())(
            message,
            extra={'extra_data': extra_data}
        )
    
    def log_client_action(self, action: str, client_id: str, client_name: str = None, **kwargs):
        """Log de ação relacionada a cliente"""
        extra_data = {
            'action': action,
            'client_id': client_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        if client_name:
            extra_data['client_name'] = client_name
        
        extra_data.update(kwargs)
        
        message = f"Client action: {action} for client {client_id}"
        if client_name:
            message += f" ({client_name})"
        
        self.logger.info(
            message,
            extra={'extra_data': extra_data, 'client_id': client_id}
        )
    
    def log_api_call(self, endpoint: str, method: str, status_code: int, 
                     duration: float, user_ip: str = None, **kwargs):
        """Log de chamada API"""
        extra_data = {
            'action': 'api_call',
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code,
            'duration': duration,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        if user_ip:
            extra_data['user_ip'] = user_ip
        
        extra_data.update(kwargs)
        
        level = 'ERROR' if status_code >= 500 else 'WARNING' if status_code >= 400 else 'INFO'
        
        message = f"{method} {endpoint} - {status_code} ({duration:.3f}s)"
        
        getattr(self.logger, level.lower())(
            message,
            extra={
                'extra_data': extra_data,
                'status_code': status_code,
                'duration': duration,
                'user_ip': user_ip
            }
        )
    
    def log_error(self, error: Exception, context: str = None, **kwargs):
        """Log de erro estruturado"""
        extra_data = {
            'action': 'error',
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        if context:
            extra_data['context'] = context
        
        extra_data.update(kwargs)
        
        message = f"Error in {context}: {str(error)}" if context else f"Error: {str(error)}"
        
        self.logger.error(
            message,
            extra={'extra_data': extra_data},
            exc_info=True
        )

# Função de conveniência para criar context de log
def log_with_context(**context):
    """Cria context manager para logging com contexto"""
    return LogContext(**context)

# Função de conveniência para logging de ações do usuário
def log_user_action(action: str, details: str = "", client_ip: str = "", 
                   client_id: str = None, level: str = 'INFO'):
    """Log padronizado para ações do usuário"""
    logger = logging.getLogger('user_actions')
    
    extra_data = {
        'action': action,
        'details': details,
        'user_ip': client_ip,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    if client_id:
        extra_data['client_id'] = client_id
    
    message = f"USER_ACTION: {action}"
    if details:
        message += f" | Details: {details}"
    if client_ip:
        message += f" | IP: {client_ip}"
    
    getattr(logger, level.lower())(
        message,
        extra={
            'extra_data': extra_data,
            'action': action,
            'user_ip': client_ip,
            'client_id': client_id
        }
    )

# Decorador para logging automático de funções
def log_function_call(logger_name: str = None, level: str = 'DEBUG'):
    """Decorador para log automático de chamadas de função"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logging.getLogger(logger_name or func.__module__)
            
            start_time = datetime.utcnow()
            
            # Log entrada da função
            func_logger.debug(
                f"Entering function {func.__name__}",
                extra={
                    'extra_data': {
                        'function': func.__name__,
                        'module': func.__module__,
                        'action': 'function_enter',
                        'args_count': len(args),
                        'kwargs_count': len(kwargs)
                    }
                }
            )
            
            try:
                result = func(*args, **kwargs)
                
                # Log saída bem-sucedida
                duration = (datetime.utcnow() - start_time).total_seconds()
                func_logger.debug(
                    f"Function {func.__name__} completed successfully",
                    extra={
                        'extra_data': {
                            'function': func.__name__,
                            'module': func.__module__,
                            'action': 'function_exit',
                            'duration': duration,
                            'success': True
                        }
                    }
                )
                
                return result
                
            except Exception as e:
                # Log erro
                duration = (datetime.utcnow() - start_time).total_seconds()
                func_logger.error(
                    f"Function {func.__name__} failed: {str(e)}",
                    extra={
                        'extra_data': {
                            'function': func.__name__,
                            'module': func.__module__,
                            'action': 'function_error',
                            'duration': duration,
                            'error_type': type(e).__name__,
                            'error_message': str(e)
                        }
                    },
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator

# Funções utilitárias para logging
def get_log_stats() -> Dict[str, Any]:
    """Retorna estatísticas dos logs"""
    stats = {
        'log_files': {},
        'handlers_count': 0,
        'loggers_count': 0
    }
    
    # Contar handlers
    root_logger = logging.getLogger()
    stats['handlers_count'] = len(root_logger.handlers)
    
    # Contar loggers ativos
    stats['loggers_count'] = len(logging.Logger.manager.loggerDict)
    
    # Informações dos arquivos de log
    log_files = ['logs/app.log', 'logs/error.log', 'logs/debug.log']
    for log_file in log_files:
        if os.path.exists(log_file):
            stat = os.stat(log_file)
            stats['log_files'][log_file] = {
                'size_bytes': stat.st_size,
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
    
    return stats

def cleanup_old_logs(days: int = 7):
    """Remove logs antigos"""
    import glob
    from pathlib import Path
    
    if not os.path.exists('logs'):
        return 0
    
    cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
    removed_count = 0
    
    for log_file in glob.glob('logs/*.log*'):
        file_path = Path(log_file)
        if file_path.stat().st_mtime < cutoff_time:
            try:
                file_path.unlink()
                removed_count += 1
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to remove old log {log_file}: {e}")
    
    return removed_count

# Instâncias globais para uso fácil
app_logger = StructuredLogger('app')
api_logger = StructuredLogger('api')
client_logger = StructuredLogger('client')
system_logger = StructuredLogger('system')