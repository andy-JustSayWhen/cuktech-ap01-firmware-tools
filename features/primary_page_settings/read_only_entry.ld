OUTPUT_ARCH(riscv)
ENTRY(ap01_page_settings_read_only_menu_dispatch)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(lv_event_get_key = 0xA00BF7EA);
PROVIDE(lv_obj_get_child = 0xA00C5D84);
PROVIDE(lv_obj_get_child_count = 0xA00C5FE4);
PROVIDE(stock_settings_key_event = 0xA00F8096);
PROVIDE(stock_settings_row_create = 0xA0192FB4);
PROVIDE(stock_scroll_to_y = 0xA00C6DFE);
PROVIDE(stock_selection_transition = 0xA00F3D5A);

SECTIONS
{
    .payload :
    {
        KEEP(*(.text.entry))
        *(.text .text.*)
        *(.rodata .rodata.*)
    } > PAYLOAD

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.riscv.attributes)
        *(.eh_frame*)
    }
}
