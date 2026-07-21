"""generate_qsvm_labels.py — One-time script to save y_qsvm_train.npy.

Run this ONCE from the project root (or webapp/) before starting the server:

    python webapp/generate_qsvm_labels.py

WHY THIS EXISTS
---------------
The precomputed kernel_matrix_train.npy (500×500) was built offline in the
QSVM notebook from a specific 500-sample subset.  The web app retrains on a
5 000-row live sample and cannot reproduce the exact same 500 rows, causing a
kernel/label mismatch (audit issue ML-01 / B-01).

This script reproduces the full-dataset preprocessing pipeline that the
offline notebook used, takes the same stratified 500-sample subset (using the
same random_state=42), and saves the corresponding labels.  The saved
y_qsvm_train.npy is then loaded by loader.py at startup so the QSVM trains
with labels that actually match the kernel matrix rows.

REQUIREMENTS
------------
- processed_data.csv must exist at models/preprocessing/processed_data.csv
- The QSVM notebook must have used random_state=42 for its sampling (the
  default in all PhishGuard notebooks).
"""

import os
import sys
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD, PCA
from sklearn.preprocessing import StandardScaler, MinMaxScaler

# ---------------------------------------------------------------------------
# Paths (resolved relative to this script's location)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_SCRIPT_DIR)

DATA_PATH   = os.path.join(_ROOT, "models", "preprocessing", "processed_data.csv")
OUTPUT_PATH = os.path.join(_ROOT, "models", "quantum", "qsvm", "result", "y_qsvm_train.npy")

RANDOM_STATE    = 42
SVD_Q_COMPONENTS = 50
N_PCA_COMPONENTS  = 4
QSVM_TRAIN_SIZE  = 500
TEST_SIZE        = 0.2


def main():
    if not os.path.exists(DATA_PATH):
        print(f"ERROR: Dataset not found at {DATA_PATH}")
        print("Run the preprocessing notebook first.")
        sys.exit(1)

    print(f"Loading full dataset from {DATA_PATH} ...")
    df = pd.read_csv(DATA_PATH)
    print(f"  Rows: {len(df):,}")

    # URL features
    def extract_url_features(url):
        import re
        url = str(url)
        return [
            len(url),
            url.count("."),
            sum(c.isdigit() for c in url),
            sum(c in "@-_=?&" for c in url),
            1.0 if re.search(r"\d+\.\d+\.\d+\.\d+", url) else 0.0,
            float(max(0, len(url.split("/")[2].split(".")) - 2)) if "//" in url else 0.0,
        ]

    url_features = np.array(
        [extract_url_features(u) for u in df["URL"].fillna("")]
    )

    # 80/20 split — must use the same parameters as the QSVM notebook
    print("Splitting data ...")
    (
        x_train_text, _,
        url_feats_train, _,
        y_train, _,
    ) = train_test_split(
        df["processed_text"].fillna("").astype(str).values,
        url_features,
        df["Label"].values,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=df["Label"].values,
    )

    # TF-IDF → SVD-50 → + 6 URL features → StandardScaler → PCA-4 → MinMaxScaler
    print("Fitting quantum preprocessing pipeline ...")
    tfidf = TfidfVectorizer(sublinear_tf=True, min_df=2, max_features=50000)
    X_tfidf = tfidf.fit_transform(x_train_text)

    svd_q = TruncatedSVD(n_components=SVD_Q_COMPONENTS, random_state=RANDOM_STATE)
    X_svd_q = svd_q.fit_transform(X_tfidf)

    X_combined = np.hstack([X_svd_q, url_feats_train])

    scaler_q = StandardScaler()
    X_scaled = scaler_q.fit_transform(X_combined)

    pca = PCA(n_components=N_PCA_COMPONENTS, random_state=RANDOM_STATE)
    X_pca = pca.fit_transform(X_scaled)

    angle_scaler = MinMaxScaler(feature_range=(0, float(np.pi)))
    angle_scaler.fit_transform(X_pca)  # fit only

    # Take 500 stratified samples — same procedure as the QSVM notebook
    print(f"Selecting {QSVM_TRAIN_SIZE} stratified training samples ...")
    idx_q, _ = train_test_split(
        np.arange(len(y_train)),
        train_size=QSVM_TRAIN_SIZE,
        random_state=RANDOM_STATE,
        stratify=y_train,
    )

    y_qsvm = np.where(y_train[idx_q] == "bad", 1.0, 0.0)
    print(f"  Phishing: {int(y_qsvm.sum())}  |  Safe: {int((y_qsvm == 0).sum())}")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    np.save(OUTPUT_PATH, y_qsvm)
    print(f"\nSaved {len(y_qsvm)} labels -> {OUTPUT_PATH}")
    print("You can now start the Flask app. QSVM will load these labels automatically.")


if __name__ == "__main__":
    main()
