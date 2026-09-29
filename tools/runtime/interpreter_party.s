.segment "CODE"
.a8
.i16

; --- the interpreter: the party --------------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::otro` or ends the frame with `rts`.
;
; Gold and items are in interpreter_gold_and_items.s.

.proc op_party
    lda [code_ptr], y            ; 0 = add, 1 = remove
    sta temp
    iny
    lda [code_ptr], y            ; the actor
    iny
    phy
    jsr change_party
    ply
    jmp run_code::other     ; `bra` does not reach: the loop ended up far away

.endproc

; `ChangeSpriteAssociation`: the actor and the index of the graphic in the
; map's table, the same one that move command 34 of a route resolves. See
; OP_ACTOR_SPRITE in events.py.
;
; The `ResetGraphic()` that RM2k does to the `Game_Player` is the `jsr
; pick_hero_graphic` down here, and it only runs if the one that changed is
; the one leading: the one not leading is not drawn, and what was saved will
; be read by `pick_hero_graphic` when its turn comes —when the party
; changes or when another map loads—.
;
; `apply_tint` afterwards for the same reason as in `change_party`: the
; CGRAM row the leader had borrowed is left with its fifteen colors on top of
; the map's, and it has to be restored from the cartridge.
.proc op_actor_sprite
.a8
.i16
    lda [code_ptr], y            ; the actor
    iny
    sta temp
    lda [code_ptr], y            ; the graphic
    iny
    sta temp + 1
    phy
    lda temp
    jsr actor_gfx_write
    lda temp
    cmp party                   ; is it the leader?
    bne gfx_no_leads
    jsr pick_hero_graphic
    jsr apply_tint
gfx_no_leads:
    ply
    jmp run_code::other

.endproc

; `FullHeal`, and `ChangeHP` when it adds. Only the entry is here: the body is
; `heal`, outside bank 0, and it reads its operands and advances the cursor
; itself, with Y in hand.
.proc op_heal
    jsl f:heal
    jmp run_code::other

.endproc

; `ChangeEquipment` and `ChangeSkills`: like `op_heal`, only the entry. The
; bodies are `equipment_remove` and `skill_change`, outside bank 0.
.proc op_equipment
    jsl f:equipment_remove
    jmp run_code::other

.endproc

.proc op_skill
    jsl f:skill_change
    jmp run_code::other

.endproc

