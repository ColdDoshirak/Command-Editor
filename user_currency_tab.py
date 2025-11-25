import json
import os
import time
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
                           QCheckBox, QDialog, QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox,
                           QFileDialog, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QDateTime
from currency_manager import CurrencyManager

class UserCurrencyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.currency_manager = self.parent.currency_manager if parent else CurrencyManager()
        self.initUI()
        
        # Файловый монитор для отслеживания изменений в файле данных
        self.last_modified_time = self.get_file_modified_time()
        
        # Создаем таймер для проверки изменения файла
        self.file_watcher_timer = QTimer(self)
        self.file_watcher_timer.timeout.connect(self.check_file_changes)
        self.file_watcher_timer.start(1000)  # Проверка каждую секунду
        
        # Создаем таймер для автообновления таблицы
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.populate_table)
        self.refresh_timer.start(30000)  # Обновление каждые 30 секунд
        
        # Первоначальное заполнение таблицы
        self.populate_table()
    
    def get_file_modified_time(self):
        """Получить время последнего изменения файла с данными пользователей"""
        try:
            if self.currency_manager and hasattr(self.currency_manager, 'users_file'):
                if os.path.exists(self.currency_manager.users_file):
                    return os.path.getmtime(self.currency_manager.users_file)
        except Exception as e:
            print(f"Error getting file modified time: {e}")
        return 0

    def check_file_changes(self):
        """Проверить, изменился ли файл с данными пользователей"""
        try:
            current_modified_time = self.get_file_modified_time()
            if current_modified_time > self.last_modified_time:
                print("Currency users file changed, updating table...")
                self.last_modified_time = current_modified_time
                self.populate_table()
        except Exception as e:
            print(f"Error checking file changes: {e}")

    def initUI(self):
        """Initialize the UI components"""
        layout = QVBoxLayout()
        
        # Добавляем панель с кнопками и информацией
        controls_layout = QHBoxLayout()
        
        # Кнопка обновления таблицы
        self.refresh_button = QPushButton("Refresh Table")
        self.refresh_button.clicked.connect(self.populate_table)
        controls_layout.addWidget(self.refresh_button)
        
        # Кнопка ручного сохранения пользователей
        self.save_button = QPushButton("Save Users")
        self.save_button.clicked.connect(self.manual_save_users)
        controls_layout.addWidget(self.save_button)
        
        # Кнопка добавления нового пользователя
        self.add_user_button = QPushButton("Add User")
        self.add_user_button.clicked.connect(self.add_user)
        controls_layout.addWidget(self.add_user_button)
        
        # Добавляем чекбокс для автообновления
        self.auto_refresh = QCheckBox("Auto-refresh")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.stateChanged.connect(self.toggle_auto_refresh)
        controls_layout.addWidget(self.auto_refresh)
        
        # Добавляем метку с временем последнего обновления
        self.last_update = QLabel("Last update: Never")
        controls_layout.addWidget(self.last_update)
        
        controls_layout.addStretch(1)  # Добавим растяжку
        
        layout.addLayout(controls_layout)
        
        # Создаем таблицу с явно заданными полосами прокрутки
        self.table = QTableWidget()
        self.table.setColumnCount(7)  # User, Points, Hours, Rank, Regular, Edit, Remove
        self.table.setHorizontalHeaderLabels(["User", "Points", "Hours", "Rank", "Regular", "Edit", "Remove"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        
        # Явно включаем полосы прокрутки
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Убеждаемся, что таблица адекватно расширяется
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        layout.addWidget(self.table)
        
        self.setLayout(layout)
    
    def toggle_auto_refresh(self, state):
        """Включить или выключить автоматическое обновление"""
        if state == Qt.Checked:
            self.refresh_timer.start(30000)
        else:
            self.refresh_timer.stop()

    def populate_table(self):
        """Заполнить таблицу данными о пользователях"""
        try:
            # Запомним текущее выделение и позицию прокрутки
            current_row = -1
            scroll_position = 0
            
            if self.table.selectionModel() and self.table.selectionModel().hasSelection():
                try:
                    selected_rows = self.table.selectionModel().selectedRows()
                    if selected_rows:
                        current_row = selected_rows[0].row()
                except Exception as e:
                    print(f"Error getting selection: {e}")
            
            if self.table.verticalScrollBar():
                scroll_position = self.table.verticalScrollBar().value()
            
            # Получаем текущие данные пользователей из менеджера
            if self.currency_manager:
                users_data = self.currency_manager.users
            else:
                users_data = {}
            
            if not users_data:
                print("No currency users data available")
                # Обновить метку времени последнего обновления
                now = QDateTime.currentDateTime().toString("HH:mm:ss")
                self.last_update.setText(f"Last update: {now}")
                return
            
            # Сортировка пользователей по количеству очков (по убыванию)
            sorted_users = sorted(users_data.items(), key=lambda x: x[1].get('points', 0), reverse=True)
            
            # Настраиваем количество строк
            self.table.setRowCount(len(sorted_users))
            
            # Заполняем таблицу
            for row, (username, data) in enumerate(sorted_users):
                # Пользователь
                user_item = QTableWidgetItem(username)
                self.table.setItem(row, 0, user_item)
                
                # Очки
                points = data.get('points', 0)
                points_item = QTableWidgetItem(str(points))
                points_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 1, points_item)                # Часы в формате "1h15m"
                hours = data.get('hours', 0)
                formatted_hours = self.currency_manager.format_hours(hours) if hasattr(self.currency_manager, 'format_hours') else f"{hours:.2f}"
                hours_item = QTableWidgetItem(formatted_hours)
                hours_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, 2, hours_item)
                
                # Ранг
                rank = self.get_user_rank(username, points)
                rank_item = QTableWidgetItem(rank)
                self.table.setItem(row, 3, rank_item)
                
                # Статус Regular
                is_regular = data.get('is_regular', False)
                regular_item = QTableWidgetItem("✓" if is_regular else "")
                regular_item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 4, regular_item)
                
                # Кнопка редактирования
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(lambda checked=False, u=username: self.edit_user(u))
                self.table.setCellWidget(row, 5, edit_btn)
                
                # Кнопка удаления
                remove_btn = QPushButton("Remove")
                remove_btn.clicked.connect(lambda checked=False, u=username: self.remove_user(u))
                self.table.setCellWidget(row, 6, remove_btn)
            
            # Восстановим выделение и позицию прокрутки
            if current_row >= 0 and current_row < self.table.rowCount():
                self.table.selectRow(current_row)
            
            if self.table.verticalScrollBar():
                self.table.verticalScrollBar().setValue(scroll_position)
            
            # Обновить метку времени последнего обновления
            now = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.last_update.setText(f"Last update: {now}")
            
            print(f"Currency table updated with {len(sorted_users)} users")
            
        except Exception as e:
            print(f"Error populating currency table: {e}")
            import traceback
            traceback.print_exc()
    
    def get_user_rank(self, username, points):
        """Получить ранг пользователя"""
        try:
            ranks = []
            
            # Получаем ранги из разных возможных источников
            if hasattr(self.parent, 'ranks_tab'):
                if hasattr(self.parent.ranks_tab, 'ranks_data'):
                    ranks = self.parent.ranks_tab.ranks_data
                elif hasattr(self.parent.ranks_tab, 'ranks_list'):
                    ranks = self.parent.ranks_tab.ranks_list
                elif hasattr(self.parent.currency_manager, 'get_ranks'):
                    ranks = self.parent.currency_manager.get_ranks()
            
            if not ranks:
                return ""
            
            # Сортировка рангов по количеству очков (по убыванию)
            sorted_ranks = sorted(ranks, key=lambda x: x['points'], reverse=True)
            
            # Находим подходящий ранг
            for rank in sorted_ranks:
                if points >= rank['points']:
                    return rank['name']
            
            return ""
            
        except Exception as e:
            print(f"Error getting rank for {username}: {e}")
            return ""
    
    def add_user(self):
        """Добавить нового пользователя"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add User")
        layout = QVBoxLayout()
        
        # Имя пользователя
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Username:"))
        name_input = QLineEdit()
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # Очки
        points_layout = QHBoxLayout()
        points_layout.addWidget(QLabel("Points:"))
        points_input = QSpinBox()
        points_input.setRange(0, 999999)
        points_layout.addWidget(points_input)
        layout.addLayout(points_layout)
          # Часы (с поддержкой дробных значений)
        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel("Hours:"))
        hours_input = QDoubleSpinBox()
        hours_input.setRange(0, 9999)
        hours_input.setDecimals(2)  # Устанавливаем 2 десятичных знака
        hours_layout.addWidget(hours_input)
        layout.addLayout(hours_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Обработка сохранения
        def save_user():
            username = name_input.text().strip()
            if not username:
                QMessageBox.warning(dialog, "Error", "Username cannot be empty")
                return
            
            points = points_input.value()
            hours = hours_input.value()
            
            if self.currency_manager:
                # Добавляем нового пользователя через CurrencyManager API
                if not hasattr(self.currency_manager, 'users') or self.currency_manager.users is None:
                    self.currency_manager.users = {}

                # Используем add_user, затем обновляем значения и сохраняем принудительно
                self.currency_manager.add_user(username, points=points, hours=hours)
                self.currency_manager.users[username]['last_seen'] = time.time()
                # Явное сохранение, чтобы гарантировать запись в файл
                self.currency_manager.save_users(force=True)
                
                # Обновляем таблицу
                self.populate_table()
                
                dialog.accept()
            else:
                QMessageBox.warning(dialog, "Error", "Currency manager not accessible")
        
        save_btn.clicked.connect(save_user)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def edit_user(self, username):
        """Редактировать пользователя"""
        if not self.currency_manager or not hasattr(self.currency_manager, 'users') or not username in self.currency_manager.users:
            QMessageBox.warning(self, "Error", f"User {username} not found")
            return
        
        user_data = self.currency_manager.users[username]
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit User: {username}")
        layout = QVBoxLayout()
        
        # Очки
        points_layout = QHBoxLayout()
        points_layout.addWidget(QLabel("Points:"))
        points_input = QSpinBox()
        points_input.setRange(0, 999999)
        points_input.setValue(user_data.get('points', 0))
        points_layout.addWidget(points_input)
        layout.addLayout(points_layout)
          # Часы (с поддержкой дробных значений)
        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel("Hours:"))
        hours_input = QDoubleSpinBox()  # Используем QDoubleSpinBox для дробных значений
        hours_input.setRange(0, 9999)
        hours_input.setDecimals(2)  # Устанавливаем 2 десятичных знака
        hours_input.setValue(user_data.get('hours', 0))
        hours_layout.addWidget(hours_input)
        layout.addLayout(hours_layout)
        
        # Добавить чекбокс для Regular после часов
        is_regular_layout = QHBoxLayout()
        is_regular_layout.addWidget(QLabel("Regular:"))
        is_regular_check = QCheckBox()
        is_regular_check.setChecked(user_data.get('is_regular', False))
        is_regular_layout.addWidget(is_regular_check)
        layout.addLayout(is_regular_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Обработка сохранения
        def save_edit():
            points = points_input.value()
            hours = hours_input.value()
            is_regular = is_regular_check.isChecked()
            
            # Обновляем данные пользователя
            self.currency_manager.users[username]['points'] = points
            self.currency_manager.users[username]['hours'] = hours
            self.currency_manager.users[username]['is_regular'] = is_regular
            self.currency_manager.users[username]['last_seen'] = time.time()

            # Помечаем данные как изменённые и сохраняем принудительно
            if hasattr(self.currency_manager, "_save_pending"):
                self.currency_manager._save_pending = True
            self.currency_manager.save_users(force=True)
            
            # Обновляем таблицу
            self.populate_table()
            
            dialog.accept()
        
        save_btn.clicked.connect(save_edit)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def remove_user(self, username):
        """Удалить пользователя"""
        if not self.currency_manager or not hasattr(self.currency_manager, 'users'):
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove user '{username}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if username in self.currency_manager.users:
                    # Удаляем пользователя
                    del self.currency_manager.users[username]

                    # Помечаем данные как изменённые и сохраняем принудительно
                    if hasattr(self.currency_manager, "_save_pending"):
                        self.currency_manager._save_pending = True
                    self.currency_manager.save_users(force=True)
                    
                    # Принудительно очищаем таблицу, если пользователей не осталось
                    if not self.currency_manager.users:
                        self.table.setRowCount(0)
                        print("All users removed, table cleared")
                    
                    # Обновляем таблицу
                    self.populate_table()
                    
                    print(f"User {username} removed successfully")
                    return True
                else:
                    print(f"User {username} not found in users dictionary")
                    return False
                    
            except Exception as e:
                print(f"Error removing user {username}: {e}")
                import traceback
                traceback.print_exc()
                QMessageBox.warning(self, "Error", f"Failed to remove user: {str(e)}")
                return False
    
    def manual_save_users(self):
        """Manually save currency users data"""
        try:
            if self.currency_manager:
                # Явное сохранение по запросу пользователя всегда должно писать файл
                success = self.currency_manager.save_users(force=True)
                if success:
                    QMessageBox.information(self, "Сохранение", "Данные пользователей успешно сохранены!")
                    # Обновляем время последнего обновления
                    now = QDateTime.currentDateTime().toString("HH:mm:ss")
                    self.last_update.setText(f"Last update: {now}")
                else:
                    QMessageBox.warning(self, "Предупреждение", "Не удалось сохранить данные пользователей.")
            else:
                QMessageBox.warning(self, "Ошибка", "Нет доступа к менеджеру валюты")
        except Exception as e:
            print(f"Ошибка при сохранении пользователей: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Ошибка", f"Произошла ошибка при сохранении: {str(e)}")