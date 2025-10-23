from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextBrowser, 
                          QTabWidget, QScrollArea, QGroupBox, QHBoxLayout, 
                          QPushButton, QFrame, QMessageBox, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPixmap, QIcon
import datetime
from pathlib import Path
import os
import sys
import requests
import json
import webbrowser

class UpdateCheckerThread(QThread):
    """Thread for checking updates without blocking the UI"""
    update_available = pyqtSignal(str, str, str)  # new_version, download_url, release_notes
    no_update = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, current_version, github_repo="colddoshirak/Command-Editor"):
        super().__init__()
        self.current_version = current_version
        self.github_repo = github_repo
    
    def run(self):
        """Check for updates on GitHub"""
        try:
            # GitHub API URL for latest release
            api_url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
            
            # Make request with timeout
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            
            # Get version from tag name (remove 'v' prefix if present)
            latest_version = release_data['tag_name'].lstrip('v')
            download_url = release_data['html_url']
            release_notes = release_data.get('body', 'No release notes available.')
            
            # Compare versions
            if self._is_newer_version(latest_version, self.current_version):
                self.update_available.emit(latest_version, download_url, release_notes)
            else:
                self.no_update.emit()
                
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            self.error_occurred.emit("Failed to parse GitHub response")
        except KeyError as e:
            self.error_occurred.emit(f"Unexpected GitHub API response: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {str(e)}")
    
    def _is_newer_version(self, latest, current):
        """Simple version comparison"""
        try:
            # Split versions into components and compare
            latest_parts = [int(x) for x in latest.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            
            # Pad shorter version with zeros
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts.extend([0] * (max_len - len(latest_parts)))
            current_parts.extend([0] * (max_len - len(current_parts)))
            
            return latest_parts > current_parts
        except Exception:
            # Fallback to string comparison if version parsing fails
            return latest != current

class UpdateDialog(QDialog):
    """Dialog to show update information"""
    
    def __init__(self, current_version, new_version, download_url, release_notes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setMinimumSize(500, 400)
        self.download_url = download_url
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title = QLabel(f"New version available: {new_version}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Current vs new version
        version_info = QLabel(f"Current version: {current_version}\nNew version: {new_version}")
        version_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_info)
        
        # Release notes
        notes_label = QLabel("Release Notes:")
        notes_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(notes_label)
        
        notes_text = QLabel(release_notes)
        notes_text.setWordWrap(True)
        notes_text.setStyleSheet("background-color: #f5f5f5; padding: 10px; border-radius: 5px;")
        notes_text.setMaximumHeight(200)
        layout.addWidget(notes_text)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        download_btn = QPushButton("Download Update")
        download_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        download_btn.clicked.connect(self.download_update)
        
        later_btn = QPushButton("Later")
        later_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        later_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(download_btn)
        button_layout.addWidget(later_btn)
        layout.addLayout(button_layout)
    
    def download_update(self):
        """Open download URL in browser"""
        webbrowser.open(self.download_url)
        self.accept()

class UpdateChecker:
    """Main update checker class"""
    
    def __init__(self, parent=None, github_repo="colddoshirak/Command-Editor"):
        self.parent = parent
        self.github_repo = github_repo
        self.current_version = "V1.1.2"  # Default version, will be updated from about tab
        self.notification_widget = None
        self.check_button = None  # Reference to the check button for resetting state
        
    def set_notification_widget(self, widget):
        """Set the notification widget for displaying updates"""
        self.notification_widget = widget
        
    def set_current_version(self, version):
        """Set the current version of the application"""
        self.current_version = version
    
    def set_check_button(self, button):
        """Set the check button for state management"""
        self.check_button = button
    
    def check_for_updates(self, silent=False):
        """Start checking for updates"""
        self.silent = silent
        
        # Create and start the update checker thread
        self.update_thread = UpdateCheckerThread(self.current_version, self.github_repo)
        self.update_thread.update_available.connect(self._on_update_available)
        self.update_thread.no_update.connect(self._on_no_update)
        self.update_thread.error_occurred.connect(self._on_error)
        self.update_thread.finished.connect(self._on_check_finished)  # Reset button state
        self.update_thread.start()
    
    def _on_update_available(self, new_version, download_url, release_notes):
        """Handle when update is available"""
        # Show notification widget if available and this is a silent check
        if self.notification_widget and self.silent:
            self.notification_widget.show_notification(new_version, download_url)
        
        # Show dialog if not silent
        if not self.silent:
            dialog = UpdateDialog(                self.current_version, 
                new_version, 
                download_url, 
                release_notes, 
                self.parent
            )
            dialog.exec_()
    
    def _on_no_update(self):
        """Handle when no update is available"""
        if not self.silent:
            QMessageBox.information(
                self.parent, 
                "No Updates", 
                f"You are running the latest version ({self.current_version})"
            )
    
    def _on_error(self, error_message):
        """Handle errors during update check"""
        if not self.silent:
            QMessageBox.warning(
                self.parent, 
                "Update Check Failed", 
                f"Failed to check for updates:\n{error_message}"
            )
    
    def _on_check_finished(self):
        """Handle when update check is finished (reset button state)"""
        if self.check_button and not self.silent:
            self.check_button.setEnabled(True)
            self.check_button.setText("Check for Updates")

class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.parent = parent
        self.current_version = "V1.1.3"  # Store current version
        
        # Initialize update checker
        self.update_checker = UpdateChecker(parent=self)
        self.update_checker.set_current_version(self.current_version)
        
        # Create main layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create tab widget for different sections
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # Add About Me tab
        about_me_widget = self.create_about_me_tab()
        tab_widget.addTab(about_me_widget, "About Me")
        
        # Add Instructions tab
        instructions_widget = self.create_instructions_tab()
        tab_widget.addTab(instructions_widget, "Instructions")
        
        # Add Version Info tab
        version_widget = self.create_version_tab()
        tab_widget.addTab(version_widget, "Version Info")
    
    def create_about_me_tab(self):
        """Create the About Me section"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Header
        header = QLabel("About Developer")
        header.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
        # Personal info
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        
        about_text = """
        <h2 style="text-align: center;">govnocoded by HotDoshirak</h2>
        
        <p>I made this app to replace Streamlabs Chatbot command functionality on Windows 7. It's trash code, most of functionality is not working.</p>
        
        <ul>
            <li>Twitch: <a href="https://twitch.tv/HotDoshirak">https://twitch.tv/HotDoshirak</a></li>
            <li>GitHub: <a href="https://github.com/colddoshirak">https://github.com/colddoshirak</a></li>
            <li>Donate: <a href="https://www.donationalerts.com/r/hotdoshirak1">https://www.donationalerts.com/r/hotdoshirak1</a></li>
        </ul>
        
        <p>Made in 2025 with ai lol</p>
        """
        
        text_browser.setHtml(about_text)
        layout.addWidget(text_browser)
        
        # Add meme gallery
        meme_group = QGroupBox("Meme Gallery")
        meme_layout = QVBoxLayout()
        meme_group.setLayout(meme_layout)
        
        # Create scrollable area for memes with horizontal scroll
        meme_scroll = QScrollArea()
        meme_scroll.setWidgetResizable(True)
        meme_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        meme_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Remove vertical scrollbar
        
        # Container for memes
        meme_container = QWidget()
        meme_container_layout = QVBoxLayout()
        meme_container.setLayout(meme_container_layout)
        
        # Load and display memes
        self.load_memes(meme_container_layout)
        
        meme_scroll.setWidget(meme_container)
        meme_layout.addWidget(meme_scroll)
        
        layout.addWidget(meme_group)
        
        return widget
    
    def get_resource_path(self, relative_path):
        """Get the correct path for resources whether running as script or frozen exe"""
        if getattr(sys, 'frozen', False):
            # If the application is run as a bundle (PyInstaller)
            base_path = sys._MEIPASS
        else:
            # If running as a script
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(base_path, relative_path)
    
    def load_memes(self, layout):
        """Load and display memes from the memes directory"""
        try:
            # Path to memes directory (packaged with PyInstaller)
            memes_dir = self.get_resource_path('memes')
            
            # Get all image files
            meme_files = []
            
            # Check if directory exists
            if not os.path.exists(memes_dir):
                placeholder = QLabel("Meme directory not found! Images should be in 'memes' folder.")
                placeholder.setAlignment(Qt.AlignCenter)
                layout.addWidget(placeholder)
                return
                
            # Look for image files
            for root, dirs, files in os.walk(memes_dir):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                        meme_files.append(os.path.join(root, file))
            
            if not meme_files:
                # Display message if no meme images found
                placeholder = QLabel("No meme images found in 'memes' folder!")
                placeholder.setAlignment(Qt.AlignCenter)
                layout.addWidget(placeholder)
                return
            
            # Create horizontal layout for memes
            meme_row = QHBoxLayout()
            
            # Display each meme in a horizontal row
            for meme_file in meme_files:
                try:
                    # Create label for the image
                    image_label = QLabel()
                    pixmap = QPixmap(meme_file)
                    
                    # Check if pixmap loaded successfully
                    if pixmap.isNull():
                        continue
                        
                    # Scale image if too large, preserving aspect ratio
                    max_height = 200  # Maximum height for the images
                    if pixmap.height() > max_height:
                        pixmap = pixmap.scaledToHeight(max_height, Qt.SmoothTransformation)
                            
                    image_label.setPixmap(pixmap)
                    image_label.setAlignment(Qt.AlignCenter)
                    
                    # Add spacing around image
                    image_label.setMargin(5)
                    
                    # Add to layout
                    meme_row.addWidget(image_label)
                except Exception as e:
                    print(f"Error loading meme image {meme_file}: {str(e)}")
                    continue
            
            # Only add the row if images were successfully loaded
            if meme_row.count() > 0:
                # Add stretches at the beginning and end to center the images
                meme_row.addStretch()
                meme_row.insertStretch(0)
                
                # Add the horizontal row to the main layout
                layout.addLayout(meme_row)
            else:
                # No images could be loaded
                placeholder = QLabel("Could not load any meme images!")
                placeholder.setAlignment(Qt.AlignCenter)
                layout.addWidget(placeholder)
                
        except Exception as e:
            print(f"Error loading meme gallery: {e}")
            placeholder = QLabel("Error loading meme gallery")
            placeholder.setAlignment(Qt.AlignCenter)
            layout.addWidget(placeholder)

    def create_instructions_tab(self):
        """Create the Instructions section"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        
        layout = QVBoxLayout(content_widget)
        
        # Header
        header = QLabel("Instructions")
        header.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
        # Instructions content
        instructions_text = QTextBrowser()
        instructions_text.setOpenExternalLinks(True)
        
        instructions_html = """
        <h2>Руководство по использованию</h2>

        <h2>Высока вероятность, что инструкция переедет в Wiki на Github.</h2>

        <h3>Как работать с этим ааа помогите</h3>
        <p>Сейчас объясню</p>
        <ul>
            <li><b>В Streamlabs Chatbot нужно экспортировать команды (правой кнопкой мыши по одной из команд - export by group, так удобнее)</li>
            <li><b>Если групп несколько... Ну это грустно, я не проверял, лучше одну группу.</li>
            <li><b>Load File</b> - Загрузить команды из бекапа команд. После этого создаётся новый файл с командами в новом формате.</li>
            <li><b>Save File</b> - Сохранить команды в файл. Также сохраняется раз в 300 секунд. Также сохраняется после закрытия программы.</li>
            <li><b>Save Legacy Format</b> - Сохранить в старом формате, хрень, нужно удалить. Вызовет жуткую несовместимость со Streamlabs Chatbot</li>
            <li><b>Auto-Assign Sounds</b> - Автоматически назначить звуковые файлы для команд. Нужно выбрать папку со звуковыми файлами. Работает только с одинаковыми названиями (!command -> !command.mp3/wav)</li>
            <li><b>Add/Remove Command</b> - Добавить, удалить выбранную команду. Ну это хотя бы работает.</li>
            <li><b>Play Sound</b> - Проигрывает/останавливает звуковую команду. Работает даже с ботом.</li>
            <li><b>Allow sounds to interrupt each other</b> - Позволяет перебивать другие звуки или запретить это делать. Да начнётся спам.</li>
            <li><b>Show message when sound blocked</b> - Отображает предупреждение о том, что звук ещё играет. Ну чтоб спамеры поняли, что это не баг, а фича.</li>
            <li><b>Search</b> - Да где же эта команда. Нашёл. Всего-то нужно в строку ввести название команды</li>
            <li><b>History</b> - Когда-то случилась ошибка ценой в 20 часов. <b>Я ОТКАЗЫВАЮСЬ ОТ ОШИБКИ. (поставь побольше бекапов)</b></li>
            <li><b>NEW Currency Settings</b> - Милорд, казна пустеет. Народ устроил анархию. В общем, тут все настройки для системы очков. (как обычно что-то не работает)</li>
            <li><b>NEW Currency Users</b> - Список гениев, миллиардеров, плейбоев, филантропов. Ну если что тут же можно лишить их этих достоинств.</li>
            <li><b>NEW Ranks - пока бесполезная функция, не работает, может в будущем починю. Заменяет ранг на нужном количестве очков.</li>
        </ul>

        <h3>А где бот аааа</h3>
        <p>Сейчас объясню</p>
        <ul>
            <li><b>Есть вкладка Twitch, там можно настроить подключение к каналу.</li>
            <li><b>Токен берём с Twitch Token Generator, я не богатый, чтобы свой хост поднимать, который сам будет всё делать.</li>
            <li><b>Сохранить не забудь и подключиться. Подключаться надо всегда при запуске программы.</li>
            <li><b>NEW Автоматическое переподключение при разрыве соединения.</li>
            <li><b>NEW Список зрителей, активных чаттеров, модераторов. Необходима повторная авторизация после обновления.</li>
            <li><b>NEW Состояние стрима. Необходима повторная авторизация после обновления.</li>
        </ul>

        <h3>Про остальное</h3>
        <p>:)</p>
        <ul>
            <li><b>Значения менять можно только вручную, в таблице. Под таблицей так, просто посмотреть, или скопировать значения.</li>
            <li><b>Менять обычно надо soundfile или cooldown(в минутах)</li>
            <li><b>Нормально работает только ползунок громкости. lolDu</li>
            <li><b>Как же он был неправ, оказывается новые фичи работают как надо.</li>
            <li><b>Теперь программа безопасно сохраняет настройки при включенном боте.</li>
            <li><b>Работают как звуковые команды, так и ответы на команду через response. Для этого даже целый чат есть. Как будто второго чата нет</li>
            <li><b>Когда-нибудь может быть возможно маловероятно но вполне реально что скорее всего я вряд ли буду это обновлять, это же говнокод. (ага, так я тебе и поверил прошлый я)</li>
            <li><b>В currency settings не работает смена команды. Также 100% не работает награда за follow, sub, raid. Зато работает Regular и Mod bonus.</li>
            <li><b>Всё надо чинить, вообще всё , пока работает как-то, не понятно каким вообще образом.</li>
            <li><b>Надо сделать вики на гитхабе, а то как-то уже много копится</li>
        </ul>        <h3>What about english tutorial?</h3>
        <p>Use google translate, i'm too lazy to make buttons for that. Or check readme.md in repository.</p>
        """
        
        instructions_text.setHtml(instructions_html)
        layout.addWidget(instructions_text)
        
        return scroll_area
    
    def create_version_tab(self):
        """Create the Version Info section"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Header
        header = QLabel("Version Information")
        header.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)
        
        # Version info
        version_info = QTextBrowser()
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        version_text = f"""
        <h3 style="text-align: center;">Command Editor</h3>
        
        <p><b>Application:</b> Twitch Bot Command Editor</p>
        <p><b>Version:</b> {self.current_version}</p>
        <p><b>Release Date:</b> 2025-10-23</p>
        <p><b>Framework:</b> PyQt5</p>
        <p><b>Python Version:</b> 3.8+</p>
        
        <p>Дата последнего обновления: {current_date}. Прикол, тут дата сегодняшняя, чтоб свежо было</p>
        """
        
        version_info.setHtml(version_text)
        layout.addWidget(version_info)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Update section
        update_section = QGroupBox("Updates")
        update_layout = QVBoxLayout()
        update_section.setLayout(update_layout)
        
        # Update info label
        update_info = QLabel("Check for updates from GitHub repository")
        update_info.setAlignment(Qt.AlignCenter)
        update_layout.addWidget(update_info)
        
        # Update button layout
        button_layout = QHBoxLayout()
        
        # Check for updates button
        self.check_updates_btn = QPushButton("Check for Updates")
        self.check_updates_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }        """)
        self.check_updates_btn.clicked.connect(self.check_for_updates)
        
        # Set the button reference in update checker
        self.update_checker.set_check_button(self.check_updates_btn)
        
        # Open GitHub button
        github_btn = QPushButton("Open GitHub Repository")
        github_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }        """)
        github_btn.clicked.connect(self.open_github)
        
        button_layout.addWidget(self.check_updates_btn)
        button_layout.addWidget(github_btn)
        update_layout.addLayout(button_layout)
        
        layout.addWidget(update_section)
        
        return widget
    
    def check_for_updates(self):
        """Check for updates from GitHub"""
        self.check_updates_btn.setEnabled(False)
        self.check_updates_btn.setText("Checking...")
        
        # Start checking for updates
        self.update_checker.check_for_updates(silent=False)
    
    def open_github(self):
        """Open GitHub repository in browser"""
        import webbrowser
        webbrowser.open("https://github.com/colddoshirak/Command-Editor")