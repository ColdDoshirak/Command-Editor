"""
Менеджер модераторов для Command Editor
Обеспечивает централизованное управление списками модераторов
"""

from typing import List, Set
from config_manager import ConfigManager


class ModeratorsManager:
    """Класс для управления списками модераторов"""
    
    def __init__(self, config_manager: ConfigManager = None):
        self.config_manager = config_manager or ConfigManager()
        self._api_moderators: Set[str] = set()
        self._combined_moderators: Set[str] = set()
    
    def get_manual_moderators(self) -> List[str]:
        """Получить список ручных модераторов"""
        return self.config_manager.get_manual_moderators()
    
    def get_api_moderators(self) -> List[str]:
        """Получить список модераторов из API"""
        return list(self._api_moderators)
    
    def get_all_moderators(self) -> List[str]:
        """Получить объединенный список всех модераторов"""
        return list(self._combined_moderators)
    
    def update_api_moderators(self, api_moderators: List[str]):
        """Обновить список модераторов из API"""
        self._api_moderators = set(mod.lower() for mod in api_moderators)
        self._update_combined_list()
    
    def add_manual_moderator(self, username: str) -> bool:
        """Добавить модератора в ручной список"""
        result = self.config_manager.add_manual_moderator(username)
        if result:
            self._update_combined_list()
        return result
    
    def remove_manual_moderator(self, username: str) -> bool:
        """Удалить модератора из ручного списка"""
        result = self.config_manager.remove_manual_moderator(username)
        if result:
            self._update_combined_list()
        return result
    
    def is_moderator(self, username: str) -> bool:
        """Проверить, является ли пользователь модератором"""
        return username.lower() in self._combined_moderators
    
    def is_manual_moderator(self, username: str) -> bool:
        """Проверить, является ли пользователь ручным модератором"""
        manual_mods = self.get_manual_moderators()
        return username.lower() in [mod.lower() for mod in manual_mods]
    
    def is_api_moderator(self, username: str) -> bool:
        """Проверить, является ли пользователь модератором из API"""
        return username.lower() in self._api_moderators
    
    def get_moderator_source(self, username: str) -> str:
        """Получить источник модератора: 'api', 'manual', 'both' или 'none'"""
        username = username.lower()
        in_api = username in self._api_moderators
        in_manual = self.is_manual_moderator(username)
        
        if in_api and in_manual:
            return 'both'
        elif in_api:
            return 'api'
        elif in_manual:
            return 'manual'
        else:
            return 'none'
    
    def _update_combined_list(self):
        """Обновить объединенный список модераторов"""
        manual_mods = set(mod.lower() for mod in self.get_manual_moderators())
        self._combined_moderators = self._api_moderators | manual_mods
    
    def get_moderators_by_source(self) -> dict:
        """Получить модераторов, сгруппированных по источнику"""
        manual_mods = set(mod.lower() for mod in self.get_manual_moderators())
        
        return {
            'api_only': list(self._api_moderators - manual_mods),
            'manual_only': list(manual_mods - self._api_moderators),
            'both': list(self._api_moderators & manual_mods)
        }
    
    def clear_api_moderators(self):
        """Очистить список модераторов из API"""
        self._api_moderators.clear()
        self._update_combined_list()
    
    def get_stats(self) -> dict:
        """Получить статистику по модераторам"""
        by_source = self.get_moderators_by_source()
        return {
            'total': len(self._combined_moderators),
            'api_only': len(by_source['api_only']),
            'manual_only': len(by_source['manual_only']),
            'both': len(by_source['both']),
            'api_total': len(self._api_moderators),
            'manual_total': len(self.get_manual_moderators())
        }
