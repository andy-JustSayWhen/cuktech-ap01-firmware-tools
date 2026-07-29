    .section .assets, "a", @progbits
    .balign 4
    .global page_settings_background_descriptor
page_settings_background_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word page_settings_background_end - page_settings_background_data
    .word page_settings_background_data
    .word 0
    .word 0
page_settings_background_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/opt-full-primary-switches/page-settings/assets/page-settings-background.gif"
page_settings_background_end:
    .balign 4
    .global page_settings_marker_descriptor
page_settings_marker_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word page_settings_marker_end - page_settings_marker_data
    .word page_settings_marker_data
    .word 0
    .word 0
page_settings_marker_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/opt-full-primary-switches/page-settings/assets/page-settings-marker.gif"
page_settings_marker_end:
    .balign 4
    .global page_settings_check_descriptor
page_settings_check_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word page_settings_check_end - page_settings_check_data
    .word page_settings_check_data
    .word 0
    .word 0
page_settings_check_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/opt-full-primary-switches/page-settings/assets/page-settings-check.gif"
page_settings_check_end:
    .balign 4
