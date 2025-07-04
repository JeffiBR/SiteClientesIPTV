from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

class Client:
    def __init__(self, id: str, name: str, phone: str, plan_type: str, value: float, 
                 plan_duration: str, server: str = "UltraPlay", reminder_time_3days: str = "09:00", 
                 reminder_time_payment: str = "10:00", custom_message_3days: str = "", 
                 custom_message_payment: str = "", created_at: Optional[str] = None,
                 payment_status: str = "pending", last_renewal_date: Optional[str] = None,
                 renewal_days: int = 0, observations: str = "", renewal_history: List = None):
        self.id = id
        self.name = name
        self.phone = phone  # Obrigatório agora
        self.plan_type = plan_type  # 'IPTV', 'VPN', 'STREAMING', 'GAMING', 'INTERNET', 'OUTROS'
        self.value = value
        self.plan_duration = plan_duration  # Data de duração do plano (YYYY-MM-DD)
        self.server = server  # 'UltraPlay', '4kPlayerPro', 'Blaze'
        self.reminder_time_3days = reminder_time_3days  # Format: "HH:MM"
        self.reminder_time_payment = reminder_time_payment  # Format: "HH:MM"
        self.custom_message_3days = custom_message_3days
        self.custom_message_payment = custom_message_payment
        self.created_at = created_at or datetime.now().isoformat()
        self.payment_status = payment_status  # 'pending', 'paid', 'overdue'
        self.last_renewal_date = last_renewal_date
        self.renewal_days = renewal_days
        self.observations = observations  # Campo para observações/notas sobre o cliente
        self.renewal_history = renewal_history or []  # Histórico de renovações
    
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
    def status_color(self) -> str:
        """Retorna a cor baseada no status para UI"""
        days = self.days_until_expiration
        if days < 0:
            return "danger"  # Vermelho
        elif days <= 3:
            return "warning"  # Amarelo
        elif days <= 7:
            return "info"  # Azul
        else:
            return "success"  # Verde
    
    @property
    def should_send_reminder(self) -> bool:
        """Verifica se deve enviar lembrete baseado no status de pagamento"""
        return self.payment_status != "paid" and not self.is_expired
    
    def renew_plan(self, days: int) -> bool:
        """Renova o plano por X dias e registra no histórico"""
        try:
            current_date = datetime.strptime(self.plan_duration, '%Y-%m-%d').date()
            
            # Se o plano já expirou, renova a partir de hoje
            if current_date < date.today():
                new_date = date.today() + timedelta(days=days)
            else:
                new_date = current_date + timedelta(days=days)
            
            # Registrar no histórico de renovações
            renewal_record = {
                'date': datetime.now().isoformat(),
                'days_added': days,
                'previous_expiration': self.plan_duration,
                'new_expiration': new_date.strftime('%Y-%m-%d'),
                'value': self.value
            }
            
            # Atualizar dados do cliente
            self.plan_duration = new_date.strftime('%Y-%m-%d')
            self.last_renewal_date = datetime.now().isoformat()
            self.renewal_days = days
            self.payment_status = "paid"  # Marcar como pago ao renovar
            self.renewal_history.append(renewal_record)
            
            return True
        except Exception as e:
            print(f"Erro ao renovar plano: {e}")
            return False
    
    def mark_as_paid(self):
        """Marca como pago"""
        self.payment_status = "paid"
    
    def mark_as_pending(self):
        """Marca como pendente"""
        self.payment_status = "pending"
    
    def mark_as_overdue(self):
        """Marca como em atraso"""
        self.payment_status = "overdue"
    
    def add_observation(self, observation: str):
        """Adiciona uma observação com timestamp"""
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
        if self.observations:
            self.observations += f"\n[{timestamp}] {observation}"
        else:
            self.observations = f"[{timestamp}] {observation}"
    
    def get_renewal_summary(self) -> Dict:
        """Retorna resumo das renovações"""
        total_renewals = len(self.renewal_history)
        total_days_renewed = sum(r.get('days_added', 0) for r in self.renewal_history)
        total_revenue = sum(r.get('value', 0) for r in self.renewal_history)
        
        return {
            'total_renewals': total_renewals,
            'total_days_renewed': total_days_renewed,
            'total_revenue': total_revenue,
            'last_renewal': self.last_renewal_date,
            'history': self.renewal_history
        }
    
    def get_total_revenue(self) -> float:
        """Calcula o total de receita gerada por este cliente"""
        # Valor inicial do plano
        initial_revenue = self.value
        
        # Soma das renovações
        renewals_revenue = sum(r.get('value', 0) for r in self.renewal_history)
        
        return initial_revenue + renewals_revenue
    
    def get_client_age_days(self) -> int:
        """Calcula quantos dias o cliente está ativo"""
        try:
            created_date = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
            return (datetime.now() - created_date).days
        except:
            return 0
    
    def get_lifetime_value(self) -> float:
        """Calcula o LTV (Lifetime Value) do cliente"""
        return self.get_total_revenue()
    
    def get_monthly_average_revenue(self) -> float:
        """Calcula a receita média mensal do cliente"""
        days_active = self.get_client_age_days()
        if days_active == 0:
            return 0
        
        total_revenue = self.get_total_revenue()
        months_active = max(1, days_active / 30)  # Mínimo 1 mês
        
        return total_revenue / months_active
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'plan_type': self.plan_type,
            'value': self.value,
            'plan_duration': self.plan_duration,
            'server': getattr(self, 'server', 'UltraPlay'),
            'reminder_time_3days': self.reminder_time_3days,
            'reminder_time_payment': self.reminder_time_payment,
            'custom_message_3days': self.custom_message_3days,
            'custom_message_payment': self.custom_message_payment,
            'created_at': self.created_at,
            'payment_status': getattr(self, 'payment_status', 'pending'),
            'last_renewal_date': getattr(self, 'last_renewal_date', None),
            'renewal_days': getattr(self, 'renewal_days', 0),
            'observations': getattr(self, 'observations', ''),
            'renewal_history': getattr(self, 'renewal_history', [])
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Client':
        return cls(**data)

class MessageTemplate:
    def __init__(self, id: str, name: str, content: str, type: str, plan_type: str = "all"):
        self.id = id
        self.name = name
        self.content = content  # Message content with placeholders
        self.type = type  # '3days' or 'payment'
        self.plan_type = plan_type  # 'IPTV', 'VPN', or 'all'
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'type': self.type,
            'plan_type': self.plan_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'MessageTemplate':
        # Para compatibilidade com templates antigos
        plan_type = data.get('plan_type', 'all')
        return cls(
            id=data['id'],
            name=data['name'],
            content=data['content'],
            type=data['type'],
            plan_type=plan_type
        )

# Default message templates
DEFAULT_TEMPLATES = [
    # Templates gerais (compatibilidade)
    {
        'id': 'default_3days',
        'name': 'Lembrete 3 Dias - Geral',
        'content': 'Olá {name}! Seu plano {plan_type} no valor de R$ {value} vence em 3 dias (dia {payment_day}). Não esqueça de renovar!',
        'type': '3days',
        'plan_type': 'all'
    },
    {
        'id': 'default_payment',
        'name': 'Lembrete Pagamento - Geral',
        'content': 'Olá {name}! Hoje é o dia do vencimento do seu plano {plan_type} no valor de R$ {value}. Por favor, realize o pagamento para manter o serviço ativo.',
        'type': 'payment',
        'plan_type': 'all'
    },
    
    # Templates específicos para IPTV
    {
        'id': 'iptv_3days',
        'name': 'IPTV - Lembrete 3 Dias',
        'content': '📺 Olá {name}! Seu plano IPTV Premium de R$ {value} vence em 3 dias (dia {payment_day}). Mantenha seus canais favoritos sempre disponíveis! Renove já e continue aproveitando todos os canais em HD.',
        'type': '3days',
        'plan_type': 'IPTV'
    },
    {
        'id': 'iptv_payment',
        'name': 'IPTV - Dia do Pagamento',
        'content': '📺 {name}, hoje é o dia! Seu plano IPTV de R$ {value} vence hoje. Para não perder nenhum programa, renove agora e garante mais 30 dias de entretenimento sem interrupção!',
        'type': 'payment',
        'plan_type': 'IPTV'
    },
    
    # Templates específicos para VPN
    {
        'id': 'vpn_3days',
        'name': 'VPN - Lembrete 3 Dias',
        'content': '🔒 Olá {name}! Sua proteção VPN Premium de R$ {value} vence em 3 dias (dia {payment_day}). Mantenha sua privacidade e segurança online protegidas. Renove já!',
        'type': '3days',
        'plan_type': 'VPN'
    },
    {
        'id': 'vpn_payment',
        'name': 'VPN - Dia do Pagamento',
        'content': '🔒 {name}, sua segurança é prioridade! Seu plano VPN de R$ {value} vence hoje. Renove agora e continue navegando com total privacidade e proteção contra ameaças online.',
        'type': 'payment',
        'plan_type': 'VPN'
    },
    
    # Templates promocionais específicos
    {
        'id': 'iptv_promo',
        'name': 'IPTV - Oferta Especial',
        'content': '🎉 {name}, oferta especial IPTV! Renovando hoje ganhe 5 dias extras GRÁTIS. Seu plano de R$ {value} pode ser renovado com desconto. Aproveite!',
        'type': 'promo',
        'plan_type': 'IPTV'
    },
    {
        'id': 'vpn_promo',
        'name': 'VPN - Upgrade Premium',
        'content': '⚡ {name}, que tal um upgrade? Sua VPN de R$ {value} pode ser atualizada para o plano Premium com servidores mais rápidos e proteção avançada. Consulte nossos planos!',
        'type': 'promo',
        'plan_type': 'VPN'
    }
]

class AIConfiguration:
    def __init__(self, 
                 provider: str = "openrouter",
                 api_key: str = "",
                 model: str = "qwen/qwen-2.5-72b-instruct:free",
                 base_url: str = "",
                 max_tokens: int = 200,
                 temperature: float = 0.7,
                 personality: str = "professional",
                 custom_personality: str = "",
                 message_style: str = "friendly",
                 include_emojis: bool = True,
                 max_message_length: int = 150,
                 language: str = "pt-BR",
                 custom_instructions: str = "",
                 enabled: bool = False,
                 fallback_to_templates: bool = True,
                 created_at: Optional[str] = None,
                 updated_at: Optional[str] = None):
        
        self.provider = provider  # openrouter, openai, anthropic, local
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.personality = personality  # professional, friendly, casual, formal
        self.custom_personality = custom_personality
        self.message_style = message_style  # friendly, formal, urgent, casual
        self.include_emojis = include_emojis
        self.max_message_length = max_message_length
        self.language = language
        self.custom_instructions = custom_instructions
        self.enabled = enabled
        self.fallback_to_templates = fallback_to_templates
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            'provider': self.provider,
            'api_key': self.api_key,
            'model': self.model,
            'base_url': self.base_url,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'personality': self.personality,
            'custom_personality': self.custom_personality,
            'message_style': self.message_style,
            'include_emojis': self.include_emojis,
            'max_message_length': self.max_message_length,
            'language': self.language,
            'custom_instructions': self.custom_instructions,
            'enabled': self.enabled,
            'fallback_to_templates': self.fallback_to_templates,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AIConfiguration':
        return cls(**data)
    
    def update_timestamp(self):
        """Atualiza o timestamp de modificação"""
        self.updated_at = datetime.now().isoformat()
    
    def get_personality_prompt(self) -> str:
        """Retorna o prompt de personalidade baseado na configuração"""
        personalities = {
            "professional": "Você é um assistente profissional e cortês. Use linguagem formal e seja sempre respeitoso.",
            "friendly": "Você é um assistente amigável e caloroso. Use um tom acolhedor e próximo, mas mantendo profissionalismo.",
            "casual": "Você é um assistente descontraído e informal. Use linguagem coloquial e seja mais direto.",
            "formal": "Você é um assistente extremamente formal e educado. Use linguagem rebuscada e cerimoniosa.",
            "custom": self.custom_personality
        }
        
        base_prompt = personalities.get(self.personality, personalities["professional"])
        
        style_additions = {
            "friendly": " Seja cordial e acolhedor em suas mensagens.",
            "formal": " Mantenha sempre um tom sério e respeitoso.",
            "urgent": " Transmita senso de urgência quando necessário, mas sem ser agressivo.",
            "casual": " Seja mais relaxado e direto na comunicação."
        }
        
        full_prompt = base_prompt + style_additions.get(self.message_style, "")
        
        if self.custom_instructions:
            full_prompt += f" Instruções adicionais: {self.custom_instructions}"
        
        if not self.include_emojis:
            full_prompt += " IMPORTANTE: Não use emojis nas mensagens."
        
        full_prompt += f" Mantenha as mensagens com no máximo {self.max_message_length} caracteres."
        
        return full_prompt

# Configuração padrão de IA
DEFAULT_AI_CONFIG = {
    'provider': 'openrouter',
    'api_key': '',
    'model': 'qwen/qwen-2.5-72b-instruct:free',
    'base_url': 'https://openrouter.ai/api/v1/chat/completions',
    'max_tokens': 200,
    'temperature': 0.7,
    'personality': 'friendly',
    'custom_personality': '',
    'message_style': 'friendly',
    'include_emojis': True,
    'max_message_length': 150,
    'language': 'pt-BR',
    'custom_instructions': '',
    'enabled': False,
    'fallback_to_templates': True
}

# Modelos disponíveis por provedor
AI_MODELS = {
    'openrouter': [
        {'name': 'qwen/qwen-2.5-72b-instruct:free', 'display': 'Qwen 2.5 72B (Gratuito)', 'free': True},
        {'name': 'meta-llama/llama-3.1-8b-instruct:free', 'display': 'Llama 3.1 8B (Gratuito)', 'free': True},
        {'name': 'microsoft/wizardlm-2-8x22b:free', 'display': 'WizardLM 2 8x22B (Gratuito)', 'free': True},
        {'name': 'openai/gpt-4o', 'display': 'GPT-4o (Pago)', 'free': False},
        {'name': 'anthropic/claude-3.5-sonnet', 'display': 'Claude 3.5 Sonnet (Pago)', 'free': False},
        {'name': 'google/gemini-pro-1.5', 'display': 'Gemini Pro 1.5 (Pago)', 'free': False}
    ],
    'openai': [
        {'name': 'gpt-4o', 'display': 'GPT-4o', 'free': False},
        {'name': 'gpt-4o-mini', 'display': 'GPT-4o Mini', 'free': False},
        {'name': 'gpt-3.5-turbo', 'display': 'GPT-3.5 Turbo', 'free': False}
    ],
    'anthropic': [
        {'name': 'claude-3-5-sonnet-20241022', 'display': 'Claude 3.5 Sonnet', 'free': False},
        {'name': 'claude-3-haiku-20240307', 'display': 'Claude 3 Haiku', 'free': False}
    ],
    'local': [
        {'name': 'llama2', 'display': 'Llama 2 (Ollama)', 'free': True},
        {'name': 'mistral', 'display': 'Mistral (Ollama)', 'free': True},
        {'name': 'codellama', 'display': 'Code Llama (Ollama)', 'free': True}
    ]
}
