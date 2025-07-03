from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app, scheduler
import uuid
from datetime import datetime
from github_storage import storage
from models import Client, MessageTemplate
from reminder_scheduler import setup_reminders, get_upcoming_reminders
from whatsapp_integration import get_whatsapp_qr_code, is_whatsapp_connected, connect_whatsapp, disconnect_whatsapp

# Importar melhorias implementadas
from validators import ClientValidator, MessageTemplateValidator, ValidationError
from rate_limiter import rate_limit_form, rate_limit_api, rate_limit_sensitive, get_client_ip
from logger_config import log_user_action, log_with_context, app_logger, client_logger
from simple_cache import cache_dashboard_stats, cache_client_list, app_cache, invalidate_cache_pattern
from backup_utils import create_backup, auto_backup_before_changes
import logging

logger = logging.getLogger(__name__)

# Temporarily comment out to isolate wrapper conflict
# @app.route('/')
# @cache_dashboard_stats(ttl=120)  # Cache por 2 minutos
# def dashboard():
    """Dashboard with statistics and upcoming reminders"""
    client_ip = get_client_ip()
    
    with log_with_context(user_ip=client_ip, action="dashboard_view"):
        try:
            # Tentar usar cache primeiro
            cached_stats = app_cache.get('dashboard_stats')
            
            if cached_stats is None:
                clients = storage.get_clients()
                
                # Calculate statistics
                total_value = sum(client.value for client in clients)
                iptv_clients = [c for c in clients if c.plan_type == 'IPTV']
                vpn_clients = [c for c in clients if c.plan_type == 'VPN']
                
                iptv_value = sum(client.value for client in iptv_clients)
                vpn_value = sum(client.value for client in vpn_clients)
                iptv_count = len(iptv_clients)
                vpn_count = len(vpn_clients)
                
                # Status statistics
                active_clients = [c for c in clients if c.status == 'ativo']
                expiring_clients = [c for c in clients if c.status == 'vencendo']
                expired_clients = [c for c in clients if c.status == 'expirado']
                
                # Active revenue (only from active clients)
                active_revenue = sum(client.value for client in active_clients)
                
                # Category breakdown for active clients
                active_iptv = [c for c in active_clients if c.plan_type == 'IPTV']
                active_vpn = [c for c in active_clients if c.plan_type == 'VPN']
                
                active_iptv_revenue = sum(c.value for c in active_iptv)
                active_vpn_revenue = sum(c.value for c in active_vpn)
                
                cached_stats = {
                    'total_value': total_value,
                    'iptv_value': iptv_value,
                    'vpn_value': vpn_value,
                    'iptv_count': iptv_count,
                    'vpn_count': vpn_count,
                    'total_clients': len(clients),
                    'active_clients': len(active_clients),
                    'expiring_clients': len(expiring_clients),
                    'expired_clients': len(expired_clients),
                    'active_revenue': active_revenue,
                    'active_iptv_count': len(active_iptv),
                    'active_vpn_count': len(active_vpn),
                    'active_iptv_revenue': active_iptv_revenue,
                    'active_vpn_revenue': active_vpn_revenue
                }
                
                # Cachear estatísticas por 2 minutos
                app_cache.set('dashboard_stats', cached_stats, ttl=120)
                
                app_logger.log_action("dashboard_stats_calculated", 
                                    total_clients=len(clients),
                                    user_ip=client_ip)
            
            # Get upcoming reminders (não cachear pois muda frequentemente)
            upcoming_reminders = get_upcoming_reminders()
            
            return render_template('dashboard.html', 
                                 upcoming_reminders=upcoming_reminders,
                                 **cached_stats)
                                 
        except Exception as e:
            app_logger.log_error(e, context="dashboard_load", user_ip=client_ip)
            flash('Erro ao carregar dashboard', 'error')
            return render_template('dashboard.html', 
                                 total_value=0, iptv_value=0, vpn_value=0,
                                 iptv_count=0, vpn_count=0, total_clients=0,
                                 active_clients=0, expiring_clients=0, expired_clients=0,
                                 active_revenue=0, active_iptv_count=0, active_vpn_count=0,
                                 active_iptv_revenue=0, active_vpn_revenue=0,
                                 upcoming_reminders=[])

@app.route('/clients')
def clients():
    """List all clients"""
    try:
        clients_list = storage.get_clients()
        return render_template('clients.html', clients=clients_list)
    except Exception as e:
        logger.error(f"Error loading clients: {str(e)}")
        flash('Erro ao carregar clientes', 'error')
        return render_template('clients.html', clients=[])

# Temporarily comment out to isolate wrapper conflict
# @app.route('/clients/add', methods=['GET', 'POST'])
# @rate_limit_form(limit=10)  # Máximo 10 adições por minuto
# @auto_backup_before_changes(data_type='clients')
# def add_client():
    """Add new client"""
    client_ip = get_client_ip()
    
    if request.method == 'POST':
        with log_with_context(user_ip=client_ip, action="client_add_attempt"):
            try:
                # Validar dados antes de criar cliente
                validated_data = ClientValidator.validate_client_data(request.form)
                
                client = Client(
                    id=str(uuid.uuid4()),
                    **validated_data
                )
                
                # Save to GitHub
                if storage.add_client(client):
                    # Limpar cache relacionado
                    invalidate_cache_pattern("dashboard_stats")
                    invalidate_cache_pattern("client_list")
                    
                    # Update scheduler
                    setup_reminders(scheduler)
                    
                    # Log da ação bem-sucedida
                    client_logger.log_client_action(
                        "client_added", 
                        client.id, 
                        client.name,
                        user_ip=client_ip,
                        phone=client.phone,
                        plan_type=client.plan_type,
                        value=client.value
                    )
                    
                    flash('Cliente adicionado com sucesso!', 'success')
                    return redirect(url_for('clients'))
                else:
                    log_user_action("CLIENT_ADD_FAILED", 
                                  f"GitHub error for {validated_data.get('name', 'unknown')}", 
                                  client_ip)
                    flash('Erro ao salvar cliente no GitHub', 'error')
                    
            except ValueError as e:
                # Erros de validação
                log_user_action("CLIENT_ADD_VALIDATION_ERROR", str(e), client_ip)
                flash(f'Erro de validação: {str(e)}', 'error')
                
            except Exception as e:
                # Outros erros
                app_logger.log_error(e, context="client_add", user_ip=client_ip)
                flash(f'Erro ao adicionar cliente: {str(e)}', 'error')
    
    return render_template('add_client.html')

@app.route('/clients/edit/<client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    """Edit existing client"""
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            flash('Cliente não encontrado', 'error')
            return redirect(url_for('clients'))
        
        if request.method == 'POST':
            # Update client data
            client.name = request.form['name']
            client.phone = request.form['phone']
            client.plan_type = request.form['plan_type']
            client.value = float(request.form['value'])
            client.plan_duration = request.form['plan_duration']
            client.reminder_time_3days = request.form.get('reminder_time_3days', '09:00')
            client.reminder_time_payment = request.form.get('reminder_time_payment', '10:00')
            client.custom_message_3days = request.form.get('custom_message_3days', '')
            client.custom_message_payment = request.form.get('custom_message_payment', '')
            
            # Save to GitHub
            if storage.update_client(client):
                # Update scheduler
                setup_reminders(scheduler)
                flash('Cliente atualizado com sucesso!', 'success')
                return redirect(url_for('clients'))
            else:
                flash('Erro ao atualizar cliente no GitHub', 'error')
        
        return render_template('edit_client.html', client=client)
        
    except Exception as e:
        logger.error(f"Error editing client: {str(e)}")
        flash(f'Erro ao editar cliente: {str(e)}', 'error')
        return redirect(url_for('clients'))

# Temporarily comment out to isolate wrapper conflict
# @app.route('/clients/delete/<client_id>', methods=['POST'])
# @rate_limit_sensitive(limit=5)  # Máximo 5 exclusões por minuto (ação sensível)
# @auto_backup_before_changes(data_type='clients')
# def delete_client(client_id):
    """Delete client"""
    client_ip = get_client_ip()
    
    with log_with_context(user_ip=client_ip, action="client_delete", client_id=client_id):
        try:
            # Buscar cliente antes de excluir para log
            client = storage.get_client_by_id(client_id)
            client_name = client.name if client else "Unknown"
            
            if storage.delete_client(client_id):
                # Limpar cache relacionado
                invalidate_cache_pattern("dashboard_stats")
                invalidate_cache_pattern("client_list")
                
                # Update scheduler
                setup_reminders(scheduler)
                
                # Log da exclusão
                client_logger.log_client_action(
                    "client_deleted",
                    client_id,
                    client_name,
                    user_ip=client_ip
                )
                
                flash('Cliente excluído com sucesso!', 'success')
            else:
                log_user_action("CLIENT_DELETE_FAILED", 
                              f"Failed to delete client {client_id}", client_ip)
                flash('Erro ao excluir cliente', 'error')
                
        except Exception as e:
            app_logger.log_error(e, context="client_delete", 
                               user_ip=client_ip, client_id=client_id)
            flash(f'Erro ao excluir cliente: {str(e)}', 'error')
    
    return redirect(url_for('clients'))

# Temporarily comment out to isolate wrapper conflict
# @app.route('/clients/renew/<client_id>', methods=['POST'])
# @rate_limit_form(limit=20)  # Máximo 20 renovações por minuto
# @auto_backup_before_changes(data_type='clients')
# def renew_client(client_id):
    """Renew client plan"""
    client_ip = get_client_ip()
    
    with log_with_context(user_ip=client_ip, action="client_renewal", client_id=client_id):
        try:
            client = storage.get_client_by_id(client_id)
            if not client:
                log_user_action("CLIENT_RENEWAL_FAILED", f"Client {client_id} not found", client_ip)
                flash('Cliente não encontrado', 'error')
                return redirect(url_for('clients'))
            
            # Validar dados de renovação
            validated_data = ClientValidator.validate_renewal_data(request.form)
            renewal_days = validated_data['renewal_days']
            mark_as_paid = validated_data['mark_as_paid']
            
            # Renew the plan
            if client.renew_plan(renewal_days):
                if mark_as_paid:
                    client.mark_as_paid()
                else:
                    client.mark_as_pending()
                
                # Save to GitHub
                if storage.update_client(client):
                    # Limpar cache relacionado
                    invalidate_cache_pattern("dashboard_stats")
                    invalidate_cache_pattern("client_list")
                    
                    # Update scheduler
                    setup_reminders(scheduler)
                    
                    # Log da renovação
                    client_logger.log_client_action(
                        "client_renewed",
                        client.id,
                        client.name,
                        user_ip=client_ip,
                        renewal_days=renewal_days,
                        marked_as_paid=mark_as_paid,
                        new_expiration=client.plan_duration
                    )
                    
                    payment_status = "e marcado como pago" if mark_as_paid else ""
                    flash(f'Plano renovado por {renewal_days} dias {payment_status}!', 'success')
                else:
                    log_user_action("CLIENT_RENEWAL_GITHUB_ERROR", 
                                  f"Failed to save renewal for {client.name}", client_ip)
                    flash('Erro ao salvar renovação no GitHub', 'error')
            else:
                log_user_action("CLIENT_RENEWAL_PLAN_ERROR", 
                              f"Plan renewal failed for {client.name}", client_ip)
                flash('Erro ao renovar plano', 'error')
                
        except ValueError as e:
            log_user_action("CLIENT_RENEWAL_VALIDATION_ERROR", str(e), client_ip, client_id)
            flash(f'Erro de validação: {str(e)}', 'error')
            
        except Exception as e:
            app_logger.log_error(e, context="client_renewal", 
                               user_ip=client_ip, client_id=client_id)
            flash(f'Erro ao renovar cliente: {str(e)}', 'error')
    
    return redirect(url_for('clients'))

@app.route('/clients/payment-status/<client_id>', methods=['POST'])
def update_payment_status(client_id):
    """Update client payment status"""
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            flash('Cliente não encontrado', 'error')
            return redirect(url_for('clients'))
        
        status = request.form.get('status')
        if status == 'paid':
            client.mark_as_paid()
            flash('Cliente marcado como pago!', 'success')
        elif status == 'pending':
            client.mark_as_pending()
            flash('Status alterado para pendente', 'info')
        else:
            flash('Status inválido', 'error')
            return redirect(url_for('clients'))
        
        # Save to GitHub
        if storage.update_client(client):
            # Update scheduler
            setup_reminders(scheduler)
        else:
            flash('Erro ao atualizar status no GitHub', 'error')
            
    except Exception as e:
        logger.error(f"Error updating payment status: {str(e)}")
        flash(f'Erro ao atualizar status: {str(e)}', 'error')
    
    return redirect(url_for('clients'))

@app.route('/messages')
def messages():
    """Manage message templates"""
    try:
        templates = storage.get_message_templates()
        return render_template('messages.html', templates=templates)
    except Exception as e:
        logger.error(f"Error loading message templates: {str(e)}")
        flash('Erro ao carregar mensagens', 'error')
        return render_template('messages.html', templates=[])

@app.route('/messages/add', methods=['POST'])
def add_message_template():
    """Add new message template"""
    try:
        template = MessageTemplate(
            id=str(uuid.uuid4()),
            name=request.form['name'],
            content=request.form['content'],
            type=request.form['type']
        )
        
        templates = storage.get_message_templates()
        templates.append(template)
        
        if storage.save_message_templates(templates):
            flash('Template de mensagem adicionado com sucesso!', 'success')
        else:
            flash('Erro ao salvar template no GitHub', 'error')
            
    except Exception as e:
        logger.error(f"Error adding message template: {str(e)}")
        flash(f'Erro ao adicionar template: {str(e)}', 'error')
    
    return redirect(url_for('messages'))

@app.route('/messages/delete/<template_id>', methods=['POST'])
def delete_message_template(template_id):
    """Delete message template"""
    try:
        templates = storage.get_message_templates()
        templates = [t for t in templates if t.id != template_id]
        
        if storage.save_message_templates(templates):
            flash('Template excluído com sucesso!', 'success')
        else:
            flash('Erro ao excluir template', 'error')
            
    except Exception as e:
        logger.error(f"Error deleting message template: {str(e)}")
        flash(f'Erro ao excluir template: {str(e)}', 'error')
    
    return redirect(url_for('messages'))

@app.route('/whatsapp')
def whatsapp():
    """WhatsApp connection management"""
    qr_code = get_whatsapp_qr_code()
    connected = is_whatsapp_connected()
    
    return render_template('whatsapp.html', qr_code=qr_code, connected=connected)

@app.route('/whatsapp/connect', methods=['POST'])
def whatsapp_connect():
    """Mark WhatsApp as connected"""
    connect_whatsapp()
    flash('WhatsApp conectado com sucesso!', 'success')
    return redirect(url_for('whatsapp'))

@app.route('/whatsapp/disconnect', methods=['POST'])
def whatsapp_disconnect():
    """Disconnect WhatsApp"""
    disconnect_whatsapp()
    flash('WhatsApp desconectado', 'info')
    return redirect(url_for('whatsapp'))

@app.route('/api/dashboard-data')
def api_dashboard_data():
    """API endpoint for dashboard data"""
    try:
        clients = storage.get_clients()
        
        data = {
            'total_value': sum(client.value for client in clients),
            'iptv_value': sum(client.value for client in clients if client.plan_type == 'IPTV'),
            'vpn_value': sum(client.value for client in clients if client.plan_type == 'VPN'),
            'iptv_count': len([c for c in clients if c.plan_type == 'IPTV']),
            'vpn_count': len([c for c in clients if c.plan_type == 'VPN']),
            'total_clients': len(clients)
        }
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/system/status')
def system_status():
    """System status and monitoring page"""
    try:
        from whatsapp_integration import get_whatsapp_status
        from message_queue import get_queue_status, get_recent_messages
        from reminder_scheduler import get_reminder_statistics
        
        # Get WhatsApp status
        whatsapp_status = get_whatsapp_status()
        
        # Get message queue status
        queue_status = get_queue_status()
        
        # Get recent messages
        recent_messages = get_recent_messages(20)
        
        # Get reminder statistics
        reminder_stats = get_reminder_statistics()
        
        # Get storage statistics
        storage_stats = storage.get_storage_stats()
        
        # Get system health
        system_health = {
            'whatsapp_connected': whatsapp_status.get('connected', False),
            'queue_processing': queue_status.get('processing', False),
            'storage_connected': storage_stats.get('connection_status') == 'connected',
            'total_clients': storage_stats.get('clients_count', 0),
            'pending_messages': queue_status.get('queue_size', 0),
            'failed_messages': queue_status.get('failed_count', 0)
        }
        
        return render_template('system_status.html',
                             whatsapp_status=whatsapp_status,
                             queue_status=queue_status,
                             recent_messages=recent_messages,
                             reminder_stats=reminder_stats,
                             storage_stats=storage_stats,
                             system_health=system_health)
                             
    except Exception as e:
        logger.error(f"Error loading system status: {str(e)}")
        flash('Erro ao carregar status do sistema', 'error')
        return render_template('system_status.html',
                             whatsapp_status={},
                             queue_status={},
                             recent_messages=[],
                             reminder_stats={},
                             storage_stats={},
                             system_health={})

@app.route('/health')
def health():
    """Simple health check endpoint"""
    try:
        from health_check import get_health_status
        status = get_health_status(detailed=False)
        
        # Retornar status HTTP apropriado
        if status.get('status') in ['healthy', 'warning']:
            return jsonify(status), 200
        else:
            return jsonify(status), 503
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

# Temporarily comment out to isolate wrapper conflict
# @app.route('/health/detailed')
# @rate_limit_api(limit=10)
# def health_detailed():
    """Detailed health check endpoint"""
    try:
        from health_check import get_health_status
        status = get_health_status(detailed=True)
        
        # Retornar status HTTP apropriado
        if status.get('overall_status') in ['healthy', 'warning']:
            return jsonify(status), 200
        else:
            return jsonify(status), 503
            
    except Exception as e:
        return jsonify({
            'overall_status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

# Temporarily comment out to isolate wrapper conflict
# @app.route('/api/system/health')
# @rate_limit_api(limit=20)
# def api_system_health():
    """API endpoint for system health check - LEGACY"""
    try:
        # Manter compatibilidade com versão anterior
        from health_check import get_health_status
        
        health_status = get_health_status(detailed=True)
        
        # Converter para formato legacy
        health = {
            'status': health_status.get('overall_status', 'error'),
            'timestamp': health_status.get('timestamp'),
            'components': {}
        }
        
        checks = health_status.get('checks', {})
        
        # Mapear checks para componentes legacy
        if 'whatsapp_connection' in checks:
            whatsapp = checks['whatsapp_connection']
            health['components']['whatsapp'] = {
                'status': 'up' if whatsapp.get('status') in ['healthy', 'warning'] else 'down',
                'connected': whatsapp.get('connected', False)
            }
        
        if 'message_queue' in checks:
            queue = checks['message_queue']
            health['components']['message_queue'] = {
                'status': 'up' if queue.get('status') in ['healthy', 'warning'] else 'down',
                'queue_size': queue.get('queue_size', 0),
                'processing': queue.get('processing', False)
            }
        
        if 'github_storage' in checks:
            storage_check = checks['github_storage']
            health['components']['storage'] = {
                'status': 'up' if storage_check.get('status') in ['healthy', 'warning'] else 'down',
                'connection': storage_check.get('connection_status', 'unknown')
            }
        
        health['components']['scheduler'] = {
            'status': 'up',
            'running_jobs': len(scheduler.get_jobs())
        }
        
        return jsonify(health)
        
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/queue/messages')
def api_queue_messages():
    """API endpoint for queue messages"""
    try:
        from message_queue import get_recent_messages
        
        limit = request.args.get('limit', 50, type=int)
        messages = get_recent_messages(limit)
        
        return jsonify({
            'messages': messages,
            'count': len(messages),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting queue messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/stats')
def api_queue_stats():
    """API endpoint for queue statistics"""
    try:
        from message_queue import get_queue_status
        
        stats = get_queue_status()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting queue stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reminders/force-send', methods=['POST'])
def api_force_send_reminder():
    """API endpoint to force send a reminder"""
    try:
        from reminder_scheduler import force_send_reminder
        
        client_id = request.json.get('client_id')
        reminder_type = request.json.get('reminder_type', 'payment')
        
        if not client_id:
            return jsonify({'error': 'client_id is required'}), 400
        
        success = force_send_reminder(client_id, reminder_type)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Reminder queued for sending'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to queue reminder'
            }), 500
            
    except Exception as e:
        logger.error(f"Error force sending reminder: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Temporarily comment out to isolate wrapper conflict
# @app.route('/api/cache/stats')
# @rate_limit_api(limit=30)
# def api_cache_stats():
    """API endpoint for cache statistics"""
    try:
        from simple_cache import cache_manager, get_cache_health
        
        health = get_cache_health()
        return jsonify(health)
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache/clear', methods=['POST'])
@rate_limit_sensitive(limit=3)
def api_clear_cache():
    """API endpoint to clear cache"""
    try:
        from simple_cache import cache_manager
        client_ip = get_client_ip()
        
        cache_manager.clear_all()
        
        log_user_action("CACHE_CLEARED", "All caches cleared", client_ip)
        
        return jsonify({
            'success': True,
            'message': 'All caches cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup/create', methods=['POST'])
@rate_limit_sensitive(limit=2)
def api_create_backup():
    """API endpoint to create manual backup"""
    try:
        from backup_utils import backup_manager
        client_ip = get_client_ip()
        
        backup_type = request.json.get('type', 'system')
        
        if backup_type == 'system':
            result = backup_manager.create_system_backup()
        elif backup_type == 'clients':
            clients = storage.get_clients()
            result = backup_manager.create_client_backup(clients)
        elif backup_type == 'templates':
            templates = storage.get_message_templates()
            result = backup_manager.create_template_backup(templates)
        else:
            return jsonify({'error': 'Invalid backup type'}), 400
        
        if result:
            log_user_action("BACKUP_CREATED", f"Manual {backup_type} backup created", client_ip)
            return jsonify({
                'success': True,
                'message': f'{backup_type.title()} backup created successfully',
                'backup_file': result
            })
        else:
            return jsonify({'error': 'Failed to create backup'}), 500
            
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup/list')
@rate_limit_api(limit=20)
def api_list_backups():
    """API endpoint to list available backups"""
    try:
        from backup_utils import backup_manager
        
        backup_type = request.args.get('type')
        backups = backup_manager.list_backups(backup_type)
        
        return jsonify({
            'backups': backups,
            'count': len(backups)
        })
        
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/rate-limit/stats')
@rate_limit_api(limit=30)
def api_rate_limit_stats():
    """API endpoint for rate limiting statistics"""
    try:
        from rate_limiter import get_rate_limit_stats
        
        stats = get_rate_limit_stats()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting rate limit stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validation/test', methods=['POST'])
@rate_limit_api(limit=10)
def api_test_validation():
    """API endpoint to test validation without saving"""
    try:
        data_type = request.json.get('type', 'client')
        data = request.json.get('data', {})
        
        if data_type == 'client':
            validated = ClientValidator.validate_client_data(data)
            return jsonify({
                'valid': True,
                'validated_data': validated,
                'message': 'Dados válidos'
            })
        elif data_type == 'template':
            validated = MessageTemplateValidator.validate_template_data(data)
            return jsonify({
                'valid': True,
                'validated_data': validated,
                'message': 'Template válido'
            })
        else:
            return jsonify({'error': 'Invalid data type'}), 400
            
    except ValueError as e:
        return jsonify({
            'valid': False,
            'error': str(e),
            'message': 'Dados inválidos'
        }), 400
    except Exception as e:
        logger.error(f"Error testing validation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/whatsapp/reconnect', methods=['POST'])
@rate_limit_api(limit=5)
def api_whatsapp_reconnect():
    """API endpoint to force WhatsApp reconnection"""
    try:
        from whatsapp_integration import force_whatsapp_reconnect
        
        force_whatsapp_reconnect()
        
        return jsonify({
            'success': True,
            'message': 'Reconnection attempted'
        })
        
    except Exception as e:
        logger.error(f"Error forcing WhatsApp reconnect: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/storage/clear-cache', methods=['POST'])
def api_clear_storage_cache():
    """API endpoint to clear storage cache"""
    try:
        storage.clear_cache()
        
        return jsonify({
            'success': True,
            'message': 'Storage cache cleared'
        })
        
    except Exception as e:
        logger.error(f"Error clearing storage cache: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue/clear-failed', methods=['POST'])
def api_clear_failed_messages():
    """API endpoint to clear failed messages"""
    try:
        from message_queue import message_queue
        
        message_queue.clear_failed_messages()
        
        return jsonify({
            'success': True,
            'message': 'Failed messages cleared'
        })
        
    except Exception as e:
        logger.error(f"Error clearing failed messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/clients/bulk-action', methods=['POST'])
def bulk_client_action():
    """Perform bulk actions on selected clients"""
    try:
        action = request.form.get('action')
        client_ids = request.form.getlist('client_ids')
        
        if not action or not client_ids:
            flash('Ação ou clientes não selecionados', 'error')
            return redirect(url_for('clients'))
        
        success_count = 0
        error_count = 0
        
        if action == 'mark_paid':
            for client_id in client_ids:
                try:
                    client = storage.get_client_by_id(client_id)
                    if client:
                        client.mark_as_paid()
                        if storage.update_client(client):
                            success_count += 1
                        else:
                            error_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error marking client {client_id} as paid: {str(e)}")
                    error_count += 1
            
            flash(f'{success_count} clientes marcados como pagos. {error_count} erros.', 
                  'success' if error_count == 0 else 'warning')
        
        elif action == 'mark_pending':
            for client_id in client_ids:
                try:
                    client = storage.get_client_by_id(client_id)
                    if client:
                        client.mark_as_pending()
                        if storage.update_client(client):
                            success_count += 1
                        else:
                            error_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error marking client {client_id} as pending: {str(e)}")
                    error_count += 1
            
            flash(f'{success_count} clientes marcados como pendentes. {error_count} erros.', 
                  'success' if error_count == 0 else 'warning')
        
        elif action == 'delete':
            for client_id in client_ids:
                try:
                    if storage.delete_client(client_id):
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error deleting client {client_id}: {str(e)}")
                    error_count += 1
            
            flash(f'{success_count} clientes excluídos. {error_count} erros.', 
                  'success' if error_count == 0 else 'warning')
        
        elif action == 'force_reminder':
            reminder_type = request.form.get('reminder_type', 'payment')
            from reminder_scheduler import force_send_reminder
            
            for client_id in client_ids:
                try:
                    if force_send_reminder(client_id, reminder_type):
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error sending reminder to client {client_id}: {str(e)}")
                    error_count += 1
            
            flash(f'{success_count} lembretes enviados. {error_count} erros.', 
                  'success' if error_count == 0 else 'warning')
        
        else:
            flash('Ação não reconhecida', 'error')
        
        # Update scheduler after bulk operations
        setup_reminders(scheduler)
        
        return redirect(url_for('clients'))
        
    except Exception as e:
        logger.error(f"Error in bulk client action: {str(e)}")
        flash(f'Erro na ação em lote: {str(e)}', 'error')
        return redirect(url_for('clients'))

@app.route('/clients/export')
def export_clients():
    """Export clients data as CSV"""
    try:
        from io import StringIO
        import csv
        
        clients = storage.get_clients()
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Nome', 'Telefone', 'Plano', 'Valor', 'Vencimento',
            'Status', 'Status Pagamento', 'Dias Restantes', 'Criado Em'
        ])
        
        # Write client data
        for client in clients:
            writer.writerow([
                client.id,
                client.name,
                client.phone,
                client.plan_type,
                f"R$ {client.value:.2f}",
                client.plan_duration,
                client.status,
                getattr(client, 'payment_status', 'pending'),
                client.days_until_expiration,
                client.created_at
            ])
        
        # Create response
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=clientes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
    except Exception as e:
        logger.error(f"Error exporting clients: {str(e)}")
        flash(f'Erro ao exportar clientes: {str(e)}', 'error')
        return redirect(url_for('clients'))
