.segment "FAR2"

; --- the weapon a skill asks for --------------------------------------------
;
; `Game_Actor::IsSkillUsable`, RM2k 2000's and 2003's alike: an actor's skill
; with a physical attribute is grey —in the battle's list and in the menu's,
; and A does not choose it— unless a weapon it holds carries that attribute.
; The model is `weapons_allow` in `rm2k-rules`, where the rule is explained.
; It reads the attribute tables of `battle_attributes.s`, the converter's
; `skill_weapon` among them, and that file's routines, which is why it comes
; after it: `ca65` does not see a `.proc`'s labels before the `.proc`.

; Whether LDB actor A8 can use skill `k` Y —its low byte— by its weapons:
; Z=0 and A8 = 1 if so. `Game_Actor::IsSkillUsable`: each attribute the
; converter put in the skill's `skill_weapon` row —its physical ones, unless
; it shifts ranks— has to be on the weapon in slot 0 or on a weapon in slot
; 1, a two-weapon actor's second one; a shield carries nothing. The battle's
; list and the menu's grey a skill by it, so it reads everything with `f:`
; and runs with the data bank at $7E or at 0. Clobbers X, Y and `temp`.
.proc ba_weapons_allow
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sta temp                    ; the actor
    tya
    and #$00FF
    asl a
    tax
    lda f:skill_weapon, x
    beq allowed                 ; row 0, the empty set: it asks for nothing
    pha                         ; 1,s: the row it asks for
    lda temp
    jsr ba_attr_equipment_row
    tax
    phx
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x
    jsr ba_attr_attack::weapon_row
    sta temp                    ; the first weapon's row
    plx
    lda f:FAR_LENGTH + FAR_EQUIPMENT + 2, x
    jsr ba_attr_attack::weapon_row
    sta temp + 2                ; the second's: a shield gives the empty one
    ldy #0
each:
    cpy #ATTR_N
    bcs carried
    tya
    clc
    adc 1, s
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    beq next                    ; not asked
    rep #$20
.a16
    tya
    clc
    adc temp
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    bne next                    ; on the first
    rep #$20
.a16
    tya
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    lda f:attr_sets, x
    beq refused                 ; on neither
next:
    rep #$20
.a16
    iny
    bra each
carried:
    pla
allowed:
    sep #$20
.a8
    lda #1
    rts
refused:
.a8
    rep #$20
.a16
    pla
    sep #$20
.a8
    lda #0
    rts
.endproc
