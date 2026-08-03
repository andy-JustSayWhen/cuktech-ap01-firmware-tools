    .option norelax

    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_delayed_row_creation
    .type ap01_page_settings_delayed_row_creation, @function
ap01_page_settings_delayed_row_creation:
    li t0, 6
    beq a5, t0, .Lsequence_six
    li t0, 0xa01989e0
    jr t0

.Lsequence_six:
    lw t1, 124(sp)
    li t0, 0xa00b4002
    beq t1, t0, .Lstock_return
    li t0, 0xa00bd9ea
    bne t1, t0, .Lstock_return
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s1
    la a1, page_settings_delayed_label
    li a2, 0
    li a3, 0
    call stock_settings_row_create
    mv a0, s1
    li a1, 0
    li a2, 0
    call stock_settings_return_create
    lw ra, 12(sp)
    addi sp, sp, 16
    li t0, 0xa01989b2
    jr t0

.Lstock_return:
    li t0, 0xa0198ad0
    jr t0
    .size ap01_page_settings_delayed_row_creation, .-ap01_page_settings_delayed_row_creation

    .section .rodata, "a", @progbits
    .balign 4
page_settings_delayed_label:
    .asciz "开关一级页面"
