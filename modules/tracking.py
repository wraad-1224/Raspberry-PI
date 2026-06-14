"""
=============================================================================
  Solar Tracking Module — Hour Angle Based Tracking
  ---------------------------------------------------------------------------
  Implements single-axis solar tracking using:
    Solar Hour Angle:  H = 15 × (T_solar − 12)
    Servo Angle:       θ_servo = H + 90

  Supports automatic mode (timed updates) and manual mode (user control).
  Uses MG996R servo motor via RPi.GPIO PWM.
=============================================================================
"""

import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import RPi.GPIO for servo control
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available — servo in simulation mode")


class SolarTracker:
    """
    Solar tracking engine with automatic and manual modes.

    Automatic Mode:
        Calculates solar time, hour angle, and servo angle.
        Updates the servo position at configurable intervals.

    Manual Mode:
        Allows direct servo angle control via API.

    Attributes:
        mode (str): "auto" or "manual"
        servo_angle (float): Current servo position (0°–180°)
        hour_angle (float): Current solar hour angle (°)
        solar_time (float): Current solar time (decimal hours)
        tracking_active (bool): Whether auto-tracking is currently running
    """

    # MG996R limits
    SERVO_MIN = 0
    SERVO_MAX = 180

    # PWM configuration for MG996R
    SERVO_GPIO = 18       # Hardware PWM pin on Pi 3B
    PWM_FREQ = 50         # 50 Hz (20ms period) — standard for servos
    # Duty cycle mapping: 0° → 2.5%, 180° → 12.5%
    DUTY_MIN = 2.5
    DUTY_MAX = 12.5

    def __init__(self):
        # Tracking state
        self.mode = "auto"
        self.servo_angle = 90.0
        self.hour_angle = 0.0
        self.solar_time = 12.0
        self.tracking_active = False

        # Configuration
        self.start_time = "06:00"
        self.end_time = "18:00"
        self.interval_minutes = 1

        # Internal
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._pwm = None
        self._gpio_initialized = False
        self._simulation = not GPIO_AVAILABLE

        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            self._init_gpio()

    def _init_gpio(self):
        """Initialize GPIO for servo PWM control."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.SERVO_GPIO, GPIO.OUT)
            self._pwm = GPIO.PWM(self.SERVO_GPIO, self.PWM_FREQ)
            self._pwm.start(0)
            self._gpio_initialized = True
            logger.info(f"Servo GPIO initialized on pin {self.SERVO_GPIO}")
        except Exception as e:
            self._simulation = True
            logger.error(f"GPIO init failed: {e} — falling back to simulation")

    def _angle_to_duty(self, angle):
        """Convert servo angle (0°–180°) to PWM duty cycle."""
        angle = max(self.SERVO_MIN, min(self.SERVO_MAX, angle))
        return self.DUTY_MIN + (angle / 180.0) * (self.DUTY_MAX - self.DUTY_MIN)

    def _set_servo(self, angle):
        """Move servo to the specified angle."""
        angle = max(self.SERVO_MIN, min(self.SERVO_MAX, angle))

        if self._gpio_initialized and self._pwm:
            duty = self._angle_to_duty(angle)
            self._pwm.ChangeDutyCycle(duty)
            time.sleep(0.3)  # Allow servo to reach position
            self._pwm.ChangeDutyCycle(0)  # Stop signal to prevent jitter

        with self._lock:
            self.servo_angle = round(angle, 1)

        logger.debug(f"Servo → {angle:.1f}°")

    # ────────────────────────────────────────────────────────
    #  Solar Calculations
    # ────────────────────────────────────────────────────────

    def calculate_solar_position(self):
        """
        Calculate current solar time, hour angle, and servo angle.

        Uses the system clock as solar time (assumes Pi is set to local timezone).

        Returns:
            dict: {solar_time, hour_angle, servo_angle}
        """
        now = datetime.now()
        solar_time = now.hour + now.minute / 60.0 + now.second / 3600.0

        # Solar Hour Angle: H = 15 × (T_solar − 12)
        hour_angle = 15.0 * (solar_time - 12.0)

        # Servo Angle: θ_servo = H + 90
        servo_angle = hour_angle + 90.0

        # Clamp to servo range
        servo_angle = max(self.SERVO_MIN, min(self.SERVO_MAX, servo_angle))

        with self._lock:
            self.solar_time = round(solar_time, 2)
            self.hour_angle = round(hour_angle, 2)

        return {
            "solar_time": round(solar_time, 2),
            "hour_angle": round(hour_angle, 2),
            "servo_angle": round(servo_angle, 1),
        }

    def _is_within_tracking_window(self):
        """Check if current time is within the configured tracking window."""
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute

        start_parts = self.start_time.split(":")
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])

        end_parts = self.end_time.split(":")
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])

        return start_minutes <= current_minutes <= end_minutes

    # ────────────────────────────────────────────────────────
    #  Automatic Tracking
    # ────────────────────────────────────────────────────────

    def start_auto_tracking(self):
        """Start automatic solar tracking in a background thread."""
        if self._running:
            return

        self.mode = "auto"
        self._running = True
        self.tracking_active = True
        self._thread = threading.Thread(target=self._auto_tracking_loop, daemon=True)
        self._thread.start()
        logger.info("Auto tracking started")

    def stop_tracking(self):
        """Stop automatic tracking."""
        self._running = False
        self.tracking_active = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Tracking stopped")

    def _auto_tracking_loop(self):
        """Background loop that updates servo position based on solar calculations."""
        while self._running:
            try:
                if self.mode != "auto":
                    time.sleep(1)
                    continue

                if self._is_within_tracking_window():
                    position = self.calculate_solar_position()
                    self._set_servo(position["servo_angle"])
                    self.tracking_active = True
                    logger.debug(
                        f"Auto track: T={position['solar_time']:.2f}h, "
                        f"H={position['hour_angle']:.1f}°, "
                        f"Servo={position['servo_angle']:.1f}°"
                    )
                else:
                    self.tracking_active = False

                # Wait for the configured interval
                time.sleep(self.interval_minutes * 60)

            except Exception as e:
                logger.error(f"Auto tracking error: {e}")
                time.sleep(5)

    # ────────────────────────────────────────────────────────
    #  Manual Control
    # ────────────────────────────────────────────────────────

    def set_manual_mode(self):
        """Switch to manual mode (stops auto tracking updates)."""
        self.mode = "manual"
        self.tracking_active = False
        logger.info("Switched to manual mode")

    def set_auto_mode(self):
        """Switch to auto mode and start tracking."""
        self.mode = "auto"
        if not self._running:
            self.start_auto_tracking()
        logger.info("Switched to auto mode")

    def set_servo_angle(self, angle):
        """
        Manually set the servo to a specific angle.

        Args:
            angle (float): Target angle (0°–180°)

        Returns:
            dict: {servo_angle, mode}
        """
        angle = max(self.SERVO_MIN, min(self.SERVO_MAX, float(angle)))
        self._set_servo(angle)
        return {"servo_angle": self.servo_angle, "mode": self.mode}

    def move_left(self, step=5):
        """Move servo left (decrease angle)."""
        return self.set_servo_angle(self.servo_angle - step)

    def move_right(self, step=5):
        """Move servo right (increase angle)."""
        return self.set_servo_angle(self.servo_angle + step)

    def center(self):
        """Move servo to center position (90°)."""
        return self.set_servo_angle(90)

    def sunrise_position(self):
        """Move servo to sunrise position (0°)."""
        return self.set_servo_angle(0)

    def noon_position(self):
        """Move servo to noon position (90°)."""
        return self.set_servo_angle(90)

    def sunset_position(self):
        """Move servo to sunset position (180°)."""
        return self.set_servo_angle(180)

    # ────────────────────────────────────────────────────────
    #  Configuration
    # ────────────────────────────────────────────────────────

    def update_settings(self, start_time=None, end_time=None, interval=None):
        """
        Update tracking configuration.

        Args:
            start_time (str): Start time "HH:MM"
            end_time (str): End time "HH:MM"
            interval (int): Tracking interval in minutes
        """
        if start_time:
            self.start_time = start_time
        if end_time:
            self.end_time = end_time
        if interval is not None:
            self.interval_minutes = max(1, int(interval))

        logger.info(
            f"Tracking settings updated: {self.start_time}–{self.end_time}, "
            f"interval={self.interval_minutes}min"
        )

        return self.get_settings()

    def get_settings(self):
        """Return current tracking settings."""
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "interval_minutes": self.interval_minutes,
        }

    # ────────────────────────────────────────────────────────
    #  Status
    # ────────────────────────────────────────────────────────

    def get_status(self):
        """Return complete tracking status."""
        # Always recalculate solar position for display
        position = self.calculate_solar_position()
        within = self._is_within_tracking_window()

        # Determine status text
        if self.mode == "manual":
            status_text = "Manual Mode"
        elif self.tracking_active and within:
            status_text = "Tracking Active"
        elif self.mode == "auto" and not within:
            status_text = "Outside Tracking Hours"
        else:
            status_text = "Tracking Disabled"

        with self._lock:
            return {
                "mode": self.mode,
                "solar_time": self.solar_time,
                "solar_time_formatted": self._format_solar_time(self.solar_time),
                "hour_angle": self.hour_angle,
                "servo_angle": self.servo_angle,
                "tracking_active": self.tracking_active,
                "tracking_status_text": status_text,
                "within_window": within,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "interval_minutes": self.interval_minutes,
                "simulation": self._simulation,
            }

    def _format_solar_time(self, decimal_hours):
        """Convert decimal hours to HH:MM:SS string."""
        h = int(decimal_hours)
        m = int((decimal_hours - h) * 60)
        s = int(((decimal_hours - h) * 60 - m) * 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def cleanup(self):
        """Clean up GPIO resources."""
        self.stop_tracking()
        if self._pwm:
            self._pwm.stop()
        if self._gpio_initialized:
            GPIO.cleanup()
        logger.info("Tracking cleanup complete")
