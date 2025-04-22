import json
import os
import time
from datetime import datetime
import shutil

class HistoryManager:
    def __init__(self, max_backups=100):
        """Initialize History Manager
        
        Args:
            max_backups (int): Maximum number of backup files to keep
        """
        self.max_backups = max_backups
        self.history_folder = "command_history"
        
        # Create history folder if it doesn't exist
        if not os.path.exists(self.history_folder):
            os.makedirs(self.history_folder)
    
    def save_backup(self, commands):
        """Save a backup of the current commands
        
        Args:
            commands (list): The commands to backup
        """
        # Generate timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(self.history_folder, f"commands_{timestamp}.json")
        
        # Save the backup
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=4, ensure_ascii=False)
            
            # Manage the number of backups
            self._cleanup_old_backups()
            return True
        except Exception as e:
            print(f"Error saving backup: {e}")
            return False
    
    def get_backups(self):
        """Get list of available backups
        
        Returns:
            list: List of backup files with their timestamps
        """
        backups = []
        for file in os.listdir(self.history_folder):
            if file.startswith("commands_") and file.endswith(".json"):
                file_path = os.path.join(self.history_folder, file)
                timestamp = os.path.getmtime(file_path)
                readable_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                
                # Get file size in KB
                size_kb = round(os.path.getsize(file_path) / 1024, 2)
                
                # Extract timestamp from filename for sorting
                file_timestamp = file.replace("commands_", "").replace(".json", "")
                
                backups.append({
                    "filename": file,
                    "path": file_path,
                    "timestamp": timestamp,
                    "readable_time": readable_time,
                    "size": size_kb,
                    "file_timestamp": file_timestamp
                })
        
        # Sort by timestamp (newest first)
        return sorted(backups, key=lambda x: x["file_timestamp"], reverse=True)
    
    def restore_backup(self, backup_path):
        """Restore commands from a backup file
        
        Args:
            backup_path (str): Path to the backup file
        
        Returns:
            list: The restored commands, or None if failed
        """
        try:
            # Create a backup of current commands before restoring
            if os.path.exists("commands.json"):
                shutil.copy("commands.json", "commands_before_restore.json")
            
            # Load and return the backed-up commands
            with open(backup_path, 'r', encoding='utf-8') as f:
                commands = json.load(f)
            return commands
        except Exception as e:
            print(f"Error restoring backup: {e}")
            return None
    
    def _cleanup_old_backups(self):
        """Remove old backups if we exceed the maximum number"""
        backups = self.get_backups()
        if len(backups) > self.max_backups:
            # Remove oldest backups
            for backup in backups[self.max_backups:]:
                try:
                    os.remove(backup["path"])
                except Exception as e:
                    print(f"Error removing old backup {backup['path']}: {e}")