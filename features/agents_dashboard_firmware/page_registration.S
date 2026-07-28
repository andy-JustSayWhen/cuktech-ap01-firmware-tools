    .option norelax
    .equ AGENTS_STATE_MAGIC, 0x41504754
    .equ EVENT_KEY, 17
    .equ EVENT_DELETE, 41
    .equ KEY_LEFT, 19
    .equ KEY_RIGHT, 20
    .equ KEY_ENTER, 10

    .section .payload, "ax", @progbits
    .align 2
    .global ap01_agents_page_register
    .type ap01_agents_page_register, @function

ap01_agents_page_register:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)

    /* s4 remains the stock top-level window container. */
    mv a0, s4
    call lv_obj_create
    beqz a0, .Lcreate_stock_detail
    mv s0, a0

    .ifdef SYNC_LOADER
    li a0, 24
    .else
    li a0, 12
    .endif
    call malloc
    beqz a0, .Ldelete_agents_root
    mv s1, a0
    li t0, AGENTS_STATE_MAGIC
    sw t0, 0(s1)
    sw zero, 4(s1)
    sw zero, 8(s1)
    .ifdef SYNC_LOADER
    sw zero, 12(s1)
    sw zero, 16(s1)
    sw zero, 20(s1)
    .endif
    sw s1, 16(s0)

    mv a0, s0
    la a1, ap01_agents_delete_event
    li a2, EVENT_DELETE
    li a3, 0
    call lv_obj_add_event_cb

    mv a0, s0
    li a1, 320
    li a2, 240
    call lv_obj_set_size

    /* Match stock 320x240 pages: no frame, padding, scrolling, or scrollbar. */
    mv a0, s0
    li a1, 0
    li a2, 0
    call lv_obj_set_style_border_width

    mv a0, s0
    li a1, 0
    li a2, 0
    call lv_obj_set_style_pad_all

    mv a0, s0
    call lv_obj_center

    mv a0, s0
    li a1, 0x10
    call lv_obj_remove_flag

    mv a0, s0
    li a1, 0
    call lv_obj_set_scrollbar_mode

    mv a0, s0
    li a1, 320
    call lv_obj_set_x

    mv a0, s0
    mv a1, s0
    la a2, agents_fallback_overview_descriptor
    call lv_gif_create
    beqz a0, .Ldelete_agents_root
    sw a0, 4(s1)
    .ifdef SYNC_LOADER
    mv a0, s1
    call ap01_agents_apply_current
    .endif
    j .Lcreate_stock_detail

.Ldelete_agents_root:
    mv a0, s0
    call lv_obj_del

.Lcreate_stock_detail:
    /* Reproduce the stock call replaced at 0xa00b2732. */
    mv a0, s4
    call lv_obj_create

    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    addi sp, sp, 32
    ret

    .size ap01_agents_page_register, .-ap01_agents_page_register

    .align 2
    .global ap01_agents_delete_event
    .type ap01_agents_delete_event, @function

ap01_agents_delete_event:
    lw t0, 8(a0)
    li t1, 0xffff7fff
    and t0, t0, t1
    li t1, EVENT_DELETE
    bne t0, t1, .Ldelete_return
    lw t0, 4(a0)
    beqz t0, .Ldelete_return
    lw a0, 16(t0)
    beqz a0, .Ldelete_return
    sw zero, 16(t0)
    tail free

.Ldelete_return:
    ret

    .size ap01_agents_delete_event, .-ap01_agents_delete_event

    .align 2
    .global ap01_agents_key_event
    .type ap01_agents_key_event, @function

ap01_agents_key_event:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    mv s0, a0

    lw s1, 0(s0)
    beqz s1, .Lstock_key_event
    mv a0, s1
    call window_get_active
    sw a0, 12(sp)
    lw t0, 8(s0)
    li t1, 0xffff7fff
    and t0, t0, t1
    li t1, EVENT_KEY
    bne t0, t1, .Lstock_key_event

    li s2, 0
    mv a0, s1
    lw a1, 12(sp)
    call lv_obj_get_child
    beqz a0, .Lread_key
    lw s2, 16(a0)
    beqz s2, .Lread_key
    lw t0, 0(s2)
    li t1, AGENTS_STATE_MAGIC
    bne t0, t1, .Lclear_agents_state
    lw t0, 4(s2)
    bnez t0, .Lread_key

.Lclear_agents_state:
    li s2, 0

.Lread_key:
    mv a0, s0
    call lv_event_get_key
    li t0, KEY_LEFT
    beq a0, t0, .Lkey_left
    li t0, KEY_RIGHT
    beq a0, t0, .Lkey_right
    li t0, KEY_ENTER
    beq a0, t0, .Lkey_enter
    j .Lstock_key_event

.Lkey_left:
    beqz s2, .Loverview_left
    lw t0, 8(s2)
    beqz t0, .Loverview_left
    li t1, 1
    beq t0, t1, .Lshow_last_30_days
    addi t0, t0, -1
    j .Lshow_detail_index

.Loverview_left:
    lw t0, 12(sp)
    sw t0, 8(sp)
    mv a0, s1
    call window_get_count
    addi t1, a0, -2
    lw t0, 8(sp)
    bltu t1, t0, .Lstock_key_event
    beqz t0, .Loverview_left_wrap
    li t2, 3
    bltu t0, t2, .Lstock_key_event
    beq t0, t2, .Loverview_left_power
    addi a1, t0, -1
    mv a0, s1
    li a2, 2
    call window_set_active
    j .Lkey_consumed

.Loverview_left_wrap:
    mv a1, t1
    mv a0, s1
    li a2, 2
    call window_set_active
    j .Lkey_consumed

.Loverview_left_power:
    li a1, 0
    mv a0, s1
    li a2, 2
    call window_set_active
    j .Lkey_consumed

.Lkey_right:
    beqz s2, .Loverview_right
    lw t0, 8(s2)
    beqz t0, .Loverview_right
    li t1, 3
    beq t0, t1, .Lshow_weekly
    addi t0, t0, 1
    j .Lshow_detail_index

.Loverview_right:
    lw t0, 12(sp)
    sw t0, 8(sp)
    mv a0, s1
    call window_get_count
    addi t1, a0, -2
    lw t0, 8(sp)
    bltu t1, t0, .Lstock_key_event
    beq t0, t1, .Loverview_right_wrap
    beqz t0, .Loverview_right_time
    li t2, 3
    bltu t0, t2, .Lstock_key_event
    addi a1, t0, 1
    j .Loverview_right_target_ready

.Loverview_right_wrap:
    li a1, 0
    j .Loverview_right_target_ready

.Loverview_right_time:
    li a1, 3

.Loverview_right_target_ready:
    mv a0, s1
    li a2, 1
    call window_set_active
    j .Lkey_consumed

.Lkey_enter:
    beqz s2, .Lstock_key_event
    lw t0, 8(s2)
    beqz t0, .Lshow_weekly
    li t0, 0
    j .Lshow_detail_index

.Lshow_weekly:
    li t0, 1
    j .Lshow_detail_index

.Lshow_last_30_days:
    li t0, 3

.Lshow_detail_index:
    sw t0, 8(s2)
    li t1, 1
    beq t0, t1, .Lweekly_source
    li t1, 2
    beq t0, t1, .Ltoday_source
    li t1, 3
    beq t0, t1, .Llast_30_days_source
    la a1, agents_fallback_overview_descriptor
    j .Lset_source

.Lweekly_source:
    la a1, agents_fallback_weekly_descriptor
    j .Lset_source

.Ltoday_source:
    la a1, agents_fallback_today_descriptor
    j .Lset_source

.Llast_30_days_source:
    la a1, agents_fallback_last_30_days_descriptor

.Lset_source:
    lw a0, 4(s2)
    call lv_gif_set_src
    .ifdef SYNC_LOADER
    mv a0, s2
    call ap01_agents_apply_current
    .endif

.Lkey_consumed:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    addi sp, sp, 32
    ret

.Lstock_key_event:
    mv a0, s0
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    addi sp, sp, 32
    tail stock_key_event

    .size ap01_agents_key_event, .-ap01_agents_key_event
