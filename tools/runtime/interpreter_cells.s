.segment "FAR"
.a8
.i16

; --- OP_CELL_TEST: "is this character on the cell in the variables?" ---------
;
; It is the pattern RM2k's parallel pages use to check whether two characters
; touch: two class-6 `ControlVars` that copy one's cell into two variables, and
; two nested `ConditionalBranch` that compare them with two others. The
; converter fuses the four into one —see `fundir_celdas` in events.py— and it
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
.macro CELL_WRITE
.local do_refresh, already, is_y, put
    lda [code_ptr], y
    iny
    iny
    bmi do_refresh              ; CELL_REFRESH, bit 15
already:
    bit #CELL_Y
    bne is_y
    and #CELL_VARIABLE
    tax
    lda temp
    bra put
do_refresh:
    pha
    sep #$20
    lda #1
    sta f:refresh
    rep #$20
    pla
    bra already
is_y:
    and #CELL_VARIABLE
    tax
    lda temp + 2
put:
    sta f:FAR_LENGTH + FAR_VARIABLES, x
.endmacro

; One of the two comparisons: two variables, as offsets, and the target if
; they are not equal. If it fails, it leaves Y on the target and jumps to `end`.
.macro CELL_TEST end
.local fails
    lda [code_ptr], y           ; the left one
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta temp                    ; the character's cell is no longer needed
    iny
    iny
    lda [code_ptr], y           ; and the right one
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    cmp temp
    bne fails
    iny                         ; it holds: skip the right one and the target
    iny
    iny
    iny
    bra :+
fails:
    iny
    iny
    lda [code_ptr], y           ; the target, absolute within the page
    tay
    bra end
:
.endmacro

; What is left of a write without the top two bits: the variable's offset,
; which with 256 slots goes up to 510.
CELL_VARIABLE = $01FF
.assert CELL_Y = $4000 && CELL_REFRESH = $8000, error, "cell_test reads the refresh from the N bit and the coordinate from bit 14"

.proc cell_test
.a8
.i16
    jsr cell_test_near
    rtl
.endproc

; The same, for callers in bank 1: returns with `rts`.
.proc cell_test_near
.a8
.i16
    rep #$20
.a16
    lda [code_ptr], y           ; the target: 0 the hero, or the event plus one
    iny
    and #$00FF
    asl a
    asl a                       ; times EV_STRIDE
    tax
    beq hero
    ; The live cell, the same as class 6 of `op_var`.
    lda f:ev_pos_buf - EV_STRIDE + 0, x
    sta temp
    lda f:ev_pos_buf - EV_STRIDE + 2, x
    sta temp + 2
    bra write
hero:
    lda tile_x
    sta temp
    lda tile_y
    sta temp + 2
write:
    ; All inline and without `jsr`: it runs forty times per frame.
    CELL_WRITE
    CELL_WRITE
    CELL_TEST ready
    CELL_TEST ready
ready:
    sep #$20
.a8
    rts
.endproc

; --- the parallels that go no further than their `OP_CELL_TEST` --------------
;
; `parallel_tick` runs the list of parallels one at a time, and each one pays
; for finding its state, saving it and returning: almost one line per page.
; But most of the race's —forty per lap— start with `OP_CELL_TEST`, are not
; in the middle of anything, fail the condition and end there. Those are run
; here back to back, from `pair_i`, up to the first one that is not like that;
; what each one does is exactly the shortcut of `one_parallel`: its condition,
; and since what follows is the `OP_DONE`, nothing else.
;
; It stops, without having touched anything of that one, at the first one that:
;   * does not start with `OP_CELL_TEST`;
;   * has the state of another page, a wait, or the page half run;
;   * moves —has a move route slot—: its step is taken by `one_parallel`;
; and before starting if there is a message or a choice on screen, because
; then it matters whose it is (see `one_parallel`). Returns with carry at 0 and
; `pair_i` on that one, or on `pair_n` if it reached the end.
;
; If one's condition holds —or what follows is not the `OP_DONE`— it has
; already run its first instruction, with whatever it writes: it returns with
; carry at 1, Y on the next one and `code_ptr`, `page_ofs`, `pair_dir` and
; `pair_ev` set, so that `one_parallel_continue` continues with its interpreter.
.proc parallel_cell
.a8
.i16
    lda f:msg_open
    ora f:msg_state
    ora pick_active
    bne no
other:
    lda pair_i
    cmp pair_n
    bcs no
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAIR_LIST_BYTES
    tax
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 1, x
    sta code_ptr
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 3, x
    sta code_ptr + 2
    lda [code_ptr]              ; the first opcode
    cmp #OP_CELL_TEST
    bne no
    rep #$20
.a16
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 4, x
    sta page_ofs
    lda f:FAR_LENGTH + FAR_PAIR_LIST + 0, x
    and #$00FF
    asl a
    asl a
    asl a                       ; times PAIR_BYTES
    sta pair_dir
    tax
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 5, x
    cmp page_ofs
    bne no16                    ; the state is another page's
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 2, x
    bne no16                    ; waiting
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_PAIR_STATE + 4, x
    bne no                      ; half run
    lda f:FAR_LENGTH + FAR_PAIR_STATE + PAIR_SLOT, x
    bne no                      ; it moves
    ldy #1
    jsr cell_test_near
    lda [code_ptr], y
    bne continues               ; did not end at its `OP_DONE`
    inc pair_i
    bra other
continues:
    rep #$20
.a16
    lda pair_dir
    lsr a
    lsr a
    lsr a
    sep #$20
.a8
    sta pair_ev
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

