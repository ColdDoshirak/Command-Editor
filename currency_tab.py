import os
import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                           QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                           QGroupBox, QSlider, QScrollArea, QSizePolicy, QGridLayout, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from currency_manager import CurrencyManager

class CurrencyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.currency_manager = self.parent.currency_manager if parent else CurrencyManager()
        
        # Загрузка настроек перед инициализацией UI
        if not hasattr(self.currency_manager, 'settings') or not self.currency_manager.settings:
            self.currency_manager.load_settings()
            
        self.initUI()
        
    def initUI(self):
        main_layout = QVBoxLayout()
        
        # Создаем прокручиваемую область для всего содержимого
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Создаем контейнер для содержимого скролла
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)        # === GENERAL SECTION ===
        general_group = QGroupBox("General")
        general_layout = QVBoxLayout()
        
        # Currency Accumulation Toggle - добавляем переключатель в начале секции
        self.accumulation_check = QCheckBox("Enable Currency Accumulation")
        self.accumulation_check.setChecked(self.currency_manager.settings.get('accumulation_enabled', True))
        self.accumulation_check.stateChanged.connect(self.save_settings)
        self.accumulation_check.setToolTip("When enabled, users will earn currency while watching the stream")
        general_layout.addWidget(self.accumulation_check)
          # Добавляем опцию показа служебных сообщений в окне программы
        self.show_service_messages_check = QCheckBox("Show Service Messages in Program")
        self.show_service_messages_check.setChecked(self.currency_manager.settings.get('show_service_messages', False))
        self.show_service_messages_check.stateChanged.connect(self.save_settings)
        self.show_service_messages_check.setToolTip("When enabled, service messages about points calculation will be shown in the program's chat window")
        general_layout.addWidget(self.show_service_messages_check)
        
        # Points command
        command_layout = QHBoxLayout()
        command_label = QLabel("Command:")
        self.command_input = QLineEdit("!points")
        command_layout.addWidget(command_label)
        command_layout.addWidget(self.command_input)
        general_layout.addLayout(command_layout)
        
        # Name
        name_layout = QHBoxLayout()
        name_label = QLabel("Name:")
        self.name_input = QLineEdit("Points")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        general_layout.addLayout(name_layout)
        
        # Response
        response_layout = QHBoxLayout()
        response_label = QLabel("Response:")
        self.response_input = QLineEdit("$username [$rank] - Hours: $hours - $currencyname: $points")
        response_layout.addWidget(response_label)
        response_layout.addWidget(self.response_input)
        general_layout.addLayout(response_layout)
        
        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_label = QLabel("Cooldown (sec):")
        self.cooldown_slider = QSlider(Qt.Horizontal)
        self.cooldown_slider.setMinimum(0)
        self.cooldown_slider.setMaximum(60)
        self.cooldown_slider.setValue(self.currency_manager.settings.get('cooldown', 5))
        self.cooldown_slider.setTickInterval(1)
        self.cooldown_slider.setTickPosition(QSlider.TicksBelow)
        self.cooldown_slider.valueChanged.connect(self.save_settings)
        
        self.cooldown_value = QLabel(str(self.cooldown_slider.value()))
        self.cooldown_slider.valueChanged.connect(lambda v: self.cooldown_value.setText(str(v)))
        
        cooldown_layout.addWidget(cooldown_label)
        cooldown_layout.addWidget(self.cooldown_slider)
        cooldown_layout.addWidget(self.cooldown_value)
        general_layout.addLayout(cooldown_layout)
          # Rank settings
        rank_layout = QHBoxLayout()
        rank_label = QLabel("Assign ranks based on x amount of")
        self.rank_type = QComboBox()
        self.rank_type.addItems(["Points", "Hours"])
        self.rank_type.setCurrentText(self.currency_manager.settings.get('rank_type', 'Points'))
        self.rank_type.currentTextChanged.connect(self.save_settings)
        rank_suffix = QLabel("gained/spent in chat")
        rank_layout.addWidget(rank_label)
        rank_layout.addWidget(self.rank_type)
        rank_layout.addWidget(rank_suffix)
        rank_layout.addStretch(1)
        general_layout.addLayout(rank_layout)
        
        # Options
        self.offline_hours_check = QCheckBox("Take offline hours in to account for total hours in the stream")
        self.offline_hours_check.setChecked(self.currency_manager.settings.get('offline_hours', False))
        self.offline_hours_check.stateChanged.connect(self.save_settings)
        general_layout.addWidget(self.offline_hours_check)
        
        self.auto_regular_check = QCheckBox("Automatically become a regular at")
        self.auto_regular_check.setChecked(self.currency_manager.settings.get('auto_regular', False))
        self.auto_regular_check.stateChanged.connect(self.save_settings)
        
        auto_regular_layout = QHBoxLayout()
        auto_regular_layout.addWidget(self.auto_regular_check)
        
        self.auto_regular_amount = QSpinBox()
        self.auto_regular_amount.setMinimum(0)
        self.auto_regular_amount.setMaximum(10000)
        self.auto_regular_amount.setValue(self.currency_manager.settings.get('auto_regular_amount', 100))
        self.auto_regular_amount.valueChanged.connect(self.save_settings)
        auto_regular_layout.addWidget(self.auto_regular_amount)
        
        self.auto_regular_type = QComboBox()
        self.auto_regular_type.addItems(["Points", "Hours"])
        self.auto_regular_type.setCurrentText(self.currency_manager.settings.get('auto_regular_type', 'Points'))
        self.auto_regular_type.currentTextChanged.connect(self.save_settings)
        auto_regular_layout.addWidget(self.auto_regular_type)
        auto_regular_layout.addStretch(1)
        general_layout.addLayout(auto_regular_layout)
        
        self.streamlabs_check = QCheckBox("Бесполезная галочка, на которой был Streamlabs")
        self.streamlabs_check.setChecked(self.currency_manager.settings.get('streamlabs_currency', False))
        self.streamlabs_check.stateChanged.connect(self.save_settings)
        general_layout.addWidget(self.streamlabs_check)
        
        general_group.setLayout(general_layout)
        scroll_layout.addWidget(general_group)
        
        # === INTERVALS SECTION ===
        intervals_group = QGroupBox("Intervals")
        intervals_layout = QVBoxLayout()
        
        # Online Interval
        online_layout = QHBoxLayout()
        online_label = QLabel("Online Interval:")
        self.online_interval_slider = QSlider(Qt.Horizontal)
        self.online_interval_slider.setMinimum(1)
        self.online_interval_slider.setMaximum(60)
        self.online_interval_slider.setValue(self.currency_manager.settings.get('online_interval', 5))
        self.online_interval_slider.setTickInterval(5)
        self.online_interval_slider.setTickPosition(QSlider.TicksBelow)
        self.online_interval_slider.valueChanged.connect(self.save_settings)
        self.online_interval_slider.valueChanged.connect(self.update_min_max_labels)
        
        self.online_interval_value = QLabel(f"{self.online_interval_slider.value()}")
        self.online_interval_slider.valueChanged.connect(lambda v: self.online_interval_value.setText(str(v)))
        
        online_layout.addWidget(online_label)
        online_layout.addWidget(self.online_interval_slider)
        online_layout.addWidget(self.online_interval_value)
        intervals_layout.addLayout(online_layout)
          # Offline Interval
        offline_layout = QHBoxLayout()
        offline_label = QLabel("Offline Interval:")
        self.offline_interval_slider = QSlider(Qt.Horizontal)
        self.offline_interval_slider.setMinimum(1)
        self.offline_interval_slider.setMaximum(60)
        self.offline_interval_slider.setValue(self.currency_manager.settings.get('offline_interval', 15))
        self.offline_interval_slider.setTickInterval(5)
        self.offline_interval_slider.setTickPosition(QSlider.TicksBelow)
        self.offline_interval_slider.valueChanged.connect(self.save_settings)
        self.offline_interval_slider.valueChanged.connect(self.update_min_max_labels)
        
        self.offline_interval_value = QLabel(f"{self.offline_interval_slider.value()}")
        self.offline_interval_slider.valueChanged.connect(lambda v: self.offline_interval_value.setText(str(v)))
        offline_layout.addWidget(offline_label)
        offline_layout.addWidget(self.offline_interval_slider)
        offline_layout.addWidget(self.offline_interval_value)
        intervals_layout.addLayout(offline_layout)
        
        # Live/Offline info
        time_info_layout = QHBoxLayout()
        self.time_info_label = QLabel()
        self.time_info_label.setAlignment(Qt.AlignCenter)  # По центру
        self.time_info_label.setText("[LIVE] Min: 0/h - Max: 0/h    [OFFLINE] Min: 0/h - Max: 0/h")
        time_info_layout.addWidget(self.time_info_label)
        intervals_layout.addLayout(time_info_layout)
        
        intervals_group.setLayout(intervals_layout)
        scroll_layout.addWidget(intervals_group)
        
        # === PAYOUT SECTION ===
        payout_group = QGroupBox("Payout")
        payout_layout = QVBoxLayout()
        
        # Live & Offline payout
        live_offline_layout = QHBoxLayout()
        
        # Live payout
        live_layout = QVBoxLayout()
        live_label = QLabel("Live Payout:")
        self.live_payout_input = QSpinBox()
        self.live_payout_input.setRange(0, 100)
        self.live_payout_input.setValue(self.currency_manager.settings.get('live_payout', 5))
        self.live_payout_input.valueChanged.connect(self.save_settings)
        self.live_payout_input.valueChanged.connect(self.update_min_max_labels)
        live_layout.addWidget(live_label)
        live_layout.addWidget(self.live_payout_input)
        live_offline_layout.addLayout(live_layout)
        
        # Offline payout
        offline_layout = QVBoxLayout()
        offline_label = QLabel("Offline Payout:")
        self.offline_payout_input = QSpinBox()
        self.offline_payout_input.setRange(0, 100)
        self.offline_payout_input.setValue(self.currency_manager.settings.get('offline_payout', 0))
        self.offline_payout_input.valueChanged.connect(self.save_settings)
        self.offline_payout_input.valueChanged.connect(self.update_min_max_labels)
        offline_layout.addWidget(offline_label)
        offline_layout.addWidget(self.offline_payout_input)
        live_offline_layout.addLayout(offline_layout)
        
        payout_layout.addLayout(live_offline_layout)
        
        # Bonus payouts
        bonus_layout = QHBoxLayout()
        
        # Regular Bonus
        regular_layout = QVBoxLayout()
        regular_label = QLabel("Regular Bonus:")
        self.regular_bonus_input = QSpinBox()
        self.regular_bonus_input.setRange(0, 100)
        self.regular_bonus_input.setValue(self.currency_manager.settings.get('regular_bonus', 0))
        self.regular_bonus_input.valueChanged.connect(self.save_settings)
        self.regular_bonus_input.valueChanged.connect(self.update_min_max_labels)
        regular_layout.addWidget(regular_label)
        regular_layout.addWidget(self.regular_bonus_input)
        bonus_layout.addLayout(regular_layout)
        
        # Sub Bonus
        sub_layout = QVBoxLayout()
        sub_label = QLabel("Sub Bonus:")
        self.sub_bonus_input = QSpinBox()
        self.sub_bonus_input.setRange(0, 100)
        self.sub_bonus_input.setValue(self.currency_manager.settings.get('sub_bonus', 0))
        self.sub_bonus_input.valueChanged.connect(self.save_settings)
        self.sub_bonus_input.valueChanged.connect(self.update_min_max_labels)
        sub_layout.addWidget(sub_label)
        sub_layout.addWidget(self.sub_bonus_input)
        bonus_layout.addLayout(sub_layout)
        
        # Mod Bonus
        mod_layout = QVBoxLayout()
        mod_label = QLabel("Moderator Bonus:")
        self.mod_bonus_input = QSpinBox()
        self.mod_bonus_input.setRange(0, 100)
        self.mod_bonus_input.setValue(self.currency_manager.settings.get('mod_bonus', 0))
        self.mod_bonus_input.valueChanged.connect(self.save_settings)
        self.mod_bonus_input.valueChanged.connect(self.update_min_max_labels)
        mod_layout.addWidget(mod_label)
        mod_layout.addWidget(self.mod_bonus_input)
        bonus_layout.addLayout(mod_layout)
        
        # Active Bonus
        active_layout = QVBoxLayout()
        active_label = QLabel("Active Bonus:")
        self.active_bonus_input = QSpinBox()
        self.active_bonus_input.setRange(0, 100)
        self.active_bonus_input.setValue(self.currency_manager.settings.get('active_bonus', 1))
        self.active_bonus_input.valueChanged.connect(self.save_settings)
        self.active_bonus_input.valueChanged.connect(self.update_min_max_labels)
        active_layout.addWidget(active_label)
        active_layout.addWidget(self.active_bonus_input)
        bonus_layout.addLayout(active_layout)
        
        payout_layout.addLayout(bonus_layout)
        payout_group.setLayout(payout_layout)
        scroll_layout.addWidget(payout_group)
        
        # === EVENT PAYOUT SECTION ===
        event_group = QGroupBox("Event Payout")
        event_layout = QVBoxLayout()
        
        # First row of event payouts
        event_row1 = QHBoxLayout()
        
        # On Raid
        raid_layout = QVBoxLayout()
        raid_label = QLabel("On Raid:")
        self.raid_payout_input = QSpinBox()
        self.raid_payout_input.setRange(0, 1000)
        self.raid_payout_input.setValue(self.currency_manager.settings.get('raid_payout', 10))
        self.raid_payout_input.valueChanged.connect(self.save_settings)
        raid_layout.addWidget(raid_label)
        raid_layout.addWidget(self.raid_payout_input)
        event_row1.addLayout(raid_layout)
        
        # On Follow
        follow_layout = QVBoxLayout()
        follow_label = QLabel("On Follow:")
        self.follow_payout_input = QSpinBox()
        self.follow_payout_input.setRange(0, 1000)
        self.follow_payout_input.setValue(self.currency_manager.settings.get('follow_payout', 10))
        self.follow_payout_input.valueChanged.connect(self.save_settings)
        follow_layout.addWidget(follow_label)
        follow_layout.addWidget(self.follow_payout_input)
        event_row1.addLayout(follow_layout)
        
        # On Sub
        sub_event_layout = QVBoxLayout()
        sub_event_label = QLabel("On Sub:")
        self.sub_event_payout_input = QSpinBox()
        self.sub_event_payout_input.setRange(0, 1000)
        self.sub_event_payout_input.setValue(self.currency_manager.settings.get('sub_event_payout', 10))
        self.sub_event_payout_input.valueChanged.connect(self.save_settings)
        sub_event_layout.addWidget(sub_event_label)
        sub_event_layout.addWidget(self.sub_event_payout_input)
        event_row1.addLayout(sub_event_layout)
        
        # Mass Sub Gift
        mass_sub_layout = QVBoxLayout()
        mass_sub_label = QLabel("Mass Sub Gift Amount (per Sub):")
        self.mass_sub_payout_input = QSpinBox()
        self.mass_sub_payout_input.setRange(0, 1000)
        self.mass_sub_payout_input.setValue(self.currency_manager.settings.get('mass_sub_payout', 0))
        self.mass_sub_payout_input.valueChanged.connect(self.save_settings)
        mass_sub_layout.addWidget(mass_sub_label)
        mass_sub_layout.addWidget(self.mass_sub_payout_input)
        event_row1.addLayout(mass_sub_layout)
        
        event_layout.addLayout(event_row1)
        
        # Second row of event payouts
        event_row2 = QHBoxLayout()
        
        # On Host
        host_layout = QVBoxLayout()
        host_label = QLabel("On Host:")
        self.host_payout_input = QSpinBox()
        self.host_payout_input.setRange(0, 1000)
        self.host_payout_input.setValue(self.currency_manager.settings.get('host_payout', 0))
        self.host_payout_input.valueChanged.connect(self.save_settings)
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.host_payout_input)
        event_row2.addLayout(host_layout)
        
        # Add empty layouts for alignment
        event_row2.addStretch(1)
        event_row2.addStretch(1)
        event_row2.addStretch(1)
        
        event_layout.addLayout(event_row2)
        event_group.setLayout(event_layout)
        scroll_layout.addWidget(event_group)

        # === BACKUP MANAGEMENT SECTION ===
        backup_group = QGroupBox("Currency Data Backup & Recovery")
        backup_layout = QVBoxLayout()

        # Backup info
        backup_info = QLabel(
            "Automatic backups are created regularly and when major changes occur. "
            "You can manually create backups or restore from existing ones here."
        )
        backup_info.setWordWrap(True)
        backup_layout.addWidget(backup_info)

        # Backup controls
        backup_controls_layout = QHBoxLayout()

        # Create backup button
        self.create_backup_btn = QPushButton("Create Manual Backup")
        self.create_backup_btn.clicked.connect(self.create_manual_backup)
        self.create_backup_btn.setToolTip("Create a backup of the current currency data")
        backup_controls_layout.addWidget(self.create_backup_btn)

        # Refresh backups button
        self.refresh_backups_btn = QPushButton("Refresh List")
        self.refresh_backups_btn.clicked.connect(self.refresh_backup_list)
        backup_controls_layout.addWidget(self.refresh_backups_btn)

        # Backup status
        self.backup_status_label = QLabel("Loading...")
        backup_controls_layout.addWidget(QLabel("Status:"))
        backup_controls_layout.addWidget(self.backup_status_label)
        backup_controls_layout.addStretch()

        backup_layout.addLayout(backup_controls_layout)

        # Backup settings
        backup_settings_layout = QHBoxLayout()
        max_backups_label = QLabel("Maximum Backups:")
        self.max_currency_backups_spin = QSpinBox()
        self.max_currency_backups_spin.setMinimum(1)
        self.max_currency_backups_spin.setMaximum(100)
        self.max_currency_backups_spin.setValue(self.currency_manager.max_currency_backups)
        self.max_currency_backups_spin.valueChanged.connect(self.update_max_currency_backups)
        backup_settings_layout.addWidget(max_backups_label)
        backup_settings_layout.addWidget(self.max_currency_backups_spin)
        backup_settings_layout.addStretch()
        backup_layout.addLayout(backup_settings_layout)

        # Backup list (will be populated when tab is shown)
        self.backup_list_layout = QVBoxLayout()
        self.backup_list_widget = QWidget()
        self.backup_list_widget.setLayout(self.backup_list_layout)
        backup_layout.addWidget(self.backup_list_widget)

        # Initial backup list refresh
        QTimer.singleShot(500, self.refresh_backup_list)

        backup_group.setLayout(backup_layout)
        scroll_layout.addWidget(backup_group)

        # Add spacer at the bottom
        scroll_layout.addStretch(1)
        
        # Set the layout for the scroll content
        scroll_content.setLayout(scroll_layout)
        
        # Add the scroll content to the scroll area
        scroll_area.setWidget(scroll_content)
        
        # Add the scroll area to the main layout
        main_layout.addWidget(scroll_area)
        
        # Set main layout for the tab
        self.setLayout(main_layout)
          # Подключаем обновление после создания слайдеров и полей ввода
        self.live_payout_input.valueChanged.connect(self.update_min_max_labels)
        self.offline_payout_input.valueChanged.connect(self.update_min_max_labels)
        self.online_interval_slider.valueChanged.connect(self.update_min_max_labels)
        self.offline_interval_slider.valueChanged.connect(self.update_min_max_labels)
        self.regular_bonus_input.valueChanged.connect(self.update_min_max_labels)
        self.sub_bonus_input.valueChanged.connect(self.update_min_max_labels)
        self.mod_bonus_input.valueChanged.connect(self.update_min_max_labels)
        self.active_bonus_input.valueChanged.connect(self.update_min_max_labels)
        if hasattr(self, 'offline_active_bonus_check'):
            self.offline_active_bonus_check.stateChanged.connect(self.update_min_max_labels)
            
        # В конце метода initUI() вызываем обновление меток
        self.update_min_max_labels()
        
    def save_settings(self):
        """Save currency settings to file"""
        try:
            # Get settings from UI controls
            settings = {
                # General settings
                'accumulation_enabled': self.accumulation_check.isChecked(),  # New setting for currency accumulation
                'show_service_messages': self.show_service_messages_check.isChecked(),  # Show service messages in chat
                'command': self.command_input.text(),
                'name': self.name_input.text(),
                'response': self.response_input.text(),
                'cooldown': self.cooldown_slider.value(),
                'rank_type': self.rank_type.currentText(),
                'payout_mode': 'per_minute',  # Всегда используем режим per_minute
                'offline_hours': self.offline_hours_check.isChecked(),
                'auto_regular': self.auto_regular_check.isChecked(),
                'auto_regular_amount': self.auto_regular_amount.value(),
                'auto_regular_type': self.auto_regular_type.currentText(),
                'streamlabs_currency': self.streamlabs_check.isChecked(),
                
                # Interval settings
                'online_interval': self.online_interval_slider.value(),
                'offline_interval': self.offline_interval_slider.value(),
                
                # Payout settings
                'live_payout': self.live_payout_input.value(),
                'offline_payout': self.offline_payout_input.value(),
                'regular_bonus': self.regular_bonus_input.value(),
                'sub_bonus': self.sub_bonus_input.value(),
                'mod_bonus': self.mod_bonus_input.value(),
                'active_bonus': self.active_bonus_input.value(),
                
                # Event payouts - используем только один набор настроек
                'raid_payout': self.raid_payout_input.value(),
                'follow_payout': self.follow_payout_input.value(),
                'sub_event_payout': self.sub_event_payout_input.value(),
                'mass_sub_payout': self.mass_sub_payout_input.value(),
                'host_payout': self.host_payout_input.value()
            }
            
            # Update currency manager settings
            self.currency_manager.settings.update(settings)
            
            # Save settings to file
            if hasattr(self.currency_manager, 'save_settings'):
                self.currency_manager.save_settings()
                return True
        except Exception as e:
            print(f"Error saving currency settings: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def update_min_max_labels(self):
        """Update the min/max labels based on current settings"""
        try:
            # Получаем базовые настройки
            live_payout = self.live_payout_input.value()
            online_interval = self.online_interval_slider.value()
            offline_payout = self.offline_payout_input.value()
            offline_interval = self.offline_interval_slider.value()
              # Получаем бонусы
            regular_bonus = self.regular_bonus_input.value()
            sub_bonus = self.sub_bonus_input.value()
            mod_bonus = self.mod_bonus_input.value()
            active_bonus = self.active_bonus_input.value()
            
            # Режим "за минуту": рассчитываем почасовые значения из интервальных
            live_min = (60 / online_interval) * live_payout
            offline_min = (60 / offline_interval) * offline_payout
            live_max = (60 / online_interval) * (live_payout + regular_bonus + sub_bonus + mod_bonus + active_bonus)
            offline_max = (60 / offline_interval) * (offline_payout + regular_bonus + sub_bonus + mod_bonus + active_bonus)
            unit = "/h"
            
            # Округляем значения
            live_min_rounded = round(live_min)
            live_max_rounded = round(live_max)
            offline_min_rounded = round(offline_min)
            offline_max_rounded = round(offline_max)
            
            # Обновляем метку с расчетными значениями
            self.time_info_label.setText(
                f"[LIVE] Min: {live_min_rounded}{unit} - Max: {live_max_rounded}{unit}    "
                f"[OFFLINE] Min: {offline_min_rounded}{unit} - Max: {offline_max_rounded}{unit}"
            )
        except Exception as e:
            print(f"Error updating min/max labels: {e}")
            import traceback
            traceback.print_exc()

    def create_manual_backup(self):
        """Create a manual backup of currency data"""
        try:
            self.create_backup_btn.setEnabled(False)
            self.create_backup_btn.setText("Creating...")

            success = self.currency_manager.create_backup(force=True)

            if success:
                # Refresh the backup list
                self.refresh_backup_list()
                # Update status
                self.backup_status_label.setText("Backup created successfully")
                self.backup_status_label.setStyleSheet("color: green;")
            else:
                self.backup_status_label.setText("Failed to create backup")
                self.backup_status_label.setStyleSheet("color: red;")

        except Exception as e:
            print(f"Error creating manual backup: {e}")
            self.backup_status_label.setText("Error creating backup")
            self.backup_status_label.setStyleSheet("color: red;")
        finally:
            self.create_backup_btn.setEnabled(True)
            self.create_backup_btn.setText("Create Manual Backup")

    def refresh_backup_list(self):
        """Refresh the list of available backups"""
        try:
            from PyQt5.QtWidgets import QFrame, QMessageBox

            # Clear existing backup items
            layout = self.backup_list_layout
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Get available backups
            backups = self.currency_manager.get_available_backups()

            if not backups:
                no_backups_label = QLabel("No backups found. Automatic backups will be created during normal operation.")
                no_backups_label.setStyleSheet("color: gray; font-style: italic;")
                layout.addWidget(no_backups_label)
                self.backup_status_label.setText("No backups")
                self.backup_status_label.setStyleSheet("color: gray;")
                return

            # Update status
            self.backup_status_label.setText(f"{len(backups)} backups available")
            self.backup_status_label.setStyleSheet("color: blue;")

            # Add each backup to the list
            for i, backup in enumerate(backups):
                # Create a frame for this backup item
                backup_frame = QFrame()
                backup_frame.setFrameStyle(QFrame.Box)
                backup_frame.setLineWidth(1)
                backup_frame_layout = QVBoxLayout()

                # Backup info header
                header_layout = QHBoxLayout()

                time_label = QLabel(f"⏰ {backup['readable_time']}")
                time_label.setStyleSheet("font-weight: bold;")
                header_layout.addWidget(time_label)

                size_label = QLabel(f"📊 {backup['size_str']}")
                header_layout.addWidget(size_label)

                users_label = QLabel(f"👥 {backup['user_count']} users")
                header_layout.addWidget(users_label)

                header_layout.addStretch()
                backup_frame_layout.addLayout(header_layout)

                # Backup details
                details_layout = QVBoxLayout()

                if backup['total_points'] != 'Unknown' and backup['total_hours'] != 'Unknown':
                    details_label = QLabel(
                        f"Points: {backup['total_points']}, Hours: {backup['total_hours']}"
                    )
                    details_label.setStyleSheet("color: gray; padding-left: 10px;")
                    details_layout.addWidget(details_label)

                # Buttons layout
                buttons_layout = QHBoxLayout()
                buttons_layout.addSpacing(10)

                # Restore button
                restore_btn = QPushButton("Restore")
                restore_btn.setToolTip(f"Restore currency data from this backup")
                restore_btn.clicked.connect(lambda checked, path=backup['path']: self.restore_from_backup(path))
                buttons_layout.addWidget(restore_btn)

                # View info button
                info_btn = QPushButton("Info")
                info_btn.setToolTip("Show detailed backup information")
                info_btn.clicked.connect(lambda checked, b=backup: self.show_backup_info(b))
                buttons_layout.addWidget(info_btn)

                buttons_layout.addStretch()
                details_layout.addLayout(buttons_layout)

                backup_frame_layout.addLayout(details_layout)
                backup_frame.setLayout(backup_frame_layout)

                # Style the frame
                if i == 0:  # Latest backup
                    backup_frame.setStyleSheet("""
                        QFrame {
                            border: 2px solid #4CAF50;
                            border-radius: 5px;
                            background-color: #f9fff9;
                        }
                    """)
                    latest_label = QLabel("🆕 Latest Backup")
                    latest_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                    backup_frame_layout.insertWidget(0, latest_label)

                layout.addWidget(backup_frame)

                # Add some spacing between items
                layout.addSpacing(5)

        except Exception as e:
            print(f"Error refreshing backup list: {e}")
            error_label = QLabel(f"Error loading backups: {e}")
            error_label.setStyleSheet("color: red;")
            self.backup_list_layout.addWidget(error_label)
            self.backup_status_label.setText("Error")
            self.backup_status_label.setStyleSheet("color: red;")

    def restore_from_backup(self, backup_path):
        """Restore currency data from a backup"""
        try:
            from PyQt5.QtWidgets import QMessageBox

            # Confirm restoration
            reply = QMessageBox.question(
                self,
                "Confirm Restore",
                "This will replace the current currency data with the selected backup.\n\n"
                "An emergency backup will be created first.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            # Perform restoration
            success = self.currency_manager.restore_from_backup(backup_path)

            if success:
                QMessageBox.information(
                    self,
                    "Restore Successful",
                    "Currency data has been successfully restored from backup.\n\n"
                    "The program may need to be restarted for all changes to take effect."
                )

                # Refresh backup list to show any changes
                self.refresh_backup_list()

                # Signal to parent to refresh any currency displays
                if self.parent and hasattr(self.parent, 'user_currency_tab'):
                    self.parent.user_currency_tab.populate_table()

            else:
                QMessageBox.critical(
                    self,
                    "Restore Failed",
                    "Failed to restore currency data from backup.\n\n"
                    "Check the program logs for more details."
                )

        except Exception as e:
            print(f"Error during backup restoration: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred during restoration:\n\n{e}"
            )

    def show_backup_info(self, backup):
        """Show detailed information about a backup"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox

            dialog = QDialog(self)
            dialog.setWindowTitle("Backup Information")
            dialog.setModal(True)

            layout = QVBoxLayout()

            # Basic info
            info_text = f"""
            <h3>Backup Details</h3>

            <p><b>Created:</b> {backup['readable_time']}</p>
            <p><b>Filename:</b> {backup['filename']}</p>
            <p><b>Size:</b> {backup['size_str']}</p>
            <p><b>Users:</b> {backup['user_count']}</p>
            <p><b>Total Points:</b> {backup['total_points']}</p>
            <p><b>Total Hours:</b> {backup['total_hours']}</p>
            """

            info_label = QLabel(info_text)
            info_label.setTextFormat(1)  # Rich text
            layout.addWidget(info_label)

            # Buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)

            dialog.setLayout(layout)
            dialog.exec_()

        except Exception as e:
            print(f"Error showing backup info: {e}")
            QMessageBox.warning(self, "Error", f"Failed to show backup information: {e}")

    def update_max_currency_backups(self, value):
        """Update the maximum number of currency backups to keep"""
        try:
            self.currency_manager.max_currency_backups = value
            if self.parent and hasattr(self.parent, 'config_manager'):
                self.parent.config_manager.set_max_currency_backups(value)
            print(f"Updated max currency backups to: {value}")
        except Exception as e:
            print(f"Error updating max currency backups: {e}")
