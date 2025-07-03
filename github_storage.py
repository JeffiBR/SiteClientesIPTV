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
        self.token = os.getenv('CL_TOKEN')
        self.repo_owner = 'JeffiBR'
        self.repo_name = 'Clientes'
        self.base_url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents'
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Bot-Cliente-Manager/1.0'
        }
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self.rate_limit_remaining = None
        self.rate_limit_reset = None
        self.cache = {}
        self.cache_timeout = 300  # 5 minutes
        self.backup_enabled = True
        self.connection_lock = threading.RLock()
        
        # Validate configuration
        self._validate_configuration()
    
    def _validate_configuration(self):
        """Validate GitHub storage configuration"""
        if not self.token:
            raise GitHubStorageError("GitHub token (CL_TOKEN) not found in environment variables")
        
        if len(self.token) < 20:
            raise GitHubStorageError("Invalid GitHub token format")
        
        # Test connection
        try:
            self._test_connection()
        except Exception as e:
            logger.warning(f"GitHub connection test failed: {str(e)}")
    
    def _test_connection(self):
        """Test GitHub API connection"""
        try:
            url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}'
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("GitHub connection test successful")
                return True
            elif response.status_code == 404:
                raise GitHubStorageError(f"Repository {self.repo_owner}/{self.repo_name} not found")
            elif response.status_code == 401:
                raise GitHubStorageError("Invalid GitHub token or insufficient permissions")
            else:
                raise GitHubStorageError(f"GitHub API error: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            raise GitHubStorageError(f"Network error connecting to GitHub: {str(e)}")
    
    def _check_rate_limit(self, response_headers: Dict):
        """Check and handle GitHub API rate limits"""
        try:
            self.rate_limit_remaining = int(response_headers.get('X-RateLimit-Remaining', 0))
            self.rate_limit_reset = int(response_headers.get('X-RateLimit-Reset', 0))
            
            if self.rate_limit_remaining < 10:
                reset_time = datetime.fromtimestamp(self.rate_limit_reset)
                wait_time = (reset_time - datetime.now()).total_seconds()
                
                if wait_time > 0:
                    logger.warning(f"GitHub rate limit low ({self.rate_limit_remaining}), waiting {wait_time:.1f}s")
                    time.sleep(min(wait_time, 60))  # Max 1 minute wait
                    
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing rate limit headers: {str(e)}")
    
    def _get_cache_key(self, filename: str) -> str:
        """Generate cache key for file"""
        return f"file_{filename}_{int(time.time() // self.cache_timeout)}"
    
    def _get_cached_content(self, filename: str) -> Optional[Dict]:
        """Get file content from cache if valid"""
        try:
            cache_key = self._get_cache_key(filename)
            if cache_key in self.cache:
                cached_data = self.cache[cache_key]
                if time.time() - cached_data['timestamp'] < self.cache_timeout:
                    logger.debug(f"Using cached content for {filename}")
                    return cached_data['data']
            return None
        except Exception as e:
            logger.warning(f"Error accessing cache: {str(e)}")
            return None
    
    def _cache_content(self, filename: str, data: Dict):
        """Cache file content"""
        try:
            cache_key = self._get_cache_key(filename)
            self.cache[cache_key] = {
                'data': data,
                'timestamp': time.time()
            }
            
            # Cleanup old cache entries
            current_time = time.time()
            keys_to_remove = []
            for key, cached_data in self.cache.items():
                if current_time - cached_data['timestamp'] > self.cache_timeout * 2:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.cache[key]
                
        except Exception as e:
            logger.warning(f"Error caching content: {str(e)}")
    
    def _get_file_content(self, filename: str, use_cache: bool = True) -> Optional[Dict]:
        """Get file content from GitHub repository with retry and error handling"""
        
        # Check cache first
        if use_cache:
            cached_content = self._get_cached_content(filename)
            if cached_content:
                return cached_content
        
        with self.connection_lock:
            for attempt in range(self.max_retries):
                try:
                    url = f'{self.base_url}/{filename}'
                    
                    # Add timeout and better error handling
                    response = requests.get(
                        url, 
                        headers=self.headers, 
                        timeout=30,
                        allow_redirects=True
                    )
                    
                    # Check rate limits
                    self._check_rate_limit(response.headers)
                    
                    if response.status_code == 200:
                        file_data = response.json()
                        
                        # Validate response structure
                        if 'content' not in file_data or 'sha' not in file_data:
                            raise GitHubStorageError(f"Invalid response structure for {filename}")
                        
                        try:
                            content = base64.b64decode(file_data['content']).decode('utf-8')
                            parsed_content = json.loads(content)
                            
                            result = {
                                'content': parsed_content,
                                'sha': file_data['sha']
                            }
                            
                            # Cache the result
                            if use_cache:
                                self._cache_content(filename, result)
                            
                            return result
                            
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            logger.error(f"Error decoding content from {filename}: {str(e)}")
                            if attempt == self.max_retries - 1:
                                raise GitHubStorageError(f"Content decode error: {str(e)}")
                            
                    elif response.status_code == 404:
                        logger.debug(f"File {filename} not found (404)")
                        return None
                        
                    elif response.status_code == 403:
                        logger.error(f"GitHub API access forbidden for {filename}: {response.text}")
                        if "rate limit" in response.text.lower():
                            time.sleep(60)  # Wait 1 minute for rate limit
                            continue
                        raise GitHubStorageError(f"Access forbidden: {response.text}")
                        
                    elif response.status_code >= 500:
                        logger.warning(f"GitHub server error {response.status_code} for {filename}, attempt {attempt + 1}")
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
                            continue
                        raise GitHubStorageError(f"Server error: {response.status_code}")
                        
                    else:
                        logger.error(f"Unexpected status code {response.status_code} for {filename}: {response.text}")
                        raise GitHubStorageError(f"API error {response.status_code}: {response.text}")
                        
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout getting {filename}, attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    raise GitHubStorageError(f"Timeout after {self.max_retries} attempts")
                    
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"Connection error getting {filename}, attempt {attempt + 1}: {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    raise GitHubStorageError(f"Connection error: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Unexpected error getting {filename}: {str(e)}")
                    if attempt == self.max_retries - 1:
                        raise GitHubStorageError(f"Unexpected error: {str(e)}")
                    time.sleep(self.retry_delay)
            
            raise GitHubStorageError(f"Failed to get {filename} after {self.max_retries} attempts")
    
    def _save_file_content(self, filename: str, content: Dict, sha: Optional[str] = None, create_backup: bool = True) -> bool:
        """Save file content to GitHub repository with retry and backup"""
        
        # Create backup if enabled and updating existing file
        if create_backup and self.backup_enabled and sha:
            try:
                self._create_backup(filename, content)
            except Exception as e:
                logger.warning(f"Backup creation failed for {filename}: {str(e)}")
        
        with self.connection_lock:
            for attempt in range(self.max_retries):
                try:
                    url = f'{self.base_url}/{filename}'
                    
                    # Validate content before encoding
                    self._validate_content(content, filename)
                    
                    # Encode content as base64
                    content_json = json.dumps(content, indent=2, ensure_ascii=False)
                    content_b64 = base64.b64encode(content_json.encode('utf-8')).decode('utf-8')
                    
                    data = {
                        'message': f'Update {filename} - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                        'content': content_b64
                    }
                    
                    if sha:
                        data['sha'] = sha
                    
                    response = requests.put(
                        url, 
                        json=data, 
                        headers=self.headers, 
                        timeout=30
                    )
                    
                    # Check rate limits
                    self._check_rate_limit(response.headers)
                    
                    if response.status_code in [200, 201]:
                        logger.info(f"Successfully saved {filename}")
                        
                        # Clear cache for this file
                        cache_keys_to_remove = [key for key in self.cache.keys() if filename in key]
                        for key in cache_keys_to_remove:
                            del self.cache[key]
                        
                        return True
                        
                    elif response.status_code == 409:
                        logger.warning(f"Conflict saving {filename}, retrying with fresh SHA")
                        # Get fresh SHA and retry
                        try:
                            fresh_data = self._get_file_content(filename, use_cache=False)
                            if fresh_data:
                                data['sha'] = fresh_data['sha']
                                response = requests.put(url, json=data, headers=self.headers, timeout=30)
                                if response.status_code in [200, 201]:
                                    return True
                        except Exception as e:
                            logger.error(f"Error retrying with fresh SHA: {str(e)}")
                        
                    elif response.status_code == 403:
                        if "rate limit" in response.text.lower():
                            logger.warning("Rate limit hit while saving, waiting...")
                            time.sleep(60)
                            continue
                        raise GitHubStorageError(f"Access forbidden: {response.text}")
                        
                    elif response.status_code >= 500:
                        logger.warning(f"Server error {response.status_code} saving {filename}, attempt {attempt + 1}")
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        
                    logger.error(f"Error saving {filename}: {response.status_code} - {response.text}")
                    if attempt == self.max_retries - 1:
                        raise GitHubStorageError(f"Save failed: {response.status_code} - {response.text}")
                    
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout saving {filename}, attempt {attempt + 1}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                    
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"Connection error saving {filename}, attempt {attempt + 1}: {str(e)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (2 ** attempt))
                        continue
                        
                except Exception as e:
                    logger.error(f"Unexpected error saving {filename}: {str(e)}")
                    logger.error(traceback.format_exc())
                    if attempt == self.max_retries - 1:
                        raise GitHubStorageError(f"Unexpected save error: {str(e)}")
                    time.sleep(self.retry_delay)
            
            return False
    
    def _validate_content(self, content: Dict, filename: str):
        """Validate content before saving"""
        try:
            # Basic validation
            if not isinstance(content, dict):
                raise ValueError("Content must be a dictionary")
            
            # File-specific validation
            if filename == 'clients.json':
                if 'clients' not in content:
                    raise ValueError("clients.json must contain 'clients' key")
                
                if not isinstance(content['clients'], list):
                    raise ValueError("clients must be a list")
                
                # Validate each client
                for i, client_data in enumerate(content['clients']):
                    try:
                        # Test if client can be created from data
                        Client.from_dict(client_data)
                    except Exception as e:
                        raise ValueError(f"Invalid client data at index {i}: {str(e)}")
            
            elif filename == 'message_templates.json':
                if 'templates' not in content:
                    raise ValueError("message_templates.json must contain 'templates' key")
                
                if not isinstance(content['templates'], list):
                    raise ValueError("templates must be a list")
            
            # Check content size (GitHub has a 100MB limit, but we'll be more conservative)
            content_json = json.dumps(content)
            if len(content_json.encode('utf-8')) > 10 * 1024 * 1024:  # 10MB limit
                raise ValueError("Content too large (>10MB)")
                
        except Exception as e:
            raise GitHubStorageError(f"Content validation failed for {filename}: {str(e)}")
    
    def _create_backup(self, filename: str, content: Dict):
        """Create backup of file before updating"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backups/{filename.replace('.json', '')}_{timestamp}.json"
            
            # Save backup (without creating another backup)
            self._save_file_content(backup_filename, content, sha=None, create_backup=False)
            logger.info(f"Backup created: {backup_filename}")
            
        except Exception as e:
            logger.error(f"Failed to create backup for {filename}: {str(e)}")
            # Don't raise exception - backup failure shouldn't stop the main operation
    
    def get_clients(self) -> List[Client]:
        """Get all clients from GitHub storage with error handling"""
        try:
            file_data = self._get_file_content('clients.json')
            
            if not file_data:
                logger.info("No clients.json found, returning empty list")
                return []
            
            clients = []
            client_data_list = file_data['content'].get('clients', [])
            
            for i, client_data in enumerate(client_data_list):
                try:
                    client = Client.from_dict(client_data)
                    clients.append(client)
                except Exception as e:
                    logger.error(f"Error loading client at index {i}: {str(e)}")
                    logger.error(f"Client data: {client_data}")
                    # Continue loading other clients even if one fails
                    continue
            
            logger.info(f"Loaded {len(clients)} clients from GitHub")
            return clients
            
        except GitHubStorageError as e:
            logger.error(f"GitHub storage error loading clients: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading clients: {str(e)}")
            logger.error(traceback.format_exc())
            raise GitHubStorageError(f"Failed to load clients: {str(e)}")
    
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
            sha = file_data['sha'] if file_data else None
            
            content = {
                'clients': [client.to_dict() for client in clients],
                'last_updated': datetime.now().isoformat(),
                'total_count': len(clients)
            }
            
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
                templates = []
                for template_data in DEFAULT_TEMPLATES:
                    templates.append(MessageTemplate.from_dict(template_data))
                return templates
            
            templates = []
            template_data_list = file_data['content'].get('templates', [])
            
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
                for template_data in DEFAULT_TEMPLATES:
                    templates.append(MessageTemplate.from_dict(template_data))
            
            return templates
            
        except Exception as e:
            logger.error(f"Error loading message templates: {str(e)}")
            # Return default templates on error
            templates = []
            for template_data in DEFAULT_TEMPLATES:
                templates.append(MessageTemplate.from_dict(template_data))
            return templates
    
    def save_message_templates(self, templates: List[MessageTemplate]) -> bool:
        """Save message templates to GitHub storage"""
        try:
            # Get current file SHA
            file_data = self._get_file_content('message_templates.json')
            sha = file_data['sha'] if file_data else None
            
            content = {
                'templates': [template.to_dict() for template in templates],
                'last_updated': datetime.now().isoformat()
            }
            
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
                'rate_limit_remaining': self.rate_limit_remaining,
                'rate_limit_reset': self.rate_limit_reset,
                'cache_size': len(self.cache),
                'clients_count': 0,
                'templates_count': 0,
                'last_error': None,
                'backup_enabled': self.backup_enabled
            }
            
            # Test connection
            try:
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
        """Clear the storage cache"""
        try:
            self.cache.clear()
            logger.info("Storage cache cleared")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
    
    def set_backup_enabled(self, enabled: bool):
        """Enable or disable backups"""
        self.backup_enabled = enabled
        logger.info(f"Backup {'enabled' if enabled else 'disabled'}")

# Global storage instance
storage = GitHubStorage()
