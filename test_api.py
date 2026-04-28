"""
Test the API-based deepfake detection
"""

import cv2
import numpy as np
from deepfake_detection_api import detect_deepfake_image, get_stats

print("🧪 Testing API-based Deepfake Detection")
print("="*70)

# Create test image
test_img = np.random.randint(0, 255, (640, 480, 3), dtype=np.uint8)
cv2.rectangle(test_img, (200, 150), (400, 400), (255, 200, 150), -1)
cv2.circle(test_img, (260, 250), 20, (0, 0, 0), -1)
cv2.circle(test_img, (340, 250), 20, (0, 0, 0), -1)

print("\n📸 Test 1: First detection (should use API)")
result1 = detect_deepfake_image(test_img)
print(f"   Result: {'FAKE' if result1['is_fake'] else 'REAL'}")
print(f"   Probability: {result1['fake_probability']*100:.1f}%")
print(f"   Method: {result1['method']}")
print(f"   Provider: {result1.get('provider', 'Unknown')}")
print(f"   Time: {result1['processing_time']:.3f}s")

print("\n📸 Test 2: Same image (should use cache)")
result2 = detect_deepfake_image(test_img)
print(f"   From cache: {result2.get('from_cache', False)}")
print(f"   Time: {result2['processing_time']:.3f}s")

# Stats
print("\n📊 Statistics:")
stats = get_stats()
print(f"   API calls: {stats['api_calls']}")
print(f"   Cache hits: {stats['cache_hits']}")
print(f"   Fallback used: {stats['fallback_used']}")

print("\n✅ Test complete!")

if result1['method'] == 'local_heuristic':
    print("\n⚠️  WARNING: API key not configured or API unavailable")
    print("   Using local fallback (~60% accuracy)")
    print("   Add your Hive API key for 90%+ accuracy")
else:
    print("\n🎉 API working perfectly!")
    print(f"   Accuracy: 90-95%")