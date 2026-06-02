"""
src/device_utils.py — Cross-platform PyTorch device auto-detection.

Tries each accelerator in order and returns the best one that actually works:
  1. CUDA  — Linux/Windows with a working NVIDIA GPU + matching PyTorch build
  2. MPS   — macOS Apple Silicon (M1/M2/M3)
  3. CPU   — universal fallback (also used on macOS Intel and this machine's
             P2000 which has a CUDA architecture mismatch with the installed
             PyTorch build)

Usage:
    from device_utils import get_device
    device = get_device()
    model = SentenceTransformer("...", device=device)
"""

import logging

logger = logging.getLogger(__name__)

_cached_device: str | None = None


def get_device() -> str:
    """
    Auto-detect the best available compute device.

    Returns one of: 'cuda', 'mps', 'cpu'

    The result is cached after the first call so repeated imports
    do not re-run the detection logic.
    """
    global _cached_device
    if _cached_device is not None:
        return _cached_device

    _cached_device = _detect_device()
    return _cached_device


def _detect_device() -> str:
    try:
        import torch
    except ImportError:
        logger.info("torch not installed — using cpu")
        return "cpu"

    # 1. Try CUDA — probe with an actual tensor to catch arch mismatches
    if torch.cuda.is_available():
        try:
            t = torch.tensor([1.0]).cuda()
            _ = t + t  # force an actual GPU op
            device_name = torch.cuda.get_device_name(0)
            logger.info("Device: cuda (%s)", device_name)
            print(f"[device_utils] Using CUDA: {device_name}")
            return "cuda"
        except Exception as exc:
            logger.warning("CUDA available but unusable (%s) — trying MPS/CPU", exc)

    # 2. Try MPS — Apple Silicon
    try:
        if torch.backends.mps.is_available():
            # Quick sanity check
            t = torch.tensor([1.0], device="mps")
            _ = t + t
            logger.info("Device: mps (Apple Silicon)")
            print("[device_utils] Using MPS (Apple Silicon)")
            return "mps"
    except Exception as exc:
        logger.warning("MPS check failed (%s) — falling back to CPU", exc)

    # 3. CPU fallback
    logger.info("Device: cpu")
    print("[device_utils] Using CPU")
    return "cpu"
