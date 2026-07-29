"""准备经过固定身份核对的只读固件工作副本。"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .image import FirmwareValidationError


_WRITABLE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_READ_ONLY_BITS = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
_PRIVATE_DIRECTORY_BITS = stat.S_IRWXU


@dataclass(frozen=True)
class PreparedFirmware:
    """已经核对并设为只读的固件工作副本。"""

    source: Path
    path: Path
    size: int
    md5: str
    sha256: str
    reused: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "path": str(self.path),
            "size": self.size,
            "md5": self.md5,
            "sha256": self.sha256,
            "read_only": True,
            "reused": self.reused,
        }


def _fingerprints(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            md5.update(chunk)
            sha256.update(chunk)
    return size, md5.hexdigest(), sha256.hexdigest()


def _validate_expected(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    expected_md5: str | None,
) -> tuple[int, str, str]:
    size, md5, sha256 = _fingerprints(path)
    if size != expected_size:
        raise FirmwareValidationError(
            f"固件材料字节数不匹配：预期 {expected_size}，实际 {size}"
        )
    if sha256 != expected_sha256.lower():
        raise FirmwareValidationError("固件材料 SHA-256 不匹配")
    if expected_md5 is not None and md5 != expected_md5.lower():
        raise FirmwareValidationError("固件材料 MD5 不匹配")
    return size, md5, sha256


def _is_read_only(path: Path) -> bool:
    return not bool(path.stat().st_mode & _WRITABLE_BITS)


def prepare_read_only_copy(
    source_path: Path,
    target_directory: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    expected_md5: str | None = None,
) -> PreparedFirmware:
    """核对版本化来源，并原子生成同名只读工作副本。"""

    if expected_size <= 0:
        raise FirmwareValidationError("固件材料预期字节数必须大于零")
    source = source_path.expanduser().resolve(strict=True)
    if not source.is_file():
        raise FirmwareValidationError(f"固件材料来源不是普通文件：{source}")
    size, md5, sha256 = _validate_expected(
        source,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        expected_md5=expected_md5,
    )

    directory = target_directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=_PRIVATE_DIRECTORY_BITS)
    if not directory.is_dir():
        raise FirmwareValidationError(f"固件工作目录不是文件夹：{directory}")
    directory.chmod(_PRIVATE_DIRECTORY_BITS)
    destination = directory / source.name
    if destination == source:
        raise FirmwareValidationError("固件工作副本不得覆盖版本化来源")

    if destination.exists():
        if not destination.is_file():
            raise FirmwareValidationError(
                f"固件工作副本目标不是普通文件：{destination}"
            )
        existing = _validate_expected(
            destination,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_md5=expected_md5,
        )
        if not _is_read_only(destination):
            raise FirmwareValidationError(
                f"已有固件工作副本仍可写，拒绝复用：{destination}"
            )
        return PreparedFirmware(
            source=source,
            path=destination,
            size=existing[0],
            md5=existing[1],
            sha256=existing[2],
            reused=True,
        )

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=directory,
            prefix=f".{source.name}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with source.open("rb") as source_stream:
                while chunk := source_stream.read(1024 * 1024):
                    temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())

        copied = _validate_expected(
            temporary_path,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_md5=expected_md5,
        )
        temporary_path.chmod(_READ_ONLY_BITS)
        if destination.exists():
            raise FirmwareValidationError(
                f"准备期间出现同名固件工作副本，拒绝覆盖：{destination}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
        if not _is_read_only(destination):
            raise FirmwareValidationError("固件工作副本未成功设为只读")
        final = _validate_expected(
            destination,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_md5=expected_md5,
        )
        if final != copied:
            raise FirmwareValidationError("固件工作副本形成后身份发生变化")
        return PreparedFirmware(
            source=source,
            path=destination,
            size=final[0],
            md5=final[1],
            sha256=final[2],
            reused=False,
        )
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            temporary_path.unlink()
