OUTPUT_ARCH(riscv)
ENTRY(ap01_agents_page_register)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(lv_obj_create = 0xA00C1EC6);
PROVIDE(lv_obj_del = 0xA00BEBEE);
PROVIDE(lv_obj_set_size = 0xA00C0060);
PROVIDE(lv_obj_set_style_border_width = 0xA00C7B56);
PROVIDE(lv_obj_set_style_pad_all = 0xA00B14B0);
PROVIDE(lv_obj_center = 0xA00C0710);
PROVIDE(lv_obj_remove_flag = 0xA00C1680);
PROVIDE(lv_obj_set_scrollbar_mode = 0xA019397A);
PROVIDE(lv_obj_set_x = 0xA00BF942);
PROVIDE(lv_obj_set_y = 0xA00BFE62);
PROVIDE(lv_obj_get_child = 0xA00C5D84);
PROVIDE(lv_obj_get_child_count = 0xA00C5FE4);
PROVIDE(lv_obj_add_event_cb = 0xA01AA0B6);
PROVIDE(lv_obj_add_flag = 0xA00C1400);
PROVIDE(lv_gif_create = 0xA01930FE);
PROVIDE(lv_gif_set_src = 0xA00CF8D8);
PROVIDE(lv_event_get_key = 0xA00BF7EA);
PROVIDE(window_get_active = 0xA00B0290);
PROVIDE(stock_get_dispatch_index = 0xA00BE388);
PROVIDE(stock_get_child = 0xA00BE3CA);
PROVIDE(stock_switch_page = 0xA00BFA4E);
PROVIDE(window_get_count = 0xA00B0570);
PROVIDE(window_set_active = 0xA00B06F4);
PROVIDE(malloc = 0xA007E1C4);
PROVIDE(free = 0xA007C256);
PROVIDE(stock_key_event = 0xA00BBFEE);
PROVIDE(stock_settings_key_event = 0xA00F8096);
PROVIDE(stock_settings_row_create = 0xA0192FB4);
PROVIDE(stock_scroll_to_y = 0xA00C6DFE);
PROVIDE(stock_selection_transition = 0xA00F3D5A);

SECTIONS
{
    .payload :
    {
        KEEP(*(.payload))
        KEEP(*(.text.entry))
        *(.text .text.*)
        *(.rodata .rodata.*)
        KEEP(*(.assets))
    } > PAYLOAD

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.riscv.attributes)
        *(.eh_frame*)
    }
}
