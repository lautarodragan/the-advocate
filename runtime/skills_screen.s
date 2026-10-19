.segment "FAR2"
.a8
.i16

; --- the skills screen -------------------------------------------------------
;
; `Scene_Skill`, opened from the pause menu's Tech Skill —the command, then
; whose, on the menu itself—: on top the description of the skill under the
; cursor in two lines, below it the actor's status line, and the list in two
; columns that read by rows, eight at a time, each skill with its cost and in
; grey if the map cannot use it or the SP do not reach. B goes back to the
; menu with the cursor on the command; A on a switch skill uses it and goes
; straight to the map, and on a heal opens the actor choice for it —see
; `sk_heal`—, and comes back here. The geometry is `SK_*` of
; `rm2k-snes-screens`, whose `render` is the reference; eight rows and two
; lines of description where RM2k has ten and one is the divergence
; `the-skills-screen` in the book.
;
; **It is the custom menus' full screen** —see `custom_menu.s`—: the text on
; BG2 with the text layer from word 0 up to `CM_BG1_MAP`, the windows on BG1
; at 8bpp with their tiles from `CM_BG1_VRAM` and their colours from
; `CM_BORDER_CGRAM`, and no objects. What it overwrites is what a custom menu
; overwrites, and the map comes back the same way: `CM_DIRTY`, and
; `big_back_far` when the pause menu closes.
;
; **The list is the battle's**: `ba_skill_walk`, in `battle_skills.s`, walks
; the actor's pairs and keeps the visible page in `BA_SKILL_LIST`, and
; `ba_skill_see` scrolls it as `Window_Selectable` does. They run with the
; data bank at $7E; this screen runs with the pause menu's, 0, and reads the
; battle's state with `f:`. Nobody uses it while the menu is open.

.assert SK_ROWS * SK_COLUMNS <= BA_SKILL_MAX, error, "a page of the skills screen does not fit in BA_SKILL_LIST"
.assert SK_COLUMNS = 2, error, "the skills screen takes a row as two places"
.assert SK_BORDER_TILES > 0 && SK_BORDER_COLORS > 0, error, "the skills screen has no windows: a DMA of 0 bytes is 64 KB"
.assert CM_BG1_VRAM + SK_BORDER_TILES * 32 <= CM_OBJ_VRAM, error, "the skills screen's windows do not fit below the objects"
.assert CM_BORDER_CGRAM + SK_BORDER_COLORS <= 240, error, "the skills screen's colours step on the last palette"

; The bars go right after the arrangement, in its block, so one bank byte
; reads both: see `skills_screen.rs` in rm2k-snes-mapdata.
SK_BARS_OFS = 32 * 28 * 2

.pushseg
.segment "FARBSS"
sk_actor:    .res 1             ; the LDB actor whose list it is
sk_bar_on:   .res 1             ; the place whose bar is on screen, $FF none
sk_bar_want: .res 1             ; and the one it should be on
; Whether the actor choice is open for a skill —0, for a medicine, which is
; what the items screen opens it for—, and the skill's `k`. See `sk_heal`.
sk_target_on: .res 1
sk_used:      .res 1
.popseg

; The LDB actor in A, with the data bank at 0. Returns with `rtl`, and A at
; 0 when B was pressed —the pause menu draws itself again— or at 1 when a
; switch skill was used —the menu closes, as `Scene::PopUntil(Map)`—.
.proc skills_screen
.a8
.i16
    sta f:sk_actor
    lda #0
    sta f:BAT_LENGTH + BA_SKILL_SEL
    sta f:BAT_LENGTH + BA_SKILL_TOP
    lda #SK_ROWS
    sta f:ba_skill_rows
    lda #(SK_ROWS * SK_COLUMNS)
    sta f:ba_skill_places
    lda #1
    sta f:CM_DIRTY              ; the map comes back whole when the menu closes
    jsr sk_upload
    jsr sk_view
wait:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    jsr sk_bar_upload           ; in the vblank, before the text's
    jsl f:tl_map + FAST         ; `scr_upload`
    jsl f:tl_vblank + FAST
    jsl f:tl_work + FAST
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    ; The cursor, as the battle's list moves it: left and right by one, up
    ; and down by a row, without wrapping —`Window_Selectable` in two
    ; columns—. The arrows are the four low bits, shifted out one by one.
    .assert PAD_RIGHT = $01 && PAD_LEFT = $02 && PAD_DOWN = $04 && PAD_UP = $08, error, "the arrows' bits"
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sta f:CM_T0                 ; where it was, to see whether it moved
    lda title_edges
    lsr a
    bcc no_right
    lda f:BAT_LENGTH + BA_SKILL_SEL
    inc a
    bra to_place
no_right:
    lsr a
    bcc no_left
    lda f:BAT_LENGTH + BA_SKILL_SEL
    beq moved
    dec a
    bra to_place
no_left:
    lsr a
    bcc no_down
    lda f:BAT_LENGTH + BA_SKILL_SEL
    clc
    adc #SK_COLUMNS
    bra to_place
no_down:
    lsr a
    bcc no_arrow
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sec
    sbc #SK_COLUMNS
    bcc moved
to_place:
    cmp f:BAT_LENGTH + BA_SKILL_N
    bcs moved                   ; past the last one: it stays
    sta f:BAT_LENGTH + BA_SKILL_SEL
moved:
    lda f:CM_T0
    cmp f:BAT_LENGTH + BA_SKILL_SEL
    beq to_wait
    phb
    lda #$7E
    pha
    plb
    jsr ba_skill_see
    plb
    jsr sk_compose
to_wait:
    jmp wait
no_arrow:
    lda title_edges
    and #PAD_B
    beq no_b
    lda #0                      ; back to the menu
    bra out
no_b:
    lda pad_a
    beq to_wait
    lda pad_a_prev
    bne to_wait                 ; it was already held: not an edge
    ; A on an enabled one —`Scene_Skill::Update`—: a switch skill is used
    ; here and closes the menu; any other the map lets through is a heal,
    ; which opens the actor choice. On a grey one RM2k plays its buzzer.
    lda f:BAT_LENGTH + BA_SKILL_N
    beq to_wait
    lda f:sk_bar_want
    jsr sk_k
    sta f:CM_T4
    jsr sk_usable
    beq to_wait
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_type, x
    cmp #BA_SKILL_TYPE_SWITCH
    beq switch
    jsr sk_heal
    jmp wait
switch:
    jsr sk_switch
    lda #1                      ; straight to the map
out:
    ; Out: the button that closes is consumed, and the other one, as the
    ; pause menu does; and what of the objects the windows' colours took.
    pha
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    jsr cm_objects_back
    pla
    rtl
.endproc

; Switch skill `CM_T4`, used by `sk_actor`: its switch on and its SP spent,
; in `Game_Battler::UseSkill`'s and `Game_Party::UseSkill`'s order. Its
; sound effect is not played: none of A Blurred Line's switch skills has
; one, and another game's would have to be in what the map carries —see the
; ports' Known issues—. The switch asks for the pages' refresh, which is
; `Game_Map::SetNeedRefresh`, and the common event that waits for it runs
; on the map when the pause menu closes.
.proc sk_switch
.a8
.i16
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    asl a
    tax
    lda f:skill_switch, x
    sta f:BAT_LENGTH + BA_T0
    sep #$20
.a8
    phb
    lda #$7E
    pha
    plb
    jsr ba_switch
    plb
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    sta f:CM_T0
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    sec
    sbc f:CM_T0                 ; `sk_usable` said it reaches
    sta f:FAR_LENGTH + FAR_SP, x
    sep #$20
.a8
    rts
.endproc

; Heal `CM_T4`: the actor choice, `Scene_ActorTarget` with a skill, which
; is the medicine's —`target_screen`, in bank 0, through `ba_t_target`—
; told by `sk_target_on` that it is for a skill. It stays there after each
; use, as RPG_RT does, and B comes back here with the cursor where it was;
; the choice took the whole VRAM, so the screen is drawn again.
.proc sk_heal
.a8
.i16
    lda f:CM_T4
    sta f:sk_used
    lda #1
    sta f:sk_target_on
    jsl f:ba_t_target
    lda #0
    sta f:sk_target_on
    jsr sk_upload
    jmp sk_view
.endproc

; The heal `sk_used` by `sk_actor` on actor A, from the actor choice:
; `Game_Party::UseSkill` outside battle, with `Game_Battler::UseSkill`'s
; effect for each target —the one chosen, the user for a skill on oneself,
; every member for one on the party—. Returns with A8 at 1 if it was of
; use to anyone, which is what spends the SP, once, and at 0 if not
; —RPG_RT's buzzer, not played here—; Z to match. A user that cannot pay
; does nothing, not even a roll. Entered with `jsl` from `target_use`, with
; the data bank at 0; the effect, `sk_heal_one`, runs with it at $7E. Clobbers X, Y, `temp`
; and the `MED_*` scratch.
;
; **The effect is the battle's**: `ba_skill_effect` and `ba_variance` over
; combatant 0's record, which only needs the user's attack and spirit
; —`eq_parameter`, as the battle reads them—, and the battle's randomness,
; seeded as a battle seeds it if nothing has drawn from it yet. So
; `field-skill` of `rm2k-snes-battle` gives the exact number, critical's
; roll —always no— included. **Outside battle there are no states**: a
; fallen actor is one at 0 HP, and curing any other state is of no use.
.proc sk_heal_use
.a8
.i16
    sta f:MED_ACTOR             ; the one chosen
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    sta f:MED_P                 ; the user's SP
    lda f:sk_used
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    cmp f:MED_P
    sep #$20
.a8
    beq pays
    bcc pays
    lda #0                      ; it cannot pay: `GetSp() < CalculateSkillCost`
    rtl
pays:
    ; The user's attack and spirit with its equipment, into combatant 0.
    lda #0
    jsr param
    sta f:BAT_LENGTH + BA_ONE + BA_ATK
    xba
    sta f:BAT_LENGTH + BA_ONE + BA_ATK + 1
    lda #2
    jsr param
    sta f:BAT_LENGTH + BA_ONE + BA_SPI
    xba
    sta f:BAT_LENGTH + BA_ONE + BA_SPI + 1
    lda #0
    sta f:BAT_LENGTH + BA_MWHO
    sta f:BAT_LENGTH + BA_MTGT
    sta f:MED_USED
    lda f:sk_used
    sta f:BAT_LENGTH + BA_MSKILL
    rep #$20
.a16
    lda f:BAT_LENGTH + BA_SEED
    bne seeded
    lda #BATTLE_SEED            ; nothing drew from it since the power-on
    sta f:BAT_LENGTH + BA_SEED
seeded:
    sep #$20
.a8
    ; Whom: by the skill's scope.
    lda f:sk_used
    jsr ba_ax
    lda f:skill_scope, x
    cmp #BA_SCOPE_PARTY
    beq party_wide
    cmp #BA_SCOPE_ALLY
    beq chosen
    lda f:sk_actor              ; on oneself
    bra one_only
chosen:
    lda f:MED_ACTOR
one_only:
    jsr sk_heal_one
    bra pay
party_wide:
    lda #0
each:
    cmp party_n
    bcs pay
    pha
    jsr ba_ax
    lda party, x
    jsr sk_heal_one
    pla
    inc a
    bra each
pay:
    lda f:MED_USED
    beq done
    rep #$20
.a16
    lda f:sk_used
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    sta f:MED_P
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    sec
    sbc f:MED_P                 ; it was checked that it pays
    sta f:FAR_LENGTH + FAR_SP, x
    sep #$20
.a8
done:
    ; Nothing of a material: the actor choice repaints the rows, not all.
    lda #0
    sta f:MED_FLAGS
    lda f:MED_USED
    rtl

; Parameter A of `sk_actor` with its equipment, in A16's two bytes as A8
; and B: `eq_parameter` through the battle's bridge.
param:
    sta comp_or01 + 2
    stz comp_or01 + 3
    stz comp_col + 1
    lda f:sk_actor
    sta comp_char
    stz comp_char + 1
    jsl f:ba_t_param
    lda comp_dup + 1
    xba
    lda comp_dup
    rts
.endproc

; The heal's effect on actor A —`Game_Battler::UseSkill` outside battle—,
; with the data bank at $7E: `CalcSkillEffect` with the variance first,
; whatever it finds; then death cured if the skill cures it and the actor is
; down, which is 1 HP; and then the HP and the SP go up only if not full
; and standing, the revived one by the effect minus that one. A skill that
; revives without touching HP gives the revived one that many percent of
; its maximum, minus the one. `MED_USED` at 1 if any of it happened. It
; sets the data bank at $7E, as the battle runs, and gives back the one
; there was.
.proc sk_heal_one
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    sta .loword(MED_ACTOR)
    ; The target, as an actor in combatant 1, for its ranks in the skill's
    ; attributes: `CalcSkillEffect` looks at them on a heal too. Its
    ; parameters are not read: a heal does not subtract the target's.
    sta BA_ONE + BA_BYTES + BA_NUMBER
    lda #1
    sta BA_MTGT
    ; And no shifted rank: outside battle there are none, and what the last
    ; battle left in combatant 1's row stays there.
    jsr ba_attr_unshift
    jsr ba_skill_effect         ; into `BA_MEFFECT`, the critical rolled
    lda f:sk_used
    jsr ba_ax
    lda f:skill_var, x
    sta BA_S5
    rep #$20
.a16
    lda BA_MEFFECT
    jsr ba_variance
    sta .loword(MED_HP)         ; the effect, never below zero
    sep #$20
.a8
    lda .loword(MED_ACTOR)
    ldy #0
    jsl f:level_param
    stx .loword(MED_HP_MAX)
    lda .loword(MED_ACTOR)
    ldy #1
    jsl f:level_param
    stx .loword(MED_SP_MAX)
    lda f:sk_used
    jsr ba_ax
    lda f:skill_affects, x
    sta .loword(MED_FLAGS)      ; bit 0 the HP, bit 1 the SP
    lda f:skill_on_map, x
    sta .loword(MED_REVIVED) + 1    ; bit 1: it cures death
    stz .loword(MED_REVIVED)
    lda .loword(MED_ACTOR)
    rep #$20
.a16
    and #$00FF
    asl a
    tax                         ; from here on, the actor times two
    lda FAR_HP, x
    bne standing
    sep #$20
.a8
    lda .loword(MED_REVIVED) + 1
    and #2
    beq standing8               ; down, and it does not raise: nothing on it
    lda #1
    sta .loword(MED_USED)
    sta .loword(MED_REVIVED)
    rep #$20
.a16
    lda #1
    sta FAR_HP, x               ; `RemoveStates`' `SetHp(1)`
    bra standing
standing8:
    rep #$20
.a16
standing:
    lda .loword(MED_REVIVED)
    and #$00FF
    sta .loword(MED_REVIVED)    ; now the word `revived`
    lda .loword(MED_HP)
    bne has_effect
    jmp ready
has_effect:
    lda FAR_HP, x
    bne alive
    jmp ready                   ; down: `!IsDead()` fails for both
alive:
    lda .loword(MED_FLAGS)
    and #1
    beq no_hp
    ; `ChangeHp(effect - revived)`, if not full.
    lda FAR_HP, x
    cmp .loword(MED_HP_MAX)
    bcs sp
    clc
    adc .loword(MED_HP)
    sec
    sbc .loword(MED_REVIVED)
    cmp .loword(MED_HP_MAX)
    bcc hp_set
    lda .loword(MED_HP_MAX)
hp_set:
    sta FAR_HP, x
    bra hp_used
no_hp:
    ; Without HP of its own, only a revived one gets something: the
    ; percentage, `ChangeHp(max * effect / 100 - revived)`, never below 1.
    ; From 1 HP that leaves `max * effect / 100`, at least 1. An effect
    ; past 100 gives the whole maximum, as it would with the product.
    lda .loword(MED_REVIVED)
    beq sp
    phx
    lda .loword(MED_HP)
    cmp #100
    bcc percent_ready
    lda #100
percent_ready:
    sta BA_T2                   ; `ba_mul`'s byte; its high byte is clobbered
    lda .loword(MED_HP_MAX)
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div                  ; max = 100 q + r: q in A, r in `comp_and`
    pha
    lda comp_and
    jsr ba_mul                  ; r times the percentage, at most 9900
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sta .loword(MED_P)          ; r * e / 100
    pla
    jsr ba_mul                  ; q * e
    clc
    adc .loword(MED_P)
    plx
    cmp #0                      ; the `plx` left the flags of X
    bne hp_some
    lda #1
hp_some:
    cmp .loword(MED_HP_MAX)
    bcc pct_set
    lda .loword(MED_HP_MAX)
pct_set:
    sta FAR_HP, x
hp_used:
    sep #$20
.a8
    lda #1
    sta .loword(MED_USED)
    rep #$20
.a16
sp:
    ; `ChangeSp(effect)`, if it touches SP and they are not full.
    lda .loword(MED_FLAGS)
    and #2
    beq ready
    lda FAR_SP, x
    cmp .loword(MED_SP_MAX)
    bcs ready
    clc
    adc .loword(MED_HP)
    cmp .loword(MED_SP_MAX)
    bcc sp_set
    lda .loword(MED_SP_MAX)
sp_set:
    sta FAR_SP, x
    sep #$20
.a8
    lda #1
    sta .loword(MED_USED)
    rep #$20
.a16
ready:
    sep #$20
.a8
    plb
    rts
.endproc

; Whether `sk_actor` can use skill `CM_T4` here: Z=0 if so —the map can use
; it, its SP reach and its weapons carry its physical attributes, see
; `ba_weapons_allow`—. `Window_Skill::CheckEnable`, without states, which
; this port does not keep outside battle. **It does not use the flag a
; `pl*` leaves**: the usual trap.
.proc sk_usable
.a8
.i16
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_on_map, x
    beq no
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:FAR_LENGTH + FAR_SP, x
    sta f:CM_T0                 ; its SP
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    cmp f:CM_T0
    sep #$20
.a8
    beq yes                     ; exactly as many as it has is enough
    bcs no
yes:
    rep #$20
.a16
    lda f:CM_T4
    tay
    sep #$20
.a8
    lda f:sk_actor
    jmp ba_weapons_allow
no:
    lda #0
    rts
.endproc

; The screen from nothing, with it off: the text layer's bank, the inks, the
; windows' tiles and colours, every object out of the screen, and the
; registers. `cm_screen_upload` without the portrait.
.proc sk_upload
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:battle_bank_upload + FAST
    rep #$20
.a16
    lda #(2 * 16 * 2)
    sta f:CM_T0
    ldx #.loword(item_cgram_uploads)
    sep #$20
.a8
    ldy #ITEMS_CGRAM_N
    lda #^item_cgram_uploads
    jsr cm_dma_cgram
    rep #$20
.a16
    lda #(SK_BORDER_COLORS * 2)
    sta f:CM_T0
    ldx #.loword(sk_border_cgram)
    sep #$20
.a8
    ldy #CM_BORDER_CGRAM
    lda #^sk_border_cgram
    jsr cm_dma_cgram
    rep #$20
.a16
    lda #(SK_BORDER_TILES * 64)
    sta f:CM_T0
    ldx #.loword(sk_border_tiles)
    sep #$20
.a8
    ldy #CM_BG1_VRAM
    lda #^sk_border_tiles
    jsr cm_dma_vram
    ; Every object below the screen, and the high table at zero.
    stz OAMADDL
    stz OAMADDL + 1
    ldx #128
hidden:
    stz OAMDATA
    lda #224
    sta OAMDATA
    stz OAMDATA
    stz OAMDATA
    dex
    bne hidden
    ldx #32
high:
    stz OAMDATA
    dex
    bne high
    lda #(CM_BG1_VRAM / $1000)  ; BG2 from word 0, BG1 from its tiles
    sta BG12NBA
    lda #(CM_BG1_MAP / 1024 * 4)
    sta BG1SC
    lda #(SLOT_MAP / 1024 * 4)
    sta BG2SC
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    sta BG2VOFS
    sta BG2VOFS
    rts
.endproc

; The windows, the text composed whole and the bar, with the screen off;
; then on.
.proc sk_view
.a8
.i16
    rep #$20
.a16
    lda #CM_TEXT_POOL
    jsl f:tl_reset + FAST
    sep #$20
.a8
    jsl f:tl_low + FAST
    rep #$20
.a16
    lda #(32 * 28 * 2)
    sta f:CM_T0
    ldx #.loword(sk_layout)
    sep #$20
.a8
    ldy #CM_BG1_MAP
    lda #^sk_layout
    jsr cm_dma_vram
    lda #$FF
    sta f:sk_bar_on
    jsr sk_compose
    jsr sk_bar_upload
    jsl f:tl_map + FAST         ; with the screen off right after `tl_reset`,
    jsl f:tl_vblank + FAST      ; `scr_upload` composes the whole text
    jsl f:tl_work + FAST
    lda #$03
    sta TM
    jsl f:ba_t_vblank
    lda #$0F
    sta INIDISP
    rts
.endproc

; The bar to place `sk_bar_want`, off place `sk_bar_on`: each is two half
; rows of BG1's tilemap, the arrangement's own or the place's in the bars.
; In the vblank or with the screen off.
.proc sk_bar_upload
.a8
.i16
    lda f:sk_bar_on
    cmp f:sk_bar_want
    beq ready
    cmp #$FF
    beq paint
    ; Off: the arrangement's cells, a row of it below the other.
    jsr word_of
    rep #$20
.a16
    lda f:CM_T3
    asl a
    clc
    adc #.loword(sk_layout)
    sta f:CM_T1
    lda #64
    sta f:CM_T2
    sep #$20
.a8
    jsr two_rows
paint:
    lda f:sk_bar_want
    sta f:sk_bar_on
    jsr word_of
    rep #$20
.a16
    lda f:sk_bar_on
    and #$00FF
    xba
    lsr a
    lsr a                       ; times 64: a place's two half rows
    clc
    adc #.loword(sk_layout) + SK_BARS_OFS
    sta f:CM_T1
    lda #(SK_HALF_COLS * 2)
    sta f:CM_T2
    sep #$20
.a8
    jsr two_rows
ready:
    rts

; Where place A's bar starts in the tilemap, in words, into `CM_T3`:
; its row of the page twice, from the list's first, times 32, and sixteen
; more for the right column.
word_of:
    rep #$20
.a16
    and #$00FF
    pha
    and #$0001
    asl a
    asl a
    asl a
    asl a
    sta f:CM_T3
    pla
    lsr a
    asl a
    clc
    adc #SK_LIST_ROW0
    xba
    lsr a
    lsr a
    lsr a                       ; times 32
    clc
    adc f:CM_T3
    sta f:CM_T3
    sep #$20
.a8
    rts

; The half row from `CM_T1` to the tilemap's word `CM_T3`, and the one
; below it from `CM_T2` bytes further.
two_rows:
    jsr one_row
    rep #$20
.a16
    lda f:CM_T3
    clc
    adc #32
    sta f:CM_T3
    lda f:CM_T1
    clc
    adc f:CM_T2
    sta f:CM_T1
    sep #$20
.a8
one_row:
    rep #$20
.a16
    lda #(SK_HALF_COLS * 2)
    sta f:CM_T0
    lda f:CM_T3
    clc
    adc #CM_BG1_MAP
    tay
    lda f:CM_T1
    tax
    sep #$20
.a8
    lda #^sk_layout
    jmp cm_dma_vram
.endproc

; The text of the screen, written whole into the text layer's records —the
; rows that say what they said keep their tiles—: the description of the one
; under the cursor, the status line and the visible page. And where the bar
; goes.
.proc sk_compose
.a8
.i16
    jsl f:tl_clear + FAST
    phb
    lda #$7E
    pha
    plb
    lda f:sk_actor
    jsr ba_skill_walk
    plb
    ; The bar: on the cursor's place in the page, the first with none.
    lda f:BAT_LENGTH + BA_SKILL_TOP
    asl a
    sta f:CM_T0
    lda f:BAT_LENGTH + BA_SKILL_SEL
    sec
    sbc f:CM_T0
    sta f:sk_bar_want
    jsr sk_status
    lda f:BAT_LENGTH + BA_SKILL_N
    bne has
    rts
has:
    ; --- the description: two slices of the battle's one text ---
    lda f:sk_bar_want
    jsr sk_k
    sta f:CM_T4                 ; the skill's `k`
    jsr desc_at
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    sep #$20
.a8
    lda f:skill_line1_n, x
    ldy #SK_HELP_ROW0
    jsr line
    jsr desc_at
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_line2_at, x
    and #$00FF
    clc
    adc msg_ptr
    sta msg_ptr
    sep #$20
.a8
    bcc same_bank               ; `sep` leaves the carry alone
    inc msg_ptr + 2
same_bank:
    lda f:skill_line2_n, x
    ldy #(SK_HELP_ROW0 + 2)
    jsr line
    ; --- the page ---
    lda #0
    sta f:CM_N                  ; the place in the page
place:
    lda f:BAT_LENGTH + BA_SKILL_TOP
    asl a
    clc
    adc f:CM_N
    cmp f:BAT_LENGTH + BA_SKILL_N
    bcs ready
    lda f:CM_N
    cmp #(SK_ROWS * SK_COLUMNS)
    bcs ready
    jsr sk_row
    lda f:CM_N
    inc a
    sta f:CM_N
    bra place
ready:
    rts

; `msg_ptr` at the start of skill `CM_T4`'s description.
desc_at:
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    asl a
    tax
    lda f:skill_desc, x
    tax
    sep #$20
.a8
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    rts

; A letters at `msg_ptr`, by reference, white, from the help's cell of row
; Y. Nothing if there are none.
line:
    cmp #0
    beq no_line
    sta temp
    tya
    ldy #SK_HELP_COL
    jsr cm_at
    stz temp + 1
    lda #1
    sta f:$7E0000 + TL_BY_REF
    lda #255
    sta comp_dup + 3
    jsl f:tl_text_at + FAST
no_line:
    rts
.endproc

; The `k` at place A of the page, in A. Only A and X.
.proc sk_k
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:BAT_LENGTH + BA_SKILL_LIST, x
    rts
.endproc

; Place `CM_N` of the page: the name, the dash and the cost, in grey if the
; map cannot use it or the SP do not reach —`Window_Skill::CheckEnable`,
; without states, which this port does not keep outside battle—.
.proc sk_row
.a8
.i16
    lda f:CM_N
    jsr sk_k
    sta f:CM_T4
    jsr sk_usable
    beq grey
    lda #ITEM_WHITE
    bra colour
grey:
    lda #ITEM_GRAY
colour:
    sta temp + 1
    ; The row, and the column's first cell.
    lda f:CM_N
    and #1
    beq left
    lda #SK_COLUMN_DX
left:
    sta f:CM_T3                 ; the column's cell
    lda f:CM_N
    lsr a
    asl a
    clc
    adc #SK_LIST_ROW0
    sta f:CM_T3 + 1             ; the row
    ; The name, by reference, cut at its cells.
    lda #SK_NAME_DX
    jsr at
    lda #SK_NAME_CELLS
    sta comp_dup + 3
    lda #1
    sta f:$7E0000 + TL_BY_REF
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    asl a
    tax
    lda f:skill_txt, x
    tax
    sep #$20
.a8
    jsl f:tl_text + FAST
    ; The dash, and the cost in two places right after it: the number goes
    ; where the dash left the pen, and continues its run, as in the battle.
    lda #SK_DASH_DX
    jsr at
    lda #'-'
    jsl f:tl_letter + FAST
    rep #$20
.a16
    lda f:CM_T4
    and #$00FF
    tax
    lda f:skill_sp, x
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #SK_COST_DIGITS
    sta comp_dup + 2
    jsl f:tl_number + FAST
    rts

; `pick_table` at the column's cell plus A, on its row.
at:
    clc
    adc f:CM_T3
    tay
    lda f:CM_T3 + 1
    jmp cm_at
.endproc

; The status line: the name, the level, "Normal", and the HP and the SP with
; their maximums for its level —`level_param`—, the terms in red.
.proc sk_status
.a8
.i16
    ; The name, by reference, cut at its cells.
    lda #SK_NAME_WIDTH
    ldy #SK_NAME_COL
    jsr place
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    jsl f:actor_name_txt        ; renames included: actor_names.s
    tax
    sep #$20
.a8
    jsl f:tl_text + FAST
    ; The level term, and the level.
    lda #255
    ldy #SK_LEVEL_COL
    jsr place
    lda #ITEM_RED
    sta temp + 1
    ldx #SK_TXT_LEVEL
    jsl f:tl_text + FAST
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    tax
    sep #$20
.a8
    lda f:actor_exp_k, x        ; `actor_level_of`, which is in another bank
    cmp #$FF
    beq no_level                ; one that cannot be in the party
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda f:FAR_LENGTH + FAR_EXP + EXP_LEVEL, x
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #LEVEL_PLACES
    ldy #SK_LEVEL_NUM_COL
    jsr number
no_level:
    ; The state: outside battle, always the normal one.
    lda #SK_STATE_WIDTH
    ldy #SK_STATE_COL
    jsr place
    ldx #BA_TXT_NORMAL
    jsl f:tl_text + FAST
    ; The HP and the SP.
    lda #0
    jsr points
    lda #1
    jmp points

LEVEL_PLACES = 2                ; "%2d", as the menu's level

; `pick_table` at cell Y of the status row, white, a text by reference of
; at most A cells.
place:
    sta comp_dup + 3
    lda #SK_STATUS_ROW
    jsr cm_at
    stz temp + 1
    lda #1
    sta f:$7E0000 + TL_BY_REF
    rts

; `comp_dup` in A places at cell Y of the status row, white.
number:
    sta comp_dup + 2
    lda #SK_STATUS_ROW
    jsr cm_at
    stz temp + 1
    jsl f:tl_number + FAST
    rts

; The HP —A = 0— or the SP —A = 1—: the term, and from its number's cell
; the current one in three places, the slash and the maximum for its level
; in three, one run.
points:
    sta f:CM_T2                 ; which: also `level_param`'s parameter
    ldy #SK_HP_COL
    ldx #BA_TXT_HP
    cmp #0
    beq term
    ldy #SK_SP_COL
    ldx #BA_TXT_SP
term:
    phx
    lda #255
    jsr place
    lda #ITEM_RED
    sta temp + 1
    plx
    jsl f:tl_text + FAST
    ; The current one, from far RAM: the SP follow the HP's table.
    rep #$20
.a16
    lda f:sk_actor
    and #$00FF
    asl a
    tax
    lda f:CM_T2
    and #$00FF
    beq hp_now
    lda f:FAR_LENGTH + FAR_SP, x
    bra now
hp_now:
    lda f:FAR_LENGTH + FAR_HP, x
now:
    jsr capped
    sep #$20
.a8
    ldy #SK_HP_NUM_COL
    lda f:CM_T2
    beq hp_cell
    ldy #SK_SP_NUM_COL
hp_cell:
    lda #3
    jsr number
    lda #'/'
    jsl f:tl_letter + FAST
    ; The maximum for its level.
    rep #$20
.a16
    lda f:CM_T2
    and #$00FF
    tay
    sep #$20
.a8
    lda f:sk_actor
    jsl f:level_param           ; into X; clobbers A and Y
    rep #$20
.a16
    txa
    jsr capped
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:tl_number + FAST
    rts

; A16 into `comp_dup`, at most 999, as the battle's line caps it.
capped:
.a16
    cmp #1000
    bcc fits
    lda #999
fits:
    sta comp_dup
    rts
.a8
.endproc
