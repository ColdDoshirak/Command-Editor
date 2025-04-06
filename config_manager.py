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
        
        # Load or create config
        self.config = self.load_config()
        
        # Load Twitch config (отдельный вызов)
        self.twitch_config = self.load_twitch_config()
        
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
                
                # Keep only last 5 backups
                backups = sorted([f for f in self.backup_dir.glob('config_*.json')])
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
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