.segment "FAR2"
.a8
.i16

; --- the custom menus -------------------------------------------------------
;
; A screen of the engine that a game declares as data: RM2k does not have
; one, and games built it out of a common event that shows pictures and
; waits for keys —the game this was written for had one of 61 pictures—. The
; game writes what each page says in a file its project names, and
; `rm2k-snes-screens` writes it down for this: see `custom_menu.rs` there,
; which is also where the geometry comes from.
;
; **What is shown**: a list of *subjects* —an actor while it is in the
; party, or an entry that is always there—, each with its portrait, its
; name, and its *tabs*; each tab shows the first of its *pages* whose
; condition holds, and goes in gray with none. A page is text, a table of
; name / value / cap —with sheets that left and right go through—, or
; counters over a text. **How it is walked** is the pause menu's: left and
; right the subject, up and down the tab, A opens the page and B goes back,
; to the same subject.
;
; **Always full screen**, and that is taro's decision, from 2026-10-04: the
; map does not show, and the screen has the whole VRAM. The text goes on BG2
; with the text layer —`text_layer.s`—, from word 0 up to `SCENE_MAP`, 447
; pairs; the System's windows on BG1, 8bpp, with their tiles
; from `CM_BG1_VRAM` and their tilemap at `SCENE_MAP`; the portrait in
; objects from `CM_OBJ_VRAM`. What that overwrites —the sprites, the map's
; tiles and tilemaps, the window— is what a big picture overwrites, and the
; map comes back the same way, `big_back_far`: right after closing when it
; was opened by its common event, and when the pause menu closes when it
; was opened from there. `CM_DIRTY` says which.
;
; It is opened two ways: by the pause menu's option —`cm_from_menu`— and by
; `OP_MENU_OPEN` —`op_menu_open`, in interpreter.s—, which is what the
; common event the menu replaces compiles to. Like the save screen, it
; blocks the page and costs no tick.
;
; It runs with the data bank where the registers are —the pause menu's, or
; the one `op_menu_open` sets—: what it reads of its data and of far RAM goes
; with `f:`.
;
; The data is one block, `cmenu_data`, read with `lda f:cmenu_data, x` and
; offsets of sixteen bits; 0 is the root, and a field that names nothing
; says 0. Its records, as `custom_menu.rs` writes them:
;
;   root     +0 word  the level term, a string
;            +2 byte  how many menus, then each one's offset, a word
;   menu     +0       its condition, five bytes: the option shows if it holds
;            +5 word  the title, a string;  +7 byte how many subjects, then
;                     each one's offset
;   subject  +0       the actor in the party, a condition;  +5 another one
;            +10 byte the actor, $FF none;  +11 byte the portrait, $FF none
;            +12 word the name;  +14 word the class, 0 none
;            +16 byte how many tabs, then six bytes each: the label, the
;                     help's lines (0 none) and the list of pages
;   pages    +0 byte  how many, then each one's offset
;   page     +0       its condition;  +5 byte the shared body to run
;                     before, $FF none;  +6 byte kind (0 text, 1 table,
;                     2 counters);  +7 byte the windows' arrangement
;            +8 word  the header's lines;  +10 word the body's lines
;            +12 byte the body's first row;  +13 byte how many lines fit
;            +14 word the table or the counters
;   lines    +0 byte  how many, then each: row, cell, ink, way (0 its
;                     letters by reference, 1 letter by letter with
;                     `$01 slot*2` for a variable's value), length, bytes
;   string   +0 byte  length, then the letters
;   table    +0 byte  how many sheets;  +1 word the heading's lines
;            +3 byte  how many special values, then five bytes each: the
;                     value, a word; its string, a word; its cell
;            then each sheet's offset
;   sheet    +0 word  the header's lines;  +2 byte how many rows, then seven
;                     bytes each —a row—
;   counters +0 byte  how many, then a row each
;   row      +0 word  the name, a string;  +2 word the variable's slot times
;                     two;  +4 byte the cap's kind (0 a number, 1 a
;                     variable, 2 none);  +5 word the cap
;   a condition: a kind (0 always, 1 switch, 2 variable at least, 3 item
;   held, 4 actor in the party) and two words —the switch's byte and mask,
;   the variable's slot times two and the value, the item, the actor—.

CM_COND_SWITCH   = 1
CM_COND_VARIABLE = 2
CM_COND_ITEM     = 3
CM_PAGE_TEXT     = 0
CM_PAGE_TABLE    = 1
CM_PAGE_COUNTERS = 2
CM_CAP_VARIABLE  = 1
CM_CAP_NONE      = 2
CM_ESCAPE_VARIABLE = 1
CM_ROW_BYTES     = 7

; The VRAM, in words. The text's pairs reach `SCENE_MAP`, as in the battle,
; and the BG1 tilemap goes there; the windows' tiles after BG2's tilemap,
; at a base BG1 can name; the portrait's objects in the last quarter.
CM_BG1_VRAM = $4000
CM_OBJ_VRAM = $6000
CM_BG1_MAP  = SCENE_MAP
; The text's pairs: from word 0 up to BG1's tilemap, a screen with every
; cell inked, like the battle's were until its windows took part of them.
; A guide of eleven full lines asks for some 330.
CM_TEXT_POOL = CM_BG1_MAP / TL_PAIR_WORDS - 1
.assert CM_TEXT_POOL < TL_PAIRS, error, "the custom menus' pairs do not fit in the text layer's tables"
.assert CM_BG1_MAP + $400 <= SLOT_MAP || SLOT_MAP + $400 <= CM_BG1_MAP, error, "the menu's BG1 tilemap steps on the text's"
.assert SLOT_MAP + $400 <= CM_BG1_VRAM, error, "the windows' tiles step on the text's tilemap"
.assert CM_BG1_VRAM + CM_BORDER_TILES * 32 <= CM_OBJ_VRAM, error, "the custom menus' windows do not fit below the portrait"
; The portrait: twelve tiles by fifteen, each tile row of it at the start of
; a row of sixteen of the objects' table, which is what a 32x32 object
; reads; three by four objects, the last row's lower eight lines empty.
CM_PORTRAIT_ROW_BYTES = CM_PORTRAIT_COLS * 32
CM_PORTRAIT_OBJECTS = 12
CM_PORTRAIT_PALETTE = 7         ; colours 240 to 255
; With the screen on, a few tile rows per vblank: they go after the text
; layer's sixteen pairs and the bar, which is some 2 KB, and two rows are
; 768 bytes more.
CM_PORTRAIT_ROWS_PER_VBLANK = 2
.assert CM_PORTRAIT_COLS = 12 && CM_PORTRAIT_ROWS = 15, error, "the portrait's objects are three by four of 32x32"
.assert CM_BORDER_CGRAM + CM_BORDER_COLORS <= 128 + 16 * CM_PORTRAIT_PALETTE, error, "the windows' colours step on the portrait's"
.assert CM_INKS_FIRST + CM_INKS_N <= 8, error, "the custom menus' inks do not fit in BG2's eight palettes"

; The state, in far RAM.
.pushseg
.segment "FARBSS"
CM_RAM: .res 48 + 1 + 8 * 5
.popseg
CM_MENU     = CM_RAM + 0        ; which menu
CM_SUBJ     = CM_RAM + 1        ; which subject, in the menu's list
CM_TAB      = CM_RAM + 2
CM_LEVEL    = CM_RAM + 3        ; 0 the subjects, 1 a page
CM_SHEET    = CM_RAM + 4
CM_SCROLL   = CM_RAM + 5        ; a text page's first visible line
CM_DIRTY    = CM_RAM + 6        ; nonzero: the map has to come back whole
CM_ROWS     = CM_RAM + 7        ; the pause menu's rows
CM_MENU_ROW = CM_RAM + 8        ; the pause menu's row the cursor goes back to
CM_MENU_CMD = CM_RAM + 9        ; and its command
CM_PUP      = CM_RAM + 10       ; the portrait's next tile row to go up, $FF none
CM_PSHOWN   = CM_RAM + 11       ; the portrait in VRAM, $FF none
CM_BAR_ON   = CM_RAM + 12       ; the tab whose bar is on screen, $FF none
CM_BAR_WANT = CM_RAM + 13       ; and the one it should be on
CM_TM       = CM_RAM + 14       ; TM for the next vblank, $FF none
CM_N        = CM_RAM + 15       ; a count, while a list is walked
CM_MREC     = CM_RAM + 16       ; the menu's record, a word
CM_SREC     = CM_RAM + 18       ; the subject's
CM_PAGE     = CM_RAM + 20       ; the page's, 0 none
CM_T0       = CM_RAM + 22       ; scratch words
CM_T1       = CM_RAM + 24
CM_T2       = CM_RAM + 26
CM_T3       = CM_RAM + 28
CM_T4       = CM_RAM + 30
CM_ROW_CMD  = CM_RAM + 32       ; the command of each row of the pause menu
CM_CT       = CM_RAM + 40       ; `cm_cond`'s scratch, a word
CM_CALLS    = CM_RAM + 48       ; the call stack, while a `before` runs
.assert MENU_ROWS_MAX <= 8, error, "the pause menu's rows do not fit in CM_ROW_CMD"
; The depth and the stack, as one block —see common_events.s—: forty-one
; bytes with eight levels, where there were sixteen with three.
CM_CALL_BYTES = CALL_LEVELS * CALL_ENTRY + 1
.assert CM_CALLS + CM_CALL_BYTES = CM_RAM + 48 + 1 + 8 * 5, error, "the custom menus' block is not CM_CALLS plus CM_CALL_BYTES"

; --- the pause menu's column ------------------------------------------------
;
; The custom menus' options go between Equipment and Save, each only while
; its condition holds: `title_sel` is a row, and which command it shows is
; `CM_ROW_CMD`. RPG Maker's five are commands 0 to 4, and menu k is
; command `MENU_OPTIONS + k`.

; The rows, into `CM_ROW_CMD` and `CM_ROWS`. From `menu_upload`.
.proc menu_rows_build
.a8
.i16
    ldy #0                      ; the row
    lda #0
three:
    jsr put
    inc a
    cmp #MENU_SAVE
    bcc three
.if ::CM_MENUS > 0
    lda #0
custom:
    pha
    jsr menu_record
    jsr cm_cond
    pla
    bcc hidden
    pha
    clc
    adc #MENU_OPTIONS
    jsr put
    pla
hidden:
    inc a
    cmp #CM_MENUS
    bcc custom
.endif
    lda #MENU_SAVE
    jsr put
    lda #MENU_END
    jsr put
    tya
    sta f:CM_ROWS
    rtl
put:
    tyx
    sta f:CM_ROW_CMD, x
    iny
    rts
.endproc

; Row A's command, in A, with Z from it. Keeps X and Y.
.proc menu_row_cmd
.a8
.i16
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:CM_ROW_CMD, x
    plx
    cmp #0                      ; the `plx` left its own flags
    rtl
.endproc

; The pause menu's custom option A: the menu, and back. The VRAM it
; overwrote comes back when the pause menu closes —see `menu_screen`—.
.proc cm_from_menu
.a8
.i16
    jsr cm_screen
    lda #1
    sta f:CM_DIRTY
    rtl
.endproc

; `OP_MENU_OPEN`, from the interpreter: menu A, and the map back.
.proc cm_from_page
.a8
.i16
    jsr cm_screen
    lda #0
    sta f:CM_DIRTY
    jsl f:big_back_far + FAST
    rtl
.endproc

; Whether the pause menu has to bring the map back whole, and that it no
; longer has to: A, with Z from it.
.proc cm_dirty_take
.a8
.i16
    lda f:CM_DIRTY
    pha
    lda #0
    sta f:CM_DIRTY
    pla
    cmp #0                      ; the `pla` left its own flags, which are
                                ; these, but the trap is not worth it
    rtl
.endproc

; --- the data ---------------------------------------------------------------

; Menu A's record, in X. Keeps A.
.proc menu_record
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:cmenu_data + 3, x
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; Whether the condition at X holds: carry set if so. Keeps A, X and Y.
.proc cm_cond
.a8
.i16
    pha
    phx
    phy
    lda f:cmenu_data, x
    beq yes
    cmp #CM_COND_SWITCH
    bne not_switch
    lda f:cmenu_data + 3, x     ; the mask
    sta f:CM_CT
    rep #$20
.a16
    lda f:cmenu_data + 1, x     ; the byte
    tax
    sep #$20
.a8
    lda f:switches, x
    and f:CM_CT
    bne yes
    bra no
not_switch:
    cmp #CM_COND_VARIABLE
    bne not_variable
    rep #$20
.a16
    lda f:cmenu_data + 3, x     ; the value
    sta f:CM_CT
    lda f:cmenu_data + 1, x     ; the slot, times two
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sec
    sbc f:CM_CT
    bvc same_sign
    eor #$8000                  ; signed: an overflow flips the sign
same_sign:
    sep #$20
.a8
    bpl yes
    bra no
not_variable:
    cmp #CM_COND_ITEM
    bne in_party
    rep #$20
.a16
    lda f:cmenu_data + 1, x
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    bne yes
    bra no
in_party:
    lda f:cmenu_data + 1, x
    ldx #0
member:
    cpx party_n
    bcs no
    cmp party, x
    beq yes
    inx
    bra member
yes:
    ply
    plx
    pla
    sec
    rts
no:
    ply
    plx
    pla
    clc
    rts
.endproc

; Subject A of the current menu: its record in X and `CM_SREC`. Keeps A.
.proc cm_subject
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc f:CM_MREC
    tax
    lda f:cmenu_data + 8, x
    sta f:CM_SREC
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; Whether subject A is shown: carry set if so. Keeps A; leaves `CM_SREC` on
; it.
.proc cm_shown
.a8
.i16
    jsr cm_subject
    jsr cm_cond
    bcc no
    pha
    rep #$20
.a16
    txa
    clc
    adc #5
    tax
    sep #$20
.a8
    pla
    jmp cm_cond                 ; the `pla` leaves the carry alone
no:
    rts
.endproc

; How many subjects the menu has, in A.
.proc cm_subjects_n
.a8
.i16
    rep #$20
.a16
    lda f:CM_MREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 7, x
    rts
.endproc

; The next shown subject after A going `CM_T1` (1 or $FF), round, in A; A
; itself if none other is.
.proc cm_step
.a8
.i16
    sta f:CM_T2                 ; where it started
    jsr cm_subjects_n
    sta f:CM_N
    lda f:CM_T2
other:
    clc
    adc f:CM_T1
    bpl not_below
    lda f:CM_N
    dec a
not_below:
    cmp f:CM_N
    bcc in_range
    lda #0
in_range:
    cmp f:CM_T2
    beq ready
    jsr cm_shown
    bcc other
ready:
    rts
.endproc

; The first subject shown, in A, or $FF if none is.
.proc cm_first
.a8
.i16
    jsr cm_subjects_n
    sta f:CM_N
    lda #0
other:
    cmp f:CM_N
    bcs none
    jsr cm_shown
    bcs ready
    inc a
    bra other
none:
    lda #$FF
ready:
    rts
.endproc

; Tab A of the subject at `CM_SREC`: its six bytes' offset in X. Keeps A.
.proc cm_tab_at
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    sta f:CM_T4
    asl a
    clc
    adc f:CM_T4
    asl a                       ; times six
    clc
    adc f:CM_SREC
    clc
    adc #17
    tax
    sep #$20
.a8
    pla
    rts
.endproc

; The page tab A shows: the offset of the first of its pages whose condition
; holds, in X, or 0; Z from it.
.proc cm_tab_page
.a8
.i16
    jsr cm_tab_at
    rep #$20
.a16
    lda f:cmenu_data + 4, x     ; the list
    tax
    sep #$20
.a8
    lda f:cmenu_data, x
    sta f:CM_N
    inx
other:
    lda f:CM_N
    beq none
    dec a
    sta f:CM_N
    rep #$20
.a16
    lda f:cmenu_data, x
    sta f:CM_T4
    inx
    inx
    phx
    lda f:CM_T4
    tax
    sep #$20
.a8
    jsr cm_cond
    plx
    bcc other
    rep #$20
.a16
    lda f:CM_T4
    tax
    sep #$20
.a8
    rts
none:
    ldx #0
    rts
.endproc

; --- writing ----------------------------------------------------------------
;
; Through the text layer, like the item screen: every write goes at
; `pick_table` —row * 64 + cell * 2— in colour `temp + 1`, which is also the
; palette. The texts go by reference, which is six bytes of the row's record
; however long they are; a line with a variable goes letter by letter,
; continuing one run.

; `pick_table` to row A, cell Y —only their low bytes count—. Keeps X and
; Y.
.proc cm_at
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

; The string at X, by reference, at `pick_table` in `temp + 1`. Keeps X.
.proc cm_string
.a8
.i16
    lda f:cmenu_data, x
    beq none
    sta temp
    phx
    rep #$20
.a16
    txa
    clc
    adc #.loword(cmenu_data + 1)
    sta msg_ptr
    sep #$20
.a8
    lda #^cmenu_data
    sta msg_ptr + 2
    lda #1
    sta f:$7E0000 + TL_BY_REF
    lda #255
    sta comp_dup + 3
    jsl f:tl_text_at + FAST
    plx
none:
    rts
.endproc

; The string whose offset is the word at X, as `cm_string`; none if the
; word is 0. Keeps X.
.proc cm_string_at
.a8
.i16
    phx
    rep #$20
.a16
    lda f:cmenu_data, x
    beq none
    tax
    sep #$20
.a8
    jsr cm_string
none:
    sep #$20
.a8
    plx
    rts
.endproc

; One letter, A, at `pick_table`. Keeps X.
.proc cm_letter
.a8
.i16
    phx
    jsl f:tl_letter + FAST
    plx
    rts
.endproc

; The lines at X, each on its own row and cell.
.proc cm_lines
.a8
.i16
    lda f:cmenu_data, x
    beq none
    sta f:CM_N
    inx
other:
    lda f:cmenu_data + 1, x     ; the cell
    tay
    lda f:cmenu_data, x         ; the row
    jsr cm_at
    lda f:CM_N
    pha
    jsr cm_line
    pla
    dec a
    sta f:CM_N
    bne other
none:
    rts
.endproc

; The line at X, at `pick_table` —whatever row it says—, in its ink. Leaves
; X on the next one.
.proc cm_line
.a8
.i16
    lda f:cmenu_data + 2, x
    sta temp + 1
    lda f:cmenu_data + 4, x
    sta f:CM_T3                 ; how many bytes
    lda f:cmenu_data + 3, x
    bne escaped
    ; By reference: a string, whose length byte is the line's.
    inx
    inx
    inx
    inx
    jsr cm_string
    jmp cm_skip_string
escaped:
    inx
    inx
    inx
    inx
    inx
letter:
    lda f:CM_T3
    beq done
    lda f:cmenu_data, x
    cmp #CM_ESCAPE_VARIABLE
    beq variable
    jsr cm_letter
    inx
    lda f:CM_T3
    dec a
    sta f:CM_T3
    bra letter
variable:
    phx
    rep #$20
.a16
    lda f:cmenu_data + 1, x
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    jsr cm_digits_inline
.a8
    plx
    inx
    inx
    inx
    lda f:CM_T3
    sec
    sbc #3
    sta f:CM_T3
    bra letter
done:
    rts
.endproc

; X past the string at X.
.proc cm_skip_string
.a8
.i16
    rep #$20
.a16
    lda f:cmenu_data, x
    and #$00FF
    sta f:CM_T4
    txa
    sec                         ; and its length byte
    adc f:CM_T4
    tax
    sep #$20
.a8
    rts
.endproc

; X past the line at X, without writing it.
.proc cm_skip_line
.a8
.i16
    inx
    inx
    inx
    inx
    jmp cm_skip_string
.endproc

; A16, signed, as letters of the font into `TL_DIG`: a minus first if it is
; below zero, and its digits. Returns with A8.
.proc cm_digits
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
    ; The digits from the right, on the stack, and then in order.
    ldy #0
divide:
    sta f:CM_CT
    sep #$20
.a8
    lda f:CM_CT
    sta WRDIVL
    lda f:CM_CT + 1
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
    rts
.endproc

; A16, signed, letter by letter at `pick_table`: a variable in the middle of
; a line, which continues its run. Returns with A8.
.proc cm_digits_inline
.a16
.i16
    jsr cm_digits
.a8
    ldx #0
other:
    txa
    cmp f:$7E0000 + TL_DIG_N
    bcs done
    lda f:$7E0000 + TL_DIG, x
    clc
    adc #' '
    jsr cm_letter
    inx
    bra other
done:
    rts
.endproc

; A16, signed, right-aligned to end with the cell at `pick_table`, in
; `temp + 1`. Returns with A8.
.proc cm_number_right
.a16
.i16
    jsr cm_digits
.a8
    jsl f:tl_right + FAST
    rts
.endproc

; "< i / n >" from the header's `CM_INDEX_COL`: A is i, counted from 1, and
; `CM_N` is n.
.proc cm_index
.a8
.i16
    pha
    lda #CM_HEADER_ROW
    ldy #CM_INDEX_COL
    jsr cm_at
    stz temp + 1
    lda #'<'
    jsr cm_letter
    lda #' '
    jsr cm_letter
    pla
    rep #$20
.a16
    and #$00FF
    jsr cm_digits_inline
.a8
    lda #' '
    jsr cm_letter
    lda #'/'
    jsr cm_letter
    lda #' '
    jsr cm_letter
    rep #$20
.a16
    lda f:CM_N
    and #$00FF
    jsr cm_digits_inline
.a8
    lda #' '
    jsr cm_letter
    lda #'>'
    jmp cm_letter
.endproc

; The row of a table or the counter at X, on screen row A: the name in ink
; `CM_T1`, and the value with its cap. For a table —`CM_T2` its record, 0
; for counters— a value of its special ones is written as its word, and
; the row goes in gray.
.proc cm_row
.a8
.i16
    sta f:CM_T3                 ; the screen row
    rep #$20
.a16
    txa
    sta f:CM_T4                 ; the row's record
    lda f:cmenu_data + 2, x
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta f:CM_T0                 ; its value
    lda f:CM_T2
    beq plain
    tax
    sep #$20
.a8
    lda f:cmenu_data + 3, x     ; how many special values
    beq plain
    sta f:CM_N
    inx
    inx
    inx
    inx                         ; the first one
special:
    rep #$20
.a16
    lda f:cmenu_data, x
    cmp f:CM_T0
    beq is_special
    txa
    clc
    adc #5
    tax
    sep #$20
.a8
    lda f:CM_N
    dec a
    sta f:CM_N
    bne special
    bra plain
.a16
is_special:
    ; The name in gray, and the word ending where the cap would.
    sep #$20
.a8
    lda #CM_GRAY
    sta temp + 1
    lda f:cmenu_data + 4, x     ; its cell
    pha
    phx
    lda f:CM_T3
    ldy #CM_TEXT_COL
    jsr cm_at
    rep #$20
.a16
    lda f:CM_T4
    tax
    sep #$20
.a8
    jsr cm_string_at            ; the name: the row's first word
    plx
    pla
    tay
    lda f:CM_T3
    jsr cm_at
    inx
    inx
    jmp cm_string_at
plain:
    sep #$20
.a8
    lda f:CM_T1
    sta temp + 1
    lda f:CM_T3
    ldy #CM_TEXT_COL
    jsr cm_at
    rep #$20
.a16
    lda f:CM_T4
    tax
    sep #$20
.a8
    jsr cm_string_at
    stz temp + 1
    lda f:cmenu_data + 4, x     ; the cap's kind
    cmp #CM_CAP_NONE
    bne capped
    lda f:CM_T3
    ldy #CM_CAP_COL
    jsr cm_at
    rep #$20
.a16
    lda f:CM_T0
    jmp cm_number_right
.a8
capped:
    lda f:CM_T3
    ldy #CM_VALUE_COL
    jsr cm_at
    rep #$20
.a16
    lda f:CM_T0
    jsr cm_number_right
.a8
    lda f:CM_T3
    ldy #CM_SLASH_COL
    jsr cm_at
    lda #'/'
    jsr cm_letter
    lda f:CM_T3
    ldy #CM_CAP_COL
    jsr cm_at
    rep #$20
.a16
    lda f:CM_T4
    tax
    lda f:cmenu_data + 5, x     ; the cap
    sta f:CM_T0
    sep #$20
.a8
    lda f:cmenu_data + 4, x
    cmp #CM_CAP_VARIABLE
    bne fixed
    rep #$20
.a16
    lda f:CM_T0
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta f:CM_T0
fixed:
    rep #$20
.a16
    lda f:CM_T0
    jmp cm_number_right
.endproc

; The subjects' screen: the title and where in the list, the subject's
; name, class and level, its tabs —gray the ones without a page— and the
; chosen one's help.
.proc cm_compose_subjects
.a8
.i16
    jsl f:tl_clear + FAST
    ; The header.
    lda #CM_HEADER_ROW
    ldy #CM_TEXT_COL
    jsr cm_at
    stz temp + 1
    rep #$20
.a16
    lda f:CM_MREC
    clc
    adc #5
    tax
    sep #$20
.a8
    jsr cm_string_at
    ; Where in the list: how many are shown, and which one this is.
    jsr cm_subjects_n
    sta f:CM_T0 + 1             ; how many there are
    lda #0
    sta f:CM_T0                 ; the one looked at
    sta f:CM_T1                 ; how many are shown
    sta f:CM_T1 + 1             ; and the place of this one
count:
    lda f:CM_T0
    cmp f:CM_T0 + 1
    bcs counted
    jsr cm_shown
    bcc next
    lda f:CM_T1
    inc a
    sta f:CM_T1
    lda f:CM_T0
    cmp f:CM_SUBJ
    bne next
    lda f:CM_T1
    sta f:CM_T1 + 1
next:
    lda f:CM_T0
    inc a
    sta f:CM_T0
    bra count
counted:
    lda f:CM_T1
    sta f:CM_N
    lda f:CM_T1 + 1
    jsr cm_index
    lda f:CM_SUBJ
    jsr cm_subject
    ; The name, the class and the level.
    lda #CM_NAME_ROW
    ldy #CM_INFO_COL
    jsr cm_at
    stz temp + 1
    rep #$20
.a16
    txa
    clc
    adc #12
    tax
    sep #$20
.a8
    jsr cm_string_at
    lda #CM_CLASS_ROW
    ldy #CM_INFO_COL
    jsr cm_at
    inx
    inx
    jsr cm_string_at            ; none if it has none
    rep #$20
.a16
    lda f:CM_SREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 10, x    ; the actor
    cmp #$FF
    beq no_level
    lda #CM_LEVEL_ROW
    ldy #CM_INFO_COL
    jsr cm_at
    lda #CM_RED
    sta temp + 1
    ldx #0
    jsr cm_string_at            ; the root's level term
    lda #CM_LEVEL_ROW
    ldy #CM_LEVEL_NUM_COL
    jsr cm_at
    stz temp + 1
    rep #$20
.a16
    lda f:CM_SREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 10, x
    jsl f:text_level + FAST     ; "%2d" at `msg_ptr`
    ldy #0
digit:
    lda [msg_ptr], y
    cmp #' '
    beq blank
    phy
    jsr cm_letter
    ply
blank:
    iny
    cpy #2
    bcc digit
no_level:
    ; The tabs.
    rep #$20
.a16
    lda f:CM_SREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 16, x
    sta f:CM_T0 + 1             ; how many
    lda #0
    sta f:CM_T0
tab:
    lda f:CM_T0
    cmp f:CM_T0 + 1
    bcs tabs_done
    jsr cm_tab_page
    beq gray
    lda #CM_WHITE
    bra inked
gray:
    lda #CM_GRAY
inked:
    sta temp + 1
    lda f:CM_T0
    asl a
    clc
    adc #CM_TAB_ROW0
    ldy #CM_TAB_COL
    jsr cm_at
    lda f:CM_T0
    jsr cm_tab_at
    jsr cm_string_at            ; the label
    lda f:CM_T0
    inc a
    sta f:CM_T0
    bra tab
tabs_done:
    ; The chosen one's help.
    lda f:CM_TAB
    jsr cm_tab_at
    rep #$20
.a16
    lda f:cmenu_data + 2, x
    beq no_help
    tax
    sep #$20
.a8
    jmp cm_lines
.a16
no_help:
    sep #$20
.a8
    rts
.endproc

; The page `CM_PAGE`: its header and its body, from line `CM_SCROLL` if it
; is text that does not fit.
.proc cm_compose_page
.a8
.i16
    jsl f:tl_clear + FAST
    rep #$20
.a16
    lda f:CM_PAGE
    tax
    sep #$20
.a8
    lda f:cmenu_data + 6, x
    cmp #CM_PAGE_TABLE
    bne not_table
    jmp table
not_table:
    pha
    phx
    rep #$20
.a16
    lda f:cmenu_data + 8, x     ; the header
    tax
    sep #$20
.a8
    jsr cm_lines
    plx
    pla
    cmp #CM_PAGE_COUNTERS
    bne text
    jmp counters
text:
    ; The lines that fit, from `CM_SCROLL`, each on the next row from the
    ; page's first.
    lda f:cmenu_data + 12, x
    sta f:CM_T1                 ; the next row
    lda f:cmenu_data + 13, x
    sta f:CM_T1 + 1             ; how many rows are left
    rep #$20
.a16
    lda f:cmenu_data + 10, x
    tax
    sep #$20
.a8
    lda f:cmenu_data, x
    sta f:CM_T2                 ; how many lines
    inx
    lda #0
skip:
    cmp f:CM_SCROLL
    bcs skipped
    cmp f:CM_T2
    bcs skipped
    pha
    jsr cm_skip_line
    pla
    inc a
    bra skip
skipped:
    sta f:CM_T2 + 1             ; the line X is on
visible:
    lda f:CM_T2 + 1
    cmp f:CM_T2
    bcs done
    lda f:CM_T1 + 1
    beq done
    dec a
    sta f:CM_T1 + 1
    lda f:cmenu_data + 1, x     ; its cell
    tay
    lda f:CM_T1
    jsr cm_at
    jsr cm_line
    lda f:CM_T1
    inc a
    inc a
    sta f:CM_T1
    lda f:CM_T2 + 1
    inc a
    sta f:CM_T2 + 1
    bra visible
done:
    rts

counters:
    rep #$20
.a16
    lda f:cmenu_data + 14, x
    tax
    lda #0
    sta f:CM_T2                 ; no specials
    sep #$20
.a8
    lda f:cmenu_data, x
    sta f:CM_T1 + 1             ; how many
    inx
    lda #CM_BODY_ROW0
    sta f:CM_T3 + 1             ; the screen row: `cm_row` keeps it
crow:
    lda f:CM_T1 + 1
    bne crow_more
    jmp body_lines
crow_more:
    dec a
    sta f:CM_T1 + 1
    lda #CM_RED
    sta f:CM_T1
    lda f:CM_T3 + 1
    phx
    jsr cm_row
.a8
    rep #$20
.a16
    pla
    clc
    adc #CM_ROW_BYTES
    tax
    sep #$20
.a8
    lda f:CM_T3 + 1
    inc a
    inc a
    sta f:CM_T3 + 1
    bra crow

table:
    rep #$20
.a16
    lda f:cmenu_data + 14, x
    sta f:CM_T2                 ; the table, for `cm_row`'s specials
    tax
    sep #$20
.a8
    lda f:cmenu_data, x
    sta f:CM_N                  ; how many sheets
    cmp #2
    bcc one_sheet
    lda f:CM_SHEET
    inc a
    jsr cm_index
one_sheet:
    ; The heading.
    rep #$20
.a16
    lda f:CM_T2
    tax
    lda f:cmenu_data + 1, x
    tax
    sep #$20
.a8
    jsr cm_lines
    ; The sheet: its offset is past the specials, five bytes each.
    rep #$20
.a16
    lda f:CM_T2
    tax
    lda f:cmenu_data + 3, x
    and #$00FF
    sta f:CM_T4
    asl a
    asl a
    clc
    adc f:CM_T4
    clc
    adc f:CM_T2
    clc
    adc #4
    sta f:CM_T4
    lda f:CM_SHEET
    and #$00FF
    asl a
    clc
    adc f:CM_T4
    tax
    lda f:cmenu_data, x
    sta f:CM_T0                 ; the sheet: `cm_lines` leaves CM_T0 alone
    tax
    lda f:cmenu_data, x         ; its header's lines
    tax
    sep #$20
.a8
    jsr cm_lines
    ; Its rows.
    rep #$20
.a16
    lda f:CM_T0
    tax
    sep #$20
.a8
    lda f:cmenu_data + 2, x
    sta f:CM_T1 + 1             ; how many
    inx
    inx
    inx
    lda #CM_TABLE_ROW0
    sta f:CM_T3 + 1             ; the screen row: `cm_row` keeps it
trow:
    lda f:CM_T1 + 1
    beq body_lines
    dec a
    sta f:CM_T1 + 1
    lda #CM_WHITE
    sta f:CM_T1
    lda f:CM_T3 + 1
    phx
    jsr cm_row
.a8
    rep #$20
.a16
    pla
    clc
    adc #CM_ROW_BYTES
    tax
    sep #$20
.a8
    lda f:CM_T3 + 1
    inc a
    inc a
    sta f:CM_T3 + 1
    bra trow

body_lines:
    ; The text under a table or the counters, on its own rows.
    rep #$20
.a16
    lda f:CM_PAGE
    tax
    lda f:cmenu_data + 10, x
    tax
    sep #$20
.a8
    jmp cm_lines
.endproc

; --- the VRAM ---------------------------------------------------------------

; DMA channel 0 from A:X to VRAM word Y, `CM_T0` bytes. VMAIN by words.
.proc cm_dma_vram
.a8
.i16
    sta A1B0
    stx A1T0L
    sty VMADDL
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:CM_T0
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

; DMA channel 0 from A:X to colour memory from entry Y, `CM_T0` bytes.
.proc cm_dma_cgram
.a8
.i16
    sta A1B0
    stx A1T0L
    tya
    sta CGADD
    rep #$20
.a16
    lda f:CM_T0
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

; Arrangement A's windows: the whole BG1 tilemap. The bar goes with it.
.proc cm_layout_upload
.a8
.i16
    rep #$20
.a16
    and #$00FF
    pha
    asl a
    tax
    lda f:cm_layout_lo, x
    sta f:CM_T1
    lda #(32 * 28 * 2)
    sta f:CM_T0
    plx
    sep #$20
.a8
    lda f:cm_layout_bk, x
    pha
    rep #$20
.a16
    lda f:CM_T1
    tax
    sep #$20
.a8
    pla
    ldy #CM_BG1_MAP
    jsr cm_dma_vram
    lda #$FF
    sta f:CM_BAR_ON
    rts
.endproc

; The bar under tab `CM_BAR_WANT`, and off tab `CM_BAR_ON`: two cell rows
; of BG1's tilemap each, from the subjects' arrangement with the bar —
; `cm_bars`— or without it.
.proc cm_bar_upload
.a8
.i16
    lda f:CM_BAR_ON
    cmp f:CM_BAR_WANT
    beq ready
    cmp #$FF
    beq paint
    ; Off: the arrangement's own rows.
    asl a
    clc
    adc #CM_TAB_ROW0
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    lsr a
    sta f:CM_T1                 ; its first byte in the tilemap
    clc
    adc f:cm_layout_lo + 2 * CM_LAYOUT_SUBJECTS
    tax
    lda #128
    sta f:CM_T0
    lda f:CM_T1
    lsr a                       ; in words
    clc
    adc #CM_BG1_MAP
    tay
    sep #$20
.a8
    lda f:cm_layout_bk + CM_LAYOUT_SUBJECTS
    jsr cm_dma_vram
paint:
    lda f:CM_BAR_WANT
    sta f:CM_BAR_ON
    cmp #$FF
    beq ready
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; 128 bytes a bar
    clc
    adc #.loword(cm_bars)
    tax
    lda #128
    sta f:CM_T0
    lda f:CM_BAR_WANT
    asl a
    clc
    adc #CM_TAB_ROW0
    and #$00FF
    xba
    lsr a
    lsr a
    lsr a                       ; times 32: its first word in the tilemap
    clc
    adc #CM_BG1_MAP
    tay
    sep #$20
.a8
    lda #^cm_bars
    jsr cm_dma_vram
ready:
    rts
.endproc

; The portrait of the subject at `CM_SREC`, into `LZ2_BUFFER` if it is not
; the one in VRAM, and `CM_PUP` at 0 so its rows go up, with the objects off
; meanwhile; or the objects off if it has none.
.proc cm_portrait_want
.a8
.i16
    rep #$20
.a16
    lda f:CM_SREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 11, x
    cmp #$FF
    beq none
    cmp f:CM_PSHOWN
    beq shown
    sta f:CM_PSHOWN
    lda #^LZ2_BUFFER
    sta f:LZ2_BANK
    lda f:CM_PSHOWN
    rep #$20
.a16
    and #$00FF
    pha
    asl a
    tax
    lda f:cm_portrait_lo, x
    sta f:CM_T1
    plx
    sep #$20
.a8
    lda f:cm_portrait_bk, x
    pha
    rep #$20
.a16
    lda f:CM_T1
    tax
    ldy #.loword(LZ2_BUFFER)
    sep #$20
.a8
    pla
    jsl f:lz2_decompress + FAST
    lda #0
    sta f:CM_PUP
    lda #$03                    ; off until its rows are up
    sta f:CM_TM
    rts
shown:
    lda #$13
    sta f:CM_TM
    rts
none:
    lda #$FF
    sta f:CM_PSHOWN
    sta f:CM_PUP
    lda #$03
    sta f:CM_TM
    rts
.endproc

; Up to A of the portrait's rows that are still to go up, and after the
; last its palette and the objects on.
.proc cm_portrait_rows
.a8
.i16
    sta f:CM_N
other:
    lda f:CM_PUP
    cmp #CM_PORTRAIT_ROWS
    bcs last
    lda f:CM_N
    beq ready
    dec a
    sta f:CM_N
    lda f:CM_PUP
    rep #$20
.a16
    and #$00FF
    sta f:CM_T1
    xba                         ; a row of the objects' table: 256 words
    clc
    adc #CM_OBJ_VRAM
    tay
    lda f:CM_T1
    asl a
    clc
    adc f:CM_T1                 ; times three
    xba
    lsr a                       ; times 128: 384 bytes a row of the portrait
    clc
    adc #.loword(LZ2_BUFFER)
    tax
    lda #CM_PORTRAIT_ROW_BYTES
    sta f:CM_T0
    sep #$20
.a8
    lda #^LZ2_BUFFER
    jsr cm_dma_vram
    lda f:CM_PUP
    inc a
    sta f:CM_PUP
    bra other
last:
    cmp #$FF
    beq ready
    ; The palette, and done.
    lda f:CM_PSHOWN
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes each
    clc
    adc #.loword(cm_portrait_cgram)
    tax
    lda #32
    sta f:CM_T0
    sep #$20
.a8
    ldy #(128 + 16 * CM_PORTRAIT_PALETTE)
    lda #^cm_portrait_cgram
    jsr cm_dma_cgram
    lda #$FF
    sta f:CM_PUP
    lda #$13
    sta f:CM_TM
ready:
    rts
.endproc

; In the vblank, before the text's: what changed of the bar and the
; portrait, and TM.
.proc cm_vblank
.a8
.i16
    lda f:CM_LEVEL
    bne page
    jsr cm_bar_upload
    lda #CM_PORTRAIT_ROWS_PER_VBLANK
    jsr cm_portrait_rows
page:
    lda f:CM_TM
    cmp #$FF
    beq ready
    sta TM
    lda #$FF
    sta f:CM_TM
ready:
    rts
.endproc

; The objects: the portrait's twelve, and every other one out of the
; screen. Through the port, with the screen off.
cm_oam_table:
.repeat 4, R
.repeat 3, C
    .byte CM_PORTRAIT_X + 32 * C, CM_PORTRAIT_Y - 1 + 32 * R, R * 64 + C * 4
    .byte $30 | CM_PORTRAIT_PALETTE << 1 ; priority 3: an object shows one line below its y
.endrepeat
.endrepeat
.proc cm_oam
.a8
.i16
    stz OAMADDL
    stz OAMADDL + 1
    ldx #0
portrait:
    lda f:cm_oam_table, x
    sta OAMDATA
    inx
    cpx #(4 * CM_PORTRAIT_OBJECTS)
    bcc portrait
    ldx #(128 - CM_PORTRAIT_OBJECTS)
hidden:
    stz OAMDATA
    lda #224
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne hidden
    ; The high table: x below 256, and the small size, which is 32x32.
    ldx #32
high:
    stz OAMDATA
    dex
    bne high
    rts
.endproc

; The screen, from nothing, with the screen off: the text layer with the
; battle's pairs, the inks, the windows' tiles and colours, the objects'
; table empty and the portrait's objects, and the registers.
.proc cm_screen_upload
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:battle_bank_upload + FAST
    ; The text screens' other two inks, and the menu's.
    rep #$20
.a16
    lda #(2 * 16 * 2)
    sta f:CM_T0
    ldx #.loword(item_cgram_uploads)
    sep #$20
.a8
    ldy #ITEMS_CGRAM_N
    lda #^item_cgram_uploads
    jsr cm_dma_cgram
.if ::CM_INKS_N > 0
    rep #$20
.a16
    lda #(CM_INKS_N * 32)
    sta f:CM_T0
    ldx #.loword(cm_inks_cgram)
    sep #$20
.a8
    ldy #(16 * CM_INKS_FIRST)
    lda #^cm_inks_cgram
    jsr cm_dma_cgram
.endif
    rep #$20
.a16
    lda #(CM_BORDER_COLORS * 2)
    sta f:CM_T0
    ldx #.loword(cm_border_cgram)
    sep #$20
.a8
    ldy #CM_BORDER_CGRAM
    lda #^cm_border_cgram
    jsr cm_dma_cgram
    rep #$20
.a16
    lda #(CM_BORDER_TILES * 64)
    sta f:CM_T0
    ldx #.loword(cm_border_tiles)
    sep #$20
.a8
    ldy #CM_BG1_VRAM
    lda #^cm_border_tiles
    jsr cm_dma_vram
    ; The objects' first table, empty: the portrait's last row of objects
    ; reaches a tile row it does not draw.
    rep #$20
.a16
    lda #CM_OBJ_VRAM
    sta VMADDL
    lda #($1000 * 2)
    sta DAS0L
    lda #.loword(tl_zero)
    sta A1T0L
    sep #$20
.a8
    lda #^tl_zero
    sta A1B0
    lda #$09                    ; two registers, without advancing the source
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    jsr cm_oam
    lda #($A0 | CM_OBJ_VRAM / $2000) ; 32x32 and 64x64, from CM_OBJ_VRAM
    sta OBSEL
    lda #(CM_BG1_VRAM / $1000)  ; BG2 from word 0, BG1 from its tiles
    sta BG12NBA
    lda #(CM_BG1_MAP / 1024 * 4)
    sta BG1SC
    lda #(SLOT_MAP / 1024 * 4)
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
    sta f:CM_PSHOWN
    sta f:CM_PUP
    sta f:CM_BAR_ON
    sta f:CM_TM
    rts
.endproc

; What the current level shows, with the screen off and the text layer
; from scratch: its windows, its text composed whole, and on the subjects'
; the bar and the portrait. Then the screen on.
.proc cm_view
.a8
.i16
    lda #$80
    sta INIDISP
    stz TM
    rep #$20
.a16
    lda #CM_TEXT_POOL
    jsl f:tl_reset + FAST
    sep #$20
.a8
    jsl f:tl_low + FAST
    lda f:CM_LEVEL
    bne page
    lda #CM_LAYOUT_SUBJECTS
    jsr cm_layout_upload
    jsr cm_compose_subjects
    lda f:CM_TAB
    sta f:CM_BAR_WANT
    jsr cm_bar_upload
    jsr cm_portrait_want
    lda #CM_PORTRAIT_ROWS
    jsr cm_portrait_rows
    bra on
page:
    rep #$20
.a16
    lda f:CM_PAGE
    tax
    sep #$20
.a8
    lda f:cmenu_data + 7, x
    jsr cm_layout_upload
    jsr cm_compose_page
    lda #$03
    sta f:CM_TM
on:
    ; `scr_upload`, which with the screen off right after `tl_reset`
    ; composes the whole text and uploads it.
    jsl f:tl_map + FAST
    jsl f:tl_vblank + FAST
    jsl f:tl_work + FAST
    lda f:CM_TM
    sta TM
    lda #$FF
    sta f:CM_TM
    jsl f:ba_t_vblank
    lda #$0F
    sta INIDISP
    rts
.endproc

; The shared body the page runs before, if it has one: to its end, now. The
; interpreter that was running —the page that opened the menu, if one did—
; is kept on the stack and in `CM_CALLS`, and comes back as it was. The
; compiler made sure the body only does what does not wait: see
; `before_commands` in `rm2k-snes-events`.
.proc cm_before
.a8
.i16
    rep #$20
.a16
    lda f:CM_PAGE
    tax
    sep #$20
.a8
    lda f:cmenu_data + 5, x
    cmp #$FF
    bne has
    rts
has:
    sta f:CM_T4                 ; the body
    ldx #0
save:
    lda f:call_depth, x
    sta f:CM_CALLS, x
    inx
    cpx #CM_CALL_BYTES
    bcc save
    rep #$20
.a16
    lda ev_cur
    pha
    lda ev_waiting
    pha
    lda f:ev_running
    pha
    lda code_ptr
    pha
    sep #$20
.a8
    lda code_ptr + 2
    pha
    lda ev_active
    pha
    lda pair_ev
    pha
    lda f:CM_T4
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:common_body_lo, x
    sta code_ptr
    stz ev_cur
    lda #$FFFF
    sta f:ev_running
    sep #$20
.a8
    lda f:common_body_bank, x
    sta code_ptr + 2
    lda #0
    sta f:call_depth
    lda #1
    sta ev_active
    lda #$FF
    sta pair_ev                 ; neither a map's parallel event nor a
                                ; battle page
    ; To its end: a body that only does what does not wait ends in one
    ; pass, and the cap is for one that would loop.
    ldy #64
again:
    phy
    jsl f:run_code_long + FAST
    ply
    lda ev_active
    beq ended
    dey
    bne again
ended:
    pla
    sta pair_ev
    pla
    sta ev_active
    pla
    sta code_ptr + 2
    rep #$20
.a16
    pla
    sta code_ptr
    pla
    sta f:ev_running
    pla
    sta ev_waiting
    pla
    sta ev_cur
    sep #$20
.a8
    ldx #0
restore:
    lda f:CM_CALLS, x
    sta f:call_depth, x
    inx
    cpx #CM_CALL_BYTES
    bcc restore
    rts
.endproc

; What of the objects `big_back_far` does not put back, with the screen off:
; OBSEL, which is the map's, and the object palettes, which the windows'
; colours and the portrait's took —from `cgram_shadow`, as the pause menu's
; `menu_exp_close` does with the four it takes—.
.proc cm_objects_back
.a8
.i16
    lda #$80
    sta INIDISP
    ldx map_ofs
    lda f:map_table + M_OBSEL_VALUE, x
    sta OBSEL
    rep #$20
.a16
    lda #(128 * 2)
    sta f:CM_T0
    ldx #.loword(cgram_shadow + 2 * 128)
    sep #$20
.a8
    ldy #128
    lda #^cgram_shadow
    jmp cm_dma_cgram
.endproc

; Menu A, until the player leaves it with B from the subjects.
.proc cm_screen
.a8
.i16
    sta f:CM_MENU
    jsr menu_record
    rep #$20
.a16
    txa
    sta f:CM_MREC
    sep #$20
.a8
    jsr cm_first
    cmp #$FF
    bne has
    rts                         ; nobody to show
has:
    sta f:CM_SUBJ
    lda #0
    sta f:CM_TAB
    sta f:CM_LEVEL
    lda #1
    sta menu_open
    jsr cm_screen_upload
    jsr cm_view
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    jsr cm_vblank
    jsl f:tl_map + FAST         ; `scr_upload`
    jsl f:tl_vblank + FAST
    jsl f:tl_work + FAST
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    lda f:CM_LEVEL
    beq subjects
    jmp in_page

subjects:
    lda title_edges
    and #(PAD_LEFT | PAD_RIGHT)
    beq no_side
    and #PAD_RIGHT
    beq left
    lda #1
    bra step
left:
    lda #$FF
step:
    sta f:CM_T1
    lda f:CM_SUBJ
    jsr cm_step
    cmp f:CM_SUBJ
    beq wait
    sta f:CM_SUBJ
    jsr cm_subject
    ; The same tab, if this one has as many.
    lda f:cmenu_data + 16, x
    dec a
    cmp f:CM_TAB
    bcs tab_kept
    sta f:CM_TAB
    sta f:CM_BAR_WANT
tab_kept:
    jsr cm_compose_subjects
    jsr cm_portrait_want
    jmp wait
no_side:
    lda title_edges
    and #(PAD_UP | PAD_DOWN)
    beq no_tab
    rep #$20
.a16
    lda f:CM_SREC
    tax
    sep #$20
.a8
    lda f:cmenu_data + 16, x
    sta f:CM_N                  ; how many tabs
    lda title_edges
    and #PAD_DOWN
    beq up
    lda f:CM_TAB
    inc a
    cmp f:CM_N
    bcc moved
    lda #0
    bra moved
up:
    lda f:CM_TAB
    bne above
    lda f:CM_N
above:
    dec a
moved:
    sta f:CM_TAB
    sta f:CM_BAR_WANT
    jsr cm_compose_subjects
    jmp wait
no_tab:
    lda title_edges
    and #PAD_B
    beq no_b
    ; Out: the B that closes is consumed, and the A from before, as the
    ; pause menu does.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    jmp cm_objects_back
no_b:
    lda pad_a
    beq to_wait
    lda pad_a_prev
    bne to_wait                 ; it was already held: not an edge
    lda f:CM_TAB
    jsr cm_tab_page
    beq to_wait                 ; in gray: nothing to open
    rep #$20
.a16
    txa
    sta f:CM_PAGE
    sep #$20
.a8
    jsr cm_before
    lda #0
    sta f:CM_SHEET
    sta f:CM_SCROLL
    lda #1
    sta f:CM_LEVEL
    jsr cm_view
to_wait:
    jmp wait

in_page:
    lda title_edges
    and #PAD_B
    beq page_no_b
    ; Back to the subjects, on the same one and the same tab.
    lda #0
    sta f:CM_LEVEL
    jsr cm_view
    jmp wait
page_no_b:
    rep #$20
.a16
    lda f:CM_PAGE
    tax
    sep #$20
.a8
    lda f:cmenu_data + 6, x
    cmp #CM_PAGE_TABLE
    bne not_table
    ; The sheets, round.
    lda title_edges
    and #(PAD_LEFT | PAD_RIGHT)
    beq to_wait
    rep #$20
.a16
    lda f:cmenu_data + 14, x
    tax
    sep #$20
.a8
    lda f:cmenu_data, x
    sta f:CM_N
    cmp #2
    bcc to_wait
    lda title_edges
    and #PAD_RIGHT
    beq sheet_left
    lda f:CM_SHEET
    inc a
    cmp f:CM_N
    bcc sheet_moved
    lda #0
    bra sheet_moved
sheet_left:
    lda f:CM_SHEET
    bne sheet_above
    lda f:CM_N
sheet_above:
    dec a
sheet_moved:
    sta f:CM_SHEET
    jsr cm_compose_page
    jmp wait
not_table:
    cmp #CM_PAGE_TEXT
    bne page_wait
    ; A text longer than its window: up and down, a line.
    lda title_edges
    and #(PAD_UP | PAD_DOWN)
    beq page_wait
    lda f:cmenu_data + 13, x
    sta f:CM_T0                 ; how many fit
    rep #$20
.a16
    lda f:cmenu_data + 10, x
    tax
    sep #$20
.a8
    lda f:cmenu_data, x         ; how many lines
    sec
    sbc f:CM_T0
    bcc page_wait
    beq page_wait
    sta f:CM_N                  ; the last first line
    lda title_edges
    and #PAD_DOWN
    beq scroll_up
    lda f:CM_SCROLL
    cmp f:CM_N
    bcs page_wait
    inc a
    bra scrolled
scroll_up:
    lda f:CM_SCROLL
    beq page_wait
    dec a
scrolled:
    sta f:CM_SCROLL
    jsr cm_compose_page
page_wait:
    jmp wait
.endproc
