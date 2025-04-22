import json
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem,
                           QHeaderView, QMessageBox, QInputDialog, QColorDialog, QComboBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

class RanksTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.ranks = []
        self.ranks_file = "data/ranks.json"
        self.load_ranks()
        self.initUI()
        self.populate_table()

    def load_ranks(self):
        if os.path.exists(self.ranks_file):
            with open(self.ranks_file, "r", encoding="utf-8") as f:
                self.ranks = json.load(f)
        else:
            self.ranks = []

    def save_ranks(self):
        os.makedirs(os.path.dirname(self.ranks_file), exist_ok=True)
        with open(self.ranks_file, "w", encoding="utf-8") as f:
            json.dump(self.ranks, f, indent=4, ensure_ascii=False)

    def initUI(self):
        layout = QVBoxLayout()
        
        # Header and description
        header_layout = QHBoxLayout()
        header_label = QLabel("Stream Ranks Configuration")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)
        layout.addLayout(header_layout)
        
        description = QLabel("Configure ranks based on points, hours or chat messages. Users will automatically receive ranks when they reach the required amount.")
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Ranks table
        self.ranks_table = QTableWidget()
        self.ranks_table.setColumnCount(5)
        self.ranks_table.setHorizontalHeaderLabels(["Rank Name", "Required Amount", "Color", "Group", "Actions"])
        self.ranks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ranks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        
        layout.addWidget(self.ranks_table)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        add_rank_btn = QPushButton("Add Rank")
        add_rank_btn.clicked.connect(self.add_rank)
        buttons_layout.addWidget(add_rank_btn)
        
        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(self.reset_all)
        buttons_layout.addWidget(reset_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)

    def populate_table(self):
        """Populate table with rank data"""
        self.ranks_table.setRowCount(0)
        
        for idx, rank_data in enumerate(self.ranks):
            row = self.ranks_table.rowCount()
            self.ranks_table.insertRow(row)
            
            # Rank name
            self.ranks_table.setItem(row, 0, QTableWidgetItem(rank_data.get('name', 'New Rank')))
            
            # Required amount
            self.ranks_table.setItem(row, 1, QTableWidgetItem(str(rank_data.get('required', 0))))
            
            # Color (displayed as cell color)
            color_item = QTableWidgetItem()
            color = QColor(rank_data.get('color', '#000000'))
            color_item.setBackground(QBrush(color))
            color_item.setForeground(QBrush(QColor(255, 255, 255) if color.lightness() < 128 else QColor(0, 0, 0)))
            color_item.setText(rank_data.get('color', '#000000'))
            self.ranks_table.setItem(row, 2, color_item)
            
            # Group
            self.ranks_table.setItem(row, 3, QTableWidgetItem(rank_data.get('group', 'Viewer')))
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked, idx=idx: self.edit_rank(idx))
            
            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda checked, idx=idx: self.delete_rank(idx))
            
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            
            self.ranks_table.setCellWidget(row, 4, actions_widget)

    def add_rank(self):
        """Add a new rank"""
        name, ok1 = QInputDialog.getText(self, "Add Rank", "Enter rank name:")
        if ok1 and name:
            required, ok2 = QInputDialog.getInt(self, "Required Amount", "Enter required amount:", 0, 0, 1000000)
            if ok2:
                group_dialog = QInputDialog(self)
                group_dialog.setComboBoxItems(["Viewer", "Regular", "Subscriber", "VIP", "Moderator", "Admin"])
                group_dialog.setComboBoxEditable(True)
                group_dialog.setWindowTitle("Group")
                group_dialog.setLabelText("Select or enter group:")
                
                if group_dialog.exec_() == QInputDialog.Accepted:
                    group = group_dialog.textValue()
                    
                    color_dialog = QColorDialog(self)
                    color_dialog.setWindowTitle("Select rank color")
                    
                    if color_dialog.exec_() == QColorDialog.Accepted:
                        color = color_dialog.selectedColor().name()
                        
                        description, ok4 = QInputDialog.getText(self, "Description", "Enter rank description (optional):")
                        
                        rank_data = {
                            'name': name,
                            'required': required,
                            'group': group,
                            'description': description,
                            'color': color
                        }
                        self.ranks.append(rank_data)
                        self.save_ranks()
                        self.populate_table()

    def edit_rank(self, index):
        """Edit an existing rank"""
        if index < 0 or index >= len(self.ranks):
            return
        
        rank_data = self.ranks[index]
        
        name, ok1 = QInputDialog.getText(self, "Edit Rank", "Enter rank name:", 
                                     text=rank_data.get('name', 'New Rank'))
        if ok1:
            required, ok2 = QInputDialog.getInt(self, "Required Amount", "Enter required amount:", 
                                           rank_data.get('required', 0), 0, 1000000)
            if ok2:
                group_dialog = QInputDialog(self)
                group_dialog.setComboBoxItems(["Viewer", "Regular", "Subscriber", "VIP", "Moderator", "Admin"])
                group_dialog.setComboBoxEditable(True)
                group_dialog.setWindowTitle("Group")
                group_dialog.setLabelText("Select or enter group:")
                group_dialog.setTextValue(rank_data.get('group', 'Viewer'))
                
                if group_dialog.exec_() == QInputDialog.Accepted:
                    group = group_dialog.textValue()
                    
                    color_dialog = QColorDialog(self)
                    color_dialog.setCurrentColor(QColor(rank_data.get('color', '#000000')))
                    color_dialog.setWindowTitle("Select rank color")
                    
                    if color_dialog.exec_() == QColorDialog.Accepted:
                        color = color_dialog.selectedColor().name()
                        
                        description, ok4 = QInputDialog.getText(self, "Description", "Enter rank description (optional):", 
                                                         text=rank_data.get('description', ''))
                        
                        rank_data.update({
                            'name': name,
                            'required': required,
                            'group': group,
                            'description': description,
                            'color': color
                        })
                        self.save_ranks()
                        self.populate_table()

    def delete_rank(self, index):
        """Delete a rank"""
        if index < 0 or index >= len(self.ranks):
            return
            
        rank_name = self.ranks[index].get('name', 'this rank')
        reply = QMessageBox.question(self, 'Delete Rank',
                                f"Are you sure you want to delete the rank '{rank_name}'?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            del self.ranks[index]
            self.save_ranks()
            self.populate_table()

    def reset_all(self):
        """Reset all ranks"""
        reply = QMessageBox.question(self, 'Reset Ranks',
                                "Are you sure you want to reset ALL ranks? This action cannot be undone!",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.ranks = []
            self.save_ranks()
            self.populate_table()
            QMessageBox.information(self, "Success", "All ranks have been reset!")