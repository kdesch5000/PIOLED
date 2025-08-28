
# Thanks to @ricardodemauro for the code modifications.
## This is a rewrite of the application.py with:
## native method instead of syscall
## no threading (less cpu usage)
## ached the cooling_fan path
## some python optimizations
## It uses less memory and less cpu time

import os
import sys
import time
import psutil
import atexit
import signal
import threading
import datetime
import subprocess
import syslog
from pathlib import Path

from oled import OLED
from expansion import Expansion

class Pi_Monitor:
    __slots__ = ['oled', 'expansion', 'font_size', 'cleanup_done', 
                 'stop_event', '_fan_pwm_path', '_format_strings', 
                 'hdmi_on', 'hdmi_timeout', 'last_activity', 
                 'motion_thread', 'capture_dir', 'frame_count', 'motion_sensitivity', 'last_motion_log_time']

    def __init__(self):
        # Initialize OLED and Expansion objects
        self.oled = None
        self.expansion = None
        self.font_size = 12
        self.cleanup_done = False
        self.stop_event = threading.Event()  # Keep for signal handling
        
        # Cache hwmon path lookup for performance
        self._fan_pwm_path = None
        
        # HDMI display wake-up configuration (OLED stays always on)
        self.hdmi_on = False
        self.hdmi_timeout = 60  # 60 seconds timeout
        self.last_activity = time.time()
        
        # Camera motion detection configuration
        self.motion_thread = None
        self.capture_dir = "/tmp/motion_frames"
        self.frame_count = 0
        self.motion_sensitivity = 30
        self.last_motion_log_time = 0
        
        # Initialize syslog for motion detection events
        syslog.openlog("PiMonitorMotion", syslog.LOG_PID, syslog.LOG_DAEMON)
        
        # Create capture directory
        Path(self.capture_dir).mkdir(exist_ok=True)
        
        # Pre-allocate format strings
        self._format_strings = {
            'cpu': "CPU: {}%",
            'mem': "MEM: {}%", 
            'disk': "DISK: {}%",
            'date': "Date: {}",
            'week': "Week: {}",
            'time': "TIME: {}",
            'pi_temp': "PI TEMP: {}C",
            'pc_temp': "PC TEMP: {}C",
            'fan_mode': "FAN Mode: {}",
            'fan_duty': "FAN Duty: {}%",
            'led_mode': "LED Mode: {}"
        }

        try:
            self.oled = OLED()
        except Exception as e:
            sys.exit(1)

        try:
            self.expansion = Expansion()
            self.expansion.set_led_mode(4)
            self.expansion.set_all_led_color(255, 0, 0)
            self.expansion.set_fan_mode(1)
        except Exception as e:
            sys.exit(1)

        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        
        # Initialize fan PWM path cache
        self._find_fan_pwm_path()
        
        # Initialize camera motion detection
        self._start_motion_detection()

    def _find_fan_pwm_path(self):
        """Cache the fan PWM path to avoid repeated directory lookups"""
        try:
            base_path = '/sys/devices/platform/cooling_fan/hwmon/'
            hwmon_dirs = [d for d in os.listdir(base_path) if d.startswith('hwmon')]
            if hwmon_dirs:
                self._fan_pwm_path = os.path.join(base_path, hwmon_dirs[0], 'pwm1')
        except Exception:
            self._fan_pwm_path = None

    def get_raspberry_fan_pwm(self, max_retries=3, retry_delay=0.1):
        """Get fan PWM using cached path and direct file read instead of subprocess"""
        for attempt in range(max_retries + 1):
            try:
                # Use cached path if available
                if self._fan_pwm_path:
                    fan_input_path = self._fan_pwm_path
                else:
                    base_path = '/sys/devices/platform/cooling_fan/hwmon/'
                    hwmon_dirs = [d for d in os.listdir(base_path) if d.startswith('hwmon')]
                    if not hwmon_dirs:
                        raise FileNotFoundError("No hwmon directory found")
                    fan_input_path = os.path.join(base_path, hwmon_dirs[0], 'pwm1')
                
                # Direct file read instead of subprocess
                with open(fan_input_path, 'r') as f:
                    pwm_value = int(f.read().strip())
                    return max(0, min(255, pwm_value))  # Clamp between 0-255
                    
            except (OSError, ValueError) as e:
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    return -1
            except Exception:
                return -1
        return -1

    def get_raspberry_cpu_usage(self):
        """Get the CPU usage percentage"""
        try:
            return psutil.cpu_percent(interval=0)
        except Exception:
            return 0

    def get_raspberry_memory_usage(self):
        """Get the memory usage percentage"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent
        except Exception:
            return 0

    def get_raspberry_disk_usage(self, path='/'):
        """Get the disk usage percentage for the specified path"""
        try:
            disk_usage = psutil.disk_usage(path)
            return disk_usage.percent
        except Exception:
            return 0

    def get_raspberry_date(self):
        """Get the current date in YYYY-MM-DD format using native Python datetime"""
        try:
            return datetime.date.today().strftime('%Y-%m-%d')
        except Exception:
            return "1990-1-1"

    def get_raspberry_weekday(self):
        """Get the current weekday name using native Python datetime"""
        try:
            return datetime.date.today().strftime('%A')
        except Exception:
            return "Error"

    def get_raspberry_time(self):
        """Get the current time in HH:MM:SS format using native Python datetime"""
        try:
            return datetime.datetime.now().strftime('%H:%M:%S')
        except Exception:
            return '0:0:0'

    def get_raspberry_cpu_temperature(self):
        """Get the CPU temperature in Celsius using direct file read"""
        try:
            with open('/sys/devices/virtual/thermal/thermal_zone0/temp', 'r') as f:
                temp_raw = int(f.read().strip())
                return temp_raw / 1000.0
        except Exception:
            return 0

    def get_computer_temperature(self):
        # Get the computer temperature using Expansion object
        try:
            return self.expansion.get_temp()
        except Exception as e:
            return 0

    def get_computer_fan_mode(self):
        # Get the computer fan mode using Expansion object
        try:
            return self.expansion.get_fan_mode()
        except Exception as e:
            return 0

    def get_computer_fan_duty(self):
        # Get the computer fan duty cycle using Expansion object
        try:
            return self.expansion.get_fan0_duty()
        except Exception as e:
            return 0

    def get_computer_led_mode(self):
        # Get the computer LED mode using Expansion object
        try:
            return self.expansion.get_led_mode()
        except Exception as e:
            return 0

    def get_days_since_reboot(self):
        """Get the number of days since last system reboot using uptime"""
        try:
            result = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
            uptime_str = result.stdout.strip()
            # Parse "up 4 days, 5 hours, 7 minutes" format
            if 'day' in uptime_str:
                parts = uptime_str.split()
                for i, part in enumerate(parts):
                    if part.isdigit() and i + 1 < len(parts) and 'day' in parts[i + 1]:
                        return int(part)
            return 0  # Less than 1 day
        except Exception:
            return 0

    def _start_motion_detection(self):
        """Start camera motion detection thread"""
        self.motion_thread = threading.Thread(target=self._camera_motion_loop, daemon=True)
        self.motion_thread.start()
        print("Camera motion detection started")
        
        # Log startup to syslog
        timestamp = datetime.datetime.now()
        syslog.syslog(syslog.LOG_INFO, f"Camera motion detection started at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - Sensitivity: {self.motion_sensitivity}, Timeout: {self.hdmi_timeout}s")

    def _camera_motion_loop(self):
        """Main camera motion detection loop"""
        try:
            while not self.stop_event.is_set():
                current_frame = f"{self.capture_dir}/frame_{self.frame_count % 2}.jpg"
                previous_frame = f"{self.capture_dir}/frame_{(self.frame_count + 1) % 2}.jpg"
                
                # Capture current frame
                if self._capture_frame(current_frame):
                    # Check for motion if we have a previous frame
                    if self.frame_count > 0 and os.path.exists(previous_frame):
                        if self._detect_motion(current_frame, previous_frame):
                            self._wake_hdmi_display()
                            
                    self.frame_count += 1
                    
                    # Cleanup old frames periodically
                    if self.frame_count % 20 == 0:
                        self._cleanup_old_frames()
                else:
                    time.sleep(1)  # Wait before retrying if capture failed
                    
                time.sleep(0.5)  # Small delay between captures
                
        except Exception as e:
            print(f"Camera motion detection error: {e}")
            syslog.syslog(syslog.LOG_ERR, f"Camera motion detection error: {e}")
            
    def _capture_frame(self, filename):
        """Capture a single frame using rpicam-still"""
        try:
            cmd = [
                'rpicam-still',
                '--timeout', '100',  # Very quick capture
                '--width', '640',
                '--height', '480',
                '--nopreview',
                '--output', filename
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
            
    def _detect_motion(self, current_frame, previous_frame):
        """Detect motion between two frames using basic comparison"""
        try:
            if not os.path.exists(current_frame) or not os.path.exists(previous_frame):
                return False
                
            # Get file sizes as a basic comparison
            size1 = os.path.getsize(previous_frame)
            size2 = os.path.getsize(current_frame)
            
            if size1 == 0:
                return False
                
            # Calculate percentage difference
            diff_percent = abs(size1 - size2) / size1 * 100
            
            # If file sizes differ significantly, assume motion
            return diff_percent > (self.motion_sensitivity / 10)
            
        except Exception:
            return False
            
    def _cleanup_old_frames(self):
        """Keep only the last 2 frames to save space"""
        try:
            files = list(Path(self.capture_dir).glob("frame_*.jpg"))
            if len(files) > 2:
                files.sort(key=lambda x: x.stat().st_mtime)
                for f in files[:-2]:
                    f.unlink()
        except Exception:
            pass

    def _wake_hdmi_display(self):
        """Wake up DSI display using multiple methods"""
        if not self.hdmi_on:
            timestamp = datetime.datetime.now()
            print(f"[{timestamp.strftime('%H:%M:%S')}] MOTION DETECTED! Waking DSI display...")
            
            # Log motion detection to syslog
            syslog.syslog(syslog.LOG_INFO, f"Motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - DSI display activated")
            
            self.hdmi_on = True
            self._set_hdmi_power(True)
        else:
            timestamp = datetime.datetime.now()
            print(f"[{timestamp.strftime('%H:%M:%S')}] Motion detected (display already on)")
            
            # Log continued motion to syslog (less verbose - only every 10 seconds)
            if (time.time() - self.last_motion_log_time) >= 10:
                syslog.syslog(syslog.LOG_DEBUG, f"Continued motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                self.last_motion_log_time = time.time()
            
        self.last_activity = time.time()

    def _set_hdmi_power(self, power_on):
        """Control DSI display power using multiple methods"""
        try:
            # Set environment for X11 commands
            env = os.environ.copy()
            env['DISPLAY'] = ':0'
            
            if power_on:
                # Try multiple methods to turn on DSI display
                methods = [
                    (['xset', 'dpms', 'force', 'on'], "xset", env),
                    (['xrandr', '--output', 'DSI-1', '--auto'], "xrandr", env),
                    (['vcgencmd', 'display_power', '1'], "vcgencmd", None),
                    (['tvservice', '-p'], "tvservice", None)
                ]
                
                success = False
                for cmd, name, cmd_env in methods:
                    try:
                        result = subprocess.run(cmd, capture_output=True, timeout=5, env=cmd_env or os.environ)
                        if result.returncode == 0:
                            print(f"DSI display powered ON via {name}")
                            success = True
                            break
                    except Exception as e:
                        print(f"Method {name} failed: {e}")
                        continue
                        
                if not success:
                    print("DSI display power on - all methods failed")
            else:
                # Try multiple methods to turn off display
                methods = [
                    (['xset', 'dpms', 'force', 'off'], "xset", env),
                    (['xrandr', '--output', 'DSI-1', '--off'], "xrandr", env),
                    (['vcgencmd', 'display_power', '0'], "vcgencmd", None),
                    (['tvservice', '-o'], "tvservice", None)
                ]
                
                success = False
                for cmd, name, cmd_env in methods:
                    try:
                        result = subprocess.run(cmd, capture_output=True, timeout=5, env=cmd_env or os.environ)
                        if result.returncode == 0:
                            print(f"DSI display powered OFF via {name}")
                            success = True
                            break
                    except Exception as e:
                        print(f"Method {name} failed: {e}")
                        continue
                
                if not success:
                    print("DSI display power off - all methods failed")
                    
        except Exception as e:
            print(f"DSI display power control error: {e}")

    def _check_hdmi_timeout(self):
        """Check if DSI display should be turned off due to inactivity"""
        if self.hdmi_on and self.last_activity > 0:
            if (time.time() - self.last_activity) > self.hdmi_timeout:
                timestamp = datetime.datetime.now()
                print(f"[{timestamp.strftime('%H:%M:%S')}] No motion for {self.hdmi_timeout}s, turning off DSI display...")
                
                # Log DSI display timeout to syslog
                syslog.syslog(syslog.LOG_INFO, f"No motion detected for {self.hdmi_timeout}s at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - DSI display deactivated")
                
                self.hdmi_on = False
                self._set_hdmi_power(False)

    def cleanup(self):
        # Perform cleanup operations
        if self.cleanup_done:
            return
        self.cleanup_done = True
        try:
            # Stop motion detection thread
            if hasattr(self, 'motion_thread') and self.motion_thread and self.motion_thread.is_alive():
                self.stop_event.set()
                self.motion_thread.join(timeout=2)
        except Exception as e:
            pass
            
        # Log shutdown to syslog
        try:
            timestamp = datetime.datetime.now()
            syslog.syslog(syslog.LOG_INFO, f"Motion detector shutting down at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass
        
        # Clean up captured frames
        try:
            if hasattr(self, 'capture_dir'):
                for f in Path(self.capture_dir).glob("frame_*.jpg"):
                    f.unlink()
        except Exception:
            pass
        
        # Close syslog
        try:
            syslog.closelog()
        except Exception:
            pass
        try:
            if self.oled:
                self.oled.close()
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.set_led_mode(1)
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.set_all_led_color(0, 0, 0)
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.set_fan_mode(0)
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.set_fan_frequency(50)
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.set_fan_duty(0, 0)
        except Exception as e:
            pass
        try:
            if self.expansion:
                self.expansion.end()
        except Exception as e:
            pass

    def handle_signal(self, signum, frame):
        # Handle signal to stop the application
        self.stop_event.set()
        self.cleanup()
        sys.exit(0)

    def run_monitor_loop(self):
        """Main monitoring loop - single-threaded infinite loop for both OLED display and fan control"""
        last_fan_pwm = 0
        last_fan_pwm_limit = 0
        temp_threshold_high = 110
        temp_threshold_low = 90
        max_pwm = 255
        min_pwm = 0
        oled_counter = 0  # Counter to control OLED update frequency
        oled_screen = 0   # Which screen to show (0, 1, 2, or 3)
        
        while not self.stop_event.is_set():
            # Check HDMI display timeout (runs every iteration)
            self._check_hdmi_timeout()
            
            # Fan control logic (runs every iteration - every 1 second)
            current_cpu_temp = self.get_raspberry_cpu_temperature()
            current_fan_pwm = self.get_raspberry_fan_pwm()
            
            # Use single print statement to reduce I/O
            print(f"CPU TEMP: {current_cpu_temp}C, FAN PWM: {current_fan_pwm}, HDMI: {'ON' if self.hdmi_on else 'OFF'}")
            
            if current_fan_pwm != -1:
                if last_fan_pwm_limit == 0 and current_fan_pwm > temp_threshold_high:
                    last_fan_pwm = max_pwm
                    self.expansion.set_fan_duty(last_fan_pwm, last_fan_pwm)
                    last_fan_pwm_limit = 1
                elif last_fan_pwm_limit == 1 and current_fan_pwm < temp_threshold_low:
                    last_fan_pwm = min_pwm
                    self.expansion.set_fan_duty(last_fan_pwm, last_fan_pwm)
                    last_fan_pwm_limit = 0
            
            # OLED update logic (runs every 3 seconds, always on)
            if oled_counter % 3 == 0:
                self.oled.clear()
                if oled_screen == 0:
                    # Screen 1: System Parameters
                    self.oled.draw_text("PI Parameters", position=(0, 0), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['cpu'].format(self.get_raspberry_cpu_usage()), position=(0, 16), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['mem'].format(self.get_raspberry_memory_usage()), position=(0, 32), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['disk'].format(self.get_raspberry_disk_usage()), position=(0, 48), font_size=self.font_size)
                elif oled_screen == 1:
                    # Screen 2: Date/Time/LED
                    self.oled.draw_text(self._format_strings['date'].format(self.get_raspberry_date()), position=(0, 0), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['week'].format(self.get_raspberry_weekday()), position=(0, 16), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['time'].format(self.get_raspberry_time()), position=(0, 32), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['led_mode'].format(self.get_computer_led_mode()), position=(0, 48), font_size=self.font_size)
                elif oled_screen == 2:
                    # Screen 3: Temperature/Fan
                    self.oled.draw_text(self._format_strings['pi_temp'].format(current_cpu_temp), position=(0, 0), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['pc_temp'].format(self.get_computer_temperature()), position=(0, 16), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['fan_mode'].format(self.get_computer_fan_mode()), position=(0, 32), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['fan_duty'].format(int(float(self.get_computer_fan_duty()/255.0)*100)), position=(0, 48), font_size=self.font_size)
                else:  # oled_screen == 3
                    # Screen 4: Days since reboot with large bold numbers
                    days = self.get_days_since_reboot()
                    self.oled.draw_text("Days Since:", position=(0, 0), font_size=14)
                    # Draw large day number - use larger font and center it
                    day_str = str(days)
                    self.oled.draw_text(day_str, position=(40, 25), font_size=40)
                    # Add "days" label below
                    self.oled.draw_text("days" if days != 1 else "day", position=(45, 50), font_size=10)
                
                self.oled.show()
                oled_screen = (oled_screen + 1) % 4  # Cycle through screens 0, 1, 2, 3
            
            oled_counter += 1
            time.sleep(1)  # Base interval of 1 second

if __name__ == "__main__":
    pi_monitor = None

    try:
        time.sleep(1)

        pi_monitor = Pi_Monitor()
        # Use simple infinite loop instead of threading
        pi_monitor.run_monitor_loop()

    except KeyboardInterrupt:
        print("\nShutdown requested by user (Ctrl+C)")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if pi_monitor is not None:
            pi_monitor.stop_event.set()
            pi_monitor.cleanup()
        print("Monitor stopped.")
