import time
import hashlib
import json
from typing import Any, Optional, Dict, Tuple, Callable
from threading import RLock
from functools import wraps
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SimpleCache:
    """Cache em memória thread-safe com TTL e estatísticas"""
    
    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self.cache: Dict[str, Tuple[Any, float]] = {}  # {key: (value, expires_at)}
        self.access_count: Dict[str, int] = {}  # Contador de acessos
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.lock = RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.created_at = time.time()
    
    def _generate_key(self, key: str) -> str:
        """Gera chave hash para o cache"""
        if isinstance(key, str) and len(key) < 100:
            return key  # Usar chave original se for pequena
        return hashlib.md5(key.encode('utf-8')).hexdigest()
    
    def _is_expired(self, expires_at: float) -> bool:
        """Verifica se item expirou"""
        return time.time() >= expires_at
    
    def _evict_expired(self) -> int:
        """Remove itens expirados"""
        current_time = time.time()
        expired_keys = []
        
        for key, (value, expires_at) in self.cache.items():
            if current_time >= expires_at:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            if key in self.access_count:
                del self.access_count[key]
        
        return len(expired_keys)
    
    def _evict_lru(self) -> int:
        """Remove itens menos usados para liberar espaço"""
        if len(self.cache) <= self.max_size:
            return 0
        
        # Ordenar por contador de acesso (crescente)
        sorted_keys = sorted(
            self.access_count.items(), 
            key=lambda x: x[1]
        )
        
        evict_count = len(self.cache) - self.max_size + 1
        evicted = 0
        
        for key, _ in sorted_keys[:evict_count]:
            if key in self.cache:
                del self.cache[key]
                del self.access_count[key]
                evicted += 1
        
        self.evictions += evicted
        return evicted
    
    def get(self, key: str, default: Any = None) -> Any:
        """Recupera item do cache"""
        cache_key = self._generate_key(key)
        current_time = time.time()
        
        with self.lock:
            if cache_key in self.cache:
                value, expires_at = self.cache[cache_key]
                
                if not self._is_expired(expires_at):
                    # Hit válido
                    self.hits += 1
                    self.access_count[cache_key] = self.access_count.get(cache_key, 0) + 1
                    
                    logger.debug(f"Cache HIT for key: {key}")
                    return value
                else:
                    # Item expirado
                    del self.cache[cache_key]
                    if cache_key in self.access_count:
                        del self.access_count[cache_key]
            
            # Miss
            self.misses += 1
            logger.debug(f"Cache MISS for key: {key}")
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Armazena item no cache"""
        cache_key = self._generate_key(key)
        expires_at = time.time() + (ttl or self.default_ttl)
        
        with self.lock:
            # Limpar expirados primeiro
            self._evict_expired()
            
            # Verificar se precisa fazer LRU eviction
            if len(self.cache) >= self.max_size:
                self._evict_lru()
            
            self.cache[cache_key] = (value, expires_at)
            self.access_count[cache_key] = 1
            
            logger.debug(f"Cache SET for key: {key}, TTL: {ttl or self.default_ttl}s")
            return True
    
    def delete(self, key: str) -> bool:
        """Remove item do cache"""
        cache_key = self._generate_key(key)
        
        with self.lock:
            if cache_key in self.cache:
                del self.cache[cache_key]
                if cache_key in self.access_count:
                    del self.access_count[cache_key]
                logger.debug(f"Cache DELETE for key: {key}")
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """Verifica se chave existe no cache"""
        cache_key = self._generate_key(key)
        
        with self.lock:
            if cache_key in self.cache:
                _, expires_at = self.cache[cache_key]
                return not self._is_expired(expires_at)
            return False
    
    def clear(self) -> None:
        """Limpa todo o cache"""
        with self.lock:
            cleared_count = len(self.cache)
            self.cache.clear()
            self.access_count.clear()
            logger.info(f"Cache cleared: {cleared_count} items removed")
    
    def cleanup_expired(self) -> int:
        """Remove itens expirados e retorna quantidade removida"""
        with self.lock:
            expired_count = self._evict_expired()
            if expired_count > 0:
                logger.debug(f"Cache cleanup: {expired_count} expired items removed")
            return expired_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas do cache"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            uptime = time.time() - self.created_at
            
            return {
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': round(hit_rate, 2),
                'cache_size': len(self.cache),
                'max_size': self.max_size,
                'evictions': self.evictions,
                'total_requests': total_requests,
                'uptime_seconds': round(uptime, 2),
                'memory_efficiency': round((len(self.cache) / self.max_size) * 100, 2),
                'default_ttl': self.default_ttl
            }
    
    def get_all_keys(self) -> list:
        """Retorna todas as chaves válidas no cache"""
        with self.lock:
            current_time = time.time()
            valid_keys = []
            
            for key, (_, expires_at) in self.cache.items():
                if current_time < expires_at:
                    valid_keys.append(key)
            
            return valid_keys

# Instância global
app_cache = SimpleCache(default_ttl=300, max_size=1000)

def cached(ttl: int = 300, key_func: Optional[Callable] = None, cache_instance: Optional[SimpleCache] = None):
    """
    Decorador para cache automático de funções
    
    Args:
        ttl: Tempo de vida em segundos
        key_func: Função para gerar chave customizada
        cache_instance: Instância específica do cache (padrão: app_cache)
    """
    def decorator(func):
        cache = cache_instance or app_cache
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Gerar chave do cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Gerar chave baseada no nome da função e argumentos
                args_str = json.dumps(args, default=str, sort_keys=True)
                kwargs_str = json.dumps(kwargs, default=str, sort_keys=True)
                cache_key = f"{func.__module__}.{func.__name__}:{args_str}:{kwargs_str}"
            
            # Tentar recuperar do cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Executar função e cachear resultado
            start_time = time.time()
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Cachear apenas se a execução foi bem-sucedida
            cache.set(cache_key, result, ttl)
            
            logger.debug(
                f"Function {func.__name__} executed and cached. "
                f"Execution time: {execution_time:.3f}s, TTL: {ttl}s"
            )
            
            return result
        
        # Adicionar funcionalidades úteis ao wrapper
        wrapper.cache_clear = lambda: cache.delete(f"{func.__module__}.{func.__name__}")
        wrapper.cache_info = lambda: cache.get_stats()
        wrapper._cache_key_prefix = f"{func.__module__}.{func.__name__}"
        
        return wrapper
    return decorator

def cache_github_data(ttl: int = 300):
    """Decorador específico para cache de dados do GitHub"""
    def github_key_func(*args, **kwargs):
        # Usar apenas argumentos relevantes para GitHub
        return f"github_data:{hash(str(args) + str(kwargs))}"
    
    return cached(ttl=ttl, key_func=github_key_func)

def cache_dashboard_stats(ttl: int = 120):
    """Decorador específico para estatísticas do dashboard"""
    return cached(ttl=ttl, key_func=lambda *args, **kwargs: "dashboard_stats")

def cache_client_list(ttl: int = 180):
    """Decorador específico para lista de clientes"""
    return cached(ttl=ttl, key_func=lambda *args, **kwargs: "client_list")

class CacheManager:
    """Gerenciador avançado de cache com múltiplas instâncias"""
    
    def __init__(self):
        self.caches: Dict[str, SimpleCache] = {
            'default': app_cache,
            'dashboard': SimpleCache(default_ttl=120, max_size=100),
            'github': SimpleCache(default_ttl=300, max_size=500),
            'api': SimpleCache(default_ttl=60, max_size=200)
        }
    
    def get_cache(self, name: str) -> SimpleCache:
        """Obtém instância específica do cache"""
        return self.caches.get(name, self.caches['default'])
    
    def clear_all(self):
        """Limpa todos os caches"""
        for name, cache in self.caches.items():
            cache.clear()
            logger.info(f"Cache '{name}' cleared")
    
    def cleanup_all(self) -> Dict[str, int]:
        """Limpa itens expirados de todos os caches"""
        results = {}
        for name, cache in self.caches.items():
            results[name] = cache.cleanup_expired()
        return results
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de todos os caches"""
        stats = {
            'total_caches': len(self.caches),
            'caches': {}
        }
        
        total_hits = 0
        total_misses = 0
        total_size = 0
        
        for name, cache in self.caches.items():
            cache_stats = cache.get_stats()
            stats['caches'][name] = cache_stats
            
            total_hits += cache_stats['hits']
            total_misses += cache_stats['misses']
            total_size += cache_stats['cache_size']
        
        total_requests = total_hits + total_misses
        global_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        stats['global'] = {
            'total_hits': total_hits,
            'total_misses': total_misses,
            'global_hit_rate': round(global_hit_rate, 2),
            'total_cache_size': total_size
        }
        
        return stats

# Instância global do gerenciador
cache_manager = CacheManager()

def invalidate_cache_pattern(pattern: str):
    """Invalida caches que correspondem a um padrão"""
    for cache_name, cache in cache_manager.caches.items():
        keys_to_delete = []
        for key in cache.get_all_keys():
            if pattern in key:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            cache.delete(key)
        
        if keys_to_delete:
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}' in cache '{cache_name}'")

def warm_cache():
    """Aquece o cache com dados frequentemente acessados"""
    try:
        from github_storage import storage
        
        # Pré-carregar dados de clientes
        clients = storage.get_clients()
        app_cache.set("client_list", clients, ttl=300)
        
        # Pré-carregar estatísticas básicas
        total_clients = len(clients)
        iptv_count = len([c for c in clients if c.plan_type == 'IPTV'])
        vpn_count = len([c for c in clients if c.plan_type == 'VPN'])
        
        basic_stats = {
            'total_clients': total_clients,
            'iptv_count': iptv_count,
            'vpn_count': vpn_count
        }
        
        app_cache.set("basic_stats", basic_stats, ttl=120)
        
        logger.info(f"Cache warmed with {total_clients} clients and basic stats")
        
    except Exception as e:
        logger.error(f"Failed to warm cache: {str(e)}")

def get_cache_health() -> Dict[str, Any]:
    """Retorna informações de saúde do cache"""
    stats = cache_manager.get_global_stats()
    
    health = {
        'status': 'healthy',
        'issues': []
    }
    
    # Verificar hit rate baixo
    global_hit_rate = stats['global']['global_hit_rate']
    if global_hit_rate < 50:
        health['issues'].append(f"Low hit rate: {global_hit_rate}%")
    
    # Verificar uso de memória alto
    for cache_name, cache_stats in stats['caches'].items():
        if cache_stats['memory_efficiency'] > 90:
            health['issues'].append(f"Cache '{cache_name}' is {cache_stats['memory_efficiency']}% full")
    
    if health['issues']:
        health['status'] = 'warning' if len(health['issues']) < 3 else 'critical'
    
    health['stats'] = stats
    return health

# Funcionalidades para limpeza automática
def schedule_cache_cleanup():
    """Agenda limpeza automática do cache"""
    import threading
    
    def cleanup_worker():
        while True:
            time.sleep(300)  # A cada 5 minutos
            try:
                cleanup_results = cache_manager.cleanup_all()
                total_cleaned = sum(cleanup_results.values())
                if total_cleaned > 0:
                    logger.debug(f"Automatic cache cleanup: {total_cleaned} expired items removed")
            except Exception as e:
                logger.error(f"Cache cleanup failed: {str(e)}")
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("Cache cleanup scheduler started")

# Utilitários para desenvolvimento e debug
def cache_debug_info() -> str:
    """Retorna informações detalhadas do cache para debug"""
    health = get_cache_health()
    
    info = []
    info.append("=== CACHE DEBUG INFO ===")
    info.append(f"Status: {health['status']}")
    
    if health['issues']:
        info.append("Issues:")
        for issue in health['issues']:
            info.append(f"  - {issue}")
    
    info.append("\nCache Statistics:")
    for cache_name, stats in health['stats']['caches'].items():
        info.append(f"  {cache_name}:")
        info.append(f"    Hit Rate: {stats['hit_rate']}%")
        info.append(f"    Size: {stats['cache_size']}/{stats['max_size']}")
        info.append(f"    Hits/Misses: {stats['hits']}/{stats['misses']}")
    
    return "\n".join(info)