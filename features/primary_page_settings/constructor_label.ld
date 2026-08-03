OUTPUT_ARCH(riscv)
ENTRY(ap01_page_settings_return_label)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

SECTIONS
{
    .payload :
    {
        KEEP(*(.text.entry))
        *(.text .text.*)
        *(.rodata .rodata.*)
    } > PAYLOAD

    /DISCARD/ :
    {
        *(.comment)
        *(.note*)
        *(.riscv.attributes)
        *(.eh_frame*)
    }
}
