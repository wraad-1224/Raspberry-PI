"""
=============================================================================
  Camera Module — Raspberry Pi Camera Integration
  ---------------------------------------------------------------------------
  Captures images using picamera2 (modern Pi camera stack).
  Falls back to OpenCV or generates a placeholder on non-Pi systems.
=============================================================================
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Determine camera backend availability
CAMERA_BACKEND = None

try:
    from picamera2 import Picamera2
    CAMERA_BACKEND = "picamera2"
    logger.info("Camera backend: picamera2")
except ImportError:
    try:
        import cv2
        CAMERA_BACKEND = "opencv"
        logger.info("Camera backend: OpenCV")
    except ImportError:
        CAMERA_BACKEND = "simulation"
        logger.warning("No camera library available — using simulation mode")


class Camera:
    """
    Camera interface for capturing solar panel images.

    Automatically selects the best available backend:
    1. picamera2 (Raspberry Pi)
    2. OpenCV (USB webcam fallback)
    3. Simulation (generates placeholder image)
    """

    def __init__(self, save_dir="static/images"):
        self.save_dir = save_dir
        self.latest_path = os.path.join(save_dir, "latest.jpg")
        self.backend = CAMERA_BACKEND
        self._available = True
        self.last_capture_time = None

        # Ensure save directory exists
        os.makedirs(save_dir, exist_ok=True)

    @property
    def is_available(self):
        """Check if camera is available."""
        return self._available

    def capture(self):
        """
        Capture an image and save to latest.jpg.

        Returns:
            dict: {success, path, timestamp, backend, message}
        """
        try:
            if self.backend == "picamera2":
                return self._capture_picamera2()
            elif self.backend == "opencv":
                return self._capture_opencv()
            else:
                return self._capture_simulation()

        except Exception as e:
            self._available = False
            logger.error(f"Camera capture failed: {e}")
            return {
                "success": False,
                "path": None,
                "timestamp": datetime.now().isoformat(),
                "backend": self.backend,
                "message": f"Capture failed: {str(e)}",
            }

    def _capture_picamera2(self):
        """Capture using Raspberry Pi Camera (picamera2)."""
        try:
            cam = Picamera2()
            config = cam.create_still_configuration(
                main={"size": (1280, 720), "format": "RGB888"}
            )
            cam.configure(config)
            cam.start()

            import time
            time.sleep(1)  # Allow auto-exposure to settle

            cam.capture_file(self.latest_path)
            cam.stop()
            cam.close()

            self.last_capture_time = datetime.now()
            self._available = True

            logger.info(f"Image captured via picamera2 → {self.latest_path}")
            return {
                "success": True,
                "path": self.latest_path,
                "timestamp": self.last_capture_time.isoformat(),
                "backend": "picamera2",
                "message": "Image captured successfully",
            }
        except Exception as e:
            self._available = False
            raise e

    def _capture_opencv(self):
        """Capture using OpenCV (USB webcam fallback)."""
        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self._available = False
            return {
                "success": False,
                "path": None,
                "timestamp": datetime.now().isoformat(),
                "backend": "opencv",
                "message": "Could not open camera",
            }

        # Read a few frames to let auto-exposure settle
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if ret:
            cv2.imwrite(self.latest_path, frame)
            self.last_capture_time = datetime.now()
            self._available = True

            logger.info(f"Image captured via OpenCV → {self.latest_path}")
            return {
                "success": True,
                "path": self.latest_path,
                "timestamp": self.last_capture_time.isoformat(),
                "backend": "opencv",
                "message": "Image captured successfully",
            }
        else:
            self._available = False
            return {
                "success": False,
                "path": None,
                "timestamp": datetime.now().isoformat(),
                "backend": "opencv",
                "message": "Failed to read frame from camera",
            }

    def _capture_simulation(self):
        """Generate a placeholder image for development/testing."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            # Create a realistic-looking placeholder
            img = Image.new("RGB", (1280, 720), color=(30, 40, 55))
            draw = ImageDraw.Draw(img)

            # Draw a solar panel shape
            panel_color = (50, 80, 130)
            draw.rectangle([340, 160, 940, 560], fill=panel_color, outline=(70, 110, 170), width=3)

            # Grid lines on panel
            for x in range(340, 941, 75):
                draw.line([(x, 160), (x, 560)], fill=(60, 95, 150), width=1)
            for y in range(160, 561, 50):
                draw.line([(340, y), (940, y)], fill=(60, 95, 150), width=1)

            # Text overlay
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
                font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            except (IOError, OSError):
                font = ImageFont.load_default()
                font_sm = font

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            draw.text((440, 330), "SIMULATION MODE", fill=(200, 200, 200), font=font)
            draw.text((480, 380), f"Captured: {timestamp}", fill=(150, 150, 150), font=font_sm)
            draw.text((480, 410), "Camera: Not Connected", fill=(150, 150, 150), font=font_sm)

            img.save(self.latest_path, "JPEG", quality=90)
            self.last_capture_time = datetime.now()
            self._available = True

            logger.info(f"Simulation image generated → {self.latest_path}")
            return {
                "success": True,
                "path": self.latest_path,
                "timestamp": self.last_capture_time.isoformat(),
                "backend": "simulation",
                "message": "Simulation image generated (no camera detected)",
            }

        except ImportError:
            # If even PIL is not available, create a minimal JPEG
            self._available = False
            return {
                "success": False,
                "path": None,
                "timestamp": datetime.now().isoformat(),
                "backend": "simulation",
                "message": "Cannot generate image — Pillow not installed",
            }
