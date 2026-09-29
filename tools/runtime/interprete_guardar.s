.segment "CODE"
.a8
.i16

; --- the interpreter: saving and the permissions ---------------------------
;
; Opcode handlers: the `correr_codigo` dispatch, in interprete.s, jumps to
; each one with Y on its first operand, and each one returns to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.

; `OpenSaveMenu`: the slot screen in save mode, and the save goes to whichever
; slot the player picks. No operands. See `OP_SAVE` in tools/port/eventos.py.
;
; **It blocks inside the interpreter and costs no tick**, which is what RM2k
; does: `OpenSaveMenu` pushes `Scene_Save`, the map stops updating until it
; closes, and the page goes on with the next command. Here `ranuras_pantalla`
; runs its own frame loop —as it does from the title— and `vueltas` does not
; advance while it is shown, so both interpreters are still on the same tick
; when it returns. Cancelling with B goes back to the map without saving,
; which is also what RM2k does; picking a slot saves and returns, without
; asking whether the slot was taken, because `Scene_Save::Action` does not
; ask either.
;
; The screen overwrote the tiles in VRAM and palette 0, and `volver_al_mapa`
; puts them back. The game state is not touched: the event table, the move
; routes, the OAM and the poses in VRAM stay as they were, and that is why
; `cargar_mapa` is not called: it would reset all of that.
;
; Until 2026-09-10 this saved to the loaded slot —or to the first one—
; without showing anything, and the attempt to open the screen gave "black
; with garbage": the test ROM had no title, and without a title the converter
; emitted the slot screen as one filler byte with `RANURA_TILES` at zero.
; Today it goes in every ROM.
.proc op_save
    phy
    lda #1                      ; save mode
    jsr ranuras_pantalla
    cmp #$FF
    beq cancelado
    jsr poner_ranura
    jsr guardar_partida
cancelado:
    jsr volver_al_mapa
    ply
    jmp correr_codigo::otro

.endproc

; `ChangeSaveAccess`, `ChangeMainMenuAccess` and `ChangeEscapeAccess`: **the
; bit** of the permission and whether it ends up allowed. Sets or clears that
; "forbidden" bit of `FAR_ACCESO`.
;
; The converter sets the bit and it is not computed here, and that is what
; lets permissions be added without touching this opcode: the operand used to
; be the permission's number and the bit came from an `inc a`, which gives $01
; and $02 for the first two and **$03 for the third**, that is, forbidding the
; other two things at once.
.proc op_access
.a8
.i16
    lda [cod_ptr], y            ; the bit: $01 save, $02 the menu, $04 escape
    sta temp
    iny
    lda [cod_ptr], y            ; allowed
    iny
    sta temp + 1
    phy
    ; The permission is looked at with an 8-bit A and not with Y: with 16-bit
    ; index registers, `ldy temp + 1` also took `temp + 2`, and a permission
    ; at zero with garbage next to it ended up allowed.
    jsr acceso_leer
    xba                         ; B = the permissions, while we look
    lda temp + 1
    beq acceso_prohibir
    lda temp
    eor #$FF
    sta temp
    xba
    and temp
    bra acceso_listo
acceso_prohibir:
    xba
    ora temp
acceso_listo:
    jsr acceso_escribir
    ply
    jmp correr_codigo::otro

.endproc
