.segment "CODE"

; --- the twins on the hero's layer -------------------------------------------
;
; The rest of `hero_blocked`: whether the twin on (dest_x, dest_y) stops the
; hero. A twin —see `twin_in_cell`— is an event the converter left without a
; row; until 2026-10-17 none was on the hero's layer, and no step asked
; about them. Then Zounds' grids of invisible signs became twins: a sign
; stops the hero if the active page of the event whose row it shares is on
; his layer —it is the same page—, unless he walks through walls.
;
; Only for the hero: an event that walks into a twin's cell is not stopped,
; which RM2k would do.
;
; **Every cycle of this counts on a map without twins**, and that is why it
; is a file of its own at the end of bank 0, why the map's answer is a
; byte of the direct page and why that case goes straight to `cell_blocked`:
; A Blurred Line's race, forty cars on map 49, is at the edge of the frames
; its lap is allowed —see `EXTRA_FRAMES` in its
; `test_playthrough_race_golden.py`—, and the count flips with a handful of
; cycles per step of the hero or with code moved in front of its hot loops.
; Measured on 2026-10-17: 57 extra frames on `main` and with this, 61 with
; the same check in `cell_blocked` for every walker, or in `hero_blocked`,
; or reading the table's count or a word of far RAM on each step; the limit
; is 58.
.pushseg
.segment "ZEROPAGE"
; Whether the map has twins: 1 if the word behind its positions —how many—
; is not 0, which `note_twins` notes on loading it. A byte of the direct
; page, for the cycles: see `hero_blocked_rest`.
twins_here: .res 1
.popseg

; Declared before its use, so `lda twins_here` is a direct-page read.
.proc hero_blocked_rest
.a8
.i16
    lda twins_here
    bne with_twins
    jmp cell_blocked            ; most maps have none: as before them
with_twins:
    jsr cell_blocked
    bne blocked
    lda crossing
    bne free
    jsr twin_at_dest
    cmp #$FF
    beq free
    jsr active_layer
    cmp #HERO_LAYER_INDEX
    bne free
blocked:
    lda #1
    rts
free:
    lda #0
    rts
.endproc

; `twins_here` for the map being loaded, with `ev_total` already set and X
; on its record. It enters and leaves in sixteen bits, and keeps X and Y.
.proc note_twins
.a16
.i16
    phy
    lda ev_total
    asl a
    asl a                       ; times EV_STRIDE: past the positions
.assert EV_STRIDE = 4, error, "the arithmetic above multiplies by four by hand"
    tay
    lda f:map_table + M_PTR_EV_POS, x
    sta npc_ptr
    sep #$20
.a8
    lda f:map_table + M_PTR_EV_POS + 2, x
    sta npc_ptr + 2
    rep #$20
.a16
    lda [npc_ptr], y
    beq none
    lda #1
none:
    sep #$20
.a8
    sta twins_here
    rep #$20
.a16
    ply
    rts
.endproc

; `twin_in_cell` for (dest_x, dest_y), the cell the hero is about to step
; into: the index of the event whose row it shares in A, or $FF. Keeps
; (cell_x, cell_y), which the step's callers still use. Clobbers X and Y.
.proc twin_at_dest
.a8
.i16
    rep #$20
.a16
    lda cell_x
    pha
    lda cell_y
    pha
    lda dest_x
    sta cell_x
    lda dest_y
    sta cell_y
    sep #$20
.a8
    jsr twin_in_cell
    sta other_ev
    rep #$20
.a16
    pla
    sta cell_y
    pla
    sta cell_x
    sep #$20
.a8
    lda other_ev                ; and its flags, which the `pla` left
    rts
.endproc
