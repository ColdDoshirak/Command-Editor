# -*- coding: utf-8 -*-
"""The update banner shown at the top of the main window.

Python 3.8 / PyQt5.
"""
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, QTimer
import webbrowser
from ui.i18n import tr


class UpdateNotificationWidget(QLabel):
    """A notification widget that appears in the top-right corner when an update is available"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.download_url = ""
        self.new_version = ""
          # Setup the widget
        self.setup_ui()
        self.hide()  # Initially hidden
        
    def setup_ui(self):
        """Setup the notification UI"""
        self.setFixedSize(180, 35)  # Сделаем меньше: 180x35 вместо 220x50
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        
        # Style the notification
        self.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                border: 2px solid #45a049;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
                padding: 4px;
            }
            QLabel:hover {
                background-color: #45a049;
                border-color: #3d8b40;
            }
        """)
          # Set initial text
        self.setText(tr("🔄 Update available"))  # Более короткий начальный текст
          # Enable word wrap
        self.setWordWrap(True)
        
    def show_notification(self, new_version, download_url):
        """Show the notification with version info"""
        self.new_version = new_version
        self.download_url = download_url
        self.setText(tr('🔄 v{0} available').format(new_version))  # Более короткий текст
        
        # Position in top-right corner
        self.update_position()
        
        # Show the notification
        self.show()
        self.raise_()
        
        # Auto-hide after 8 seconds (уменьшим время)
        QTimer.singleShot(8000, self.hide)
        
    def update_position(self):
        """Update position to stay in top-right corner"""
        if self.parent_widget:
            parent_rect = self.parent_widget.rect()
            x = parent_rect.width() - self.width() - 10
            y = 10
            self.move(x, y)
            
    def mousePressEvent(self, event):
        """Handle click events"""
        if event.button() == Qt.LeftButton:
            if self.download_url:
                webbrowser.open(self.download_url)
            self.hide()
        super().mousePressEvent(event)
        
    def resizeEvent(self, event):
        """Handle parent widget resize"""
        super().resizeEvent(event)
        if self.isVisible():
            self.update_position()
            
    def enterEvent(self, event):
        """Handle mouse enter - show tooltip"""
        self.setToolTip(tr('New version {0} is available!\nClick to open download page').format(self.new_version))
        super().enterEvent(event)
