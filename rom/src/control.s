.segment "CODE"

; Cuántas vueltas el autofire deja A prendido y cuántas apagado: cuatro y
; cuatro son 7,5 toques por segundo. Es para ajustarlo jugando, pero tiene que
; ser potencia de dos, porque la fase es un bit del contador; y así además el
; contador da la vuelta en 256 sin cortar un medio ciclo.
AUTOFIRE_CUADROS = 4
.assert AUTOFIRE_CUADROS & (AUTOFIRE_CUADROS - 1) = 0, error, "AUTOFIRE_CUADROS tiene que ser potencia de dos"
.assert AUTOFIRE_CUADROS > 0 && AUTOFIRE_CUADROS < $100, error, "AUTOFIRE_CUADROS tiene que entrar en el contador de un byte"

; --- lectura del control ---------------------------------------------------
; La consola lee los controles sola al empezar el vblank, pero tarda unos
; scanlines. El bit 0 de HVBJOY dice si todavía está en eso: leer antes devuelve
; basura a medio armar.
; La consola lee los controles sola al empezar el vblank, pero no arranca en el
; mismo ciclo en que el vblank empieza: tarda unas decenas de ciclos, y después
; unos cuatro scanlines en terminar. El bit 0 de HVBJOY vale 1 mientras está en
; eso.
;
; Preguntar sólo "¿terminó?" tiene una carrera: como wait_vblank devuelve justo
; al empezar el vblank, la lectura todavía no arrancó, el bit vale 0, y se pasa
; de largo leyendo los registros mientras la consola está por pisarlos. Cada
; tanto sale un valor a medio armar y ese cuadro se pierde el movimiento, que se
; ve como un tirón. Por eso hay que esperar primero a que empiece.
.proc read_pad
.a8
.i16
arranca:
    lda HVBJOY
    and #$01
    beq arranca                 ; todavía no empezó
termina:
    lda HVBJOY
    and #$01
    bne termina                 ; sigue leyendo
    lda pad
    sta pad_ant                 ; el de recién, para los flancos de abajo
    lda JOY1H
    sta pad
    ; De A no interesa el estado sino el flanco: RM2k cierra el mensaje con
    ; `Input::IsTriggered`, o sea con la transición de suelto a apretado.
    ; Sostenerlo no vuelve a disparar nada, y por eso la prueba puede apretarlo
    ; y dejarlo apretado hasta el final.
    lda pad_a
    sta pad_a_ant
    lda JOY1L
    bit #PAD_X
    bne con_x
    stz autofire                ; así el próximo X arranca apretando A
    and #PAD_A
    sta pad_a
    rts
    ; X es el autofire de A: mientras está apretado, `pad_a` pasa
    ; AUTOFIRE_CUADROS vueltas prendido y otras tantas apagado, y cada vuelta a
    ; prendido es un flanco nuevo, o sea un toque. RM2k no lo tiene: ver
    ; `workflow/divergencias/autofire-de-a-con-x.md`.
    ;
    ; La A de verdad se suma con un OR, así que gana: con A y X apretados
    ; `pad_a` queda prendido y no hay flancos, que es lo mismo que sostener A
    ; solo. Y soltar X no puede dejar nada trabado ni tocar de más: la vuelta
    ; siguiente pasa por arriba, que escribe sólo la A de verdad, así que a lo
    ; sumo apaga un `pad_a` prendido, y eso no es un flanco de subida.
con_x:
    and #PAD_A
    sta pad_a
    lda autofire
    inc autofire
    and #AUTOFIRE_CUADROS       ; la vuelta 0 cae en fase prendida: X toca ya
    bne apagado
    lda #PAD_A
    tsb pad_a
apagado:
    rts
.endproc

