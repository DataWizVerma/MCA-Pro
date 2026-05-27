"""
image_utils.py
--------------
Project : Digital Image Forensics System for Tampering Detection
College : Chandigarh University
Author  : Kumar Verma
Purpose : Supplementary image forensics utilities.
          Provides cryptographic hashing, JPEG quantization analysis, and a
          lightweight copy-move forgery detection hint using block matching.
"""

import hashlib
import struct
import io
import os
import cv2
import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# 1. CRYPTOGRAPHIC HASH COMPUTATION
# ---------------------------------------------------------------------------

def compute_image_hash(image_path: str) -> dict:
    """
    Compute MD5 and SHA-256 cryptographic hashes of the raw image file bytes.

    These hashes serve as a digital fingerprint of the file.  If even a single
    pixel is altered, both hashes will completely change — making them useful
    for verifying that a file has not been modified after an initial scan.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    hashes : dict – {'md5': str, 'sha256': str, 'file_size_kb': float}
    """
    md5    = hashlib.md5()
    sha256 = hashlib.sha256()

    with open(image_path, "rb") as f:
        data = f.read()

    md5.update(data)
    sha256.update(data)

    return {
        "md5":          md5.hexdigest(),
        "sha256":       sha256.hexdigest(),
        "file_size_kb": round(len(data) / 1024, 2),
    }


# ---------------------------------------------------------------------------
# 2. JPEG DOUBLE-COMPRESSION DETECTION
# ---------------------------------------------------------------------------

def detect_double_compression(image_path: str) -> dict:
    """
    Attempt to detect double JPEG compression by reading the quantization
    tables stored in the JPEG file header.

    When an image is edited in software (e.g., Photoshop) and re-saved as
    JPEG, it goes through a second compression pass.  This can leave forensic
    artefacts detectable through quantization table analysis.

    Parameters
    ----------
    image_path : str – path to the JPEG image file.

    Returns
    -------
    result : dict – {
        'has_quantization_tables': bool,
        'num_tables': int,
        'avg_quantization_value': float,
        'suspicion_level': str  ('Low' | 'Medium' | 'High'),
        'explanation': str
    }
    """
    try:
        img = Image.open(image_path)
        qt  = img.quantization   # dict of table_id → list of 64 values

        if not qt:
            return {
                "has_quantization_tables": False,
                "num_tables":              0,
                "avg_quantization_value":  0.0,
                "suspicion_level":         "Unknown",
                "explanation": "No quantization tables found. File may not be JPEG.",
            }

        all_values = []
        for table in qt.values():
            all_values.extend(table)

        avg_q = round(float(np.mean(all_values)), 2)

        # Heuristic: very low average quantization value (< 5) is typical of
        # high-quality originals.  Moderate values (5-15) can indicate
        # re-saving.  High values (> 15) suggest heavy re-compression.
        if avg_q < 5:
            level = "Low"
            explanation = (
                "Quantization values are very low, consistent with a high-quality "
                "original JPEG with minimal compression history."
            )
        elif avg_q < 15:
            level = "Medium"
            explanation = (
                "Moderate quantization values detected.  The image may have been "
                "re-saved or converted, which is common in edited photographs."
            )
        else:
            level = "High"
            explanation = (
                "High quantization values detected.  The image shows signs of "
                "significant re-compression, which may indicate editing and re-saving."
            )

        return {
            "has_quantization_tables": True,
            "num_tables":              len(qt),
            "avg_quantization_value":  avg_q,
            "suspicion_level":         level,
            "explanation":             explanation,
        }

    except Exception as e:
        return {
            "has_quantization_tables": False,
            "num_tables":              0,
            "avg_quantization_value":  0.0,
            "suspicion_level":         "Unknown",
            "explanation": f"Could not analyse JPEG tables: {str(e)}",
        }


# ---------------------------------------------------------------------------
# 3. COPY-MOVE FORGERY DETECTION (lightweight block-matching)
# ---------------------------------------------------------------------------

def check_copy_move(image_path: str, block_size: int = 32) -> dict:
    """
    Perform a lightweight copy-move forgery detection using block-based
    feature matching.

    Copy-move forgery involves copying a region from within the same image and
    pasting it elsewhere to hide or duplicate content.  This function splits the
    image into non-overlapping blocks, computes a simple hash for each block,
    and counts blocks whose hashes appear more than once (potential duplicates).

    Note: This is an approximate / heuristic method.  It works well for
    low-complexity uniform regions but may produce false positives in images
    with repetitive patterns (e.g., sky, grass).

    Parameters
    ----------
    image_path : str – path to the image file.
    block_size : int – size (pixels) of each square block (default 32).

    Returns
    -------
    result : dict – {
        'total_blocks': int,
        'duplicate_blocks': int,
        'duplication_ratio': float,
        'copy_move_suspected': bool,
        'explanation': str
    }
    """
    try:
        # Load image in grayscale and resize to a standard working resolution
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("Cannot read image.")

        # Downsample large images for performance
        max_dim = 512
        h, w = img.shape
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape

        block_hashes = {}
        total_blocks = 0

        # Slide non-overlapping blocks across the image
        for y in range(0, h - block_size, block_size):
            for x in range(0, w - block_size, block_size):
                block = img[y:y + block_size, x:x + block_size]
                if block.shape != (block_size, block_size):
                    continue
                # Use MD5 of the raw block bytes as a fast hash
                block_hash = hashlib.md5(block.tobytes()).hexdigest()
                block_hashes[block_hash] = block_hashes.get(block_hash, 0) + 1
                total_blocks += 1

        # Count blocks whose hash appears more than once
        duplicate_blocks = sum(1 for cnt in block_hashes.values() if cnt > 1)
        ratio = round(duplicate_blocks / total_blocks, 4) if total_blocks > 0 else 0.0

        # A ratio above 15% is considered suspicious for copy-move artefacts
        suspected = ratio > 0.15

        if suspected:
            explanation = (
                f"{duplicate_blocks} out of {total_blocks} image blocks "
                f"({ratio * 100:.1f}%) appear duplicated, which is a potential "
                "indicator of copy-move forgery."
            )
        else:
            explanation = (
                f"Only {duplicate_blocks} out of {total_blocks} blocks "
                f"({ratio * 100:.1f}%) appear duplicated.  "
                "No significant copy-move artefacts detected."
            )

        return {
            "total_blocks":        total_blocks,
            "duplicate_blocks":    duplicate_blocks,
            "duplication_ratio":   ratio,
            "copy_move_suspected": suspected,
            "explanation":         explanation,
        }

    except Exception as e:
        return {
            "total_blocks":        0,
            "duplicate_blocks":    0,
            "duplication_ratio":   0.0,
            "copy_move_suspected": False,
            "explanation": f"Copy-move analysis failed: {str(e)}",
        }


# ---------------------------------------------------------------------------
# 4. IMAGE QUALITY / DIMENSION INFO
# ---------------------------------------------------------------------------

def get_image_info(image_path: str) -> dict:
    """
    Return basic image properties: dimensions, colour mode, format, and file size.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    info : dict – image properties dictionary.
    """
    try:
        img  = Image.open(image_path)
        size = os.path.getsize(image_path)
        return {
            "width":      img.width,
            "height":     img.height,
            "mode":       img.mode,
            "format":     img.format or "JPEG",
            "file_size":  f"{round(size / 1024, 1)} KB",
            "megapixels": round((img.width * img.height) / 1_000_000, 2),
        }
    except Exception as e:
        return {"error": str(e)}
