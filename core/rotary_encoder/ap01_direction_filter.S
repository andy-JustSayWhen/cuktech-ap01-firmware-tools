    .option rvc

    .section .encoder_direction_filter, "ax"
    .globl encoder_direction_filter
encoder_direction_filter:
    c.j . - 0x164
