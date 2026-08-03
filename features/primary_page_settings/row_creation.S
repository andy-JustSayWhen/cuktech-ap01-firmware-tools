    .option norelax

    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_row_creation
    .type ap01_page_settings_row_creation, @function
ap01_page_settings_row_creation:
    li t0, 6
    beq a5, t0, .Lcreate_new_row
    li t0, 7
    beq a5, t0, .Lstock_return
    li t0, 0xa01989e0
    jr t0

.Lcreate_new_row:
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s1
    la a1, page_settings_row_label
    li a2, 0
    li a3, 0
    call stock_settings_row_create
    lw ra, 12(sp)
    addi sp, sp, 16
    li t0, 0xa01989b2
    jr t0

.Lstock_return:
    li t0, 0xa0198ad0
    jr t0
    .size ap01_page_settings_row_creation, .-ap01_page_settings_row_creation

    .section .rodata, "a", @progbits
    .balign 4
page_settings_row_label:
    .asciz "开关一级页面"
