import os
import json
import requests
import base64
import time
import threading
from typing import List, Dict, Optional
from models import Client, MessageTemplate, DEFAULT_TEMPLATES
import logging
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class GitHubStorageError(Exception):
    """Custom exception for GitHub storage errors"""
    pass

class GitHubStorage:
    def __init__(self):
        self.token = os.environ.get('CL_TOKEN')
        self.username = os.environ.get('CL_USERNAME', 'default_user')
        self.repo_name = os.environ.get('CL_REPO', 'client-manager-data')
        self.branch = os.environ.get('CL_BRANCH', 'main')
        self.base_url = f"https://api.github.com/repos/{self.username}/{self.repo_name}/contents"
        
        # Modo de desenvolvimento - funciona offline sem GitHub válido
        self.dev_mode = os.environ.get('CL_DEV_MODE', 'true').lower() == 'true'
        self.local_storage_path = os.path.join(os.getcwd(), 'local_data')
        
        if self.dev_mode:
            logger.info("Running in development mode - using local storage")
            self._ensure_local_storage()
        else:
            # Só valida configuração se não estiver em modo dev
            self._validate_configuration()
    
    def _ensure_local_storage(self):
        """Criar diretório de armazenamento local para modo dev"""
        try:
            os.makedirs(self.local_storage_path, exist_ok=True)
            
            # Criar arquivos iniciais se não existirem
            default_files = {
                'clients.json': [],
                'message_templates.json': [
                    {
                        "id": "1",
                        "name": "Lembrete 3 dias",
                        "content": "Olá {name}! Seu plano vence em 3 dias. Renovar agora: R$ {value}",
                        "type": "reminder_3days"
                    },
                    {
                        "id": "2", 
                        "name": "Cobrança",
                        "content": "Olá {name}! Seu plano VPN venceu. Renove agora por apenas R$ {value}",
                        "type": "payment_due"
                    }
                ],
                'whatsapp_status.json': {
                    'status': 'disconnected',
                    'error': None,
                    'session_id': None,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
            for filename, content in default_files.items():
                filepath = os.path.join(self.local_storage_path, filename)
                if not os.path.exists(filepath):
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(content, f, indent=2, ensure_ascii=False)
                    logger.info(f"Created local file: {filename}")
                    
        except Exception as e:
            logger.error(f"Error setting up local storage: {str(e)}")

    def _validate_configuration(self):
        """Validate GitHub configuration"""
        if not self.token:
            raise GitHubStorageError("GitHub token (CL_TOKEN) not found in environment variables")
        
        if len(self.token) < 10:  # Basic token validation
            raise GitHubStorageError("GitHub token appears to be invalid (too short)")
        
        # Test connection
        self._test_connection()

    def _test_connection(self):
        """Test GitHub API connection"""
        try:
            if self.dev_mode:
                logger.info("Skipping GitHub connection test in dev mode")
                return True
                
            test_url = f"https://api.github.com/repos/{self.username}/{self.repo_name}"
            headers = {
                'Authorization': f'token {self.token}',
                'User-Agent': 'Client-Manager-Bot/1.0'
            }
            
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("GitHub connection test successful")
                return True
            elif response.status_code == 401:
                logger.warning("GitHub connection test failed: Invalid GitHub token or insufficient permissions")
                # Em modo dev, continua funcionando mesmo com token inválido
                if self.dev_mode:
                    return True
                else:
                    raise GitHubStorageError("Invalid GitHub token or insufficient permissions")
            else:
                logger.warning(f"GitHub connection test failed with status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            if self.dev_mode:
                logger.warning(f"GitHub connection failed, continuing in dev mode: {str(e)}")
                return True
            else:
                logger.error(f"GitHub connection test failed: {str(e)}")
                raise GitHubStorageError(f"GitHub connection test failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}")
            if self.dev_mode:
                return True
            else:
                raise GitHubStorageError(f"Unexpected connection test error: {str(e)}")

    def _get_file_content(self, filename: str) -> Optional[Dict]:
        """Get file content from GitHub or local storage"""
        try:
            if self.dev_mode:
                return self._get_local_file_content(filename)
            else:
                return self._get_github_file_content(filename)
        except Exception as e:
            logger.error(f"Error getting file content for {filename}: {str(e)}")
            if self.dev_mode:
                # Em modo dev, sempre usar local storage
                logger.info(f"Using local storage for {filename} in dev mode")
                return self._get_local_file_content(filename)
            else:
                raise GitHubStorageError(f"Unexpected error: {str(e)}")
    
    def _get_local_file_content(self, filename: str) -> Optional[Dict]:
        """Get file content from local storage"""
        try:
            filepath = os.path.join(self.local_storage_path, filename)
            
            if not os.path.exists(filepath):
                logger.debug(f"Local file not found: {filename}")
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            return {
                'content': content,
                'sha': 'local_' + str(hash(json.dumps(content, sort_keys=True))),
                'name': filename
            }
            
        except Exception as e:
            logger.error(f"Error reading local file {filename}: {str(e)}")
            return None
    
    def _get_github_file_content(self, filename: str) -> Optional[Dict]:
        """Get file content from GitHub"""
        try:
            url = f"{self.base_url}/{filename}"
            headers = {
                'Authorization': f'token {self.token}',
                'User-Agent': 'Client-Manager-Bot/1.0',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Decode base64 content
                        content_b64 = data.get('content', '')
                        content_bytes = base64.b64decode(content_b64)
                        content_str = content_bytes.decode('utf-8')
                        content_json = json.loads(content_str)
                        
                        return {
                            'content': content_json,
                            'sha': data.get('sha'),
                            'name': data.get('name'),
                            'size': data.get('size')
                        }
                    elif response.status_code == 404:
                        logger.debug(f"File not found in GitHub: {filename}")
                        return None
                    elif response.status_code == 401:
                        logger.error(f"Unauthorized access to {filename} - check GitHub token")
                        if self.dev_mode:
                            logger.info(f"GitHub auth failed in dev mode, falling back to local storage for {filename}")
                            return None  # Let the calling method handle fallback
                        else:
                            raise GitHubStorageError(f"Unauthorized access to {filename}")
                    else:
                        logger.error(f"Unexpected status code {response.status_code} for {filename}: {response.text}")
                        if self.dev_mode:
                            logger.info(f"GitHub API error in dev mode, falling back to local storage for {filename}")
                            return None
                        else:
                            raise GitHubStorageError(f"API error {response.status_code}: {response.text}")
                        
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout on attempt {attempt + 1} for {filename}")
                    if attempt == max_retries - 1:
                        raise GitHubStorageError(f"Timeout after {max_retries} attempts")
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error on attempt {attempt + 1} for {filename}: {str(e)}")
                    if attempt == max_retries - 1:
                        raise GitHubStorageError(f"Request error after {max_retries} attempts: {str(e)}")
                    time.sleep(2 ** attempt)
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {filename}: {str(e)}")
            raise GitHubStorageError(f"Invalid JSON in {filename}: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error getting {filename}: {str(e)}")
            raise GitHubStorageError(f"Unexpected error: {str(e)}")
    
    def _save_file_content(self, filename: str, content: Dict, sha: Optional[str] = None) -> bool:
        """Save file content to GitHub or local storage"""
        try:
            if self.dev_mode:
                return self._save_local_file_content(filename, content)
            else:
                return self._save_github_file_content(filename, content, sha)
        except Exception as e:
            logger.error(f"Error saving file {filename}: {str(e)}")
            if self.dev_mode:
                # Em modo dev, sempre usar local storage
                logger.info(f"Using local storage to save {filename} in dev mode")
                return self._save_local_file_content(filename, content)
            else:
                return False
    
    def _save_local_file_content(self, filename: str, content: Dict) -> bool:
        """Save file content to local storage"""
        try:
            filepath = os.path.join(self.local_storage_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False, default=str)
            
            logger.debug(f"Saved local file: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving local file {filename}: {str(e)}")
            return False
    
    def _save_github_file_content(self, filename: str, content: Dict, sha: Optional[str] = None) -> bool:
        """Save file content to GitHub"""
        try:
            url = f"{self.base_url}/{filename}"
            headers = {
                'Authorization': f'token {self.token}',
                'User-Agent': 'Client-Manager-Bot/1.0',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Convert content to JSON string and then to base64
            content_str = json.dumps(content, indent=2, ensure_ascii=False, default=str)
            content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
            
            data = {
                'message': f'Update {filename} via Client Manager',
                'content': content_b64,
                'branch': self.branch
            }
            
            if sha:
                data['sha'] = sha
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.put(url, headers=headers, json=data, timeout=30)
                    
                    if response.status_code in [200, 201]:
                        logger.info(f"Successfully saved {filename} to GitHub")
                        return True
                    elif response.status_code == 409:
                        logger.warning(f"Conflict saving {filename}, trying to get latest SHA")
                        # Get latest SHA and retry
                        file_data = self._get_github_file_content(filename)
                        if file_data:
                            data['sha'] = file_data['sha']
                            continue
                        else:
                            logger.error(f"Could not get latest SHA for {filename}")
                            return False
                    else:
                        logger.error(f"Failed to save {filename}: {response.status_code} - {response.text}")
                        return False
                        
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout on save attempt {attempt + 1} for {filename}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(2 ** attempt)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error on save attempt {attempt + 1} for {filename}: {str(e)}")
                    if attempt == max_retries - 1:
                        return False
                    time.sleep(2 ** attempt)
            
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error saving {filename}: {str(e)}")
            return False
    
    def get_clients(self) -> List[Client]:
        """Get all clients from GitHub storage with error handling"""
        try:
            file_data = self._get_file_content('clients.json')
            
            if not file_data:
                logger.info("No clients.json found, returning empty list")
                return []
            
            content = file_data.get('content', [])
            
            # Handle both old format (with 'clients' key) and new format (direct list)
            if isinstance(content, dict) and 'clients' in content:
                client_data_list = content['clients']
            elif isinstance(content, list):
                client_data_list = content
            else:
                logger.warning("Invalid clients file format, returning empty list")
                return []
            
            clients = []
            for i, client_data in enumerate(client_data_list):
                try:
                    client = Client.from_dict(client_data)
                    clients.append(client)
                except Exception as e:
                    logger.error(f"Error loading client at index {i}: {str(e)}")
                    logger.error(f"Client data: {client_data}")
                    # Continue loading other clients even if one fails
                    continue
            
            logger.info(f"Loaded {len(clients)} clients from storage")
            return clients
            
        except GitHubStorageError as e:
            logger.error(f"GitHub storage error loading clients: {str(e)}")
            return []  # Return empty list instead of raising in dev mode
        except Exception as e:
            logger.error(f"Unexpected error loading clients: {str(e)}")
            logger.error(traceback.format_exc())
            return []  # Return empty list instead of raising in dev mode
    
    def save_clients(self, clients: List[Client]) -> bool:
        """Save clients to GitHub storage with validation"""
        try:
            # Validate all clients before saving
            for i, client in enumerate(clients):
                if not isinstance(client, Client):
                    raise ValueError(f"Item at index {i} is not a Client instance")
                
                # Validate required fields
                if not client.id or not client.name or not client.phone:
                    raise ValueError(f"Client at index {i} missing required fields")
            
            # Get current file SHA
            file_data = self._get_file_content('clients.json')
            sha = file_data.get('sha') if file_data else None
            
            # Save as simple list for easier handling
            content = [client.to_dict() for client in clients]
            
            success = self._save_file_content('clients.json', content, sha)
            
            if success:
                logger.info(f"Successfully saved {len(clients)} clients")
            else:
                logger.error("Failed to save clients")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving clients: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    def get_message_templates(self) -> List[MessageTemplate]:
        """Get message templates from GitHub storage with fallback to defaults"""
        try:
            file_data = self._get_file_content('message_templates.json')
            
            if not file_data:
                logger.info("No message_templates.json found, returning default templates")
                return self._get_default_templates()
            
            content = file_data.get('content', [])
            
            # Handle both old format (with 'templates' key) and new format (direct list)
            if isinstance(content, dict) and 'templates' in content:
                template_data_list = content['templates']
            elif isinstance(content, list):
                template_data_list = content
            else:
                logger.warning("Invalid templates file format, returning defaults")
                return self._get_default_templates()
            
            templates = []
            for i, template_data in enumerate(template_data_list):
                try:
                    template = MessageTemplate.from_dict(template_data)
                    templates.append(template)
                except Exception as e:
                    logger.error(f"Error loading template at index {i}: {str(e)}")
                    continue
            
            # If no templates loaded, return defaults
            if not templates:
                logger.warning("No valid templates found, returning defaults")
                return self._get_default_templates()
            
            return templates
            
        except Exception as e:
            logger.error(f"Error loading message templates: {str(e)}")
            # Return default templates on error
            return self._get_default_templates()
    
    def _get_default_templates(self) -> List[MessageTemplate]:
        """Get default message templates"""
        default_templates_data = [
            {
                "id": "1",
                "name": "Lembrete 3 dias",
                "content": "Olá {name}! Seu plano vence em 3 dias. Renovar agora: R$ {value}",
                "type": "reminder_3days"
            },
            {
                "id": "2", 
                "name": "Cobrança",
                "content": "Olá {name}! Seu plano VPN venceu. Renove agora por apenas R$ {value}",
                "type": "payment_due"
            }
        ]
        
        templates = []
        for template_data in default_templates_data:
            try:
                templates.append(MessageTemplate.from_dict(template_data))
            except Exception as e:
                logger.error(f"Error creating default template: {str(e)}")
                
        return templates
    
    def save_message_templates(self, templates: List[MessageTemplate]) -> bool:
        """Save message templates to GitHub storage"""
        try:
            # Get current file SHA
            file_data = self._get_file_content('message_templates.json')
            sha = file_data.get('sha') if file_data else None
            
            # Save as simple list for easier handling
            content = [template.to_dict() for template in templates]
            
            return self._save_file_content('message_templates.json', content, sha)
            
        except Exception as e:
            logger.error(f"Error saving message templates: {str(e)}")
            return False
    
    def add_client(self, client: Client) -> bool:
        """Add a new client with validation"""
        try:
            if not isinstance(client, Client):
                raise ValueError("Must provide a Client instance")
            
            clients = self.get_clients()
            
            # Check for duplicate IDs
            existing_ids = {c.id for c in clients}
            if client.id in existing_ids:
                raise ValueError(f"Client with ID {client.id} already exists")
            
            # Check for duplicate phone numbers
            existing_phones = {c.phone for c in clients}
            if client.phone in existing_phones:
                logger.warning(f"Client with phone {client.phone} already exists")
            
            clients.append(client)
            success = self.save_clients(clients)
            
            if success:
                logger.info(f"Added client: {client.name} ({client.id})")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding client: {str(e)}")
            return False
    
    def update_client(self, client: Client) -> bool:
        """Update an existing client with validation"""
        try:
            if not isinstance(client, Client):
                raise ValueError("Must provide a Client instance")
            
            clients = self.get_clients()
            
            for i, existing_client in enumerate(clients):
                if existing_client.id == client.id:
                    clients[i] = client
                    success = self.save_clients(clients)
                    
                    if success:
                        logger.info(f"Updated client: {client.name} ({client.id})")
                    
                    return success
            
            logger.error(f"Client not found for update: {client.id}")
            return False
            
        except Exception as e:
            logger.error(f"Error updating client: {str(e)}")
            return False
    
    def delete_client(self, client_id: str) -> bool:
        """Delete a client with validation"""
        try:
            if not client_id:
                raise ValueError("Client ID is required")
            
            clients = self.get_clients()
            original_count = len(clients)
            
            clients = [c for c in clients if c.id != client_id]
            
            if len(clients) == original_count:
                logger.warning(f"Client not found for deletion: {client_id}")
                return False
            
            success = self.save_clients(clients)
            
            if success:
                logger.info(f"Deleted client: {client_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting client: {str(e)}")
            return False
    
    def get_client_by_id(self, client_id: str) -> Optional[Client]:
        """Get a specific client by ID with caching"""
        try:
            if not client_id:
                return None
            
            clients = self.get_clients()
            
            for client in clients:
                if client.id == client_id:
                    return client
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting client by ID {client_id}: {str(e)}")
            return None
    
    def get_storage_stats(self) -> Dict:
        """Get storage statistics and health info"""
        try:
            stats = {
                'connection_status': 'unknown',
                'dev_mode': self.dev_mode,
                'storage_type': 'local' if self.dev_mode else 'github',
                'clients_count': 0,
                'templates_count': 0,
                'last_error': None
            }
            
            # Test connection
            try:
                if self.dev_mode:
                    stats['connection_status'] = 'local_storage'
                else:
                    self._test_connection()
                    stats['connection_status'] = 'connected'
            except Exception as e:
                stats['connection_status'] = 'error'
                stats['last_error'] = str(e)
            
            # Get counts
            try:
                clients = self.get_clients()
                stats['clients_count'] = len(clients)
            except Exception as e:
                stats['last_error'] = f"Error loading clients: {str(e)}"
            
            try:
                templates = self.get_message_templates()
                stats['templates_count'] = len(templates)
            except Exception as e:
                stats['last_error'] = f"Error loading templates: {str(e)}"
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting storage stats: {str(e)}")
            return {
                'connection_status': 'error',
                'last_error': str(e)
            }
    
    def clear_cache(self):
        """Clear any cache - placeholder for future implementation"""
        logger.info("Cache clear requested - no cache to clear in current implementation")
    
    def get_dev_mode(self) -> bool:
        """Check if running in development mode"""
        return self.dev_mode

# Global storage instance
storage = GitHubStorage()
