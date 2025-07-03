#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste das melhorias implementadas no sistema
"""
import os
import sys
import json
import time
from datetime import datetime

def test_imports():
    """Testa importação de módulos das melhorias"""
    print("🔍 Testando importações...")
    test_results = {}
    
    try:
        from validators import ClientValidator, MessageTemplateValidator, ValidationError
        test_results['validators'] = True
        print("✅ Validators: OK")
    except Exception as e:
        test_results['validators'] = False
        print(f"❌ Erro na importação de validators: {e}")
    
    try:
        from simple_cache import SimpleCache, CacheManager
        test_results['cache'] = True
        print("✅ Cache: OK")
    except Exception as e:
        test_results['cache'] = False
        print(f"❌ Erro na importação de cache: {e}")
    
    try:
        from rate_limiter import SimpleRateLimiter
        test_results['rate_limiter'] = True
        print("✅ Rate Limiter: OK")
    except Exception as e:
        test_results['rate_limiter'] = False
        print(f"❌ Erro na importação de rate limiter: {e}")
    
    try:
        from logger_config import setup_logging, StructuredLogger
        test_results['logging'] = True
        print("✅ Logging: OK")
    except Exception as e:
        test_results['logging'] = False
        print(f"❌ Erro na importação de logging: {e}")
    
    try:
        from backup_utils import BackupManager
        test_results['backup'] = True
        print("✅ Backup: OK")
    except Exception as e:
        test_results['backup'] = False
        print(f"❌ Erro na importação de backup: {e}")
    
    try:
        from health_check import HealthChecker
        test_results['health'] = True
        print("✅ Health Check: OK")
    except Exception as e:
        test_results['health'] = False
        print(f"❌ Erro na importação de health check: {e}")
    
    return test_results

def test_validators():
    """Testa o sistema de validação"""
    print("\n🔍 Testando validadores...")
    try:
        from validators import ClientValidator, ValidationError
        
        # Teste com dados válidos
        valid_data = {
            'name': 'João Silva',
            'phone': '5511999888777',
            'plan_type': 'IPTV',
            'value': '29.90',
            'plan_duration': '2025-01-15',
            'reminder_time_3days': '09:00',
            'reminder_time_payment': '10:00',
            'custom_message_3days': '',
            'custom_message_payment': ''
        }
        
        validated = ClientValidator.validate_client_data(valid_data)
        print("✅ Validação de dados válidos: OK")
        
        # Teste com dados inválidos
        invalid_data = {
            'name': '',  # Nome vazio
            'phone': '123',  # Telefone inválido
            'plan_type': 'INVALID',  # Tipo inválido
            'value': '-10',  # Valor negativo
            'plan_duration': '2020-01-01',  # Data no passado
        }
        
        try:
            ClientValidator.validate_client_data(invalid_data)
            print("❌ Validação deveria ter falhado")
            return False
        except ValueError:
            print("✅ Validação de dados inválidos: OK")
            return True
            
    except Exception as e:
        print(f"❌ Erro no teste de validadores: {e}")
        return False

def test_cache():
    """Testa o sistema de cache"""
    print("\n🔍 Testando cache...")
    try:
        from simple_cache import SimpleCache
        
        cache = SimpleCache(max_size=100, default_ttl=60)
        
        # Teste set/get
        cache.set('test_key', 'test_value')
        value = cache.get('test_key')
        if value == 'test_value':
            print("✅ Cache set/get: OK")
        else:
            print("❌ Cache set/get: FALHOU")
            return False
        
        # Teste TTL
        cache.set('ttl_key', 'ttl_value', ttl=1)
        time.sleep(1.1)
        expired_value = cache.get('ttl_key')
        if expired_value is None:
            print("✅ Cache TTL: OK")
        else:
            print("❌ Cache TTL: FALHOU")
            return False
        
        # Teste estatísticas
        stats = cache.get_stats()
        if 'hits' in stats and 'misses' in stats:
            print("✅ Cache stats: OK")
            return True
        else:
            print("❌ Cache stats: FALHOU")
            return False
            
    except Exception as e:
        print(f"❌ Erro no teste de cache: {e}")
        return False

def test_rate_limiter():
    """Testa o sistema de rate limiting"""
    print("\n🔍 Testando rate limiter...")
    try:
        from rate_limiter import SimpleRateLimiter
        
        limiter = SimpleRateLimiter()
        
        # Teste básico de rate limiting
        ip = '127.0.0.1'
        
        # Primeiro deve passar
        if limiter.is_allowed(ip, limit=2):
            print("✅ Rate limiter first request: OK")
        else:
            print("❌ Rate limiter first request: FALHOU")
            return False
        
        # Segundo deve passar
        if limiter.is_allowed(ip, limit=2):
            print("✅ Rate limiter second request: OK")
        else:
            print("❌ Rate limiter second request: FALHOU")
            return False
        
        # Terceiro deve falhar (sem parâmetro nomeado extra)
        if not limiter.is_allowed(ip, limit=2):
            print("✅ Rate limiter rate limit: OK")
            return True
        else:
            print("❌ Rate limiter rate limit: FALHOU")
            return False
            
    except Exception as e:
        print(f"❌ Erro no teste de rate limiter: {e}")
        return False

def test_backup():
    """Testa o sistema de backup"""
    print("\n🔍 Testando backup...")
    try:
        from backup_utils import BackupManager
        
        backup_manager = BackupManager()
        
        # Teste criação de backup (simular dados de cliente)
        from models import Client
        test_client = Client(
            id='test-123',
            name='Cliente Teste',
            phone='5511999999999',
            plan_type='IPTV',
            value=50.0,
            plan_duration='2025-12-31'
        )
        backup_file = backup_manager.create_client_backup([test_client], compress=False)
        
        if backup_file and os.path.exists(backup_file):
            print("✅ Backup creation: OK")
        else:
            print("❌ Backup creation: FALHOU")
            return False
        
        # Teste listagem de backups
        backups = backup_manager.list_backups('clients')
        if len(backups) > 0:
            print("✅ Backup listing: OK")
        else:
            print("❌ Backup listing: FALHOU")
            return False
        
        # Cleanup
        if backup_file and os.path.exists(backup_file):
            os.remove(backup_file)
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste de backup: {e}")
        return False

def test_health_check():
    """Testa o sistema de health check"""
    print("\n🔍 Testando health check...")
    try:
        from health_check import HealthChecker
        
        health_checker = HealthChecker()
        
        # Teste health check simples
        status = health_checker.get_simple_status()
        if isinstance(status, dict) and 'status' in status:
            print("✅ Health check simple: OK")
        else:
            print("❌ Health check simple: FALHOU")
            return False
        
        # Teste health check detalhado
        detailed = health_checker.run_all_checks()
        if isinstance(detailed, dict) and 'checks' in detailed:
            print("✅ Health check detailed: OK")
            return True
        else:
            print("❌ Health check detailed: FALHOU")
            return False
            
    except Exception as e:
        print(f"❌ Erro no teste de health check: {e}")
        return False

def test_logging():
    """Testa o sistema de logging"""
    print("\n🔍 Testando logging...")
    try:
        from logger_config import log_user_action, log_with_context, app_logger
        
        # Teste log de ação do usuário
        log_user_action("TEST_ACTION", "Testing logging system", "127.0.0.1")
        print("✅ User action log: OK")
        
        # Teste log estruturado
        with log_with_context(action="test_action"):
            app_logger.log_action("test_action")
        print("✅ Structured log: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste de logging: {e}")
        return False

def create_test_summary(results):
    """Cria resumo dos testes"""
    summary = {
        'timestamp': datetime.now().isoformat(),
        'test_results': results,
        'total_tests': len(results),
        'passed_tests': sum(1 for result in results.values() if result),
        'failed_tests': sum(1 for result in results.values() if not result),
        'success_rate': sum(1 for result in results.values() if result) / len(results) * 100
    }
    
    # Adicionar informações das melhorias implementadas
    summary['improvements_implemented'] = {
        'validators': 'Sistema de validação robusta com validação de telefones brasileiros',
        'rate_limiter': 'Rate limiting thread-safe com diferentes limitadores',
        'cache': 'Cache inteligente em memória com TTL e LRU',
        'logging': 'Sistema de logging estruturado para desenvolvimento e produção',
        'backup': 'Sistema de backup automático com compressão',
        'health_check': 'Monitoramento de recursos e conectividade'
    }
    
    # Salvar resumo
    with open('MELHORIAS_IMPLEMENTADAS.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    return summary

def main():
    """Função principal de teste"""
    print("🔧 TESTE DAS MELHORIAS - Sistema de Gestão de Clientes")
    print("=" * 60)
    print("🚀 Iniciando testes das melhorias implementadas\n")
    
    # Executar todos os testes
    all_results = {}
    
    # Testes de importação
    import_results = test_imports()
    all_results.update(import_results)
    
    # Testes funcionais (apenas se as importações funcionaram)
    tests = [
        ('Validadores', test_validators),
        ('Cache', test_cache),
        ('Rate Limiter', test_rate_limiter),
        ('Backup', test_backup),
        ('Health Check', test_health_check),
        ('Logging', test_logging)
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            all_results[test_name.lower().replace(' ', '_')] = result
        except Exception as e:
            print(f"❌ Erro no teste {test_name}: {e}")
            all_results[test_name.lower().replace(' ', '_')] = False
    
    # Criar resumo
    summary = create_test_summary(all_results)
    
    # Exibir resultados finais
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES")
    print("=" * 50)
    
    for test_name, result in all_results.items():
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{test_name.replace('_', ' ').title():<20}... {status}")
    
    print(f"\n📈 Total: {summary['total_tests']} testes")
    print(f"✅ Passou: {summary['passed_tests']}")
    print(f"❌ Falhou: {summary['failed_tests']}")
    
    if summary['failed_tests'] > 0:
        print(f"\n⚠️  {summary['failed_tests']} teste(s) falharam. Revisar implementação.")
    else:
        print(f"\n🎉 Todos os testes passaram! Taxa de sucesso: {summary['success_rate']:.1f}%")
    
    print(f"📄 Resumo das melhorias salvo em: MELHORIAS_IMPLEMENTADAS.json")
    
    if summary['failed_tests'] > 0:
        print(f"\n⚠️  Revisar falhas antes do deploy")
        sys.exit(1)
    else:
        print(f"\n✅ Sistema pronto para uso!")
        sys.exit(0)

if __name__ == "__main__":
    main()