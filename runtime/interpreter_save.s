.segment "CODE"
.a8
.i16

; --- the interpreter: saving and the permissions ---------------------------
;
; Opcode handlers: the `run_code` dispatch, in interpreter.s, jumps to
; each one with Y on its first operand, and each one returns to the loop
; with `jmp run_code::other` or ends the frame with `rts`.

; `OpenSaveMenu`: the slot screen in save mode, and the save goes to whichever
; slot the player picks. No operands. See `OP_SAVE` in rm2k-snes/bytecode/src/events.rs.
;
; **It blocks inside the interpreter and costs no tick**, which is what RM2k
; does: `OpenSaveMenu` pushes `Scene_Save`, the map stops updating until it
; closes, and the page goes on with the next command. Here `slots_screen`
; runs its own frame loop —as it does from the title— and `ticks` does not
; advance while it is shown, so both interpreters are still on the same tick
; when it returns. Cancelling with B goes back to the map without saving,
; which is also what RM2k does; picking a slot saves and returns, without
; asking whether the slot was taken, because `Scene_Save::Action` does not
; ask either.
;
; The screen overwrote the tiles in VRAM and palette 0, and `back_to_map`
; puts them back. The game state is not touched: the event table, the move
; routes, the OAM and the poses in VRAM stay as they were, and that is why
; `enter_map` is not called: it would reset all of that.
;
; Until 2026-09-10 this saved to the loaded slot —or to the first one—
; without showing anything, and the attempt to open the screen gave "black
; with garbage": the test ROM had no title, and without a title the converter
; emitted the slot screen as one filler byte with `SLOT_TILES` at zero.
; Today it goes in every ROM.
.proc op_save
    phy
    lda #1                      ; save mode
    jsr slots_screen
    cmp #$FF
    beq cancelled
    jsr set_slot
    jsr save_game
cancelled:
    jsl f:screen_unerase        ; the map comes back even if an event erased it
    jsr back_to_map
    ply
    jmp run_code::other

.endproc

; `ChangeSaveAccess`, `ChangeMainMenuAccess` and `ChangeEscapeAccess`: **the
; bit** of the permission and whether it ends up allowed. Sets or clears that
; "forbidden" bit of `FAR_ACCESS`.
;
; The converter sets the bit and it is not computed here, and that is what
; lets permissions be added without touching this opcode: the operand used to
; be the permission's number and the bit came from an `inc a`, which gives $01
; and $02 for the first two and **$03 for the third**, that is, forbidding the
; other two things at once.
.proc op_access
.a8
.i16
    lda [code_ptr], y           ; the bit: $01 save, $02 the menu, $04 escape
    sta temp
    iny
    lda [code_ptr], y           ; allowed
    iny
    sta temp + 1
    phy
    ; The permission is looked at with an 8-bit A and not with Y: with 16-bit
    ; index registers, `ldy temp + 1` also took `temp + 2`, and a permission
    ; at zero with garbage next to it ended up allowed.
    jsr access_read
    xba                         ; B = the permissions, while we look
    lda temp + 1
    beq access_forbid
    lda temp
    eor #$FF
    sta temp
    xba
    and temp
    bra access_ready
access_forbid:
    xba
    ora temp
access_ready:
    jsr access_write
    jsl f:compar_owe_access     ; a pure parallel common event may set it back
    ply
    jmp run_code::other

.endproc

; `OP_MENU_OPEN`: a custom menu —the common event it replaces compiles to
; this—. Like `OpenSaveMenu`, it blocks inside the page and costs no tick,
; and on leaving the map comes back and the page goes on: see
; `custom_menu.s`. With a big picture up it does nothing: the map that comes
; back would go under it.
.proc op_menu_open
.a8
.i16
    lda [code_ptr], y           ; the menu
    iny
    phy
    pha
    lda f:BIG_FLAGS
    lsr a
    pla
    bcs leave
    phb
    phk
    plb
    jsl f:cm_from_page
    ; The edges that closed it belong to it, as with the shop.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz menu_open
    lda boot_frames
    sta nmi_seen
    plb
leave:
    ply
    jmp run_code::other
.endproc
