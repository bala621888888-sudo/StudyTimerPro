import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import os
import sys
import subprocess
import threading
import tempfile
import time
import re
from secrets_util import get_secret, ONLINE

class SimpleAutoUpdater:
    def __init__(self, current_version="1.0"):
        self.current_version = current_version
        
        # ✅ Reuse existing LB_SHEET_ID (already stored in secrets or env)
        sheet_id = get_secret("LB_SHEET_ID") or os.getenv("LB_SHEET_ID")

        if sheet_id:
            self.update_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json&sheet=Updates"
            print(f"[UPDATE] Using LB_SHEET_ID for updates: {sheet_id}")
        else:
            self.update_url = None
            print("[UPDATE] ❌ LB_SHEET_ID not found — skipping update check")
        # Where to download files
        self.download_folder = tempfile.gettempdir() + "\\StudyTimer_Updates"
        os.makedirs(self.download_folder, exist_ok=True)
        
        # Track dialog states to prevent multiple dialogs
        self.dialog_open = False
        self.master_window = None
        
        print(f"[UPDATE] Initialized updater with version {self.current_version}")
    
    def check_for_updates(self, show_dialog=True):
        """Check if there's a new version available"""
        try:
            print(f"[UPDATE] Checking for updates... Current version: {self.current_version}")
            
            # Get data from Google Sheet
            response = requests.get(self.update_url, timeout=10)
            if response.status_code != 200:
                print(f"[UPDATE] HTTP Error: {response.status_code}")
                if show_dialog:
                    messagebox.showerror("Update Check", "Could not check for updates.")
                return False, None
            
            # Parse the response
            versions = self.parse_sheet_data(response.text)
            if not versions:
                print("[UPDATE] No versions found in sheet")
                if show_dialog:
                    messagebox.showinfo("Update Check", "No version information found.")
                return False, None
            
            print(f"[UPDATE] Found versions: {list(versions.keys())}")
            
            # Find the latest version
            latest_version = self.get_latest_version(versions)
            print(f"[UPDATE] Current: {self.current_version}, Latest: {latest_version}")
            
            # Check if update is needed
            if self.is_newer_version(latest_version, self.current_version):
                update_info = versions[latest_version]
                print(f"[UPDATE] Update available: {latest_version}")
                print(f"[UPDATE] Download URL: {update_info['download_url']}")
                
                if show_dialog and not self.dialog_open:
                    print("[UPDATE] Showing update dialog...")
                    self.show_update_dialog(update_info)
                return True, update_info
            else:
                print("[UPDATE] No update needed")
                if show_dialog:
                    messagebox.showinfo("StudyTimer", "You have the latest version!")
                return False, None
        
        except Exception as e:
            print(f"[UPDATE] Error: {e}")
            import traceback
            traceback.print_exc()
            if show_dialog:
                messagebox.showerror("Update Error", f"Could not check for updates: {e}")
            return False, None
            
    def should_check_update_on_startup(self):
        """Check if we should check for updates on startup based on profile"""
        try:
            if not self.profile_path:
                print("[UPDATE] No profile path provided, skipping startup check")
                return False
            
            if not os.path.exists(self.profile_path):
                print(f"[UPDATE] Profile file not found: {self.profile_path}")
                return False
            
            # Read profile file
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            
            # Check if referral_prompt_shown exists
            if 'referral_prompt_shown' in profile:
                print("[UPDATE] referral_prompt_shown found in profile - will check for updates")
                return True
            else:
                print("[UPDATE] referral_prompt_shown NOT found in profile - skipping startup check")
                return False
                
        except Exception as e:
            print(f"[UPDATE] Error reading profile: {e}")
            return False
    
    def parse_sheet_data(self, response_text):
        """Convert Google Sheet response to version info"""
        try:
            # Extract JSON from Google's response
            start = response_text.find('(') + 1
            end = response_text.rfind(')')
            json_data = response_text[start:end]
            
            data = json.loads(json_data)
            rows = data['table']['rows']
            
            versions = {}
            # Process all rows (no header skip since your data starts from row 1)
            for i, row in enumerate(rows):
                if len(row['c']) >= 4 and row['c'][0]:  # Make sure we have data
                    version = str(row['c'][0]['v']) if row['c'][0] else None
                    download_url = str(row['c'][1]['v']) if row['c'][1] else None
                    release_date = str(row['c'][2]['v']) if row['c'][2] else None
                    release_notes = str(row['c'][3]['v']) if row['c'][3] else ""
                    
                    print(f"[UPDATE] Row {i}: Version={version}, URL={download_url}")
                    
                    if version and download_url:
                        # Convert Google Drive URL to direct download
                        direct_url = self.make_download_url(download_url)
                        
                        versions[version] = {
                            "version": version,
                            "download_url": direct_url,
                            "release_date": release_date,
                            "release_notes": release_notes
                        }
            
            print(f"[UPDATE] Parsed versions: {versions}")
            return versions
            
        except Exception as e:
            print(f"[UPDATE] Parse error: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def make_download_url(self, drive_url):
        """Convert Google Drive share URL to direct download URL"""
        print(f"[UPDATE] Converting URL: {drive_url}")
        
        # Extract file ID from Google Drive URL
        if '/file/d/' in drive_url:
            file_id = drive_url.split('/file/d/')[1].split('/')[0]
            # Use the confirm parameter to bypass virus scan for large files
            direct_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=1"
            print(f"[UPDATE] Direct URL: {direct_url}")
            return direct_url
        return drive_url
    
    def get_latest_version(self, versions):
        """Find the highest version number"""
        def version_key(version_str):
            try:
                return [int(x) for x in version_str.split('.')]
            except:
                return [0]
        
        latest = max(versions.keys(), key=version_key)
        print(f"[UPDATE] Latest version determined: {latest}")
        return latest
    
    def is_newer_version(self, latest, current):
        """Check if latest version is newer than current"""
        try:
            # Remove "version" prefix if present (case-insensitive)
            latest_clean = re.sub(r'^version\s+', '', latest.strip(), flags=re.IGNORECASE)
            current_clean = re.sub(r'^version\s+', '', current.strip(), flags=re.IGNORECASE)
            
            latest_parts = [int(x) for x in latest_clean.split('.')]
            current_parts = [int(x) for x in current_clean.split('.')]
            result = latest_parts > current_parts
            print(f"[UPDATE] Version comparison: {latest} > {current} = {result}")
            return result
        except Exception as e:
            print(f"[UPDATE] Version comparison failed: {e}, assuming no update needed")
            return False
    
    def show_update_dialog(self, update_info):
        """Show the mandatory update dialog"""
        if self.dialog_open:
            print("[UPDATE] Dialog already open, skipping...")
            return
            
        self.dialog_open = True
        print(f"[UPDATE] Showing MANDATORY update dialog for version {update_info['version']}")
        
        try:
            # Ensure we have a proper root window
            root_window = self.master_window
            if not root_window:
                try:
                    root_window = tk._default_root
                    if not root_window or not root_window.winfo_exists():
                        root_window = tk.Tk()
                        root_window.withdraw()
                except:
                    root_window = tk.Tk()
                    root_window.withdraw()
            
            # Create dialog
            dialog = tk.Toplevel(root_window)
            dialog.title("StudyTimer - Mandatory Update Required")
            dialog.geometry("500x500")
            dialog.resizable(False, False)
            
            # Make dialog modal and prevent closing
            dialog.lift()
            dialog.attributes('-topmost', True)
            dialog.focus_force()
            dialog.grab_set()
            
            # Disable the close button (X)
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Do nothing when X is clicked
            
            # Center the window
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
            y = (dialog.winfo_screenheight() // 2) - (500 // 2)
            dialog.geometry(f"500x500+{x}+{y}")
            
            # Title with warning color
            title_frame = tk.Frame(dialog, bg='#e74c3c', height=60)  # Changed to red
            title_frame.pack(fill='x')
            title_frame.pack_propagate(False)
            
            tk.Label(
                title_frame,
                text="⚠ Mandatory Update Required",  # Changed text
                font=('Arial', 14, 'bold'),
                fg='white',
                bg='#e74c3c'
            ).pack(expand=True)
            
            # Content
            content = tk.Frame(dialog, bg='white')
            content.pack(fill='both', expand=True, padx=20, pady=20)
            
            tk.Label(
                content,
                text=f"Current Version: {self.current_version}",
                font=('Arial', 10),
                bg='white'
            ).pack(anchor='w', pady=5)
            
            tk.Label(
                content,
                text=f"Required Version: {update_info['version']}",
                font=('Arial', 12, 'bold'),
                fg='#e74c3c',  # Red color
                bg='white'
            ).pack(anchor='w', pady=5)
            
            # Mandatory update notice
            tk.Label(
                content,
                text="This update is required to continue using StudyTimer.\nThe application cannot be used without updating.",
                font=('Arial', 11, 'bold'),
                fg='#e74c3c',
                bg='white',
                wraplength=450
            ).pack(anchor='w', pady=(10, 5))
            
            if update_info.get('release_date'):
                tk.Label(
                    content,
                    text=f"Released: {update_info['release_date']}",
                    font=('Arial', 9),
                    fg='#7f8c8d',
                    bg='white'
                ).pack(anchor='w', pady=5)
            
            # Release notes
            tk.Label(
                content,
                text="What's New:",
                font=('Arial', 11, 'bold'),
                bg='white'
            ).pack(anchor='w', pady=(15, 5))
            
            notes_frame = tk.Frame(content)
            notes_frame.pack(fill='both', expand=True, pady=5)
            
            notes_text = tk.Text(
                notes_frame,
                wrap='word',
                height=8,
                font=('Arial', 9),
                bg='#f8f9fa'
            )
            scrollbar = ttk.Scrollbar(notes_frame, command=notes_text.yview)
            notes_text.configure(yscrollcommand=scrollbar.set)
            
            notes_text.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Add release notes
            notes_text.insert('1.0', update_info.get('release_notes', 'No release notes available.'))
            notes_text.configure(state='disabled')
            
            # Buttons - Only "Update Now" and "Exit Application"
            button_frame = tk.Frame(dialog, bg='#ecf0f1', height=60)
            button_frame.pack(fill='x', side='bottom')
            button_frame.pack_propagate(False)
            
            def update_now():
                print("[UPDATE] User clicked 'Update Now'")
                self.dialog_open = False
                dialog.destroy()
                # Use after() to ensure dialog closes before download starts
                if root_window and root_window.winfo_exists():
                    root_window.after(100, lambda: self.download_and_install(update_info))
                else:
                    self.download_and_install(update_info)
            
            def exit_app():
                print("[UPDATE] User chose to exit instead of updating")
                dialog.destroy()
                self.force_exit()
            
            # Create buttons
            exit_btn = tk.Button(
                button_frame,
                text="Exit Application",
                command=exit_app,
                bg='#95a5a6',
                fg='white',
                font=('Arial', 10, 'bold'),
                padx=30,
                pady=8,
                relief='flat',
                cursor='hand2'
            )
            exit_btn.pack(side='right', padx=(5, 15), pady=15)
            
            update_btn = tk.Button(
                button_frame,
                text="Update Now",
                command=update_now,
                bg='#27ae60',
                fg='white',
                font=('Arial', 10, 'bold'),
                padx=30,
                pady=8,
                relief='flat',
                cursor='hand2'
            )
            update_btn.pack(side='right', padx=5, pady=15)
            
            # Keep dialog on top but allow other interactions after 2 seconds
            dialog.after(2000, lambda: dialog.attributes('-topmost', False))
            
            print("[UPDATE] Mandatory update dialog created successfully")
            
        except Exception as e:
            self.dialog_open = False
            print(f"[UPDATE] Error creating mandatory dialog: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback: Use simple messagebox that forces choice
            response = messagebox.askyesno(
                "Mandatory Update Required", 
                f"StudyTimer requires an update to version {update_info['version']}.\n"
                f"Current version: {self.current_version}\n\n"
                f"This update is mandatory. Choose:\n"
                f"YES = Update now\n"
                f"NO = Exit application",
                default='yes'
            )
            
            if response:
                self.download_and_install(update_info)
            else:
                self.force_exit()
    

    def download_and_install(self, update_info):
        """Download and install the mandatory update with working real-time progress tracking"""
        print(f"[UPDATE] Starting MANDATORY download for version {update_info['version']}")
        
        try:
            # Ensure we have a proper root window for the progress dialog
            root_window = self.master_window
            if not root_window:
                try:
                    root_window = tk._default_root
                    if not root_window or not root_window.winfo_exists():
                        root_window = tk.Tk()
                        root_window.withdraw()
                except:
                    root_window = tk.Tk()
                    root_window.withdraw()
            
            # Show progress dialog - MAKE IT NON-CLOSEABLE
            progress = tk.Toplevel(root_window)
            progress.title("Downloading Mandatory Update")
            progress.geometry("500x220")
            progress.resizable(False, False)
            progress.grab_set()
            
            # PREVENT CLOSING THE PROGRESS DIALOG
            progress.protocol("WM_DELETE_WINDOW", lambda: None)
            progress.attributes('-topmost', True)
            
            # Center window
            progress.update_idletasks()
            x = (progress.winfo_screenwidth() // 2) - (500 // 2)
            y = (progress.winfo_screenheight() // 2) - (220 // 2)
            progress.geometry(f"500x220+{x}+{y}")
            
            # Main frame
            main_frame = tk.Frame(progress, bg='white')
            main_frame.pack(fill='both', expand=True, padx=15, pady=15)
            
            # Title with warning
            title_label = tk.Label(
                main_frame,
                text="⚠ Downloading Mandatory Update",
                font=('Arial', 14, 'bold'),
                fg='#e74c3c',
                bg='white'
            )
            title_label.pack(pady=(5, 10))
            
            subtitle_label = tk.Label(
                main_frame,
                text="This update is required. Please wait...",
                font=('Arial', 10),
                fg='#e74c3c',
                bg='white'
            )
            subtitle_label.pack(pady=(0, 15))
            
            # Progress bar - DETERMINATE MODE
            progress_bar = ttk.Progressbar(
                main_frame,
                mode='determinate',
                length=400,
                maximum=100
            )
            progress_bar.pack(pady=(0, 10))
            
            # Use StringVar for automatic UI updates
            status_var = tk.StringVar(value="Starting download...")
            info_var = tk.StringVar(value="Preparing...")
            
            # Status labels
            status_label = tk.Label(
                main_frame,
                textvariable=status_var,
                font=('Arial', 10),
                bg='white'
            )
            status_label.pack(pady=(0, 5))
            
            # Download speed and size info
            info_label = tk.Label(
                main_frame,
                textvariable=info_var,
                font=('Arial', 9),
                fg='#7f8c8d',
                bg='white'
            )
            info_label.pack()
            
            # Simple progress tracking variables
            progress_data = {
                'percent': 0,
                'total_size': 0,
                'downloaded_size': 0,
                'start_time': time.time(),
                'completed': False,
                'error': None,
                'file_path': None
            }
            
            def update_progress_ui():
                """Update the progress UI"""
                try:
                    if not progress.winfo_exists():
                        return
                        
                    # Update progress bar
                    progress_bar['value'] = progress_data['percent']
                    
                    # Calculate and display progress info
                    if progress_data['total_size'] > 0 and progress_data['downloaded_size'] > 0:
                        downloaded_mb = progress_data['downloaded_size'] / (1024 * 1024)
                        total_mb = progress_data['total_size'] / (1024 * 1024)
                        elapsed = time.time() - progress_data['start_time']
                        
                        if elapsed > 0:
                            speed_bps = progress_data['downloaded_size'] / elapsed
                            
                            # Format speed appropriately
                            if speed_bps >= 1024 * 1024:  # >= 1 MB/s
                                speed_mbps = speed_bps / (1024 * 1024)
                                speed_text = f"{speed_mbps:.1f} MB/s"
                            elif speed_bps >= 1024:  # >= 1 KB/s
                                speed_kbps = speed_bps / 1024
                                speed_text = f"{speed_kbps:.1f} KB/s"
                            else:  # < 1 KB/s
                                speed_text = f"{speed_bps:.0f} B/s"
                            
                            # Calculate and format ETA
                            if speed_bps > 0:
                                remaining_bytes = progress_data['total_size'] - progress_data['downloaded_size']
                                eta_seconds = remaining_bytes / speed_bps
                                
                                if eta_seconds < 60:  # Less than 1 minute
                                    eta_text = f"ETA: {int(eta_seconds)}s"
                                elif eta_seconds < 3600:  # Less than 1 hour
                                    eta_minutes = eta_seconds / 60
                                    eta_text = f"ETA: {int(eta_minutes)}m"
                                else:  # 1 hour or more
                                    eta_hours = eta_seconds / 3600
                                    eta_minutes = (eta_seconds % 3600) / 60
                                    if eta_minutes < 5:  # Don't show minutes if less than 5
                                        eta_text = f"ETA: {int(eta_hours)}h"
                                    else:
                                        eta_text = f"ETA: {int(eta_hours)}h {int(eta_minutes)}m"
                            else:
                                eta_text = "ETA: Calculating..."
                            
                            status_var.set(f"Downloading... {progress_data['percent']:.1f}%")
                            info_var.set(f"{downloaded_mb:.1f}/{total_mb:.1f} MB - {speed_text} - {eta_text}")
                            
                            print(f"[UPDATE] UI Progress: {progress_data['percent']:.1f}% - {downloaded_mb:.1f}/{total_mb:.1f} MB - {speed_text}")
                    
                    # Handle completion or error
                    if progress_data['error']:
                        print(f"[UPDATE] Error in download: {progress_data['error']}")
                        try:
                            progress.destroy()
                        except:
                            pass
                        messagebox.showerror(
                            "Mandatory Update Failed",
                            f"Could not download the mandatory update: {progress_data['error']}\n\n"
                            f"StudyTimer cannot continue without this update.\n\n"
                            f"Please check your internet connection and restart the application."
                        )
                        self.force_exit()
                        return
                        
                    elif progress_data['completed']:
                        print(f"[UPDATE] Download completed, showing installation options")
                        try:
                            progress.destroy()
                            self.show_installation_options(progress_data['file_path'], update_info)
                        except Exception as e:
                            print(f"[UPDATE] Error showing installation options: {e}")
                            messagebox.showerror(
                                "Download Complete - Manual Installation Required",
                                f"Update downloaded but could not show installer.\n\n"
                                f"Please run the installer manually from the downloads folder."
                            )
                            self.force_exit()
                        return
                    
                    # Continue updating if not completed
                    progress.after(200, update_progress_ui)
                    
                except Exception as e:
                    print(f"[UPDATE] UI update error: {e}")
                    if progress.winfo_exists() and not progress_data['completed']:
                        progress.after(500, update_progress_ui)
            
            def download_thread():
                try:
                    download_url = update_info['download_url']
                    filename = f"StudyTimer_v{update_info['version']}_Installer.exe"
                    file_path = os.path.join(self.download_folder, filename)
                    
                    print(f"[UPDATE] Downloading from: {download_url}")
                    print(f"[UPDATE] Saving to: {file_path}")
                    
                    # Clean up any existing partial downloads
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"[UPDATE] Removed existing file: {file_path}")
                        except Exception as cleanup_error:
                            print(f"[UPDATE] Could not remove existing file: {cleanup_error}")
                            # Try with a different filename
                            import uuid
                            unique_id = str(uuid.uuid4())[:8]
                            filename = f"StudyTimer_v{update_info['version']}_{unique_id}_Installer.exe"
                            file_path = os.path.join(self.download_folder, filename)
                            print(f"[UPDATE] Using alternative filename: {file_path}")
                    
                    status_var.set("Connecting...")
                    info_var.set("Establishing connection")
                    
                    # Start the download with better timeout handling
                    print("[UPDATE] Making HTTP request...")
                    
                    # Use session for better connection handling
                    session = requests.Session()
                    session.headers.update({
                        'User-Agent': 'StudyTimer-Updater/1.0'
                    })
                    
                    response = session.get(
                        download_url, 
                        stream=True, 
                        timeout=(10, 30),  # (connect_timeout, read_timeout)
                        allow_redirects=True
                    )
                    response.raise_for_status()
                    print("[UPDATE] HTTP request successful")
                    
                    # Get file size
                    total_size = int(response.headers.get('content-length', 0))
                    progress_data['total_size'] = total_size
                    progress_data['start_time'] = time.time()
                    
                    print(f"[UPDATE] File size: {total_size} bytes")
                    
                    if total_size > 0:
                        total_mb = total_size / (1024 * 1024)
                        info_var.set(f"File size: {total_mb:.1f} MB")
                    else:
                        info_var.set("File size unknown")
                    
                    status_var.set("Downloading...")
                    
                    # Download with progress tracking and better error handling
                    with open(file_path, 'wb') as f:
                        chunk_size = 8192
                        downloaded_size = 0
                        last_update = time.time()
                        
                        try:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    
                                    # Update progress data
                                    progress_data['downloaded_size'] = downloaded_size
                                    if total_size > 0:
                                        percent = (downloaded_size / total_size) * 100
                                        progress_data['percent'] = min(percent, 100)
                                    
                                    # Update UI less frequently to avoid blocking
                                    current_time = time.time()
                                    if current_time - last_update >= 0.5:  # Update every 0.5 seconds
                                        last_update = current_time
                                        
                        except requests.exceptions.ChunkedEncodingError as chunk_error:
                            print(f"[UPDATE] Chunked encoding error (partial download): {chunk_error}")
                            # Don't treat this as fatal - file might still be partially downloaded
                            if downloaded_size > total_size * 0.8:  # If we got most of the file
                                print(f"[UPDATE] Downloaded {downloaded_size}/{total_size} bytes, attempting to continue")
                            else:
                                raise chunk_error
                        
                        except requests.exceptions.ConnectionError as conn_error:
                            print(f"[UPDATE] Connection error during download: {conn_error}")
                            raise conn_error
                    
                    # Verify download completed successfully
                    if os.path.exists(file_path):
                        actual_size = os.path.getsize(file_path)
                        print(f"[UPDATE] Download completed successfully")
                        print(f"[UPDATE] Expected size: {total_size}, Actual size: {actual_size}")
                        
                        if total_size > 0 and actual_size < total_size * 0.9:  # Allow 10% variance
                            raise Exception(f"Download incomplete: got {actual_size} bytes, expected {total_size}")
                    else:
                        raise Exception("Download failed: file not found after download")
                    
                    # Mark as completed
                    progress_data['percent'] = 100
                    progress_data['completed'] = True
                    progress_data['file_path'] = file_path
                    status_var.set("Download complete!")
                    info_var.set("Preparing installation...")
                    
                    # Close the session
                    session.close()
                    
                except requests.exceptions.Timeout as timeout_error:
                    print(f"[UPDATE] Download timeout: {timeout_error}")
                    progress_data['error'] = f"Download timed out. Please check your internet connection."
                
                except requests.exceptions.ConnectionError as conn_error:
                    print(f"[UPDATE] Connection error: {conn_error}")
                    progress_data['error'] = f"Connection failed. Please check your internet connection."
                
                except requests.exceptions.HTTPError as http_error:
                    print(f"[UPDATE] HTTP error: {http_error}")
                    progress_data['error'] = f"Server error: {http_error}"
                
                except Exception as e:
                    print(f"[UPDATE] Download failed: {e}")
                    import traceback
                    traceback.print_exc()
                    progress_data['error'] = str(e)
                
                finally:
                    # Cleanup
                    try:
                        if 'session' in locals():
                            session.close()
                    except:
                        pass
            
            # Start the UI updater
            progress.after(200, update_progress_ui)
            
            # Start download in background
            thread = threading.Thread(target=download_thread)
            thread.daemon = True
            thread.start()
            
            # Remove topmost after 3 seconds
            progress.after(3000, lambda: progress.attributes('-topmost', False))
            
        except Exception as e:
            print(f"[UPDATE] Error in mandatory download_and_install: {e}")
            try:
                messagebox.showerror(
                    "Mandatory Update Error", 
                    f"Could not start mandatory update download: {e}\n\n"
                    f"StudyTimer cannot continue. Please restart and try again."
                )
            except:
                pass
            self.force_exit()
    def show_installation_options(self, file_path, update_info):
        """Show mandatory installation options with guaranteed button visibility"""
        try:
            print(f"[UPDATE] Showing MANDATORY installation options for {file_path}")
            
            # Verify file exists
            if not os.path.exists(file_path):
                print(f"[UPDATE] Installer file not found: {file_path}")
                messagebox.showerror("File Error", "Installer file not found. Application will exit.")
                self.force_exit()
                return
            
            # Get root window with better bundled exe support
            root_window = None
            try:
                root_window = self.master_window
                if root_window and not root_window.winfo_exists():
                    root_window = None
            except:
                root_window = None
            
            if not root_window:
                try:
                    root_window = tk._default_root
                    if not root_window or not root_window.winfo_exists():
                        root_window = None
                except:
                    root_window = None
            
            # If we still don't have a root window, create one (for bundled exe)
            if not root_window:
                print("[UPDATE] Creating temporary root window for bundled exe")
                root_window = tk.Tk()
                root_window.withdraw()  # Hide it
            
            # Create installation dialog with larger height to ensure buttons fit
            install_dialog = tk.Toplevel(root_window)
            install_dialog.title("Install Mandatory Update")
            install_dialog.geometry("550x500")  # Increased height to 500
            install_dialog.resizable(False, False)
            
            # Make it modal and prevent closing
            install_dialog.lift()
            install_dialog.attributes('-topmost', True)
            install_dialog.focus_force()
            install_dialog.grab_set()
            install_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent closing with X
            
            # Center window
            install_dialog.update_idletasks()
            x = (install_dialog.winfo_screenwidth() // 2) - (550 // 2)
            y = (install_dialog.winfo_screenheight() // 2) - (500 // 2)
            install_dialog.geometry(f"550x500+{x}+{y}")
            
            print("[UPDATE] Mandatory installation dialog created and positioned")
            
            # Main container with proper packing
            main_frame = tk.Frame(install_dialog, bg='white')
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Title - Changed to warning style
            title_label = tk.Label(
                main_frame,
                text="⚠ Mandatory Update Ready",
                font=('Arial', 16, 'bold'),
                fg='#e74c3c',  # Red color for warning
                bg='white'
            )
            title_label.pack(pady=(10, 5))
            
            subtitle_label = tk.Label(
                main_frame,
                text=f"StudyTimer v{update_info.get('version')} must be installed now",
                font=('Arial', 12, 'bold'),
                bg='white'
            )
            subtitle_label.pack(pady=(5, 15))
            
            # Installation instructions - Updated text
            instructions_label = tk.Label(
                main_frame,
                text="The update has been downloaded and is ready to install.\n\n"
                     "This update is MANDATORY. You must install it to continue using StudyTimer.\n\n"
                     "Choose your preferred installation method:",
                font=('Arial', 11),
                justify='center',
                wraplength=500,
                fg='#e74c3c',  # Red color for emphasis
                bg='white'
            )
            instructions_label.pack(pady=(0, 20))
            
            # Show file path with better layout
            path_frame = tk.Frame(main_frame, bg='white')
            path_frame.pack(pady=(0, 20), fill='x')
            
            path_title = tk.Label(
                path_frame, 
                text="Installer location:", 
                font=('Arial', 9, 'bold'),
                bg='white'
            )
            path_title.pack(anchor='w')
            
            path_entry = tk.Entry(
                path_frame, 
                font=('Arial', 8), 
                width=70
            )
            path_entry.pack(fill='x', pady=(5, 0))
            path_entry.insert(0, file_path)
            path_entry.config(state='readonly')
            
            # Add flexible spacer that pushes buttons to bottom
            spacer = tk.Frame(main_frame, bg='white')
            spacer.pack(expand=True, fill='both')
            
            # Buttons frame - positioned at bottom
            button_frame = tk.Frame(main_frame, bg='white')
            button_frame.pack(side='bottom', pady=(20, 10))
            
            def install_now():
                print("[UPDATE] User chose Install Now (mandatory)")
                install_dialog.destroy()
                self.install_now_with_cleanup(file_path)
            
            def open_folder_and_exit():
                print("[UPDATE] User chose to open folder and exit")
                install_dialog.destroy()
                try:
                    subprocess.run(['explorer', '/select,', file_path])
                except Exception as e:
                    print(f"[UPDATE] Failed to open folder: {e}")
                
                messagebox.showinfo(
                    "Manual Installation Required", 
                    f"StudyTimer will now close.\n\n"
                    f"Please run the installer manually:\n{file_path}\n\n"
                    f"StudyTimer cannot be used until the update is installed."
                )
                self.force_exit()
            
            # Create buttons with guaranteed visibility
            install_btn = tk.Button(
                button_frame,
                text="Install Now & Restart",
                command=install_now,
                bg='#27ae60',
                fg='white',
                font=('Arial', 12, 'bold'),
                padx=25,
                pady=12,
                relief='raised',
                borderwidth=2
            )
            install_btn.pack(side='left', padx=(0, 20))
            
            exit_btn = tk.Button(
                button_frame,
                text="Open Folder & Exit",
                command=open_folder_and_exit,
                bg='#e74c3c',  # Red color to indicate this will exit
                fg='white',
                font=('Arial', 12, 'bold'),
                padx=25,
                pady=12,
                relief='raised',
                borderwidth=2
            )
            exit_btn.pack(side='left')
            
            # Force dialog update to ensure everything is visible
            install_dialog.update_idletasks()
            
            # Keep dialog on top for 2 seconds, then allow normal interaction
            install_dialog.after(2000, lambda: install_dialog.attributes('-topmost', False))
            
            print("[UPDATE] Mandatory installation options dialog created with buttons")
            
        except Exception as e:
            print(f"[UPDATE] Error showing mandatory installation options: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback for bundled executables - ALSO MANDATORY
            print("[UPDATE] Attempting mandatory fallback dialog")
            try:
                # Create a simple root if needed
                temp_root = tk.Tk()
                temp_root.withdraw()
                
                # Simple dialog that forces choice - NO "CANCEL" OPTION
                response = messagebox.askyesno(
                    "Mandatory Update - Install Required",
                    f"StudyTimer v{update_info.get('version')} downloaded successfully.\n\n"
                    f"THIS UPDATE IS MANDATORY.\n\n"
                    f"YES = Install now (close app and run installer)\n"
                    f"NO = Show installer location and exit app",
                    parent=temp_root,
                    default='yes'
                )
                
                if response is True:  # Install Now
                    print("[UPDATE] User chose install now via fallback")
                    temp_root.destroy()
                    self.install_now_with_cleanup(file_path)
                else:  # Show location and exit
                    print("[UPDATE] User chose show location and exit via fallback")
                    temp_root.destroy()
                    try:
                        subprocess.run(['explorer', '/select,', file_path], check=True)
                    except Exception as e2:
                        messagebox.showinfo(
                            "Manual Installation Required", 
                            f"The installer is saved at:\n\n{file_path}\n\n"
                            f"StudyTimer will now close. Run the installer manually to update."
                        )
                    
                    # Force exit after showing location
                    messagebox.showinfo(
                        "Application Closing", 
                        f"StudyTimer cannot continue without the mandatory update.\n\n"
                        f"Please run the installer to update, then restart StudyTimer."
                    )
                    self.force_exit()
                    
            except Exception as e2:
                print(f"[UPDATE] Even fallback failed: {e2}")
                # Final fallback - force exit with message
                try:
                    messagebox.showerror(
                        "Mandatory Update Error", 
                        f"Could not display update installation options.\n\n"
                        f"StudyTimer will now close. Please check:\n{file_path}\n\n"
                        f"Run the installer manually to update StudyTimer."
                    )
                except:
                    print("[UPDATE] All dialog attempts failed")
                
                # Force exit no matter what
                self.force_exit()

    def install_now_with_cleanup(self, file_path):
        """Install now with faster, cleaner process"""
        try:
            print("[UPDATE] Preparing to install and exit...")

            # Show a brief "closing" message
            try:
                root_window = self.master_window or tk._default_root
                if root_window and root_window.winfo_exists():
                    closing_dialog = tk.Toplevel(root_window)
                    closing_dialog.title("StudyTimer")
                    closing_dialog.geometry("300x100")
                    closing_dialog.resizable(False, False)
                    closing_dialog.attributes('-topmost', True)
                    
                    # Center the window
                    closing_dialog.update_idletasks()
                    x = (closing_dialog.winfo_screenwidth() // 2) - (150)
                    y = (closing_dialog.winfo_screenheight() // 2) - (50)
                    closing_dialog.geometry(f"300x100+{x}+{y}")
                    
                    tk.Label(
                        closing_dialog, 
                        text="Starting installer...\nStudyTimer will close now.",
                        font=('Arial', 11),
                        justify='center'
                    ).pack(expand=True)
                    
                    closing_dialog.update()
                    
                    # Show for just 1 second instead of 5
                    closing_dialog.after(1000, closing_dialog.destroy)
            except:
                pass

            # Method 1: Direct execution (fastest, no console window)
            try:
                print("[UPDATE] Attempting direct installer launch...")
                
                # Start installer directly without console window
                subprocess.Popen(
                    [file_path], 
                    shell=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
                
                print("[UPDATE] Installer started directly, exiting app...")
                
                # Give just a brief moment for installer to start
                time.sleep(0.5)
                
                # Exit immediately
                self.force_exit()
                return
                
            except Exception as direct_error:
                print(f"[UPDATE] Direct launch failed: {direct_error}")
            
            # Method 2: Reduced delay with hidden console (fallback)
            try:
                print("[UPDATE] Using fallback method with reduced delay...")
                
                # Use a much shorter delay (0.5 seconds instead of 2)
                wait_and_run = f'cmd /c "timeout /t 1 >nul & start \"\" \"{file_path}\""'
                
                # Start with hidden console window
                subprocess.Popen(
                    wait_and_run, 
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW  # Hide console window
                )
                
                print("[UPDATE] Installer scheduled, exiting app...")
                time.sleep(0.2)  # Very brief pause
                self.force_exit()
                
            except Exception as fallback_error:
                print(f"[UPDATE] Fallback method failed: {fallback_error}")
            
            # Method 3: Last resort - immediate launch
            try:
                print("[UPDATE] Using immediate launch (last resort)...")
                subprocess.Popen([file_path])
                self.force_exit()
                
            except Exception as final_error:
                print(f"[UPDATE] All launch methods failed: {final_error}")
                messagebox.showerror(
                    "Install Error",
                    f"Could not start installer automatically.\n\n"
                    f"Please run manually:\n{file_path}"
                )

        except Exception as e:
            print(f"[UPDATE] Installation failed: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror(
                "Install Error",
                f"Could not start installer automatically.\n\n"
                f"Please run manually:\n{file_path}"
            )

    def force_exit(self):
        """Force exit the application"""
        try:
            print("[UPDATE] Force exiting application")
            
            # Multiple exit strategies for maximum reliability
            try:
                # Method 1: Standard exit
                sys.exit(0)
            except:
                pass
            
            try:
                # Method 2: OS-level exit
                os._exit(0)
            except:
                pass
            
            try:
                # Method 3: Windows-specific force exit
                import ctypes
                ctypes.windll.kernel32.ExitProcess(0)
            except:
                pass
                
        except Exception as e:
            print(f"[UPDATE] Force exit failed: {e}")

    def check_pending_updates(self):
        """Check for pending updates scheduled for installation on startup"""
        try:
            update_flag_file = os.path.join(self.download_folder, "pending_update.json")
            
            if os.path.exists(update_flag_file):
                print("[UPDATE] Found pending update")
                
                # Read the update information
                with open(update_flag_file, 'r') as f:
                    update_info = json.load(f)
                
                installer_path = update_info.get('installer_path')
                version = update_info.get('version', 'unknown')
                
                # Check if installer still exists
                if installer_path and os.path.exists(installer_path):
                    print(f"[UPDATE] Installing pending update to version {version}")
                    
                    # Show installation dialog
                    response = messagebox.askyesno(
                        "Install Pending Update",
                        f"A StudyTimer update (version {version}) is ready to install.\n\n"
                        f"Install now? StudyTimer will close and restart with the new version."
                    )
                    
                    if response:
                        try:
                            # Remove the flag file first
                            os.remove(update_flag_file)
                            
                            # Start the installer
                            subprocess.Popen([installer_path])
                            print("[UPDATE] Started pending update installer")
                            
                            # Close StudyTimer
                            sys.exit(0)
                            
                        except Exception as e:
                            print(f"[UPDATE] Error installing pending update: {e}")
                            messagebox.showerror("Update Error", f"Could not install update: {e}")
                    else:
                        # User declined, remove the flag file
                        try:
                            os.remove(update_flag_file)
                            print("[UPDATE] User declined pending update, removed flag file")
                        except:
                            pass
                else:
                    # Installer file missing, clean up flag file
                    try:
                        os.remove(update_flag_file)
                        print("[UPDATE] Installer file missing, cleaned up flag file")
                    except:
                        pass
            
        except Exception as e:
            print(f"[UPDATE] Error checking pending updates: {e}")

def add_auto_update_to_app(app_instance, current_version="1.0", profile_path=None):
    """Add auto-update functionality to your existing app"""
    
    print(f"[UPDATE] Adding auto-update to app with version {current_version}")
    
    # Create updater
    updater = SimpleAutoUpdater(current_version)
    
    # Store reference to main app window for proper closing
    updater.master_window = app_instance
    
    # Store profile path
    updater.profile_path = profile_path
    
    # Add to your app
    app_instance.updater = updater
    
    # Check for pending updates first (on startup)
    def check_pending_on_startup():
        print("[UPDATE] Checking for pending updates on startup...")
        updater.check_pending_updates()
    
    # Check pending updates after a short delay (1 second after startup)
    app_instance.after(1000, check_pending_on_startup)
    
    # Add menu item (if your app has a menu)
    def add_update_menu():
        try:
            if hasattr(app_instance, 'menubar'):
                print("[UPDATE] Found menubar, adding update menu...")
                
                # Create Help menu
                help_menu = tk.Menu(app_instance.menubar, tearoff=0)
                app_instance.menubar.add_cascade(label="Help", menu=help_menu)
                
                # Add update check option
                help_menu.add_command(
                    label="Check for Updates...",
                    command=lambda: updater.check_for_updates(show_dialog=True)
                )
                print("[UPDATE] Update menu added successfully")
            else:
                print("[UPDATE] No menubar found, creating one...")
                # Create a simple menubar
                menubar = tk.Menu(app_instance)
                app_instance.config(menu=menubar)
                app_instance.menubar = menubar
                
                # Create Help menu
                help_menu = tk.Menu(menubar, tearoff=0)
                menubar.add_cascade(label="Help", menu=help_menu)
                
                # Add update check option
                help_menu.add_command(
                    label="Check for Updates...",
                    command=lambda: updater.check_for_updates(show_dialog=True)
                )
                print("[UPDATE] Created menubar and added update menu")
                
        except Exception as e:
            print(f"[UPDATE] Could not add menu item: {e}")
            import traceback
            traceback.print_exc()
    
    # Add menu after a short delay to ensure app is fully initialized
    app_instance.after(100, add_update_menu)
    
    # NEW: Check profile and decide whether to show update on startup
    def startup_check():
        print("[UPDATE] Starting startup update check...")
        
        # Check if referral_prompt_shown exists in profile
        should_check = updater.should_check_update_on_startup()
        
        if should_check:
            print("[UPDATE] Profile check passed - checking for updates on startup")
            def check_thread():
                try:
                    # Call check_for_updates and show dialog if update available
                    has_update, update_info = updater.check_for_updates(show_dialog=False)
                    if has_update:
                        print("[UPDATE] Update found on startup, showing dialog...")
                        # Schedule dialog in main thread
                        app_instance.after(0, lambda: updater.show_update_dialog(update_info))
                except Exception as e:
                    print(f"[UPDATE] Background check failed: {e}")
            
            thread = threading.Thread(target=check_thread)
            thread.daemon = True
            thread.start()
        else:
            print("[UPDATE] Profile check failed - skipping startup update check")
    
    # Check 3 seconds after startup
    app_instance.after(3000, startup_check)
    
    # Also check every 15 minutes (900000 ms) regardless of profile
    def periodic_check():
        print("[UPDATE] Starting periodic update check (15 min interval)...")
        def check_thread():
            try:
                has_update, update_info = updater.check_for_updates(show_dialog=False)
                if has_update:
                    print("[UPDATE] Update found in periodic check, showing dialog...")
                    app_instance.after(0, lambda: updater.show_update_dialog(update_info))
            except Exception as e:
                print(f"[UPDATE] Periodic check failed: {e}")
        
        thread = threading.Thread(target=check_thread)
        thread.daemon = True
        thread.start()
        
        # Schedule next check
        app_instance.after(900000, periodic_check)
    
    # Start periodic checks after 15 minutes
    app_instance.after(900000, periodic_check)
    
    print("[UPDATE] Auto-update functionality added successfully")
    return app_instance

# Test function to manually check for updates
def test_updater():
    """Test the updater manually"""
    print("Testing auto-updater...")
    updater = SimpleAutoUpdater("1.0")  # Use version 1.0 to test
    updater.check_for_updates(show_dialog=True)

if __name__ == "__main__":
    # Test the updater
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    test_updater()
    root.mainloop()