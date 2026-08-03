OUTPUT_ARCH(riscv)
ENTRY(ap01_page_settings_row_creation)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(stock_settings_row_create = 0xA0192FB4);

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
