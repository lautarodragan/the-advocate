.segment "FAR"

; --- una medicina desde el menú ----------------------------------------------
;
; `Game_Party::UseItem(id, actor)` de easyrpg (`game_party.cpp:322`), que es
; `Game_Actor::IsItemUsable` —el `actor_set` del ítem— y después
; `Game_Battler::UseItem` (`game_battler.cpp:146`), más el `ConsumeItemUse` si
; sirvió y, antes de todo, el "¿queda alguno?" de `Scene_ActorTarget`. La
; elección de actor la llama con cada A sobre una medicina.
;
; Entra con A8 el actor y `eleg_flancos` el `k` del ítem, que lo deja ahí
; `items_pantalla`. Vuelve con A8 en 1 si sirvió y en 0 si no, y Z según eso.
; Se entra con `jsl`, con cualquier banco de datos: pone el $7E y lo repone.
; Se lleva X, Y y `temp`.
;
; **Un caído es un actor con cero HP**, y no por atajo: `IsDead` de easyrpg
; (`game_battler.h:995`) mira los HP y no el estado, "RPG_RT compatibility
; requires checking the death state and not hp". Fuera de la pelea este port no
; guarda estados, así que levantar a uno es el `SetHp(1)` de `RemoveStates`, y
; los demás estados de `state_set` no sacan nada: `was_used` sólo se prende si
; el actor tenía el estado.
.proc medicina_usar
.a8
.i16
    phb
    pha
    lda #$7E
    pha
    plb
    pla
    sta MED_ACTOR
    stz MED_USADO
    stz MED_REVIVIO
    stz MED_REVIVIO + 1
    ; ¿Queda alguno? Con la elección abierta se puede gastar el último y
    ; seguir apretando A.
    jsr k_en_x
    lda f:item_medicina, x
    sta MED_BANDERAS
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_id, x            ; en TABLAS, del banco 0: con `f:`
    sta MED_ID
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    bne queda
    jmp no_sirve
queda:
    ; `Game_Actor::IsItemUsable`: el bit del actor en `item_actores`, ocho
    ; bytes por ítem, el actor 1 en el bit 0 del primero.
    jsr k_en_x
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta MED_P
    lda MED_ACTOR
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc MED_P
    tax
    pla
    and #$0007
    tay
    sep #$20
.a8
    lda f:item_actores, x
    cpy #0
    beq bit_listo
correr:
    lsr a
    dey
    bne correr
bit_listo:
    and #1
    bne puede
    jmp no_sirve
puede:
    ; Los máximos de su nivel de ahora, como `FullHeal`.
    lda MED_ACTOR
    ldy #0
    jsl f:nivel_param
    stx MED_HP_MAX
    lda MED_ACTOR
    ldy #1
    jsl f:nivel_param
    stx MED_SP_MAX
    ; `hp_change = recover_hp_rate * GetMaxHp() / 100 + recover_hp`, y lo
    ; mismo con los SP. Topado en $FFFF, que es "más de lo que falta".
    jsr k_en_x
    lda f:item_cura_rate, x
    ldx MED_HP_MAX
    jsr por_ciento
    sta MED_HP
    jsr k_en_x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_cura_hp, x
    clc
    adc MED_HP
    bcc hp_listo
    lda #$FFFF
hp_listo:
    sta MED_HP
    sep #$20
.a8
    jsr k_en_x
    lda f:item_cura_sp_rate, x
    ldx MED_SP_MAX
    jsr por_ciento
    sta MED_SP
    jsr k_en_x
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:item_cura_sp, x
    clc
    adc MED_SP
    bcc sp_listo
    lda #$FFFF
sp_listo:
    sta MED_SP
    ; Muerto o no. Desde acá X es el actor por dos, para los HP y los SP.
    lda MED_ACTOR
    and #$00FF
    asl a
    tax
    lda FAR_HP, x
    sep #$20
.a8
    bne vivo
    ; Muerto: sólo sirve si saca el estado de muerto, y sacarlo es 1 HP.
    lda MED_BANDERAS
    and #2
    bne levantar
    jmp no_sirve
levantar:
    rep #$20
.a16
    lda #1
    sta FAR_HP, x
    sta MED_REVIVIO
    sep #$20
.a8
    sta MED_USADO
    bra curar_hp
vivo:
    lda MED_BANDERAS
    and #1
    beq curar_hp
    jmp no_sirve                ; `ko_only` sobre uno en pie
curar_hp:
    ; `if (hp_change > 0 && !HasFullHp()) ChangeHp(hp_change - revived)`.
    ; `ChangeHp` topa en el máximo con el `SetHp` de adentro, y nunca baja
    ; de 1 porque acá nada resta.
    rep #$20
.a16
    lda MED_HP
    beq curar_sp
    lda FAR_HP, x
    cmp MED_HP_MAX
    bcs curar_sp                ; lleno
    lda MED_HP
    sec
    sbc MED_REVIVIO
    clc
    adc FAR_HP, x
    bcs hp_topado
    cmp MED_HP_MAX
    bcc hp_poner
hp_topado:
    lda MED_HP_MAX
hp_poner:
    sta FAR_HP, x
    sep #$20
.a8
    lda #1
    sta MED_USADO
    rep #$20
.a16
curar_sp:
    ; `if (sp_change > 0 && !HasFullSp()) ChangeSp(sp_change)`.
    lda MED_SP
    beq gastar
    lda FAR_SP, x
    cmp MED_SP_MAX
    bcs gastar
    clc
    adc MED_SP
    bcs sp_topado
    cmp MED_SP_MAX
    bcc sp_poner
sp_topado:
    lda MED_SP_MAX
sp_poner:
    sta FAR_SP, x
    sep #$20
.a8
    lda #1
    sta MED_USADO
gastar:
    ; `ConsumeItemUse`, si sirvió y el ítem tiene usos. Uno por vez: RM2k
    ; cuenta los usos de un ítem de varios, y este port no, pero las medicinas
    ; de este juego son todas de uno.
    sep #$20
.a8
    lda MED_USADO
    beq listo
    lda MED_BANDERAS
    and #4
    beq listo
    ldx MED_ID
    lda FAR_ITEMS, x
    dec a
    sta FAR_ITEMS, x
    bra listo
no_sirve:
    stz MED_USADO
listo:
    plb
    lda f:FAR_LARGO + MED_USADO ; después del `plb`: las banderas son de esto
    rtl

; El `k` del ítem, de `eleg_flancos` a X. Sólo A y X.
k_en_x:
    rep #$20
.a16
    lda eleg_flancos
    and #$00FF
    tax
    sep #$20
.a8
    rts

; A8 el tanto por ciento y X el máximo: vuelve con A16 = tanto * máximo / 100,
; la división entera de easyrpg. El producto se arma en 24 bits —un máximo de
; SP llega a 999, y por 100 no entra en dieciséis— y se divide restando, de a
; un bit. Se lleva X e Y.
por_ciento:
.a8
    sta f:WRMPYA
    stx MED_P
    lda MED_P
    sta f:WRMPYB                ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta MED_R                   ; tanto por el byte bajo
    sep #$20
.a8
    lda MED_P + 1
    sta f:WRMPYB                ; WRMPYA sigue siendo el tanto
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL                ; tanto por el byte alto, que pesa 256
    xba
    pha
    and #$FF00
    clc
    adc MED_R
    sta MED_P
    pla
    and #$00FF
    adc #0                      ; el acarreo de la suma de arriba
    sta MED_P + 2
    stz MED_R
    ldy #32
dividir:
    asl MED_P
    rol MED_P + 2
    rol MED_R
    lda MED_R
    sec
    sbc #100
    bcc no_entra
    sta MED_R
    inc MED_P                   ; el bit del cociente que acaba de entrar
no_entra:
    dey
    bne dividir
    lda MED_P
    rts
.endproc

