.segment "FAR"

; --- level and maximum in the menu ---------------------------------------------
;
; Until 2026-09-21 both were cartridge strips, composed at conversion time with
; the starting level: they never changed, so nothing more was needed. Since
; leveling up exists, they are composed here in `EXP_TEXT` with the same
; thing they used to say —`level_text` and
; `max_text` of `rm2k-snes-screens`— and the menu writes them with
; `slot_text_write` as before: all that changes is where `msg_ptr`
; points. With the starting level they give exactly the same letters as the
; strips, which is what keeps the menu goldens still.
;
; All three enter with the actor in A, leave `msg_ptr` pointing at the text and
; **leave Y as it was**, which is the cell where the caller is going to write.
; An actor without an experience slot keeps its cartridge strip.

; A16 —less than a thousand— into three digits from 0 to 9, at
; `EXP_TEXT + 5`, `+ 6` and `+ 7`. Clobbers A and X; enters and leaves with a
; 16-bit A.
.proc three_digits
.a16
.i16
    ldx #0
hundreds:
    cmp #100
    bcc has_hundreds
    sbc #100                    ; C comes from the comparison
    inx
    bra hundreds
has_hundreds:
    pha
    txa
    sep #$20
.a8
    sta f:EXP_TEXT + 5
    rep #$20
.a16
    pla
    ldx #0
tens:
    cmp #10
    bcc units
    sbc #10
    inx
    bra tens
units:
    sep #$20
.a8
    sta f:EXP_TEXT + 7
    txa
    sta f:EXP_TEXT + 6
    rep #$20
.a16
    rts
.endproc

; `msg_ptr` to actor A's cartridge strip, offset by X bytes: the same as bank
; 0's `slot_text_of`, for those with no slot. Clobbers A.
.proc cartridge_strip
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; SLOT_TEXT_WIDTH bytes per actor
    sta msg_ptr
    txa
    clc
    adc msg_ptr
    clc
    adc #.loword(slot_actor_text)
    sta msg_ptr
    sep #$20
.a8
    lda #^slot_actor_text
    sta msg_ptr + 2
    rtl
.endproc

; `msg_ptr` to `EXP_TEXT`.
.proc point_text
.a8
.i16
    rep #$20
.a16
    lda #.loword(EXP_TEXT)
    sta msg_ptr
    sep #$20
.a8
    lda #^EXP_TEXT
    sta msg_ptr + 2
    rtl
.endproc

; Level A8 as "%2d" in `EXP_TEXT`: the tens digit or a space, and the units.
.proc level_to_text
.a8
.i16
    rep #$20
.a16
    and #$00FF
    jsr three_digits
    sep #$20
.a8
    lda f:EXP_TEXT + 6
    beq no_tens
    ora #'0'
    bra tens
no_tens:
    lda #' '
tens:
    sta f:EXP_TEXT
    lda f:EXP_TEXT + 7
    ora #'0'
    sta f:EXP_TEXT + 1
    rts
.endproc

; Actor A's current level.
.proc text_level
.a8
.i16
    pha
    jsr actor_level_of
    cmp #$FF
    bne has
    pla
    ldx #SLOT_TEXT_LEVEL
    jmp cartridge_strip
has:
    jsr level_to_text
    pla
    jmp point_text
.endproc

EXP_LEVEL_IN_SLOT = SRAM_DATA + SAVE_BYTES - EXP_K * 4 + EXP_LEVEL

; The level actor A had **in the saved game in slot `slot`**, read from its
; SRAM: the slots screen shows each save as it was left, not as the current
; one is. `FAR_EXP` is the last line of `save_table`, so in the slot it
; falls `EXP_K * 4` bytes before the end; and the slot is a bank of its own,
; see `SRAM_STRIDE`.
.proc text_level_saved
.a8
.i16
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne has
    pla
    ldx #SLOT_TEXT_LEVEL
    jmp cartridge_strip
has:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax                         ; the experience slot times four
    sep #$20
.a8
    phb
    lda slot
    clc
    adc #SRAM_BANK
    pha
    plb
    lda EXP_LEVEL_IN_SLOT, x    ; the data bank is the slot's: absolute
    plb
    jsr level_to_text
    pla
    jmp point_text
.endproc

; The maximum HP for actor A's current level, as "/%d" padded to
; `MENU_MAX_DIGITS` with spaces: the screens stage's `max_text`.
.proc text_max
.a8
.i16
    pha
    jsr actor_level_of
    cmp #$FF
    bne has
    pla
    ldx #SLOT_TEXT_MAX
    jmp cartridge_strip
has:
    pla
    phy
    ldy #0
    jsl f:level_param
    rep #$20
.a16
    txa
    jsr three_digits
    sep #$20
.a8
    ldx #0
    lda #'/'
    sta f:EXP_TEXT, x
    inx
    lda f:EXP_TEXT + 5
    beq no_hundreds
    ora #'0'
    sta f:EXP_TEXT, x
    inx
    lda f:EXP_TEXT + 6
    bra with_tens               ; with hundreds the tens digit goes in even if zero
no_hundreds:
    lda f:EXP_TEXT + 6
    beq no_tens
with_tens:
    ora #'0'
    sta f:EXP_TEXT, x
    inx
no_tens:
    lda f:EXP_TEXT + 7
    ora #'0'
    sta f:EXP_TEXT, x
    inx
padding:
    cpx #MENU_MAX_DIGITS
    bcs full
    lda #' '
    sta f:EXP_TEXT, x
    inx
    bra padding
full:
    ply
    jmp point_text
.endproc

; An actor's current HP, in its row of the party panel: three right-aligned
; digits and whatever is left over on the left, blank. `temp` carries the
; actor's LDB number and `temp + 2` the row; clobbers A, X, Y and `temp`.
;
; **This exists because the row's block is baked at conversion time.** Until
; 2026-09-13 the HP went inside that block, so the menu always showed the
; level's maximum no matter how much the battle lowered them: it is what taro
; reported while playing —"en el menú siempre se muestra en 40" ("in the menu
; it always shows 40"), which is Talan's maximum—. The maximum and the bar are
; still baked, since those do not change.
;
; The digits are the same glyphs as the gold —`slot_glyph_cells`, one per
; cell— and they line up without touching anything because both lines are
; drawn two pixels from the top edge of their cell. The screens stage's
; `actor_row` is the reference, with the same columns.
;
; It lives outside bank 0 for the same reason as `hp_initial_set`: there are
; tens of bytes left there and this is over a hundred. It is entered with
; `jsl` and with the data bank at 0 —the menu runs that way— but it sets it
; anyway, because everything it touches —`temp`, the `TABLES` tables and the
; PPU registers— is bank 0 absolute, and depending on the caller for that has
; already cost one bug in this repo.
.proc menu_hp_write
.a8
.i16
    phb
    lda #0
    pha
    plb
    ; The units cell: the first of the row's block, plus the offset the
    ; converter emits, plus the digits that go to the left.
    rep #$20
.a16
    lda temp + 2
    and #$00FF
    asl a
    tax
    lda menu_row_vram, x
    clc
    adc #(MENU_HP_OFS + MENU_HP_DIGITS - 1)
    tay
    ; And the HP, from far RAM. An actor with more than 999 would show its
    ; three lowest digits; nobody in the game gets there.
    lda temp
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    sta temp
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #MENU_HP_DIGITS
    sta temp + 3
digit:
    rep #$20
.a16
    lda temp
    sta WRDIVL                  ; the dividend, 16 bits
    sep #$20
.a8
    lda #10
    sta WRDIVB                  ; starts it: the quotient takes sixteen cycles
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
    lda RDDIVL
    sta temp
    lda RDMPYL                  ; the remainder, which is the digit
    and #$00FF
    asl a
    asl a                       ; two words per digit
    tax
    sty VMADDL
    lda f:slot_glyph_cells + GLYPH_DIGIT_0, x
    sta VMDATAL
    tya
    clc
    adc #32                     ; the lower cell
    sta VMADDL
    lda f:slot_glyph_cells + GLYPH_DIGIT_0 + 2, x
    sta VMDATAL
    sep #$20
.a8
    dey
    dec temp + 3
    beq ready
    lda temp
    ora temp + 1
    bne digit
    ; What is left on the left, blank: cell 0, which in the actor's block is
    ; the one already under the digits.
target:
    rep #$20
.a16
    sty VMADDL
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    dey
    dec temp + 3
    bne target
ready:
    plb
    rtl
.endproc

; Actor A's current level, in A: the fourth byte of its `FAR_EXP` slot. An
; actor with no slot answers $FF, and the one asking knows that for that actor
; the cartridge's value holds, which is its starting level forever. Clobbers
; X; reads with `f:`, so the data bank does not matter.
.proc actor_level_of
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    beq ready
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + EXP_LEVEL, x
ready:
    rts
.endproc

; Parameter Y of an actor **at its current level**: `GetBaseMaxHp` and its
; siblings, without the equipment —`eq_parameter` adds that—, with what the
; materials added —`FAR_GROWTH`, the `*_mod`— and clamped as RM2k clamps it:
; from 1 to 999, and the SP from 0. Y is the order of `lcf.CURVES`: 0 HP, 1
; SP, 2 attack, 3 defense, 4 spirit and 5 agility.
;
; Enters with the actor in A and returns the value in X. **Clobbers A and Y**,
; and does not touch the direct page: its callers —the equipment screen, the
; battle, `FullHeal`— each have it busy with something else, so the arithmetic
; goes through the stack. Everything it reads goes with `f:`, so the data bank
; does not matter.
;
; An actor with no experience slot —one that cannot join the party— never
; levels up, and its values come from the tables for its initial level, which
; are the usual ones.
.proc level_param
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    beq no_slot
    rep #$20
.a16
    and #$00FF
    pha                         ; the slot
    asl a
    asl a
    tax
    lda f:FAR_LENGTH + FAR_EXP + 2, x   ; the high byte is the level
    xba
    and #$00FF
    dec a
    asl a
    pha                         ; (level - 1) * 2, with the slot below it
    lda 3, s
    asl a
    adc 3, s                    ; the slot times three: the `asl` left C clear
    asl a
    sta 3, s                    ; and times six, which is its first row
    tya
    clc
    adc 3, s
    asl a
    tax
    lda f:level_row, x
    clc
    adc 1, s
    tax
    lda f:level_params, x
    ; And what the materials added, from the slot's row of `FAR_GROWTH`,
    ; which is the slot times twelve: twice its first row of the table.
    pha                         ; stack = value, (level - 1) * 2, slot * 6
    tya
    clc
    adc 5, s
    asl a
    tax
    pla
    clc
    adc f:FAR_GROWTH, x
    bmi low
    cmp #(GROWTH_MAX + 1)
    bcc high_ok
    lda #GROWTH_MAX
    bra high_ok
low:
    lda #0
high_ok:
    cmp #1
    bcs clamped
    cpy #1
    beq clamped                 ; the SP can be zero
    lda #1
clamped:
    tax
    pla
    pla
    sep #$20
.a8
    rtl
no_slot:
    rep #$20
.a16
    txa
    asl a
    tax                         ; the actor times two
    cpy #2
    bcs from_four
    cpy #1
    beq sp
    lda f:actor_hpmax, x
    bra ready
sp:
    lda f:actor_spmax, x
    bra ready
from_four:
    txa
    asl a
    asl a                       ; the actor times eight: four words each
    pha
    tya
    asl a
    clc
    adc 1, s
    tax
    pla
    lda f:actor_params - 4, x   ; `actor_params` starts at attack, number 2
ready:
    tax
    sep #$20
.a8
    rtl
.endproc

; Every actor's HP full, into `FAR_HP`: the same DMA as the equipment, from
; `actor_hpmax`. Runs at reset, before loading the saved game, which
; overwrites it.
;
; It lives **outside bank 0** —it is called with `jsl`— and that is why its
; registers go with `f:`: bank 0 had seventy bytes free and this is forty. It
; is the same reason the whole battle lives over there.
;
; It exists since there are battles. Until 2026-09-12 HP were not state —the
; menu always showed them full and `ChangeHP` compiled to nothing— and now a
; battle lowers them, so they have to start somewhere and travel in the saved
; game. Starting full is RM2k: `Game_Actor::Setup`.
;
; Since 2026-09-13 it does the same with SP, which are state for the same
; reason: a skill costs its `sp_cost`. It is two identical DMAs and not a loop
; because writing it twice costs less than a loop with a table, and this lives
; in RODATA, where the cartridge has room to spare.
.proc hp_initial_set
.a8
.i16
    rep #$20
.a16
    lda #FAR_HP
    sta f:WMADDL
    lda #<(actor_hpmax)
    ora #(>(actor_hpmax) * 256)
    sta f:A1T0L
    lda #(ACTORS_N * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(actor_hpmax)
    sta f:A1B0
    lda #0
    sta f:DMAP0                 ; A to B, one byte at a time
    lda #$80                    ; WMDATA
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    ; and the SP, from `actor_spmax`
    rep #$20
.a16
    lda #FAR_SP
    sta f:WMADDL
    lda #<(actor_spmax)
    ora #(>(actor_spmax) * 256)
    sta f:A1T0L
    lda #(ACTORS_N * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(actor_spmax)
    sta f:A1B0
    lda #0
    sta f:DMAP0
    lda #$80
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    ; and the experience and level, from `exp_initial`: `Game_Actor` starts
    ; at `initial_level` with exactly the experience for that level.
    rep #$20
.a16
    lda #FAR_EXP
    sta f:WMADDL
    lda #<(exp_initial)
    ora #(>(exp_initial) * 256)
    sta f:A1T0L
    lda #(EXP_K * 4)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(exp_initial)
    sta f:A1B0
    lda #0
    sta f:DMAP0
    lda #$80
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    ; And nothing added by a material yet: see `FAR_GROWTH`.
    rep #$20
.a16
    lda #0
    ldx #0
no_growth:
    sta f:FAR_GROWTH, x
    inx
    inx
    cpx #(EXP_K * GROWTH_BYTES)
    bcc no_growth
    sep #$20
.a8
    rtl
.endproc

; `FullHeal`, and `ChangeHP` when it adds: both are OP_HEAL, and the amount
; tells them apart. At 0 it is `FullHeal`: the HP and SP of each actor in the
; target to their maximums. It is easyrpg's `Game_Actor::FullHeal`
; (`game_actor.cpp:391`), which also does `RemoveAllStates` and restores the
; equipment's states: here there is none of that to clear, because outside
; battle states do not exist —the battle builds them and throws them away—
; and a fallen actor is just an actor with zero HP, so filling them already
; revives it. With an amount it is `ChangeHP`; see `heal_actor`.
;
; Entered from `op_heal` with Y on the operand: the actor, or 0 for the whole
; party —the `GetActors` of `game_interpreter.cpp:1539`, see `target_actor`
; in the event compiler— and the amount, 16 bits. Returns with Y after it. It lives
; **outside bank 0** for the same reason as `hp_initial_set`, and that is
; why everything it touches goes with `f:` or is in the direct page. Clobbers
; A, X and `temp`.
;
; It does not reuse `hp_initial_set` on purpose: that one fills all 61
; actors at once, and `FullHeal [0, 0]` is the party and nobody else.
; `test_full_heal_of_the_party_does_not_heal_those_outside` catches it.
.proc heal
.a8
.i16
    lda [code_ptr], y           ; the actor
    iny
    sta temp + 2
    rep #$20
.a16
    lda [code_ptr], y           ; and the amount
    sta temp
    sep #$20
.a8
    iny
    iny
    phy
    lda temp + 2
    bne one
    ; Up to `party_n` and not all four slots: the extra ones are not cleared
    ; when someone is removed, and in the test suite one showed up with 85
    ; —healing it meant writing into actor 21's SP—.
    ldx #0
slot:
    cpx party_n
    bcs ready
    lda party, x
    phx
    jsr heal_actor
    plx
    inx
    bra slot
ready:
    ply
    rtl
one:
    jsr heal_actor
    ply
    rtl
.endproc

; Actor A: to its maximums with `temp` at 0, or `temp` more HP. Clobbers X
; and Y.
;
; The second is `Game_Battler::ChangeHp` (`game_battler.cpp:480`): it does not
; touch a fallen actor —there it is `IsDead`, here zero HP, which outside
; battle is the same— and whatever goes past the maximum is capped, which is
; the `SetHp` inside. Not the SP.
;
; The maximums are those of its current level, `level_param`, and they live on
; the stack meanwhile: `temp` is the amount and `temp + 2` the actor from
; `heal`.
.proc heal_actor
.a8
.i16
    pha                         ; the actor
    ldy #0
    jsl f:level_param
    phx                         ; the maximum HP
    lda 3, s
    ldy #1
    jsl f:level_param
    phx                         ; and the SP: stack = SP, HP, actor
    lda 5, s
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda temp
    bne add
    lda 3, s
    sta f:FAR_LENGTH + FAR_HP, x
    lda 1, s
    sta f:FAR_LENGTH + FAR_SP, x
    bra ready
add:
    lda f:FAR_LENGTH + FAR_HP, x
    beq ready                   ; fallen: `ChangeHp` does not revive it
    clc
    adc temp
    bcs cap                     ; it wrapped around: the amount reaches $FFFF
    cmp 3, s
    bcc put
cap:
    lda 3, s
put:
    sta f:FAR_LENGTH + FAR_HP, x
ready:
    pla
    pla
    sep #$20
.a8
    pla
    rts
.endproc

; `ChangeHP` in the forms `FullHeal` does not share —subtracting, or by a
; variable—, `ChangeSP`, and the `ChangeCondition` that removes the death
; state: OP_ACTOR, since 2026-09-30. The characters' systems hurt Talan and
; get the party back up from a troop page, and `ResetAfterBattles` gives
; Talan back the HP and SP he had before its `FullHeal`.
;
; `what` says which: the SP and not the HP (`ACT_SP`), getting a fallen one
; up with 1 HP and nothing else (`ACT_REVIVE`, the `SetHp(1)` of
; `RemoveStates`), equipping (`ACT_EQUIP`, see `actor_equip`), the amount as
; a variable's slot (`ACT_VARIABLE`), a loss of HP that can kill
; (`ACT_LETHAL`) and subtracting (`ACT_SUBTRACT`). The compiler writes them
; with the same numbers: `ACT_*` in its `compile.rs`.
; In a battle it lands on the battle's HP, because `ba_page_step` copies
; them here before the page and back after it: see `ba_sync_out`.
;
; Like `heal`: entered from `op_actor` with Y on the operands, returns with Y
; after them, lives outside bank 0 and walks `party` for actor 0. Clobbers
; A, X and `temp`.
ACT_SP       = $01
ACT_REVIVE   = $02
ACT_EQUIP    = $04
ACT_VARIABLE = $20
ACT_LETHAL   = $40
ACT_SUBTRACT = $80
.proc actor_change
.a8
.i16
    lda [code_ptr], y           ; the actor, 0 the whole party
    iny
    sta temp + 2
    lda [code_ptr], y           ; what
    iny
    sta temp + 3
    rep #$20
.a16
    lda [code_ptr], y           ; the amount, or the variable's slot
    iny
    iny
    sta temp
    sep #$20
.a8
    phy
    lda temp + 3
    and #ACT_VARIABLE
    beq constant
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    sta temp
    sep #$20
.a8
constant:
    lda temp + 3
    bpl adds
    rep #$20
.a16
    lda #0
    sec
    sbc temp
    sta temp                    ; the change, signed
    sep #$20
.a8
adds:
    lda temp + 2
    bne one
    ldx #0
slot:
    cpx party_n
    bcs ready
    lda party, x
    phx
    jsr actor_change_one
    plx
    inx
    bra slot
ready:
    ply
    rtl
one:
    jsr actor_change_one
    ply
    rtl
.endproc

; Actor A, by the signed change in `temp` and the bits in `temp + 3`. The HP
; is `Game_Battler::ChangeHp`: a fallen one does not change, it does not go
; past the maximum of its level and a loss that is not lethal leaves it at 1.
; The SP is `SetSp`, between zero and its maximum. Clobbers X and Y.
.proc actor_change_one
.a8
.i16
    pha                         ; the actor
    lda temp + 3
    and #ACT_EQUIP
    beq not_equip
    pla
    jmp actor_equip
not_equip:
    ldy #0                      ; `level_param`'s HP
    lda temp + 3
    and #ACT_SP
    beq which
    iny                         ; or its SP
which:
    lda 1, s
    jsl f:level_param
    phx                         ; its maximum: stack = maximum, actor
    lda 3, s
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    sep #$20
.a8
    lda temp + 3
    and #ACT_REVIVE
    bne revive
    lda temp + 3
    and #ACT_SP
    bne sp
    rep #$20
.a16
    lda f:FAR_LENGTH + FAR_HP, x
    beq ready                   ; fallen: `ChangeHp` does nothing to it
    clc
    adc temp
    bmi down
    beq down
    cmp 1, s
    bcc put_hp
    lda 1, s
put_hp:
    sta f:FAR_LENGTH + FAR_HP, x
    bra ready
down:
    lda temp + 2                ; with `what` in the high byte
    and #(ACT_LETHAL * 256)
    beq one_left                ; `std::max(1, ...)` when it is not lethal
    lda #0
    bra put_hp
one_left:
    lda #1
    bra put_hp
.a8
revive:
    rep #$20
.a16
    lda f:FAR_LENGTH + FAR_HP, x
    bne ready                   ; standing: there is no death to remove
    lda #1
    bra put_hp
.a8
sp:
    rep #$20
.a16
    lda f:FAR_LENGTH + FAR_SP, x
    clc
    adc temp
    bpl sp_positive
    lda #0
sp_positive:
    cmp 1, s
    bcc put_sp
    lda 1, s
put_sp:
    sta f:FAR_LENGTH + FAR_SP, x
ready:
    pla                         ; the maximum
    sep #$20
.a8
    pla                         ; the actor
    rts
.endproc

; `ChangeEquipment` that equips, for actor A: the item in the low thirteen
; bits of `temp` and its slot, 0 to 4, in the top three —the compiler knows
; the item's type and the ROM does not carry every item's—. It is
; `Game_Actor::ChangeEquipment`: the item goes into the slot, what was there
; goes back to the inventory, capped at ITEM_MAX, and then one of the new one
; comes out of it, if there is one. In that order: re-equipping what it
; already had leaves the inventory as it was. The compiler only lets through
; armor, helmet and accessory, which have none of the weapons' two-handed
; business, and one the actor can use. In a battle the parameters it changes
; are taken up by `ba_sync_in`. Clobbers X.
.proc actor_equip
.a8
.i16
    rep #$20
.a16
    and #$00FF
    pha                         ; the actor
    asl a
    asl a
    clc
    adc 1, s
    asl a                       ; times ten, which is what a row measures
    sta 1, s
    lda temp
    xba
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; the slot, from the top three bits
    and #$0007
    asl a                       ; the slot is a word
    clc
    adc 1, s
    tax
    pla
    lda f:FAR_LENGTH + FAR_EQUIPMENT, x
    pha                         ; what it had
    lda temp
    and #$1FFF
    sta f:FAR_LENGTH + FAR_EQUIPMENT, x
    pla
    ; goombario: pull-branch: what that slot had equipped: 0 is that it had
    ; nothing
    beq taken
    cmp #ITEMS_N
    bcs taken                   ; an item the inventory does not carry
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs taken8
    inc a
    sta f:FAR_LENGTH + FAR_ITEMS, x
taken8:
    rep #$20
.a16
taken:
    lda temp
    and #$1FFF
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_ITEMS, x
    beq none                    ; `RemoveItem` does not go below zero
    dec a
    sta f:FAR_LENGTH + FAR_ITEMS, x
none:
    rts
.endproc

; The first of the `ControlVariables::Actor` numbers `actor_stat` does.
ACTOR_STAT_HP = 2

; `ControlVars` with an actor's data, class 5, for `op_var`: Y on its `a`
; —the actor— with `b` —which one— after it, with `ControlVariables::Actor`'s
; numbers. Here, the four A Blurred Line asks for: 2 the HP, 3 the SP, 4 and
; 5 their maximums. The first two are the saved game's —in battle, the
; battle's, through `ba_sync_out`—; the maximums, those of its current
; level, like `GetMaxHp` without equipment. The other eleven —the level, the
; experience, the four parameters with the equipment and the five equipped
; items— go to `actor_stat_other`, in actor_stats.s, which lives in `FAR3`
; because this bank was nearly full when they came (2026-10-16). Returns the
; value in A16 **with the accumulator at sixteen bits**, and Y as it came.
; Clobbers X.
.proc actor_stat
.a8
.i16
    phy
    rep #$20
.a16
    lda [code_ptr], y           ; the actor
    and #$00FF
    pha
    iny
    iny
    lda [code_ptr], y           ; and which one
    sec
    sbc #ACTOR_STAT_HP
    cmp #2
    bcc hp_or_sp
    cmp #4
    bcc maximum
    ; The level and the experience come out as $FFFE and $FFFF, above
    ; everything; the parameters and the equipment as 4 to 12. The stack is
    ; this routine's —the actor, then Y— and the other one undoes it.
    jml f:actor_stat_other
hp_or_sp:
    tax                         ; 0 the HP, 1 the SP
    pla
    asl a
    cpx #0
    beq hp
    clc
    adc #(FAR_SP - FAR_HP)
hp:
    tax
    lda f:FAR_LENGTH + FAR_HP, x
    ply
    rtl
maximum:
    dec a
    dec a
    tay                         ; 0 the HP, 1 the SP: `level_param`'s order
    pla
    sep #$20
.a8
    jsl f:level_param
    rep #$20
.a16
    txa
    ply
    rtl
.endproc

; `Game_Actor::ChangeExp(GetExp() + BA_T1)` for actor A: adds, caps at
; `MaxExpValue()` and levels up while it is enough. An actor with no
; experience slot gains nothing. Runs with the data bank at $7E, like the
; whole battle. Clobbers A, X, Y, `BA_T0` and `BA_T2`; `BA_T1` stays as it
; was, so whoever hands it out can add it to several. With `jsl`: the battle
; that calls it lives in `FAR2`.
;
; And for each level gained, `LearnLevelSkills` for that level: see
; `learn_from_level`.
.proc exp_add
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne has
    rtl
has:
    phx                         ; the actor, for what it learns on leveling up
    rep #$20
.a16
    and #$00FF
    sta BA_T2                   ; the slot
    asl a
    asl a
    sta BA_T0                   ; and its offset in `FAR_EXP`
    tax
    lda FAR_EXP, x
    clc
    adc BA_T1
    sta FAR_EXP, x
    sep #$20
.a8
    lda FAR_EXP + 2, x          ; the carry from the addition above is still in C
    adc #0
    sta FAR_EXP + 2, x
    cmp #EXP_CAP_HI
    bcc no_cap
    bne cap
    rep #$20
.a16
    lda FAR_EXP, x
    cmp #(EXP_CAP_LO + 1)
    sep #$20
.a8
    bcc no_cap
cap:
    rep #$20
.a16
    lda #EXP_CAP_LO
    sta FAR_EXP, x
    sep #$20
.a8
    lda #EXP_CAP_HI
    sta FAR_EXP + 2, x
no_cap:
    ; And it levels up while it is enough: the `ChangeExp` loop, which looks at
    ; `GetNextExp(level)` —row `level` of `exp_table`, what it takes to reach
    ; the next one— up to `GetMaxLevel()`. A battle can raise more than one
    ; level at once, and that is RM2k's. HP and SP are not touched: leveling
    ; up does not heal, it only raises the maximum.
upload:
    ldx BA_T2
    lda f:exp_level_max, x
    ldx BA_T0
    cmp FAR_EXP + EXP_LEVEL, x
    beq ready                   ; at the cap
    bcc ready                   ; above the cap: does not happen, but no level up
    lda FAR_EXP + EXP_LEVEL, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    pha                         ; the level times four: its row in the curve
    lda BA_T2
    asl a
    tax
    lda f:exp_curve, x
    clc
    adc 1, s
    tax
    pla
    ; What it takes, in two halves: the low one to the stack —all three
    ; `BA_T*` are in use— and the high one in A.
    lda f:exp_table, x
    pha
    lda f:exp_table + 2, x
    ldx BA_T0
    sep #$20
.a8
    cmp FAR_EXP + 2, x          ; the high byte first
    bne height_different
    rep #$20
.a16
    lda FAR_EXP, x
    cmp 1, s                    ; C if the experience is enough
    sep #$20
.a8
    ply                         ; `ply` does not touch C
    bcc ready
    bra uploads
height_different:
    ply
    bcs ready                   ; C: the high byte required is more than there is
uploads:
    inc FAR_EXP + EXP_LEVEL, x
    lda FAR_EXP + EXP_LEVEL, x
    ply                         ; the actor, without taking it off the stack
    phy
    jsr learn_from_level
    bra upload
ready:
    plx
    rtl
.endproc

; `LearnLevelSkills` for a single level, A, for actor Y: sets in `FAR_SKILL` the
; bit of each of its pairs that the LDB's learning table teaches at that level
; —`skill_pair_level`—. If it already knew it nothing changes, which is
; `LearnSkill`; and what a `ChangeSkills` made it forget comes back only if it
; is taught at a level just reached, as in RM2k. Runs in battle, but
; everything it touches goes with `f:` or through the stack. Clobbers A, X
; and Y.
.proc learn_from_level
.a8
.i16
    pha                         ; the level
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:skill_pair_init, x
    pha                         ; the slot of the pair being looked at: stack = slot, level
    tyx
    lda f:skill_pair_n, x
    and #$00FF
    beq end
    tay                         ; how many pairs it has left
other:
    lda 1, s
    tax
    sep #$20
.a8
    lda f:skill_pair_level, x
    cmp 3, s
    bne next
    rep #$20
.a16
    txa
    and #$0007
    tax
    sep #$20
.a8
    lda f:mask, x
    pha                         ; its bit: stack = bit, slot, level
    rep #$20
.a16
    lda 2, s
    lsr a
    lsr a
    lsr a
    tax
    sep #$20
.a8
    pla
    ora f:FAR_LENGTH + FAR_SKILL, x
    sta f:FAR_LENGTH + FAR_SKILL, x
next:
    rep #$20
.a16
    lda 1, s
    inc a
    sta 1, s
    dey
    bne other
end:
    pla
    sep #$20
.a8
    pla
    rts
.endproc

; --- `ChangeExp` and `ChangeLevel` from an event ----------------------------
;
; OP_EXP, since 2026-10-04: easyrpg's `CommandChangeExp` and
; `CommandChangeLevel`, which are `Game_Actor::ChangeExp(GetExp() + value)`
; and `ChangeLevel(GetLevel() + value)` on each actor of the target. Going up
; it learns what the levels it went through teach, as `exp_add` does after a
; battle; going down it forgets nothing, and the experience drops to the new
; level's base only if it had reached the next one. Either way, `SetLevel`
; leaves no HP nor SP above the new level's maximum.
;
; With `EXP_WITH_MESSAGE` it also notes the lines of the level-up message
; —see `LVL` in far_ram.s— for the `OP_LEVEL_PAGE` the compiler puts right
; behind: `level_page`, further down.
;
; `what` carries bits, which the compiler writes with the same numbers:
; `EXP_*` in its `compile.rs`.
EXP_BY_LEVELS    = $01
EXP_WITH_MESSAGE = $02
EXP_BY_VARIABLE  = $20
EXP_SUBTRACTS    = $80

; Entered from `op_exp` with Y on the operands —the actor, 0 the whole
; party; `what`; the amount, 24 bits, or the variable's slot in its low
; byte— and returns with Y after them. Runs with the data bank at $7E, like
; `exp_add`, so the far RAM goes with sixteen-bit addresses and the
; cartridge's tables with `f:`. Clobbers A, X and the `LVL_*`.
.proc exp_change
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    lda [code_ptr], y           ; the actor, 0 the whole party
    iny
    pha
    lda [code_ptr], y           ; what
    iny
    sta LVL_WHAT
    rep #$20
.a16
    lda [code_ptr], y           ; the amount, or the variable's slot
    sta LVL_AMOUNT
    iny
    iny
    sep #$20
.a8
    lda [code_ptr], y
    iny
    sta LVL_AMOUNT + 2
    stz LVL_AMOUNT + 3
    phy                         ; stack = cursor, target
    lda LVL_WHAT
    and #EXP_BY_VARIABLE
    beq constant
    ; A variable is sixteen bits and signed, and `OperateValue` takes it as
    ; it is: a negative one that adds takes away.
    rep #$20
.a16
    lda LVL_AMOUNT
    and #$00FF
    asl a
    tax
    lda FAR_VARIABLES, x
    sta LVL_AMOUNT
    bpl positive                ; the `lda`'s N: `sta` does not touch it
    lda #$FFFF
    bra extended
positive:
    lda #0
extended:
    sta LVL_AMOUNT + 2
    sep #$20
.a8
constant:
    lda LVL_WHAT
    bpl adds                    ; EXP_SUBTRACTS is bit 7
    rep #$20
.a16
    lda #0
    sec
    sbc LVL_AMOUNT
    sta LVL_AMOUNT
    lda #0
    sbc LVL_AMOUNT + 2
    sta LVL_AMOUNT + 2
    sep #$20
.a8
adds:
    ; No lines yet, with a message or without: that way `level_page` never
    ; reads what an earlier one left, nor the WRAM's garbage.
    stz LVL_N
    stz LVL_AT
    lda 3, s                    ; the target
    bne one
    ; Up to `party_n`, like `heal`: the slots past it are not cleared.
    ldx #0
slot:
    cpx party_n
    bcs ready
    lda party, x
    phx
    jsr exp_one
    plx
    inx
    bra slot
one:
    jsr exp_one
ready:
    ply
    pla
    plb
    rtl
.endproc

; OP_EXP's change on actor A8. One with no experience slot —one that can
; never be in the party— changes nothing. Clobbers A, X and Y.
.proc exp_one
.a8
.i16
    sta LVL_ACTOR
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x
    cmp #$FF
    bne has
    rts
has:
    rep #$20
.a16
    and #$00FF
    sta LVL_K
    asl a
    asl a
    sta LVL_OFS
    tax
    sep #$20
.a8
    lda FAR_EXP + EXP_LEVEL, x
    sta LVL_OLD
    sta LVL_NEW
    lda LVL_WHAT
    and #EXP_BY_LEVELS
    bne by_levels
    jmp by_exp

by_levels:
    ; `ChangeLevel(GetLevel() + value)`, which `SetLevel` clamps between 1
    ; and `GetMaxLevel()`. The sum goes in 32 bits, because the value can be
    ; a variable's.
    rep #$20
.a16
    lda LVL_OLD
    and #$00FF
    clc
    adc LVL_AMOUNT
    sta LVL_VALUE
    lda #0
    adc LVL_AMOUNT + 2          ; the high word: negative, zero or more
    sep #$20                    ; `sep` does not touch the flags
.a8
    bmi to_one
    bne to_max
    lda LVL_VALUE + 1
    bne to_max                  ; 256 or more
    lda LVL_VALUE
    beq to_one
    ldx LVL_K
    cmp f:exp_level_max, x
    bcc chosen
to_max:
    ldx LVL_K
    lda f:exp_level_max, x
    bra chosen
to_one:
    lda #1
chosen:
    sta LVL_NEW
    cmp LVL_OLD
    beq same
    jmp set_level
same:
    rts

by_exp:
    ; `ChangeExp(GetExp() + value)`: the sum, in 32 bits, clamped between 0
    ; and `MaxExpValue()`.
    ldx LVL_OFS
    rep #$20
.a16
    lda FAR_EXP, x
    clc
    adc LVL_AMOUNT
    sta LVL_VALUE
    sep #$20
.a8
    lda FAR_EXP + 2, x
    adc LVL_AMOUNT + 2
    sta LVL_VALUE + 2
    lda #0
    adc LVL_AMOUNT + 3
    sta LVL_VALUE + 3
    bmi zero                    ; the `adc`'s N
    bne cap                     ; past 24 bits
    lda LVL_VALUE + 2
    cmp #EXP_CAP_HI
    bcc in_range
    bne cap
    rep #$20
.a16
    lda LVL_VALUE
    cmp #(EXP_CAP_LO + 1)
    sep #$20
.a8
    bcc in_range
cap:
    rep #$20
.a16
    lda #EXP_CAP_LO
    sta LVL_VALUE
    sep #$20
.a8
    lda #EXP_CAP_HI
    sta LVL_VALUE + 2
    bra in_range
zero:
    rep #$20
.a16
    stz LVL_VALUE
    sep #$20
.a8
    stz LVL_VALUE + 2
in_range:
    ; Up or down against what it had, which is easyrpg's `new_exp >
    ; GetExp()` and `new_exp < GetExp()`: equal, the level stays.
    ldx LVL_OFS
    lda LVL_VALUE + 2
    cmp FAR_EXP + 2, x
    bne compared
    rep #$20
.a16
    lda LVL_VALUE
    cmp FAR_EXP, x
    sep #$20
.a8
compared:
    beq store
    bcc down
up:
    ; Up while it reaches the next level's, and not past the cap.
    ldx LVL_K
    lda LVL_NEW
    cmp f:exp_level_max, x
    bcs store
    jsr exp_row                 ; `GetNextExp(level)`
    jsr exp_reaches
    bcc store
    inc LVL_NEW
    bra up
down:
    ; Down while it does not reach the current level's, and not below 1.
    lda LVL_NEW
    cmp #2
    bcc store
    dec a
    jsr exp_row                 ; `GetNextExp(level - 1)`
    jsr exp_reaches
    bcs store
    dec LVL_NEW
    bra down
store:
    ldx LVL_OFS
    rep #$20
.a16
    lda LVL_VALUE
    sta FAR_EXP, x
    sep #$20
.a8
    lda LVL_VALUE + 2
    sta FAR_EXP + 2, x
    lda LVL_NEW
    cmp LVL_OLD
    bne set_level
    rts

set_level:
    ; `ChangeLevel(LVL_NEW)`: the level, and what going up or down does.
    ldx LVL_OFS
    lda LVL_NEW
    sta FAR_EXP + EXP_LEVEL, x
    rep #$20
.a16
    lda FAR_EXP, x
    sta LVL_VALUE
    sep #$20
.a8
    lda FAR_EXP + 2, x
    sta LVL_VALUE + 2
    lda LVL_NEW
    cmp LVL_OLD
    bcc lower
    ; Going up: its line, if there is a message, then what the levels it
    ; went through teach, and the experience up to the new level's base if
    ; it was below.
    xba
    lda LVL_ACTOR
    rep #$20
.a16
    ora #$8000                  ; `$8000 | level << 8 | actor`
    jsr exp_note
    sep #$20
.a8
    jsr exp_learn
    lda LVL_NEW
    dec a
    jsr exp_row                 ; `GetBaseExp()`
    jsr exp_reaches
    bcs clamp
    jsr exp_put_row
    bra clamp
lower:
    ; Going down: the new level's base, if it had the next one's.
    jsr exp_row                 ; `GetNextExp()`, the new level's row
    jsr exp_reaches
    bcc clamp
    lda LVL_NEW
    dec a
    jsr exp_row
    jsr exp_put_row
clamp:
    ; And `SetLevel`'s `SetHp(GetHp())` and `SetSp(GetSp())`: neither stays
    ; above the maximum of the level it is at now.
    lda LVL_ACTOR
    ldy #0
    jsl f:level_param
    stx LVL_T
    rep #$20
.a16
    lda LVL_ACTOR
    and #$00FF
    asl a
    tax
    lda LVL_T
    cmp FAR_HP, x
    bcs hp_fits
    sta FAR_HP, x
hp_fits:
    sep #$20
.a8
    lda LVL_ACTOR
    ldy #1
    jsl f:level_param
    stx LVL_T
    rep #$20
.a16
    lda LVL_ACTOR
    and #$00FF
    asl a
    tax
    lda LVL_T
    cmp FAR_SP, x
    bcs sp_fits
    sta FAR_SP, x
sp_fits:
    sep #$20
.a8
    rts
.endproc

; Row A8 of the actor's curve in `exp_table` —`GetNextExp(A)`, what it
; takes to go from level A to the next— into `LVL_T`. Clobbers A and X.
.proc exp_row
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    sta LVL_T
    lda LVL_K
    asl a
    tax
    lda f:exp_curve, x
    clc
    adc LVL_T
    tax
    lda f:exp_table, x
    sta LVL_T
    lda f:exp_table + 2, x
    sta LVL_T + 2
    sep #$20
.a8
    rts
.endproc

; C if `LVL_VALUE` reaches `LVL_T`, both 24 bits.
.proc exp_reaches
.a8
.i16
    lda LVL_VALUE + 2
    cmp LVL_T + 2
    bne ready
    rep #$20
.a16
    lda LVL_VALUE
    cmp LVL_T
    sep #$20
.a8
ready:
    rts
.endproc

; `LVL_T`, 24 bits, as the actor's experience. Clobbers A and X.
.proc exp_put_row
.a8
.i16
    ldx LVL_OFS
    rep #$20
.a16
    lda LVL_T
    sta FAR_EXP, x
    sep #$20
.a8
    lda LVL_T + 2
    sta FAR_EXP + 2, x
    rts
.endproc

; A16 as one more line of the message, if OP_EXP asked for it and it fits:
; past `LVL_LINES_MAX` the rest are not shown, and are still learned.
; Returns with A16 as it came. Clobbers X.
.proc exp_note
.a16
.i16
    pha
    sep #$20
.a8
    lda LVL_WHAT
    and #EXP_WITH_MESSAGE
    beq skip
    lda LVL_N
    cmp #LVL_LINES_MAX
    bcs skip
    inc LVL_N
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    pla
    sta LVL_LINES, x
    rts
skip:
    rep #$20
.a16
    pla
    rts
.endproc

; `LearnLevelSkills(LVL_OLD + 1, LVL_NEW)` for the actor: each of its pairs
; the LDB's table teaches at those levels. One it already knew changes
; nothing and is not announced —`LearnSkill`—; one it did not sets its bit
; and notes its line.
;
; **Level by level**, like the victory's page, and not in one pass over the
; pairs: the pairs go by skill number and RM2k goes in its table's order,
; which the editor keeps by level. Two skills at the same level come out in
; the pairs' order, which can differ from the table's; in ABL no actor
; learns two at once. Uses `LVL_T` —the pair, how many are left, the bit—
; and `LVL_LEFT` —the level—, and clobbers A, X and Y.
.proc exp_learn
.a8
.i16
    lda LVL_OLD
    sta LVL_LEFT                ; the level being looked at, from the next one
level:
    lda LVL_LEFT
    cmp LVL_NEW
    bcs ready
    inc LVL_LEFT
    rep #$20
.a16
    lda LVL_ACTOR
    and #$00FF
    pha
    asl a
    tax
    lda f:skill_pair_init, x
    sta LVL_T                   ; the pair being looked at
    plx                         ; the actor
    sep #$20
.a8
    lda f:skill_pair_n, x
    beq ready                   ; no pairs at all
    sta LVL_T + 2               ; how many it has left
pair:
    ldx LVL_T
    lda f:skill_pair_level, x
    cmp LVL_LEFT
    bne next
taught:
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    tay                         ; its byte in `FAR_SKILL`
    txa
    and #$0007
    tax
    sep #$20
.a8
    lda f:mask, x
    sta LVL_T + 3
    tyx
    and FAR_SKILL, x
    bne next                    ; known already
    lda LVL_T + 3
    ora FAR_SKILL, x
    sta FAR_SKILL, x
    rep #$20
.a16
    lda LVL_T
    jsr exp_note
    sep #$20
.a8
next:
    rep #$20
.a16
    inc LVL_T
    sep #$20
.a8
    dec LVL_T + 2
    bne pair
    bra level
ready:
    rts
.endproc

; --- the level-up message, a page at a time ----------------------------------
;
; `OP_LEVEL_PAGE`: the lines `exp_change` noted, as RM2k's `PendingMessage`
; shows them —`ChangeLevel` pushes the level line, `LearnSkill` one per
; skill and then a page end—: four lines a page, and each actor from the top
; of its own. The words come from the LDB through the cartridge's text
; table —the actor's name, `level`, `level_up` and `skill_learned`, and the
; skill's— and are put together as the victory does, `ba_vic_message`, which
; is `game_message_terms.cpp` for English RM2k: "<name> <level>
; <n><level_up>" and "<skill><skill_learned>".
;
; In a troop page it shows nothing: the battle's window is not the map's.
; The levels change all the same.

; Returns C clear if no line is left, and the page goes on. With C set, A8
; nonzero if the next page is composed and `msg_ptr` is on it, or zero if a
; parallel has to wait for another's window, as `op_message` waits. Y as it
; came. Runs with the data bank at $7E.
.proc level_page
.a8
.i16
    phy
    phb
    lda #$7E
    pha
    plb
    lda pair_ev
    cmp #PAIR_BATTLE
    beq none
    lda LVL_AT
    cmp LVL_N
    bcs none
    lda pair_ev
    cmp #$FF
    beq open                    ; the foreground: nothing is open
    lda msg_open
    ora msg_state
    ora pick_active
    beq open
    lda #0
    bra stays
none:
    plb
    ply
    clc
    rtl
open:
    lda pair_ev
    sta msg_owner               ; $FF if the foreground opens it
    stz msg_open
    stz pick_active
    jsr level_compose
    rep #$20
.a16
    lda #.loword(LVL_BOX)
    sta msg_ptr
    sep #$20
.a8
    lda #^LVL_BOX
    sta msg_ptr + 2
    lda #1
stays:
    plb
    ply
    sec
    rtl
.endproc

; One page into `LVL_BOX`, from line `LVL_AT`: up to four lines, and a
; level line only at the top. Advances `LVL_AT`. Clobbers A, X, Y and
; `msg_ptr`, which it reads the texts through.
.proc level_compose
.a8
.i16
    rep #$20
.a16
    lda #1                      ; past the header
    sta LVL_CUR
    sep #$20
.a8
    stz LVL_ROWS
line:
    lda LVL_AT
    cmp LVL_N
    bcs done
    lda LVL_ROWS
    cmp #4
    bcc more
done:
    lda LVL_ROWS
    sta f:LVL_BOX               ; the header: how many lines, and nothing else
    rts
more:
    lda LVL_AT
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda LVL_LINES, x
    sta LVL_T
    sep #$20
.a8
    bit LVL_T + 1               ; N: bit 15, a level line
    bpl a_skill
    lda LVL_ROWS
    bne done                    ; another actor: on a page of its own
    jsr line_start
    lda LVL_T                   ; the actor
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    jsl f:actor_name_txt        ; renames included: actor_names.s
    tax
    sep #$20
.a8
    jsr put_text
    lda #' '
    jsr put_letter
    ldx #BA_TXT_LEVEL
    jsr put_text
    lda #' '
    jsr put_letter
    lda LVL_T + 1
    and #$7F                    ; the level
    jsr put_number
    ldx #BA_TXT_LEVEL_UP
    jsr put_text
    bra line_end
a_skill:
    jsr line_start
    rep #$20
.a16
    lda LVL_T                   ; the pair
    asl a
    tax
    lda f:skill_pair_learns_txt, x
    tax
    sep #$20
.a8
    cpx #$FFFF
    beq unnamed                 ; a pair the cartridge has no name for
    jsr put_text
unnamed:
    ldx #BA_TXT_LEARNED
    jsr put_text
line_end:
    ldx LVL_START
    lda LVL_LEN
    sta f:LVL_BOX, x            ; its length, before its letters
    inc LVL_ROWS
    inc LVL_AT
    jmp line

line_start:
    ldx LVL_CUR
    stx LVL_START
    inx
    stx LVL_CUR
    stz LVL_LEN
    rts
.endproc

; Text X of the cartridge's text table —`item_txt_*`, ASCII— onto the line.
; Clobbers A, X, Y and `msg_ptr`.
.proc put_text
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    beq empty
    sta LVL_LEFT
    ldy #0
letter:
    lda [msg_ptr], y
    jsr put_letter
    iny
    dec LVL_LEFT
    bne letter
empty:
    rts
.endproc

; Letter A8, in ASCII, onto the line in the font's numbering, unless the
; line already has `LVL_LINE_MAX`: the window would cut it before anyway.
; Clobbers X.
.proc put_letter
.a8
.i16
    pha
    lda LVL_LEN
    cmp #LVL_LINE_MAX
    pla                         ; `pla` does not touch C
    bcs full
    sec
    sbc #' '
    ldx LVL_CUR
    sta f:LVL_BOX, x
    inx
    stx LVL_CUR
    inc LVL_LEN
full:
    rts
.endproc

; A8, below a hundred, without leading zeros. Clobbers A, X and Y.
.proc put_number
.a8
.i16
    cmp #10
    bcc units
    ldy #0
tens:
    cmp #10
    bcc has_tens
    sbc #10                     ; C comes from the comparison
    iny
    bra tens
has_tens:
    pha
    tya
    ora #'0'
    jsr put_letter
    pla
units:
    ora #'0'
    jsr put_letter
    rts
.endproc
