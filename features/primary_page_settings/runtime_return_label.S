    .option norelax
    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_return_label
ap01_page_settings_return_label:
    li t0, 6
    beq a5, t0, 1f
    li t0, 0xa01989e0
    jr t0
1:
    li t0, 0xa0198ad0
    jr t0

    .align 2
    .global ap01_page_settings_runtime_return_label
ap01_page_settings_runtime_return_label:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)
    li t0, 0xa01988d4
    jalr ra, t0, 0
    mv s1, a0
    beqz a0, 2f
    li a1, 6
    li t0, 0xa00c5d84
    jalr ra, t0, 0
    beqz a0, 2f
    li a1, 0
    li t0, 0xa00c5d84
    jalr ra, t0, 0
    beqz a0, 2f
    la a1, page_settings_entry_label
    li t0, 0xa0086bcc
    jalr ra, t0, 0
2:
    mv a0, s1
    lw s1, 4(sp)
    lw s0, 8(sp)
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

    .section .rodata, "a", @progbits
    .balign 4
    .global page_settings_entry_label
page_settings_entry_label:
    .asciz "开关一级页面"
