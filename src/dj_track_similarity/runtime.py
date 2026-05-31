from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from .analysis_config import normalize_analysis_device


@dataclass(frozen=True)
class TorchRuntimeInfo:
    python: str
    torch_installed: bool
    torch_version: str | None = None
    torch_cuda_build: str | None = None
    cuda_available: bool = False
    device_count: int = 0
    device_name: str | None = None
    nvidia_smi_cuda: str | None = None
    error: str | None = None


def select_torch_device(torch_module: Any, requested_device: str | None) -> str:
    requested = normalize_analysis_device(requested_device)
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not torch_module.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        return "cuda"
    return "cuda" if torch_module.cuda.is_available() else "cpu"


def get_torch_runtime_info() -> TorchRuntimeInfo:
    try:
        import torch
    except Exception as error:
        return TorchRuntimeInfo(
            python=sys.executable,
            torch_installed=False,
            nvidia_smi_cuda=_detect_nvidia_smi_cuda(),
            error=str(error),
        )

    cuda_available = bool(torch.cuda.is_available())
    device_count = int(torch.cuda.device_count()) if cuda_available else 0
    device_name = torch.cuda.get_device_name(0) if cuda_available and device_count else None
    return TorchRuntimeInfo(
        python=sys.executable,
        torch_installed=True,
        torch_version=str(getattr(torch, "__version__", "unknown")),
        torch_cuda_build=str(torch.version.cuda),
        cuda_available=cuda_available,
        device_count=device_count,
        device_name=device_name,
        nvidia_smi_cuda=_detect_nvidia_smi_cuda(),
    )


def recommended_torch_index(info: TorchRuntimeInfo) -> str | None:
    cuda_version = info.nvidia_smi_cuda or info.torch_cuda_build or ""
    major, minor = _parse_cuda_version(cuda_version)
    if major >= 13:
        return "https://download.pytorch.org/whl/cu130"
    if major == 12 and minor >= 8:
        return "https://download.pytorch.org/whl/cu128"
    if major == 12 and minor >= 6:
        return "https://download.pytorch.org/whl/cu126"
    if major:
        return "https://download.pytorch.org/whl/cu126"
    return None


def _detect_nvidia_smi_cuda() -> str | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        completed = subprocess.run([nvidia_smi], check=False, capture_output=True, text=True)
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    import re

    match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", completed.stdout)
    return match.group(1) if match else None


def _parse_cuda_version(cuda_version: str) -> tuple[int, int]:
    import re

    match = re.match(r"^(\d+)(?:\.(\d+))?", cuda_version.strip())
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2) or "0")
