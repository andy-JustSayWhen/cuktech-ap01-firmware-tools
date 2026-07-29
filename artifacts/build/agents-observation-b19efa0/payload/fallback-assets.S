    .section .assets, "a", @progbits
    .balign 4
    .global agents_fallback_overview_descriptor
agents_fallback_overview_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word agents_fallback_overview_end - agents_fallback_overview_data
    .word agents_fallback_overview_data
    .word 0
    .word 0
agents_fallback_overview_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/agents-observation-b19efa0/payload/fallback-assets/fallback-overview.gif"
agents_fallback_overview_end:
    .balign 4
    .global agents_fallback_weekly_descriptor
agents_fallback_weekly_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word agents_fallback_weekly_end - agents_fallback_weekly_data
    .word agents_fallback_weekly_data
    .word 0
    .word 0
agents_fallback_weekly_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/agents-observation-b19efa0/payload/fallback-assets/fallback-weekly.gif"
agents_fallback_weekly_end:
    .balign 4
    .global agents_fallback_today_descriptor
agents_fallback_today_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word agents_fallback_today_end - agents_fallback_today_data
    .word agents_fallback_today_data
    .word 0
    .word 0
agents_fallback_today_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/agents-observation-b19efa0/payload/fallback-assets/fallback-today.gif"
agents_fallback_today_end:
    .balign 4
    .global agents_fallback_last_30_days_descriptor
agents_fallback_last_30_days_descriptor:
    .word 0x00000119
    .word 0
    .word 0
    .word agents_fallback_last_30_days_end - agents_fallback_last_30_days_data
    .word agents_fallback_last_30_days_data
    .word 0
    .word 0
agents_fallback_last_30_days_data:
    .incbin "/Users/mac/Desktop/cuktech-ap01-firmware-tools/artifacts/build/agents-observation-b19efa0/payload/fallback-assets/fallback-last_30_days.gif"
agents_fallback_last_30_days_end:
    .balign 4
