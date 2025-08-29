#!/usr/bin/env python3
"""
PIR Motion Sensor Test Program
HC-SR501 PIR Motion Sensor Module Test

Connections:
- VCC -> 5V (Pin 2 or Pin 4)
- GND -> Ground (Pin 6, 9, 14, 20, 25, 30, 34, or 39)
- OUT -> GPIO 23 (Pin 16)

Usage: python3 pir_test.py
Press Ctrl+C to stop
"""

import RPi.GPIO as GPIO
import time
import datetime
import syslog
import signal
import sys

class PIRSensorTest:
    def __init__(self, pir_pin=23):
        self.pir_pin = pir_pin
        self.motion_detected = False
        self.last_motion_time = 0
        
        # Initialize syslog
        syslog.openlog("PIRTest", syslog.LOG_PID, syslog.LOG_DAEMON)
        
        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pir_pin, GPIO.IN)
        
        print("="*60)
        print("HC-SR501 PIR Motion Sensor Test")
        print("="*60)
        print(f"PIR sensor connected to GPIO {self.pir_pin}")
        print("Waiting for sensor to stabilize (30 seconds)...")
        print("Move in front of sensor to test motion detection")
        print("Press Ctrl+C to stop")
        print("="*60)
        
        # Allow sensor to stabilize
        time.sleep(30)
        print("✓ Sensor ready - monitoring for motion...")
        
        # Log startup
        timestamp = datetime.datetime.now()
        log_msg = f"PIR sensor test started at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} on GPIO {self.pir_pin}"
        print(log_msg)
        syslog.syslog(syslog.LOG_INFO, log_msg)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)
    
    def cleanup(self, signum=None, frame=None):
        """Clean up GPIO and exit gracefully"""
        timestamp = datetime.datetime.now()
        log_msg = f"PIR sensor test stopped at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        print(f"\n{log_msg}")
        syslog.syslog(syslog.LOG_INFO, log_msg)
        
        GPIO.cleanup()
        syslog.closelog()
        sys.exit(0)
    
    def motion_callback(self, channel):
        """Callback function for motion detection"""
        current_time = time.time()
        timestamp = datetime.datetime.now()
        
        if GPIO.input(self.pir_pin):
            # Motion detected (rising edge)
            if not self.motion_detected:
                self.motion_detected = True
                self.last_motion_time = current_time
                
                log_msg = f"MOTION DETECTED at {timestamp.strftime('%H:%M:%S')}"
                print(f"🚨 {log_msg}")
                syslog.syslog(syslog.LOG_INFO, f"Motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            # Motion ended (falling edge)
            if self.motion_detected:
                duration = current_time - self.last_motion_time
                self.motion_detected = False
                
                log_msg = f"Motion ended at {timestamp.strftime('%H:%M:%S')} (duration: {duration:.1f}s)"
                print(f"✓ {log_msg}")
                syslog.syslog(syslog.LOG_INFO, f"Motion ended at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - duration: {duration:.1f}s")
    
    def run_polling_mode(self):
        """Run PIR sensor in polling mode (alternative to interrupt mode)"""
        last_state = False
        motion_start_time = 0
        
        try:
            while True:
                current_state = GPIO.input(self.pir_pin)
                current_time = time.time()
                timestamp = datetime.datetime.now()
                
                if current_state and not last_state:
                    # Motion started
                    motion_start_time = current_time
                    log_msg = f"MOTION DETECTED at {timestamp.strftime('%H:%M:%S')}"
                    print(f"🚨 {log_msg}")
                    syslog.syslog(syslog.LOG_INFO, f"Motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                
                elif not current_state and last_state:
                    # Motion ended
                    if motion_start_time > 0:
                        duration = current_time - motion_start_time
                        log_msg = f"Motion ended at {timestamp.strftime('%H:%M:%S')} (duration: {duration:.1f}s)"
                        print(f"✓ {log_msg}")
                        syslog.syslog(syslog.LOG_INFO, f"Motion ended at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - duration: {duration:.1f}s")
                
                last_state = current_state
                time.sleep(0.1)  # Check every 100ms
                
        except KeyboardInterrupt:
            self.cleanup()
    
    def run_interrupt_mode(self):
        """Run PIR sensor using GPIO interrupts"""
        try:
            # Setup interrupt on both rising and falling edges
            GPIO.add_event_detect(self.pir_pin, GPIO.BOTH, callback=self.motion_callback, bouncetime=300)
            
            # Keep the program running
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.cleanup()
    
    def run_status_mode(self):
        """Run with periodic status updates"""
        status_counter = 0
        last_state = False
        
        try:
            while True:
                current_state = GPIO.input(self.pir_pin)
                current_time = time.time()
                timestamp = datetime.datetime.now()
                
                # Motion detection logic
                if current_state and not last_state:
                    log_msg = f"MOTION DETECTED at {timestamp.strftime('%H:%M:%S')}"
                    print(f"🚨 {log_msg}")
                    syslog.syslog(syslog.LOG_INFO, f"Motion detected at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                elif not current_state and last_state:
                    log_msg = f"Motion ended at {timestamp.strftime('%H:%M:%S')}"
                    print(f"✓ {log_msg}")
                    syslog.syslog(syslog.LOG_INFO, f"Motion ended at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Periodic status update (every 60 seconds)
                if status_counter % 60 == 0:
                    status = "MOTION" if current_state else "IDLE"
                    print(f"[{timestamp.strftime('%H:%M:%S')}] Status: {status}")
                
                last_state = current_state
                status_counter += 1
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.cleanup()

if __name__ == "__main__":
    print("Starting PIR sensor test...")
    
    try:
        pir_test = PIRSensorTest(pir_pin=23)
        
        # Run in status mode (combines polling with periodic status updates)
        pir_test.run_status_mode()
        
    except Exception as e:
        print(f"Error: {e}")
        GPIO.cleanup()
        sys.exit(1)