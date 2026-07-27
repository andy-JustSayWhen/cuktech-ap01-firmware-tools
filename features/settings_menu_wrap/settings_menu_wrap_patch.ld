OUTPUT_ARCH(riscv)
ENTRY(right_log_tail)

SECTIONS
{
    .patch_map 0xa00f3d5a :
    {
        KEEP(*(.patch_map))
    }
    ASSERT(selection_transition == 0xa00f3d5a, "selection transition address mismatch")
    ASSERT(handler_return == 0xa00f80d8, "handler return address mismatch")
    ASSERT(right_log_tail == 0xa00f8134, "right log tail address mismatch")
    ASSERT(right_original_path - right_log_tail == 26, "right log tail must be 26 bytes")
    ASSERT(right_type_log == 0xa00f8172, "right type log address mismatch")
    ASSERT(right_type_original_path - right_type_log == 26, "right type log must be 26 bytes")
    ASSERT(right_state_load == 0xa00f819e, "right state load address mismatch")
    ASSERT(left_log_tail == 0xa00f8700, "left log tail address mismatch")
    ASSERT(left_original_path - left_log_tail == 26, "left log tail must be 26 bytes")
    ASSERT(left_type_log == 0xa00f873e, "left type log address mismatch")
    ASSERT(left_type_original_path - left_type_log == 26, "left type log must be 26 bytes")
    ASSERT(left_state_load == 0xa00f876a, "left state load address mismatch")
    ASSERT(SIZEOF(.patch_map) == 0x4a14, "patch map end mismatch")

    /DISCARD/ :
    {
        *(.riscv.attributes)
        *(.comment)
    }
}
