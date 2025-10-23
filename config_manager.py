import json
import os
import sys
from pathlib import Path
import shutil
from datetime import datetime
from typing import Dict, Any
import traceback

class ConfigManager:
    def __init__(self):
        # Определяем корневую директорию в зависимости от того, запущено ли приложение как .exe или как .py
        if getattr(sys, 'frozen', False):
            # Если приложение запущено как .exe
            self.program_dir = Path(os.path.dirname(sys.executable))
        else:
            # Если приложение запущено как .py
            self.program_dir = Path(os.path.dirname(os.path.abspath(__file__)))
          # Настраиваем пути к конфигурационным файлам
        self.config_file = self.program_dir / 'config.json'
        self.twitch_file = self.program_dir / 'twitch_config.json'
        self.commands_file = self.program_dir / 'commands.json'
        self.moderators_file = self.program_dir / 'moderators.json'  # Отдельный файл для модераторов
        self.backup_dir = self.program_dir / 'backups'
        
        # Default configuration
        self.default_config = {
            'format_version': '2.0',
            'current_file': None,
            'volume': 0.5,
            'twitch': {
                'channel': ''  # Без токенов в основной конфигурации
            },
            'auto_save': {
                'enabled': True,
                'interval': 300  # 5 minutes
            },
            'recent_files': [],
            'sound': {
                'volume': 1.0,
                'sound_dir': ''
            },
            'commands': {}
        }
          # Default Twitch configuration
        self.default_twitch = {
            'access_token': '',
            'client_id': '',
            'refresh_token': ''
        }
          # Default moderators configuration
        self.default_moderators = {
            'manual_moderators': [],
            'excluded_moderators': [],
            'notes': 'Этот файл содержит список ручных модераторов и исключенных модераторов. Безопасен для показа на стриме'
        }
          # Load or create config
        self.config = self.load_config()
        
        # Load Twitch config (отдельный вызов)
        self.twitch_config = self.load_twitch_config()
        
        # Load moderators config (отдельный вызов)
        self.moderators_config = self.load_moderators_config()
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # Merge with default config to ensure all keys exist
                    config = {**self.default_config, **loaded_config}
                    
                    # Make sure twitch config structure is preserved with nested values
                    if 'twitch' in loaded_config:
                        config['twitch'] = {**self.default_config['twitch'], **loaded_config['twitch']}
                        
                return config
            except json.JSONDecodeError:
                config = self.default_config.copy()
                self.save_config(config)
                return config
        else:
            config = self.default_config.copy()
            self.save_config(config)
            return config
            
    def load_twitch_config(self) -> Dict[str, str]:
        """Load Twitch configuration from separate file"""
        if self.twitch_file.exists():
            try:
                with open(self.twitch_file, 'r', encoding='utf-8') as f:
                    loaded_twitch = json.load(f)
                    # Merge with default twitch config
                    twitch_config = {**self.default_twitch, **loaded_twitch}
                return twitch_config
            except json.JSONDecodeError:
                twitch_config = self.default_twitch.copy()
                self.save_twitch_config_file(twitch_config)
                return twitch_config
        else:
            # Move existing twitch token if present in main config
            if self.config.get('twitch', {}).get('access_token'):
                twitch_config = {
                    'access_token': self.config['twitch'].get('access_token', ''),
                    'client_id': self.config['twitch'].get('client_id', ''),
                    'refresh_token': self.config['twitch'].get('refresh_token', '')
                }
                # Удаляем токены из основного конфига
                if 'access_token' in self.config.get('twitch', {}):
                    del self.config['twitch']['access_token']
                if 'client_id' in self.config.get('twitch', {}):
                    del self.config['twitch']['client_id']
                if 'refresh_token' in self.config.get('twitch', {}):
                    del self.config['twitch']['refresh_token']
                self.save_config(self.config)
            else:
                twitch_config = self.default_twitch.copy()
                
            self.save_twitch_config_file(twitch_config)
            return twitch_config
        
    def load_moderators_config(self) -> Dict[str, Any]:
        """Load moderators configuration from separate file"""
        if self.moderators_file.exists():
            try:
                with open(self.moderators_file, 'r', encoding='utf-8') as f:
                    loaded_moderators = json.load(f)
                    # Merge with default moderators config
                    moderators_config = {**self.default_moderators, **loaded_moderators}
                return moderators_config
            except json.JSONDecodeError:
                moderators_config = self.default_moderators.copy()
                self.save_moderators_config_file(moderators_config)
                return moderators_config
        else:
            # Migrate existing manual_moderators from twitch_config if present
            existing_manual_mods = self.twitch_config.get('manual_moderators', [])
            moderators_config = self.default_moderators.copy()
            if existing_manual_mods:
                moderators_config['manual_moderators'] = existing_manual_mods
                # Remove from twitch_config
                if 'manual_moderators' in self.twitch_config:
                    del self.twitch_config['manual_moderators']
                    self.save_twitch_config_file()
            
            self.save_moderators_config_file(moderators_config)
            return moderators_config
    
    def save_config(self, config=None):
        """Save configuration to file"""
        try:
            if config is not None:
                # Вместо полной замены конфигурации, обновляем только переданные поля
                for key, value in config.items():
                    if key in self.config:
                        if isinstance(value, dict) and isinstance(self.config[key], dict):
                            # Для вложенных словарей делаем рекурсивное обновление
                            self._update_nested_dict(self.config[key], value)
                        else:
                            self.config[key] = value
                    else:
                        self.config[key] = value
            
            # Create backup before saving
            self._create_backup()
            
            # Debug print for stack trace
            stack_trace = traceback.extract_stack()
            caller = stack_trace[-2]  # Предпоследний элемент - это вызывающий метод
            print(f"Saving config from {caller.name} at {caller.filename}:{caller.lineno}")
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Save the config - УБЕДИМСЯ, что токены Twitch не сохраняются в основной файл
            config_to_save = self.config.copy()
            if 'twitch' in config_to_save:
                config_to_save['twitch'] = {k: v for k, v in config_to_save['twitch'].items() 
                                         if k not in ('access_token', 'client_id', 'refresh_token')}
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4)
                
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def save_twitch_config_file(self, twitch_config=None):
        """Save Twitch configuration to separate file"""
        try:
            if twitch_config is not None:
                # Update only provided fields
                for key, value in twitch_config.items():
                    self.twitch_config[key] = value
            
            # Debug print
            stack_trace = traceback.extract_stack()
            caller = stack_trace[-2]
            print(f"Saving twitch config from {caller.name} at {caller.filename}:{caller.lineno}. Token present: {'Yes' if self.twitch_config.get('access_token') else 'No'}")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.twitch_file), exist_ok=True)
            
            # Save to separate file
            with open(self.twitch_file, 'w', encoding='utf-8') as f:
                json.dump(self.twitch_config, f, indent=4)
                
            return True
        except Exception as e:
            print(f"Error saving twitch config: {e}")
            return False
    
    def save_moderators_config_file(self, moderators_config=None):
        """Save moderators configuration to separate file"""
        try:
            if moderators_config is not None:
                # Update only provided fields
                for key, value in moderators_config.items():
                    self.moderators_config[key] = value
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.moderators_file), exist_ok=True)
            
            # Save to separate file
            with open(self.moderators_file, 'w', encoding='utf-8') as f:
                json.dump(self.moderators_config, f, indent=4, ensure_ascii=False)
                
            return True
        except Exception as e:
            print(f"Error saving moderators config: {e}")
            return False
    
    def _update_nested_dict(self, original, update):
        """Recursively update a nested dictionary without overwriting non-updated values"""
        for key, value in update.items():
            if key in original and isinstance(value, dict) and isinstance(original[key], dict):
                self._update_nested_dict(original[key], value)
            else:
                original[key] = value
            
    def _create_backup(self):
        try:
            if not self.backup_dir.exists():
                self.backup_dir.mkdir(parents=True)
                
            if self.config_file.exists():
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = self.backup_dir / f'config_{timestamp}.json'
                shutil.copy2(self.config_file, backup_file)
                
                # Keep only last N backups
                backups = sorted([f for f in self.backup_dir.glob('config_*.json')])
                max_backups = self.get_max_backups()
                if len(backups) > max_backups:
                    for old_backup in backups[:-max_backups]:
                        old_backup.unlink()
        except Exception as e:
            print(f"Error creating backup: {e}")
            
    def get_twitch_config(self) -> Dict[str, str]:
        """Get Twitch configuration"""
        result = self.twitch_config.copy()  # Начинаем с токенов
        
        # Добавляем channel из основной конфигурации
        if 'twitch' in self.config and 'channel' in self.config['twitch']:
            result['channel'] = self.config['twitch']['channel']
        else:
            result['channel'] = ''
            
        return result
        
    def set_twitch_config(self, access_token=None, client_id=None, channel=None) -> None:
        """Set Twitch configuration"""
        # Обновляем токены в отдельный файл
        twitch_update = {}
        if access_token is not None and access_token:
            twitch_update['access_token'] = access_token
        if client_id is not None and client_id:
            twitch_update['client_id'] = client_id
            
        if twitch_update:
            self.save_twitch_config_file(twitch_update)
        
        # Обновляем канал в основную конфигурацию
        if channel is not None:
            if 'twitch' not in self.config:
                self.config['twitch'] = {}
            self.config['twitch']['channel'] = channel
            self.save_config()
        
    def set_twitch_channel(self, channel: str) -> None:
        """Set only the Twitch channel without affecting tokens"""
        if 'twitch' not in self.config:
            self.config['twitch'] = {}
        self.config['twitch']['channel'] = channel
        self.save_config()
        
    # Остальные методы класса...
    
    def get_current_file(self):
        return self.config.get('current_file')
        
    def set_current_file(self, file_name):
        self.config['current_file'] = file_name
        # Add to recent files if not already there
        if file_name and file_name not in self.config['recent_files']:
            self.config['recent_files'].insert(0, file_name)
            # Keep only last 10 files
            self.config['recent_files'] = self.config['recent_files'][:10]
        self.save_config()
        
    def get_volume(self):
        return self.config.get('volume', 0.5)
        
    def set_volume(self, volume):
        self.config['volume'] = max(0.0, min(1.0, volume))
        self.save_config()
        
    def get_auto_save(self):
        return self.config.get('auto_save', {'enabled': True, 'interval': 300})
        
    def set_auto_save(self, enabled, interval):
        if 'auto_save' not in self.config:
            self.config['auto_save'] = {}
        self.config['auto_save']['enabled'] = enabled
        self.config['auto_save']['interval'] = interval
        self.save_config()

    def get_currency_auto_save(self):
        """Get currency auto-save settings"""
        return self.config.get('currency_auto_save', {'enabled': True, 'interval': 300})

    def set_currency_auto_save(self, enabled, interval):
        """Set currency auto-save settings"""
        if 'currency_auto_save' not in self.config:
            self.config['currency_auto_save'] = {}
        self.config['currency_auto_save']['enabled'] = enabled
        self.config['currency_auto_save']['interval'] = interval
        self.save_config()

    def get_system_auto_backup(self):
        """Get system auto-backup settings"""
        return self.config.get('system_auto_backup', {'enabled': False, 'interval': 3600})

    def set_system_auto_backup(self, enabled, interval):
        """Set system auto-backup settings"""
        if 'system_auto_backup' not in self.config:
            self.config['system_auto_backup'] = {}
        self.config['system_auto_backup']['enabled'] = enabled
        self.config['system_auto_backup']['interval'] = interval
        self.save_config()
        
    def get_recent_files(self):
        return self.config.get('recent_files', [])
        
    def save_commands(self, commands):
        try:
            with open(self.commands_file, 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving commands: {e}")
            return False
            
    def load_commands(self):
        try:
            if self.commands_file.exists():
                with open(self.commands_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error loading commands: {e}")
            return []
            
    def save_legacy_format(self, commands, file_name):
        try:
            with open(file_name, 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving legacy format: {e}")
            return False

    def get_commands_config(self) -> Dict[str, Any]:
        """Get commands configuration"""
        return self.config.get('commands', {})
        
    def set_commands_config(self, commands: Dict[str, Any]) -> None:
        """Set commands configuration"""
        self.config['commands'] = commands
        self.save_config()
        
    def get_sound_config(self) -> Dict[str, Any]:
        """Get sound configuration"""
        return self.config.get('sound', {})
        
    def set_sound_config(self, volume: float, sound_dir: str) -> None:
        """Set sound configuration"""
        if 'sound' not in self.config:
            self.config['sound'] = {}
            
        if volume is not None:
            self.config['sound']['volume'] = volume
        if sound_dir is not None:
            self.config['sound']['sound_dir'] = sound_dir
        
        self.save_config()

    def get_sound_interruption(self):
        """Get sound interruption setting"""
        return self.config.get('sound', {}).get('allow_interruption', True)
    
    def set_sound_interruption(self, allow_interruption):
        """Set sound interruption setting"""
        if 'sound' not in self.config:
            self.config['sound'] = {}
        self.config['sound']['allow_interruption'] = allow_interruption
        self.save_config()

    def get_interruption_message(self):
        """Get whether to show interruption messages"""
        return self.config.get('sound', {}).get('show_interruption_message', True)
    
    def set_interruption_message(self, show_message):
        """Set whether to show interruption messages"""
        if 'sound' not in self.config:
            self.config['sound'] = {}
        self.config['sound']['show_interruption_message'] = show_message
        self.save_config()

    def save_twitch_config(self, access_token=None, client_id=None, channel=None, refresh_token=None):
        """Save Twitch configuration"""
        try:
            # Обновляем токены в отдельный файл
            twitch_update = {}
            if access_token is not None and access_token:
                twitch_update['access_token'] = access_token
            if client_id is not None and client_id:
                twitch_update['client_id'] = client_id
            if refresh_token is not None and refresh_token:
                twitch_update['refresh_token'] = refresh_token
                
            if twitch_update:
                self.save_twitch_config_file(twitch_update)
            
            # Обновляем канал в основную конфигурацию
            if channel is not None:
                if 'twitch' not in self.config:
                    self.config['twitch'] = {}
                self.config['twitch']['channel'] = channel
                self.save_config()
                
            return True
        except Exception as e:
            print(f"Error saving Twitch config: {e}")
            return False

    def get_max_backups(self):
        """Get maximum number of backups to keep"""
        return self.config.get('backup', {}).get('max_backups', 10)
    
    def set_max_backups(self, max_backups):
        """Set maximum number of backups to keep"""
        if 'backup' not in self.config:
            self.config['backup'] = {}
        self.config['backup']['max_backups'] = max_backups
        self.save_config()

    def get_max_currency_backups(self):
        """Get maximum number of currency backups to keep"""
        return self.config.get('backup', {}).get('max_currency_backups', 10)

    def set_max_currency_backups(self, max_backups):
        """Set maximum number of currency backups to keep"""
        if 'backup' not in self.config:
            self.config['backup'] = {}
        self.config['backup']['max_currency_backups'] = max_backups
        self.save_config()

    def get_max_comprehensive_backups(self):
        """Get maximum number of comprehensive backups to keep"""
        return self.config.get('backup', {}).get('max_comprehensive_backups', 5)

    def set_max_comprehensive_backups(self, max_backups):
        """Set maximum number of comprehensive backups to keep"""
        if 'backup' not in self.config:
            self.config['backup'] = {}
        self.config['backup']['max_comprehensive_backups'] = max_backups
        self.save_config()

    def get_manual_moderators(self):
        """Get manual moderators list"""
        return self.moderators_config.get('manual_moderators', [])
    
    def set_manual_moderators(self, moderators_list):
        """Set manual moderators list"""
        self.moderators_config['manual_moderators'] = moderators_list
        self.save_moderators_config_file()
    
    def add_manual_moderator(self, username):
        """Add a moderator to manual list and remove from excluded list if present"""
        username = username.lower().strip()
        if not username:
            return False
        
        manual_mods = self.get_manual_moderators()
        added = False
        
        if username not in manual_mods:
            manual_mods.append(username)
            self.set_manual_moderators(manual_mods)
            added = True
        
        # Убираем из списка исключенных, если там есть
        if self.remove_excluded_moderator(username):
            print(f"User {username} removed from excluded list")
            added = True
        
        return added
    
    def remove_manual_moderator(self, username):
        """Remove a moderator from manual list and add to excluded list"""
        username = username.lower().strip()
        manual_mods = self.get_manual_moderators()
        removed = False
        
        if username in manual_mods:
            manual_mods.remove(username)
            self.set_manual_moderators(manual_mods)
            removed = True
        
        # Добавляем в список исключенных, чтобы API не переопределял решение
        self.add_excluded_moderator(username)
        
        return True  # Возвращаем True, если действие выполнено

    def get_excluded_moderators(self):
        """Get excluded moderators list"""
        return self.moderators_config.get('excluded_moderators', [])
    
    def set_excluded_moderators(self, moderators_list):
        """Set excluded moderators list"""
        self.moderators_config['excluded_moderators'] = moderators_list
        self.save_moderators_config_file()
    
    def add_excluded_moderator(self, username):
        """Add a moderator to excluded list"""
        username = username.lower().strip()
        if not username:
            return False
        excluded_mods = self.get_excluded_moderators()
        if username not in excluded_mods:
            excluded_mods.append(username)
            self.set_excluded_moderators(excluded_mods)
            return True
        return False
    
    def remove_excluded_moderator(self, username):
        """Remove a moderator from excluded list"""
        username = username.lower().strip()
        excluded_mods = self.get_excluded_moderators()
        if username in excluded_mods:
            excluded_mods.remove(username)
            self.set_excluded_moderators(excluded_mods)
            return True
        return False
