OUTPUT_ARCH(riscv)
ENTRY(ap01_agents_page_register)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(lv_obj_create = 0xA00C1EC6);
PROVIDE(lv_obj_del = 0xA00BEBEE);
PROVIDE(lv_obj_set_size = 0xA00C0060);
PROVIDE(lv_obj_get_child = 0xA00C5D84);
PROVIDE(lv_obj_add_event_cb = 0xA01AA0B6);
PROVIDE(lv_gif_create = 0xA01930FE);
PROVIDE(lv_gif_set_src = 0xA00CF8D8);
PROVIDE(lv_event_get_key = 0xA00BF7EA);
PROVIDE(window_set_active = 0xA00B06F4);
PROVIDE(malloc = 0xA007E1C4);
PROVIDE(free = 0xA007C256);
PROVIDE(stock_key_event = 0xA00BBFEE);

SECTIONS
{
    .payload :
    {
        KEEP(*(.payload))
        KEEP(*(.assets))
    } > PAYLOAD

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.riscv.attributes)
    }
}
