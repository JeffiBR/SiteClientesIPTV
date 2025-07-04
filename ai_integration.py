import os
import requests
import json
import logging
from typing import Dict, Optional
from models import Client, AIConfiguration
from github_storage import storage

logger = logging.getLogger(__name__)

class AIMessageGenerator:
    def __init__(self):
        self.config = None
        self.load_configuration()
        
    def load_configuration(self):
        """Carrega a configuração de IA do storage"""
        try:
            config_dict = storage.get_ai_configuration()
            self.config = AIConfiguration.from_dict(config_dict)
            logger.info(f"AI configuration loaded: Provider={self.config.provider}, Enabled={self.config.enabled}")
        except Exception as e:
            logger.error(f"Error loading AI configuration: {str(e)}")
            # Fallback para configuração padrão
            from models import DEFAULT_AI_CONFIG
            self.config = AIConfiguration.from_dict(DEFAULT_AI_CONFIG)
    
    def generate_reminder_message(self, client: Client, reminder_type: str) -> str:
        """Gera uma mensagem personalizada usando IA para o cliente"""
        try:
            # Recarregar configuração se necessário
            if not self.config or not self.config.enabled:
                logger.info("AI disabled, using template message")
                return self._get_template_message(client, reminder_type)
            
            if not self.config.api_key:
                logger.warning("No API key configured, using template message")
                return self._get_template_message(client, reminder_type)
            
            # Gerar mensagem baseada no provedor
            if self.config.provider == 'openrouter':
                return self._generate_openrouter_message(client, reminder_type)
            elif self.config.provider == 'openai':
                return self._generate_openai_message(client, reminder_type)
            elif self.config.provider == 'anthropic':
                return self._generate_anthropic_message(client, reminder_type)
            elif self.config.provider == 'local':
                return self._generate_local_message(client, reminder_type)
            else:
                logger.error(f"Unsupported provider: {self.config.provider}")
                return self._get_template_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Error generating AI message: {str(e)}")
            if self.config and self.config.fallback_to_templates:
                return self._get_template_message(client, reminder_type)
            else:
                return self._get_default_message(client, reminder_type)
    
    def _generate_openrouter_message(self, client: Client, reminder_type: str) -> str:
        """Gera mensagem usando OpenRouter"""
        try:
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/yourusername/client-manager",
                "X-Title": "Client Manager Bot"
            }
            
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(client, reminder_type)
            
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
            
            response = requests.post(
                self.config.base_url or "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, 
                json=payload, 
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data['choices'][0]['message']['content'].strip()
                logger.info(f"OpenRouter message generated for {client.name}")
                return self._format_message(message)
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return self._get_template_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Error generating OpenRouter message: {str(e)}")
            return self._get_template_message(client, reminder_type)
    
    def _generate_openai_message(self, client: Client, reminder_type: str) -> str:
        """Gera mensagem usando OpenAI"""
        try:
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(client, reminder_type)
            
            payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature
            }
            
            response = requests.post(
                self.config.base_url or "https://api.openai.com/v1/chat/completions",
                headers=headers, 
                json=payload, 
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data['choices'][0]['message']['content'].strip()
                logger.info(f"OpenAI message generated for {client.name}")
                return self._format_message(message)
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return self._get_template_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Error generating OpenAI message: {str(e)}")
            return self._get_template_message(client, reminder_type)
    
    def _generate_anthropic_message(self, client: Client, reminder_type: str) -> str:
        """Gera mensagem usando Anthropic Claude"""
        try:
            headers = {
                "x-api-key": self.config.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(client, reminder_type)
            
            payload = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            }
            
            response = requests.post(
                self.config.base_url or "https://api.anthropic.com/v1/messages",
                headers=headers, 
                json=payload, 
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data['content'][0]['text'].strip()
                logger.info(f"Anthropic message generated for {client.name}")
                return self._format_message(message)
            else:
                logger.error(f"Anthropic API error: {response.status_code} - {response.text}")
                return self._get_template_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Error generating Anthropic message: {str(e)}")
            return self._get_template_message(client, reminder_type)
    
    def _generate_local_message(self, client: Client, reminder_type: str) -> str:
        """Gera mensagem usando Ollama local"""
        try:
            base_url = self.config.base_url or "http://localhost:11434"
            
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(client, reminder_type)
            
            payload = {
                "model": self.config.model,
                "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
                "stream": False,
                "options": {
                    "num_predict": self.config.max_tokens,
                    "temperature": self.config.temperature
                }
            }
            
            response = requests.post(
                f"{base_url}/api/generate",
                json=payload, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data['response'].strip()
                logger.info(f"Local AI message generated for {client.name}")
                return self._format_message(message)
            else:
                logger.error(f"Local AI error: {response.status_code} - {response.text}")
                return self._get_template_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Error generating local AI message: {str(e)}")
            return self._get_template_message(client, reminder_type)
    
    def _build_system_prompt(self) -> str:
        """Constrói o prompt do sistema baseado na configuração"""
        base_prompt = self.config.get_personality_prompt()
        
        system_prompt = f"""{base_prompt}

Você é um assistente especializado em criar mensagens de cobrança e lembretes para clientes de serviços digitais (IPTV, VPN, Streaming, Gaming, Internet).

Diretrizes importantes:
- Seja sempre respeitoso e profissional
- Use linguagem clara e objetiva
- Inclua informações específicas do cliente (nome, valor, tipo de serviço)
- Adapte o tom baseado no tipo de serviço
- Mantenha o foco na renovação/pagamento
- Evite ser muito insistente ou agressivo

Idioma: {self.config.language}
"""
        
        if self.config.custom_instructions:
            system_prompt += f"\n\nInstruções personalizadas: {self.config.custom_instructions}"
        
        return system_prompt
    
    def _build_user_prompt(self, client: Client, reminder_type: str) -> str:
        """Constrói o prompt do usuário baseado no cliente e tipo de lembrete"""
        context = {
            "nome": client.name,
            "plano": client.plan_type,
            "valor": f"R$ {client.value:.2f}",
            "data_vencimento": client.plan_duration,
            "dias_restantes": client.days_until_expiration,
            "status": client.status,
            "dia_pagamento": client.payment_day
        }
        
        if reminder_type == "3days":
            return f"""
Crie uma mensagem de lembrete para um cliente cujo plano vence em 3 dias.

Informações do cliente:
- Nome: {context['nome']}
- Tipo de serviço: {context['plano']}
- Valor: {context['valor']}
- Data de vencimento: {context['data_vencimento']}
- Dia do pagamento: {context['dia_pagamento']}

Tipo de mensagem: Lembrete amigável de 3 dias antes do vencimento.

Gere apenas a mensagem final, sem explicações ou formatação extra.
"""
        else:  # payment day
            return f"""
Crie uma mensagem de cobrança para um cliente cujo plano vence HOJE.

Informações do cliente:
- Nome: {context['nome']}
- Tipo de serviço: {context['plano']}
- Valor: {context['valor']}
- Data de vencimento: HOJE ({context['data_vencimento']})

Tipo de mensagem: Cobrança do dia do vencimento.

Gere apenas a mensagem final, sem explicações ou formatação extra.
"""
    
    def _format_message(self, message: str) -> str:
        """Formata a mensagem baseada nas configurações"""
        # Remover aspas se existirem
        message = message.strip('"\'')
        
        # Limitar tamanho se configurado
        if len(message) > self.config.max_message_length:
            message = message[:self.config.max_message_length-3] + "..."
        
        return message
    
    def _get_template_message(self, client: Client, reminder_type: str) -> str:
        """Busca mensagem dos templates baseada no tipo de plano"""
        try:
            templates = storage.get_message_templates()
            
            # Procurar template específico para o tipo de plano
            for template in templates:
                if (template.plan_type == client.plan_type and 
                    template.type == reminder_type):
                    return self._replace_placeholders(template.content, client)
            
            # Procurar template geral
            for template in templates:
                if (template.plan_type == 'all' and 
                    template.type == reminder_type):
                    return self._replace_placeholders(template.content, client)
            
            # Fallback para mensagem padrão
            return self._get_default_message(client, reminder_type)
            
        except Exception as e:
            logger.error(f"Error getting template message: {str(e)}")
            return self._get_default_message(client, reminder_type)
    
    def _replace_placeholders(self, template: str, client: Client) -> str:
        """Substitui placeholders na mensagem template"""
        return template.format(
            name=client.name,
            plan_type=client.plan_type,
            value=f"{client.value:.2f}",
            payment_day=client.payment_day
        )
    
    def _get_default_message(self, client: Client, reminder_type: str) -> str:
        """Retorna mensagens padrão como último recurso"""
        if reminder_type == "3days":
            return f"Olá {client.name}! Seu plano {client.plan_type} no valor de R$ {client.value:.2f} vence em 3 dias. Não esqueça de renovar!"
        else:
            return f"Olá {client.name}! Hoje é o dia do vencimento do seu plano {client.plan_type} no valor de R$ {client.value:.2f}. Por favor, realize o pagamento."
    
    def test_configuration(self) -> Dict:
        """Testa a configuração atual de IA"""
        if not self.config:
            return {
                'status': 'error',
                'message': 'Configuração não carregada'
            }
        
        return storage.test_ai_configuration(self.config.to_dict())
    
    def reload_configuration(self):
        """Recarrega a configuração de IA"""
        self.load_configuration()

# Instância global
ai_generator = AIMessageGenerator()

def get_ai_generator() -> AIMessageGenerator:
    """Retorna a instância global do gerador de IA"""
    return ai_generator