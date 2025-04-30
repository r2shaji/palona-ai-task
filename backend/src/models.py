# backend/src/models.py
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import numpy as np

# --- CLIP Model Setup ---
MODEL_NAME = "openai/clip-vit-large-patch14" 
if torch.backends.mps.is_available():
    DEVICE = "mps"
    print("Using MPS acceleration")
elif torch.cuda.is_available():
    DEVICE = "cuda"
    print("Using CUDA acceleration")
else:
    DEVICE = "cpu"
    print("Using CPU for computation")

clip_model = None
clip_processor = None

def load_clip_model():
    """Loads the CLIP model and processor from Hugging Face."""
    global clip_model, clip_processor
    if clip_model is None or clip_processor is None:
        print(f"Loading CLIP model ({MODEL_NAME}) to {DEVICE}...")
        try:
            clip_model = CLIPModel.from_pretrained(MODEL_NAME).to(DEVICE)
            clip_processor = CLIPProcessor.from_pretrained(MODEL_NAME)
            print("CLIP model loaded successfully.")
        except Exception as e:
            print(f"Error loading CLIP model: {e}")
            # Handle error appropriately, maybe fall back to CPU or raise
            clip_model = None
            clip_processor = None
    return clip_model, clip_processor

def extract_features_clip(image):
    """Extracts features from an image using the loaded CLIP model."""
    model, processor = load_clip_model()
    if model is None or processor is None:
        print("Cannot extract features: CLIP model not loaded.")
        return None

    try:
        # Ensure image is in RGB format
        if isinstance(image, str):
            image = Image.open(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
            
        inputs = processor(images=image, return_tensors="pt", padding=True)
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
        
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
            
        # Normalize features
        image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        
        return image_features.cpu().numpy().flatten() # Return as numpy array
    except Exception as e:
        print(f"Error extracting CLIP features: {e}")
        return None


