.segment "CODE"
.a8
.i16

; --- the interpreter: switches and variables -------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.
;
; The timer is in interprete_cronometro.s, and the conditions on a variable
; in interprete_condiciones.s.

; `ControlVars`, one variable at a time: slot, operation, operand class, and
; sixteen-bit a and b. See OP_VAR in eventos.py. Sixteen bits signed,
; wrapping around.
.proc op_var
.a8
.i16
    lda [code_ptr], y
    sta temp                    ; the slot
    iny
    lda [code_ptr], y
    sta temp + 1                ; the operation, with VAR_REFRESCO on top
    iny
    lda [code_ptr], y            ; the operand class
    iny
    phy                         ; Y -> a; restored at the end
    ; Class 6 first: it is the one that the parallel pages comparing cells run
    ; every frame —the ones for the race, the lights on map 11—.
    cmp #VAR_PERSONAJE
    bne :+
    jmp var_de_personaje
:
    cmp #VAR_VARIABLE
    beq var_de_variable
    cmp #VAR_AZAR
    beq var_al_azar
    cmp #VAR_OTRO
    beq var_de_otro
    rep #$20
.a16
    lda [code_ptr], y            ; a constant
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_variable:
    lda [code_ptr], y            ; the slot it comes from
    jsr var_read
.a16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_otro:
    lda [code_ptr], y
    bne var_del_timer
    ; The gold, capped at 32767: the variable is sixteen bits signed.
    lda gold + 2
    bne var_oro_tope
    rep #$20
.a16
    lda gold
    bmi var_oro_tope_16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
.a16
var_oro_tope_16:
    sep #$20
.a8
var_oro_tope:
    lda #$FF
    sta temp + 2
    lda #$7F
    sta temp + 3
    bra var_aplicar
var_del_timer:
    rep #$20
.a16
    lda timer_sec               ; the seconds the timer has left
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_al_azar:
    ; a + x mod (b - a + 1), with x the next step of the xorshift and the
    ; modulo done with the hardware's eight-bit divider: the converter does
    ; not let through a range wider than 255.
    jsr random_next
    sta WRDIVL                  ; the dividend, sixteen bits
    lda [code_ptr], y            ; a
    sta temp + 2
    iny
    iny
    lda [code_ptr], y            ; b
    sec
    sbc temp + 2
    inc a                       ; b - a + 1
    sep #$20
.a8
    sta WRDIVB                  ; starts it: sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL                  ; the remainder
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_aplicar:
    ; `temp + 2` is the operand; depending on the operation, it is set as is
    ; or added to or subtracted from what the variable had.
    lda temp + 1
    and #<~VAR_REFRESCO
    beq var_pone
    lda temp
    jsr var_read                ; A = what it had, sixteen bits
.a16
    pha
    sep #$20
.a8
    lda temp + 1
    and #<~VAR_REFRESCO
    cmp #VAR_SUMAR
    beq var_suma
    rep #$20
.a16
    pla
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    bra var_pone
var_suma:
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_pone:
    lda temp + 1                ; the operation, which carries the refresh bit
    xba
    lda temp
    jsr var_write            ; and the refresh, if the operation asks for
                                ; it: the pages that look at this variable may
    ply                         ; change. See `var_write`
    iny                         ; a and b, four bytes
    iny
    iny
    iny
    jmp run_code::otro

var_de_personaje:
    ; Class 6: a character's coordinates, in cells. `a` is the target —0 the
    ; hero, the event index plus one, the same byte as OP_ROUTE— and `b` says
    ; which one: PERSONAJE_X or PERSONAJE_Y.
    ;
    ; The cell read is the **live** one: `tile_x`/`tile_y` for the hero and
    ; `ev_pos_buf` for an event, which is where a forced move route, a
    ; ChangeEventLocation or a TradeEventLocations left it. In RM2k it is
    ; `character->GetX()`, that is, the same thing.
    ; Neither operand is stored in RAM: the BSS is full —two more bytes and
    ; `ld65` warns that it does not fit— and there is no need. The target
    ; **times** EV_STRIDE is carried in X, which nobody uses here, with the
    ; offset folded into the address: that way the hero ends up with X at zero
    ; and telling it apart is a `cpx`, which does not touch the accumulator.
    lda [code_ptr], y            ; a: the target
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes per event
    tax
    sep #$20
.a8
    iny
    iny
    lda [code_ptr], y            ; b: which coordinate
    cpx #$0000
    beq var_personaje_heroe
    ; An event: its cell is in `ev_pos_buf`, indexed by the index in the
    ; map's table, which is the target minus one; hence the - EV_STRIDE.
    cmp #PERSONAJE_X
    beq var_personaje_ev_x
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 2, x
    bra var_personaje_listo
.a8
var_personaje_ev_x:
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 0, x
    bra var_personaje_listo
.a8
var_personaje_heroe:
    cmp #PERSONAJE_X
    beq var_personaje_heroe_x
    rep #$20
.a16
    lda tile_y
    bra var_personaje_listo
.a8
var_personaje_heroe_x:
    rep #$20
.a16
    lda tile_x
var_personaje_listo:
    sta temp + 2
    sep #$20
.a8
    jmp var_aplicar

.endproc

; Two class-6 `ControlVars` and two `ConditionalBranch` on variable equality,
; fused into one: see `cell_test`, which lives in bank 1.
.proc op_cell_test
    jsl f:cell_test + FAST   ; see MEMSEL
    jmp run_code::otro
.endproc

.proc op_switch
    rep #$20
.a16
    lda [code_ptr], y            ; the number, 16 bits
    sta temp
    sep #$20
.a8
    iny
    iny
    lda [code_ptr], y            ; and whether it goes on or off
    iny
    phy
    jsr set_switch
    ply
    jmp run_code::otro     ; `bra` does not reach: the loop is far away

.endproc

