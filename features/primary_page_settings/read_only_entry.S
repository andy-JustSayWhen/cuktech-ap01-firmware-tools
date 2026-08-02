    .option norelax
    .equ EVENT_KEY, 17
    .equ KEY_RIGHT, 19
    .equ KEY_LEFT, 20
    .equ KEY_ENTER, 10
    .equ SETTINGS_TYPE, 26

    .section .text.entry, "ax", @progbits
    .align 2
    .global ap01_page_settings_read_only_menu_dispatch
    .type ap01_page_settings_read_only_menu_dispatch, @function
ap01_page_settings_read_only_menu_dispatch:
    li t0, 6
    beq a5, t0, .Lappend_read_only_row
    li t0, 7
    beq a5, t0, .Lcreate_stock_return
    li t0, 0xa01989e0
    jr t0

.Lappend_read_only_row:
    addi sp, sp, -16
    sw ra, 12(sp)
    mv a0, s1
    la a1, page_settings_read_only_label
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
    .size ap01_page_settings_read_only_menu_dispatch, .-ap01_page_settings_read_only_menu_dispatch

    .align 2
    .global ap01_page_settings_read_only_event
    .type ap01_page_settings_read_only_event, @function
ap01_page_settings_read_only_event:
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
    beq t0, t1, .Lconsumed
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
    call ap01_page_settings_read_only_find_list
    beqz a0, .Lconsumed
    sw a0, 20(sp)
    mv a1, s4
    li a2, 0
    call stock_scroll_to_y
    lw a0, 20(sp)
    mv a1, s2
    mv a2, s3
    call stock_selection_transition

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
    .size ap01_page_settings_read_only_event, .-ap01_page_settings_read_only_event

    .align 2
    .type ap01_page_settings_read_only_find_list, @function
ap01_page_settings_read_only_find_list:
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
    .size ap01_page_settings_read_only_find_list, .-ap01_page_settings_read_only_find_list

    .section .rodata, "a", @progbits
    .balign 4
page_settings_read_only_label:
    .asciz "开关一级页面"
