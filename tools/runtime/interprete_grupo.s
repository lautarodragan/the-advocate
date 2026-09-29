.segment "CODE"
.a8
.i16

; --- the interpreter: the party --------------------------------------------
;
; Opcode handlers: the dispatch in `correr_codigo`, in interprete.s, jumps to
; each one with Y on its first operand, and each one goes back to the loop
; with `jmp correr_codigo::otro` or ends the frame with `rts`.
;
; Gold and items are in interprete_oro_e_items.s.

.proc op_party
    lda [cod_ptr], y            ; 0 = add, 1 = remove
    sta temp
    iny
    lda [cod_ptr], y            ; the actor
    iny
    phy
    jsr cambiar_grupo
    ply
    jmp correr_codigo::otro     ; `bra` does not reach: the loop ended up far away

.endproc

; `ChangeSpriteAssociation`: the actor and the index of the graphic in the
; map's table, the same one that move command 34 of a route resolves. See
; OP_ACTOR_SPRITE in eventos.py.
;
; The `ResetGraphic()` that RM2k does to the `Game_Player` is the `jsr
; elegir_grafico_heroe` down here, and it only runs if the one that changed is
; the one leading: the one not leading is not drawn, and what was saved will
; be read by `elegir_grafico_heroe` when its turn comes —when the party
; changes or when another map loads—.
;
; `aplicar_tinte` afterwards for the same reason as in `cambiar_grupo`: the
; CGRAM row the leader had borrowed is left with its fifteen colors on top of
; the map's, and it has to be restored from the cartridge.
.proc op_actor_sprite
.a8
.i16
    lda [cod_ptr], y            ; the actor
    iny
    sta temp
    lda [cod_ptr], y            ; the graphic
    iny
    sta temp + 1
    phy
    lda temp
    jsr actor_graf_escribir
    lda temp
    cmp grupo                   ; is it the leader?
    bne graf_no_lidera
    jsr elegir_grafico_heroe
    jsr aplicar_tinte
graf_no_lidera:
    ply
    jmp correr_codigo::otro

.endproc

; `FullHeal`, and `ChangeHP` when it adds. Only the entry is here: the body is
; `curar`, outside bank 0, and it reads its operands and advances the cursor
; itself, with Y in hand.
.proc op_heal
    jsl f:curar
    jmp correr_codigo::otro

.endproc

; `ChangeEquipment` and `ChangeSkills`: like `op_heal`, only the entry. The
; bodies are `equipo_quitar` and `habilidad_cambiar`, outside bank 0.
.proc op_equipment
    jsl f:equipo_quitar
    jmp correr_codigo::otro

.endproc

.proc op_skill
    jsl f:habilidad_cambiar
    jmp correr_codigo::otro

.endproc

