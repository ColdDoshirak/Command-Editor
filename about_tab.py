from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextBrowser, 
                          QTabWidget, QScrollArea, QGroupBox, QHBoxLayout)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QIcon
import datetime
from pathlib import Path
import os
import sys

class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
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
        </ul>

        <h3>What about english tutorial?</h3>
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
        <p><b>Version:</b> 1.1.1</p>
        <p><b>Release Date:</b> 2025-06-16</p>
        <p><b>Framework:</b> PyQt5</p>
        <p><b>Python Version:</b> 3.8+</p>
        
        <p>Дата последнего обновления: {current_date}. Прикол, тут дата сегодняшняя, чтоб свежо было</p>
        """
        
        version_info.setHtml(version_text)
        layout.addWidget(version_info)
        
        return widget