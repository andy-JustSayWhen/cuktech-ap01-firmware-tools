OUTPUT_ARCH(riscv)
ENTRY(payload_start)

selection_transition = 0xa00f3d5a;
list_item_count = 0xa00c5fe4;
list_position_adjust = 0xa00c6dfe;
handler_return = 0xa00f80d8;
right_original_switch = 0xa00f81a2;
left_original_switch = 0xa00f876e;
encoder_irq_return = 0xa0107cbc;

SECTIONS
{
    .payload 0xa001b008 :
    {
        KEEP(*(.payload))
    }
    ASSERT(SIZEOF(.payload) == 0xa4, "payload size mismatch")
    ASSERT(payload_end == 0xa001b0ac, "payload end mismatch")

    .right_hook 0xa00f819e :
    {
        KEEP(*(.right_hook))
    }
    ASSERT(SIZEOF(.right_hook) == 4, "right hook must be four bytes")

    .left_hook 0xa00f876a :
    {
        KEEP(*(.left_hook))
    }
    ASSERT(SIZEOF(.left_hook) == 4, "left hook must be four bytes")

    .encoder_direction_filter 0xa0107e20 :
    {
        KEEP(*(.encoder_direction_filter))
    }
    ASSERT(
        SIZEOF(.encoder_direction_filter) == 2,
        "encoder direction filter must be two bytes"
    )
    ASSERT(
        ADDR(.encoder_direction_filter) - 0x164 == encoder_irq_return,
        "encoder direction filter return target mismatch"
    )

    /DISCARD/ :
    {
        *(.riscv.attributes)
        *(.comment)
    }
}
