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
    
    def test_connection(self, config_data: Dict) -> Dict:
        """Testa a conexão com o provedor de IA"""
        try:
            test_message = "Responda apenas 'Teste realizado com sucesso' para confirmar a conexão."
            
            if config_data['provider'] == 'openrouter':
                response = self._call_openrouter_api(config_data, test_message)
            elif config_data['provider'] == 'openai':
                response = self._call_openai_api(config_data, test_message)
            elif config_data['provider'] == 'anthropic':
                response = self._call_anthropic_api(config_data, test_message)
            else:
                return {'success': False, 'error': 'Provedor não suportado'}
            
            return {'success': True, 'response': response}
            
        except Exception as e:
            logger.error(f"Error testing AI connection: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _call_openrouter_api(self, config: Dict, prompt: str) -> str:
        """Chama a API do OpenRouter"""
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/seu-usuario/cliente-manager",
            "X-Title": "Cliente Manager Bot"
        }
        
        data = {
            "model": config['model'],
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": config.get('max_tokens', 200),
            "temperature": config.get('temperature', 0.7)
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
    
    def _call_openai_api(self, config: Dict, prompt: str) -> str:
        """Chama a API do OpenAI"""
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": config['model'],
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": config.get('max_tokens', 200),
            "temperature": config.get('temperature', 0.7)
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")
    
    def _call_anthropic_api(self, config: Dict, prompt: str) -> str:
        """Chama a API do Anthropic"""
        headers = {
            "x-api-key": config['api_key'],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": config['model'],
            "max_tokens": config.get('max_tokens', 200),
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['content'][0]['text'].strip()
        else:
            raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")
    
    def generate_message_for_category(self, client_data: Dict, message_type: str) -> str:
        """Gera mensagem personalizada para categoria de cliente"""
        try:
            if not self.config.enabled:
                return self._get_fallback_message(client_data, message_type)
            
            # Construir prompt baseado na categoria e tipo
            prompt = self._build_category_prompt(client_data, message_type)
            
            # Chamar API baseada no provedor
            if self.config.provider == 'openrouter':
                response = self._call_openrouter_api(self.config.__dict__, prompt)
            elif self.config.provider == 'openai':
                response = self._call_openai_api(self.config.__dict__, prompt)
            elif self.config.provider == 'anthropic':
                response = self._call_anthropic_api(self.config.__dict__, prompt)
            else:
                return self._get_fallback_message(client_data, message_type)
            
            # Limitar tamanho da mensagem
            if len(response) > self.config.max_message_length:
                response = response[:self.config.max_message_length] + "..."
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating AI message: {str(e)}")
            if self.config.fallback_to_templates:
                return self._get_fallback_message(client_data, message_type)
            else:
                return "Erro ao gerar mensagem automática."
    
    def _build_category_prompt(self, client_data: Dict, message_type: str) -> str:
        """Constrói prompt específico para categoria"""
        category = client_data.get('plan_type', 'GERAL')
        name = client_data.get('name', 'Cliente')
        value = client_data.get('value', 0)
        days_remaining = client_data.get('days_remaining', 0)
        
        # Personalidade base
        personality_prompts = {
            'professional': 'Seja profissional e direto.',
            'friendly': 'Seja amigável e caloroso.',
            'casual': 'Use linguagem descontraída e informal.',
            'formal': 'Use tom formal e respeitoso.',
            'energetic': 'Seja animado e motivador.',
            'custom': self.config.custom_personality
        }
        
        personality = personality_prompts.get(self.config.personality, personality_prompts['professional'])
        
        # Mensagens específicas por categoria
        category_contexts = {
            'IPTV': 'sobre serviços de IPTV, canais de TV, qualidade de imagem e entretenimento',
            'VPN': 'sobre VPN, segurança online, privacidade e proteção de dados',
            'STREAMING': 'sobre streaming, filmes, séries e entretenimento digital',
            'GAMING': 'sobre gaming, jogos online, performance e velocidade de conexão',
            'INTERNET': 'sobre internet, conectividade e navegação',
            'OUTROS': 'sobre o serviço contratado'
        }
        
        context = category_contexts.get(category, category_contexts['OUTROS'])
        
        # Tipo de mensagem
        if message_type == '3days':
            timing = f"o plano vence em {days_remaining} dias"
        elif message_type == 'payment':
            timing = "o plano vence hoje"
        else:
            timing = "é hora de renovar"
        
        # Instruções personalizadas
        custom_instructions = self.config.custom_instructions or ""
        
        # Emojis
        emoji_instruction = "Use emojis adequados" if self.config.include_emojis else "Não use emojis"
        
        prompt = f"""
        Você é um assistente de atendimento ao cliente especializado em {context}.
        
        Instruções:
        - {personality}
        - {emoji_instruction}
        - Mantenha a mensagem com no máximo {self.config.max_message_length} caracteres
        - Use linguagem {self.config.language}
        - Estilo: {self.config.message_style}
        {f"- Instruções específicas: {custom_instructions}" if custom_instructions else ""}
        
        Situação: {timing}
        Cliente: {name}
        Categoria do serviço: {category}
        Valor: R$ {value:.2f}
        
        Crie uma mensagem personalizada de lembrete de pagamento/renovação para este cliente.
        A mensagem deve ser específica para a categoria {category} e mencionar os benefícios do serviço.
        """
        
        return prompt.strip()
    
    def _get_fallback_message(self, client_data: Dict, message_type: str) -> str:
        """Mensagem padrão quando IA não está disponível"""
        category = client_data.get('plan_type', 'GERAL')
        name = client_data.get('name', 'Cliente')
        value = client_data.get('value', 0)
        days_remaining = client_data.get('days_remaining', 0)
        
        if message_type == '3days':
            timing = f"vence em {days_remaining} dias"
        else:
            timing = "vence hoje"
        
        # Mensagens padrão por categoria
        fallback_messages = {
            'IPTV': f"📺 Olá {name}! Seu plano IPTV {timing}. Renove agora e continue aproveitando seus canais favoritos! Valor: R$ {value:.2f}",
            'VPN': f"🔒 Olá {name}! Sua VPN {timing}. Mantenha sua segurança online renovando agora! Valor: R$ {value:.2f}",
            'STREAMING': f"🎬 Olá {name}! Seu plano de streaming {timing}. Continue assistindo seus conteúdos favoritos! Valor: R$ {value:.2f}",
            'GAMING': f"🎮 Olá {name}! Seu plano gaming {timing}. Mantenha sua conexão de alta performance! Valor: R$ {value:.2f}",
            'INTERNET': f"🌐 Olá {name}! Seu plano de internet {timing}. Continue conectado com qualidade! Valor: R$ {value:.2f}",
            'OUTROS': f"📋 Olá {name}! Seu plano {timing}. Renove agora para continuar aproveitando nossos serviços! Valor: R$ {value:.2f}"
        }
        
        return fallback_messages.get(category, fallback_messages['OUTROS'])
    
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