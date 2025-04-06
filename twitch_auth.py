from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QLineEdit, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
import json
import os
from config_manager import ConfigManager

class TwitchAuthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Twitch Authentication")
        self.setModal(True)
        
        # Initialize config manager
        self.config_manager = ConfigManager()
        
        # Load saved tokens
        twitch_config = self.config_manager.get_twitch_config()
        
        # Create layout
        layout = QVBoxLayout()
        
        # Add token input fields
        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText("Enter Client ID")
        self.client_id_edit.setText(twitch_config.get('client_id', ''))
        layout.addWidget(QLabel("Client ID:"))
        layout.addWidget(self.client_id_edit)
        
        self.access_token_edit = QLineEdit()
        self.access_token_edit.setPlaceholderText("Enter Access Token")
        self.access_token_edit.setText(twitch_config.get('access_token', ''))
        layout.addWidget(QLabel("Access Token:"))
        layout.addWidget(self.access_token_edit)
        
        self.refresh_token_edit = QLineEdit()
        self.refresh_token_edit.setPlaceholderText("Enter Refresh Token")
        self.refresh_token_edit.setText(twitch_config.get('refresh_token', ''))
        layout.addWidget(QLabel("Refresh Token:"))
        layout.addWidget(self.refresh_token_edit)
        
        # Add help text
        help_label = QLabel("How to get these tokens: Visit twitchtokengenerator.com and generate a token with 'chat:read chat:edit' permissions")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Add a button to open token generator
        token_gen_btn = QPushButton("Open Twitch Token Generator")
        token_gen_btn.clicked.connect(self.open_token_generator)
        layout.addWidget(token_gen_btn)
        
        # Add buttons
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_tokens)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def save_tokens(self):
        """Save tokens to config"""
        try:
            # Get values from input fields
            client_id = self.client_id_edit.text().strip()
            access_token = self.access_token_edit.text().strip()
            refresh_token = self.refresh_token_edit.text().strip()
            
            # Validate required fields
            if not client_id:
                QMessageBox.warning(self, "Error", "Client ID is required!")
                return
                
            if not access_token:
                QMessageBox.warning(self, "Error", "Access Token is required!")
                return
                
            # Refresh token is optional
            
            # Save all credentials using the new method that stores them in a separate file
            success = self.config_manager.save_twitch_config(
                access_token=access_token,
                client_id=client_id,
                refresh_token=refresh_token if refresh_token else None
            )
            
            if success:
                QMessageBox.information(self, "Success", "Twitch credentials saved successfully!")
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Failed to save credentials")
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save credentials: {str(e)}")
            
    def open_token_generator(self):
        """Open Twitch Token Generator in browser"""
        QDesktopServices.openUrl(QUrl("https://twitchtokengenerator.com/"))
        
    def accept(self):
        """Handle dialog acceptance"""
        # This method is overridden to prevent automatic saving
        super().accept() 