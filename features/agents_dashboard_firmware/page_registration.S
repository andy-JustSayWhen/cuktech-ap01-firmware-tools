    .option norelax
    .equ AGENTS_STATE_MAGIC, 0x41504754
    .equ EVENT_KEY, 17
    .equ EVENT_DELETE, 41
    .equ KEY_LEFT, 19
    .equ KEY_RIGHT, 20
    .equ KEY_ENTER, 10
    .equ AGENTS_TAIL_MAGIC, 0xa5010000
    .equ AGENTS_TAIL_MAGIC_MASK, 0xffff0000
    .equ AGENTS_STATE_CLOSED, 0
    .equ AGENTS_STATE_OVERVIEW, 1
    .equ AGENTS_STATE_WEEKLY, 2
    .equ AGENTS_STATE_TODAY, 3
    .equ AGENTS_STATE_LAST_30_DAYS, 4
    .equ STOCK_PET_DESCRIPTOR, 0xa01f7090
    .equ PAGE_BIT_PET, 4
    .equ PAGE_BIT_AGENTS, 5

    .ifdef STOCK_PET_REUSE

    .section .payload, "ax", @progbits
    .align 2
    .global ap01_agents_page_register
    .type ap01_agents_page_register, @function

/* Kept only as the fixed payload entry symbol.  The zero-object build does not
 * patch the stock page-registration call, so this function is never invoked.
 */
ap01_agents_page_register:
    ret

    .size ap01_agents_page_register, .-ap01_agents_page_register

    .align 2
    .global ap01_agents_state_read
    .type ap01_agents_state_read, @function

/* a0 = stock pet state; returns 0..4 or -1 when the independent tail is bad. */
ap01_agents_state_read:
    lw t0, 16(a0)
    li t1, AGENTS_TAIL_MAGIC_MASK
    and t2, t0, t1
    li t1, AGENTS_TAIL_MAGIC
    bne t2, t1, .Lsync_state_invalid
    srli t1, t0, 8
    andi t1, t1, 255
    li t2, AGENTS_STATE_LAST_30_DAYS
    bltu t2, t1, .Lsync_state_invalid
    xori t2, t1, 255
    andi t2, t2, 255
    andi t0, t0, 255
    bne t0, t2, .Lsync_state_invalid
    mv a0, t1
    ret

.Lsync_state_invalid:
    li a0, -1
    ret

    .size ap01_agents_state_read, .-ap01_agents_state_read

    .align 2
    .global ap01_agents_state_write
    .type ap01_agents_state_write, @function

/* a0 = stock pet state; a1 = validated state 0..4. */
ap01_agents_state_write:
    slli t0, a1, 8
    xori t1, a1, 255
    andi t1, t1, 255
    or t0, t0, t1
    li t1, AGENTS_TAIL_MAGIC
    or t0, t0, t1
    sw t0, 16(a0)
    ret

    .size ap01_agents_state_write, .-ap01_agents_state_write

    .align 2
    .global ap01_agents_find_pet_state
    .type ap01_agents_find_pet_state, @function

/* theme -> stock page 7 -> root user data -> type 10 wrapper -> pet state. */
ap01_agents_find_pet_state:
    addi sp, sp, -16
    sw ra, 12(sp)
    beqz a0, .Lsync_find_no
    li a1, 7
    call stock_get_child
    beqz a0, .Lsync_find_no
    lw t0, 16(a0)
    beqz t0, .Lsync_find_no
    lw t1, 0(t0)
    li t2, 10
    bne t1, t2, .Lsync_find_no
    lw a0, 4(t0)
    beqz a0, .Lsync_find_no
    lw t0, 0(a0)
    beqz t0, .Lsync_find_no
    j .Lsync_find_done

.Lsync_find_no:
    li a0, 0

.Lsync_find_done:
    lw ra, 12(sp)
    addi sp, sp, 16
    ret

    .size ap01_agents_find_pet_state, .-ap01_agents_find_pet_state

    .align 2
    .global ap01_agents_stock_pet_left_entry
    .type ap01_agents_stock_pet_left_entry, @function
ap01_agents_stock_pet_left_entry:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s2, 8(sp)
    sw s3, 4(sp)
    li s3, 1
    j .Llocal_find_state

    .global ap01_agents_stock_pet_right_entry
    .type ap01_agents_stock_pet_right_entry, @function
ap01_agents_stock_pet_right_entry:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s2, 8(sp)
    sw s3, 4(sp)
    li s3, 2
    j .Llocal_find_state

    .global ap01_agents_stock_pet_enter_entry
    .type ap01_agents_stock_pet_enter_entry, @function
ap01_agents_stock_pet_enter_entry:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s2, 8(sp)
    sw s3, 4(sp)
    li s3, 3

.Llocal_find_state:
    mv a0, s1
    call ap01_agents_find_pet_state
    mv s2, a0
    beqz s2, .Llocal_fallback
    mv a0, s2
    call ap01_agents_state_read
    bltz a0, .Llocal_invalid_state
    li t0, 1
    beq s3, t0, .Llocal_pet_left
    li t0, 2
    beq s3, t0, .Llocal_pet_right
    j .Llocal_pet_enter

.Llocal_invalid_state:
    mv a0, s2
    call ap01_agents_restore_pet
    beqz a0, .Llocal_fallback
    li a0, AGENTS_STATE_CLOSED
    j .Llocal_dispatch

.Llocal_dispatch:
    li t0, 1
    beq s3, t0, .Llocal_pet_left
    li t0, 2
    beq s3, t0, .Llocal_pet_right
    j .Llocal_pet_enter

.Llocal_pet_left:
    beqz a0, .Llocal_fallback
    li t0, AGENTS_STATE_OVERVIEW
    bne a0, t0, .Llocal_detail_left
    .ifdef OPT_INTEGRATION
    call ap01_page_settings_load_mask
    li t0, 1
    li t1, PAGE_BIT_PET
    sll t0, t0, t1
    and t0, t0, a0
    bnez t0, .Llocal_pet_left_restore_only
    mv a0, s2
    call ap01_agents_restore_pet
    beqz a0, .Llocal_fallback
    mv a0, s1
    li a1, 6
    li a2, 2
    call stock_switch_page
    mv a0, s1
    call stock_get_dispatch_index
    li t0, 6
    beq a0, t0, .Llocal_consumed
    j .Llocal_fallback
.Llocal_pet_left_restore_only:
    .endif
    mv a0, s2
    call ap01_agents_restore_pet
    bnez a0, .Llocal_consumed
    j .Llocal_fallback

.Llocal_detail_left:
    li t0, AGENTS_STATE_WEEKLY
    beq a0, t0, .Llocal_detail_left_wrap
    li t0, AGENTS_STATE_TODAY
    beq a0, t0, .Llocal_detail_left_weekly
    li a1, AGENTS_STATE_TODAY
    j .Llocal_show_detail

.Llocal_detail_left_wrap:
    li a1, AGENTS_STATE_LAST_30_DAYS
    j .Llocal_show_detail

.Llocal_detail_left_weekly:
    li a1, AGENTS_STATE_WEEKLY
    j .Llocal_show_detail

.Llocal_pet_right:
    beqz a0, .Llocal_enter_agents
    li t0, AGENTS_STATE_OVERVIEW
    bne a0, t0, .Llocal_detail_right
    mv a0, s2
    call ap01_agents_restore_pet
    beqz a0, .Llocal_fallback
    mv a0, s1
    li a1, 0
    li a2, 1
    .ifdef OPT_INTEGRATION
    call ap01_primary_page_filter_and_switch
    .else
    call stock_switch_page
    .endif
    mv a0, s1
    call stock_get_dispatch_index
    beqz a0, .Llocal_consumed
    j .Llocal_fallback

.Llocal_enter_agents:
    .ifdef OPT_INTEGRATION
    call ap01_page_settings_load_mask
    li t0, 1
    li t1, PAGE_BIT_AGENTS
    sll t0, t0, t1
    and t0, t0, a0
    beqz t0, .Llocal_fallback
    .endif
    mv a0, s2
    li a1, AGENTS_STATE_OVERVIEW
    call ap01_agents_show_page
    bnez a0, .Llocal_consumed
    j .Llocal_fallback

.Llocal_detail_right:
    li t0, AGENTS_STATE_LAST_30_DAYS
    beq a0, t0, .Llocal_detail_right_wrap
    addi a1, a0, 1
    j .Llocal_show_detail

.Llocal_detail_right_wrap:
    li a1, AGENTS_STATE_WEEKLY

.Llocal_show_detail:
    mv a0, s2
    call ap01_agents_show_page
    bnez a0, .Llocal_consumed
    j .Llocal_fallback

.Llocal_pet_enter:
    beqz a0, .Llocal_fallback
    li t0, AGENTS_STATE_OVERVIEW
    li a1, AGENTS_STATE_OVERVIEW
    bne a0, t0, .Llocal_enter_show
    li a1, AGENTS_STATE_WEEKLY

.Llocal_enter_show:
    mv a0, s2
    call ap01_agents_show_page
    bnez a0, .Llocal_consumed

.Llocal_fallback:
    mv t0, s3
    lw ra, 12(sp)
    lw s2, 8(sp)
    lw s3, 4(sp)
    addi sp, sp, 16
    li t1, 1
    beq t0, t1, .Llocal_resume_pet_left
    li t1, 2
    beq t0, t1, .Llocal_resume_pet_right
    mv a0, s1
    li a1, 7
    tail stock_pet_enter_resume

.Llocal_resume_pet_left:
    mv a0, s1
    li a1, 7
    tail stock_pet_left_resume

.Llocal_resume_pet_right:
    mv a0, s1
    li a1, 7
    tail stock_pet_right_resume

.Llocal_consumed:
    lw ra, 12(sp)
    lw s2, 8(sp)
    lw s3, 4(sp)
    addi sp, sp, 16
    tail stock_key_epilogue

    .size ap01_agents_stock_pet_left_entry, .-ap01_agents_stock_pet_left_entry
    .size ap01_agents_stock_pet_right_entry, .-ap01_agents_stock_pet_right_entry
    .size ap01_agents_stock_pet_enter_entry, .-ap01_agents_stock_pet_enter_entry

    .align 2
    .global ap01_agents_show_page
    .type ap01_agents_show_page, @function

/* a0 = stock pet state, a1 = independent state 1..4. */
ap01_agents_show_page:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)
    mv s0, a0
    mv s1, a1
    beqz s0, .Lsync_show_no
    li t0, AGENTS_STATE_OVERVIEW
    bltu s1, t0, .Lsync_show_failed
    li t0, AGENTS_STATE_LAST_30_DAYS
    bltu t0, s1, .Lsync_show_failed

    li t0, AGENTS_STATE_WEEKLY
    beq s1, t0, .Lsync_weekly_source
    li t0, AGENTS_STATE_TODAY
    beq s1, t0, .Lsync_today_source
    li t0, AGENTS_STATE_LAST_30_DAYS
    beq s1, t0, .Lsync_last_30_days_source
    la a1, agents_fallback_overview_descriptor
    j .Lsync_set_agents_source

.Lsync_weekly_source:
    la a1, agents_fallback_weekly_descriptor
    j .Lsync_set_agents_source

.Lsync_today_source:
    la a1, agents_fallback_today_descriptor
    j .Lsync_set_agents_source

.Lsync_last_30_days_source:
    la a1, agents_fallback_last_30_days_descriptor

.Lsync_set_agents_source:
    lw a0, 0(s0)
    beqz a0, .Lsync_show_failed
    call lv_gif_set_src
    lw t0, 0(s0)
    lw t0, 92(t0)
    beqz t0, .Lsync_show_failed
    mv a0, s0
    mv a1, s1
    call ap01_agents_state_write
    mv a0, s0
    call ap01_agents_apply_current
    bnez a0, .Lsync_show_yes

    .global ap01_agents_show_failed
ap01_agents_show_failed:
.Lsync_show_failed:
    mv a0, s0
    call ap01_agents_restore_pet

.Lsync_show_no:
    li a0, 0
    j .Lsync_show_done

.Lsync_show_yes:
    li a0, 1

.Lsync_show_done:
    lw ra, 12(sp)
    lw s0, 8(sp)
    lw s1, 4(sp)
    addi sp, sp, 16
    ret

    .size ap01_agents_show_page, .-ap01_agents_show_page

    .align 2
    .global ap01_agents_restore_pet
    .type ap01_agents_restore_pet, @function

/* Close AGENTS first, then restore the stock descriptor on the existing GIF. */
ap01_agents_restore_pet:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    mv s0, a0
    beqz s0, .Lsync_restore_no
    li a1, AGENTS_STATE_CLOSED
    call ap01_agents_state_write
    lw a0, 0(s0)
    beqz a0, .Lsync_restore_no
    li a1, STOCK_PET_DESCRIPTOR
    call lv_gif_set_src
    lw t0, 0(s0)
    lw t0, 92(t0)
    snez a0, t0
    j .Lsync_restore_done

.Lsync_restore_no:
    li a0, 0

.Lsync_restore_done:
    lw ra, 12(sp)
    lw s0, 8(sp)
    addi sp, sp, 16
    ret

    .size ap01_agents_restore_pet, .-ap01_agents_restore_pet

    .align 2
    .global ap01_agents_detail_active
    .type ap01_agents_detail_active, @function

ap01_agents_detail_active:
    addi sp, sp, -16
    sw ra, 12(sp)
    sw s0, 8(sp)
    sw s1, 4(sp)
    mv s0, a0
    beqz s0, .Lsync_detail_no
    lw a0, 0(s0)
    beqz a0, .Lsync_detail_no
    call stock_get_dispatch_index
    li t0, 7
    bne a0, t0, .Lsync_detail_no
    lw a0, 0(s0)
    call ap01_agents_find_pet_state
    mv s1, a0
    beqz s1, .Lsync_detail_no
    call ap01_agents_state_read
    bgez a0, .Lsync_detail_valid
    mv a0, s1
    call ap01_agents_restore_pet
    j .Lsync_detail_no

.Lsync_detail_valid:
    li t0, AGENTS_STATE_WEEKLY
    sltu a0, a0, t0
    xori a0, a0, 1
    j .Lsync_detail_done

.Lsync_detail_no:
    li a0, 0

.Lsync_detail_done:
    lw ra, 12(sp)
    lw s0, 8(sp)
    lw s1, 4(sp)
    addi sp, sp, 16
    ret

    .size ap01_agents_detail_active, .-ap01_agents_detail_active

    .else

    .section .payload, "ax", @progbits
    .align 2
    .global ap01_agents_page_register
    .type ap01_agents_page_register, @function

ap01_agents_page_register:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    .ifdef SYNC_LOADER
    sw s2, 16(sp)

    /* Host the overlay inside the stock pet page so the top-level count stays 9. */
    mv a0, s4
    li a1, 7
    call lv_obj_get_child
    beqz a0, .Lcreate_stock_detail
    mv s2, a0
    .endif

    .ifdef SYNC_LOADER
    mv a0, s2
    .else
    mv a0, s4
    .endif
    call lv_obj_create
    beqz a0, .Lcreate_stock_detail
    mv s0, a0

    .ifdef SYNC_LOADER
    li a0, 32
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
    sw zero, 24(s1)
    sw s0, 28(s1)
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

.Lpage_register_return:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    .ifdef SYNC_LOADER
    lw s2, 16(sp)
    .endif
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

    .ifdef SYNC_LOADER
    .align 2
    .global ap01_agents_find_state
    .type ap01_agents_find_state, @function

/*
 * Return the AGENTS state attached to a child overlay of stock pet page 7.
 * Search from the last child backwards and fail closed when no tagged child
 * exists.  The state stores its root pointer at offset 28.
 */
ap01_agents_find_state:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    beqz a0, .Lfind_state_no
    li a1, 7
    call lv_obj_get_child
    beqz a0, .Lfind_state_no
    mv s1, a0
    call lv_obj_get_child_count
    mv s2, a0

.Lfind_state_loop:
    beqz s2, .Lfind_state_no
    addi s2, s2, -1
    mv a0, s1
    mv a1, s2
    call lv_obj_get_child
    beqz a0, .Lfind_state_loop
    mv s0, a0
    lw t0, 16(s0)
    beqz t0, .Lfind_state_loop
    lw t1, 0(t0)
    li t2, AGENTS_STATE_MAGIC
    bne t1, t2, .Lfind_state_loop
    lw t1, 4(t0)
    beqz t1, .Lfind_state_loop
    lw t1, 28(t0)
    bne t1, s0, .Lfind_state_loop
    mv a0, t0
    j .Lfind_state_done

.Lfind_state_no:
    li a0, 0

.Lfind_state_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    addi sp, sp, 32
    ret

    .size ap01_agents_find_state, .-ap01_agents_find_state
    .endif

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

    .ifdef SYNC_LOADER
    mv a0, s1
    call ap01_agents_find_state
    mv s2, a0
    beqz s2, .Lread_key
    lw t0, 24(s2)
    beqz t0, .Lread_key
    lw t1, 12(sp)
    li t2, 7
    beq t1, t2, .Lread_key
    sw zero, 24(s2)
    lw a0, 28(s2)
    li a1, 320
    call lv_obj_set_x
    .else
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
    .endif

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
    .ifdef SYNC_LOADER
    beqz s2, .Lstock_key_event
    lw t0, 24(s2)
    beqz t0, .Lsync_left_stock_page
    lw t0, 8(s2)
    beqz t0, .Lsync_leave_to_pet
    li t1, 1
    beq t0, t1, .Lshow_last_30_days
    addi t0, t0, -1
    j .Lshow_detail_index

.Lsync_leave_to_pet:
    sw zero, 24(s2)
    lw a0, 28(s2)
    li a1, 320
    call lv_obj_set_x
    j .Lkey_consumed

.Lsync_left_stock_page:
    lw t0, 12(sp)
    beqz t0, .Lsync_enter_from_power
    li t1, 3
    bltu t0, t1, .Lstock_key_event
    li t1, 7
    bltu t1, t0, .Lstock_key_event
    beq t0, t1, .Lsync_left_target_settings
    li t1, 3
    beq t0, t1, .Lsync_left_target_power
    addi a1, t0, -1
    j .Lsync_left_set_active

.Lsync_left_target_settings:
    li a1, 6
    j .Lsync_left_set_active

.Lsync_left_target_power:
    li a1, 0

.Lsync_left_set_active:
    mv a0, s1
    li a2, 2
    call window_set_active
    j .Lkey_consumed

.Lsync_enter_from_power:
    li t0, 1
    sw t0, 24(s2)
    lw a0, 28(s2)
    li a1, 0
    call lv_obj_set_x
    mv a0, s1
    li a1, 7
    li a2, 2
    call window_set_active
    j .Lkey_consumed
    .else
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
    .endif

.Lkey_right:
    .ifdef SYNC_LOADER
    beqz s2, .Lstock_key_event
    lw t0, 24(s2)
    beqz t0, .Lsync_right_stock_page
    lw t0, 8(s2)
    beqz t0, .Lsync_leave_to_power
    li t1, 3
    beq t0, t1, .Lshow_weekly
    addi t0, t0, 1
    j .Lshow_detail_index

.Lsync_leave_to_power:
    sw zero, 24(s2)
    lw a0, 28(s2)
    li a1, 320
    call lv_obj_set_x
    mv a0, s1
    li a1, 0
    li a2, 1
    call window_set_active
    j .Lkey_consumed

.Lsync_right_stock_page:
    lw t0, 12(sp)
    li t1, 7
    beq t0, t1, .Lsync_enter_from_pet
    beqz t0, .Lsync_right_target_time
    li t1, 3
    bltu t0, t1, .Lstock_key_event
    li t1, 6
    bltu t1, t0, .Lstock_key_event
    addi a1, t0, 1
    j .Lsync_right_set_active

.Lsync_right_target_time:
    li a1, 3

.Lsync_right_set_active:
    mv a0, s1
    li a2, 1
    call window_set_active
    j .Lkey_consumed

.Lsync_enter_from_pet:
    li t0, 1
    sw t0, 24(s2)
    lw a0, 28(s2)
    li a1, 0
    call lv_obj_set_x
    j .Lkey_consumed
    .else
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
    .endif

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
    .ifdef SYNC_LOADER
    beqz s2, .Lstock_key_event
    lw t1, 24(s2)
    beqz t1, .Lstock_key_event
    .else
    beqz s2, .Lstock_key_event
    .endif
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

    .ifdef SYNC_LOADER
    .align 2
    .global ap01_agents_detail_active
    .type ap01_agents_detail_active, @function

ap01_agents_detail_active:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    mv s0, a0
    lw s1, 0(s0)
    beqz s1, .Lagents_detail_no
    mv a0, s1
    call ap01_agents_find_state
    beqz a0, .Lagents_detail_no
    lw t0, 24(a0)
    beqz t0, .Lagents_detail_no
    lw a0, 8(a0)
    snez a0, a0
    j .Lagents_detail_done
.Lagents_detail_no:
    li a0, 0
.Lagents_detail_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    addi sp, sp, 32
    ret

    .size ap01_agents_detail_active, .-ap01_agents_detail_active
    .endif

    .endif
