OUTPUT_ARCH(riscv)
ENTRY(ap01_agents_page_register)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA0213F90, LENGTH = 60934
}

PROVIDE(lv_obj_create = 0xA00D91C6);
PROVIDE(lv_obj_del = 0xA00D7806);
PROVIDE(lv_obj_set_size = 0xA00D8E96);
PROVIDE(lv_obj_set_style_border_width = 0xA00DFBCA);
PROVIDE(lv_obj_set_style_pad_all = 0xA00A5C0C);
PROVIDE(lv_obj_center = 0xA00DD202);
PROVIDE(lv_obj_remove_flag = 0xA00D9044);
PROVIDE(lv_obj_set_scrollbar_mode = 0xA019D53A);
PROVIDE(lv_obj_set_x = 0xA00D8C12);
PROVIDE(lv_obj_set_y = 0xA00D8C98);
PROVIDE(lv_obj_get_child = 0xA00DCEE4);
PROVIDE(lv_obj_get_child_count = 0xA00DD144);
PROVIDE(lv_obj_add_event_cb = 0xA01AD654);
PROVIDE(lv_obj_add_flag = 0xA00D8F7C);
PROVIDE(lv_gif_create = 0xA019CF0A);
PROVIDE(lv_gif_set_src = 0xA00ED7F4);
PROVIDE(lv_event_get_key = 0xA00D8AF6);
PROVIDE(stock_get_dispatch_index = 0xA00B2FF4);
PROVIDE(stock_get_child = 0xA00B3902);
PROVIDE(stock_switch_page = 0xA00B3106);
PROVIDE(malloc = 0xA008E362);
PROVIDE(free = 0xA008AC12);
PROVIDE(stock_key_event = 0xA00AFC88);
PROVIDE(stock_key_epilogue = 0xA00AFE6C);
PROVIDE(stock_pet_left_resume = 0xA00B010C);
PROVIDE(stock_pet_right_resume = 0xA00B03C6);
PROVIDE(stock_pet_enter_resume = 0xA00B17EE);
PROVIDE(stock_power_confirm_resume = 0xA00B059E);
PROVIDE(stock_set_dev_port_num = 0xA00A5CAE);
PROVIDE(stock_theme_change_home_page = 0xA019D422);

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
