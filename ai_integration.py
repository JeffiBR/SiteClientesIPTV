import os
import requests
import json
import logging
from typing import Dict, Optional
from models import Client

logger = logging.getLogger(__name__)

class AIMessageGenerator:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY', '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')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "qwen/qwen-2.5-72b-instruct:free"
        
    def generate_reminder_message(self, client: Client, reminder_type: str) -> str:
        """Gera uma mensagem personalizada usando IA para o cliente"""
        try:
            if not self.api_key:
                logger.warning("OPENROUTER_API_KEY não encontrada. Usando mensagem padrão.")
                return self._get_default_message(client, reminder_type)
            
            # Contexto do cliente
            context = self._build_client_context(client, reminder_type)
            
            # Prompt para a IA
            prompt = self._build_prompt(client, reminder_type, context)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Você é um assistente especializado em criar mensagens de cobrança amigáveis e profissionais para clientes de IPTV e VPN. Seja cordial, direto e inclua informações específicas do cliente."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.7
            }
            
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                message = data['choices'][0]['message']['content'].strip()
                logger.info(f"Mensagem IA gerada para {client.name}")
                return message
            else:
                logger.error(f"Erro na API OpenRouter: {response.status_code} - {response.text}")
                return self._get_default_message(client, reminder_type)
                
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem com IA: {str(e)}")
            return self._get_default_message(client, reminder_type)
    
    def _build_client_context(self, client: Client, reminder_type: str) -> Dict:
        """Constrói o contexto do cliente para a IA"""
        return {
            "nome": client.name,
            "plano": client.plan_type,
            "valor": client.value,
            "data_vencimento": client.plan_duration,
            "dias_restantes": client.days_until_expiration,
            "status": client.status,
            "tipo_lembrete": reminder_type
        }
    
    def _build_prompt(self, client: Client, reminder_type: str, context: Dict) -> str:
        """Constrói o prompt para a IA"""
        if reminder_type == "3days":
            return f"""
Crie uma mensagem de lembrete amigável para um cliente de {context['plano']} que tem 3 dias para renovar.

Informações do cliente:
- Nome: {context['nome']}
- Plano: {context['plano']}
- Valor: R$ {context['valor']:.2f}
- Vencimento: {context['data_vencimento']}
- Status: {context['status']}

A mensagem deve:
- Ser cordial e profissional
- Lembrar sobre o vencimento em 3 dias
- Incluir o valor e tipo do plano
- Ter um tom amigável mas urgente
- Ser concisa (máximo 150 caracteres)
- Não incluir emojis

Gere apenas a mensagem, sem aspas ou formatação extra.
"""
        else:  # payment day
            return f"""
Crie uma mensagem de cobrança para um cliente cujo plano vence HOJE.

Informações do cliente:
- Nome: {context['nome']}
- Plano: {context['plano']}
- Valor: R$ {context['valor']:.2f}
- Vencimento: HOJE ({context['data_vencimento']})

A mensagem deve:
- Ser educada mas firme
- Informar que o plano vence hoje
- Incluir valor e instruções para renovação
- Ser profissional
- Ser concisa (máximo 150 caracteres)
- Não incluir emojis

Gere apenas a mensagem, sem aspas ou formatação extra.
"""
    
    def _get_default_message(self, client: Client, reminder_type: str) -> str:
        """Retorna mensagens padrão caso a IA não esteja disponível"""
        if reminder_type == "3days":
            return f"Olá {client.name}! Seu plano {client.plan_type} no valor de R$ {client.value:.2f} vence em 3 dias ({client.plan_duration}). Não esqueça de renovar para manter seu serviço ativo!"
        else:
            return f"Olá {client.name}! Hoje é o dia do vencimento do seu plano {client.plan_type} no valor de R$ {client.value:.2f}. Por favor, realize o pagamento para manter o serviço ativo."

# Instância global
ai_generator = AIMessageGenerator()