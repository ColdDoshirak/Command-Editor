import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
import sys


class CurrencyManager:
    def __init__(self):
        # Основные хранилища данных        self.users = {}
        self.ranks = []
        
        # Настройки по умолчанию
        self.settings = {
            'accumulation_enabled': True,  # New setting for currency accumulation
            'show_service_messages': False,  # Setting for showing service messages in chat
            'command': '!points',
            'name': 'Points',
            'response': '$username [$rank] - Hours: $hours - $currencyname: $points',
            'cooldown': 5,
            'rank_type': 'Points',
            'offline_hours': False,
            'auto_regular': False,
            'auto_regular_amount': 100,
            'auto_regular_type': 'Points',
            'online_interval': 5,
            'offline_interval': 15,
            'live_payout': 1,
            'offline_payout': 0,
            'regular_bonus': 0,
            'sub_bonus': 0,            'mod_bonus': 0,
            'active_bonus': 1,
            'payout_mode': 'per_minute',  # Только per_minute режим
            'on_raid': 10,
            'on_follow': 10,
            'on_sub': 10,
            'mass_sub_gift': 0,
            'on_host': 0
        }
        
        # Определение корректных путей для работы и с PyInstaller
        if getattr(sys, 'frozen', False):
            # Запущено как скомпилированный .exe
            self.data_dir = Path(os.path.dirname(sys.executable))
        else:
            # Запущено как обычный .py файл
            self.data_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        
        # Создаем директорию для данных, если она не существует
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Пути к файлам данных
        self.users_file = self.data_dir / 'users_currency.json'
        self.currency_file = self.data_dir / 'users_currency.json'
        
        # Загружаем данные
        self.load_data()
        
        self.users_lock = threading.Lock()  # Блокировка для безопасности потоков
        
    def load_data(self):
        """Reload users data from file"""
        try:
            # Load users from JSON file if it exists, otherwise start empty
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    self.users = json.load(f)
            else:
                self.users = {}
        except Exception as e:
            print(f"Error loading currency data: {e}")
            # Ensure users dict exists even on error
            self.users = {}
    
    def save_users(self):
        """Сохранить данные о пользователях"""
        try:
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(str(self.users_file)), exist_ok=True)
            
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=4, ensure_ascii=False)
            print(f"Пользователи сохранены в {self.users_file}")
            return True
        except Exception as e:
            print(f"Ошибка сохранения данных пользователей: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Метод для совместимости с currency_file
    def save_currency_users(self):
        """Alias для save_users() для совместимости"""
        return self.save_users()
    
    def save_ranks(self):
        """Сохранить данные о рангах"""
        try:
            with open(self.data_dir / 'ranks.json', 'w', encoding='utf-8') as f:
                json.dump(self.ranks, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения данных рангов: {e}")
            return False
    
    def save_settings(self):
        """Save currency settings to file"""
        try:
            # Ensure data directory exists
            if not os.path.exists('data'):
                os.makedirs('data')
                
            # Save settings to file
            with open('data/currency_settings.json', 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
                
            print("Currency settings saved to file")
            return True
        except Exception as e:
            print(f"Error saving currency settings: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def load_settings(self):
        """Load currency settings from file"""
        try:
            # Ensure we have a settings dictionary
            if not hasattr(self, 'settings'):
                self.settings = {}
                
            # Default settings
            defaults = {
                'live_payout': 1,
                'online_interval': 5,
                'lurker_payout': 0,
                'lurker_hours': False,
                'offline_payout': 0,
                'offline_interval': 15,
                'offline_hours': False,
                'offline_active_bonus': False,
                'sub_bonus': 1,
                'regular_bonus': 1,
                'mod_bonus': 2,                'active_bonus': 1,
                'currency_single': 'point',
                'currency_plural': 'points',
                'hours_name': 'hours',
                'show_service_messages': False,  # Настройка для показа служебных сообщений в чате
                # Добавляем настройки, используемые в process_currency_update
                'online_amount': 1,
                'offline_amount': 0,
                'active_bonus_enabled': False,
                'active_bonus_amount': 1
            }
            
            # Update with defaults first
            self.settings.update(defaults)
            
            # Load from file if it exists
            if os.path.exists('data/currency_settings.json'):
                with open('data/currency_settings.json', 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
                print("Currency settings loaded from file")
            else:
                print("No currency settings file found, using defaults")
            
            # Добавьте к существующим настройкам:
            self.settings.setdefault("raid_points", 10)
            self.settings.setdefault("follow_points", 5)
            self.settings.setdefault("sub_points", 20)
            self.settings.setdefault("gift_sub_points", 15)  # Для получателя
            self.settings.setdefault("gift_sub_bonus", 5)    # Бонус дарителю за каждую            self.settings.setdefault("bits_ratio", 1)        # Очки за каждые 100 битов
            self.settings.setdefault("host_points", 5)
            self.settings.setdefault("sub_bonus", 2)         # Множитель очков для подписчиков
            self.settings.setdefault("payout_mode", "per_minute")  # Всегда используем per_minute
            
            return self.settings  # Возвращаем словарь настроек, а не True/False
        except Exception as e:
            print(f"Error loading currency settings: {e}")
            import traceback
            traceback.print_exc()
            return self.settings  # Возвращаем настройки по умолчанию в случае ошибки
    
    def add_user(self, username, points=0, hours=0):
        """Add a new user to the currency system"""
        username = username.lower()
        
        if not hasattr(self, 'users') or self.users is None:
            self.users = {}
            
        self.users[username] = {
            'points': points,
            'hours': hours,
            'last_seen': time.time()
        }
        
        # Save changes
        self.save_users()
    
    def update_user(self, username, points=None, hours=None):
        """Update user data in the currency system"""
        username = username.lower()
        
        if not hasattr(self, 'users') or self.users is None:
            self.users = {}
            
        if username not in self.users:
            return False
            
        if points is not None:
            self.users[username]['points'] = points
            
        if hours is not None:
            self.users[username]['hours'] = hours
            
        # Update last seen timestamp
        self.users[username]['last_seen'] = time.time()
        
        # Save changes
        self.save_users()
        return True
    
    def remove_user(self, username):
        """Remove a user from the currency system"""
        username = username.lower()
        
        if not hasattr(self, 'users') or self.users is None:
            return False
            
        if username in self.users:
            del self.users[username]
            
            # Save changes
            self.save_users()
            return True
            
        return False
    
    def add_points(self, username, amount):
        """Add points to a user"""
        # Нормализуем имя
        username = username.lower()
        if username.startswith('@'):
            username = username[1:]
        
        with self.users_lock:  # Блокируем доступ на время изменений
            if username not in self.users:
                self.users[username] = {
                    'points': 0,
                    'hours': 0,
                    'last_seen': time.time()
                }
                
            self.users[username]['points'] += amount
            self.users[username]['last_seen'] = time.time()
            
            # Применение бонуса только если был передан параметр apply_bonus=True
            if self.users[username].get("is_regular"):
                bonus = self.settings.get("regular_bonus", 0)
                self.users[username]['points'] += bonus
                
            current_points = self.users[username]['points']
            
        # Проверки ранга и автоматического получения статуса регуляра после освобождения блокировки
        self.check_auto_regular(username)
        self.check_rank_promotion(username)
        
        return current_points
    
    def set_points(self, username, amount):
        """Set points for a user to a specific amount"""
        username = username.lower()
        if username not in self.users:
            self.users[username] = {
                'points': 0,
                'hours': 0,
                'last_seen': time.time()
            }
        self.users[username]['points'] = amount
        self.users[username]['last_seen'] = time.time()
        self.save_users()
    
    def remove_points(self, username, amount):
        """Убрать очки у пользователя"""
        if username not in self.users:
            return False
        
        self.users[username]['points'] = max(0, self.users[username]['points'] - amount)
        self.save_users()
        return True
    
    def add_hours(self, username, hours):
        """Добавить часы пользователю"""
        if username not in self.users:
            self.add_user(username)
        
        self.users[username]['hours'] += hours
        if self.settings.get('rank_type') == 'Hours':
            self.check_rank_promotion(username)
        self.save_users()
        return True
    
    def add_rank(self, name, required, group, description=""):
        """Добавить новый ранг"""
        rank = {
            'name': name,
            'required': required,
            'group': group,
            'description': description,
            'color': "#000000"
        }
        self.ranks.append(rank)
        self.ranks.sort(key=lambda x: x['required'])
        self.save_ranks()
        return True
    
    def edit_rank(self, index, name=None, required=None, group=None, description=None, color=None):
        """Изменить существующий ранг"""
        if index < 0 or index >= len(self.ranks):
            return False
        
        if name is not None:
            self.ranks[index]['name'] = name
        if required is not None:
            self.ranks[index]['required'] = required
        if group is not None:
            self.ranks[index]['group'] = group
        if description is not None:
            self.ranks[index]['description'] = description
        if color is not None:
            self.ranks[index]['color'] = color
        
        self.ranks.sort(key=lambda x: x['required'])
        self.save_ranks()
        return True
    
    def delete_rank(self, index):
        """Удалить ранг"""
        if index < 0 or index >= len(self.ranks):
            return False
        
        del self.ranks[index]
        self.save_ranks()
        return True
    
    def check_rank_promotion(self, username):
        """Проверить, нужно ли повысить ранг пользователя"""
        if username not in self.users or not self.ranks:
            return False
        
        user = self.users[username]
        
        # Проверка на существование 'rank' в данных пользователя
        if 'rank' not in user:
            user['rank'] = ""
            
        rank_value = user['points'] if self.settings.get('rank_type') == 'Points' else user['hours']
        
        for rank in reversed(self.ranks):
            if rank_value >= rank['required']:
                if user['rank'] != rank['name']:
                    user['rank'] = rank['name']
                    self.save_users()
                    return True
                break
        
        return False
    
    def check_auto_regular(self, username):
        """Автоматически присваивает статус Regular при достижении нужных поинтов"""
        settings = self.settings
        if not settings.get("auto_regular", False):
            return False
        
        required = settings.get("auto_regular_amount", 50)
        user = self.users.get(username)
        
        if user and user.get("points", 0) >= required:
            # Если пользователь еще не Regular, выводим сообщение
            if not user.get("is_regular", False):
                print(f"User {username} became Regular (points: {user.get('points', 0)})")
            user["is_regular"] = True
            return True
        
        return False
    
    def format_currency_message(self, username):
        """Форматировать сообщение о валюте для пользователя"""
        user = self.users.get(username)
        if not user:
            return "Пользователь не найден"
        rank = user.get('rank') or ("Regular" if user.get("is_regular") else "Unranked")        # Format points to always display with 2 decimal places
        points = user.get('points', 0)
        formatted_points = f"{float(points):.2f}"
        
        message = self.settings['response']
        # Форматируем часы в формате "1h15m"
        hours = user.get('hours', 0)
        formatted_hours = self.format_hours(hours)
        
        replacements = {
            '$username': username,
            '$rank': rank,
            '$hours': formatted_hours,
            '$points': formatted_points,
            '$currencyname': self.settings.get('name', 'Points')
        }
        for placeholder, value in replacements.items():
            message = message.replace(placeholder, value)
        return message
    
    def process_command(self, username, command, args=None):
        """Обработать команду валюты"""
        if command.lower() == self.settings['command'].lower():
            return self.format_currency_message(username)
        return None
    
    def update_settings(self, new_settings):
        """Обновить настройки валюты"""
        self.settings.update(new_settings)
        self.save_settings()
        return True
    
    def bulk_update_points(self, action, amount, filter_func=None):
        """Массовое обновление очков для пользователей"""
        updated_count = 0
        
        for username, data in self.users.items():
            if filter_func is None or filter_func(username, data):
                if action == "add":
                    data['points'] += amount
                elif action == "set":
                    data['points'] = amount
                elif action == "reset":
                    data['points'] = 0
                
                updated_count += 1
                self.check_rank_promotion(username)
        
        if updated_count > 0:
            self.save_users()
        
        return updated_count
    
    def get_currency_name(self):
        """Получить название валюты"""
        return self.settings.get('currency_name', 'Points')
    
    def get_currency_command(self):
        """Получить команду для валюты"""
        return self.settings['command']
    
    def pay_for_command(self, username, cost):
        """Снять плату за команду с пользователя"""
        if cost <= 0:
            return True
        
        if username not in self.users:
            self.add_user(username)
        
        if self.users[username]['points'] >= cost:
            self.users[username]['points'] -= cost
            self.save_users()
            return True
        
        return False
    
    def update_last_seen(self, username):
        """Update last_seen timestamp for a user without adding points"""
        username = username.lower()  # Нормализация имени
        
        # Загрузка пользовательских данных при необходимости
        if not hasattr(self, 'users') or self.users is None:
            self.users = self.get_all_users()
        
        if username not in self.users:            self.users[username] = {
                'points': 0,
                'hours': 0,
                'last_seen': time.time()
            }
        else:
            self.users[username]['last_seen'] = time.time()
    
    def get_all_users(self):
        """Метод для совместимости с обращениями к get_all_users"""
        return self.users
    
    def process_currency_update(self, is_live=False, active_viewers=None, all_viewers=None, chat_message_callback=None):
        """Process currency update for viewers"""
        # Проверяем, включено ли накопление валюты
        if not self.settings.get('accumulation_enabled', True):
            print(f"[{datetime.now().isoformat()}] Currency accumulation disabled - skipping update")
            if chat_message_callback and self.settings.get('show_service_messages', False):
                chat_message_callback("Currency accumulation disabled")
            return False
            
        # Добавляем защиту от двойного начисления и вычисляем интервал начисления
        current_time = time.time()
        
        # Если прошло менее 5 секунд с момента последнего обновления, пропускаем
        if hasattr(self, 'last_update_time') and current_time - self.last_update_time < 5:
            print(f"[{datetime.now().isoformat()}] Skipping currency update - too soon after previous update")
            return
        
        # Рассчитываем время, прошедшее с последнего начисления в минутах
        elapsed_minutes = 0
        if hasattr(self, 'last_update_time'):
            elapsed_minutes = (current_time - self.last_update_time) / 60
        
        self.last_update_time = current_time
        
        try:
            if active_viewers is None:
                active_viewers = []
            if all_viewers is None:
                all_viewers = []

            if not all_viewers:
                print(f"[{datetime.now().isoformat()}] process_currency_update: no viewers → skip")
                return False

            # Логируем начало
            print(f"[{datetime.now().isoformat()}] process_currency_update: is_live={is_live}, "
                  f"active={len(active_viewers)}, all={len(all_viewers)}")
                  
            # Получаем базовую сумму поинтов и интервал начисления
            if is_live:
                base_payout = self.settings.get('live_payout', 0)
                interval_minutes = self.settings.get('online_interval', 5)
            else:
                base_payout = self.settings.get('offline_payout', 0)
                interval_minutes = self.settings.get('offline_interval', 15)            # Проратируем награду в зависимости от времени с последнего обновления
            # Формула: (Points per interval) * (elapsed minutes) / (interval minutes)
            if elapsed_minutes > 0:
                points_to_award = base_payout * elapsed_minutes / interval_minutes
            else:
                # Первый запуск, начисляем минимальную сумму
                points_to_award = base_payout / (interval_minutes * 2)
              # Округляем до двух знаков после запятой
            points_to_award = round(points_to_award, 2)
            
            status_message = f"Points calculation: {base_payout:.2f} per {interval_minutes} min, elapsed: {elapsed_minutes:.2f} min, awarding {points_to_award:.2f} points"
            print(f"[{datetime.now().isoformat()}] Proration: {base_payout} points per {interval_minutes} min interval, "                  f"elapsed: {elapsed_minutes:.2f} min, awarding {points_to_award:.2f} points")
            
            # Отправляем сообщение в чат, если есть callback и показ служебных сообщений включен
            if chat_message_callback and self.settings.get('show_service_messages', False):
                chat_message_callback(status_message)
            
            if points_to_award <= 0:
                print(f"[{datetime.now().isoformat()}] no points to award → skip")
                if chat_message_callback and self.settings.get('show_service_messages', False):
                    chat_message_callback("No points to award, skipping update")
                return False

            viewers_awarded = 0
            for user in all_viewers:
                uname = user.lower()
                  # Базовые очки с точностью до сотых
                pts = points_to_award
                
                # Бонус для регуляров
                is_regular = self.users.get(uname, {}).get('is_regular', False)
                regular_bonus = 0
                if is_regular:
                    # Проратируем и бонус регулярам
                    regular_bonus_rate = self.settings.get('regular_bonus', 0)
                    if elapsed_minutes > 0:
                        regular_bonus = round(regular_bonus_rate * elapsed_minutes / interval_minutes, 2)
                    else:
                        regular_bonus = round(regular_bonus_rate / (interval_minutes * 2), 2)
                
                # Бонус для подписчиков
                is_subscriber = self.users.get(uname, {}).get('is_subscriber', False)
                sub_bonus = 0
                if is_subscriber:
                    sub_multiplier = self.settings.get('sub_bonus', 2)
                    sub_bonus = round(pts * (sub_multiplier - 1), 2)  # Точность до сотых
                
                # Бонус для модераторов
                is_mod = self.users.get(uname, {}).get('is_mod', False)
                mod_bonus = 0
                if is_mod:
                    mod_bonus_base = self.settings.get('mod_bonus', 0)
                    if elapsed_minutes > 0:
                        mod_bonus = round(mod_bonus_base * elapsed_minutes / interval_minutes, 2)
                    else:
                        mod_bonus = round(mod_bonus_base / (interval_minutes * 2), 2)
                
                # Применяем все бонусы и округляем итоговую сумму до сотых
                total = round(pts + regular_bonus + sub_bonus + mod_bonus, 2)
                
                # Для целочисленных значений не нужна проверка на минимум 0.1
                
                self.add_points(uname, total)
                  # Обновляем часы просмотра (только если stream is live или offline_hours включены)
                hours_added = 0
                if is_live or self.settings.get('offline_hours', False):
                    # Конвертируем elapsed_minutes в часы, с округлением до сотых (поминутная точность)
                    hours_added = round(elapsed_minutes / 60, 2)
                    # Если пользователя нет в системе, добавляем его
                    if uname not in self.users:
                        self.users[uname] = {'points': 0, 'hours': 0, 'last_seen': time.time()}
                    # Добавляем часы пользователю
                    self.users[uname]['hours'] += hours_added
                
                # Логирование начисления (с точностью до сотых)
                bonus_str = f"(base {pts:.2f}"
                if regular_bonus > 0:
                    bonus_str += f" + regular bonus {regular_bonus:.2f}"
                if sub_bonus > 0:
                    bonus_str += f" + sub bonus {sub_bonus:.2f}"
                if mod_bonus > 0:
                    bonus_str += f" + mod bonus {mod_bonus:.2f}"
                bonus_str += ")"                # Добавляем информацию о часах в лог только если они начислены
                if hours_added > 0:
                    # Форматируем добавленные часы в виде минут, так как обычно они будут маленькими
                    minutes_added = round(hours_added * 60)
                    hours_info = f", hours +{minutes_added}m"
                else:
                    hours_info = ""
                print(f"[{datetime.now().isoformat()}] awarded {total:.2f} to {uname} {bonus_str} → new total {self.users[uname]['points']:.2f}{hours_info}")
                
                # Добавляем специальный лог для отслеживания часов
                if hours_added > 0:
                    total_hours_formatted = self.format_hours(self.users[uname]['hours'])
                    print(f"[{datetime.now().isoformat()}] Hours tracking: {uname} +{minutes_added}m → new total {total_hours_formatted}")
                viewers_awarded += 1
            
            self.save_users()
            summary_message = f"Points update completed: {viewers_awarded} users received points"
            print(f"[{datetime.now().isoformat()}] process_currency_update: done, "
                  f"{viewers_awarded} users processed")            # Отправляем итоговое сообщение в чат, если есть callback и показ служебных сообщений включен
            if chat_message_callback and self.settings.get('show_service_messages', False):
                chat_message_callback(summary_message)
                
            return True

        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error in process_currency_update: {e}")
            import traceback; traceback.print_exc()
            return False
    
    def get_currency_users(self):
        """Load currency users from file or return current users"""
        try:
            # Если users уже загружены, просто возвращаем их 
            if hasattr(self, 'users') and self.users is not None:
                return self.users
                
            # Если нет, загружаем из файла
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    self.users = json.load(f)
                    return self.users
            
            # Если файла нет, возвращаем пустой словарь
            self.users = {}
            return self.users
        except Exception as e:
            print(f"Error loading currency users: {e}")
            self.users = {}
            return self.users
    
    def get_points(self, username):
        """Получить количество поинтов пользователя"""
        username = username.lower()
        if username not in self.users:
            self.users[username] = {
                'points': 0,
                'hours': 0,
                'last_seen': time.time()
            }
        return self.users[username]['points']
        
    def get_hours(self, username):
        """Получить количество часов пользователя"""
        username = username.lower()
        if username not in self.users:
            self.users[username] = {
                'points': 0,
                'hours': 0,
                'last_seen': time.time()
            }
        return self.users[username].get('hours', 0)
        
    def get_rank(self, username):
        """Получить ранг пользователя"""
        username = username.lower()
        if username not in self.users:
            return ""
            
        user = self.users[username]
        
        # Если у пользователя уже есть ранг, вернем его
        if 'rank' in user and user['rank']:
            return user['rank']
            
        # Если у пользователя нет ранга, вычислим его на основе поинтов или часов
        rank_value = user['points'] if self.settings.get('rank_type', 'Points') == 'Points' else user['hours']
        
        # Сортируем ранги по требуемым значениям (от большего к меньшему)
        sorted_ranks = sorted(self.ranks, key=lambda x: x.get('points', 0) if 'points' in x else x.get('required', 0), reverse=True)
        
        # Находим подходящий ранг
        for rank in sorted_ranks:
            required = rank.get('points', 0) if 'points' in rank else rank.get('required', 0)
            if rank_value >= required:
                return rank['name']
        
        # Если ранг не был найден, возвращаем пустую строку
        return ""
    
    def format_hours(self, hours):
        """Форматирует часы в формате 1h15m"""
        # Округляем до ближайшей минуты
        total_minutes = round(hours * 60)
        hours_part = total_minutes // 60
        minutes_part = total_minutes % 60
        
        # Форматируем в виде "1h15m" или только "15m" если часов нет
        if hours_part > 0:
            if minutes_part > 0:
                return f"{hours_part}h{minutes_part}m"
            else:
                return f"{hours_part}h"
        else:
            return f"{minutes_part}m"