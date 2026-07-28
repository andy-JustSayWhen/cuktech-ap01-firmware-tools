    .option norelax
    .section .text, "ax", @progbits
    .align 2
    .global ap01_page_settings_hook_passthrough
    .type ap01_page_settings_hook_passthrough, @function

ap01_page_settings_hook_passthrough:
    li t0, 6
    beq a5, t0, .Lstock_return
    li t0, 0xa01989e0
    jr t0

.Lstock_return:
    li t0, 0xa0198ad0
    jr t0

    .size ap01_page_settings_hook_passthrough, .-ap01_page_settings_hook_passthrough
