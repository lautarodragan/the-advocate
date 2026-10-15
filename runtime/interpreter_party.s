.segment "CODE"
.a8
.i16

; --- the interpreter: the party --------------------------------------------
;
; Opcode handlers: the dispatch in `run_code`, in interpreter.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp run_code::other` or ends the frame with `rts`.
;
; Gold and items are in interpreter_gold_and_items.s.

.proc op_party
    lda [code_ptr], y           ; 0 = add, 1 = remove
    sta temp
    iny
    lda [code_ptr], y           ; the actor
    iny
    phy
    jsr change_party
    ply
    jmp run_code::other         ; `bra` does not reach: the loop ended up far away

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
    lda [code_ptr], y           ; the actor
    iny
    sta temp
    lda [code_ptr], y           ; the graphic
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

; `ChangeHeroName`: which of the game's names an actor carries. The body is
; `change_name`, outside bank 0, which reads the operands.
.proc op_change_name
    jsl f:change_name
    jmp run_code::other
.endproc

; `FullHeal`, and `ChangeHP` when it adds. Only the entry is here: the body is
; `heal`, outside bank 0, and it reads its operands and advances the cursor
; itself, with Y in hand.
.proc op_heal
    jsl f:heal
    jmp run_code::other

.endproc

; `ChangeHP` that subtracts or reads a variable, `ChangeSP`, and the
; `ChangeCondition` that removes death: the same, with `actor_change`.
.proc op_actor
    jsl f:actor_change
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

; `ChangeExp` and `ChangeLevel`: the body is `exp_change`, in level.s.
.proc op_exp
    jsl f:exp_change
    jmp run_code::other

.endproc

; The level-up message, a page each time through: `level_page`, in level.s,
; says whether there is one left —C— and whether it is ready at `msg_ptr`
; or has to wait for another page's window —A—. While there is, the cursor
; stays on this opcode, so it comes back here when the window closes, the
; way `op_message` comes back when it waits.
.proc op_level_page
    jsl f:level_page
    bcs stays
    jmp run_code::other
stays:
    dey                         ; back on this same opcode
    sty ev_cur
    cmp #0                      ; `dey` left its own flags
    beq waits
    rep #$20
.a16
    jsr msg_start_at
waits:
    sep #$20
.a8
    rts

.endproc

