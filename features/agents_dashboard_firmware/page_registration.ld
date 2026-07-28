OUTPUT_ARCH(riscv)
ENTRY(ap01_agents_page_register)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(lv_obj_create = 0xA00C1EC6);
PROVIDE(lv_obj_set_size = 0xA00C0060);

SECTIONS
{
    .payload :
    {
        KEEP(*(.payload))
    } > PAYLOAD

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.riscv.attributes)
    }
}
