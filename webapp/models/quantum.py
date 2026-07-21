"""quantum.py — PennyLane circuit definitions for VQC, QKNN, and QSVM."""

import threading

import numpy as np
import pennylane as qml

N_QUBITS = 4
N_VQC_LAYERS = 3
N_QSVM_REPS = 2

try:
    import torch
    torch.manual_seed(42)
    _TORCH_AVAILABLE = True
except (ImportError, OSError):
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
    print("[quantum] WARNING: torch unavailable (not installed or DLL error) — VQC model will be disabled.")

_dev = qml.device("default.qubit", wires=N_QUBITS)
_VQC_INTERFACE = "torch" if _TORCH_AVAILABLE else "numpy"

# PennyLane's default.qubit device is NOT thread-safe: it maintains internal
# quantum state that is mutated during circuit execution. Concurrent calls to
# any qnode sharing the same device produce corrupted results. This lock
# serialises all device access so only one circuit executes at a time.
_dev_lock = threading.Lock()


@qml.qnode(_dev, interface=_VQC_INTERFACE)
def vqc_circuit(x, params) -> list:
    """VQC forward pass: AngleEmbedding + RY/RZ rotation layers + CNOT ring.

    Args:
        x: Angle-encoded input, shape (n_qubits,).
        params: Rotation parameters, shape (n_vqc_layers, n_qubits, 2).

    Returns:
        List of Pauli-Z expectation values, length n_qubits.
    """
    qml.AngleEmbedding(x, wires=range(N_QUBITS), rotation="Y")
    for layer in range(N_VQC_LAYERS):
        for i in range(N_QUBITS):
            qml.RY(params[layer, i, 0], wires=i)
            qml.RZ(params[layer, i, 1], wires=i)
        for i in range(N_QUBITS):
            qml.CNOT(wires=[i, (i + 1) % N_QUBITS])
    return [qml.expval(qml.PauliZ(i)) for i in range(N_QUBITS)]


@qml.qnode(_dev)
def fidelity_circuit(x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
    """QKNN fidelity circuit: |<ψ(x1)|ψ(x2)>|² via AngleEmbedding + adjoint.

    Args:
        x1: First sample, shape (n_qubits,), values in [0, π].
        x2: Second sample, shape (n_qubits,), values in [0, π].

    Returns:
        Probability distribution; probs[0] = F(x1, x2).
    """
    qml.AngleEmbedding(x1, wires=range(N_QUBITS), rotation="Y")
    qml.adjoint(qml.AngleEmbedding)(x2, wires=range(N_QUBITS), rotation="Y")
    return qml.probs(wires=range(N_QUBITS))


def _iqp_feature_map(x: np.ndarray) -> None:
    """IQP feature map: Hadamard + RZ single-qubit phase + ZZ nearest-neighbor interactions.

    Applied N_QSVM_REPS times. Matches the Havlíček et al. kernel used in the QSVM notebook.

    Args:
        x: Input vector, shape (n_qubits,), values in [0, π].
    """
    for _ in range(N_QSVM_REPS):
        for i in range(N_QUBITS):
            qml.Hadamard(wires=i)
            qml.RZ(x[i], wires=i)
        for i in range(N_QUBITS - 1):
            qml.CNOT(wires=[i, i + 1])
            qml.RZ(x[i] * x[i + 1], wires=i + 1)
            qml.CNOT(wires=[i, i + 1])


@qml.qnode(_dev)
def qsvm_kernel_circuit(x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
    """QSVM IQP kernel circuit: K(x1, x2) = |<φ(x1)|φ(x2)>|².

    Args:
        x1: First sample, shape (n_qubits,), values in [0, π].
        x2: Second sample, shape (n_qubits,), values in [0, π].

    Returns:
        Probability distribution; probs[0] = K(x1, x2).
    """
    _iqp_feature_map(x1)
    qml.adjoint(_iqp_feature_map)(x2)
    return qml.probs(wires=range(N_QUBITS))


def vqc_predict(x, params):
    """Thread-safe VQC forward pass. Returns raw qnode output."""
    with _dev_lock:
        return vqc_circuit(x, params)


def quantum_fidelity(x1: np.ndarray, x2: np.ndarray) -> float:
    """Scalar QKNN fidelity F(x1, x2) = probs[0] of the fidelity circuit."""
    with _dev_lock:
        return float(fidelity_circuit(x1, x2)[0])


def quantum_kernel(x1: np.ndarray, x2: np.ndarray) -> float:
    """Scalar QSVM kernel K(x1, x2) = probs[0] of the IQP kernel circuit."""
    with _dev_lock:
        return float(qsvm_kernel_circuit(x1, x2)[0])
