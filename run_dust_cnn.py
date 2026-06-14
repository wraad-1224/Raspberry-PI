"""
=============================================================================
  CNN Inference — Solar Panel Dust Detection (Clean vs Dusty)
=============================================================================
  Usage:
    python run_dust_cnn.py                          # uses default test image
    python run_dust_cnn.py path/to/image.jpg        # specify image
    python run_dust_cnn.py image.jpg model.pt       # specify image + model
=============================================================================
"""

import sys
import os
import json
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image

# ============================================================
# CONFIGURATION (Must match training)
# ============================================================
IMG_SIZE = 128

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ============================================================
# MODEL DEFINITION (Identical to training script)
# ============================================================
class DustDetectorCNN(nn.Module):
    """
    Lightweight CNN for binary dust detection.

    Architecture:
      Conv Block 1:  3 → 16 channels,  128→64  (MaxPool)
      Conv Block 2: 16 → 32 channels,   64→32  (MaxPool)
      Conv Block 3: 32 → 64 channels,   32→16  (MaxPool)
      Global Average Pooling → 64-dim vector
      FC: 64 → 32 → num_classes
    """

    def __init__(self, num_classes=2):
        super().__init__()

        # --- Block 1: 3 → 16, spatial 128→64 ---
        self.block1 = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

        # --- Block 2: 16 → 32, spatial 64→32 ---
        self.block2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

        # --- Block 3: 32 → 64, spatial 32→16 ---
        self.block3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

        # --- Classifier ---
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(64, 32),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(32, num_classes),
        )

    def forward(self, x):
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        x = self.global_pool(x)        # [B, 64, 1, 1]
        x = x.view(x.size(0), -1)      # [B, 64]
        x = self.classifier(x)         # [B, num_classes]
        return x

# ============================================================
# PREPROCESSING (Must match training — same Normalize values)
# ============================================================
transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
])

# ============================================================
# PREDICTION FUNCTION
# ============================================================
def predict_image(image_path, model_path="cnn_dust_model.pt", classes_path="cnn_classes.json"):
    """Load model, preprocess image, and predict Clean/Dusty."""
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

    # --- Load model ---
    if not os.path.exists(model_path):
        print(f"Error: Model file '{model_path}' not found.")
        print("Please run train_dust_cnn.py first.")
        sys.exit(1)

    model = DustDetectorCNN(num_classes=len(classes)).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.eval()
    print(f"Model loaded from {model_path}")

    # --- Load & preprocess image ---
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error loading image '{image_path}': {e}")
        sys.exit(1)

    input_tensor = transform(image).unsqueeze(0).to(device)  # [1, 3, 128, 128]

    # --- Inference ---
    with torch.no_grad():
        outputs = model(input_tensor)                # [1, num_classes]
        probs = torch.softmax(outputs, dim=1)        # probabilities
        confidence, predicted_idx = probs.max(1)
        class_idx = predicted_idx.item()

    prediction = classes[class_idx]

    # --- Display results ---
    print("=" * 44)
    print("   CNN DUST DETECTION RESULTS")
    print("=" * 44)
    print(f"  Input Image : {os.path.basename(image_path)}")
    print(f"  Prediction  : {prediction.upper()}")
    print(f"  Confidence  : {confidence.item()*100:.1f}%")
    print("-" * 44)
    print("  Class Probabilities:")
    for idx, class_name in enumerate(classes):
        prob = probs[0][idx].item() * 100
        bar = "█" * int(prob / 5)
        print(f"    {class_name:>6}: {prob:5.1f}% {bar}")
    print("=" * 44)

    return prediction, confidence.item()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
   # default_img = r"C:\Users\Ahmed\Downloads\Solar_Conditions\Detect_solar_dust\Clean\Imgclean_917_0.jpg"
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
