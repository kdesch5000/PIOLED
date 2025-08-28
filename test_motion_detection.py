#!/usr/bin/env python3
"""
Standalone motion detection test program using OpenCV
Detects motion from camera and simulates HDMI display wake-up
"""

import cv2
import time
import subprocess
import threading
from datetime import datetime

class MotionDetector:
    def __init__(self, camera_index=0, threshold=500, min_area=1000):
        self.camera_index = camera_index
        self.threshold = threshold  # Motion detection sensitivity
        self.min_area = min_area    # Minimum area to consider as motion
        self.background_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        self.cap = None
        self.running = False
        self.hdmi_on = False
        self.hdmi_timeout = 30  # 30 seconds for testing (vs 5 min in production)
        self.last_motion_time = 0
        self.display_thread = None
        
    def initialize_camera(self):
        """Initialize camera capture"""
        print(f"Initializing camera {self.camera_index}...")
        
        # Try Pi camera first with specific backend
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        
        if not self.cap.isOpened():
            print(f"V4L2 failed, trying default backend...")
            self.cap = cv2.VideoCapture(self.camera_index)
            
        if not self.cap.isOpened():
            print(f"Error: Could not open camera {self.camera_index}")
            return False
            
        # Set camera properties for Pi camera
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 15)
        
        # Set specific format that Pi camera supports
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))
        
        # Let camera warm up and test a frame
        print("Warming up camera...")
        time.sleep(3)
        
        # Test if we can actually read frames
        for i in range(5):
            ret, frame = self.cap.read()
            if ret:
                print(f"Test frame {i+1}: {frame.shape} - OK")
                break
            time.sleep(0.5)
        else:
            print("Error: Could not read frames from camera")
            return False
        
        print("Camera initialized successfully")
        return True
        
    def wake_hdmi_display(self):
        """Simulate HDMI display wake-up"""
        if not self.hdmi_on:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] MOTION DETECTED! Waking HDMI display...")
            self.hdmi_on = True
            try:
                # Turn on HDMI display
                subprocess.run(['vcgencmd', 'display_power', '1'], check=True)
                subprocess.run(['tvservice', '-p'], check=False)
                print("HDMI display powered ON")
            except Exception as e:
                print(f"Display power control error: {e}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Motion detected (display already on)")
            
        self.last_motion_time = time.time()
        
    def check_hdmi_timeout(self):
        """Check if HDMI should be turned off due to no motion"""
        while self.running:
            if self.hdmi_on and self.last_motion_time > 0:
                if (time.time() - self.last_motion_time) > self.hdmi_timeout:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No motion for {self.hdmi_timeout}s, turning off HDMI...")
                    self.hdmi_on = False
                    try:
                        subprocess.run(['vcgencmd', 'display_power', '0'], check=True)
                        print("HDMI display powered OFF")
                    except Exception as e:
                        print(f"Display power control error: {e}")
            time.sleep(5)  # Check every 5 seconds
            
    def detect_motion(self, frame):
        """Detect motion in the current frame"""
        # Apply background subtraction
        fg_mask = self.background_subtractor.apply(frame)
        
        # Remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        motion_detected = False
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > self.min_area:
                motion_detected = True
                # Draw bounding box around motion (for debugging)
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
        return motion_detected, frame, fg_mask
        
    def run(self, show_video=False, debug=False):
        """Main motion detection loop"""
        if not self.initialize_camera():
            return
            
        self.running = True
        
        # Start display timeout thread
        self.display_thread = threading.Thread(target=self.check_hdmi_timeout, daemon=True)
        self.display_thread.start()
        
        print("Starting motion detection...")
        print("Press 'q' to quit, 'r' to reset background model")
        print(f"Motion sensitivity: {self.threshold}, Min area: {self.min_area}")
        
        try:
            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    print("Error reading from camera")
                    break
                    
                # Detect motion
                motion_detected, annotated_frame, fg_mask = self.detect_motion(frame)
                
                if motion_detected:
                    self.wake_hdmi_display()
                    
                # Show video feed if requested
                if show_video:
                    # Add status text
                    status = "HDMI: ON" if self.hdmi_on else "HDMI: OFF"
                    cv2.putText(annotated_frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0) if self.hdmi_on else (0, 0, 255), 2)
                    
                    cv2.imshow('Motion Detection', annotated_frame)
                    
                    if debug:
                        cv2.imshow('Motion Mask', fg_mask)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    elif key == ord('r'):
                        print("Resetting background model...")
                        self.background_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
                        
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
                
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            
        finally:
            self.cleanup()
            
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        self.running = False
        
        if self.cap:
            self.cap.release()
            
        cv2.destroyAllWindows()
        
        # Turn off HDMI if it was on
        if self.hdmi_on:
            try:
                subprocess.run(['vcgencmd', 'display_power', '0'], check=True)
                print("HDMI display powered OFF")
            except Exception:
                pass

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Motion detection test program')
    parser.add_argument('--camera', '-c', type=int, default=0, help='Camera index (default: 0)')
    parser.add_argument('--threshold', '-t', type=int, default=500, help='Motion detection threshold (default: 500)')
    parser.add_argument('--min-area', '-a', type=int, default=1000, help='Minimum motion area (default: 1000)')
    parser.add_argument('--show-video', '-v', action='store_true', help='Show video feed window')
    parser.add_argument('--debug', '-d', action='store_true', help='Show debug windows')
    parser.add_argument('--timeout', type=int, default=30, help='HDMI timeout in seconds (default: 30)')
    
    args = parser.parse_args()
    
    detector = MotionDetector(
        camera_index=args.camera,
        threshold=args.threshold,
        min_area=args.min_area
    )
    detector.hdmi_timeout = args.timeout
    
    print(f"Motion Detection Test Program")
    print(f"Camera: {args.camera}")
    print(f"Threshold: {args.threshold}")
    print(f"Min Area: {args.min_area}")
    print(f"HDMI Timeout: {args.timeout}s")
    print(f"Show Video: {args.show_video}")
    print("-" * 40)
    
    detector.run(show_video=args.show_video, debug=args.debug)

if __name__ == "__main__":
    main()