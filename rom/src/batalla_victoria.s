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
; RM2k también cuenta el oro y los ítems que se ganan; este port todavía no
; los da, así que tampoco los cuenta.

; Al ganar, antes de mostrar nada: anota el nivel de cada uno, reparte la
; experiencia —que sube de nivel y enseña, ver `exp_sumar`— y deja lista la
; primera página. Es el orden de `ProcessSceneActionVictory`, que arma el
; mensaje y le da la experiencia a cada uno en el mismo sub-estado. Se lleva
; `BA_S0`, `BA_T*`, A, X e Y.
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
    lda #$FF
    sta BA_VIC_ACTOR
    stz BA_VIC_SALTEAR
    stz BA_VIC_MAS
    rts
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
    ; El término de la victoria, en los renglones en que lo partió el
    ; conversor —ver `pantallas.renglones_de_la_victoria`—.
    ldx #BA_TXT_VICTORIA
    jsr ba_termino
    lda #BA_VIC_TERMINO_N       ; no con `.if`: la constante llega después
    cmp #2
    bcc un_renglon
    jsr ba_vic_renglon
    ldx #BA_TXT_VICTORIA2
    jsr ba_termino
un_renglon:
    ; Y la experiencia, si la hay: `if (exp > 0)` de easyrpg.
    lda BA_TROPA_K
    cmp #$FF
    beq sin_exp
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tropa_exp, x
    beq sin_exp
    sta BA_T0
    sep #$20
.a8
    jsr ba_vic_renglon
    jsr ba_vic_numero
    ldx #BA_TXT_EXP_RECIBIDA
    jsr ba_termino
sin_exp:
    sep #$20
.a8
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
