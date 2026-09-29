; ===========================================================================
; La batalla, fuera del banco 0
; ===========================================================================
;
; Son unos dos kilobytes de código y en el banco 0 quedaban trescientos bytes,
; así que vive acá, en RODATA, y se entra con `jsl batalla_correr`. Lo que eso
; obliga está en el comentario de los puentes `ba_t_*`, en el banco 0: desde
; acá no se puede volver con `jsr`, porque `jsr` no cambia el banco de
; programa.
;
; **El banco de datos es $7E mientras dura la pelea.** Lo pone `op_battle`
; antes del `jsl` y lo repone al volver. Es lo que le deja a este código usar
; direccionamiento absoluto sobre su estado: `inc`, `stz`, `ldx` y `cpy` no
; tienen modo largo, así que con `f:` cada uno pediría pasar por el
; acumulador. Y no le cuesta nada a lo demás: en el banco $7E las direcciones
; de $0000 a $1FFF **son** la RAM baja del banco 0, así que `temp`, `comp_*` y
; `grupo` se leen igual que siempre.
;
; Lo que sí cambia son **las tablas de la ROM**, que van con `f:`: las de acá
; porque viven en otro banco, y las del banco 0 —`actor_txt`— porque con el
; banco de datos en $7E su dirección absoluta caería en la RAM.
;
; El escritorio, prestado como en la tienda —con el menú abierto no hay
; mensaje que componer—:
;   ba_diva   es temp        ; el dividendo, y después el cociente
;   ba_divb   es temp + 2    ; el divisor
;   ba_divr   es comp_and    ; el resto
;   ba_mulp   es comp_or23   ; el parcial bajo del producto
; **Todo lo que sigue, hasta la cabecera, vive en el banco 1 y entero en él.**
; Adentro se llaman entre sí con `jsr`, que no cruza de banco, y antes de tener
; segmento propio esto iba detrás de los datos generados: caía en un banco
; distinto con cada cartucho, y un relleno calculado a ojo tenía que evitar que
; la pelea quedara partida. Lo que garantiza que entre lo cobra
; `rom/pruebas/herramientas/test_bancos.py`, sobre la tabla de símbolos.
.segment "FAR"

; --- lo que no hace falta que viva en el banco 0 ---------------------------
;
; Estas tres se leen con `lda f:tabla, x` —absoluto largo indexado, que suma X
; sobre los 24 bits y no depende del registro de banco de datos—, así que
; pueden vivir acá afuera. Cuestan un byte y un ciclo por acceso, y ninguna de
; las tres está en un lazo que se corra por cuadro: los registros del PPU se
; escriben una vez al encender y `partida_tabla` se recorre al guardar y al
; cargar.
;
; Bajaron del banco 0 el 2026-09-13, cuando `HaltAllMovement` y la rama por
; objeto lo pasaron por 128 bytes. El banco 0 lleva el código y las tablas que
; **sí** se indexan con el banco de datos en cero; lo que no, sobra.

; Y desde el mismo día, seis más: el 2026-09-13 el `KeyInputProc` que espera la
; cruceta y el `ChangeEventLocation` por variables volvieron a pasar el banco 0,
; esta vez por 58 bytes. Las seis se leen con **X**, que es lo único que el
; 65816 indexa en largo —`long,Y` no existe—, y por eso bajaron éstas y no las
; de velocidad de las rutas, que se leen con Y.
;
; Ninguna está en un lazo por cuadro. La más caliente es `tabla_fila_buf`, que
; el compositor de texto lee **una vez por fila de glifo**: dieciséis por letra
; y sólo mientras se está armando una ventana de mensaje, o sea un ciclo de más
; por fila sobre los cientos que cuesta componerla.

; De qué byte del buffer de texto arranca cada una de sus dieciséis filas. El
; buffer son dos filas de celda, así que la fila Y cae en el tile (Y/8) por 30
; columnas de 32 bytes, más (Y mod 8) por 2 dentro del tile.
tabla_fila_buf:
    .word 0, 2, 4, 6, 8, 10, 12, 14
    .word 960, 962, 964, 966, 968, 970, 972, 974

; Cuánto se corre cada dirección, en celdas: arriba, derecha, abajo,
; izquierda, y las cuatro diagonales. Con signo, que es como las suma
; `armar_salto`.
paso_dx:
    .byte 0, 1, 0, $FF, 1, 1, $FF, $FF
paso_dy:
    .byte $FF, 0, 1, 0, $FF, 1, 1, $FF

; `paso_dx`, `paso_dy` y `paso_por_vel` bajaron a RODATA el 2026-09-13, al
; resolver el merge de dos ramas que habían bajado tablas cada una por su lado y
; aun así no entraban juntas: faltaban diez bytes. Los doce accesos a las dos
; primeras son con X, que tiene modo largo; la tercera tiene uno solo y se pasa
; por X salvando la ranura, cuatro bytes contra los doce de la tabla.
; Cuánto avanza un paso por cuadro según la velocidad, 1 a 6, de 256 por
; celda, y cuánto el salto: PASO_POR_VELOCIDAD de eventos.py y
; `jump_speed[move_speed - 1]` de RM2k. La 4 es la del héroe: 32 por cuadro,
; dos pixeles.
paso_por_vel:
    .word 4, 8, 16, 32, 64, 128

; `paso_por_vel` bajó a RODATA el 2026-09-13: tiene un solo acceso, y pasarlo
; por X cuesta cuatro bytes contra los doce de la tabla.
salto_por_vel:
    .byte 8, 12, 16, 24, 32, 64

; El tilemap del menú que le toca a la opción elegida. Hay uno por opción y
; están seguidos, así que cuál es sale de multiplicar; mover el cursor es subir
; el otro y no escribir a mano las dos celdas que cambian, que es la clase de
; número que se escribe bien de un lado y mal del otro.
;
; Corre con la pantalla apagada la primera vez y adentro del vblank las demás:
; son 2048 bytes por DMA, que entran de sobra en un vblank que no tiene nada más
; que hacer.
; `titulo_subir_menu` vive en RODATA desde el 2026-09-14: la demo con
; pantalla de título se pasaba del banco 0 por cuatro bytes. No llama a nadie,
; así que mudarla sólo cuesta el `jsl` de sus tres llamadores.
.proc titulo_subir_menu
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #TITULO_MENU_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    ; El origen: el principio del bloque más 2048 por opción.
    lda titulo_sel
    and #$00FF
    xba                         ; por 256
    asl a
    asl a
    asl a                       ; y por 8: 2048 en total
    sta temp
    lda #<(titulo_menu_celdas)
    ora #(>(titulo_menu_celdas) * 256)
    clc
    adc temp
    ; La suma puede pasarse de los 16 bits del desplazamiento, así que el banco
    ; se toma del acarreo: el acomodo de `tools/ensamblado/bancos.py` garantiza que el
    ; bloque no cruce de banco, no en qué banco arranca.
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_menu_celdas)
    adc #0
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; Un bit por posición, para el bitmap de switches. Sale más barata que ocho
; corrimientos y se lee con el índice que ya tenemos.
mascara:
    .byte $01,$02,$04,$08,$10,$20,$40,$80

; La tabla del HDMA que enmascara los objetos debajo de la ventana de mensaje:
; nada en las 144 líneas de arriba —en dos tramos, por los 7 bits del contador—
; y la ventana 1 prendida para los objetos en las 80 de abajo. Ver `armar_hdma`.
;
; **Fuera del banco 0**: el HDMA lee de donde diga `A1B3`, así que una tabla de
; ocho bytes que no cambia nunca no tiene por qué gastarlo.
hdma_mascara:
    .byte 127, $00
    .byte (VENTANA_LINEA - 127), $00
    .byte (LINEAS - VENTANA_LINEA), $02
    .byte 0

; Qué permiso hace falta para salir de una celda y para entrar en la de al
; lado, por dirección —arriba, derecha, abajo, izquierda—.
;
; Los pares son cruzados a propósito: para ir hacia arriba hay que poder salir
; por arriba de la celda de origen y poder entrar por abajo a la de destino. Es
; la regla de RM2k.
pass_salir:
    .byte PASS_UP, PASS_RIGHT, PASS_DOWN, PASS_LEFT
pass_entrar:
    .byte PASS_DOWN, PASS_LEFT, PASS_UP, PASS_RIGHT

; Las dos componentes de cada diagonal, indexadas por la dirección menos
; cuatro: primero la vertical y después la horizontal. De acá salen las dos
; eles que prueba `puede_celda_diag` y las dos poses que compara
; `encarar_diagonal`. Son RUTA_DIAGONALES de eventos.py.
diag_vert:
    .byte DIR_UP, DIR_DOWN, DIR_DOWN, DIR_UP
diag_horiz:
    .byte DIR_RIGHT, DIR_RIGHT, DIR_LEFT, DIR_LEFT

; Dónde empiezan los glifos compuestos de cada fase, indexados por la fase
; misma —0, 2, 4 o 6—: por eso los bancos van con un byte de relleno entre
; uno y otro. Ver `componer_char`. Se leen **una vez por glifo**, no por fila.
fuente_pre_lo:
    .word .loword(fuente_pre0), .loword(fuente_pre1)
    .word .loword(fuente_pre2), .loword(fuente_pre3)
fuente_pre_bk:
    .byte ^fuente_pre0, 0, ^fuente_pre1, 0, ^fuente_pre2, 0, ^fuente_pre3

; Qué bit de JOY1H mira cada dirección de `KeyInputProc` y qué número le guarda
; a la variable, en el orden de `CheckInput` —de mayor valor a menor—. El mismo
; orden que recorre `eventos.tecla_de` del lado del modelo; los números los
; emite el conversor, así que no están escritos dos veces.
tecla_dir_bit:
    .byte PAD_UP, PAD_RIGHT, PAD_LEFT, PAD_DOWN, 0
tecla_dir_val:
    .byte TECLA_VALOR_ARRIBA, TECLA_VALOR_DERECHA
    .byte TECLA_VALOR_IZQUIERDA, TECLA_VALOR_ABAJO

; Agregar, sacar o agrandar un renglón cambia `PARTIDA_BYTES`, y con él la
; cabecera: las partidas guardadas antes dejan de cargar, que es lo que tiene
; que pasar —ver `SRAM_BYTES`—. **Reordenar dos renglones sin cambiar el total
; no lo ve nadie**: la cabecera sale igual y una partida vieja cargaría
; corrida. La firma del conversor no mira esta tabla, que es fuente a mano.
partida_tabla:
    .word hero_x, 2
    .word hero_y, 2
    .word hero_dir, 1
    .word tile_x, 2
    .word tile_y, 2
    .word mapa_actual, 2
    .word grupo, 6              ; el grupo y cuántos son, que van seguidos
    .word tinte_r, 3            ; el tinte, menos la saturación, que vive lejos
    .word tinte_s, 1
    .word timer_seg, 5          ; segundos, sub, si corre y si se ve
    .word oro, 3
    .word switches, SWITCH_BYTES
    ; Qué tema está sonando y si está callado. Lo prende un `PlayBGM` de un
    ; evento, así que es estado del mundo como un switch: sin esto una partida
    ; cargada arranca con el tema del mapa inicial de la ROM en vez de con el
    ; que sonaba. Van seguidos en la BSS —`music_apagada` y después
    ; `tema_actual`— pero se piden por separado igual, porque que estén
    ; pegados es un detalle del orden en que se declararon y no una promesa.
    .word music_apagada, 1
    .word tema_actual, 2
    ; Y las variables, desde la RAM lejana. VARIABLES_N es al menos 1 —el
    ; conversor lo garantiza— porque un largo cero terminaría la tabla acá.
    .word FAR_VARIABLES, VARIABLES_N * 2
    .word FAR_HERO_VEL, 1       ; la velocidad del héroe, que las rutas cambian
    .word FAR_ITEMS, ITEMS_N    ; el inventario
    .word FAR_ACCESO, 1         ; los permisos de guardar y del menú
    .word FAR_EQUIPO, ACTORES_N * 10    ; el equipo de cada actor
    ; Y los HP de cada actor, que desde que hay batallas son estado de verdad.
    .word FAR_HP, ACTORES_N * 2
    ; Y los SP, por lo mismo desde que hay habilidades que gastarlos.
    .word FAR_SP, ACTORES_N * 2
    ; Y a qué gráfico le cambió el sprite un `ChangeSpriteAssociation`: un byte
    ; por actor. Viaja en la partida como en RM2k, y cruza el teletransporte.
    .word FAR_ACTOR_GRAF, ACTORES_N
    ; Y qué habilidades sabe cada actor: un bit por par (actor, habilidad), que
    ; `ChangeSkills` prende y apaga. Ver `FAR_HAB`.
    .word FAR_HAB, HAB_BYTES
    ; Y la experiencia y el nivel de cada actor que puede pelear. **Va
    ; última a propósito**: la pantalla de ranuras lee el nivel del líder de
    ; la SRAM contando desde el final de la partida —`EXP_NIVEL_EN_SRAM`—, y
    ; un renglón que se agregue detrás lo correría.
    .word FAR_EXP, EXP_K * 4
    .word 0, 0

; Las cuatro tablas que bajaron del banco 0 el 2026-09-13, para hacerle lugar
; al Game Over de `op_battle`. Las tres que se indexan se leen con
; `lda f:tabla, x` —absoluto largo, que no depende del banco de datos— y por eso
; van con X y no con Y: el 65816 no tiene `long,Y`. `hdma_mascara` no se indexa:
; su dirección y su banco se los pasa `armar_hdma` al canal de HDMA.

; Hacia dónde mira cada pose, de 0 a 11: la dirección es la pose entre tres.
dir_de_pose:
    .byte 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3

ppu_bajos:
    .byte $00,$00,$00,$00       ; $2101 OBSEL, $2102-3 OAMADD, $2104 OAMDATA
    .byte $00,$00,$00,$00       ; $2105 BGMODE, $2106 MOSAIC, $2107-8 BG1-2SC
    .byte $00,$00,$00,$00       ; $2109-A BG3-4SC, $210B-C BGxNBA
ppu_bajos_end:

; De $2115 a $2133: VRAM, modo 7, CGRAM, ventanas, capas visibles y color math.
; Los tres que no son cero son los que importan.
ppu_altos:
    .byte $80,$00,$00           ; $2115 VMAIN: avanzar tras el byte alto
    .byte $00,$00               ; $2118-9 VMDATA
    .byte $00,$00,$00,$00,$00   ; $211A-E modo 7
    .byte $00,$00               ; $211F-20 modo 7
    .byte $00,$00               ; $2121 CGADD, $2122 CGDATA
    .byte $00,$00,$00           ; $2123-5 selección de ventanas: la 1 se le
                                ; prende a los objetos por HDMA, sólo en las
                                ; líneas de la ventana de mensaje
    .byte $00,$FF,$00,$00       ; $2126-9 posiciones de ventanas: la 1 va de
                                ; punta a punta, para que tape todo objeto
    .byte $00,$00               ; $212A-B lógica de ventanas
    .byte $00,$00               ; $212C TM, $212D TS: ninguna capa visible
    .byte $10,$00               ; $212E TMW: la máscara vale para los objetos
                                ; de la pantalla principal. $212F TSW
    .byte $30,$00               ; $2130 CGWSEL: color math apagado. $2131
    .byte $E0,$00               ; $2132 COLDATA: color fijo negro. $2133
ppu_altos_end:
cero:
    .byte $00,$00

