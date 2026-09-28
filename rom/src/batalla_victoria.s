.segment "FAR"

; Los renglones de la ventana: los del grupo, que es lo que tapa.
BA_VIC_RENGLONES = BA_GRUPO_MAX

; --- lo que la victoria cuenta ------------------------------------------------
;
; `ProcessSceneActionVictory` de `Scene_Battle_Rpg2k`: al ganar, la ventana de
; mensaje dice el término de la victoria y la experiencia ganada, y después
; una página por cada actor que subió de nivel, con "<nombre> LEVEL <n>
; achieved!" y lo que aprendió. Cada página espera a A, como un mensaje del
; mapa. Todas las palabras son del LDB —`victory`, `exp_received`, `level`,
; `level_up`, `skill_learned`— y el armado es el de `game_message_terms.cpp`
; para RM2k en inglés, sin placeholders: ver `pantallas.renglon_de_nivel` y
; sus hermanas, que son las que el conversor usa para cobrar que entren.
;
; En RM2k es la ventana de mensaje de siempre, abajo, **tapando al grupo**; acá
; son los cuatro renglones del grupo, igual que el mensaje de una página de
; tropa (`ba_pag_mensaje`), y el renglón de abajo queda vacío.
;
; Desde el 2026-09-27 la primera página cuenta también el oro —"<gold_recieved_a>
; <n><gold><gold_recieved_b>"— y un renglón por ítem que soltaron los enemigos
; —"<ítem><item_recieved>"—, como `PushGoldReceivedMessage` y
; `PushItemRecievedMessages`. Son renglones del mismo mensaje que la victoria y
; la experiencia, así que lo que no entra en los cuatro sigue en otra página,
; igual que las habilidades de un actor.

; Al ganar, antes de mostrar nada: anota el nivel de cada uno, reparte la
; experiencia —que sube de nivel y enseña, ver `exp_sumar`—, da el oro y tira
; el botín, y deja lista la primera página. Es el orden de
; `ProcessSceneActionVictory`, que arma el mensaje y le da todo al grupo en el
; mismo sub-estado; de los tres, sólo el botín tira azar. Se lleva `BA_S0` a
; `BA_S2`, `BA_T*`, A, X e Y.
.proc ba_vic_empezar
.a8
.i16
    stz BA_S0
ranura:
    lda BA_S0
    cmp #BA_GRUPO_MAX
    bcs anotadas
    jsr ba_vic_nivel
    pha
    lda BA_S0
    jsr ba_ax
    pla
    sta BA_VIC_ANTES, x
    inc BA_S0
    bra ranura
anotadas:
    jsr ba_exp_repartir
    jsr ba_vic_oro
    jsr ba_vic_botin
    lda #$FF
    sta BA_VIC_ACTOR
    stz BA_VIC_SALTEAR
    stz BA_VIC_MAS
    rts
.endproc

; El oro de la tropa, al grupo: `Game_Party::GainGold`, topado en ORO_MAX.
; No mira si la tropa da cero: sumar cero no cambia nada.
.proc ba_vic_oro
.a8
.i16
    lda BA_TROPA_K
    cmp #$FF
    beq listo                   ; una tropa que el cartucho no lleva
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_oro, x
    ldy #2                      ; el oro: ver `ba_sin_ocultos`
    jsr ba_sin_ocultos
    sta comp_or01
    sep #$20
.a8
    stz comp_or01 + 2
    jsr oro_sumar
listo:
    rts
.endproc

; La suma de la tropa en A16 sin lo de los enemigos que siguen ocultos: una
; victoria con alguno que nunca apareció —el Rat King que cae antes de llamar
; a sus ratas— no da su experiencia ni su oro, porque `GetExp` y `GetMoney`
; suman **los muertos** y un oculto no murió. Y = 0 la experiencia, 2 el oro.
; Vuelve con A16. Se lleva `BA_T0`, `BA_T2`, X e Y.
.proc ba_sin_ocultos
.a16
.i16
    sta BA_T2
    sep #$20
.a8
    stz BA_T0                   ; el lugar en la tropa
otro:
    lda BA_T0
    cmp BA_NENE
    bcs listo
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_OCULTO
    beq siguiente
    lda BA_TROPA_K
    jsr ba_ax
    lda f:tropa_ini, x
    clc
    adc BA_T0
    jsr ba_ax
    lda f:tropa_miembro, x      ; el enemigo, como lugar en las tablas
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    cpy #0
    bne es_oro
    lda BA_T2
    sec
    sbc f:enemigo_exp, x
    bra restado
es_oro:
    lda BA_T2
    sec
    sbc f:enemigo_oro, x
restado:
    sta BA_T2
    sep #$20
.a8
siguiente:
    inc BA_T0
    bra otro
listo:
    rep #$20
.a16
    lda BA_T2
    rts
.endproc

; Lo que sueltan los enemigos: `Game_EnemyParty::GenerateDrops`. Por cada uno,
; en el orden de la tropa, si tiene ítem **tira** `ba_pct` con su chance —el de
; cien también, que es lo que hace `Rand::ChanceOf`—, y si sale el ítem va al
; inventario, topado en ITEM_MAX como `Game_Party::AddItem`, y su `k` a
; `BA_BOTIN_K` para que la página lo cuente. El orden de los tiros es el de
; `batalla.tirar_el_botin`. Todos los de la tropa están muertos —que es lo que
; pide `IsDead`— menos los que siguen ocultos. Se lleva `BA_S0` a `BA_S2`,
; `BA_T*`, A, X e Y.
.proc ba_vic_botin
.a8
.i16
    stz BA_BOTIN_N
    stz BA_S0                   ; el lugar en la tropa
otro:
    lda BA_S0
    cmp BA_NENE
    bcc hay
    rts
hay:
    ; Uno que sigue oculto no murió, y `GenerateDrops` sólo tira por los
    ; muertos: no tira.
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_OCULTO
    beq a_la_vista
    jmp siguiente
a_la_vista:
    ; El enemigo, como lugar en las tablas: el mismo camino que `ba_armar`.
    lda BA_TROPA_K
    jsr ba_ax
    lda f:tropa_ini, x
    clc
    adc BA_S0
    jsr ba_ax
    lda f:tropa_miembro, x
    sta BA_S2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:enemigo_botin, x
    sta BA_S1                   ; el ítem del LDB, o 0
    sep #$20
.a8
    beq siguiente               ; no deja nada: no tira
    lda BA_S2
    jsr ba_ax
    lda f:enemigo_botin_pct, x
    jsr ba_pct
    beq siguiente
    ldx BA_S1
    lda FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs lleno
    inc a
    sta FAR_ITEMS, x
lleno:
    lda f:item_k, x             ; el conversor cobra que lo lleve
    pha
    lda BA_BOTIN_N
    jsr ba_ax
    pla
    sta BA_BOTIN_K, x
    inc BA_BOTIN_N
siguiente:
    inc BA_S0
    bra otro
.endproc

; El nivel de ahora del actor de la ranura A8 del grupo, o 0 si la ranura
; está vacía o su actor no tiene experiencia. Se lleva X.
.proc ba_vic_nivel
.a8
.i16
    cmp BA_NACT
    bcs nada
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq nada
    lda BA_UNO + BA_NUMERO, x
    jsr ba_ax
    lda f:actor_exp_k, x
    cmp #$FF
    beq nada
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    sep #$20
.a8
    lda FAR_EXP + EXP_NIVEL, x
    rts
nada:
    lda #0
    rts
.endproc

; A8 distinto de cero —y Z en 0— si el actor de la ranura A8 subió de nivel en
; esta victoria. Se lleva X y `BA_T0`.
.proc ba_vic_subio
.a8
.i16
    pha
    jsr ba_vic_nivel
    sta BA_T0
    pla
    jsr ba_ax
    lda BA_VIC_ANTES, x
    beq no                      ; sin experiencia, o sin nadie
    cmp BA_T0
    bcs no                      ; el mismo nivel de antes
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A en la pantalla del fin: si queda otra página, la deja puesta y devuelve A8
; distinto de cero; si no, 0, y la pelea se cierra. Una derrota o una huida no
; tienen páginas. Se lleva X y `BA_T0`.
.proc ba_vic_siguiente
.a8
.i16
    lda BA_RESULT
    cmp #BA_VICTORIA
    bne ninguna
    lda BA_VIC_MAS
    beq otro_actor
    ; Las habilidades que no entraron siguen en otra página del mismo actor,
    ; que es lo que hace la ventana de RM2k con un mensaje de más de cuatro
    ; renglones.
    lda BA_VIC_SIG
    sta BA_VIC_SALTEAR
    lda #1
    rts
otro_actor:
    stz BA_VIC_SALTEAR
    lda BA_VIC_ACTOR
busca:
    inc a                       ; de $FF, la primera página, pasa a la ranura 0
    cmp BA_NACT
    bcs ninguna
    sta BA_VIC_ACTOR
    jsr ba_vic_subio
    cmp #0                      ; `jsr` no deja las banderas del `lda` de adentro
    bne hay
    lda BA_VIC_ACTOR
    bra busca
hay:
    lda #1
    rts
ninguna:
    lda #0
    rts
.endproc

; Z en 0 si lo que la pantalla muestra es una victoria: la pelea terminó ganada
; y el mensaje es el suyo. Lo pregunta `ba_componer` antes de dibujar al grupo.
.proc ba_vic_en_pantalla
.a8
.i16
    lda BA_MTIPO
    cmp #BA_MSG_VICTORIA
    bne no
    lda BA_MODO
    cmp #BA_M_MENSAJE
    beq si
    cmp #BA_M_FIN
    beq si
no:
    lda #0
    rts
si:
    lda #1
    rts
.endproc

; La página de ahora en los renglones del grupo. La llama `ba_componer` con
; `jmp`, así que su `rts` es el del compositor: el renglón de abajo, el del
; mensaje de la pelea, queda vacío. Se lleva `BA_S0` a `BA_S4`, `BA_T*`, A, X
; e Y.
.proc ba_vic_mensaje
.a8
.i16
    stz temp + 1                ; en blanco
    rep #$20
.a16
    lda #BA_PAG_MSG_POS0
    sta BA_T1
    lda #BA_PAG_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_VIC_ACTOR
    cmp #$FF
    beq primera
    jmp de_un_actor
primera:
    ; Los renglones del mensaje de la victoria, de a cuatro por página: ver
    ; `ba_vic_linea`, que cuenta los que ya salieron.
    stz BA_VIC_MAS
    lda BA_VIC_SALTEAR
    sta BA_VIC_SIG
    stz BA_S3
    stz BA_S4
    ; El término de la victoria, en los renglones en que lo partió el
    ; conversor —ver `pantallas.renglones_de_la_victoria`—.
    jsr ba_vic_linea
    bcc sin_v1
    ldx #BA_TXT_VICTORIA
    jsr ba_termino
sin_v1:
    lda #BA_VIC_TERMINO_N       ; no con `.if`: la constante llega después
    cmp #2
    bcc un_renglon
    jsr ba_vic_linea
    bcc un_renglon
    ldx #BA_TXT_VICTORIA2
    jsr ba_termino
un_renglon:
    ; Y la experiencia, si la hay: `if (exp > 0)` de easyrpg. El oro va igual,
    ; `if (money > 0)`.
    lda BA_TROPA_K
    cmp #$FF
    bne con_tropa
    rts
con_tropa:
    rep #$20
.a16
    and #$00FF
    asl a
    sta BA_S1                   ; el lugar de la tropa en las de palabras
    tax
    lda f:tropa_exp, x
    ldy #0                      ; sin los que siguieron ocultos
    jsr ba_sin_ocultos
    sep #$20                    ; `sep` no toca Z
.a8
    beq sin_exp
    jsr ba_vic_linea
    bcc sin_exp
    rep #$20
.a16
    ldx BA_S1
    lda f:tropa_exp, x
    ldy #0
    jsr ba_sin_ocultos
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_numero
    ldx #BA_TXT_EXP_RECIBIDA
    jsr ba_termino
sin_exp:
    rep #$20
.a16
    ldx BA_S1
    lda f:tropa_oro, x
    ldy #2
    jsr ba_sin_ocultos
    sep #$20
.a8
    beq sin_oro
    jsr ba_vic_linea
    bcc sin_oro
    ldx #BA_TXT_ORO_A
    jsr ba_termino
    lda #$20
    jsl f:ba_t_glifo
    rep #$20
.a16
    ldx BA_S1
    lda f:tropa_oro, x
    ldy #2
    jsr ba_sin_ocultos
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_numero
    ldx #BA_TXT_MONEDA
    jsr ba_termino
    ldx #BA_TXT_ORO_B
    jsr ba_termino
sin_oro:
    ; Y un renglón por ítem, en el orden en que salieron.
    stz BA_S0
item:
    lda BA_S0
    cmp BA_BOTIN_N
    bcs listos
    jsr ba_vic_linea
    bcc otro_item
    lda BA_S0
    jsr ba_ax
    lda BA_BOTIN_K, x
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; por tres: `3k` es el nombre del ítem
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    ldx #BA_TXT_OBTENIDO
    jsr ba_termino
otro_item:
    inc BA_S0
    bra item
listos:
    rts

de_un_actor:
    ; "<nombre> LEVEL <n> achieved!", sólo en su primera página.
    lda #1
    sta BA_S3                   ; renglones escritos, el de arriba ya contado
    lda BA_VIC_SALTEAR
    bne sin_nivel
    lda BA_VIC_ACTOR
    jsr ba_nombre
    lda #$20
    jsl f:ba_t_glifo
    ldx #BA_TXT_NIVEL
    jsr ba_termino
    lda #$20
    jsl f:ba_t_glifo
    lda BA_VIC_ACTOR
    jsr ba_vic_nivel
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_numero
    ldx #BA_TXT_SUBIO
    jsr ba_termino
    bra habilidades
sin_nivel:
    stz BA_S3                   ; la continuación arranca en el de arriba
habilidades:
    ; Y "<habilidad> acquired!" por cada una que enseñan los niveles que pasó,
    ; nivel por nivel como `LearnLevelSkills(old_level + 1, new_level)`.
    ; `BA_VIC_SALTEAR` son las que ya salieron en páginas anteriores.
    ;
    ; **Dice todas las que la tabla enseña en esos niveles**, y RM2k sólo las
    ; que no sabía —`LearnSkill` no avisa si ya estaba—: las dos cosas
    ; difieren sólo si un `ChangeSkills` le enseñó antes una que después
    ; enseña un nivel, y en el ABL ninguno lo hace. `exp_sumar` ya prendió los
    ; bits, así que acá no hay cómo saber cuáles estaban.
    stz BA_VIC_MAS
    lda BA_VIC_SALTEAR
    sta BA_VIC_SIG
    stz BA_S4                   ; las que ya se vieron, escritas o salteadas
    lda BA_VIC_ACTOR
    jsr ba_vic_nivel
    sta BA_S2                   ; hasta qué nivel
    lda BA_VIC_ACTOR
    jsr ba_ax
    lda BA_VIC_ANTES, x
    sta BA_S0                   ; el nivel que se mira, desde el de antes + 1
    lda BA_VIC_ACTOR
    jsr ba_x
    lda BA_UNO + BA_NUMERO, x
    sta BA_S0 + 1               ; el actor del LDB
nivel:
    lda BA_S0
    cmp BA_S2
    bcc otro_nivel
    rts                         ; ya se miró el de ahora
otro_nivel:
    inc BA_S0
    ; Los pares del actor: `hab_par_ini` y `hab_par_n`, como `aprender_del_nivel`.
    lda BA_S0 + 1
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:hab_par_ini, x
    sta BA_S1                   ; el par que se mira
    sep #$20
.a8
    lda BA_S0 + 1
    jsr ba_ax
    lda f:hab_par_n, x
    sta BA_S2 + 1               ; cuántos le quedan
    beq nivel
par:
    ldx BA_S1
    lda f:hab_par_nivel, x
    cmp BA_S0
    bne siguiente
    inc BA_S4
    lda BA_S4
    cmp BA_VIC_SALTEAR
    beq siguiente               ; salió en una página anterior
    bcc siguiente
    lda BA_S3
    cmp #BA_VIC_RENGLONES
    bcc entra
    lda #1                      ; no entra: sigue en otra página
    sta BA_VIC_MAS
    bra listo
entra:
    inc BA_S3
    inc BA_VIC_SIG
    lda BA_S3
    cmp #1
    beq arriba                  ; el primero de una continuación
    jsr ba_vic_renglon
arriba:
    rep #$20
.a16
    lda BA_S1
    asl a
    tax
    lda f:hab_par_aprende_txt, x
    tax
    sep #$20
.a8
    jsr ba_termino
    ldx #BA_TXT_APRENDIO
    jsr ba_termino
siguiente:
    rep #$20
.a16
    inc BA_S1
    sep #$20
.a8
    dec BA_S2 + 1
    beq otro
    jmp par
otro:
    jmp nivel
listo:
    rts
.endproc

; El renglón que sigue de la primera página, si le toca a ésta: C en 1 y la
; posición puesta, o C en 0 si salió en una página anterior —los primeros
; `BA_VIC_SALTEAR`— o no entra, y entonces queda `BA_VIC_MAS`. Lleva la cuenta
; en `BA_S4`, los vistos, y `BA_S3`, los escritos, que `ba_vic_mensaje` pone en
; cero. Es la misma cuenta que las habilidades de un actor, más abajo.
.proc ba_vic_linea
.a8
.i16
    inc BA_S4
    lda BA_S4
    cmp BA_VIC_SALTEAR
    beq no                      ; salió en una página anterior
    bcc no
    lda BA_S3
    cmp #BA_VIC_RENGLONES
    bcc entra
    lda #1                      ; no entra: sigue en otra página
    sta BA_VIC_MAS
no:
    clc
    rts
entra:
    inc BA_VIC_SIG
    lda BA_S3
    beq arriba                  ; el primero de la página ya está puesto
    jsr ba_vic_renglon
arriba:
    inc BA_S3
    sec
    rts
.endproc

; El renglón de abajo del que se está escribiendo, desde su principio.
.proc ba_vic_renglon
.a8
.i16
    rep #$20
.a16
    lda BA_T1
    clc
    adc #BA_FILA_BYTES
    sta BA_T1
    lda #BA_PAG_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    rts
.endproc

; `BA_T0` sin espacios adelante, de hasta cinco cifras: la experiencia de una
; tropa no entra en las tres de `pant_numero`. Se lleva A, X, Y y `BA_T0`.
.proc ba_vic_numero
.a8
.i16
    stz BA_T2                   ; si ya salió una cifra
    ldx #0                      ; qué potencia de diez
potencia:
    ldy #0                      ; la cifra
    rep #$20
.a16
resta:
    lda BA_T0
    cmp f:potencias, x          ; con `f:`: el banco de datos es $7E
    bcc cifra
    sbc f:potencias, x          ; C viene de la comparación
    sta BA_T0
    iny
    bra resta
cifra:
    sep #$20
.a8
    tya
    ora BA_T2
    beq cero_adelante
    sta BA_T2
    tya
    clc
    adc #$30
    phx
    jsl f:ba_t_glifo
    plx
cero_adelante:
    inx
    inx
    cpx #8
    bcc potencia
    lda BA_T0                   ; las unidades, siempre
    clc
    adc #$30
    jsl f:ba_t_glifo
    rts
potencias:
    .word 10000, 1000, 100, 10
.endproc
