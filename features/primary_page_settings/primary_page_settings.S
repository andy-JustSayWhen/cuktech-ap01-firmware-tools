    .option norelax
    .equ EVENT_KEY, 17
    .equ EVENT_DELETE, 41
    .equ KEY_RIGHT, 19
    .equ KEY_LEFT, 20
    .equ KEY_ENTER, 10
    .equ SETTINGS_TYPE, 26
    .equ SWITCH_TYPE, 34
    .equ SWITCH_MAGIC, 0x53504750
    .equ STATE_SIZE, 52
    .equ STATE_ROOT, 4
    .equ STATE_MARKER, 8
    .equ STATE_CHECK0, 12
    .equ STATE_MASK, 36
    .equ STATE_SELECTION, 40
    .equ STATE_SETTINGS_DATA, 44
    .equ PAGE_BIT_TIME, 0
    .equ PAGE_BIT_POWER, 1
    .equ PAGE_BIT_WEATHER, 2
    .equ PAGE_BIT_DATE, 3
    .equ PAGE_BIT_PET, 4
    .equ PAGE_BIT_AGENTS, 5
    .equ AGENTS_STATE_OVERVIEW, 1

    .section .text, "ax", @progbits
    .align 2
    .global ap01_page_settings_menu_dispatch
    .type ap01_page_settings_menu_dispatch, @function
ap01_page_settings_menu_dispatch:
    li t0, 6
    beq a5, t0, .Lappend_switch_row
    li t0, 7
    beq a5, t0, .Lcreate_stock_return
    li t0, 0xa01989e0
    jr t0

.Lappend_switch_row:
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s1
    la a1, page_settings_menu_label
    li a2, 0
    li a3, 0
    call stock_settings_row_create
    lw ra, 12(sp)
    addi sp, sp, 16
    li t0, 0xa01989b2
    jr t0

.Lcreate_stock_return:
    li t0, 0xa0198ad0
    jr t0
    .size ap01_page_settings_menu_dispatch, .-ap01_page_settings_menu_dispatch

    .align 2
    .global ap01_page_settings_event
    .type ap01_page_settings_event, @function
ap01_page_settings_event:
    addi sp, sp, -48
    sw ra, 44(sp)
    sw s0, 40(sp)
    sw s1, 36(sp)
    sw s2, 32(sp)
    sw s3, 28(sp)
    sw s4, 24(sp)
    mv s4, a0
    lw s0, 0(a0)
    beqz s0, .Ltail_stock
    lw s1, 16(s0)
    beqz s1, .Ltail_stock
    lw t0, 8(s4)
    li t1, 0xffff7fff
    and t0, t0, t1
    li t1, EVENT_KEY
    bne t0, t1, .Ltail_stock

    mv a0, s4
    call lv_event_get_key
    mv s3, a0
    mv a0, s0
    call ap01_page_settings_find_state
    mv s2, a0
    bnez s2, .Lcustom_key

    lbu t0, 2(s1)
    li t1, SETTINGS_TYPE
    bne t0, t1, .Ltail_stock
    li t0, KEY_RIGHT
    beq s3, t0, .Lmain_right
    li t0, KEY_LEFT
    beq s3, t0, .Lmain_left
    li t0, KEY_ENTER
    bne s3, t0, .Ltail_stock
    lbu t0, 1(s1)
    li t1, 54
    beq t0, t1, .Lopen_switch_page
    li t1, 55
    bne t0, t1, .Ltail_stock
    li t0, 54
    sb t0, 1(s1)
    j .Ltail_stock

.Lmain_right:
    lbu t0, 1(s1)
    li t1, 54
    bne t0, t1, .Ltail_stock
    li s2, 6
    li s3, 7
    li t0, 55
    sb t0, 1(s1)
    li s4, 460
    j .Lmain_transition

.Lmain_left:
    lbu t0, 1(s1)
    li t1, 55
    bne t0, t1, .Ltail_stock
    li s2, 7
    li s3, 6
    li t0, 54
    sb t0, 1(s1)
    li s4, 400

.Lmain_transition:
    mv a0, s0
    call ap01_page_settings_find_list
    beqz a0, .Lconsumed
    sw a0, 20(sp)
    mv a0, a0
    mv a1, s4
    li a2, 0
    call stock_scroll_to_y
    lw a0, 20(sp)
    mv a1, s2
    mv a2, s3
    call stock_selection_transition
    j .Lconsumed

.Lopen_switch_page:
    mv a0, s0
    mv a1, s1
    call ap01_page_settings_create
    j .Lconsumed

.Lcustom_key:
    li t0, KEY_RIGHT
    beq s3, t0, .Lcustom_next
    li t0, KEY_LEFT
    beq s3, t0, .Lcustom_previous
    li t0, KEY_ENTER
    beq s3, t0, .Lcustom_enter
    j .Lconsumed

.Lcustom_next:
    lw t0, STATE_SELECTION(s2)
    addi t0, t0, 1
    li t1, 7
    bltu t0, t1, .Lcustom_selection_ready
    li t0, 0
    j .Lcustom_selection_ready

.Lcustom_previous:
    lw t0, STATE_SELECTION(s2)
    bnez t0, .Lcustom_previous_nonzero
    li t0, 6
    j .Lcustom_selection_ready
.Lcustom_previous_nonzero:
    addi t0, t0, -1

.Lcustom_selection_ready:
    sw t0, STATE_SELECTION(s2)
    slli t1, t0, 4
    slli t2, t0, 3
    add t1, t1, t2
    slli t2, t0, 1
    add t1, t1, t2
    add t1, t1, t0
    addi a1, t1, 44
    lw a0, STATE_MARKER(s2)
    call lv_obj_set_y
    j .Lconsumed

.Lcustom_enter:
    lw t0, STATE_SELECTION(s2)
    li t1, 6
    beq t0, t1, .Lclose_switch_page
    li t1, 1
    sll t1, t1, t0
    lw s3, STATE_MASK(s2)
    xor s3, s3, t1
    mv a0, s3
    call ap01_page_settings_save_mask
    beqz a0, .Lconsumed
    sw s3, STATE_MASK(s2)
    mv a0, s2
    call ap01_page_settings_apply_checks
    j .Lconsumed

.Lclose_switch_page:
    lw t0, STATE_SETTINGS_DATA(s2)
    li t1, SETTINGS_TYPE
    sb t1, 2(t0)
    li t1, 54
    sb t1, 1(t0)
    lw a0, STATE_ROOT(s2)
    call lv_obj_del
    j .Lconsumed

.Lconsumed:
    lw ra, 44(sp)
    lw s0, 40(sp)
    lw s1, 36(sp)
    lw s2, 32(sp)
    lw s3, 28(sp)
    lw s4, 24(sp)
    addi sp, sp, 48
    ret

.Ltail_stock:
    mv a0, s4
    lw ra, 44(sp)
    lw s0, 40(sp)
    lw s1, 36(sp)
    lw s2, 32(sp)
    lw s3, 28(sp)
    lw s4, 24(sp)
    addi sp, sp, 48
    tail stock_settings_key_event
    .size ap01_page_settings_event, .-ap01_page_settings_event

    .align 2
    .global ap01_primary_page_filter_and_switch
    .type ap01_primary_page_filter_and_switch, @function
ap01_primary_page_filter_and_switch:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    sw s3, 12(sp)
    sw s4, 8(sp)
    sw s5, 4(sp)
    mv s0, a0
    mv s1, a1
    mv s2, a2
    mv s3, a1
    li s4, 0
    li t0, 1
    beq s2, t0, .Lfilter_load_mask
    li t0, 2
    bne s2, t0, .Lfilter_fallback

.Lfilter_load_mask:
    li t0, 1
    beq s1, t0, .Lfilter_fallback
    li t0, 2
    beq s1, t0, .Lfilter_fallback
    call ap01_page_settings_load_mask
    mv s5, a0

.Lfilter_check:
    li t0, 6
    bgeu s4, t0, .Lfilter_fallback
    beqz s1, .Lfilter_power
    li t0, 3
    beq s1, t0, .Lfilter_time
    li t0, 4
    beq s1, t0, .Lfilter_date
    li t0, 5
    beq s1, t0, .Lfilter_weather
    li t0, 6
    beq s1, t0, .Lfilter_switch
    li t0, 7
    beq s1, t0, .Lfilter_shared_page
    j .Lfilter_fallback

.Lfilter_power:
    li t0, PAGE_BIT_POWER
    j .Lfilter_test_bit
.Lfilter_time:
    li t0, PAGE_BIT_TIME
    j .Lfilter_test_bit
.Lfilter_date:
    li t0, PAGE_BIT_DATE
    j .Lfilter_test_bit
.Lfilter_weather:
    li t0, PAGE_BIT_WEATHER

.Lfilter_test_bit:
    li t1, 1
    sll t1, t1, t0
    and t1, t1, s5
    bnez t1, .Lfilter_switch
    j .Lfilter_advance

.Lfilter_shared_page:
    li t0, 2
    beq s2, t0, .Lfilter_shared_left
    li t0, PAGE_BIT_PET
    li t1, PAGE_BIT_AGENTS
    j .Lfilter_shared_bits_ready
.Lfilter_shared_left:
    li t0, PAGE_BIT_AGENTS
    li t1, PAGE_BIT_PET

.Lfilter_shared_bits_ready:
    li t2, 1
    sll t3, t2, t0
    and t3, t3, s5
    beqz t3, .Lfilter_shared_second
    li t3, PAGE_BIT_AGENTS
    beq t0, t3, .Lfilter_show_agents
    j .Lfilter_show_pet

.Lfilter_shared_second:
    sll t3, t2, t1
    and t3, t3, s5
    beqz t3, .Lfilter_advance
    li t3, PAGE_BIT_AGENTS
    beq t1, t3, .Lfilter_show_agents

.Lfilter_show_pet:
    mv a0, s0
    call ap01_agents_find_pet_state
    beqz a0, .Lfilter_switch
    call ap01_agents_restore_pet
    j .Lfilter_switch

.Lfilter_show_agents:
    mv a0, s0
    call ap01_agents_find_pet_state
    beqz a0, .Lfilter_fallback
    li a1, AGENTS_STATE_OVERVIEW
    call ap01_agents_show_page
    beqz a0, .Lfilter_fallback
    li s4, -1
    j .Lfilter_switch

.Lfilter_advance:
    addi s4, s4, 1
    li t0, 1
    beq s2, t0, .Lfilter_advance_right
    beqz s1, .Lfilter_left_power
    li t0, 3
    beq s1, t0, .Lfilter_left_time
    addi s1, s1, -1
    j .Lfilter_check
.Lfilter_left_power:
    li s1, 7
    j .Lfilter_check
.Lfilter_left_time:
    li s1, 0
    j .Lfilter_check

.Lfilter_advance_right:
    beqz s1, .Lfilter_right_power
    li t0, 7
    beq s1, t0, .Lfilter_right_pet
    addi s1, s1, 1
    j .Lfilter_check
.Lfilter_right_power:
    li s1, 3
    j .Lfilter_check
.Lfilter_right_pet:
    li s1, 0
    j .Lfilter_check

.Lfilter_switch:
    mv a0, s0
    mv a1, s1
    mv a2, s2
    call stock_switch_page
    bgez s4, .Lfilter_done
    mv a0, s0
    call stock_get_dispatch_index
    beq a0, s1, .Lfilter_done
    mv a0, s0
    call ap01_agents_find_pet_state
    beqz a0, .Lfilter_done
    call ap01_agents_restore_pet
    j .Lfilter_done

.Lfilter_fallback:
    mv a0, s0
    mv a1, s3
    mv a2, s2
    call stock_switch_page

.Lfilter_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    lw s3, 12(sp)
    lw s4, 8(sp)
    lw s5, 4(sp)
    addi sp, sp, 32
    ret
    .size ap01_primary_page_filter_and_switch, .-ap01_primary_page_filter_and_switch

    .align 2
    .type ap01_page_settings_find_state, @function
ap01_page_settings_find_state:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    mv s0, a0
    call lv_obj_get_child_count
    mv s1, a0
    li s2, 0
.Lfind_state_loop:
    bgeu s2, s1, .Lfind_state_missing
    mv a0, s0
    mv a1, s2
    call lv_obj_get_child
    beqz a0, .Lfind_state_next
    lw a0, 16(a0)
    beqz a0, .Lfind_state_next
    lw t0, 0(a0)
    li t1, SWITCH_MAGIC
    beq t0, t1, .Lfind_state_done
.Lfind_state_next:
    addi s2, s2, 1
    j .Lfind_state_loop
.Lfind_state_missing:
    li a0, 0
.Lfind_state_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    addi sp, sp, 32
    ret

    .align 2
    .type ap01_page_settings_find_list, @function
ap01_page_settings_find_list:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    sw s2, 16(sp)
    mv s0, a0
    call lv_obj_get_child_count
    mv s1, a0
    li s2, 0
.Lfind_list_loop:
    bgeu s2, s1, .Lfind_list_missing
    mv a0, s0
    mv a1, s2
    call lv_obj_get_child
    beqz a0, .Lfind_list_next
    lw t0, 16(a0)
    beqz t0, .Lfind_list_next
    lw t1, 0(t0)
    li t2, SETTINGS_TYPE
    bne t1, t2, .Lfind_list_next
    lw t0, 4(t0)
    beqz t0, .Lfind_list_missing
    lw a0, 8(t0)
    j .Lfind_list_done
.Lfind_list_next:
    addi s2, s2, 1
    j .Lfind_list_loop
.Lfind_list_missing:
    li a0, 0
.Lfind_list_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    lw s2, 16(sp)
    addi sp, sp, 32
    ret

    .align 2
    .type ap01_page_settings_create, @function
ap01_page_settings_create:
    addi sp, sp, -48
    sw ra, 44(sp)
    sw s0, 40(sp)
    sw s1, 36(sp)
    sw s2, 32(sp)
    sw s3, 28(sp)
    mv s2, a0
    mv s3, a1
    li a0, STATE_SIZE
    call malloc
    beqz a0, .Lcreate_done
    mv s1, a0
    li t0, SWITCH_MAGIC
    sw t0, 0(s1)
    sw s3, STATE_SETTINGS_DATA(s1)
    sw zero, STATE_SELECTION(s1)
    call ap01_page_settings_load_mask
    sw a0, STATE_MASK(s1)

    mv a0, s2
    call lv_obj_create
    beqz a0, .Lcreate_free
    mv s0, a0
    sw s0, STATE_ROOT(s1)
    sw s1, 16(s0)
    mv a0, s0
    la a1, ap01_page_settings_delete_event
    li a2, EVENT_DELETE
    li a3, 0
    call lv_obj_add_event_cb
    mv a0, s0
    li a1, 320
    li a2, 240
    call lv_obj_set_size
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
    mv a1, s0
    la a2, page_settings_background_descriptor
    call lv_gif_create
    beqz a0, .Lcreate_delete
    mv a0, s0
    mv a1, s0
    la a2, page_settings_marker_descriptor
    call lv_gif_create
    beqz a0, .Lcreate_delete
    sw a0, STATE_MARKER(s1)
    li a1, 8
    call lv_obj_set_x
    lw a0, STATE_MARKER(s1)
    li a1, 44
    call lv_obj_set_y

    li s2, 0
.Lcreate_check_loop:
    li t0, 6
    bgeu s2, t0, .Lcreate_checks_done
    mv a0, s0
    mv a1, s0
    la a2, page_settings_check_descriptor
    call lv_gif_create
    beqz a0, .Lcreate_delete
    slli t0, s2, 2
    add t0, t0, s1
    sw a0, STATE_CHECK0(t0)
    li a1, 285
    call lv_obj_set_x
    slli t0, s2, 4
    slli t1, s2, 3
    add t0, t0, t1
    slli t1, s2, 1
    add t0, t0, t1
    add t0, t0, s2
    addi a1, t0, 46
    slli t0, s2, 2
    add t0, t0, s1
    lw a0, STATE_CHECK0(t0)
    call lv_obj_set_y
    addi s2, s2, 1
    j .Lcreate_check_loop

.Lcreate_checks_done:
    mv a0, s1
    call ap01_page_settings_apply_checks
    li t0, SWITCH_TYPE
    sb t0, 2(s3)
    li t0, 80
    sb t0, 1(s3)
    j .Lcreate_done

.Lcreate_delete:
    mv a0, s0
    call lv_obj_del
    j .Lcreate_done
.Lcreate_free:
    mv a0, s1
    call free
.Lcreate_done:
    lw ra, 44(sp)
    lw s0, 40(sp)
    lw s1, 36(sp)
    lw s2, 32(sp)
    lw s3, 28(sp)
    addi sp, sp, 48
    ret

    .align 2
    .type ap01_page_settings_apply_checks, @function
ap01_page_settings_apply_checks:
    addi sp, sp, -32
    sw ra, 28(sp)
    sw s0, 24(sp)
    sw s1, 20(sp)
    mv s0, a0
    li s1, 0
.Lapply_check_loop:
    li t0, 6
    bgeu s1, t0, .Lapply_check_done
    slli t0, s1, 2
    add t0, t0, s0
    lw a0, STATE_CHECK0(t0)
    lw t1, STATE_MASK(s0)
    srl t1, t1, s1
    andi t1, t1, 1
    beqz t1, .Lhide_check
    li a1, 1
    call lv_obj_remove_flag
    j .Lapply_check_next
.Lhide_check:
    li a1, 1
    call lv_obj_add_flag
.Lapply_check_next:
    addi s1, s1, 1
    j .Lapply_check_loop
.Lapply_check_done:
    lw ra, 28(sp)
    lw s0, 24(sp)
    lw s1, 20(sp)
    addi sp, sp, 32
    ret

    .align 2
    .type ap01_page_settings_delete_event, @function
ap01_page_settings_delete_event:
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

    .section .rodata, "a", @progbits
    .balign 4
page_settings_menu_label:
    .asciz "开关一级页面"
