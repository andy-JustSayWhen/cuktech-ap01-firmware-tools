"""发布包内 AP01 固件的冻结身份核对。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.firmware_image import AP01_1_0_2_0031, validate_baseline


ALLOWED_KINDS = frozenset({"official", "settings", "optimized"})


class FirmwareInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectedFirmware:
    path: Path
    kind: str
    model: str
    version: str
    size: int
    md5: str
    sha256: str
    manifest_path: Path
    install_approved: bool

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "model": self.model,
            "version": self.version,
            "filename": self.path.name,
            "size": self.size,
            "md5": self.md5,
            "sha256": self.sha256,
            "install_approved": self.install_approved,
        }


def _inside(directory: Path, selected: Path) -> Path:
    root = directory.expanduser().resolve(strict=True)
    path = selected.expanduser().resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(root):
        raise FirmwareInspectionError("固件必须是发布包允许目录内的普通文件")
    return path


def _hashes(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return size, md5.hexdigest(), sha256.hexdigest()


def inspect_release_firmware(allowed_directory: Path, selected: Path) -> InspectedFirmware:
    path = _inside(allowed_directory, selected)
    if path.read_bytes()[:4] != b"BFNP":
        raise FirmwareInspectionError("文件不是 AP01 固件")
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if not manifest_path.is_file():
        raise FirmwareInspectionError("固件缺少同名构建清单")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirmwareInspectionError("构建清单无法读取") from exc
    if not isinstance(manifest, dict):
        raise FirmwareInspectionError("构建清单不是对象")

    kind = str(manifest.get("kind") or "")
    model = str(manifest.get("model") or "")
    version = str(manifest.get("version") or "")
    if kind not in ALLOWED_KINDS:
        raise FirmwareInspectionError("构建清单中的成品类型不受支持")
    if model != AP01_1_0_2_0031.model or version != AP01_1_0_2_0031.version:
        raise FirmwareInspectionError("固件型号或版本不匹配")
    size, md5, sha256 = _hashes(path)
    expected = (manifest.get("size"), manifest.get("md5"), manifest.get("sha256"))
    if expected != (size, md5, sha256):
        raise FirmwareInspectionError("固件与构建清单的完整身份不匹配")
    if size != AP01_1_0_2_0031.size:
        raise FirmwareInspectionError("固件总长度不匹配")
    if kind == "official":
        validate_baseline(path.read_bytes(), AP01_1_0_2_0031)
    return InspectedFirmware(
        path=path,
        kind=kind,
        model=model,
        version=version,
        size=size,
        md5=md5,
        sha256=sha256,
        manifest_path=manifest_path,
        install_approved=manifest.get("install_approved") is True,
    )
