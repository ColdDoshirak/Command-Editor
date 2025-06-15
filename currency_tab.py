import os
import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                           QGroupBox, QSlider, QScrollArea, QSizePolicy, QGridLayout)
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
        scroll_layout = QVBoxLayout(scroll_content)
          # === GENERAL SECTION ===
        general_group = QGroupBox("General")
        general_layout = QVBoxLayout()
        # Currency Accumulation Toggle - добавляем переключатель в начале секции
        self.accumulation_check = QCheckBox("Enable Currency Accumulation")
        self.accumulation_check.setChecked(self.currency_manager.settings.get('accumulation_enabled', True))
        self.accumulation_check.stateChanged.connect(self.save_settings)
        self.accumulation_check.setToolTip("When enabled, users will earn currency while watching the stream")
        general_layout.addWidget(self.accumulation_check)
        
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
            settings = {            # General settings
                'accumulation_enabled': self.accumulation_check.isChecked(),  # New setting for currency accumulation
                'command': self.command_input.text(),
                'name': self.name_input.text(),
                'response': self.response_input.text(),
                'cooldown': self.cooldown_slider.value(),
                'rank_type': self.rank_type.currentText(),
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
            
            # Расчет минимальных значений в час (одинаковый для Live и Offline)
            live_min = (60 / online_interval) * live_payout
            offline_min = (60 / offline_interval) * offline_payout
            
            # Расчет максимальных значений в час, включая все возможные бонусы
            live_max = (60 / online_interval) * (live_payout + regular_bonus + sub_bonus + mod_bonus + active_bonus)
            
            # Для offline максимум также включает все применимые бонусы
            offline_max = (60 / offline_interval) * (offline_payout + regular_bonus + sub_bonus + mod_bonus + active_bonus)
            
            # Округляем значения
            live_min_rounded = round(live_min)
            live_max_rounded = round(live_max)
            offline_min_rounded = round(offline_min)
            offline_max_rounded = round(offline_max)
            
            # Обновляем метку с расчетными значениями
            self.time_info_label.setText(
                f"[LIVE] Min: {live_min_rounded}/h - Max: {live_max_rounded}/h    "
                f"[OFFLINE] Min: {offline_min_rounded}/h - Max: {offline_max_rounded}/h"
            )
        except Exception as e:
            print(f"Error updating min/max labels: {e}")
            import traceback
            traceback.print_exc()