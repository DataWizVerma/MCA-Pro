"""
app.py
------
Project : Digital Image Forensics System for Tampering Detection
College : Chandigarh University — MCA Final Year Major Project
Student : Kumar Verma
Guide   : (Your Guide Name)
Year    : 2024-25

Description :
    A Streamlit-based web application that analyses digital images for signs
    of tampering using two complementary techniques:
      1. Error Level Analysis (ELA)  — detects JPEG compression inconsistencies
         using a pre-trained DenseNet121 deep-learning model.
      2. Metadata & Weather Validation — cross-checks EXIF location/time
         metadata against historical weather API data and a Weather CNN model.

    Additional forensic modules include:
      - Cryptographic hashing (MD5 / SHA-256) for file integrity verification
      - JPEG quantization table analysis (double-compression detection)
      - Lightweight copy-move forgery detection via block hashing
      - Noise consistency analysis across image regions
      - Downloadable plain-text forensic report

Usage:
    streamlit run app.py
"""

# ============================================================
# Standard library imports
# ============================================================
import os
import io
import warnings

warnings.filterwarnings("ignore")   # suppress TensorFlow verbose logs

# ============================================================
# Third-party imports
# ============================================================
import streamlit as st
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")               # non-interactive backend for Streamlit
import matplotlib.pyplot as plt
from PIL import Image as PILImage

# -----------------------------------------------------------------------
# Model loader — robust fallback for old Keras 2.x .h5 files
# The pre-trained models were saved with Keras 2.x which allowed '/'
# characters in layer names (e.g. "conv1/conv"). Keras 3.x rejects this.
# We try three loaders in order until one succeeds.
# -----------------------------------------------------------------------
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

def load_model(path):
    """
    Load a Keras .h5 model file with automatic version compatibility.
    Tries loaders in order:
      1. tf_keras  — official Keras 2 backward-compat package (best for old models)
      2. tensorflow.keras with compile=False
      3. Raises the last exception so the caller can handle it gracefully.
    """
    last_err = None

    # Attempt 1: tf_keras — Keras 2 API, fully compatible with old .h5 models
    try:
        import tf_keras
        return tf_keras.models.load_model(path, compile=False)
    except Exception as e:
        last_err = e

    # Attempt 2: tensorflow.keras fallback
    try:
        from tensorflow.keras.models import load_model as tf_load
        return tf_load(path, compile=False)
    except Exception as e:
        last_err = e

    raise last_err

# ============================================================
# Project module imports
# ============================================================
from helper import (
    prepare_image_for_ela,
    prerpare_img_for_weather,
    get_ela_heatmap,
    multi_quality_ela,
    extract_exif_data,
    compute_noise_analysis,
)
from fetchOriginal import image_coordinates, get_weather, get_full_exif_report
from image_utils import compute_image_hash, detect_double_compression, check_copy_move, get_image_info
from analysis_report import generate_text_report


# ============================================================
# Constants
# ============================================================
CLASSES_ELA     = ["Real", "Tampered"]
CLASSES_WEATHER = ["Lightning", "Rainy", "Snow", "Sunny"]

# Path to the pre-trained models (relative to project root)
ELA_MODEL_PATH     = "ELA_Training/model_ela.h5"
WEATHER_MODEL_PATH = "WeatherCNNTraining/Weather_Model.h5"

# Temporary file path for the uploaded image
TEMP_IMAGE_PATH = "temp.jpg"


# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="Image Forensics — Chandigarh University",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS — Premium Dark Theme
# ============================================================
st.markdown("""
<style>
/* ---- Google Font ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ---- Root variables ---- */
:root {
    --bg-primary:    #0d1117;
    --bg-secondary:  #161b22;
    --bg-card:       #1c2128;
    --accent:        #00d4aa;
    --accent-dark:   #00a884;
    --danger:        #ff4b4b;
    --warning:       #ffa500;
    --success:       #00d4aa;
    --text-primary:  #e6edf3;
    --text-muted:    #8b949e;
    --border:        #30363d;
    --radius:        12px;
}

/* ---- Global ---- */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

/* ---- App background ---- */
.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%) !important;
}

/* ---- Main content area ---- */
.main .block-container {
    padding: 2rem 3rem !important;
    max-width: 1200px !important;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] .block-container {
    padding: 2rem 1.2rem !important;
}

/* ---- Tab styling ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: var(--bg-secondary) !important;
    border-radius: var(--radius) !important;
    padding: 6px !important;
    border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    border-radius: 8px !important;
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    padding: 8px 20px !important;
    transition: all 0.2s ease !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, var(--accent), var(--accent-dark)) !important;
    color: #0d1117 !important;
    font-weight: 700 !important;
}

/* ---- Buttons ---- */
.stButton > button {
    background: linear-gradient(135deg, #00d4aa, #00a884) !important;
    color: #0d1117 !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 10px 28px !important;
    font-size: 15px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 15px rgba(0, 212, 170, 0.25) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(0, 212, 170, 0.4) !important;
}

/* ---- File uploader ---- */
[data-testid="stFileUploader"] {
    border: 2px dashed var(--accent) !important;
    border-radius: var(--radius) !important;
    background: rgba(0, 212, 170, 0.04) !important;
    padding: 20px !important;
}

/* ---- Metric cards ---- */
[data-testid="metric-container"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 16px !important;
}

/* ---- Info / Success / Warning / Error boxes ---- */
.stAlert {
    border-radius: var(--radius) !important;
}

/* ---- Expander ---- */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}

/* ---- Data table ---- */
.stDataFrame {
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}

/* ---- Custom card component ---- */
.forensic-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 24px;
    margin-bottom: 16px;
}
.forensic-card h3 {
    color: var(--accent);
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ---- Verdict badge ---- */
.verdict-tampered {
    display: inline-block;
    background: linear-gradient(135deg, #ff4b4b, #c0392b);
    color: white;
    font-weight: 800;
    font-size: 22px;
    padding: 12px 36px;
    border-radius: 40px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(255, 75, 75, 0.4);
    letter-spacing: 0.08em;
}
.verdict-authentic {
    display: inline-block;
    background: linear-gradient(135deg, #00d4aa, #00a884);
    color: #0d1117;
    font-weight: 800;
    font-size: 22px;
    padding: 12px 36px;
    border-radius: 40px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0, 212, 170, 0.4);
    letter-spacing: 0.08em;
}
.verdict-uncertain {
    display: inline-block;
    background: linear-gradient(135deg, #ffa500, #e67e00);
    color: #0d1117;
    font-weight: 800;
    font-size: 22px;
    padding: 12px 36px;
    border-radius: 40px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(255, 165, 0, 0.4);
    letter-spacing: 0.08em;
}

/* ---- Hero header ---- */
.hero-title {
    font-size: 38px;
    font-weight: 800;
    background: linear-gradient(135deg, #00d4aa, #00aaff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
    margin-bottom: 8px;
}
.hero-subtitle {
    font-size: 16px;
    color: var(--text-muted);
    margin-bottom: 24px;
}

/* ---- Section header ---- */
.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 24px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent);
}
.section-header span {
    font-size: 18px;
    font-weight: 700;
    color: var(--text-primary);
}

/* ---- Tag pill ---- */
.tag-pill {
    display: inline-block;
    background: rgba(0, 212, 170, 0.15);
    color: var(--accent);
    border: 1px solid rgba(0, 212, 170, 0.3);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
    margin: 2px;
}

/* ---- Radio & Checkbox ---- */
.stRadio label, .stCheckbox label {
    color: var(--text-primary) !important;
}

/* ---- Progress bar ---- */
.stProgress > div > div {
    background: linear-gradient(90deg, var(--accent), var(--accent-dark)) !important;
}

/* ---- Selectbox ---- */
.stSelectbox select, .stSelectbox > div {
    background: var(--bg-card) !important;
    border-color: var(--border) !important;
    color: var(--text-primary) !important;
}

/* ---- Hide default Streamlit header ---- */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}

/* ---- Scrollbar ---- */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 10px 0 20px 0;">
        <div style="font-size:48px;">🔍</div>
        <div style="font-size:18px; font-weight:800; color:#00d4aa; margin-top:8px;">
            Image Forensics
        </div>
        <div style="font-size:12px; color:#8b949e; margin-top:4px;">
            Tampering Detection System
        </div>
    </div>
    <hr style="border-color:#30363d; margin-bottom:20px;">
    """, unsafe_allow_html=True)

    st.markdown("**📚 Project Info**")
    st.markdown("""
    <div style="font-size:13px; color:#8b949e; line-height:1.8;">
    🏫 Chandigarh University<br>
    👤 Kumar Verma<br>
    🎓 MCA — Final Year<br>
    📅 2024-25<br>
    📌 Major Project
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#30363d;'>", unsafe_allow_html=True)

    st.markdown("**🛠️ Techniques Used**")
    st.markdown("""
    <div style="margin-top:8px;">
        <span class="tag-pill">ELA</span>
        <span class="tag-pill">DenseNet121</span>
        <span class="tag-pill">Weather CNN</span>
        <span class="tag-pill">EXIF Analysis</span>
        <span class="tag-pill">MD5 / SHA-256</span>
        <span class="tag-pill">Copy-Move Detection</span>
        <span class="tag-pill">Noise Analysis</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#30363d;'>", unsafe_allow_html=True)

    st.markdown("**📊 Model Accuracy**")
    st.markdown("""
    | Model | Accuracy |
    |-------|----------|
    | ELA (DenseNet121) | 87.24% |
    | Weather CNN | 73.40% |
    """)

    st.markdown("<hr style='border-color:#30363d;'>", unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:11px; color:#8b949e; text-align:center;">
    For academic and educational use only.<br>
    Results are not legally binding.
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# MAIN CONTENT — TABS
# ============================================================
tab_home, tab_analyze, tab_about, tab_how = st.tabs([
    "🏠 Home", "🔬 Analyze Image", "ℹ️ About Project", "📖 How It Works"
])


# ============================================================
# TAB 1: HOME
# ============================================================
with tab_home:
    st.markdown("""
    <div class="hero-title">Digital Image Forensics System</div>
    <div class="hero-subtitle">
        Detect image tampering using AI-powered Error Level Analysis & Metadata Validation
    </div>
    """, unsafe_allow_html=True)

    # Stat cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("ELA Model Accuracy", "87.24%", "DenseNet121")
    with c2:
        st.metric("Weather CNN Accuracy", "73.40%", "CNN Model")
    with c3:
        st.metric("Analysis Techniques", "5+", "Multi-modal")
    with c4:
        st.metric("Report Format", "TXT", "Downloadable")

    st.markdown("<br>", unsafe_allow_html=True)

    # Feature cards
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="forensic-card">
        <h3>⚡ Error Level Analysis</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.7;">
        Uses a pre-trained DenseNet121 model trained on the CASIA 2.0 dataset.
        Detects compression inconsistencies in JPEG images that are invisible
        to the human eye but reveal tampering.
        </p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="forensic-card">
        <h3>🌍 Metadata Validation</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.7;">
        Extracts GPS coordinates, camera details, and timestamps from EXIF data.
        Cross-validates the weather visible in the image against historical
        weather records from the Open-Meteo ERA5 database.
        </p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="forensic-card">
        <h3>🔐 Cryptographic Integrity</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.7;">
        Generates MD5 and SHA-256 fingerprints of the image file.
        Additional checks include JPEG quantization table analysis and a
        lightweight copy-move forgery detection algorithm.
        </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👉 Switch to the **Analyze Image** tab to upload and analyse an image.")


# ============================================================
# TAB 2: ANALYZE IMAGE
# ============================================================
with tab_analyze:
    st.markdown("""
    <div class="section-header">
        <span>🔬 Upload & Analyse</span>
    </div>
    """, unsafe_allow_html=True)

    # Initialize Streamlit session state variables
    if "step" not in st.session_state:
        st.session_state.step = 0
    if "analysis_done" not in st.session_state:
        st.session_state.analysis_done = False
    if "results" not in st.session_state:
        st.session_state.results = {}

    # ---- File uploader ------------------------------------------------
    uploaded_file = st.file_uploader(
        "Upload a JPEG image to analyse",
        type=["jpg", "jpeg"],
        help="Only JPEG/JPG format is supported. Images with GPS EXIF enable weather validation.",
    )

    if uploaded_file is not None:
        # Save the uploaded file to a temporary location on disk
        with open(TEMP_IMAGE_PATH, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Show preview
        col_prev, col_opts = st.columns([1, 1])
        with col_prev:
            st.image(uploaded_file, caption="Uploaded Image", width='stretch')
        with col_opts:
            st.markdown("**Image Details:**")
            img_info = get_image_info(TEMP_IMAGE_PATH)
            st.write(f"📐 **Size:** {img_info.get('width')} × {img_info.get('height')} px")
            st.write(f"💾 **File Size:** {img_info.get('file_size')}")
            st.write(f"📷 **Mode:** {img_info.get('mode')}")
            st.write(f"🔭 **Megapixels:** {img_info.get('megapixels')} MP")

            st.markdown("<br>", unsafe_allow_html=True)
            flag = st.radio(
                "Is weather visible in this image? (enables weather validation)",
                ("Yes — outdoor image with visible weather",
                 "No — indoor or no weather visible"),
                help="Select 'Yes' only if the image was taken outdoors and shows sky/weather. "
                     "This requires GPS EXIF data to be present in the image.",
            )
            is_outdoor = flag.startswith("Yes")

            # Reset session if a new file is uploaded
            if st.session_state.step > 0:
                if st.button("🔄 Reset & Analyse New Image"):
                    st.session_state.step = 0
                    st.session_state.analysis_done = False
                    st.session_state.results = {}
                    st.rerun()

        # ---- Analyse button --------------------------------------------
        if st.button("🔬 Run Forensic Analysis", use_container_width=True):
            st.session_state.step = 1
            st.session_state.analysis_done = False

    # ---- Analysis execution -------------------------------------------
    if st.session_state.step > 0 and uploaded_file is not None:
        if not st.session_state.analysis_done:

            # Run all analyses with a progress bar for user feedback
            progress = st.progress(0, text="Starting forensic analysis…")

            with st.spinner("Analysing image — please wait…"):
                results = {}

                # Step 1: Image info & hashes
                progress.progress(10, text="Computing cryptographic hashes…")
                results["img_info"]    = get_image_info(TEMP_IMAGE_PATH)
                results["hashes"]      = compute_image_hash(TEMP_IMAGE_PATH)

                # Step 2: ELA analysis
                progress.progress(25, text="Running Error Level Analysis (ELA)…")
                try:
                    np_input, ela_pil = prepare_image_for_ela(TEMP_IMAGE_PATH)
                    ela_model          = load_model(ELA_MODEL_PATH)
                    ela_predictions    = ela_model.predict(np_input, verbose=0)
                    ela_class_idx      = int(np.argmax(ela_predictions[0]))
                    ela_label          = CLASSES_ELA[ela_class_idx]
                    ela_confidence     = float(np.max(ela_predictions[0])) * 100
                    ela_probs          = [float(p) * 100 for p in ela_predictions[0]]

                    results["ela_label"]      = ela_label
                    results["ela_confidence"] = ela_confidence
                    results["ela_probs"]      = ela_probs
                    results["ela_pil"]        = ela_pil
                    results["ela_ok"]         = True
                except Exception as e:
                    results["ela_ok"]    = False
                    results["ela_error"] = str(e)

                # Step 3: Multi-quality ELA
                progress.progress(40, text="Running multi-quality ELA…")
                results["ela_multi_q"] = multi_quality_ela(TEMP_IMAGE_PATH)

                # Step 4: EXIF metadata
                progress.progress(50, text="Extracting EXIF metadata…")
                results["exif_data"]  = extract_exif_data(TEMP_IMAGE_PATH)
                results["exif_full"]  = get_full_exif_report(TEMP_IMAGE_PATH)

                # Step 5: Noise analysis
                progress.progress(60, text="Analysing noise consistency…")
                results["noise_info"] = compute_noise_analysis(TEMP_IMAGE_PATH)

                # Step 6: JPEG compression analysis
                progress.progress(70, text="Analysing JPEG compression tables…")
                results["compression"] = detect_double_compression(TEMP_IMAGE_PATH)

                # Step 7: Copy-move detection
                progress.progress(78, text="Running copy-move forgery check…")
                results["copy_move"] = check_copy_move(TEMP_IMAGE_PATH)

                # Step 8: ELA heatmap
                progress.progress(85, text="Generating ELA heatmap overlay…")
                try:
                    results["heatmap_pil"] = get_ela_heatmap(TEMP_IMAGE_PATH)
                except Exception:
                    results["heatmap_pil"] = None

                # Step 9: Weather validation (only if outdoor selected)
                results["weather_done"] = False
                results["weather_ok"]   = False
                if is_outdoor:
                    progress.progress(90, text="Fetching metadata & weather data…")
                    try:
                        date_time, lat, lon, outdoor_flag = image_coordinates(TEMP_IMAGE_PATH)
                        if outdoor_flag and date_time:
                            location, date_str, weather_actual, weather_cnn_class = get_weather(
                                date_time, lat, lon
                            )
                            # CNN weather prediction
                            np_weather = prerpare_img_for_weather(TEMP_IMAGE_PATH)
                            weather_model = load_model(WEATHER_MODEL_PATH)
                            weather_preds = weather_model.predict(np_weather, verbose=0)
                            weather_cnn_label = CLASSES_WEATHER[int(np.argmax(weather_preds[0]))]
                            weather_cnn_conf  = float(np.max(weather_preds[0])) * 100

                            results["weather_location"]  = str(location)
                            results["weather_date"]      = date_str
                            results["weather_actual"]    = weather_actual
                            results["weather_cnn_api"]   = weather_cnn_class    # API-mapped class
                            results["weather_cnn_label"] = weather_cnn_label    # CNN-predicted label
                            results["weather_cnn_conf"]  = weather_cnn_conf
                            results["weather_done"]      = True
                            results["weather_ok"]        = True
                        else:
                            results["weather_done"] = True
                            results["weather_ok"]   = False
                    except Exception as e:
                        results["weather_done"] = True
                        results["weather_ok"]   = False
                        results["weather_error"] = str(e)

                # Step 10: Compute overall verdict
                progress.progress(95, text="Computing overall verdict…")
                tamper_signals = 0
                if results.get("ela_ok") and results.get("ela_label") == "Tampered" and results.get("ela_confidence", 0) > 60:
                    tamper_signals += 2
                if results.get("copy_move", {}).get("copy_move_suspected"):
                    tamper_signals += 1
                if results.get("compression", {}).get("suspicion_level") == "High":
                    tamper_signals += 1
                if results.get("noise_info", {}).get("tamper_hint"):
                    tamper_signals += 1

                if tamper_signals >= 3:
                    verdict = "⚠️ IMAGE IS LIKELY TAMPERED"
                    verdict_class = "verdict-tampered"
                elif tamper_signals == 0 and results.get("ela_label") == "Real":
                    verdict = "✅ IMAGE APPEARS AUTHENTIC"
                    verdict_class = "verdict-authentic"
                else:
                    verdict = "🔶 RESULT IS UNCERTAIN — MANUAL REVIEW RECOMMENDED"
                    verdict_class = "verdict-uncertain"

                results["verdict"]       = verdict
                results["verdict_class"] = verdict_class
                results["tamper_signals"] = tamper_signals

                progress.progress(100, text="Analysis complete!")

            st.session_state.results      = results
            st.session_state.analysis_done = True

        # ---- DISPLAY RESULTS ------------------------------------------
        res = st.session_state.results

        st.markdown("---")
        st.markdown("""
        <div class="section-header">
            <span>📊 Forensic Analysis Results</span>
        </div>
        """, unsafe_allow_html=True)

        # ---- OVERALL VERDICT (prominent) ----
        st.markdown("<br>", unsafe_allow_html=True)
        verdict_col = st.columns([1, 2, 1])[1]
        with verdict_col:
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div class="{res["verdict_class"]}">{res["verdict"]}</div>'
                f'<div style="color:#8b949e; font-size:13px; margin-top:8px;">'
                f'Tamper signals detected: {res["tamper_signals"]} / 5</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<br>", unsafe_allow_html=True)

        # ---- SIMPLE LANGUAGE SUMMARY (for non-technical users) ----------
        ela_ok     = res.get("ela_ok", False)
        ela_lbl    = res.get("ela_label", "Unknown")
        ela_conf   = res.get("ela_confidence", 0.0)
        real_pct   = round(res["ela_probs"][0], 1) if ela_ok else 0.0
        tamper_pct = round(res["ela_probs"][1], 1) if ela_ok else 0.0
        signals    = res.get("tamper_signals", 0)

        # Build a plain-English explanation anyone can understand
        if ela_ok:
            if ela_lbl == "Real":
                emoji_main = "✅"
                colour_main = "#00d4aa"
                headline = f"This image looks {real_pct}% REAL / ORIGINAL"
                sub1 = (
                    f"Our AI checked the image and found it is "
                    f"<strong style='color:#00d4aa;'>{real_pct}% likely to be an original, unedited photo</strong>. "
                    f"Only <strong style='color:#ff4b4b;'>{tamper_pct}% chance</strong> it was edited."
                )
            else:
                emoji_main = "⚠️"
                colour_main = "#ff4b4b"
                headline = f"This image looks {tamper_pct}% EDITED / TAMPERED"
                sub1 = (
                    f"Our AI checked the image and found it is "
                    f"<strong style='color:#ff4b4b;'>{tamper_pct}% likely to have been edited</strong> "
                    f"(e.g. in Photoshop, GIMP, or similar software). "
                    f"Only <strong style='color:#00d4aa;'>{real_pct}% chance</strong> it is fully original."
                )
        else:
            emoji_main = "🔶"
            colour_main = "#ffa500"
            headline = "AI model could not analyse this image (model compatibility issue)"
            sub1 = "The deep-learning model failed to load. Other forensic checks still ran."

        # Signal explanation in simple words
        signal_words = []
        if res.get("copy_move", {}).get("copy_move_suspected"):
            signal_words.append("part of the image appears to be copy-pasted within itself")
        if res.get("compression", {}).get("suspicion_level") == "High":
            signal_words.append("the image was re-saved multiple times (common after editing)")
        if res.get("noise_info", {}).get("tamper_hint"):
            signal_words.append("different regions have inconsistent noise levels (sign of splicing)")
        exif_software = res.get("exif_data", {}).get("Software", "")
        if any(k in exif_software.lower() for k in ["photoshop", "gimp", "lightroom", "paint"]):
            signal_words.append(f"EXIF data shows the image was opened in '{exif_software}'")

        if signal_words:
            signal_html = "<br>".join([f"&nbsp;&nbsp;🔴 {w.capitalize()}" for w in signal_words])
        else:
            signal_html = "&nbsp;&nbsp;🟢 No suspicious signals detected in additional checks."

        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #1c2128, #161b22);
            border: 2px solid {colour_main};
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 24px;
        ">
            <div style="font-size:28px; font-weight:800; color:{colour_main}; margin-bottom:6px;">
                {emoji_main} {headline}
            </div>
            <div style="font-size:15px; color:#e6edf3; line-height:1.9; margin-bottom:12px;">
                {sub1}
            </div>
            <div style="font-size:14px; color:#8b949e; line-height:2.0;">
                <strong style="color:#e6edf3;">What else did we find?</strong><br>
                {signal_html}
            </div>
            <div style="
                background:#0d1117; border-radius:10px; padding:14px 18px;
                margin-top:16px; font-size:13px; color:#8b949e; line-height:1.8;
            ">
                💡 <strong style="color:#e6edf3;">Think of it like this:</strong>
                Imagine 100 forensic experts examined this image.
                <strong style="color:{colour_main};">{real_pct if ela_lbl == 'Real' else tamper_pct} out of 100</strong>
                would say it looks <strong>{ela_lbl.lower() if ela_ok else 'unknown'}</strong>.
                We also ran {5} different checks — {signals} of them raised a red flag.
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ---- RESULT TABS ----
        r_ela, r_exif, r_weather, r_extra, r_hash = st.tabs([
            "🖼️ ELA Analysis",
            "📋 EXIF Metadata",
            "🌦️ Weather Validation",
            "🔍 Additional Checks",
            "🔐 File Integrity",
        ])

        # ======== ELA TAB ========
        with r_ela:
            if res.get("ela_ok"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**ELA Result Image**")
                    # ELA image: brighter spots = regions with more compression error = likely tampered
                    st.image(res["ela_pil"], caption="Error Level Analysis — brighter regions = more suspicious", width='stretch')

                    # Download ELA image
                    buf = io.BytesIO()
                    res["ela_pil"].save(buf, format="JPEG")
                    buf.seek(0)
                    st.download_button(
                        "⬇️ Download ELA Image",
                        data=buf,
                        file_name="ela_result.jpg",
                        mime="image/jpeg",
                    )

                with col_b:
                    st.markdown("**Heatmap Overlay**")
                    if res.get("heatmap_pil"):
                        # Heatmap: red/warm = high error level, blue/cool = low error
                        st.image(res["heatmap_pil"], caption="Red = suspicious area, Blue = normal area", width='stretch')
                    else:
                        st.info("Heatmap not available.")

                # ELA verdict and confidence bar chart
                st.markdown("<br>", unsafe_allow_html=True)
                mc1, mc2 = st.columns(2)
                with mc1:
                    ela_label = res["ela_label"]
                    ela_conf  = res["ela_confidence"]
                    colour    = "#ff4b4b" if ela_label == "Tampered" else "#00d4aa"
                    st.markdown(
                        f'<div class="forensic-card">'
                        f'<h3>ELA Verdict</h3>'
                        f'<div style="font-size:28px; font-weight:800; color:{colour};">{ela_label}</div>'
                        f'<div style="color:#8b949e; margin-top:6px;">Confidence: {ela_conf:.1f}%</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with mc2:
                    # Confidence bar chart
                    fig, ax = plt.subplots(figsize=(4, 2.5))
                    fig.patch.set_facecolor("#1c2128")
                    ax.set_facecolor("#1c2128")
                    labels = CLASSES_ELA
                    values = res["ela_probs"]
                    colours = ["#00d4aa", "#ff4b4b"]
                    bars = ax.barh(labels, values, color=colours, height=0.5)
                    ax.set_xlim(0, 100)
                    ax.set_xlabel("Confidence (%)", color="#8b949e", fontsize=9)
                    ax.tick_params(colors="#e6edf3", labelsize=10)
                    for spine in ax.spines.values():
                        spine.set_edgecolor("#30363d")
                    for bar, val in zip(bars, values):
                        ax.text(val + 1, bar.get_y() + bar.get_height() / 2,
                                f"{val:.1f}%", va="center", color="#e6edf3", fontsize=9)
                    plt.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)

                # Multi-quality ELA
                with st.expander("📈 Multi-Quality ELA Details"):
                    st.markdown(
                        "ELA was run at three JPEG quality levels. "
                        "Higher mean error values generally correlate with a higher likelihood of tampering."
                    )
                    mq = res["ela_multi_q"]
                    fig2, ax2 = plt.subplots(figsize=(5, 2.5))
                    fig2.patch.set_facecolor("#1c2128")
                    ax2.set_facecolor("#1c2128")
                    qs = ["Quality 70", "Quality 80", "Quality 90"]
                    vs = [mq.get("q70", 0), mq.get("q80", 0), mq.get("q90", 0)]
                    ax2.bar(qs, vs, color=["#ff4b4b", "#ffa500", "#00d4aa"], width=0.4)
                    ax2.set_ylabel("Mean Pixel Error", color="#8b949e", fontsize=9)
                    ax2.tick_params(colors="#e6edf3", labelsize=9)
                    for spine in ax2.spines.values():
                        spine.set_edgecolor("#30363d")
                    plt.tight_layout()
                    st.pyplot(fig2)
                    plt.close(fig2)
                    c1m, c2m, c3m = st.columns(3)
                    c1m.metric("Quality 70", mq.get("q70"))
                    c2m.metric("Quality 80", mq.get("q80"))
                    c3m.metric("Quality 90", mq.get("q90"))
            else:
                st.error(f"ELA analysis failed: {res.get('ela_error', 'Unknown error')}")

        # ======== EXIF TAB ========
        with r_exif:
            exif_data = res.get("exif_data", {})
            st.markdown("""
            <div class="forensic-card">
            <h3>What is EXIF Data?</h3>
            <p style="color:#8b949e; font-size:13px; line-height:1.7;">
            EXIF (Exchangeable Image File Format) metadata is automatically embedded into
            photos by cameras and smartphones. It contains camera settings, GPS location,
            date/time, and sometimes software information (e.g., "Adobe Photoshop") that
            can reveal if an image was edited.
            </p>
            </div>
            """, unsafe_allow_html=True)

            if exif_data:
                # Check if software field suggests editing
                software = exif_data.get("Software", "")
                if any(kw in software.lower() for kw in ["photoshop", "gimp", "lightroom", "paint"]):
                    st.warning(f"⚠️ **Software field detected:** `{software}` — Image may have been edited in photo-editing software.")

                # Display as a nice table
                import pandas as pd
                df = pd.DataFrame(
                    {"Property": list(exif_data.keys()), "Value": list(exif_data.values())}
                )
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("ℹ️ No EXIF metadata was found in this image. The EXIF data may have been stripped — which can itself be a sign of editing.")

        # ======== WEATHER TAB ========
        with r_weather:
            st.markdown("""
            <div class="forensic-card">
            <h3>Weather Validation Explained</h3>
            <p style="color:#8b949e; font-size:13px; line-height:1.7;">
            If the image contains GPS coordinates and a timestamp in its EXIF metadata, we can
            query historical weather databases (Open-Meteo ERA5) to find out what the actual
            weather was at that exact location and time. A CNN model also classifies the weather
            visible in the image. If the two results disagree, it could indicate the image was
            taken at a different location or time than its metadata suggests.
            </p>
            </div>
            """, unsafe_allow_html=True)

            if not is_outdoor:
                st.info("ℹ️ Weather validation was not selected. If the image is an outdoor photo with weather visible, re-run with 'Yes' selected.")
            elif res.get("weather_ok"):
                wc1, wc2 = st.columns(2)
                with wc1:
                    st.markdown("**📍 Location & Date**")
                    st.info(f"📍 {res.get('weather_location', 'Unknown')}")
                    st.info(f"📅 {res.get('weather_date', 'Unknown')}")
                with wc2:
                    st.markdown("**🌦️ Weather Comparison**")
                    cnn_w  = res.get("weather_cnn_label", "N/A")
                    api_w  = res.get("weather_actual", "N/A")
                    api_cls = res.get("weather_cnn_api", "N/A")   # API mapped to CNN class

                    st.metric("CNN Detected Weather", cnn_w,
                              delta=f"{res.get('weather_cnn_conf', 0):.1f}% confidence")
                    st.metric("Historical Weather (API)", api_w)

                    # Match evaluation
                    if api_w != "NA":
                        match = (
                            cnn_w.lower() in api_w.lower()
                            or api_cls.lower() == cnn_w.lower()
                        )
                        if match:
                            st.success("✅ Weather is **consistent** — image location/time metadata appears authentic.")
                        else:
                            st.error("❌ Weather **mismatch** — the weather in the image does not match historical records for this location and time. This may indicate tampering.")
                    else:
                        st.warning("⚠️ Historical weather data is not available for this date/location.")
            elif res.get("weather_done") and not res.get("weather_ok"):
                st.warning("⚠️ Weather validation could not be completed. The image may not contain GPS EXIF data, or the data was not readable.")
                if "weather_error" in res:
                    with st.expander("Technical details"):
                        st.code(res["weather_error"])

        # ======== ADDITIONAL CHECKS TAB ========
        with r_extra:
            col_n, col_c = st.columns(2)

            # Noise analysis
            with col_n:
                noise = res.get("noise_info", {})
                st.markdown("""
                <div class="forensic-card">
                <h3>📡 Noise Consistency Analysis</h3>
                </div>
                """, unsafe_allow_html=True)
                st.write(
                    "The image is divided into a 3×3 grid and local noise (Laplacian "
                    "variance) is measured for each region. Inconsistent noise across "
                    "regions can indicate that parts of the image were spliced from another source."
                )
                if "error" not in noise:
                    n1, n2, n3 = st.columns(3)
                    n1.metric("Mean Noise", noise.get("mean_noise", "N/A"))
                    n2.metric("Std Deviation", noise.get("std_noise", "N/A"))
                    n3.metric("Max Noise", noise.get("max_noise", "N/A"))

                    hint = noise.get("tamper_hint", False)
                    if hint:
                        st.warning("⚠️ Noise is **inconsistent** across image regions — potential splice tampering detected.")
                    else:
                        st.success("✅ Noise is **consistent** across image regions.")

                    # Noise region bar chart
                    regions = noise.get("regions", [])
                    if regions:
                        fig3, ax3 = plt.subplots(figsize=(5, 2.5))
                        fig3.patch.set_facecolor("#1c2128")
                        ax3.set_facecolor("#1c2128")
                        ax3.bar(range(1, len(regions) + 1), regions,
                                color=["#ff4b4b" if r > noise.get("mean_noise", 0) * 1.5 else "#00d4aa" for r in regions])
                        ax3.set_xlabel("Region (1–9 left-to-right, top-to-bottom)", color="#8b949e", fontsize=8)
                        ax3.set_ylabel("Noise Level", color="#8b949e", fontsize=8)
                        ax3.tick_params(colors="#e6edf3", labelsize=8)
                        for spine in ax3.spines.values():
                            spine.set_edgecolor("#30363d")
                        plt.tight_layout()
                        st.pyplot(fig3)
                        plt.close(fig3)
                else:
                    st.error(noise["error"])

            # Copy-move detection
            with col_c:
                cm = res.get("copy_move", {})
                st.markdown("""
                <div class="forensic-card">
                <h3>🔄 Copy-Move Detection</h3>
                </div>
                """, unsafe_allow_html=True)
                st.write(
                    "Divides the image into blocks and computes a fingerprint for each. "
                    "Duplicate blocks suggest that a region was copied and pasted within "
                    "the same image — a common forgery technique."
                )
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Total Blocks", cm.get("total_blocks", "N/A"))
                cc2.metric("Duplicate Blocks", cm.get("duplicate_blocks", "N/A"))
                cc3.metric("Duplication %", f"{round(cm.get('duplication_ratio', 0) * 100, 1)}%")

                if cm.get("copy_move_suspected"):
                    st.warning(f"⚠️ {cm.get('explanation', '')}")
                else:
                    st.success(f"✅ {cm.get('explanation', '')}")

            st.markdown("<br>", unsafe_allow_html=True)

            # JPEG double compression
            comp = res.get("compression", {})
            st.markdown("""
            <div class="forensic-card">
            <h3>🗜️ JPEG Double-Compression Analysis</h3>
            </div>
            """, unsafe_allow_html=True)
            st.write(
                "When a JPEG image is edited and re-saved, it undergoes a second round of "
                "lossy compression. This leaves traces in the JPEG quantization tables that "
                "can indicate the image was processed after its original capture."
            )
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("Suspicion Level",    comp.get("suspicion_level", "N/A"))
            dc2.metric("Avg Quant. Value",   comp.get("avg_quantization_value", "N/A"))
            dc3.metric("Quantization Tables", comp.get("num_tables", "N/A"))

            level = comp.get("suspicion_level", "Unknown")
            explanation = comp.get("explanation", "")
            if level == "High":
                st.error(f"🔴 High suspicion: {explanation}")
            elif level == "Medium":
                st.warning(f"🟠 Medium suspicion: {explanation}")
            elif level == "Low":
                st.success(f"🟢 Low suspicion: {explanation}")
            else:
                st.info(explanation)

        # ======== FILE INTEGRITY TAB ========
        with r_hash:
            st.markdown("""
            <div class="forensic-card">
            <h3>What are Cryptographic Hashes?</h3>
            <p style="color:#8b949e; font-size:13px; line-height:1.7;">
            A cryptographic hash is a unique fixed-length fingerprint of a file, computed
            from its entire contents. If even a single pixel in the image is changed, the
            hash value will be completely different. This is used in digital forensics to
            verify that a file has not been modified since it was first captured and hashed.
            </p>
            </div>
            """, unsafe_allow_html=True)

            hashes = res.get("hashes", {})
            h1, h2 = st.columns(2)
            with h1:
                st.markdown("**MD5 Hash**")
                st.code(hashes.get("md5", "N/A"), language=None)
            with h2:
                st.markdown("**SHA-256 Hash**")
                st.code(hashes.get("sha256", "N/A"), language=None)

            st.metric("File Size", f"{hashes.get('file_size_kb', 'N/A')} KB")

            st.info(
                "💡 **Tip:** Note down the SHA-256 hash when you first receive the image. "
                "If the hash changes later, the file has been modified."
            )

        # ---- Download Report ------------------------------------------
        st.markdown("---")
        st.markdown("""
        <div class="section-header">
            <span>📄 Download Forensic Report</span>
        </div>
        """, unsafe_allow_html=True)

        weather_loc  = res.get("weather_location") if res.get("weather_ok") else None
        weather_date = res.get("weather_date")     if res.get("weather_ok") else None
        weather_act  = res.get("weather_actual")   if res.get("weather_ok") else None
        weather_cnn_l = res.get("weather_cnn_label") if res.get("weather_ok") else None

        report_text = generate_text_report(
            image_name       = uploaded_file.name,
            image_info       = res.get("img_info", {}),
            hashes           = res.get("hashes", {}),
            ela_result       = res.get("ela_label", "Unknown"),
            ela_confidence   = res.get("ela_confidence", 0.0),
            ela_multi_q      = res.get("ela_multi_q", {}),
            exif_data        = res.get("exif_data", {}),
            noise_info       = res.get("noise_info", {}),
            compression_info = res.get("compression", {}),
            copy_move_info   = res.get("copy_move", {}),
            weather_location = weather_loc,
            weather_date     = weather_date,
            weather_actual   = weather_act,
            weather_cnn      = weather_cnn_l,
            overall_verdict  = res.get("verdict", "UNCERTAIN"),
        )

        st.download_button(
            label="📥 Download Full Forensic Report (.txt)",
            data=report_text.encode("utf-8"),
            file_name=f"forensic_report_{uploaded_file.name.replace('.jpg','').replace('.jpeg','')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    elif st.session_state.step == 0 and not uploaded_file:
        # No file uploaded yet — show placeholder
        st.markdown("""
        <div style="text-align:center; padding: 60px 20px; color:#8b949e;">
            <div style="font-size:64px;">📷</div>
            <div style="font-size:20px; font-weight:600; margin-top:16px;">Upload an Image to Begin</div>
            <div style="font-size:14px; margin-top:8px;">Supported format: JPEG / JPG</div>
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# TAB 3: ABOUT PROJECT
# ============================================================
with tab_about:
    st.markdown("""
    <div class="hero-title">About This Project</div>
    <div class="hero-subtitle">Understanding the Digital Image Forensics System</div>
    """, unsafe_allow_html=True)

    # ---- What is image tampering? ----
    st.markdown("""
    <div class="forensic-card">
    <h3>🖼️ What is Image Tampering?</h3>
    <p style="color:#e6edf3; font-size:15px; line-height:1.9;">
    Image tampering means <strong>changing a digital photograph</strong> in a way that makes it look like
    something that never really happened. For example:
    </p>
    <ul style="color:#8b949e; font-size:14px; line-height:2.2; padding-left:20px;">
        <li>Removing a person from a photo to make it look like they were never there</li>
        <li>Copying a part of one image and pasting it into another image</li>
        <li>Changing a document photograph — such as altering the amount on a receipt</li>
        <li>Placing someone at a different location or time than they were actually at</li>
    </ul>
    <p style="color:#8b949e; font-size:14px; line-height:1.8; margin-top:10px;">
    With modern tools like Photoshop, GIMP, or AI image generators, it has become very easy to
    create fake images that look completely real. This is a serious problem in news media, legal
    evidence, social media, and security applications.
    </p>
    </div>
    """, unsafe_allow_html=True)

    # ---- What does this system do? ----
    st.markdown("""
    <div class="forensic-card">
    <h3>🔍 What Does This System Do?</h3>
    <p style="color:#e6edf3; font-size:15px; line-height:1.9;">
    This system is a <strong>Digital Image Forensics Tool</strong>. Think of it like a detective
    that examines a photograph for hidden clues that prove it was edited. It uses multiple
    techniques to look for signs of tampering:
    </p>
    </div>
    """, unsafe_allow_html=True)

    a1, a2 = st.columns(2)
    with a1:
        st.markdown("""
        <div class="forensic-card">
        <h3>1️⃣ Error Level Analysis (ELA)</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.8;">
        JPEG images use a process called "compression" to make files smaller. Every time a JPEG
        is saved, it loses a tiny bit of quality. If someone edits part of the image and saves it
        again, that edited part will have been compressed a <em>different number of times</em>
        compared to the rest of the image.
        <br><br>
        ELA makes this difference <strong>visible</strong> by highlighting regions with inconsistent
        compression. A deep-learning model (DenseNet121) trained on thousands of real and tampered
        images then classifies whether the image is authentic or has been manipulated.
        </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="forensic-card">
        <h3>3️⃣ Copy-Move Detection</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.8;">
        One common trick in image forgery is to <strong>copy a part of the image and paste it
        elsewhere</strong> in the same image — for example, to hide an object by covering it with
        another part of the background.
        <br><br>
        This system divides the image into small blocks and computes a digital fingerprint for each
        block. If the same fingerprint appears in more than one place, it suggests that a region was
        duplicated — a sign of copy-move forgery.
        </p>
        </div>
        """, unsafe_allow_html=True)

    with a2:
        st.markdown("""
        <div class="forensic-card">
        <h3>2️⃣ Metadata & Weather Validation</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.8;">
        Every photo taken by a smartphone or digital camera contains hidden information called
        <strong>EXIF metadata</strong>. This includes:
        </p>
        <ul style="color:#8b949e; font-size:14px; line-height:1.9; padding-left:18px;">
            <li>The exact date and time the photo was taken</li>
            <li>The GPS location (latitude and longitude)</li>
            <li>The camera make and model</li>
            <li>The software used to edit it (e.g., "Adobe Photoshop")</li>
        </ul>
        <p style="color:#8b949e; font-size:14px; line-height:1.8; margin-top:8px;">
        Using the GPS and time data, this system queries a historical weather database to find out
        what the weather <em>actually was</em> at that location on that day. A separate CNN model
        then examines what weather <em>looks like</em> in the image. If the two don't match — the
        image may be from a different place or time than the metadata claims.
        </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="forensic-card">
        <h3>4️⃣ Cryptographic File Integrity</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.8;">
        A <strong>cryptographic hash</strong> is like a unique fingerprint of a file. This system
        computes the <em>MD5</em> and <em>SHA-256</em> hashes of the image. If even a single pixel
        is changed, these hash values will be completely different.
        <br><br>
        This is useful for proving that an image file has not been altered since it was originally
        captured — an important requirement in legal and evidentiary contexts.
        </p>
        </div>
        """, unsafe_allow_html=True)

    # ---- Who is this for? ----
    st.markdown("""
    <div class="forensic-card">
    <h3>👥 Who Can Use This System?</h3>
    <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-top:12px;">
        <div style="background:#0d1117; border-radius:8px; padding:16px; text-align:center;">
            <div style="font-size:32px;">🕵️</div>
            <div style="font-weight:700; margin:8px 0; color:#e6edf3;">Law Enforcement</div>
            <div style="color:#8b949e; font-size:13px;">Verify authenticity of photographic evidence in investigations</div>
        </div>
        <div style="background:#0d1117; border-radius:8px; padding:16px; text-align:center;">
            <div style="font-size:32px;">📰</div>
            <div style="font-weight:700; margin:8px 0; color:#e6edf3;">Journalists</div>
            <div style="color:#8b949e; font-size:13px;">Fact-check images before publishing news articles</div>
        </div>
        <div style="background:#0d1117; border-radius:8px; padding:16px; text-align:center;">
            <div style="font-size:32px;">🏦</div>
            <div style="font-weight:700; margin:8px 0; color:#e6edf3;">Insurance & Banking</div>
            <div style="color:#8b949e; font-size:13px;">Detect fraudulent document or claim photographs</div>
        </div>
    </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Technical Details ----
    with st.expander("🧑‍💻 Technical Details (for advanced readers)"):
        st.markdown("""
        **Technology Stack:**
        - **Python 3.10** — primary programming language
        - **Streamlit** — web application framework
        - **TensorFlow / Keras** — deep learning inference
        - **DenseNet121** — ELA classification model (trained on CASIA 2.0 dataset)
        - **Custom CNN** — weather classification model
        - **OpenCV** — image processing
        - **Pillow (PIL)** — image manipulation and ELA generation
        - **piexif** — EXIF metadata parsing
        - **geopy** — reverse geocoding (GPS coordinates → location name)
        - **Open-Meteo ERA5 API** — historical weather data retrieval

        **ELA Model Training:**
        - Dataset: CASIA 2.0 (real and tampered JPEG images)
        - Architecture: DenseNet121 with custom classification head
        - Train Accuracy: 98.34% | Validation: 93.78% | Test: 87.24%

        **Weather CNN Training:**
        - Dataset: Custom-collected dataset (1,804 training / 451 validation images)
        - Categories: Lightning, Rainy, Snow, Sunny
        - Train Accuracy: 91.2% | Validation: 81.6% | Test: 73.4%

        **Forensic Pipeline:**
        1. Image uploaded → saved to disk
        2. Cryptographic hashes computed (MD5 + SHA-256)
        3. ELA image generated at quality 90 → resized to 128×128 → DenseNet121 inference
        4. Multi-quality ELA (70, 80, 90) for robustness
        5. EXIF metadata extracted and parsed via piexif
        6. Noise variance computed across 3×3 image grid (Laplacian variance)
        7. JPEG quantization table analysis for double-compression detection
        8. Block-hash based copy-move detection
        9. (Optional) GPS + datetime → Open-Meteo API → weather validation + CNN comparison
        10. Overall verdict computed from weighted tamper signals
        11. Downloadable forensic report generated
        """)

    # ---- Project Info ----
    st.markdown("""
    <div class="forensic-card" style="margin-top:20px;">
    <h3>📌 Project Information</h3>
    <table style="color:#8b949e; font-size:14px; border-collapse:collapse; width:100%;">
        <tr><td style="padding:8px 0; color:#e6edf3; width:200px;"><strong>Project Title</strong></td>
            <td>Digital Image Forensics System for Tampering Detection</td></tr>
        <tr><td style="padding:8px 0; color:#e6edf3;"><strong>Student</strong></td>
            <td>Kumar Verma</td></tr>
        <tr><td style="padding:8px 0; color:#e6edf3;"><strong>Programme</strong></td>
            <td>Master of Computer Applications (MCA) — Final Year</td></tr>
        <tr><td style="padding:8px 0; color:#e6edf3;"><strong>University</strong></td>
            <td>Chandigarh University</td></tr>
        <tr><td style="padding:8px 0; color:#e6edf3;"><strong>Academic Year</strong></td>
            <td>2024-25</td></tr>
        <tr><td style="padding:8px 0; color:#e6edf3;"><strong>Project Type</strong></td>
            <td>Major Project — MCA Final Year</td></tr>
    </table>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# TAB 4: HOW IT WORKS
# ============================================================
with tab_how:
    st.markdown("""
    <div class="hero-title">How It Works</div>
    <div class="hero-subtitle">A step-by-step guide to the forensic analysis process</div>
    """, unsafe_allow_html=True)

    # Step-by-step process
    steps = [
        ("1", "📤 Upload Your Image",
         "Go to the **Analyze Image** tab and upload any JPEG photograph you want to check. "
         "The image is processed entirely on the server — nothing is stored permanently."),
        ("2", "🔐 Cryptographic Hashing",
         "The system immediately computes **MD5** and **SHA-256** hash fingerprints of your image. "
         "These values uniquely identify the exact file. Any modification — even a single pixel — "
         "will produce a completely different hash."),
        ("3", "⚡ Error Level Analysis",
         "The image is re-compressed at JPEG quality 90, and the **pixel-wise difference** between "
         "the original and re-compressed version is computed. This difference map (ELA image) is fed "
         "into a **DenseNet121** neural network trained on real and tampered images. The model outputs "
         "a prediction of whether the image is **Real** or **Tampered** with a confidence score."),
        ("4", "📋 EXIF Metadata Extraction",
         "All EXIF metadata embedded in the image is extracted and displayed. Special attention is "
         "paid to the **Software** field — tools like Adobe Photoshop leave their name here when "
         "they save a file, which is a direct indicator of post-processing."),
        ("5", "🌦️ Weather Validation (Optional)",
         "If GPS coordinates and a timestamp are present in the EXIF data, the system queries the "
         "**Open-Meteo ERA5 historical weather API** to retrieve what the weather was at that "
         "exact location and time. A **Weather CNN** model then independently classifies the "
         "weather visible in the image. A mismatch between the two is a red flag."),
        ("6", "🔍 Additional Forensic Checks",
         "Three additional checks are performed: (a) **Noise analysis** across a 3×3 image grid to "
         "detect splicing artefacts, (b) **JPEG quantization table analysis** to detect double "
         "compression from re-saving after editing, and (c) **Copy-move detection** using block "
         "fingerprinting to find duplicated regions within the image."),
        ("7", "📊 Overall Verdict",
         "All forensic signals are combined to produce a final verdict: **Likely Tampered**, "
         "**Appears Authentic**, or **Uncertain — Manual Review Recommended**. The number of "
         "active tamper signals (out of 5) is also displayed."),
        ("8", "📄 Download Report",
         "A complete forensic analysis report can be downloaded as a plain-text file. It contains "
         "all results, hashes, EXIF data, noise statistics, and the final verdict — suitable for "
         "submission or documentation purposes."),
    ]

    for num, title, desc in steps:
        st.markdown(f"""
        <div class="forensic-card" style="display:flex; gap:20px; align-items:flex-start;">
            <div style="
                min-width:44px; height:44px; border-radius:50%;
                background:linear-gradient(135deg,#00d4aa,#00a884);
                display:flex; align-items:center; justify-content:center;
                font-size:18px; font-weight:800; color:#0d1117; flex-shrink:0;
            ">{num}</div>
            <div>
                <div style="font-size:16px; font-weight:700; color:#e6edf3; margin-bottom:6px;">{title}</div>
                <div style="font-size:14px; color:#8b949e; line-height:1.8;">{desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ELA visual explanation
    with st.expander("📸 Visual Example: What does ELA look like?"):
        st.markdown("""
        ELA (Error Level Analysis) re-compresses the image at a fixed quality and measures the
        difference. **Bright = high error = suspicious.** **Dark = low error = normal.**
        """)
        col1, col2 = st.columns(2)
        with col1:
            if os.path.exists("rsc/real.jpg"):
                # use_container_width replaces deprecated use_column_width
                st.image("rsc/real.jpg",
                         caption="✅ ELA of a REAL Image — dark and uniform across the whole image",
                         width='stretch')
        with col2:
            if os.path.exists("rsc/fake.jpg"):
                st.image("rsc/fake.jpg",
                         caption="⚠️ ELA of a TAMPERED Image — bright patches show where editing happened",
                         width='stretch')
        st.markdown("""
        > **Simple explanation:** Think of ELA like an X-ray for photos.
        > A genuine photo looks **dark and even** everywhere.
        > A tampered photo shows **bright white or yellow spots** exactly where someone made edits.
        > Those bright spots are the "fingerprints" left behind by editing software.
        """)

    # Limitations
    st.markdown("""
    <div class="forensic-card" style="margin-top:20px; border-color:#ffa500;">
    <h3>⚠️ Limitations & Disclaimer</h3>
    <ul style="color:#8b949e; font-size:14px; line-height:2.0; padding-left:20px;">
        <li>This system is designed for <strong>academic and educational purposes</strong>. Results should not be used as sole legal evidence.</li>
        <li>ELA may produce false positives for images that have been downloaded and re-uploaded multiple times (each re-upload can cause re-compression).</li>
        <li>Weather validation only works for images with GPS EXIF data. Many smartphones and social media platforms strip GPS data for privacy.</li>
        <li>Copy-move detection is a heuristic method and may flag repetitive textures (sky, grass, walls) as suspicious even in authentic images.</li>
        <li>Advanced AI-generated or professionally retouched images may evade some detection methods.</li>
        <li>Always combine automated analysis with expert human review for critical decisions.</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
