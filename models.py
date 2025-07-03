from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

class Client:
    def __init__(self, id: str, name: str, phone: str, plan_type: str, value: float, 
                 plan_duration: str, reminder_time_3days: str = "09:00", 
                 reminder_time_payment: str = "10:00", custom_message_3days: str = "", 
                 custom_message_payment: str = "", created_at: Optional[str] = None,
                 payment_status: str = "pending", last_renewal_date: Optional[str] = None,
                 renewal_days: int = 0):
        self.id = id
        self.name = name
        self.phone = phone  # Obrigatório agora
        self.plan_type = plan_type  # 'IPTV' or 'VPN'
        self.value = value
        self.plan_duration = plan_duration  # Data de duração do plano (YYYY-MM-DD)
        self.reminder_time_3days = reminder_time_3days  # Format: "HH:MM"
        self.reminder_time_payment = reminder_time_payment  # Format: "HH:MM"
        self.custom_message_3days = custom_message_3days
        self.custom_message_payment = custom_message_payment
        self.created_at = created_at or datetime.now().isoformat()
        self.payment_status = payment_status  # 'pending', 'paid', 'overdue'
        self.last_renewal_date = last_renewal_date
        self.renewal_days = renewal_days
    
    @property
    def payment_day(self) -> int:
        """Calcula o dia do pagamento baseado na data de duração do plano"""
        try:
            plan_date = datetime.strptime(self.plan_duration, '%Y-%m-%d')
            return plan_date.day
        except:
            return 1
    
    @property
    def days_until_expiration(self) -> int:
        """Calcula quantos dias faltam para o plano expirar"""
        try:
            plan_date = datetime.strptime(self.plan_duration, '%Y-%m-%d').date()
            today = date.today()
            delta = plan_date - today
            return delta.days
        except:
            return 0
    
    @property
    def is_expired(self) -> bool:
        """Verifica se o plano está expirado"""
        return self.days_until_expiration < 0
    
    @property
    def status(self) -> str:
        """Retorna o status do plano"""
        days = self.days_until_expiration
        if days < 0:
            return "expirado"
        elif days <= 3:
            return "vencendo"
        else:
            return "ativo"
    
    @property
    def should_send_reminder(self) -> bool:
        """Verifica se deve enviar lembrete baseado no status de pagamento"""
        return self.payment_status != "paid"
    
    def renew_plan(self, days: int) -> bool:
        """Renova o plano por X dias"""
        try:
            current_date = datetime.strptime(self.plan_duration, '%Y-%m-%d').date()
            # Se o plano já expirou, renova a partir de hoje
            if current_date < date.today():
                new_date = date.today() + timedelta(days=days)
            else:
                new_date = current_date + timedelta(days=days)
            
            self.plan_duration = new_date.strftime('%Y-%m-%d')
            self.last_renewal_date = datetime.now().isoformat()
            self.renewal_days = days
            return True
        except:
            return False
    
    def mark_as_paid(self):
        """Marca como pago"""
        self.payment_status = "paid"
    
    def mark_as_pending(self):
        """Marca como pendente"""
        self.payment_status = "pending"
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'plan_type': self.plan_type,
            'value': self.value,
            'plan_duration': self.plan_duration,
            'reminder_time_3days': self.reminder_time_3days,
            'reminder_time_payment': self.reminder_time_payment,
            'custom_message_3days': self.custom_message_3days,
            'custom_message_payment': self.custom_message_payment,
            'created_at': self.created_at,
            'payment_status': getattr(self, 'payment_status', 'pending'),
            'last_renewal_date': getattr(self, 'last_renewal_date', None),
            'renewal_days': getattr(self, 'renewal_days', 0)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Client':
        return cls(**data)

class MessageTemplate:
    def __init__(self, id: str, name: str, content: str, type: str):
        self.id = id
        self.name = name
        self.content = content  # Message content with placeholders
        self.type = type  # '3days' or 'payment'
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'type': self.type
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MessageTemplate':
        return cls(**data)

# Default message templates
DEFAULT_TEMPLATES = [
    {
        'id': 'default_3days',
        'name': 'Lembrete 3 Dias Antes',
        'content': 'Olá {name}! Seu plano {plan_type} no valor de R$ {value} vence em 3 dias (dia {payment_day}). Não esqueça de renovar!',
        'type': '3days'
    },
    {
        'id': 'default_payment',
        'name': 'Lembrete Dia do Pagamento',
        'content': 'Olá {name}! Hoje é o dia do vencimento do seu plano {plan_type} no valor de R$ {value}. Por favor, realize o pagamento para manter o serviço ativo.',
        'type': 'payment'
    }
]
