.segment "CODE"

; --- la animación de batalla ------------------------------------------------
;
; `OP_ANIMATION` deja acá la línea de tiempo: dónde está la entrada que sigue
; —en el bytecode—, cuántas quedan y el reloj. `animacion_tick` corre una vez
; por cuadro antes que los destellos y dispara las del tick: un efecto, un
; destello de pantalla o uno del evento objetivo. El dibujo de la animación no
; se hace.
ANIM_PTR   = $7E30E2            ; tres bytes
ANIM_N     = $7E30E5
ANIM_T     = $7E30E6

; Y el estado del cartel, quince bytes en la misma RAM lejana. **No está en el
; banco 0 porque ahí no entra**: la BSS estaba en 7680 de 7680 y esto son
; quince bytes más. Vive donde la animación de batalla y por lo mismo: se lee y
; se escribe unas pocas veces por cuadro, así que el direccionamiento largo no
; se nota, y no hay que indexarlo con nada que no sea el canal.
;
; El tono son **tres** bytes y no cuatro: la saturación de un cartel es siempre
; la neutra —`imagen_aceptable` no acepta otra— así que no hay nada que
; interpolar ahí y `imagen_paleta` le pone `TINTE_NEUTRO` a `tinte_s`.
; **$30E8 a $30EB son del MSU-1** —`MSU_HAY`, `MSU_SUENA` y `MSU_FACTOR`—, así
; que esto arranca en $30EC y llega hasta $30FA; el bloque siguiente es
; `FAR_ARAM_DE`, en $3100. Empezó en $30E8 y se los pisaba: la ROM dejaba de
; detectar el MSU-1 y la música del título se quedaba muda. No lo vio ninguna
; prueba —la tanda compara pixeles— y lo encontró taro escuchando.
FAR_CARTEL    = $7E30EC
CARTEL_ACTIVA = FAR_CARTEL + 0
CARTEL_TONO   = FAR_CARTEL + 1  ; r, g, b, con 100 neutro como el tinte
CARTEL_DESDE  = FAR_CARTEL + 4
CARTEL_HASTA  = FAR_CARTEL + 7
CARTEL_PASO   = FAR_CARTEL + 10
CARTEL_PASOS  = FAR_CARTEL + 11
CARTEL_LISTO  = FAR_CARTEL + 12 ; hay una paleta nueva esperando el vblank
CARTEL_I      = FAR_CARTEL + 13
CARTEL_CAMBIO = FAR_CARTEL + 14

; Y la cola de escapes del cuadro de texto que esté abierto: cuántos cuadros le
; quedan a la pausa del `\|` y si al terminarse se cierra solo —el `\^`—. Los
; pone `msg_empezar` leyendo la cabecera del cuadro y los gasta `eventos_tick`.
;
; **Van en la RAM lejana por la misma razón que el cartel**: el banco 0 no
; tiene lugar. Los 7680 bytes de BSS estaban en 7679 cuando esto se escribió,
; o sea que entraba un byte y hacen falta tres. Acá sobran los cinco que
; quedaron entre el cartel —que termina en $30FA— y `FAR_ARAM_DE`, en $3100.
; Se leen una vez por cuadro y nunca indexados, así que el direccionamiento
; largo no se nota.
FAR_MSG_PAUSA = $7E30FB         ; palabra: hasta PAUSAS_MAX por CUADROS_DE_PAUSA
FAR_MSG_AUTO  = $7E30FD

.proc animacion_limpiar
.a8
.i16
    lda #0
    sta f:ANIM_N
    sta f:ANIMB_ACTIVA          ; y el dibujo, que va por su cuenta
    sta f:ANIMB_SUBIR
    sta f:ANIMB_PAL
    sta f:ANIMB_HAY             ; hasta que `cargar_mapa` diga lo contrario
    rts
.endproc

.proc animacion_tick
.a8
.i16
    lda f:ANIM_N
    bne hay
    rts
hay:
    ; `cod_ptr` prestado: las rutinas de los opcodes leen sus operandos de
    ; ahí, y la página que esté corriendo lo necesita de vuelta.
    lda cod_ptr + 2
    pha
    rep #$20
.a16
    lda cod_ptr
    pha
    lda f:ANIM_PTR
    sta cod_ptr
    sep #$20
.a8
    lda f:ANIM_PTR + 2
    sta cod_ptr + 2
otra:
    ldy #0
    lda [cod_ptr], y            ; su tick
    cmp f:ANIM_T
    bne listo
    iny
    lda [cod_ptr], y            ; su tipo
    iny                         ; y los datos, desde el tercer byte
    cmp #ANIM_SONIDO
    bne no_sonido
    jsr sonido_de_codigo
    bra hecha
no_sonido:
    cmp #ANIM_DESTELLO
    bne no_destello
    jsr destello_de_codigo
    bra hecha
no_destello:
    jsr flash_empezar           ; el del objetivo
hecha:
    rep #$20
.a16
    lda cod_ptr
    clc
    adc #ANIM_ENTRADA
    sta cod_ptr
    sep #$20
.a8
    lda f:ANIM_N
    dec a
    sta f:ANIM_N
    bne otra
listo:
    rep #$20
.a16
    lda cod_ptr
    sta f:ANIM_PTR
    sep #$20
.a8
    lda f:ANIM_T
    inc a
    sta f:ANIM_T
    rep #$20
.a16
    pla
    sta cod_ptr
    sep #$20
.a8
    pla
    sta cod_ptr + 2
    rts
.endproc

; --- el dibujo de la animación de batalla ------------------------------------
;
; Cuatro objetos de 32x32 en una caja de 64x64, con una paleta de sprite para
; ellos solos, y **los 2 KB del cuadro que toca subidos por DMA cada dos
; cuadros**. Es la mezcla de los dos precedentes: los objetos y la paleta
; propia son los del cartel, y subir dibujos nuevos en el vblank es lo que ya
; hacen los tiles animados del ChipSet.
;
; Dónde cae cada pixel y de qué color es está en `tools/port/animacion.py`, que es
; lo único que las dos puntas comparten; acá no se decide nada de eso. La caja
; es una sola para toda la ROM y lo que cambia por mapa —en qué tile queda y
; con qué paleta— lo trae `anim_batalla_reparto`, un byte por mapa.
;
; El estado vive en la RAM lejana, en $3600, bien arriba de lo del MSU-1
; ($30E8), del cartel ($30EC a $30FA) y de las tablas del paquete de audio
; ($3100 a $35FF): el 2026-09-12 un agente pisó el MSU-1 por no mirar el mapa
; de esta RAM.
ANIMB_HAY    = $7E3600          ; este mapa dibuja animaciones
ANIMB_TILE   = $7E3601          ; el primer tile de la caja, palabra
ANIMB_ATTR   = $7E3603          ; vhoopppN ya armado para los cuatro objetos
ANIMB_VRAM   = $7E3604          ; a dónde va el DMA del cuadro, en palabras
ANIMB_CGADD  = $7E3606          ; la entrada de CGRAM de su paleta
ANIMB_SOMBRA = $7E3607          ; y su desplazamiento en `cgram_sombra`, palabra
ANIMB_ACTIVA = $7E3609          ; hay una dibujándose
ANIMB_FILA   = $7E360A          ; su fila en `anim_batalla_tabla`, palabra
ANIMB_BLANCO = $7E360C          ; sobre qué va; $FF es la pantalla
ANIMB_T      = $7E360D          ; el tick, palabra
ANIMB_CUADRO = $7E360F          ; el cuadro que toca, palabra
ANIMB_N      = $7E3611          ; cuántos cuadros tiene, palabra
ANIMB_SUBIR  = $7E3613          ; hay un cuadro esperando el vblank
ANIMB_PAL    = $7E3614          ; y una paleta
ANIMB_I      = $7E3615          ; cuál de los cuatro objetos se está armando
ANIMB_PREV   = $7E3616          ; tres bytes: el último cuadro armado en
                                ; ANIMB_BUF, con el banco en 0 si no hay

; El reparto de este mapa, al cargarlo. El byte es 0 —"acá no se dibuja"— o el
; bit 7 prendido con el bloque de 64 tiles y la paleta, de tres bits cada uno.
; Ver `animaciones_asm` en snes_convert.py.
.proc animacion_dibujo_mapa
.a8
.i16
    jsl f:anim_buf_limpiar      ; con la pantalla apagada, donde no se nota
    lda #0
    sta f:ANIMB_ACTIVA
    sta f:ANIMB_SUBIR
    sta f:ANIMB_PAL
    sta f:ANIMB_HAY
    rep #$20
.a16
    lda mapa_actual
    tax
    sep #$20
.a8
    lda f:anim_batalla_reparto, x
    bne hay
    rts
hay:
    sta f:ANIMB_HAY
    and #$07                    ; la paleta
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32: su lugar en `cgram_sombra`
    rep #$20
.a16
    and #$00FF
    clc
    adc #256                    ; las 128 entradas de abajo, a dos bytes
    sta f:ANIMB_SOMBRA
    sep #$20
.a8
    lda temp
    asl a
    asl a
    asl a
    asl a                       ; por 16: su entrada de CGRAM
    clc
    adc #128
    sta f:ANIMB_CGADD
    lda temp
    asl a
    ora #$30                    ; prioridad 3: adelante de las dos capas
    sta temp + 1
    lda f:ANIMB_HAY
    lsr a
    lsr a
    lsr a
    and #$07                    ; el bloque de 64 tiles
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 64
    sta f:ANIMB_TILE
    ; El noveno bit del tile va en el atributo, y es el mismo para los cuatro:
    ; la caja arranca en un múltiplo de 64 y se lleva doce tiles de nombre.
    xba
    sep #$20
.a8
    and #$01
    ora temp + 1
    sta f:ANIMB_ATTR
    ; Y a dónde va el DMA: la base de sprites del mapa más el tile por dieciséis
    ; palabras, que es lo que mide un tile de 4bpp.
    ldx mapa_ofs
    rep #$20
.a16
    lda f:ANIMB_TILE
    asl a
    asl a
    asl a
    asl a
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x   ; largo: `mapa_tabla` vive en RODATA
    sta f:ANIMB_VRAM
    sep #$20
.a8
    rts
.endproc

; Empieza el dibujo de la animación `temp` sobre `temp + 1`. Lo llama
; `op_animation`, y la nueva reemplaza a la que hubiera, como la línea de
; tiempo. Si este mapa no dibuja, o el número no tiene dibujo, no pasa nada:
; los sonidos y los destellos siguen igual.
.proc animacion_dibujo_empezar
.a8
.i16
    lda #0
    sta f:ANIMB_ACTIVA
    lda f:ANIMB_HAY
    beq no
    lda temp
    cmp #ANIM_B_MAX
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:anim_batalla_de, x
    cmp #ANIM_B_SIN
    beq no
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por ANIM_B_STRIDE
    sta f:ANIMB_FILA
    tax
    sep #$20
.a8
    lda f:anim_batalla_tabla, x ; cuántos cuadros
    rep #$20
.a16
    and #$00FF
    sta f:ANIMB_N
    lda #0
    sta f:ANIMB_T
    lda #$FFFF
    sta f:ANIMB_CUADRO          ; ninguno todavía: el primer tick sube el 0
    sep #$20
.a8
    lda temp + 1
    sta f:ANIMB_BLANCO
    lda #1
    sta f:ANIMB_ACTIVA
    jmp animacion_dibujo_paleta
no:
    rts
.endproc

; Los dieciséis colores de la animación a la sombra de CGRAM, tal cual salen
; del cartucho: no se tiñen ni se destellan, que es lo que hace RM2k —el tono
; del mapa va al tilemap, a los personajes, al panorama y a las sombras, y a
; las animaciones no—. Los sube `flush_video` en el vblank.
.proc animacion_dibujo_paleta
.a8
.i16
    rep #$20
.a16
    lda f:ANIMB_FILA
    asl a
    asl a                       ; por 32: dieciséis palabras por animación
    tax
    lda f:ANIMB_SOMBRA
    tay
copia:
    sep #$20
.a8
    lda f:anim_batalla_cgram, x
    sta cgram_sombra, y
    rep #$20
.a16
    inx
    iny
    txa
    and #$001F
    bne copia
    sep #$20
.a8
    lda #1
    sta f:ANIMB_PAL
    rts
.endproc

; Un cuadro del dibujo. Corre una vez por cuadro, pegado a `animacion_tick`, y
; **el cuadro que se dibuja sale del tick de antes de avanzarlo**: en el tick 0
; se dibuja el cuadro 0, que es el mismo en que dispara el `timing` del cuadro
; 1 de RM2k. Dos cuadros de consola por cada cuadro de animación, que es el
; `num_frames = GetRealFrames() * 2` de `BattleAnimation`.
.proc animacion_dibujo_tick
.a8
.i16
    lda f:ANIMB_ACTIVA
    bne hay
    rts
hay:
    rep #$20
.a16
    lda f:ANIMB_T
    lsr a
    cmp f:ANIMB_N
    bcc sigue
    sep #$20
.a8
    lda #0
    sta f:ANIMB_ACTIVA
    rts
sigue:
.a16
    cmp f:ANIMB_CUADRO
    beq igual
    sta f:ANIMB_CUADRO
    sep #$20
.a8
    lda #1
    sta f:ANIMB_SUBIR           ; el vblank que viene lo manda a la VRAM
    ; Y se arma ya, acá afuera: el vblank sólo copia. No hay carrera con el
    ; DMA porque el lazo sube lo pendiente antes de volver a llamar a esto.
    jsl f:anim_cuadro_armar + RAPIDO   ; desde el espejo rápido: ver MEMSEL
    rep #$20
.a16
igual:
    lda f:ANIMB_T
    inc a
    sta f:ANIMB_T
    sep #$20
.a8
    rts
.endproc

; Los 2 KB del cuadro que toca, a la VRAM. Lo llama `flush_video` adentro del
; vblank y se le descuenta al presupuesto de poses, igual que un paso de la
; animación del ChipSet: cuatro poses de las cinco, y sólo en los cuadros
; pares de la animación.
.proc animacion_dibujo_dma
.a8
.i16
    ; De la RAM lejana y no del cartucho: el cuadro ya lo armó
    ; `anim_cuadro_armar` cuando el tick lo eligió.
    rep #$20
.a16
    lda #.loword(ANIMB_BUF)
    sta A1T0L
    lda f:ANIMB_VRAM
    sta VMADDL
    lda #ANIM_B_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #^ANIMB_BUF
    sta A1B0
    lda #$80                    ; de a palabra, incrementando en $2119
    sta VMAIN
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; Lo que se llevó, en poses de 512 bytes, descontado y no fijado: así se
    ; suma a lo que ya se hayan llevado el tinte o un renglón de la ventana.
    lda vq_tope
    sec
    sbc #(ANIM_B_BYTES / 512)
    bcc una
    bne queda
una:
    lda #1                      ; siempre queda para una pose
queda:
    sta vq_tope
    rts
.endproc

; Los cuatro objetos de la caja, si hay una animación dibujándose.
;
; Van **después del cartel y antes de los personajes**, que es el orden de
; RM2k: `Priority_Timer` es 140, `Priority_PictureOld` 120,
; `Priority_BattleAnimation` 110 y `Priority_Player` 40. En OAM eso es el orden
; de la lista, porque gana el índice más bajo.
;
; Cuestan **ocho de los treinta y cuatro tiles por línea** en las 64 líneas que
; ocupan: dos objetos de cuatro tiles de ancho en cada una. La referencia
; cuenta lo mismo y declara las líneas donde no alcanza.
.proc animacion_dibujo_oam
.a8
.i16
    lda f:ANIMB_ACTIVA
    bne hay
    rts
hay:
    lda f:ANIMB_BLANCO
    cmp #ANIM_B_PANTALLA
    beq pantalla
    ; Sobre el objetivo: el centro de su celda y sus pies, que es
    ; `GetScreenX()` y `GetScreenY(false)`, menos la cámara. El ancla de la
    ; tabla ya trae horneada la corrida de `Animation::Position`.
    cmp #0
    bne evento
    rep #$20
.a16
    lda hero_x
    sta temp
    lda hero_y
    sta temp + 2
    sep #$20
.a8
    bra con_celda
evento:
    dec a                       ; el blanco es el índice del evento más uno
    jsr npc_de_evento
    cpy #$FFFF
    beq nada                    ; sin fila no hay dónde dibujarla
    lda npc_buf + 14, y
    bne con_fila
nada:
    rts                         ; sin fila, o escondido: no se dibuja
con_fila:
    rep #$20
.a16
    lda npc_buf + 0, y
    sta temp
    lda npc_buf + 2, y
    sta temp + 2
    sep #$20
.a8
con_celda:
    rep #$20
.a16
    lda temp
    clc
    adc #8                      ; el centro de la celda
    sec
    sbc pantalla_x
    sta obj_x
    lda temp + 2
    clc
    adc #16                     ; sus pies
    sec
    sbc camara_y
    sta obj_y
    bra restar_ancla
pantalla:
.a8
    rep #$20
.a16
    lda #ANIM_B_CENTRO_X
    sta obj_x
    lda #ANIM_B_CENTRO_Y
    sta obj_y
restar_ancla:
    ; El ancla de la tabla, que ya trae horneada la corrida de
    ; `Animation::Position`. Los dos bytes se leen de a uno: la palabra de +1
    ; trae la X abajo y la Y arriba.
    lda f:ANIMB_FILA
    tax
    lda f:anim_batalla_tabla + 1, x
    and #$00FF
    sta temp
    lda obj_x
    sec
    sbc temp
    sta temp
    lda f:anim_batalla_tabla + 2, x
    and #$00FF
    sta temp + 2
    lda obj_y
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    lda #$02
    sta obj_grande              ; los cuatro objetos son de 32x32
    lda f:ANIMB_ATTR
    sta obj_attr
    lda #0
    sta f:ANIMB_I
cada:
    rep #$20
.a16
    lda f:ANIMB_I
    and #$0001
    beq sin_x
    lda temp
    clc
    adc #ANIM_B_OBJ
    bra con_x
sin_x:
    lda temp
con_x:
    sta obj_x
    lda f:ANIMB_I
    and #$0002
    beq sin_y
    lda temp + 2
    clc
    adc #ANIM_B_OBJ
    bra con_y
sin_y:
    lda temp + 2
con_y:
    sta obj_y
    lda f:ANIMB_I
    and #$00FF
    asl a
    asl a                       ; cuatro tiles de nombre por objeto
    clc
    adc f:ANIMB_TILE
    sep #$20
.a8
    sta obj_tile
    jsr emit_object
    lda f:ANIMB_I
    inc a
    sta f:ANIMB_I
    cmp #ANIM_B_OBJETOS
    bne cada
    rts
.endproc

