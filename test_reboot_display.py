#!/usr/bin/env python3
"""
Standalone test program for displaying days since reboot on OLED
"""

import sys
import time
import subprocess
from oled import OLED

def get_days_since_reboot():
    """Get the number of days since last system reboot using uptime"""
    try:
        result = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
        uptime_str = result.stdout.strip()
        print(f"Uptime output: {uptime_str}")
        
        # Parse "up 4 days, 5 hours, 7 minutes" format
        if 'day' in uptime_str:
            parts = uptime_str.split()
            for i, part in enumerate(parts):
                if part.isdigit() and i + 1 < len(parts) and 'day' in parts[i + 1]:
                    return int(part)
        return 0  # Less than 1 day
    except Exception as e:
        print(f"Error getting uptime: {e}")
        return 0

def main():
    print("Testing days since reboot OLED display...")
    
    try:
        # Initialize OLED
        oled = OLED()
        print("OLED initialized successfully")
        
        # Get days since reboot
        days = get_days_since_reboot()
        print(f"Days since reboot: {days}")
        
        # Clear display
        oled.clear()
        
        # Display the reboot information
        oled.draw_text("Days Since:", position=(0, 0), font_size=14)
        
        # Draw large day number - use larger font and center it
        day_str = str(days)
        oled.draw_text(day_str, position=(40, 25), font_size=40)
        
        # Add "days" label below
        label = "days" if days != 1 else "day"
        oled.draw_text(label, position=(45, 50), font_size=10)
        
        # Show on display
        oled.show()
        
        print("Display updated! Press Ctrl+C to exit...")
        
        # Keep display active
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            if 'oled' in locals():
                oled.clear()
                oled.show()
                oled.close()
                print("OLED display cleared and closed")
        except Exception as e:
            print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    main()
