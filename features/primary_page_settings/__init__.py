"""一级页面开关固件功能公开入口。"""

from .assets import PageSettingsAssetError, build_page_settings_assets
from .build import (
    REQUIRED_SYMBOLS,
    PrimaryPageSettingsBuildError,
    PrimaryPageSettingsObjects,
    apply_page_settings_patches,
    build_page_settings_objects,
)

__all__ = (
    "PageSettingsAssetError",
    "PrimaryPageSettingsBuildError",
    "PrimaryPageSettingsObjects",
    "REQUIRED_SYMBOLS",
    "apply_page_settings_patches",
    "build_page_settings_assets",
    "build_page_settings_objects",
)
