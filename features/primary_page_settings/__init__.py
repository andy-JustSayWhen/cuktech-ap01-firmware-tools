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
from .startup_passthrough import (
    OUTPUT_NAME as STARTUP_PASSTHROUGH_OUTPUT_NAME,
    PageSettingsStartupPassthroughError,
    PageSettingsStartupPassthroughResult,
    build_page_settings_startup_passthrough,
    simulate_page_settings_startup_passthrough,
)
from .row_creation import (
    OUTPUT_NAME as ROW_CREATION_OUTPUT_NAME,
    PageSettingsRowCreationError,
    PageSettingsRowCreationResult,
    build_page_settings_row_creation,
    simulate_page_settings_row_creation,
)
from .single_iteration_append import (
    OUTPUT_NAME as SINGLE_ITERATION_APPEND_OUTPUT_NAME,
    PageSettingsSingleIterationAppendError,
    PageSettingsSingleIterationAppendResult,
    build_page_settings_single_iteration_append,
    simulate_page_settings_single_iteration_append,
)

__all__ = (
    "HOOK_OBSERVATION_OUTPUT_NAME",
    "PageSettingsAssetError",
    "PrimaryPageSettingsBuildError",
    "PrimaryPageSettingsObjects",
    "PageSettingsReadOnlyEntryError",
    "PageSettingsReadOnlyEntryResult",
    "PageSettingsRowCreationError",
    "PageSettingsRowCreationResult",
    "PageSettingsSingleIterationAppendError",
    "PageSettingsSingleIterationAppendResult",
    "READ_ONLY_ENTRY_OUTPUT_NAME",
    "ROW_CREATION_OUTPUT_NAME",
    "SINGLE_ITERATION_APPEND_OUTPUT_NAME",
    "REQUIRED_SYMBOLS",
    "SettingsHookObservationError",
    "SettingsHookObservationResult",
    "STARTUP_PASSTHROUGH_OUTPUT_NAME",
    "PageSettingsStartupPassthroughError",
    "PageSettingsStartupPassthroughResult",
    "apply_page_settings_patches",
    "build_page_settings_assets",
    "build_page_settings_objects",
    "build_page_settings_read_only_entry",
    "build_page_settings_row_creation",
    "build_page_settings_single_iteration_append",
    "build_page_settings_startup_passthrough",
    "build_settings_hook_observation",
    "simulate_page_settings_read_only_entry",
    "simulate_page_settings_row_creation",
    "simulate_page_settings_single_iteration_append",
    "simulate_page_settings_startup_passthrough",
)
