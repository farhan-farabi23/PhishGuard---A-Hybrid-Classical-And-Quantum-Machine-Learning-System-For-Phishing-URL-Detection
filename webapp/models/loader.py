"""models/loader.py — Train all 9 PhishGuard models at startup and serve predictions."""

import logging
import os
import re
import threading
import time
from typing import Any

import numpy as np
import pandas as pd
import nltk
from nltk.tokenize import RegexpTokenizer
from nltk.stem import SnowballStemmer

from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import TruncatedSVD, PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import LinearSVC, SVC
from sklearn.ensemble import RandomForestClassifier

from models.quantum import (
    _TORCH_AVAILABLE,
    vqc_predict as _vqc_predict,
    quantum_fidelity as _quantum_fidelity,
    quantum_kernel as _quantum_kernel,
)

if _TORCH_AVAILABLE:
    import torch
else:
    torch = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Download NLTK data at import time; suppress network errors gracefully.
try:
    nltk.download("punkt", quiet=True)
    nltk.download("punkt_tab", quiet=True)
except Exception:
    pass

# ---------------------------------------------------------------------------
# __file__-relative paths — independent of the shell's working directory.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))   # webapp/models/
_ROOT = os.path.dirname(os.path.dirname(_HERE))       # project root

LOADER_CONFIG = {
    "data_path":           os.path.join(_ROOT, "models", "preprocessing", "processed_data.csv"),
    "sample_size":         5000,
    "test_size":           0.2,
    "random_state":        42,
    "max_tfidf_features":  50000,
    "svd_components":      200,
    "svd_q_components":    50,
    "n_pca_components":    4,
    "n_qubits":            4,
    "n_vqc_layers":        3,
    "knn_k":               3,
    "qknn_k":              5,
    "qsvm_train_size":     500,
    "qsvm_n_reps":         2,
    "svm_c":               1.0,
    "rf_estimators":       100,
    "mlp_hidden":          (100,),
    "vqc_weights_path":    os.path.join(_ROOT, "models", "quantum", "vqc",  "result", "vqc_weights.npy"),
    "qsvm_kernel_path":    os.path.join(_ROOT, "models", "quantum", "qsvm", "result", "kernel_matrix_train.npy"),
    # Labels saved by generate_qsvm_labels.py — must match the kernel matrix rows.
    "qsvm_labels_path":    os.path.join(_ROOT, "models", "quantum", "qsvm", "result", "y_qsvm_train.npy"),
}

MAX_URL_LENGTH = 2048

# ---------------------------------------------------------------------------
# Text preprocessing helpers
# ---------------------------------------------------------------------------

_tokenizer = RegexpTokenizer(r"[A-Za-z0-9]+")
_stemmer = SnowballStemmer("english")


def preprocess_url_text(url: str) -> str:
    tokens = _tokenizer.tokenize(url.lower())
    return " ".join(_stemmer.stem(t) for t in tokens)


def extract_url_features(url: str) -> list[float]:
    return [
        len(url),
        url.count("."),
        sum(c.isdigit() for c in url),
        sum(c in "@-_=?&" for c in url),
        1.0 if re.search(r"\d+\.\d+\.\d+\.\d+", url) else 0.0,
        float(max(0, len(url.split("/")[2].split(".")) - 2)) if "//" in url else 0.0,
    ]


# ---------------------------------------------------------------------------
# Module-level state (populated by initialize())
# ---------------------------------------------------------------------------

_tfidf: TfidfVectorizer | None = None
_svd: TruncatedSVD | None = None
_scaler: StandardScaler | None = None
_svd_q: TruncatedSVD | None = None
_scaler_q: StandardScaler | None = None
_pca: PCA | None = None
_angle_scaler: MinMaxScaler | None = None

_models: dict[str, Any] = {}
_svm_qsvm: SVC | None = None
_vqc_params = None
_x_qknn_train: np.ndarray | None = None
_y_qknn_train: np.ndarray | None = None
_x_qsvm_train: np.ndarray | None = None
_y_qsvm_train: np.ndarray | None = None

_initialized: bool = False

# Prevents two threads from running initialize() simultaneously.
_init_lock = threading.Lock()


def is_initialized() -> bool:
    """Return True if initialize() has completed successfully."""
    return _initialized


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------

def initialize() -> None:
    """Train all 9 phishing detection models and fit the full preprocessing pipeline."""
    global _tfidf, _svd, _scaler, _svd_q, _scaler_q, _pca, _angle_scaler
    global _models, _svm_qsvm, _vqc_params
    global _x_qknn_train, _y_qknn_train, _x_qsvm_train, _y_qsvm_train
    global _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:  # Double-checked locking: re-test after acquiring the lock
            return

        # ------------------------------------------------------------------
        # Step 1 — Load & sample data
        # ------------------------------------------------------------------
        data_path = LOADER_CONFIG["data_path"]
        if not os.path.exists(data_path):
            raise FileNotFoundError(
                f"[loader] Dataset not found: {data_path}\n"
                "Run preprocessing-dataset/data_preprocessing.ipynb first."
            )

        logger.info("Loading data...")
        df_full = pd.read_csv(data_path)
        df, _ = train_test_split(
            df_full,
            train_size=LOADER_CONFIG["sample_size"],
            random_state=LOADER_CONFIG["random_state"],
            stratify=df_full["Label"],
        )
        df = df.reset_index(drop=True)

        # ------------------------------------------------------------------
        # Step 2 — Extract URL features (each row independently, no leakage)
        # ------------------------------------------------------------------
        url_features = np.array(
            [extract_url_features(str(u)) for u in df["URL"].fillna("")]
        )

        # ------------------------------------------------------------------
        # Step 3 — 80/20 stratified train/test split
        # ------------------------------------------------------------------
        logger.info("Fitting preprocessing pipeline...")
        (
            x_train_text, x_test_text,
            url_feats_train, url_feats_test,
            y_train, y_test,
        ) = train_test_split(
            df["processed_text"].fillna("").astype(str).values,
            url_features,
            df["Label"].values,
            test_size=LOADER_CONFIG["test_size"],
            random_state=LOADER_CONFIG["random_state"],
            stratify=df["Label"].values,
        )

        # ------------------------------------------------------------------
        # Step 4 — Fit TF-IDF on training text only
        # ------------------------------------------------------------------
        _tfidf = TfidfVectorizer(
            sublinear_tf=True,
            min_df=2,
            max_features=LOADER_CONFIG["max_tfidf_features"],
        )
        X_tfidf_train = _tfidf.fit_transform(x_train_text)
        X_tfidf_test = _tfidf.transform(x_test_text)

        # ------------------------------------------------------------------
        # Step 5 — SVD-200 on training TF-IDF (classical path)
        # ------------------------------------------------------------------
        _svd = TruncatedSVD(
            n_components=LOADER_CONFIG["svd_components"],
            random_state=LOADER_CONFIG["random_state"],
        )
        X_svd_train = _svd.fit_transform(X_tfidf_train)
        X_svd_test = _svd.transform(X_tfidf_test)

        # ------------------------------------------------------------------
        # Step 6 — Combine SVD-200 + 6 URL features → StandardScaler
        # ------------------------------------------------------------------
        X_combined_train = np.hstack([X_svd_train, url_feats_train])
        X_combined_test = np.hstack([X_svd_test, url_feats_test])

        _scaler = StandardScaler()
        X_scaled_train = _scaler.fit_transform(X_combined_train)
        X_scaled_test = _scaler.transform(X_combined_test)

        # ------------------------------------------------------------------
        # Step 7 — Train 6 classical models
        # NB uses raw TF-IDF directly — SVD can produce negative values which
        # violate ComplementNB's non-negative input requirement.
        # ------------------------------------------------------------------
        classical_specs: dict[str, Any] = {
            "knn":    KNeighborsClassifier(n_neighbors=LOADER_CONFIG["knn_k"]),
            "logreg": LogisticRegression(
                          max_iter=1000,
                          class_weight="balanced",
                          random_state=LOADER_CONFIG["random_state"],
                      ),
            "nb":     ComplementNB(),
            "svm":    CalibratedClassifierCV(
                          LinearSVC(
                              C=LOADER_CONFIG["svm_c"],
                              max_iter=2000,
                              class_weight="balanced",
                              random_state=LOADER_CONFIG["random_state"],
                          )
                      ),
            "rf":     RandomForestClassifier(
                          n_estimators=LOADER_CONFIG["rf_estimators"],
                          class_weight="balanced",
                          random_state=LOADER_CONFIG["random_state"],
                      ),
            "mlp":    MLPClassifier(
                          hidden_layer_sizes=LOADER_CONFIG["mlp_hidden"],
                          max_iter=300,
                          random_state=LOADER_CONFIG["random_state"],
                      ),
        }

        _models = {}
        for name, clf in classical_specs.items():
            if name == "nb":
                clf.fit(X_tfidf_train, y_train)
                preds = clf.predict(X_tfidf_test)
            else:
                clf.fit(X_scaled_train, y_train)
                preds = clf.predict(X_scaled_test)
            _models[name] = clf
            logger.info("%s accuracy: %.4f", name, accuracy_score(y_test, preds))

        # ------------------------------------------------------------------
        # Step 8 — Quantum preprocessing pipeline (SVD-50 branch)
        # ------------------------------------------------------------------
        _svd_q = TruncatedSVD(
            n_components=LOADER_CONFIG["svd_q_components"],
            random_state=LOADER_CONFIG["random_state"],
        )
        X_svd_q_train = _svd_q.fit_transform(X_tfidf_train)

        X_q_combined_train = np.hstack([X_svd_q_train, url_feats_train])

        _scaler_q = StandardScaler()
        X_q_scaled_train = _scaler_q.fit_transform(X_q_combined_train)

        _pca = PCA(
            n_components=LOADER_CONFIG["n_pca_components"],
            random_state=LOADER_CONFIG["random_state"],
        )
        X_pca_train = _pca.fit_transform(X_q_scaled_train)

        _angle_scaler = MinMaxScaler(feature_range=(0, float(np.pi)))
        X_angles_train = _angle_scaler.fit_transform(X_pca_train)

        # ------------------------------------------------------------------
        # Step 9 — Build QKNN training subset (500 stratified samples)
        # ------------------------------------------------------------------
        y_train_encoded = np.where(y_train == "bad", 1.0, 0.0)

        idx_q, _ = train_test_split(
            np.arange(len(X_angles_train)),
            train_size=LOADER_CONFIG["qsvm_train_size"],
            random_state=LOADER_CONFIG["random_state"],
            stratify=y_train,
        )
        _x_qknn_train = X_angles_train[idx_q]
        _y_qknn_train = y_train_encoded[idx_q]

        # ------------------------------------------------------------------
        # Step 10 — Load pre-computed QSVM kernel matrix and fit SVC.
        # ------------------------------------------------------------------
        K_train = np.load(LOADER_CONFIG["qsvm_kernel_path"])

        labels_path = LOADER_CONFIG["qsvm_labels_path"]
        if os.path.exists(labels_path):
            _y_qsvm_train = np.load(labels_path)
            logger.info("QSVM: loaded %d offline labels from disk.", len(_y_qsvm_train))
        else:
            _y_qsvm_train = _y_qknn_train
            logger.warning(
                "y_qsvm_train.npy not found — QSVM will use live labels "
                "which may not match the offline kernel matrix. "
                "Run generate_qsvm_labels.py once to fix this."
            )

        _x_qsvm_train = _x_qknn_train

        _svm_qsvm = SVC(
            kernel="precomputed",
            C=LOADER_CONFIG["svm_c"],
            random_state=LOADER_CONFIG["random_state"],
        )
        _svm_qsvm.fit(K_train, _y_qsvm_train)
        logger.info("QSVM: %s support vectors", _svm_qsvm.n_support_)

        # ------------------------------------------------------------------
        # Step 11 — Load VQC weights
        # ------------------------------------------------------------------
        if _TORCH_AVAILABLE:
            vqc_path = LOADER_CONFIG["vqc_weights_path"]
            if os.path.exists(vqc_path):
                vqc_weights = np.load(vqc_path)
                _vqc_params = torch.tensor(vqc_weights, dtype=torch.float32)
                logger.info("VQC weights loaded.")
            else:
                logger.warning("VQC weights not found at %s — VQC disabled.", vqc_path)
        else:
            logger.info("VQC skipped (torch unavailable).")

        logger.info("All models ready.")
        _initialized = True


# ---------------------------------------------------------------------------
# predict_all()
# ---------------------------------------------------------------------------

def predict_all(url: str, include_quantum: bool = True) -> dict[str, Any]:
    """Run phishing detection models on a single URL.

    Args:
        url: Raw URL string to classify (max MAX_URL_LENGTH chars).
        include_quantum: When False, skip VQC, QKNN, and QSVM.

    Returns:
        Dict with one entry per model (verdict, confidence, time_ms),
        a url_features summary, and an ensemble verdict with confidence.

    Raises:
        RuntimeError: If initialize() has not been called first.
        ValueError: If url exceeds MAX_URL_LENGTH.
    """
    if not _initialized:
        raise RuntimeError("Call loader.initialize() first")
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")

    results: dict[str, Any] = {}

    # Shared preprocessing
    text = preprocess_url_text(url)
    url_feats = extract_url_features(url)
    tfidf_vec = _tfidf.transform([text])

    # Classical feature vector: SVD-200 + 6 URL features → StandardScaler
    svd_feat = _svd.transform(tfidf_vec)
    combined = np.hstack([svd_feat, np.array(url_feats).reshape(1, -1)])
    scaled = _scaler.transform(combined)

    # ------------------------------------------------------------------
    # Classical models
    # ------------------------------------------------------------------
    classical_inputs: dict[str, Any] = {
        "knn":    scaled,
        "logreg": scaled,
        "nb":     tfidf_vec,
        "svm":    scaled,
        "rf":     scaled,
        "mlp":    scaled,
    }
    for name in ("knn", "logreg", "nb", "svm", "rf", "mlp"):
        t0 = time.monotonic()
        proba = _models[name].predict_proba(classical_inputs[name])
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        classes = list(_models[name].classes_)
        bad_prob = float(proba[0][classes.index("bad")])
        verdict = "bad" if bad_prob >= 0.5 else "good"
        confidence = round(max(bad_prob, 1.0 - bad_prob), 4)
        results[name] = {"verdict": verdict, "confidence": confidence, "time_ms": elapsed_ms}

    # ------------------------------------------------------------------
    # Quantum models (skipped when include_quantum=False)
    # ------------------------------------------------------------------
    if include_quantum:
        svd_q_feat = _svd_q.transform(tfidf_vec)
        q_combined = np.hstack([svd_q_feat, np.array(url_feats).reshape(1, -1)])
        q_scaled = _scaler_q.transform(q_combined)
        pca_feat = _pca.transform(q_scaled)
        angles = _angle_scaler.transform(pca_feat)[0]

        # VQC
        if _TORCH_AVAILABLE and _vqc_params is not None:
            t0 = time.monotonic()
            xi = torch.tensor(angles, dtype=torch.float32)
            with torch.no_grad():
                out = torch.stack(list(_vqc_predict(xi, _vqc_params)))
            logit = out.mean().item()
            vqc_elapsed = int((time.monotonic() - t0) * 1000)
            # Convention: PauliZ mean < 0 → "bad" (verified against training notebook).
            vqc_verdict = "bad" if logit < 0 else "good"
            vqc_conf = round(float(abs(torch.sigmoid(out.mean()).item() - 0.5) * 2), 4)
            results["vqc"] = {"verdict": vqc_verdict, "confidence": vqc_conf, "time_ms": vqc_elapsed}
        else:
            results["vqc"] = None

        # QKNN: fidelity-based majority vote over top-k training samples
        t0 = time.monotonic()
        fidelities = [_quantum_fidelity(angles, train_pt) for train_pt in _x_qknn_train]
        top_k_idx = np.argsort(fidelities)[-LOADER_CONFIG["qknn_k"]:]
        votes = _y_qknn_train[top_k_idx]
        qknn_verdict = "bad" if votes.mean() >= 0.5 else "good"
        qknn_conf = round(float(abs(votes.mean() - 0.5) * 2), 4)
        qknn_elapsed = int((time.monotonic() - t0) * 1000)
        results["qknn"] = {"verdict": qknn_verdict, "confidence": qknn_conf, "time_ms": qknn_elapsed}

        # QSVM: compute kernel row against training samples, then SVC decision
        t0 = time.monotonic()
        k_row = np.array([_quantum_kernel(angles, tr) for tr in _x_qsvm_train])
        K_new = k_row.reshape(1, -1)
        pred = _svm_qsvm.predict(K_new)[0]
        qsvm_verdict = "bad" if pred == 1 else "good"
        qsvm_conf = round(float(np.clip(abs(_svm_qsvm.decision_function(K_new)[0]), 0, 1)), 4)
        qsvm_elapsed = int((time.monotonic() - t0) * 1000)
        results["qsvm"] = {"verdict": qsvm_verdict, "confidence": qsvm_conf, "time_ms": qsvm_elapsed}
    else:
        results["vqc"] = None
        results["qknn"] = None
        results["qsvm"] = None

    # ------------------------------------------------------------------
    # URL feature summary
    # ------------------------------------------------------------------
    results["url_features"] = {
        "length":          int(url_feats[0]),
        "dots":            int(url_feats[1]),
        "digits":          int(url_feats[2]),
        "special_chars":   int(url_feats[3]),
        "has_ip":          int(url_feats[4]),
        "subdomain_depth": int(url_feats[5]),
    }

    # ------------------------------------------------------------------
    # Ensemble: majority vote + average confidence over active models
    # ------------------------------------------------------------------
    active_keys = ["knn", "logreg", "nb", "svm", "rf", "mlp"]
    if include_quantum:
        active_keys += ["vqc", "qknn", "qsvm"]
    active_keys = [k for k in active_keys if results.get(k) is not None]

    total_models = len(active_keys)
    bad_votes = sum(1 for k in active_keys if results[k]["verdict"] == "bad")
    avg_confidence = round(
        sum(results[k]["confidence"] for k in active_keys) / total_models, 4
    ) if total_models else 0.0

    results["ensemble"] = {
        "verdict":        "bad" if bad_votes > total_models / 2 else "good",
        "phishing_votes": bad_votes,
        "total_models":   total_models,
        "confidence":     avg_confidence,
    }

    return results


# ---------------------------------------------------------------------------
# get_angles_for_url() — used by /api/circuit (quantum visualizer)
# ---------------------------------------------------------------------------

def get_angles_for_url(url: str) -> np.ndarray:
    """Compute the 4 PCA angle-encoded features for a URL.

    Args:
        url: Raw URL string.

    Returns:
        Array of shape (4,) with angles in [0, π].

    Raises:
        RuntimeError: If initialize() has not been called first.
    """
    if not _initialized:
        raise RuntimeError("Call loader.initialize() first")
    text = preprocess_url_text(url)
    url_feats = extract_url_features(url)
    tfidf_vec = _tfidf.transform([text])
    svd_q_feat = _svd_q.transform(tfidf_vec)
    q_combined = np.hstack([svd_q_feat, np.array(url_feats).reshape(1, -1)])
    q_scaled = _scaler_q.transform(q_combined)
    pca_feat = _pca.transform(q_scaled)
    angles = _angle_scaler.transform(pca_feat)[0]
    return angles
