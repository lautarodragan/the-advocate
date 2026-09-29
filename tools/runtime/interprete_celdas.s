.segment "FAR"
.a8
.i16

; --- OP_CELL_TEST: "is this character on the cell in the variables?" ---------
;
; It is the pattern RM2k's parallel pages use to check whether two characters
; touch: two class-6 `ControlVars` that copy one's cell into two variables, and
; two nested `ConditionalBranch` that compare them with two others. The
; converter fuses the four into one —see `fundir_celdas` in eventos.py— and it
; does **exactly the same**: the two writes, with their refresh, and the two
; comparisons, each with its target.
;
; It exists for the cost, not for the semantics. Each lap of the race (49, 52
; and 54) has forty pages like this running every frame, and with the four
; opcodes the interpreter took almost five lines per page: the whole lap did
; not fit in a frame. Measured in
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
;
; It lives in bank 1 because there is no room in bank 0: `op_cell_test`, the
; dispatch handler, is a `jsl` to here. That is why everything uses long
; addressing: the data bank is the bytecode's.
;
; Enters with Y on the first operand and returns with Y on the next opcode or
; on the target of the condition that failed.
; One of the two writes: the variable, as an offset, with the coordinate and
; the refresh in the top two bits. `temp` is the character's x and `temp + 2`
; its y. Enters and leaves with a 16-bit A.
.macro CELDA_ESCRIBIR
.local refrescar, ya, es_y, poner
    lda [cod_ptr], y
    iny
    iny
    bmi refrescar               ; CELDA_REFRESCO, bit 15
ya:
    bit #CELDA_Y
    bne es_y
    and #CELDA_VARIABLE
    tax
    lda temp
    bra poner
refrescar:
    pha
    sep #$20
    lda #1
    sta f:refresco
    rep #$20
    pla
    bra ya
es_y:
    and #CELDA_VARIABLE
    tax
    lda temp + 2
poner:
    sta f:FAR_LARGO + FAR_VARIABLES, x
.endmacro

; One of the two comparisons: two variables, as offsets, and the target if
; they are not equal. If it fails, it leaves Y on the target and jumps to `fin`.
.macro CELDA_PROBAR fin
.local falla
    lda [cod_ptr], y            ; the left one
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    sta temp                    ; the character's cell is no longer needed
    iny
    iny
    lda [cod_ptr], y            ; and the right one
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    cmp temp
    bne falla
    iny                         ; it holds: skip the right one and the target
    iny
    iny
    iny
    bra :+
falla:
    iny
    iny
    lda [cod_ptr], y            ; the target, absolute within the page
    tay
    bra fin
:
.endmacro

; What is left of a write without the top two bits: the variable's offset,
; which with 256 slots goes up to 510.
CELDA_VARIABLE = $01FF
.assert CELDA_Y = $4000 && CELDA_REFRESCO = $8000, error, "celda_probar reads the refresh from the N bit and the coordinate from bit 14"

.proc celda_probar
.a8
.i16
    jsr celda_probar_cerca
    rtl
.endproc

; The same, for callers in bank 1: returns with `rts`.
.proc celda_probar_cerca
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; the target: 0 the hero, or the event plus one
    iny
    and #$00FF
    asl a
    asl a                       ; times EV_STRIDE
    tax
    beq heroe
    ; The live cell, the same as class 6 of `op_var`.
    lda f:ev_pos_buf - EV_STRIDE + 0, x
    sta temp
    lda f:ev_pos_buf - EV_STRIDE + 2, x
    sta temp + 2
    bra escribir
heroe:
    lda tile_x
    sta temp
    lda tile_y
    sta temp + 2
escribir:
    ; All inline and without `jsr`: it runs forty times per frame.
    CELDA_ESCRIBIR
    CELDA_ESCRIBIR
    CELDA_PROBAR listo
    CELDA_PROBAR listo
listo:
    sep #$20
.a8
    rts
.endproc

; --- the parallels that go no further than their `OP_CELL_TEST` --------------
;
; `paralelos_tick` runs the list of parallels one at a time, and each one pays
; for finding its state, saving it and returning: almost one line per page.
; But most of the race's —forty per lap— start with `OP_CELL_TEST`, are not
; in the middle of anything, fail the condition and end there. Those are run
; here back to back, from `par_i`, up to the first one that is not like that;
; what each one does is exactly the shortcut of `un_paralelo`: its condition,
; and since what follows is the `OP_DONE`, nothing else.
;
; It stops, without having touched anything of that one, at the first one that:
;   * does not start with `OP_CELL_TEST`;
;   * has the state of another page, a wait, or the page half run;
;   * moves —has a move route slot—: its step is taken by `un_paralelo`;
; and before starting if there is a message or a choice on screen, because
; then it matters whose it is (see `un_paralelo`). Returns with carry at 0 and
; `par_i` on that one, or on `par_n` if it reached the end.
;
; If one's condition holds —or what follows is not the `OP_DONE`— it has
; already run its first instruction, with whatever it writes: it returns with
; carry at 1, Y on the next one and `cod_ptr`, `pag_ofs`, `par_dir` and
; `par_ev` set, so that `un_paralelo_seguir` continues with its interpreter.
.proc paralelos_celda
.a8
.i16
    lda f:msg_abierto
    ora f:msg_estado
    ora eleg_activo
    bne no
otro:
    lda par_i
    cmp par_n
    bcs no
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAR_LISTA_BYTES
    tax
    lda f:FAR_LARGO + FAR_PAR_LISTA + 1, x
    sta cod_ptr
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_LISTA + 3, x
    sta cod_ptr + 2
    lda [cod_ptr]               ; the first opcode
    cmp #OP_CELL_TEST
    bne no
    rep #$20
.a16
    lda f:FAR_LARGO + FAR_PAR_LISTA + 4, x
    sta pag_ofs
    lda f:FAR_LARGO + FAR_PAR_LISTA + 0, x
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAR_BYTES
    sta par_dir
    tax
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 5, x
    cmp pag_ofs
    bne no16                    ; the state is another page's
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    bne no16                    ; waiting
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 4, x
    bne no                      ; half run
    lda f:FAR_LARGO + FAR_PAR_ESTADO + PAR_RANURA, x
    bne no                      ; it moves
    ldy #1
    jsr celda_probar_cerca
    lda [cod_ptr], y
    bne sigue                   ; did not end at its `OP_DONE`
    inc par_i
    bra otro
sigue:
    rep #$20
.a16
    lda par_dir
    lsr a
    lsr a
    lsr a
    sep #$20
.a8
    sta par_ev
    sec
    rtl
.a16
no16:
    sep #$20
.a8
no:
    clc
    rtl
.endproc

