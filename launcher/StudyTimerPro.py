import tkinter as tk
from PIL import Image, ImageTk
import subprocess
import sys
import os
import psutil
import win32gui
import glob
import random
import traceback
try:
    from StudyTimer import CURRENT_VERSION  # Replace 'StudyTimer' with your main app module name
    APP_VERSION = f"v{CURRENT_VERSION}"
except ImportError:
    APP_VERSION = "version 00.04.10.25"  # Fallback version

class RotatingSplashScreen:
    def __init__(self, logo_folder):
        self.logo_folder = logo_folder
        self.root = None
        self.label = None
        self.version = APP_VERSION
        self.version_label = None
        self.progress_bar = None
        self.progress_label = None
        self.images = []
        self.current_image_index = 0
        self.rotation_interval = 10000 # milliseconds between image changes
        self.screen_w = 0
        self.screen_h = 0
        self.splash_width = 0
        self.splash_height = 0
        
        # Progress control variables
        self.progress_value = 0
        self.progress_max = 100
        self.manual_progress = False
        self.target_progress = 0
        self.progress_animation_running = False
        
        # Load all images from the logo folder
        self.load_images()
        
    def load_images(self):
        """Load all supported image files from the logo folder"""
        # Supported image formats
        supported_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
        
        self.images = []
        print(f"Loading images from: {self.logo_folder}")
        print(f"Folder exists: {os.path.exists(self.logo_folder)}")
        
        if os.path.exists(self.logo_folder):
            print("Searching for image files...")
            try:
                # Get all files in the logo folder
                all_files = os.listdir(self.logo_folder)
                print(f"All files in folder: {all_files}")
                
                for filename in all_files:
                    file_path = os.path.join(self.logo_folder, filename)
                    
                    # Check if it's a file (not a subdirectory)
                    if os.path.isfile(file_path):
                        # Get file extension
                        _, ext = os.path.splitext(filename.lower())
                        
                        # Check if extension is supported
                        if ext in supported_extensions:
                            self.images.append(file_path)
                            print(f"Added image: {filename}")
                        else:
                            print(f"Skipped (unsupported format): {filename} (ext: {ext})")
                    else:
                        print(f"Skipped (not a file): {filename}")
                        
            except Exception as e:
                print(f"Error reading logo folder: {e}")
                
        else:
            print(f"Logo folder does not exist: {self.logo_folder}")
        
        # Shuffle the images randomly instead of sorting
        if self.images:
            random.shuffle(self.images)
        
        print(f"Final image list ({len(self.images)} total) - randomized:")
        for i, img in enumerate(self.images):
            print(f"  {i+1}. {os.path.basename(img)}")
        
        if not self.images:
            print(f"Warning: No supported images found in {self.logo_folder}")
            return False
        
        print(f"Successfully loaded {len(self.images)} images in random order")
        return True
    
    def create_splash_window(self):
        """Create the splash screen window"""
        try:
            self.root = tk.Tk()
            self.root.overrideredirect(True)
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 1.0)
            
            self.screen_w = self.root.winfo_screenwidth()
            self.screen_h = self.root.winfo_screenheight()
            
            # Calculate splash screen size (50% of screen)
            self.splash_width = int(self.screen_w * 0.5)
            self.splash_height = int(self.screen_h * 0.5)
            
            # Position window at center
            x = (self.screen_w - self.splash_width) // 2
            y = (self.screen_h - self.splash_height) // 2
            self.root.geometry(f"{self.splash_width}x{self.splash_height}+{x}+{y}")
            
            # Create main container
            container = tk.Frame(self.root, bg='black')
            container.pack(fill=tk.BOTH, expand=True)
            
            # Calculate image area height (leave minimal space for progress at bottom)
            progress_area_height = 35  # ULTRA SLIM as requested
            image_height = self.splash_height - progress_area_height
            
            # Create label for displaying images (almost full height)
            self.label = tk.Label(container, bd=0, bg='black')
            self.label.place(x=0, y=0, width=self.splash_width, height=image_height)
            
            # Create progress overlay frame - positioned at the very bottom, ultra slim
            progress_overlay = tk.Frame(container, bg='black', height=progress_area_height)
            progress_overlay.place(x=0, y=image_height, width=self.splash_width, height=progress_area_height)
            
            # Progress label (smaller font)
            self.progress_label = tk.Label(progress_overlay, text="Loading StudyTimer Pro...", 
                                         fg='white', bg='black', font=('Arial', 8))
            self.progress_label.pack(pady=(2, 1))
            
            # Create a frame for progress bar with minimal dimensions
            progress_container = tk.Frame(progress_overlay, bg='black')
            progress_container.pack(fill=tk.X, padx=20, pady=(0, 3))
            
            # Ultra slim progress bar
            self.progress_bg = tk.Frame(progress_container, bg='#333333', height=12, 
                                      relief='flat', bd=1)
            self.progress_bg.pack(fill=tk.X)
            
            self.progress_fill = tk.Frame(self.progress_bg, bg='#00AA44', height=10)
            self.progress_fill.place(x=1, y=1, width=0, height=10)  # Start with 0 width
            
            # Progress percentage label (smaller)
            self.progress_percent = tk.Label(self.progress_bg, text="0%", fg='white', 
                                           bg='#333333', font=('Arial', 7, 'bold'))
            self.progress_percent.place(relx=0.5, rely=0.5, anchor='center')
            
            print(f"Progress UI created successfully")
            
            # Load and display first image after a short delay to ensure UI is ready
            if self.images:
                # Use after() to delay image loading until UI is fully initialized
                self.root.after(100, self.show_current_image)
                self.root.after(200, self.schedule_next_image)
            
            # Don't start auto progress - will be controlled manually
            
            return self.root
            
        except Exception as e:
            print(f"Error creating splash window: {e}")
            print(f"Error details: {traceback.format_exc()}")
            return None
    
   
    def show_current_image(self):
        """Display the current image - FILL COMPLETELY without hiding important content"""
        if not self.images or not self.label:
            return
            
        try:
            current_image_path = self.images[self.current_image_index]
            print(f"Loading image: {os.path.basename(current_image_path)}")
            
            # Use the predefined dimensions - ULTRA SLIM progress
            progress_area_height = 35  # Match the ultra slim progress area
            label_width = self.splash_width
            label_height = self.splash_height - progress_area_height
            
            print(f"Target dimensions: {label_width}x{label_height}")
            
            # Load image
            img = Image.open(current_image_path)
            original_size = img.size
            print(f"Original image size: {original_size}")
            
            # Calculate scaling to fill the entire image area (FULL FIT as requested)
            img_width, img_height = img.size
            
            # Calculate scale factors for both dimensions
            scale_x = label_width / img_width
            scale_y = label_height / img_height
            
            # Use the larger scale factor to fill the entire area (FULL FIT)
            scale = max(scale_x, scale_y)
            
            # Calculate new dimensions
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            print(f"Scaled dimensions: {new_width}x{new_height} (scale: {scale:.3f})")
            
            # Resize image to fill the entire area
            img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # If image is larger than target area, crop from center (minimal cropping)
            if new_width > label_width or new_height > label_height:
                left = (new_width - label_width) // 2
                top = (new_height - label_height) // 2
                right = left + label_width
                bottom = top + label_height
                img = img.crop((left, top, right, bottom))
                print(f"Cropped to fit: {label_width}x{label_height}")
            
            # Draw version text directly on the image for true transparency
            from PIL import ImageDraw, ImageFont
            
            # Create a copy of the image to draw on
            img_with_text = img.copy()
            draw = ImageDraw.Draw(img_with_text)
            
            # Try to use a sharp system font
            try:
                # Try different fonts for better clarity
                font = ImageFont.truetype("calibri.ttf", 11)  # Calibri is very sharp
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 11)  # Arial fallback
                except:
                    try:
                        font = ImageFont.truetype("segoeui.ttf", 11)  # Segoe UI fallback
                    except:
                        try:
                            # Load default but with specific size
                            font = ImageFont.load_default()
                        except:
                            font = None
            
            # Calculate text size to position it properly
            if font:
                # Get the bounding box of the text
                bbox = draw.textbbox((0, 0), self.version, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                # Estimate text size if font is not available
                text_width = len(self.version) * 7  # Rough estimate
                text_height = 12
            
            # Position text in top-right corner with padding
            right_padding = 10  # Padding from right edge
            top_padding = 5     # Padding from top edge (moved up)
            
            text_x = img_with_text.width - text_width - right_padding
            text_y = top_padding
            
            # Ensure text doesn't go off-screen on the left
            text_x = max(5, text_x)  # Minimum 5px from left edge
            
            # Draw pure white text without outline
            if font:
                draw.text((text_x, text_y), self.version, font=font, fill='white')
            else:
                # Fallback without font
                draw.text((text_x, text_y), self.version, fill='white')
            
            # Use the image with text drawn on it
            img_tk = ImageTk.PhotoImage(img_with_text)
            
            # Update label
            self.label.configure(image=img_tk)
            self.label.image = img_tk  # Keep a reference
            
            print(f"Image displayed successfully (FULL FIT) with version text: {os.path.basename(current_image_path)}")
            
        except Exception as e:
            print(f"Error loading image {current_image_path}: {e}")
            print(f"Error details: {traceback.format_exc()}")
            # Skip to next image if current one fails
            self.next_image()
    def next_image(self):
        """Move to next image in sequence"""
        if self.images:
            self.current_image_index = (self.current_image_index + 1) % len(self.images)
            # If we've completed a full cycle, shuffle again for a new random order
            if self.current_image_index == 0 and len(self.images) > 1:
                print("Completed a full cycle, reshuffling images...")
                random.shuffle(self.images)
            self.show_current_image()
    
    def schedule_next_image(self):
        """Schedule the next image rotation"""
        if self.root and self.images:
            self.root.after(self.rotation_interval, self.rotate_image)
    
    def rotate_image(self):
        """Rotate to next image and schedule the following one"""
        self.next_image()
        self.schedule_next_image()
    
    def withdraw(self):
        """Hide the splash screen"""
        if self.root:
            self.root.withdraw()
    
    def destroy(self):
        """Destroy the splash screen"""
        if self.root:
            self.root.destroy()
    
    def after(self, delay, func):
        """Schedule a function call"""
        if self.root:
            self.root.after(delay, func)
    
    def mainloop(self):
        """Start the main event loop"""
        if self.root:
            self.root.mainloop()
    
    def update(self):
        """Update the splash screen"""
        if self.root:
            self.root.update()
    
    def animate_progress_gradually(self):
        """Gradually animate progress to target value"""
        if not hasattr(self, 'progress_fill') or not self.progress_fill:
            return
            
        if self.progress_value < self.target_progress:
            # Calculate increment (slower as we approach target)
            remaining = self.target_progress - self.progress_value
            if remaining > 20:
                increment = random.uniform(0.8, 2.0)
            elif remaining > 10:
                increment = random.uniform(0.3, 0.8)
            elif remaining > 5:
                increment = random.uniform(0.1, 0.4)
            else:
                increment = random.uniform(0.05, 0.2)
            
            self.progress_value = min(self.progress_value + increment, self.target_progress)
            
            try:
                # Get the background frame width
                bg_width = self.progress_bg.winfo_width()
                if bg_width <= 1:
                    self.root.after(50, self.animate_progress_gradually)
                    return
                
                # Calculate progress bar width (account for border)
                progress_pixels = int((self.progress_value / self.progress_max) * (bg_width - 2))
                
                # Update progress fill width
                self.progress_fill.place_configure(width=max(0, progress_pixels))
                
                # Update percentage text
                percentage = int(self.progress_value)
                self.progress_percent.configure(text=f"{percentage}%")
                
            except Exception as e:
                print(f"Error in animate_progress_gradually: {e}")
            
            # Continue animation if we haven't reached target
            if self.progress_value < self.target_progress:
                delay = random.randint(80, 150)  # Variable delay for more natural feel
                self.root.after(delay, self.animate_progress_gradually)
            else:
                self.progress_animation_running = False
                print(f"Progress animation completed at {int(self.progress_value)}%")
        else:
            self.progress_animation_running = False
    
    def update_progress_text(self, text):
        """Update the progress text"""
        if hasattr(self, 'progress_label') and self.progress_label:
            self.progress_label.configure(text=text)
            print(f"Progress text updated: {text}")
            self.update()
    
    def set_progress_target(self, value):
        """Set target progress value and start gradual animation"""
        self.target_progress = min(max(0, value), self.progress_max)
        print(f"Progress target set to {self.target_progress}%")
        
        # Start animation if not already running
        if not self.progress_animation_running:
            self.progress_animation_running = True
            self.animate_progress_gradually()
    
    def set_progress(self, value):
        """Set progress value instantly (for immediate updates)"""
        old_value = self.progress_value
        self.progress_value = min(max(0, value), self.progress_max)
        self.target_progress = self.progress_value
        self.manual_progress = True
        print(f"Progress set instantly from {old_value} to {self.progress_value}")
        
        # Force immediate update
        if hasattr(self, 'progress_fill'):
            try:
                bg_width = self.progress_bg.winfo_width()
                if bg_width > 1:
                    progress_pixels = int((self.progress_value / self.progress_max) * (bg_width - 2))
                    self.progress_fill.place_configure(width=max(0, progress_pixels))
                    percentage = int(self.progress_value)
                    self.progress_percent.configure(text=f"{percentage}%")
            except:
                pass

def is_process_running(process_name):
    """Check if a process with given name is running"""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def window_exists(title_substring):
    """Check if a window with given title substring exists"""
    found = []
    def callback(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in window_text.lower():
                results.append(hwnd)
        return True
    win32gui.EnumWindows(callback, found)
    return len(found) > 0

def main():
    # Get the directory where the launcher is located
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        launcher_dir = os.path.dirname(sys.executable)
    else:
        # Running as Python script
        launcher_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"Launcher directory: {launcher_dir}")
    
    # Logo folder path (relative to launcher location)
    logo_folder = os.path.join(launcher_dir, "logo")
    print(f"Looking for logo folder at: {logo_folder}")
    print(f"Logo folder exists: {os.path.exists(logo_folder)}")
    
    if os.path.exists(logo_folder):
        print(f"Contents of logo folder:")
        try:
            for item in os.listdir(logo_folder):
                item_path = os.path.join(logo_folder, item)
                print(f"  - {item} ({'file' if os.path.isfile(item_path) else 'folder'})")
        except Exception as e:
            print(f"Error reading logo folder: {e}")
    
    # Create rotating splash screen
    splash = RotatingSplashScreen(logo_folder)
    
    # Check if images were loaded successfully
    if not splash.load_images():
        print("No images found in logo folder.")
        print("Continuing without rotating images...")
        sys.exit(1)
    
    # Create and show splash window
    splash_window = splash.create_splash_window()
    if not splash_window:
        print("Failed to create splash window")
        sys.exit(1)
    
    # Force update to ensure window is ready
    splash.update()
    print("Splash window created and updated")
    
    # Application paths and settings
    app_path = os.path.join(launcher_dir, "StudyTimer.exe")
    process_name = "StudyTimer.exe"
    main_app_window_title = "Study Timer Pro"
    
    # Initialize progress tracking with slower gradual animation
    splash.set_progress(5)
    splash.update_progress_text("Loading components..")
    
    # Much slower gradual progress - spread over longer time
    def simulate_initialization():
        splash.set_progress_target(12)
        # Keep "Loading components.." message
        
        splash.after(2000, lambda: splash.set_progress_target(20))
        splash.after(4000, lambda: splash.set_progress_target(28))
        
        # Switch to "Preparing environment.." at 35%
        splash.after(6000, lambda: [
            splash.set_progress_target(35),
            splash.update_progress_text("Preparing environment..")
        ])
    
    splash.after(500, simulate_initialization)
    
    # Launch the main application
    proc = None
    
    def launch_application():
        nonlocal proc
        try:
            splash.set_progress_target(42)
            # Keep "Preparing environment.." message
            proc = subprocess.Popen([app_path], cwd=launcher_dir)
            print(f"Launched main application: {app_path}")
            splash.root.attributes("-topmost", False)
            # Continue with slower spaced progress updates
            splash.after(2000, lambda: splash.set_progress_target(50))
            
            # Switch to "Loading interface..." at 58%
            splash.after(4000, lambda: [
                splash.set_progress_target(58),
                splash.update_progress_text("Loading interface...")
            ])
            
        except Exception as e:
            print(f"Failed to launch main app: {e}")
            splash.destroy()
            sys.exit(1)
    
    splash.after(7000, launch_application)
    
    def wait_for_process():
        """Wait for the main process to start"""
        if proc and proc.poll() is None:
            if is_process_running(process_name):
                print("Main process detected, checking for window...")
                splash.set_progress_target(65)
                # Keep "Loading interface..." message
                
                # Continue slower spaced progress updates
                splash.after(2500, lambda: splash.set_progress_target(72))
                splash.after(5000, lambda: splash.set_progress_target(79))
                splash.after(7500, lambda: splash.set_progress_target(86))
                splash.after(10000, lambda: splash.set_progress_target(92))
                
                # Reach 97% and switch to "Starting app..."
                splash.after(12500, lambda: [
                    splash.set_progress_target(97),
                    splash.update_progress_text("Starting app...")
                ])
                splash.after(15000, check_for_window)
            else:
                splash.after(500, wait_for_process)
        else:
            print("Main process terminated unexpectedly")
            splash.destroy()
            sys.exit(1)
    
    def check_for_window():
        """Check if the main application window is visible"""
        if proc and proc.poll() is None:
            if window_exists(main_app_window_title):
                print("Main application window detected, finalizing...")
                splash.set_progress_target(97)
                splash.update_progress_text("Application ready, finalizing...")
                splash.root.attributes("-topmost", False)
                
                # Artificial pause but shorter - stop at 97%
                def final_steps():
                    # Don't go to 100% yet, keep at 97%
                    splash.update_progress_text("Launch ready...")
                    
                    def complete_and_hide():
                        splash.set_progress_target(100)
                        splash.update_progress_text("Complete!")
                        
                        # Hide splash immediately after reaching 100%
                        def hide_splash():
                            splash.withdraw()
                            monitor_process()
                        
                        splash.after(200, hide_splash)  # Much shorter delay
                    
                    splash.after(300, complete_and_hide)  # Reduced delay
                
                splash.after(200, final_steps)  # Reduced initial delay
            else:
                splash.after(250, check_for_window)
        else:
            print("Main process terminated")
            splash.destroy()
            sys.exit(0)
    
    def monitor_process():
        """Monitor the main process and exit when it closes"""
        if proc and proc.poll() is None:
            splash.after(1000, monitor_process)
        else:
            print("Main process ended, exiting launcher...")
            splash.destroy()
            sys.exit(0)
    
    # Start the process monitoring after the longer loading sequence
    splash.after(12000, wait_for_process)
    
    # Start the splash screen main loop
    splash.mainloop()

if __name__ == "__main__":
    main()