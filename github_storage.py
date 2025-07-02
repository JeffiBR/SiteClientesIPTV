import os
import json
import requests
import base64
from typing import List, Dict, Optional
from models import Client, MessageTemplate, DEFAULT_TEMPLATES
import logging

logger = logging.getLogger(__name__)

class GitHubStorage:
    def __init__(self):
        self.token = os.getenv('CL_TOKEN')
        self.repo_owner = 'JeffiBR'
        self.repo_name = 'Clientes'
        self.base_url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents'
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def _get_file_content(self, filename: str) -> Optional[Dict]:
        """Get file content from GitHub repository"""
        try:
            url = f'{self.base_url}/{filename}'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                file_data = response.json()
                content = base64.b64decode(file_data['content']).decode('utf-8')
                return {
                    'content': json.loads(content),
                    'sha': file_data['sha']
                }
            elif response.status_code == 404:
                return None
            else:
                logger.error(f"Error getting file {filename}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Exception getting file {filename}: {str(e)}")
            return None
    
    def _save_file_content(self, filename: str, content: Dict, sha: Optional[str] = None) -> bool:
        """Save file content to GitHub repository"""
        try:
            url = f'{self.base_url}/{filename}'
            
            # Encode content as base64
            content_json = json.dumps(content, indent=2, ensure_ascii=False)
            content_b64 = base64.b64encode(content_json.encode('utf-8')).decode('utf-8')
            
            data = {
                'message': f'Update {filename}',
                'content': content_b64
            }
            
            if sha:
                data['sha'] = sha
            
            response = requests.put(url, json=data, headers=self.headers)
            
            if response.status_code in [200, 201]:
                return True
            else:
                logger.error(f"Error saving file {filename}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Exception saving file {filename}: {str(e)}")
            return False
    
    def get_clients(self) -> List[Client]:
        """Get all clients from GitHub storage"""
        file_data = self._get_file_content('clients.json')
        
        if not file_data:
            return []
        
        clients = []
        for client_data in file_data['content'].get('clients', []):
            clients.append(Client.from_dict(client_data))
        
        return clients
    
    def save_clients(self, clients: List[Client]) -> bool:
        """Save clients to GitHub storage"""
        # Get current file SHA
        file_data = self._get_file_content('clients.json')
        sha = file_data['sha'] if file_data else None
        
        content = {
            'clients': [client.to_dict() for client in clients]
        }
        
        return self._save_file_content('clients.json', content, sha)
    
    def get_message_templates(self) -> List[MessageTemplate]:
        """Get message templates from GitHub storage"""
        file_data = self._get_file_content('message_templates.json')
        
        if not file_data:
            # Return default templates if file doesn't exist
            templates = []
            for template_data in DEFAULT_TEMPLATES:
                templates.append(MessageTemplate.from_dict(template_data))
            return templates
        
        templates = []
        for template_data in file_data['content'].get('templates', []):
            templates.append(MessageTemplate.from_dict(template_data))
        
        return templates
    
    def save_message_templates(self, templates: List[MessageTemplate]) -> bool:
        """Save message templates to GitHub storage"""
        # Get current file SHA
        file_data = self._get_file_content('message_templates.json')
        sha = file_data['sha'] if file_data else None
        
        content = {
            'templates': [template.to_dict() for template in templates]
        }
        
        return self._save_file_content('message_templates.json', content, sha)
    
    def add_client(self, client: Client) -> bool:
        """Add a new client"""
        clients = self.get_clients()
        clients.append(client)
        return self.save_clients(clients)
    
    def update_client(self, client: Client) -> bool:
        """Update an existing client"""
        clients = self.get_clients()
        
        for i, existing_client in enumerate(clients):
            if existing_client.id == client.id:
                clients[i] = client
                return self.save_clients(clients)
        
        return False
    
    def delete_client(self, client_id: str) -> bool:
        """Delete a client"""
        clients = self.get_clients()
        
        for i, client in enumerate(clients):
            if client.id == client_id:
                del clients[i]
                return self.save_clients(clients)
        
        return False
    
    def get_client_by_id(self, client_id: str) -> Optional[Client]:
        """Get a specific client by ID"""
        clients = self.get_clients()
        
        for client in clients:
            if client.id == client_id:
                return client
        
        return None

# Global storage instance
storage = GitHubStorage()
