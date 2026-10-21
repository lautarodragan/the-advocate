; --- the debug screen ---------------------------------------------------------
;
; RPG_RT's F9, `Scene_Debug` in a test play: the switches and the variables,
; turned on and off and changed by hand. The console has no F9, so it is one
; more option of the pause menu, its last row —see `menu_rows_build` and
; `cm_from_menu`, in custom_menu.s—, and only in a
; cartridge whose project asks for it with `[debug] debug_screen`: **without
; it this file assembles nothing**, not even its segment, so that ROM is the
; same byte for byte as before the screen existed.
;
; **What it shows is RPG_RT 2000's**, measured under Wine: two windows, the
; ranges on the left —ten rows of `S[0001-0010]`— and the list on the
; right —ten rows of `0001: Name` and `[ON]` or `[OFF]`, or a variable's
; value right-aligned—. In the ranges up and down go round the page's ten,
; left and right flip pages of ten ranges, round, and after the switches'
; pages come the variables'; A goes into the list, on its first row, and B
; leaves. In the list up and down go round its rows, A turns a switch on or
; off, and B goes back to the ranges. The ranges' cursor stays on while the
; list has its own, as in RPG_RT.
;
; **What it does not do like RPG_RT**: a variable is changed with left and
; right by one and with L and R by ten, where RPG_RT opens a number input
; of seven digits; and a variable the cartridge does not keep —no page of
; its maps names it: see `VARIABLES_N` in far_ram.s— shows a grey `-` and
; does not change, and a switch past the table, `SWITCH_BYTES`, a grey
; `[OFF]`. See `what-the-debug-screen-does-not-model` in the book.
;
; **A change takes effect when the map comes back**, as in RPG_RT, where the
; map's `need_refresh` is looked at on its next frame: a switch or a variable
; that changes asks for the pages' refresh —`refresh`—, and the pause menu
; asks the pure parallel common events to run again when it closes
; —`compar_owe`—.
;
; **It is in the console's 512-wide mode**, mode 5, since 2026-10-20 —taro's,
; so that the switches' names fit—: the text on BG1 with the text layer in
; its wide mode —`tl_hires`: the font's same pixels, half as wide on
; screen—, its quads from word 0 up to `CM_BG1_MAP`; the windows on BG2 at
; 2bpp, each tilemap word a cell 16 pixels wide, with their tiles from
; `CM_BG1_VRAM` and their colours in the first 32 entries; and no objects
; —`TM` and `TS` show BG1 and BG2 only, both, which is what shows every
; pixel of the 512—. The text's inks go after the windows' colours, in
; palettes 2 and 3: `DBG_WHITE` and `DBG_GREY`. When B leaves, mode 3 and
; no subscreen again, which is what the pause menu draws in. The map comes
; back as from a custom menu: `CM_DIRTY`, and `big_back_far` when the pause
; menu closes.
;
; The geometry and the data are `rm2k-snes-screens`'s `debug_screen.rs`,
; which says how `dbg_data` is laid out. It lives in `FAR3`, entered with
; `jsl` from `cm_from_menu` with the pause menu's data bank, 0.

.if ::DEBUG_SCREEN
.pushseg
.segment "FAR3"
.a8
.i16

.assert DBG_BORDER_TILES > 0 && DBG_BORDER_COLORS > 0, error, "the debug screen has no windows: a DMA of 0 bytes is 64 KB"
.assert CM_BG1_VRAM + DBG_BORDER_TILES * 8 <= $8000, error, "the debug screen's windows do not fit in the VRAM"
.assert DBG_CGRAM + DBG_BORDER_COLORS <= 32, error, "the debug screen's colours are not BG2's eight palettes at 2bpp"
.assert DBG_PAGES > 0, error, "the debug screen has nothing to show"

; A bar's two cell rows, in bytes, as `dbg_bars` keeps them: the ranges' ten
; and then the list's.
DBG_BAR_BYTES = 2 * 32 * 2
; The text's colours: `items_cgram`'s two palettes, white and grey, after
; the windows' eight of four.
DBG_INKS     = 32
DBG_WHITE    = DBG_INKS / 16
DBG_GREY     = DBG_WHITE + 1
.assert ITEMS_CGRAM_N = 32, error, "the debug screen takes items_cgram's two first palettes as its white and grey"
; The text's quads: from word 0 up to the windows' tilemap, below the
; text's own; four tiles each, and a tilemap word names 1024 tiles.
DBG_QUADS    = CM_BG1_MAP / 64 - 1
.assert CM_BG1_MAP <= SLOT_MAP, error, "the debug screen's quads reach the text's tilemap"
.assert DBG_QUADS < TL_PAIRS && 4 * DBG_QUADS + 3 < 1024, error, "the debug screen's quads do not fit the text layer's tables or BG1's tiles"
; Two bytes that say the state below is the screen's and not the garbage
; WRAM starts with: the page and the cursors are kept from one opening to
; the next, as easyrpg-player keeps them.
DBG_MAGIC = $D9F9

.pushseg
.segment "FARBSS"
dbg_ram: .res 36
.popseg
DBG_SEEN     = dbg_ram + 0      ; DBG_MAGIC once it was opened
DBG_PAGE     = dbg_ram + 2      ; the page of ten ranges
DBG_RANGE    = dbg_ram + 3      ; the range, in the page
DBG_ROW      = dbg_ram + 4      ; the row, in the list
DBG_LEVEL    = dbg_ram + 5      ; 0 the ranges, 1 the list
DBG_KIND     = dbg_ram + 6      ; 0 the page is switches, 1 variables
DBG_RANGES   = dbg_ram + 7      ; how many ranges the page has
DBG_COUNT    = dbg_ram + 8      ; how many rows the range has
DBG_BAR_R    = dbg_ram + 9      ; the ranges' bar on screen, $FF none
DBG_BAR_L    = dbg_ram + 10     ; the list's
DBG_LR       = dbg_ram + 11     ; L and R last frame, for their edges
DBG_W        = dbg_ram + 12     ; the window a bar goes in: 0 or 1
DBG_BASE     = dbg_ram + 14     ; the page's first number, less one
DBG_N        = dbg_ram + 16     ; how many switches or variables there are
DBG_FIRST    = dbg_ram + 18     ; the range's first number
DBG_T0       = dbg_ram + 20     ; scratch words
DBG_T1       = dbg_ram + 22
DBG_LEN      = dbg_ram + 24     ; a DMA's bytes
DBG_SRC      = dbg_ram + 26     ; and its source, a word and a bank
DBG_SRC_BK   = dbg_ram + 28
DBG_VRAM     = dbg_ram + 30     ; and where in the VRAM, a word
DBG_ON       = dbg_ram + 32     ; nonzero: a bar goes on, zero: off
DBG_SROW     = dbg_ram + 33     ; the screen row being written

; From `cm_from_menu`: the screen, until B leaves it from the ranges.
.proc debug_screen
.a8
.i16
    lda #1
    sta f:CM_DIRTY              ; the map comes back whole when the menu closes
    rep #$20
.a16
    lda f:DBG_SEEN
    cmp #DBG_MAGIC
    beq seen
    lda #DBG_MAGIC
    sta f:DBG_SEEN
    sep #$20
.a8
    lda #0
    sta f:DBG_PAGE
    sta f:DBG_RANGE
seen:
    sep #$20
.a8
    lda #0
    sta f:DBG_LEVEL
    sta f:DBG_ROW
    lda f:JOY1L
    sta f:DBG_LR
    jsr page_set
    jsr dbg_upload
    jsr dbg_view
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    jsr bars_upload             ; in the vblank, before the text's
    jsl f:tl_map + FAST         ; `scr_upload`
    jsl f:tl_vblank + FAST
    jsl f:tl_work + FAST
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    ; L and R, which `read_pad` does not keep: their edges, by hand.
    lda f:DBG_LR
    eor #$FF
    sta f:DBG_T0
    lda f:JOY1L
    sta f:DBG_LR
    and f:DBG_T0
    and #(PAD_L | PAD_R)
    sta f:DBG_T1                ; L and R just pressed
    lda f:DBG_LEVEL
    beq ranges
    jmp list

ranges:
    lda title_edges
    and #PAD_B
    beq ranges_no_b
    ; Out: the B that closes and the A from before are consumed, as the
    ; pause menu does; and what of the objects the windows' colours took.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    jmp objects_back
ranges_no_b:
    lda pad_a
    beq ranges_no_a
    lda pad_a_prev
    bne ranges_no_a             ; it was already held: not an edge
    lda #1
    sta f:DBG_LEVEL
    lda #0
    sta f:DBG_ROW
    jmp changed
ranges_no_a:
    lda title_edges
    and #(PAD_UP | PAD_DOWN)
    beq ranges_no_vertical
    and #PAD_DOWN
    beq range_up
    lda f:DBG_RANGE
    inc a
    cmp f:DBG_RANGES
    bcc range_moved
    lda #0
    bra range_moved
range_up:
    lda f:DBG_RANGE
    bne range_above
    lda f:DBG_RANGES
range_above:
    dec a
range_moved:
    sta f:DBG_RANGE
    jmp changed
ranges_no_vertical:
    lda title_edges
    and #(PAD_LEFT | PAD_RIGHT)
    beq to_wait
    and #PAD_RIGHT
    beq page_left
    lda f:DBG_PAGE
    inc a
    cmp #DBG_PAGES
    bcc page_moved
    lda #0
    bra page_moved
page_left:
    lda f:DBG_PAGE
    bne page_above
    lda #DBG_PAGES
page_above:
    dec a
page_moved:
    sta f:DBG_PAGE
    jsr page_set                ; the same range, if the page has as many
    jmp changed
to_wait:
    jmp wait

list:
    lda title_edges
    and #PAD_B
    beq list_no_b
    lda #0
    sta f:DBG_LEVEL
    jmp changed
list_no_b:
    lda title_edges
    and #(PAD_UP | PAD_DOWN)
    beq list_no_vertical
    and #PAD_DOWN
    beq row_up
    lda f:DBG_ROW
    inc a
    cmp f:DBG_COUNT
    bcc row_moved
    lda #0
    bra row_moved
row_up:
    lda f:DBG_ROW
    bne row_above
    lda f:DBG_COUNT
row_above:
    dec a
row_moved:
    sta f:DBG_ROW
    bra changed
list_no_vertical:
    lda f:DBG_KIND
    bne variable
    ; A switch: A turns it on or off.
    lda pad_a
    beq to_wait
    lda pad_a_prev
    bne to_wait                 ; it was already held: not an edge
    jsr switch_flip
    bra changed
variable:
    ; A variable: left and right by one, L and R by ten.
    rep #$20
.a16
    lda #1
    sta f:DBG_T0
    sep #$20
.a8
    lda title_edges
    and #(PAD_LEFT | PAD_RIGHT)
    bne by
    lda #10
    sta f:DBG_T0
    lda f:DBG_T1
    beq to_wait
    and #PAD_R
    bra sign
by:
    and #PAD_RIGHT
sign:
    bne add
    rep #$20
.a16
    lda #0
    sec
    sbc f:DBG_T0
    sta f:DBG_T0
    sep #$20
.a8
add:
    jsr variable_add
changed:
    jsr range_set
    jsr compose
    jmp wait
.endproc

; What the objects had of the colour memory and of OBSEL, back, and the
; pause menu's mode: the pause menu draws itself again over the rest.
; `cm_objects_back`, which is in FAR2. Returns from the screen.
.proc objects_back
.a8
.i16
    lda #$80
    sta INIDISP
    lda #$03                    ; the pause menu's mode, and no subscreen
    sta BGMODE
    stz TS
    lda #0
    jsl f:tl_hires              ; the strips the menu composes are 256 wide
    ldx map_ofs
    lda f:map_table + M_OBSEL_VALUE, x
    sta OBSEL
    rep #$20
.a16
    lda #(128 * 2)
    sta f:DBG_LEN
    ldx #.loword(cgram_shadow + 2 * 128)
    sep #$20
.a8
    ldy #128
    lda #^cgram_shadow
    jsr dma_cgram
    rtl
.endproc

; --- the page and the range ---------------------------------------------------

; The page's kind, its first number less one, how many there are of its
; kind and how many of its ranges have something.
.proc page_set
.a8
.i16
    lda f:DBG_PAGE
    cmp #DBG_PAGES
    bcc in_range
    lda #0                      ; the garbage of a first opening
    sta f:DBG_PAGE
in_range:
    ldx #0
    cmp #DBG_SWITCH_PAGES
    bcc switches
    sbc #DBG_SWITCH_PAGES       ; the carry is set
    inx
switches:
    sta f:DBG_T0
    txa
    sta f:DBG_KIND
    rep #$20
.a16
    lda f:DBG_T0
    and #$00FF
    asl a
    asl a
    sta f:DBG_T1                ; times 4
    asl a
    asl a
    asl a
    sta f:DBG_BASE              ; times 32
    asl a                       ; times 64
    clc
    adc f:DBG_BASE              ; times 96
    clc
    adc f:DBG_T1                ; times 100
    sta f:DBG_BASE
    lda #DBG_SWITCHES
    cpx #0
    beq kind_n
    lda #DBG_VARIABLES
kind_n:
    sta f:DBG_N
    ; The ranges with something: what is left of the kind past the base,
    ; in tens, rounded up, ten at most.
    sec
    sbc f:DBG_BASE
    clc
    adc #9
    ldx #0
tens:
    cmp #10
    bcc counted
    sbc #10                     ; the carry is set
    inx
    cpx #DBG_ROWS
    bcc tens
counted:
    sep #$20
.a8
    txa
    sta f:DBG_RANGES
    lda f:DBG_RANGE
    cmp f:DBG_RANGES
    bcc ready
    lda f:DBG_RANGES            ; the last one the page has
    dec a
    sta f:DBG_RANGE
ready:
    rts
.endproc

; Range A's first number, into A16 and `DBG_T0`: the page's base, ten per
; range, plus one. Returns with A16.
.proc range_first
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sta f:DBG_T0
    asl a
    asl a
    clc
    adc f:DBG_T0
    asl a                       ; times ten
    sec                         ; and one
    adc f:DBG_BASE
    sta f:DBG_T0
    rts
.endproc

; The range under the cursor: its first number and how many rows it has;
; and the list's row inside them.
.proc range_set
.a8
.i16
    lda f:DBG_RANGE
    jsr range_first
.a16
    sta f:DBG_FIRST
    lda f:DBG_N
    sec
    sbc f:DBG_FIRST
    inc a                       ; how many from the first on
    cmp #DBG_ROWS
    bcc few
    lda #DBG_ROWS
few:
    sep #$20
.a8
    sta f:DBG_COUNT
    lda f:DBG_ROW
    cmp f:DBG_COUNT
    bcc ready
    lda #0
    sta f:DBG_ROW
ready:
    rts
.endproc

; --- what a switch or a variable is -----------------------------------------

; Switch A16's byte in X and its mask in A8, carry set; carry clear if it is
; past the table, which holds the switches the game names: see switches.s.
.proc switch_bit
.a16
.i16
    cmp #(SWITCH_BYTES * 8)
    bcs none
    pha
    lsr a
    lsr a
    lsr a
    sta f:DBG_T1                ; the byte
    pla
    and #$0007
    tax
    sep #$20
.a8
    lda f:mask, x
    pha
    rep #$20
.a16
    lda f:DBG_T1
    tax
    sep #$20
.a8
    pla
    sec
    rts
.a16
none:
    sep #$20
.a8
    clc
    rts
.endproc

; The switch under the list's cursor, on if it was off and off if it was on;
; and the pages' refresh.
.proc switch_flip
.a8
.i16
    jsr cursor_number
.a16
    jsr switch_bit
.a8
    bcc ready
    sta f:DBG_T1
    lda f:switches, x
    eor f:DBG_T1
    sta f:switches, x
    jsr refresh_asked
ready:
    rts
.endproc

; The number under the list's cursor, in A16.
.proc cursor_number
.a8
.i16
    lda f:DBG_ROW
    rep #$20
.a16
    and #$00FF
    clc
    adc f:DBG_FIRST
    rts
.endproc

; Where the cartridge keeps variable A16, its slot times two, in X; carry
; clear if it does not keep it. Clobbers A.
.proc variable_slot
.a16
.i16
    dec a
    asl a
    asl a                       ; four bytes each
    clc
    adc #(DBG_VAR_TABLE + 2)
    tax
    lda f:dbg_data, x
    tax
    cmp #$FFFF
    beq none
    sec
    rts
none:
    clc
    rts
.endproc

; `DBG_T0`, signed, added to the variable under the list's cursor, at the
; sixteen bits the runtime keeps them in —see `var_write`—; and the pages'
; refresh.
.proc variable_add
.a8
.i16
    jsr cursor_number
.a16
    jsr variable_slot
    bcc ready
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    clc
    adc f:DBG_T0
    bvc kept
    ; Past the edge: the edge, on the side it went past.
    lda f:DBG_T0
    bmi low
    lda #$7FFF
    bra kept
low:
    lda #$8000
kept:
    sta f:FAR_LENGTH + FAR_VARIABLES, x
    sep #$20
.a8
    jsr refresh_asked
ready:
    sep #$20
.a8
    rts
.endproc

; A switch or a variable changed: the pages that ask for it may change, on
; the map's next frame —`set_switch` and `var_note` ask for the same—.
.proc refresh_asked
.a8
.i16
    lda #1
    sta f:refresh
    rts
.endproc

; --- writing ----------------------------------------------------------------
;
; Through the text layer, as the custom menus write: at `pick_table` —row *
; 64 + cell * 2— in colour `temp + 1`, `DBG_WHITE` or `DBG_GREY`.

; `pick_table` to row A, cell Y. Keeps X and Y.
.proc at
.a8
.i16
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a                       ; times 64
    sta pick_table
    tya
    and #$00FF
    asl a
    clc
    adc pick_table
    sta pick_table
    sep #$20
.a8
    rts
.endproc

; Letter A, after the last one written. Keeps X.
.proc letter
.a8
.i16
    phx
    jsl f:tl_letter + FAST
    plx
    rts
.endproc

; A16, 0 to 9999, as four digits with the zeroes in front, as RPG_RT writes
; a number. Returns with A8. Clobbers X, Y, `DBG_T1` and `DBG_LEN`.
.proc four_digits
.a16
.i16
    sta f:DBG_T1
    ldy #1000
    jsr digit
    ldy #100
    jsr digit
    ldy #10
    jsr digit
    ldy #1
    jsr digit
    sep #$20
.a8
    rts
.a16
digit:
    tya
    sta f:DBG_LEN               ; the place's value
    ldx #0
count:
    lda f:DBG_T1
    cmp f:DBG_LEN
    bcc counted
    sbc f:DBG_LEN               ; the carry is set
    sta f:DBG_T1
    inx
    bra count
counted:
    sep #$20
.a8
    txa
    clc
    adc #'0'
    jsr letter
    rep #$20
.a16
    rts
.endproc

; The string at offset X of `dbg_data`, by reference, at `pick_table`.
.proc string_at
.a8
.i16
    lda f:dbg_data, x
    beq none
    sta temp                    ; how many letters
    rep #$20
.a16
    txa
    clc
    adc #.loword(dbg_data + 1)
    sta msg_ptr
    sep #$20
.a8
    lda #^dbg_data
    sta msg_ptr + 2
    lda #1
    sta f:$7E0000 + TL_BY_REF
    lda #255
    sta comp_dup + 3
    jsl f:tl_text_at + FAST
none:
    rts
.endproc

; A16, signed, right-aligned to end with the cell at `pick_table`. As
; `cm_digits`, with the hardware's divider. Returns with A8.
.proc number_right
.a16
.i16
    ldx #0
    cmp #$8000
    bcc positive
    eor #$FFFF
    inc a
    pha
    sep #$20
.a8
    lda #('-' - ' ')
    sta f:$7E0000 + TL_DIG
    inx
    rep #$20
.a16
    pla
positive:
    ldy #0
divide:
    sta f:DBG_T1
    sep #$20
.a8
    lda f:DBG_T1
    sta WRDIVL
    lda f:DBG_T1 + 1
    sta WRDIVH
    lda #10
    sta WRDIVB                  ; sixteen cycles until the quotient is there
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDMPYL                  ; the remainder
    pha
    iny
    rep #$20
.a16
    lda RDDIVL
    bne divide
    sep #$20
.a8
put:
    pla
    clc
    adc #('0' - ' ')
    sta f:$7E0000 + TL_DIG, x
    inx
    dey
    bne put
    txa
    sta f:$7E0000 + TL_DIG_N
    jsl f:tl_right + FAST
    rts
.endproc

; The text of the screen, written whole into the text layer's records —the
; rows that say what they said keep their tiles—: the page's ranges, and
; the range's rows.
.proc compose
.a8
.i16
    jsl f:tl_clear + FAST
    lda #DBG_WHITE
    sta temp + 1
    lda #0
range:
    cmp f:DBG_RANGES
    bcc range_shown
    jmp list
range_shown:
    pha
    asl a
    clc
    adc #DBG_ROW0
    ldy #1
    jsr at
    lda f:DBG_KIND
    beq switch_kind
    lda #'V'
    bra kind
switch_kind:
    lda #'S'
kind:
    jsr letter
    lda #'['
    jsr letter
    lda 1, s
    jsr range_first
.a16
    jsr four_digits
.a8
    lda #'-'
    jsr letter
    rep #$20
.a16
    lda f:DBG_T0
    clc
    adc #(DBG_ROWS - 1)
    cmp f:DBG_N
    bcc last
    lda f:DBG_N
last:
    jsr four_digits
.a8
    lda #']'
    jsr letter
    pla
    inc a
    cmp #DBG_ROWS
    bcc range

list:
    lda #0
row:
    cmp f:DBG_COUNT
    bcc row_shown
    rts
row_shown:
    pha
    lda #DBG_WHITE
    sta temp + 1
    lda 1, s
    asl a
    clc
    adc #DBG_ROW0
    sta f:DBG_SROW              ; the screen row, for the writes below
    ldy #DBG_NUMBER_COL
    jsr at
    lda 1, s
    rep #$20
.a16
    and #$00FF
    clc
    adc f:DBG_FIRST
    pha
    jsr four_digits
.a8
    lda #':'
    jsr letter
    ; The name: switch k's word, or variable k's first one.
    lda f:DBG_KIND
    rep #$20
.a16
    bne variable_name           ; `rep` leaves Z alone
    lda 1, s
    dec a
    asl a
    clc
    adc #4
    bra name
variable_name:
    lda 1, s
    dec a
    asl a
    asl a
    clc
    adc #DBG_VAR_TABLE
name:
    tax
    lda f:dbg_data, x
    tax
    sep #$20
.a8
    beq no_name
    lda f:DBG_SROW
    ldy #DBG_NAME_COL
    phx
    jsr at
    plx
    jsr string_at
no_name:
    lda f:DBG_KIND
    bne value
    ; A switch: on or off, grey past the table.
    lda f:DBG_SROW
    ldy #DBG_ONOFF_COL
    jsr at
    rep #$20
.a16
    pla
    jsr switch_bit
.a8
    bcs in_table
    lda #DBG_GREY
    sta temp + 1
    bra off
in_table:
    and f:switches, x
    beq off
    lda #'['
    jsr letter
    lda #'O'
    jsr letter
    lda #'N'
    jsr letter
    bra close
off:
    lda #'['
    jsr letter
    lda #'O'
    jsr letter
    lda #'F'
    jsr letter
    lda #'F'
    jsr letter
close:
    lda #']'
    jsr letter
    bra next
value:
    ; A variable: its value, or a grey "-" if the cartridge does not keep
    ; it.
    lda f:DBG_SROW
    ldy #DBG_VALUE_COL
    jsr at
    rep #$20
.a16
    pla
    jsr variable_slot
    bcc not_kept
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    jsr number_right
.a8
    bra next
.a16
not_kept:
    sep #$20
.a8
    lda #DBG_GREY
    sta temp + 1
    lda #('-' - ' ')
    sta f:$7E0000 + TL_DIG
    lda #1
    sta f:$7E0000 + TL_DIG_N
    jsl f:tl_right + FAST
next:
    pla
    inc a
    cmp #DBG_ROWS
    bcs done
    jmp row
done:
    rts
.endproc

; --- the VRAM ---------------------------------------------------------------

; DMA channel 0 from A:X to VRAM word Y, `DBG_LEN` bytes. VMAIN by words.
.proc dma_vram
.a8
.i16
    sta A1B0
    stx A1T0L
    sty VMADDL
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:DBG_LEN
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; DMA channel 0 from A:X to colour memory from entry Y, `DBG_LEN` bytes.
.proc dma_cgram
.a8
.i16
    sta A1B0
    stx A1T0L
    tya
    sta CGADD
    rep #$20
.a16
    lda f:DBG_LEN
    sta DAS0L
    sep #$20
.a8
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; The screen, from nothing, with the screen off: the text layer's blank quad,
; the inks, the windows' tiles and colours, and the registers of mode 5.
; `sk_upload` without the objects, which `TM` does not show.
.proc dbg_upload
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    stz TS
    jsl f:battle_bank_upload + FAST
    ; Quad 0, the blank one every cell without text points to: four tiles.
    rep #$20
.a16
    stz VMADDL
    lda #(2 * TL_PAIR_WORDS * 2)
    sta DAS0L
    lda #.loword(tl_zero)
    sta A1T0L
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #^tl_zero
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda #(ITEMS_CGRAM_N * 2)
    sta f:DBG_LEN
    ldx #.loword(items_cgram)
    sep #$20
.a8
    ldy #DBG_INKS
    lda #^items_cgram
    jsr dma_cgram
    rep #$20
.a16
    lda #(DBG_BORDER_COLORS * 2)
    sta f:DBG_LEN
    ldx #.loword(dbg_border_cgram)
    sep #$20
.a8
    ldy #DBG_CGRAM
    lda #^dbg_border_cgram
    jsr dma_cgram
    rep #$20
.a16
    lda #(DBG_BORDER_TILES * 16)
    sta f:DBG_LEN
    ldx #.loword(dbg_border_tiles)
    sep #$20
.a8
    ldy #CM_BG1_VRAM
    lda #^dbg_border_tiles
    jsr dma_vram
    ; Mode 5: BG1 at 4bpp, the text, and BG2 at 2bpp, the windows, both
    ; with cells 16 pixels wide.
    lda #$05
    sta BGMODE
    lda #(CM_BG1_VRAM / $1000 * 16) ; BG1 from word 0, BG2 from its tiles
    sta BG12NBA
    lda #(SLOT_MAP / 1024 * 4)
    sta BG1SC
    lda #(CM_BG1_MAP / 1024 * 4)
    sta BG2SC
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    sta BG2VOFS
    sta BG2VOFS
    rts
.endproc
.assert CM_BG1_VRAM .mod $1000 = 0, error, "the debug screen's windows are not at a base BG2 can name"

; The windows, the text composed whole and the bars, with the screen off;
; then on.
.proc dbg_view
.a8
.i16
    rep #$20
.a16
    lda #DBG_QUADS
    jsl f:tl_reset + FAST
    sep #$20
.a8
    jsl f:tl_low + FAST
    lda #1
    jsl f:tl_hires
    rep #$20
.a16
    lda #(32 * 28 * 2)
    sta f:DBG_LEN
    ldx #.loword(dbg_layout)
    sep #$20
.a8
    ldy #CM_BG1_MAP
    lda #^dbg_layout
    jsr dma_vram
    lda #$FF
    sta f:DBG_BAR_R
    sta f:DBG_BAR_L
    jsr range_set
    jsr compose
    jsr bars_upload
    jsl f:tl_map + FAST         ; with the screen off right after `tl_reset`,
    jsl f:tl_vblank + FAST      ; `scr_upload` composes the whole text
    jsl f:tl_work + FAST
    lda #$03
    sta TM
    sta TS                      ; both screens: each gives half the pixels
    jsl f:ba_t_vblank
    lda #$0F
    sta INIDISP
    rts
.endproc

; The two bars where the cursors are: the ranges' always, the list's while
; it is the one being walked. Each is taken off where it was and put where
; it goes, only in its window's columns, so the two can share a row. In the
; vblank or with the screen off.
.proc bars_upload
.a8
.i16
    lda #0
    sta f:DBG_W
    lda f:DBG_RANGE
    ldx #DBG_BAR_R - dbg_ram
    jsr one
    lda #1
    sta f:DBG_W
    lda f:DBG_LEVEL
    beq none
    lda f:DBG_ROW
    bra list
none:
    lda #$FF
list:
    ldx #DBG_BAR_L - dbg_ram
one:
    ; A is where the bar goes, and X where it is kept in `dbg_ram`.
    cmp f:dbg_ram, x
    beq ready
    pha
    lda f:dbg_ram, x
    cmp #$FF
    beq paint
    phx
    clc                         ; off
    jsr rows
    plx
paint:
    pla
    sta f:dbg_ram, x
    cmp #$FF
    beq ready
    sec                         ; on
    jmp rows
ready:
    rts
.endproc

; The two cell rows of row A of window `DBG_W`: the bar's with the carry
; set, the windows' own with it clear. Only the window's columns.
.proc rows
.a8
.i16
    sta f:DBG_T0                ; the row
    lda #0
    sta f:DBG_T0 + 1
    rol a
    sta f:DBG_ON
    ; The window's first column, and how many bytes of each cell row.
    lda f:DBG_W
    rep #$20
.a16
    bne list                    ; `rep` leaves Z alone
    lda #0
    sta f:DBG_T1
    lda #(DBG_RANGE_COLS * 2)
    bra columns
list:
    lda #DBG_RANGE_COLS
    sta f:DBG_T1
    lda #((32 - DBG_RANGE_COLS) * 2)
columns:
    sta f:DBG_LEN
    ; The first cell row's word: (DBG_ROW0 + 2 * row) * 32 + column.
    lda f:DBG_T0
    asl a
    clc
    adc #DBG_ROW0
    xba
    lsr a
    lsr a
    lsr a                       ; times 32
    clc
    adc f:DBG_T1
    sta f:DBG_VRAM
    sep #$20
.a8
    lda f:DBG_ON
    rep #$20
.a16
    bne bar
    ; Off: the windows' tilemap, at the same place.
    lda f:DBG_VRAM
    asl a
    clc
    adc #.loword(dbg_layout)
    sta f:DBG_SRC
    sep #$20
.a8
    lda #^dbg_layout
    bra source
.a16
bar:
    ; On: the bar's own rows, window * ten + row, at the same column.
    lda f:DBG_W
    and #$00FF
    beq first_window
    lda #DBG_ROWS
first_window:
    clc
    adc f:DBG_T0
    xba
    lsr a                       ; times 128, a bar's bytes
    sta f:DBG_SRC
    lda f:DBG_T1
    asl a
    clc
    adc f:DBG_SRC
    clc
    adc #.loword(dbg_bars)
    sta f:DBG_SRC
    sep #$20
.a8
    lda #^dbg_bars
source:
    sta f:DBG_SRC_BK
    jsr row
    rep #$20
.a16
    lda f:DBG_VRAM
    clc
    adc #32
    sta f:DBG_VRAM
    lda f:DBG_SRC
    clc
    adc #64
    sta f:DBG_SRC
    sep #$20
.a8
row:
    rep #$20
.a16
    lda f:DBG_VRAM
    clc
    adc #CM_BG1_MAP
    tay
    lda f:DBG_SRC
    tax
    sep #$20
.a8
    lda f:DBG_SRC_BK
    jmp dma_vram
.endproc

.assert DBG_BAR_BYTES = 128, error, "a bar is 128 bytes: see `rows`"
.popseg
.a8
.i16
.endif
