.segment "FAR"

; --- el equipo y las habilidades desde un evento ----------------------------
;
; Los cuerpos de OP_EQUIPMENT y OP_SKILL, y lo que la rama "sabe la habilidad"
; pregunta. Viven acá por lo mismo que `curar`: se entra con `jsl` desde el
; intérprete, con Y en el operando y **el banco de datos del bytecode**, así que
; todo lo que tocan va con `f:` o es de la página directa.

; `ChangeEquipment` que saca lo de una ranura: el actor —o 0 por todo el grupo,
; como en `curar`— y la ranura, de 0 a 4. Se vuelve con Y después de ella. Se
; lleva A, X y `temp`.
.proc equipo_quitar
.a8
.i16
    lda [cod_ptr], y            ; el actor
    iny
    sta temp + 2
    lda [cod_ptr], y            ; la ranura
    iny
    sta temp + 3
    phy
    lda temp + 2
    bne uno
    ; Hasta `grupo_n`: ver `curar`, que tuvo el mismo cuidado.
    ldx #0
ranura:
    cpx grupo_n
    bcs listo
    lda grupo, x
    phx
    jsr equipo_quitar_actor
    plx
    inx
    bra ranura
uno:
    jsr equipo_quitar_actor
listo:
    ply
    rtl
.endproc

; El actor A, la ranura `temp + 3`. Es `Game_Actor::ChangeEquipment(ranura, 0)`
; de easyrpg (`game_actor.cpp:335`): la ranura queda vacía y lo que tenía vuelve
; al inventario —`Game_Party::AddItem`, topado en ITEM_MAX—. Lo de las armas a
; dos manos no aplica: sacar nunca deja dos cosas donde entra una. Se lleva X y
; `temp`.
.proc equipo_quitar_actor
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta temp                    ; el actor por dos
    asl a
    asl a
    clc
    adc temp                    ; por diez, que es lo que mide una fila
    sta temp
    lda temp + 3
    and #$00FF
    asl a                       ; la ranura es una palabra
    clc
    adc temp
    tax
    lda f:FAR_LARGO + FAR_EQUIPO, x
    beq listo                   ; no tenía nada
    sta temp
    lda #0
    sta f:FAR_LARGO + FAR_EQUIPO, x
    lda temp
    cmp #ITEMS_N
    bcs listo                   ; un ítem que el inventario no lleva
    tax
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_ITEMS, x
    cmp #ITEM_MAX
    bcs listo8
    inc a
    sta f:FAR_LARGO + FAR_ITEMS, x
listo8:
    rts
.a16
listo:
    sep #$20
.a8
    rts
.endproc

; `ChangeSkills`: la ranura del par (actor, habilidad) y si la aprende. Es
; prender o apagar su bit en `FAR_HAB`: `LearnSkill` no hace nada si ya la
; sabía y `UnlearnSkill` tampoco si no, y con un bit las dos cosas salen solas.
; Se vuelve con Y después de los operandos. Se lleva A, X y `temp`.
.proc habilidad_cambiar
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; la ranura del par
    iny
    iny
    sta temp + 2
    jsr hab_apuntar
    sep #$20
.a8
    lda [cod_ptr], y            ; 1 aprende, 0 olvida
    iny
    cmp #0
    beq olvidar
    lda f:FAR_LARGO + FAR_HAB, x
    ora temp
    bra poner
olvidar:
    lda temp
    eor #$FF
    and f:FAR_LARGO + FAR_HAB, x
poner:
    sta f:FAR_LARGO + FAR_HAB, x
    rtl
.endproc

; `IsSkillLearned` para la rama de `ConditionalBranch`: la ranura del par en
; `temp + 2`, y vuelve con Z=0 si la sabe. Se lleva A, X y `temp`.
.proc hab_sabe
.a8
.i16
    jsr hab_apuntar
    lda f:FAR_LARGO + FAR_HAB, x
    and temp
    rtl                         ; `rtl` no toca las banderas: vale el `and`
.endproc

; La ranura del par en `temp + 2` → X en su byte de `FAR_HAB`, y su bit en
; `temp`. Vuelve con A de ocho bits.
.proc hab_apuntar
.a8
.i16
    rep #$20
.a16
    lda temp + 2
    and #$0007
    tax
    sep #$20
.a8
    lda f:mascara, x
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

; Los bits de las habilidades a lo que el LDB dice que cada actor sabe a su
; nivel inicial: la tabla `hab_inicial` del conversor copiada a `FAR_HAB`. Corre
; en el reset, antes de cargar la partida, que la pisa. Son pocos bytes y va de
; a uno: un DMA costaría más código que el lazo.
.proc hab_inicial_poner
.a8
.i16
    ldx #0
otro:
    lda f:hab_inicial, x
    sta f:FAR_LARGO + FAR_HAB, x
    inx
    cpx #HAB_BYTES
    bne otro
    rtl
.endproc

; Los HP de ahora de un actor, en su fila del panel del grupo: tres cifras
; alineadas a la derecha y lo que sobre a la izquierda, en blanco. `temp` trae
; el número de actor del LDB y `temp + 2` la fila; se lleva A, X, Y y `temp`.
;
; **Esto existe porque el bloque de la fila se hornea al convertir.** Hasta el
; 2026-09-13 los HP iban adentro de ese bloque, así que el menú mostraba
; siempre el máximo del nivel por más que la pelea los bajara: es lo que taro
; reportó jugando —"en el menú siempre se muestra en 40", que es el máximo de
; Talan—. El máximo y la barra siguen horneados, que ésos no cambian.
;
; Las cifras son los mismos glifos que el oro —`ranura_glifo_celdas`, una por
; celda— y caen alineadas sin tocar nada porque las dos líneas se dibujan a
; dos pixeles del borde de arriba de su celda. `titulo._pegar_hp` es la
; referencia, con las mismas columnas.
;
; Vive fuera del banco 0 por lo mismo que `hp_inicial_poner`: allá quedan
; decenas de bytes y esto son más de cien. Se entra con `jsl` y con el banco de
; datos en 0 —el menú corre así— pero se lo pone igual, porque todo lo que toca
; —`temp`, las tablas de `TABLAS` y los registros del PPU— es absoluto del
; banco 0 y depender del llamador para eso ya costó un error en este repo.
.proc menu_hp_escribir
.a8
.i16
    phb
    lda #0
    pha
    plb
    ; La celda de las unidades: la primera del bloque de la fila, más el
    ; desplazamiento que emite el conversor, más las cifras que van a la
    ; izquierda.
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
    ; Y los HP, de la RAM lejana. Un actor con más de 999 mostraría sus tres
    ; cifras de abajo; ninguno del juego llega.
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
    sta WRDIVL                  ; el dividendo, de dieciséis bits
    sep #$20
.a8
    lda #10
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
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
    lda RDMPYL                  ; el resto, que es la cifra
    and #$00FF
    asl a
    asl a                       ; dos palabras por cifra
    tax
    sty VMADDL
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0, x
    sta VMDATAL
    tya
    clc
    adc #32                     ; la celda de abajo
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
    ; Lo que queda a la izquierda, en blanco: la celda 0, que en el bloque del
    ; actor es la que ya hay debajo de las cifras.
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

