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
from backup_utils import create_backup, backup_manager
import logging

logger = logging.getLogger(__name__)

@app.route('/')
def dashboard():
    """Dashboard with statistics and upcoming reminders"""
    client_ip = get_client_ip()
    
    try:
        # Cache dashboard stats manually to avoid decorator conflicts
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
            
            # Cache statistics for 2 minutes
            app_cache.set('dashboard_stats', cached_stats, ttl=120)
            
            app_logger.log_action("dashboard_stats_calculated", 
                                total_clients=len(clients),
                                user_ip=client_ip)
        
        # Get upcoming reminders
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

@app.route('/clients/add', methods=['GET', 'POST'])
def add_client():
    """Add new client"""
    client_ip = get_client_ip()
    
    # Simple rate limiting check
    if not rate_limit_form(limit=10).is_allowed(client_ip):
        flash('Muitas tentativas. Aguarde alguns minutos.', 'error')
        return redirect(url_for('clients'))
    
    if request.method == 'POST':
        try:
            # Create backup before changes
            clients = storage.get_clients()
            backup_manager.create_client_backup(clients)
            
            # Validate data
            validated_data = ClientValidator.validate_client_data(request.form)
            
            client = Client(
                id=str(uuid.uuid4()),
                **validated_data
            )
            
            # Save to GitHub
            if storage.add_client(client):
                # Clear cache
                invalidate_cache_pattern("dashboard_stats")
                invalidate_cache_pattern("client_list")
                
                # Update scheduler
                setup_reminders(scheduler)
                
                # Log successful action
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
                flash('Erro ao salvar cliente no GitHub', 'error')
                
        except ValueError as e:
            flash(f'Erro de validação: {str(e)}', 'error')
            
        except Exception as e:
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

@app.route('/clients/delete/<client_id>', methods=['POST'])
def delete_client(client_id):
    """Delete client"""
    client_ip = get_client_ip()
    
    # Rate limiting for sensitive action
    if not rate_limit_sensitive(limit=5).is_allowed(client_ip):
        flash('Muitas tentativas de exclusão. Aguarde.', 'error')
        return redirect(url_for('clients'))
    
    try:
        # Create backup before deletion
        clients = storage.get_clients()
        backup_manager.create_client_backup(clients)
        
        # Get client before deleting for log
        client = storage.get_client_by_id(client_id)
        client_name = client.name if client else "Unknown"
        
        if storage.delete_client(client_id):
            # Clear cache
            invalidate_cache_pattern("dashboard_stats")
            invalidate_cache_pattern("client_list")
            
            # Update scheduler
            setup_reminders(scheduler)
            
            # Log deletion
            client_logger.log_client_action(
                "client_deleted",
                client_id,
                client_name,
                user_ip=client_ip
            )
            
            flash('Cliente excluído com sucesso!', 'success')
        else:
            flash('Erro ao excluir cliente', 'error')
            
    except Exception as e:
        app_logger.log_error(e, context="client_delete", 
                           user_ip=client_ip, client_id=client_id)
        flash(f'Erro ao excluir cliente: {str(e)}', 'error')

    return redirect(url_for('clients'))

@app.route('/clients/renew/<client_id>', methods=['POST'])
def renew_client(client_id):
    """Renew client plan"""
    client_ip = get_client_ip()
    
    # Rate limiting for form action
    if not rate_limit_form(limit=20).is_allowed(client_ip):
        flash('Muitas tentativas de renovação. Aguarde.', 'error')
        return redirect(url_for('clients'))
    
    try:
        # Create backup before changes
        clients = storage.get_clients()
        backup_manager.create_client_backup(clients)
        
        client = storage.get_client_by_id(client_id)
        if not client:
            flash('Cliente não encontrado', 'error')
            return redirect(url_for('clients'))
        
        # Validate renewal data
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
                # Clear cache
                invalidate_cache_pattern("dashboard_stats")
                invalidate_cache_pattern("client_list")
                
                # Update scheduler
                setup_reminders(scheduler)
                
                # Log renewal
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
                flash('Erro ao salvar renovação no GitHub', 'error')
        else:
            flash('Erro ao renovar plano', 'error')
            
    except ValueError as e:
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
        
        # Return appropriate HTTP status
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

# API Routes with manual rate limiting to avoid decorator conflicts
@app.route('/api/cache/stats')
def api_cache_stats():
    """API endpoint for cache statistics"""
    client_ip = get_client_ip()
    
    # Manual rate limiting
    if not rate_limit_api(limit=30).is_allowed(client_ip):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        from simple_cache import cache_manager, get_cache_health
        
        health = get_cache_health()
        return jsonify(health)
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup/create', methods=['POST'])
def api_create_backup():
    """API endpoint to create backup"""
    client_ip = get_client_ip()
    
    # Manual rate limiting for sensitive action
    if not rate_limit_sensitive(limit=2).is_allowed(client_ip):
        return jsonify({'error': 'Rate limit exceeded for backup creation'}), 429
    
    try:
        backup_path = backup_manager.create_system_backup()
        
        if backup_path:
            log_user_action("BACKUP_CREATED", f"System backup created: {backup_path}", client_ip)
            return jsonify({
                'success': True,
                'message': 'Backup criado com sucesso',
                'backup_path': backup_path,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Falha ao criar backup'
            }), 500
            
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/backup/list')
def api_list_backups():
    """API endpoint to list backups"""
    client_ip = get_client_ip()
    
    # Manual rate limiting
    if not rate_limit_api(limit=20).is_allowed(client_ip):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        backup_type = request.args.get('type')
        backups = backup_manager.list_backups(backup_type)
        
        return jsonify({
            'backups': backups,
            'count': len(backups),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/clients/export')
def export_clients():
    """Export clients to JSON"""
    try:
        clients = storage.get_clients()
        
        # Convert to dict for JSON export
        clients_data = [client.to_dict() for client in clients]
        
        return jsonify({
            'clients': clients_data,
            'count': len(clients_data),
            'exported_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error exporting clients: {str(e)}")
        return jsonify({'error': str(e)}), 500
