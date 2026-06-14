"""
=============================================================================
  Dust Analyzer Module — Remote AI Inference
  ---------------------------------------------------------------------------
  Sends captured images to the AI server (Windows laptop) for dust
  detection inference. The AI server runs ONNX Runtime with the
  cnn_dust_model.onnx model.

  IMPORTANT: This module does NOT run inference locally.
  It sends images via HTTP to the remote AI server.
=============================================================================
"""

import os
import sys
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
# AI Server URL — Change this to your Windows laptop's IP address
# Example: "http://192.168.1.100:5001/predict"
AI_SERVER_URL = "http://192.168.1.100:5001/predict"

# Connection timeout (seconds)
AI_SERVER_TIMEOUT = 15

# Project root for resolving image paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DustAnalyzer:
    """
    Remote AI dust detection client.

    Sends images to the AI server (Windows laptop) via HTTP POST
    and receives prediction results as JSON.

    Architecture:
        Raspberry Pi (Dashboard) → HTTP POST → Windows Laptop (AI Server)
        └── static/images/latest.jpg         └── run_dust_onnx.py
                                              └── cnn_dust_model.onnx

    Returns structured results with prediction, confidence,
    and actionable recommendation.
    """

    def __init__(self, server_url=None):
        self.server_url = server_url or AI_SERVER_URL
        self.last_result = None
        self._available = None  # None = not yet checked

        # Check server connectivity on startup
        self._check_server()

    def _check_server(self):
        """Check if the remote AI server is reachable."""
        try:
            # Try the health endpoint (GET /)
            health_url = self.server_url.replace("/predict", "/")
            resp = requests.get(health_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self._available = data.get("status") == "Online"
                logger.info(
                    f"AI server connected: {self.server_url} "
                    f"(status: {data.get('status', 'unknown')})"
                )
            else:
                self._available = False
                logger.warning(f"AI server returned status {resp.status_code}")
        except requests.ConnectionError:
            self._available = False
            logger.warning(f"AI server not reachable: {self.server_url}")
        except Exception as e:
            self._available = False
            logger.warning(f"AI server check failed: {e}")

    @property
    def is_available(self):
        """Check if AI server is available."""
        if self._available is None:
            self._check_server()
        return self._available if self._available is not None else False

    def analyze(self, image_path):
        """
        Send image to remote AI server for dust detection.

        Args:
            image_path (str): Path to the image file to analyze.

        Returns:
            dict: {
                success: bool,
                prediction: str ("Clean" or "Dusty"),
                confidence: float (0.0-1.0),
                confidence_pct: str ("97.4%"),
                recommendation: str,
                timestamp: str (ISO format),
                image_path: str,
                message: str
            }
        """
        timestamp = datetime.now().isoformat()

        # Validate image exists
        if not os.path.exists(image_path):
            result = {
                "success": False,
                "prediction": None,
                "confidence": 0.0,
                "confidence_pct": "0.0%",
                "recommendation": "No image found — capture an image first",
                "timestamp": timestamp,
                "image_path": image_path,
                "message": f"Image not found: {image_path}",
            }
            self.last_result = result
            return result

        # Send image to AI server
        try:
            with open(image_path, "rb") as img_file:
                files = {"image": ("latest.jpg", img_file, "image/jpeg")}
                response = requests.post(
                    self.server_url,
                    files=files,
                    timeout=AI_SERVER_TIMEOUT,
                )

            # Parse server response
            if response.status_code == 200:
                data = response.json()

                if data.get("success"):
                    prediction = data["prediction"]
                    confidence = data["confidence"]

                    # Generate recommendation locally (preserves existing logic)
                    recommendation = self._get_recommendation(prediction, confidence)

                    result = {
                        "success": True,
                        "prediction": prediction,
                        "confidence": round(confidence, 4),
                        "confidence_pct": data.get("confidence_pct", f"{confidence * 100:.1f}%"),
                        "recommendation": recommendation,
                        "timestamp": timestamp,
                        "image_path": image_path,
                        "message": f"Analysis complete — {prediction} ({confidence * 100:.1f}%)",
                    }

                    self._available = True
                    logger.info(f"Dust analysis: {prediction} ({confidence * 100:.1f}%)")
                else:
                    # Server returned success=false
                    result = {
                        "success": False,
                        "prediction": None,
                        "confidence": 0.0,
                        "confidence_pct": "0.0%",
                        "recommendation": "AI server reported an error",
                        "timestamp": timestamp,
                        "image_path": image_path,
                        "message": data.get("message", "Unknown server error"),
                    }
            else:
                result = {
                    "success": False,
                    "prediction": None,
                    "confidence": 0.0,
                    "confidence_pct": "0.0%",
                    "recommendation": "AI server error",
                    "timestamp": timestamp,
                    "image_path": image_path,
                    "message": f"AI server returned HTTP {response.status_code}",
                }

        except requests.ConnectionError:
            self._available = False
            logger.error(f"AI server unavailable: {self.server_url}")
            result = {
                "success": False,
                "prediction": None,
                "confidence": 0.0,
                "confidence_pct": "0.0%",
                "recommendation": "AI server unavailable — check laptop connection",
                "timestamp": timestamp,
                "image_path": image_path,
                "message": f"AI server unavailable: {self.server_url}",
            }

        except requests.Timeout:
            logger.error(f"AI server timeout after {AI_SERVER_TIMEOUT}s")
            result = {
                "success": False,
                "prediction": None,
                "confidence": 0.0,
                "confidence_pct": "0.0%",
                "recommendation": "AI server timeout — try again",
                "timestamp": timestamp,
                "image_path": image_path,
                "message": f"AI server timeout after {AI_SERVER_TIMEOUT} seconds",
            }

        except Exception as e:
            logger.error(f"Dust analysis failed: {e}")
            result = {
                "success": False,
                "prediction": None,
                "confidence": 0.0,
                "confidence_pct": "0.0%",
                "recommendation": "Analysis failed — check logs",
                "timestamp": timestamp,
                "image_path": image_path,
                "message": f"Analysis error: {str(e)}",
            }

        self.last_result = result
        return result

    def _get_recommendation(self, prediction, confidence):
        """Generate actionable recommendation based on prediction."""
        if prediction.lower() == "dusty":
            if confidence >= 0.9:
                return "⚠️ Cleaning Recommended — High dust accumulation detected"
            elif confidence >= 0.7:
                return "⚠️ Cleaning Recommended — Moderate dust detected"
            else:
                return "🔍 Inspection Recommended — Possible dust detected"
        else:  # Clean
            if confidence >= 0.9:
                return "✅ No Cleaning Required — Panel is clean"
            elif confidence >= 0.7:
                return "✅ No Cleaning Required — Panel appears clean"
            else:
                return "🔍 Re-inspection Recommended — Low confidence result"

    def get_last_result(self):
        """Return the most recent analysis result."""
        return self.last_result
