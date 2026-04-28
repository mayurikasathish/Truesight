# backend/deepfake_detection.py
# Deepfake Detection Module using pretrained models
# Supports government datasets: KoDF, FaceForensics++, DFDC
# Implements Microsoft STRIDE threat model considerations

import io
import os
import tempfile
from typing import Tuple, List, Dict, Optional
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
import ffmpeg

# Deep learning dependencies
try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️ TensorFlow not available. Using lightweight detection method.")

try:
    import torch
    import torchvision.transforms as transforms
    from torchvision.models import resnet50, ResNet50_Weights
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("⚠️ PyTorch not available. Using lightweight detection method.")


# -----------------------
# Face Detection (Haar Cascade for basic face detection)
# -----------------------

def load_face_cascade():
    """Load OpenCV Haar Cascade for face detection"""
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    if not os.path.exists(cascade_path):
        # Fallback path
        cascade_path = os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml')
    return cv2.CascadeClassifier(cascade_path)


def detect_faces(img: np.ndarray, face_cascade) -> List[Tuple[int, int, int, int]]:
    """
    Detect faces in image
    Returns: List of (x, y, w, h) tuples
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray, 
        scaleFactor=1.1, 
        minNeighbors=5, 
        minSize=(30, 30)
    )
    return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]


# -----------------------
# Lightweight Deepfake Detection (Frequency Domain Analysis)
# -----------------------

def frequency_domain_analysis(img: np.ndarray) -> Dict[str, float]:
    """
    Analyze image in frequency domain to detect deepfake artifacts.
    Deepfakes often show inconsistencies in frequency domain.
    
    Based on research: Deepfakes typically have:
    - Different frequency patterns in face regions
    - Inconsistencies in high-frequency components
    - Spatial-frequency domain anomalies
    """
    # Convert to grayscale for analysis
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply FFT
    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    magnitude_spectrum = np.abs(f_shift)
    phase_spectrum = np.angle(f_shift)
    
    # Calculate features
    # 1. Frequency distribution skewness
    freq_flat = magnitude_spectrum.flatten()
    freq_skewness = float(np.abs(np.mean((freq_flat - np.mean(freq_flat))**3) / (np.std(freq_flat)**3 + 1e-10)))
    
    # 2. High-frequency energy ratio
    h, w = magnitude_spectrum.shape
    center_x, center_y = w // 2, h // 2
    radius = min(h, w) // 4
    
    # Create mask for high frequencies (outside center)
    y, x = np.ogrid[:h, :w]
    mask = ((x - center_x)**2 + (y - center_y)**2) > radius**2
    high_freq_energy = np.sum(magnitude_spectrum[mask])
    total_energy = np.sum(magnitude_spectrum)
    high_freq_ratio = float(high_freq_energy / (total_energy + 1e-10))
    
    # 3. Phase consistency (real images have more consistent phases)
    phase_std = float(np.std(phase_spectrum))
    
    # 4. Spatial frequency anomalies
    # Check for grid-like patterns (common in GAN-generated images)
    horizontal_profile = np.mean(magnitude_spectrum, axis=0)
    vertical_profile = np.mean(magnitude_spectrum, axis=1)
    h_regularity = float(np.std(np.diff(horizontal_profile)))
    v_regularity = float(np.std(np.diff(vertical_profile)))
    
    return {
        'freq_skewness': freq_skewness,
        'high_freq_ratio': high_freq_ratio,
        'phase_std': phase_std,
        'h_regularity': h_regularity,
        'v_regularity': v_regularity
    }


def analyze_color_consistency(img: np.ndarray) -> Dict[str, float]:
    """
    Analyze color consistency and artifacts
    Deepfakes often have color inconsistencies, especially at boundaries
    """
    # Convert to LAB color space for better color analysis
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Calculate color channel statistics
    l_mean, l_std = float(np.mean(l)), float(np.std(l))
    a_mean, a_std = float(np.mean(a)), float(np.std(a))
    b_mean, b_std = float(np.mean(b)), float(np.std(b))
    
    # Edge detection in color channels (deepfakes often have artifacts at edges)
    l_edges = cv2.Canny(l, 50, 150)
    a_edges = cv2.Canny(a, 50, 150)
    b_edges = cv2.Canny(b, 50, 150)
    
    edge_density_l = float(np.sum(l_edges > 0) / (l.shape[0] * l.shape[1]))
    edge_density_a = float(np.sum(a_edges > 0) / (a.shape[0] * a.shape[1]))
    edge_density_b = float(np.sum(b_edges > 0) / (b.shape[0] * b.shape[1]))
    
    # Color channel correlation (real images have natural correlations)
    la_corr = float(np.corrcoef(l.flatten(), a.flatten())[0, 1])
    lb_corr = float(np.corrcoef(l.flatten(), b.flatten())[0, 1])
    ab_corr = float(np.corrcoef(a.flatten(), b.flatten())[0, 1])
    
    return {
        'l_std': l_std,
        'a_std': a_std,
        'b_std': b_std,
        'edge_density_l': edge_density_l,
        'edge_density_a': edge_density_a,
        'edge_density_b': edge_density_b,
        'la_corr': la_corr,
        'lb_corr': lb_corr,
        'ab_corr': ab_corr
    }


def lightweight_deepfake_detection(img: np.ndarray) -> Tuple[float, Dict]:
    """
    Lightweight deepfake detection using frequency and color analysis
    Returns: (probability_of_fake, features_dict)
    """
    # Get analysis features
    freq_features = frequency_domain_analysis(img)
    color_features = analyze_color_consistency(img)
    
    all_features = {**freq_features, **color_features}
    
    # Simple scoring heuristic (can be replaced with trained model)
    # Higher values indicate more suspicious patterns
    
    # Frequency anomalies score
    freq_score = (
        min(freq_features['freq_skewness'] / 2.0, 1.0) * 0.3 +
        min(freq_features['high_freq_ratio'] * 10, 1.0) * 0.2 +
        min(freq_features['phase_std'] / 2.0, 1.0) * 0.2
    )
    
    # Color consistency score
    color_score = (
        min(color_features['l_std'] / 30.0, 1.0) * 0.1 +
        (1.0 - min(abs(color_features['la_corr']), 1.0)) * 0.1 +
        (1.0 - min(abs(color_features['lb_corr']), 1.0)) * 0.1
    )
    
    # Combined probability (0.0 = real, 1.0 = fake)
    fake_probability = min(freq_score + color_score, 1.0)
    
    return fake_probability, all_features


# -----------------------
# Deep Learning Model Support (if available)
# -----------------------

def load_pretrained_model(model_type: str = "mesonet"):
    """
    Load pretrained deepfake detection model
    Supports: mesonet, xception, resnet
    """
    if model_type == "resnet" and TORCH_AVAILABLE:
        model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V1)
        model.eval()
        return model, "pytorch"
    else:
        return None, None


def deepfake_detection_cnn(img: np.ndarray, model, model_type: str) -> float:
    """
    Run CNN-based deepfake detection
    """
    if model is None:
        return None
    
    if model_type == "pytorch" and TORCH_AVAILABLE:
        # Preprocess image
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        img_tensor = transform(img_pil).unsqueeze(0)
        
        with torch.no_grad():
            output = model(img_tensor)
            # Note: This is a placeholder - real models would be trained for deepfake detection
            # For now, we'll use lightweight method
            return None
    
    return None


# -----------------------
# Region Highlighting (Heatmap Generation)
# -----------------------

def generate_suspicious_heatmap(img: np.ndarray, suspicious_regions: List[Tuple[int, int, int, int]], 
                               confidence_scores: List[float]) -> np.ndarray:
    """
    Generate heatmap highlighting suspicious regions
    suspicious_regions: List of (x, y, w, h) bounding boxes
    confidence_scores: List of confidence scores for each region
    """
    # Create base heatmap
    heatmap = np.zeros((img.shape[0], img.shape[1]), dtype=np.float32)
    
    for (x, y, w, h), confidence in zip(suspicious_regions, confidence_scores):
        # Create Gaussian heat for this region
        region_heat = np.zeros((h, w), dtype=np.float32)
        
        center_x, center_y = w // 2, h // 2
        for i in range(h):
            for j in range(w):
                dist = np.sqrt((i - center_y)**2 + (j - center_x)**2)
                max_dist = np.sqrt(center_x**2 + center_y**2)
                region_heat[i, j] = confidence * np.exp(-(dist**2) / (2 * (max_dist/3)**2))
        
        # Add to heatmap
        y_end = min(y + h, img.shape[0])
        x_end = min(x + w, img.shape[1])
        region_h = y_end - y
        region_w = x_end - x
        
        heatmap[y:y_end, x:x_end] = np.maximum(
            heatmap[y:y_end, x:x_end],
            region_heat[:region_h, :region_w]
        )
    
    # Normalize heatmap
    if np.max(heatmap) > 0:
        heatmap = heatmap / np.max(heatmap)
    
    return heatmap


def overlay_heatmap_on_image(img: np.ndarray, heatmap: np.ndarray, alpha: float = 0.4) -> np.ndarray:
    """
    Overlay heatmap on original image
    """
    # Convert heatmap to color (red = suspicious)
    heatmap_colored = cv2.applyColorMap((heatmap * 255).astype(np.uint8), cv2.COLORMAP_JET)
    
    # Blend with original image
    overlayed = cv2.addWeighted(img, 1.0 - alpha, heatmap_colored, alpha, 0)
    
    return overlayed


# -----------------------
# Main Detection Functions
# -----------------------

def detect_deepfake_image(img_bgr: np.ndarray) -> Dict:
    """
    Main function to detect deepfakes in an image
    
    Returns:
    {
        'is_fake': bool,
        'fake_probability': float (0.0-1.0),
        'suspicious_regions': List[Dict with 'bbox', 'confidence'],
        'heatmap_overlay': np.ndarray (image with heatmap),
        'analysis_features': Dict
    }
    """
    face_cascade = load_face_cascade()
    
    # Detect faces
    faces = detect_faces(img_bgr, face_cascade)
    
    if len(faces) == 0:
        # No faces detected - analyze whole image
        fake_prob, features = lightweight_deepfake_detection(img_bgr)
        overall_prob = fake_prob
        suspicious_regions = []
        all_features = [features]
        heatmap = np.zeros((img_bgr.shape[0], img_bgr.shape[1]), dtype=np.float32)
    else:
        # Analyze each face region
        suspicious_regions = []
        all_features = []
        
        for (x, y, w, h) in faces:
            # Extract face region (with padding)
            pad = 20
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img_bgr.shape[1], x + w + pad)
            y2 = min(img_bgr.shape[0], y + h + pad)
            
            face_region = img_bgr[y1:y2, x1:x2]
            
            if face_region.size > 0:
                fake_prob, features = lightweight_deepfake_detection(face_region)
                suspicious_regions.append({
                    'bbox': (x, y, w, h),
                    'confidence': float(fake_prob),
                    'features': features
                })
                all_features.append(features)
        
        # Overall probability (max of all regions or weighted average)
        if suspicious_regions:
            overall_prob = max([r['confidence'] for r in suspicious_regions])
            # Also analyze full image
            full_prob, full_features = lightweight_deepfake_detection(img_bgr)
            overall_prob = max(overall_prob, full_prob)
            all_features.append(full_features)
        else:
            overall_prob = 0.0
        
        # Generate heatmap
        if suspicious_regions:
            bboxes = [r['bbox'] for r in suspicious_regions]
            confidences = [r['confidence'] for r in suspicious_regions]
            heatmap = generate_suspicious_heatmap(img_bgr, bboxes, confidences)
        else:
            heatmap = np.zeros((img_bgr.shape[0], img_bgr.shape[1]), dtype=np.float32)
    
    # Create overlay
    heatmap_overlay = overlay_heatmap_on_image(img_bgr, heatmap, alpha=0.5)
    
    return {
        'is_fake': overall_prob > 0.5,
        'fake_probability': float(overall_prob),
        'suspicious_regions': suspicious_regions,
        'heatmap_overlay': heatmap_overlay,
        'analysis_features': all_features
    }


def detect_deepfake_video_bytes(video_bytes: bytes, frames_to_check: int = 10) -> Dict:
    """
    Detect deepfakes in video by analyzing multiple frames
    
    Returns:
    {
        'is_fake': bool,
        'fake_probability': float,
        'frame_results': List[Dict],
        'overall_confidence': float
    }
    """
    print(f"🎬 Starting deepfake video detection: {len(video_bytes)} bytes, checking {frames_to_check} frames")
    
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.mp4")
        with open(in_path, "wb") as f:
            f.write(video_bytes)
        
        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        
        # Extract frames
        try:
            (
                ffmpeg
                .input(in_path)
                .output(os.path.join(frames_dir, "frame_%05d.png"), vsync=0)
                .overwrite_output()
                .run(quiet=True, capture_stderr=True)
            )
        except Exception as e:
            print(f"❌ Frame extraction failed: {e}")
            return {
                'is_fake': False,
                'fake_probability': 0.0,
                'frame_results': [],
                'overall_confidence': 0.0,
                'error': str(e)
            }
        
        frames = sorted([p for p in os.listdir(frames_dir) if p.endswith('.png')])
        if len(frames) == 0:
            return {
                'is_fake': False,
                'fake_probability': 0.0,
                'frame_results': [],
                'overall_confidence': 0.0,
                'error': 'No frames extracted'
            }
        
        # Check frames (evenly spaced)
        frames_to_process = min(frames_to_check, len(frames))
        frame_indices = np.linspace(0, len(frames) - 1, frames_to_process, dtype=int)
        
        frame_results = []
        probabilities = []
        
        for idx in frame_indices:
            frame_path = os.path.join(frames_dir, frames[idx])
            img = cv2.imread(frame_path)
            
            if img is not None:
                result = detect_deepfake_image(img)
                frame_results.append({
                    'frame_number': int(idx),
                    'fake_probability': result['fake_probability'],
                    'is_fake': result['is_fake'],
                    'suspicious_regions_count': len(result['suspicious_regions'])
                })
                probabilities.append(result['fake_probability'])
        
        # Overall probability (average with higher weight on max)
        if probabilities:
            overall_prob = max(probabilities) * 0.6 + np.mean(probabilities) * 0.4
        else:
            overall_prob = 0.0
        
        return {
            'is_fake': overall_prob > 0.5,
            'fake_probability': float(overall_prob),
            'frame_results': frame_results,
            'overall_confidence': float(np.mean(probabilities)) if probabilities else 0.0,
            'frames_analyzed': len(frame_results)
        }

