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
    jsl flechas_repetir         ; sostener una flecha la vuelve a tocar
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


; --- la repetición de las flechas -------------------------------------------
; Es el `Input::IsRepeated` de RM2k: una flecha sostenida vuelve a dispararse
; sola, primero a los REPETIR_ESPERA cuadros de apretarla y después cada
; REPETIR_CADA, así que sostener abajo en un menú baja solo. Los números son
; los de easyrpg, `src/input.cpp`: `start_repeat_time = 23` y `repeat_time =
; 4`, con `press_time == 1 || (press_time >= 23 && press_time % 4 == 0)`, y
; `press_time` vale 1 en el cuadro del flanco. O sea que dispara en el cuadro 0
; —el flanco de siempre—, en el 23, en el 27, en el 31…: una espera de 0,38 s
; y quince por segundo después.
;
; **No cambia ninguna pantalla: les falsifica el cuadro anterior.** Todas
; calculan el flanco igual, `pad` contra `pad_ant`, así que en el cuadro de la
; repetición se borran de `pad_ant` las flechas sostenidas y cada una lo ve
; como un toque nuevo. Es lo que hace que la lleve todo lo que en easyrpg es
; `Window_Selectable` —el menú, los ítems, el equipo, las ranuras, el título,
; las elecciones de un mensaje, la tienda, la pelea, el fin del juego—, que
; mueve el cursor con `IsRepeated`. B no se toca, y A y X viven en el otro
; byte del control.
;
; Para lo que tiene que distinguir un toque de una repetición queda en
; `flechas_repetidas` qué bits se falsificaron este cuadro. Son dos: la
; entrada de teclas **con espera**, que en RM2k es `IsTriggered` a secas y
; los saca (`tecla_valor`), y la pantalla de ranuras, que es `Scene_File` y
; repitiendo no da la vuelta (`ranuras.s`).
;
; Hay **un solo contador para las cuatro**, y no uno por botón como easyrpg:
; apretar una flecha nueva lo pone en cero aunque otra siga sostenida, así que
; bajar sosteniendo abajo y tocar derecha le reinicia la espera a abajo. En un
; menú de una columna no se nota, y cuesta tres bytes de RAM menos. Ver
; `workflow/divergencias/un-solo-contador-para-las-cuatro-flechas.md`.
;
; Vive en el banco 1 porque en el banco 0 no hay lugar; entra con A8 e I16 y
; un banco de datos que ve la RAM baja, que es lo que ya pide `read_pad`.
REPETIR_ESPERA = 23
REPETIR_CADA   = 4
FLECHAS = PAD_UP | PAD_DOWN | PAD_LEFT | PAD_RIGHT
.assert FLECHAS = $0F, error, "las flechas son el nibble bajo de JOY1H"

.segment "FAR"
.proc flechas_repetir
.a8
.i16
    stz flechas_repetidas
    lda pad
    eor pad_ant
    and pad
    and #FLECHAS
    bne de_cero                 ; una flecha recién apretada: su flanco basta
    lda pad
    and #FLECHAS
    beq de_cero                 ; ninguna sostenida
    inc flechas_cuadros
    lda flechas_cuadros
    cmp #REPETIR_ESPERA
    bcc listo
    ; Vuelve atrás REPETIR_CADA, así que la próxima cae a esa distancia y el
    ; contador no pasa nunca de REPETIR_ESPERA.
    lda #REPETIR_ESPERA - REPETIR_CADA
    sta flechas_cuadros
    lda pad
    and #FLECHAS
    sta flechas_repetidas
    trb pad_ant                 ; para las pantallas, recién apretadas
    rtl
de_cero:
    stz flechas_cuadros
listo:
    rtl
.endproc
