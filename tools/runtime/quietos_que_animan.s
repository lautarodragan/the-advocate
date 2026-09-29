.segment "CODE"

; --- the still events that animate anyway ---------------------------------
;
; RM2k's `animation_type` 1 and 3 —"Continuous" and "Fixed Dir/Continuous"—
; make the event run through its walk cycle **without moving**. The save point
; in Lashe City is of the second kind, and taro asked for it on 2026-09-07.
;
; The ones that walk already do this: their move route slot carries the counter
; and `.proc animar_ruta_ev` advances it. The still ones have no slot, and there
; is nowhere to keep a counter for them: the NPC's row has no free byte —+11 is
; the jump height— and the BSS is full. So the column comes from the game
; clock, the same as the ChipSet animation: `vueltas` divided by how many
; frames between changes, which is `anim_continua` for the speed, and the
; four-step cycle with the third step repeating the first.
;
; **The phase is not RM2k's**, which starts each character's counter when the
; map creates it; here it is global. It is declared in
; workflow/divergencias/la-fase-de-los-quietos-que-animan.md, and all it changes
; is which of the four steps of the cycle each event enters on.
;
; It runs before `mover_eventos` on purpose: if a forced move route grabs one of
; these, the slot overwrites its pose afterwards and wins, since it is the one
; that carries the real counter.
.proc animar_quietos
.a8
.i16
    ; Does this map have any? The padding of the last family in `anim_tabla`
    ; says so; without this we would have to walk the forty rows every time.
    ldy #(ANIM_FAMILIAS - 1)
    jsr anim_donde
    lda f:anim_tabla + 7, x
    bne hay
    rts
hay:
    ldy #$0000
otra:
    cpy npc_total
    beq listo
    lda npc_buf + 14, y
    beq siguiente               ; hidden: not drawn
    lda npc_buf + 13, y
    bpl siguiente               ; bit 7 is "still and animating"
    and #$7F
    dec a                       ; the speed, 0 to 5
    phy
    rep #$20
.a16
    and #$00FF
    tax
    ; The tick being drawn is `vueltas + 1` as seen from here, which is the
    ; same number the ChipSet animation looks at —it reads it after the `inc
    ; vueltas`—. Measured: without the `inc`, the save point on map 8 stays
    ; one column behind and that is 76 pixels. Without the frozen ticks, like
    ; it: see `vueltas_congeladas`.
    lda vueltas
    sec
    sbc f:vueltas_congeladas
    inc a
    sta WRDIVL                  ; the dividend, in a single 16-bit write
    sep #$20
.a8
    lda anim_continua, x        ; how many frames between column changes
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    and #(AGUA_CICLO_N - 1)
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ciclo_tres, x           ; the column: 0, 1, 2 or back to 1
    ply
    sta temp + 3
    ; The pose: where its page faces times three, plus the column. With a
    ; fixed facing —which is what `animation_type` 3 asks for— nobody turns it.
    jsr mirada_de_fila          ; its page's, or the turn's
    sta temp + 2
    asl a
    clc
    adc temp + 2
    clc
    adc temp + 3
    sty npc_fila
    jsr subir_pose_npc
    ldy npc_fila
siguiente:
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
    rts
.endproc
