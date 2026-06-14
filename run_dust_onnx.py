"""
=============================================================================
  ONNX Inference — Solar Panel Dust Detection (Clean vs Dusty)
  ---------------------------------------------------------------------------
  Drop-in replacement for run_dust_cnn.py using ONNX Runtime.
  No PyTorch dependency required.

  Usage:
    python run_dust_onnx.py                              # uses default test image
    python run_dust_onnx.py path/to/image.jpg            # specify image
    python run_dust_onnx.py image.jpg model.onnx         # specify image + model

  Requirements:
    pip install onnxruntime numpy pillow
=============================================================================
"""

import sys
import os
import json
import numpy as np
import onnxruntime as ort
from PIL import Image

# ============================================================
# CONFIGURATION (Must match training)
# ============================================================
IMG_SIZE = 128

# Preprocessing constants (identical to PyTorch training)
MEAN = (0.5, 0.5, 0.5)
STD = (0.5, 0.5, 0.5)


# ============================================================
# PREPROCESSING (Identical to PyTorch — no torch/torchvision)
# ============================================================
def preprocess_image(image_path):
    """
    Load and preprocess an image identically to the PyTorch pipeline.

    Steps (matching torchvision.transforms):
      1. Open image as RGB
      2. Resize to (IMG_SIZE, IMG_SIZE) using bilinear interpolation
      3. Convert to float32 numpy array in [0, 1] range
      4. Transpose from HWC to CHW format
      5. Normalize: (pixel - mean) / std with mean=0.5, std=0.5

    Args:
        image_path (str): Path to image file.

    Returns:
        numpy.ndarray: Preprocessed image tensor [1, 3, 128, 128]
    """
    # Load and convert to RGB
    image = Image.open(image_path).convert("RGB")

    # Resize to IMG_SIZE x IMG_SIZE (bilinear — matches torchvision default)
    image = image.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)

    # Convert to numpy float32 array [H, W, C] in range [0, 1]
    img_array = np.array(image, dtype=np.float32) / 255.0

    # Transpose to [C, H, W] (PyTorch format)
    img_array = img_array.transpose(2, 0, 1)

    # Normalize: (pixel - mean) / std
    for c in range(3):
        img_array[c] = (img_array[c] - MEAN[c]) / STD[c]

    # Add batch dimension: [1, 3, 128, 128]
    img_array = np.expand_dims(img_array, axis=0)

    return img_array


# ============================================================
# SOFTMAX (Pure numpy — replaces torch.softmax)
# ============================================================
def softmax(x):
    """Compute softmax probabilities along the last axis."""
    exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return exp_x / np.sum(exp_x, axis=-1, keepdims=True)


# ============================================================
# PREDICTION FUNCTION
# ============================================================
def predict_image(image_path, model_path="cnn_dust_model.onnx", classes_path="cnn_classes.json"):
    """
    Load ONNX model, preprocess image, and predict Clean/Dusty.

    API is identical to run_dust_cnn.predict_image().

    Args:
        image_path (str): Path to the image to classify.
        model_path (str): Path to the ONNX model file.
        classes_path (str): Path to the JSON class labels file.

    Returns:
        tuple: (prediction: str, confidence: float)
            prediction — "Clean" or "Dusty"
            confidence — float between 0.0 and 1.0
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Resolve relative paths to script directory
    if not os.path.isabs(model_path):
        model_path = os.path.join(script_dir, model_path)
    if not os.path.isabs(classes_path):
        classes_path = os.path.join(script_dir, classes_path)

    # --- Load class names ---
    if os.path.exists(classes_path):
        with open(classes_path, "r") as f:
            classes = json.load(f)
    else:
        print(f"Warning: {classes_path} not found. Defaulting to ['Clean', 'Dusty']")
        classes = ["Clean", "Dusty"]

    # --- Check model file ---
    if not os.path.exists(model_path):
        print(f"Error: Model file '{model_path}' not found.")
        print("Please run export_to_onnx.py first to generate the ONNX model.")
        sys.exit(1)

    # --- Create ONNX Runtime session ---
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    print(f"Model loaded from {model_path}")

    # --- Load & preprocess image ---
    try:
        input_tensor = preprocess_image(image_path)
    except Exception as e:
        print(f"Error loading image '{image_path}': {e}")
        sys.exit(1)

    # --- Inference ---
    outputs = session.run(None, {input_name: input_tensor})
    logits = outputs[0]                          # [1, num_classes]
    probs = softmax(logits)                      # probabilities
    class_idx = int(np.argmax(probs[0]))
    confidence = float(probs[0][class_idx])

    prediction = classes[class_idx]

    # --- Display results ---
    print("=" * 44)
    print("   ONNX DUST DETECTION RESULTS")
    print("=" * 44)
    print(f"  Input Image : {os.path.basename(image_path)}")
    print(f"  Prediction  : {prediction.upper()}")
    print(f"  Confidence  : {confidence*100:.1f}%")
    print("-" * 44)
    print("  Class Probabilities:")
    for idx, class_name in enumerate(classes):
        prob = float(probs[0][idx]) * 100
        bar_len = int(prob / 5)
        bar = "#" * bar_len
        print(f"    {class_name:>6}: {prob:5.1f}% {bar}")
    print("=" * 44)

    return prediction, confidence


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    default_img = r"C:\Users\Ahmed\capture7.jpg"
    if len(sys.argv) < 2:
        print(f"No arguments provided. Using default image:")
        print(f"  {default_img}\n")
        predict_image(default_img)
    else:
        img_path = sys.argv[1]
        if len(sys.argv) >= 3:
            predict_image(img_path, model_path=sys.argv[2])
        else:
            predict_image(img_path)
