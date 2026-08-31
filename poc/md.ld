OUTPUT_ARCH(m68k)
ENTRY(_start)

SECTIONS
{
    . = 0x00000000;
    .vectors : { KEEP(*(.text.vectors)) }
    . = 0x00000100;
    .header  : { KEEP(*(.text.header)) }
    . = 0x00000200;
    .text    : { *(.text*) *(.rodata*) . = ALIGN(2); }
    _rom_end = .;

    . = 0x00FF0000;
    .bss (NOLOAD) : {
        _bss_start = .;
        *(.bss*) *(COMMON) *(.data*)
        . = ALIGN(4);
        _bss_end = .;
    }
}
