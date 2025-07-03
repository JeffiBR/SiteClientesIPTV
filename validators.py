import re
from typing import Dict, Any, List
from datetime import datetime, date, timedelta

class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

class ClientValidator:
    @staticmethod
    def validate_phone(phone: str) -> str:
        """Valida e sanitiza número de telefone brasileiro"""
        if not phone:
            raise ValidationError("phone", "Telefone é obrigatório")
        
        # Remove caracteres não numéricos
        clean_phone = re.sub(r'[^\d]', '', phone)
        
        # Valida comprimento
        if len(clean_phone) < 10:
            raise ValidationError("phone", "Telefone deve ter pelo menos 10 dígitos")
        
        if len(clean_phone) > 15:
            raise ValidationError("phone", "Telefone deve ter no máximo 15 dígitos")
        
        # Formato brasileiro: adiciona 55 se necessário
        if len(clean_phone) == 11:  # Celular: 11987654321
            return f"55{clean_phone}"
        elif len(clean_phone) == 10:  # Fixo: 1134567890
            return f"55{clean_phone}"
        elif len(clean_phone) == 13 and clean_phone.startswith('55'):
            return clean_phone
        else:
            return clean_phone
    
    @staticmethod
    def validate_name(name: str) -> str:
        """Valida nome do cliente"""
        if not name or not name.strip():
            raise ValidationError("name", "Nome é obrigatório")
        
        clean_name = name.strip()
        
        if len(clean_name) < 2:
            raise ValidationError("name", "Nome deve ter pelo menos 2 caracteres")
        
        if len(clean_name) > 100:
            raise ValidationError("name", "Nome deve ter no máximo 100 caracteres")
        
        # Remove caracteres especiais perigosos
        if re.search(r'[<>\"\'&]', clean_name):
            raise ValidationError("name", "Nome contém caracteres inválidos")
        
        return clean_name
    
    @staticmethod
    def validate_plan_type(plan_type: str) -> str:
        """Valida tipo de plano"""
        if not plan_type:
            raise ValidationError("plan_type", "Tipo de plano é obrigatório")
        
        valid_plans = ['IPTV', 'VPN']
        if plan_type.upper() not in valid_plans:
            raise ValidationError("plan_type", f"Plano deve ser um de: {', '.join(valid_plans)}")
        
        return plan_type.upper()
    
    @staticmethod
    def validate_value(value: Any) -> float:
        """Valida valor do plano"""
        if value is None or value == '':
            raise ValidationError("value", "Valor é obrigatório")
        
        try:
            # Se for string, tenta converter removendo vírgulas
            if isinstance(value, str):
                value = value.replace(',', '.')
            value = float(value)
        except (ValueError, TypeError):
            raise ValidationError("value", "Valor deve ser um número válido")
        
        if value <= 0:
            raise ValidationError("value", "Valor deve ser maior que zero")
        
        if value > 9999.99:
            raise ValidationError("value", "Valor muito alto (máximo R$ 9.999,99)")
        
        return round(value, 2)
    
    @staticmethod
    def validate_plan_duration(plan_duration: str) -> str:
        """Valida data de vencimento"""
        if not plan_duration:
            raise ValidationError("plan_duration", "Data de vencimento é obrigatória")
        
        try:
            # Verifica formato da data
            plan_date = datetime.strptime(plan_duration, '%Y-%m-%d').date()
            
            # Verificar se não é muito no passado (mais de 1 ano)
            if plan_date < date.today() - timedelta(days=365):
                raise ValidationError("plan_duration", "Data muito antiga (máximo 1 ano no passado)")
            
            # Verificar se não é muito no futuro (mais de 10 anos)
            if plan_date > date.today() + timedelta(days=3650):
                raise ValidationError("plan_duration", "Data muito no futuro (máximo 10 anos)")
            
            return plan_duration
        except ValueError:
            raise ValidationError("plan_duration", "Data deve estar no formato YYYY-MM-DD")
    
    @staticmethod
    def validate_time(time_str: str, field_name: str) -> str:
        """Valida formato de horário HH:MM"""
        if not time_str:
            return "09:00"  # Default
        
        try:
            # Verifica formato
            datetime.strptime(time_str, '%H:%M')
            return time_str
        except ValueError:
            raise ValidationError(field_name, "Horário deve estar no formato HH:MM")
    
    @staticmethod
    def validate_message(message: str, field_name: str) -> str:
        """Valida mensagem personalizada"""
        if not message:
            return ""  # Mensagem vazia é permitida
        
        clean_message = message.strip()
        
        if len(clean_message) > 500:
            raise ValidationError(field_name, "Mensagem muito longa (máximo 500 caracteres)")
        
        # Remove tags HTML básicas por segurança
        clean_message = re.sub(r'<[^>]*>', '', clean_message)
        
        return clean_message
    
    @staticmethod
    def validate_renewal_days(days: Any) -> int:
        """Valida número de dias para renovação"""
        if days is None or days == '':
            raise ValidationError("renewal_days", "Número de dias é obrigatório")
        
        try:
            days = int(days)
        except (ValueError, TypeError):
            raise ValidationError("renewal_days", "Número de dias deve ser um número inteiro")
        
        if days <= 0:
            raise ValidationError("renewal_days", "Número de dias deve ser maior que zero")
        
        if days > 3650:  # Máximo 10 anos
            raise ValidationError("renewal_days", "Número de dias muito alto (máximo 3650)")
        
        return days
    
    @staticmethod
    def validate_payment_status(status: str) -> str:
        """Valida status de pagamento"""
        if not status:
            return "pending"  # Default
        
        valid_statuses = ['pending', 'paid', 'overdue']
        if status not in valid_statuses:
            raise ValidationError("payment_status", f"Status deve ser um de: {', '.join(valid_statuses)}")
        
        return status
    
    @classmethod
    def validate_client_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida todos os dados do cliente"""
        validated = {}
        errors = []
        
        # Validações obrigatórias
        try:
            validated['name'] = cls.validate_name(data.get('name', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['phone'] = cls.validate_phone(data.get('phone', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['plan_type'] = cls.validate_plan_type(data.get('plan_type', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['value'] = cls.validate_value(data.get('value'))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['plan_duration'] = cls.validate_plan_duration(data.get('plan_duration', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        # Validações opcionais com defaults
        try:
            validated['reminder_time_3days'] = cls.validate_time(
                data.get('reminder_time_3days', '09:00'), 'reminder_time_3days'
            )
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['reminder_time_payment'] = cls.validate_time(
                data.get('reminder_time_payment', '10:00'), 'reminder_time_payment'
            )
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['custom_message_3days'] = cls.validate_message(
                data.get('custom_message_3days', ''), 'custom_message_3days'
            )
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['custom_message_payment'] = cls.validate_message(
                data.get('custom_message_payment', ''), 'custom_message_payment'
            )
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['payment_status'] = cls.validate_payment_status(
                data.get('payment_status', 'pending')
            )
        except ValidationError as e:
            errors.append(str(e))
        
        if errors:
            raise ValueError(f"Erros de validação: {'; '.join(errors)}")
        
        return validated
    
    @classmethod
    def validate_renewal_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida dados de renovação"""
        validated = {}
        errors = []
        
        try:
            validated['renewal_days'] = cls.validate_renewal_days(data.get('renewal_days'))
        except ValidationError as e:
            errors.append(str(e))
        
        # mark_as_paid é boolean
        validated['mark_as_paid'] = data.get('mark_as_paid') in ['on', 'true', True, '1', 1]
        
        if errors:
            raise ValueError(f"Erros de validação: {'; '.join(errors)}")
        
        return validated

class MessageTemplateValidator:
    @staticmethod
    def validate_template_name(name: str) -> str:
        """Valida nome do template"""
        if not name or not name.strip():
            raise ValidationError("name", "Nome do template é obrigatório")
        
        clean_name = name.strip()
        
        if len(clean_name) < 3:
            raise ValidationError("name", "Nome deve ter pelo menos 3 caracteres")
        
        if len(clean_name) > 50:
            raise ValidationError("name", "Nome deve ter no máximo 50 caracteres")
        
        return clean_name
    
    @staticmethod
    def validate_template_content(content: str) -> str:
        """Valida conteúdo do template"""
        if not content or not content.strip():
            raise ValidationError("content", "Conteúdo do template é obrigatório")
        
        clean_content = content.strip()
        
        if len(clean_content) < 10:
            raise ValidationError("content", "Conteúdo deve ter pelo menos 10 caracteres")
        
        if len(clean_content) > 1000:
            raise ValidationError("content", "Conteúdo muito longo (máximo 1000 caracteres)")
        
        return clean_content
    
    @staticmethod
    def validate_template_type(template_type: str) -> str:
        """Valida tipo do template"""
        if not template_type:
            raise ValidationError("type", "Tipo do template é obrigatório")
        
        valid_types = ['3days', 'payment']
        if template_type not in valid_types:
            raise ValidationError("type", f"Tipo deve ser um de: {', '.join(valid_types)}")
        
        return template_type
    
    @classmethod
    def validate_template_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida todos os dados do template"""
        validated = {}
        errors = []
        
        try:
            validated['name'] = cls.validate_template_name(data.get('name', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['content'] = cls.validate_template_content(data.get('content', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        try:
            validated['type'] = cls.validate_template_type(data.get('type', ''))
        except ValidationError as e:
            errors.append(str(e))
        
        if errors:
            raise ValueError(f"Erros de validação: {'; '.join(errors)}")
        
        return validated

# Funções de conveniência para uso direto
def validate_and_format_phone(phone: str) -> str:
    """Função de conveniência para validar telefone"""
    return ClientValidator.validate_phone(phone)

def validate_monetary_value(value: Any) -> float:
    """Função de conveniência para validar valor monetário"""
    return ClientValidator.validate_value(value)

def validate_date_format(date_str: str) -> str:
    """Função de conveniência para validar data"""
    return ClientValidator.validate_plan_duration(date_str)