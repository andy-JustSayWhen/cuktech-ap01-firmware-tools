"""Rebuild the settings-stage firmware without the direction filter patch."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "app"))

from app.ap01_firmware import _tool_revision
from core.firmware_image import AP01_1_0_2_0031, prepare_read_only_copy
from features.offline_firmware_build import make_firmware
from features.settings_menu_wrap import write_approved_plan

SOURCE = REPO / "artifacts/firmware/original/ap01-1.0.2_0031.bin"
OUTPUT = REPO / "artifacts/firmware/ap01-1.0.2_0031-opt-setting.bin"
MANIFEST = REPO / "artifacts/build/settings-stage-manifest.json"
MANIFEST.parent.mkdir(parents=True, exist_ok=True)

revision = _tool_revision()
checked_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
print("tool_revision:", revision)

with tempfile.TemporaryDirectory() as selected:
    material = prepare_read_only_copy(
        SOURCE,
        Path(selected),
        expected_size=AP01_1_0_2_0031.size,
        expected_sha256=AP01_1_0_2_0031.sha256,
        expected_md5=AP01_1_0_2_0031.md5,
    ).path
    plan_path = Path(selected) / "settings-menu-wrap-approved.json"
    document = write_approved_plan(material, plan_path, tool_revision=revision)
    print("plan status:", document["status"])
    print("plan patches:", document["review"]["patch_count"])

    result = make_firmware(
        material,
        plan_path,
        OUTPUT,
        MANIFEST,
        repo_root=REPO,
        tool_revision=revision,
        cloud_version=AP01_1_0_2_0031.version,
        cloud_md5=AP01_1_0_2_0031.md5,
        cloud_checked_at=checked_at,
    )
    print("output:", result.output)
    print("sha256:", result.output_sha256)
    print("md5:", result.output_md5)
