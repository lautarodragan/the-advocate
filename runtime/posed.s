; --- still events drawn into the background ---------------------------------
; A still event that changes pose —a floor switch, a chest— can be drawn
; into the background's cells instead of as an object: the converter gives
; its cell one block per pose it can show, and here its cell of the grid and
; its four tilemap words are written again when its row's pose changes.
; Which events, and why the background and not the layer above: `posed` in
; Wally; the table: `posed.rs` in rm2k-snes-mapdata.
;
; **The row stays whole**: its pages, its routes, its triggers and its
; collisions are a still row's as ever, and the page writes its graphic and
; pose as into any still row (`page_graphic`), and a route's turn its pose
; (`still_turn`). What tells it apart is its attribute byte, whose priority
; bits say 3 —no character's object has it— and whose palette bits say
; which of its characters it shows; its tile byte is its number here.
; `build_oam` sends such a row to `posed_row` instead of placing an object,
; so a pose change reaches the screen in the same vblank an object's would:
; the runs of tilemap words `posed_row` leaves go up in `flush_video`, with
; the OAM.
;
; **Only a cartridge with such an event assembles any of this**: without
; `posed_stills` in the `.inc` the file is empty, and so are the calls to it.
;
; Everything here is reached with `jsl` and goes back with `rtl`.

.ifdef posed_stills

; **The tilemap words wait in runs**, one DMA each in the vblank: a cell is
; two rows of two words, and the rows of cells side by side are side by
; side in VRAM. Zounds' map 96 turns fifty-five floor switches with one
; switch, and word by word they did not fit in a vblank —eight cells cost
; seven lines, measured—; in runs, a row of switches is one DMA per line of
; tiles. So there are two regions, the cells' top rows and their bottom
; rows, each a list of runs and the words they upload, which grow
; downward: `build_oam` walks a row of cells from right to left —it sorts
; them by x too, front to back—, so the cell on the left of the last one
; puts its words right before that one's and the run grows from its start.
; A cell that is not beside the last one starts a run.
POSED_RUNS  = 16                ; runs a region holds: a DMA each, see posed_drain
POSED_WORDS = 128               ; and words: a row of 64 cells
PR_N     = 0                    ; word: how many runs
PR_P     = 2                    ; word: where the words start, from POSED_REG
PR_L     = 4                    ; word: where the last run is, from POSED_REG
PR_RUN   = 6                    ; POSED_RUNS runs: VRAM word, where its words are, how many
PR_WORDS = PR_RUN + 6 * POSED_RUNS
PR_SIZE  = PR_WORDS + 2 * POSED_WORDS

.pushseg
.segment "FARBSS"
POSED_REC:  .res 3              ; the loaded map's record, in posed_table's data
POSED_N:    .res 2              ; how many it has; 0 a map without any
; The key each one's cell shows now —character * 12 + pose, or $FF without
; it—: what the grid holds, which `posed_row` compares the row against.
POSED_LAST: .res POSED_MAX
POSED_REG:  .res 2 * PR_SIZE    ; the top rows' region, then the bottom rows'
POSED_T:    .res 16             ; scratch
.popseg
POSED_KEY   = POSED_T + 0       ; byte: the key the row asks for
POSED_P     = POSED_T + 1       ; byte: which one
POSED_BLOCK = POSED_T + 2       ; word: the block
POSED_X     = POSED_T + 4       ; word: the cell's 8x8 column, from the window's first
POSED_Y     = POSED_T + 6       ; word: and row
POSED_A     = POSED_T + 8       ; word: the VRAM word a run starts at
POSED_C     = POSED_T + 10      ; word: and how many words it has, 1 or 2
POSED_W     = POSED_T + 12      ; word: where they are, from POSED_REG
POSED_R     = POSED_T + 14      ; word: the region, from POSED_REG

; The fields of a record: see `posed.rs` in rm2k-snes-mapdata.
PS_GRID  = 0
PS_X     = 3
PS_Y     = 5
PS_NONE  = 7
PS_FROM  = 9
PS_START = 11

.segment "FAR3"

; Looks the map being entered up in `posed_table`, with `map_current` set,
; and takes its cells as the grid starts them. From `enter_map`, next to
; `wrap_find`.
.proc posed_find
.a8
.i16
    php
    rep #$30
.a16
    lda #0
    sta f:POSED_N
    jsr posed_empty
    ldx #0
other:
    lda f:posed_table, x
    cmp #$FFFF
    beq none
    cmp map_current
    beq found
    txa
    clc
    adc #5
    tax
    bra other
found:
    lda f:posed_table + 2, x
    sta f:POSED_REC
    sta temp
    sep #$20
.a8
    lda f:posed_table + 4, x
    sta f:POSED_REC + 2
    sta temp + 2
    lda [temp]
    sta f:POSED_N
    ; Each one's key as the grid starts it.
    rep #$20
.a16
    ldy #(1 + PS_START)
    ldx #0
start:
    sep #$20
.a8
    lda [temp], y
    sta f:POSED_LAST, x
    rep #$20
.a16
    tya
    clc
    adc #POSED_STRIDE
    tay
    inx
    txa
    cmp f:POSED_N
    bcc start
none:
    plp
    rtl
.endproc

; Row X, drawn into the background, from `build_oam` instead of placing it:
; if what it shows is not what its cell holds, the cell changes —the grid
; now, the tilemap in the next vblank, if the window holds the cell—. With
; no room in the runs it waits for the next frame, all of it.
;
; A pose $FF is a still row's after a battle or a big picture forgets the
; poses —`npc_poses_forget`—, until its page puts it back: the cell keeps
; what it shows.
.proc posed_row
.a8
.i16
    php
    lda npc_buf + 6, x
    sta f:POSED_P
    lda npc_buf + 14, x
    beq hidden                  ; its page draws nothing: the cell without it
    lda npc_buf + 12, x
    cmp #12
    bcc known
    plp
    rtl
known:
    sta f:POSED_KEY
    lda npc_buf + 7, x
    lsr a
    and #$07                    ; which of its characters
    sta f:POSED_BLOCK
    asl a
    clc
    adc f:POSED_BLOCK           ; times three
    asl a
    asl a                       ; times twelve
    clc
    adc f:POSED_KEY
    bra keyed
hidden:
    lda #$FF
keyed:
    sta f:POSED_KEY
    rep #$30
.a16
    lda f:POSED_P
    and #$00FF
    tax
    sep #$20
.a8
    lda f:POSED_LAST, x
    cmp f:POSED_KEY
    bne changes
    plp
    rtl
changes:
    rep #$20
.a16
    ; Room for two runs of two words in each region, or it waits.
    lda f:POSED_REG + PR_N
    cmp #(POSED_RUNS - 1)
    bcs full
    lda f:POSED_REG + PR_SIZE + PR_N
    cmp #(POSED_RUNS - 1)
    bcs full
    lda f:POSED_REG + PR_P
    cmp #(PR_WORDS + 4)
    bcc full
    lda f:POSED_REG + PR_SIZE + PR_P
    cmp #(PR_SIZE + PR_WORDS + 4)
    bcs room
full:
    plp                         ; no room for its cell: next frame
    rtl
room:
    sep #$20
.a8
    lda f:POSED_KEY
    sta f:POSED_LAST, x
    jsr posed_block             ; the block, and Y on its record
    jsr posed_grid
    ; The tilemap with the data bank at far RAM's: what follows reads and
    ; writes it a hundred times a cell, and the bank 0 RAM it reads too is
    ; the same WRAM there.
    phb
    sep #$20
.a8
    lda #^POSED_REG
    pha
    plb
    rep #$20
.a16
    jsr posed_queue
    plb
    plp
    rtl
.endproc

; The block of number `POSED_P` showing `POSED_KEY`, into `POSED_BLOCK`;
; `temp` points at the map's record and Y at the event's. A16 on return.
.proc posed_block
.a8
.i16
    rep #$30
.a16
    lda f:POSED_REC
    sta temp
    sep #$20
.a8
    lda f:POSED_REC + 2
    sta temp + 2
    rep #$20
.a16
    lda f:POSED_P
    and #$00FF
    asl a
    asl a
    sta f:POSED_BLOCK
    asl a
    clc
    adc f:POSED_BLOCK           ; times twelve
    inc a                       ; past the count
    tay
    lda f:POSED_KEY
    and #$00FF
    cmp #$00FF
    bne posed
    phy
    tya
    clc
    adc #PS_NONE
    tay
    lda [temp], y
    ply
    sta f:POSED_BLOCK
    rts
posed:
    asl a
    phy
    pha
    tya
    clc
    adc #PS_FROM
    tay
    lda [temp], y               ; where its blocks start
    clc
    adc 1, s
    tay
    pla
    lda [temp], y
    ply
    sta f:POSED_BLOCK
    rts
.endproc

; `POSED_BLOCK` into the event's cell of the grid, through the WRAM port: its
; address is in its record at Y. A narrow grid takes the low byte. A16 in
; and out.
.proc posed_grid
.a16
.i16
    phy
    lda [temp], y               ; PS_GRID, low word
    sta f:WMADDL
    iny
    iny
    sep #$20
.a8
    lda [temp], y               ; and the bank: $7E or $7F
    and #$01
    sta f:WMADDH
    lda f:POSED_BLOCK
    sta f:WMDATA
    rep #$20
.a16
    bit cell_mask               ; bit 15: set only in a wide grid
    bpl narrow
    sep #$20
.a8
    lda f:POSED_BLOCK + 1
    sta f:WMDATA
    rep #$20
.a16
narrow:
    ply
    rts
.endproc

; The cell's four tilemap words into the regions, those the window holds:
; the window is the torus of `build_column` and `build_row`, columns from
; `win_col - MARGIN_COLS` and rows from `win_row`, 64 by 32; a word outside
; it is built from the grid when it comes in. Y on the event's record, the
; data bank far RAM's. A16 in and out.
.proc posed_queue
.a16
.i16
    phy
    tya
    clc
    adc #PS_X
    tay
    lda [temp], y
    sta .loword(POSED_X)
    iny
    iny
    lda [temp], y               ; PS_Y
    sta .loword(POSED_Y)
    ply
    ; The top-left word's slot, by the map's 8x8 cell as `build_column`
    ; picks it: (row mod 32) * 32 + (column mod 32), the right screen 1024
    ; words on. The cell's column is even, so its right half is the next
    ; word, and its bottom row 32 words on.
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a
    sta .loword(POSED_A)
    lda .loword(POSED_X)
    and #$0020
    beq left_screen
    lda #1024
left_screen:
    clc
    adc .loword(POSED_A)
    sta .loword(POSED_A)
    lda .loword(POSED_X)
    and #$001F
    clc
    adc .loword(POSED_A)
    clc
    adc .loword(FAR_VRAM_MAP)
    sta .loword(POSED_A)
    ; Where it is in the window.
    lda .loword(POSED_X)
    sec
    sbc win_col
    clc
    adc #MARGIN_COLS
    sta .loword(POSED_X)
    lda .loword(POSED_Y)
    sec
    sbc win_row
    sta .loword(POSED_Y)
    lda .loword(POSED_BLOCK)
    asl a
    asl a
    asl a
    asl a                       ; its record is 16 bytes, the background's first
    tay
    ldx #0                      ; the top rows' region
    lda .loword(POSED_Y)
    cmp #WINDOW_ROWS
    bcs no_top                  ; unsigned: above it too
    jsr posed_pair
no_top:
    iny
    iny
    iny
    iny
    lda .loword(POSED_A)
    clc
    adc #32
    sta .loword(POSED_A)
    ldx #PR_SIZE                ; and the bottom rows'
    lda .loword(POSED_Y)
    inc a
    cmp #WINDOW_ROWS
    bcs no_bottom
    jsr posed_pair
no_bottom:
    rts
.endproc

; One row of the cell: the block's words at Y and Y + 2, for the VRAM word
; `POSED_A` and the next, into the region at X, those of the two the window
; holds —`POSED_X` is the left one's column in it—. Keeps Y. A16, the data
; bank far RAM's.
.proc posed_pair
.a16
.i16
    stx .loword(POSED_R)
    lda .loword(POSED_X)
    cmp #(WINDOW_COLS - 1)
    bcs edge
    ; Both: the right word below the region's words, then the left one.
    lda #2
    sta .loword(POSED_C)
    lda .loword(POSED_REG) + PR_P, x
    sec
    sbc #4
    sta .loword(POSED_REG) + PR_P, x
    sta .loword(POSED_W)
    tax
    lda [blocks_ptr], y
    sta .loword(POSED_REG), x
    iny
    iny
    lda [blocks_ptr], y
    sta .loword(POSED_REG) + 2, x
    dey
    dey
    jmp posed_link
edge:
    beq only_left               ; the last column of the window
    inc a
    beq only_right              ; the one left of it: only its right half is in
    rts
only_right:
    lda .loword(POSED_A)
    inc a
    sta .loword(POSED_A)
    iny
    iny
    jsr posed_one
    dey
    dey
    lda .loword(POSED_A)
    dec a
    sta .loword(POSED_A)
    rts
only_left:
.endproc
    ; falls into posed_one

; One word, the block's at Y, for the VRAM word `POSED_A`: a run of its own
; or the start of the last. Keeps Y. A16, the data bank far RAM's.
.proc posed_one
.a16
.i16
    ldx .loword(POSED_R)
    lda #1
    sta .loword(POSED_C)
    lda .loword(POSED_REG) + PR_P, x
    dec a
    dec a
    sta .loword(POSED_REG) + PR_P, x
    sta .loword(POSED_W)
    tax
    lda [blocks_ptr], y
    sta .loword(POSED_REG), x
.endproc
    ; falls into posed_link

; The words just put —`POSED_C` of them at `POSED_W`, for the VRAM word
; `POSED_A`— join the region's last run if they go right before it, in VRAM
; and below the region's words; if not, they are a run of their own. A16,
; the data bank far RAM's; X back on the region.
.proc posed_link
.a16
.i16
    ldx .loword(POSED_R)
    lda .loword(POSED_REG) + PR_N, x
    beq first
    lda .loword(POSED_REG) + PR_L, x
    tax
    lda .loword(POSED_REG), x   ; the last run's VRAM word
    sec
    sbc .loword(POSED_C)
    cmp .loword(POSED_A)
    bne apart
    lda .loword(POSED_REG) + 2, x ; and where its words are
    sec
    sbc .loword(POSED_C)
    sec
    sbc .loword(POSED_C)
    cmp .loword(POSED_W)
    bne apart
    lda .loword(POSED_A)
    sta .loword(POSED_REG), x
    lda .loword(POSED_W)
    sta .loword(POSED_REG) + 2, x
    lda .loword(POSED_REG) + 4, x
    clc
    adc .loword(POSED_C)
    sta .loword(POSED_REG) + 4, x
    ldx .loword(POSED_R)
    rts
apart:
    txa
    clc
    adc #6                      ; the run after the last
    bra place
first:
    txa
    clc
    adc #PR_RUN
place:
    ldx .loword(POSED_R)
    sta .loword(POSED_REG) + PR_L, x
    inc .loword(POSED_REG) + PR_N, x
    tax
    lda .loword(POSED_A)
    sta .loword(POSED_REG), x
    lda .loword(POSED_W)
    sta .loword(POSED_REG) + 2, x
    lda .loword(POSED_C)
    sta .loword(POSED_REG) + 4, x
    ldx .loword(POSED_R)
    rts
.endproc

; Both regions empty.
.proc posed_empty
.a16
.i16
    lda #0
    sta f:POSED_REG + PR_N
    sta f:POSED_REG + PR_SIZE + PR_N
    lda #PR_SIZE
    sta f:POSED_REG + PR_P
    lda #(2 * PR_SIZE)
    sta f:POSED_REG + PR_SIZE + PR_P
    rts
.endproc

; The runs to VRAM, in the vblank: from `flush_video`, after the strips, so
; a cell a strip just built comes out as its row says. A DMA each, on
; channel 0, which every DMA of the vblank sets up whole. How many there
; can be is `POSED_RUNS` a region, which `posed_row` keeps: a cell that does
; not fit waits for the next frame, whole, so no cell is ever seen half
; changed.
.proc posed_drain
    php
    phb
    rep #$30
.a16
    lda f:POSED_REG + PR_N
    ora f:POSED_REG + PR_SIZE + PR_N
    beq done
    sep #$20
.a8
    lda #0                      ; the registers' bank
    pha
    plb
    lda #$80                    ; advance after the high byte
    sta VMAIN
    lda #$01
    sta DMAP0                   ; two registers, word by word
    lda #$18
    sta BBAD0                   ; to VMDATAL
    lda #^POSED_REG
    sta A1B0
    rep #$20
.a16
    ldx #0
    jsr posed_region
    ldx #PR_SIZE
    jsr posed_region
    jsr posed_empty
done:
    plb
    plp
    rtl
.endproc

; Region X's runs. A16, the data bank 0.
.proc posed_region
.a16
.i16
    lda f:POSED_REG + PR_N, x
    beq none
    tay                         ; how many
run:
    lda f:POSED_REG + PR_RUN, x
    sta VMADDL
    lda f:POSED_REG + PR_RUN + 2, x
    clc
    adc #.loword(POSED_REG)
    sta A1T0L
    lda f:POSED_REG + PR_RUN + 4, x
    asl a                       ; in bytes
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #6
    tax
    dey
    bne run
none:
    rts
.endproc

; Back from a battle, which overwrote the grid: it comes back as the
; cartridge starts it, so each cell is written again with what it showed.
; Before `fill_window`, which builds the window from the grid. The runs go:
; the window is built whole.
.proc posed_sync
    php
    rep #$30
.a16
    jsr posed_empty
    ldx #0
other:
    txa
    cmp f:POSED_N
    bcs done
    sep #$20
.a8
    sta f:POSED_P
    lda f:POSED_LAST, x
    sta f:POSED_KEY
    phx
    jsr posed_block
    jsr posed_grid
    plx
    inx
    bra other
done:
    plp
    rtl
.endproc

.endif
