#!/usr/bin/env python3
import cv2
import time

def test_camera(camera_index):
    print(f"Testing camera {camera_index}...")
    cap = cv2.VideoCapture(camera_index)
    
    if not cap.isOpened():
        print(f"Could not open camera {camera_index}")
        return False
    
    # Try different formats
    formats_to_try = [
        # (width, height, fourcc)
        (640, 480, cv2.CAP_PROP_FOURCC),
        (1280, 720, None),
        (1920, 1080, None),
    ]
    
    for i in range(5):  # Try to read 5 frames
        ret, frame = cap.read()
        if ret:
            print(f"Frame {i+1}: {frame.shape} - SUCCESS")
            time.sleep(0.5)
        else:
            print(f"Frame {i+1}: FAILED")
            break
    
    cap.release()
    return ret

if __name__ == "__main__":
    for i in range(3):  # Test cameras 0, 1, 2
        if test_camera(i):
            print(f"Camera {i} is working!")
            break
        else:
            print(f"Camera {i} failed")
        print("-" * 30)