OUTPUT_ARCH(riscv)
ENTRY(payload_start)

selection_transition = 0xa00f3d5a;
handler_return = 0xa00f80d8;
right_original_switch = 0xa00f81a2;
left_original_switch = 0xa00f876e;

SECTIONS
{
    .payload 0xa001b008 :
    {
        KEEP(*(.payload))
    }
    ASSERT(SIZEOF(.payload) == 0x76, "payload size mismatch")
    ASSERT(payload_end == 0xa001b07e, "payload end mismatch")

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

    /DISCARD/ :
    {
        *(.riscv.attributes)
        *(.comment)
    }
}
