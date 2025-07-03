import json
import os
import gzip
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from models import Client, MessageTemplate

logger = logging.getLogger(__name__)

class BackupManager:
    """Gerenciador de backup que funciona junto com o GitHub storage"""
    
    def __init__(self, backup_dir: str = 'backups', max_backups: int = 20):
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.backup_dir.mkdir(exist_ok=True)
        
        # Subdiretórios para organização
        (self.backup_dir / 'clients').mkdir(exist_ok=True)
        (self.backup_dir / 'templates').mkdir(exist_ok=True)
        (self.backup_dir / 'system').mkdir(exist_ok=True)
    
    def create_client_backup(self, clients: List[Client], compress: bool = True) -> Optional[str]:
        """
        Cria backup dos clientes
        
        Args:
            clients: Lista de clientes
            compress: Se deve comprimir o backup
            
        Returns:
            Caminho do arquivo de backup criado ou None se falhou
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Preparar dados do backup
            backup_data = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'total_clients': len(clients),
                    'backup_type': 'clients',
                    'version': '1.0',
                    'source': 'github_storage'
                },
                'clients': [client.to_dict() for client in clients]
            }
            
            # Determinar nome e extensão do arquivo
            filename = f"clients_backup_{timestamp}"
            if compress:
                filename += ".json.gz"
                filepath = self.backup_dir / 'clients' / filename
                
                # Salvar comprimido
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            else:
                filename += ".json"
                filepath = self.backup_dir / 'clients' / filename
                
                # Salvar sem compressão
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            
            # Log do backup criado
            file_size = filepath.stat().st_size
            logger.info(
                f"Client backup created: {filename} "
                f"({len(clients)} clients, {file_size} bytes)"
            )
            
            # Limpar backups antigos
            self._cleanup_old_backups('clients')
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to create client backup: {str(e)}", exc_info=True)
            return None
    
    def create_template_backup(self, templates: List[MessageTemplate], compress: bool = True) -> Optional[str]:
        """Cria backup dos templates de mensagem"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            backup_data = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'total_templates': len(templates),
                    'backup_type': 'templates',
                    'version': '1.0',
                    'source': 'github_storage'
                },
                'templates': [template.to_dict() for template in templates]
            }
            
            filename = f"templates_backup_{timestamp}"
            if compress:
                filename += ".json.gz"
                filepath = self.backup_dir / 'templates' / filename
                
                with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            else:
                filename += ".json"
                filepath = self.backup_dir / 'templates' / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Template backup created: {filename} ({len(templates)} templates)")
            self._cleanup_old_backups('templates')
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to create template backup: {str(e)}", exc_info=True)
            return None
    
    def create_system_backup(self) -> Optional[str]:
        """Cria backup completo do sistema"""
        try:
            from github_storage import storage
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Coletar dados do sistema
            clients = storage.get_clients()
            templates = storage.get_message_templates()
            storage_stats = storage.get_storage_stats()
            
            backup_data = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'backup_type': 'system_complete',
                    'version': '1.0',
                    'total_clients': len(clients),
                    'total_templates': len(templates),
                    'storage_stats': storage_stats
                },
                'clients': [client.to_dict() for client in clients],
                'templates': [template.to_dict() for template in templates]
            }
            
            filename = f"system_backup_{timestamp}.json.gz"
            filepath = self.backup_dir / 'system' / filename
            
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            
            file_size = filepath.stat().st_size
            logger.info(
                f"System backup created: {filename} "
                f"({len(clients)} clients, {len(templates)} templates, {file_size} bytes)"
            )
            
            self._cleanup_old_backups('system')
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to create system backup: {str(e)}", exc_info=True)
            return None
    
    def restore_from_backup(self, backup_file: str) -> Dict[str, Any]:
        """
        Restaura dados de um arquivo de backup
        
        Returns:
            Dicionário com resultado da restauração
        """
        try:
            filepath = Path(backup_file)
            if not filepath.exists():
                return {'success': False, 'error': 'Backup file not found'}
            
            # Determinar se é comprimido
            if filepath.suffix == '.gz':
                with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                    backup_data = json.load(f)
            else:
                with open(filepath, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
            
            # Validar estrutura do backup
            if 'metadata' not in backup_data:
                return {'success': False, 'error': 'Invalid backup format'}
            
            metadata = backup_data['metadata']
            backup_type = metadata.get('backup_type', 'unknown')
            
            result = {
                'success': True,
                'backup_type': backup_type,
                'timestamp': metadata.get('timestamp'),
                'restored': {}
            }
            
            # Restaurar clientes se existirem
            if 'clients' in backup_data:
                clients_data = backup_data['clients']
                clients = [Client.from_dict(data) for data in clients_data]
                result['restored']['clients'] = len(clients)
                logger.info(f"Restored {len(clients)} clients from backup")
            
            # Restaurar templates se existirem
            if 'templates' in backup_data:
                templates_data = backup_data['templates']
                templates = [MessageTemplate.from_dict(data) for data in templates_data]
                result['restored']['templates'] = len(templates)
                logger.info(f"Restored {len(templates)} templates from backup")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to restore from backup: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def list_backups(self, backup_type: str = None) -> List[Dict[str, Any]]:
        """Lista backups disponíveis"""
        try:
            backups = []
            
            # Diretórios para verificar
            dirs_to_check = ['clients', 'templates', 'system']
            if backup_type:
                dirs_to_check = [backup_type] if backup_type in dirs_to_check else []
            
            for dir_name in dirs_to_check:
                backup_subdir = self.backup_dir / dir_name
                if not backup_subdir.exists():
                    continue
                
                for backup_file in backup_subdir.glob('*.json*'):
                    try:
                        stat = backup_file.stat()
                        
                        # Tentar extrair informações do arquivo
                        backup_info = {
                            'filename': backup_file.name,
                            'path': str(backup_file),
                            'type': dir_name,
                            'size_bytes': stat.st_size,
                            'size_mb': round(stat.st_size / (1024 * 1024), 2),
                            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'compressed': backup_file.suffix == '.gz'
                        }
                        
                        # Tentar ler metadata do backup
                        try:
                            if backup_file.suffix == '.gz':
                                with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                                    data = json.load(f)
                            else:
                                with open(backup_file, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                            
                            if 'metadata' in data:
                                metadata = data['metadata']
                                backup_info.update({
                                    'total_clients': metadata.get('total_clients', 0),
                                    'total_templates': metadata.get('total_templates', 0),
                                    'backup_timestamp': metadata.get('timestamp'),
                                    'version': metadata.get('version')
                                })
                        except:
                            # Se não conseguir ler, continua com info básica
                            pass
                        
                        backups.append(backup_info)
                        
                    except Exception as e:
                        logger.warning(f"Failed to get info for backup {backup_file}: {e}")
            
            # Ordenar por data de criação (mais recente primeiro)
            backups.sort(key=lambda x: x['created'], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {str(e)}")
            return []
    
    def delete_backup(self, backup_path: str) -> bool:
        """Deleta um backup específico"""
        try:
            filepath = Path(backup_path)
            if filepath.exists() and filepath.is_file():
                filepath.unlink()
                logger.info(f"Deleted backup: {backup_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_path}: {str(e)}")
            return False
    
    def _cleanup_old_backups(self, backup_type: str):
        """Remove backups antigos mantendo apenas os mais recentes"""
        try:
            backup_subdir = self.backup_dir / backup_type
            backup_files = list(backup_subdir.glob('*.json*'))
            
            # Ordenar por data de modificação (mais antigo primeiro)
            backup_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Remover arquivos excedentes
            if len(backup_files) > self.max_backups:
                files_to_remove = backup_files[:-self.max_backups]
                for file_to_remove in files_to_remove:
                    try:
                        file_to_remove.unlink()
                        logger.debug(f"Removed old backup: {file_to_remove.name}")
                    except Exception as e:
                        logger.warning(f"Failed to remove old backup {file_to_remove}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to cleanup old backups for {backup_type}: {str(e)}")
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas dos backups"""
        try:
            stats = {
                'backup_dir': str(self.backup_dir),
                'max_backups': self.max_backups,
                'types': {}
            }
            
            total_size = 0
            total_files = 0
            
            for backup_type in ['clients', 'templates', 'system']:
                type_stats = {
                    'count': 0,
                    'total_size_bytes': 0,
                    'total_size_mb': 0,
                    'oldest': None,
                    'newest': None
                }
                
                backup_subdir = self.backup_dir / backup_type
                if backup_subdir.exists():
                    files = list(backup_subdir.glob('*.json*'))
                    type_stats['count'] = len(files)
                    total_files += len(files)
                    
                    if files:
                        # Calcular tamanho total
                        type_size = sum(f.stat().st_size for f in files)
                        type_stats['total_size_bytes'] = type_size
                        type_stats['total_size_mb'] = round(type_size / (1024 * 1024), 2)
                        total_size += type_size
                        
                        # Encontrar mais antigo e mais novo
                        files_with_time = [(f, f.stat().st_mtime) for f in files]
                        files_with_time.sort(key=lambda x: x[1])
                        
                        type_stats['oldest'] = datetime.fromtimestamp(files_with_time[0][1]).isoformat()
                        type_stats['newest'] = datetime.fromtimestamp(files_with_time[-1][1]).isoformat()
                
                stats['types'][backup_type] = type_stats
            
            stats['total'] = {
                'files': total_files,
                'size_bytes': total_size,
                'size_mb': round(total_size / (1024 * 1024), 2)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get backup stats: {str(e)}")
            return {}

# Instância global
backup_manager = BackupManager()

def create_backup(clients: List[Client]) -> bool:
    """Função de conveniência para criar backup de clientes"""
    result = backup_manager.create_client_backup(clients)
    return result is not None

def create_template_backup(templates: List[MessageTemplate]) -> bool:
    """Função de conveniência para criar backup de templates"""
    result = backup_manager.create_template_backup(templates)
    return result is not None

def create_system_backup() -> bool:
    """Função de conveniência para criar backup completo do sistema"""
    result = backup_manager.create_system_backup()
    return result is not None

def auto_backup_before_changes(data_type: str = 'system'):
    """
    Decorador para criar backup automático antes de modificações
    
    Args:
        data_type: Tipo de backup ('clients', 'templates', 'system')
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Criar backup antes da modificação
                if data_type == 'system':
                    backup_manager.create_system_backup()
                elif data_type == 'clients':
                    from github_storage import storage
                    clients = storage.get_clients()
                    backup_manager.create_client_backup(clients)
                elif data_type == 'templates':
                    from github_storage import storage
                    templates = storage.get_message_templates()
                    backup_manager.create_template_backup(templates)
                
                # Executar função original
                result = func(*args, **kwargs)
                
                logger.debug(f"Auto-backup created before {func.__name__}")
                return result
                
            except Exception as e:
                logger.error(f"Auto-backup failed before {func.__name__}: {str(e)}")
                # Continuar com a execução mesmo se backup falhar
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def cleanup_old_backups(days: int = 30) -> int:
    """Remove backups mais antigos que X dias"""
    try:
        cutoff_time = datetime.now() - timedelta(days=days)
        cutoff_timestamp = cutoff_time.timestamp()
        
        removed_count = 0
        
        for backup_type in ['clients', 'templates', 'system']:
            backup_subdir = backup_manager.backup_dir / backup_type
            if not backup_subdir.exists():
                continue
            
            for backup_file in backup_subdir.glob('*.json*'):
                try:
                    if backup_file.stat().st_mtime < cutoff_timestamp:
                        backup_file.unlink()
                        removed_count += 1
                        logger.debug(f"Removed old backup: {backup_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove old backup {backup_file}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleanup completed: {removed_count} old backups removed")
        
        return removed_count
        
    except Exception as e:
        logger.error(f"Backup cleanup failed: {str(e)}")
        return 0

def get_backup_health() -> Dict[str, Any]:
    """Verifica a saúde do sistema de backup"""
    try:
        stats = backup_manager.get_backup_stats()
        health = {
            'status': 'healthy',
            'issues': [],
            'stats': stats
        }
        
        # Verificar se há backups recentes
        recent_backup_hours = 24
        cutoff_time = datetime.now() - timedelta(hours=recent_backup_hours)
        
        has_recent_backup = False
        for backup_type, type_stats in stats['types'].items():
            if type_stats['newest']:
                newest_time = datetime.fromisoformat(type_stats['newest'])
                if newest_time > cutoff_time:
                    has_recent_backup = True
                    break
        
        if not has_recent_backup:
            health['issues'].append(f"No recent backups in the last {recent_backup_hours} hours")
        
        # Verificar uso de espaço
        total_size_mb = stats['total']['size_mb']
        if total_size_mb > 100:  # Mais de 100MB
            health['issues'].append(f"Backup storage using {total_size_mb}MB")
        
        # Verificar se há muitos backups
        total_files = stats['total']['files']
        if total_files > backup_manager.max_backups * 3:
            health['issues'].append(f"Too many backup files: {total_files}")
        
        if health['issues']:
            health['status'] = 'warning' if len(health['issues']) < 3 else 'critical'
        
        return health
        
    except Exception as e:
        logger.error(f"Failed to check backup health: {str(e)}")
        return {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'stats': {}
        }

# Função para agendar backups automáticos
def schedule_automatic_backups():
    """Agenda backups automáticos"""
    import threading
    import time
    
    def backup_worker():
        while True:
            try:
                # Fazer backup completo a cada 6 horas
                time.sleep(6 * 3600)  
                backup_manager.create_system_backup()
                logger.info("Automatic system backup completed")
                
                # Cleanup de backups antigos a cada backup
                cleanup_old_backups(days=7)
                
            except Exception as e:
                logger.error(f"Automatic backup failed: {str(e)}")
    
    backup_thread = threading.Thread(target=backup_worker, daemon=True)
    backup_thread.start()
    logger.info("Automatic backup scheduler started (6-hour interval)")