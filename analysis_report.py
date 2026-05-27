"""
analysis_report.py
------------------
Project : Digital Image Forensics System for Tampering Detection
College : Chandigarh University
Author  : Kumar Verma
Purpose : Generate a structured, downloadable forensic analysis report for
          any image submitted to the tampering detection system.
          The report contains: image metadata, ELA verdict, EXIF data,
          weather validation, copy-move analysis, and an overall verdict.
"""

from datetime import datetime
import io


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

def generate_text_report(
    image_name:      str,
    image_info:      dict,
    hashes:          dict,
    ela_result:      str,
    ela_confidence:  float,
    ela_multi_q:     dict,
    exif_data:       dict,
    noise_info:      dict,
    compression_info: dict,
    copy_move_info:  dict,
    weather_location: str = None,
    weather_date:     str = None,
    weather_actual:   str = None,
    weather_cnn:      str = None,
    overall_verdict:  str = "UNCERTAIN",
) -> str:
    """
    Build a plain-text forensic analysis report.

    Parameters
    ----------
    image_name       : str   – name of the uploaded image file.
    image_info       : dict  – from image_utils.get_image_info()
    hashes           : dict  – from image_utils.compute_image_hash()
    ela_result       : str   – 'Real' or 'Tampered'
    ela_confidence   : float – confidence percentage (0–100)
    ela_multi_q      : dict  – multi-quality ELA from helper.multi_quality_ela()
    exif_data        : dict  – from helper.extract_exif_data()
    noise_info       : dict  – from helper.compute_noise_analysis()
    compression_info : dict  – from image_utils.detect_double_compression()
    copy_move_info   : dict  – from image_utils.check_copy_move()
    weather_location : str   – reverse-geocoded location name
    weather_date     : str   – date of capture
    weather_actual   : str   – actual historical weather
    weather_cnn      : str   – CNN-predicted weather class
    overall_verdict  : str   – final verdict string

    Returns
    -------
    report_text : str – complete report as a formatted plain-text string.
    """

    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    line = "=" * 70

    lines = [
        line,
        "     DIGITAL IMAGE FORENSICS ANALYSIS REPORT",
        "     Chandigarh University — MCA Final Year Project",
        "     Student: Kumar Verma",
        line,
        f"  Report Generated : {now}",
        f"  Image File       : {image_name}",
        line,
        "",
        # ---- Section 1: File Information ----
        "SECTION 1 — FILE INFORMATION",
        "-" * 40,
        f"  File Name        : {image_name}",
        f"  File Size        : {image_info.get('file_size', 'N/A')}",
        f"  Dimensions       : {image_info.get('width', '?')} x {image_info.get('height', '?')} px",
        f"  Megapixels       : {image_info.get('megapixels', 'N/A')} MP",
        f"  Colour Mode      : {image_info.get('mode', 'N/A')}",
        f"  Format           : {image_info.get('format', 'N/A')}",
        "",
        # ---- Section 2: Cryptographic Hashes ----
        "SECTION 2 — CRYPTOGRAPHIC INTEGRITY",
        "-" * 40,
        "  These hash values uniquely identify the file.",
        "  Any modification — even a single pixel — will change these values.",
        "",
        f"  MD5    : {hashes.get('md5', 'N/A')}",
        f"  SHA-256: {hashes.get('sha256', 'N/A')}",
        "",
        # ---- Section 3: ELA Analysis ----
        "SECTION 3 — ERROR LEVEL ANALYSIS (ELA)",
        "-" * 40,
        "  ELA detects inconsistencies in JPEG compression artefacts.",
        "  Tampered regions typically show higher error levels than the original.",
        "",
        f"  ELA Verdict      : {ela_result.upper()}",
        f"  Model Confidence : {ela_confidence:.1f}%",
        "",
        "  Multi-Quality ELA (mean pixel error at different quality levels):",
        f"    Quality 70  : {ela_multi_q.get('q70', 'N/A')}",
        f"    Quality 80  : {ela_multi_q.get('q80', 'N/A')}",
        f"    Quality 90  : {ela_multi_q.get('q90', 'N/A')}",
        "",
        # ---- Section 4: EXIF Metadata ----
        "SECTION 4 — EXIF / IMAGE METADATA",
        "-" * 40,
        "  EXIF data is embedded in the image by the camera at capture time.",
        "  Software tags (e.g., Photoshop) may indicate post-processing.",
        "",
    ]

    if exif_data:
        for key, val in exif_data.items():
            lines.append(f"  {key:<30}: {val}")
    else:
        lines.append("  No EXIF metadata found in this image.")

    lines += [
        "",
        # ---- Section 5: Noise Analysis ----
        "SECTION 5 — NOISE CONSISTENCY ANALYSIS",
        "-" * 40,
        "  Tampered images often show inconsistent noise levels across regions.",
        "",
        f"  Mean Noise  : {noise_info.get('mean_noise', 'N/A')}",
        f"  Std Dev     : {noise_info.get('std_noise', 'N/A')}",
        f"  Max Noise   : {noise_info.get('max_noise', 'N/A')}",
        f"  Tamper Hint : {'YES — noise is inconsistent across image regions' if noise_info.get('tamper_hint') else 'No significant inconsistency detected'}",
        "",
        # ---- Section 6: JPEG Compression Analysis ----
        "SECTION 6 — JPEG DOUBLE-COMPRESSION ANALYSIS",
        "-" * 40,
        f"  Suspicion Level    : {compression_info.get('suspicion_level', 'N/A')}",
        f"  Avg Quant. Value   : {compression_info.get('avg_quantization_value', 'N/A')}",
        f"  Number of Tables   : {compression_info.get('num_tables', 'N/A')}",
        f"  Explanation        : {compression_info.get('explanation', 'N/A')}",
        "",
        # ---- Section 7: Copy-Move Detection ----
        "SECTION 7 — COPY-MOVE FORGERY DETECTION",
        "-" * 40,
        f"  Suspected : {'YES' if copy_move_info.get('copy_move_suspected') else 'No'}",
        f"  Total Blocks    : {copy_move_info.get('total_blocks', 'N/A')}",
        f"  Duplicate Blocks: {copy_move_info.get('duplicate_blocks', 'N/A')}",
        f"  Duplication %   : {round(copy_move_info.get('duplication_ratio', 0) * 100, 1)}%",
        f"  Explanation     : {copy_move_info.get('explanation', 'N/A')}",
        "",
    ]

    # ---- Section 8: Weather Validation (optional) ----
    lines += [
        "SECTION 8 — WEATHER METADATA VALIDATION",
        "-" * 40,
    ]
    if weather_location:
        lines += [
            "  This section compares the weather visible in the image against",
            "  historical weather records for the captured location and time.",
            "",
            f"  Location         : {weather_location}",
            f"  Date             : {weather_date}",
            f"  CNN Detected     : {weather_cnn}",
            f"  Actual (API)     : {weather_actual}",
        ]
        if weather_cnn and weather_actual and weather_actual != "NA":
            # Simple match check (case-insensitive keyword comparison)
            match = (
                weather_cnn.lower() in weather_actual.lower()
                or weather_actual.lower() in weather_cnn.lower()
            )
            lines.append(
                f"  Weather Match    : {'YES — consistent' if match else 'NO — DISCREPANCY DETECTED'}"
            )
    else:
        lines.append("  Weather validation was not performed (no GPS EXIF data or indoor image).")

    # ---- Section 9: Overall Verdict ----
    lines += [
        "",
        line,
        "SECTION 9 — OVERALL FORENSIC VERDICT",
        line,
        f"  >> {overall_verdict} <<",
        "",
        "  Disclaimer: This report is generated by an automated forensics",
        "  system for academic purposes.  Results should be interpreted by a",
        "  qualified digital forensics professional for legal or evidentiary",
        "  use.  No automated tool can guarantee 100% accuracy.",
        line,
        "  END OF REPORT",
        line,
    ]

    return "\n".join(lines)
