OUTPUT_ARCH(riscv)
ENTRY(ap01_page_settings_single_iteration_append)

MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0xA02465D0, LENGTH = 60934
}

PROVIDE(stock_settings_row_create = 0xA0192FB4);
PROVIDE(stock_settings_return_create = 0xA0193058);

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
