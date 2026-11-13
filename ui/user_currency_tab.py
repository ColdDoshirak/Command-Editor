import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QCheckBox, QDialog, QLineEdit,
                             QDoubleSpinBox, QMessageBox, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, QDateTime
from core.currency_manager import CurrencyManager
from ui.i18n import tr

def _points_box():
    box = QDoubleSpinBox()
    box.setDecimals(2)
    box.setRange(0, CurrencyManager.MAX_BALANCE)
    return box


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
        self.refresh_button = QPushButton(tr("Refresh Table"))
        self.refresh_button.clicked.connect(self.populate_table)
        controls_layout.addWidget(self.refresh_button)
        
        # Кнопка ручного сохранения пользователей
        self.save_button = QPushButton(tr("Save Users"))
        self.save_button.clicked.connect(self.manual_save_users)
        controls_layout.addWidget(self.save_button)
        
        # Кнопка добавления нового пользователя
        self.add_user_button = QPushButton(tr("Add User"))
        self.add_user_button.clicked.connect(self.add_user)
        controls_layout.addWidget(self.add_user_button)
        
        # Добавляем чекбокс для автообновления
        self.auto_refresh = QCheckBox(tr("Auto-refresh"))
        self.auto_refresh.setChecked(True)
        self.auto_refresh.stateChanged.connect(self.toggle_auto_refresh)
        controls_layout.addWidget(self.auto_refresh)
        
        # Добавляем метку с временем последнего обновления
        self.last_update = QLabel(tr("Last update: Never"))
        controls_layout.addWidget(self.last_update)
        
        controls_layout.addStretch(1)  # Добавим растяжку
        
        layout.addLayout(controls_layout)
        
        # Создаем таблицу с явно заданными полосами прокрутки
        self.table = QTableWidget()
        self.table.setColumnCount(7)  # User, Points, Hours, Rank, Regular, Edit, Remove
        self.table.setHorizontalHeaderLabels([tr("User"), tr("Points"), tr("Hours"), tr("Rank"), tr("Regular"), tr("Edit"), tr("Remove")])
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
            
            # Снимок под users_lock: бот меняет users из своего потока, а
            # sorted(users.items()) по живому словарю падал с "dictionary
            # changed size during iteration" - и таблица молча не обновлялась.
            cm = self.currency_manager
            users_data = []
            if cm:
                lock = getattr(cm, 'users_lock', None)
                if lock is not None:
                    with lock:
                        users_data = [(name, dict(data)) for name, data in cm.users.items()
                                      if isinstance(data, dict)]
                else:
                    users_data = [(name, dict(data)) for name, data in cm.users.items()
                                  if isinstance(data, dict)]

            # Сортировка пользователей по количеству очков (по убыванию)
            sorted_users = sorted(users_data, key=lambda x: x[1].get('points', 0), reverse=True)
            # кнопки строк узнают зрителя отсюда: их больше не пересоздаём
            # на каждом обновлении (раньше - две новые кнопки на зрителя раз в 30 с)
            self._row_users = [name for name, _data in sorted_users]

            # Настраиваем количество строк (лишние строки и их кнопки уходят)
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
                self.table.setItem(row, 1, points_item)
                # Часы в формате "1h15m"
                hours = data.get('hours', 0)
                formatted_hours = cm.format_hours(hours) if hasattr(cm, 'format_hours') else f"{hours:.2f}"
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

                # Кнопки - один раз на строку
                if self.table.cellWidget(row, 5) is None:
                    edit_btn = QPushButton(tr("Edit"))
                    edit_btn.clicked.connect(lambda checked=False, r=row: self._on_row_button(r, "edit_user"))
                    self.table.setCellWidget(row, 5, edit_btn)
                if self.table.cellWidget(row, 6) is None:
                    remove_btn = QPushButton(tr("Remove"))
                    remove_btn.clicked.connect(lambda checked=False, r=row: self._on_row_button(r, "remove_user"))
                    self.table.setCellWidget(row, 6, remove_btn)

            # Восстановим выделение и позицию прокрутки
            if current_row >= 0 and current_row < self.table.rowCount():
                self.table.selectRow(current_row)
            
            if self.table.verticalScrollBar():
                self.table.verticalScrollBar().setValue(scroll_position)
            
            # Обновить метку времени последнего обновления
            now = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.last_update.setText(tr('Last update: {0}').format(now))
            
            print(f"Currency table updated with {len(sorted_users)} users")
            
        except Exception as e:
            print(f"Error populating currency table: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_row_button(self, row, action):
        """Кнопка строки: зритель - тот, что сейчас в этой строке."""
        users = getattr(self, '_row_users', [])
        if 0 <= row < len(users):
            getattr(self, action)(users[row])

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
        dialog.setWindowTitle(tr("Add User"))
        layout = QVBoxLayout()
        
        # Имя пользователя
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel(tr("Username:")))
        name_input = QLineEdit()
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # Очки
        points_layout = QHBoxLayout()
        points_layout.addWidget(QLabel(tr("Points:")))
        points_input = _points_box()
        points_layout.addWidget(points_input)
        layout.addLayout(points_layout)
          # Часы (с поддержкой дробных значений)
        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel(tr("Hours:")))
        hours_input = QDoubleSpinBox()
        hours_input.setRange(0, 9999)
        hours_input.setDecimals(2)  # Устанавливаем 2 десятичных знака
        hours_layout.addWidget(hours_input)
        layout.addLayout(hours_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        save_btn = QPushButton(tr("Save"))
        cancel_btn = QPushButton(tr("Cancel"))
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Обработка сохранения
        def save_user():
            username = name_input.text().strip()
            if not username:
                QMessageBox.warning(dialog, tr("Error"), tr("Username cannot be empty"))
                return
            
            points = points_input.value()
            hours = hours_input.value()
            
            if self.currency_manager:
                # Добавляем нового пользователя через CurrencyManager API
                if not hasattr(self.currency_manager, 'users') or self.currency_manager.users is None:
                    self.currency_manager.users = {}

                # add_user хранит имя в нижнем регистре, ставит last_seen и
                # сохраняет (раньше здесь был users[username] с исходным
                # регистром: "Alice" -> KeyError, диалог не закрывался)
                self.currency_manager.add_user(username, points=points, hours=hours)
                
                # Обновляем таблицу
                self.populate_table()
                
                dialog.accept()
            else:
                QMessageBox.warning(dialog, tr("Error"), tr("Currency manager not accessible"))
        
        save_btn.clicked.connect(save_user)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def edit_user(self, username):
        """Редактировать пользователя"""
        if not self.currency_manager or not hasattr(self.currency_manager, 'users') or not username in self.currency_manager.users:
            QMessageBox.warning(self, tr("Error"), tr('User {0} not found').format(username))
            return
        
        user_data = self.currency_manager.users[username]
        
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Edit User: {0}').format(username))
        layout = QVBoxLayout()
        
        # Очки
        points_layout = QHBoxLayout()
        points_layout.addWidget(QLabel(tr("Points:")))
        points_input = _points_box()
        points_input.setValue(float(user_data.get('points', 0) or 0))
        points_layout.addWidget(points_input)
        layout.addLayout(points_layout)
          # Часы (с поддержкой дробных значений)
        hours_layout = QHBoxLayout()
        hours_layout.addWidget(QLabel(tr("Hours:")))
        hours_input = QDoubleSpinBox()  # Используем QDoubleSpinBox для дробных значений
        hours_input.setRange(0, 9999)
        hours_input.setDecimals(2)  # Устанавливаем 2 десятичных знака
        hours_input.setValue(user_data.get('hours', 0))
        hours_layout.addWidget(hours_input)
        layout.addLayout(hours_layout)
        
        # Добавить чекбокс для Regular после часов
        is_regular_layout = QHBoxLayout()
        is_regular_layout.addWidget(QLabel(tr("Regular:")))
        is_regular_check = QCheckBox()
        is_regular_check.setChecked(user_data.get('is_regular', False))
        is_regular_layout.addWidget(is_regular_check)
        layout.addLayout(is_regular_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        save_btn = QPushButton(tr("Save"))
        cancel_btn = QPushButton(tr("Cancel"))
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Обработка сохранения
        def save_edit():
            points = points_input.value()
            hours = hours_input.value()
            is_regular = is_regular_check.isChecked()
            
            # под users_lock и с записью на диск (бот меняет тех же зрителей)
            self.currency_manager.update_user_fields(
                username, points=round(points, 2), hours=hours, is_regular=is_regular)
            
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
            tr("Confirm Deletion"),
            tr("Are you sure you want to remove user '{0}'?").format(username),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # под users_lock, с записью на диск
                if self.currency_manager.remove_user(username):
                    
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
                QMessageBox.warning(self, tr("Error"), tr('Failed to remove user: {0}').format(str(e)))
                return False
    
    def manual_save_users(self):
        """Manually save currency users data"""
        try:
            if self.currency_manager:
                # Явное сохранение по запросу пользователя всегда должно писать файл
                success = self.currency_manager.save_users(force=True)
                if success:
                    QMessageBox.information(self, tr("Saving"), tr("Viewers' data saved!"))
                    # Обновляем время последнего обновления
                    now = QDateTime.currentDateTime().toString("HH:mm:ss")
                    self.last_update.setText(tr('Last update: {0}').format(now))
                else:
                    QMessageBox.warning(self, tr("Warning"), tr("Could not save the viewers' data."))
            else:
                QMessageBox.warning(self, tr("Error"), tr("The currency manager is not available"))
        except Exception as e:
            print(f"Ошибка при сохранении пользователей: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, tr("Error"), tr('Error while saving: {0}').format(str(e)))