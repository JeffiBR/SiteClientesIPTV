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
from rate_limiter import rate_limiter, get_client_ip
from logger_config import log_user_action, log_with_context, app_logger, client_logger
from simple_cache import cache_dashboard_stats, cache_client_list, app_cache, invalidate_cache_pattern
from backup_utils import create_backup, backup_manager
from ai_integration import AIMessageGenerator
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
    if not rate_limiter.is_allowed(client_ip, limit=10):
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
            
            # Handle new observation if provided
            new_observation = request.form.get('new_observation', '').strip()
            if new_observation:
                client.add_observation(new_observation)
            
            # Save to GitHub
            if storage.update_client(client):
                # Update scheduler
                setup_reminders(scheduler)
                success_msg = 'Cliente atualizado com sucesso!'
                if new_observation:
                    success_msg += ' Nova observação adicionada.'
                flash(success_msg, 'success')
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
    if not rate_limiter.is_allowed(client_ip, limit=5):
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
    if not rate_limiter.is_allowed(client_ip, limit=20):
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

@app.route('/clients/observations/<client_id>', methods=['POST'])
def update_client_observations(client_id):
    """Update client observations"""
    client_ip = get_client_ip()
    
    # Rate limiting for form action
    if not rate_limiter.is_allowed(client_ip, limit=10):
        flash('Muitas tentativas. Aguarde.', 'error')
        return redirect(url_for('clients'))
    
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            flash('Cliente não encontrado', 'error')
            return redirect(url_for('clients'))
        
        new_observation = request.form.get('new_observation', '').strip()
        if not new_observation:
            flash('Observação não pode estar vazia', 'error')
            return redirect(url_for('clients'))
        
        # Add the new observation with timestamp
        client.add_observation(new_observation)
        
        # Save to GitHub
        if storage.update_client(client):
            # Log observation update
            client_logger.log_client_action(
                "observation_added",
                client.id,
                client.name,
                user_ip=client_ip,
                observation_preview=new_observation[:50] + "..." if len(new_observation) > 50 else new_observation
            )
            
            flash('Observação adicionada com sucesso!', 'success')
        else:
            flash('Erro ao salvar observação no GitHub', 'error')
            
    except Exception as e:
        app_logger.log_error(e, context="client_observations", 
                           user_ip=client_ip, client_id=client_id)
        flash(f'Erro ao adicionar observação: {str(e)}', 'error')

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
            type=request.form['type'],
            plan_type=request.form.get('plan_type', 'all')
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
    if not rate_limiter.is_allowed(client_ip, limit=30):
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
    if not rate_limiter.is_allowed(client_ip, limit=2):
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
    if not rate_limiter.is_allowed(client_ip, limit=20):
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

# VPN Dashboard Routes
@app.route('/vpn/dashboard')
def vpn_dashboard():
    """VPN specific dashboard with enhanced KPIs"""
    client_ip = get_client_ip()
    
    try:
        # Get VPN specific statistics
        clients = storage.get_clients()
        vpn_clients = [c for c in clients if c.plan_type == 'VPN']
        
        # Calculate VPN-specific KPIs
        total_vpn_value = sum(client.value for client in vpn_clients)
        active_vpn_clients = [c for c in vpn_clients if c.status == 'ativo']
        expiring_vpn_clients = [c for c in vpn_clients if c.status == 'vencendo']
        expired_vpn_clients = [c for c in vpn_clients if c.status == 'expirado']
        
        vpn_stats = {
            'total_value': total_vpn_value,
            'vpn_value': total_vpn_value,
            'vpn_count': len(vpn_clients),
            'total_clients': len(vpn_clients),
            'active_clients': len(active_vpn_clients),
            'expiring_clients': len(expiring_vpn_clients),
            'expired_clients': len(expired_vpn_clients),
            'active_revenue': sum(c.value for c in active_vpn_clients),
            'conversion_rate': (len(active_vpn_clients) / len(vpn_clients) * 100) if vpn_clients else 0
        }
        
        # Get upcoming reminders for VPN clients
        upcoming_reminders = get_upcoming_reminders()
        vpn_reminders = [r for r in upcoming_reminders if any(c.id == r.client_id and c.plan_type == 'VPN' for c in clients)]
        
        return render_template('vpn_messages.html', 
                             upcoming_reminders=vpn_reminders,
                             **vpn_stats)
                             
    except Exception as e:
        app_logger.log_error(e, context="vpn_dashboard_load", user_ip=client_ip)
        flash('Erro ao carregar dashboard VPN', 'error')
        return render_template('vpn_messages.html', 
                             total_value=0, vpn_value=0, vpn_count=0,
                             total_clients=0, active_clients=0, 
                             expiring_clients=0, expired_clients=0,
                             upcoming_reminders=[])

@app.route('/api/vpn/stats')
def api_vpn_stats():
    """API endpoint for VPN-specific statistics"""
    client_ip = get_client_ip()
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip, limit=30):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        clients = storage.get_clients()
        vpn_clients = [c for c in clients if c.plan_type == 'VPN']
        
        # Calculate comprehensive VPN statistics
        total_vpn_value = sum(client.value for client in vpn_clients)
        active_vpn = [c for c in vpn_clients if c.status == 'ativo']
        expiring_vpn = [c for c in vpn_clients if c.status == 'vencendo']
        expired_vpn = [c for c in vpn_clients if c.status == 'expirado']
        
        # Monthly growth calculation (mock data for now)
        current_month_revenue = total_vpn_value
        last_month_revenue = total_vpn_value * 0.88  # Simulate 12% growth
        growth_percentage = ((current_month_revenue - last_month_revenue) / last_month_revenue * 100) if last_month_revenue > 0 else 0
        
        # Renewal rate calculation
        total_eligible_for_renewal = len([c for c in vpn_clients if c.status in ['ativo', 'vencendo']])
        renewed_clients = len(active_vpn)
        renewal_rate = (renewed_clients / total_eligible_for_renewal * 100) if total_eligible_for_renewal > 0 else 0
        
        stats = {
            'total_vpn_revenue': total_vpn_value,
            'active_vpn_clients': len(active_vpn),
            'expiring_vpn_clients': len(expiring_vpn),
            'expired_vpn_clients': len(expired_vpn),
            'total_vpn_clients': len(vpn_clients),
            'active_vpn_revenue': sum(c.value for c in active_vpn),
            'growth_percentage': growth_percentage,
            'renewal_rate': renewal_rate,
            'conversion_rate': (len(active_vpn) / len(vpn_clients) * 100) if vpn_clients else 0,
            'average_vpn_value': total_vpn_value / len(vpn_clients) if vpn_clients else 0,
            'monthly_trend': [
                {'month': 'Jan', 'revenue': total_vpn_value * 0.7, 'clients': len(vpn_clients) - 15},
                {'month': 'Fev', 'revenue': total_vpn_value * 0.75, 'clients': len(vpn_clients) - 12},
                {'month': 'Mar', 'revenue': total_vpn_value * 0.82, 'clients': len(vpn_clients) - 8},
                {'month': 'Abr', 'revenue': total_vpn_value * 0.88, 'clients': len(vpn_clients) - 5},
                {'month': 'Mai', 'revenue': total_vpn_value * 0.94, 'clients': len(vpn_clients) - 2},
                {'month': 'Jun', 'revenue': total_vpn_value, 'clients': len(vpn_clients)}
            ]
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting VPN stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vpn/clients')
def api_vpn_clients():
    """API endpoint for VPN clients data"""
    client_ip = get_client_ip()
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip, limit=20):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        clients = storage.get_clients()
        vpn_clients = [c for c in clients if c.plan_type == 'VPN']
        
        # Prepare client data for API response
        client_data = []
        for client in vpn_clients:
            client_data.append({
                'id': client.id,
                'name': client.name,
                'phone': client.phone,
                'status': client.status,
                'value': client.value,
                'plan_duration': client.plan_duration,
                'created_at': client.created_at.isoformat() if hasattr(client, 'created_at') else None,
                'expiration_date': client.get_expiration_date().isoformat() if hasattr(client, 'get_expiration_date') else None
            })
        
        return jsonify({
            'clients': client_data,
            'total_count': len(vpn_clients),
            'active_count': len([c for c in vpn_clients if c.status == 'ativo']),
            'total_revenue': sum(c.value for c in vpn_clients)
        })
        
    except Exception as e:
        logger.error(f"Error getting VPN clients: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/vpn/reports')
def vpn_reports():
    """VPN reports and analytics page"""
    try:
        clients = storage.get_clients()
        vpn_clients = [c for c in clients if c.plan_type == 'VPN']
        
        # Generate report data
        report_data = {
            'total_clients': len(vpn_clients),
            'total_revenue': sum(c.value for c in vpn_clients),
            'average_value': sum(c.value for c in vpn_clients) / len(vpn_clients) if vpn_clients else 0,
            'status_breakdown': {
                'active': len([c for c in vpn_clients if c.status == 'ativo']),
                'expiring': len([c for c in vpn_clients if c.status == 'vencendo']),
                'expired': len([c for c in vpn_clients if c.status == 'expirado'])
            }
        }
        
        return render_template('vpn_reports.html', report_data=report_data)
        
    except Exception as e:
        logger.error(f"Error loading VPN reports: {str(e)}")
        flash('Erro ao carregar relatórios VPN', 'error')
        return redirect(url_for('dashboard'))

# Mobile API endpoints
@app.route('/api/mobile/dashboard')
def api_mobile_dashboard():
    """Mobile-optimized dashboard API"""
    client_ip = get_client_ip()
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip, limit=60):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        clients = storage.get_clients()
        
        # Simplified data for mobile
        mobile_data = {
            'summary': {
                'total_clients': len(clients),
                'total_revenue': sum(c.value for c in clients),
                'active_clients': len([c for c in clients if c.status == 'ativo']),
                'alerts': len([c for c in clients if c.status == 'vencendo'])
            },
            'quick_stats': {
                'vpn_clients': len([c for c in clients if c.plan_type == 'VPN']),
                'iptv_clients': len([c for c in clients if c.plan_type == 'IPTV']),
                'vpn_revenue': sum(c.value for c in clients if c.plan_type == 'VPN'),
                'iptv_revenue': sum(c.value for c in clients if c.plan_type == 'IPTV')
            },
            'recent_activity': get_recent_activity(5),
            'upcoming_tasks': get_upcoming_reminders()[:3]
        }
        
        return jsonify(mobile_data)
        
    except Exception as e:
        logger.error(f"Error getting mobile dashboard data: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_recent_activity(limit=10):
    """Get recent activity for dashboard"""
    try:
        # This would typically come from a database log
        # For now, return mock data
        activity = [
            {
                'type': 'client_added',
                'description': 'Novo cliente VPN adicionado',
                'timestamp': datetime.now().isoformat(),
                'icon': 'fas fa-user-plus'
            },
            {
                'type': 'payment_received',
                'description': 'Pagamento recebido - Cliente VPN',
                'timestamp': datetime.now().isoformat(),
                'icon': 'fas fa-dollar-sign'
            }
        ]
        
        return activity[:limit]
        
    except Exception as e:
        logger.error(f"Error getting recent activity: {str(e)}")
        return []

# Analytics and reporting functions
@app.route('/api/analytics/revenue-trend')
def api_revenue_trend():
    """API endpoint for revenue trend analytics"""
    client_ip = get_client_ip()
    
    # Rate limiting
    if not rate_limiter.is_allowed(client_ip, limit=10):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        # Get time period from query params
        period = request.args.get('period', '6months')
        service_type = request.args.get('type', 'all')
        
        clients = storage.get_clients()
        
        if service_type == 'vpn':
            clients = [c for c in clients if c.plan_type == 'VPN']
        elif service_type == 'iptv':
            clients = [c for c in clients if c.plan_type == 'IPTV']
        
        # Generate trend data (mock implementation)
        total_revenue = sum(c.value for c in clients)
        
        trend_data = {
            'labels': ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun'],
            'datasets': [{
                'label': 'Receita',
                'data': [
                    total_revenue * 0.6,
                    total_revenue * 0.7,
                    total_revenue * 0.8,
                    total_revenue * 0.85,
                    total_revenue * 0.92,
                    total_revenue
                ],
                'borderColor': '#667eea',
                'backgroundColor': 'rgba(102, 126, 234, 0.1)'
            }]
        }
        
        return jsonify(trend_data)
        
    except Exception as e:
        logger.error(f"Error getting revenue trend: {str(e)}")
        return jsonify({'error': str(e)}), 500

# WebSocket-like real-time updates (using polling for now)
@app.route('/api/realtime/updates')
def api_realtime_updates():
    """API endpoint for real-time updates"""
    client_ip = get_client_ip()
    
    # Rate limiting for frequent polling
    if not rate_limiter.is_allowed(client_ip, limit=120):
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    try:
        # Get last update timestamp
        last_update = request.args.get('last_update')
        
        updates = {
            'timestamp': datetime.now().isoformat(),
            'has_updates': False,
            'updates': [],
            'notifications': []
        }
        
        # Check for new notifications or updates
        # This is a simplified implementation
        upcoming_reminders = get_upcoming_reminders()
        if upcoming_reminders:
            updates['has_updates'] = True
            updates['notifications'] = [
                {
                    'type': 'reminder',
                    'message': f'Lembrete para {r.client_name}',
                    'time': r.scheduled_time.isoformat()
                } for r in upcoming_reminders[:3]
            ]
        
        return jsonify(updates)
        
    except Exception as e:
        logger.error(f"Error getting real-time updates: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return render_template('500.html'), 500

# Health check with enhanced monitoring
@app.route('/api/health/detailed')
def detailed_health():
    """Detailed health check for monitoring"""
    try:
        # Check all system components
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': check_storage_health(),
                'whatsapp': check_whatsapp_health(),
                'scheduler': check_scheduler_health(),
                'cache': check_cache_health()
            },
            'metrics': {
                'total_clients': len(storage.get_clients()),
                'active_connections': 1,  # Simplified
                'memory_usage': get_memory_usage(),
                'uptime': get_uptime()
            }
        }
        
        # Determine overall status
        component_statuses = [comp.get('status', 'unknown') for comp in health_status['components'].values()]
        if 'error' in component_statuses:
            health_status['status'] = 'error'
        elif 'warning' in component_statuses:
            health_status['status'] = 'warning'
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(health_status), status_code
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 503

def check_storage_health():
    """Check GitHub storage health"""
    try:
        # Try to fetch clients to test storage
        clients = storage.get_clients()
        return {
            'status': 'healthy',
            'client_count': len(clients),
            'last_check': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'last_check': datetime.now().isoformat()
        }

def check_whatsapp_health():
    """Check WhatsApp integration health"""
    try:
        connected = is_whatsapp_connected()
        return {
            'status': 'healthy' if connected else 'warning',
            'connected': connected,
            'last_check': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'last_check': datetime.now().isoformat()
        }

def check_scheduler_health():
    """Check scheduler health"""
    try:
        return {
            'status': 'healthy' if scheduler.running else 'error',
            'running': scheduler.running,
            'job_count': len(scheduler.get_jobs()),
            'last_check': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'last_check': datetime.now().isoformat()
        }

def check_cache_health():
    """Check cache health"""
    try:
        from simple_cache import get_cache_health
        return get_cache_health()
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'last_check': datetime.now().isoformat()
        }

def get_memory_usage():
    """Get current memory usage (simplified)"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss': memory_info.rss,
            'vms': memory_info.vms,
            'percent': process.memory_percent()
        }
    except ImportError:
        return {'error': 'psutil not available'}
    except Exception:
        return {'error': 'Unable to get memory info'}

def get_uptime():
    """Get application uptime (simplified)"""
    try:
        # This would typically be calculated from app start time
        return {
            'seconds': 3600,  # Mock data
            'formatted': '1h 0m 0s'
        }
    except Exception:
        return {'error': 'Unable to get uptime'}

# Template helper functions
@app.template_global()
def get_plan_color(plan_type):
    """Get color class for plan type"""
    colors = {
        'IPTV': 'info',
        'VPN': 'secondary',
        'all': 'primary'
    }
    return colors.get(plan_type, 'primary')

@app.template_global()
def get_plan_icon(plan_type):
    """Get icon for plan type"""
    icons = {
        'IPTV': 'tv',
        'VPN': 'shield-lock',
        'all': 'gear'
    }
    return icons.get(plan_type, 'gear')

@app.template_global()
def get_type_color(message_type):
    """Get color class for message type"""
    colors = {
        '3days': 'warning',
        'payment': 'danger',
        'promo': 'success'
    }
    return colors.get(message_type, 'secondary')

@app.template_global()
def get_type_label(message_type):
    """Get label for message type"""
    labels = {
        '3days': 'Lembrete 3 Dias',
        'payment': 'Dia do Pagamento',
        'promo': 'Promocional'
    }
    return labels.get(message_type, message_type)
