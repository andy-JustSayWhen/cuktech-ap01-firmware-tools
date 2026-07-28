    .option rvc

    .section .payload, "ax"
    .globl payload_start
payload_start:
    .globl right_validate
right_validate:
    lw a0, 8(s3)
    jal ra, list_item_count
    c.mv s5, a0
    lbu a5, 1(s1)
    c.li a4, 2
    bltu s5, a4, handler_return
    addi a3, a5, -47
    bltu s5, a3, handler_return
    beq a3, s5, right_wrap
    jal x0, right_original_switch
right_wrap:
    lw a0, 8(s3)
    c.li a1, 0
    c.li a2, 1
    jal ra, list_position_adjust
    li a5, 48
    sb a5, 1(s1)
    lw a0, 8(s3)
    addi a1, s5, -1
    c.li a2, 0
    jal ra, selection_transition
    jal x0, handler_return

    .globl left_validate
left_validate:
    lw a0, 8(s3)
    jal ra, list_item_count
    c.mv s5, a0
    lbu a5, 1(s1)
    c.li a4, 2
    bltu s5, a4, handler_return
    addi a3, a5, -48
    bgeu a3, s5, handler_return
    beq a3, x0, left_wrap
    jal x0, left_original_switch
left_wrap:
    lw a0, 8(s3)
    li a1, 400
    c.li a2, 1
    jal ra, list_position_adjust
    addi a5, s5, 47
    sb a5, 1(s1)
    lw a0, 8(s3)
    c.li a1, 0
    addi a2, s5, -1
    jal ra, selection_transition
    jal x0, handler_return
    .globl payload_end
payload_end:

    .section .right_hook, "ax"
    .globl right_hook
right_hook:
    jal x0, right_validate

    .section .left_hook, "ax"
    .globl left_hook
left_hook:
    jal x0, left_validate
