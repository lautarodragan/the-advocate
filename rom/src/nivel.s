.segment "FAR"

; --- el nivel y el máximo en el menú -------------------------------------------
;
; Hasta el 2026-09-21 los dos eran tiras del cartucho, compuestas al convertir
; con el nivel de arranque: no cambiaban nunca, así que no hacía falta más.
; Desde que se sube de nivel, se componen acá en `EXP_TEXTO` con lo mismo que
; decían —`titulo.texto_de_nivel` y `titulo.texto_de_maximo`— y el menú los
; escribe con `ranura_texto_escribir` igual que antes: sólo cambia a dónde
; apunta `msg_ptr`. Con el nivel de arranque dan exactamente las mismas
; letras que las tiras, que es lo que deja a las goldens del menú quietas.
;
; Los tres entran con el actor en A, dejan `msg_ptr` apuntando al texto y
; **dejan Y como estaba**, que es la celda donde el que llama va a escribir.
; Un actor sin ranura de experiencia sigue con su tira del cartucho.

; A16 —menos de mil— en tres cifras de 0 a 9, en `EXP_TEXTO + 5`, `+ 6` y
; `+ 7`. Se lleva A y X; entra y sale con A de dieciséis.
.proc tres_cifras
.a16
.i16
    ldx #0
centenas:
    cmp #100
    bcc hay_centenas
    sbc #100                    ; C viene de la comparación
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

; `msg_ptr` a la tira del cartucho del actor A, corrida X bytes: lo mismo que
; `ranura_texto_de` del banco 0, para los que no tienen ranura. Se lleva A.
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
    asl a                       ; RANURA_TEXTO_ANCHO bytes por actor
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

; `msg_ptr` a `EXP_TEXTO`.
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

; El nivel A8 como "%2d" en `EXP_TEXTO`: la decena o un espacio, y la unidad.
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

; El nivel de ahora del actor A.
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

; El nivel que el actor A tenía **en la partida de la ranura `ranura`**, leído
; de su SRAM: la pantalla de ranuras muestra cada partida como quedó, no como
; está la de ahora. `FAR_EXP` es el último renglón de `partida_tabla`, así que
; en la ranura cae `EXP_K * 4` bytes antes del final.
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
    pha                         ; la ranura de experiencia por cuatro
    lda ranura
    and #$00FF
    xba
    asl a
    asl a
    asl a                       ; la ranura de SRAM por SRAM_STRIDE
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

; Los HP máximos del nivel de ahora del actor A, como "/%d" completado a
; `MENU_MAX_CIFRAS` con espacios: `titulo.texto_de_maximo`.
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
    bra con_decena              ; con centena la decena va aunque sea cero
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

; El parámetro Y de un actor **a su nivel de ahora**: `GetBaseMaxHp` y sus
; hermanas, sin el equipo —eso lo suma `eq_parametro`— y sin los `*_mod` de
; `ChangeParameters`, que el juego no usa. Y es el orden de `lcf.CURVAS`: 0 los
; HP, 1 los SP, 2 el ataque, 3 la defensa, 4 el espíritu y 5 la agilidad.
;
; Entra con el actor en A y devuelve el valor en X. **Se lleva A e Y**, y no
; toca la página directa: los que la llaman —la pantalla de equipo, la pelea,
; `FullHeal`— la tienen ocupada cada uno con otra cosa, así que las cuentas van
; por la pila. Todo lo que lee va con `f:`, así que el banco de datos da igual.
;
; Un actor sin ranura de experiencia —uno que no puede entrar al grupo— no
; sube nunca, y lo suyo sale de las tablas de su nivel inicial, que son las de
; siempre.
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
    pha                         ; la ranura
    asl a
    asl a
    tax
    lda f:FAR_LARGO + FAR_EXP + 2, x    ; el byte alto es el nivel
    xba
    and #$00FF
    dec a
    asl a
    pha                         ; (nivel - 1) * 2, con la ranura debajo
    lda 3, s
    asl a
    adc 3, s                    ; la ranura por tres: el `asl` dejó C en cero
    asl a
    sta 3, s                    ; y por seis, que es su primera fila
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
    tax                         ; el actor por dos
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
    asl a                       ; el actor por ocho: cuatro palabras cada uno
    pha
    tya
    asl a
    clc
    adc 1, s
    tax
    pla
    lda f:actor_params - 4, x   ; `actor_params` arranca en el ataque, el 2
listo:
    tax
    sep #$20
.a8
    rtl
.endproc

; `FullHeal`, y `ChangeHP` cuando suma: los dos son OP_HEAL, y los separa la
; cantidad. En 0 es `FullHeal`: los HP y los SP de cada actor del blanco a sus
; máximos. Es `Game_Actor::FullHeal` de easyrpg (`game_actor.cpp:391`), que
; además `RemoveAllStates` y repone los estados del equipo: acá no hay nada de
; eso que limpiar, porque fuera de pelea los estados no existen —la pelea los
; arma y los tira— y un caído es sólo un actor con cero HP, así que llenarlos
; ya lo levanta. Con cantidad es `ChangeHP`; ver `curar_actor`.
;
; Se entra desde `op_heal` con Y en el operando: el actor o 0 por todo el grupo
; —el `GetActors` de `game_interpreter.cpp:1539`, ver `actor_de_blanco` en
; eventos.py— y la cantidad, de 16 bits. Se vuelve con Y después de ella. Vive
; **fuera del banco 0** por lo mismo que `hp_inicial_poner`, y por eso todo lo
; que toca va con `f:` o es de la página directa. Se lleva A, X y `temp`.
;
; No reusa `hp_inicial_poner` a propósito: aquélla llena a los 61 actores de
; una, y `FullHeal [0, 0]` es el grupo y nadie más. Lo cobra
; `test_full_heal_del_grupo_no_cura_a_los_de_afuera`.
.proc curar
.a8
.i16
    lda [cod_ptr], y            ; el actor
    iny
    sta temp + 2
    rep #$20
.a16
    lda [cod_ptr], y            ; y la cantidad
    sta temp
    sep #$20
.a8
    iny
    iny
    phy
    lda temp + 2
    bne uno
    ; Hasta `grupo_n` y no las cuatro ranuras: las de más no se limpian al
    ; sacar a alguien, y en la tanda se vio una con 85 —curarlo era escribir
    ; en los SP del actor 21—.
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

; El actor A: a sus máximos con `temp` en 0, o `temp` HP más. Se lleva X e Y.
;
; Lo segundo es `Game_Battler::ChangeHp` (`game_battler.cpp:480`): a un caído
; no lo toca —ahí es `IsDead`, acá cero HP, que fuera de pelea es lo mismo— y
; lo que pase del máximo se topa, que es el `SetHp` de adentro. Los SP no.
;
; Los máximos son los de su nivel de ahora, `nivel_param`, y viven en la pila
; mientras tanto: `temp` es la cantidad y `temp + 2` el actor de `curar`.
.proc curar_actor
.a8
.i16
    pha                         ; el actor
    ldy #0
    jsl f:nivel_param
    phx                         ; los HP máximos
    lda 3, s
    ldy #1
    jsl f:nivel_param
    phx                         ; y los SP: pila = SP, HP, actor
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
    beq listo                   ; caído: `ChangeHp` no lo levanta
    clc
    adc temp
    bcs topar                   ; dio la vuelta: la cantidad llega a $FFFF
    cmp 3, s
    bcc poner
topar:
    lda 3, s
poner:
    sta f:FAR_LARGO + FAR_HP, x
listo:
    pla
    pla
    sep #$20
.a8
    pla
    rts
.endproc

; `Game_Actor::ChangeExp(GetExp() + BA_T1)` para el actor A: suma, topa en
; `MaxExpValue()` y sube de nivel mientras alcance. Un actor sin ranura de
; experiencia no gana nada. Corre con el banco de datos en $7E, como toda la
; pelea. Se lleva A, X, Y, `BA_T0` y `BA_T2`; `BA_T1` queda como estaba, así
; el que reparte la puede sumar a varios.
;
; Y por cada nivel que sube, `LearnLevelSkills` de ese nivel: ver
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
    phx                         ; el actor, para lo que aprenda al subir
    rep #$20
.a16
    and #$00FF
    sta BA_T2                   ; la ranura
    asl a
    asl a
    sta BA_T0                   ; y su desplazamiento en `FAR_EXP`
    tax
    lda FAR_EXP, x
    clc
    adc BA_T1
    sta FAR_EXP, x
    sep #$20
.a8
    lda FAR_EXP + 2, x          ; el acarreo de la suma de arriba sigue en C
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
    ; Y sube mientras alcance: el lazo de `ChangeExp`, que mira
    ; `GetNextExp(nivel)` —la fila `nivel` de `exp_tabla`, lo que pide pasar
    ; al siguiente— hasta el `GetMaxLevel()`. Una pelea puede subir más de un
    ; nivel de una vez, y eso es de RM2k. Los HP y los SP no se tocan: subir
    ; de nivel no cura, sólo sube el máximo.
subir:
    ldx BA_T2
    lda f:exp_nivel_max, x
    ldx BA_T0
    cmp FAR_EXP + EXP_NIVEL, x
    beq listo                   ; en el tope
    bcc listo                   ; más arriba del tope: no pasa, pero no sube
    lda FAR_EXP + EXP_NIVEL, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    pha                         ; el nivel por cuatro: su fila en la curva
    lda BA_T2
    asl a
    tax
    lda f:exp_curva, x
    clc
    adc 1, s
    tax
    pla
    ; Lo que pide, en dos mitades: la baja a la pila —`BA_T*` están las tres
    ; ocupadas— y la alta en A.
    lda f:exp_tabla, x
    pha
    lda f:exp_tabla + 2, x
    ldx BA_T0
    sep #$20
.a8
    cmp FAR_EXP + 2, x          ; primero el byte alto
    bne alto_distinto
    rep #$20
.a16
    lda FAR_EXP, x
    cmp 1, s                    ; C si la experiencia alcanza
    sep #$20
.a8
    ply                         ; `ply` no toca C
    bcc listo
    bra sube
alto_distinto:
    ply
    bcs listo                   ; C: el alto que pide es más que el que hay
sube:
    inc FAR_EXP + EXP_NIVEL, x
    lda FAR_EXP + EXP_NIVEL, x
    ply                         ; el actor, sin sacarlo de la pila
    phy
    jsr aprender_del_nivel
    bra subir
listo:
    plx
    rts
.endproc

; `LearnLevelSkills` de un solo nivel, el A, para el actor Y: prende en
; `FAR_HAB` el bit de cada par suyo que la tabla de aprendizaje del LDB enseña
; en ese nivel —`hab_par_nivel`—. Si ya lo sabía no cambia nada, que es
; `LearnSkill`; y lo que un `ChangeSkills` le hizo olvidar vuelve sólo si se
; enseña en un nivel que recién pasa, como en RM2k. Corre en la pelea, pero
; todo lo que toca va con `f:` o por la pila. Se lleva A, X e Y.
.proc aprender_del_nivel
.a8
.i16
    pha                         ; el nivel
    rep #$20
.a16
    tya
    asl a
    tax
    lda f:hab_par_ini, x
    pha                         ; la ranura del par que se mira: pila = ranura, nivel
    tyx
    lda f:hab_par_n, x
    and #$00FF
    beq fin
    tay                         ; cuántos pares le quedan
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
    pha                         ; su bit: pila = bit, ranura, nivel
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

