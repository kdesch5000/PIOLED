#!/usr/bin/env python3
"""
LED System Monitor Test Program
Tests individual LED control for system monitoring before integrating into main application
"""

import time
import sys
import psutil
import getopt
from expansion import Expansion

class LEDSystemMonitor:
    def __init__(self):
        self.expansion = None
        self.last_disk_bytes = 0
        self.last_disk_activity = time.time()
        
        try:
            self.expansion = Expansion()
            self.expansion.set_led_mode(1)  # Set to mode 1 for individual control
            print("✓ LED system initialized in mode 1 (individual control)")
            
            # Initialize all LEDs to off
            for i in range(4):
                self.expansion.set_led_color(i, 0, 0, 0)
            print("✓ All LEDs initialized to OFF")
            
            # Initialize disk monitoring
            self._init_disk_monitoring()
            
        except Exception as e:
            print(f"✗ Failed to initialize LED system: {e}")
            sys.exit(1)
    
    def _init_disk_monitoring(self):
        """Initialize disk activity monitoring"""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.last_disk_bytes = disk_io.read_bytes + disk_io.write_bytes
            print("✓ Disk monitoring initialized")
        except Exception:
            self.last_disk_bytes = 0
            print("⚠ Disk monitoring failed to initialize")

    def get_cpu_temperature(self):
        """Get CPU temperature"""
        try:
            with open('/sys/devices/virtual/thermal/thermal_zone0/temp', 'r') as f:
                temp_raw = int(f.read().strip())
                return temp_raw / 1000.0
        except Exception:
            return 45.0  # Default safe temperature for testing

    def check_disk_activity(self):
        """Check for disk activity"""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                current_bytes = disk_io.read_bytes + disk_io.write_bytes
                if current_bytes != self.last_disk_bytes:
                    self.last_disk_activity = time.time()
                    self.last_disk_bytes = current_bytes
                    return True
            return False
        except Exception:
            return False

    # Individual LED Test Functions
    
    def test_temperature_led(self, temp):
        """LED 0: Temperature Heat Map"""
        try:
            if temp < 40:
                self.expansion.set_led_color(0, 0, 255, 0)      # Green - Cool
                status = f"Green (Cool: {temp:.1f}°C)"
            elif temp < 50:
                self.expansion.set_led_color(0, 255, 255, 0)    # Yellow - Warm
                status = f"Yellow (Warm: {temp:.1f}°C)"
            elif temp < 60:
                self.expansion.set_led_color(0, 255, 165, 0)    # Orange - Hot
                status = f"Orange (Hot: {temp:.1f}°C)"
            else:
                self.expansion.set_led_color(0, 255, 0, 0)      # Red - Very hot
                status = f"Red (Very Hot: {temp:.1f}°C)"
            return status
        except Exception as e:
            return f"Error: {e}"

    def test_cpu_load_led(self, cpu_percent):
        """LED 1: CPU/System Load Indicator"""
        try:
            if cpu_percent < 25:
                self.expansion.set_led_color(1, 0, 0, 255)      # Blue - Low load
                status = f"Blue (Low: {cpu_percent:.1f}%)"
            elif cpu_percent < 50:
                self.expansion.set_led_color(1, 0, 255, 0)      # Green - Light load
                status = f"Green (Light: {cpu_percent:.1f}%)"
            elif cpu_percent < 75:
                self.expansion.set_led_color(1, 255, 255, 0)    # Yellow - Moderate load
                status = f"Yellow (Moderate: {cpu_percent:.1f}%)"
            else:
                self.expansion.set_led_color(1, 255, 0, 0)      # Red - Heavy load
                status = f"Red (Heavy: {cpu_percent:.1f}%)"
            return status
        except Exception as e:
            return f"Error: {e}"

    def test_disk_activity_led(self, disk_usage_percent, has_activity):
        """LED 2: Disk Activity Indicator"""
        try:
            if disk_usage_percent > 90:
                self.expansion.set_led_color(2, 255, 0, 0)      # Red - Disk full
                status = f"Red (Disk Full: {disk_usage_percent:.1f}%)"
            elif has_activity:
                self.expansion.set_led_color(2, 255, 255, 255)  # White - Activity
                status = f"White (Active I/O)"
            elif (time.time() - self.last_disk_activity) < 2:
                self.expansion.set_led_color(2, 255, 255, 255)  # White - Recent activity
                status = f"White (Recent Activity)"
            else:
                self.expansion.set_led_color(2, 0, 0, 100)      # Dim blue - Idle
                status = f"Dim Blue (Idle)"
            return status
        except Exception as e:
            return f"Error: {e}"

    def test_system_health_led(self, temp, cpu_percent, mem_percent, disk_percent):
        """LED 3: Traffic Light System Health"""
        try:
            # Critical conditions
            critical_conditions = (
                temp > 70 or 
                cpu_percent > 90 or 
                mem_percent > 90 or 
                disk_percent > 95
            )
            
            # Warning conditions
            warning_conditions = (
                temp > 55 or 
                cpu_percent > 75 or 
                mem_percent > 80 or 
                disk_percent > 85
            )
            
            if critical_conditions:
                self.expansion.set_led_color(3, 255, 0, 0)      # Red - Critical
                status = "Red (Critical)"
                if temp > 70: status += f" TEMP:{temp:.1f}°C"
                if cpu_percent > 90: status += f" CPU:{cpu_percent:.1f}%"
                if mem_percent > 90: status += f" MEM:{mem_percent:.1f}%"
                if disk_percent > 95: status += f" DISK:{disk_percent:.1f}%"
            elif warning_conditions:
                self.expansion.set_led_color(3, 255, 255, 0)    # Yellow - Warning
                status = "Yellow (Warning)"
            else:
                self.expansion.set_led_color(3, 0, 255, 0)      # Green - All good
                status = "Green (All Good)"
            return status
        except Exception as e:
            return f"Error: {e}"

    def test_individual_leds(self):
        """Test each LED individually with different colors"""
        print("\n=== Testing Individual LED Control ===")
        colors = [
            ("Red", 255, 0, 0),
            ("Green", 0, 255, 0),
            ("Blue", 0, 0, 255),
            ("Yellow", 255, 255, 0),
            ("Purple", 255, 0, 255),
            ("Cyan", 0, 255, 255),
            ("White", 255, 255, 255)
        ]
        
        for i in range(4):
            print(f"\nTesting LED {i}...")
            for color_name, r, g, b in colors:
                try:
                    self.expansion.set_led_color(i, r, g, b)
                    print(f"  LED {i}: {color_name}")
                    time.sleep(0.8)
                except Exception as e:
                    print(f"  LED {i}: Error setting {color_name} - {e}")
            
            # Turn off LED
            self.expansion.set_led_color(i, 0, 0, 0)
            print(f"  LED {i}: OFF")
            time.sleep(0.5)

    def test_system_monitoring(self, duration=30):
        """Test system monitoring LEDs for specified duration"""
        print(f"\n=== Testing System Monitoring LEDs for {duration} seconds ===")
        print("LED 0: Temperature | LED 1: CPU Load | LED 2: Disk Activity | LED 3: System Health")
        print("Press Ctrl+C to stop early\n")
        
        start_time = time.time()
        
        try:
            while (time.time() - start_time) < duration:
                # Get system metrics
                temp = self.get_cpu_temperature()
                cpu_percent = psutil.cpu_percent(interval=0.1)
                mem = psutil.virtual_memory()
                mem_percent = mem.percent
                disk = psutil.disk_usage('/')
                disk_percent = disk.percent
                disk_activity = self.check_disk_activity()
                
                # Update LEDs
                temp_status = self.test_temperature_led(temp)
                cpu_status = self.test_cpu_load_led(cpu_percent)
                disk_status = self.test_disk_activity_led(disk_percent, disk_activity)
                health_status = self.test_system_health_led(temp, cpu_percent, mem_percent, disk_percent)
                
                # Print status
                elapsed = int(time.time() - start_time)
                remaining = duration - elapsed
                print(f"[{elapsed:2d}s] LED0: {temp_status}")
                print(f"     LED1: {cpu_status}")
                print(f"     LED2: {disk_status}")
                print(f"     LED3: {health_status}")
                print(f"     {remaining}s remaining...\n")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\nTest stopped by user")
        
        print("System monitoring test completed!")

    def test_stress_simulation(self):
        """Simulate different system stress conditions"""
        print("\n=== Testing Stress Condition Simulations ===")
        
        # Simulate different temperature conditions
        print("Simulating temperature conditions...")
        temps = [35, 45, 55, 65, 75]  # Different temperature ranges
        for temp in temps:
            status = self.test_temperature_led(temp)
            print(f"Temperature {temp}°C: {status}")
            time.sleep(2)
        
        print("\nSimulating CPU load conditions...")
        cpu_loads = [15, 35, 60, 85]  # Different CPU loads
        for cpu_load in cpu_loads:
            status = self.test_cpu_load_led(cpu_load)
            print(f"CPU Load {cpu_load}%: {status}")
            time.sleep(2)
        
        print("\nSimulating system health conditions...")
        # Normal, Warning, Critical
        conditions = [
            (45, 20, 50, 70, "Normal"),
            (60, 80, 85, 90, "Warning"), 
            (75, 95, 95, 98, "Critical")
        ]
        
        for temp, cpu, mem, disk, desc in conditions:
            status = self.test_system_health_led(temp, cpu, mem, disk)
            print(f"{desc} condition (T:{temp} C:{cpu} M:{mem} D:{disk}): {status}")
            time.sleep(3)

    def cleanup(self):
        """Clean up and turn off all LEDs"""
        try:
            if self.expansion:
                print("Cleaning up...")
                for i in range(4):
                    self.expansion.set_led_color(i, 0, 0, 0)
                self.expansion.end()
                print("✓ All LEDs turned off and cleaned up")
        except Exception as e:
            print(f"⚠ Cleanup error: {e}")

def print_help():
    print("LED System Monitor Test Program")
    print("Usage: python3 led_test.py [option]")
    print()
    print("Options:")
    print("  --individual     Test each LED individually with different colors")
    print("  --monitor        Test system monitoring LEDs (default 30s)")
    print("  --monitor=60     Test system monitoring LEDs for 60 seconds")  
    print("  --stress         Test stress condition simulations")
    print("  --all            Run all tests")
    print("  -h, --help       Show this help message")

def main(argv):
    if len(argv) == 0:
        print_help()
        return
        
    led_monitor = None
    
    try:
        opts, args = getopt.getopt(argv, "h", ["help", "individual", "monitor", "monitor=", "stress", "all"])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    try:
        led_monitor = LEDSystemMonitor()
        
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                print_help()
                return
            elif opt == "--individual":
                led_monitor.test_individual_leds()
            elif opt == "--monitor":
                if arg:
                    duration = int(arg)
                else:
                    duration = 30
                led_monitor.test_system_monitoring(duration)
            elif opt == "--stress":
                led_monitor.test_stress_simulation()
            elif opt == "--all":
                print("Running all LED tests...")
                led_monitor.test_individual_leds()
                time.sleep(2)
                led_monitor.test_stress_simulation()
                time.sleep(2)
                led_monitor.test_system_monitoring(20)
                
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test error: {e}")
    finally:
        if led_monitor:
            led_monitor.cleanup()

if __name__ == '__main__':
    main(sys.argv[1:])

