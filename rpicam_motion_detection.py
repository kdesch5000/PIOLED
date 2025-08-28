#!/usr/bin/env python3
"""
Motion detection using rpicam tools and image processing
Works with Pi Camera v1/v2/v3 on Pi 5
"""

import subprocess
import time
import threading
import os
import numpy as np
import syslog
from datetime import datetime
from pathlib import Path

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("OpenCV not available - using basic image comparison")

class RPiCamMotionDetector:
    def __init__(self, sensitivity=30, min_area=1000):
        self.sensitivity = sensitivity  # Motion detection sensitivity (0-100)
        self.min_area = min_area       # Minimum changed pixels to trigger
        self.hdmi_on = False
        self.hdmi_timeout = 60  # 60 seconds default
        self.last_motion_time = 0
        self.running = False
        self.display_thread = None
        self.capture_dir = "/tmp/motion_frames"
        self.frame_count = 0
        self.prev_frame = None
        
        # Initialize syslog for motion detection events
        syslog.openlog("RPiCamMotionDetector", syslog.LOG_PID, syslog.LOG_DAEMON)
        
        # Create capture directory
        Path(self.capture_dir).mkdir(exist_ok=True)
        
    def wake_hdmi_display(self):
        """Wake up HDMI display using multiple methods"""
        if not self.hdmi_on:
            timestamp = datetime.now()
            print(f"[{timestamp.strftime('%H:%M:%S')}] MOTION DETECTED! Waking HDMI display...")
            
            # Log motion detection to syslog
            syslog.syslog(syslog.LOG_INFO, f"Motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - HDMI display activated")
            
            self.hdmi_on = True
            
            # Try multiple methods to turn on HDMI display
            methods_tried = []
            success = False
            
            # Method 1: vcgencmd display_power
            try:
                result = subprocess.run(['vcgencmd', 'display_power', '1'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    methods_tried.append("vcgencmd: SUCCESS")
                    success = True
                else:
                    methods_tried.append(f"vcgencmd: FAILED ({result.stderr.strip()})")
            except Exception as e:
                methods_tried.append(f"vcgencmd: ERROR ({e})")
            
            # Method 2: tvservice 
            try:
                result = subprocess.run(['tvservice', '-p'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    methods_tried.append("tvservice: SUCCESS")
                    success = True
                else:
                    methods_tried.append(f"tvservice: FAILED")
            except Exception as e:
                methods_tried.append(f"tvservice: ERROR ({e})")
            
            # Method 3: Try xset if X11 is running
            try:
                result = subprocess.run(['xset', 'dpms', 'force', 'on'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    methods_tried.append("xset: SUCCESS")
                    success = True
                else:
                    methods_tried.append(f"xset: FAILED")
            except Exception as e:
                methods_tried.append(f"xset: ERROR ({e})")
            
            # Method 4: Try wlr-randr for Wayland
            try:
                result = subprocess.run(['wlr-randr', '--output', 'HDMI-A-1', '--on'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    methods_tried.append("wlr-randr: SUCCESS")
                    success = True
                else:
                    methods_tried.append(f"wlr-randr: FAILED")
            except Exception as e:
                methods_tried.append(f"wlr-randr: ERROR ({e})")
            
            # Method 5: Try writing to sys files directly
            try:
                with open('/sys/class/drm/card1-HDMI-A-1/status', 'r') as f:
                    status = f.read().strip()
                    if status == 'connected':
                        methods_tried.append("sysfs: Display connected")
                        success = True
            except Exception as e:
                methods_tried.append(f"sysfs: ERROR ({e})")
            
            # Method 6: Simple framebuffer wake (write to fb)
            try:
                with open('/dev/fb0', 'wb') as fb:
                    fb.write(b'\x00' * 1024)  # Write some data to wake framebuffer
                methods_tried.append("framebuffer: ATTEMPTED")
                success = True
            except Exception as e:
                methods_tried.append(f"framebuffer: ERROR ({e})")
            
            if success:
                print("HDMI display wake attempted successfully")
            else:
                print("All HDMI wake methods failed")
            
            # Show which methods were tried (for debugging)
            print(f"Methods tried: {', '.join(methods_tried)}")
            
        else:
            timestamp = datetime.now()
            print(f"[{timestamp.strftime('%H:%M:%S')}] Motion detected (display already on)")
            
            # Log continued motion to syslog (less verbose - only every 10 seconds)
            if not hasattr(self, 'last_motion_log_time'):
                self.last_motion_log_time = 0
            
            if (time.time() - self.last_motion_log_time) >= 10:
                syslog.syslog(syslog.LOG_DEBUG, f"Continued motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                self.last_motion_log_time = time.time()
            
        self.last_motion_time = time.time()
        
    def check_hdmi_timeout(self):
        """Check if HDMI should be turned off due to no motion"""
        while self.running:
            if self.hdmi_on and self.last_motion_time > 0:
                if (time.time() - self.last_motion_time) > self.hdmi_timeout:
                    timestamp = datetime.now()
                    print(f"[{timestamp.strftime('%H:%M:%S')}] No motion for {self.hdmi_timeout}s, turning off HDMI...")
                    
                    # Log HDMI display timeout to syslog
                    syslog.syslog(syslog.LOG_INFO, f"No motion detected for {self.hdmi_timeout}s at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - HDMI display deactivated")
                    
                    self.hdmi_on = False
                    try:
                        # Try multiple methods to turn off display
                        methods = [
                            (['vcgencmd', 'display_power', '0'], "vcgencmd"),
                            (['xset', 'dpms', 'force', 'off'], "xset"),
                            (['tvservice', '-o'], "tvservice")
                        ]
                        
                        success = False
                        for cmd, name in methods:
                            try:
                                result = subprocess.run(cmd, capture_output=True, timeout=5)
                                if result.returncode == 0:
                                    print(f"HDMI display powered OFF via {name}")
                                    success = True
                                    break
                            except Exception:
                                continue
                        
                        if not success:
                            print("HDMI display power off - all methods failed")
                            
                    except Exception as e:
                        print(f"Display power control error: {e}")
            time.sleep(5)  # Check every 5 seconds
            
    def capture_frame(self, filename):
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
        except subprocess.TimeoutExpired:
            print("Camera capture timeout")
            return False
        except Exception as e:
            print(f"Camera capture error: {e}")
            return False
            
    def compare_frames_opencv(self, frame1_path, frame2_path):
        """Compare two frames using OpenCV (more accurate)"""
        if not OPENCV_AVAILABLE:
            return False
            
        try:
            # Read images
            img1 = cv2.imread(frame1_path, cv2.IMREAD_GRAYSCALE)
            img2 = cv2.imread(frame2_path, cv2.IMREAD_GRAYSCALE)
            
            if img1 is None or img2 is None:
                return False
                
            # Calculate difference
            diff = cv2.absdiff(img1, img2)
            
            # Apply threshold
            _, thresh = cv2.threshold(diff, self.sensitivity, 255, cv2.THRESH_BINARY)
            
            # Count changed pixels
            changed_pixels = cv2.countNonZero(thresh)
            
            return changed_pixels > self.min_area
            
        except Exception as e:
            print(f"OpenCV comparison error: {e}")
            return False
            
    def compare_frames_basic(self, frame1_path, frame2_path):
        """Basic frame comparison without OpenCV"""
        try:
            # Get file sizes as a basic comparison
            size1 = os.path.getsize(frame1_path)
            size2 = os.path.getsize(frame2_path)
            
            # Calculate percentage difference
            if size1 == 0:
                return False
                
            diff_percent = abs(size1 - size2) / size1 * 100
            
            # If file sizes differ significantly, assume motion
            return diff_percent > (self.sensitivity / 10)  # Convert sensitivity to percentage
            
        except Exception as e:
            print(f"Basic comparison error: {e}")
            return False
            
    def detect_motion(self, current_frame, previous_frame):
        """Detect motion between two frames"""
        if not os.path.exists(current_frame) or not os.path.exists(previous_frame):
            return False
            
        # Try OpenCV method first, fallback to basic
        if OPENCV_AVAILABLE:
            return self.compare_frames_opencv(previous_frame, current_frame)
        else:
            return self.compare_frames_basic(previous_frame, current_frame)
            
    def cleanup_old_frames(self):
        """Keep only the last 2 frames to save space"""
        try:
            files = list(Path(self.capture_dir).glob("frame_*.jpg"))
            if len(files) > 2:
                # Sort by modification time and remove oldest
                files.sort(key=lambda x: x.stat().st_mtime)
                for f in files[:-2]:
                    f.unlink()
        except Exception:
            pass
            
    def run(self, duration=None):
        """Main motion detection loop"""
        self.running = True
        
        # Start display timeout thread
        self.display_thread = threading.Thread(target=self.check_hdmi_timeout, daemon=True)
        self.display_thread.start()
        
        # Log startup to syslog
        timestamp = datetime.now()
        syslog.syslog(syslog.LOG_INFO, f"Motion detector started at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - Sensitivity: {self.sensitivity}, Timeout: {self.hdmi_timeout}s")
        
        print("RPi Camera Motion Detection Started")
        print(f"Sensitivity: {self.sensitivity}, Min area: {self.min_area}")
        print(f"HDMI timeout: {self.hdmi_timeout}s")
        print(f"OpenCV available: {OPENCV_AVAILABLE}")
        print("Press Ctrl+C to stop")
        print("-" * 50)
        
        start_time = time.time()
        
        try:
            while self.running:
                # Check duration limit
                if duration and (time.time() - start_time) > duration:
                    print(f"Duration limit ({duration}s) reached")
                    break
                    
                current_frame = f"{self.capture_dir}/frame_{self.frame_count % 2}.jpg"
                previous_frame = f"{self.capture_dir}/frame_{(self.frame_count + 1) % 2}.jpg"
                
                # Capture current frame
                if not self.capture_frame(current_frame):
                    print("Failed to capture frame, retrying...")
                    time.sleep(1)
                    continue
                    
                # Check for motion if we have a previous frame
                if self.frame_count > 0 and os.path.exists(previous_frame):
                    if self.detect_motion(current_frame, previous_frame):
                        self.wake_hdmi_display()
                        
                self.frame_count += 1
                
                # Status update every 10 frames
                if self.frame_count % 10 == 0:
                    status = "ON" if self.hdmi_on else "OFF"
                    print(f"Frame {self.frame_count}, HDMI: {status}")
                    
                # Cleanup old frames periodically
                if self.frame_count % 20 == 0:
                    self.cleanup_old_frames()
                    
                # Small delay between captures
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        self.running = False
        
        # Log shutdown to syslog
        timestamp = datetime.now()
        syslog.syslog(syslog.LOG_INFO, f"Motion detector shutting down at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Clean up captured frames
        try:
            for f in Path(self.capture_dir).glob("frame_*.jpg"):
                f.unlink()
        except Exception:
            pass
            
        # Turn off HDMI if it was on
        if self.hdmi_on:
            try:
                # Try multiple methods to turn off display
                methods = [
                    (['vcgencmd', 'display_power', '0'], "vcgencmd"),
                    (['xset', 'dpms', 'force', 'off'], "xset"),
                    (['tvservice', '-o'], "tvservice")
                ]
                
                for cmd, name in methods:
                    try:
                        result = subprocess.run(cmd, capture_output=True, timeout=5)
                        if result.returncode == 0:
                            print(f"HDMI display powered OFF via {name}")
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        
        # Close syslog
        syslog.closelog()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='RPi Camera Motion Detection')
    parser.add_argument('--sensitivity', '-s', type=int, default=30, help='Motion sensitivity 0-100 (default: 30)')
    parser.add_argument('--min-area', '-a', type=int, default=1000, help='Minimum changed pixels (default: 1000)')
    parser.add_argument('--timeout', '-t', type=int, default=60, help='HDMI timeout in seconds (default: 60)')
    parser.add_argument('--duration', '-d', type=int, help='Run for specified seconds (default: infinite)')
    
    args = parser.parse_args()
    
    detector = RPiCamMotionDetector(
        sensitivity=args.sensitivity,
        min_area=args.min_area
    )
    detector.hdmi_timeout = args.timeout
    
    detector.run(duration=args.duration)

if __name__ == "__main__":
    main()