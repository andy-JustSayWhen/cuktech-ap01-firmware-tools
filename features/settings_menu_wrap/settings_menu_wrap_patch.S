    .option rvc

    .section .patch_map, "ax"
    .globl selection_transition
selection_transition:

    .org 0x437e
    .globl handler_return
handler_return:

    .org 0x43da
    .globl right_log_tail
right_log_tail:
    c.j right_original_path
right_wrap:
    li a5, 48
    sb a5, 1(s1)
    lw a0, 8(s3)
    addi a1, s5, -1
    c.li a2, 0
    jal ra, selection_transition
    c.j handler_return
    .globl right_original_path
right_original_path:

    .org 0x4418
    .globl right_type_log
right_type_log:
    c.j right_type_original_path
right_validate:
    lbu a5, 1(s1)
    c.li a4, 2
    bltu s5, a4, handler_return
    addi a3, a5, -47
    bltu s5, a3, handler_return
    beq a3, s5, right_wrap
    c.j right_original_switch
    .globl right_type_original_path
right_type_original_path:

    .org 0x4444
    .globl right_state_load
right_state_load:
    jal x0, right_validate
right_original_switch:

    .org 0x49a6
    .globl left_log_tail
left_log_tail:
    c.j left_original_path
left_wrap:
    addi a5, s5, 47
    sb a5, 1(s1)
    lw a0, 8(s3)
    c.li a1, 0
    addi a2, s5, -1
    jal ra, selection_transition
    c.j handler_return
    .globl left_original_path
left_original_path:

    .org 0x49e4
    .globl left_type_log
left_type_log:
    c.j left_type_original_path
left_validate:
    lbu a5, 1(s1)
    c.li a4, 2
    bltu s5, a4, handler_return
    addi a3, a5, -48
    bgeu a3, s5, handler_return
    beq a3, x0, left_wrap
    c.j left_original_switch
    c.nop
    .globl left_type_original_path
left_type_original_path:

    .org 0x4a10
    .globl left_state_load
left_state_load:
    jal x0, left_validate
left_original_switch:
