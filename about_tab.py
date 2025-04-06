from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextBrowser, 
                          QTabWidget, QScrollArea, QGroupBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QIcon
import datetime

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
        </ul>
        
        <p>Made in 2025 with ai lol</p>
        """
        
        text_browser.setHtml(about_text)
        layout.addWidget(text_browser)
        
        return widget
    
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
        </ul>

        <h3>А где бот аааа</h3>
        <p>Сейчас объясню</p>
        <ul>
            <li><b>Есть вкладка Twitch, там можно настроить подключение к каналу.</li>
            <li><b>Токен берём с Twitch Token Generator, я не богатый, чтобы свой хост поднимать, который сам будет всё делать.</li>
            <li><b>Сохранить не забудь и подключиться. Подключаться надо всегда при запуске программы.</li>
        </ul>

        <h3>Про остальное</h3>
        <p>:)</p>
        <ul>
            <li><b>Значения менять можно только вручную, в таблице. Под таблицей так, просто посмотреть, или скопировать значения.</li>
            <li><b>Менять обычно надо soundfile или cooldown(в минутах)</li>
            <li><b>Нормально работает только ползунок громкости. lolDu</li>
            <li><b>Работают как звуковые команды, так и ответы на команду через response. Для этого даже целый чат есть. Как будто второго чата нет</li>
            <li><b>Когда-нибудь может быть возможно маловероятно но вполне реально что скорее всего я вряд ли буду это обновлять, это же говнокод</li>
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
        <h3 style="text-align: center;">Command Editor v1.0.0</h3>
        
        <p><b>Application:</b> Twitch Bot Command Editor</p>
        <p><b>Version:</b> 1.0.0</p>
        <p><b>Release Date:</b> 2023-11-15</p>
        <p><b>Framework:</b> PyQt5</p>
        <p><b>Python Version:</b> 3.8+</p>
        
        <p>Дата последнего обновления: {current_date}. Прикол, тут дата сегодняшняя, чтоб свежо было</p>
        """
        
        version_info.setHtml(version_text)
        layout.addWidget(version_info)
        
        return widget