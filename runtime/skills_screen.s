.segment "FAR2"
.a8
.i16

; --- the skills screen -------------------------------------------------------
;
; `Scene_Skill`, opened from the pause menu's Tech Skill —the command, then
; whose, on the menu itself—: on top the description of the skill under the
; cursor in two lines, below it the actor's status line, and the list in two
; columns that read by rows, eight at a time, each skill with its cost and in
; grey if the map cannot use it or the SP do not reach. B goes back to the
; menu with the cursor on the command. The geometry is `SK_*` of
; `rm2k-snes-screens`, whose `render` is the reference; eight rows and two
; lines of description where RM2k has ten and one is the divergence
; `the-skills-screen` in the book.
;
; **It is the custom menus' full screen** —see `custom_menu.s`—: the text on
; BG2 with the text layer from word 0 up to `CM_BG1_MAP`, the windows on BG1
; at 8bpp with their tiles from `CM_BG1_VRAM` and their colours from
; `CM_BORDER_CGRAM`, and no objects. What it overwrites is what a custom menu
; overwrites, and the map comes back the same way: `CM_DIRTY`, and
; `big_back_far` when the pause menu closes.
;
; **The list is the battle's**: `ba_skill_walk`, in `battle_skills.s`, walks
; the actor's pairs and keeps the visible page in `BA_SKILL_LIST`, and
; `ba_skill_see` scrolls it as `Window_Selectable` does. They run with the
; data bank at $7E; this screen runs with the pause menu's, 0, and reads the
; battle's state with `f:`. Nobody uses it while the menu is open.

.assert SK_ROWS * SK_COLUMNS <= BA_SKILL_MAX, error, "a page of the skills screen does not fit in BA_SKILL_LIST"
.assert SK_COLUMNS = 2, error, "the skills screen takes a row as two places"
.assert SK_BORDER_TILES > 0 && SK_BORDER_COLORS > 0, error, "the skills screen has no windows: a DMA of 0 bytes is 64 KB"
.assert CM_BG1_VRAM + SK_BORDER_TILES * 32 <= CM_OBJ_VRAM, error, "the skills screen's windows do not fit below the objects"
.assert CM_BORDER_CGRAM + SK_BORDER_COLORS <= 240, error, "the skills screen's colours step on the last palette"

; The bars go right after the arrangement, in its block, so one bank byte
; reads both: see `skills_screen.rs` in rm2k-snes-mapdata.
SK_BARS_OFS = 32 * 28 * 2

.pushseg
.segment "FARBSS"
sk_actor:    .res 1             ; the LDB actor whose list it is
sk_bar_on:   .res 1             ; the place whose bar is on screen, $FF none
sk_bar_want: .res 1             ; and the one it should be on
.popseg

; The LDB actor in A, with the data bank at 0. Returns with `rtl` when B is
; pressed, to the pause menu, which draws itself again.
.proc skills_screen
.a8
.i16
    sta f:sk_actor
    lda #0
    sta f:BAT_LENGTH + BA_SKILL_SEL
    sta f:BAT_LENGTH + BA_SKILL_TOP
    lda #SK_ROWS
    sta f:ba_skill_rows
    lda #(SK_ROWS * SK_COLUMNS)
    sta f:ba_skill_places
    lda #1
    sta f:CM_DIRTY              ; the map comes back whole when the menu closes
    jsr sk_upload
    jsr sk_view
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    jsr sk_bar_upload           ; in the vblank, before the text's
    jsl f:tl_map + FAST         ; `scr_upload`
    jsl f:tl_vblank + FAST
    jsl f:tl_work + FAST
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    ; The cursor, as the battle's list moves it: left and right by one, up
    ; and down by a row, without wrapping —`Window_Selectable` in two
    ; columns—. The arrows are the four low bits, shifted out one by one.
    .assert PAD_RIGHT = $01 && PAD_LEFT = $02 && PAD_DOWN = $04 && PAD_UP = $08, error, "the arrows' bits"
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sta f:CM_T0                 ; where it was, to see whether it moved
    lda title_edges
    lsr a
    bcc no_right
    lda f:BAT_LENGTH + BA_SKILL_SEL
    inc a
    bra to_place
no_right:
    lsr a
    bcc no_left
    lda f:BAT_LENGTH + BA_SKILL_SEL
    beq moved
    dec a
    bra to_place
no_left:
    lsr a
    bcc no_down
    lda f:BAT_LENGTH + BA_SKILL_SEL
    clc
    adc #SK_COLUMNS
    bra to_place
no_down:
    lsr a
    bcc no_arrow
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sec
    sbc #SK_COLUMNS
    bcc moved
to_place:
    cmp f:BAT_LENGTH + BA_SKILL_N
    bcs moved                   ; past the last one: it stays
    sta f:BAT_LENGTH + BA_SKILL_SEL
moved:
    lda f:CM_T0
    cmp f:BAT_LENGTH + BA_SKILL_SEL
    beq to_wait
    phb
    lda #$7E
    pha
    plb
    jsr ba_skill_see
    plb
    jsr sk_compose
to_wait:
    jmp wait
no_arrow:
    lda title_edges
    and #PAD_B
    beq to_wait
    ; Out: the B that closes is consumed, and the A from before, as the
    ; pause menu does; and what of the objects the windows' colours took.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    jsr cm_objects_back
    rtl
.endproc

; The screen from nothing, with it off: the text layer's bank, the inks, the
; windows' tiles and colours, every object out of the screen, and the
; registers. `cm_screen_upload` without the portrait.
.proc sk_upload
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:battle_bank_upload + FAST
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
    rep #$20
.a16
    lda #(SK_BORDER_COLORS * 2)
    sta f:CM_T0
    ldx #.loword(sk_border_cgram)
    sep #$20
.a8
    ldy #CM_BORDER_CGRAM
    lda #^sk_border_cgram
    jsr cm_dma_cgram
    rep #$20
.a16
    lda #(SK_BORDER_TILES * 64)
    sta f:CM_T0
    ldx #.loword(sk_border_tiles)
    sep #$20
.a8
    ldy #CM_BG1_VRAM
    lda #^sk_border_tiles
    jsr cm_dma_vram
    ; Every object below the screen, and the high table at zero.
    stz OAMADDL
    stz OAMADDL + 1
    ldx #128
hidden:
    stz OAMDATA
    lda #224
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne hidden
    ldx #32
high:
    stz OAMDATA
    dex
    bne high
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
    rts
.endproc

; The windows, the text composed whole and the bar, with the screen off;
; then on.
.proc sk_view
.a8
.i16
    rep #$20
.a16
    lda #CM_TEXT_POOL
    jsl f:tl_reset + FAST
    sep #$20
.a8
    jsl f:tl_low + FAST
    rep #$20
.a16
    lda #(32 * 28 * 2)
    sta f:CM_T0
    ldx #.loword(sk_layout)
    sep #$20
.a8
    ldy #CM_BG1_MAP
    lda #^sk_layout
    jsr cm_dma_vram
    lda #$FF
    sta f:sk_bar_on
    jsr sk_compose
    jsr sk_bar_upload
    jsl f:tl_map + FAST         ; with the screen off right after `tl_reset`,
    jsl f:tl_vblank + FAST      ; `scr_upload` composes the whole text
    jsl f:tl_work + FAST
    lda #$03
    sta TM
    jsl f:ba_t_vblank
    lda #$0F
    sta INIDISP
    rts
.endproc

; The bar to place `sk_bar_want`, off place `sk_bar_on`: each is two half
; rows of BG1's tilemap, the arrangement's own or the place's in the bars.
; In the vblank or with the screen off.
.proc sk_bar_upload
.a8
.i16
    lda f:sk_bar_on
    cmp f:sk_bar_want
    beq ready
    cmp #$FF
    beq paint
    ; Off: the arrangement's cells, a row of it below the other.
    jsr word_of
    rep #$20
.a16
    lda f:CM_T3
    asl a
    clc
    adc #.loword(sk_layout)
    sta f:CM_T1
    lda #64
    sta f:CM_T2
    sep #$20
.a8
    jsr two_rows
paint:
    lda f:sk_bar_want
    sta f:sk_bar_on
    jsr word_of
    rep #$20
.a16
    lda f:sk_bar_on
    and #$00FF
    xba
    lsr a
    lsr a                       ; times 64: a place's two half rows
    clc
    adc #.loword(sk_layout) + SK_BARS_OFS
    sta f:CM_T1
    lda #(SK_HALF_COLS * 2)
    sta f:CM_T2
    sep #$20
.a8
    jsr two_rows
ready:
    rts

; Where place A's bar starts in the tilemap, in words, into `CM_T3`:
; its row of the page twice, from the list's first, times 32, and sixteen
; more for the right column.
word_of:
    rep #$20
.a16
    and #$00FF
    pha
    and #$0001
    asl a
    asl a
    asl a
    asl a
    sta f:CM_T3
    pla
    lsr a
    asl a
    clc
    adc #SK_LIST_ROW0
    xba
    lsr a
    lsr a
    lsr a                       ; times 32
    clc
    adc f:CM_T3
    sta f:CM_T3
    sep #$20
.a8
    rts

; The half row from `CM_T1` to the tilemap's word `CM_T3`, and the one
; below it from `CM_T2` bytes further.
two_rows:
    jsr one_row
    rep #$20
.a16
    lda f:CM_T3
    clc
    adc #32
    sta f:CM_T3
    lda f:CM_T1
    clc
    adc f:CM_T2
    sta f:CM_T1
    sep #$20
.a8
one_row:
    rep #$20
.a16
    lda #(SK_HALF_COLS * 2)
    sta f:CM_T0
    lda f:CM_T3
    clc
    adc #CM_BG1_MAP
    tay
    lda f:CM_T1
    tax
    sep #$20
.a8
    lda #^sk_layout
    jmp cm_dma_vram
.endproc

; The text of the screen, written whole into the text layer's records —the
; rows that say what they said keep their tiles—: the description of the one
; under the cursor, the status line and the visible page. And where the bar
; goes.
.proc sk_compose
.a8
.i16
    jsl f:tl_clear + FAST
    phb
    lda #$7E
    pha
    plb
    lda f:sk_actor
    jsr ba_skill_walk
    plb
    ; The bar: on the cursor's place in the page, the first with none.
    lda f:BAT_LENGTH + BA_SKILL_TOP
    asl a
    sta f:CM_T0
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sec
    sbc f:CM_T0
    sta f:sk_bar_want
    jsr sk_status
    lda f:BAT_LENGTH + BA_SKILL_N
    bne has
    rts
has:
    ; --- the description: two slices of the battle's one text ---
    lda f:sk_bar_want
    jsr sk_k
    sta f:CM_T4                 ; the skill's `k`
    jsr desc_at
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_line1_n, x
    ldy #SK_HELP_ROW0
    jsr line
    jsr desc_at
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_line2_at, x
    and #$00FF
    clc
    adc msg_ptr
    sta msg_ptr
    sep #$20
.a8
    bcc same_bank               ; `sep` leaves the carry alone
    inc msg_ptr + 2
same_bank:
    lda f:skill_line2_n, x
    ldy #(SK_HELP_ROW0 + 2)
    jsr line
    ; --- the page ---
    lda #0
    sta f:CM_N                  ; the place in the page
place:
    lda f:BAT_LENGTH + BA_SKILL_TOP
    asl a
    clc
    adc f:CM_N
    cmp f:BAT_LENGTH + BA_SKILL_N
    bcs ready
    lda f:CM_N
    cmp #(SK_ROWS * SK_COLUMNS)
    bcs ready
    jsr sk_row
    lda f:CM_N
    inc a
    sta f:CM_N
    bra place
ready:
    rts

; `msg_ptr` at the start of skill `CM_T4`'s description.
desc_at:
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    asl a
    tax
    lda f:skill_desc, x
    tax
    sep #$20
.a8
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    rts

; A letters at `msg_ptr`, by reference, white, from the help's cell of row
; Y. Nothing if there are none.
line:
    cmp #0
    beq no_line
    sta temp
    tya
    ldy #SK_HELP_COL
    jsr cm_at
    stz temp + 1
    lda #1
    sta f:$7E0000 + TL_BY_REF
    lda #255
    sta comp_dup + 3
    jsl f:tl_text_at + FAST
no_line:
    rts
.endproc

; The `k` at place A of the page, in A. Only A and X.
.proc sk_k
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:BAT_LENGTH + BA_SKILL_LIST, x
    rts
.endproc

; Place `CM_N` of the page: the name, the dash and the cost, in grey if the
; map cannot use it or the SP do not reach —`Window_Skill::CheckEnable`,
; without states, which this port does not keep outside battle—.
.proc sk_row
.a8
.i16
    lda f:CM_N
    jsr sk_k
    sta f:CM_T4
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_on_map, x
    beq grey
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    sta f:CM_T0                 ; its SP
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    cmp f:CM_T0
    sep #$20
.a8
    beq white                   ; exactly as many as it has is enough
    bcs grey
white:
    lda #ITEM_WHITE
    bra colour
grey:
    lda #ITEM_GRAY
colour:
    sta temp + 1
    ; The row, and the column's first cell.
    lda f:CM_N
    and #1
    beq left
    lda #SK_COLUMN_DX
left:
    sta f:CM_T3                 ; the column's cell
    lda f:CM_N
    lsr a
    asl a
    clc
    adc #SK_LIST_ROW0
    sta f:CM_T3 + 1             ; the row
    ; The name, by reference, cut at its cells.
    lda #SK_NAME_DX
    jsr at
    lda #SK_NAME_CELLS
    sta comp_dup + 3
    lda #1
    sta f:$7E0000 + TL_BY_REF
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    asl a
    tax
    lda f:skill_txt, x
    tax
    sep #$20
.a8
    jsl f:tl_text + FAST
    ; The dash, and the cost in two places right after it: the number goes
    ; where the dash left the pen, and continues its run, as in the battle.
    lda #SK_DASH_DX
    jsr at
    lda #'-'
    jsl f:tl_letter + FAST
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #SK_COST_DIGITS
    sta comp_dup + 2
    jsl f:tl_number + FAST
    rts

; `pick_table` at the column's cell plus A, on its row.
at:
    clc
    adc f:CM_T3
    tay
    lda f:CM_T3 + 1
    jmp cm_at
.endproc

; The status line: the name, the level, "Normal", and the HP and the SP with
; their maximums for its level —`level_param`—, the terms in red.
.proc sk_status
.a8
.i16
    ; The name, by reference, cut at its cells.
    lda #SK_NAME_WIDTH
    ldy #SK_NAME_COL
    jsr place
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:actor_txt, x
    tax
    sep #$20
.a8
    jsl f:tl_text + FAST
    ; The level term, and the level.
    lda #255
    ldy #SK_LEVEL_COL
    jsr place
    lda #ITEM_RED
    sta temp + 1
    ldx #SK_TXT_LEVEL
    jsl f:tl_text + FAST
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x        ; `actor_level_of`, which is in another bank
    cmp #$FF
    beq no_level                ; one that cannot be in the party
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + EXP_LEVEL, x
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #LEVEL_PLACES
    ldy #SK_LEVEL_NUM_COL
    jsr number
no_level:
    ; The state: outside battle, always the normal one.
    lda #SK_STATE_WIDTH
    ldy #SK_STATE_COL
    jsr place
    ldx #BA_TXT_NORMAL
    jsl f:tl_text + FAST
    ; The HP and the SP.
    lda #0
    jsr points
    lda #1
    jmp points

LEVEL_PLACES = 2                ; "%2d", as the menu's level

; `pick_table` at cell Y of the status row, white, a text by reference of
; at most A cells.
place:
    sta comp_dup + 3
    lda #SK_STATUS_ROW
    jsr cm_at
    stz temp + 1
    lda #1
    sta f:$7E0000 + TL_BY_REF
    rts

; `comp_dup` in A places at cell Y of the status row, white.
number:
    sta comp_dup + 2
    lda #SK_STATUS_ROW
    jsr cm_at
    stz temp + 1
    jsl f:tl_number + FAST
    rts

; The HP —A = 0— or the SP —A = 1—: the term, and from its number's cell
; the current one in three places, the slash and the maximum for its level
; in three, one run.
points:
    sta f:CM_T2                 ; which: also `level_param`'s parameter
    ldy #SK_HP_COL
    ldx #BA_TXT_HP
    cmp #0
    beq term
    ldy #SK_SP_COL
    ldx #BA_TXT_SP
term:
    phx
    lda #255
    jsr place
    lda #ITEM_RED
    sta temp + 1
    plx
    jsl f:tl_text + FAST
    ; The current one, from far RAM: the SP follow the HP's table.
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:CM_T2
    and #$00FF
    beq hp_now
    lda f:FAR_LENGTH + FAR_SP, x
    bra now
hp_now:
    lda f:FAR_LENGTH + FAR_HP, x
now:
    jsr capped
    sep #$20
.a8
    ldy #SK_HP_NUM_COL
    lda f:CM_T2
    beq hp_cell
    ldy #SK_SP_NUM_COL
hp_cell:
    lda #3
    jsr number
    lda #'/'
    jsl f:tl_letter + FAST
    ; The maximum for its level.
    rep #$20
.a16
    lda f:CM_T2
    and #$00FF
    tay
    sep #$20
.a8
    lda f:sk_actor
    jsl f:level_param           ; into X; clobbers A and Y
    rep #$20
.a16
    txa
    jsr capped
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:tl_number + FAST
    rts

; A16 into `comp_dup`, at most 999, as the battle's line caps it.
capped:
.a16
    cmp #1000
    bcc fits
    lda #999
fits:
    sta comp_dup
    rts
.a8
.endproc
