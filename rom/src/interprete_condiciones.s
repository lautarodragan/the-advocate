.segment "CODE"
.a8
.i16

; `ConditionalBranch` con condición de switch. Los operandos son el número (dos
; bytes), la polaridad —copiada tal cual de RM2k, donde 0 quiere decir "tiene
; que estar prendido"— y el destino: **el índice absoluto dentro de la página**
; al que va el cursor si la condición no se cumple, o sea el `else` o el `end`
; que le corresponde. Quién es ese destino lo resolvió el conversor, que es el
; único que ve la página entera; acá saltar es asignar Y.
.proc op_if
    ; El primer byte dice **qué se pregunta**, con el número de RM2k tal cual: 0
    ; un switch, 3 el oro, 5 si un actor está en el grupo. Ver `bytes_de_rama`.
    ;
    ; Cada rama deja en A si la condición se cumple —cero o distinto de cero— y
    ; a Y apuntando al byte de polaridad; de ahí en adelante el camino es uno
    ; solo. El switch es el único que usa la polaridad para decidir: en el oro
    ; ya está adentro de la comparación y el actor no la tiene.
    lda [cod_ptr], y
    iny                         ; Y -> el operando
    cmp #COND_ORO
    beq si_oro
    cmp #COND_ACTOR
    beq si_actor
    cmp #COND_ITEM
    bne :+
    jmp si_item                 ; el cuerpo está detrás del oro: `beq` no llega
:

    ; --- el switch ---
    rep #$20
.a16
    phy                         ; el cursor: `switch_encendido` se lleva X e Y
    lda [cod_ptr], y            ; el número, de 16 bits
    jsr switch_encendido        ; Z=1 apagado, Z=0 prendido
    beq si_apagado
    lda #$0001
    bra si_tengo
si_apagado:
    lda #$0000
si_tengo:
    ply                         ; el cursor de vuelta; `ply` no toca A
    sep #$20
.a8
    ; A vale 1 si el switch está prendido, y la polaridad 0 si tenía que
    ; estarlo: el `eor` da distinto de cero exactamente cuando se cumple, en
    ; los dos sentidos, y sin ninguna rama de más. Va por `temp` porque el
    ; ensamblador no tiene `eor [dp], y`. El objeto usa el mismo final, con la
    ; misma polaridad.
si_polaridad:
    iny
    iny                         ; Y -> la polaridad
    sta temp
    lda [cod_ptr], y
    eor temp
    bra si_decide

    ; --- el actor: `IsActorInParty` ---
    ; No lleva polaridad: la rama de abajo es el `else`, así que el conversor
    ; emite cero ahí y acá no se lo mira.
si_actor:
    lda [cod_ptr], y            ; el id, que entra en un byte
    phy
    jsr en_el_grupo             ; A=1 si está, A=0 si no
    ply
    iny
    iny                         ; Y -> la polaridad, que vale cero
    ; **La Z se arma acá, pegada al salto.** `si_decide` decide con un `beq`,
    ; y `ply` y los dos `iny` le dejaban la Z del cursor, que nunca es cero:
    ; "está en el grupo" daba que sí siempre, y en el techo del Warehouse
    ; aparecía Arden sin haberlo sumado. El 2026-09-12 el `cmp #0` iba
    ; después del `ply` y antes de los `iny`, que era arreglar la mitad: ver
    ; `test_rama_grupo`.
    cmp #0
    bra si_decide

    ; --- el oro ---
    ; `CommandConditionalBranch` caso 3: con la polaridad en cero es
    ; `oro >= operando` y con cualquier otra cosa `oro <= operando`. **No son
    ; una la negación de la otra**: en la igualdad se cumplen las dos, así que
    ; se calculan por separado en vez de dar vuelta un bit.
si_oro:
    rep #$20
.a16
    lda [cod_ptr], y            ; contra cuánto, de 16 bits
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> la polaridad
    lda oro + 2
    bne si_oro_grande           ; el oro pasa de 65535: mayor que cualquier
                                ; operando, que entra en una palabra
    rep #$20
.a16
    lda oro
    cmp temp + 2                ; C=1 si oro >= operando
    sep #$20
.a8
    lda #$01
    bcs si_oro_ge
    lda #$00
si_oro_ge:
    sta temp
    rep #$20
.a16
    lda temp + 2
    cmp oro                     ; C=1 si operando >= oro, o sea oro <= operando
    sep #$20
.a8
    lda #$01
    bcs si_oro_le
    lda #$00
si_oro_le:
    sta temp + 1
    bra si_oro_elige
si_oro_grande:
    lda #$01
    sta temp                    ; el >= se cumple
    stz temp + 1                ; y el <= no
si_oro_elige:
    lda [cod_ptr], y            ; la polaridad
    beq si_oro_usa_ge
    lda temp + 1
    bra si_decide
si_oro_usa_ge:
    lda temp
    bra si_decide

    ; --- el objeto: `CommandConditionalBranch` caso 4 ---
    ; `GetItemCount(id) > 0`, la misma pregunta que la condición de página por
    ; ítem y leída del mismo lugar: un byte de `FAR_ITEMS` indexado por el
    ; número de RM2k. `GetEquippedItemCount` no entra porque no hay equipo, que
    ; es lo que `condiciones_ok` ya da por sentado.
    ;
    ; La polaridad es la del switch —0 es "tiene que tenerlo"— así que decide
    ; con el mismo `eor` y sin una rama de más.
si_item:
    rep #$20
.a16
    lda [cod_ptr], y            ; el número de ítem, de 16 bits
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA                  ; cuántos hay en el inventario
    beq si_item_no
    lda #$01
    bra si_item_listo
si_item_no:
    lda #$00
si_item_listo:
    jmp si_polaridad

si_decide:
    beq si_no_cumple
    iny
    iny
    iny                         ; Y -> el opcode siguiente
    jmp correr_codigo::otro
si_no_cumple:
    iny                         ; Y -> el destino
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp correr_codigo::otro

.endproc

; `ConditionalBranch` caso 5 con dos operandos: "sabe esta habilidad" —el
; sub 4— y "tiene puesto este objeto" —el 5—. Van en un opcode aparte y no en
; `OP_IF` porque llevan **dos** operandos, el actor y el ítem o la habilidad;
; ver OP_IF_ACTOR en eventos.py.
;
; Ninguna de las dos tiene polaridad: RM2k no se la da, igual que a "está en el
; grupo", así que la rama de abajo es el `else`.
;
; Al entrar, Y apunta al sub. Los dos caminos terminan en `sia_si` o en
; `sia_no` con Y ya apuntando al destino.
.proc op_if_actor
    lda [cod_ptr], y
    sta temp                    ; el sub
    iny
    lda [cod_ptr], y
    sta temp + 1                ; el actor, que entra en un byte
    iny
    rep #$20
.a16
    lda [cod_ptr], y
    sta temp + 2                ; el ítem o la habilidad, de 16 bits
    sep #$20
.a8
    iny
    iny                         ; Y -> el destino
    lda temp
    cmp #COND_ACTOR_HABILIDAD
    beq sia_habilidad

    ; --- el equipo puesto ---
    ; Los cinco `Get*Id()` de easyrpg comparados contra el ítem: alcanza con
    ; que esté en una ranura. Se leen del mismo lugar que los lee la pantalla
    ; de equipo —`FAR_EQUIPO` + actor * 10, ver `eq_apuntar`— por el puerto de
    ; la WRAM, que autoincrementa: una palabra por ranura, byte por byte,
    ; porque `WMDATA` es un puerto de ocho bits y leerlo de a dos leería el
    ; registro de al lado.
    rep #$20
.a16
    lda temp + 1
    and #$00FF                  ; el actor, sin el ítem que sigue
    asl a                       ; por dos
    sta temp                    ; el sub ya no hace falta
    asl a
    asl a                       ; por ocho
    clc
    adc temp                    ; por diez, que es lo que mide una fila
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #RANURAS_EQUIPO
sia_eq_otra:
    lda WMDATA
    sta temp                    ; el byte bajo del ítem de esta ranura
    lda WMDATA
    sta temp + 1
    rep #$20
.a16
    lda temp
    cmp temp + 2
    sep #$20
.a8
    beq sia_si                  ; `sep` no toca Z: la comparación sigue viva
    dex
    bne sia_eq_otra
    bra sia_no

    ; --- la habilidad ---
    ; `Game_Actor::IsSkillLearned`: el bit del par (actor, habilidad) en
    ; `FAR_HAB`. El conversor ya puso la ranura del par donde las otras
    ; preguntas llevan el ítem, así que `temp + 2` la trae y el actor no hace
    ; falta. Ver `HABILIDAD_RANURA` en eventos.py.
sia_habilidad:
    jsl f:hab_sabe
    bne sia_si
sia_no:
    rep #$20
.a16
    lda [cod_ptr], y            ; el destino, absoluto adentro de la página
    tay
    sep #$20
.a8
    jmp correr_codigo::otro
sia_si:
    iny
    iny                         ; Y -> el opcode siguiente
    jmp correr_codigo::otro

.endproc

