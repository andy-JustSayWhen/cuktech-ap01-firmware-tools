"""一级页面开关固件功能公开入口。"""

from .assets import PageSettingsAssetError, build_page_settings_assets
from .build import (
    REQUIRED_SYMBOLS,
    PrimaryPageSettingsBuildError,
    PrimaryPageSettingsObjects,
    apply_page_settings_patches,
    build_page_settings_objects,
)
from .hook_observation import (
    OUTPUT_NAME as HOOK_OBSERVATION_OUTPUT_NAME,
    SettingsHookObservationError,
    SettingsHookObservationResult,
    build_settings_hook_observation,
)
from .read_only_entry import (
    OUTPUT_NAME as READ_ONLY_ENTRY_OUTPUT_NAME,
    PageSettingsReadOnlyEntryError,
    PageSettingsReadOnlyEntryResult,
    build_page_settings_read_only_entry,
    simulate_page_settings_read_only_entry,
)

__all__ = (
    "HOOK_OBSERVATION_OUTPUT_NAME",
    "PageSettingsAssetError",
    "PrimaryPageSettingsBuildError",
    "PrimaryPageSettingsObjects",
    "PageSettingsReadOnlyEntryError",
    "PageSettingsReadOnlyEntryResult",
    "READ_ONLY_ENTRY_OUTPUT_NAME",
    "REQUIRED_SYMBOLS",
    "SettingsHookObservationError",
    "SettingsHookObservationResult",
    "apply_page_settings_patches",
    "build_page_settings_assets",
    "build_page_settings_objects",
    "build_page_settings_read_only_entry",
    "build_settings_hook_observation",
    "simulate_page_settings_read_only_entry",
)
