"""
=============================================================================
  AI Inference Server — Solar Panel Dust Detection
  ---------------------------------------------------------------------------
  Runs on the Windows laptop. Receives images from the Raspberry Pi
  dashboard and returns CNN dust detection predictions via ONNX Runtime.

  Usage:
    python ai_server.py
    python ai_server.py --port 5001
    python ai_server.py --port 5001 --host 0.0.0.0

  Endpoint:
    POST /predict   — Upload an image, receive prediction JSON

  Requirements (Windows laptop only):
    pip install flask onnxruntime numpy pillow
=============================================================================
"""

import os
import sys
import argparse
import tempfile
import logging
from datetime import datetime
from flask import Flask, request, jsonify

# ============================================================
# CONFIGURATION
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure run_dust_onnx.py can be imported
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ai_server")

# ============================================================
# LOAD AI MODEL
# ============================================================
AI_AVAILABLE = False
predict_image = None

try:
    from run_dust_onnx import predict_image
    AI_AVAILABLE = True
    logger.info("AI model loaded successfully (ONNX Runtime)")
except ImportError as e:
    logger.error(f"Could not import run_dust_onnx: {e}")
    logger.error("Make sure run_dust_onnx.py, cnn_dust_model.onnx, and cnn_classes.json are in the same directory.")
except Exception as e:
    logger.error(f"Error loading AI model: {e}")

# Verify model file exists
MODEL_PATH = os.path.join(SCRIPT_DIR, "cnn_dust_model.onnx")
CLASSES_PATH = os.path.join(SCRIPT_DIR, "cnn_classes.json")

if not os.path.exists(MODEL_PATH):
    logger.error(f"Model file not found: {MODEL_PATH}")
    AI_AVAILABLE = False

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)

# Temporary directory for uploaded images
UPLOAD_DIR = os.path.join(SCRIPT_DIR, "temp_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "service": "Solar Panel AI Inference Server",
        "status": "Online" if AI_AVAILABLE else "Offline",
        "model": "cnn_dust_model.onnx",
        "runtime": "ONNX Runtime",
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/predict", methods=["POST"])
def predict():
    """
    Run dust detection on an uploaded image.

    Expects:
        multipart/form-data with 'image' file field.

    Returns:
        JSON: {
            success: bool,
            prediction: str,
            confidence: float,
            confidence_pct: str,
            timestamp: str,
            message: str
        }
    """
    timestamp = datetime.now().isoformat()

    # --- Check if AI is available ---
    if not AI_AVAILABLE:
        return jsonify({
            "success": False,
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "timestamp": timestamp,
            "message": "AI model not available on server",
        }), 503

    # --- Check for uploaded image ---
    if "image" not in request.files:
        return jsonify({
            "success": False,
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "timestamp": timestamp,
            "message": "No image file provided. Send as 'image' field in multipart/form-data.",
        }), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "timestamp": timestamp,
            "message": "Empty filename",
        }), 400

    # --- Save temporary image ---
    temp_path = os.path.join(UPLOAD_DIR, "temp_analysis.jpg")
    try:
        file.save(temp_path)
        logger.info(f"Image received: {file.filename} ({os.path.getsize(temp_path)} bytes)")
    except Exception as e:
        return jsonify({
            "success": False,
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "timestamp": timestamp,
            "message": f"Failed to save image: {str(e)}",
        }), 500

    # --- Run inference ---
    try:
        prediction, confidence = predict_image(
            temp_path,
            model_path=MODEL_PATH,
            classes_path=CLASSES_PATH,
        )

        result = {
            "success": True,
            "prediction": prediction,
            "confidence": round(confidence, 4),
            "confidence_pct": f"{confidence * 100:.1f}%",
            "timestamp": timestamp,
            "message": f"Analysis complete - {prediction} ({confidence * 100:.1f}%)",
        }

        logger.info(f"Prediction: {prediction} ({confidence * 100:.1f}%)")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Inference failed: {e}")
        return jsonify({
            "success": False,
            "prediction": None,
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "timestamp": timestamp,
            "message": f"Inference error: {str(e)}",
        }), 500

    finally:
        # Clean up temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Inference Server for Solar Panel Dust Detection")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5001, help="Port to listen on (default: 5001)")
    args = parser.parse_args()

    print("=" * 60)
    print("  SOLAR PANEL AI INFERENCE SERVER")
    print("=" * 60)
    print(f"  Model   : cnn_dust_model.onnx")
    print(f"  Runtime : ONNX Runtime")
    print(f"  Status  : {'Online' if AI_AVAILABLE else 'OFFLINE'}")
    print(f"  Endpoint: http://{args.host}:{args.port}/predict")
    print("=" * 60)

    if not AI_AVAILABLE:
        print("\n  WARNING: AI model is not available!")
        print("  Check that these files exist:")
        print(f"    - {MODEL_PATH}")
        print(f"    - {CLASSES_PATH}")
        print(f"    - {os.path.join(SCRIPT_DIR, 'run_dust_onnx.py')}")
        print()

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
