.segment "CODE"
.a8
.i16

; --- la transición del teletransporte ---------------------------------------
;
; RM2k borra y vuelve a mostrar la pantalla en cada teletransporte con la
; transición que diga el sistema, y `ChangeScreenTransitions` la cambia de ahí
; en más. La ROM hace dos, y el conversor ya decidió cuál va —ver
; `CHANGE_SCREEN_TRANSITIONS` en tools/port/eventos.py—:
;
;   el fundido   el de siempre, `fundido_tick`: el brillo maestro sobre
;                `fundido_rampa`. Es también lo que va para las que la consola
;                no hace, como el zoom
;   el mosaico   el mismo fundido, y además el registro MOSAIC atado al brillo:
;                tamaño 16 con brillo 0, tamaño 1 con brillo 15, que es lo que
;                hace la pelea —ver `fundido_de_pelea.s`, que explica por qué
;                el mosaico también oscurece, y en RM2k no: la carga tiene que
;                caer adentro del negro—
;
; El mosaico del PPU es de los fondos y nada más: **los sprites no se
; pixelan**, y en RM2k sí, porque allá se pixela la pantalla entera. Con el
; brillo bajando a la vez casi no se nota; está en
; workflow/divergencias/las-transiciones-del-teletransporte.md.
;
; No hay que tocar `fundido_tick` para esto: el mosaico se deduce de lo que el
; fundido ya lleva —si hay uno, si la carga sigue pendiente y el brillo de este
; cuadro— y se escribe en el vblank, al lado del brillo, en `fundido_mosaico`.

; `ChangeScreenTransitions`: cuál —0 borrar, 1 mostrar— y la transición. En el
; banco 0 queda sólo el salto, porque el despacho pide el manejador acá y el
; banco 0 no tiene lugar de sobra.
.proc op_transition
    jsl f:transicion_poner
    jmp correr_codigo::otro
.endproc

.segment "FAR"

; Lo de `op_transition`: con Y en el primer operando, y vuelve con Y después
; del último. El bytecode se lee con `[cod_ptr], y`, que no depende del banco
; de datos, y la RAM lejana con `f:`.
.proc transicion_poner
.a8
.i16
    lda [cod_ptr], y            ; cuál: 0 borrar, 1 mostrar
    iny
    lsr a                       ; al carry
    lda [cod_ptr], y            ; la transición
    iny
    bcs mostrar
    sta f:TRANSICION_BORRAR
    rtl
mostrar:
    sta f:TRANSICION_MOSTRAR
    rtl
.endproc

; Las dos en el fundido, desde el reset: la RAM lejana arranca con basura en
; bsnes, y el primer teletransporte saldría en mosaico si cayera justo.
; Cualquier valor que no sea TRANSICION_MOSAICO es el fundido.
.assert TRANSICION_MOSAICO <> 0, error, "el cero tiene que ser el fundido"
.proc transicion_de_arranque
.a8
.i16
    lda #0
    sta f:TRANSICION_BORRAR
    sta f:TRANSICION_MOSTRAR
    rtl
.endproc

; El mosaico de este cuadro. Desde `flush_video`, en el vblank y justo antes de
; escribir el brillo, así que los dos cambian en el mismo cuadro.
;
; Mientras la carga del mapa esté pendiente —`fundido_que` distinto de cero—
; el fundido está borrando la pantalla; después la está mostrando. Sin fundido,
; o con uno que no sea en mosaico, lo apaga: se escribe en cada cuadro, así
; que nadie más tiene que acordarse de apagarlo. `fundido`, `fundido_que` y
; `brillo` viven en la BSS del banco 0, y se leen con `f:` para no depender del
; banco de datos.
.proc fundido_mosaico
.a8
.i16
    lda f:fundido
    beq apagado
    lda f:fundido_que
    beq mostrando
    lda f:TRANSICION_BORRAR
    bra mirar
mostrando:
    lda f:TRANSICION_MOSTRAR
mirar:
    cmp #TRANSICION_MOSAICO
    bne apagado
    lda f:brillo
    eor #$0F                    ; el tamaño, al revés que el brillo
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 y BG2: el mapa y la capa de encima
    bra escribir
apagado:
    lda #0
escribir:
    sta f:MOSAIC
    rtl
.endproc
