# Application.py Modifications - Sep 5, 2025

## Original Issue
- Raspberry Pi monitoring application with OLED display and RGB LEDs
- Originally based on @ricardodemauro's optimized code with native methods

## Major Changes Made

### LED System Indicators (NEW)
- **LED 0 - Temperature Indicator**: Color-coded heat map
  - 🟢 Green: < 40°C (Cool and Safe)
  - 🟡 Yellow: 40-50°C (Getting Warm) 
  - 🟠 Orange: 50-60°C (Hot - Fan Running)
  - 🔴 Red: > 60°C (Very Hot)

- **LED 1 - CPU Load Indicator**: System performance
  - 🔵 Blue: < 25% (Low Load)
  - 🟢 Green: 25-50% (Light Load)
  - 🟡 Yellow: 50-75% (Moderate Load)
  - 🔴 Red: > 75% (Heavy Load)

- **LED 2 - Disk Activity Indicator**: I/O monitoring
  - 🔵 Dim Blue: Idle (No Recent Activity)
  - ⚪ White: Active I/O or Recent Activity
  - 🔴 Red: Disk > 90% Full

- **LED 3 - System Health (Traffic Light)**: Overall status
  - 🟢 Green: All Systems Normal
  - 🟡 Yellow: Warning (Any Metric Elevated)
  - 🔴 Red: Critical (Temp>70°C, CPU>90%, Mem>90%, Disk>95%)

### PIR Motion Detection (NEW - PRIMARY)
- **PIR Sensor Integration**: HC-SR501 PIR motion sensor on GPIO 23 (Pin 16)
- **Primary Motion Detection**: PIR sensor used as main motion detection method
- **Auto-Fallback**: Automatically falls back to camera motion detection if PIR unavailable
- **Fast Initialization**: 5-second PIR stabilization period
- **High-Speed Polling**: 200ms detection intervals for responsive motion sensing
- **Power Efficient**: PIR sensor consumes minimal power compared to camera
- **GPIO Cleanup**: Proper GPIO resource cleanup on exit

### Camera Motion Detection (FALLBACK)
- **Fallback Method**: Used when PIR sensor is not available or fails to initialize
- **rpicam-still Integration**: Uses Raspberry Pi camera for motion detection
- **File Size Comparison**: Basic motion detection via frame size differences
- **Frame Management**: 640x480 capture with automatic cleanup
- **Configurable Sensitivity**: Adjustable motion sensitivity threshold

### DSI Display Control (ENHANCED)
- **Motion-Triggered Wake**: Both PIR and camera motion detection trigger display
- **Multiple Wake Methods**: Robust display control with fallback options:
  - xset DPMS commands
  - xrandr output control
  - vcgencmd display power
  - tvservice commands
- **Source Identification**: Logs clearly identify PIR vs Camera motion detection
- **Configurable Timeout**: 60-second inactivity timeout
- **OLED Always On**: OLED display remains unaffected by motion detection

### Fan Control Fixes
- **CRITICAL FIX**: Temperature threshold comparison
  - Fixed bug where fan PWM value was compared to temperature thresholds
  - Now correctly compares CPU temperature to 40°C/50°C thresholds
- Improved fan control logic with hysteresis

### Performance Optimizations
- Cached fan PWM path lookup to reduce filesystem calls
- Pre-allocated format strings for OLED display
- Direct file reads instead of subprocess calls where possible
- Single-threaded main loop with optimized update intervals

### Enhanced Monitoring
- Real-time status output with all key metrics
- Disk activity monitoring for LED indicators
- Uptime display with "days since reboot" screen
- Comprehensive error handling and logging

### Logging Optimizations (Sep 5, 2025)
- **Motion Detection Rate Limiting**: PIR and camera motion logging limited to once every 30 seconds
- **Reduced Console Verbosity**: Eliminated repetitive motion detection console messages
- **Simplified Syslog Messages**: Streamlined log entries without redundant timestamps
- **Smart Motion End Logging**: Only logs PIR motion end events for durations > 5 seconds
- **Display Event Optimization**: Simplified display wake/sleep logging without verbose details

### Syslog Integration
- **PIR Motion Events**: PIR sensor motion detection with 30-second rate limiting
- **Camera Motion Events**: Camera motion detection with 30-second rate limiting (fallback mode)
- **Motion Source Tracking**: Clear identification of PIR vs Camera in logs
- **LED System Events**: LED indicator initialization and status
- **Startup/Shutdown Events**: Application lifecycle tracking
- **Reduced Verbosity**: Motion logging limited to significant events and periodic updates

## Key Benefits
- **Dual Motion Detection**: PIR sensor primary + camera fallback for maximum reliability
- **Power Efficiency**: PIR sensor uses minimal power vs constant camera monitoring
- **Fast Response**: 200ms PIR polling for immediate motion detection
- **Visual System Status**: 4 LED indicators provide at-a-glance system health
- **Automatic Fallback**: Seamless switch to camera if PIR unavailable
- **Enhanced Logging**: Clear motion source identification in system logs
- **Robust Display Control**: Multiple wake methods ensure reliable display activation

## Configuration
- **PIR Sensor**: GPIO 23 (Pin 16), 200ms polling interval
- **PIR Stabilization**: 5-second initialization period
- **Camera Motion Sensitivity**: 30 (adjustable for fallback mode)
- **Display Timeout**: 60 seconds
- **Temperature Thresholds**: 40°C (fan off) / 50°C (fan on)
- **OLED Screens**: 4 different info displays every 3 seconds

## Hardware Requirements
- **PIR Sensor (Primary)**: HC-SR501 PIR Motion Sensor
  - VCC → 5V (Pin 2 or 4)
  - GND → Ground (Pin 6, 9, 14, 20, 25, 30, 34, or 39)
  - OUT → GPIO 23 (Pin 16)
- **Camera (Fallback)**: Raspberry Pi Camera Module (any version)
- **Freenove Board**: For OLED display and LED indicators

## Service Management
- **Service Name**: `my_app_running.service`
- **Service File Location**: `/etc/systemd/system/my_app_running.service`
- **Common Commands**:
  ```bash
  # Restart the service
  sudo systemctl restart my_app_running.service
  
  # Check service status
  sudo systemctl status my_app_running.service
  
  # View recent logs
  sudo journalctl -u my_app_running.service -n 20 --no-pager
  
  # Reset failed state
  sudo systemctl reset-failed my_app_running.service
  ```
- **Working Directory**: `/home/kdesch/scripts/PIOLED`
- **Runs as User**: `kdesch`