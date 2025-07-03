import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

class HealthChecker:
    """Sistema de health check para monitoramento completo"""
    
    def __init__(self):
        self.start_time = time.time()
        self.checks = {}
        self.register_default_checks()
    
    def register_check(self, name: str, check_func):
        """Registra um check personalizado"""
        self.checks[name] = check_func
    
    def register_default_checks(self):
        """Registra checks padrão do sistema"""
        self.checks['system_resources'] = self._check_system_resources
        self.checks['github_storage'] = self._check_github_storage
        self.checks['whatsapp_connection'] = self._check_whatsapp
        self.checks['message_queue'] = self._check_message_queue
        self.checks['cache_health'] = self._check_cache
        self.checks['backup_health'] = self._check_backups
        self.checks['rate_limiter'] = self._check_rate_limiter
    
    def _check_system_resources(self) -> Dict[str, Any]:
        """Verifica recursos do sistema"""
        try:
            import psutil
            
            # CPU e Memória
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Verificar se está dentro dos limites aceitáveis
            issues = []
            if cpu_percent > 80:
                issues.append(f"High CPU usage: {cpu_percent}%")
            if memory.percent > 85:
                issues.append(f"High memory usage: {memory.percent}%")
            if disk.percent > 90:
                issues.append(f"High disk usage: {disk.percent}%")
            
            health_score = self._calculate_health_score(cpu_percent, memory.percent, disk.percent)
            
            return {
                'status': 'healthy' if not issues else 'warning',
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'health_score': health_score,
                'issues': issues,
                'uptime_seconds': round(time.time() - self.start_time, 2)
            }
        except ImportError:
            return {
                'status': 'warning',
                'message': 'psutil not available - system monitoring disabled',
                'uptime_seconds': round(time.time() - self.start_time, 2)
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_github_storage(self) -> Dict[str, Any]:
        """Verifica conectividade com GitHub storage"""
        try:
            from github_storage import storage
            
            stats = storage.get_storage_stats()
            
            issues = []
            status = 'healthy'
            
            if stats.get('connection_status') != 'connected':
                issues.append("GitHub storage disconnected")
                status = 'critical'
            
            rate_limit = stats.get('rate_limit_remaining', 0)
            if rate_limit < 100:
                issues.append(f"Low GitHub rate limit: {rate_limit}")
                status = 'warning' if status == 'healthy' else status
            
            return {
                'status': status,
                'connection_status': stats.get('connection_status'),
                'clients_count': stats.get('clients_count', 0),
                'rate_limit_remaining': rate_limit,
                'issues': issues
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_whatsapp(self) -> Dict[str, Any]:
        """Verifica conexão WhatsApp"""
        try:
            from whatsapp_integration import is_whatsapp_connected, get_whatsapp_status
            
            connected = is_whatsapp_connected()
            status_info = get_whatsapp_status()
            
            return {
                'status': 'healthy' if connected else 'warning',
                'connected': connected,
                'connection_status': status_info.get('status', 'unknown'),
                'last_activity': status_info.get('last_activity'),
                'issues': [] if connected else ['WhatsApp not connected']
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_message_queue(self) -> Dict[str, Any]:
        """Verifica saúde da fila de mensagens"""
        try:
            from message_queue import get_queue_status
            
            queue_status = get_queue_status()
            
            issues = []
            status = 'healthy'
            
            queue_size = queue_status.get('queue_size', 0)
            if queue_size > 100:
                issues.append(f"Large queue size: {queue_size}")
                status = 'warning'
            
            failed_count = queue_status.get('failed_count', 0)
            if failed_count > 10:
                issues.append(f"High failure count: {failed_count}")
                status = 'warning' if status == 'healthy' else status
            
            if not queue_status.get('processing', False):
                issues.append("Queue processing stopped")
                status = 'critical'
            
            return {
                'status': status,
                'queue_size': queue_size,
                'processing': queue_status.get('processing', False),
                'failed_count': failed_count,
                'success_rate': queue_status.get('success_rate', 0),
                'issues': issues
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_cache(self) -> Dict[str, Any]:
        """Verifica saúde do sistema de cache"""
        try:
            from simple_cache import get_cache_health
            
            health = get_cache_health()
            return health
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_backups(self) -> Dict[str, Any]:
        """Verifica saúde do sistema de backup"""
        try:
            from backup_utils import get_backup_health
            
            health = get_backup_health()
            return health
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _check_rate_limiter(self) -> Dict[str, Any]:
        """Verifica funcionamento do rate limiter"""
        try:
            from rate_limiter import get_rate_limit_stats
            
            stats = get_rate_limit_stats()
            
            issues = []
            status = 'healthy'
            
            active_clients = stats.get('active_clients', 0)
            if active_clients > 1000:
                issues.append(f"High number of tracked IPs: {active_clients}")
                status = 'warning'
            
            return {
                'status': status,
                'active_clients': active_clients,
                'total_requests': stats.get('total_requests', 0),
                'window_seconds': stats.get('window_seconds', 60),
                'default_limit': stats.get('default_limit', 60),
                'issues': issues
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _calculate_health_score(self, cpu: float, memory: float, disk: float) -> float:
        """Calcula score de saúde do sistema (0-100)"""
        # Penalizar uso alto de recursos
        cpu_score = max(0, 100 - cpu)
        memory_score = max(0, 100 - memory)
        disk_score = max(0, 100 - disk)
        
        # Média ponderada (CPU e memória são mais importantes)
        return round((cpu_score * 0.4 + memory_score * 0.4 + disk_score * 0.2), 1)
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Executa todos os health checks"""
        results = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'overall_status': 'healthy',
            'checks': {},
            'summary': {
                'healthy': 0,
                'warning': 0,
                'critical': 0,
                'error': 0
            }
        }
        
        for name, check_func in self.checks.items():
            try:
                check_result = check_func()
                results['checks'][name] = check_result
                
                # Contar status
                status = check_result.get('status', 'error')
                if status in results['summary']:
                    results['summary'][status] += 1
                else:
                    results['summary']['error'] += 1
                    
            except Exception as e:
                logger.error(f"Health check '{name}' failed: {str(e)}")
                results['checks'][name] = {
                    'status': 'error',
                    'error': f"Check failed: {str(e)}"
                }
                results['summary']['error'] += 1
        
        # Determinar status geral
        if results['summary']['critical'] > 0:
            results['overall_status'] = 'critical'
        elif results['summary']['error'] > 0:
            results['overall_status'] = 'error'
        elif results['summary']['warning'] > 0:
            results['overall_status'] = 'warning'
        else:
            results['overall_status'] = 'healthy'
        
        return results
    
    def get_simple_status(self) -> Dict[str, Any]:
        """Retorna status simplificado para endpoints rápidos"""
        try:
            # Checks rápidos apenas
            quick_checks = ['github_storage', 'whatsapp_connection']
            
            status = 'healthy'
            issues = []
            
            for check_name in quick_checks:
                if check_name in self.checks:
                    result = self.checks[check_name]()
                    check_status = result.get('status', 'error')
                    
                    if check_status in ['critical', 'error']:
                        status = 'critical'
                        issues.extend(result.get('issues', []))
                    elif check_status == 'warning' and status == 'healthy':
                        status = 'warning'
                        issues.extend(result.get('issues', []))
            
            return {
                'status': status,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'uptime_seconds': round(time.time() - self.start_time, 2),
                'issues': issues[:3]  # Limitar a 3 issues principais
            }
        except Exception as e:
            return {
                'status': 'error',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'error': str(e)
            }

# Instância global
health_checker = HealthChecker()

def get_health_status(detailed: bool = False) -> Dict[str, Any]:
    """
    Função de conveniência para obter status de saúde
    
    Args:
        detailed: Se deve executar todos os checks (lento) ou apenas os básicos
    """
    if detailed:
        return health_checker.run_all_checks()
    else:
        return health_checker.get_simple_status()

def is_system_healthy() -> bool:
    """Verifica se o sistema está saudável (check rápido)"""
    try:
        status = health_checker.get_simple_status()
        return status.get('status') in ['healthy', 'warning']
    except:
        return False

def get_uptime() -> float:
    """Retorna uptime em segundos"""
    return time.time() - health_checker.start_time

def add_custom_check(name: str, check_func):
    """Adiciona um check personalizado"""
    health_checker.register_check(name, check_func)