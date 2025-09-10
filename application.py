# Thanks to @ricardodemauro for the code modifications.
## This is a rewrite of the application.py with:
## native method instead of syscall
## no threading (less cpu usage)
## ached the cooling_fan path
## some python optimizations
## It uses less memory and less cpu time
## Added individual LED system indicators
##
## For detailed documentation of all features, modifications, and service management:
## See: application-modifications.md

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

try:
    import RPi.GPIO as GPIO
    PIR_AVAILABLE = True
except ImportError:
    PIR_AVAILABLE = False
    print("⚠ RPi.GPIO not available - PIR sensor disabled, using video motion detection only")

class Pi_Monitor:
    __slots__ = ['oled', 'expansion', 'font_size', 'cleanup_done',
                 'stop_event', '_fan_pwm_path', '_format_strings',
                 'hdmi_on', 'hdmi_timeout', 'last_activity',
                 'motion_thread', 'capture_dir', 'frame_count', 'motion_sensitivity', 'last_motion_log_time',
                 'last_disk_activity', 'last_disk_bytes', 'pir_pin', 'pir_available', 'pir_initialized', 'use_camera_fallback', 'last_pir_log_time']

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

        # Motion detection configuration
        self.motion_thread = None
        
        # PIR sensor configuration
        self.pir_pin = 23
        self.pir_available = PIR_AVAILABLE
        self.pir_initialized = False
        
        # Camera motion detection configuration (fallback)
        self.capture_dir = "/tmp/motion_frames"
        self.frame_count = 0
        self.motion_sensitivity = 30
        self.last_motion_log_time = 0
        self.use_camera_fallback = False
        self.last_pir_log_time = 0  # Rate limit PIR logging

        # Disk activity tracking for LED indicator
        self.last_disk_activity = time.time()
        self.last_disk_bytes = 0

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
            print("✓ OLED display initialized")
        except Exception as e:
            print(f"✗ OLED initialization failed: {e}")
            sys.exit(1)

        try:
            self.expansion = Expansion()
            # Set LED mode to 1 for individual LED control
            self.expansion.set_led_mode(1)
            print("✓ LED system set to mode 1 (individual control)")
            
            # Initialize all LEDs to off
            for i in range(4):
                self.expansion.set_led_color(i, 0, 0, 0)
            print("✓ All LEDs initialized to OFF")
            
            # Initialize fan
            self.expansion.set_fan_mode(1)
            print("✓ Fan system initialized")
            
        except Exception as e:
            print(f"✗ Expansion board initialization failed: {e}")
            sys.exit(1)

        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        # Initialize fan PWM path cache
        self._find_fan_pwm_path()

        # Initialize disk monitoring for LED indicators
        self._init_disk_monitoring()

        # Initialize motion detection (PIR primary, camera fallback)
        self._init_motion_detection()

        # Log LED indicator meanings at startup
        self._log_led_indicators()

    def _init_disk_monitoring(self):
        """Initialize disk activity monitoring for LED indicator"""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.last_disk_bytes = disk_io.read_bytes + disk_io.write_bytes
            print("✓ Disk activity monitoring initialized")
        except Exception:
            self.last_disk_bytes = 0
            print("⚠ Disk activity monitoring failed to initialize")

    def _log_led_indicators(self):
        """Log what each LED indicator means at startup"""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print("\n" + "="*60)
        print("LED SYSTEM INDICATORS - STARTUP SUMMARY")
        print("="*60)
        print("LED 0 - TEMPERATURE INDICATOR:")
        print("  🟢 Green:  < 40°C (Cool and Safe)")
        print("  🟡 Yellow: 40-50°C (Getting Warm)")
        print("  🟠 Orange: 50-60°C (Hot - Fan Running)")
        print("  🔴 Red:    > 60°C (Very Hot)")
        print()
        print("LED 1 - CPU LOAD INDICATOR:")
        print("  🔵 Blue:   < 25% (Low Load)")
        print("  🟢 Green:  25-50% (Light Load)")
        print("  🟡 Yellow: 50-75% (Moderate Load)")
        print("  🔴 Red:    > 75% (Heavy Load)")
        print()
        print("LED 2 - DISK ACTIVITY INDICATOR:")
        print("  🔵 Dim Blue: Idle (No Recent Activity)")
        print("  ⚪ White:    Active I/O or Recent Activity")
        print("  🔴 Red:      Disk > 90% Full")
        print()
        print("LED 3 - SYSTEM HEALTH (Traffic Light):")
        print("  🟢 Green:  All Systems Normal")
        print("  🟡 Yellow: Warning (Any Metric Elevated)")
        print("  🔴 Red:    Critical (Temp>70°C, CPU>90%, Mem>90%, Disk>95%)")
        print("="*60)
        print(f"LED System Monitoring Started at {timestamp}")
        print("="*60 + "\n")

        # Also log to syslog
        syslog.syslog(syslog.LOG_INFO, f"LED System Indicators initialized at {timestamp}")
        syslog.syslog(syslog.LOG_INFO, "LED0:Temperature LED1:CPU-Load LED2:Disk-Activity LED3:System-Health")

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
            # Parse "up X weeks, Y days, Z hours, W minutes" format
            total_days = 0
            parts = uptime_str.split()
            
            for i, part in enumerate(parts):
                if part.isdigit():
                    value = int(part)
                    # Check the next part for time unit
                    if i + 1 < len(parts):
                        unit = parts[i + 1].rstrip(',')
                        if 'week' in unit:
                            total_days += value * 7
                        elif 'day' in unit:
                            total_days += value
            
            return total_days
        except Exception:
            return 0

    def check_disk_activity(self):
        """Check for disk activity and return activity status"""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                current_bytes = disk_io.read_bytes + disk_io.write_bytes
                if current_bytes != self.last_disk_bytes:
                    self.last_disk_activity = time.time()
                    self.last_disk_bytes = current_bytes
                    return True  # Activity detected
            return False  # No activity
        except Exception:
            return False

    # LED Control Functions for Individual System Indicators
    # See application-modifications.md for complete LED indicator documentation

    def update_temperature_led(self, temp):
        """LED 0: Temperature Heat Map"""
        try:
            if temp < 40:
                self.expansion.set_led_color(0, 0, 255, 0)      # Green - Cool
            elif temp < 50:
                self.expansion.set_led_color(0, 255, 255, 0)    # Yellow - Warm
            elif temp < 60:
                self.expansion.set_led_color(0, 255, 165, 0)    # Orange - Hot
            else:
                self.expansion.set_led_color(0, 255, 0, 0)      # Red - Very hot
        except Exception as e:
            pass  # Silently continue if LED update fails

    def update_cpu_load_led(self, cpu_percent):
        """LED 1: CPU/System Load Indicator"""
        try:
            if cpu_percent < 25:
                self.expansion.set_led_color(1, 0, 0, 255)      # Blue - Low load
            elif cpu_percent < 50:
                self.expansion.set_led_color(1, 0, 255, 0)      # Green - Light load
            elif cpu_percent < 75:
                self.expansion.set_led_color(1, 255, 255, 0)    # Yellow - Moderate load
            else:
                self.expansion.set_led_color(1, 255, 0, 0)      # Red - Heavy load
        except Exception as e:
            pass  # Silently continue if LED update fails

    def update_disk_activity_led(self, disk_usage_percent, has_activity):
        """LED 2: Disk Activity Indicator"""
        try:
            if disk_usage_percent > 90:
                # Solid red for disk > 90% full
                self.expansion.set_led_color(2, 255, 0, 0)      # Red - Disk full
            elif has_activity:
                # Brief white flash for activity
                self.expansion.set_led_color(2, 255, 255, 255)  # White - Activity
            elif (time.time() - self.last_disk_activity) < 2:
                # Keep showing activity for 2 seconds after last activity
                self.expansion.set_led_color(2, 255, 255, 255)  # White - Recent activity
            else:
                # Blue for idle
                self.expansion.set_led_color(2, 0, 0, 100)      # Dim blue - Idle
        except Exception as e:
            pass  # Silently continue if LED update fails

    def update_system_health_led(self, temp, cpu_percent, mem_percent, disk_percent):
        """LED 3: Traffic Light System Health"""
        try:
            # Critical conditions (Red)
            critical_conditions = (
                temp > 70 or 
                cpu_percent > 90 or 
                mem_percent > 90 or 
                disk_percent > 95
            )
            
            # Warning conditions (Yellow)
            warning_conditions = (
                temp > 55 or 
                cpu_percent > 75 or 
                mem_percent > 80 or 
                disk_percent > 85
            )
            
            if critical_conditions:
                self.expansion.set_led_color(3, 255, 0, 0)      # Red - Critical
            elif warning_conditions:
                self.expansion.set_led_color(3, 255, 255, 0)    # Yellow - Warning
            else:
                self.expansion.set_led_color(3, 0, 255, 0)      # Green - All good
        except Exception as e:
            pass  # Silently continue if LED update fails

    def blink_motion_indicator(self):
        """Blink LED 3 (system health) 3 times to indicate motion detected"""
        try:
            # Simple blink without interfering with main loop LED updates
            # Just blink 3 times and let the main loop restore the proper color
            for i in range(3):
                # Flash bright white
                self.expansion.set_led_color(3, 255, 255, 255)  # Bright white
                time.sleep(0.08)
                # Turn off briefly
                self.expansion.set_led_color(3, 0, 0, 0)        # Off
                time.sleep(0.08)
            
            # Don't restore color here - let the main loop handle it
            # The main loop will restore proper system health color on next update
            
        except Exception as e:
            pass  # Silently continue if LED blink fails

    def _init_motion_detection(self):
        """Initialize motion detection - PIR primary, camera fallback
        
        Motion Detection System (see application-modifications.md for details):
        - Primary: PIR sensor on GPIO 23 (HC-SR501)
        - Fallback: Camera motion detection via rpicam-still
        - Auto-fallback if PIR unavailable or fails
        """
        motion_method = "None"
        
        if self.pir_available:
            try:
                self._init_pir_sensor()
                motion_method = "PIR sensor (primary)"
            except Exception as e:
                print(f"⚠ PIR sensor initialization failed: {e}")
                print("  Falling back to camera motion detection...")
                self.pir_available = False
        
        if not self.pir_available:
            self._start_camera_motion_detection()
            motion_method = "Camera motion detection (fallback)"
            self.use_camera_fallback = True
        
        print(f"✓ Motion detection initialized: {motion_method}")
        
        # Log startup to syslog
        timestamp = datetime.datetime.now()
        syslog.syslog(syslog.LOG_INFO, f"Motion detection started at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - Method: {motion_method}, Timeout: {self.hdmi_timeout}s")
    
    def _init_pir_sensor(self):
        """Initialize PIR motion sensor"""
        if not PIR_AVAILABLE:
            raise Exception("RPi.GPIO not available")
        
        try:
            # GPIO setup
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pir_pin, GPIO.IN)
            
            print(f"✓ PIR sensor initialized on GPIO {self.pir_pin}")
            print("  Waiting 5 seconds for sensor to stabilize...")
            time.sleep(5)  # Reduced from 30s for faster startup
            print("  PIR sensor ready")
            
            # Start PIR monitoring thread
            self.motion_thread = threading.Thread(target=self._pir_motion_loop, daemon=True)
            self.motion_thread.start()
            
            self.pir_initialized = True
            
        except Exception as e:
            if GPIO:
                GPIO.cleanup()
            raise e
    
    def _pir_motion_loop(self):
        """PIR motion detection loop"""
        last_state = False
        motion_start_time = 0
        
        try:
            while not self.stop_event.is_set():
                current_state = GPIO.input(self.pir_pin)
                current_time = time.time()
                timestamp = datetime.datetime.now()
                
                if current_state and not last_state:
                    # Motion started - only log every 30 seconds to reduce verbosity
                    motion_start_time = current_time
                    if (current_time - self.last_pir_log_time) >= 30:
                        print(f"[{timestamp.strftime('%H:%M:%S')}] PIR motion detected")
                        syslog.syslog(syslog.LOG_INFO, f"PIR motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        self.last_pir_log_time = current_time
                    self._wake_hdmi_display()
                
                elif not current_state and last_state:
                    # Motion ended - reduce logging verbosity
                    if motion_start_time > 0:
                        duration = current_time - motion_start_time
                        # Only log motion end for longer durations (> 5 seconds)
                        if duration > 5:
                            syslog.syslog(syslog.LOG_DEBUG, f"PIR motion ended - duration: {duration:.1f}s")
                
                last_state = current_state
                time.sleep(0.2)  # Check every 200ms
                
        except Exception as e:
            print(f"PIR motion detection error: {e}")
            syslog.syslog(syslog.LOG_ERR, f"PIR motion detection error: {e}")
    
    def _start_camera_motion_detection(self):
        """Start camera motion detection thread (fallback method)"""
        # Create capture directory
        Path(self.capture_dir).mkdir(exist_ok=True)
        
        self.motion_thread = threading.Thread(target=self._camera_motion_loop, daemon=True)
        self.motion_thread.start()
        print("✓ Camera motion detection started (fallback method)")

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
                            # Rate limit camera motion logging
                            current_time = time.time()
                            if (current_time - self.last_motion_log_time) >= 30:
                                timestamp = datetime.datetime.now()
                                print(f"[{timestamp.strftime('%H:%M:%S')}] Camera motion detected")
                                syslog.syslog(syslog.LOG_INFO, f"Camera motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                                self.last_motion_log_time = current_time
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
        motion_source = "PIR" if self.pir_available and self.pir_initialized else "Camera"
        
        # Always blink LED 3 to indicate motion detected (non-blocking)
        threading.Thread(target=self.blink_motion_indicator, daemon=True).start()
        
        if not self.hdmi_on:
            # Only log display wake events, not every motion detection
            syslog.syslog(syslog.LOG_INFO, f"Display activated by {motion_source} motion")
            self.hdmi_on = True
            self._set_hdmi_power(True)
        # Remove logging for continued motion when display is already on

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
                ]

                success = False
                for cmd, name, cmd_env in methods:
                    try:
                        result = subprocess.run(cmd, capture_output=True, timeout=5, env=cmd_env or os.environ)
                        if result.returncode == 0:
                            print(f"DSI display powered ON via {name}")
                            success = True
                            # Don't break - run both commands for better reliability
                        else:
                            print(f"Method {name} returned code {result.returncode}")
                    except Exception as e:
                        print(f"Method {name} failed: {e}")
                        continue

                # Always consider it successful if xset or xrandr ran without exception
                # The display state tracking is more important than command success codes
                
            else:
                # Try multiple methods to turn off display
                methods = [
                    (['xset', 'dpms', 'force', 'standby'], "xset standby", env),
                    (['xset', 'dpms', 'force', 'off'], "xset off", env),
                    (['xrandr', '--output', 'DSI-1', '--off'], "xrandr off", env),
                ]

                success = False
                for cmd, name, cmd_env in methods:
                    try:
                        result = subprocess.run(cmd, capture_output=True, timeout=5, env=cmd_env or os.environ)
                        if result.returncode == 0:
                            print(f"DSI display powered OFF via {name}")
                            success = True
                            # Don't break - run multiple methods for better reliability
                        else:
                            print(f"Method {name} returned code {result.returncode}")
                    except Exception as e:
                        print(f"Method {name} failed: {e}")
                        continue

                # Force the internal state - assume display is off after running commands
                print("DSI display power off commands executed")

        except Exception as e:
            print(f"DSI display power control error: {e}")

    def _check_hdmi_timeout(self):
        """Check if DSI display should be turned off due to inactivity"""
        if self.hdmi_on and self.last_activity > 0:
            if (time.time() - self.last_activity) > self.hdmi_timeout:
                # Reduced verbosity - just log the timeout event
                syslog.syslog(syslog.LOG_INFO, f"Display deactivated after {self.hdmi_timeout}s timeout")
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
        
        # Cleanup PIR sensor GPIO
        try:
            if hasattr(self, 'pir_initialized') and self.pir_initialized and PIR_AVAILABLE:
                GPIO.cleanup()
                print("✓ PIR sensor GPIO cleaned up")
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
                # Turn off all individual LEDs
                for i in range(4):
                    self.expansion.set_led_color(i, 0, 0, 0)
                print("✓ All LEDs turned off")
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
        temp_threshold_high = 50  # FIXED: Changed from 110 to 50°C
        temp_threshold_low = 40   # FIXED: Changed from 90 to 40°C
        max_pwm = 255
        min_pwm = 0
        oled_counter = 0  # Counter to control OLED update frequency
        oled_screen = 0   # Which screen to show (0, 1, 2, or 3)

        print("Starting main monitoring loop with LED system indicators...")

        while not self.stop_event.is_set():
            # Check HDMI display timeout (runs every iteration)
            self._check_hdmi_timeout()

            # Get all system metrics for both fan control and LED indicators
            current_cpu_temp = self.get_raspberry_cpu_temperature()
            current_cpu_usage = self.get_raspberry_cpu_usage()
            current_mem_usage = self.get_raspberry_memory_usage()
            current_disk_usage = self.get_raspberry_disk_usage()
            current_fan_pwm = self.get_raspberry_fan_pwm()
            disk_activity = self.check_disk_activity()

            # Update all LED system indicators
            self.update_temperature_led(current_cpu_temp)
            self.update_cpu_load_led(current_cpu_usage)
            self.update_disk_activity_led(current_disk_usage, disk_activity)
            self.update_system_health_led(current_cpu_temp, current_cpu_usage, current_mem_usage, current_disk_usage)

            # Enhanced status output including all metrics (commented out to reduce log verbosity)
            # print(f"TEMP: {current_cpu_temp:.1f}°C, CPU: {current_cpu_usage:.1f}%, MEM: {current_mem_usage:.1f}%, DISK: {current_disk_usage:.1f}%, FAN: {current_fan_pwm}, HDMI: {'ON' if self.hdmi_on else 'OFF'}")

            # FIXED: Compare current_cpu_temp instead of current_fan_pwm against temperature thresholds
            if current_fan_pwm != -1:  # Only proceed if we can read fan PWM
                if last_fan_pwm_limit == 0 and current_cpu_temp > temp_threshold_high:
                    last_fan_pwm = max_pwm
                    self.expansion.set_fan_duty(last_fan_pwm, last_fan_pwm)
                    last_fan_pwm_limit = 1
                    print(f"Fan turned ON - CPU temp {current_cpu_temp}°C > {temp_threshold_high}°C")
                elif last_fan_pwm_limit == 1 and current_cpu_temp < temp_threshold_low:
                    last_fan_pwm = min_pwm
                    self.expansion.set_fan_duty(last_fan_pwm, last_fan_pwm)
                    last_fan_pwm_limit = 0
                    print(f"Fan turned OFF - CPU temp {current_cpu_temp}°C < {temp_threshold_low}°C")

            # OLED update logic (runs every 3 seconds, always on)
            if oled_counter % 3 == 0:
                self.oled.clear()
                if oled_screen == 0:
                    # Screen 1: System Parameters
                    self.oled.draw_text("PI Parameters", position=(0, 0), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['cpu'].format(current_cpu_usage), position=(0, 16), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['mem'].format(current_mem_usage), position=(0, 32), font_size=self.font_size)
                    self.oled.draw_text(self._format_strings['disk'].format(current_disk_usage), position=(0, 48), font_size=self.font_size)
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
                    # Draw large day number - dynamically center based on digit count
                    day_str = str(days)
                    # Calculate x position to center the text (approx 24 pixels per digit at font size 40)
                    text_width = len(day_str) * 24
                    x_pos = max(0, (128 - text_width) // 2)  # Center on 128px wide display
                    self.oled.draw_text(day_str, position=(x_pos, 15), font_size=40)

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

