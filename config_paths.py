import os
import sys
from pathlib import Path

class AppPaths:
    """Centralized path management for the Study Timer app"""
    
    APP_NAME = "StudyTimer"
    
    def __init__(self):
        # Determine if we're running as a PyInstaller bundle or regular Python
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            self.app_dir = Path(sys.executable).parent
        else:
            # Running as Python script
            self.app_dir = Path(__file__).parent
            
        # App data directory in %APPDATA%/StudyTimer (for user data only)
        self.appdata_dir = Path(os.environ.get('APPDATA', '')) / self.APP_NAME
        
        # Create app data directory if it doesn't exist
        self.appdata_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for user data only
        (self.appdata_dir / "logs").mkdir(exist_ok=True)
    
    def get_data_file(self, filename):
        """Get path for data files (stored in AppData)"""
        return str(self.appdata_dir / filename)
    
    def get_asset_file(self, filename):
        """Get path for asset files (stored with app executable)"""
        return str(self.app_dir / filename)
    
    def get_log_file(self, filename):
        """Get path for log files"""
        return str(self.appdata_dir / "logs" / filename)
    
    # Data file paths (saved to AppData - user-specific data)
    @property
    def profile_file(self):
        return self.get_data_file("profile.json")
     
    @property
    def integrity_file(self):
        """Integrity verification file"""
        return self.get_data_file(".integrity")
        

    @property
    def backup_file(self):
        """Backup state file"""
        return self.get_data_file(".st_backup")

    @property
    def time_check_file(self):
        """Time check file for tamper detection"""
        return self.get_data_file(".time_check")

    @property
    def trial_data_file(self):
        """Trial version data"""
        return self.get_data_file(".trial_data")

    @property
    def trial_salt_file(self):
        """Trial salt for encryption"""
        return self.get_data_file(".trial_salt")
        
    @property
    def license_file(self):
        """Encrypted license file"""
        return self.get_data_file("app_license.dat")
        
    @property
    def plans_file(self):
        return self.get_data_file("plans.json")

    @property
    def payment_file(self):
        """Payment status file"""
        return self.get_data_file("payment_status.json")

    @property
    def license_salt_file(self):
        """License encryption salt"""
        return self.get_data_file("license.salt")

    @property
    def verify_file_prefix(self):
        """Prefix for verify files: .verify_<machine_id>"""
        return str(self.appdata_dir)  # use with os.path.join

    @property
    def last_runrate_file(self):
        """Last runrate snapshot"""
        return self.get_data_file("last_runrate.jpg")

    @property
    def goal_config_file(self):
        """Goal config file"""
        return self.get_data_file("goal_config.json")

    @property
    def daily_report_file(self):
        """Daily report status file"""
        return self.get_data_file("daily_report_status.json")
    
    @property
    def config_file(self):
        return self.get_data_file("config.json")
    
    @property
    def state_file(self):
        return self.get_data_file("study_session_state.json")
    
    @property
    def wastage_file(self):
        return self.get_data_file("wastage_log.csv")
    
    @property
    def study_total_file(self):
        return self.get_data_file("total_studied_time.json")
    
    @property
    def wastage_day_file(self):
        return self.get_data_file("wastage_by_day.json")
    
    @property
    def study_today_file(self):
        return self.get_data_file("studied_today_time.json")
    
    @property
    def reset_wastage_file(self):
        return self.get_data_file("reset_wastage_sessions.json")
    
    @property
    def custom_schedule_file(self):
        return self.get_data_file("custom_schedule.json")
    
    @property
    def history_log_file(self):
        return self.get_data_file("session_history_log.csv")
    
    @property
    def target_drift_file(self):
        return self.get_data_file("per_day_target_drift.json")
    
    @property
    def last_seen_file(self):
        return self.get_data_file("last_seen_ts.txt")
    
    @property
    def target_thresh_file(self):
        return self.get_data_file("per_day_thresholds.json")
    
    @property
    def pending_report_file(self):
        return self.get_data_file("pending_daily_report.json")
    
    @property
    def snapshot_file(self):
        return self.get_data_file("last_report_snapshot.json")
    
    @property
    def runrate_data_file(self):
        return self.get_data_file("runrate_data.json")
    
    @property
    def week_state_file(self):
        return self.get_data_file("week_state_main.json")
    
    @property
    def exam_date_file(self):
        return self.get_data_file("exam_date.json")
    
    @property
    def gsync_config_file(self):
        return self.get_data_file("gsync_config.json")
    
    @property
    def alarm_settings_file(self):
        return self.get_data_file("alarm_settings.json")
    
    @property
    def opened_days_file(self):
        return self.get_data_file("opened_days.txt")
    
    @property
    def session_history_file(self):
        return self.get_data_file("session_history.csv")
    
    # ✅ UPDATED: Asset directories (bundled with app executable - required for app to function)
    @property
    def avatars_dir(self):
        """Avatar images directory - bundled with app"""
        return str(self.app_dir / "avatars")
    
    @property
    def medals_dir(self):
        """Medal images directory - bundled with app"""
        return str(self.app_dir / "medals")
    
    @property
    def quotes_dir(self):
        """Quotes directory - bundled with app"""
        return str(self.app_dir / "quotes")
    
    @property
    def buttons_dir(self):
        """Button images directory - bundled with app"""
        return str(self.app_dir / "buttons")
    
    @property
    def logo_dir(self):
        """Logo images directory - bundled with app"""
        return str(self.app_dir / "logo")

    def migrate_existing_data(self):
        """Migrate user data files from app dir to AppData (but keep assets with app)"""
        # Only migrate user data files, not asset folders
        data_files = [
            # User data files (migrate to AppData)
            "profile.json", "config.json", "study_session_state.json",
            "wastage_log.csv", "total_studied_time.json", "wastage_by_day.json",
            "studied_today_time.json", "reset_wastage_sessions.json",
            "custom_schedule.json", "session_history_log.csv",
            "per_day_target_drift.json", "last_seen_ts.txt",
            "per_day_thresholds.json", "daily_report_status.json",
            "pending_daily_report.json", "last_report_snapshot.json",
            "runrate_data.json", "week_state_main.json",
            "exam_date.json", "goal_config.json", "gsync_config.json",
            "alarm_settings.json", "opened_days.txt", "session_history.csv",

            # Trial/license/security files (migrate to AppData)
            "app_license.dat", "payment_status.json", "license.salt",
            ".integrity", ".st_backup", ".time_check", ".trial_data", ".trial_salt"
        ]

        migrated_files = []
        for filename in data_files:
            old_path = self.app_dir / filename
            new_path = self.appdata_dir / filename

            if old_path.exists() and not new_path.exists():
                try:
                    import shutil
                    shutil.copy2(old_path, new_path)
                    migrated_files.append(filename)
                except Exception as e:
                    print(f"Failed to migrate {filename}: {e}")

        # ✅ NOTE: Asset directories (avatars, medals, quotes, buttons, logo) 
        # are NOT migrated - they stay with the app executable where they belong

        if migrated_files:
            print(f"Migrated {len(migrated_files)} data files to AppData")

        return migrated_files

    def check_asset_integrity(self):
        """Check if all required asset directories exist with the app"""
        required_assets = ["avatars", "medals", "quotes", "buttons", "logo"]
        missing_assets = []
        
        for asset in required_assets:
            asset_path = self.app_dir / asset
            if not asset_path.exists():
                missing_assets.append(asset)
        
        if missing_assets:
            print(f"⚠  Missing required asset folders: {missing_assets}")
            print(f"📁 Expected location: {self.app_dir}")
            return False
        
        return True

# Global instance
app_paths = AppPaths()

# Convenience functions for backward compatibility
def get_data_file(filename):
    return app_paths.get_data_file(filename)

def get_asset_file(filename):
    return app_paths.get_asset_file(filename)