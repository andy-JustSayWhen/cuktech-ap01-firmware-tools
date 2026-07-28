    .option norelax
    .section .text, "ax", @progbits
    .align 2
    .global ap01_combined_primary_key_event
    .type ap01_combined_primary_key_event, @function

ap01_combined_primary_key_event:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    mv s0, a0
    call ap01_agents_detail_active
    bnez a0, .Lagents
    mv a0, s0
    call ap01_primary_page_navigation_event
    beqz a0, .Lagents
    lw ra, 12(sp)
    lw s0, 8(sp)
    addi sp, sp, 16
    ret
.Lagents:
    mv a0, s0
    lw ra, 12(sp)
    lw s0, 8(sp)
    addi sp, sp, 16
    tail ap01_agents_key_event

    .size ap01_combined_primary_key_event, .-ap01_combined_primary_key_event
