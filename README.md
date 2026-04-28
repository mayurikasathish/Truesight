TrueSight - Media Authentication, Watermarking, and Deepfake Detection
Overview
TrueSight is a lightweight media-authentication system that embeds an invisible cryptographic watermark into images and videos. It can later verify authenticity by comparing the original and watermarked versions. The system also integrates deepfake detection using SightEngine’s cloud API. A simple FastAPI backend powers all features with a minimal frontend UI.
Key Features
• Invisible digital watermarking for images and videos  
• Extraction and cryptographic verification of watermarks  
• Deepfake detection using SightEngine API (image + video frame-level)  
• Heatmap generation tools for analyzing watermark impact  
• Ed25519-based key generation and signing  
• FastAPI backend with CORS support  
• Basic frontend UI for quick testing
How Watermarking Works
TrueSight embeds watermarks in the frequency components of an image or video.  
This transform-domain embedding method ensures the watermark is:  
• Invisible  
• Hard to remove  
• Cryptographically verifiable  

A signature is generated using Ed25519 from the **original file bytes**, ensuring authenticity. This signature is then embedded invisibly into the media.
Image Watermark Example
A transparent PNG image of a pizza (no background) was watermarked.

Original: Transparent PNG with no background  
Watermarked: Appears to have a faint background

This effect occurs because watermarking modifies internal frequency coefficients, proving that the watermark exists even though it is **not visibly drawn**. It demonstrates successful hidden watermark embedding.
Deepfake Detection
TrueSight uses **SightEngine**’s AI-based deepfake detection API.

Capabilities include:  
• Predicting whether an image or video frame is fake  
• Providing probability scores  
• Detecting face-level anomalies  
• Supporting multiple file formats  

The backend fetches results from SightEngine and returns structured authenticity reports.
Project Structure
backend/  
  • main.py — FastAPI application  
  • watermarking.py — watermark algorithms  
  • deepfake_detection_api.py — SightEngine API integration  
  • deepfake_detection.py — optional local helpers  
  • test_api.py — scripts for testing endpoints  
  • storage/ — temporary output files  

frontend/  
  • index.html — user interface  

Additional Files:  
  • requirements.txt — dependencies  
  • STRIDE_THREAT_MODEL.md — security analysis  
  • DEEPFAKE_DETECTION_README.md — deepfake documentation
Running the Server
1. Activate your virtual environment  
2. Install requirements  
3. Start FastAPI:

    uvicorn main:app --reload

Access the service:  
http://127.0.0.1:8000  

API docs:  
http://127.0.0.1:8000/docs
Technologies Used
• FastAPI  
• OpenCV  
• NumPy  
• PyNaCl (Ed25519)  
• FFmpeg  
• SightEngine API  
• Python 3.10
License
This project is intended for educational and research purposes only.
