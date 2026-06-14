"""
=============================================================================
  Serial Reader Module — ESP32 UART Communication
  ---------------------------------------------------------------------------
  Reads voltage and current from ESP32 via UART serial.
  Expected format:  "voltage,current"   e.g. "18.4,1.25"
  Calculates power, accumulates daily energy (Wh).
=============================================================================
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

# Try to import pyserial
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logger.warning("pyserial not installed — running in simulation mode")


class SerialReader:
    """
    Thread-safe serial reader for ESP32 UART data.

    Attributes:
        port (str): Serial port path (e.g., /dev/ttyUSB0)
        baud_rate (int): Baud rate for UART
        voltage (float): Latest voltage reading (V)
        current (float): Latest current reading (A)
        power (float): Latest power (W) = voltage × current
        daily_energy (float): Accumulated energy today (Wh)
        history (deque): Rolling buffer of readings for charts
    """

    def __init__(self, port="/dev/ttyUSB0", baud_rate=9600, max_history=200):
        self.port = port
        self.baud_rate = baud_rate
        self.max_history = max_history

        # Latest readings
        self.voltage = 0.0
        self.current = 0.0
        self.power = 0.0
        self.daily_energy = 0.0
        self.last_update = None

        # History for charts
        self.history = deque(maxlen=max_history)

        # Internal state
        self._lock = threading.Lock()
        self._serial = None
        self._running = False
        self._thread = None
        self._connected = False
        self._last_energy_time = None
        self._energy_reset_date = datetime.now().date()
        self._connect_attempts = 0
        self._max_connect_attempts = 3

        # Simulation mode
        self._simulation_mode = not SERIAL_AVAILABLE
        self._sim_time = 0

        # UART debug info
        self._last_raw_packet = None
        self._last_packet_time = None
        self._packet_count = 0

    @property
    def is_connected(self):
        """Check if serial connection is active."""
        return self._connected

    def start(self):
        """Start the serial reading thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info(f"Serial reader started ({'simulation' if self._simulation_mode else self.port})")

    def stop(self):
        """Stop the serial reading thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info("Serial reader stopped")

    def _connect(self):
        """Attempt to connect to the serial port."""
        if self._simulation_mode:
            self._connected = True
            return True

        try:
            if self._serial and self._serial.is_open:
                self._serial.close()

            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=2,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            self._connected = True
            logger.info(f"Connected to {self.port} at {self.baud_rate} baud")
            return True

        except (serial.SerialException, OSError) as e:
            self._connected = False
            self._connect_attempts += 1
            logger.warning(f"Serial connection failed ({self._connect_attempts}/{self._max_connect_attempts}): {e}")

            # Fall back to simulation after max attempts
            if self._connect_attempts >= self._max_connect_attempts:
                self._simulation_mode = True
                self._connected = True
                logger.info("Max connection attempts reached — switching to simulation mode")
                return True

            return False

    def _read_loop(self):
        """Main reading loop — runs in background thread."""
        while self._running:
            try:
                if not self._connected:
                    if not self._connect():
                        time.sleep(3)  # Wait before retry
                        continue

                if self._simulation_mode:
                    self._simulate_reading()
                    time.sleep(1)
                else:
                    self._read_serial()

            except Exception as e:
                logger.error(f"Serial read error: {e}")
                self._connected = False
                time.sleep(2)

    def _read_serial(self):
        """Read and parse a line from the serial port."""
        try:
            raw = self._serial.readline().decode("utf-8").strip()
            if not raw:
                return

            # Store debug info
            self._last_raw_packet = raw
            self._last_packet_time = datetime.now().isoformat()
            self._packet_count += 1

            parts = raw.split(",")
            if len(parts) >= 2:
                voltage = float(parts[0])
                current = float(parts[1])
                self._update_values(voltage, current)
            else:
                logger.warning(f"Unexpected serial format: {raw}")

        except (ValueError, UnicodeDecodeError) as e:
            logger.warning(f"Parse error: {e}")
        except serial.SerialException:
            self._connected = False
            logger.warning("Serial connection lost")

    def _simulate_reading(self):
        """Generate simulated solar panel readings for development."""
        import math
        self._sim_time += 1

        # Simulate a realistic solar day cycle
        hour = datetime.now().hour + datetime.now().minute / 60.0
        # Solar-like curve peaking at noon
        solar_factor = max(0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0

        # Add small random variation
        import random
        noise = random.uniform(-0.3, 0.3)

        voltage = 18.0 * solar_factor + noise + 0.5  # ~0.5V to ~18.5V
        current = 1.2 * solar_factor + noise * 0.05 + 0.05  # ~0.05A to ~1.25A

        voltage = max(0.0, round(voltage, 2))
        current = max(0.0, round(current, 2))

        # Store simulated packet for debug display
        self._last_raw_packet = f"{voltage},{current}"
        self._last_packet_time = datetime.now().isoformat()
        self._packet_count += 1

        self._update_values(voltage, current)

    def _update_values(self, voltage, current):
        """Update stored values thread-safely and accumulate energy."""
        now = datetime.now()

        # Reset daily energy at midnight
        if now.date() != self._energy_reset_date:
            self.daily_energy = 0.0
            self._energy_reset_date = now.date()
            self._last_energy_time = None

        power = voltage * current

        # Accumulate energy using trapezoidal integration (Wh)
        if self._last_energy_time is not None:
            dt_hours = (now - self._last_energy_time).total_seconds() / 3600.0
            avg_power = (self.power + power) / 2.0
            energy_increment = avg_power * dt_hours
            self.daily_energy += energy_increment

        with self._lock:
            self.voltage = round(voltage, 2)
            self.current = round(current, 3)
            self.power = round(power, 2)
            self.daily_energy = round(self.daily_energy, 4)
            self.last_update = now.isoformat()

            # Add to history
            self.history.append({
                "time": now.strftime("%H:%M:%S"),
                "timestamp": now.isoformat(),
                "voltage": self.voltage,
                "current": self.current,
                "power": self.power,
                "energy": self.daily_energy,
            })

        self._last_energy_time = now

    def get_latest(self):
        """Return latest readings as a dict."""
        with self._lock:
            return {
                "voltage": self.voltage,
                "current": self.current,
                "power": self.power,
                "daily_energy": self.daily_energy,
                "last_update": self.last_update,
                "connected": self._connected,
                "simulation": self._simulation_mode,
            }

    def get_history(self, limit=60):
        """Return recent history for chart rendering."""
        with self._lock:
            data = list(self.history)
            return data[-limit:] if len(data) > limit else data

    def get_debug_info(self):
        """Return UART debugging information."""
        return {
            "last_packet": self._last_raw_packet,
            "last_packet_time": self._last_packet_time,
            "packet_count": self._packet_count,
            "port": self.port,
            "baud_rate": self.baud_rate,
            "connected": self._connected,
            "simulation": self._simulation_mode,
            "status": "Simulation" if self._simulation_mode else ("Connected" if self._connected else "Disconnected"),
        }
