    .option norelax

    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_single_iteration_append
    .type ap01_page_settings_single_iteration_append, @function
ap01_page_settings_single_iteration_append:
    li t0, 6
    beq a5, t0, .Lappend_rows
    li t0, 0xa01989e0
    jr t0

.Lappend_rows:
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s1
    la a1, page_settings_append_label
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
    .size ap01_page_settings_single_iteration_append, .-ap01_page_settings_single_iteration_append

    .section .rodata, "a", @progbits
    .balign 4
page_settings_append_label:
    .asciz "开关一级页面"
