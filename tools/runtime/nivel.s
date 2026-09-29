.segment "FAR"

; --- level and maximum in the menu ---------------------------------------------
;
; Until 2026-09-21 both were cartridge strips, composed at conversion time with
; the starting level: they never changed, so nothing more was needed. Since
; leveling up exists, they are composed here in `EXP_TEXTO` with the same
; thing they used to say —`titulo.texto_de_nivel` and
; `titulo.texto_de_maximo`— and the menu writes them with
; `ranura_texto_escribir` as before: all that changes is where `msg_ptr`
; points. With the starting level they give exactly the same letters as the
; strips, which is what keeps the menu goldens still.
;
; All three enter with the actor in A, leave `msg_ptr` pointing at the text and
; **leave Y as it was**, which is the cell where the caller is going to write.
; An actor without an experience slot keeps its cartridge strip.

; A16 —less than a thousand— into three digits from 0 to 9, at
; `EXP_TEXTO + 5`, `+ 6` and `+ 7`. Clobbers A and X; enters and leaves with a
; 16-bit A.
.proc tres_cifras
.a16
.i16
    ldx #0
centenas:
    cmp #100
    bcc hay_centenas
    sbc #100                    ; C comes from the comparison
    inx
    bra centenas
hay_centenas:
    pha
    txa
    sep #$20
.a8
    sta f:EXP_TEXTO + 5
    rep #$20
.a16
    pla
    ldx #0
decenas:
    cmp #10
    bcc unidades
    sbc #10
    inx
    bra decenas
unidades:
    sep #$20
.a8
    sta f:EXP_TEXTO + 7
    txa
    sta f:EXP_TEXTO + 6
    rep #$20
.a16
    rts
.endproc

; `msg_ptr` to actor A's cartridge strip, offset by X bytes: the same as bank
; 0's `ranura_texto_de`, for those with no slot. Clobbers A.
.proc tira_del_cartucho
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; RANURA_TEXTO_ANCHO bytes per actor
    sta msg_ptr
    txa
    clc
    adc msg_ptr
    clc
    adc #.loword(ranura_actor_texto)
    sta msg_ptr
    sep #$20
.a8
    lda #^ranura_actor_texto
    sta msg_ptr + 2
    rtl
.endproc

; `msg_ptr` to `EXP_TEXTO`.
.proc apuntar_texto
.a8
.i16
    rep #$20
.a16
    lda #.loword(EXP_TEXTO)
    sta msg_ptr
    sep #$20
.a8
    lda #^EXP_TEXTO
    sta msg_ptr + 2
    rtl
.endproc

; Level A8 as "%2d" in `EXP_TEXTO`: the tens digit or a space, and the units.
.proc nivel_a_texto
.a8
.i16
    rep #$20
.a16
    and #$00FF
    jsr tres_cifras
    sep #$20
.a8
    lda f:EXP_TEXTO + 6
    beq sin_decena
    ora #'0'
    bra decena
sin_decena:
    lda #' '
decena:
    sta f:EXP_TEXTO
    lda f:EXP_TEXTO + 7
    ora #'0'
    sta f:EXP_TEXTO + 1
    rts
.endproc

; Actor A's current level.
.proc texto_nivel
.a8
.i16
    pha
    jsr actor_nivel_de
    cmp #$FF
    bne tiene
    pla
    ldx #RANURA_TEXTO_NIVEL
    jmp tira_del_cartucho
tiene:
    jsr nivel_a_texto
    pla
    jmp apuntar_texto
.endproc

EXP_NIVEL_EN_SRAM = SRAM_BANCO * $10000 + SRAM_DATOS + PARTIDA_BYTES - EXP_K * 4 + EXP_NIVEL

; The level actor A had **in the saved game in slot `ranura`**, read from its
; SRAM: the slots screen shows each save as it was left, not as the current
; one is. `FAR_EXP` is the last line of `partida_tabla`, so in the slot it
; falls `EXP_K * 4` bytes before the end.
.proc texto_nivel_guardado
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
    bne tiene
    pla
    ldx #RANURA_TEXTO_NIVEL
    jmp tira_del_cartucho
tiene:
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    pha                         ; the experience slot times four
    lda ranura
    and #$00FF
    xba
    asl a
    asl a
    asl a                       ; the SRAM slot times SRAM_STRIDE
    clc
    adc 1, s
    tax
    pla
    sep #$20
.a8
    lda f:EXP_NIVEL_EN_SRAM, x
    jsr nivel_a_texto
    pla
    jmp apuntar_texto
.endproc

; The maximum HP for actor A's current level, as "/%d" padded to
; `MENU_MAX_CIFRAS` with spaces: `titulo.texto_de_maximo`.
.proc texto_maximo
.a8
.i16
    pha
    jsr actor_nivel_de
    cmp #$FF
    bne tiene
    pla
    ldx #RANURA_TEXTO_MAX
    jmp tira_del_cartucho
tiene:
    pla
    phy
    ldy #0
    jsl f:nivel_param
    rep #$20
.a16
    txa
    jsr tres_cifras
    sep #$20
.a8
    ldx #0
    lda #'/'
    sta f:EXP_TEXTO, x
    inx
    lda f:EXP_TEXTO + 5
    beq sin_centena
    ora #'0'
    sta f:EXP_TEXTO, x
    inx
    lda f:EXP_TEXTO + 6
    bra con_decena              ; with hundreds the tens digit goes in even if zero
sin_centena:
    lda f:EXP_TEXTO + 6
    beq sin_decena
con_decena:
    ora #'0'
    sta f:EXP_TEXTO, x
    inx
sin_decena:
    lda f:EXP_TEXTO + 7
    ora #'0'
    sta f:EXP_TEXTO, x
    inx
relleno:
    cpx #MENU_MAX_CIFRAS
    bcs completo
    lda #' '
    sta f:EXP_TEXTO, x
    inx
    bra relleno
completo:
    ply
    jmp apuntar_texto
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
; The digits are the same glyphs as the gold —`ranura_glifo_celdas`, one per
; cell— and they line up without touching anything because both lines are
; drawn two pixels from the top edge of their cell. `titulo._pegar_hp` is the
; reference, with the same columns.
;
; It lives outside bank 0 for the same reason as `hp_inicial_poner`: there are
; tens of bytes left there and this is over a hundred. It is entered with
; `jsl` and with the data bank at 0 —the menu runs that way— but it sets it
; anyway, because everything it touches —`temp`, the `TABLAS` tables and the
; PPU registers— is bank 0 absolute, and depending on the caller for that has
; already cost one bug in this repo.
.proc menu_hp_escribir
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
    lda menu_fila_vram, x
    clc
    adc #(MENU_HP_DESPL + MENU_HP_CIFRAS - 1)
    tay
    ; And the HP, from far RAM. An actor with more than 999 would show its
    ; three lowest digits; nobody in the game gets there.
    lda temp
    and #$00FF
    asl a
    tax
    lda f:FAR_LARGO + FAR_HP, x
    sta temp
    sep #$20
.a8
    lda #$80
    sta VMAIN
    lda #MENU_HP_CIFRAS
    sta temp + 3
cifra:
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
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0, x
    sta VMDATAL
    tya
    clc
    adc #32                     ; the lower cell
    sta VMADDL
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0 + 2, x
    sta VMDATAL
    sep #$20
.a8
    dey
    dec temp + 3
    beq listo
    lda temp
    ora temp + 1
    bne cifra
    ; What is left on the left, blank: cell 0, which in the actor's block is
    ; the one already under the digits.
blanco:
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
    bne blanco
listo:
    plb
    rtl
.endproc

; Actor A's current level, in A: the fourth byte of its `FAR_EXP` slot. An
; actor with no slot answers $FF, and the one asking knows that for that actor
; the cartridge's value holds, which is its starting level forever. Clobbers
; X; reads with `f:`, so the data bank does not matter.
.proc actor_nivel_de
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
    beq listo
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_EXP + EXP_NIVEL, x
listo:
    rts
.endproc

; Parameter Y of an actor **at its current level**: `GetBaseMaxHp` and its
; siblings, without the equipment —`eq_parametro` adds that— and without the
; `*_mod` from `ChangeParameters`, which the game does not use. Y is the order
; of `lcf.CURVES`: 0 HP, 1 SP, 2 attack, 3 defense, 4 spirit and 5 agility.
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
.proc nivel_param
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
    beq sin_ranura
    rep #$20
.a16
    and #$00FF
    pha                         ; the slot
    asl a
    asl a
    tax
    lda f:FAR_LARGO + FAR_EXP + 2, x    ; the high byte is the level
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
    lda f:nivel_fila, x
    clc
    adc 1, s
    tax
    lda f:nivel_params, x
    tax
    pla
    pla
    sep #$20
.a8
    rtl
sin_ranura:
    rep #$20
.a16
    txa
    asl a
    tax                         ; the actor times two
    cpy #2
    bcs de_los_cuatro
    cpy #1
    beq los_sp
    lda f:actor_hpmax, x
    bra listo
los_sp:
    lda f:actor_spmax, x
    bra listo
de_los_cuatro:
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
listo:
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
.proc hp_inicial_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_HP
    sta f:WMADDL
    lda #<(actor_hpmax)
    ora #(>(actor_hpmax) * 256)
    sta f:A1T0L
    lda #(ACTORES_N * 2)
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
    lda #(ACTORES_N * 2)
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
    ; and the experience and level, from `exp_inicial`: `Game_Actor` starts
    ; at `initial_level` with exactly the experience for that level.
    rep #$20
.a16
    lda #FAR_EXP
    sta f:WMADDL
    lda #<(exp_inicial)
    ora #(>(exp_inicial) * 256)
    sta f:A1T0L
    lda #(EXP_K * 4)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(exp_inicial)
    sta f:A1B0
    lda #0
    sta f:DMAP0
    lda #$80
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rtl
.endproc

; `FullHeal`, and `ChangeHP` when it adds: both are OP_HEAL, and the amount
; tells them apart. At 0 it is `FullHeal`: the HP and SP of each actor in the
; target to their maximums. It is easyrpg's `Game_Actor::FullHeal`
; (`game_actor.cpp:391`), which also does `RemoveAllStates` and restores the
; equipment's states: here there is none of that to clear, because outside
; battle states do not exist —the battle builds them and throws them away—
; and a fallen actor is just an actor with zero HP, so filling them already
; revives it. With an amount it is `ChangeHP`; see `curar_actor`.
;
; Entered from `op_heal` with Y on the operand: the actor, or 0 for the whole
; party —the `GetActors` of `game_interpreter.cpp:1539`, see `actor_de_blanco`
; in eventos.py— and the amount, 16 bits. Returns with Y after it. It lives
; **outside bank 0** for the same reason as `hp_inicial_poner`, and that is
; why everything it touches goes with `f:` or is in the direct page. Clobbers
; A, X and `temp`.
;
; It does not reuse `hp_inicial_poner` on purpose: that one fills all 61
; actors at once, and `FullHeal [0, 0]` is the party and nobody else.
; `test_full_heal_del_grupo_no_cura_a_los_de_afuera` catches it.
.proc curar
.a8
.i16
    lda [cod_ptr], y            ; the actor
    iny
    sta temp + 2
    rep #$20
.a16
    lda [cod_ptr], y            ; and the amount
    sta temp
    sep #$20
.a8
    iny
    iny
    phy
    lda temp + 2
    bne uno
    ; Up to `grupo_n` and not all four slots: the extra ones are not cleared
    ; when someone is removed, and in the test suite one showed up with 85
    ; —healing it meant writing into actor 21's SP—.
    ldx #0
ranura:
    cpx grupo_n
    bcs listo
    lda grupo, x
    phx
    jsr curar_actor
    plx
    inx
    bra ranura
listo:
    ply
    rtl
uno:
    jsr curar_actor
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
; The maximums are those of its current level, `nivel_param`, and they live on
; the stack meanwhile: `temp` is the amount and `temp + 2` the actor from
; `curar`.
.proc curar_actor
.a8
.i16
    pha                         ; the actor
    ldy #0
    jsl f:nivel_param
    phx                         ; the maximum HP
    lda 3, s
    ldy #1
    jsl f:nivel_param
    phx                         ; and the SP: stack = SP, HP, actor
    lda 5, s
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda temp
    bne sumar
    lda 3, s
    sta f:FAR_LARGO + FAR_HP, x
    lda 1, s
    sta f:FAR_LARGO + FAR_SP, x
    bra listo
sumar:
    lda f:FAR_LARGO + FAR_HP, x
    beq listo                   ; fallen: `ChangeHp` does not revive it
    clc
    adc temp
    bcs topar                   ; it wrapped around: the amount reaches $FFFF
    cmp 3, s
    bcc put
topar:
    lda 3, s
put:
    sta f:FAR_LARGO + FAR_HP, x
listo:
    pla
    pla
    sep #$20
.a8
    pla
    rts
.endproc

; `Game_Actor::ChangeExp(GetExp() + BA_T1)` for actor A: adds, caps at
; `MaxExpValue()` and levels up while it is enough. An actor with no
; experience slot gains nothing. Runs with the data bank at $7E, like the
; whole battle. Clobbers A, X, Y, `BA_T0` and `BA_T2`; `BA_T1` stays as it
; was, so whoever hands it out can add it to several.
;
; And for each level gained, `LearnLevelSkills` for that level: see
; `aprender_del_nivel`.
.proc exp_sumar
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
    bne tiene
    rts
tiene:
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
    cmp #EXP_TOPE_HI
    bcc sin_tope
    bne topar
    rep #$20
.a16
    lda FAR_EXP, x
    cmp #(EXP_TOPE_LO + 1)
    sep #$20
.a8
    bcc sin_tope
topar:
    rep #$20
.a16
    lda #EXP_TOPE_LO
    sta FAR_EXP, x
    sep #$20
.a8
    lda #EXP_TOPE_HI
    sta FAR_EXP + 2, x
sin_tope:
    ; And it levels up while it is enough: the `ChangeExp` loop, which looks at
    ; `GetNextExp(level)` —row `level` of `exp_tabla`, what it takes to reach
    ; the next one— up to `GetMaxLevel()`. A battle can raise more than one
    ; level at once, and that is RM2k's. HP and SP are not touched: leveling
    ; up does not heal, it only raises the maximum.
subir:
    ldx BA_T2
    lda f:exp_nivel_max, x
    ldx BA_T0
    cmp FAR_EXP + EXP_NIVEL, x
    beq listo                   ; at the cap
    bcc listo                   ; above the cap: does not happen, but no level up
    lda FAR_EXP + EXP_NIVEL, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    pha                         ; the level times four: its row in the curve
    lda BA_T2
    asl a
    tax
    lda f:exp_curva, x
    clc
    adc 1, s
    tax
    pla
    ; What it takes, in two halves: the low one to the stack —all three
    ; `BA_T*` are in use— and the high one in A.
    lda f:exp_tabla, x
    pha
    lda f:exp_tabla + 2, x
    ldx BA_T0
    sep #$20
.a8
    cmp FAR_EXP + 2, x          ; the high byte first
    bne alto_distinto
    rep #$20
.a16
    lda FAR_EXP, x
    cmp 1, s                    ; C if the experience is enough
    sep #$20
.a8
    ply                         ; `ply` does not touch C
    bcc listo
    bra sube
alto_distinto:
    ply
    bcs listo                   ; C: the high byte required is more than there is
sube:
    inc FAR_EXP + EXP_NIVEL, x
    lda FAR_EXP + EXP_NIVEL, x
    ply                         ; the actor, without taking it off the stack
    phy
    jsr aprender_del_nivel
    bra subir
listo:
    plx
    rts
.endproc

; `LearnLevelSkills` for a single level, A, for actor Y: sets in `FAR_HAB` the
; bit of each of its pairs that the LDB's learning table teaches at that level
; —`hab_par_nivel`—. If it already knew it nothing changes, which is
; `LearnSkill`; and what a `ChangeSkills` made it forget comes back only if it
; is taught at a level just reached, as in RM2k. Runs in battle, but
; everything it touches goes with `f:` or through the stack. Clobbers A, X
; and Y.
.proc aprender_del_nivel
.a8
.i16
    pha                         ; the level
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:hab_par_ini, x
    pha                         ; the slot of the pair being looked at: stack = slot, level
    tyx
    lda f:hab_par_n, x
    and #$00FF
    beq fin
    tay                         ; how many pairs it has left
otro:
    lda 1, s
    tax
    sep #$20
.a8
    lda f:hab_par_nivel, x
    cmp 3, s
    bne siguiente
    rep #$20
.a16
    txa
    and #$0007
    tax
    sep #$20
.a8
    lda f:mascara, x
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
    ora f:FAR_LARGO + FAR_HAB, x
    sta f:FAR_LARGO + FAR_HAB, x
siguiente:
    rep #$20
.a16
    lda 1, s
    inc a
    sta 1, s
    dey
    bne otro
fin:
    pla
    sep #$20
.a8
    pla
    rts
.endproc
