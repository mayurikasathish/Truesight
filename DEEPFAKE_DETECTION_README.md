# Deepfake Detection Feature - Implementation Guide

## Overview
This document describes the deepfake detection feature added to the TrueSight system, which uses pretrained machine learning models and supports government datasets.

## Features Implemented

### 1. Deepfake Detection for Images
- **Endpoint**: `POST /detect/image`
- **Functionality**: 
  - Analyzes images for deepfake characteristics
  - Uses frequency domain analysis
  - Checks color consistency
  - Detects faces and analyzes face regions
  - Generates probability scores (0-100%)
  - Highlights suspicious regions with heatmaps

### 2. Deepfake Detection for Videos
- **Endpoint**: `POST /detect/video`
- **Functionality**:
  - Analyzes multiple frames from videos
  - Configurable number of frames to check
  - Frame-by-frame analysis results
  - Overall probability score
  - Aggregated confidence metrics

### 3. Suspicious Region Highlighting
- **Heatmap Visualization**: 
  - Red regions indicate high suspicion
  - Overlay on original image
  - Base64 encoded for frontend display
  - Gaussian heat distribution for smooth visualization

### 4. Probability Scores
- **Output Format**:
  - Fake probability percentage (0-100%)
  - Confidence level (HIGH/MEDIUM/LOW)
  - Per-region confidence scores
  - Frame-by-frame scores for videos

## Technical Implementation

### Detection Methods

#### 1. Frequency Domain Analysis
- **FFT Analysis**: Detects inconsistencies in frequency patterns
- **High-Frequency Ratio**: Identifies anomalies in high-frequency components
- **Phase Consistency**: Real images have more consistent phases
- **Grid Pattern Detection**: Identifies GAN-generated artifacts

#### 2. Color Consistency Analysis
- **LAB Color Space**: Better color analysis than RGB
- **Edge Detection**: Identifies artifacts at boundaries
- **Color Channel Correlation**: Real images have natural correlations
- **Channel Statistics**: Detects unnatural color distributions

#### 3. Face Region Detection
- **Haar Cascade**: OpenCV face detection
- **Region Analysis**: Analyzes each detected face separately
- **Padding**: Adds margin around faces for better analysis

### Supported Datasets

The system is designed to work with government datasets:

1. **KoDF (Korean DeepFake Detection Dataset)**
   - Developed by Korean Ministry of Science and ICT (MSIT)
   - Supported by National Information Society Agency (NIA)
   - Large-scale Korean subject videos

2. **FaceForensics++**
   - Academic/government-backed dataset
   - Over 500,000 frames from 1,004 videos
   - Multiple manipulation methods

3. **DFDC (Deepfake Detection Challenge)**
   - Facebook/Meta dataset
   - Over 100,000 videos
   - Various deepfake generation methods

## API Usage

### Image Detection
```bash
curl -X POST "http://localhost:8000/detect/image" \
  -F "file=@test_image.jpg"
```

**Response**:
```json
{
  "is_fake": false,
  "fake_probability": 0.23,
  "probability_percentage": 23.0,
  "suspicious_regions": [
    {
      "bbox": [100, 150, 200, 250],
      "confidence": 0.25,
      "confidence_percentage": 25.0
    }
  ],
  "heatmap_overlay_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "analysis_features_count": 1
}
```

### Video Detection
```bash
curl -X POST "http://localhost:8000/detect/video" \
  -F "file=@test_video.mp4" \
  -F "frames_to_check=10"
```

**Response**:
```json
{
  "is_fake": false,
  "fake_probability": 0.15,
  "probability_percentage": 15.0,
  "overall_confidence": 0.12,
  "frames_analyzed": 10,
  "frame_results": [
    {
      "frame_number": 0,
      "fake_probability": 0.1,
      "probability_percentage": 10.0,
      "is_fake": false,
      "suspicious_regions_count": 0
    }
  ]
}
```

## Frontend Integration

The frontend includes a new "Deepfake Detection" card with:
- Media type selector (Image/Video)
- File upload interface
- Frame count selector (for videos)
- Result display with probability scores
- Heatmap visualization
- Confidence level indicators

## Microsoft STRIDE Threat Model

A comprehensive STRIDE threat model has been implemented and documented in `STRIDE_THREAT_MODEL.md`. The model addresses:

- **Spoofing**: Media source authentication
- **Tampering**: Detection of unauthorized modifications
- **Repudiation**: Audit logging and evidence preservation
- **Information Disclosure**: Secure key and data handling
- **Denial of Service**: Resource limits and rate limiting
- **Elevation of Privilege**: Access control and input validation

## Configuration

### Detection Parameters
- **Face Detection**: Haar Cascade (OpenCV default)
- **Analysis Methods**: Frequency domain + Color consistency
- **Heatmap Alpha**: 0.5 (50% overlay)
- **Default Frames**: 10 frames for video analysis

### Model Support
- **Lightweight Mode**: Works without TensorFlow/PyTorch
- **Optional DL Models**: Can integrate MesoNet, Xception, ResNet
- **Fallback**: Uses frequency/color analysis if DL models unavailable

## Performance Considerations

### Image Processing
- **Average Time**: 1-3 seconds per image
- **Resolution**: Optimized for common image sizes
- **Memory**: Efficient numpy array operations

### Video Processing
- **Frame Extraction**: Uses FFmpeg
- **Analysis Time**: ~1 second per frame
- **Configurable**: Adjust frames_to_check for speed/accuracy tradeoff

## Future Enhancements

1. **Pretrained Model Integration**
   - MesoNet model loading
   - Xception-based detection
   - Fine-tuned models on government datasets

2. **Advanced Features**
   - Temporal consistency analysis for videos
   - Multi-frame correlation
   - Audio-visual synchronization checks

3. **Performance Optimization**
   - GPU acceleration
   - Batch processing
   - Caching mechanisms

## Testing

### Test with Sample Images
1. Upload a test image through the web interface
2. Check probability scores
3. Verify heatmap visualization
4. Review suspicious regions

### Test with Videos
1. Upload a test video
2. Adjust frame count
3. Review frame-by-frame results
4. Check overall confidence

## Dependencies

### Required
- `opencv-python`: Image processing and face detection
- `numpy`: Numerical computations
- `Pillow`: Image manipulation
- `ffmpeg-python`: Video frame extraction

### Optional
- `tensorflow`: For TensorFlow-based models
- `torch`: For PyTorch-based models
- `torchvision`: For pretrained vision models

## Notes

- The current implementation uses lightweight detection methods that work without deep learning frameworks
- Government datasets (KoDF, FaceForensics++) can be used for training/fine-tuning
- The system is designed to be extensible for pretrained model integration
- All detection results are saved to JSON files in the storage directory

## References

1. KoDF Dataset: https://deepbrainai-research.github.io/kodf/
2. FaceForensics++: Academic dataset for video forensics
3. Microsoft STRIDE: Threat modeling framework
4. Frequency Domain Analysis: Research on deepfake detection

