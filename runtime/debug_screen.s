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
; pages come the variables', and after them one that is not RPG_RT's: the
; switches of the state the game keeps across maps —the tint, the timer and
; the weather—, see debug_switches.s; A goes into the list, on its first row, and B
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
; its wide mode —`tl_hires`: a font's pixels are the screen's, and since
; 2026-11-01 the font is the screen's own, `hires-wide`, which taro reads
; on a CRT—; its quads from word 0 for the screen's upper half and from
; `TL_HI_LOWER` for the lower half, each half its own 1024 tiles, which an
; HDMA switches at line 112 —`dbg_hdma`—; the windows on BG2 at 2bpp, each
; tilemap word a cell 16 pixels wide, with their tiles from
; `DBG_TILES_VRAM` and their colours in the first 32 entries; and no objects
; —`TM` and `TS` show BG1 and BG2 only, both, which is what shows every
; pixel of the 512—. The text's inks go after the windows' colours, in
; palettes 2 and 3: `DBG_WHITE` and `DBG_GREY`. When B leaves, mode 3 and
; no subscreen again, which is what the pause menu draws in. The map comes
; back as from a custom menu: `CM_DIRTY`, and `big_back_far` when the pause
; menu closes.
;
; The geometry and the data are `rm2k-snes-screens`'s `debug_screen.rs`,
; which says how a page of names is laid out —`pages`—, and the data
; travels only in the `.msu`: see "What comes from the `.msu`" below. It
; lives in `FAR3`, entered with `jsl` from `cm_from_menu` with the pause
; menu's data bank, 0.

.if ::DEBUG_SCREEN
.pushseg
.segment "FAR3"
.a8
.i16

.assert DBG_BORDER_TILES > 0 && DBG_BORDER_COLORS > 0, error, "the debug screen has no windows: a DMA of 0 bytes is 64 KB"
; The VRAM, in words: the text's quads from 0 —the upper half's, 1024
; tiles— and from `TL_HI_LOWER` —the lower half's— up to the windows'
; tiles, and the two tilemaps at the top. Nothing of the map's is kept: it
; comes back whole when the pause menu closes.
DBG_TILES_VRAM = $7000          ; the windows' tiles, BG2's
DBG_WIN_MAP    = $7800          ; the windows' tilemap, BG2's
.assert TL_HI_LOWER + 64 * (TL_HI_LAST_Q + 1 - TL_HI_LOWER_Q) <= DBG_TILES_VRAM, error, "the lower half's quads reach the windows' tiles"
.assert DBG_TILES_VRAM + DBG_BORDER_TILES * 8 <= DBG_WIN_MAP, error, "the debug screen's windows do not fit under their tilemap: see DBG_TILES_MAX in rm2k-snes-screens"
.assert DBG_WIN_MAP + $400 <= TL_HI_MAP && TL_HI_MAP + $400 <= $8000, error, "the debug screen's tilemaps overlap"
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
; The upper half's quads: from word 0, four tiles each, as many as a
; tilemap word names; the lower half's are `tl_hires`'s.
DBG_QUADS    = TL_HI_LOWER_Q - 1
.assert 4 * DBG_QUADS + 3 < 1024, error, "the debug screen's quads do not fit BG1's tiles"
.assert (TL_HI_SPLIT - DBG_ROW0) .mod 2 = 0 && TL_HI_SPLIT > DBG_ROW0 && TL_HI_SPLIT < DBG_ROW0 + 2 * DBG_ROWS, error, "the text layer's pools do not split the screen between two of its lines"
; BG1's tiles from word 0 in the upper half and from `TL_HI_LOWER` in the
; lower one, and BG2's from its own all the way: what `dbg_hdma` writes.
DBG_NBA_UPPER = DBG_TILES_VRAM / $1000 * 16
DBG_NBA_LOWER = DBG_NBA_UPPER | (TL_HI_LOWER / $1000)
.assert DBG_TILES_VRAM .mod $1000 = 0 && TL_HI_LOWER .mod $1000 = 0, error, "the debug screen's tiles are not at bases BG12NBA can name"
; The HDMA's channel, 7: see registers.s.
DBG_HDMA     = $80
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
DBG_KIND     = dbg_ram + 6      ; what the page is: see below
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
; What a page is, `DBG_KIND`: the game's switches, its variables, or the
; switches of the state the game keeps across maps —the last page, after the
; variables': see debug_switches.s—.
DBG_KIND_SWITCHES  = 0
DBG_KIND_VARIABLES = 1
DBG_KIND_OFF     = 2
DBG_ALL_PAGES = DBG_PAGES + 1

; --- what comes from the `.msu` -------------------------------------------------
;
; **The screen's bulk travels only in the `.msu`**, since 2026-11-16: its
; font, its names and its windows are `.msu_only` pieces, which the packing
; sends to the `.msu`'s region in any cartridge —see `msu_only_block` in
; rm2k-snes-mapdata and `pack_with_msu` in rm2k-snes-cartridge—, and their
; labels here are bank `MSU_SPILL_BANK` and their unit. It is taro's: they
; test with the `.msu`, and the screen is not needed to enjoy the game. So
; **without the MSU-1, or with another build's `.msu`, the pause menu does
; not offer it**: `dbg_available`, each time the menu is drawn.
;
; While it is open it lives in `LZ2_BUFFER`, after the wide stage and up to
; `ANIM_DRAWINGS_END`: `back_to_map` rebuilds all of that when the pause
; menu closes, and the menu never opens over a big picture —see
; `request_menu`—. `.define`s and not symbols, like `TL_STAGE_HI`: it is
; the load buffer, not a new tenant of the WRAM's upper half.
;
;   DBG_VARS        what the screen keeps while it is open and nobody else:
;                   far RAM has no room left in A Blurred Line
;   DBG_FRAME_RAM   the windows' tilemap and the bars, `dbg_frame`, loaded
;                   when it opens: what `dbg_view` and `rows` upload
;   DBG_PAGE_RAM0   the names of a page, `dbg_pageN`, loaded when the page
;   DBG_PAGE_RAM1   changes, each into the buffer the screen does not show:
;                   the text layer keeps a name written by reference as its
;                   address, so the page on screen must not change under it
;                   —and a flip waits for the text to be shown, `DBG_FLIP`—
;   DBG_CINDEX      the font's cache, `dbg_glyph`: a word per letter and
;   DBG_COWNER      phase, its slot's address or 0; a word per slot, the
;   DBG_CSLOTS      entry it holds or $FFFF; and the slots, a letter's
;                   phase each, `FONT_PRE_CHAR` bytes, taken in turn
;
; The windows' tiles and colours, `dbg_border`, pass through the slots
; before the cache starts. Each `.define` starts with a unary `+`: with its
; body in parentheses right after the name, `ca65` takes them for a macro's
; parameters.
.define DBG_VARS +(TL_STAGE_HI + TL_STAGE_HI_BYTES)
.define DBG_PAGE_AT +(DBG_VARS + 0)  ; the loaded page's names, a word of bank $7F
.define DBG_FLIP +(DBG_VARS + 2)     ; a page flip waiting for the text: 0
                                     ; none, PAD_LEFT or PAD_RIGHT
.define DBG_RD_LEN +(DBG_VARS + 4)   ; `dbg_read`: how many bytes
.define DBG_KEY +(DBG_VARS + 6)      ; `dbg_glyph`: the letter's entry in the
                                     ; index,
.define DBG_CSLOT +(DBG_VARS + 8)    ; the cache's next slot, times two,
.define DBG_CADDR +(DBG_VARS + 10)   ; and its address in bank $7F,
.define DBG_GOFS +(DBG_VARS + 12)    ; and the letter's offset in its phase's
                                     ; piece
DBG_VARS_BYTES = 14
.define DBG_FRAME_RAM +(DBG_VARS + DBG_VARS_BYTES)
.define DBG_PAGE_RAM0 +(DBG_FRAME_RAM + DBG_FRAME_BYTES)
.define DBG_PAGE_RAM1 +(DBG_PAGE_RAM0 + DBG_PAGE_MAX)
.define DBG_CINDEX +(DBG_PAGE_RAM1 + DBG_PAGE_MAX)
.define DBG_COWNER +(DBG_CINDEX + 16 * DBG_GLYPHS)
.define DBG_SLOTS +((ANIM_DRAWINGS_END - DBG_COWNER) / (FONT_PRE_CHAR + 2))
.define DBG_CSLOTS +(DBG_COWNER + 2 * DBG_SLOTS)
.assert DBG_CSLOTS + DBG_SLOTS * FONT_PRE_CHAR <= ANIM_DRAWINGS_END, error, "the debug screen's cache goes past LZ2_BUFFER"
.assert DBG_SLOTS >= 32, error, "the debug screen's font cache has fewer than 32 letters"
.assert DBG_CSLOTS + DBG_BORDER_TILES * 16 + DBG_BORDER_COLORS * 2 <= ANIM_DRAWINGS_END, error, "the debug screen's windows do not fit where its cache goes"
.assert ^DBG_FRAME_RAM = $7F && ^ANIM_DRAWINGS_END = $7F, error, "the debug screen's WRAM is not bank $7F: see dbg_read"
.assert DBG_PAGE_MAX > 0 && DBG_FRAME_BYTES > 0, error, "a DMA of 0 bytes is 64 KB"
.assert FONT_PRE_CHAR .mod 2 = 0, error, "dbg_glyph blanks a letter a word at a time"
; And for the tests, which compare the cache with the `.msu`: where it is,
; as sixteen-bit numbers of bank $7F.
DBG_VARS_AT   = .loword(DBG_VARS)
DBG_CINDEX_AT = .loword(DBG_CINDEX)
DBG_CSLOTS_AT = .loword(DBG_CSLOTS)
DBG_SLOTS_N   = DBG_SLOTS

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
    sta f:DBG_FLIP
    lda f:JOY1L
    sta f:DBG_LR
    jsr frame_load
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
    sta f:DBG_FLIP              ; a flip that waited is forgotten
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
    bne flip
    lda f:DBG_FLIP              ; one that waited for the text
    beq to_wait
flip:
    ; The page's names go into the buffer the screen does not show, and
    ; until the screen shows what it was given, the other one may still be
    ; on it: the flip waits —see `DBG_PAGE_RAM1`—.
    sta f:DBG_FLIP
    jsr shown
    bcc to_wait
    lda f:DBG_FLIP
    pha
    lda #0
    sta f:DBG_FLIP
    pla
    and #PAD_RIGHT
    beq page_left
    lda f:DBG_PAGE
    inc a
    cmp #DBG_ALL_PAGES
    bcc page_moved
    lda #0
    bra page_moved
page_left:
    lda f:DBG_PAGE
    bne page_above
    lda #DBG_ALL_PAGES
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
    cmp #DBG_KIND_VARIABLES
    beq variable
    ; A switch, the game's or the state's: A turns it on or off.
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
    stz HDMAEN                  ; BG12NBA is the pause menu's again
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
    cmp #DBG_ALL_PAGES
    bcc in_range
    lda #0                      ; the garbage of a first opening
    sta f:DBG_PAGE
in_range:
    cmp #DBG_PAGES
    bne the_game_s
    ; The last one, the state's: a range of `DBG_OFF_ROWS`, from 1, and no
    ; names to load —they are in the ROM—.
    lda #DBG_KIND_OFF
    sta f:DBG_KIND
    lda #1
    sta f:DBG_RANGES
    lda #0
    sta f:DBG_RANGE
    rep #$20
.a16
    lda #0
    sta f:DBG_BASE
    lda #DBG_OFF_ROWS
    sta f:DBG_N
    sep #$20
.a8
    rts
the_game_s:
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
    jmp page_load
.endproc

; The page's names, `dbg_pageN`, from the `.msu` into the buffer the screen
; does not show, which becomes `DBG_PAGE_AT`. If the `.msu` does not answer
; in time, zeros: no names, and no variable kept.
.proc page_load
.a8
.i16
    rep #$20
.a16
    lda f:DBG_PAGE_AT
    cmp #.loword(DBG_PAGE_RAM0)
    beq second
    lda #.loword(DBG_PAGE_RAM0)
    bra chosen
second:
    lda #.loword(DBG_PAGE_RAM1)
chosen:
    sta f:DBG_PAGE_AT
    lda f:DBG_PAGE
    and #$00FF
    asl a
    tax
    lda #DBG_PAGE_MAX
    sta f:DBG_RD_LEN
    lda f:dbg_pages, x
    pha
    lda f:DBG_PAGE_AT
    tay
    plx                         ; its unit
    lda #0
    jsr dbg_read
.a8
    bcc ready
    rep #$20
.a16
    lda f:DBG_PAGE_AT
    tax
    ldy #DBG_PAGE_MAX
    sep #$20
.a8
    lda #0
zero:
    sta f:$7F0000, x
    inx
    dey
    bne zero
ready:
    rts
.endproc

; The windows' tilemap and its bars, `dbg_frame`, from the `.msu` into
; `DBG_FRAME_RAM`; zeros if it does not answer in time, which is no window.
.proc frame_load
.a8
.i16
    rep #$20
.a16
    lda #DBG_FRAME_BYTES
    sta f:DBG_RD_LEN
    ldx #.loword(dbg_frame)
    ldy #.loword(DBG_FRAME_RAM)
    lda #0
    jsr dbg_read
.a8
    bcc ready
    ldx #.loword(DBG_FRAME_RAM)
    ldy #DBG_FRAME_BYTES
    lda #0
zero:
    sta f:$7F0000, x
    inx
    dey
    bne zero
ready:
    rts
.endproc

; Whether the text layer shows all it was given —`tl_pace`'s question—:
; carry set if it does. Clobbers A.
.proc shown
.a8
.i16
    rep #$20
.a16
    lda f:$7E0000 + TL_UP_N
    ora f:$7E0000 + TL_MAP_DIRTY
    bne no
    lda f:$7E0000 + TL_IDLE_DONE
    beq no
    sep #$20
.a8
    sec
    rts
.a16
no:
    sep #$20
.a8
    clc
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
; and the pages' refresh. On the last page, the state's switch: see
; debug_switches.s.
.proc switch_flip
.a8
.i16
    lda f:DBG_KIND
    cmp #DBG_KIND_OFF
    bne the_game_s
    lda f:DBG_ROW
    jmp dbg_off_flip
the_game_s:
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
; clear if it does not keep it. Only a variable of the loaded page: its
; table is `DBG_PAGE_AT`'s, the slot plus two and 0 none. Clobbers A.
.proc variable_slot
.a16
.i16
    sec
    sbc f:DBG_BASE
    dec a                       ; its place in the page
    asl a
    asl a                       ; four bytes each
    clc
    adc f:DBG_PAGE_AT
    tax
    lda f:$7F0002, x
    beq none
    dec a
    dec a
    tax
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

; The string at X of bank $7F —a page's, see `page_load`—, by reference, at
; `pick_table`.
.proc string_at
.a8
.i16
    lda f:$7F0000, x
    beq none
    sta temp                    ; how many letters
    rep #$20
.a16
    txa
    inc a
    sta msg_ptr
    sep #$20
.a8
    lda #^DBG_PAGE_RAM0
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
    cmp #DBG_KIND_OFF
    beq state_kind
    lda #'V'
    bra kind
state_kind:
    lda #'D'
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
    lda f:DBG_KIND
    cmp #DBG_KIND_OFF
    bne the_game_s_name
    jmp state_row
the_game_s_name:
    ; The name: the page's k-th switch's word, or its k-th variable's first
    ; one, an offset in the page's block —see `pages` in
    ; rm2k-snes-screens—, 0 none.
    rep #$20
.a16
    lda 1, s
    sec
    sbc f:DBG_BASE
    dec a                       ; its place in the page
    asl a
    tax
    sep #$20
.a8
    lda f:DBG_KIND
    rep #$20
.a16
    beq name                    ; `rep` leaves Z alone
    txa
    asl a                       ; a variable's is two words
    tax
name:
    txa
    clc
    adc f:DBG_PAGE_AT
    tax
    lda f:$7F0000, x
    beq no_name_16
    clc
    adc f:DBG_PAGE_AT
    tax                         ; the string, in bank $7F
    sep #$20
.a8
    bra named
.a16
no_name_16:
    sep #$20
.a8
    bra no_name
named:
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
on:
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

state_row:
    ; A switch of the state's: its name from the ROM, copied, and `[ON]`
    ; while the game has its way —see debug_switches.s—.
    lda f:DBG_SROW
    ldy #DBG_NAME_COL
    jsr at
    lda 3, s                    ; the row, under the number
    jsr dbg_off_name
    lda f:dbg_off_names, x
    sta f:DBG_T1                ; how many letters
name_letter:
    inx
    lda f:dbg_off_names, x
    jsr letter
    lda f:DBG_T1
    dec a
    sta f:DBG_T1
    bne name_letter
    lda f:DBG_SROW
    ldy #DBG_ONOFF_COL
    jsr at
    rep #$20
.a16
    pla                         ; the number
    sep #$20
.a8
    lda 1, s                    ; and the row
    jsr dbg_off_is
    bcs state_off_row
    jmp on
state_off_row:
    jmp off
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
    ; Quad 0, the blank one every cell without text points to: four tiles;
    ; and the lower half's, at `TL_HI_LOWER`, its tile 0.
    ldy #0
    jsr blank_quad
    ldy #TL_HI_LOWER
    jsr blank_quad
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
    ; The windows' tiles and colours, `dbg_border`, through where the font's
    ; cache goes: it starts afterwards. If the `.msu` does not answer in
    ; time, the windows go without them.
    rep #$20
.a16
    lda #(DBG_BORDER_TILES * 16 + DBG_BORDER_COLORS * 2)
    sta f:DBG_RD_LEN
    ldx #.loword(dbg_border)
    ldy #.loword(DBG_CSLOTS)
    lda #0
    jsr dbg_read
.a8
    bcs no_windows
    rep #$20
.a16
    lda #(DBG_BORDER_COLORS * 2)
    sta f:DBG_LEN
    ldx #.loword(DBG_CSLOTS + DBG_BORDER_TILES * 16)
    sep #$20
.a8
    ldy #DBG_CGRAM
    lda #^DBG_CSLOTS
    jsr dma_cgram
    rep #$20
.a16
    lda #(DBG_BORDER_TILES * 16)
    sta f:DBG_LEN
    ldx #.loword(DBG_CSLOTS)
    sep #$20
.a8
    ldy #DBG_TILES_VRAM
    lda #^DBG_CSLOTS
    jsr dma_vram
no_windows:
    jsr cache_clear
    ; Mode 5: BG1 at 4bpp, the text, and BG2 at 2bpp, the windows, both
    ; with cells 16 pixels wide.
    lda #$05
    sta BGMODE
    lda #DBG_NBA_UPPER          ; BG1 from word 0, BG2 from its tiles
    sta BG12NBA
    lda #(TL_HI_MAP / 1024 * 4)
    sta BG1SC
    lda #(DBG_WIN_MAP / 1024 * 4)
    sta BG2SC
    ; And from line 112 BG1's tiles from `TL_HI_LOWER`: the HDMA, which
    ; `dbg_view` turns on with the screen.
    lda #$00                    ; one register, written once
    sta DMAP7
    lda #<BG12NBA
    sta BBAD7
    ldx #.loword(dbg_hdma)
    stx A1T7L
    lda #^dbg_hdma
    sta A1B7
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

; The HDMA's table: BG12NBA for the upper half, written on line 0, and for
; the lower one from line 112, `TL_HI_SPLIT`'s first. A line's text goes
; from its third pixel row to its fifteenth, so the line the write lands on
; is blank in either half. HDMA reads it from the ROM every frame.
dbg_hdma:
    .byte TL_HI_SPLIT * 8, DBG_NBA_UPPER
    .byte 1, DBG_NBA_LOWER
    .byte 0
.assert TL_HI_SPLIT * 8 < 128, error, "an HDMA entry counts 127 lines at most"

; A blank quad, four tiles of zeros, at VRAM word Y. With the screen off.
.proc blank_quad
.a8
.i16
    sty VMADDL
    rep #$20
.a16
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
    rts
.endproc

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
    ldx #.loword(DBG_FRAME_RAM)
    sep #$20
.a8
    ldy #DBG_WIN_MAP
    lda #^DBG_FRAME_RAM
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
    lda #DBG_HDMA               ; from the next frame on, in the vblank
    sta HDMAEN
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
    adc #.loword(DBG_FRAME_RAM)
    sta f:DBG_SRC
    sep #$20
.a8
    lda #^DBG_FRAME_RAM
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
    adc #.loword(DBG_FRAME_RAM + DBG_BARS_AT)
    sta f:DBG_SRC
    sep #$20
.a8
    lda #^DBG_FRAME_RAM
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
    adc #DBG_WIN_MAP
    tay
    lda f:DBG_SRC
    tax
    sep #$20
.a8
    lda f:DBG_SRC_BK
    jmp dma_vram
.endproc

.assert DBG_BAR_BYTES = 128, error, "a bar is 128 bytes: see `rows`"
.assert DBG_BARS_AT = 32 * 28 * 2, error, "dbg_frame is the windows' tilemap and then the bars"

; --- the `.msu` ------------------------------------------------------------------

; Whether the pause menu offers the screen: carry set if there is an MSU-1,
; its `.msu` is this build's —`msu_data_valid`— and so is the region its
; pieces are in —its signature against `msu_spill_signature`, as
; `msu_required` asks at the boot of a game that needs the MSU-1—. Two
; seeks, each time the pause menu is drawn: nothing without an MSU-1, and
; in Mednafen, where a seek takes one or two frames, that many more on
; opening it. From `menu_rows_build`, with `jsl`. Clobbers A and X.
.proc dbg_available
.a8
.i16
    lda f:MSU_HAS
    beq no
    jsl f:msu_data_valid_l
    jsr port_moved
    cmp #1
    bne no
    rep #$20
.a16
    lda #0
    tax                         ; unit 0: the region's signature
    jsr dbg_seek
.a8
    bcs no
    ldx #0
compares:
    lda f:MSU_DATA
    cmp f:msu_spill_signature, x
    bne no
    inx
    cpx #8
    bcc compares
    sec
    rtl
no:
    clc
    rtl
.endproc

; The `.msu`'s sound effects remember where they left the port, so as not to
; seek twice —see `se_msu_upload`—, and the screen moves it. Keeps A.
.proc port_moved
.a8
.i16
    pha
    lda #$FF
    sta f:MSU_SE_NEXT
    sta f:MSU_SE_NEXT + 1
    sta f:MSU_SE_NEXT + 2
    pla
    rts
.endproc

; Seeks the `.msu` to byte A16 of the piece at unit X of the region
; —`MSU_SPILL_AT` plus the unit, times 256, plus A— and waits for the port.
; Returns with A8, the carry set if the wait ran out: unlike
; `msu_spill_seek`'s, it has the cap `msu_data_seek` has, because what is
; read here can go without. Clobbers X. It keeps nothing in RAM: the pause
; menu asks with it too, and the screen's is not its own then.
.proc dbg_seek
.a16
.i16
    pha
    sep #$20
.a8
    jsr port_moved
    sta f:MSU_SEEK              ; byte 0: the offset's low one
    rep #$20
.a16
    pla
    xba
    and #$00FF                  ; the offset's high byte, in units
    phx
    clc
    adc 1, s                    ; and the unit
    plx                         ; the pulls keep the carry
    tax
    lda #0
    rol a
    pha                         ; that sum's carry
    txa
    clc
    adc #.loword(MSU_SPILL_AT)
    sta f:MSU_SEEK + 1          ; bytes 1 and 2
    pla
    adc #^MSU_SPILL_AT          ; with this one's carry
    sep #$20
.a8
    sta f:MSU_SEEK + 3          ; the one that seeks, last
    ldx #0
wait:
    lda f:MSU_STATE
    bpl ready                   ; bit 7: still seeking
    inx
    cpx #MSU_WAIT
    bcc wait
    sec
    rts
ready:
    clc
    rts
.endproc

; `DBG_RD_LEN` bytes from byte A16 of the piece at unit X, into
; bank $7F from Y, by DMA from the port through the WRAM's: channel 0, with
; the source fixed. Returns with A8, the carry set if the seek ran out, and
; then nothing was read. Clobbers X.
.proc dbg_read
.a16
.i16
    phy
    jsr dbg_seek
.a8
    ply
    bcs out
    rep #$20
.a16
    tya
    sta f:WMADDL
    lda f:DBG_RD_LEN
    sta f:DAS0L
    lda #MSU_DATA
    sta f:A1T0L
    sep #$20
.a8
    lda #1                      ; bit 16 of the 17: bank $7F
    sta f:WMADDH
    lda #0
    sta f:A1B0
    lda #$08                    ; to the B bus, one register, the source fixed
    sta f:DMAP0
    lda #<WMDATA
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    clc
out:
    rts
.endproc

; The font's cache, empty: no letter in the index, no slot held, and the
; first slot next. When the screen opens: the map was in that WRAM.
.proc cache_clear
.a8
.i16
    rep #$20
.a16
    ldx #0
    lda #0
index:
    sta f:DBG_CINDEX, x
    inx
    inx
    cpx #(16 * DBG_GLYPHS)
    bcc index
    ldx #0
    lda #$FFFF
owner:
    sta f:DBG_COWNER, x
    inx
    inx
    cpx #(2 * DBG_SLOTS)
    bcc owner
    lda #0
    sta f:DBG_CSLOT
    lda #.loword(DBG_CSLOTS)
    sta f:DBG_CADDR
    sep #$20
.a8
    rts
.endproc

; The letter the text layer's wide mode composes, `TL_C` at phase `TL_X`'s
; low three bits, into `comp_glyph`: where `tl_glyph_hi` reads it. From
; the cache, or into it from the `.msu` —a seek and `FONT_PRE_CHAR` bytes;
; the next slot in turn, whoever held it forgets it—. If the `.msu` does
; not answer in time the letter is blank, all rows "nothing", and the next
; time it is asked for again. The multiplier holds `TL_C` times
; `FONT_PRE_CHAR`: the letter's offset in its phase's piece. A16, data bank
; $7E, from `tl_glyph_hi`. Clobbers X and Y.
.proc dbg_glyph
.a16
.i16
    lda f:RDMPYL
    sta f:DBG_GOFS
    lda TL_X
    and #$0007
    sta f:DBG_KEY
    lda TL_C
    asl a
    asl a
    asl a
    ora f:DBG_KEY
    asl a                       ; a word per letter and phase
    sta f:DBG_KEY
    tax
    lda f:DBG_CINDEX, x
    beq miss
    sta comp_glyph
    jmp bank
miss:
    lda f:DBG_CSLOT
    tax
    lda f:DBG_COWNER, x
    cmp #$FFFF
    beq free
    tax
    lda #0
    sta f:DBG_CINDEX, x         ; its letter is no longer in the cache
    lda f:DBG_CSLOT
    tax
free:
    lda f:DBG_KEY
    sta f:DBG_COWNER, x
    and #$000E                  ; the phase, times two
    tax
    lda #FONT_PRE_CHAR
    sta f:DBG_RD_LEN
    lda f:DBG_CADDR
    tay
    lda f:tl_hi_pre_lo, x       ; its piece's unit
    tax
    lda f:DBG_GOFS
    jsr dbg_read
    rep #$20
.a16
    bcs blank
    lda f:DBG_KEY
    tax
    lda f:DBG_CADDR
    sta f:DBG_CINDEX, x
    bra taken
blank:
    lda f:DBG_CSLOT
    tax
    lda #$FFFF
    sta f:DBG_COWNER, x         ; nobody's: the index does not point here
    lda f:DBG_CADDR
    tax
    ldy #(FONT_PRE_CHAR / 2)
    lda #$FFFF
nothing:
    sta f:$7F0000, x
    inx
    inx
    dey
    bne nothing
taken:
    lda f:DBG_CADDR
    sta comp_glyph
    clc
    adc #FONT_PRE_CHAR
    tay
    lda f:DBG_CSLOT
    inc a
    inc a
    cmp #(2 * DBG_SLOTS)
    bcc next
    lda #0
    ldy #.loword(DBG_CSLOTS)
next:
    sta f:DBG_CSLOT
    tya
    sta f:DBG_CADDR
bank:
    sep #$20
.a8
    lda #^DBG_CSLOTS
    sta comp_glyph + 2
    rep #$20
.a16
    rtl
.endproc
.popseg
.a8
.i16
.endif
