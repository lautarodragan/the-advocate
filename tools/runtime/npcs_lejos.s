.segment "FAR"
.a8
.i16

; ===========================================================================
; The NPCs, their move route slots and the OAM, from bank 1
; ===========================================================================
;
; What runs for each event that moves, or for each NPC row, on every frame or
; on every step that starts. In the race —forty cars, five of them moving—
; this took almost a hundred lines of the frame's 262, and bank 0 had no room
; to make it faster: it lives here, in the fast mirror, and the callers over
; there come in with `jsl f:... + FAST`. See
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.

; --- an NPC row that changed, into its place --------------------------------
;
; Leaves row `npc_row` where it now belongs, with the table already sorted,
; and `npc_row` at its new place. The order is RM2k's: greater Y —which goes
; inside the key, together with the layer—, then greater X, and then greater
; id. The three tie-breakers are needed because an event that walks changes
; row all the time and ties with anyone; with still NPCs it was hardly ever
; noticeable.
;
; Only the one that changed is moved: Y changes by two pixels per frame, and
; sorting the whole table every frame would cost the same even if nobody
; moved. Until 2026-09-27 it moved one place at a time, swapping the two whole
; rows at each one; in the race a car that changes lane goes past the seven or
; eight on the lane next to it at once, and five cars starting their step on
; the same frame added up to thirty lines. Now it first searches how far it
; goes, comparing with its key, and the rows in between are shifted all
; together with an `mvn`/`mvp`: the same order in the end, which is the one
; the one-by-one swaps left.
;
; Clobbers `temp` and `cmp_a`, and X and Y.
.proc fit_far
.a8
.i16
    rep #$20
.a16
    ldx npc_row
    lda npc_buf + 4, x
    sta temp                    ; its key: the layer and the Y
    lda npc_buf + 0, x
    sta temp + 2                ; its X
    lda npc_buf + 8, x
    and #$00FF
    sta cmp_a                   ; its event
    ; Does it go up? As long as it goes before the one above.
    txy
subir:
    cpy #$0000
    beq tope_arriba
    lda temp
    cmp npc_buf + 4 - NPC_STRIDE, y
    bne s_por_clave
    lda temp + 2
    cmp npc_buf + 0 - NPC_STRIDE, y
    bne s_por_clave
    lda npc_buf + 8 - NPC_STRIDE, y
    and #$00FF
    cmp cmp_a
    bcs tope_arriba             ; the one above has the greater or equal id
    bra s_pasa
s_por_clave:
    bcc tope_arriba             ; the one above goes first
s_pasa:
    tya
    sec
    sbc #NPC_STRIDE
    tay
    bra subir
tope_arriba:
    cpy npc_row
    beq no_sube
    ; It goes up to Y: the row, set aside; the ones from Y to its own, one
    ; place down; and the row at Y.
    sty cmp_a                   ; where it goes (its event is no longer needed)
    jsr apartar
    phb
    lda npc_row
    sec
    sbc cmp_a                   ; how many bytes are shifted
    dec a
    pha
    lda npc_row
    clc
    adc #.loword(npc_buf) - 1
    tax                         ; the last of the ones shifted
    adc #NPC_STRIDE             ; carry was left at zero
    tay                         ; and where it goes
    pla
    mvp #^FAR_LENGTH, #^FAR_LENGTH
    plb
    ldx cmp_a
    jsr volver
    sep #$20
.a8
    rtl
.a16
no_sube:
    ; Does it go down? As long as the one below goes before it.
lower:
    tya
    clc
    adc #NPC_STRIDE
    cmp npc_total
    bcs tope_abajo
    tax
    lda npc_buf + 4, x
    cmp temp
    bne b_por_clave
    lda npc_buf + 0, x
    cmp temp + 2
    bne b_por_clave
    lda npc_buf + 8, x
    and #$00FF
    cmp cmp_a
    beq tope_abajo              ; the same id: it does not pass
    bcc tope_abajo              ; the one below has the smaller id
    bra b_pasa
b_por_clave:
    bcc tope_abajo              ; the one below goes after
b_pasa:
    txy
    bra lower
tope_abajo:
    cpy npc_row
    beq ready
    sty cmp_a
    jsr apartar
    phb
    tya
    sec
    sbc npc_row                ; how many bytes are shifted
    dec a
    pha
    lda npc_row
    clc
    adc #.loword(npc_buf)
    tay                         ; where they go: where it was
    adc #NPC_STRIDE
    tax                         ; and from where: the one after it
    pla
    mvn #^FAR_LENGTH, #^FAR_LENGTH
    plb
    ldx cmp_a
    jsr volver
ready:
    sep #$20
.a8
    rtl

; Row `npc_row`, set aside in `NPC_ROW_SEPARATE`; and back at X.
.a16
apartar:
    ldx npc_row
    .repeat ::NPC_STRIDE / 2, k
    lda npc_buf + k * 2, x
    sta f:NPC_ROW_SEPARATE + k * 2
    .endrepeat
    rts
volver:
    .repeat ::NPC_STRIDE / 2, k
    lda f:NPC_ROW_SEPARATE + k * 2
    sta npc_buf + k * 2, x
    .endrepeat
    stx npc_row
    rts
.endproc
.assert .bankbyte(npc_buf) = 0 && .loword(npc_buf) < $2000, error, "fit_far shifts the rows in bank $7E: npc_buf has to be in low RAM"

; --- whether some row imposes its passability bits --------------------------
;
; `pass_has` right after the NPC table is loaded: one if some row has a +15
; other than $FF. Runs once per map.
.proc pass_look
.a8
.i16
    stz pass_has
    ldy #$0000
otra:
    cpy npc_total
    beq ready
    lda npc_buf + 15, y
    cmp #$FF
    beq :+
    sta pass_has
:
    rep #$21
.a16
    tya
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
ready:
    rtl
.endproc

; --- the objects, hidden -----------------------------------------------------
;
; All objects start hidden, and `build_oam` does it at the start of every
; frame. An object 32 tall at row 224 covers 224 to 255, that is, entirely
; outside the 224 that are visible, and without wrapping the counter.
;
; Unrolled and in bank 1 —in the fast mirror—, because the one-object-at-a-time
; loop that was in bank 0 took fifteen lines of every frame, on every map: a
; quarter of what the race had to spare. This way it is about four. See
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
.proc oam_hide
.a8
.i16
    ldx #$0000
grande:
    lda #$E0
    .repeat 16, k
    sta oam + 1 + k * 4, x      ; each object's Y
    .endrepeat
    rep #$21                    ; M at sixteen and carry at zero
.a16
    txa
    adc #16 * 4
    tax
    sep #$20
.a8
    cpx #512
    bne grande
    ; The small table: two bits per object, the high one says whether it is
    ; large. Only object 0 is; the rest stay small and hidden all the same.
    rep #$20
.a16
    .repeat 16, k
    stz oam_high + k * 2
    .endrepeat
    sep #$20
.a8
    lda #$02
    sta oam_high                ; object 0: large size
    rtl
.endproc

; --- the move route slots -----------------------------------------------------

; Move route slot X —in bytes, times ROUTE_EV_STRIDE— has just become event
; A's: it is noted in its parallel state, `PAIR_SLOT`, so that `one_parallel`
; does not have to search for it. It belongs to the two places that hand out
; a slot —`route_for_event` and `apply_pages`—, and lives here because
; of bank 0. Does not touch A, X or Y.
.proc slot_record
    php
    rep #$30
.a16
.i16
    pha
    phx
    phy
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAIR_BYTES
    tay
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; from bytes to slot number
    inc a
    tyx
    sep #$20
.a8
    sta f:FAR_LENGTH + FAR_PAIR_STATE + PAIR_SLOT, x
    rep #$20
.a16
    ply
    plx
    pla
    plp
    rtl
.endproc
.assert ROUTE_EV_STRIDE = 32, error, "slot_record divides by ROUTE_EV_STRIDE with five lsr"

; The `npc_buf` row of the event of move route slot X, in Y, or $FFFF if it
; has none. It is `event_npc` for `refresh_npc`, which asks for it for
; every event that moves and on every frame: the search walks the rows from
; the first one, and on a map with forty events it was four lines for each.
;
; The row is remembered in the slot's +19, plus one, and is trusted only if
; it still belongs to that event: the rows are reordered when two events
; cross in Y (`fit_npc`), and a slot just taken carries whatever was left
; in it. Otherwise, it is searched for and noted. Does not touch X; A is lost.
.proc slot_npc
.a8
.i16
    lda route_ev + 19, x
    beq buscar
    dec a
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a                       ; times NPC_STRIDE
    tay
    sep #$20
.a8
    cpy npc_total
    bcs buscar                  ; outside the table: a leftover
    lda npc_buf + 8, y
    cmp route_ev + 0, x
    beq ready
buscar:
    lda route_ev + 0, x
    sta temp
    ldy #$0000
otra:
    cpy npc_total
    beq no_hay
    lda npc_buf + 8, y
    cmp temp
    beq hallada
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
hallada:
    rep #$20
.a16
    tya
    lsr a
    lsr a
    lsr a
    lsr a
    inc a
    sep #$20
.a8
    sta route_ev + 19, x
ready:
    rtl
no_hay:
    ldy #$FFFF
    rtl
.endproc
.assert NPC_STRIDE = 16, error, "slot_npc multiplies by NPC_STRIDE with four asl"
.assert NPC_MAX < 255, error, "slot_npc stores the row plus one in a byte"
