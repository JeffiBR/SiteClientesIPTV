from flask import render_template, request, redirect, url_for, flash, jsonify
from app import app, scheduler
import uuid
from datetime import datetime
from github_storage import storage
from models import Client, MessageTemplate
from reminder_scheduler import setup_reminders, get_upcoming_reminders
from whatsapp_integration import get_whatsapp_qr_code, is_whatsapp_connected, connect_whatsapp, disconnect_whatsapp
import logging

logger = logging.getLogger(__name__)

@app.route('/')
def dashboard():
    """Dashboard with statistics and upcoming reminders"""
    try:
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
        
        # Get upcoming reminders
        upcoming_reminders = get_upcoming_reminders()
        
        return render_template('dashboard.html', 
                             total_value=total_value,
                             iptv_value=iptv_value,
                             vpn_value=vpn_value,
                             iptv_count=iptv_count,
                             vpn_count=vpn_count,
                             total_clients=len(clients),
                             active_clients=len(active_clients),
                             expiring_clients=len(expiring_clients),
                             expired_clients=len(expired_clients),
                             active_revenue=active_revenue,
                             active_iptv_count=len(active_iptv),
                             active_vpn_count=len(active_vpn),
                             active_iptv_revenue=active_iptv_revenue,
                             active_vpn_revenue=active_vpn_revenue,
                             upcoming_reminders=upcoming_reminders)
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        flash('Erro ao carregar dashboard', 'error')
        return render_template('dashboard.html', 
                             total_value=0, iptv_value=0, vpn_value=0,
                             iptv_count=0, vpn_count=0, total_clients=0,
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
    if request.method == 'POST':
        try:
            # Validate and create client
            client = Client(
                id=str(uuid.uuid4()),
                name=request.form['name'],
                phone=request.form['phone'],
                plan_type=request.form['plan_type'],
                value=float(request.form['value']),
                plan_duration=request.form['plan_duration'],
                reminder_time_3days=request.form.get('reminder_time_3days', '09:00'),
                reminder_time_payment=request.form.get('reminder_time_payment', '10:00'),
                custom_message_3days=request.form.get('custom_message_3days', ''),
                custom_message_payment=request.form.get('custom_message_payment', '')
            )
            
            # Save to GitHub
            if storage.add_client(client):
                # Update scheduler
                setup_reminders(scheduler)
                flash('Cliente adicionado com sucesso!', 'success')
                return redirect(url_for('clients'))
            else:
                flash('Erro ao salvar cliente no GitHub', 'error')
                
        except Exception as e:
            logger.error(f"Error adding client: {str(e)}")
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
    try:
        if storage.delete_client(client_id):
            # Update scheduler
            setup_reminders(scheduler)
            flash('Cliente excluído com sucesso!', 'success')
        else:
            flash('Erro ao excluir cliente', 'error')
    except Exception as e:
        logger.error(f"Error deleting client: {str(e)}")
        flash(f'Erro ao excluir cliente: {str(e)}', 'error')
    
    return redirect(url_for('clients'))

@app.route('/clients/renew/<client_id>', methods=['POST'])
def renew_client(client_id):
    """Renew client plan"""
    try:
        client = storage.get_client_by_id(client_id)
        if not client:
            flash('Cliente não encontrado', 'error')
            return redirect(url_for('clients'))
        
        renewal_days = int(request.form.get('renewal_days', 30))
        mark_as_paid = request.form.get('mark_as_paid') == 'on'
        
        # Renew the plan
        if client.renew_plan(renewal_days):
            if mark_as_paid:
                client.mark_as_paid()
            else:
                client.mark_as_pending()
            
            # Save to GitHub
            if storage.update_client(client):
                # Update scheduler
                setup_reminders(scheduler)
                payment_status = "e marcado como pago" if mark_as_paid else ""
                flash(f'Plano renovado por {renewal_days} dias {payment_status}!', 'success')
            else:
                flash('Erro ao salvar renovação no GitHub', 'error')
        else:
            flash('Erro ao renovar plano', 'error')
            
    except ValueError:
        flash('Número de dias inválido', 'error')
    except Exception as e:
        logger.error(f"Error renewing client: {str(e)}")
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

@app.route('/api/system/health')
def api_system_health():
    """API endpoint for system health check"""
    try:
        from whatsapp_integration import is_whatsapp_connected
        from message_queue import get_queue_status
        
        queue_status = get_queue_status()
        storage_stats = storage.get_storage_stats()
        
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'whatsapp': {
                    'status': 'up' if is_whatsapp_connected() else 'down',
                    'connected': is_whatsapp_connected()
                },
                'message_queue': {
                    'status': 'up' if queue_status.get('processing', False) else 'down',
                    'queue_size': queue_status.get('queue_size', 0),
                    'processing': queue_status.get('processing', False)
                },
                'storage': {
                    'status': 'up' if storage_stats.get('connection_status') == 'connected' else 'down',
                    'connection': storage_stats.get('connection_status', 'unknown')
                },
                'scheduler': {
                    'status': 'up',
                    'running_jobs': len(scheduler.get_jobs())
                }
            }
        }
        
        # Determine overall health
        component_statuses = [comp['status'] for comp in health['components'].values()]
        if 'down' in component_statuses:
            health['status'] = 'degraded' if 'up' in component_statuses else 'down'
        
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

@app.route('/api/whatsapp/reconnect', methods=['POST'])
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
