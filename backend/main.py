from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from pathlib import Path
import cv2
import numpy as np
import json
import hashlib
import tempfile
import ffmpeg
import base64
import io
from matplotlib import pyplot as plt

from watermarking import (
    generate_keypair_hex, sign_bytes_ed25519, verify_bytes_ed25519,
    embed_watermark_image, extract_watermark_image,
    bits_to_bytes, embed_watermark_video_bytes, extract_watermark_from_video_bytes
)

# IMPORTANT: Using API-based detection (90-95% accuracy)
from deepfake_detection_api import (
    detect_deepfake_image, detect_deepfake_video_bytes
)

app = FastAPI(title="TrueSight - Watermark, Verify & Deepfake Detection")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE = Path("storage")
STORAGE.mkdir(exist_ok=True)

# 🔧 IMPROVED PARAMETERS - More robust watermarking
DEFAULT_MAX_BITS = 512  # Reduced from 512 - smaller payload is more robust
DEFAULT_QUANT = 64.0    # Increased from 8.0 - larger quantization = more robust
DEFAULT_SEED = 42


@app.get("/keys/new")
def new_keys():
    sk, vk = generate_keypair_hex()
    return {"private_key_hex": sk, "public_key_hex": vk}


@app.post("/watermark/image")
async def watermark_file(
    file: UploadFile = File(...), 
    private_key_hex: str = Form(None)
):
    content = await file.read()
    original_name = file.filename or "uploaded"
    ext = Path(original_name).suffix.lower()

    if ext not in [".png", ".jpg", ".jpeg", ".bmp"]:
        return JSONResponse(
            {"error": "Only images are supported (.png, .jpg, .jpeg, .bmp)"}, 
            status_code=400
        )

    if private_key_hex and private_key_hex.strip():
        priv = private_key_hex.strip()
        try:
            from nacl.signing import SigningKey
            from nacl.encoding import HexEncoder
            sk = SigningKey(priv.encode(), encoder=HexEncoder)
            pub = sk.verify_key.encode(encoder=HexEncoder).decode()
        except Exception as e:
            return JSONResponse(
                {"error": f"Invalid private key: {str(e)}"}, 
                status_code=400
            )
    else:
        priv, pub = generate_keypair_hex()

    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return JSONResponse(
            {"error": "Failed to decode image"}, 
            status_code=400
        )

    # IMPORTANT: Sign the ORIGINAL image bytes
    signature = sign_bytes_ed25519(priv, content)
    
    # Calculate hash for debugging
    original_hash = hashlib.sha256(content).hexdigest()
    
    print(f"🔐 WATERMARKING DEBUG:")
    print(f"   Original filename: {original_name}")
    print(f"   Original size: {len(content)} bytes")
    print(f"   Original SHA256: {original_hash}")
    print(f"   Signature: {signature.hex()}")
    print(f"   Public key: {pub}")
    print(f"   Using parameters: max_bits={DEFAULT_MAX_BITS}, quant={DEFAULT_QUANT}")
    
    try:
        wm = embed_watermark_image(
            img, 
            signature, 
            max_bits=DEFAULT_MAX_BITS, 
            quant=DEFAULT_QUANT, 
            seed=DEFAULT_SEED
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Watermarking failed: {str(e)}"}, 
            status_code=500
        )

    success, buf = cv2.imencode('.png', wm, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    if not success:
        return JSONResponse(
            {"error": "Failed to encode watermarked image"}, 
            status_code=500
        )

    out_bytes = buf.tobytes()
    out_name = STORAGE / f"watermarked_{Path(original_name).stem}.png"
    out_name.write_bytes(out_bytes)
    
    # Save metadata including original hash
    metadata = {
        "original_filename": original_name,
        "original_hash_sha256": original_hash,
        "public_key_hex": pub,
        "private_key_hex": priv,
        "signature_hex": signature.hex(),
        "watermarked_filename": out_name.name,
        "watermark_params": {
            "max_bits": DEFAULT_MAX_BITS,
            "quant": DEFAULT_QUANT,
            "seed": DEFAULT_SEED
        }
    }
    meta_path = STORAGE / f"watermarked_{Path(original_name).stem}.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return FileResponse(
        out_name, 
        media_type="image/png", 
        filename=f"watermarked_{Path(original_name).stem}.png",
        headers={
            "X-Public-Key": pub,
        }
    )


@app.post("/verify/image")
async def verify_file(
    file: UploadFile = File(...), 
    public_key_hex: str = Form(...),
    original_file: UploadFile = File(None)
):
    watermarked_content = await file.read()
    original_name = file.filename or "uploaded"
    ext = Path(original_name).suffix.lower()

    if ext not in [".png", ".jpg", ".jpeg", ".bmp"]:
        return JSONResponse(
            {"error": "Only images are supported"}, 
            status_code=400
        )

    nparr = np.frombuffer(watermarked_content, np.uint8)
    wm_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if wm_img is None:
        return JSONResponse(
            {"error": "Failed to decode watermarked image"}, 
            status_code=400
        )

    try:
        # Extract watermark bits from watermarked image
        bits = extract_watermark_image(
            wm_img, 
            payload_bits=DEFAULT_MAX_BITS, 
            quant=DEFAULT_QUANT, 
            seed=DEFAULT_SEED
        )
        extracted_signature = bits_to_bytes(bits)
        
        # Get original image content
        if original_file:
            original_content = await original_file.read()
            original_filename = original_file.filename
        else:
            return JSONResponse(
                {"error": "Original image is required for verification"}, 
                status_code=400
            )
        
        # Calculate hashes for debugging
        watermarked_hash = hashlib.sha256(watermarked_content).hexdigest()
        original_hash = hashlib.sha256(original_content).hexdigest()
        
        print(f"\n🔍 VERIFICATION DEBUG:")
        print(f"   Watermarked file: {original_name}")
        print(f"   Watermarked size: {len(watermarked_content)} bytes")
        print(f"   Watermarked SHA256: {watermarked_hash}")
        print(f"   Original file: {original_filename}")
        print(f"   Original size: {len(original_content)} bytes")
        print(f"   Original SHA256: {original_hash}")
        print(f"   Extracted signature: {extracted_signature.hex()}")
        print(f"   Public key: {public_key_hex.strip()}")
        print(f"   Using parameters: max_bits={DEFAULT_MAX_BITS}, quant={DEFAULT_QUANT}")
        
        # Verify signature against original content
        verified = verify_bytes_ed25519(
            public_key_hex.strip(), 
            original_content, 
            extracted_signature
        )
        
        print(f"   ✅ Verification result: {verified}\n")
        
        return {
            "verified": verified,
            "extracted_signature_hex": extracted_signature.hex(),
            "signature_length_bytes": len(extracted_signature),
            "original_hash": original_hash,
            "watermarked_hash": watermarked_hash,
            "debug_info": {
                "original_file": original_filename,
                "original_size": len(original_content),
                "watermarked_file": original_name,
                "watermarked_size": len(watermarked_content),
                "watermark_params_used": {
                    "max_bits": DEFAULT_MAX_BITS,
                    "quant": DEFAULT_QUANT
                }
            }
        }
        
    except Exception as e:
        import traceback
        print(f"❌ VERIFICATION ERROR: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            {"error": f"Verification failed: {str(e)}"}, 
            status_code=500
        )
    

@app.post("/watermark/video")
async def watermark_video(
    file: UploadFile = File(...),
    private_key_hex: str = Form(None),
    frame_stride: int = Form(10)
):
    """Watermark a video with digital signature"""
    content = await file.read()
    original_name = file.filename or "uploaded"
    ext = Path(original_name).suffix.lower()

    if ext not in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        return JSONResponse(
            {"error": "Only videos are supported (.mp4, .avi, .mov, .mkv, .webm)"}, 
            status_code=400
        )

    # Handle key generation/validation
    if private_key_hex and private_key_hex.strip():
        priv = private_key_hex.strip()
        try:
            from nacl.signing import SigningKey
            from nacl.encoding import HexEncoder
            sk = SigningKey(priv.encode(), encoder=HexEncoder)
            pub = sk.verify_key.encode(encoder=HexEncoder).decode()
        except Exception as e:
            return JSONResponse(
                {"error": f"Invalid private key: {str(e)}"}, 
                status_code=400
            )
    else:
        priv, pub = generate_keypair_hex()

    # Create signature from original video bytes
    signature = sign_bytes_ed25519(priv, content)
    
    print(f"🎬 VIDEO WATERMARKING DEBUG:")
    print(f"   Original filename: {original_name}")
    print(f"   Original size: {len(content)} bytes")
    print(f"   Signature: {signature.hex()}")
    print(f"   Public key: {pub}")
    print(f"   Frame stride: {frame_stride}")
    
    # Embed watermark in video
    try:
        watermarked_video_bytes = embed_watermark_video_bytes(
            content, 
            signature, 
            frames_stride=frame_stride,
            quant=DEFAULT_QUANT,
            seed=DEFAULT_SEED
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Video watermarking failed: {str(e)}"}, 
            status_code=500
        )

    # Save watermarked video
    out_name = STORAGE / f"watermarked_{Path(original_name).stem}.mp4"
    out_name.write_bytes(watermarked_video_bytes)
    
    # Save metadata
    metadata = {
        "original_filename": original_name,
        "public_key_hex": pub,
        "signature_hex": signature.hex(),
        "watermarked_filename": out_name.name,
        "watermark_params": {
            "max_bits": DEFAULT_MAX_BITS,
            "quant": DEFAULT_QUANT,
            "seed": DEFAULT_SEED,
            "frame_stride": frame_stride
        }
    }
    meta_path = STORAGE / f"watermarked_{Path(original_name).stem}.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return FileResponse(
        out_name,
        media_type="video/mp4",
        filename=f"watermarked_{Path(original_name).stem}.mp4"
    )


@app.post("/verify/video")
async def verify_video(
    file: UploadFile = File(...),
    public_key_hex: str = Form(...),
    original_file: UploadFile = File(...),
    frames_to_check: int = Form(5)
):
    """Verify watermark in a video"""
    watermarked_content = await file.read()
    original_content = await original_file.read()
    
    original_name = file.filename or "uploaded"
    original_filename = original_file.filename or "original"

    # Extract from multiple frames
    try:
        extracted_bits_list = extract_watermark_from_video_bytes(
            watermarked_content,
            frames_to_check=frames_to_check,
            payload_bits=DEFAULT_MAX_BITS,
            quant=DEFAULT_QUANT,
            seed=DEFAULT_SEED
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Video extraction failed: {str(e)}"}, 
            status_code=500
        )

    print(f"🎬 VIDEO VERIFICATION DEBUG:")
    print(f"   Watermarked file: {original_name}")
    print(f"   Original file: {original_filename}")
    print(f"   Frames to check: {frames_to_check}")
    print(f"   Frames processed: {len(extracted_bits_list)}")
    print(f"   Public key: {public_key_hex.strip()}")

    # Try each extracted signature from different frames
    public_key_hex = public_key_hex.strip()
    verified = False
    best_signature = None
    
    for i, bits in enumerate(extracted_bits_list):
        extracted_signature = bits_to_bytes(bits)
        if verify_bytes_ed25519(public_key_hex, original_content, extracted_signature):
            verified = True
            best_signature = extracted_signature
            print(f"   ✅ Frame {i+1}: Verification SUCCESS")
            break
        else:
            print(f"   ❌ Frame {i+1}: Verification failed")

    print(f"   🎯 Final verification result: {verified}")

    return {
        "verified": verified,
        "extracted_signature": best_signature.hex() if best_signature else None,
        "frames_checked": len(extracted_bits_list),
        "total_frames_processed": len(extracted_bits_list)
    }


@app.get("/")
def root():
    file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "frontend", 
        "index.html"
    )
    if not os.path.exists(file_path):
        file_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
        if not os.path.exists(file_path):
            return JSONResponse(
                {"error": f"Frontend not found at {file_path}"}, 
                status_code=404
            )
    # Add cache control headers to prevent caching
    response = FileResponse(file_path)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "TrueSight Watermarking API"}


@app.post("/debug_simple")
async def debug_simple(
    original_file: UploadFile = File(...),
    private_key_hex: str = Form(None)
):
    """Simple debug - watermark and verify without saving"""
    original_content = await original_file.read()
    
    # Use provided key or generate
    if private_key_hex:
        priv = private_key_hex
    else:
        priv, _ = generate_keypair_hex()
    
    # Create signature from original
    signature = sign_bytes_ed25519(priv, original_content)
    print(f"🔐 Original signature: {signature.hex()}")
    
    # Convert to image
    nparr = np.frombuffer(original_content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return JSONResponse({"error": "Failed to decode image"}, status_code=400)
    
    print(f"🔧 Using improved parameters: max_bits={DEFAULT_MAX_BITS}, quant={DEFAULT_QUANT}")
    
    # Embed watermark
    wm_img = embed_watermark_image(img, signature, DEFAULT_MAX_BITS, DEFAULT_QUANT, DEFAULT_SEED)
    
    # Immediately extract from the same image in memory
    bits = extract_watermark_image(wm_img, DEFAULT_MAX_BITS, DEFAULT_QUANT, DEFAULT_SEED)
    extracted = bits_to_bytes(bits)
    print(f"🔍 Extracted signature: {extracted.hex()}")
    
    # Compare
    match = signature == extracted
    print(f"✅ Signatures match: {match}")
    print(f"📏 Original length: {len(signature)}, Extracted: {len(extracted)}")
    
    return {
        "signatures_match": match,
        "original_length": len(signature),
        "extracted_length": len(extracted),
        "original_sig": signature.hex(),
        "extracted_sig": extracted.hex(),
        "parameters_used": {
            "max_bits": DEFAULT_MAX_BITS,
            "quant": DEFAULT_QUANT,
            "seed": DEFAULT_SEED
        }
    }


# -----------------------
# Deepfake Detection Endpoints
# -----------------------

@app.post("/detect/image")
async def detect_deepfake_image_endpoint(
    file: UploadFile = File(...)
):
    """Detect deepfakes in an image - Using Cloud API (90-95% accuracy)"""
    content = await file.read()
    original_name = file.filename or "uploaded"
    ext = Path(original_name).suffix.lower()

    if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
        return JSONResponse(
            {"error": "Only images are supported (.png, .jpg, .jpeg, .bmp, .tiff, .webp)"}, 
            status_code=400
        )

    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return JSONResponse(
            {"error": "Failed to decode image"}, 
            status_code=400
        )

    try:
        result = detect_deepfake_image(img)
        
        # Check if error occurred
        if "error" in result:
            return JSONResponse(
                {"error": result["error"]}, 
                status_code=500
            )
        
        # Encode heatmap overlay as base64 for response
        import base64
        success, buf = cv2.imencode('.png', result['heatmap_overlay'], [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if success:
            heatmap_base64 = base64.b64encode(buf.tobytes()).decode('utf-8')
        else:
            heatmap_base64 = None
        
        # Save analysis result
        analysis_path = STORAGE / f"deepfake_analysis_{Path(original_name).stem}.json"
        analysis_data = {
            "filename": original_name,
            "is_fake": result['is_fake'],
            "fake_probability": result['fake_probability'],
            "method": result.get('method', 'unknown'),
            "provider": result.get('provider', 'unknown'),
            "from_cache": result.get('from_cache', False),
            "processing_time": result.get('processing_time', 0)
        }
        analysis_path.write_text(json.dumps(analysis_data, indent=2))
        
        return {
            "is_fake": result['is_fake'],
            "fake_probability": result['fake_probability'],
            "probability_percentage": round(result['fake_probability'] * 100, 2),
            "confidence": result.get('confidence', result['fake_probability']),
            "method": result.get('method', 'unknown'),
            "provider": result.get('provider', 'Unknown'),
            "from_cache": result.get('from_cache', False),
            "processing_time": result.get('processing_time', 0),
            "heatmap_overlay_base64": heatmap_base64,
            "warning": result.get('warning', None)

        }
        
    except Exception as e:
        import traceback
        print(f"❌ DEEPFAKE DETECTION ERROR: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            {"error": f"Deepfake detection failed: {str(e)}"}, 
            status_code=500
        )


@app.post("/detect/video")
async def detect_deepfake_video_endpoint(
    file: UploadFile = File(...),
    frames_to_check: int = Form(5)
):
    """Detect deepfakes in a video - Using Cloud API (90-95% accuracy)"""
    content = await file.read()
    original_name = file.filename or "uploaded"
    ext = Path(original_name).suffix.lower()

    if ext not in [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"]:
        return JSONResponse(
            {"error": "Only videos are supported (.mp4, .avi, .mov, .mkv, .webm, .flv)"}, 
            status_code=400
        )

    try:
        result = detect_deepfake_video_bytes(content, frames_to_check=frames_to_check)
        
        # Check if error occurred
        if "error" in result:
            return JSONResponse(
                {"error": result["error"]}, 
                status_code=500
            )
        
        # Save analysis result
        analysis_path = STORAGE / f"deepfake_analysis_{Path(original_name).stem}.json"
        analysis_data = {
            "filename": original_name,
            "is_fake": result['is_fake'],
            "fake_probability": result['fake_probability'],
            "overall_confidence": result.get('overall_confidence', 0.0),
            "frames_analyzed": result.get('frames_analyzed', 0),
            "frame_results": result.get('frame_results', [])
        }
        analysis_path.write_text(json.dumps(analysis_data, indent=2))
        
        return {
            "is_fake": result['is_fake'],
            "fake_probability": result['fake_probability'],
            "probability_percentage": round(result['fake_probability'] * 100, 2),
            "overall_confidence": result.get('overall_confidence', 0.0),
            "frames_analyzed": result.get('frames_analyzed', 0),
            "frame_results": [
                {
                    "frame_number": fr['frame_number'],
                    "fake_probability": fr['fake_probability'],
                    "probability_percentage": round(fr['fake_probability'] * 100, 2),
                    "is_fake": fr['is_fake'],
                    "method": fr.get('method', 'unknown')
                }
                for fr in result.get('frame_results', [])
            ]
        }
        
    except Exception as e:
        import traceback
        print(f"❌ DEEPFAKE VIDEO DETECTION ERROR: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            {"error": f"Deepfake video detection failed: {str(e)}"}, 
            status_code=500
        )

@app.post("/debug/watermark-heatmap-download")
async def debug_watermark_heatmap_download(
    original_file: UploadFile = File(...),
    watermarked_file: UploadFile = File(...),
    heatmap_type: str = Form("difference")
):
    """
    Download heatmap images directly
    heatmap_type: "original", "watermarked", "difference", "comparison"
    """
    try:
        original_content = await original_file.read()
        watermarked_content = await watermarked_file.read()
        
        original_img = cv2.imdecode(np.frombuffer(original_content, np.uint8), cv2.IMREAD_COLOR)
        watermarked_img = cv2.imdecode(np.frombuffer(watermarked_content, np.uint8), cv2.IMREAD_COLOR)
        
        if original_img is None or watermarked_img is None:
            return JSONResponse({"error": "Failed to decode images"}, status_code=400)
        
        # Generate the requested heatmap
        if heatmap_type == "difference":
            result_img = _create_difference_heatmap_cv2(original_img, watermarked_img)
            filename = "watermark_difference_map.png"
        elif heatmap_type == "original":
            result_img = _create_frequency_heatmap_cv2(original_img, "Original")
            filename = "original_frequency_heatmap.png"
        elif heatmap_type == "watermarked":
            result_img = _create_frequency_heatmap_cv2(watermarked_img, "Watermarked")
            filename = "watermarked_frequency_heatmap.png"
        elif heatmap_type == "comparison":
            result_img = _create_comparison_image(original_img, watermarked_img)
            filename = "watermark_comparison.png"
        else:
            return JSONResponse({"error": "Invalid heatmap type"}, status_code=400)
        
        # Save to temp file and return
        temp_path = STORAGE / f"heatmap_{filename}"
        cv2.imwrite(str(temp_path), result_img)
        
        return FileResponse(
            temp_path,
            media_type="image/png",
            filename=filename
        )
        
    except Exception as e:
        return JSONResponse({"error": f"Heatmap generation failed: {str(e)}"}, status_code=500)

def _create_difference_heatmap_cv2(original, watermarked):
    """Create difference heatmap using OpenCV colormaps"""
    original_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    watermarked_gray = cv2.cvtColor(watermarked, cv2.COLOR_BGR2GRAY)
    
    diff = cv2.absdiff(original_gray, watermarked_gray)
    diff_enhanced = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
    diff_colored = cv2.applyColorMap(diff_enhanced, cv2.COLORMAP_JET)
    
    # Add title
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(diff_colored, "Watermark Difference Map", (10, 30), font, 1, (255, 255, 255), 2)
    
    return diff_colored

def _create_frequency_heatmap_cv2(image, title):
    """Create frequency domain heatmap using OpenCV"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply DFT
    dft = cv2.dft(np.float32(gray), flags=cv2.DFT_COMPLEX_OUTPUT)
    dft_shift = np.fft.fftshift(dft)
    magnitude_spectrum = 20 * np.log(cv2.magnitude(dft_shift[:,:,0], dft_shift[:,:,1]) + 1)
    
    # Normalize and apply colormap
    magnitude_normalized = cv2.normalize(magnitude_spectrum, None, 0, 255, cv2.NORM_MINMAX)
    magnitude_colored = cv2.applyColorMap(np.uint8(magnitude_normalized), cv2.COLORMAP_HOT)
    
    # Add title
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(magnitude_colored, f"Frequency Map - {title}", (10, 30), font, 0.7, (255, 255, 255), 2)
    
    return magnitude_colored

def _create_comparison_image(original, watermarked):
    """Create side-by-side comparison with difference map"""
    original_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    watermarked_gray = cv2.cvtColor(watermarked, cv2.COLOR_BGR2GRAY)
    
    diff = cv2.absdiff(original_gray, watermarked_gray)
    diff_enhanced = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)
    diff_colored = cv2.applyColorMap(diff_enhanced, cv2.COLORMAP_JET)
    
    # Resize all images to same height for comparison
    height = max(original.shape[0], watermarked.shape[0], diff_colored.shape[0])
    
    original_resized = cv2.resize(original, (300, height))
    watermarked_resized = cv2.resize(watermarked, (300, height))
    diff_resized = cv2.resize(diff_colored, (300, height))
    
    # Create comparison image
    comparison = np.hstack([original_resized, watermarked_resized, diff_resized])
    
    # Add labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(comparison, "Original", (10, 30), font, 1, (255, 255, 255), 2)
    cv2.putText(comparison, "Watermarked", (310, 30), font, 1, (255, 255, 255), 2)
    cv2.putText(comparison, "Difference", (610, 30), font, 1, (255, 255, 255), 2)
    
    return comparison




if __name__ == "_main_":
    print("🚀 Starting TrueSight Watermarking Service...")
    print("📝 API docs available at: http://localhost:8000/docs")
    print("🌐 Web interface at: http://localhost:8000/")
    print("🔧 Watermark parameters:")
    print(f"   - MAX_BITS: {DEFAULT_MAX_BITS}")
    print(f"   - QUANT: {DEFAULT_QUANT}")
    print("\n🔍 Deepfake Detection: Cloud API (90-95% accuracy)")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)