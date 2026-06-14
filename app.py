"""
=============================================================================
  Intelligent Solar Panel Management System — Flask Application
  ---------------------------------------------------------------------------
  Project : AI-Based Solar Panel Dust Detection and Monitoring System
             Using Raspberry Pi
  Author  : Ahmed
  Date    : June 2026

  Description:
    Main Flask web server that integrates all subsystems:
      - ESP32 UART serial communication (voltage, current)
      - Solar tracking (auto/manual servo control)
      - AI dust detection (CNN inference)
      - Raspberry Pi Camera
      - Real-time dashboard

  Usage:
    python app.py                    # Start on 0.0.0.0:5000
    python app.py --port 8080        # Custom port
    python app.py --debug            # Debug mode
=============================================================================
"""

import os
import sys
import json
import logging
import argparse
import atexit
from datetime import datetime

from flask import Flask, render_template, jsonify, request, send_from_directory

# ============================================================
#  CONFIGURATION
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Serial / UART
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 9600

# Paths
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure directories exist
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(BASE_DIR, "logs", "dashboard.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("dashboard")

# ============================================================
#  FLASK APP
# ============================================================
app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    template_folder=TEMPLATES_DIR,
)
app.config["SECRET_KEY"] = "solar-panel-dashboard-2026"

# ============================================================
#  INITIALIZE SUBSYSTEMS
# ============================================================
logger.info("=" * 60)
logger.info("  INTELLIGENT SOLAR PANEL MANAGEMENT SYSTEM")
logger.info("=" * 60)

# --- Serial Reader ---
from modules.serial_reader import SerialReader
serial_reader = SerialReader(port=SERIAL_PORT, baud_rate=SERIAL_BAUD)
serial_reader.start()

# --- Camera ---
from modules.camera import Camera
camera = Camera(save_dir=IMAGES_DIR)

# --- Solar Tracker ---
from modules.tracking import SolarTracker
tracker = SolarTracker()
tracker.start_auto_tracking()

# --- Dust Analyzer ---
from modules.dust_analyzer import DustAnalyzer
dust_analyzer = DustAnalyzer()

logger.info("All subsystems initialized")
logger.info(f"Serial: {'simulation' if serial_reader._simulation_mode else SERIAL_PORT}")
logger.info(f"Camera: {camera.backend}")
logger.info(f"Tracking: {'simulation' if tracker._simulation else 'GPIO'}")
logger.info(f"AI Model: {'available' if dust_analyzer.is_available else 'NOT available'}")

# ============================================================
#  CLEANUP ON EXIT
# ============================================================
def cleanup():
    """Graceful shutdown of all subsystems."""
    logger.info("Shutting down subsystems...")
    serial_reader.stop()
    tracker.cleanup()
    logger.info("Shutdown complete")

atexit.register(cleanup)

# ============================================================
#  ROUTES — Dashboard
# ============================================================

@app.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("index.html")


# ============================================================
#  ROUTES — Live Data API
# ============================================================

@app.route("/api/live_data")
def api_live_data():
    """
    Return latest electrical readings.
    
    Response:
        {voltage, current, power, daily_energy, last_update, connected}
    """
    data = serial_reader.get_latest()
    return jsonify(data)


@app.route("/api/history")
def api_history():
    """
    Return historical readings for chart rendering.
    
    Query params:
        limit (int): Number of data points (default 60)
    
    Response:
        [{time, voltage, current, power, energy}, ...]
    """
    limit = request.args.get("limit", 60, type=int)
    history = serial_reader.get_history(limit=limit)
    return jsonify(history)


# ============================================================
#  ROUTES — System Status
# ============================================================

@app.route("/api/system_status")
def api_system_status():
    """
    Return health status of all subsystems.
    
    Response:
        {esp32, uart, raspberry_pi, camera, ai_model, dashboard}
    """
    status = {
        "esp32": {
            "name": "ESP32",
            "status": "online" if serial_reader.is_connected else "offline",
            "detail": "Simulation" if serial_reader._simulation_mode else "Connected",
        },
        "uart": {
            "name": "UART Communication",
            "status": "online" if serial_reader.is_connected else "offline",
            "detail": f"Port: {serial_reader.port}",
        },
        "raspberry_pi": {
            "name": "Raspberry Pi",
            "status": "online",
            "detail": "Dashboard Host",
        },
        "camera": {
            "name": "Camera Module",
            "status": "online" if camera.is_available else "offline",
            "detail": f"Backend: {camera.backend}",
        },
        "ai_model": {
            "name": "AI Model",
            "status": "online" if dust_analyzer.is_available else "offline",
            "detail": "CNN Dust Detector",
        },
        "dashboard": {
            "name": "Dashboard Server",
            "status": "online",
            "detail": "Flask Running",
        },
        "simulation_active": serial_reader._simulation_mode,
        "timestamp": datetime.now().isoformat(),
    }
    return jsonify(status)


# ============================================================
#  ROUTES — Solar Tracking
# ============================================================

@app.route("/api/tracking", methods=["GET"])
def api_tracking_get():
    """
    Return current tracking status.
    
    Response:
        {mode, solar_time, hour_angle, servo_angle, tracking_active, ...}
    """
    status = tracker.get_status()
    return jsonify(status)


@app.route("/api/tracking", methods=["POST"])
def api_tracking_post():
    """
    Update tracking mode.
    
    Request body:
        {mode: "auto" | "manual"}
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "auto")

    if mode == "auto":
        tracker.set_auto_mode()
    elif mode == "manual":
        tracker.set_manual_mode()
    else:
        return jsonify({"error": f"Invalid mode: {mode}"}), 400

    return jsonify(tracker.get_status())


@app.route("/api/manual_servo", methods=["POST"])
def api_manual_servo():
    """
    Manually control servo position.
    
    Request body:
        {angle: 0-180}
        or {action: "left" | "right" | "center" | "sunrise" | "noon" | "sunset"}
    """
    data = request.get_json(silent=True) or {}

    if "angle" in data:
        result = tracker.set_servo_angle(data["angle"])
    elif "action" in data:
        action = data["action"]
        action_map = {
            "left": tracker.move_left,
            "right": tracker.move_right,
            "center": tracker.center,
            "sunrise": tracker.sunrise_position,
            "noon": tracker.noon_position,
            "sunset": tracker.sunset_position,
        }
        handler = action_map.get(action)
        if handler:
            result = handler()
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400
    else:
        return jsonify({"error": "Provide 'angle' or 'action'"}), 400

    return jsonify({**result, **tracker.get_status()})


@app.route("/api/tracking_settings", methods=["GET"])
def api_tracking_settings_get():
    """Return current tracking configuration."""
    return jsonify(tracker.get_settings())


@app.route("/api/tracking_settings", methods=["POST"])
def api_tracking_settings_post():
    """
    Update tracking configuration.
    
    Request body:
        {start_time: "HH:MM", end_time: "HH:MM", interval: minutes}
    """
    data = request.get_json(silent=True) or {}
    result = tracker.update_settings(
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        interval=data.get("interval"),
    )
    return jsonify(result)


# ============================================================
#  ROUTES — Camera
# ============================================================

@app.route("/capture", methods=["POST"])
def capture_image():
    """
    Trigger camera capture.
    
    Saves image to static/images/latest.jpg
    
    Response:
        {success, path, timestamp, backend, message}
    """
    result = camera.capture()

    # Add image metadata if capture was successful
    if result.get("success"):
        image_path = os.path.join(IMAGES_DIR, "latest.jpg")
        try:
            from PIL import Image as PILImage
            with PILImage.open(image_path) as img:
                result["resolution"] = f"{img.width}x{img.height}"
                result["width"] = img.width
                result["height"] = img.height
        except Exception:
            result["resolution"] = "Unknown"
        result["filename"] = "latest.jpg"
        result["filesize"] = os.path.getsize(image_path) if os.path.exists(image_path) else 0

    return jsonify(result)


# ============================================================
#  ROUTES — AI Dust Detection
# ============================================================

@app.route("/analyze", methods=["POST"])
def analyze_dust():
    """
    Run AI dust detection on the latest captured image.
    
    Response:
        {success, prediction, confidence, confidence_pct,
         recommendation, timestamp, message}
    """
    image_path = os.path.join(IMAGES_DIR, "latest.jpg")

    if not os.path.exists(image_path):
        return jsonify({
            "success": False,
            "message": "No image found — capture an image first",
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "recommendation": "Capture an image before analysis",
        })

    result = dust_analyzer.analyze(image_path)
    return jsonify(result)


@app.route("/api/dust_result")
def api_dust_result():
    """Return the last dust analysis result."""
    result = dust_analyzer.get_last_result()
    if result:
        return jsonify(result)
    return jsonify({"success": False, "message": "No analysis performed yet"})


# ============================================================
#  ROUTES — Static Files
# ============================================================

@app.route("/images/<path:filename>")
def serve_image(filename):
    """Serve captured images."""
    return send_from_directory(IMAGES_DIR, filename)


# ============================================================
#  ROUTES — UART Debug
# ============================================================

@app.route("/api/uart_debug")
def api_uart_debug():
    """Return UART debugging information."""
    return jsonify(serial_reader.get_debug_info())


# ============================================================
#  ROUTES — AI Status
# ============================================================

@app.route("/api/ai_status")
def api_ai_status():
    """
    Return AI model information.

    Response:
        {model_file, inference_script, status, classes, available}
    """
    return jsonify({
        "model_file": "cnn_dust_model.onnx",
        "inference_script": "run_dust_onnx.py",
        "status": "Online" if dust_analyzer.is_available else "Offline",
        "available": dust_analyzer.is_available,
        "classes": ["Clean", "Dusty"],
        "model_type": "Convolutional Neural Network (CNN)",
        "runtime": "ONNX Runtime",
        "last_result": dust_analyzer.get_last_result(),
    })


# ============================================================
#  ROUTES — Data Export
# ============================================================

@app.route("/api/export_csv")
def api_export_csv():
    """
    Export chart data as CSV.
    """
    import io
    history = serial_reader.get_history(limit=999)

    output = io.StringIO()
    output.write("Time,Voltage (V),Current (A),Power (W),Energy (Wh)\n")
    for row in history:
        output.write(f"{row['time']},{row['voltage']},{row['current']},{row['power']},{row['energy']}\n")

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=solar_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"},
    )


# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solar Panel Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--serial-port", default=SERIAL_PORT, help=f"Serial port (default: {SERIAL_PORT})")
    parser.add_argument("--baud", type=int, default=SERIAL_BAUD, help=f"Baud rate (default: {SERIAL_BAUD})")
    args = parser.parse_args()

    # Update serial config if provided
    if args.serial_port != SERIAL_PORT:
        serial_reader.port = args.serial_port
        logger.info(f"Serial port overridden: {args.serial_port}")

    logger.info(f"Dashboard starting on http://{args.host}:{args.port}")
    logger.info("Access from tablet: http://<raspberry-pi-ip>:5000")

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=False,  # Prevent double-initialization of threads
    )
