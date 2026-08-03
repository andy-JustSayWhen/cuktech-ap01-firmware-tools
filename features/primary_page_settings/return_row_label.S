    .option norelax

    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_return_label
    .type ap01_page_settings_return_label, @function
ap01_page_settings_return_label:
    li t0, 6
    beq a5, t0, .Lstock_return
    li t0, 0xa01989e0
    jr t0

.Lstock_return:
    li t0, 0xa0198ad0
    jr t0
    .size ap01_page_settings_return_label, .-ap01_page_settings_return_label

    .section .rodata, "a", @progbits
    .balign 4
    .global page_settings_entry_label
page_settings_entry_label:
    .asciz "开关一级页面"
