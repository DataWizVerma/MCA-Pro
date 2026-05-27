"""
helper.py
---------
Project : Digital Image Forensics System for Tampering Detection
College : Chandigarh University
Author  : Kumar Verma
Purpose : Core image-processing utilities used by the main Streamlit application.
          Includes ELA generation, heatmap overlay, EXIF extraction, and noise analysis.
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter
import piexif
import io


# ---------------------------------------------------------------------------
# 1. ERROR LEVEL ANALYSIS (ELA)
# ---------------------------------------------------------------------------

def convert_to_ela_image(path: str, quality: int = 90) -> Image.Image:
    """
    Generate an Error Level Analysis (ELA) image from a JPEG file.

    ELA works by re-saving the original image at a known JPEG quality level,
    then computing the absolute pixel difference between the original and the
    re-saved version.  Regions that were inserted from another source (i.e.,
    tampered areas) typically show a different error level than untouched parts
    because they were compressed a different number of times.

    Parameters
    ----------
    path    : str  – absolute or relative path to the source image file.
    quality : int  – JPEG re-save quality (default 90).  Lower values amplify
                     differences further; 90 is the empirically optimal value
                     for CASIA-trained models.

    Returns
    -------
    ela_image : PIL.Image  – brightness-scaled ELA image (RGB mode).
    """
    temp_filename = "temp_file_name.jpg"

    # Open the original image and convert to RGB (handles PNG / RGBA cases)
    original = Image.open(path).convert("RGB")

    # Re-save at the specified quality to introduce fresh compression artifacts
    original.save(temp_filename, "JPEG", quality=quality)
    recompressed = Image.open(temp_filename)

    # Pixel-wise absolute difference between original and re-compressed image
    ela_image = ImageChops.difference(original, recompressed)

    # Scale the brightness so that the maximum difference maps to 255
    extrema = ela_image.getextrema()          # returns ((min,max),(min,max),(min,max)) per channel
    max_diff = sum([ex[1] for ex in extrema]) / 3   # average max across channels
    if max_diff == 0:
        max_diff = 1   # avoid division by zero for perfectly uniform images

    scale = 255.0 / max_diff
    ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

    return ela_image


def prepare_image_for_ela(image_path: str):
    """
    Prepare a numpy array suitable for the ELA-DenseNet121 model and also
    return the raw ELA PIL image for display purposes.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    model_input : np.ndarray – shape (1, 128, 128, 3), float32 in [0, 1].
    ela_img     : PIL.Image  – the raw ELA image for visualisation.
    """
    ela_img = convert_to_ela_image(image_path, quality=90)

    # Resize to 128×128 as required by the DenseNet121 model
    arr = np.array(ela_img.resize((128, 128))).flatten() / 255.0
    arr = arr.reshape(128, 128, 3).astype(np.float32)

    return np.expand_dims(arr, axis=0), ela_img


# ---------------------------------------------------------------------------
# 2. ELA HEATMAP OVERLAY
# ---------------------------------------------------------------------------

def get_ela_heatmap(original_path: str) -> Image.Image:
    """
    Create a colour-heatmap overlay by blending the ELA result with the
    original image.  Brighter (hotter) regions indicate higher error levels
    and potential tampering.

    Parameters
    ----------
    original_path : str – path to the original image.

    Returns
    -------
    blended : PIL.Image – heatmap overlay image (RGB).
    """
    ela_img = convert_to_ela_image(original_path, quality=90)

    # Convert ELA to grayscale → apply OpenCV colour map (JET palette)
    ela_gray = np.array(ela_img.convert("L"))
    heatmap_bgr = cv2.applyColorMap(ela_gray, cv2.COLORMAP_JET)
    heatmap_rgb = cv2.cvtColor(heatmap_bgr, cv2.COLOR_BGR2RGB)
    heatmap_pil = Image.fromarray(heatmap_rgb)

    # Resize both images to the same size for blending
    original = Image.open(original_path).convert("RGB")
    heatmap_pil = heatmap_pil.resize(original.size)

    # Blend: 55% original + 45% heatmap for a clear but non-obtrusive overlay
    blended = Image.blend(original, heatmap_pil, alpha=0.45)
    return blended


# ---------------------------------------------------------------------------
# 3. MULTI-QUALITY ELA (robustness check)
# ---------------------------------------------------------------------------

def multi_quality_ela(image_path: str) -> dict:
    """
    Run ELA at three different compression quality levels (70, 80, 90) and
    compute the mean error level for each.  Consistent high error at multiple
    levels is a stronger signal of tampering.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    results : dict – {'q70': float, 'q80': float, 'q90': float}
              Each value is the mean pixel intensity of the ELA image (0-255).
    """
    results = {}
    for q in [70, 80, 90]:
        ela = convert_to_ela_image(image_path, quality=q)
        mean_val = float(np.array(ela).mean())
        results[f"q{q}"] = round(mean_val, 3)
    return results


# ---------------------------------------------------------------------------
# 4. WEATHER CNN IMAGE PREPARATION
# ---------------------------------------------------------------------------

def prerpare_img_for_weather(image_path: str) -> np.ndarray:
    """
    Prepare a numpy array suitable for the Weather CNN model.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    model_input : np.ndarray – shape (1, 128, 128, 3), float32 in [0, 1].
    """
    img = np.array(
        Image.open(image_path).convert("RGB").resize((128, 128))
    ) / 255.0
    img = img.reshape(128, 128, 3).astype(np.float32)
    return np.expand_dims(img, axis=0)


# ---------------------------------------------------------------------------
# 5. EXIF METADATA EXTRACTION
# ---------------------------------------------------------------------------

def extract_exif_data(image_path: str) -> dict:
    """
    Extract ALL readable EXIF metadata from a JPEG image and return it as a
    clean, human-readable dictionary.  Uses the piexif library for reliable
    tag parsing.

    Parameters
    ----------
    image_path : str – path to the JPEG image file.

    Returns
    -------
    exif_dict : dict – flat dictionary of tag_name → value strings.
                       Returns an empty dict if no EXIF data is found.
    """
    result = {}
    try:
        img = Image.open(image_path)
        raw_exif = img.info.get("exif", None)
        if raw_exif is None:
            return result

        exif_data = piexif.load(raw_exif)

        # Human-readable tag name mapping
        tag_map = {
            piexif.ImageIFD.Make:             "Camera Make",
            piexif.ImageIFD.Model:            "Camera Model",
            piexif.ImageIFD.Software:         "Software",
            piexif.ImageIFD.DateTime:         "Date & Time",
            piexif.ImageIFD.Artist:           "Artist",
            piexif.ImageIFD.Copyright:        "Copyright",
            piexif.ImageIFD.XResolution:      "X Resolution",
            piexif.ImageIFD.YResolution:      "Y Resolution",
            piexif.ImageIFD.ResolutionUnit:   "Resolution Unit",
        }
        exif_tag_map = {
            piexif.ExifIFD.ExposureTime:      "Exposure Time",
            piexif.ExifIFD.FNumber:           "F-Number (Aperture)",
            piexif.ExifIFD.ISOSpeedRatings:   "ISO Speed",
            piexif.ExifIFD.DateTimeOriginal:  "Date Taken (Original)",
            piexif.ExifIFD.DateTimeDigitized: "Date Digitized",
            piexif.ExifIFD.ShutterSpeedValue: "Shutter Speed",
            piexif.ExifIFD.ApertureValue:     "Aperture Value",
            piexif.ExifIFD.Flash:             "Flash",
            piexif.ExifIFD.FocalLength:       "Focal Length",
            piexif.ExifIFD.ColorSpace:        "Colour Space",
            piexif.ExifIFD.PixelXDimension:   "Image Width (px)",
            piexif.ExifIFD.PixelYDimension:   "Image Height (px)",
        }
        gps_tag_map = {
            piexif.GPSIFD.GPSLatitudeRef:     "GPS Latitude Ref",
            piexif.GPSIFD.GPSLatitude:        "GPS Latitude",
            piexif.GPSIFD.GPSLongitudeRef:    "GPS Longitude Ref",
            piexif.GPSIFD.GPSLongitude:       "GPS Longitude",
            piexif.GPSIFD.GPSAltitudeRef:     "GPS Altitude Ref",
            piexif.GPSIFD.GPSAltitude:        "GPS Altitude",
            piexif.GPSIFD.GPSDateStamp:       "GPS Date Stamp",
        }

        def _decode(val):
            """Decode bytes to string; convert rationals to float strings."""
            if isinstance(val, bytes):
                return val.decode("utf-8", errors="ignore").strip("\x00")
            if isinstance(val, tuple) and len(val) == 2 and val[1] != 0:
                return str(round(val[0] / val[1], 4))
            if isinstance(val, tuple):
                # Could be a GPS rational tuple-of-tuples
                parts = []
                for item in val:
                    if isinstance(item, tuple) and len(item) == 2 and item[1] != 0:
                        parts.append(str(round(item[0] / item[1], 6)))
                    else:
                        parts.append(str(item))
                return " / ".join(parts)
            return str(val)

        # Parse Image IFD
        for tag, name in tag_map.items():
            if tag in exif_data.get("0th", {}):
                result[name] = _decode(exif_data["0th"][tag])

        # Parse Exif IFD
        for tag, name in exif_tag_map.items():
            if tag in exif_data.get("Exif", {}):
                result[name] = _decode(exif_data["Exif"][tag])

        # Parse GPS IFD
        for tag, name in gps_tag_map.items():
            if tag in exif_data.get("GPS", {}):
                result[name] = _decode(exif_data["GPS"][tag])

    except Exception:
        # If EXIF parsing fails for any reason, return whatever was collected
        pass

    return result


# ---------------------------------------------------------------------------
# 6. NOISE ANALYSIS (additional forgery hint)
# ---------------------------------------------------------------------------

def compute_noise_analysis(image_path: str) -> dict:
    """
    Estimate local noise variance across different image regions.
    Tampered regions often have significantly different noise levels compared
    to the rest of the image because they originated from a different source.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    noise_info : dict – contains 'mean_noise', 'std_noise', 'max_noise',
                        'tamper_hint' (bool), and 'regions' (list of region
                        noise values for a 3×3 grid).
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"error": "Could not read image for noise analysis."}

    h, w = img.shape
    region_noise = []

    # Divide image into a 3×3 grid and compute local noise for each block
    rows, cols = 3, 3
    rh, rw = h // rows, w // cols

    for r in range(rows):
        for c in range(cols):
            block = img[r * rh:(r + 1) * rh, c * rw:(c + 1) * rw]
            # Laplacian variance is a good measure of local noise/sharpness
            lap_var = cv2.Laplacian(block, cv2.CV_64F).var()
            region_noise.append(round(lap_var, 2))

    mean_noise = float(np.mean(region_noise))
    std_noise  = float(np.std(region_noise))

    # A high standard deviation means noise is inconsistent across regions,
    # which is a potential indicator of splicing / copy-move tampering.
    tamper_hint = std_noise > (mean_noise * 0.5)

    return {
        "mean_noise": round(mean_noise, 3),
        "std_noise":  round(std_noise, 3),
        "max_noise":  round(float(np.max(region_noise)), 3),
        "tamper_hint": tamper_hint,
        "regions":    region_noise,
    }
