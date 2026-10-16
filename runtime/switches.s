; --- the RM2k switches --------------------------------------------------------
; One bit per switch, from 0 up to the highest the game names: the converter
; writes `SWITCH_BYTES` —the event compiler's `switch_top` over eight, plus
; one—, so the table is the game's size and every switch a page, a common
; event, a troop page or the database names fits in it. They start off at
; reset, as a new RM2k game does, and travel in the save.
;
; Until 2026-10-15 the table was 128 bytes in bank 0's BSS for every game:
; ABL names up to 1008, but Vampires Dawn goes up to 1643 and The Frozen
; World to 1077, and their `ControlSwitches` wrote past it while their page
; conditions read whatever followed. It is a segment of its own, `SWITCHES`,
; which the linker places in far RAM next to `FARBSS` —see `FAR_POOL_START`
; in rm2k-snes/cartridge/src/banks.rs—, and a game that names more than 2047
; is refused by the converter.
;
; **The label carries the bank, `$7E`**: it is reached with `f:switches, x`
; whatever the data bank, and `.loword(switches)` only where the data bank
; is `$7E` —the battle— or in a `.word` —`save_table`—. A plain `switches, y`
; does not assemble. The byte a switch is in fits in eight bits, which is
; what `compar_table` keeps.
.pushseg
.segment "SWITCHES": far
switches: .res SWITCH_BYTES
.popseg
.assert SWITCH_BYTES <= 256, error, "the switch table's index is a byte: see compar_table"
