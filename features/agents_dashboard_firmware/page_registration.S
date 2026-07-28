    .option norelax
    .section .payload, "ax", @progbits
    .align 2
    .global ap01_agents_page_register
    .type ap01_agents_page_register, @function

ap01_agents_page_register:
    addi sp, sp, -16
    sw ra, 12(sp)

    /* s4 remains the stock top-level window container. */
    mv a0, s4
    call lv_obj_create
    beqz a0, .Lcreate_stock_detail

    li a1, 320
    li a2, 240
    call lv_obj_set_size

.Lcreate_stock_detail:
    /* Reproduce the stock call replaced at 0xa00b2732. */
    mv a0, s4
    call lv_obj_create

    lw ra, 12(sp)
    addi sp, sp, 16
    ret

    .size ap01_agents_page_register, .-ap01_agents_page_register
