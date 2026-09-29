.segment "FAR"

; --- equipment and skills from an event -------------------------------------
;
; The bodies of OP_EQUIPMENT and OP_SKILL, and what the "knows the skill"
; branch asks. They live here for the same reason as `heal`: they are entered
; with `jsl` from the interpreter, with Y on the operand and **the bytecode's
; data bank**, so everything they touch goes through `f:` or is on the direct
; page.

; `ChangeEquipment` that removes what is in a slot: the actor —or 0 for the
; whole party, as in `heal`— and the slot, 0 to 4. Returns with Y past it.
; Clobbers A, X and `temp`.
.proc equipment_remove
.a8
.i16
    lda [code_ptr], y            ; the actor
    iny
    sta temp + 2
    lda [code_ptr], y            ; the slot
    iny
    sta temp + 3
    phy
    lda temp + 2
    bne uno
    ; Up to `party_n`: see `heal`, which took the same care.
    ldx #0
slot:
    cpx party_n
    bcs ready
    lda party, x
    phx
    jsr equipment_remove_actor
    plx
    inx
    bra slot
uno:
    jsr equipment_remove_actor
ready:
    ply
    rtl
.endproc

; Actor A, slot `temp + 3`. It is easyrpg's `Game_Actor::ChangeEquipment(slot,
; 0)` (`game_actor.cpp:335`): the slot is left empty and what it held goes
; back to the inventory —`Game_Party::AddItem`, capped at ITEM_MAX—. The
; two-handed weapon business does not apply: removing never leaves two things
; where one fits. Clobbers X and `temp`.
.proc equipment_remove_actor
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta temp                    ; the actor times two
    asl a
    asl a
    clc
    adc temp                    ; times ten, which is what a row measures
    sta temp
    lda temp + 3
    and #$00FF
    asl a                       ; the slot is a word
    clc
    adc temp
    tax
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x
    beq ready                   ; it held nothing
    sta temp
    lda #0
    sta f:FAR_LENGTH + FAR_EQUIPMENT, x
    lda temp
    cmp #ITEMS_N
    bcs ready                   ; an item the inventory does not carry
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs listo8
    inc a
    sta f:FAR_LENGTH + FAR_ITEMS, x
listo8:
    rts
.a16
ready:
    sep #$20
.a8
    rts
.endproc

; `ChangeSkills`: the slot of the (actor, skill) pair and whether it is
; learned. It is setting or clearing its bit in `FAR_SKILL`: `LearnSkill` does
; nothing if it was already known and `UnlearnSkill` nothing if it was not,
; and with a bit both come for free. Returns with Y past the operands.
; Clobbers A, X and `temp`.
.proc skill_change
.a8
.i16
    rep #$20
.a16
    lda [code_ptr], y            ; the pair's slot
    iny
    iny
    sta temp + 2
    jsr skill_point
    sep #$20
.a8
    lda [code_ptr], y            ; 1 learns, 0 forgets
    iny
    cmp #0
    beq olvidar
    lda f:FAR_LENGTH + FAR_SKILL, x
    ora temp
    bra put
olvidar:
    lda temp
    eor #$FF
    and f:FAR_LENGTH + FAR_SKILL, x
put:
    sta f:FAR_LENGTH + FAR_SKILL, x
    rtl
.endproc

; `IsSkillLearned` for the `ConditionalBranch` branch: the pair's slot in
; `temp + 2`, and returns with Z=0 if it is known. Clobbers A, X and `temp`.
.proc skill_known
.a8
.i16
    jsr skill_point
    lda f:FAR_LENGTH + FAR_SKILL, x
    and temp
    rtl                         ; `rtl` does not touch the flags: the `and`
                                ; holds
.endproc

; The pair's slot in `temp + 2` → X at its byte of `FAR_SKILL`, and its bit in
; `temp`. Returns with 8-bit A.
.proc skill_point
.a8
.i16
    rep #$20
.a16
    lda temp + 2
    and #$0007
    tax
    sep #$20
.a8
    lda f:mask, x
    sta temp
    rep #$20
.a16
    lda temp + 2
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    rts
.endproc

; The parallel common events that only look at the equipment
; —`COMUNES_DEL_EQUIPO` in eventos.py; in the game, number 37, `UpdateAG7
; Skills`—, each run once if its switch is on. `menu_screen` calls it on
; closing, which is where the equipment changes: in RM2k they run every frame,
; but they only read their switch and the equipment, so between one menu close
; and the next they would give the same result. The other moment they change,
; their switch turning on, does not go through here: the converter pastes the
; body after the `ControlSwitches`.
;
; They run through `run_code`, as one more parallel event, with the
; interpreter's context saved and restored as in `parallel_tick`; their body
; neither waits nor opens messages, so it finishes within the same call. It
; must be entered with the data bank at 0, which is where `switches` and the
; interpreter keep their things.
.proc equipment_commons
.a8
.i16
    ldx #0
otro:
    cpx #COMEQ_N
    bcc hay
    rtl
hay:
    phx
    lda f:comeq_mask, x
    sta temp
    rep #$20
.a16
    txa
    asl a
    tax                         ; times two: the word tables
    lda f:comeq_byte, x
    tay
    sep #$20
.a8
    lda switches, y
    and temp
    beq apagado
    rep #$20
.a16
    lda ev_cur
    pha
    lda ev_waiting
    pha
    lda ev_running
    pha
    lda code_ptr
    pha
    lda f:comeq_code, x
    sta code_ptr
    stz ev_cur
    sep #$20
.a8
    lda code_ptr + 2
    pha
    lda ev_active
    pha
    lda pair_ev
    pha
    lda f:comeq_bank, x
    sta code_ptr + 2
    lda #1
    sta ev_active
    lda #$FF
    sta pair_ev                  ; neither a map's parallel event nor a
                                ; battle page
    jsl f:run_code_long
    pla
    sta pair_ev
    pla
    sta ev_active
    pla
    sta code_ptr + 2
    rep #$20
.a16
    pla
    sta code_ptr
    pla
    sta ev_running
    pla
    sta ev_waiting
    pla
    sta ev_cur
    sep #$20
.a8
apagado:
    plx
    inx
    bra otro
.endproc

; The skill bits set to what the LDB says each actor knows at their initial
; level: the converter's `skill_initial` table copied into `FAR_SKILL`. It runs at
; reset, before loading the saved game, which overwrites it. It is few bytes
; and goes one at a time: a DMA would cost more code than the loop.
.proc initial_skills_set
.a8
.i16
    ldx #0
otro:
    lda f:skill_initial, x
    sta f:FAR_LENGTH + FAR_SKILL, x
    inx
    cpx #SKILL_BYTES
    bne otro
    rtl
.endproc
