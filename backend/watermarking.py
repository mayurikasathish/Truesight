# backend/watermarking.py
# Provides: key generation, sign/verify using Ed25519 (PyNaCl),
# simple DWT-QIM embed/extract for images, basic video support (embed into frames).

import io
import os
import hashlib
import tempfile
from typing import Tuple, List

import numpy as np
import cv2
import pywt
import ffmpeg

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder

# -----------------------
# Cryptographic helpers
# -----------------------

def generate_keypair_hex() -> Tuple[str, str]:
    sk = SigningKey.generate()
    vk = sk.verify_key
    sk_hex = sk.encode(encoder=HexEncoder).decode()
    vk_hex = vk.encode(encoder=HexEncoder).decode()
    return sk_hex, vk_hex

def sign_bytes_ed25519(private_hex: str, data: bytes) -> bytes:
    sk = SigningKey(private_hex.encode(), encoder=HexEncoder)
    digest = hashlib.sha256(data).digest()
    signature = sk.sign(digest).signature
    return signature

def verify_bytes_ed25519(public_hex: str, data: bytes, signature: bytes) -> bool:
    vk = VerifyKey(public_hex.encode(), encoder=HexEncoder)
    digest = hashlib.sha256(data).digest()
    try:
        vk.verify(digest, signature)
        return True
    except Exception:
        return False

# -----------------------
# Image watermarking (DWT + QIM simple)
# -----------------------
# We embed a small payload (signature truncated or hashed) as bits into mid-frequency coefficients.

def _img_to_gray_float(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return gray.astype('float32') / 255.0

def _float_to_uint8(imgf: np.ndarray) -> np.ndarray:
    return np.clip(imgf * 255.0, 0, 255).astype('uint8')

def signature_to_bitlist(sig: bytes, max_bits: int) -> List[int]:
    # Convert bytes -> bits and trim or pad to max_bits
    bits = []
    for b in sig:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
            if len(bits) >= max_bits:
                return bits
    # pad with zeros if needed
    while len(bits) < max_bits:
        bits.append(0)
    return bits

def bits_to_bytes(bits: List[int]) -> bytes:
    # convert bit list to bytes (multiple of 8)
    n = (len(bits) // 8) * 8
    bits = bits[:n]
    out = bytearray()
    for i in range(0, n, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)

def embed_watermark_image(img_bgr: np.ndarray, payload: bytes, max_bits=256, quant=32.0, seed=42) -> np.ndarray:
    """
    Embed payload into image using DWT on the luminance channel (Y of YCrCb).
    Keeps original color instead of turning grayscale.
    """
    # Convert to YCrCb and split channels
    img_ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(img_ycrcb)

    # Convert Y (luminance) to float for processing - PRESERVE original range
    y_float = y.astype(np.float32)

    # DWT on Y channel
    coeffs2 = pywt.dwt2(y_float, 'haar')
    LL, (LH, HL, HH) = coeffs2

    band = LH.copy()
    flat = band.flatten()
    total = flat.size

    bits = signature_to_bitlist(payload, max_bits)
    nbits = len(bits)

    if nbits > total:
        raise ValueError(f"payload too big for image/selected capacity: {nbits} > {total}")

    rng = np.random.RandomState(seed)
    indices = rng.choice(total, size=nbits, replace=False)

    for i, bit in enumerate(bits):
        idx = indices[i]
        coeff = flat[idx]
        q = quant
        base = q * np.round(coeff / q)
        flat[idx] = base + (q / 4.0 if bit == 1 else -q / 4.0)

    band_mod = flat.reshape(band.shape)
    coeffs2_mod = (LL, (band_mod, HL, HH))

    # Inverse DWT to reconstruct Y - NO CLIPPING to preserve dynamic range
    y_mod = pywt.idwt2(coeffs2_mod, 'haar')
    
    # Convert back to uint8 without losing range
    y_mod_uint8 = np.clip(y_mod, 0, 255).astype(np.uint8)

    # Merge modified Y with original Cr and Cb
    img_ycrcb_mod = cv2.merge([y_mod_uint8, cr, cb])
    img_bgr_mod = cv2.cvtColor(img_ycrcb_mod, cv2.COLOR_YCrCb2BGR)

    return img_bgr_mod

def extract_watermark_image(img_bgr: np.ndarray, payload_bits=256, quant=32.0, seed=42) -> List[int]:
    """
    Improved extraction with more robust QIM decoding
    """
    # Use same YCrCb processing as embedding (NOT grayscale)
    img_ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y, _, _ = cv2.split(img_ycrcb)
    
    # Convert Y to float same as embedding
    y_float = y.astype(np.float32)
    
    # DWT on Y channel same as embedding
    coeffs2 = pywt.dwt2(y_float, 'haar')
    _, (LH, HL, HH) = coeffs2
    
    # Use same band as embedding (LH)
    flat = LH.flatten()
    total = flat.size
    
    if payload_bits > total:
        raise ValueError(f"requested bits exceed capacity: {payload_bits} > {total}")
    
    rng = np.random.RandomState(seed)
    indices = rng.choice(total, size=payload_bits, replace=False)
    bits = []
    q = quant
    
    for idx in indices:
        coeff = flat[idx]
        
        # Same QIM extraction as embedding
        base = np.round(coeff / q) * q
        distance_to_upper = abs(coeff - (base + q/4.0))
        distance_to_lower = abs(coeff - (base - q/4.0))
        
        if distance_to_upper < distance_to_lower:
            bits.append(1)
        else:
            bits.append(0)
    
    return bits



def embed_watermark_video_bytes(input_bytes: bytes, payload: bytes, frames_stride=10, quant=32.0, seed=42) -> bytes:
    """
    input_bytes: raw video bytes
    returns: new video bytes with watermark embedded into frames
    """
    print(f"🎬 Starting video watermarking: {len(input_bytes)} bytes, frame stride: {frames_stride}")
    
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.mp4")
        out_path = os.path.join(tmp, "out.mp4")
        with open(in_path, "wb") as f:
            f.write(input_bytes)

        # Extract frames
        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        
        try:
            # Get video info
            probe = ffmpeg.probe(in_path)
            video_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
            original_framerate = eval(video_info['avg_frame_rate'])
            print(f"📊 Video info: {video_info['width']}x{video_info['height']}, {original_framerate} fps")
        except Exception as e:
            original_framerate = 25
            print(f"⚠️ Using default framerate 25 (probe failed: {e})")

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
            raise
        
        frames = sorted([p for p in os.listdir(frames_dir) if p.endswith('.png')])
        print(f"📊 Extracted {len(frames)} frames")
        
        watermarked_count = 0
        for i, fname in enumerate(frames):
            path = os.path.join(frames_dir, fname)
            img = cv2.imread(path)
            if img is not None and i % frames_stride == 0:
                # Use 512 bits to match images
                img_w = embed_watermark_image(img, payload, max_bits=512, quant=quant, seed=seed)
                cv2.imwrite(path, img_w)
                watermarked_count += 1
        
        print(f"🔒 Watermarked {watermarked_count} frames (every {frames_stride} frames)")
        
        if watermarked_count == 0:
            raise ValueError("No frames were watermarked. Check frame_stride and video length.")
        
        # Reassemble
        try:
            (
                ffmpeg
                .input(os.path.join(frames_dir, "frame_%05d.png"), framerate=original_framerate)
                .output(out_path, vcodec='libx264',crf=0, preset='ultrafast')
                .overwrite_output()
                .run(quiet=True, capture_stderr=True)
            )
        except Exception as e:
            print(f"❌ Video reassembly failed: {e}")
            raise
        
        with open(out_path, "rb") as f:
            out_bytes = f.read()
            
        print(f"✅ Video reassembled: {len(out_bytes)} bytes")
    return out_bytes

def extract_watermark_from_video_bytes(video_bytes: bytes, frames_to_check=5, payload_bits=256, quant=32.0, seed=42) -> List[List[int]]:
    """
    Extract watermark bits from a small sample of frames (first N frames spaced evenly).
    Returns list of bit-lists for sampled frames.
    """
    print(f"🎬 Starting video extraction: {len(video_bytes)} bytes, checking {frames_to_check} frames")
    
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
            return []
        
        frames = sorted([p for p in os.listdir(frames_dir) if p.endswith('.png')])
        if len(frames) == 0:
            print("❌ No frames extracted from video")
            return []
        
        print(f"📊 Extracted {len(frames)} frames")
            
        # Check first N frames
        frames_to_process = min(frames_to_check, len(frames))
        results = []
        successful_extractions = 0
        
        for i in range(frames_to_process):
            path = os.path.join(frames_dir, frames[i])
            img = cv2.imread(path)
            if img is not None:
                try:
                    bits = extract_watermark_image(img, payload_bits, quant=quant, seed=seed)
                    if len(bits) == payload_bits:  # Only count successful extractions
                        results.append(bits)
                        successful_extractions += 1
                        print(f"   ✅ Frame {i+1}: Successfully extracted {len(bits)} bits")
                    else:
                        print(f"   ⚠️ Frame {i+1}: Got {len(bits)} bits, expected {payload_bits}")
                except Exception as e:
                    print(f"   ❌ Frame {i+1}: Extraction failed - {e}")
            else:
                print(f"   ❌ Frame {i+1}: Could not read image")
        
        print(f"🔍 Successfully extracted from {successful_extractions}/{frames_to_process} frames")
        return results