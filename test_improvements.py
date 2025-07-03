#!/usr/bin/env python3
"""
Teste das melhorias implementadas no sistema de gestão de clientes
"""
import os
import sys
import time
import json
from datetime import datetime

def test_imports():
    """Testa se todas as importações estão funcionando"""
    print("🔍 Testando importações...")
    
    try:
        # Testar validators
        from validators import ClientValidator, MessageTemplateValidator, ValidationError
        print("✅ Validators: OK")
        
        # Testar rate limiter
        from rate_limiter import rate_limiter, rate_limit, get_client_ip
        print("✅ Rate Limiter: OK")
        
        # Testar logger
        from logger_config import setup_logging, log_user_action, app_logger
        print("✅ Logger Config: OK")
        
        # Testar cache
        from simple_cache import app_cache, cached, cache_manager
        print("✅ Simple Cache: OK")
        
        # Testar backup
        from backup_utils import backup_manager, create_backup
        print("✅ Backup Utils: OK")
        
        # Testar health check
        from health_check import health_checker, get_health_status
        print("✅ Health Check: OK")
        
        return True
    except Exception as e:
        print(f"❌ Erro na importação: {e}")
        return False

def test_validators():
    """Testa o sistema de validação"""
    print("\n🔍 Testando validadores...")
    
    try:
        from validators import ClientValidator, ValidationError
        
        # Teste de dados válidos
        valid_data = {
            'name': 'João Silva',
            'phone': '11987654321',
            'plan_type': 'IPTV',
            'value': '50.00',
            'plan_duration': '2024-12-31'
        }
        
        validated = ClientValidator.validate_client_data(valid_data)
        print("✅ Validação de dados válidos: OK")
        
        # Teste de dados inválidos
        invalid_data = {
            'name': '',  # Nome vazio
            'phone': '123',  # Telefone muito curto
            'plan_type': 'INVALID',  # Tipo inválido
            'value': '-10',  # Valor negativo
            'plan_duration': 'invalid-date'  # Data inválida
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
        from simple_cache import app_cache
        
        # Teste básico de set/get
        app_cache.set('test_key', 'test_value', ttl=60)
        value = app_cache.get('test_key')
        
        if value == 'test_value':
            print("✅ Cache set/get: OK")
        else:
            print(f"❌ Cache get retornou: {value}")
            return False
        
        # Teste de TTL
        app_cache.set('test_ttl', 'will_expire', ttl=1)
        time.sleep(2)
        expired_value = app_cache.get('test_ttl')
        
        if expired_value is None:
            print("✅ Cache TTL: OK")
        else:
            print("❌ Cache TTL não funcionou")
            return False
        
        # Teste de estatísticas
        stats = app_cache.get_stats()
        if 'hits' in stats and 'misses' in stats:
            print("✅ Cache stats: OK")
        else:
            print("❌ Cache stats inválidas")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Erro no teste de cache: {e}")
        return False

def test_rate_limiter():
    """Testa o rate limiter"""
    print("\n🔍 Testando rate limiter...")
    
    try:
        from rate_limiter import rate_limiter
        
        test_ip = "127.0.0.1"
        
        # Teste básico
        allowed = rate_limiter.is_allowed(test_ip, limit=5)
        if allowed:
            print("✅ Rate limiter allow: OK")
        else:
            print("❌ Rate limiter deveria permitir primeira requisição")
            return False
        
        # Teste de limite
        for i in range(10):
            rate_limiter.is_allowed(test_ip, limit=5)
        
        blocked = not rate_limiter.is_allowed(test_ip, limit=5)
        if blocked:
            print("✅ Rate limiter block: OK")
        else:
            print("❌ Rate limiter deveria ter bloqueado")
            return False
        
        # Teste de estatísticas
        stats = rate_limiter.get_stats()
        if 'active_clients' in stats:
            print("✅ Rate limiter stats: OK")
        else:
            print("❌ Rate limiter stats inválidas")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Erro no teste de rate limiter: {e}")
        return False

def test_backup():
    """Testa o sistema de backup"""
    print("\n🔍 Testando backup...")
    
    try:
        from backup_utils import backup_manager
        from models import Client
        
        # Criar cliente de teste
        test_client = Client(
            id="test-123",
            name="Cliente Teste",
            phone="11999999999",
            plan_type="IPTV",
            value=50.0,
            plan_duration="2024-12-31"
        )
        
        # Testar backup
        backup_file = backup_manager.create_client_backup([test_client], compress=False)
        
        if backup_file and os.path.exists(backup_file):
            print("✅ Backup creation: OK")
            
            # Testar listagem de backups
            backups = backup_manager.list_backups('clients')
            if len(backups) > 0:
                print("✅ Backup listing: OK")
            else:
                print("❌ Backup listing falhou")
                return False
            
            # Limpar arquivo de teste
            try:
                os.remove(backup_file)
            except:
                pass
            
        else:
            print("❌ Backup creation falhou")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Erro no teste de backup: {e}")
        return False

def test_health_check():
    """Testa o health check"""
    print("\n🔍 Testando health check...")
    
    try:
        from health_check import health_checker, get_health_status
        
        # Teste básico
        simple_status = get_health_status(detailed=False)
        if 'status' in simple_status and 'timestamp' in simple_status:
            print("✅ Health check simple: OK")
        else:
            print("❌ Health check simple inválido")
            return False
        
        # Teste detalhado
        detailed_status = get_health_status(detailed=True)
        if 'overall_status' in detailed_status and 'checks' in detailed_status:
            print("✅ Health check detailed: OK")
        else:
            print("❌ Health check detailed inválido")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Erro no teste de health check: {e}")
        return False

def test_logging():
    """Testa o sistema de logging"""
    print("\n🔍 Testando logging...")
    
    try:
        from logger_config import setup_logging, log_user_action, app_logger
        
        # Configurar logging
        logger = setup_logging(log_level='INFO', enable_file_logging=False)
        
        # Teste de log básico
        log_user_action("TEST_ACTION", "Testing logging system", "127.0.0.1")
        print("✅ User action log: OK")
        
        # Teste de log estruturado
        app_logger.log_action("test_action", level="INFO", test_data="test_value")
        print("✅ Structured log: OK")
        
        return True
    except Exception as e:
        print(f"❌ Erro no teste de logging: {e}")
        return False

def run_all_tests():
    """Executa todos os testes"""
    print("🚀 Iniciando testes das melhorias implementadas\n")
    
    tests = [
        ("Importações", test_imports),
        ("Validadores", test_validators),
        ("Cache", test_cache),
        ("Rate Limiter", test_rate_limiter),
        ("Backup", test_backup),
        ("Health Check", test_health_check),
        ("Logging", test_logging)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}: ERRO - {e}")
            results.append((test_name, False))
    
    print("\n" + "="*50)
    print("📊 RESUMO DOS TESTES")
    print("="*50)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{test_name:.<30} {status}")
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 Total: {len(results)} testes")
    print(f"✅ Passou: {passed}")
    print(f"❌ Falhou: {failed}")
    
    if failed == 0:
        print("\n🎉 TODOS OS TESTES PASSARAM! Sistema pronto para uso.")
        return True
    else:
        print(f"\n⚠️  {failed} teste(s) falharam. Revisar implementação.")
        return False

def create_test_summary():
    """Cria um resumo das melhorias para documentação"""
    summary = {
        "melhorias_implementadas": {
            "validacao_robusta": {
                "arquivo": "validators.py",
                "descricao": "Sistema completo de validação de dados",
                "funcionalidades": [
                    "Validação de telefones brasileiros",
                    "Sanitização de dados",
                    "Validação de valores monetários",
                    "Validação de datas",
                    "Mensagens de erro detalhadas"
                ]
            },
            "rate_limiting": {
                "arquivo": "rate_limiter.py", 
                "descricao": "Proteção contra spam e abuso",
                "funcionalidades": [
                    "Limits configuráveis por endpoint",
                    "Tracking por IP",
                    "Cleanup automático",
                    "Estatísticas detalhadas"
                ]
            },
            "logging_estruturado": {
                "arquivo": "logger_config.py",
                "descricao": "Sistema de logs avançado",
                "funcionalidades": [
                    "Logs em formato JSON",
                    "Context managers",
                    "Diferentes níveis e outputs",
                    "Logs coloridos no console"
                ]
            },
            "cache_inteligente": {
                "arquivo": "simple_cache.py",
                "descricao": "Cache em memória com TTL e LRU",
                "funcionalidades": [
                    "TTL configurável",
                    "LRU eviction",
                    "Múltiplas instâncias",
                    "Estatísticas de performance"
                ]
            },
            "backup_automatico": {
                "arquivo": "backup_utils.py",
                "descricao": "Sistema de backup robusto",
                "funcionalidades": [
                    "Backups comprimidos",
                    "Backup automático antes de mudanças",
                    "Cleanup de arquivos antigos",
                    "Restauração de dados"
                ]
            },
            "health_monitoring": {
                "arquivo": "health_check.py",
                "descricao": "Monitoramento completo do sistema",
                "funcionalidades": [
                    "Checks de recursos do sistema",
                    "Verificação de serviços externos",
                    "Score de saúde",
                    "Alertas automáticos"
                ]
            }
        },
        "apis_adicionadas": [
            "/health - Health check simples",
            "/health/detailed - Health check detalhado", 
            "/api/cache/stats - Estatísticas de cache",
            "/api/cache/clear - Limpar cache",
            "/api/backup/create - Criar backup manual",
            "/api/backup/list - Listar backups",
            "/api/rate-limit/stats - Stats do rate limiter",
            "/api/validation/test - Testar validação"
        ],
        "melhorias_nas_rotas": [
            "Rate limiting em todas as rotas críticas",
            "Validação robusta de dados",
            "Logging estruturado de ações",
            "Cache automático no dashboard",
            "Backup antes de modificações",
            "Invalidação inteligente de cache"
        ],
        "configuracao_app": [
            "Logging estruturado configurado",
            "Rate limiting global aplicado",
            "Serviços de background iniciados",
            "Cache aquecido na inicialização",
            "Tratamento robusto de erros"
        ],
        "compatibilidade": {
            "github_storage": "✅ Mantido como storage principal",
            "apis_existentes": "✅ Compatibilidade total",
            "interface_mobile": "✅ Mantida e melhorada",
            "sistema_mensagens": "✅ Integração completa"
        }
    }
    
    with open('MELHORIAS_IMPLEMENTADAS.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print("📄 Resumo das melhorias salvo em: MELHORIAS_IMPLEMENTADAS.json")

if __name__ == '__main__':
    print("🔧 TESTE DAS MELHORIAS - Sistema de Gestão de Clientes")
    print("="*60)
    
    # Verificar se está no diretório correto
    if not os.path.exists('app.py'):
        print("❌ Execute este script no diretório raiz do projeto")
        sys.exit(1)
    
    # Executar testes
    success = run_all_tests()
    
    # Criar resumo
    create_test_summary()
    
    if success:
        print("\n🚀 Sistema pronto para deploy!")
        sys.exit(0)
    else:
        print("\n⚠️  Revisar falhas antes do deploy")
        sys.exit(1)