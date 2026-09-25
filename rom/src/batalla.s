.segment "FAR"

; El xorshift de la pelea, el mismo que `eventos.azar_siguiente` y que
; `lluvia_azar`, pero sobre `BA_SEM`, que tiene **semilla propia**: pelear no
; le corre el azar del mapa, que es lo que la referencia de pixeles supone
; cuando dice que una batalla no cuesta ningún tick.
.proc ba_azar
.a16
.i16
    lda BA_SEM
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor BA_SEM
    sta BA_SEM
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor BA_SEM
    sta BA_SEM
    xba
    and #$FF00
    eor BA_SEM
    sta BA_SEM
    rts
.endproc

; `temp` dividido `temp + 2`: el cociente queda en `temp` y el resto en
; `comp_and`. Desplazar y restar, dieciséis vueltas.
;
; Existe porque el divisor del hardware es de **ocho bits** y acá hay dos
; divisiones que no entran: el ajuste de acierto por agilidad divide por dos
; veces la agilidad —hasta 600 en este juego— y la varianza del daño, por el
; ajuste, que llega a lo mismo. Hacerlas con el divisor del hardware pedía
; recortar, y recortar cambia el número: los dos lados dejarían de dar igual.
;
; **El divisor tiene que ser menor que 32768**: el resto entra por un `rol` y
; uno más grande se saldría por arriba. Ninguno de los que se usan se acerca.
.proc ba_div
.a16
.i16
    stz comp_and
    ldy #16
lazo:
    asl temp
    rol comp_and
    lda comp_and
    sec
    sbc temp + 2
    bcc no_entra
    sta comp_and
    inc temp                    ; el bit del cociente que acaba de entrar
no_entra:
    dey
    bne lazo
    lda temp
    rts
.endproc

; A16 = n; vuelve con A16 = un número de 0 a n, inclusive. Es
; `Rand::GetRandomNumber(0, n)` de easyrpg con nuestro azar: ver
; `batalla.Azar.hasta`.
.proc ba_hasta
.a16
.i16
    inc a
    sta temp + 2
    jsr ba_azar
    sta temp
    jsr ba_div
    lda comp_and
    rts
.endproc

; A8 = el tanto por ciento; vuelve con A8 en 1 si salió y Z puesto según eso.
; Es `Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.
.proc ba_pct
.a8
.i16
    sta BA_T2
    rep #$20
.a16
    lda #99
    jsr ba_hasta
    sta BA_T0
    lda BA_T2
    and #$00FF
    cmp BA_T0                 ; C=1 si el tanto >= la tirada
    sep #$20
.a8
    beq no                      ; iguales: la tirada no es menor
    bcc no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 por el byte de `BA_T2`, en A16. Dos productos del hardware, que es de
; ocho por ocho.
;
; Los registros van con `f:` y no absolutos: acá el banco de datos es $7E, así
; que un `sta WRMPYA` pelado escribiría en la WRAM y el producto saldría de un
; registro que nadie tocó. Costó una tarde y se veía como que todos los golpes
; fallaban.
.proc ba_mul
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta comp_or23
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    xba                         ; por 256: el byte alto pesa eso
    and #$FF00
    clc
    adc comp_or23
    rts
.endproc

; A8 a X, con el byte de arriba en cero. Existe para no escribir `ldx` sobre
; una variable de un byte: con los índices de dieciséis se llevaría el byte de
; al lado, que es la trampa que AGENTS.md nombra.
.proc ba_ax
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = el combatiente; X = su desplazamiento adentro de `BA_UNO`. Son 40 bytes,
; o sea treinta y dos más ocho: dos desplazamientos y una suma, sin tabla.
.proc ba_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por ocho
    sta temp + 2
    asl a
    asl a                       ; por treinta y dos
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = el combatiente; Z=0 si está vivo, o sea si la ranura existe y le quedan
; HP. **No usa `pl*`**: la trampa de siempre.
.proc ba_vivo
.a8
.i16
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq no
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sep #$20
.a8
    beq no
    lda #1
    rts
no:
    lda #0
    rts
.endproc


; --- armar la pelea -------------------------------------------------------
;
; El grupo en las ranuras 0 a 3 y la tropa en las 4 a 11. Que el lugar sea fijo
; y no una lista compactada es lo que hace que un muerto se siga viendo en su
; renglón, como en la pantalla.

; El parámetro `A` —0 ataque, 1 defensa, 3 agilidad— del actor de `BA_S0`, en
; `BA_T2`. Va por memoria y no por el acumulador a propósito: una rutina que
; entra con A de ocho y sale con A de dieciséis deja al ensamblador creyendo
; otra cosa, y el `lda #1` que viniera detrás se comería el opcode siguiente.
; Ya pasó, y lo que se veía era un ataque de 999. Es `eq_parametro`, la misma que usa la pantalla de equipo: el del nivel
; más lo que suma cada pieza, topado en [1, 999]. `comp_col + 1` en cero es "no
; se está eligiendo nada", el camino simple de `eq_efectivo`. **Se lleva X.**
.proc ba_param
.a8
.i16
    sta comp_or01 + 2
    stz comp_or01 + 3
    stz comp_col + 1
    lda BA_S0
    sta comp_char
    stz comp_char + 1
    jsl f:ba_t_param
    rep #$20
.a16
    lda comp_dup
    sta BA_T2
    sep #$20
.a8
    rts
.endproc

.proc ba_armar
.a8
.i16
    ; Todas las ranuras vacías: la pantalla y los barridos miran `BAF_HAY`.
    lda #0
otra_ranura:
    pha
    jsr ba_x
    lda #0
    sta BA_UNO + BA_FLAGS, x
    pla
    inc a
    cmp #BA_COMB_MAX
    bcc otra_ranura
    stz BA_NACT
    stz BA_NENE

    ; --- el grupo ---
    lda #0
    sta BA_S1                 ; el lugar en el grupo
otro_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    cmp grupo_n
    sep #$20
.a8
    bcc hay_lugar
    jmp grupo_listo
hay_lugar:
    lda BA_S1
    cmp #BA_GRUPO_MAX
    bcc hay_ranura
    jmp grupo_listo
hay_ranura:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    bne con_actor
    jmp siguiente_actor         ; una ranura del grupo sin nadie
con_actor:
    sta BA_S0                 ; el actor del LDB
    ldy #0
    jsl f:nivel_param
    stx BA_S2                 ; los HP máximos de su nivel
    ; Todo lo suyo a las palabras de paso: `ba_param` se lleva X, así que
    ; primero se junta y después se escribe con X puesto de una sola vez.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:actor_txt, x
    sta BA_S3                 ; y el número de texto de su nombre
    lda FAR_HP, x
    sta BA_S4                 ; los HP que trae la partida
    sep #$20
.a8
    lda #0
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S5                   ; el ataque
    sep #$20
.a8
    lda #1
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S6                   ; la defensa
    sep #$20
.a8
    lda #3
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_T0                   ; la agilidad
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S2
    sta BA_UNO + BA_HPMAX, x
    lda BA_S4
    sta BA_UNO + BA_HP, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_S3
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda #BA_ACIERTO_ACTOR
    sta BA_UNO + BA_HIT, x
    lda #0
    sta BA_UNO + BA_CRIT, x   ; ningún actor del ABL tiene golpe crítico
    lda BA_S0
    sta BA_UNO + BA_NUMERO, x
    lda #(BAF_HAY | BAF_ACTOR)
    sta BA_UNO + BA_FLAGS, x
    ; Y lo que las habilidades necesitan: los SP —que vienen de la partida,
    ; como los HP— y el espíritu, que hasta el 2026-09-13 no se leía porque
    ; ninguna cuenta lo pedía. Va en un segundo paso porque `ba_param` se
    ; lleva X y hay que volver a ponerlo.
    lda #2
    jsr ba_param                ; el espíritu, `eq_parametro` como los otros
    rep #$20
.a16
    sep #$20
.a8
    lda BA_S0
    ldy #1
    jsl f:nivel_param
    stx BA_S3                 ; los SP máximos de su nivel
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda FAR_SP, x
    sta BA_S4
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_UNO + BA_SP, x
    lda BA_S3
    sta BA_UNO + BA_SPMAX, x
    lda BA_T2
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_S5
    sta BA_UNO + BA_BATK, x
    lda BA_S6
    sta BA_UNO + BA_BDEF, x
    lda BA_T0
    sta BA_UNO + BA_BAGI, x
    lda #0                      ; sin modificadores: la pelea recién empieza
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    inc BA_NACT
siguiente_actor:
    inc BA_S1
    jmp otro_actor
grupo_listo:

    ; --- la tropa ---
    ; El bytecode lleva el número de RM2k, así que hay que buscarlo. Una tropa
    ; que este cartucho no lleve es una pelea sin enemigos, y `batalla_correr`
    ; la gana sola: es lo mismo que hace el conversor con un tema que no entró.
    lda #$FF
    sta BA_TROPA_K
    lda #0
    sta BA_S1
busca:
    lda BA_S1
    cmp #TROPAS_N
    bcs sin_tropa
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    asl a
    tax
    lda f:tropa_id, x
    cmp BA_TROPA
    sep #$20
.a8
    beq la_tengo
    inc BA_S1
    bra busca
sin_tropa:
    rts
la_tengo:
    lda BA_S1
    sta BA_TROPA_K              ; para `escena_tropa_fondo`
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_n, x
    sta BA_S2                 ; cuántos miembros
    lda f:tropa_ini, x
    sta BA_S3                 ; dónde arranca su lista
    lda #0
    sta BA_S1                 ; el lugar en la tropa
otro_enemigo:
    lda BA_S1
    cmp BA_S2
    bcc hay_miembro
    jmp tropa_lista
hay_miembro:
    cmp #BA_ENEMIGOS_MAX
    bcc hay_ranura_ene
    jmp tropa_lista
hay_ranura_ene:
    rep #$20
.a16
    lda BA_S1
    clc
    adc BA_S3
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_miembro, x      ; el enemigo, como lugar en las tablas
    sta BA_S0
    ; Como con el actor: primero se junta todo y después se escribe, porque el
    ; índice largo es X y hay dos tablas que recorrer con él.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:enemigo_hp, x
    sta BA_S4
    lda f:enemigo_atk, x
    sta BA_S5
    lda f:enemigo_def, x
    sta BA_S6
    lda f:enemigo_agi, x
    sta BA_T0
    lda f:enemigo_txt, x
    sta BA_T1
    sep #$20
.a8
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enemigo_hit, x
    sta BA_T2
    lda f:enemigo_crit, x
    sta BA_T2 + 1
    lda BA_S1
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_UNO + BA_HP, x
    sta BA_UNO + BA_HPMAX, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_T1
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda BA_T2
    sta BA_UNO + BA_HIT, x
    lda BA_T2 + 1
    sta BA_UNO + BA_CRIT, x
    lda BA_S1
    sta BA_UNO + BA_NUMERO, x
    lda #BAF_HAY
    sta BA_UNO + BA_FLAGS, x
    ; Lo de las habilidades: los SP, el espíritu y las cuatro bases. Un enemigo
    ; de este port no usa ninguna —`CreateEnemyActions` sólo le da el ataque
    ; básico— pero **las recibe**: Mental Hack le baja la defensa y el
    ; espíritu, y para eso hacen falta la base y el modificador.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    phx
    tax
    lda f:enemigo_sp, x
    sta BA_T0
    lda f:enemigo_spi, x
    sta BA_T1
    plx
    lda BA_T0
    sta BA_UNO + BA_SP, x
    sta BA_UNO + BA_SPMAX, x
    lda BA_T1
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_UNO + BA_ATK, x
    sta BA_UNO + BA_BATK, x
    lda BA_UNO + BA_DEF, x
    sta BA_UNO + BA_BDEF, x
    lda BA_UNO + BA_AGI, x
    sta BA_UNO + BA_BAGI, x
    lda #0
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    inc BA_NENE
    inc BA_S1
    jmp otro_enemigo
tropa_lista:
    rts
.endproc

; --- el golpe -------------------------------------------------------------
;
; `Normal::vExecute` de easyrpg: **tres tiros en este orden** —acierto,
; crítico y varianza— y el del crítico se hace aunque la chance sea cero. Ese
; orden es el contrato con `tools/port/batalla.py`: cambiarlo de un lado desfasa el
; azar del otro y no se ve hasta que un golpe da distinto.
;
; La fuente en `BA_MQUIEN` y el blanco en `BA_MBLA`. Deja el daño en
; `BA_MDANO`, con $FFFF si el golpe falló, y le baja los HP al blanco.
.proc ba_atacar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; el desplazamiento de la fuente
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; y el del blanco
    sep #$20
.a8

    ; --- el acierto, con el ajuste por agilidad ---
    ldx BA_S0
    lda #100
    sec
    sbc BA_UNO + BA_HIT, x      ; X es el desplazamiento, ya de dieciséis
    sta BA_T2                   ; 100 - acierto, que es el byte del producto
    rep #$20
.a16
    lda BA_UNO + BA_AGI, x
    bne agi_hay
    lda #1                      ; `max(1, GetAgi())` de CalcToHitAgiAdjustment
agi_hay:
    sta BA_S2                   ; la agilidad de la fuente
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_S2
    jsr ba_mul                  ; (100 - acierto) * (agiF + agiB)
    sta BA_S3
    lda BA_S2
    asl a
    sta temp + 2                ; el divisor: dos veces la agilidad
    ; Hacia arriba, que es lo que hace el truncado de easyrpg sobre `100 - x`:
    ; ver `batalla.acierto_por_agilidad`.
    lda BA_S3
    clc
    adc temp + 2
    dec a
    sta temp
    jsr ba_div
    sta BA_S3
    lda #100
    sec
    sbc BA_S3
    bpl acierto_listo
    lda #0
acierto_listo:
    sep #$20
.a8
    jsr ba_pct
    sta BA_S4                   ; 1 si pegó
    beq crit_cero
    lda BA_S0
    jsr ba_ax
    lda BA_UNO + BA_CRIT, x
    bra crit_tira
crit_cero:
    lda #0
crit_tira:
    jsr ba_pct
    sta BA_S5                   ; 1 si fue crítico
    lda BA_S4
    bne pega
    rep #$20
.a16
    lda #$FFFF
    sta BA_MDANO
    sep #$20
.a8
    rts

    ; --- el daño: max(0, atk / 2 - def / 4) ---
pega:
    rep #$20
.a16
    ldx BA_S0
    lda BA_UNO + BA_ATK, x
    lsr a
    sta BA_S2
    ldx BA_S1
    lda BA_UNO + BA_DEF, x
    lsr a
    lsr a
    cmp BA_S2
    bcc hay_dano
    lda #0
    sta BA_S2
    bra sin_varianza
hay_dano:
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    sta BA_S2
    sep #$20
.a8
    lda BA_S5
    beq sin_critico
    rep #$20
.a16
    ; El crítico triplica: `dmg *= 3`.
    lda BA_S2
    asl a
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
sin_critico:
    rep #$20
.a16
    ; La varianza de `VarianceAdjustEffect` con var = 4:
    ;     adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2
    lda BA_S2
    asl a
    asl a
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne ajuste_listo
    lda #1
ajuste_listo:
    sta BA_S3
    jsr ba_hasta                ; A16 sigue siendo el ajuste
    clc
    adc BA_S2
    sta BA_S2
    lda BA_S3
    lsr a
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    bpl varianza_listo
    lda #0                      ; no puede pasar: 0,8 por el daño es positivo
varianza_listo:
    sta BA_S2
sin_varianza:
    sep #$20
.a8
    ; El que se defiende recibe la mitad: `AdjustDamageForDefend`.
    ldx BA_S1
    lda BA_UNO + BA_FLAGS, x
    and #BAF_DEF
    beq sin_defensa
    rep #$20
.a16
    lda BA_S2
    lsr a
    sta BA_S2
    sep #$20
.a8
sin_defensa:
    rep #$20
.a16
    lda BA_S2
    cmp #(BA_DANO_MAX + 1)
    bcc dano_listo
    lda #BA_DANO_MAX
dano_listo:
    sta BA_MDANO
    ldx BA_S1
    lda BA_UNO + BA_HP, x
    sec
    sbc BA_MDANO
    bpl hp_listo
    lda #0
hp_listo:
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; --- el turno -------------------------------------------------------------

; Las acciones de los enemigos: cada uno vivo ataca a un actor vivo al azar.
; Es `CreateEnemyActions`, con la única acción que los enemigos de las dos
; peleas de la intro tienen —"básica: atacar"—. **Un tiro por enemigo**, y va
; antes del orden de ejecución, que es como lo llama `SelectNextActor`.
;
; Si no queda ningún actor vivo se corta y los enemigos que faltaban se quedan
; sin acción, que es el `break` de `batalla.acciones_de_los_enemigos`: sin eso
; los dos lados tirarían distinta cantidad de veces.
.proc ba_acciones_enemigas
.a8
.i16
    lda #BA_GRUPO_MAX
    sta BA_S0
otro:
    lda BA_S0
    cmp #BA_COMB_MAX
    bcs listo
    lda BA_S0
    jsr ba_vivo
    beq siguiente
    ; Los actores vivos, en una lista, para elegir uno.
    lda #0
    sta BA_S1                   ; cuántos hay
    sta BA_S2
busca:
    lda BA_S2
    cmp #BA_GRUPO_MAX
    bcs buscados
    lda BA_S2
    jsr ba_vivo
    beq no_vive
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_CAND, x
    inc BA_S1
no_vive:
    inc BA_S2
    bra busca
buscados:
    lda BA_S1
    beq listo                   ; no queda nadie a quien pegarle
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    dec a
    jsr ba_hasta
    tax
    sep #$20
.a8
    lda BA_CAND, x
    sta BA_T0                   ; el blanco elegido
    lda BA_S0
    asl a
    jsr ba_ax                   ; dos bytes de acción por combatiente
    lda #BA_ATACAR
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACC
    jsr ba_ax
    lda BA_S0
    sta BA_EJEC, x
    inc BA_NACC
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; El orden de ejecución: `agi + rand(0, agi / 4 + 3)` por cada uno que actúa,
; de mayor a menor y con un orden **estable**, que es lo que hace `std::sort`
; sobre una lista que ya viene apilada en el orden en que se empujó. Es
; `CreateExecutionOrder`. **Un tiro por acción**, en ese mismo orden: primero
; el grupo y después la tropa.
.proc ba_orden_ejecucion
.a8
.i16
    lda #0
    sta BA_S0
tira:
    lda BA_S0
    cmp BA_NACC
    bcs tirados
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; su desplazamiento
    lda BA_UNO + BA_AGI, x
    lsr a
    lsr a
    clc
    adc #3
    jsr ba_hasta
    sta BA_T0
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_T0
    sta BA_UNO + BA_SORT, x
    sep #$20
.a8
    inc BA_S0
    bra tira
tirados:
    ; Y el orden, por inserción: son doce como mucho, y queda **estable** si
    ; sólo se corre al que tiene arriba a uno estrictamente menor.
    lda #1
    sta BA_S0
afuera:
    lda BA_S0
    cmp BA_NACC
    bcs ordenado
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    sta BA_S2                   ; el que se acomoda
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    sta BA_S3
    sep #$20
.a8
    lda BA_S0
    sta BA_S1
adentro:
    lda BA_S1
    beq poner
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    cmp BA_S3
    sep #$20
.a8
    bcs poner                   ; el de arriba es mayor o igual: se queda ahí
    lda BA_S1
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    inx
    sta BA_EJEC, x
    dec BA_S1
    bra adentro
poner:
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_EJEC, x
    inc BA_S0
    bra afuera
ordenado:
    rts
.endproc

; --- la pantalla ----------------------------------------------------------
;
; De texto y sobre negro, en la misma grilla de 32 por 28 celdas que el equipo
; y la tienda. La geometría sale de `tools/port/pantallas.py` y el conversor emite
; las posiciones, así que la escribe **uno solo de los dos lados**. Arriba los enemigos, abajo el grupo, y el último renglón es o el
; menú de órdenes o los dos renglones del mensaje.

; `BA_T1` = A16 + `BA_S0` por lo que mide un renglón: dónde arranca el renglón
; número `BA_S0` de la lista que empieza en A16.
.proc ba_fila
.a16
.i16
    sta BA_T2
    lda BA_S0
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc BA_T2
    sta BA_T1
    rts
.endproc

; El cursor de escritura en la columna A16 del renglón `BA_T1`.
.proc ba_ir
.a16
.i16
    clc
    adc BA_T1
    sta eleg_tabla
    rts
.endproc

; El renglón de un combatiente: su nombre y sus HP, en gris si está muerto.
; A8 = el combatiente, `BA_T1` = dónde arranca su renglón, y el bit 0 de
; `BA_CONMAX` dice si además van los HP máximos —o sea si es del grupo—.
.proc ba_renglon
.a8
.i16
    sta BA_S4
    jsr ba_vivo
    beq muerto
    lda #0
    bra variante
muerto:
    lda #1
variante:
    sta temp + 1
    lda BA_S4
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S5                   ; su desplazamiento, que `pant_texto` pisa
    lda #BA_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_NOMBRE_ANCHO
    sta comp_dup + 3
    ldx BA_S5
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; "HP"
    rep #$20
.a16
    lda #BA_HP_DX
    jsr ba_ir
    sep #$20
.a8
    ldx #BA_TXT_HP
    jsl f:ba_t_texto
    ; y el número, de tres cifras, topado en 999 como en la referencia
    rep #$20
.a16
    lda #BA_HP_NUM_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HP, x
    cmp #1000
    bcc hp_cabe
    lda #999
hp_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    lda BA_CONMAX
    and #$01
    bne con_maximo
    rts
con_maximo:
    rep #$20
.a16
    lda #BA_BARRA_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$2F                    ; la barra entre los HP y su máximo
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda #BA_HPMAX_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HPMAX, x
    cmp #1000
    bcc max_cabe
    lda #999
max_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    rts
.endproc

; El cursor ">" al principio del renglón `BA_T1`.
.proc ba_cursor
.a8
.i16
    stz temp + 1
    rep #$20
.a16
    lda #BA_CURSOR_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$3E                    ; el cursor
    jsl f:ba_t_glifo
    rts
.endproc

; Un número sin espacios adelante, en `BA_T0`, donde diga `eleg_tabla`. Es lo
; que hace easyrpg al armar el mensaje de daño, que pega el número al nombre
; sin rellenar; `pant_numero` rellena, así que hay que decirle el ancho justo.
.proc ba_numero_justo
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    sta comp_dup
    ldx #1
    cmp #10
    bcc ancho_listo
    ldx #2
    cmp #100
    bcc ancho_listo
    ldx #3
ancho_listo:
    sep #$20
.a8
    txa                         ; el ancho: con M en 8 sólo viaja el byte bajo
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_numero
    rts
.endproc

; El nombre del combatiente A8 donde diga `eleg_tabla`, entero.
.proc ba_nombre
.a8
.i16
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; Un término del juego —X ya puesto— donde diga `eleg_tabla`, entero.
.proc ba_termino
.a8
.i16
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; Los dos renglones del mensaje, según `BA_MTIPO`. Todas las palabras salen
; del LDB —`attacking`, `enemy_damaged`, `victory`...— y se arman como
; `game_message_terms.cpp`: el nombre pegado al término, y en el de daño el
; número en el medio. Ninguna es nuestra.
