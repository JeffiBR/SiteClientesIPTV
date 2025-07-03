import time
from typing import Dict, Tuple, Optional
from threading import Lock
from functools import wraps
import logging

# Import Flask components only when available
try:
    from flask import request, jsonify, flash, redirect, url_for
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    # Mock objects for testing
    class MockRequest:
        def __init__(self):
            self.environ = {'HTTP_X_REAL_IP': '127.0.0.1'}
            self.remote_addr = '127.0.0.1'
            self.is_json = False
            self.path = '/test'
            self.endpoint = 'test'
            self.referrer = None
    
    request = MockRequest()
    
    def jsonify(data):
        return data
    
    def flash(message, category='info'):
        print(f"FLASH [{category}]: {message}")
    
    def redirect(location):
        return f"REDIRECT: {location}"
    
    def url_for(endpoint):
        return f"URL_FOR: {endpoint}"

logger = logging.getLogger(__name__)

class SimpleRateLimiter:
    def __init__(self):
        self.clients: Dict[str, Tuple[int, float]] = {}  # {ip: (count, reset_time)}
        self.lock = Lock()
        self.default_limit = 60  # requests per minute
        self.window = 60  # 1 minute window
    
    def is_allowed(self, client_ip: str, limit: int = None) -> bool:
        """Verifica se o cliente pode fazer uma requisição"""
        if limit is None:
            limit = self.default_limit
        
        current_time = time.time()
        
        with self.lock:
            if client_ip not in self.clients:
                self.clients[client_ip] = (1, current_time + self.window)
                return True
            
            count, reset_time = self.clients[client_ip]
            
            # Reset window if expired
            if current_time >= reset_time:
                self.clients[client_ip] = (1, current_time + self.window)
                return True
            
            # Check if under limit
            if count < limit:
                self.clients[client_ip] = (count + 1, reset_time)
                return True
            
            return False
    
    def get_remaining(self, client_ip: str, limit: int = None) -> int:
        """Retorna quantas requisições restam"""
        if limit is None:
            limit = self.default_limit
        
        current_time = time.time()
        
        with self.lock:
            if client_ip not in self.clients:
                return limit
            
            count, reset_time = self.clients[client_ip]
            
            if current_time >= reset_time:
                return limit
            
            return max(0, limit - count)
    
    def get_reset_time(self, client_ip: str) -> Optional[float]:
        """Retorna quando o limite será resetado"""
        with self.lock:
            if client_ip in self.clients:
                return self.clients[client_ip][1]
            return None
    
    def cleanup_expired(self) -> int:
        """Remove entradas expiradas"""
        current_time = time.time()
        expired_count = 0
        
        with self.lock:
            expired_ips = []
            for ip, (count, reset_time) in self.clients.items():
                if current_time >= reset_time:
                    expired_ips.append(ip)
            
            for ip in expired_ips:
                del self.clients[ip]
                expired_count += 1
        
        return expired_count
    
    def get_stats(self) -> Dict[str, any]:
        """Retorna estatísticas do rate limiter"""
        with self.lock:
            active_clients = len(self.clients)
            total_requests = sum(count for count, _ in self.clients.values())
        
        return {
            'active_clients': active_clients,
            'total_requests': total_requests,
            'window_seconds': self.window,
            'default_limit': self.default_limit
        }

# Instância global
rate_limiter = SimpleRateLimiter()

def get_client_ip() -> str:
    """Obtém IP real do cliente considerando proxies"""
    # Verifica headers de proxy comuns
    forwarded_ips = request.environ.get('HTTP_X_FORWARDED_FOR')
    if forwarded_ips:
        # Pega o primeiro IP (cliente real)
        return forwarded_ips.split(',')[0].strip()
    
    real_ip = request.environ.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip
    
    # Fallback para IP direto
    return request.remote_addr or '127.0.0.1'

def rate_limit(limit: int = 60, window: int = 60, key_func=None):
    """
    Decorador para aplicar rate limiting
    
    Args:
        limit: Número máximo de requisições por janela
        window: Janela de tempo em segundos (padrão: 60)
        key_func: Função para gerar chave customizada (padrão: usa IP)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Gerar chave do cliente
            if key_func:
                client_key = key_func(request)
            else:
                client_key = get_client_ip()
            
            # Verificar rate limit
            if not rate_limiter.is_allowed(client_key, limit):
                remaining_time = rate_limiter.get_reset_time(client_key)
                if remaining_time:
                    wait_time = int(remaining_time - time.time())
                    wait_time = max(0, wait_time)
                else:
                    wait_time = window
                
                # Log da tentativa bloqueada
                logger.warning(
                    f"Rate limit exceeded for {client_key} on {request.endpoint}. "
                    f"Limit: {limit}/{window}s. Wait: {wait_time}s"
                )
                
                # Resposta dependendo do tipo de requisição
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'error': 'Rate limit exceeded',
                        'message': f'Máximo {limit} requisições por {window} segundos',
                        'retry_after': wait_time,
                        'limit': limit,
                        'window': window
                    }), 429
                else:
                    flash(f'Muitas tentativas. Aguarde {wait_time} segundos.', 'error')
                    return redirect(request.referrer or url_for('dashboard'))
            
            # Log da requisição permitida (apenas em debug)
            remaining = rate_limiter.get_remaining(client_key, limit)
            logger.debug(f"Request allowed for {client_key}. Remaining: {remaining}/{limit}")
            
            return f(*args, **kwargs)
        
        # Adicionar informações do rate limit na função
        decorated_function._rate_limit = {
            'limit': limit,
            'window': window
        }
        
        return decorated_function
    return decorator

def rate_limit_api(limit: int = 30):
    """Rate limiter específico para APIs"""
    return rate_limit(limit=limit, window=60)

def rate_limit_form(limit: int = 10):
    """Rate limiter específico para formulários"""
    return rate_limit(limit=limit, window=60)

def rate_limit_sensitive(limit: int = 3):
    """Rate limiter para ações sensíveis"""
    return rate_limit(limit=limit, window=60)

def rate_limit_by_user():
    """Rate limiter baseado em session/user"""
    def user_key_func(req):
        # Primeiro tenta session
        if hasattr(req, 'session') and req.session.get('user_id'):
            return f"user:{req.session['user_id']}"
        # Fallback para IP
        return get_client_ip()
    
    return rate_limit(limit=20, key_func=user_key_func)

class RateLimitMiddleware:
    """Middleware para aplicar rate limiting globalmente"""
    
    def __init__(self, app, global_limit: int = 100):
        self.app = app
        self.global_limit = global_limit
        self.setup_middleware()
    
    def setup_middleware(self):
        @self.app.before_request
        def check_global_rate_limit():
            # Aplicar rate limit global apenas em produção
            if self.app.config.get('ENV') == 'production':
                client_ip = get_client_ip()
                
                if not rate_limiter.is_allowed(client_ip, self.global_limit):
                    logger.warning(f"Global rate limit exceeded for {client_ip}")
                    
                    if request.is_json or request.path.startswith('/api/'):
                        return jsonify({
                            'error': 'Global rate limit exceeded',
                            'message': 'Muitas requisições. Tente novamente em alguns minutos.'
                        }), 429
                    else:
                        return "Muitas requisições. Tente novamente em alguns minutos.", 429

def cleanup_rate_limiter():
    """Função para limpar entradas expiradas periodicamente"""
    expired = rate_limiter.cleanup_expired()
    if expired > 0:
        logger.debug(f"Cleaned up {expired} expired rate limit entries")
    return expired

# Função para obter estatísticas do rate limiter
def get_rate_limit_stats() -> Dict[str, any]:
    """Retorna estatísticas do rate limiter"""
    stats = rate_limiter.get_stats()
    stats['cleanup_count'] = cleanup_rate_limiter()
    return stats

# Função para resetar rate limits (útil para desenvolvimento)
def reset_rate_limits():
    """Reseta todos os rate limits"""
    with rate_limiter.lock:
        rate_limiter.clients.clear()
    logger.info("All rate limits have been reset")

# Função para verificar rate limit sem consumir
def check_rate_limit(client_ip: str = None, limit: int = None) -> Dict[str, any]:
    """Verifica status do rate limit sem consumir"""
    if client_ip is None:
        client_ip = get_client_ip()
    
    if limit is None:
        limit = rate_limiter.default_limit
    
    remaining = rate_limiter.get_remaining(client_ip, limit)
    reset_time = rate_limiter.get_reset_time(client_ip)
    
    return {
        'client_ip': client_ip,
        'limit': limit,
        'remaining': remaining,
        'reset_time': reset_time,
        'is_blocked': remaining <= 0
    }