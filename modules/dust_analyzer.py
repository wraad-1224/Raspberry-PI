"""
=============================================================================
  Dust Analyzer Module — AI Inference Wrapper
  ---------------------------------------------------------------------------
  Wraps the existing run_dust_cnn.py script to provide structured JSON
  results for the dashboard. Uses the existing cnn_dust_model.pt model.
  
  IMPORTANT: This module does NOT create or retrain any model.
  It uses the existing model files as-is.
=============================================================================
"""

import os
import sys
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Add project root to path so we can import run_dust_cnn
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Try to import the existing prediction function
AI_AVAILABLE = False
try:
    from run_dust_cnn import predict_image
    AI_AVAILABLE = True
    logger.info("AI dust detection model loaded successfully")
except ImportError as e:
    logger.warning(f"Could not import run_dust_cnn: {e}")
except Exception as e:
    logger.error(f"Error loading AI model: {e}")


class DustAnalyzer:
    """
    Wrapper around the existing CNN dust detection model.

    Uses:
        - run_dust_cnn.py → predict_image() function
        - cnn_dust_model.pt → trained PyTorch model
        - cnn_classes.json → class labels ["Clean", "Dusty"]

    Returns structured results with prediction, confidence,
    and actionable recommendation.
    """

    def __init__(self):
        self.available = AI_AVAILABLE
        self.last_result = None
        self.model_path = os.path.join(PROJECT_ROOT, "cnn_dust_model.pt")
        self.classes_path = os.path.join(PROJECT_ROOT, "cnn_classes.json")

        # Verify model file exists
        if not os.path.exists(self.model_path):
            self.available = False
            logger.error(f"Model file not found: {self.model_path}")

    @property
    def is_available(self):
        """Check if AI model is available for inference."""
        return self.available

    def analyze(self, image_path):
        """
        Run dust detection inference on an image.

        Args:
            image_path (str): Path to the image file to analyze.

        Returns:
            dict: {
                success: bool,
                prediction: str ("Clean" or "Dusty"),
                confidence: float (0.0–1.0),
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

        # Check if AI is available
        if not self.available:
            result = {
                "success": False,
                "prediction": None,
                "confidence": 0.0,
                "confidence_pct": "0.0%",
                "recommendation": "AI model is not available",
                "timestamp": timestamp,
                "image_path": image_path,
                "message": "AI model not loaded — check run_dust_cnn.py and cnn_dust_model.pt",
            }
            self.last_result = result
            return result

        try:
            # Redirect stdout during inference to prevent Unicode
            # encoding errors from print statements in run_dust_cnn.py
            # (the bar chart uses █ characters that crash cp1256 on Windows)
            import io
            old_stdout = sys.stdout
            sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')

            try:
                # Call the existing predict_image function
                prediction, confidence = predict_image(
                    image_path,
                    model_path=self.model_path,
                    classes_path=self.classes_path,
                )
            finally:
                sys.stdout = old_stdout

            # Generate recommendation based on prediction
            recommendation = self._get_recommendation(prediction, confidence)

            result = {
                "success": True,
                "prediction": prediction,
                "confidence": round(confidence, 4),
                "confidence_pct": f"{confidence * 100:.1f}%",
                "recommendation": recommendation,
                "timestamp": timestamp,
                "image_path": image_path,
                "message": f"Analysis complete — {prediction} ({confidence * 100:.1f}%)",
            }

            logger.info(f"Dust analysis: {prediction} ({confidence * 100:.1f}%)")

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
