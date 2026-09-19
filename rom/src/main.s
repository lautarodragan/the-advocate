; ---------------------------------------------------------------------------
; PoC de audio en Super Nintendo: reproduce un tema en loop, sin dibujar nada.
;
; El audio de la SNES lo maneja el SPC700, un procesador aparte con su propia
; memoria de 64 KB. El 65816 no puede tocar el DSP directamente: sólo puede
; hablarle al SPC700 por cuatro puertos.
;
; Al encender, el SPC700 corre una ROM interna que implementa un protocolo de
; carga. Lo usamos para meterle en memoria las muestras y un driver mínimo, y
; después ese driver se queda esperando pares (registro, valor) del DSP que le
; manda el 65816. O sea que toda la música la sigue manejando el 65816, igual
; que en la Mega Drive.
; ---------------------------------------------------------------------------

.p816
.smart

; --- puertos ---------------------------------------------------------------
INIDISP  = $2100        ; brillo y blanking
NMITIMEN = $4200        ; habilitación de NMI y joypads
RDNMI    = $4210        ; leerlo baja la bandera de NMI
TIMEUP   = $4211        ; leerlo baja la bandera de la IRQ
VTIMEL   = $4209        ; en qué línea cae la IRQ de la música
VTIMEH   = $420A
; La línea de la IRQ de la música: lejos del vblank, que es donde el lazo
; hace sus DMA con el tiempo contado, y en el medio de la parte visible, donde
; lo que haya corriendo puede esperar lo que tarde un cuadro de música.
IRQ_LINEA = 112
HVBJOY   = $4212        ; bit 7: estamos en vblank
MEMSEL   = $420D        ; bit 0: la ROM de los bancos $80 en adelante, rápida
; El código corre desde el espejo del banco $80, no desde el banco 0. Los
; bancos $80 a $BF son los mismos que $00 a $3F —la RAM baja, los registros y
; la ROM en los mismos lugares—, pero con MEMSEL en 1 la ROM de allá se lee a
; 3,58 MHz en vez de 2,68: todo lo que la CPU saca del cartucho, empezando por
; las instrucciones, va un tercio más rápido. Es el FastROM de la cabecera.
; Lo único que hay que hacer es entrar: el reset y las interrupciones llegan
; por vectores de dieciséis bits, o sea al banco 0, y saltan al espejo con un
; `jml`; de ahí en más cada `jsr` y cada `rts` se quedan en el banco en el que
; están. Desde el 2026-09-11, porque la apertura con lluvia, trueno y texto
; perdía un cuadro de cada tres.
RAPIDO   = $800000
STAT78   = $213F        ; bit 4: 0 = consola NTSC, 1 = PAL
HDMAEN   = $420C        ; canales de DMA por scanline
APUIO0   = $2140        ; los cuatro puertos hacia el SPC700
APUIO1   = $2141
APUIO2   = $2142
APUIO3   = $2143

; El comando del driver del SPC700 que lo manda de vuelta a la ROM del IPL.
; Ver `DRIVER` en tools/audio/snes_music.py y el lazo de `reset` que lo usa.
APU_CMD_IPL = 4

; La consola multiplica y divide por hardware, que es lo único que hace falta
; para el tinte de pantalla: escala cada canal por un valor de 0 a 200 con 100
; como neutro, o sea multiplicar y dividir por cien. Las dos son exactas y con
; enteros, así que la referencia en Python puede hacer la misma cuenta y dar
; siempre lo mismo.
;
; El producto tarda 8 ciclos en estar listo y el cociente 16. No hay que
; esperarlos con un lazo: alcanza con no leer el resultado enseguida, y el
; código que hay en el medio ya alcanza.
WRMPYA   = $4202        ; multiplicando de 8 bits
WRMPYB   = $4203        ; multiplicador: escribirlo arranca la cuenta
RDMPYL   = $4216        ; el producto de 16 bits
WRDIVL   = $4204        ; dividendo de 16 bits
WRDIVH   = $4205
WRDIVB   = $4206        ; divisor de 8: escribirlo arranca la cuenta
RDDIVL   = $4214        ; el cociente de 16 bits

; --- el PPU ----------------------------------------------------------------
BGMODE   = $2105        ; qué modo gráfico y con cuántos bits por pixel
BG1SC    = $2107        ; dónde vive el tilemap de BG1 y de qué tamaño es
BG2SC    = $2108        ; lo mismo para BG2, la capa que tapa al héroe
BG2HOFS  = $210F        ; su scroll, que tiene que ir con el de BG1
BG2VOFS  = $2110
BG12NBA  = $210B        ; dónde viven los tiles de BG1 y BG2
BG1HOFS  = $210D        ; scroll horizontal de BG1 (se escribe dos veces)
BG1VOFS  = $210E        ; scroll vertical
VMAIN    = $2115        ; cómo avanza el puntero de VRAM tras cada escritura
VMADDL   = $2116        ; dirección de VRAM, en palabras
VMDATAL  = $2118        ; y el dato, de a una palabra con VMAIN en $80
CGADD    = $2121        ; índice de CGRAM
TM       = $212C        ; qué capas se ven en la pantalla principal
OBSEL    = $2101        ; tamaño de los sprites y dónde viven sus tiles
OAMADDL  = $2102        ; índice dentro de OAM, en palabras
OBJSEL_TM = $212C
JOY1H    = $4219        ; control 1: arriba, abajo, izquierda, derecha y más
JOY1L    = $4218        ; y el otro byte, donde viven A, X, L y R

; Los bits del control que nos interesan, tal como aparecen en JOY1H.
PAD_RIGHT = $01
PAD_LEFT  = $02
PAD_DOWN  = $04
PAD_UP    = $08
; Y start, que hasta la pantalla de título no lo miraba nadie: el juego se
; camina con la cruceta y se habla con A.
PAD_START = $10

; A vive en el otro byte. Los dieciséis bits del control son, de arriba hacia
; abajo, B Y select start arriba abajo izquierda derecha A X L R y cuatro de
; relleno; JOY1H trae los ocho de más peso y JOY1L los ocho de menos, así que
; A es el bit 7 de JOY1L.
PAD_A     = $80

; B vive con los otros en JOY1H, y es el de más peso de los dieciséis. Lo usa
; la elección para cancelar; caminar no lo mira.
PAD_B     = $80

; --- DMA, canal 0 ----------------------------------------------------------
DMAP0    = $4300        ; modo de transferencia
BBAD0    = $4301        ; registro del PPU al que va
A1T0L    = $4302        ; origen: dirección y banco
A1B0     = $4304
DAS0L    = $4305        ; cuántos bytes
MDMAEN   = $420B        ; arrancar

; --- HDMA, canales 1 y 2 ---------------------------------------------------
; El DMA de siempre transfiere todo de una, con la pantalla apagada o en el
; vblank. El HDMA es otra cosa: el mismo hardware, pero disparado **una vez por
; scanline**, así que un registro del PPU puede valer una cosa arriba de la
; pantalla y otra abajo. Es lo que usan los juegos para las barras de estado y
; los degradés de cielo, y acá es lo que clava la ventana de mensaje.
;
; Cada canal lee una tabla de la RAM con entradas `[cuántas líneas][valor...]`
; y termina con un cero. El contador es de 7 bits, o sea 127 líneas como mucho.
DMAP1    = $4310
BBAD1    = $4311
A1T1L    = $4312
A1B1     = $4314
DMAP2    = $4320
BBAD2    = $4321
A1T2L    = $4322
A1B2     = $4324
DMAP3    = $4330
BBAD3    = $4331
A1T3L    = $4332
A1B3     = $4334
HDMA_VENTANA = $0E      ; los canales 1, 2 y 3 prendidos a la vez
; La ventana 1 del PPU, que no es la de mensaje: es la máscara con la que se
; esconden los objetos debajo de ella. Ver `armar_hdma`.
WOBJSEL  = $2125        ; qué ventanas del PPU enmascaran objetos
WH0      = $2126        ; el borde izquierdo de la ventana 1
WH1      = $2127        ; y el derecho
TMW      = $212E        ; a qué capas de la pantalla principal se les aplica

; El puerto de la WRAM. Sirve para lo que el DMA normal no puede hacer solo:
; copiar de la ROM a la RAM. El DMA va siempre del bus A al bus B, y la WRAM
; tiene su ventana en el bus B, así que apuntando WMADD a dónde se quiere
; escribir y mandando a $2180 se copia ROM -> RAM a la misma velocidad que
; cualquier otro DMA.
WMDATA   = $2180
; --- la RAM del banco 1 ------------------------------------------------------
; La BSS del banco 0 está llena —7680 de 7680— y el ZEROPAGE tiene doce bytes
; libres. La consola tiene 128 KB de WRAM y la ROM usa ocho: al resto se llega
; por esta misma ventana, apuntando WMADD y leyendo o escribiendo $2180 con
; auto-incremento. No es direccionamiento normal —no se puede indexar— así que
; sirve para lo que se guarda y se recorre de a poco, no para lo que se dibuja.
;
; Hoy lo usa el estado de los intérpretes paralelos: 840 bytes que en el banco 0
; no entraban. El día que haya variables de RM2k —cinco mil, diez kilobytes— van
; acá también.
FAR_PAR_ESTADO = $2000      ; EV_MAX entradas de PAR_BYTES
FAR_PAR_LISTA  = $2400      ; PARALELO_MAX entradas de PAR_LISTA_BYTES
; Las variables de RM2k, una palabra con signo por ranura. Cuántas son lo dice
; el conversor —`VARIABLES_N`—, que le da ranura sólo a las que nombran las
; páginas de los mapas de la ROM; el bytecode habla de ranuras. Se leen y
; escriben por la ventana, `var_leer` y `var_escribir`, y viajan en la
; partida: `partida_tabla` las copia desde acá, que el DMA alcanza igual que
; el banco 0 porque WMADD es una dirección de diecisiete bits.
FAR_VARIABLES  = $2600
; Y el inventario, después de las variables —que son hasta 256, el conversor
; lo garantiza—: un byte por ítem del LDB, indexado por el número de RM2k —el
; 0 no se usa— y topado en ITEM_MAX, como `Game_Party::AddItem`. Viaja en la
; partida y se limpia con las variables.
FAR_ITEMS      = $2800
; Y el equipo de cada actor del LDB, por número de actor: cinco palabras
; —arma, escudo, armadura, casco, accesorio— con el número de ítem o 0. Arranca
; con el equipo inicial de la base, que `equipo_inicial_poner` copia en el
; reset, y viaja en la partida.
FAR_EQUIPO     = $2C00
; Y el estado del azar, dos bytes antes: un xorshift de dieciséis bits, el
; mismo que `azar_siguiente` en eventos.py, sembrado en el reset. Va acá y no
; en la página directa porque la página directa quedó en 258 de 256 al
; intentarlo; el azar se pide pocas veces y el puerto no lo nota.
FAR_AZAR       = $25FE
; Y la velocidad del héroe, de 1 a 6, un byte antes: las órdenes 28 y 29 de una
; ruta forzada la suben y la bajan y **queda así**, también para el pad —RM2k
; sólo repone la frecuencia al terminar la ruta, `original_move_frequency`; la
; velocidad no—. Viaja en la partida. Se lee una vez por paso.
FAR_HERO_VEL   = $25FD
; Y los permisos, un byte antes: `ChangeSaveAccess`, `ChangeMainMenuAccess` y
; `ChangeEscapeAccess` los apagan y los prenden, y el bit 7 es el pedido de
; menú de RM2k, `menu_calling`: B lo prende y el héroe lo atiende cuando está
; quieto. Los bits van en "prohibido" para que el cero del reset sea "todo
; permitido", que es como arranca RM2k. Viaja en la partida, como allá.
;
; El de escapar se guarda y **todavía no lo lee nadie**: la huida es de la
; batalla. Está porque es un bit y porque sin él no compilan 30 de las 39
; páginas del juego con `EnemyEncounter` que hoy se caen; ver ACCESO_BIT en
; eventos.py.
FAR_ACCESO     = $25FC
ACCESO_SIN_GUARDAR = $01
ACCESO_SIN_MENU    = $02
ACCESO_SIN_ESCAPAR = $04
ACCESO_PEDIDO      = $80
; --- la batalla: su estado en la RAM lejana -------------------------------------
;
; **La RAM lejana tiene un mapa y hay que respetarlo.** El 2026-09-12 el cartel
; se puso en $30E8, que era donde vivía el estado del MSU-1, y la ROM dejó de
; detectar el chip: la música se calló y ninguna prueba lo vio. De $2000 a
; $30FA está todo tomado —los intérpretes paralelos, las variables, el
; inventario, el equipo, el clima, los efectos de sonido, el giro, el cartel— y
; de $3100 a $3600 va el reparto de la ARAM. Así que esto arranca en $3700, que
; es el primer lugar donde no hay nadie.
;
; Los HP de cada actor del LDB, una palabra por número de actor. **Son estado
; de verdad desde que hay batallas**: hasta el 2026-09-12 nadie bajaba de los
; máximos y `ChangeHP` compilaba a nada. Viajan en la partida, detrás del
; equipo, y el reset los pone llenos.
FAR_HP = $3700

; La RAM lejana con el banco adelante, para los pocos que la leen desde afuera
; con `lda f:`: es lo mismo que `BAT_LARGO`, que quedó con nombre de pelea.
FAR_LARGO = $7E0000

; Y los SP, que son estado por lo mismo que los HP desde que las habilidades
; se pueden usar: cada una cuesta su `sp_cost` y `Scene_Battle` se lo descuenta
; al que la usa. Arrancan llenos desde `actor_spmax` y viajan en la partida,
; detrás de los HP. `FAR_HP` son ACTORES_N palabras —61 actores, 122 bytes— o
; sea que llega hasta $3779; esto arranca en $3780 y termina antes de $3800.
FAR_SP = $3780

; Y a qué gráfico le cambió el sprite un `ChangeSpriteAssociation` a cada actor
; del LDB, un byte por número de actor: el índice en la tabla de gráficos del
; mapa —la misma que resuelve la orden 34 de una ruta— o $FF si conserva el del
; LDB. Viaja en la partida, como en RM2k, y **cruza el teletransporte**: es lo
; que lo diferencia de la orden 34 sobre el héroe, que se repone al cargar.
;
; Va en $3800 y la pelea se corre a $3A00. Podría haber ido pegado a `FAR_HP`
; —hoy sobra lugar de sobra hasta $37FF— pero entonces su dirección dependería
; de `ACTORES_N`, que lo emite el conversor, y el mapa de la RAM lejana quedaría
; a merced de un número que no está escrito acá. Ver arriba: este mapa ya se
; pisó una vez y la música quedó muda un día entero.
FAR_ACTOR_GRAF = $3800
ACTOR_GRAF_NINGUNO = $FF

; --- los encuentros al azar: su estado en la RAM lejana ----------------------
;
; Nueve bytes en $3900, que es el hueco que queda entre `FAR_ACTOR_GRAF` —61
; bytes desde $3800— y la pelea. **No viaja en la partida**, como no viajan los
; HP de una pelea sin cerrar: al cargar, el acumulado arranca en cero, que es
; lo mismo que pasa al entrar a un mapa.
;
; En el banco 0 no entraba: la BSS está en 7680 de 7680, medido el 2026-09-13
; metiéndole un `.res 64` y mirando el corte del ensamblador.
FAR_ENCUENTRO = $3900
ENC_N     = FAR_ENCUENTRO + 0   ; pasos dados desde el último encuentro
ENC_IDX   = FAR_ENCUENTRO + 1   ; la fila de la tabla, que no baja nunca
ENC_PIDE  = FAR_ENCUENTRO + 2   ; salió uno y se cobra en el cuadro que viene
ENC_SEM   = FAR_ENCUENTRO + 3   ; palabra: el xorshift, con semilla propia
ENC_BASE  = FAR_ENCUENTRO + 5   ; palabra: 1/pasos en 1/65536; 0 es apagados
ENC_REG   = FAR_ENCUENTRO + 7   ; el registro de este mapa, o ENC_SIN
; Un mapa sin tropas propias y sin áreas que lo tapen.
ENC_SIN   = $FF
; Las ocho filas de la tabla de `UpdateEncounterSteps`, y cuántos bytes de
; umbral lleva cada registro: siete —el de la fila 0 es 0 y no se guarda— más
; uno de relleno, para que el índice sea un corrimiento y no una multiplicación.
ENC_FILAS  = 8
ENC_STRIDE = 8

; Y el estado de la pelea, que **no** viaja en la partida: una batalla no se
; puede guardar en RM2k tampoco.
FAR_BATALLA = $3A00
; La misma dirección pero larga, para los pocos que la tocan desde afuera de
; la pelea: `op_battle` corre con el banco de datos del bytecode.
BAT_LARGO = $7E0000
; **Todo lo de acá se nombra con dirección de dieciséis bits, no larga**, y el
; código de la pelea corre con el banco de datos en $7E. Es lo que le deja usar
; direccionamiento absoluto: `inc`, `stz`, `ldx` y `cpy` no tienen modo largo,
; así que con `f:` habría que pasar cada uno por el acumulador. Y no le cuesta
; nada a lo demás: en el banco $7E las direcciones de $0000 a $1FFF **son** la
; RAM baja del banco 0, así que `temp`, `comp_*` y `grupo` se siguen leyendo
; como siempre. Lo que sí cambia son las tablas de la ROM, que van con `f:`.
BA_TROPA   = FAR_BATALLA + 0      ; la tropa, como número de RM2k
BA_RESULT  = FAR_BATALLA + 2      ; 0 victoria, 1 huida, 2 derrota
BA_SEM     = FAR_BATALLA + 3      ; el xorshift de la pelea, con semilla propia
BA_NACT    = FAR_BATALLA + 5      ; cuántos actores
BA_NENE    = FAR_BATALLA + 6      ; cuántos enemigos
BA_MODO    = FAR_BATALLA + 7
BA_ACTOR   = FAR_BATALLA + 8      ; a quién se le está pidiendo la orden
BA_ORDEN   = FAR_BATALLA + 9      ; qué orden marca el cursor
BA_BLANCO  = FAR_BATALLA + 10     ; qué enemigo marca el cursor
BA_HUIDA   = FAR_BATALLA + 11     ; la chance de escapar, que sube al fallar
BA_I       = FAR_BATALLA + 12     ; por cuál de la ejecución va el turno
BA_ESPERA  = FAR_BATALLA + 13     ; cuadros que le quedan al mensaje
BA_MTIPO   = FAR_BATALLA + 14     ; qué dice el mensaje
BA_MQUIEN  = FAR_BATALLA + 15
BA_MBLA    = FAR_BATALLA + 16
BA_MDANO   = FAR_BATALLA + 17     ; palabra
BA_NACC    = FAR_BATALLA + 19     ; cuántas acciones tiene el turno
BA_T0      = FAR_BATALLA + 20     ; palabras de paso, que cualquiera pisa
BA_T1      = FAR_BATALLA + 22
BA_T2      = FAR_BATALLA + 24
BA_S0      = FAR_BATALLA + 26     ; y las que sobreviven a un `jsr`
BA_S1      = FAR_BATALLA + 28
BA_S2      = FAR_BATALLA + 30
BA_S3      = FAR_BATALLA + 32
BA_S4      = FAR_BATALLA + 34
BA_S5      = FAR_BATALLA + 36
BA_S6      = FAR_BATALLA + 38
; Si el renglón que se compone muestra además los HP máximos, o sea si es del
; grupo. Tiene byte propio y no un `BA_T2 + 2` prestado, que es lo que era y
; caía justo encima de `BA_S0`: el lazo de los enemigos se reiniciaba solo y
; la pantalla no llegaba a aparecer nunca.
BA_CONMAX  = FAR_BATALLA + 40
; El audio de la pelea, en los bytes que quedaban sueltos antes de `BA_ACC`.
; `BA_TEMA_ANT` es el tema que sonaba en el mapa —$FF si no sonaba nada—, que
; es el `before_battle_music` de RM2k: al terminar la pelea vuelve. `BA_SE2`
; es el efecto que falta disparar en el mensaje en curso, o $FFFF: RM2k toca
; dos por golpe —el del ataque y el del daño, separados por una espera— y acá
; el segundo sale cuando `BA_ESPERA` llega a `BA_SE2_CUADROS`.
BA_TEMA_ANT = FAR_BATALLA + 41
BA_SE2      = FAR_BATALLA + 42     ; palabra
; Qué escena de batalla está puesta en BG1, o $FF si esta pelea va sobre
; negro. Ver `escena_subir`.
BA_ESCENA   = FAR_BATALLA + 44
; Y en qué lugar de `tropa_id` cayó la tropa de esta pelea, que es lo que
; `escena_de` indexa. $FF: el cartucho no la lleva.
BA_TROPA_K  = FAR_BATALLA + 45
; Y el ítem que se está usando, desde el 2026-09-13. Va **detrás de
; `BA_UNO`**, que termina en +575, porque entre +40 y +48 ya no queda nada y
; correr `BA_ACC` sería mover todo lo demás.
;
; Estaba en +320 hasta que `BA_BYTES` pasó de 18 a 40 —los SP y los cuatro
; modificadores de parámetro de las habilidades— y `BA_UNO` se le vino encima.
BA_ITEM_N    = FAR_BATALLA + 576   ; cuántos hay en la lista
BA_ITEM_SEL  = FAR_BATALLA + 577   ; cuál marca el cursor
BA_ITEM_ARR  = FAR_BATALLA + 578   ; el primero que se ve
BA_ITEM_BLA  = FAR_BATALLA + 579   ; a qué actor se le da; desde el 2026-09-13
                                   ; también el blanco de una habilidad que
                                   ; cura, que elige con el mismo modo
BA_MITEM     = FAR_BATALLA + 580   ; el `k` del ítem del mensaje en curso
BA_ACTOR2    = FAR_BATALLA + 581   ; un contador de actores que `BA_S0` no puede
BA_MCURA     = FAR_BATALLA + 582   ; palabra: cuánto curó
BA_ACC_ITEM  = FAR_BATALLA + 584   ; el `k` que eligió cada actor, uno por byte
BA_ITEM_LISTA = FAR_BATALLA + 592  ; la lista, un `k` por byte
BA_ITEM_MAX = 64
; --- las habilidades, desde el 2026-09-13 ---------------------------------
;
; Detrás de `BA_ITEM_LISTA`, que termina en +656.
BA_HAB_N     = FAR_BATALLA + 656   ; cuántas sabe el que está ordenando
BA_HAB_SEL   = FAR_BATALLA + 657   ; cuál marca el cursor
BA_MHAB      = FAR_BATALLA + 658   ; el `k` de la del mensaje en curso
BA_ACC_HAB   = FAR_BATALLA + 660   ; el `k` que eligió cada actor, uno por byte
BA_HAB_LISTA = FAR_BATALLA + 672   ; su lista, un `k` por byte
BA_HAB_MAX   = 16                  ; BA_HAB_FILAS por BA_HAB_COLUMNAS, y sobra
BA_MEFECTO   = FAR_BATALLA + 688   ; palabra con signo: cuánto hizo la última
BA_ACC     = FAR_BATALLA + 48     ; dos bytes por combatiente: orden y blanco
BA_EJEC    = FAR_BATALLA + 72     ; el orden de ejecución, un combatiente por byte
BA_CAND    = FAR_BATALLA + 88     ; los vivos de un lado, para elegir blanco
BA_UNO     = FAR_BATALLA + 96     ; los combatientes, BA_BYTES cada uno

; Los combatientes: los cuatro primeros son el grupo y los ocho siguientes la
; tropa. Que el lugar sea fijo y no una lista compactada es lo que hace que un
; muerto se siga viendo en su renglón, como en la pantalla.
BA_GRUPO_MAX = 4
BA_ENEMIGOS_MAX = 8
BA_COMB_MAX = BA_GRUPO_MAX + BA_ENEMIGOS_MAX
; Eran 18 hasta el 2026-09-13, que es cuando entraron los SP y los cuatro
; modificadores de parámetro que dos de las siete habilidades del grupo
; mueven. 40 además es cómodo: el desplazamiento sale con cinco `asl` y una
; suma, ver `ba_x`.
BA_BYTES  = 40
BA_HP     = 0               ; palabra
BA_HPMAX  = 2
; **Los cuatro parámetros de acá son los efectivos**, o sea `AdjustParam` de
; game_battler.cpp: `clamp(base + modificador, 1, 999)`. El base y el
; modificador viven más abajo y se guardan enteros porque un modificador que
; sobreviva al recorte no se puede despejar de la resta; `ba_mod` los rehace.
BA_ATK    = 4
BA_DEF    = 6
BA_AGI    = 8
BA_SORT   = 10              ; el `agi + azar` con el que se ordena el turno
BA_TXT    = 12              ; el número de texto de su nombre
BA_HIT    = 14              ; byte
BA_CRIT   = 15
BA_FLAGS  = 16
BA_NUMERO = 17              ; el actor del LDB, o el lugar en la tropa
BA_SP     = 18              ; palabra: los SP que le quedan
BA_SPMAX  = 20
BA_MATK   = 22              ; los cuatro modificadores, con signo
BA_MDEF   = 24
BA_MSPI   = 26
BA_MAGI   = 28
BA_BATK   = 30              ; y los cuatro bases
BA_BDEF   = 32
BA_BSPI   = 34
BA_BAGI   = 36
BA_SPI    = 38              ; el espíritu efectivo, que `CalcSkillEffect` pide
BAF_DEF   = $01             ; se está defendiendo
BAF_ACTOR = $02             ; es del grupo
BAF_HAY   = $04             ; la ranura está ocupada

; Los tres resultados y las tres órdenes, en el orden de `tools/port/batalla.py`.
BA_VICTORIA = 0
BA_HUIDA_R  = 1
BA_DERROTA  = 2
BA_ATACAR   = 0
BA_DEFENDER = 1
BA_HUIR     = 2
BA_ITEM     = 3
BA_HABILIDAD = 4
; Los modos de la pantalla, como `pantallas.BA_ELIGE_ORDEN` y compañía. **El
; orden importa**: más de un lugar pregunta `cmp #BA_M_MENSAJE / bcs` para
; decir "mensaje o fin", así que los que eligen algo van todos antes.
BA_M_ORDEN  = 0
BA_M_BLANCO = 1
BA_M_ITEM   = 2
BA_M_ACTOR  = 3
BA_M_HAB    = 4
BA_M_MENSAJE = 5
BA_M_FIN    = 6
; Qué dice el mensaje.
BA_MSG_ATAQUE = 0
BA_MSG_DEFIENDE = 1
BA_MSG_NO_HUYO = 2
BA_MSG_HUYO = 3
BA_MSG_VICTORIA = 4
BA_MSG_DERROTA = 5
BA_MSG_ITEM = 6
BA_MSG_HAB = 7
; Cuántos cuadros se queda un mensaje si nadie aprieta A. Son dos segundos, que
; es lo que tarda en leerse un renglón, y A lo saltea.
BA_MSG_CUADROS = 120
; Cuándo sale el segundo efecto del golpe: `Scene_Battle_Rpg2k` pone el del
; ataque al empezar la acción y el del daño en el sub-estado del mensaje, con
; un `SetWait(4,4)` en el medio. Acá el mensaje dura `BA_MSG_CUADROS` y el
; segundo efecto sale veinticuatro cuadros más tarde, que es lo que se
; distingue con una sola voz: los dos juntos serían uno solo, porque el efecto
; nuevo le pisa la voz al anterior.
BA_SE2_CUADROS = BA_MSG_CUADROS - 24
; El acierto de un actor sin arma que lo cambie: `Game_Actor::GetHitChance`.
BA_ACIERTO_ACTOR = 90
; El tope del daño —`MaxDamageValue()` de RM2k— y el del promedio de agilidad
; que entra en la cuenta de la huida: doscientos por el promedio tiene que
; entrar en dieciséis bits, y el enemigo más ágil del juego tiene 300.
BA_DANO_MAX = 999
BA_AGI_TOPE = 320
; El tope de un parámetro efectivo: `Game_Actor::GetAtk` y sus hermanas, o sea
; el `MaxStatBattleValue` de RM2k.
BA_PARAM_MAX = 999
; `rpg::Skill::Type_switch`, la que prende un switch y no hace nada más. Es el
; único tipo que este port distingue del normal: las siete que el grupo de la
; intro sabe son o `normal` o `switch`.
BA_HAB_TIPO_SWITCH = 3

; Cursor (2), espera (2), si está corriendo (1) y de qué página (2). **Ocho y
; no siete**: el séptimo byte no se usa y a cambio el índice sale con tres
; `asl` en vez de un `x * 8 - x`, que son seis bytes de banco 0 y unos ciclos
; en cada paralelo y en cada cuadro. EV_MAX por ocho son 960 bytes, así que
; sigue entrando abajo de `FAR_PAR_LISTA`.
PAR_BYTES = 8

; Y lo que la lista de paralelos guarda de cada uno: el evento (1), el puntero
; a su bytecode (3) y de qué página salió (2). Los tres últimos son lo que
; antes se volvía a sacar del cartucho en cada cuadro y por cada paralelo, con
; `pagina_desde_eleg`: veinticuatro bytes de cabecera de página leídos por la
; ventana de banco, para contestar lo mismo que la vez anterior. La lista se
; rehace entera en `aplicar_paginas`, o sea exactamente cuando la página activa
; puede haber cambiado, así que anotarlo ahí es la misma respuesta y una vez.
; Ocho por lo mismo que `PAR_BYTES`: los dos que sobran se pagan en RAM lejana,
; que hay de sobra, y se ahorran en banco 0 y en ciclos. PARALELO_MAX por ocho
; son 384 bytes y hasta `FAR_AZAR` hay 508.
PAR_LISTA_BYTES = 8
WMADDL   = $2181
WMADDM   = $2182
WMADDH   = $2183

; La VRAM se direcciona por palabras y son 64 K en total. Cómo se reparte entre
; los tiles del fondo, los de la capa de encima, los de los sprites y los dos
; tilemaps no está acá: lo decide el conversor mapa por mapa y llega en
; mapdata.inc, junto con los valores ya armados de OBSEL y BG12NBA.
;
; No es una comodidad: el mapa que más tiles de fondo gasta necesita 620, y otro
; con muchos personajes necesita 512 de sprite. Los dos juntos no entran, y
; ninguno de los dos repartos sirve para todos los mapas.

; El orden de prioridades del modo 3, de adelante hacia atrás, es
;   objetos 3 / BG1 1 / objetos 2 / BG2 1 / objetos 1 / BG1 0 / objetos 0
; así que con el mapa en BG1 prioridad 0, el héroe en objetos prioridad 1 y la
; capa de encima en BG2 prioridad 1, el orden de RM2k sale del hardware sin
; ningún truco. Los eventos marcados "above" van en objetos prioridad 2, que es
; lo único que queda por encima de BG2.
; En el byte de atributos de OAM —vhoopppN— la prioridad son los bits 5 y 4, o
; sea que el valor va corrido cuatro lugares: prioridad 1 es $10 y no $20. Con
; $20 el héroe quedaba en prioridad 2, que en este orden está *adelante* de
; BG2 1, y entonces se dibujaba encima de la capa que tenía que taparlo.
;
; Los dos valores los arma el conversor —la de cada NPC ya viene en su byte de
; atributos— y la del héroe llega como HERO_PRIORITY en mapdata.inc. Tenerlos
; acá además era la duplicación de siempre: dos lados que se pueden equivocar
; igual y una comparación que da cero. La del héroe es $10 en toda ROM que no
; sea la de `snes-encima`, que la sube a $20 para ejercitar la prioridad 2.

; Las poses de RM2k son de 24x32 y la SNES no tiene ese tamaño, así que se usa
; el objeto de 32x32 y sobra un poco a los costados. El valor de OBSEL, que
; lleva ese tamaño y la página de los tiles, lo arma el conversor.

; Las 12 poses: 3 frames de caminata por 4 direcciones. En RM2k las direcciones
; van 0=arriba, 1=derecha, 2=abajo, 3=izquierda, y el frame del medio es la
; pose parada.
DIR_UP    = 0
DIR_RIGHT = 1
DIR_DOWN  = 2
DIR_LEFT  = 3

; A velocidad 4, que es la del héroe, se avanzan dos pixeles por cuadro y la
; animación cambia de frame cada seis.
; WALK_SPEED ya no existe: el héroe avanza según su velocidad, ver
; `paso_medio_por_vel`. Quedó el renglón para que nadie lo busque.
; ANIM_FRAMES = 6 era cada cuántos cuadros cambiaba el frame de la caminata;
; ahora depende de la velocidad del héroe: ver `anim_por_vel`.

; El sprite se dibuja centrado sobre su celda de 16x16 y apoyado por los pies.
; Al objeto de 32 hay que restarle además los 4 que sobran de cada lado.
SPRITE_OFF_X = 8
SPRITE_OFF_Y = 16

; --- la ventana del mapa ---------------------------------------------------
; El tilemap del PPU son 64x32 celdas, o sea 512x256 pixeles, y la pantalla son
; 256x224. El mapa entero no entra: los del juego llegan a 1000x80 celdas. Lo
; que hay en la VRAM es una ventana que se mueve con la cámara.
;
; La ventana no se desplaza: se la trata como un toro. La celda (mx,my) del mapa
; vive siempre en la ranura (mx mod 64, my mod 32), y el scroll por hardware ya
; hace la vuelta sola porque 1024 —el máximo del registro— es múltiplo de 512.
; Así, cuando la cámara cruza el borde de una celda, sólo hay que reescribir la
; columna o la fila que acaba de entrar: la que sale está 32 columnas o 4 filas
; afuera de la pantalla y nadie la mira mientras tanto.
WINDOW_COLS = 64
WINDOW_ROWS = 32

; Cuántas celdas de 8x8 llega a tocar la pantalla. Son 32 y 28 justas más una,
; porque el scroll casi nunca cae parado sobre una celda.
VIEW_COLS = 33
; Cuántas columnas de más se tienen cargadas a cada lado de la pantalla. Es
; por la sacudida de pantalla, que corre el dibujo hasta 19 pixeles sin mover
; la cámara: sin margen, la columna que asoma por la izquierda es una ranura
; del toro que nadie escribió. Cuatro son 32 pixeles, y el toro tiene 64
; columnas para 33 visibles, así que sobran.
MARGEN_COLS = 4
; En qué cuadro termina el arranque, contado desde el reset. El arranque
; —cargar el mapa, subir el banco al SPC700— tarda lo que tarda, y eso cambiaba
; con cada cambio de código o de datos: un bucle más y el lazo principal
; arrancaba un cuadro después, y cada receta que compara cuadros en movimiento
; lleva ese número medido a mano. Ahora se espera hasta este cuadro y el lazo
; arranca siempre en el mismo. Una ROM cuyo arranque tarde más que esto sale
; sin esperar, más tarde, pero igual de fijo para ella.
;
; Eran 64 hasta el 2026-09-06, cuando el cartucho pasó a llevar varios temas: el
; banco de muestras lo comparten todos y creció, y **la subida al SPC700 va byte
; a byte con acuse**, que es lo caro —unos 1,4 cuadros por kilobyte—. El número
; está medido y sale del techo, no del banco de hoy: con la ARAM llena, 62310 B,
; la ROM llega al lazo en el cuadro 101. 112 lo cubre con margen, y de paso hace
; que llenar la ARAM no cueste nada: el arranque ya está pagado.
;
; Lo que compraría los 48 cuadros de vuelta es un driver que sepa recibir datos
; por los cuatro puertos en vez de por el protocolo del IPL, que manda uno.
; Está anotado en "Lo que falta".
BOOT_CUADROS = 112
VIEW_ROWS = 29

; La ventana de mensaje: 256x80 pegada abajo de una pantalla de 224 líneas, o
; sea las diez filas de celdas que van de la 18 a la 27. Los mismos números
; están en `tools/port/ventana.py`, que es de donde salen: 80 de alto y pegada al
; pie, como la pone RM2k.
VENTANA_FILA  = 18
VENTANA_FILAS = 10
VENTANA_LINEA = VENTANA_FILA * 8        ; y en scanlines: la 144
LINEAS = 224

; El scroll vertical de BG2 mientras se dibuja la ventana. El PPU muestra en el
; primer scanline la línea `vofs + 1`, así que para que en la línea 144 caiga la
; fila 0 del tilemap propio hace falta `vofs + 1 + 144 = 0` módulo 256, que es
; el alto de un tilemap de 32x32. De ahí el 111. El horizontal va en cero.
VENTANA_VOFS = 111

; El tilemap de 64x32 son dos pantallas de 32 al lado de la otra, y la
; segunda no vive 32 palabras más adelante sino 1024.
VIEW_COLS_TILEMAP = 32

; Los dos bytecodes que esta ROM lee, generados desde tools/protocol/: el de los
; eventos, que interpreta `correr_codigo`, y el del stream de música, que lee
; `irq_musica`. Cada uno lo declara un archivo que no es ni del que emite los
; bytes ni del que los lee.
;
; El de eventos venía adentro de mapdata.inc hasta el 2026-09-14, o sea que el
; número de un opcode llegaba acá dentro de los datos de un mapa; el de música
; estaba escrito a mano de los dos lados hasta el 2026-09-15.
.include "event_opcodes.inc"
.include "music_opcodes.inc"

.include "musicdata.inc"
.include "mapdata.inc"

; El área de texto son ocho filas de celda, o sea cuatro renglones de a dos, y
; el buffer del compositor mide un renglón. Van acá abajo y no arriba porque
; `VENTANA_TEXTO_COLS` lo emite el conversor.
VENTANA_LINEAS_TEXTO = VENTANA_TEXTO_FILAS / 2
TEXTO_BUF_BYTES = VENTANA_TEXTO_COLS * 2 * 32

.segment "ZEROPAGE"
source:     .res 3      ; puntero al bloque que estamos subiendo
music:      .res 3      ; puntero dentro del stream de música
camara_x:   .res 2      ; dónde está mirando la cámara, en pixeles
camara_y:   .res 2
scroll_y:   .res 2      ; lo mismo menos uno, que es lo que el PPU quiere
pad:        .res 1      ; lo que el control tenía apretado este cuadro
pad_a:      .res 1      ; y A, que vive en el otro byte del control
pad_a_ant:  .res 1      ; cómo estaba el cuadro pasado, para ver el flanco
; La elección abierta, si hay una: es `ShowChoice`. Mientras `eleg_activo` esté
; puesto hay una ventana de mensaje en pantalla con las opciones y la página
; está bloqueada, igual que con un mensaje común.
;
; El cursor no es un sprite ni un dibujo: el conversor emitió **un cuadro de
; texto por opción**, iguales salvo por dónde está el ">", así que moverlo es
; recomponer la ventana con otro desplazamiento. Por eso acá no hay más estado
; que cuál está marcada.
eleg_activo: .res 1
eleg_n:      .res 1     ; cuántas opciones
eleg_sel:    .res 1     ; cuál está marcada, desde cero
eleg_cancel: .res 1     ; qué opción elige el botón B, más uno; 0 es "no se
                        ; puede cancelar". Es el `choice_cancel_type` de RM2k
                        ; tal cual, que easyrpg usa como `type - 1`.
eleg_tabla:  .res 2     ; dónde empieza la tabla de la elección, dentro de la
                        ; página: por cada opción, el cuadro y el destino
eleg_flancos: .res 1    ; los botones que se acaban de apretar este cuadro. No
                        ; usa `temp` porque `eventos_tick` lo tiene ocupado.
; El menú de la pantalla de título. Son dos bytes propios y no los de `eleg_`
; aunque el movimiento del cursor sea el mismo: la elección del intérprete vive
; adentro de una página de evento y ésta corre antes de que haya mapa, así que
; compartirlos ataría dos cosas que no se tocan nunca.
; 1 si el arranque —o el menú del título— cargó una partida de la SRAM. Lo mira
; `music_boot`: una partida trae su propio tema y no el del mapa inicial.
; En qué ranura se está trabajando, de 0 a SRAM_RANURAS - 1, o **$FF si no hay
; ninguna partida cargada**. Ese centinela hace de las dos cosas —qué ranura y
; si se cargó— porque la RAM del banco 0 está llena y guardar el dato aparte no
; entraba.
;
; Vive en la **página directa** a propósito, y no por lugar sino por el banco:
; las rutinas que trabajan con la SRAM tienen el banco de datos en $70, y una
; variable de la BSS leída con direccionamiento absoluto les daría la SRAM. La
; página directa apunta siempre al banco 0, así que desde ahí se lee bien esté
; el banco donde esté.
ranura: .res 1
titulo_sel:     .res 1  ; qué opción está elegida, desde cero
titulo_flancos: .res 1  ; y los botones que se acaban de apretar
; 1 mientras la pantalla de ranuras está a la vista. La ROM no lo lee: es para
; el arnés, como `cuadros_perdidos`. `vueltas` no avanza mientras la pantalla
; se ve, así que una prueba que espera por ticks se colgaría; con esto
; `consola.py` sabe cuándo apretar. Ver `Partida.guardar_en`.
menu_abierto:   .res 1
pad_ant:     .res 1     ; JOY1H del cuadro pasado, para mirar flancos de las
                        ; direcciones y de B como ya se hacía con A

temp:       .res 4      ; cuentas intermedias
hero_x:     .res 2      ; dónde está el héroe en el mapa, en pixeles
hero_y:     .res 2
hero_dir:   .res 1      ; hacia dónde mira
tile_x:     .res 2      ; y en qué celda de 16x16 está. Dos bytes: hay mapas de
tile_y:     .res 2      ; 500 celdas de ancho y en uno no entrarían
celdas:     .res 3      ; puntero a la fila de bloques donde arranca la ventana
celdas_ptr: .res 3      ; el mismo, mientras se recorre para armar una tira
; La ruta forzada del evento que se está caminando, mientras dura la vuelta.
; Vive en la página directa y no en la ranura porque `lda [ptr], y` **sólo**
; direcciona la página directa: con el puntero en BSS el ensamblador emitiría el
; byte bajo y la ROM leería de otro lado. Ya pasó una vez, con `msg_ptr`.
ruta_ptr:   .res 3
; La tabla de poses de los NPCs que caminan, del mapa cargado.
poses_ptr:  .res 3
win_col:    .res 2      ; la celda de 8x8 que quedó en el borde de la ventana
win_row:    .res 2      ; el cuadro pasado, para saber si la cámara la cruzó
win_block:  .res 2      ; y la fila de bloques a la que apunta `celdas`
col_addr:   .res 2      ; dónde va en la VRAM la columna recién armada
row_addr:   .res 2      ; ídem la fila; $0000 en las dos si no hay nada
tira_ofs:   .res 2      ; desplazamiento dentro del bloque, mientras se arma
tira_paso_col: .res 2   ; lo que mide una fila de bloques, en bytes
tira_resta: .res 2      ; cuántas celdas faltan por armar
hero_ptr:   .res 3      ; y en qué celda de la grilla, como puntero: se mueve
                        ; con él en vez de recalcularse
step_left:  .res 1      ; lo que falta del paso en curso, en medias unidades
                        ; de RM2k —128 por celda—, 0 si no hay
step_dx:    .res 2      ; el sentido del paso en x: -1, 0 o 1
step_dy:    .res 2
anim_step:  .res 1      ; en qué punto del ciclo de caminata va
anim_timer: .res 1      ; cuántos cuadros lleva el frame de la caminata:
                        ; `anim_count`, que sube y se compara con la velocidad
moving:     .res 1      ; si se movió este cuadro
oam_slot:   .res 2      ; en qué objeto de OAM vamos
npc_ofs:    .res 2      ; desplazamiento dentro de la tabla de NPCs
hero_key:   .res 2      ; la clave de orden del héroe
hero_drawn: .res 1      ; si ya se lo intercaló
high_acc:   .res 1      ; los bits de la tabla chica que se van juntando
high_ptr:   .res 2      ; y en qué byte de ella van. Dos bytes porque se usa
                        ; como índice, y `ldx` con X de 16 bits lee dos: con uno
                        ; solo tomaría de basura el byte alto.
obj_x:      .res 2      ; posición en pantalla del objeto que se está armando
obj_y:      .res 2
obj_tile:   .res 1
obj_attr:   .res 1
wait_frames: .res 1     ; cuántos cuadros faltan para el próximo evento
token:      .res 1      ; testigo del handshake con el SPC700
es_pal:     .res 1      ; 1 si la consola corre a 50 cuadros por segundo
pal_tick:   .res 1      ; para meter el cuadro de música que falta
reinicio:   .res 1      ; si el stream ya volvió al principio en este cuadro

; El mapa que está cargado. Todo esto salía de constantes del .inc cuando había
; un mapa solo; ahora sale de su registro en `mapa_tabla` —que vive en RODATA y
; se lee con `lda f:`— y queda acá mientras
; dure. Lo que se usa una sola vez —los tamaños de los DMA, las bases de VRAM—
; no se copia: se lee del registro en el momento.
mapa_ofs:    .res 2     ; el desplazamiento del registro del mapa actual
; Y su índice, para saber si un salto cambia de mapa. Dos bytes desde que el
; destino de OP_TELEPORT es un word: el juego tiene 328 mapas y en un byte
; entran 256. El techo que queda es MAPA_STRIDE: `mapa_ofs` es de dieciséis
; bits, así que son 512 mapas.
mapa_actual: .res 2
mapa_ancho:  .res 2     ; su ancho en celdas de 16x16
mapa_alto:   .res 2
mapa_cw:     .res 2     ; y en celdas de 8x8, que es el doble. Se guarda hecho
mapa_ch:     .res 2     ; porque el redibujado lo mira en cada columna y fila
npc_total:   .res 2     ; cuántos bytes ocupa la tabla de NPCs de este mapa
cam_max_x:   .res 2     ; hasta dónde puede llegar la cámara sin salirse
cam_max_y:   .res 2
bloques_ptr: .res 3     ; la tabla de bloques, que ya no entra en el banco 0
bloques8_ptr: .res 3    ; la misma corrida ocho bytes, que es donde arranca la
                        ; capa de encima dentro del bloque. Dos punteros salen
                        ; más baratos que ocho `iny` en el lazo más caliente.
pass_ptr:    .res 3     ; la pasabilidad, un byte por bloque
npc_ptr:     .res 3     ; y la de NPCs, sólo mientras se la copia a la RAM
puerta_ptr:  .res 3     ; la de puertas, mientras se la busca
entrada_x:   .res 2     ; por dónde entrar al mapa que se está por cargar, en
entrada_y:   .res 2     ; celdas. $FFFF quiere decir "donde diga el registro"

; El intérprete de eventos.
pag_ptr:     .res 3     ; la tabla de páginas del mapa cargado
cod_ptr:     .res 3     ; el código de la página que se está ejecutando
elegida:     .res 3     ; el código de la página que ganó, mientras se decide
elegida_hay: .res 1     ; si alguna página del evento en curso ganó
elegida_trigger: .res 1 ; y qué la dispara, para correr sólo las automáticas
; Y en qué capa está, que es lo que decide cuál de las dos celdas la dispara
; con la tecla de acción: la de adelante pide la capa del héroe y la propia
; pide cualquier otra. Ver `probar_accion`.
elegida_capa: .res 1
; Cuál de las dos se está mirando: 1 la del héroe, 0 la de adelante.
accion_propia: .res 1
; `ev_actual` vivía acá y no lo leía nadie: sus dos bytes son los que pagan
; el índice de mapa de dieciséis bits, que si no no entraba —la ZP estaba en
; 256 de 256—.
salto_mapa:  .res 2     ; un Teleport pedido por un evento: a qué mapa
salto_x:     .res 2     ; y a qué celda. salto_hay dice si hay uno pendiente
salto_y:     .res 2
salto_hay:   .res 1
saltos_restantes: .res 1 ; cuántas cadenas de teletransporte quedan permitidas
; Y cuántas son. Lo que cuenta el tope son los teletransportes **encadenados**,
; o sea los que ocurren sin que el jugador recupere el control: dos mapas que se
; apuntan entre sí se colgarían para siempre. No cuenta los de una partida, que
; son todos los que quieran ser. Ver dónde se repone, en `eventos_tick`.
SALTOS_MAX = 8
; Y qué pasa cuando se acaba. **No se descarta el salto**: se para todo y se
; avisa. Descartarlo en silencio fue lo que escondió el bug de arriba durante
; semanas —la partida seguía andando, sólo que en el mapa equivocado— y es
; exactamente la falla que el CLAUDE.md llama "un camino que ninguna prueba
; ejecuta". Un tope que se alcanza es siempre un error nuestro: la única manera
; legítima de encadenar nueve teletransportes sin devolver el control es que dos
; mapas se apunten entre sí, y eso en RM2k cuelga el juego.
;
; `panico` es el código de lo que pasó, cero mientras no pase nada. Lo lee la
; prueba de estado; en la consola lo que se ve es la pantalla parpadeando, que
; no se confunde con nada del juego.
panico:      .res 1
PANICO_SALTOS = 1       ; se acabó el presupuesto de teletransportes
; El intérprete corre de a un cuadro, no de una sola pasada. Antes `cargar_mapa`
; ejecutaba todas las páginas del tirón con la pantalla apagada y las esperas se
; salteaban: eso colapsaba el tiempo, y todo lo que en RM2k pasa *durante* una
; página no existía. Ahora las páginas elegidas se encolan al cargar el mapa y
; el lazo principal las va comiendo.
; Cuántas páginas se pueden arrancar en un mismo cuadro, encadenadas. En RM2k
; el tope no es de páginas sino de comandos —`loop_limit = 10000` en
; `game_interpreter.h`— y se reparte entre todas las que arranquen en el
; cuadro. Acá se cuenta por página, que es más grueso: sólo se nota con una
; página que termine sin hacer nada y vuelva a activarse, o sea la que en RM2k
; cuelga el juego. Ahí ésta no cuelga: gasta el cuadro y sigue.
ARRANQUES_MAX = 8

; Los dos bits de `ev_flags`, uno por evento.
FLAG_ESPERA = $01
FLAG_AUTO   = $02
ev_cur:      .res 2     ; el cursor dentro de la página que corre
; Los intérpretes paralelos. La lista de eventos y el estado de cada uno viven
; en la RAM del banco 1; acá queda sólo lo que el lazo necesita en la mano.
par_n:       .res 1     ; cuántos eventos con página paralela tiene el mapa
par_i:       .res 1     ; por cuál va el lazo
par_dir:     .res 2     ; dónde cae su estado, que hay que apuntar dos veces
par_ev:      .res 1     ; de qué evento es, para moverlo detrás del intérprete
; Cuántas vueltas dio el lazo principal, o sea **el tiempo del juego**. Un tick
; es un paso de lógica de RM2k —el `while (Game_Clock::NextGameTimeStep())` de
; easyrpg, `player.cpp:245`—, que allá también está separado del cuadro que se
; dibuja: la lógica va a DEFAULT_FPS y el dibujo a lo que la máquina aguante.
; Acá normalmente coinciden, y se separan cuando una vuelta se pasa del cuadro.
;
; Lo leen las pruebas por la WRAM para saber **qué tick** están mirando —ver
; `Partida` en pruebas/arnes/consola.py—, así que con esto deja de importar si
; la ROM llegó tarde. Lo tarde que llega lo dice
; `cuadros_perdidos`, que es otra pregunta.
vueltas:     .res 2
; Lo único que la animación del ChipSet guarda: qué hay que subir en el vblank
; que viene, tres bits por familia —cero es nada, y si no el dibujo más uno—.
;
; Que la **decisión** viva acá y no adentro del vblank no es gusto: el vblank
; del mapa 8 no tiene un ciclo de sobra. Veinte `nop` puestos ahí a propósito le
; cuestan 61 pixeles —la cola de poses se le va del vblank y las últimas
; escrituras caen con la pantalla ya encendida— así que las dos divisiones van
; en el cuerpo del lazo, donde sí sobra tiempo, y en el vblank queda un `lda` y
; un `beq`. Es el último byte libre de la página directa.
anim_pend:   .res 1
ev_activo:   .res 1     ; si hay una página a medio correr
ev_esperando: .res 2    ; cuántos cuadros faltan de la espera en curso
; La ruta forzada del héroe. En RM2k `ForceMoveRoute` es asincrónico: la página
; sigue corriendo y quien camina es el personaje, así que esto no vive en el
; intérprete sino acá, y lo come `move_hero` en vez del pad.
RUTA_MAX = 32
ruta_n:      .res 1
ruta_i:      .res 1
; Si el paso que el héroe tiene en curso lo arrancó la ruta forzada y no el pad.
; Hace falta para `hay_rutas`: el último paso de una ruta sigue contando como
; ruta pendiente aunque ya no queden órdenes, y un paso del pad no cuenta nunca.
; Sin esto, `ProceedWithMovement` dejaría de esperar ocho cuadros antes de
; tiempo, o esperaría de más porque el jugador se puso a caminar.
ruta_paso:   .res 1
ruta_espera: .res 1     ; los cuadros que faltan de un `wait` de la ruta
; El blanco y el largo de la ruta que se está leyendo del bytecode. El largo va
; en dos bytes con el alto siempre en cero: se le suma a Y, que es de dieciséis.
ruta_blanco: .res 1
ruta_cuantas: .res 2
; Un tinte pedido por un evento, para aplicarlo en el vblank siguiente.
tinte_pendiente: .res 1
; El grupo, en orden. El gráfico del héroe es el del primero —RM2k lo decide
; así, y `AddActor`/`RemoveActor` llaman los dos a `ResetGraphic`—, o sea que
; esto no es contabilidad: se ve en la pantalla. `hero_poses` apunta a las doce
; palabras de la tabla de actores del mapa que dicen qué tile es cada pose, y
; `hero_pal` a con qué paleta se dibuja.
grupo:       .res 4
grupo_n:     .res 2
hero_poses:  .res 3
hero_pal:    .res 1
; Y dónde están sus quince colores, adentro de la tabla de actores del mapa.
;
; Los líderes posibles **comparten una ranura de CGRAM**: lidera uno a la vez,
; así que darle una paleta a cada uno es tenerla ocupada por alguien que no está
; en pantalla. `aplicar_tinte` sube los del que lidera encima de esa ranura,
; teñidos como el resto. En cero, no hay líder con gráfico y no se sube nada.
hero_cgram:  .res 3
; La página que se está mirando, ya leída de la tabla. Se copia en vez de
; leerse en el lugar porque Y hace de cursor de la tabla, y usarlo además para
; indexar el bitmap de switches vuelve el código imposible de seguir.
pag_ofs:     .res 2
pag_restan:  .res 2
pg_evento:   .res 2
pg_trigger:  .res 1
pg_sa:       .res 2
pg_sb:       .res 2
pg_cod:      .res 3
pg_actor:    .res 1     ; el actor que pide en el grupo, o 0
act_ptr:     .res 3     ; cursor de la tabla de actores del mapa
tinte_r:     .res 1     ; el tinte de pantalla, de 0 a 200 con 100 neutro
tinte_g:     .res 1
tinte_b:     .res 1
tin_ptr:     .res 3     ; la paleta que se está tiñendo, en la ROM
tin_count:   .res 2     ; cuántos colores tiene
tin_cgadd:   .res 1     ; y en qué entrada de CGRAM va
tin_fin:     .res 2     ; cuántos bytes mide, que es el tope del lazo

; --- el compositor de texto ------------------------------------------------
; Todo esto se toca en el lazo más interno del repo —doce filas por caracter,
; cuatro escrituras de dieciséis bits por fila— así que va en la página cero.
msg_ptr:     .res 3     ; puntero al caracter que sigue, dentro de `mensajes`. Va
                        ; acá y no con el resto del estado porque `[dp],y` sólo
                        ; direcciona la página directa.
comp_glifo:  .res 3     ; puntero a las doce filas del caracter, en la ROM
comp_char:   .res 2     ; qué caracter, ya como índice en la fuente
comp_col:    .res 2     ; en qué columna del renglón va
comp_fase:   .res 2     ; y en qué pixel de la celda cae, o sea x mod 8
comp_base:   .res 2     ; el byte del buffer donde arranca su columna de celda
comp_mask:   .res 2     ; la fila del glifo ya corrida a su fase
comp_color:  .res 1     ; con qué índice de paleta se pinta
comp_fila:   .res 1     ; en qué fila del buffer, de 0 a 15
comp_dup:    .res 4     ; la máscara duplicada a los dos planos de cada par
comp_and:    .res 4     ; y las tres combinaciones que salen de ella
comp_or01:   .res 4
comp_or23:   .res 4

.segment "CODE"

; --- arranque --------------------------------------------------------------
.proc reset
    sei
    clc
    xce                         ; a modo nativo del 65816
    jml f:rapido + RAPIDO       ; al espejo rápido: ver MEMSEL
rapido:
    rep #$30                    ; A, X e Y de 16 bits
.a16
.i16
    ldx #$1FFF
    txs
    ; El banco de datos, en el del código. En un reset de verdad el 65816 lo
    ; deja en cero y todo lo de acá abajo funcionaría igual, pero desde el
    ; 2026-09-13 acá se llega también con un `jml` —el Game Over de
    ; `op_battle`— y ahí el banco de datos es el del bytecode, o sea un banco
    ; del cartucho: `sta INIDISP` escribiría la ROM en vez del PPU.
    phk
    plb

    sep #$20
.a8
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    ; La región no es un detalle cosmético: el stream de música está armado en
    ; cuadros, y una consola PAL da 50 por segundo en vez de 60. Sin corregirlo
    ; el tema suena un 17% lento.
    lda STAT78
    and #$10
    sta es_pal
    stz pal_tick

    jsr ppu_reset               ; la consola no arranca limpia; el emulador sí
    lda #$01
    sta MEMSEL                  ; la ROM del espejo, rápida
    jsr msu_detectar            ; ¿la música sale de una pista?

    ; Después del reset, no antes: ppu_reset apaga NMITIMEN junto con todo lo
    ; demás, así que habilitarlo primero no serviría de nada.
    lda #$01
    sta NMITIMEN                ; que la consola lea los controles sola
    stz boot_cuadros
    stz vueltas                 ; la RAM arranca con basura y el arnés lo
    stz vueltas + 1             ; lee desde el cuadro cero
    rep #$20
.a16
    lda #0
    sta f:vueltas_congeladas    ; y ésta, que las animaciones restan
    sep #$20
.a8
    lda #$81
    sta NMITIMEN                ; y la NMI, que cuenta los cuadros del arranque

    jsr ppu_init

    ; Sin entrada puesta: el primer mapa arranca donde diga su registro.
    rep #$20
.a16
    lda #$FFFF
    sta entrada_x
    sep #$20
.a8

    ; Los switches arrancan todos apagados, como una partida nueva de RM2k, y
    ; la pantalla sin teñir.
    ldx #$0000
borrar_switches:
    stz switches, x
    inx
    cpx #SWITCH_BYTES
    bne borrar_switches
    lda #TINTE_NEUTRO
    sta tinte_r
    sta tinte_g
    sta tinte_b
    sta tinte_s
    stz salto_hay
    stz anim_pend               ; la RAM arranca con basura y esto dispara DMAs
    stz panico                  ; la RAM arranca con basura, y 85 no es un código
    stz oro
    stz oro + 1
    stz oro + 2
    ; El grupo va antes de cargar el primer mapa: `cargar_mapa` elige con
    ; qué se dibuja el héroe, y sin esto leería la basura con la que
    ; arranca la RAM. El grupo con el que arranca la partida la partida, de la base del juego. El gráfico
    ; del héroe sale del primero, así que esto decide qué sprite se ve; que en
    ; este juego el actor 10 sea invisible es dato del juego, no un error.
    ldx #$0000
copiar_grupo:
    cpx #GRUPO_INICIAL_N
    beq grupo_listo
    lda grupo_inicial, x
    sta grupo, x
    inx
    bra copiar_grupo
grupo_listo:
    rep #$20
.a16
    lda #GRUPO_INICIAL_N
    sta grupo_n                 ; de 16 bits: X e Y lo comparan enteros
    sep #$20
.a8

    ; El intérprete y la ruta, en cero antes de cargar nada. La RAM arranca con
    ; basura y esto la lee en el primer cuadro: con `ev_esperando` en cualquier
    ; cosa se queda descontando para siempre y ninguna página corre, y con
    ; `ruta_i` menor que `ruta_n` `move_hero` cree que hay una ruta forzada
    ; pendiente y no lee el pad nunca —el héroe no se mueve—.
    ;
    ; Lo de la ruta lo encontró taro jugando en mednafen, no la tanda, y ésa es
    ; la parte que importa: **lo que snes9x deja en la RAM es siempre lo mismo**,
    ; así que esconde justo los errores que un patrón fijo esconde. Con estas dos
    ; sin inicializar, `ruta_i < ruta_n` da falso las diez corridas de snes9x y
    ; el error desaparece; en bsnes con entropía alta se ve. La tanda entera
    ; daba verde con esto adentro, y en hardware real habría fallado igual que
    ; en mednafen. Está medido: con estas dos sin inicializar a mano y diez
    ; corridas por core, snes9x da 0 de 10 en rojo y bsnes 2 de 10. Contra eso
    ; existe `pruebas/rpgmaker/test_cores.py`, que corre la misma ROM en snes9x y en
    ; bsnes —éste con `bsnes_entropy=High`— y compara las dos pantallas entre
    ; sí; ese archivo tiene el resto de los números. Verificado el 2026-09-16
    ; sacando estas dos líneas: de cinco corridas, cuatro en rojo.
    stz ev_activo
    jsr limpiar_esperas
    stz ruta_n                  ; sin ruta forzada pendiente
    stz ruta_i
    stz ruta_espera
    lda #8
    sta ruta_frec               ; la de siempre, hasta que un OP_ROUTE diga otra
    ; Y lo demás que una ruta deja prendido. La RAM arranca con basura —snes9x
    ; la llena de $55— así que sin esto el héroe arrancaría atravesando paredes
    ; y con la animación parada.
    stz ruta_salto
    stz ruta_atraviesa
    stz ruta_anim_para
    stz atravesando
    stz atravesando + 1
    stz tinte_pendiente
    ; Y la ventana de mensaje. `msg_abierto` en basura deja la página bloqueada
    ; para siempre: `eventos_tick` cree que hay un mensaje en pantalla y espera
    ; una A que ya no cierra nada. Está medido —sin este `stz`, `snes-cerrar` se
    ; cae en las doce corridas, y en snes9x además de en bsnes—.
    stz msg_abierto
    stz eleg_activo
    stz msg_estado
    stz msg_subir
    ; Y su cola de escapes, por lo mismo: una pausa en basura frenaría la
    ; página igual que `msg_abierto`. Hoy no se leen sin que `msg_empezar` las
    ; haya escrito, pero eso vale mientras el guard de arriba siga siendo
    ; `msg_abierto | msg_estado`.
    rep #$20
.a16
    lda #0
    sta f:FAR_MSG_PAUSA         ; `stz` no tiene modo largo
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ; Los dos del pad son por las dudas y no por un error visto: `read_pad`
    ; los reescribe antes de que nadie los mire. Cuestan dos instrucciones.
    stz pad_a
    stz pad_a_ant
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    stz sacudida_pos
    stz sacudida_pos + 1
    stz tinte_listo
    lda #VQ_POR_CUADRO
    sta vq_tope
    stz sacudida_resta
    stz sacudida_resta + 1
    stz destello_nivel          ; la RAM arranca con basura: sin esto el
    stz destello_nivel + 1      ; primer cuadro sale destellado
    stz destello_resta
    stz destello_listo
    rep #$20
.a16
    stz ev_esperando
    stz ev_cur
    sep #$20
.a8

    ; Mirando a cámara, como arranca RM2k. Va antes de cargar el primer mapa
    ; porque ahí corren sus eventos, y una ruta forzada puede girarlo: si esto
    ; quedara después, pisaría lo que la ruta acaba de decidir.
    lda #DIR_DOWN
    sta hero_dir

    ; El cronómetro arranca apagado y en cero. Va acá y no en `cargar_mapa`
    ; porque en RM2k vive en `Game_Party`: sobrevive a los mapas, que es
    ; justamente para lo que el juego lo usa. La RAM arranca con basura —snes9x
    ; la llena de $55— así que sin esto se vería corriendo solo.
    stz timer_activo
    stz timer_visible
    stz timer_sub
    rep #$20
.a16
    stz timer_seg
    sep #$20
.a8
    jsr timer_digitos

    ; La RAM arranca con basura —snes9x la llena de $55— y `flush_video` mira
    ; las dos: sin esto el primer vblank prendería la pantalla con el brillo que
    ; hubiera quedado, y el lazo arrancaría creyéndose adentro de un fundido.
    stz fundido
    lda #BRILLO_MAX
    sta brillo
    stz bgm_fundido             ; y lo mismo con el del tema
    jsl f:encuentro_arranque    ; la semilla del azar de los encuentros

    ; Si el cartucho tiene una partida guardada, se carga acá: los switches que
    ; trae deciden qué página está activa en cada evento, así que tienen que
    ; estar puestos **antes** de cargar el mapa. Y la entrada se arma con la
    ; celda guardada, que es como una puerta le dice a `cargar_mapa` dónde
    ; plantar al héroe.
    lda #$FF
    sta ranura                  ; ninguna cargada; la RAM arranca con basura
    ; La semilla del azar, y las variables en cero: la RAM lejana también
    ; arranca con basura, y una partida cargada las pisa después.
    jsr limpiar_variables
    jsr equipo_inicial_poner
    jsl f:hp_inicial_poner
    jsr actor_graf_limpiar
    jsr clima_limpiar
    jsr se_limpiar
    jsr giro_limpiar
    jsr aram_limpiar
    jsr animacion_limpiar
    lda #0                      ; la RAM arranca con basura
    sta f:CARTEL_ACTIVA
    sta f:CARTEL_LISTO
    ; El testigo de la pantalla de ranuras también: con $55 el arnés la vería
    ; abierta desde el reset. Es lo que pasó el 2026-09-10 con los dos
    ; contadores que "daban 85": leían la basura del emulador.
    stz menu_abierto
    ; Con pantalla de título esto no se hace acá: cargar o empezar de nuevo lo
    ; decide el menú, y hasta que el jugador elija la partida guardada no se
    ; toca. Sin pantalla de título —que es toda la tanda— sigue pasando lo de
    ; siempre, o sea que si hay partida se carga sola.
    lda #<TITULO_TILES
    ora #>TITULO_TILES
    bne nueva
    lda #0                      ; sin menú que elija, siempre la primera
    jsr poner_ranura
    jsr cargar_partida
    beq nueva
    jsr entrada_de_la_partida
    rep #$20
.a16
    lda mapa_actual             ; el índice va en dieciséis bits
    bra cargar
.a8
nueva:
    rep #$20
.a16
    lda #MAPA_INICIAL
cargar:
    jsr cargar_mapa
    sep #$20
.a8
    jsr clear_oam

    stz step_left               ; parado, sin paso en curso
    stz pad                     ; la RAM arranca con basura y move_hero la lee
    lda #1
    sta anim_step               ; el frame del medio: la pose parada
    stz anim_timer

    jsr build_oam
    jsr flush_video

    lda #$0F
    sta INIDISP                 ; pantalla encendida, brillo al máximo

    ; La subida al SPC700 va después de prender la pantalla, no antes: son casi
    ; siete décimas de segundo, y así el mapa aparece de entrada en vez de
    ; hacerte mirar una pantalla negra hasta que termine.
    ;
    ; Y antes de subir nada, el comando 4: **que el SPC700 vuelva a su ROM del
    ; IPL**. Acá se llega de dos maneras y sólo una de las dos deja al SPC700
    ; como recién encendido. Con el botón de reset de la consola la línea les
    ; llega a los dos procesadores y el IPL arranca solo; con el `jml reset`
    ; del Game Over de `op_battle`, no: el SPC700 sigue corriendo el driver y
    ; el saludo $AA/$BB que `spc_upload` espera no llega **nunca**. Ése era el
    ; cuelgue del cofre trampa de los Rat Tracks —pantalla encendida, mapa
    ; dibujado y el juego clavado—, y el mismo lo tenía cualquier Game Over.
    ;
    ; Con el IPL corriendo esto no molesta: mientras espera el $CC mira el
    ; puerto 0, y acá se escriben el 2 y el 3. El testigo se incrementa sin
    ; esperar acuse, porque del otro lado ya no queda quién lo devuelva.
    lda #APU_CMD_IPL
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    jsr spc_upload
    ; El puerto 2 es el comando del driver, y `spc_upload` lo deja con lo que
    ; haya mandado último: en cero, el driver lee pares del DSP.
    stz APUIO2
    ; Y el paquete de audio del mapa de arranque: `cargar_mapa` no lo pudo
    ; subir porque el driver todavía no corría. Ver `paquete_cargar`.
    lda #1
    sta f:APU_LISTO
    jsr paquete_cargar
    jsr music_boot

    ; Y se espera a que el arranque dure lo que dura siempre: BOOT_CUADROS.
espera_boot:
    lda boot_cuadros
    cmp #BOOT_CUADROS
    bcc espera_boot
    ; La NMI sigue contando después del arranque: es la única forma de saber
    ; si una vuelta del lazo se pasó del cuadro. Ver `contar_perdidos`.
    lda boot_cuadros
    sta nmi_visto
    stz cuadros_perdidos

    ; Y desde acá la música corre sola, en `irq_musica`: una vez por cuadro
    ; en la línea IRQ_LINEA, tarde lo que tarde el lazo. Va después de la
    ; espera y no antes para que el tema arranque en el mismo cuadro que
    ; cuando la tocaba el lazo.
    lda #<IRQ_LINEA
    sta VTIMEL
    lda #>IRQ_LINEA
    sta VTIMEH
    lda #$A1
    sta NMITIMEN                ; la NMI, los controles y la IRQ vertical
    cli

    ; La pantalla de título, si esta ROM la lleva. Va **después** de que el
    ; arranque terminó de contar sus BOOT_CUADROS y no antes: así una ROM sin
    ; título llega al lazo exactamente en el cuadro de siempre, y los 96 casos
    ; de la tanda —que cuentan cuadros desde el reset— no se enteran de que
    ; esto existe.
    jsr pantalla_titulo

loop:
    jsr wait_vblank
    ; El control primero: la consola lo lee sola al empezar el vblank y hay que
    ; esperar a que arranque. Si antes se hiciera algo largo —el DMA de OAM, por
    ; ejemplo— se llegaría con la lectura ya terminada, y esperar su arranque
    ; significaría esperar al cuadro siguiente: medio cuadro por vuelta.
    jsr read_pad
    jsr flush_video             ; lo del cuadro anterior, todavía en vblank
    ; El fundido de un teletransporte congela el juego entero mientras dura,
    ; como RM2k: lo único que sigue corriendo es la música. Ver `fundido_tick`.
    jsr fundido_tick
    bne congelado
    ; El cronómetro va **antes** del intérprete, que es donde lo pone
    ; `Game_Map::Update`: `UpdateTimers()` corre y recién después
    ; `UpdateForegroundEvents`. O sea que la página que lo arranca no se lleva
    ; un cuadro en el mismo cuadro en que lo arranca. Acá estaba después, y por
    ; eso la ROM iba un cuadro adelante de la referencia para siempre: se veía
    ; sólo en los cuadros en que los dos puntos parpadean o cambia un dígito.
    ; No lo cobraba nadie porque `snes-timer` tiñe la pantalla, el tinte
    ; costaba un cuadro perdido, y el cuadro perdido tapaba justo este uno de
    ; más. Los dos errores juntos daban cero.
    jsr timer_tick
    jsr eventos_tick
    jsr tinte_de_evento
    jsr move_hero
    jsr pedir_menu              ; B, al final del héroe: ver `pedir_menu`
    jsr animar_quietos          ; los que animan sin moverse, antes que las
                                ; rutas: si una agarra a uno, gana la ranura
    jsr mover_eventos           ; y las rutas forzadas de los eventos, después
                                ; del héroe y después del intérprete: el orden
                                ; es el mismo que el de la referencia
    jsr animacion_tick          ; la animación de batalla, antes que los
                                ; destellos que dispara
    jsr animacion_dibujo_tick   ; y su dibujo, pegado: los dos avanzan el
                                ; mismo reloj de RM2k y el dibujo dura más
    jsr flashes_tick            ; y los destellos, en el mismo lugar
    jsr sacudida_tick           ; y uno de la sacudida de pantalla
    jsr pan_tick                ; y uno de la cámara corrida sin el héroe
    jsr imagen_tick             ; y uno del fundido del cartel. Va **antes**
                                ; del destello y no después: los dos arman su
                                ; paleta en `pal_buf`, y el destello deja la
                                ; suya ahí esperando el vblank. Al revés, el
                                ; cartel le pisaba los primeros dieciséis
                                ; colores del fondo en el cuadro en que los
                                ; dos corren. Del lado de la referencia el
                                ; orden da igual —son dos estados que no se
                                ; tocan— y está escrito igual para que se lean
                                ; en el mismo orden.
    jsr destello_tick           ; y uno del destello de pantalla
    jsr lluvia_tick             ; y uno de la lluvia
    jsr animate_hero
    jsr follow_camera
    jsr stream_map              ; la columna o la fila que la cámara destapó
    jsr mensaje_tick            ; y unos caracteres del mensaje que se esté
                                ; componiendo, si hay alguno
    jsr build_oam               ; y se arma el siguiente, ya fuera del vblank
    bra contada
congelado:
    ; Una vuelta del fundido: el tick corre —el fundido y el arnés lo cuentan—
    ; pero el mundo no, y las animaciones del mapa tampoco. Ver
    ; `vueltas_congeladas`.
    rep #$20
.a16
    lda f:vueltas_congeladas
    inc a
    sta f:vueltas_congeladas
    sep #$20
.a8
contada:
    rep #$20
.a16
    inc vueltas
    sep #$20
.a8
    jsr anim_tick               ; qué dibujo del ChipSet toca en la vuelta que
                                ; viene, para que el vblank sólo tenga que subirlo
    jsr contar_perdidos
    bra loop
.endproc

; Cuántos vblanks pasaron desde la vuelta anterior: uno es lo normal, y cada
; uno de más es un cuadro que la ROM perdió, porque la vuelta tardó más que un
; cuadro y `wait_vblank` tuvo que esperar al siguiente. Se mira acá, al final
; de la vuelta, y no a la salida de `wait_vblank`: ahí la NMI de este cuadro
; puede no haber corrido todavía. Contra una golden un cuadro perdido es
; una posición atrasada, y la comparación lo cobra en pixeles sin decir por
; qué; este contador dice por qué. Lo leen las pruebas por la WRAM del
; emulador —`Partida.cuadros_perdidos`—, y en la consola no lo lee nadie.
; Satura en 255.
.proc contar_perdidos
.a8
.i16
    lda boot_cuadros
    sec
    sbc nmi_visto
    dec a                       ; el vblank que le tocaba a esta vuelta
    beq al_dia
    clc
    adc cuadros_perdidos
    bcc cabe
    lda #255
cabe:
    sta cuadros_perdidos
al_dia:
    lda boot_cuadros
    sta nmi_visto
    rts
.endproc

; --- espera de vblank ------------------------------------------------------
; Sin NMI habilitada, se mira la bandera de HVBJOY: primero que salga del
; vblank anterior y después que entre al siguiente.
; La NMI: suma un cuadro y baja la bandera. No toca nada más, y deja P como
; estaba porque `rti` lo saca de la pila. Corre durante el arranque, para que
; dure siempre lo mismo, y después también: ver `contar_perdidos`.
.proc nmi_boot
    sep #$20
.a8
    pha
    inc boot_cuadros
    lda RDNMI
    pla
    rti
.endproc

.proc wait_vblank
.a8
.i16
out:
    lda HVBJOY
    bmi out
in:
    lda HVBJOY
    bpl in
    rts
.endproc

; --- puesta a cero del PPU -------------------------------------------------
; El emulador arranca con todos los registros en cero. La consola real no: se
; queda con lo que dejó el programa anterior, que en un EverDrive es su menú.
; Si ese menú dejó encendido el color math, el sub-screen, una ventana o un
; canal de HDMA, todo eso sigue funcionando debajo de nuestro mapa aunque
; nosotros no lo hayamos pedido.
;
; Por eso no alcanza con escribir los registros que usamos: hay que escribir
; todos. Es la misma lección que el registro 23 del VDP en la Mega Drive, donde
; también andaba en emulador y no en consola.
.proc ppu_reset
.a8
.i16
    lda #$80
    sta INIDISP                 ; blanking forzado antes de tocar nada

    ; Lo primero es cortar el DMA por scanline: si quedó un canal activo, sigue
    ; escribiendo registros del PPU en cada línea y nada de lo que hagamos acá
    ; se sostiene.
    stz HDMAEN
    stz MDMAEN
    stz NMITIMEN

    ; Los registros del PPU con valores conocidos, en dos tramos: los de scroll
    ; quedan en el medio y necesitan otro tratamiento.
    ldx #$0000
bajos:
    lda f:ppu_bajos, x
    sta $2101, x
    inx
    cpx #(ppu_bajos_end - ppu_bajos)
    bne bajos

    ldx #$0000
altos:
    lda f:ppu_altos, x
    sta $2115, x
    inx
    cpx #(ppu_altos_end - ppu_altos)
    bne altos

    ; Los ocho registros de scroll: cada uno se escribe dos veces, byte bajo y
    ; byte alto, o el latch queda a medias.
    ldx #$0000
scrolls:
    stz $210D, x
    stz $210D, x
    inx
    cpx #8
    bne scrolls

    ; La VRAM entera a cero, por DMA con la fuente fija en un byte nulo. Sin
    ; esto quedan los tiles del menú donde no llegan los nuestros.
    lda #$80
    sta VMAIN
    ldx #$0000
    stx VMADDL
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #$0000                  ; 0 significa 65536: la VRAM completa
    stx DAS0L
    lda #$09                    ; dos registros, de a palabras, fuente fija
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Y CGRAM, que si no deja la paleta del menú en los colores que no usamos.
    stz CGADD
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #512
    stx DAS0L
    lda #$08                    ; un registro, de a bytes, fuente fija
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; De $2101 a $210C: objetos, modo, mosaico y dónde vive cada capa. Todo en
; cero, que es "nada encendido".
.segment "TABLAS"

; Lo que **tiene** que vivir en el banco 0: se lee con `lda tabla, y`, y el
; 65816 no tiene absoluto largo indexado por Y —`long,X` sí, `long,Y` no—, o
; con tantos índices distintos que el byte de más por acceso costaría más que
; la tabla. Las que se leen con X y se leen poco fueron bajando a RODATA a lo
; largo del 2026-09-13, en tres vueltas distintas y por el mismo motivo: hacer
; lugar. Ahí abajo está el porqué de cada una y lo que todavía se podría bajar.

; `salto_por_vel` bajó a RODATA el 2026-09-14: un solo acceso, y pasarlo por X
; cuesta cuatro bytes contra los seis de la tabla. Ver allá abajo.
; Cada cuántos cuadros cambia el frame de la caminata, por velocidad: caminando
; y quieto con la animación continua. ANIM_PARADO y ANIM_CONTINUA de eventos.py.
anim_parado:
    .byte 12, 10, 8, 6, 5, 4
anim_continua:
    .byte 16, 12, 10, 8, 7, 6


.segment "CODE"

; --- el PPU ----------------------------------------------------------------
; Modo 3: BG1 con 8 bits por pixel. Ahí cada pixel es un índice directo a CGRAM
; y no hay paleta por tile, así que el mapa entra con sus 60 colores sin
; fusionar ninguno. Cuesta el doble de VRAM por tile y sobra lugar de todas
; formas.
.proc ppu_init
.a8
.i16
    lda #$03
    sta BGMODE
    ; BG1SC lleva la dirección del tilemap en el byte alto y el tamaño en los
    ; dos bits bajos; con VRAM_MAP en $7000 y el tamaño 1 —dos pantallas de
    ; 32x32 una al lado de la otra, o sea 64x32— queda $71.
    lda #>VRAM_MAP | MAP_LAYOUT
    sta BG1SC                   ; la ventana del mapa, siempre de 64x32
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC                   ; y la de la capa de encima, del mismo tamaño
    ; BG12NBA sale del mapa, así que lo pone cargar_mapa. Acá quedaría con el
    ; valor del mapa anterior en cuanto haya más de uno.
    stz BG1HOFS                 ; el scroll es de dos escrituras, byte bajo
    stz BG1HOFS                 ; y byte alto
    ; El PPU muestra la línea vofs+1 en el primer scanline visible, no la vofs.
    ; Con 0 el mapa queda corrido una línea hacia arriba; con -1 cae en su
    ; lugar. Lo destapó la comparación pixel a pixel contra el render de Python:
    ; a ojo las dos imágenes se veían idénticas.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$13
    sta TM                      ; las dos capas del mapa y los sprites
    rts
.endproc

; --- volcado del mapa a la VRAM --------------------------------------------
; Todo por DMA y con la pantalla apagada, que es cuando se puede escribir la
; VRAM sin pelearle al PPU.
; Carga entero el mapa cuyo índice viene en A **de dieciséis bits**: sus datos
; a la VRAM y a CGRAM,
; sus tablas a donde la ROM las busca, la cámara donde arranca el héroe y la
; ventana del tilemap llena. Es todo lo que hay que hacer para cambiar de mapa.
;
; Con la pantalla encendida esto no se puede llamar: escribe VRAM y CGRAM por
; DMA, que fuera del vblank el PPU no deja.
.proc cargar_mapa_sin_eventos
.a16
.i16
    sta mapa_actual             ; para saber si el próximo salto cambia de mapa
    sep #$20
.a8
    jsr giro_limpiar            ; las filas van a ser otras
    jsr animacion_limpiar       ; y la animación de batalla no sigue
    lda #0                      ; y el cartel se borra: es el
    sta f:CARTEL_ACTIVA         ; `erase_on_map_change` de Game_Pictures, y
    sta f:CARTEL_LISTO          ; además sus tiles son de un solo mapa
    jsr paquete_cargar          ; el audio del mapa, en el fundido
    rep #$20
.a16
    lda mapa_actual
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por MAPA_STRIDE, que es 128
    sta mapa_ofs
    tax

    ; El reparto de la animación de batalla en este mapa: en qué tile cae su
    ; caja y con qué paleta, o que acá no se dibuja. Necesita `mapa_actual` y
    ; `mapa_ofs`, que acaban de quedar puestos.
    phx
    sep #$20
.a8
    jsr animacion_dibujo_mapa   ; entra y sale con el acumulador en ocho
    jsl f:encuentro_mapa        ; y cada cuántos pasos hay un encuentro acá
    rep #$20
.a16
    plx

    ; Lo que se mira seguido se copia; lo que se usa una vez se lee en el lugar.
    lda f:mapa_tabla + M_MAP_BW, x
    sta mapa_ancho
    asl a
    sta mapa_cw                 ; el ancho en celdas de 8x8 es el doble
    lda f:mapa_tabla + M_MAP_BH, x
    sta mapa_alto
    asl a
    sta mapa_ch
    lda f:mapa_tabla + M_CAM_MAX_X, x
    sta cam_max_x
    lda f:mapa_tabla + M_CAM_MAX_Y, x
    sta cam_max_y
    lda f:mapa_tabla + M_EV_COUNT, x
    ; Todo lo que barre eventos va hasta acá y no hasta `EV_MAX`: con los
    ; ciento veinte, un mapa de cuatro eventos barría ciento dieciséis de más y
    ; eso alcanzaba para perder el cuadro.
    sta ev_total
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; por dieciséis: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "la cuenta de arriba multiplica por dieciséis a mano"
    sta npc_total

    ; Los punteros a las dos tablas que se leen desde la ROM. El segundo apunta
    ; ocho bytes más adelante, que es donde cada bloque guarda su capa de
    ; encima; sumar ocho no puede desbordar el banco porque el acomodo de
    ; `tools/ensamblado/bancos.py` garantiza que la tabla entera entra en uno.
    lda f:mapa_tabla + M_PTR_NPC_POSES, x
    sta poses_ptr
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES, x
    sta bloques_ptr
    clc
    adc #8
    sta bloques8_ptr
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES + 2, x
    sta bloques_ptr + 2
    sta bloques8_ptr + 2
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS + 2, x
    sta pass_ptr + 2
    lda f:mapa_tabla + M_PTR_NPC_POSES + 2, x
    sta poses_ptr + 2

    ; Dónde arranca el héroe: donde diga el registro, salvo que quien llamó haya
    ; dejado una entrada puesta, que es lo que hace una puerta. La cámara se
    ; acomoda antes de llenar la ventana, porque la ventana se llena alrededor
    ; de ella.
    rep #$20
.a16
    lda entrada_x
    cmp #$FFFF
    bne desde_puerta
    lda f:mapa_tabla + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda f:mapa_tabla + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra puesto

desde_puerta:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida: la próxima carga vuelve al registro

puesto:
    sep #$20
.a8
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA

    ; La cámara corrida vuelve a cero al cambiar de mapa, y de golpe: es lo que
    ; hace `Game_Player::PerformTeleport` con `map_changed`, que le devuelve a
    ; `pan_current` y a `pan_finish` el valor por omisión. Un salto al mismo
    ; mapa no pasa por acá y no la toca, que es también lo que hace RM2k.
    rep #$20
.a16
    stz pan_x
    stz pan_y
    stz pan_dest_x
    stz pan_dest_y
    stz pan_px
    stz pan_py
    sep #$20
.a8

    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    jsr load_ruta_graficos
    jsr load_ev_pos             ; y dónde arranca cada evento, con o sin gráfico
    stz refresco
    ; Antes del refresco, no después: las marcas del mapa anterior no valen
    ; nada acá —sus índices de evento apuntarían a otros eventos— y el refresco
    ; es el que vuelve a prender el `FLAG_AUTO` de los que corresponda.
    jsr limpiar_esperas
    jsr limpiar_paralelos
    jsr rutas_de_pagina         ; y las rutas propias de las páginas activas
    ; La tabla de actores es de este mapa, así que dónde caen las poses del
    ; líder cambia al cambiar de mapa aunque el grupo sea el mismo.
    jsr elegir_grafico_heroe
    jsr limpiar_tilemaps        ; lo que `fill_window` no pisa, del mapa de antes
    jsr fill_window             ; deja listo tira_paso_col, que el otro usa
    jsr load_ventana            ; tiles, paleta, tilemap propio y tablas de HDMA
    jsr init_hero_ptr

    ; El tinte es estado del juego, no del mapa: sobrevive al teletransporte.
    ; Las paletas que se acaban de subir son las del cartucho, sin teñir, así
    ; que se vuelven a teñir acá. Con el tinte neutro la cuenta es i*100/100 y
    ; deja los colores donde estaban, así que no hace falta preguntar si hay
    ; tinte: el camino es siempre el mismo.
    jsr aplicar_tinte
    stz destello_listo          ; lo que hubiera en `pal_buf` ya no
                                ; es de este mapa; el cuadro que viene lo
                                ; vuelve a armar si el destello sigue
    jsr subir_tinte             ; la pantalla está apagada: va ya
    rts
.endproc

; Y esto es lo que hay que llamar: carga el mapa y le corre los eventos
; automáticos.
;
; Si un evento pide un teletransporte, el ciclo se repite acá y no adentro del
; intérprete. Llamar a cargar_mapa desde el intérprete sería recursión, y dos
; mapas que se apuntan entre sí la harían infinita: la pila se va al fondo y la
; consola hace cualquier cosa. El tope de vueltas está por la misma razón, para
; el caso en que se apunten con un ciclo más largo.
.proc cargar_mapa
.a16
.i16
    pha                         ; el índice del mapa, que lo de abajo pisaría
    sep #$20
.a8
    lda #SALTOS_MAX
    sta saltos_restantes        ; con stx serían dos bytes y pisaría el de al lado
    rep #$20
.a16
    pla
    jsr cargar_mapa_sin_eventos
    rts
.endproc

; El tinte que haya pedido un evento, con la pantalla apagada mientras dura.
;
; CGRAM no acepta escrituras con el PPU dibujando, así que esto no puede correr
; en cualquier momento. Se intentó primero meterlo en `flush_video`, que corre en
; el vblank, y no entra: `aplicar_tinte` arma tres tablas de canal de treinta y
; dos entradas y sube tres paletas por DMA. Lo que se pasaba del vblank caía con
; el PPU dibujando, y el resultado era un tinte a medias distinto cada vez —una
; vez la capa de encima y un sprite, otra vez el fondo con el héroe en negro y
; los NPCs sin teñir—.
;
; Y esto la tanda no lo cobra: snes9x **acepta** las escrituras a CGRAM con el
; PPU dibujando y mednafen no, así que un tinte roto puede dar verde en las
; sesenta comparaciones y verse mal en la consola. Cuando algo de CGRAM o VRAM
; anda acá adentro y no en el hardware, ésta es la primera sospecha.
;
; La otra salida que se probó —apagar la pantalla a mitad del cuadro, escribir
; el tinte y volver a prenderla— es otra trampa de las que el emulador tapa: en
; la consola son líneas negras mientras dura la cuenta, y en el emulador un
; cuadro teñido de la mitad para abajo. La vio la sacudida de pantalla, que es
; la primera receta que compara cuadro por cuadro.
;
; Apagar la pantalla es lo que ya hacen `cruzar_puerta` y el teletransporte por
; la misma razón. Cuesta un cuadro en negro, que en RM2k tampoco desentona: el
; motor original funde a negro en las transiciones.
.proc tinte_de_evento
.a8
.i16
    lda tinte_pendiente
    beq nada
    stz tinte_pendiente
    jsr aplicar_tinte           ; a la sombra; CGRAM se escribe en el vblank
nada:
    rts
.endproc

; Un cuadro del intérprete, desde el lazo principal.
;
; Acá estaba el cambio de fondo: antes `cargar_mapa` corría todas las páginas de
; una, con la pantalla apagada, y volvía con todo hecho. El tiempo quedaba
; colapsado —las esperas se salteaban, y lo que pasaba antes de un
; teletransporte no se veía nunca— y por eso nada de eso se podía verificar.
;
; Un teletransporte se atiende acá y no adentro del intérprete: llamar a
; `cargar_mapa` desde ahí sería recursión, y dos mapas que se apuntan entre sí
; la harían infinita. El tope de saltos sigue por la misma razón.
.proc eventos_tick
.a8
.i16
    ; El refresco pendiente, antes del intérprete: es cuando `Game_Map::Update`
    ; mira `GetNeedRefresh`.
    lda refresco
    ora refresco_cuadro         ; o uno de adentro del lazo de comandos, que
    beq sin_refresco            ; hizo la pasada corta y dejó ésta debiendo
    stz refresco
    stz refresco_cuadro
    jsr rutas_de_pagina         ; que además rehace el `FLAG_AUTO` de cada
                                ; evento: la página activa cambió
sin_refresco:
    ; `Game_Event::CheckEventAutostart`: todo evento con una automática activa
    ; queda esperando, una vez por cuadro y **antes** del intérprete, que es el
    ; orden de `Game_Map::Update`. Marcarlo más tarde —al terminar una página—
    ; le adelantaba un cuadro a las que se activan en medio de otra.
    ;
    ; `auto_n` está para que el lazo de ciento veinte no corra cuando no hay
    ; ninguna, que es casi siempre: corriéndolo igual se perdía el cuadro justo
    ; donde caía algo caro, como el tinte de `snes-pan`.
    lda auto_n
    beq sin_automaticas
    jsr esperar_automaticas
sin_automaticas:
    ; Los paralelos, **antes** del mensaje y antes de la espera del primer
    ; plano: en `Game_Map::Update` el orden es refresco, `UpdateMapEvents`,
    ; `game_player->Update()`, `UpdateMessage` y recién ahí
    ; `UpdateForegroundEvents`. O sea que un evento paralelo sigue corriendo
    ; con un cuadro de texto abierto y con otra página en curso, que es justo
    ; para lo que existe.
    jsr paralelos_tick
    rep #$20
.a16
    lda ev_esperando
    beq sin_espera
    dec a
    sta ev_esperando
    sep #$20
.a8
    rts
sin_espera:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8

    ; Con un mensaje en pantalla la página queda bloqueada, que es lo que hace
    ; `Game_Message`. Todo lo demás sigue: la ruta forzada del héroe camina y la
    ; cámara lo sigue, porque en `game_player.cpp` de easyrpg `UpdateMoveRoute`
    ; corre **antes** del guard de `IsMessageActive`. En este juego hay 186
    ; páginas donde eso pasa, y la primera está en el mapa 1.
    ; Una elección abierta manda sobre el mensaje: la ventana es la misma pero
    ; A no la cierra, la resuelve.
    lda eleg_activo
    beq sin_eleccion
    jsr eleccion_tick
    bne sin_mensaje             ; eligió: la página sigue en este mismo cuadro
    rts
sin_eleccion:
    lda msg_abierto
    ora msg_estado              ; también mientras se está componiendo
    beq sin_mensaje
    ; La pausa del `\|`, si el cuadro trae alguna. Se cuenta **desde que la
    ; página pidió el mensaje** y no desde que la ventana terminó de
    ; componerse, que es lo único que la hace coincidir cuadro a cuadro con la
    ; referencia: allá la ventana se dibuja de golpe y acá tarda entre nueve y
    ; diecinueve cuadros en componerse. Con una pausa de 61 la composición
    ; termina mucho antes, así que en pantalla se ve lo mismo.
    ;
    ; **A no la saltea**: en `Window_Message::Update` el `if (wait_count > 0)`
    ; va antes de `WaitForInput()`, así que mientras la pausa corre el botón no
    ; se mira. Por eso va arriba de todo y no después del flanco.
    rep #$20
.a16
    lda f:FAR_MSG_PAUSA
    beq sin_pausa
    dec a
    sta f:FAR_MSG_PAUSA
    sep #$20
.a8
    rts
.a16
sin_pausa:
    sep #$20
.a8
    lda f:FAR_MSG_AUTO
    beq espera_boton
    ; El `\^`: el cuadro se cierra solo, sin que nadie apriete nada. Se apaga
    ; también el compositor, y no es teórico: un cuadro con `\^` y ninguna
    ; pausa se cierra antes de que termine de componerse, y sin esto
    ; `flush_video` prendería la ventana de un mensaje ya cerrado.
    lda #0
    sta f:FAR_MSG_AUTO
    stz msg_estado
    stz msg_subir
    stz msg_abierto
    bra sigue
espera_boton:
    lda msg_abierto
    beq no_avanza               ; todavía no terminó de componerse
    lda pad_a
    beq no_avanza               ; nadie apretó: el mensaje se queda
    lda pad_a_ant
    bne no_avanza               ; ya lo tenía apretado: no es un flanco
    stz msg_abierto             ; y con eso `flush_video` apaga el HDMA: cerrar
                                ; la ventana no escribe un solo byte de VRAM
    ; Y el flanco queda consumido, como el de B en la elección. Si el mensaje
    ; era de un paralelo no hay página que siga, así que este mismo cuadro cae
    ; en `probar_accion` con la A todavía "recién apretada" y le hablaba al
    ; evento que el héroe tuviera enfrente. En RM2k el mensaje sigue activo
    ; unos ocho cuadros más, mientras se anima el cierre (easyrpg
    ; `window_message.cpp:379-403`), y con un mensaje activo el héroe no busca
    ; eventos (`game_player.cpp:297`). Lo cobra `test_la_a_que_cierra_el_
    ; mensaje_no_le_habla_al_de_enfrente`.
    lda pad_a
    sta pad_a_ant
sigue:
    ; Y la página sigue **en este mismo cuadro**, cayendo en el `jsr
    ; correr_codigo` de siempre. Cerrar acá y retomar el cuadro siguiente
    ; sería un cuadro de diferencia contra la referencia.
    bra sin_mensaje
no_avanza:
    rts
sin_mensaje:

    lda ev_activo
    bne corriendo
    ; No hay página a medio correr: se toma la del primer evento que espere.
    lda esperando_n
    bne hay_esperando

    ; Nada corriendo y nada esperando: el jugador tiene el control, así que la
    ; cadena de teletransportes terminó y el presupuesto se repone. Es el
    ; alcance que el tope tiene en la referencia, donde `saltos` es local a
    ; `entrar_al_mapa` y se reinicia en cada entrada.
    ;
    ; Antes lo reponía sólo `cargar_mapa`, y a esa altura el único que la
    ; llamaba era una **puerta**: un comando `Teleport` carga el mapa por
    ; `cargar_mapa_sin_eventos`, que no la toca. Así que ocho teletransportes
    ; gastaban el presupuesto para toda la partida y del noveno en adelante el
    ; `beq nada` de abajo los descartaba **en silencio**. La apertura entera son
    ; teletransportes encadenados y casi no tiene puertas: para cuando el
    ; despachante del mapa 4 quería mandar al pad de Talan ya no quedaba
    ; ninguno, el salto se perdía, y como su página es automática y su switch
    ; sigue prendido volvía a arrancar sola para siempre. taro lo vio el
    ; 2026-09-07 como un mapa vacío del que no se podía salir, con la música
    ; fundiéndose y volviendo a empezar en ciclo; el volcado de la RAM decía
    ; `mapa_actual` = 4 con el evento 1 corriendo.
    lda #SALTOS_MAX
    sta saltos_restantes

    ; La cola está vacía, así que el flanco de A es para hablar. En RM2k es el
    ; mismo botón que cierra un mensaje y que confirma, y el orden importa: con
    ; un mensaje abierto el jugador no se actualiza —arriba se sale por
    ; `no_avanza`— así que no puede hablarle a nadie mientras lee.
    ;
    ; Y sólo con el héroe quieto: `CheckActionEvent` cuelga del `if
    ; (IsStopping())` de `Game_Player::UpdateNextMovementAction`.
    lda pad_a
    beq nada
    lda pad_a_ant
    bne nada                    ; ya lo tenía apretado: no es un flanco
    lda step_left
    bne nada                    ; a mitad de un paso no se habla
    jsr probar_accion
    beq nada
    ; Marcó un evento: se arranca en este mismo cuadro.
hay_esperando:
    jsr arrancar_esperando
    beq nada                    ; ninguno tenía página con qué correr

corriendo:
    ; El `while (!interp.IsRunning())` de `Game_Map::UpdateForegroundEvents`:
    ; si la página termina, la que siga esperando arranca **en este mismo
    ; cuadro** y no en el que viene. Encadenarlas al cuadro siguiente metía un
    ; cuadro de diferencia por página, y una cinemática son decenas.
    lda #ARRANQUES_MAX
    sta arranques
seguir_corriendo:
    jsr correr_codigo
    ; Si la página terminó y era la del evento que gira, vuelve a su pose: el
    ; `UpdateFacing` de `OnFinishForegroundEvent`.
    lda ev_activo
    bne sin_fin_de_giro
    lda f:GIRO_EV
    cmp ev_corriendo
    bne sin_fin_de_giro
    jsr giro_deshacer
sin_fin_de_giro:
    ; El refresco pendiente, **al salir del intérprete**: es el
    ; `if (Game_Map::GetNeedRefresh()) Game_Map::Refresh();` del final de
    ; `Game_Interpreter::Update`, y de él depende que el idioma de RM2k
    ; funcione. Una página que prende el switch que la desactiva deja de ser la
    ; activa antes de que se decida qué corre después; sin esto, al terminar
    ; seguía pareciendo automática y volvía a arrancar en el mismo cuadro, una
    ; y otra vez hasta agotar el presupuesto de `ARRANQUES_MAX`.
    ;
    ; EasyRPG además refresca **antes de cada comando**, arriba del lazo. Acá
    ; no hace falta y sale caro: ningún opcode de los que hay lee cuál es la
    ; página activa de un evento —el único que la lee es `arrancar_esperando`,
    ; que corre justo acá abajo—. Haciéndolo por comando, la cinemática de
    ; apertura perdía cinco cuadros: sus páginas prenden switches de a montones.
    ; El día que aparezca un opcode que sí la lea, esto vuelve al lazo.
    lda refresco
    beq sin_refresco_aca
    stz refresco
    lda #1
    sta refresco_cuadro         ; la completa, al principio del cuadro que viene
    jsr elegir_automaticas
sin_refresco_aca:
    lda salto_hay
    bne hubo_salto
    lda ev_activo
    bne nada                    ; sigue corriendo: el cuadro terminó
    lda esperando_n
    beq nada
    dec arranques
    beq nada                    ; se acabó el presupuesto del cuadro
    jsr arrancar_esperando
    bne seguir_corriendo
    rts
hubo_salto:
    stz salto_hay
    rep #$20
.a16
    lda salto_x
    sta entrada_x
    lda salto_y
    sta entrada_y
    sep #$20
.a8
    ; De acá no se carga nada: se pide el fundido y el mapa se carga adentro,
    ; en el primer cuadro negro. Ver `fundido_tick`. Lo que sí queda decidido
    ; acá es **cuál** de los dos casos es, porque `mapa_actual` va a haber
    ; cambiado para cuando toque hacerlo.
    ;
    ; Un salto **al mismo mapa** no recarga nada: sólo mueve al héroe. Es el
    ; `map_changed = (GetMapId() != teleport_target.GetMapId())` de
    ; `Game_Player::PerformTeleport`. Recargarlo volvía a encolar los eventos
    ; automáticos, y con eso la cinemática de apertura —que salta dos veces
    ; adentro del mapa 1— se reiniciaba sola para siempre. Fundir, en cambio,
    ; funde igual: en RM2k el `TeleportParams` sale siempre con
    ; `erase_screen = true`, mire a donde mire el salto.
    ; El índice del mapa es de dieciséis bits —ver `mapa_actual`— y esto va por
    ; X y no por A justamente por eso: X ya es de dieciséis, así que copiar y
    ; comparar no cuesta el `rep`/`sep` que sí costaría por el acumulador. Y no
    ; es una cuenta de elegancia: con los cuatro bytes de más, el `beq nada` de
    ; `eventos_tick` se pasaba de los 128 que alcanza un salto relativo.
    ldx salto_mapa
    stx fundido_mapa
    cpx mapa_actual
    bne otro_mapa
    lda #FUNDIDO_MISMO          ; un salto al mismo mapa no recarga nada
    bra pedir_fundido
otro_mapa:
    ; El presupuesto de saltos se gasta **acá y no antes**, o sea sólo cuando
    ; se cambia de mapa. Es lo que hace la referencia, donde `saltos` es local
    ; a `entrar_al_mapa` y sólo lo baja el lazo que entra a un mapa nuevo; un
    ; salto al mismo mapa no lo toca.
    ;
    ; Cobrándoselo a los saltos al mismo mapa —que es lo que hacía— el
    ; presupuesto se drenaba sin reponerse nunca, porque un salto al mismo mapa
    ; no llama a `cargar_mapa`, que es quien lo repone. La escena de Talan salta
    ; tres veces adentro del mapa 3 y la apertura dos adentro del 1: después de
    ; ocho, **todo teletransporte se descartaba en silencio**. taro lo vio como
    ; puertas que se abren y no llevan a ningún lado, y como algo que "a veces
    ; pasa y a veces no": dependía de cuántos saltos llevara la partida.
    ;
    ; Y se mira antes de bajarlo, no después: con `dec` sobre cero el byte daba
    ; la vuelta a 255 y el tope fallaba **una sola vez** y después dejaba pasar
    ; doscientos cincuenta y cinco más.
    lda saltos_restantes
    bne hay_presupuesto
    lda #PANICO_SALTOS
    jmp entrar_en_panico        ; y de ahí no se vuelve
hay_presupuesto:
    dec saltos_restantes
    lda #FUNDIDO_SALTO
pedir_fundido:
    jsr empezar_fundido
    ; La página que pidió el salto sigue corriendo del otro lado: su código está
    ; en la ROM y el cursor quedó guardado. Las páginas del mapa nuevo se
    ; encolan recién cuando ésta termine.
nada:
    rts
.endproc

; Se acabó: algo que no puede pasar pasó. A trae el código, que queda en
; `panico` para que una prueba de estado pueda decir cuál fue.
;
; No hay `printf` en una SNES y volver de acá no tiene sentido —el estado ya es
; inconsistente—, así que lo que queda es que se vea: la pantalla parpadea entre
; negro y pleno para siempre. Es feo a propósito. Lo que se quiere evitar es lo
; contrario, que el juego siga andando como si nada y el error aparezca media
; hora después convertido en otra cosa.
.proc entrar_en_panico
.a8
.i16
    sta panico
    sei                         ; ni siquiera el vblank: nada más va a pasar
lazo:
    ldx #$2000
espera_prendido:
    dex
    bne espera_prendido
    lda #$0F
    sta INIDISP
    ldx #$2000
espera_apagado:
    dex
    bne espera_apagado
    lda #$80
    sta INIDISP
    bra lazo
.endproc

; Arranca un fundido de teletransporte. A trae qué hay que hacer cuando la
; pantalla llegue a negro; el mapa, si hace falta, ya está en `fundido_mapa`.
.proc empezar_fundido
.a8
.i16
    sta fundido_que
    lda #1
    sta fundido
    ; El reloj del fundido son **vueltas del lazo**, o sea ticks, y no cuadros
    ; de hardware: así el fundido dura FUNDIDO_TOTAL ticks tarde lo que tarde la
    ; carga del mapa adentro del negro. La referencia lo contaba igual, con un
    ; contador que subía una vez por cuadro de mundo; ya no está.
    ;
    ; Estuvo contando `boot_cuadros` —cuadros de hardware— desde que la carga
    ; empezó a tardar seis o siete cuadros adentro de una sola vuelta: contando
    ; vueltas el fundido duraba eso de más **en cuadros**, y el arnés, que
    ; contaba cuadros, quedaba corrido. Desde el 2026-09-08 el arnés cuenta
    ; ticks —ver `vueltas`— así que el reloj vuelve a ser el mismo de los dos
    ; lados y el que absorbe el atraso es el reloj de pared.
    lda vueltas
    sta fundido_base
    rts
.endproc

; Un cuadro del fundido. Devuelve A distinto de cero mientras el juego tenga que
; quedarse quieto, que es todo lo que dura.
;
; RM2k congela la escena entera mientras la transición corre: `Scene::MainFunction`
; ve `IsAsyncPending()` y llama a `Player::Update(false)`, que no actualiza nada.
; Acá es lo mismo por omisión: el lazo principal se saltea el intérprete, al
; héroe, los eventos, el cronómetro y todo lo que mueva algo. Lo que sigue
; corriendo es la música, que en RM2k tampoco se corta.
.proc fundido_tick
.a8
.i16
    lda fundido
    beq no_hay
    lda vueltas                 ; el byte bajo alcanza: el fundido dura 70
    sec
    sbc fundido_base
    cmp #FUNDIDO_TOTAL
    bcs terminar
    cmp #FUNDIDO_CARGA
    bcc rampa                   ; todavía se está apagando
    pha
    jsr cargar_lo_pedido        ; una sola vez: se apaga solo
    pla
rampa:
    ; El brillo de este cuadro. Bajando, la rampa se lee al revés.
    cmp #FUNDIDO_RAMPA
    bcs subiendo
    eor #$FF
    clc
    adc #FUNDIDO_RAMPA          ; FUNDIDO_RAMPA - 1 - t
    bra en_la_rampa
subiendo:
    sec
    sbc #(FUNDIDO_CUADROS + FUNDIDO_NEGRO)
    bcs en_la_rampa             ; pasada la carga: la rampa de vuelta
    lda #0                      ; el negro del medio
    sta brillo
    bra sigue
en_la_rampa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda fundido_rampa, x
    sta brillo
sigue:
    lda #1                      ; el juego sigue congelado
    rts
terminar:
    stz fundido
    lda #BRILLO_MAX
    sta brillo
no_hay:
    lda #0
    rts
.endproc

; Lo que el fundido tiene que hacer en su primer cuadro negro: cargar el mapa,
; o mover al héroe si el salto era al mismo. Se hace una vez y se apaga.
;
; La pantalla se pone en blanking forzado a mano en vez de esperar al vblank:
; `cargar_mapa` escribe VRAM y CGRAM por DMA y con el PPU dibujando esas
; escrituras se pierden. No se ve, porque el brillo ya viene en cero.
.proc cargar_lo_pedido
.a8
.i16
    lda fundido_que
    beq listo
    pha
    lda #$80
    sta INIDISP
    stz brillo                  ; y que el vblank que viene lo deje en negro
    pla
    cmp #FUNDIDO_MISMO
    bne carga
    jsr mover_heroe_a
    bra hecho
carga:
    cmp #FUNDIDO_PUERTA
    bne salto
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa             ; una puerta: además reinicia el tope de saltos
    sep #$20
.a8
    stz step_left               ; el paso que se estaba dando quedó allá
    stz moving
    bra hecho
salto:
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa_sin_eventos
    sep #$20
.a8
    ; Y los eventos automáticos del mapa nuevo, a la cola. La página que pidió
    ; el salto sigue corriendo —su código está en la ROM y el cursor quedó
    ; guardado— así que éstos arrancan recién cuando ella termine, que es el
    ; orden de RM2k: `Game_Interpreter_Map::OnMapChange` no toca la pila del
    ; intérprete, sólo los ids de evento.
    ;
    ; Antes no se marcaban nunca. El comentario decía que se encolaban "cuando
    ; ésta termine" y no lo hacía nadie: después de un teletransporte, los
    ; eventos del mapa de destino no corrían jamás. Nada lo veía porque la única
    ; prueba que teletransportaba miraba el tinte, que lo pone el mapa de origen.
    ; Hoy lo hace `cargar_mapa_sin_eventos`, adentro de su refresco.
hecho:
    stz fundido_que
    ; Y OAM, que si no se queda con la del mapa que se dejó. El lazo no la
    ; rearma mientras el fundido dura —`build_oam` es de las cosas que se
    ; saltea— así que la rampa de vuelta iría dibujando el mapa nuevo con los
    ; sprites viejos. No es teórico: son los mil y pico de pixeles que la
    ; referencia cobró la primera vez que se comparó adentro de un fundido.
    jsr build_oam
listo:
    rts
.endproc

; Mueve al héroe a (entrada_x, entrada_y) sin tocar el mapa. Es lo que hace un
; teletransporte que no cambia de mapa: la tabla de eventos, sus posiciones, las
; rutas que estén corriendo y las páginas encoladas siguen como estaban.
.proc mover_heroe_a
.a8
.i16
    rep #$20
.a16
    lda entrada_x
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida
    sep #$20
.a8
    stz step_left               ; un paso a mitad de camino se corta
    stz moving
    jsr menu_olvidar            ; y un pedido de menú también: `MoveTo`
    jsl f:encuentro_mover       ; y lo caminado, que es lo otro que borra
    jsr follow_camera
    jsr fill_window             ; la cámara saltó: el tilemap se llena de nuevo
    jsr init_hero_ptr
    rts
.endproc

; --- el intérprete de eventos ----------------------------------------------
;
; RM2k se queda con la página de número más alto cuyas condiciones se cumplen
; todas. Las páginas vienen agrupadas por evento y en orden, así que alcanza una
; sola pasada: se recuerda la última que cumplió, y al cambiar de evento se
; ejecuta la que haya quedado.
;
; Sólo se corren las automáticas. Las de contacto ya las cubren las puertas, y
; las de botón necesitan que haya un botón que apretar.

; Los campos de la página que está en pag_ofs, a variables.
.proc leer_pagina
.a8
.i16
    ldy pag_ofs
    rep #$20
.a16
    lda [pag_ptr], y            ; +0  a qué evento pertenece
    sta pg_evento
    sep #$20
.a8
    iny
    iny
    iny
    lda [pag_ptr], y            ; +3  qué la dispara. De a un byte: leerlo de a
    sta pg_trigger              ;     dos se llevaría puesto el switch de al lado
    iny
    rep #$20
.a16
    lda [pag_ptr], y            ; +4  el switch que pide, o 0
    sta pg_sa
    iny
    iny
    lda [pag_ptr], y            ; +6  el segundo, o 0
    sta pg_sb
    iny
    iny
    lda [pag_ptr], y            ; +8  su código: los 16 bits bajos
    sta pg_cod
    sep #$20
.a8
    iny
    iny
    lda [pag_ptr], y            ; +10 y su banco
    sta pg_cod + 2
    iny
    lda [pag_ptr], y            ; +11 el actor que pide en el grupo, o 0
    sta pg_actor
    iny
    lda [pag_ptr], y            ; +12 su capa
    sta pg_capa
    iny
    lda [pag_ptr], y            ; +13 las banderas de la ruta propia
    sta pg_flags
    iny
    lda [pag_ptr], y            ; +14 su frecuencia
    sta pg_frec
    iny
    lda [pag_ptr], y            ; +15 la velocidad de la página
    sta pg_vel
    iny
    lda [pag_ptr], y            ; +16 las órdenes de la ruta propia
    sta pg_ruta
    iny
    lda [pag_ptr], y
    sta pg_ruta + 1
    iny
    lda [pag_ptr], y
    sta pg_ruta + 2
    iny
    lda [pag_ptr], y            ; +19 cuántas
    sta pg_ruta_n
    iny
    lda [pag_ptr], y            ; +20 lo que dibuja la página, para los eventos
    sta pg_tile                 ;     que cambian de gráfico: el tile,
    iny
    lda [pag_ptr], y            ; +21 los atributos con paleta y prioridad,
    sta pg_attr
    iny
    lda [pag_ptr], y            ; +22 la pose, con el bit 7 si hay gráfico,
    sta pg_pose
    iny
    lda [pag_ptr], y            ; +23 y los bits de paso de su tile, o $FF
    sta pg_pasa
    rts
.endproc

; La página activa de cada evento y, con ella, la ruta propia que le toca. Es
; `Game_Map::Refresh` con `Game_Event::SetupFromPage`: al cargar el mapa y cada
; vez que un switch o el grupo cambian. Un evento cuya página activa es la
; misma de antes no se toca, y su ruta sigue por donde iba; uno cuya página
; cambió carga la ruta de la nueva desde el principio, con la espera del giro
; antes de la primera orden; y uno cuya página nueva no tiene ruta se queda sin
; órdenes. La velocidad de la página queda en `vel_por_ev` para las rutas
; forzadas.
;
; Son dos pasadas y no un lazo adentro del otro: la tabla de páginas se recorre
; una sola vez anotando la ganadora de cada evento, y después se mira evento
; por evento. Con eventos por páginas costaba más de un cuadro, y un cuadro
; perdido en un switch es un cuadro corrido contra la referencia.
; `Game_Map::Refresh` entero: elegir las páginas activas y aplicarlas.
.proc rutas_de_pagina
.a8
.i16
    jsr elegir_paginas
    jmp aplicar_paginas
.endproc

; Como `elegir_paginas`, pero mirando **sólo** los eventos con automáticas.
;
; Es lo que corre el refresco de adentro del lazo de comandos, y es lo único
; que ese refresco necesita hacer en el acto: lo que el comando siguiente puede
; llegar a mirar es qué evento tiene una automática activa. En el mapa 2 son
; cuatro páginas de sesenta y tres, contra las veintitrés que mira la completa.
; La completa corre igual, al principio del cuadro que viene.
.proc elegir_automaticas
.a8
.i16
    lda #1
    sta solo_auto
    jmp elegir_con_filtro
.endproc

; La primera mitad: qué página queda activa en cada evento, y de paso el
; `FLAG_AUTO` de cada uno.
.proc elegir_paginas
.a8
.i16
    stz solo_auto
    jmp elegir_con_filtro
.endproc

; El cuerpo de las dos, con `solo_auto` diciendo cuál es.
.proc elegir_con_filtro
.a8
.i16
    ; El `FLAG_AUTO` no se apaga con un lazo aparte sino en la primera página
    ; de cada evento, más abajo: ciento veinte vueltas en cada refresco
    ; costaban el cuadro entero cuando el refresco caía sobre algo caro.
    lda solo_auto
    beq vaciar_todo
    rep #$20
.a16
    lda #$FFFF
    sta rp_ev_ant
    bra sin_vaciar              ; la pasada corta no pisa lo de las rutas
.a8
vaciar_todo:
    rep #$20
.a16
    ldx #$0000
    lda ev_total
    asl a
    sta rp_ev_ant               ; el tope en bytes, prestado un momento
vaciar:
    lda #$FFFF
    sta eleg_por_ev, x
    inx
    inx
    cpx rp_ev_ant
    bne vaciar
    lda #$FFFF
    sta rp_ev_ant               ; y ahora sí, "ningún evento visto todavía"
.a16
sin_vaciar:
    ldx mapa_ofs
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    bne hay_paginas
    jmp sin_paginas             ; queda lejos para un salto corto
hay_paginas:
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
recorrer:
    ; Sólo las páginas de los eventos que tienen alguna con ruta propia, o
    ; gráfico que sigue a la página, o alguna automática: los bits 5, 6 y 7 de
    ; +13 lo dicen, y se lee ese byte solo. Con todas las páginas enteras esto
    ; costaba más de un cuadro, y el cuadro se perdía.
    ;
    ; Las tres cosas se resuelven en **una sola** recorrida a propósito. Con la
    ; de las automáticas aparte —que es como nació— el refresco hacía dos
    ; vueltas y volvía a perder el cuadro: se veía como el tinte de
    ; `snes-pan` llegando uno tarde.
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #13
    tay
    sep #$20
.a8
    lda [pag_ptr], y
    ldx solo_auto
    beq filtro_completo
    and #$80                    ; la pasada corta: sólo las automáticas
    bra con_filtro
filtro_completo:
    and #$E0
con_filtro:
    bne mirar_pagina
    jmp siguiente               ; la recorrida creció y ya no entra en un beq
mirar_pagina:
    jsr leer_pagina
    ; La primera página de un evento con automáticas le apaga el `FLAG_AUTO`:
    ; lo vuelve a prender, más abajo, la última de sus páginas que cumpla. Las
    ; páginas de un evento vienen juntas, así que alcanza con mirar si cambió.
    lda pg_flags
    and #$80
    beq no_es_auto
    rep #$20
.a16
    lda pg_evento
    cmp rp_ev_ant
    beq mismo_ev16
    sta rp_ev_ant
    tax
    sep #$20
.a8
    cpx #EV_MAX
    bcs no_es_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq ya_apagada
    dec auto_n
ya_apagada:
    ; Los **dos** bits, y la última página que cumpla los vuelve a poner. El
    ; de espera también: si ninguna página del evento cumple, se queda sin
    ; página activa y la marca tiene que irse, que es el
    ; `ClearWaitingForegroundExecution` que `RefreshPage` hace cuando no
    ; encuentra ninguna. Dejándola puesta, la página que acababa de terminar
    ; volvía a arrancar: en la cinemática de apertura eso reiniciaba la escena
    ; entera en el cuadro 692.
    jsr desmarcar_esperando     ; el de espera, con su cuenta
    stz ev_flags, x             ; y el de automática, que la cuenta ya bajó
    bra no_es_auto
.a16
mismo_ev16:
    sep #$20
.a8
no_es_auto:
    jsr condiciones_ok
    beq no_cumple
    ; Cumple, así que por ahora es la activa de su evento. Si el evento tiene
    ; automáticas, acá se decide si la activa lo es: escribir en cada página
    ; que cumple deja al final lo que diga la última, que es la que gana.
    lda pg_flags
    and #$80
    beq sin_auto
    ldx pg_evento
    cpx #EV_MAX
    bcs sin_auto
    lda ev_flags, x
    and #FLAG_AUTO
    beq sigue_apagada
    dec auto_n
sigue_apagada:
    lda ev_flags, x
    and #FLAG_ESPERA            ; se apaga, y abajo se vuelve a prender si toca
    sta ev_flags, x
    lda pg_trigger
    cmp #TRIGGER_AUTOMATICO
    bne no_gana_una_auto
    lda pg_cod
    ora pg_cod + 1
    ora pg_cod + 2
    beq no_gana_una_auto        ; no compiló: no hay nada que arrancar
    lda ev_flags, x
    ora #FLAG_AUTO
    sta ev_flags, x
    inc auto_n
    jsr marcar_esperando        ; sigue siendo automática: la marca vuelve
    bra sin_auto
no_gana_una_auto:
    ; La que gana no es automática, así que el evento **deja** de esperar. Se
    ; escribe en cada página que cumple y gana la última, que es la activa;
    ; marcando y no desmarcando, la página 0 de un evento dejaba la marca
    ; puesta aunque ganara la 1. Es el `ClearWaitingForegroundExecution` que
    ; `Game_Event::RefreshPage` hace al cambiar de página.
    jsr desmarcar_esperando
sin_auto:
    ; La página activa se anota para los tres casos, no sólo para los de ruta o
    ; gráfico: `arrancar_esperando` la lee de acá en vez de volver a recorrer
    ; las páginas del mapa. En el mapa 2 eso son sesenta y tres páginas por
    ; cada página que arranca, y se perdía el cuadro. La segunda pasada, que
    ; es la que toca rutas y gráficos, saltea a los que no tienen esos bits.
    rep #$20
.a16
    lda pg_evento
    asl a
    tax
    lda pag_ofs
    sta eleg_por_ev, x          ; gana la última que cumple
    sep #$20
.a8
    bra siguiente
no_cumple:
    lda pg_flags
    and #$60
    bne con_rutas
    jmp siguiente               ; sólo automáticas: ya quedó apagado arriba
con_rutas:
    ; Un evento con rutas y sin página que cumpla todavía: $FFFE, para que la
    ; segunda pasada lo distinga de los que no tienen rutas.
    rep #$20
.a16
    lda pg_evento
    asl a
    tax
    lda eleg_por_ev, x
    cmp #$FFFF
    bne ya_tiene
    ; Sin página que cumpla, por ahora: $FFFE, o $FFFD si el gráfico sigue a
    ; la página, que es el que hay que esconder.
    lda #$FFFE
    sta eleg_por_ev, x
    sep #$20
.a8
    lda pg_flags
    and #$20
    beq ya_tiene8
    rep #$20
.a16
    lda #$FFFD
    sta eleg_por_ev, x
    sep #$20
.a8
ya_tiene8:
    rep #$20
.a16
ya_tiene:
    sep #$20
.a8
siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    beq listo_eligiendo
    jmp recorrer                ; la recorrida creció y ya no entra en un bcc
listo_eligiendo:
    rts
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; La segunda mitad: cada evento con la ruta y el gráfico de su página activa.
; Recorre los eventos del mapa recargando filas de OAM y ranuras de ruta, así
; que es la cara: hacerla en medio de un cuadro costaba el cuadro entero en el
; mapa 2. Por eso el refresco a mitad de comando la deja para el principio del
; cuadro que viene, donde no cambia nada: lo que toca no se ve hasta que se
; dibuje.
.proc aplicar_paginas
.a8
.i16
    ; El giro primero, con las páginas nuevas ya elegidas y antes de que se
    ; reescriban las filas: ver `giro_revisar` y `giro_reponer`.
    jsr giro_revisar
    ; El puntero a las páginas se rearma acá y no se hereda de `elegir_paginas`:
    ; entre una y otra puede haber pasado un cuadro entero.
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz par_n                   ; la lista de paralelos se rehace entera
    stz rp_ev
    stz rp_ev + 1
cada_evento:
    rep #$20
.a16
    lda rp_ev
    cmp ev_total
    bcc :+
    jmp fin16                   ; lejos para un salto corto
:
    asl a
    tax
    lda eleg_por_ev, x
    cmp #$FFFF
    bne :+
    jmp proximo                 ; sin rutas propias: nada que mirar
:
    cmp #$FFFE
    bne :+
    jmp sin_activa16            ; con rutas, y ninguna página que cumpla
:
    cmp #$FFFD
    bne :+
    jmp esconder16              ; con gráfico de página, y ninguna: se esconde
:
    sta pag_ofs
    sep #$20
.a8
    jsr leer_pagina
    ; Si la que ganó es paralela, el evento entra en la lista de los que
    ; `paralelos_tick` corre. Se arma acá y no en cada cuadro porque cuál es la
    ; página activa sólo cambia en un refresco, y recorrer los ciento veinte
    ; eventos por cuadro es justo lo que este refresco existe para no hacer.
    lda pg_trigger
    cmp #TRIGGER_PARALELO
    bne no_es_paralela
    lda pg_cod
    ora pg_cod + 1
    ora pg_cod + 2
    beq no_es_paralela          ; no compiló: no hay nada que correr
    jsr anotar_paralelo
no_es_paralela:
    lda pg_flags
    and #$60
    bne con_ruta_o_grafico
    jmp proximo                 ; sólo automáticas: la anotación es para otro
con_ruta_o_grafico:
    jsr grafico_de_pagina       ; lo que la página dibuja, a la fila del NPC
    lda rp_ev
    jsr ranura_del_evento       ; X = su ranura, o $FFFF
    lda pg_flags
    and #$01
    beq sin_ruta
    cpx #$FFFF
    beq nueva
    rep #$20
.a16
    lda ruta_ev + 20, x
    cmp pag_ofs
    sep #$20
.a8
    bne :+
    jmp proximo                 ; la misma página de antes: sigue por donde iba
:
    bra cargar
nueva:
    lda rp_ev
    jsr giro_por_ruta
    jsr ranura_libre
    cpx #$FFFF
    bne :+
    jmp proximo                 ; no hay lugar: se queda quieto
:
    lda rp_ev
    sta ruta_ev + 0, x
    stz ruta_ev + 6, x
    stz ruta_ev + 7, x
    lda #RUTA_EV_SIN_MIRAR
    sta ruta_ev + 8, x
    stz ruta_ev + 12, x
    stz ruta_ev + 13, x
    lda #1
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
    stz ruta_ev + 22, x
    stz ruta_ev + 23, x
cargar:
    phx
    lda rp_ev
    jsr giro_por_ruta           ; con ruta, adónde mira lo decide ella
    plx
    jsr cargar_pagina_en_ranura
    jmp proximo
sin_ruta:
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr quitar_pagina_de_ranura
    jmp proximo
.a16
esconder16:
    sep #$20
.a8
    lda rp_ev
    jsr esconder_npc
    jmp proximo
.a16
sin_activa16:
    sep #$20
.a8
    lda rp_ev
    jsr ranura_del_evento
    cpx #$FFFF
    bne :+
    jmp proximo
:
    jsr quitar_pagina_de_ranura
proximo:
    rep #$20
.a16
    inc rp_ev
    sep #$20
.a8
    jmp cada_evento
.a16
fin16:
sin_paginas:
    sep #$20
.a8
    rts
.endproc

; --- los intérpretes paralelos ----------------------------------------------
; `Game_Map::UpdateMapEvents`: cada evento con una página paralela tiene **su
; propio intérprete** y corre todos los cuadros, aparte del de primer plano, con
; un mensaje abierto y con otra página en curso. Cuando su página termina, el
; cuadro siguiente la vuelve a empezar: RPG_RT hace el `Push` antes de cada
; `Update` si el intérprete no está corriendo, así que una página que se agota
; en un cuadro se reinicia para siempre. Es lo que hace andar a los cuatro autos
; de Lashe City, cuya página entera es un `MoveEvent`.
;
; Corren con los **mismos** globales que el primer plano —`cod_ptr`, `ev_cur`,
; `ev_esperando`, `ev_activo`, `ev_corriendo`— así que ese contexto se guarda en
; la pila y se devuelve al final. Doce bytes, contra los 24 que es lo más hondo
; que la pila llegó a bajar en toda la tanda.
;
; El estado de cada uno va en la RAM del banco 1 e **indexado por evento**, no
; por ranura, y lleva de qué página es: si la página activa cambia, RM2k rehace
; el intérprete (`Game_Event::Setup`), así que se arranca de cero. Sin eso, un
; refresco en medio de una espera la dejaba a mitad de camino corriendo el
; código de otra página.
.proc limpiar_paralelos
.a8
.i16
    stz par_n
    rep #$20
.a16
    lda #FAR_PAR_ESTADO
    sta WMADDL                  ; los dos bytes bajos de la dirección
    sep #$20
.a8
    stz WMADDH
    ldx #(EV_MAX * PAR_BYTES)
borrar:
    stz WMDATA                  ; el puerto auto-incrementa
    dex
    bne borrar
    rts
.endproc

; La ventana de banco apuntada a la entrada de la lista que trae A. Es la misma
; cuenta para escribirla y para leerla, y estaba copiada en los dos lados.
.proc par_lista_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_LISTA_BYTES
    clc
    adc #FAR_PAR_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; Anota al evento `rp_ev` en la lista de paralelos del mapa, con la página que
; acaba de ganar: entra con `pg_*` de ella y con `pag_ofs` en su offset, que es
; como `aplicar_paginas` la tiene leída.
.proc anotar_paralelo
.a8
.i16
    lda par_n
    cmp #PARALELO_MAX
    bcc hay_lugar
    rts                         ; el conversor corta antes de que esto pase
hay_lugar:
    jsr par_lista_apuntar
    lda rp_ev
    sta WMDATA
    lda pg_cod
    sta WMDATA
    lda pg_cod + 1
    sta WMDATA
    lda pg_cod + 2
    sta WMDATA
    lda pag_ofs
    sta WMDATA
    lda pag_ofs + 1
    sta WMDATA
    inc par_n
    rts
.endproc

; Un cuadro de cada evento con página paralela.
.proc paralelos_tick
.a8
.i16
    lda par_n
    bne hay
    rts
hay:
    rep #$20
.a16
    lda ev_cur
    pha
    lda ev_esperando
    pha
    lda ev_corriendo
    pha
    lda cod_ptr
    pha
    sep #$20
.a8
    lda cod_ptr + 2
    pha
    lda ev_activo
    pha

    stz par_i
lazo:
    lda par_i
    jsr par_lista_apuntar
    lda WMDATA                  ; de qué evento es esta ranura
    sta par_ev
    lda WMDATA                  ; y su página, ya resuelta por el refresco:
    sta cod_ptr                 ; derecho al cursor del intérprete, que es lo
    lda WMDATA                  ; único que `un_paralelo` iba a hacer con ella
    sta cod_ptr + 1
    lda WMDATA
    sta cod_ptr + 2
    lda WMDATA
    sta pag_ofs
    lda WMDATA
    sta pag_ofs + 1
    rep #$20
.a16
    lda par_ev
    and #$00FF
    tax
    sep #$20
.a8
    jsr un_paralelo
    inc par_i
    lda par_i
    cmp par_n
    bcc lazo

    pla
    sta ev_activo
    pla
    sta cod_ptr + 2
    rep #$20
.a16
    pla
    sta cod_ptr
    pla
    sta ev_corriendo
    pla
    sta ev_esperando
    pla
    sta ev_cur
    sep #$20
.a8
    rts
.endproc

; Un cuadro del evento cuyo índice trae X, con `elegida` y `pag_ofs` ya puestos
; por el lazo desde la lista de paralelos.
;
; Acá **no** se vuelve a elegir la página ni a leerla del cartucho. Era lo que
; costaba el cuadro en el HQ de los Lazer Teeth —once paralelos, y el décimo se
; pasaba— y no podía dar otra respuesta: la lista y lo que lleva adentro los
; rehace `aplicar_paginas`, que es `Game_Map::Refresh`, o sea el único momento
; en que la página activa cambia. Tampoco hace falta preguntar si la página es
; paralela y si compiló: si no lo fuera, el evento no estaría en la lista.
.proc un_paralelo
.a8
.i16
    ; Dónde cae su estado: el evento por ocho.
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; por PAR_BYTES
    clc
    adc #FAR_PAR_ESTADO
    sta par_dir
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    sta ev_cur
    lda WMDATA
    sta ev_cur + 1
    lda WMDATA
    sta ev_esperando
    lda WMDATA
    sta ev_esperando + 1
    lda WMDATA
    sta ev_activo
    lda WMDATA
    sta temp + 2                ; de qué página era este estado
    lda WMDATA
    sta temp + 3

    rep #$20
.a16
    lda temp + 2
    cmp pag_ofs
    beq misma_pagina
    ; Otra página: otro intérprete, y su número queda anotado. Se escribe
    ; **antes** de correr porque `correr_codigo` se lleva puesto a `temp`.
    stz ev_cur
    stz ev_esperando
    lda par_dir
    clc
    adc #5
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    stz ev_activo
    rep #$20
.a16
    lda pag_ofs
    sta temp + 2
    sep #$20
.a8
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    rep #$20
.a16
misma_pagina:
    ; La espera, igual que la del primer plano.
    lda ev_esperando
    beq sin_espera
    dec a
    sta ev_esperando
    sep #$20
.a8
    jmp guardar                 ; este cuadro se le va esperando
.a16
sin_espera:
    txa
    sta ev_corriendo            ; de quién es la página, para un MoveEvent suyo
    sep #$20
.a8
    lda ev_activo
    bne corriendo
    ; No venía corriendo: la página vuelve a empezar. Es el `Push` que RPG_RT
    ; hace antes de cada `Update`, y por eso no se reinicia al terminar sino al
    ; cuadro siguiente.
    rep #$20
.a16
    stz ev_cur
    sep #$20
.a8
    lda #1
    sta ev_activo
corriendo:
    jsr correr_codigo
guardar:
    rep #$20
.a16
    lda par_dir
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda ev_cur
    sta WMDATA
    lda ev_cur + 1
    sta WMDATA
    lda ev_esperando
    sta WMDATA
    lda ev_esperando + 1
    sta WMDATA
    lda ev_activo
    sta WMDATA

    ; Y el paso de **este** evento, acá mismo y no al final de la vuelta.
    ; `Game_Event::Update` corre el intérprete paralelo y a continuación llama a
    ; `Game_Character::Update()` —easyrpg, `game_event.cpp:580`—, y
    ; `UpdateMapEvents` hace eso evento por evento. No es lo mismo que correr
    ; todos los intérpretes y después mover a todos: se ve cuando una página
    ; paralela le fuerza una ruta a **otro** evento. En Lashe City el `Car4` le
    ; pisa la suya al `Car2` en cada cuadro —los dos apuntan al id 3 de RM2k, que
    ; ahí es el `Car2`— y con los pasos todos al final el pisotón gana y el
    ; `Car2` no camina nunca. taro lo vio, y en EasyRPG y en el RPG Maker
    ; original los cuatro autos andan.
    lda par_ev
    jsr ranura_del_evento
    cpx #$FFFF
    beq sin_ranura
    phx
    jsr cuadro_de_ruta_ev
    plx
    phx
    jsr animar_ruta_ev
    plx
    phx
    jsr refrescar_npc
    plx
    lda ruta_ev + 18, x
    ora #$40                    ; ya dio su paso: `mover_eventos` lo saltea
    sta ruta_ev + 18, x
sin_ranura:
    rts
.endproc

; La ranura de ruta del evento cuyo índice trae A: X, o $FFFF si no tiene.
; Lo que la página activa de un evento que cambia de gráfico dibuja, copiado a
; su fila de NPC: el tile, los atributos —paleta y prioridad de su capa—, la
; pose y hacia dónde mira, si se ve, y los bits de paso de su tile. Y la clave
; de dibujado con la capa de la página, que puede cambiar —el ascensor del
; mapa 2 pasa de la capa del héroe a la de abajo al abrirse—, así que la fila
; se reacomoda como la de un evento que camina. Es `SetupFromPage` para el
; gráfico, y es lo que abre las puertas de este juego: la página con el tile
; de los escombros aparece donde antes no había nada. Entra con `pg_*` de la
; página activa y el evento en `rp_ev`.
.proc grafico_de_pagina
.a8
.i16
    ; El bit 5 dice que la fila sigue a la página, y quiere decir dos cosas
    ; según la fila:
    ;
    ; * **si no camina**, sale todo de la página activa: el tile, la paleta, la
    ;   pose y si se ve. Es lo que abre las puertas de este juego.
    ; * **si camina**, todo eso menos el tile y la paleta, que apuntan a su
    ;   ranura de doce poses y pisarlos la dejaría quieta.
    ;
    ; La distinción existe porque un evento puede caminar **y** aparecer con la
    ; página, y antes del 2026-09-08 el conversor tenía que elegir: elegía
    ; caminar, y entonces la fila —que nace escondida cuando al cargar el mapa
    ; ninguna página cumple— no aparecía nunca. taro lo encontró con el `Bum` y
    ; el `Mechanic` de Lashe City; la referencia los dibujaba y la ROM no, 245
    ; y 191 pixeles.
    ;
    ; No es un bit nuevo porque en +13 no queda ninguno: con ruta propia los
    ; cinco de abajo son las banderas de la ruta. Y no hace falta, porque
    ; **la fila ya lo dice**: +9 vale NPC_QUIETO o el banco de sus poses.
    lda pg_flags
    and #$20
    bne hay_algo
    rts                         ; su fila no sigue a la página
hay_algo:
    lda rp_ev
    jsr npc_de_evento
    cpy #$FFFF
    bne hay_fila
    rts                         ; sin fila: nada que dibujar
hay_fila:
    sty npc_fila
    lda pg_pose
    bmi con_grafico
    lda #0                      ; la página no dibuja nada: escondido
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
    rts
con_grafico:
    and #$0F
    sta npc_buf + 12, y         ; la pose que hay en VRAM es ésta
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:dir_de_pose, x
    sta npc_buf + 10, y
    ; El tile y la paleta sólo si la fila no camina. Si camina, apuntan a su
    ; ranura de doce poses y pisarlos la dejarían quieta; la pose de arriba sí
    ; va, que es la que la página declara y la que el refresco sube del banco.
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne sin_tocar_el_tile
    lda pg_tile
    sta npc_buf + 6, y
    lda pg_attr
    sta npc_buf + 7, y
sin_tocar_el_tile:
    lda #1
    sta npc_buf + 14, y
    lda pg_pasa
    sta npc_buf + 15, y
    ; La clave: la capa de la página, con la Y de la fila.
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$0FFF
    sta temp
    lda pg_capa
    and #$00FF
    xba
    asl a
    asl a
    asl a
    asl a
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8
    phy
    jsr giro_reponer            ; si es la que gira, gira de nuevo
    ply
    jmp acomodar_npc
listo:
    rts
.endproc

; Esconde la fila del evento en A, si tiene una: no se dibuja y su tile no le
; impone nada a la celda.
.proc esconder_npc
.a8
.i16
    jsr npc_de_evento
    cpy #$FFFF
    beq listo
    lda #0
    sta npc_buf + 14, y
    lda #$FF
    sta npc_buf + 15, y
listo:
    rts
.endproc

.proc ranura_del_evento
.a8
.i16
    sta otro_ev
    ; De la más alta usada para abajo, y no de cero para arriba: así el corte
    ; es `X == 0`, que el `tax` deja en Z gratis, y no hace falta un límite de
    ; dieciséis bits en RAM —que no hay—. Un evento tiene a lo sumo una ranura
    ; —sólo se le da una cuando `ranura_del_evento` no le encontró ninguna— así
    ; que el orden no cambia la respuesta.
    lda ruta_ev_tope
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por RUTA_EV_STRIDE
    tax
    sep #$20
.a8
buscar:
    cpx #$0000
    beq no_tiene
    rep #$20
.a16
    txa
    sec
    sbc #RUTA_EV_STRIDE
    tax
    sep #$20
.a8
    lda ruta_ev, x
    cmp otro_ev
    bne buscar
    rts                         ; X = su ranura
no_tiene:
    ldx #$FFFF
    rts
.endproc

; Una ranura de ruta libre: X, o $FFFF si no queda ninguna.
.proc ranura_libre
.a8
.i16
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq listo
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    ldx #$FFFF
    rts                         ; sin lugar: el tope no se toca
listo:
    ; La ranura pasa a tener dueño, así que el tope sube si quedó más arriba
    ; del que había. Es el único lugar por donde se toma una: las dos —la
    ; página propia y la ruta forzada— piden acá.
    rep #$20
.a16
    txa
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a                       ; de bytes a número de ranura
    inc a
    sep #$20
.a8
    cmp ruta_ev_tope
    bcc ya_estaba
    sta ruta_ev_tope
ya_estaba:
    rts
.endproc

; La ruta propia de la página recién leída, a la ranura X, desde el principio.
; Queda guardada también aparte —+24 a +29— para volver a ella cuando una
; ruta forzada sobre el mismo evento termine.
.proc cargar_pagina_en_ranura
.a8
.i16
    lda pg_ruta
    sta ruta_ev + 1, x
    sta ruta_ev + 24, x
    lda pg_ruta + 1
    sta ruta_ev + 2, x
    sta ruta_ev + 25, x
    lda pg_ruta + 2
    sta ruta_ev + 3, x
    sta ruta_ev + 26, x
    lda pg_ruta_n
    sta ruta_ev + 4, x
    sta ruta_ev + 27, x
    stz ruta_ev + 5, x
    lda pg_frec
    sta ruta_ev + 16, x
    sta ruta_ev + 28, x
    lda pg_vel
    sta ruta_ev + 17, x
    sta ruta_ev + 29, x
    lda pg_flags
    and #$1E
    ora #$01                    ; de página
    sta ruta_ev + 18, x
    lda pg_capa
    sta ruta_ev + 31, x         ; su capa, para chocar con los demás
    rep #$20
.a16
    lda pag_ofs
    sta ruta_ev + 20, x
    sep #$20
.a8
    lda pg_frec
    jsr tras_giro               ; `SetMaxStopCountForTurn` antes de la primera
    sta ruta_ev + 9, x
    rts
.endproc

; La página nueva del evento de la ranura X no tiene ruta: se queda sin
; órdenes y sin página a la que volver.
.proc quitar_pagina_de_ranura
.a8
.i16
    lda ruta_ev + 18, x
    and #$01
    beq listo                   ; corría una forzada: no se toca
    stz ruta_ev + 4, x
    stz ruta_ev + 5, x
    stz ruta_ev + 9, x
    lda ruta_ev + 18, x
    and #$FE
    sta ruta_ev + 18, x
listo:
    stz ruta_ev + 27, x
    rep #$20
.a16
    lda #$FFFF
    sta ruta_ev + 20, x
    sep #$20
.a8
    rts
.endproc

; Cuánto avanza el paso de la ranura X por cuadro, a `temp`, de dieciséis bits.
.proc paso_de_ranura
.a8
.i16
    lda ruta_ev + 17, x
    dec a
    asl a
    rep #$20
.a16
    and #$00FF
    tay
    phx                         ; X trae la ranura y el que llama cuenta con ella
    tyx
    lda f:paso_por_vel, x
    plx
    sta temp
    sep #$20
.a8
    rts
.endproc

; Cuánto avanza el salto de la ranura X por cuadro, en A.
.proc salto_de_ranura
.a8
.i16
    lda ruta_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    phx                         ; X trae la ranura y el que llama cuenta con ella
    tyx
    lda f:salto_por_vel, x
    plx
    rts
.endproc

; La capa de la página activa del evento cuyo índice trae A, o $FF si no tiene
; ninguna. Es la misma pasada que `encolar_por_accion`: gana la última página
; cuyas condiciones se cumplen. Conserva X e Y; pisa `pag_*` y `pg_*`, que
; nadie tiene a medio usar cuando esto corre —se llama desde un paso, no desde
; adentro de una búsqueda de página—.
.proc capa_activa
.a8
.i16
    phx
    phy
    rep #$20
.a16
    and #$00FF
    sta capa_ev
    sep #$20
.a8
    lda #$FF
    sta capa_hallada
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    beq sin_paginas
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
recorrer:
    ; Sólo el evento que se busca: de las demás páginas se lee el evento y
    ; nada más. Leerlas enteras costaba, con un droide empujando contra el
    ; héroe cuadro por cuadro, más de un cuadro cada tanto.
    rep #$20
.a16
    ldy pag_ofs
    lda [pag_ptr], y            ; +0 a qué evento pertenece
    cmp capa_ev
    sep #$20
.a8
    bne siguiente
    jsr leer_pagina
    jsr condiciones_ok
    beq siguiente
    lda pg_capa
    sta capa_hallada
siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    bne recorrer
    lda capa_hallada
    ply
    plx
    rts
sin_paginas:
.a16
    sep #$20
.a8
    lda #$FF
    ply
    plx
    rts
.endproc

; Si el evento cuyo índice trae A está atravesando paredes: tiene ranura de
; ruta y la ranura lleva el bit. Devuelve A distinto de cero si sí. Pisa X.
.proc atraviesa_el_evento
.a8
.i16
    sta otro_ev
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp otro_ev
    bne siguiente
    lda ruta_ev + 12, x
    and #$01
    rts
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar
    lda #0
    rts
.endproc

; ¿Hay alguien parado en `dest_x`/`dest_y` que le cierre el paso a `movil`?
; Devuelve A distinto de cero si sí.
;
; Es `WouldCollide` de `game_map.cpp` con lo que este repo modela: dos
; personajes chocan si están en la misma capa —la del héroe es CAPA_HEROE— y
; no chocan si alguno de los dos atraviesa paredes. Un evento sin página
; activa no está y no choca. La celda de cada evento es la de `ev_pos_buf`,
; que se mueve al **empezar** el paso: es `IsInPosition` sobre `GetX()`, o sea
; la de destino mientras camina; y la del héroe es `tile_x`/`tile_y`, que
; `begin_step` mueve igual. Lo que no se modela es `overlap_forbidden` —17
; páginas del juego— y el conflicto de un evento con gráfico de tile contra su
; propio bloque. Pisa X e Y.
.proc celda_bloqueada
.a8
.i16
    lda movil_capa
    cmp #$FF
    beq libre_cerca             ; sin página activa no choca con nadie
    lda movil
    cmp #MOVIL_HEROE
    beq es_heroe
    jsr atraviesa_el_evento
    bne libre_cerca
    bra recorrer
es_heroe:
    ; **`atravesando` y no `ruta_atraviesa`**, que es la divergencia declarada
    ; en el README, "Atravesar paredes vale mientras dura la ruta": la bandera
    ; que deja la orden 36 vale mientras el paso lo dé la ruta forzada —ahí
    ; `paso_de_ruta` la copia a `atravesando`— y no para la caminata con el
    ; pad, que la deja en cero. Leyendo la pegajosa, cualquier página que
    ; prendiera el 36 y no lo apagara dejaba al héroe caminando por encima de
    ; **todos** los eventos para el resto de la partida, y las paredes lo
    ; seguían frenando porque `can_leave` y `can_enter` ya miraban
    ; `atravesando`: el mismo héroe atravesaba eventos y no paredes. Lo vio
    ; taro jugando, con los cofres del Sector 30, y el culpable es el
    ; Hover-Tram (mapa 13, EV0028), que prende la 36 y nunca la apaga.
    lda atravesando
    beq recorrer
libre_cerca:
    jmp libre                   ; `libre` queda lejos para un salto corto
recorrer:
    ldx #$0000
    ldy #$0000
otro:
    cpx ev_total
    beq eventos_listos
    rep #$20
.a16
    lda ev_pos_buf, y
    cmp dest_x
    bne siguiente
    lda ev_pos_buf + 2, y
    cmp dest_y
    bne siguiente
    sep #$20
.a8
    txa                         ; el índice cabe en un byte: EV_MAX es 128
    cmp movil
    beq siguiente8              ; consigo mismo no
    sta otro_ev
    phx
    phy
    jsr atraviesa_el_evento
    bne no_choca
    lda otro_ev
    jsr capa_activa
    cmp movil_capa
    bne no_choca
    ply
    plx
    lda #1
    rts
no_choca:
    ply
    plx
siguiente8:
    rep #$20
siguiente:
.a16
    tya
    clc
    adc #EV_STRIDE
    tay
    sep #$20
.a8
    inx
    bra otro
eventos_listos:
    ; Y el héroe, cuando quien se mueve es un evento de su capa.
    lda movil
    cmp #MOVIL_HEROE
    beq libre
    lda movil_capa
    cmp #CAPA_HEROE
    bne libre
    lda ruta_atraviesa
    bne libre
    rep #$20
.a16
    lda tile_x
    cmp dest_x
    bne libre16
    lda tile_y
    cmp dest_y
    bne libre16
    sep #$20
.a8
    lda #1
    rts
libre16:
.a16
    sep #$20
.a8
libre:
    lda #0
    rts
.endproc

; `celda_bloqueada` para el héroe: la celda de destino ya está en dest_x/dest_y.
.proc heroe_bloqueado
.a8
.i16
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    jmp celda_bloqueada
.endproc

; `movil` y `movil_capa` desde la ranura de ruta que apunta X. Conserva X.
.proc preparar_movil
.a8
.i16
    lda ruta_ev + 0, x
    sta movil
    lda ruta_ev + 31, x         ; la capa que la ranura trae desde que se cargó
    sta movil_capa
    rts
.endproc

; ¿Se cumplen las condiciones de la página leída? Vuelve con Z=0 si sí.
; Un switch en 0 quiere decir "esta página no lo pide".
.proc condiciones_ok
.a8
.i16
    rep #$20
.a16
    lda pg_sa
    beq mirar_b
    jsr switch_encendido
    beq falla
mirar_b:
    lda pg_sb
    beq cumple
    jsr switch_encendido
    beq falla
cumple:
    sep #$20
.a8
    ; Y la condición de grupo: un 0 quiere decir "esta página no pide a nadie".
    lda pg_actor
    beq mirar_var
    jsr en_el_grupo
    beq falla8
mirar_var:
    ; Y el ítem y la variable, que se leen de la tabla y no de una copia —la
    ; BSS está llena—: +28 el ítem o 0, y +24 la ranura o $FF por "no pide
    ; ninguna", +25 cómo se compara y +26 contra qué. Es la misma comparación
    ; con signo de
    ; `ConditionalBranch`, `comparar_var`, con los mismos seis códigos: RM2k
    ; usa `CheckOperator` para las dos. Pisa X e Y, como ya lo hacía
    ; `switch_encendido`.
    ldy pag_ofs
    rep #$20
.a16
    tya
    clc
    adc #28
    tay
    lda [pag_ptr], y            ; +28 el ítem que pide, o 0
    beq sin_item
    ; Con el inventario en la RAM lejana: la cuenta del ítem, y con cero no
    ; está. Es `GetItemCount(id) + GetEquippedItemCount(id)` sin equipo.
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq falla8
    rep #$20
.a16
sin_item:
    tya
    sec
    sbc #4
    tay                         ; +24
    sep #$20
.a8
    lda [pag_ptr], y            ; +24 la ranura
    cmp #$FF
    beq cumple8
    pha
    iny
    lda [pag_ptr], y            ; +25 la comparación
    sta temp + 1
    iny
    rep #$20
.a16
    lda [pag_ptr], y            ; +26 contra qué, con signo
    sta temp + 2
    sep #$20
.a8
    pla
    jsr var_leer                ; A = la variable, de dieciséis
.a16
    jsr comparar_var
.a8
    beq falla8
cumple8:
    lda #1                      ; Z=0
    rts
falla8:
    lda #0                      ; Z=1
    rts
sin_usar:
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
falla:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
    lda #0                      ; Z=1
    rts
.endproc

; ¿Está encendido el switch cuyo número viene en A? Vuelve con Z=0 si sí.
.proc switch_encendido
.a16
.i16
    pha
    and #$0007
    tax                         ; el bit dentro del byte
    pla
    lsr a
    lsr a
    lsr a
    tay                         ; y qué byte del bitmap
    sep #$20
.a8
    lda switches, y
    and f:mascara, x
    rep #$20
.a16
    rts                         ; rep no toca Z, así que el and sigue valiendo
.endproc

; La parte de encolar, que comparten los automáticos y la tecla de acción.
; Ningún evento esperando y ninguno automático: al entrar a un mapa las marcas
; del anterior no valen nada, y sus índices de evento apuntarían a otros
; eventos. La llama la carga del mapa **antes** del refresco, que es quien
; vuelve a prender el `FLAG_AUTO` de los que corresponda.
.proc limpiar_esperas
.a8
.i16
    ldx #$0000
:   stz ev_flags, x
    inx
    cpx #EV_MAX
    bne :-
    stz esperando_n
    stz auto_n
    stz refresco_cuadro
    ; Y de quién era la página que corre: si sobrevivió a un teletransporte, su
    ; índice ya no significa nada en el mapa nuevo.
    rep #$20
.a16
    lda #$FFFF
    sta ev_corriendo
    sep #$20
.a8
    rts
.endproc

; Todo evento con una automática activa vuelve a quedar esperando. Es
; `Game_Event::CheckEventAutostart`, que corre una vez por cuadro y para todos.
; Lo llama `eventos_tick` antes del intérprete, y sólo si `auto_n` dice que hay
; alguna.
.proc esperar_automaticas
.a8
.i16
    ldx #$0000
mirar:
    lda ev_flags, x
    and #FLAG_AUTO
    beq siguiente
    jsr marcar_esperando
siguiente:
    inx
    cpx ev_total
    bne mirar
    rts
.endproc

; La página activa que anotó el refresco para el evento X, a `elegida`. Z=1 si
; no hay ninguna anotada y hay que salir a buscarla.
;
; Existe para que arrancar una página no cueste una recorrida de todas las del
; mapa. El refresco ya la resolvió; volver a resolverla acá era hacer dos veces
; el mismo trabajo, y el segundo caía en un cuadro cualquiera.
.proc pagina_desde_eleg
.a8
.i16
    stz elegida_hay
    cpx #EV_MAX
    bcs no
    rep #$20
.a16
    txa
    asl a
    tay
    lda eleg_por_ev, y
    cmp #$FFFD                  ; $FFFD, $FFFE y $FFFF son centinelas
    bcc anotada
    sep #$20
.a8
no:
    lda #0
    rts
.a16
anotada:
    sta pag_ofs
    ; Con X, y no con Y como hasta que `mapa_tabla` se mudó a RODATA: el
    ; direccionamiento absoluto largo indexado del 65816 sólo existe con X. X
    ; trae el evento y el llamador cuenta con él, así que va y vuelve por la
    ; pila; el `plx` deja N y Z del valor que saca, y por eso lo que sigue es
    ; un `jsr` y no una rama.
    phx
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    plx
    jsr leer_pagina
    lda pg_trigger
    sta elegida_trigger
    rep #$20
.a16
    lda pg_cod
    sta elegida
    sep #$20
.a8
    lda pg_cod + 2
    sta elegida + 2
    lda #1
    sta elegida_hay
    rts
.endproc

; Arranca la página del primer evento que esté esperando. Devuelve 0 si no
; arrancó ninguna. El orden es por número de evento, que es el mismo en que
; `Game_Map::Update` recorre `events`.
;
; La página se resuelve **acá**, no cuando se marcó el evento: entre una cosa y
; la otra puede haber pasado un refresco y ser otra la activa.
.proc arrancar_esperando
.a8
.i16
    ldx #$0000
buscar:
    lda ev_flags, x
    and #FLAG_ESPERA
    bne encontrado
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
encontrado:
    ; Se desmarca antes de saber si hay con qué correr, igual que el
    ; `ClearWaitingForegroundExecution` de `Game_Map::Update`, que corre
    ; siempre. Si la página no compiló, el evento pierde el turno; y si es
    ; automática, el barrido del cuadro que viene lo vuelve a marcar.
    lda ev_flags, x
    and #(FLAG_AUTO)            ; deja sólo el de automática
    sta ev_flags, x
    dec esperando_n
    phx
    jsr pagina_desde_eleg
    bne con_pagina
    rep #$20
.a16
    txa
    sta ev_buscado
    sep #$20
.a8
    jsr buscar_pagina_de_evento
con_pagina:
    plx
    lda elegida_hay
    beq buscar_mas
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq buscar_mas              ; la página activa no se pudo compilar
    rep #$20
.a16
    lda elegida
    sta cod_ptr
    stz ev_cur
    sep #$20
.a8
    lda elegida + 2
    sta cod_ptr + 2
    rep #$20
.a16
    txa
    sta ev_corriendo            ; para poder remarcarlo cuando termine
    sep #$20
.a8
    lda #1
    sta ev_activo
    rts
buscar_mas:
    inx
    cpx ev_total
    bne buscar
    lda #0
    rts
.endproc

; Lo contrario de `marcar_esperando`, con la misma cuenta.
.proc desmarcar_esperando
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_ESPERA
    beq no                      ; no estaba: no se descuenta de nuevo
    lda ev_flags, x
    and #(FLAG_AUTO)            ; deja sólo el de automática
    sta ev_flags, x
    dec esperando_n
no:
    rts
.endproc

; Marca al evento X como que tiene una página esperando turno. Es
; `Game_Event::ScheduleForegroundExecution`: un bit por evento, no una cola.
; Marcarlo dos veces no lo encola dos veces, que es lo que hacía falta para que
; el barrido de cada cuadro pueda remarcar sin miedo.
.proc marcar_esperando
.a8
.i16
    cpx #EV_MAX
    bcs no
    lda ev_flags, x
    and #FLAG_ESPERA
    bne no                      ; ya estaba: no se cuenta de nuevo
    lda ev_flags, x
    ora #FLAG_ESPERA
    sta ev_flags, x
    inc esperando_n
no:
    rts
.endproc

; El bucle del intérprete: un opcode por vuelta hasta el FIN.
;
; Y es el cursor del bytecode y tiene que sobrevivir a todo el bucle, así que
; cada `jsr` que sale de acá lo guarda antes de irse. Las rutinas que se llaman
; usan X e Y para lo suyo —poner_switch indexa el bitmap de switches,
; aplicar_tinte recorre tres paletas— y ninguna tiene por qué saber que acá
; significan otra cosa. Sin esto, el primer OP_SWITCH dejaba a Y valiendo el
; número del switch dividido ocho, y lo que se leía como opcode siguiente era
; un byte cualquiera del medio de la página: el bucle cortaba ahí y el resto no
; corría.
.proc correr_codigo
.a8
.i16
    ldy ev_cur                  ; donde quedó el cuadro anterior
otro:
    lda [cod_ptr], y
    iny
    ; Cada opcode se despacha con `bne` al salteo y `jmp` al cuerpo, y no con un
    ; `beq` derecho al cuerpo, que es lo que había. La diferencia es el alcance:
    ; un `beq` llega a 127 bytes y el cuerpo del último opcode está detrás de
    ; todos los demás, así que el límite lo marca la suma de los otros seis.
    ;
    ; Eso ya cortó dos veces. La primera, al aparecer OP_MESSAGE, dejó a
    ; OP_TELEPORT a 140 bytes; se arregló ordenando las comparaciones como los
    ; cuerpos. La segunda fue darle su operando a OP_MESSAGE: 129 bytes, o sea
    ; que aquel arreglo duraba exactamente un opcode. Y faltan cuatro —MoveEvent
    ; sobre otro evento, FlashSprite, PlaySound y ControlVars, en ese orden y
    ; medidos con `just snes-destraba`—, así que el límite se saca del medio de
    ; una vez: un `jmp` llega a cualquier parte del banco.
    ;
    ; Sale tres bytes y cuatro ciclos por opcode que no matchea, en un despacho
    ; que corre unas pocas veces por cuadro. El orden ya no significa nada.
    cmp #OP_MESSAGE
    bne :+
    jmp op_message
:   cmp #OP_SWITCH
    bne :+
    jmp op_switch
:   cmp #OP_ROUTE
    bne :+
    jmp op_route
:   cmp #OP_PARTY
    bne :+
    jmp op_party
:   cmp #OP_DELAY
    bne :+
    jmp op_delay
:   cmp #OP_TINT
    bne :+
    jmp op_tint
:   cmp #OP_FLASH
    bne :+
    jmp op_flash
:   cmp #OP_WAIT_ROUTES
    bne :+
    jmp op_wait_routes
:   cmp #OP_BGM
    bne :+
    jmp op_bgm
:   cmp #OP_PLACE
    bne :+
    jmp op_place
:   cmp #OP_PLACE_VAR
    bne :+
    jmp op_place_var
:   cmp #OP_SWAP
    bne :+
    jmp op_swap
:   cmp #OP_SHAKE
    bne :+
    jmp op_shake
:   cmp #OP_FLASH_SCREEN
    bne :+
    jmp op_flash_screen
:   cmp #OP_FADE_BGM
    bne :+
    jmp op_fade_bgm
:   cmp #OP_PAN
    bne :+
    jmp op_pan
:   cmp #OP_TIMER
    bne :+
    jmp op_timer
:   cmp #OP_IF
    bne :+
    jmp op_if
:   cmp #OP_GOTO
    bne :+
    jmp op_goto
:   cmp #OP_CHOICE
    bne :+
    jmp op_choice
:   cmp #OP_GOLD
    bne :+
    jmp op_gold
:   cmp #OP_ITEM
    bne :+
    jmp op_item
:   cmp #OP_ACCESS
    bne :+
    jmp op_access
:   cmp #OP_ACTOR_SPRITE
    bne :+
    jmp op_actor_sprite
:   cmp #OP_KEY
    bne :+
    jmp op_key
:   cmp #OP_SHOP
    bne :+
    jmp op_shop
:   cmp #OP_BATTLE
    bne :+
    jmp op_battle
:   cmp #OP_WEATHER
    bne :+
    jmp op_weather
:   cmp #OP_ANIMATION
    bne :+
    jmp op_animation
:   cmp #OP_SOUND
    bne :+
    jmp op_sound
:   cmp #OP_PICTURE
    bne :+
    jmp op_picture
:   cmp #OP_PICTURE_MOVE
    bne :+
    jmp op_picture_move
:   cmp #OP_PICTURE_ERASE
    bne :+
    jmp op_picture_erase
:   cmp #OP_SAVE
    bne :+
    jmp op_save
:   cmp #OP_TELEPORT
    bne :+
    jmp op_teleport
:   cmp #OP_VAR
    bne :+
    jmp op_var
:   cmp #OP_IF_VAR
    bne :+
    jmp op_if_var
:   cmp #OP_IF_ACTOR
    bne :+
    jmp op_if_actor
:   cmp #OP_STOP_ROUTES
    bne :+
    jmp op_stop_routes
:   stz ev_activo               ; OP_DONE, o algo que no conocemos: se corta
    rts

; Abre la ventana de mensaje y corta el cuadro. El cursor ya quedó en el
; comando siguiente —el `iny` del lazo— pero `eventos_tick` no vuelve a llamar
; acá hasta que el jugador apriete A.
;
; El operando es el desplazamiento del cuadro de texto dentro del bloque
; `mensajes`, de 16 bits. No es el texto: emitir cada cuadro ya compuesto son
; 240 tiles de 4bpp, o sea 7,5 KB, y los 2895 del juego serían 21 MB. Lo que
; viaja en el cartucho es un byte por letra y lo compone el 65816, que es la
; salida de FF6.
op_message:
    ; El mensaje no aparece en este cuadro: hay que componerle el texto, y eso
    ; lleva unos cuantos. La ventana se prende sola cuando el compositor
    ; termina; mientras tanto la página ya está bloqueada.
    stz msg_abierto
    stz eleg_activo
    rep #$20
.a16
    lda [cod_ptr], y            ; el desplazamiento, que va en A a msg_empezar
    iny
    iny
    phy
    jsr msg_empezar
    ply
    sep #$20
.a8
    sty ev_cur
    rts

; `ConditionalBranch` con condición de switch. Los operandos son el número (dos
; bytes), la polaridad —copiada tal cual de RM2k, donde 0 quiere decir "tiene
; que estar prendido"— y el destino: **el índice absoluto dentro de la página**
; al que va el cursor si la condición no se cumple, o sea el `else` o el `end`
; que le corresponde. Quién es ese destino lo resolvió el conversor, que es el
; único que ve la página entera; acá saltar es asignar Y.
op_if:
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
    jsr en_el_grupo             ; Z=0 si está
    ply
    cmp #0                      ; la Z de `en_el_grupo`, que `ply` acaba de
                                ; pisar con el cursor: ver `tema_asegurar`
    beq si_actor_no
    lda #$01
    bra si_actor_listo
si_actor_no:
    lda #$00
si_actor_listo:
    iny
    iny                         ; Y -> la polaridad, que vale cero
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
    jmp otro
si_no_cumple:
    iny                         ; Y -> el destino
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp otro

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
op_if_actor:
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
    ; `Game_Actor::IsSkillLearned`: la lista de `sabe_hab` que arranca en
    ; `sabe_hab_ini[actor]` y dura `sabe_hab_n[actor]`. **No es `actor_hab`**,
    ; que es la lista del menú de la pelea: ésa lleva sólo las que este port
    ; sabe ejecutar y sólo de los actores que pueden entrar al grupo, y esta
    ; pregunta no filtra ninguna de las dos cosas. Ver `sabe_hab` en el
    ; conversor y `batalla.aprendidas_de`.
sia_habilidad:
    rep #$20
.a16
    lda temp + 1
    and #$00FF
    tax                         ; el actor
    sep #$20
.a8
    lda f:sabe_hab_n, x
    beq sia_no                  ; no sabe ninguna
    sta temp                    ; cuántas quedan por mirar
    lda f:sabe_hab_ini, x
    rep #$20
.a16
    and #$00FF
    asl a                       ; la tabla es de palabras
    tax
    sep #$20
.a8
sia_hab_otra:
    rep #$20
.a16
    lda f:sabe_hab, x
    cmp temp + 2
    sep #$20
.a8
    beq sia_si
    inx
    inx
    dec temp
    bne sia_hab_otra
sia_no:
    rep #$20
.a16
    lda [cod_ptr], y            ; el destino, absoluto adentro de la página
    tay
    sep #$20
.a8
    jmp otro
sia_si:
    iny
    iny                         ; Y -> el opcode siguiente
    jmp otro

; `ChangeGold`: suma o resta y recorta a [0, ORO_MAX], que es lo que hace
; `Game_Party::GainGold`. El monto va en tres bytes porque el tope de RM2k son
; 999999 y este juego usa el valor entero.
;
; No hay dónde mostrarlo —el menú no existe— pero sí quién lo pregunta: la rama
; de oro de `ConditionalBranch`.
op_gold:
    lda [cod_ptr], y            ; el signo: 0 suma, 1 resta
    sta temp
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; los 16 bits bajos del monto
    sta temp + 2
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y el byte alto
    sta temp + 1                ; el byte alto del monto
    iny
    phy

    lda temp
    bne oro_resta
    ; Sumar: 24 bits, y si se pasa de ORO_MAX queda en ORO_MAX.
    rep #$20
.a16
    lda oro
    clc
    adc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    adc temp + 1
    sta oro + 2
    bra oro_recorta
oro_resta:
    rep #$20
.a16
    lda oro
    sec
    sbc temp + 2
    sta oro
    sep #$20
.a8
    lda oro + 2
    sbc temp + 1
    sta oro + 2
    bcs oro_recorta
    ; Se fue abajo de cero: queda en cero.
    rep #$20
.a16
    stz oro
    sep #$20
.a8
    stz oro + 2
    bra oro_listo
oro_recorta:
    ; ¿Se pasó de ORO_MAX? Se compara de 24 bits, el byte alto primero.
    lda oro + 2
    cmp #^ORO_MAX
    bcc oro_listo
    bne oro_tope
    rep #$20
.a16
    lda oro
    cmp #.loword(ORO_MAX)
    sep #$20
.a8
    bcc oro_listo
    beq oro_listo
oro_tope:
    rep #$20
.a16
    lda #.loword(ORO_MAX)
    sta oro
    sep #$20
.a8
    lda #^ORO_MAX
    sta oro + 2
oro_listo:
    ply
    jmp otro

; `ChangeItems`: el ítem de dieciséis bits y cuánto se suma, con signo. Es
; `Game_Party::AddItem`: la cuenta queda en [0, ITEM_MAX]. Y como cambiar
; un ítem puede cambiar qué página está activa, pide el refresco: RM2k hace
; `SetNeedRefresh(true)` tras cada ChangeItems.
op_item:
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el ítem
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sta temp + 2                ; el puerto avanza al leer y no se puede leer
    iny                         ; de vuelta: se guarda la dirección
    iny
    sep #$20
.a8
    stz WMADDH
    lda [cod_ptr], y            ; cuánto, con signo
    iny
    sta temp
    lda WMDATA                  ; la cuenta que había
    clc
    adc temp
    bit temp
    bmi item_resto
    ; Sumó: si se pasó de ITEM_MAX —o dio la vuelta— queda en el tope.
    bcs item_tope
    cmp #(ITEM_MAX + 1)
    bcc item_guardar
item_tope:
    lda #ITEM_MAX
    bra item_guardar
item_resto:
    ; Restó: sin acarreo se fue abajo de cero, y queda en cero.
    bcs item_guardar
    lda #0
item_guardar:
    pha
    rep #$20
.a16
    lda temp + 2                ; el puerto avanzó al leer: se vuelve
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    lda #1
    sta refresco
    jmp otro

; `OpenShop`: tipo, juego, cuántos y la lista, de a dos bytes cada ítem. La
; tienda se abre acá adentro y, al salir, el mapa vuelve y la página sigue.
op_shop:
.a8
.i16
    lda [cod_ptr], y
    sta comp_col + 1
    iny
    lda [cod_ptr], y
    sta comp_fase
    iny
    lda [cod_ptr], y
    iny
    sta eleg_cancel             ; cuántos vienen
    stz comp_mask + 1
    ; `item_k` vive en el banco del código y el intérprete corre con el banco
    ; de datos donde está el bytecode: se cambia hasta volver.
    phb
    phk
    plb
op_shop_other:
    lda eleg_cancel
    beq op_shop_done
    rep #$20
.a16
    lda [cod_ptr], y            ; el ítem
    iny
    iny
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq op_shop_next         ; uno que esta ROM no conoce
    pha
    rep #$20
.a16
    lda comp_mask + 1
    and #$00FF
    clc
    adc #FAR_TIENDA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_mask + 1
op_shop_next:
    dec eleg_cancel
    bra op_shop_other
op_shop_done:
    phy
    jsr tienda_pantalla
    ; Los flancos que cerraron la tienda son de ella, como en el menú.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    jsr volver_al_mapa
    ply
    plb
    jmp otro

; `EnemyEncounter`: la tropa y los tres destinos, todos de dieciséis bits. La
; pelea se juega acá adentro y, al salir, el mapa vuelve —como en la tienda— y
; la página sigue por el destino que le tocó al resultado.
op_battle:
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; la tropa, como número de RM2k
    sta f:BAT_LARGO + BA_TROPA
    sep #$20
.a8
    phy                         ; el cursor: los destinos se leen al volver
    jsr pelea_arrancar
    ply
    ; Y apunta a la tropa; los tres destinos vienen detrás, de a palabra, en el
    ; orden victoria, huida, derrota, que es el de `BATALLA_HANDLERS`.
    lda f:BAT_LARGO + BA_RESULT
    jmp op_battle_destination

op_battle_destination:
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sty temp
    clc
    adc temp
    inc a
    inc a
    tay
    lda [cod_ptr], y            ; el destino, absoluto dentro de la página
    tay
    ; `BATALLA_PERDER`, o sea $FFFF: la pelea no traía manejador de derrota
    ; porque en RM2k perderla es `Scene_Gameover`. Es un destino imposible —los
    ; tres son absolutos adentro de la página y ninguna llega a 64 KB— así que
    ; no hace falta un opcode nuevo ni un byte más en las otras peleas. El `iny`
    ; es el `cmp #$FFFF` barato: con A de 16 bits compararlo costaría tres
    ; bytes y en el banco 0 no sobran.
    ;
    ; **Game Over es volver al arranque**, que es la pantalla de título si esta
    ; ROM la lleva, con la partida guardada esperando en la SRAM: es lo que
    ; `Scene_Gameover` hace cuando el jugador aprieta, menos la imagen, que este
    ; port no dibuja —ver assets/LIMITACIONES.md—. Se va con `jml` y no
    ; devolviendo el control porque no hay a dónde volver: la página no tiene
    ; rama de derrota y `reset` repone la pila él mismo.
    iny
    bne sigue_la_pagina
    jml f:reset
sigue_la_pagina:
    dey
    sep #$20
.a8
    jmp otro


; `OP_SOUND`: el índice en `sonido_tabla`. Queda pendiente y arranca al
; final de `music_tick`, detrás de lo que la música escriba en el cuadro.
op_sound:
    jsr sonido_de_codigo
    jmp otro

; Los tres del cartel. `OP_PICTURE` lo pone ya con su tono —`Game_Pictures::
; Show` deja `time_left` en cero—, `OP_PICTURE_MOVE` arranca la rampa hacia
; otro tono y `OP_PICTURE_ERASE` lo saca. Ninguno corta el cuadro: si la página
; espera lo que dura el fundido, el conversor le pone un OP_DELAY detrás,
; igual que al `FlashScreen` y a la sacudida.
op_picture:
    ldx #$0000
img_poner:
    lda [cod_ptr], y
    cpx #3
    bcs img_poner_sat           ; el cuarto operando es la saturación, que no
    sta f:CARTEL_TONO, x        ; se guarda: la del cartel es siempre la neutra
    sta f:CARTEL_DESDE, x
    sta f:CARTEL_HASTA, x
img_poner_sat:
    iny
    inx
    cpx #4
    bne img_poner
    lda #1
    sta f:CARTEL_ACTIVA
    lda #0
    sta f:CARTEL_PASO
    sta f:CARTEL_PASOS
    jsr imagen_paleta
    jmp otro

op_picture_move:
    ldx #$0000
img_mover:
    lda [cod_ptr], y
    cpx #3
    bcs img_mover_sat           ; la saturación, otra vez
    sta f:CARTEL_HASTA, x
img_mover_sat:
    iny
    inx
    cpx #4
    bne img_mover
    lda [cod_ptr], y
    sta f:CARTEL_PASOS
    iny
    ; Un `Move` sobre una imagen que no se mostró le escribe el destino a algo
    ; que no se dibuja: los operandos se consumen igual —el stream tiene que
    ; seguir en el mismo byte de los dos lados— y no pasa nada más.
    lda f:CARTEL_ACTIVA
    beq img_mover_fin
    lda f:CARTEL_PASOS
    bne img_mover_rampa
    ldx #$0000
img_mover_ya:
    lda f:CARTEL_HASTA, x
    sta f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_ya
    lda #0
    sta f:CARTEL_PASO
    jsr imagen_paleta
    jmp otro
img_mover_rampa:
    ldx #$0000
img_mover_desde:
    lda f:CARTEL_TONO, x
    sta f:CARTEL_DESDE, x
    inx
    cpx #3
    bne img_mover_desde
    lda #0
    sta f:CARTEL_PASO
img_mover_fin:
    jmp otro

op_picture_erase:
    lda #0
    sta f:CARTEL_ACTIVA
    jmp otro

; `OP_ANIMATION`: el número de animación de RM2k, sobre qué se dibuja, cuántas
; entradas y las entradas, que se quedan en el bytecode. Ver OP_ANIMATION en
; eventos.py y `animacion_tick`. La nueva reemplaza a la que hubiera, y no
; cuesta ningún tick.
;
; Los dos primeros bytes son del **dibujo**, que va por su cuenta y dura más
; que la línea de tiempo: ver `animacion_dibujo_empezar`.
op_animation:
    lda [cod_ptr], y            ; el número de animación de RM2k
    sta temp
    iny
    lda [cod_ptr], y            ; y sobre qué va: $FF es la pantalla
    sta temp + 1
    iny
    phy
    jsr animacion_dibujo_empezar
    ply
    lda [cod_ptr], y            ; cuántas
    sta f:ANIM_N
    iny
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta f:ANIM_PTR              ; la primera, en el banco del bytecode
    sep #$20
.a8
    lda cod_ptr + 2
    sta f:ANIM_PTR + 2
    lda #0
    sta f:ANIM_T
    lda f:ANIM_N
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; ocho bytes por entrada
    sta temp
    tya
    clc
    adc temp
    tay
    sep #$20
.a8
    jmp otro

; `WeatherEffects`: el tipo y la fuerza. No cuesta ningún tick.
op_weather:
.a8
.i16
    lda [cod_ptr], y
    sta temp
    iny
    lda [cod_ptr], y
    sta temp + 1
    iny
    phy
    jsr clima_poner
    ply
    jmp otro

; `ChangeSaveAccess`, `ChangeMainMenuAccess` y `ChangeEscapeAccess`: **el bit**
; del permiso y si queda permitido. Prende o apaga ese bit de "prohibido" de
; `FAR_ACCESO`.
;
; El bit lo pone el conversor y acá no se calcula, y eso es lo que deja agregar
; permisos sin tocar este opcode: antes el operando era el número del permiso y
; el bit salía de un `inc a`, que da $01 y $02 para los dos primeros y **$03
; para el tercero**, o sea prohibir las otras dos cosas de una.
op_access:
.a8
.i16
    lda [cod_ptr], y            ; el bit: $01 guardar, $02 el menú, $04 escapar
    sta temp
    iny
    lda [cod_ptr], y            ; permitido
    iny
    sta temp + 1
    phy
    ; El permiso se mira con A de ocho bits y no con Y: con los índices en
    ; dieciséis, `ldy temp + 1` se llevaba también `temp + 2`, y un permiso
    ; en cero con basura al lado quedaba permitido.
    jsr acceso_leer
    xba                         ; B = los permisos, mientras se mira
    lda temp + 1
    beq acceso_prohibir
    lda temp
    eor #$FF
    sta temp
    xba
    and temp
    bra acceso_listo
acceso_prohibir:
    xba
    ora temp
acceso_listo:
    jsr acceso_escribir
    ply
    jmp otro

; El salto sin condición que el conversor pone donde estaba el `else`, para que
; la rama de arriba se saltee la de abajo.
op_goto:
    rep #$20
.a16
    lda [cod_ptr], y
    tay
    sep #$20
.a8
    jmp otro

; `ShowChoice`: abre la ventana con las opciones y corta el cuadro, igual que
; un mensaje. La diferencia es que la página **no retoma donde quedó**: cuando
; el jugador elige, `eleccion_tick` le pone al cursor el destino de la opción
; marcada. Por eso acá no se guarda `ev_cur`: lo que se guarda es dónde está la
; tabla, que es de donde salen los dos, el cuadro que se dibuja y el destino.
op_choice:
    lda [cod_ptr], y            ; cuántas opciones
    sta eleg_n
    iny
    lda [cod_ptr], y            ; qué opción elige cancelar, más uno
    sta eleg_cancel
    iny
    sty eleg_tabla
    stz eleg_sel                ; `Window_Selectable` arranca con el índice en
                                ; cero, y la primera opción es la marcada
    lda #1
    sta eleg_activo
    jsr eleg_abrir
    rts


op_switch:
    rep #$20
.a16
    lda [cod_ptr], y            ; el número, de 16 bits
    sta temp
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y si va encendido o apagado
    iny
    phy
    jsr poner_switch
    ply
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

; Una ruta forzada de MoveEvent. El primer operando dice sobre quién: 0 es el
; héroe, y cualquier otro número es el índice del evento en la tabla del mapa
; más uno. **No es el id de RM2k**: 39 mapas de este juego tienen huecos en la
; numeración de eventos, y traducir es cosa del conversor.
;
; De todos los comandos de ruta de RM2k acá se aceptan los cuatro de girar, los
; cuatro de mover y la espera: el conversor no emite ningún otro.
;
; face_up/right/down/left son 12, 13, 14 y 15, y nuestras direcciones son
; 0, 1, 2 y 3 en el mismo orden, así que restar doce alcanza.
;
; Los dos caminos se parecen pero no son el mismo, y la diferencia vale la pena:
; la del héroe se **copia** a RAM, y la de un evento se guarda como puntero al
; bytecode. Copiarla existe desde antes y tiene un tope, RUTA_MAX; el puntero no
; lo tiene, porque el código del mapa vive en la ROM y no se va a ningún lado.
op_route:
    lda [cod_ptr], y            ; sobre quién
    sta ruta_blanco
    iny
    lda [cod_ptr], y            ; con qué frecuencia
    sta ruta_frec_op
    iny
    lda [cod_ptr], y            ; cuántos comandos trae
    sta ruta_cuantas
    stz ruta_cuantas + 1
    iny
    lda ruta_blanco
    bne op_route_event

    ; --- el héroe: la ruta se copia a RAM y la camina `move_hero`, no el
    ; intérprete: en RM2k `ForceMoveRoute` es asincrónico y la página sigue.
    ; Lo que se corta es la espera —`SetStopCount(0xFFFF)`: la primera orden
    ; corre ya— y nada más: el paso o el salto en curso se terminan, como
    ; allá. Acá se cortaba también el salto, y la referencia no.
    lda ruta_cuantas
    sta temp
    stz ruta_i
    stz ruta_espera
    lda ruta_frec_op
    sta ruta_frec
    ldx #$0000
copiar_orden:
    lda temp
    beq fin_copia
    dec temp
    cpx #RUTA_MAX
    bcs saltear                 ; no entra: se consume pero no se guarda
    lda [cod_ptr], y
    sta ruta, x
    inx
saltear:
    iny
    bra copiar_orden
fin_copia:
    txa                         ; X no pasa de RUTA_MAX, así que el byte alcanza
    sta ruta_n
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

    ; --- un evento: no se copia nada. Se anota dónde empieza la ruta dentro del
    ; bytecode y en qué orden va, y el cursor de la página saltea las órdenes.
op_route_event:
    phy
    jsr ruta_para_evento
    ply
    rep #$20
.a16
    tya
    clc
    adc ruta_cuantas
    tay
    sep #$20
.a8
    jmp otro

; Planta a un evento en una celda: ChangeEventLocation. Es `MoveTo`, y nada
; más que `MoveTo`: la celda cambia ya y el paso o el salto en curso se cortan
; —`SetRemainingStep(0)`—, la ruta que tuviera sigue con la orden siguiente
; desde acá, y hacia dónde mira no cambia; la dirección la toca sólo RM2k3. La
; cinemática de apertura lo usa seis veces para traer a Core, a Manta y al
; droide a escena.
op_place:
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda [cod_ptr], y
    sta ev_pos_buf + 0, x       ; la celda, que es lo que miran las rutas, la
    iny                         ; tecla de acción y el contacto
    iny
    lda [cod_ptr], y
    sta ev_pos_buf + 2, x
    iny
    iny
    sep #$20
.a8
    phy
lugar_plantar:                  ; con Y ya en la pila: ver `op_place_var`
    jsr plantar_evento
    ply
    jmp otro

; `ChangeEventLocation` con la celda en **dos variables**, que es la otra rama
; de `CommandChangeEventLocation`. Lo demás es idéntico a `op_place`: el mismo
; `MoveTo`, o sea la celda cambia ya, el paso en curso se corta y ni la ruta ni
; hacia dónde mira se tocan. Ver OP_PLACE_VAR en eventos.py.
;
; Las dos lecturas van **antes** de escribir ninguna de las dos palabras, como
; en `op_swap`: una variable que se leyera después de haber movido al evento
; ya podría valer otra cosa si es una de las de coordenadas de `ControlVars`.
; En este juego no pasa —el minijuego del mapa 11 las calcula antes— pero es la
; misma regla y no cuesta nada.
;
; `var_leer` no toca X ni `temp`, así que el desplazamiento de la fila se
; calcula una sola vez y sobrevive a las dos lecturas.
op_place_var:
.a8
.i16
    lda [cod_ptr], y            ; el blanco: el índice del evento más uno
    dec a
    sta temp
    iny
    lda [cod_ptr], y            ; la ranura de la x
    sta temp + 1
    iny
    lda [cod_ptr], y            ; y la de la y
    sta temp + 2
    iny
    phy
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    lda temp + 1
    jsr var_leer                ; vuelve con M en dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 2
    jsr var_leer
.a16
    sta ev_pos_buf + 2, x
    pla
    sta ev_pos_buf + 0, x
    sep #$20
.a8
    bra lugar_plantar

; `TradeEventLocations`: los dos eventos se cambian de celda, y cada uno es un
; `MoveTo` como el de `op_place` —la celda, el corte del paso, y el dibujo que
; la sigue—. Las dos celdas se leen antes de escribir ninguna.
op_swap:
    lda [cod_ptr], y            ; el primero: el índice más uno
    dec a
    sta trueque_a
    iny
    lda [cod_ptr], y            ; y el segundo
    dec a
    sta trueque_b
    iny
    phy
    rep #$20
.a16
    lda trueque_a
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    lda trueque_b
    and #$00FF
    asl a
    asl a
    tay
    lda ev_pos_buf + 0, x
    sta celda_x
    lda ev_pos_buf + 2, x
    sta celda_y
    lda ev_pos_buf + 0, y
    sta ev_pos_buf + 0, x
    lda ev_pos_buf + 2, y
    sta ev_pos_buf + 2, x
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    lda trueque_a
    sta temp
    jsr plantar_evento
    lda trueque_b
    sta temp
    jsr plantar_evento
    ply
    jmp otro

; `ShakeScreen`: `ShakeOnce`, que no reinicia la posición para que dos
; sacudidas seguidas se encadenen suaves, o `ShakeEnd` con cero cuadros. No
; corta el cuadro: si la página espera, el conversor le pone un OP_DELAY
; detrás, como con los destellos.
op_shake:
    lda [cod_ptr], y            ; fuerza
    sta sacudida_fuerza
    iny
    lda [cod_ptr], y            ; velocidad
    sta sacudida_vel
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; cuadros
    sta sacudida_resta
    bne con_cuadros
    stz sacudida_pos            ; ShakeEnd: la pantalla vuelve a su lugar
con_cuadros:
    iny
    iny
    sep #$20
.a8
    jmp otro

; `FlashOnce`: el color, el nivel a escala 256 y los cuadros. No corta el
; cuadro: si la página espera, el conversor le pone un OP_DELAY detrás.
op_flash_screen:
    jsr destello_de_codigo
    jmp otro

; Arranca un destello sobre un personaje. No corta el cuadro: si la página
; espera, el conversor le pone un OP_DELAY detrás, que es exactamente lo que
; hace `CommandFlashSprite` con `SetupWait(tenths)`.
op_flash:
    phy
    jsr flash_empezar
    ply
    rep #$20
.a16
    tya
    clc
    adc #6                      ; los seis operandos
    tay
    sep #$20
.a8
    jmp otro

; El cronómetro: poner, arrancar o parar. Los cinco bytes de operando son fijos
; aunque cada operación use dos, así que el cursor avanza igual en las tres.
op_timer:
    lda [cod_ptr], y            ; la operación
    sta temp
    iny
    cmp #TIMER_PONER
    bne no_pone
    rep #$20
.a16
    lda [cod_ptr], y            ; los segundos, de dieciséis bits
timer_poner_16:
    sta timer_seg
    sep #$20
.a8
    ; `Game_Party::SetTimer` guarda `segundos * 60 + 59`: los 59 de más son lo
    ; que hace que el valor pedido se vea un segundo entero y no un cuadro.
    ; Acá los cuadros van partidos, así que son el resto y nada más.
    lda #TIMER_DE_MAS
    sta timer_sub
    jsr timer_digitos
    bra timer_fin
no_pone:
    cmp #TIMER_PONER_VAR
    bne no_pone_var
    ; Los segundos desde una variable, que es lo que hace el Tram Officer del
    ; mapa 9: "lo que le queda al cronómetro, menos sesenta". Una variable
    ; negativa pone cero, como `Game_Party::SetTimer`.
    lda [cod_ptr], y            ; la ranura
    phy
    jsr var_leer                ; A de dieciséis bits
.a16
    ply
    cmp #0                      ; el signo de la variable, que `ply` pisó con
                                ; el cursor: ver `tema_asegurar`
    bpl timer_poner_16
    lda #0
    bra timer_poner_16
.a8
no_pone_var:
    cmp #TIMER_ARRANCAR
    bne timer_para
    lda #1
    sta timer_activo
    iny
    iny
    lda [cod_ptr], y            ; si se ve
    sta timer_visible
    dey
    dey
    bra timer_fin
timer_para:
    ; `StopTimer` apaga las dos cosas, no sólo la cuenta.
    stz timer_activo
    stz timer_visible
timer_fin:
    rep #$20
.a16
    tya
    clc
    adc #3                      ; los tres operandos que quedan: el primero ya
    tay                         ; lo consumió el `iny` de la operación
    sep #$20
.a8
    jmp otro

; `PlayBGM`. El operando es el índice del tema en `Temas`, y el cartucho lleva
; los que hayan entrado en la ARAM: los primeros `TEMA_TOTAL`. Un índice más
; alto es un tema que no entró y no suena, que es lo que pasaba con todos menos
; uno hasta el 2026-09-06. Ver `temas_de_la_rom` en el conversor.
op_bgm:
    lda [cod_ptr], y
    iny
    cmp #TEMA_TOTAL
    bcs otro_tema
    phy
    jsr music_start
    ply
otro_tema:
    jmp otro

; `FadeOutBGM`. El operando es cuánto baja el volumen por cuadro; lo baja
; `bgm_fundido_tick`, no acá, y la página sigue de largo en este mismo cuadro,
; que es lo que hace `CommandFadeOutBGM` devolviendo true.
;
; Con el tema apagado no se arranca nada: el fundido escribiría el volumen de un
; tema que no suena, y encima lo dejaría en cero para el `PlayBGM` que venga.
;
; Con una pista del MSU-1 sonando, en cambio, sí hay qué fundir: `music_apagada`
; vale 1 —el SPC700 está callado a propósito— y el que baja es el volumen del
; MSU-1. Sin esta salida, un `FadeOutBGM` no hacía nada y la pista seguía
; sonando para siempre.
op_fade_bgm:
    lda f:MSU_SUENA
    bne fundir
    lda music_apagada
    bne fundir_nada
fundir:
    php
    sei                         ; lo lee `irq_musica`: todo junto o nada
    lda [cod_ptr], y
    sta bgm_paso
    iny
    lda [cod_ptr], y
    sta bgm_paso + 1
    iny
    lda #$FF
    sta bgm_nivel               ; el volumen entero, que es de donde baja
    sta bgm_nivel + 1
    lda #1
    sta bgm_fundido
    plp
    jmp otro
fundir_nada:
    iny
    iny
    jmp otro

; `OpenSaveMenu`: la pantalla de ranuras en modo guardar, y la partida a la
; que el jugador elija. Sin operandos. La referencia hace lo mismo con el mismo
; opcode: ver `OP_SAVE` en tools/port/eventos.py.
;
; **Bloquea adentro del intérprete y no cuesta ningún tick**, que es lo que hace
; RM2k: `OpenSaveMenu` apila `Scene_Save`, el mapa deja de actualizarse hasta
; que se cierra, y la página sigue por el comando siguiente. Acá
; `ranuras_pantalla` corre su propio lazo de cuadros —como desde el título— y
; `vueltas` no avanza mientras se ve, así que los dos intérpretes siguen en el
; mismo tick cuando vuelve. Cancelar con B vuelve al mapa sin guardar, que es
; también lo de RM2k; elegir guarda y vuelve, sin preguntar si la ranura estaba
; ocupada, porque `Scene_Save::Action` tampoco pregunta.
;
; La pantalla pisó la VRAM de los tiles y la paleta 0, y `volver_al_mapa` los
; repone. El estado del juego no se toca: la tabla de eventos, las rutas, la
; OAM y las poses en VRAM siguen como estaban, y por eso no se llama a
; `cargar_mapa`, que reiniciaría todo eso.
;
; Hasta el 2026-09-10 esto guardaba en la ranura cargada —o en la primera— sin
; mostrar nada, y el intento de abrir la pantalla dio "negro con basura": la
; ROM de prueba no llevaba título, y sin título el conversor emitía la pantalla
; de ranuras como un byte de relleno con `RANURA_TILES` en cero. Hoy va en toda
; ROM.
op_save:
    phy
    lda #1                      ; modo guardar
    jsr ranuras_pantalla
    cmp #$FF
    beq cancelado
    jsr poner_ranura
    jsr guardar_partida
cancelado:
    jsr volver_al_mapa
    ply
    jmp otro

; "Esperá a que terminen las rutas". Si no queda ninguna corriendo no cuesta ni
; un cuadro, que es lo que hace el `while` de `Game_Interpreter::Update`; y si
; queda, el cursor se deja **en el opcode** y se corta el cuadro, así que el
; siguiente vuelve a preguntar. Espera a que no quede **ninguna**, ni la del
; héroe ni la de ningún evento: es `Game_Map::IsAnyMovePending`, y no una espera
; por el evento que se acaba de mandar a caminar.
op_wait_routes:
    jsr hay_rutas
    beq op_wait_routes_next
    dey                         ; el cursor vuelve al opcode
    sty ev_cur
    rts
op_wait_routes_next:
    jmp otro

; `HaltAllMovement`: todas las rutas forzadas del mapa se abandonan de golpe.
; Es `Game_Map::RemoveAllPendingMoves`, o sea un `CancelMoveRoute` sobre el
; héroe y sobre cada evento. No cuesta un cuadro: la página sigue en el mismo
; tick, que es el `return true` de `CommandHaltAllMovement`.
;
; Lo que **no** hace, y es lo que lo separa de `MoveTo`: el paso y el salto en
; curso se terminan, y hacia dónde mira cada uno queda donde la ruta lo dejó.
; `hay_rutas` los sigue mirando, así que un `ProceedWithMovement` pegado atrás
; espera los cuadros que le falten al paso; la referencia cuenta igual.
;
; Y quien tenía ruta propia de página vuelve a la suya con `retomar_pagina`,
; que es la misma rutina que corre cuando una forzada termina sola: cancelarla
; y terminarla no se pueden separar, que es justo la clase de diferencia que
; nadie ve hasta que la escena sale distinta.
op_stop_routes:
.a8
.i16
    ; El héroe. Se le vacían las órdenes y la espera; el paso en curso no.
    stz ruta_n
    stz ruta_i
    stz ruta_espera
    phy                         ; Y es el cursor del bytecode
    ldx #$0000
parar_otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq parar_siguiente
    lda ruta_ev + 18, x
    and #$01
    bne parar_siguiente         ; la de la página no es forzada
    lda ruta_ev + 27, x         ; ¿tiene ruta propia a la que volver?
    beq parar_sin_pagina
    jsr retomar_pagina
    bra parar_siguiente
parar_sin_pagina:
    stz ruta_ev + 4, x
    stz ruta_ev + 5, x
    stz ruta_ev + 9, x
parar_siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc parar_otra
    ply
    jmp otro

; `ControlVars`, de a una variable: ranura, operación, clase del operando, y
; a y b de dieciséis bits. Ver OP_VAR en eventos.py. Dieciséis bits con signo,
; dando la vuelta.
op_var:
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la operación
    iny
    lda [cod_ptr], y            ; la clase del operando
    iny
    phy                         ; Y -> a; se repone al final
    cmp #VAR_VARIABLE
    beq var_de_variable
    cmp #VAR_AZAR
    beq var_al_azar
    cmp #VAR_OTRO
    beq var_de_otro
    cmp #VAR_PERSONAJE
    bne :+
    jmp var_de_personaje
:
    rep #$20
.a16
    lda [cod_ptr], y            ; una constante
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_variable:
    lda [cod_ptr], y            ; la ranura de donde sale
    jsr var_leer
.a16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_de_otro:
    lda [cod_ptr], y
    bne var_del_timer
    ; El oro, topado en 32767: la variable es de dieciséis bits con signo.
    lda oro + 2
    bne var_oro_tope
    rep #$20
.a16
    lda oro
    bmi var_oro_tope_16
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
.a16
var_oro_tope_16:
    sep #$20
.a8
var_oro_tope:
    lda #$FF
    sta temp + 2
    lda #$7F
    sta temp + 3
    bra var_aplicar
var_del_timer:
    rep #$20
.a16
    lda timer_seg               ; los segundos que le quedan al cronómetro
    sta temp + 2
    sep #$20
.a8
    bra var_aplicar
var_al_azar:
    ; a + x mod (b - a + 1), con x el paso siguiente del xorshift y el módulo
    ; con el divisor de ocho bits del hardware: el conversor no deja pasar un
    ; rango de más de 255.
    jsr azar_siguiente
    sta WRDIVL                  ; el dividendo, de dieciséis
    lda [cod_ptr], y            ; a
    sta temp + 2
    iny
    iny
    lda [cod_ptr], y            ; b
    sec
    sbc temp + 2
    inc a                       ; b - a + 1
    sep #$20
.a8
    sta WRDIVB                  ; arranca: dieciséis ciclos
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
    lda RDMPYL                  ; el resto
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_aplicar:
    ; `temp + 2` es el operando; según la operación, se pone tal cual o se
    ; suma o resta a lo que la variable tenía.
    lda temp + 1
    beq var_pone
    lda temp
    jsr var_leer                ; A = lo que tenía, de dieciséis
.a16
    pha
    sep #$20
.a8
    lda temp + 1
    cmp #VAR_SUMAR
    beq var_suma
    rep #$20
.a16
    pla
    sec
    sbc temp + 2
    sta temp + 2
    sep #$20
.a8
    bra var_pone
var_suma:
    rep #$20
.a16
    pla
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
var_pone:
    lda temp
    jsr var_escribir            ; y el refresco, si la ranura lo pide: las
                                ; páginas que miran esta variable pueden
    ply                         ; cambiar. Ver `var_escribir`
    iny                         ; a y b, cuatro bytes
    iny
    iny
    iny
    jmp otro

var_de_personaje:
    ; La clase 6: las coordenadas de un personaje, en celdas. `a` es el blanco
    ; —0 el héroe, el índice del evento más uno, el mismo byte que OP_ROUTE— y
    ; `b` dice cuál: PERSONAJE_X o PERSONAJE_Y.
    ;
    ; La celda que se lee es la **viva**: `tile_x`/`tile_y` para el héroe y
    ; `ev_pos_buf` para un evento, que es adonde una ruta forzada, un
    ; ChangeEventLocation o un TradeEventLocations la dejaron. En RM2k es
    ; `character->GetX()`, o sea lo mismo.
    ; No se guarda ninguno de los dos operandos en RAM: la BSS está llena
    ; —dos bytes más y `ld65` avisa que no entra— y no hace falta. El blanco
    ; **por** EV_STRIDE se lleva en X, que acá no la usa nadie, y con el
    ; corrimiento puesto en la dirección: así el héroe queda con X en cero y
    ; distinguirlo es un `cpx`, que no toca el acumulador.
    lda [cod_ptr], y            ; a: el blanco
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tax
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; b: cuál coordenada
    cpx #$0000
    beq var_personaje_heroe
    ; Un evento: su celda está en `ev_pos_buf`, indexada por el índice de la
    ; tabla del mapa, que es el blanco menos uno; de ahí el - EV_STRIDE.
    cmp #PERSONAJE_X
    beq var_personaje_ev_x
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 2, x
    bra var_personaje_listo
.a8
var_personaje_ev_x:
    rep #$20
.a16
    lda ev_pos_buf - EV_STRIDE + 0, x
    bra var_personaje_listo
.a8
var_personaje_heroe:
    cmp #PERSONAJE_X
    beq var_personaje_heroe_x
    rep #$20
.a16
    lda tile_y
    bra var_personaje_listo
.a8
var_personaje_heroe_x:
    rep #$20
.a16
    lda tile_x
var_personaje_listo:
    sta temp + 2
    sep #$20
.a8
    jmp var_aplicar

; `ConditionalBranch` por variable: ranura, clase del valor, comparación, el
; valor de dieciséis bits y el destino si no se cumple. La comparación es con
; signo: después de restar, "menor" es N distinto de V.
op_if_var:
.a8
.i16
    lda [cod_ptr], y
    sta temp                    ; la ranura
    iny
    lda [cod_ptr], y
    sta temp + 1                ; la clase: constante u otra variable
    iny
    lda [cod_ptr], y            ; la comparación
    pha
    iny
    rep #$20
.a16
    lda [cod_ptr], y            ; el valor, o la ranura
    sta temp + 2
    sep #$20
.a8
    iny
    iny                         ; Y -> el destino
    lda temp + 1
    beq si_var_contra_constante
    lda temp + 2
    phy
    jsr var_leer
.a16
    ply
    sta temp + 2
    sep #$20
.a8
si_var_contra_constante:
    pla                         ; la comparación
    sta temp + 1
    lda temp
    phy
    jsr var_leer                ; A = la variable, de dieciséis
.a16
    jsr comparar_var
.a8
    ply
    cmp #0                      ; lo que dijo `comparar_var`, que `ply` pisó
                                ; con el cursor: ver `tema_asegurar`
    bne si_var_sigue
    rep #$20
.a16
    lda [cod_ptr], y            ; no se cumple: al destino
    tay
    sep #$20
.a8
    jmp otro
si_var_sigue:
    iny
    iny
    jmp otro

op_party:
    lda [cod_ptr], y            ; 0 = agregar, 1 = sacar
    sta temp
    iny
    lda [cod_ptr], y            ; el actor
    iny
    phy
    jsr cambiar_grupo
    ply
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

; `ChangeSpriteAssociation`: el actor y el índice del gráfico en la tabla del
; mapa, la misma que resuelve la orden 34 de una ruta. Ver OP_ACTOR_SPRITE en
; eventos.py.
;
; El `ResetGraphic()` que RM2k le hace al `Game_Player` es el `jsr
; elegir_grafico_heroe` de acá abajo, y va sólo si el que cambió es el que
; lidera: el que no lidera no se dibuja, y lo guardado lo va a leer
; `elegir_grafico_heroe` cuando le toque —al cambiar el grupo o al cargar otro
; mapa—.
;
; `aplicar_tinte` detrás por lo mismo que en `cambiar_grupo`: la fila de CGRAM
; que el líder tenía prestada queda con sus quince colores encima de los del
; mapa, y hay que reponerla desde el cartucho.
op_actor_sprite:
.a8
.i16
    lda [cod_ptr], y            ; el actor
    iny
    sta temp
    lda [cod_ptr], y            ; el gráfico
    iny
    sta temp + 1
    phy
    lda temp
    jsr actor_graf_escribir
    lda temp
    cmp grupo                   ; ¿es el líder?
    bne graf_no_lidera
    jsr elegir_grafico_heroe
    jsr aplicar_tinte
graf_no_lidera:
    ply
    jmp otro

; `KeyInputProc`: qué tecla apretó el jugador, guardada en una variable. Ver
; OP_KEY en eventos.py, que es donde está el porqué de que la forma que
; espera se emita dos veces.
;
; La que **espera** y no encuentra nada rebobina su propio cursor a este mismo
; opcode y devuelve el control: el cuadro que viene se la vuelve a ejecutar. Es
; lo mismo que hace la referencia devolviendo `(i, 0, None)`, y es lo que evita
; tener que guardar "estoy esperando" en algún lado —el intérprete de un evento
; paralelo son siete bytes y no le sobra ninguno—.
op_key:
.a8
.i16
    lda [cod_ptr], y            ; la ranura de la variable
    iny
    sta temp
    lda [cod_ptr], y            ; las banderas
    iny
    sta temp + 1
    and #TECLA_ARRANCA
    beq tecla_mirar
    ; La primera de las dos: la variable en cero y el control de vuelta sin
    ; mirar nada. Es el `Input::ResetTriggerKeys()` de RPG_RT: el flanco se
    ; calcula contra el pad del cuadro anterior, así que dejar pasar un cuadro
    ; es perderlo **para este intérprete**.
    ;
    ; Para el resto del cuadro no alcanzaba, y por eso se pisan los dos
    ; "anteriores" con el pad de ahora: easyrpg dice que el reset también
    ; impide "player actions for this frame such as summoning the menu or
    ; triggering events" (`game_interpreter.cpp:3403-3408`). Un paralelo corre
    ; antes que el héroe, así que sin esto la A con la que el motor de las
    ; piedras del mapa 11 prepara una le hablaba además a la reja que el héroe
    ; tenía enfrente. Lo cobra `test_con_a_y_una_direccion_la_piedra_sale_
    ; volando`.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz temp + 2
    stz temp + 3
    lda temp
    jsr var_escribir            ; con su refresco, si la ranura lo pide
    sty ev_cur
    rts
tecla_mirar:
    ; La que espera no mira el pad mientras haya un mensaje o una elección en
    ; pantalla, **de quien sea**: es el `if (Game_Message::IsMessageActive())
    ; break;` de `Game_Interpreter::Update`, easyrpg `game_interpreter.cpp:
    ; 470-473`. Importa en los paralelos, que siguen corriendo con el mensaje
    ; de otro abierto: sin esto, el A que cierra el mensaje de la PC rota del
    ; mapa 11 lo leía también el motor de las piedras, y se perdía una. Lo
    ; cobra `test_la_a_que_cierra_el_mensaje_no_saca_una_piedra`.
    lda temp + 1
    and #TECLA_ESPERA
    beq tecla_leer
    lda msg_abierto
    ora msg_estado              ; también mientras se compone
    ora eleg_activo
    bne tecla_rebobinar
tecla_leer:
    phy
    jsr tecla_valor
    ply
    sta temp + 2                ; el valor, que es de donde lo saca var_escribir
    stz temp + 3
    lda temp + 1
    and #TECLA_ESPERA
    beq tecla_guardar           ; sin espera se guarda lo que haya, cero incluido
    lda temp + 2
    bne tecla_guardar
tecla_rebobinar:
    dey                         ; todavía nada: el cursor vuelve a este opcode
    dey
    dey
    sty ev_cur
    rts
tecla_guardar:
    lda temp
    jsr var_escribir            ; `SetNeedRefreshForVarChange`, como ControlVars:
    jmp otro                    ; lo decide la ranura. Ver `var_escribir`

op_delay:
    ; Y acá se devuelve el control. Antes se salteaba, y el comentario decía
    ; que no había cuadros que dejar pasar porque esto corría con la pantalla
    ; apagada mientras se cargaba el mapa. Eso dejó de ser cierto: el intérprete
    ; corre desde el lazo principal, con la pantalla encendida, y una espera de
    ; RM2k es tiempo que el jugador ve pasar.
    rep #$20
.a16
    lda [cod_ptr], y            ; cuántos cuadros, de dieciséis bits
    sta ev_esperando
    sep #$20
.a8
    iny
    iny
    sty ev_cur
    rts

; `PanScreen`, en sus dos operaciones: correr la cámara sin el héroe y
; devolverla. El desplazamiento viene con signo y en 1/16 de pixel, y el paso
; por cuadro ya resuelto; lo que se cuenta acá son los cuadros que la página
; espera, que salen de **lo que falta** después de mover el destino y no de lo
; que este comando pidió. Ver `GetPanWait`.
op_pan:
    lda [cod_ptr], y            ; la operación
    iny
    cmp #PAN_VOLVER
    bne pan_correr
    rep #$20
.a16
    stz pan_dest_x              ; volver es ir al cero
    stz pan_dest_y
    sep #$20
.a8
    bra pan_saltear_desp
pan_correr:
    rep #$20
.a16
    lda [cod_ptr], y            ; el desplazamiento en x, con signo
    clc
    adc pan_dest_x
    sta pan_dest_x
    iny
    iny
    lda [cod_ptr], y            ; y en y
    clc
    adc pan_dest_y
    sta pan_dest_y
    sep #$20
.a8
    iny                         ; los dos de la y
    iny
    bra pan_leer_paso
pan_saltear_desp:
    iny                         ; los cuatro bytes del desplazamiento
    iny
    iny
    iny
pan_leer_paso:
    lda [cod_ptr], y            ; el paso por cuadro
    iny
    rep #$20
.a16
    and #$00FF
    sta pan_paso
    sep #$20
.a8
    lda [cod_ptr], y            ; si la página espera
    iny
    beq pan_sin_espera
    jsr pan_cuadros
    rep #$20
.a16
    sta ev_esperando
    ora #$0000                  ; `sta` no toca las banderas
    sep #$20
.a8
    ; Cero cuadros —la cámara ya estaba donde va— y la página **sigue en este
    ; mismo cuadro**: `CommandPanScreen` pone `wait_time = GetPanWait()` y
    ; devuelve true, y el lazo del intérprete sólo se detiene si `wait_time`
    ; es mayor que cero. Acá se cortaba el cuadro igual, y la puerta EV0009 del
    ; mapa 8 —un "volver" con espera y después el Teleport— llegaba al mapa 9
    ; un tick después que la referencia: el auto de Lashe City 33,36 iba 4 px
    ; atrás, medido el 2026-09-10. Lo cobra `snes-pan 6 "3 0 0 4 1"`.
    beq pan_sin_espera
    sty ev_cur
    rts
pan_sin_espera:
    jmp otro

op_tint:
    lda [cod_ptr], y
    sta tinte_r
    iny
    lda [cod_ptr], y
    sta tinte_g
    iny
    lda [cod_ptr], y
    sta tinte_b
    iny
    lda [cod_ptr], y
    sta tinte_s
    iny
    ; El tinte no se aplica acá: se pide, y lo hace `flush_video` en el vblank
    ; siguiente. `aplicar_tinte` sube tres paletas a CGRAM por DMA, y con el PPU
    ; dibujando esas escrituras se pierden. Mientras el intérprete corría adentro
    ; de `cargar_mapa`, con la pantalla apagada, no hacía falta; al mudarlo al
    ; lazo principal pasó a ejecutarse con la pantalla encendida y el tinte
    ; entraba a medias —quedaban teñidos la capa de encima y un sprite, y el
    ; resto no, según qué escritura pescara el vblank—.
    lda #1
    sta tinte_pendiente
    jmp otro                    ; `bra` no llega: el lazo quedó lejos

op_teleport:
    rep #$20
.a16
    lda [cod_ptr], y            ; el mapa, en un word desde que el formato
    sta salto_mapa              ; tiene que poder nombrar los 328 del juego
    iny
    iny
    lda [cod_ptr], y
    sta salto_x
    iny
    iny
    lda [cod_ptr], y
    sta salto_y
    sep #$20
.a8
    lda #1
    sta salto_hay
    iny                         ; los dos bytes de la Y, que se leyeron sin
    iny                         ; avanzar el cursor
    ; Y corta el cuadro, que es exactamente lo que hace
    ; `Game_Interpreter_Map::CommandTeleport` en easyrpg-player: reserva el
    ; salto, hace `index++` y devuelve false. El mapa se carga entre este cuadro
    ; y el siguiente, y la página retoma en el comando de después con el cursor
    ; guardado acá. Ninguna página del juego que hoy compile tiene comandos
    ; después de un teletransporte —está en la lista de ESTADO.md—; la
    ; cinemática de apertura tiene once.
    sty ev_cur
    rts
.endproc

; Una pelea de punta a punta, con la tropa ya puesta en `BA_TROPA`: guardar el
; tema del mapa, cargar el audio de la pelea, pelearla y volver al mapa.
;
; Está separada de `op_battle` desde que hay encuentros al azar, que la
; arrancan **sin bytecode**: allá no hay cursor que guardar ni manejadores a
; los que saltar. Lo de adentro no cambió de lugar.
.proc pelea_arrancar
.a8
.i16
    ; El tema del mapa se guarda y vuelve al terminar, que es el
    ; `before_battle_music` de RM2k —`Scene_Battle` lo anota al construirse y
    ; `Game_Map` lo repone al volver—. $FF quiere decir "no sonaba nada", y es
    ; un caso real: los primeros mapas del juego no traen música.
    ; **Con el banco de datos en el 0**, que acá todavía es el del bytecode:
    ; `music_apagada` y `tema_actual` son absolutos de la BSS y sin esto se
    ; leerían del banco del cartucho donde está la página. Es la misma trampa
    ; que los puentes `ba_t_*` del otro lado, y costó exactamente lo mismo.
    phb
    phk
    plb
    lda music_apagada
    bne callado_antes
    lda tema_actual
    bra anotado
callado_antes:
    lda #$FF
anotado:
    sta f:BAT_LARGO + BA_TEMA_ANT
    ; El paquete de audio de la pelea: su tema y sus efectos. Va aparte del
    ; paquete del mapa y no adentro, y está medido: el tema de batalla son 18
    ; muestras y 51.480 B de los 64.512 de ARAM, o sea que metiéndolo en el
    ; paquete del mapa 2 los 24 efectos de ese mapa se caían casi enteros.
    ; Se calla antes de rearmar, como hace `tema_asegurar`: `paquete_cargar`
    ; deja quietas las muestras del tema que suena, y las del mapa no tienen
    ; por qué ocupar lugar adentro de la pelea.
    ldx #BA_PAQUETE
    jsr batalla_audio_cargar
    lda #BA_TEMA
    jsr batalla_bgm
    plb
    ; El banco de datos, en $7E: es lo que le deja al código de la pelea usar
    ; direccionamiento absoluto sobre su estado sin perder la RAM baja, que en
    ; ese banco está en las mismas direcciones. Ver el comentario de
    ; `FAR_BATALLA`.
    phb
    lda #$7E
    pha
    plb
    jsl f:batalla_correr
    plb
    ; Los flancos que cerraron la pelea son de ella, como en la tienda y en el
    ; menú: si no, el A con el que se cerró el último mensaje abriría lo que
    ; haya en el mapa.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    phb
    phk
    plb                         ; el banco 0, por lo mismo que al entrar
    ldx mapa_actual             ; y el audio del mapa vuelve al SPC700
    jsr batalla_audio_cargar
    lda f:BAT_LARGO + BA_TEMA_ANT
    jsr batalla_bgm             ; el tema del mapa, o el silencio que había
    plb
    jsr volver_de_batalla
    rts
.endproc

; --- las variables ---------------------------------------------------------
;
; Viven en la RAM lejana, así que no se indexan: se apunta WMADD a la ranura y
; se lee o escribe la palabra por el puerto. Son pocas operaciones por página y
; el precio no se nota. `var_leer` devuelve en A de dieciséis bits **y deja M
; en dieciséis**; `var_escribir` toma el valor de `temp + 2`.

; A: la ranura. Deja WMADD apuntando a su palabra.
.proc var_apuntar
.a8
.i16
    rep #$20
.a16
    and #VAR_RANURA             ; sin el bit de VAR_REFRESCO, que viaja pegado
    asl a                       ; dos bytes por variable
    clc
    adc #FAR_VARIABLES
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: la ranura. Vuelve con su valor en A de dieciséis bits, y M en dieciséis.
.proc var_leer
.a8
.i16
    jsr var_apuntar
    lda WMDATA                  ; el byte bajo
    pha
    lda WMDATA                  ; y el alto
    xba
    pla                         ; C = alto:bajo
    rep #$20
.a16
    rts
.endproc

; A: la ranura, con `VAR_REFRESCO` en el bit de arriba si esta escritura pide
; el refresco de páginas; `temp + 2`: el valor.
;
; El refresco se marca **acá y no en cada opcode** porque por acá pasan las
; tres escrituras que hay —`op_var` y las dos ramas de `op_key`— y así el
; bit se mira una sola vez. Es `Game_Map::SetNeedRefreshForVarChange`, que
; tampoco marca por cualquier escritura: le pregunta al `map_cache` si alguna
; condición de página del mapa mira esa variable. Acá esa pregunta la contestó
; el conversor; ver VAR_REFRESCO en eventos.py.
.proc var_escribir
.a8
.i16
    pha                         ; la ranura con su bit, que var_apuntar tira
    jsr var_apuntar
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    pla
    and #VAR_REFRESCO           ; explícito y no el N que deja `pla`: ver la
    beq sin_refresco            ; trampa de las banderas en AGENTS.md
    lda #1
    sta refresco
sin_refresco:
    rts
.endproc

; Todas en cero, la semilla del azar puesta, la velocidad del héroe en 4, el
; inventario vacío y el menú y guardar permitidos. Corre en el reset, antes de
; cargar la partida. Viven seguidos en la RAM lejana, así que es una sola
; pasada por el puerto.
.proc limpiar_variables
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    ; Hasta el final del inventario, con el hueco que haya entre las
    ; variables y él: es una pasada en el reset y no importa.
    ldx #(FAR_ITEMS + ITEMS_N - FAR_ACCESO - 4)
    sep #$20
.a8
    stz WMADDH
    stz WMDATA                  ; guardar y el menú, permitidos
    lda #4                      ; la velocidad normal del héroe
    sta WMDATA
    lda #<AZAR_SEMILLA
    sta WMDATA
    lda #>AZAR_SEMILLA
    sta WMDATA
otra:
    stz WMDATA
    dex
    bne otra
    rts
.endproc

; El equipo inicial de todos los actores a `FAR_EQUIPO`: un DMA de la tabla
; del conversor a la ventana de la WRAM. Corre en el reset, antes de cargar
; la partida, que lo pisa.
.proc equipo_inicial_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_EQUIPO
    sta WMADDL
    lda #<(equipo_inicial)
    ora #(>(equipo_inicial) * 256)
    sta A1T0L
    lda #(ACTORES_N * 10)
    sta DAS0L
    sep #$20
.a8
    stz WMADDH
    lda #^(equipo_inicial)
    sta A1B0
    stz DMAP0                   ; de A a B, de a un byte
    lda #$80                    ; WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc


; La velocidad del héroe, en A. Sólo A: quien la pide está en medio de un paso
; con X e Y ocupados.
.proc hero_vel_leer
.a8
.i16
    rep #$20
.a16
    lda #FAR_HERO_VEL
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: la velocidad nueva.
.proc hero_vel_escribir
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_HERO_VEL
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; Cuántos cuadros dura cada frame de la caminata a la velocidad del héroe:
; `ANIM_PARADO` en eventos.py, `GetStationaryAnimFrames`. Con la velocidad 4
; son los seis de siempre.
.proc anim_cuadros_del_heroe
.a8
.i16
    jsr hero_vel_leer
    rep #$20
.a16
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    lda anim_por_vel, x
    rts
.endproc

; La comparación con signo de `ConditionalBranch` y de la condición de página
; por variable —RM2k usa `CheckOperator` para las dos—. A trae el valor de la
; variable en dieciséis bits, `temp + 2` contra qué se compara y `temp + 1` el
; código: ==, >=, <=, >, <, != en ese orden. Vuelve en ocho bits con A = 1 y
; Z=0 si se cumple, A = 0 y Z=1 si no. Pisa `temp + 1` a `temp + 3`.
.proc comparar_var
.a16
.i16
    sec
    sbc temp + 2                ; N, V y Z de la resta con signo
    sep #$20
.a8
    php
    pla                         ; A = las banderas: N $80, V $40, Z $02
    pha
    and #$C0
    beq no_menor                ; N y V en cero: no es menor
    cmp #$C0
    beq no_menor                ; los dos puestos: tampoco
    lda #1
    bra menor_listo
no_menor:
    lda #0
menor_listo:
    sta temp + 2                ; menor
    pla
    and #$02
    beq no_igual
    lda #1
no_igual:
    sta temp + 3                ; igual
    lda temp + 1                ; la comparación
    beq igual
    cmp #1
    beq mayor_igual
    cmp #2
    beq menor_igual
    cmp #3
    beq mayor
    cmp #4
    beq menor
    lda temp + 3                ; !=
    eor #1
    rts
igual:
    lda temp + 3
    rts
mayor_igual:
    lda temp + 2
    eor #1
    rts
menor_igual:
    lda temp + 2
    ora temp + 3
    rts
mayor:
    lda temp + 2
    ora temp + 3
    eor #1
    rts
menor:
    lda temp + 2
    rts
.endproc

; El paso del xorshift: x ^= x << 7; x ^= x >> 9; x ^= x << 8. Vuelve con el
; valor nuevo en A de dieciséis bits, y M en dieciséis. Es `azar_siguiente` de
; eventos.py, instrucción por instrucción. Usa `temp + 2` de escritorio: quien
; lo llama —`op_var`— todavía no lo cargó.
.proc azar_siguiente
.a8
.i16
    rep #$20
.a16
    lda #FAR_AZAR
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    pha
    lda WMDATA
    xba
    pla                         ; C = x
    rep #$20
.a16
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor temp + 2
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lda #FAR_AZAR
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    rep #$20
.a16
    lda temp + 2
    rts
.endproc
.a8
.i16



; Compone la ventana de la opción marcada. El cuadro sale de la tabla, en
; `eleg_tabla + eleg_sel * 4`; el destino está dos bytes más allá y lo lee
; `eleccion_tick`.
;
; Volver a llamar a `msg_empezar` con la ventana ya abierta es lo que mueve el
; cursor: `msg_abierto` no se apaga, así que la ventana no parpadea, y el
; compositor va pisando renglón por renglón lo que había. Un renglón de una
; opción son cinco o seis caracteres, o sea un par de cuadros: se ve como un
; cursor que se mueve, no como una ventana que se rehace.
.proc eleg_abrir
.a8
.i16
    lda eleg_sel
    asl
    asl                         ; cuatro bytes por opción
    rep #$20
.a16
    and #$00FF
    clc
    adc eleg_tabla
    tay
    lda [cod_ptr], y            ; el desplazamiento del cuadro, de 16 bits
    jsr msg_empezar             ; que lo espera en A y en modo 16
    sep #$20
.a8
    rts
.endproc

; Un cuadro de una elección abierta. Devuelve A distinto de cero cuando el
; jugador eligió, y ahí la página ya tiene el cursor puesto en el cuerpo de la
; opción y sigue en este mismo cuadro.
;
; El movimiento del cursor es `Window_Selectable::Update` con `column_max` en
; uno: arriba y abajo dan la vuelta, y valen por **flanco** y no por estado, que
; es el `Input::IsTriggered` de allá. Sostener abajo no baja de a un renglón por
; cuadro.
;
; **Este camino no lo cubre la tanda de pixeles**, que sólo sabe apretar A, y
; por eso la referencia no lo modela: escribir del otro lado código que ninguna
; prueba corre es la manera en que este repo ya se equivocó tres veces. Lo cubre
; `pruebas/rpgmaker/test_elegir.py`, que sí puede apretar cualquier botón.
.proc eleccion_tick
.a8
.i16
    lda msg_abierto
    bne abierta
    lda #0                      ; todavía se está componiendo: nadie elige
    rts
abierta:
    lda pad
    eor pad_ant
    and pad                     ; lo que se apretó **en este cuadro**
    sta eleg_flancos
    and #PAD_UP
    beq no_arriba
    lda eleg_sel
    bne sube_una
    lda eleg_n                  ; desde la primera, arriba da la vuelta
sube_una:
    dec a
    sta eleg_sel
    jsr eleg_abrir
    lda #0
    rts
no_arriba:
    lda eleg_flancos
    and #PAD_DOWN
    beq no_abajo
    lda eleg_sel
    inc a
    cmp eleg_n
    bcc baja_una
    lda #0                      ; y desde la última, abajo también
baja_una:
    sta eleg_sel
    jsr eleg_abrir
    lda #0
    rts
no_abajo:
    lda eleg_flancos
    and #PAD_B
    beq mira_a
    lda eleg_cancel
    beq mira_a                  ; esta elección no se deja cancelar
    dec a                       ; `choice_result = cancel_type - 1`
    sta eleg_sel
    ; Y el B se consume acá: en RM2k la ventana procesa la tecla **después**
    ; del héroe, que la vio con el mensaje abierto y no pidió el menú. Acá la
    ; elección corre antes que `pedir_menu`, así que se le borra el flanco.
    lda pad_ant
    ora #PAD_B
    sta pad_ant
    bra elige
mira_a:
    lda pad_a
    beq nada
    lda pad_a_ant
    bne nada                    ; ya lo tenía apretado: no es un flanco
elige:
    lda eleg_sel
    asl
    asl
    rep #$20
.a16
    and #$00FF
    clc
    adc eleg_tabla
    inc a
    inc a                       ; el destino va después del cuadro
    tay
    lda [cod_ptr], y
    sta ev_cur
    sep #$20
.a8
    stz eleg_activo
    stz msg_abierto             ; y con eso `flush_video` apaga el HDMA
    lda #1
    rts
nada:
    lda #0
    rts
.endproc

; --- el tinte de pantalla --------------------------------------------------
;
; RM2k escala cada canal por un valor de 0 a 200, con 100 como neutro. En una
; consola con paleta eso no es un efecto de pantalla sino una transformación de
; la paleta: se escalan los colores al subirlos y el fondo, que va en 8 bits por
; pixel y direcciona CGRAM en directo, queda teñido exactamente.
;
; La cuenta es `i * valor / 100` con enteros. Las dos operaciones las hace el
; hardware y son exactas, así que la referencia en Python hace la misma cuenta
; y da siempre lo mismo. Una aproximación con corrimientos no serviría: la
; comparación es pixel por pixel.

; t[i] = i * valor / 100 para i de 0 a 31, topado en 31. A = valor, X = tabla.
.proc tabla_canal
.a8
.i16
    ; El tinte de RM2k no escala el canal: lo compone con un *hard light*, que
    ; es `2ab` para la mitad de abajo y el screen `1-2(1-a)(1-b)` para la de
    ; arriba. En las unidades de RM2k, con 100 neutro, las dos mitades son la
    ; misma cuenta espejada en los dos ejes:
    ;
    ;     valor <= 100:  canal * valor / 100
    ;     valor  > 100:  31 - (200 - valor) * (31 - canal) / 100
    ;
    ; Así que se arma siempre la de abajo —que es lo que este archivo venía
    ; haciendo, o sea que los tintes que oscurecen dan exactamente lo mismo que
    ; antes— y si el valor aclara se espeja la tabla terminada:
    ; `t'[j] = 31 - t[31 - j]`.
    ;
    ; La mitad de arriba estaba mal: multiplicaba por dos y topaba en 31, y la
    ; diferencia con RM2k llegaba a 31 de 31 con el valor 200. No lo cobró nadie
    ; porque ninguna página que compilara aclaraba la pantalla; dos de las once
    ; que destraba la saturación sí, con (0, 120, 120).
    ;
    ; El espejo va afuera del lazo a propósito. Hacerlo por entrada —con la
    ; cuenta metida en una subrutina— son noventa y seis `jsr` y `rts` de más
    ; por tinte, y eso alcanzó para que `aplicar_tinte` pasara de un cuadro a
    ; dos: se vio como `snes-timer` perdiendo un tic del cronómetro.
    sta temp                    ; el valor del canal
    stx temp + 2                ; dónde va la tabla
    stz tinte_espejo
    cmp #(TINTE_NEUTRO + 1)
    bcc arrancar
    lda #(2 * TINTE_NEUTRO)
    sec
    sbc temp
    sta temp                    ; 200 - valor
    inc tinte_espejo
arrancar:
    ldy #$0000
cada:
    tya
    sta WRMPYA
    lda temp
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #TINTE_NEUTRO
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc cabe
    lda #31                     ; el canal tiene cinco bits y no más
cabe:
    sta (temp + 2), y
    iny
    cpy #32
    bne cada

    lda tinte_espejo
    bne espejar
    rts

    ; El espejo va en dos pasadas, con una copia en el medio, porque `(dp), y`
    ; direcciona con Y y acá hacen falta dos índices a la vez: `j` y `31 - j`.
espejar:
    ldy #$0000
copiar:
    lda (temp + 2), y
    sta tinte_tmp, y
    iny
    cpy #32
    bne copiar
    ldy #$0000
volver:
    rep #$20
.a16
    tya
    eor #$001F                  ; con cinco bits, el complemento es 31 - j
    tax
    sep #$20
.a8
    lda #31
    sec
    sbc tinte_tmp, x
    sta (temp + 2), y
    iny
    cpy #32
    bne volver
    rts
.endproc

; Lee una paleta de la ROM, la tiñe color por color y la sube a CGRAM.
.proc tenir_paleta
.a8
.i16
    jsr armar_paleta
    jmp copiar_a_sombra
.endproc
; Copia la paleta recién armada en `pal_buf` a su lugar de `cgram_sombra`, y
; deja el tinte listo para que `flush_video` lo suba en el vblank.
.proc copiar_a_sombra
.a8
.i16
    lda tin_cgadd
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por color
    tay
    sep #$20
.a8
    ldx #$0000
    cpx tin_fin
    beq listo                   ; una paleta sin colores
copia:
    lda pal_buf, x
    sta cgram_sombra, y
    inx
    iny
    cpx tin_fin
    bne copia
listo:
    lda #1
    sta tinte_listo
    rts
.endproc

; Arma la paleta teñida en `pal_buf`, sin subirla.
.proc armar_paleta
.a8
.i16
    ; La cuenta va en Y y no en X: adentro del lazo X es el índice de las tres
    ; tablas de canal, así que al llegar acá vale el azul del color anterior y
    ; no cuántos colores van. Y sí sobrevive: es el cursor de la paleta.
    rep #$20
.a16
    lda tin_count
    asl a                       ; dos bytes por color
    sta tin_fin
    sep #$20
.a8
    ; Ni `sta` ni `sep` tocan Z, así que esto mira el `asl`. Una paleta sin
    ; colores se va sin hacer nada: el DMA de abajo mediría cero bytes, que en
    ; el hardware son 64 KB, y llenaría CGRAM de basura.
    bne hay_colores
    rts
hay_colores:
    ldy #$0000
    ; Con la saturación neutra —que es casi siempre— el color no necesita ni
    ; los tres canales juntos ni salir de los dieciséis bits, y ahí el lazo
    ; corto se paga solo. La cuenta: `aplicar_tinte` recorre los colores del
    ; mapa, los de la capa de encima, los de las ocho paletas de sprite y los
    ; del líder —en CoreRetro II son 151— y el lazo largo salía 205 ciclos cada
    ; uno. Con eso la vuelta del cuadro en que corre el tinte terminaba en la
    ; línea 224 de 262: **una** de margen. El primer evento de más que pidió
    ; una paleta la voló, y la pantalla quedó un cuadro sin teñir contra la
    ; referencia. Medido con la sonda de `contar_perdidos`.
    lda tinte_s
    cmp #TINTE_NEUTRO
    bne cada_color
    rep #$20
.a16
    jmp cada_color_neutro

cada_color:
.a8
    cpy tin_fin
    bne sigue_color
    rts
sigue_color:
    rep #$20
.a16
    lda [tin_ptr], y
    sta temp                    ; el color original, de 15 bits
    and #$001F
    sta sat_r
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_g
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F
    sta sat_b
    sep #$20
.a8
    ; La saturación va **antes** del color, que es el orden de `ToneBlit`: allá
    ; `saturation_tone` corre antes que `color_tone`. Al revés el gris se
    ; calcularía sobre el color ya teñido, y es de las que la comparación no
    ; vería porque los dos lados harían lo mismo mal.
    ;
    ; Y sólo cuando hace falta, igual que el `apply_sat` de easyrpg: no se puede
    ; hacer canal por canal —necesita el gris del color entero, o sea los tres a
    ; la vez— así que no entra en las tablas y es lo caro de todo esto.
    lda tinte_s
    cmp #TINTE_NEUTRO
    beq sin_saturar
    jsr saturar_color
sin_saturar:
    ldx sat_r
    lda tabla_r, x
    sta temp + 2
    ldx sat_g
    lda tabla_g, x
    sta temp + 3
    ldx sat_b
    lda tabla_b, x
    rep #$20
.a16
    and #$001F
    xba                         ; el azul va en los bits 10 a 14: ocho lugares
    asl a                       ; los da el intercambio de bytes y los dos que
    asl a                       ; faltan, dos corrimientos. Diez `asl` seguidos
                                ; se cuentan mal, y así fue como salieron cinco
    sta temp
    lda temp + 2
    and #$001F                  ; el rojo, sin el verde que quedó al lado
    ora temp
    sta temp
    lda temp + 3
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a                       ; y el verde en los bits 5 a 9
    ora temp
    sta pal_buf, y

    iny
    iny
    sep #$20
.a8
    bra cada_color

    ; El mismo color, sin saturación y sin salir de los dieciséis bits. Los
    ; `lda tabla_x, x` leen de paso el byte de al lado —las tres tablas están
    ; pegadas y después viene `puro`—; el `and` lo tira.
cada_color_neutro:
.a16
    cpy tin_fin
    beq subir_neutro
    lda [tin_ptr], y
    sta temp
    and #$001F                  ; el rojo
    tax
    lda tabla_r, x
    and #$001F
    sta temp + 2
    lda temp
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    and #$001F                  ; el verde
    tax
    lda tabla_g, x
    and #$001F
    xba                         ; por ocho
    lsr a
    lsr a
    lsr a                       ; menos tres: a los bits 5 a 9
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; el byte de arriba abajo
    lsr a
    lsr a
    and #$001F                  ; el azul, que estaba en los bits 10 a 14
    tax
    lda tabla_b, x
    and #$001F
    xba                         ; por ocho
    asl a
    asl a                       ; y dos más: a los bits 10 a 14
    ora temp + 2
    sta pal_buf, y
    iny
    iny
    bra cada_color_neutro
subir_neutro:
    sep #$20
.a8
subir:
    rts
.endproc

; --- la saturación del tinte -----------------------------------------------
; Acerca o aleja del gris los tres canales que quedaron en `sat_r`, `sat_g` y
; `sat_b`. Es `saturation_tone` de easyrpg puesto en cinco bits y en las
; unidades de RM2k: allá el factor sale de `gray = s * 128 / 100` y vale
; `gray * 8` o `1024 + (gray - 128) * 16` sobre 1024, que hecha la cuenta es
; `s / 100` por debajo de 100 y `(2s - 100) / 100` por arriba. O sea que 0
; lleva todo al gris, 100 no hace nada y 200 triplica la distancia.
.proc saturar_color
.a8
.i16
    ; Primero el gris. Los pesos son los de Y' del Y'CbCr y suman 65536
    ; exactos, así que sobre canales de cinco bits dan una luminancia de cinco
    ; bits: alcanza con quedarse con el byte de arriba de la suma de 24.
    stz sat_acc + 0
    stz sat_acc + 1
    stz sat_acc + 2
    lda sat_r
    sta peso_ch
    lda #<LUZ_R
    sta peso_lo
    lda #>LUZ_R
    sta peso_hi
    jsr sumar_peso
    lda sat_g
    sta peso_ch
    lda #<LUZ_G
    sta peso_lo
    lda #>LUZ_G
    sta peso_hi
    jsr sumar_peso
    lda sat_b
    sta peso_ch
    lda #<LUZ_B
    sta peso_lo
    lda #>LUZ_B
    sta peso_hi
    jsr sumar_peso
    lda sat_acc + 2             ; la suma sobre 65536
    sta sat_luz

    lda sat_r
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_r
    sep #$20
.a8
    lda sat_g
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_g
    sep #$20
.a8
    lda sat_b
    jsr saturar_canal
    rep #$20
.a16
    and #$00FF
    sta sat_b
    sep #$20
.a8
    rts
.endproc

; `sat_acc += peso * peso_ch`, en 24 bits. El peso es de dieciséis y la unidad
; de la consola multiplica de a ocho, así que va en dos productos: el bajo tal
; cual y el alto corrido un byte.
.proc sumar_peso
.a8
.i16
    lda peso_lo
    sta WRMPYA
    lda peso_ch
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda sat_acc + 2
    adc #0                      ; ni `sta` ni `sep` tocan el acarreo
    sta sat_acc + 2

    lda peso_hi
    sta WRMPYA
    lda peso_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp                    ; el producto alto, que va corrido ocho bits
    and #$00FF
    xba                         ; su byte bajo, ya en el lugar de arriba
    clc
    adc sat_acc
    sta sat_acc
    sep #$20
.a8
    lda temp + 1                ; y el byte alto del producto
    adc sat_acc + 2
    sta sat_acc + 2
    rts
.endproc

; Un canal acercado o alejado de `sat_luz`. Entra y sale en A.
.proc saturar_canal
.a8
.i16
    sta sat_ch
    lda tinte_s
    cmp #(TINTE_NEUTRO + 1)
    bcs sobre

    ; Hasta 100 es una interpolación entre el gris y el color, con los dos
    ; términos positivos: es la forma que el 65816 puede hacer sin signo.
    ;
    ;     (luz * (100 - s) + canal * s) / 100
    lda #TINTE_NEUTRO
    sec
    sbc tinte_s
    sta WRMPYA
    lda sat_luz
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta temp + 2
    sep #$20
.a8
    lda tinte_s
    sta WRMPYA
    lda sat_ch
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc temp + 2
    sta WRDIVL
    sep #$20
.a8
    jmp dividir_y_topar

    ; Por arriba de 100 el canal se aleja del gris: `canal +- |canal - luz| *
    ; (s - 100) / 100`, con el signo aparte para no tener que restar con signo.
    ; easyrpg lo hace con un desplazamiento aritmético, que redondea hacia abajo
    ; también con negativos; acá se trunca. La diferencia es de un valor de 31 y
    ; sólo cuando sobresatura.
sobre:
    lda tinte_s
    sec
    sbc #TINTE_NEUTRO
    sta WRMPYA
    lda sat_ch
    cmp sat_luz
    bcc baja
    inc sat_sube_marca
    sec
    sbc sat_luz
    bra multiplicar
baja:
    stz sat_sube_marca
    lda sat_luz
    sec
    sbc sat_ch
multiplicar:
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda #TINTE_NEUTRO
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta temp + 2
    lda sat_sube_marca
    beq restar
    lda sat_ch
    clc
    adc temp + 2
    cmp #32
    bcc listo_sobre
    lda #31
listo_sobre:
    rts
restar:
    lda sat_ch
    sec
    sbc temp + 2
    bcs listo_sobre
    lda #0
    rts
.endproc

; El divisor y la espera, que son los mismos en los dos caminos.
.proc dividir_y_topar
.a8
.i16
    lda #TINTE_NEUTRO
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc cabe
    lda #31
cabe:
    rts
.endproc

; Y la sube desde `pal_buf` a la entrada `tin_cgadd` de CGRAM.

; El tinte que dejó el evento, aplicado a las tres paletas del mapa.
.proc aplicar_tinte
.a8
.i16
    jsr tablas_de_tinte

    ; El fondo, desde donde arranca: debajo de él están el color de fondo de la
    ; pantalla y la paleta de la ventana, que **no se tiñen**. Que queden afuera
    ; sale de dónde empieza el rango y no de acordarse de saltearlas.
    ldx #M_PTR_MAP_CGRAM
    ldy #M_MAP_CGRAM
    lda #CGRAM_BASE
    jsr una_paleta

    ; La capa de encima, en la entrada que le haya tocado a este mapa. Hay que
    ; leerla del registro antes de cargar X con el campo, porque el registro se
    ; direcciona justamente con X.
    ldx mapa_ofs
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    pha
    ldx #M_PTR_ABOVE_CGRAM
    ldy #M_ABOVE_CGRAM
    pla
    jsr una_paleta

    ; Y los sprites, en la mitad de arriba de CGRAM.
    ldx #M_PTR_SPRITE_CGRAM
    ldy #M_SPRITE_CGRAM
    lda #128
    jsr una_paleta

    ; Encima, los colores del líder en su ranura. Los líderes posibles comparten
    ; una, así que el bloque que vino del cartucho trae los del que el conversor
    ; puso primero, y el que está liderando puede ser otro. Va **acá** y no
    ; aparte para que se tiña con todo lo demás: subirlos después dejaría al
    ; héroe sin teñir, que es el error inverso del cronómetro.
    lda hero_cgram + 2
    beq sin_lider_pal           ; ningún líder con gráfico: nada que subir
    rep #$20
.a16
    lda hero_cgram
    sta tin_ptr
    lda #OBJ_COLORS
    sta tin_count
    sep #$20
.a8
    lda hero_cgram + 2
    sta tin_ptr + 2
    lda hero_pal                ; viene corrido un lugar, o sea paleta por dos
    asl a
    asl a
    asl a                       ; y esto lo lleva a paleta por dieciséis
    clc
    adc #129                    ; la mitad de sprites, más el índice 0 que no se
    sta tin_cgadd               ; dibuja
    jsr tenir_paleta
sin_lider_pal:

    ; El cronómetro va **sin teñir**, encima de lo que acaba de subir. En RM2k
    ; el tinte es una propiedad de los dibujables del mapa —`Priority_Screen`
    ; es 90 y `Priority_Timer` 140—, así que la pantalla se oscurece y los
    ; dígitos no. Acá el tinte es una transformación de CGRAM y se lleva por
    ; delante todo lo que toca, pero los dígitos tienen una paleta para ellos
    ; solos, así que alcanza con volver a subir la de la ROM.
    ;
    ; La ventana de mensaje tampoco se tiñe, y sin hacer nada: vive en las
    ; entradas de abajo de todo y el fondo arranca en `CGRAM_BASE`, así que
    ; queda fuera del rango. Es lo que hace RM2k —el tono se aplica al mapa, a
    ; los personajes y al panorama, no a la ventana— y acá decía que no se
    ; podía.
    ;
    ; Nada de esto tocó CGRAM: las tres paletas quedaron en `cgram_sombra` y
    ; las sube `subir_tinte`, en el vblank.
    rts
.endproc

; Sube a CGRAM las tres paletas teñidas de `cgram_sombra`, y la del cronómetro
; sin teñir detrás. Es para el vblank, o para `cargar_mapa` con la pantalla
; apagada. Los tres DMA juntos son a lo sumo 544 bytes.
.proc subir_tinte
.a8
.i16
    stz tinte_listo
    rep #$20
.a16
    lda #.loword(cgram_sombra)
    sta sombra_origen
    sep #$20
.a8
    jmp subir_paletas
.endproc
; Lo mismo desde `pal_buf`, que es donde queda la sombra con el destello de
; pantalla encima. Se lleva el tinte pendiente, si lo había: el destello ya
; se armó sobre la sombra recién teñida.
.proc subir_destello
.a8
.i16
    stz destello_listo
    stz tinte_listo
    rep #$20
.a16
    lda #.loword(pal_buf)
    sta sombra_origen
    sep #$20
.a8
    jmp subir_paletas
.endproc
.proc subir_paletas
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #CGRAM_BASE             ; el fondo arranca corrido: abajo está la
    jsr dma_sombra              ; ventana, que no se tiñe ni se vuelve a subir
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    jsr dma_sombra
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #128
    jsr dma_sombra
    jmp subir_timer_pal
.endproc
; Un DMA de `tin_count` colores desde `sombra_origen` a la entrada A de CGRAM.
.proc dma_sombra
.a8
.i16
    sta CGADD
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc sombra_origen
    sta A1T0L
    lda tin_count
    asl a                       ; dos bytes por color
    beq nada                    ; cero bytes serían 64 KB
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; la sombra vive en el banco 0
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN
    rts
.a16
nada:
    sep #$20
.a8
    rts
.endproc

; La paleta del cronómetro, tal cual está en la ROM. Es la última de las de
; sprite, así que arranca en el color 128 + TIMER_PAL*16 y son 16 colores.
.proc subir_timer_pal
.a8
.i16
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_BASE, x
    ora f:mapa_tabla + M_TIMER_BASE + 1, x
    bne hay                     ; TIMER_BASE = 0: esta ROM no lleva cronómetro
    rts
hay:
    lda f:mapa_tabla + M_TIMER_PAL, x
    asl a
    asl a
    asl a
    asl a                       ; dieciséis colores por paleta
    clc
    adc #128
    sta CGADD

    ldy #M_PTR_SPRITE_CGRAM
    jsr dma_origen
    ; Y el desplazamiento de la paleta adentro del bloque: el doble, porque
    ; cada color son dos bytes.
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_PAL, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por paleta
    clc
    adc A1T0L
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; Tiñe y sube una de las paletas del mapa. X = el campo del puntero, Y = el
; campo de la cantidad, A = en qué entrada de CGRAM arranca.
.proc una_paleta
.a8
.i16
    sta tin_cgadd
    stx temp
    sty temp + 2

    rep #$20
.a16
    lda temp
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta tin_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta tin_ptr + 2

    rep #$20
.a16
    lda temp + 2
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta tin_count
    sep #$20
.a8
    jsr tenir_paleta
    rts
.endproc

; ¿Está el actor de A en el grupo? Vuelve con Z=0 si sí.
.proc en_el_grupo
.a8
.i16
    ldx #$0000
busca:
    cpx grupo_n                 ; grupo_n es de 16 bits a propósito: con .i16
    beq no_esta                 ; esta comparación lee dos bytes igual
    cmp grupo, x
    beq esta
    inx
    bra busca
esta:
    lda #1                      ; Z=0
    rts
no_esta:
    lda #0                      ; Z=1
    rts
.endproc

; Agrega o saca un actor del grupo y recalcula con qué se dibuja el héroe.
; A = el actor, temp = 0 para agregar y 1 para sacar.
;
; Las reglas son las de `Game_Party::AddActor` y `RemoveActor`: agregar a
; alguien que ya está no lo duplica ni lo mueve de lugar, agregar con el grupo
; lleno no hace nada, y sacar a alguien que no está tampoco. El orden importa
; porque el primero es el que se dibuja.
.proc cambiar_grupo
.a8
.i16
    ldx #$0000
buscar:
    cpx grupo_n
    beq no_estaba
    cmp grupo, x
    beq estaba
    inx
    bra buscar

estaba:
    ; `temp` se mira con A y no con `ldy temp`: con .i16 eso leería dos bytes y
    ; el de al lado no es nuestro. Es la trampa del ancho de los índices, que ya
    ; está anotada en el README, y acá dio exactamente el síntoma que promete:
    ; ningún cambio de grupo tenía efecto y no había ningún error.
    pha
    lda temp
    beq era_agregar             ; agregar uno que ya está: nada que hacer
    pla
    ; Sacarlo: se corren los de atrás un lugar.
correr:
    inx
    cpx grupo_n
    beq acortar
    lda grupo, x
    sta grupo - 1, x
    bra correr
acortar:
    rep #$20
.a16
    dec grupo_n
    sep #$20
.a8
    bra listo
era_agregar:
    pla
    bra listo

no_estaba:
    pha
    lda temp
    bne era_sacar               ; sacar uno que no está: nada que hacer
    pla
    cpx #GRUPO_MAX
    beq listo                   ; lleno: RM2k tampoco lo agrega
    sta grupo, x
    rep #$20
.a16
    inc grupo_n
    sep #$20
.a8
    bra listo
era_sacar:
    pla

listo:
    jsr elegir_grafico_heroe
    ; El líder nuevo tiene otros colores y comparte la ranura con el anterior,
    ; así que hay que rearmar las paletas. No toca CGRAM: deja todo en
    ; `cgram_sombra` y lo sube `subir_tinte` en el vblank.
    jsr aplicar_tinte
    lda #1
    sta refresco                ; las páginas que piden un actor pueden cambiar
    rts
.endproc

; A: un índice de la tabla de gráficos del mapa —la que arma `ruta_grafico` y
; que `load_ruta_graficos` copia a `ruta_graf_buf`—. Deja `hero_poses`,
; `hero_pal` y `hero_cgram` apuntando a ese gráfico y vuelve con C=1; si el
; gráfico no está en el banco de sprites de este mapa vuelve con C=0 y sin
; tocar nada.
;
; Sale barata porque las dos tablas de poses tienen la misma forma: una entrada
; de `npc_poses` son doce punteros de tres bytes a las poses del personaje, y
; los doce que la tabla de actores le da al líder están escritos igual. O sea
; que alcanza con apuntar `hero_poses` treinta y seis bytes adentro de
; `npc_poses` y `place_hero` sigue sin enterarse.
;
; `hero_cgram` se apaga: los quince colores del líder los sube `aplicar_tinte`
; **en la fila que dice `hero_pal`**, así que dejarlo puesto con la paleta nueva
; le escribiría los colores de Talan encima a la paleta del gráfico al que se
; cambió. Mientras el cambio está puesto, el héroe se dibuja con la paleta del
; gráfico nuevo, que ya vive en CGRAM con el resto de los sprites del mapa.
;
; La usan los dos que le cambian el gráfico al héroe: la orden 34 de una ruta
; —`grafico_heroe`— y el `ChangeSpriteAssociation` sobre el actor que lidera
; —`elegir_grafico_heroe`—. Lo que cada uno hace con el C=0 es distinto y por
; eso queda afuera: la orden 34 esconde al héroe y el cambio de actor lo deja
; con el gráfico del LDB.
.proc hero_poses_de_grafico
.a8
.i16
    asl a                       ; dos bytes por entrada en `ruta_graf_buf`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta_graf_buf, x        ; su entrada en `npc_poses`, o $FF
    cmp #$FF
    beq no_esta
    sta temp
    lda ruta_graf_buf + 1, x
    asl a
    and #$0E                    ; la paleta, corrida a su lugar en vhoopppN
    sta hero_pal
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; k por cuatro
    sta temp + 2
    asl a
    asl a
    asl a                       ; k por treinta y dos
    clc
    adc temp + 2                ; treinta y seis por personaje: doce punteros
    clc                         ; de tres bytes, como la tabla del actor
    adc poses_ptr
    sta hero_poses
    sep #$20
.a8
    lda poses_ptr + 2
    adc #0
    sta hero_poses + 2
    stz hero_cgram + 2          ; ver arriba: nadie sube colores encima
    sec
    rts
no_esta:
    clc
    rts
.endproc

; Con qué se dibuja el héroe: se busca al primero del grupo en la tabla de
; actores del mapa y se guardan sus doce poses y su paleta.
;
; Antes esto no existía: el héroe era siempre el personaje 0 del banco de
; sprites y el tile de cada pose salía de una cuenta. Con el grupo cambiando en
; caliente ya no alcanza, y además el tile puede pasar de ocho bits cuando hay
; varios personajes, así que se lee de una tabla.
.proc elegir_grafico_heroe
.a8
.i16
    lda #$FF
    sta hero_pose_vram          ; otro actor: su pose hay que subirla sí o sí
    stz hero_pal
    rep #$20
.a16
    stz hero_poses
    stz hero_cgram
    sep #$20
.a8
    stz hero_poses + 2
    stz hero_cgram + 2
    lda grupo_n
    beq sin_lider               ; grupo vacío: no se dibuja nada

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ACTOR_COUNT, x
    beq sin_lider16
    sta temp + 2
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE, x
    sta act_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE + 2, x
    sta act_ptr + 2

    ldy #$0000
    lda grupo                   ; el líder
    sta temp
cada_actor:
    lda [act_ptr], y
    cmp temp
    beq lo_encontre
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_BYTES
    tay
    dec temp + 2
    sep #$20
.a8
    bne cada_actor
    bra sin_lider

lo_encontre:
    ; Antes que el LDB, el `ChangeSpriteAssociation` que le hayan hecho a este
    ; actor: es el `actor->SetSprite` de RM2k, y vive en el actor, así que
    ; **cruza el teletransporte**. Si su gráfico no está en el banco de sprites
    ; de este mapa se cae al del LDB, que es a lo que apunta el camino de
    ; abajo; la referencia hace lo mismo. Ver OP_ACTOR_SPRITE en eventos.py.
    phy                         ; la entrada del actor, por si no hay cambio
    lda temp                    ; el líder
    jsr actor_graf_leer
    cmp #ACTOR_GRAF_NINGUNO
    beq sin_cambio_de_sprite
    jsr hero_poses_de_grafico
    bcc sin_cambio_de_sprite
    ply
    rts
sin_cambio_de_sprite:
    ply
    iny
    lda [act_ptr], y            ; su paleta, ya corrida a su lugar en vhoopppN
    asl a
    and #$0E
    sta hero_pal
    iny                         ; y acá arrancan sus quince colores
    rep #$20
.a16
    tya
    clc
    adc act_ptr
    sta hero_cgram
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_cgram + 2
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_COLORES          ; y detrás, las doce palabras de las poses
    tay
    clc
    adc act_ptr
    sta hero_poses
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_poses + 2
    rts

sin_lider16:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
sin_lider:
    rts
.endproc

; Un comando de la ruta forzada. Girar no consume cuadro y se sigue con el
; siguiente; esperar sí; y moverse arranca un paso de una celda, que después
; camina `advance_step` como cualquier otro. Un movimiento bloqueado se saltea:
; RM2k reintentaría para siempre y una prueba colgada no dice nada.
; Los saltos de acá adentro van con `jmp` y no con `bra`: el cuerpo pasó de
; siete órdenes a quince y los 127 bytes de alcance de un `bra` se quedaron
; cortos tres veces seguidas. Es la misma trampa que ya había cortado dos veces
; en el despacho de opcodes de `correr_codigo`, y se saca igual.
.proc paso_de_ruta
.a8
.i16
    ; Un `wait` en curso se lleva el cuadro entero y no mira la ruta. Son
    ; RUTA_ESPERA cuadros y no uno: es `SetMaxStopCountForWait` de RM2k, que con
    ; la frecuencia 8 da veinte. Valía uno de los dos lados a la vez, así que la
    ; comparación daba cero —el mismo error que el hard light del tinte—.
    ; Un salto en curso se lleva el cuadro entero: la celda ya se movió al
    ; empezar y lo único que pasa es que le queda menos arco.
    lda ruta_salto
    beq sin_salto
    sec
    sbc #SALTO_VELOCIDAD
    bcs guardar_salto
    lda #0
guardar_salto:
    sta ruta_salto
    jsr salto_posicion_heroe
    rts
sin_salto:
    lda ruta_espera
    beq sin_espera
    dec ruta_espera
    rts
sin_espera:
otra_orden:
    lda ruta_i
    cmp ruta_n
    bcc hay_orden
    jmp listo                   ; se terminó la ruta; `bcs` ya no llega
hay_orden:
    ; El índice a X pasando por A de dieciséis bits y limpiando el alto: `tax`
    ; transfiere los dos bytes del acumulador aunque A esté en ocho, y el alto
    ; trae lo que dejó la operación anterior. Es la trampa que ya está anotada
    ; en el README, y acá hacía que la ruta leyera basura y se cortara al primer
    ; paso: el héroe caminaba una celda de tres y no había ningún error.
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i

    cmp #23                     ; wait: éste y los RUTA_ESPERA - 1 que siguen,
    bne no_es_wait              ; más los del giro si la frecuencia es baja
    lda ruta_frec
    jsr tras_giro
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_espera
    jmp listo
no_es_wait:
    cmp #12
    bcs no_es_mover
    jmp mover                   ; 0..3 son los move_*
no_es_mover:
    cmp #16
    bcc face                    ; 12..15 son los face_*
    ; Girar sin moverse no se compila, y encarar al héroe —la 21— e ir hacia
    ; él —la 9— no se compilan **sobre el héroe**: ver `RUTA_ORDENES` en
    ; eventos.py. Acá no llegan. La 9 además caería en `mover` de arriba, que
    ; con una dirección que no es 0..3 manda al héroe a la izquierda por
    ; descarte, que es la misma trampa que las diagonales.
    cmp #24
    bne no_es_salto
    jsr armar_salto_heroe
    lda ruta_salto
    bne salto_arranco
    jmp otra_orden              ; no se pudo caer ahí: se saltea
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    bne no_es_fin
    jmp otra_orden              ; el par ya lo consumió el `begin_jump`
no_es_fin:
    cmp #28
    bcc otra_orden              ; 26 y 27 no llegan sobre el héroe
    cmp #30
    bcs no_es_velocidad
    jmp velocidad               ; 28 y 29: la velocidad, que queda
no_es_velocidad:
    cmp #32
    bcc frecuencia              ; 30 y 31: la frecuencia de la ruta
    cmp #34
    bne no_es_grafico_heroe
    jmp grafico_heroe           ; la 34, la única con operando; queda lejos
no_es_grafico_heroe:
    cmp #36
    bcc otra_orden              ; 32, 33 y 35 —los switches y el sonido— no
                                ; llegan: el conversor los tira o los rechaza
    cmp #38
    bcc atravesar               ; 36 y 37
    cmp #40
    bcs otra_orden
    ; 38 para la animación y 39 la sigue, así que la resta va al revés.
    sec
    sbc #38
    eor #$01
    sta ruta_anim_para
    jmp otra_orden
atravesar:
    ; 36 prende y 37 apaga, así que el bit de abajo invertido es el valor.
    and #$01
    eor #$01
    sta ruta_atraviesa
    jmp otra_orden
frecuencia:
    ; 30 sube la frecuencia de la ruta y 31 la baja, topando en 8 y en 1: es
    ; `increase/decrease_movement_frequence`. De ella salen los cuadros quieto
    ; tras cada orden, así que se lee de `ruta_frec` y no de otro lado.
    ;
    ; Con la 1 la espera tras un paso son 256 cuadros y no entran en el byte de
    ; `ruta_tras_paso`; que no se llegue lo garantiza el conversor, que rechaza
    ; la ruta entera. Acá se topa igual en 1, como RM2k: topar distinto sería
    ; que los dos lados se equivoquen igual el día que ese guard falle.
    and #$01
    bne frec_menos
    lda ruta_frec
    cmp #RUTA_FRECUENCIA
    bcs frec_listo
    inc ruta_frec
    bra frec_listo
frec_menos:
    lda ruta_frec
    cmp #2
    bcc frec_listo
    dec ruta_frec
frec_listo:
    jmp otra_orden
face:
    sec
    sbc #12
    sta hero_dir                ; face_*: con la frecuencia 8 es instantáneo y
    lda ruta_frec               ; sigue el que viene; con otra, se queda
    jsr tras_giro               ; quieto los cuadros del giro
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_espera
    jmp listo

; `change_graphic` **sobre el héroe**: la 34 con su operando, el índice del
; gráfico en la tabla del mapa, igual que sobre un evento.
;
; Sale barata porque las dos tablas de poses tienen la misma forma: una entrada
; de `npc_poses` son doce punteros de tres bytes a las poses del personaje, y
; los doce que la tabla de actores le da al líder están escritos igual. O sea
; que alcanza con apuntar `hero_poses` treinta y seis bytes adentro de
; `npc_poses` y `place_hero` sigue sin enterarse.
;
; Dos cosas que **no** se hacen y que son lo que costaría de más:
;
; * `hero_cgram` se apaga. Los quince colores del líder los sube
;   `aplicar_tinte` **en la fila que dice `hero_pal`**, así que dejarlo puesto
;   con la paleta nueva le escribiría los colores de Talan encima a la paleta
;   del gráfico al que se cambió. Mientras el cambio está puesto, el héroe se
;   dibuja con la paleta del gráfico nuevo, que ya vive en CGRAM con el resto
;   de los sprites del mapa.
; * No sobrevive al cambio de mapa: `elegir_grafico_heroe` corre al cargar y lo
;   repone. No es pereza —las poses viven en el banco de sprites **del mapa**,
;   así que el gráfico de allá no existe acá—, y la referencia lo repone igual.
;   La página del `EV0047` del mapa 8, que es la que pidió todo esto, cambia a
;   `Crown7` justo antes de teletransportarse y vuelve a `Future1` justo
;   después, así que en el juego no se nota.
grafico_heroe:
    lda #$FF
    sta hero_pose_vram          ; la pose que hay en VRAM ya no es la suya
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i                  ; el operando ya está consumido
    jsr hero_poses_de_grafico
    bcc heroe_sin_grafico
    jmp otra_orden
heroe_sin_grafico:
    ; Un CharSet sin un solo pixel opaco —`nobodyhere`— o uno que no entró en
    ; las ocho paletas de sprite: el héroe deja de dibujarse, que es lo que
    ; `place_hero` hace con el puntero de poses en cero y lo mismo que le pasa
    ; a un evento con la fila escondida.
    stz hero_poses + 2
    stz hero_cgram + 2
    jmp otra_orden


mover:
    ; Acá no llegan las diagonales: el conversor rechaza la página que le dé
    ; una al héroe —ver MOVE_EVENT en `eventos.traducir`— porque la ROM sólo
    ; las camina sobre eventos, y ninguna de las 26 rutas del juego que las
    ; usan es del héroe. Sin ese corte, el descarte de abajo mandaría al héroe
    ; hacia la izquierda.
    sta hero_dir                ; move_* mira hacia donde va
    ; Atravesando paredes las dos caras dan que sí. Es el
    ; `if (self.GetThrough()) return true;` de `Game_Map::CheckOrMakeWayEx`, y
    ; se prende sólo alrededor de este paso: `can_leave` y `can_enter` los usa
    ; también la caminata con el pad, que no lo mira.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    lda hero_dir
    cmp #DIR_UP
    bne no_es_arriba
    jsr try_up
    jmp ver_si_arranco
no_es_arriba:
    cmp #DIR_RIGHT
    bne no_es_derecha
    jsr try_right
    jmp ver_si_arranco
no_es_derecha:
    cmp #DIR_DOWN
    bne no_es_abajo
    jsr try_down
    jmp ver_si_arranco
no_es_abajo:
    jsr try_left
ver_si_arranco:
    stz atravesando
    stz atravesando + 1
    lda step_left
    bne arranco                 ; bloqueado: se saltea y se prueba el siguiente
    jmp otra_orden
arranco:
    ; El paso arrancó, y queda anotado que lo arrancó la ruta: `hay_rutas` lo
    ; necesita para saber que el último paso de una ruta todavía cuenta.
    lda #1
    sta ruta_paso
listo:
    rts
velocidad:
    ; `increase_movement_speed` y `decrease_movement_speed`, topadas en 6 y 1
    ; como `MoveRouteSpeedUp`. Sobre el héroe la ROM las ignoraba; ahora
    ; cambian el paso, y lo cambian para siempre: RM2k repone la frecuencia al
    ; terminar la ruta y la velocidad no.
    cmp #29
    beq vel_menos
    jsr hero_vel_leer
    cmp #6
    bcs vel_guardar
    inc a
    bra vel_guardar
vel_menos:
    jsr hero_vel_leer
    cmp #2
    bcc vel_guardar
    dec a
vel_guardar:
    jsr hero_vel_escribir
    jmp otra_orden
.endproc

; Si queda alguna ruta forzada sin terminar, la del héroe incluida. Devuelve A
; distinto de cero si la hay. Es `Game_Map::IsAnyMovePending`, que es a lo que
; espera `ProceedWithMovement`.
;
; Del héroe cuentan dos cosas, y la segunda no es obvia: que le queden órdenes,
; y que tenga un paso en curso **que haya arrancado la ruta**. Lo segundo hace
; falta porque el último paso de una ruta sigue siendo la ruta aunque ya no
; queden órdenes —sin eso la página seguiría ocho cuadros antes de tiempo—, y
; tiene que ser sólo el de la ruta porque, terminada ésta, el jugador puede
; ponerse a caminar mientras otra ruta sigue corriendo, y un paso del pad no es
; una ruta pendiente.
.proc hay_rutas
.a8
.i16
    lda ruta_espera
    bne si                      ; el héroe está en medio de un `wait`
    lda ruta_i
    cmp ruta_n
    bcc si                      ; al héroe le quedan órdenes
    lda ruta_paso
    beq de_eventos
    lda step_left
    bne si                      ; y el paso que está dando es de la ruta

de_eventos:
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    lda ruta_ev + 18, x
    and #$01
    bne siguiente               ; la ruta propia de la página no se espera
    lda ruta_ev + 7, x          ; un paso en curso
    bne si
    lda ruta_ev + 9, x          ; o una espera
    bne si
    lda ruta_ev + 13, x         ; o un salto
    bne si
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc si                      ; le quedan órdenes
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc otra
    lda #0
    rts
si:
    lda #1
    rts
.endproc

; Enciende o apaga el switch de temp según A.
;
; **Pisa X e Y**, y quien llama desde el intérprete tiene que salvar Y, que es el
; cursor del bytecode: por eso el `phy`/`ply` de `op_switch`. Sin él el lazo de
; `correr_codigo` sigue leyendo desde el byte que quedó en Y —un desplazamiento
; de la tabla de switches— así que la página se corta en su primer comando y el
; evento no hace nada. Las dos páginas del juego que hacen algo arrancan
; prendiendo switches, así que el síntoma es "ninguna página corre" y no "esta
; página falla".
.proc poner_switch
.a8
.i16
    pha
    rep #$20
.a16
    lda temp
    and #$0007
    tax
    lda temp
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
.a8
    pla
    beq apagar
    lda switches, y
    ora f:mascara, x
    sta switches, y
    lda #1
    sta refresco                ; las páginas que lo piden pueden cambiar
    rts
apagar:
    lda f:mascara, x
    eor #$FF
    and switches, y
    sta switches, y
    lda #1
    sta refresco
    rts
.endproc

; Deja en A1T0L/A1B0 el puntero de 24 bits que el registro del mapa guarda en el
; campo que venga en Y. Los tres bytes del puntero están seguidos, así que la
; parte baja sale de una lectura de 16 bits y el banco de la de al lado.
; La cuenta va con el acumulador en 16 bits de punta a punta. Hacerla en 8 y
; después `tax` no sirve: el acumulador del 65816 son 16 bits siempre, y `tax`
; con X ancho transfiere los dos bytes, incluido el alto que quedó de la
; operación anterior. Con el mapa 7 daba cero de casualidad para los tiles y
; basura para la paleta.
.proc dma_origen
.a8
.i16
    rep #$20
.a16
    tya                         ; el desplazamiento del campo
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta A1T0L
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta A1B0
    rts
.endproc

.proc load_map
.a8
.i16
    ldx mapa_ofs
    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_TILES, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_MAP_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 64 bytes por tile de 8 bits
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- la animación del ChipSet ---
    ; El mapa trae en la VRAM el dibujo 0 de cada corrida y el reloj puede estar
    ; en cualquier otro: es un reloj de la partida y no del mapa. Acá se sube el
    ; que toca, sin presupuesto de vblank porque la pantalla está apagada.
    jsr anim_cargar

    ; --- los colores ---
    ;
    ; Primero lo de abajo, que es de toda la ROM y no de este mapa: el color de
    ; fondo de la pantalla y la paleta de la ventana de mensaje. Va acá y no en
    ; `load_ventana` porque `load_ventana` se saltea entera cuando la ROM no
    ; lleva ventana, y el color de fondo hace falta igual.
    stz CGADD
    rep #$20
.a16
    lda #.loword(ventana_cgram)
    sta A1T0L
    lda #(CGRAM_BASE * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_cgram
    sta A1B0
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; Y encima el mapa, que arranca donde termina lo reservado.
    lda #CGRAM_BASE
    sta CGADD
    ldy #M_PTR_MAP_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    asl a                       ; dos bytes por color
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; El tilemap no se sube acá: no existe uno entero para subir. Lo arma
    ; fill_window a partir de los bloques, y desde ahí lo mantiene el streaming.
    rts
.endproc

; --- los sprites -----------------------------------------------------------
.proc load_sprite
.a8
.i16
    ; El banco que sube acá trae una pose por ranura. La cola de subidas
    ; arranca vacía, y la pose del héroe en VRAM es la que puso el conversor
    ; —mirando abajo— salvo que mire a otro lado: `place_hero` lo resuelve en
    ; el primer cuadro, con la pantalla todavía apagada.
    stz vq_n
    lda #$FF
    sta hero_pose_vram
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_SPRITE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_SPRITE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por tile de 4 bits
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; La paleta va a la mitad de arriba de CGRAM, que es la de los sprites: la
    ; 8 arranca en el color 128.
    lda #128
    sta CGADD
    ldy #M_PTR_SPRITE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    lda f:mapa_tabla + M_OBSEL_VALUE, x
    sta OBSEL
    rts
.endproc

; --- OAM -------------------------------------------------------------------
; Todos los objetos arrancan escondidos. Un objeto de 32 de alto en la fila 224
; ocupa de la 224 a la 255, o sea entero fuera de las 224 que se ven, y sin
; darle la vuelta al contador.
.proc clear_oam
.a8
.i16
    ldx #$0000
borrar:
    lda #$E0
    sta oam + 1, x              ; la Y de cada objeto
    inx
    inx
    inx
    inx
    cpx #512
    bne borrar

    ; La tabla chica: dos bits por objeto, el alto dice si es grande. Sólo el
    ; objeto 0 lo es; el resto quedan chicos y escondidos igual.
    ldx #$0000
chica:
    stz oam_high, x
    inx
    cpx #32
    bne chica
    lda #$02
    sta oam_high                ; objeto 0: tamaño grande
    rts
.endproc

.proc push_oam
.a8
.i16
    stz OAMADDL
    stz OAMADDL + 1
    ldx #.loword(oam)
    stx A1T0L
    lda #^oam
    sta A1B0
    ldy #544                    ; los 512 de la tabla grande más los 32 chicos
    sty DAS0L
    lda #$00
    sta DMAP0
    lda #$04
    sta BBAD0                   ; destino: OAMDATA
    lda #$01
    sta MDMAEN
    rts
.endproc

; --- las poses en caliente ---------------------------------------------------
; En VRAM vive una pose por personaje: el héroe en el bloque 0 y cada NPC que
; camina en su ranura. Las doce poses de cada uno están en el cartucho, y
; cuando alguien quiere dibujarse con otra, la encola acá y sube en el vblank
; que viene, en el mismo `flush_video` que sube la OAM que ya cuenta con ella.
; Es lo que hacen los RPG de la consola con más de dos personajes animados:
; con todas las poses residentes, 512 tiles son dos personajes y medio.
;
; Encola la pose que está en `vq_src` (24 bits, en el cartucho) para la
; ranura que arranca en la palabra `vq_dest`. Devuelve A distinto de cero si
; entró; si la cola está llena, quien llama tiene que volver a pedirla.
.proc vram_encolar
.a8
.i16
    lda vq_n
    cmp #VQ_MAX
    bcc hay_lugar
    lda #0
    rts
hay_lugar:
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; por cinco
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda vq_src
    sta vq + 0, x
    lda vq_src + 1
    sta vq + 1, x
    lda vq_src + 2
    sta vq + 2, x
    lda vq_dest
    sta vq + 3, x
    lda vq_dest + 1
    sta vq + 4, x
    inc vq_n
    lda #1
    rts
.endproc

; Sube hasta VQ_POR_CUADRO poses de la cola y deja las demás al principio.
; Cada pose son cuatro DMA de 128 bytes: las cuatro filas del bloque de 4x4,
; que en la grilla de nombres están a 256 palabras una de otra.
.proc vram_drenar
.a8
.i16
    lda vq_n
    bne hay
    rts
hay:
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    stz vq_hechas
    ldx #$0000                  ; la entrada, en bytes
otra:
    lda vq_hechas
    cmp vq_n
    beq fin
    cmp vq_tope
    beq fin
    lda vq + 2, x
    sta A1B0                    ; el banco del origen
    rep #$20
.a16
    lda vq + 0, x
    sta vq_src
    lda vq + 3, x
    sta vq_dest
    sep #$20
.a8
    lda #4
    sta vq_filas
fila:
    rep #$20
.a16
    lda vq_dest
    sta VMADDL
    lda vq_src
    sta A1T0L
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    lda vq_src
    clc
    adc #128
    sta vq_src
    lda vq_dest
    clc
    adc #256                    ; la fila que sigue de la grilla de nombres
    sta vq_dest
    sep #$20
.a8
    dec vq_filas
    bne fila
    inc vq_hechas
    rep #$20
.a16
    txa
    clc
    adc #VQ_STRIDE
    tax
    sep #$20
.a8
    bra otra
fin:
    ; Lo que no entró, al principio de la cola. X apunta a la primera entrada
    ; que quedó.
    lda vq_n
    sec
    sbc vq_hechas
    sta vq_n
    beq listo
    sta temp + 2
    asl a
    asl a
    clc
    adc temp + 2                ; los bytes que quedan: entradas por cinco
    sta temp + 2
    ldy #$0000
mover:
    lda vq, x
    sta vq, y
    inx
    iny
    dec temp + 2
    bne mover
listo:
    rts
.endproc

; --- la capa que va por encima del héroe -----------------------------------
; Sus tiles y su paleta se suben una sola vez, con la pantalla apagada. Su
; tilemap no: va en la misma ventana móvil que el del fondo, y lo llena el
; streaming.
.proc load_above
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_ABOVE, x
    sta VMADDL
    sep #$20
.a8
    ldy #M_PTR_ABOVE_TILES
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_TILES, x
    asl a
    asl a
    asl a
    asl a
    asl a                       ; son de 4 bits: 32 bytes por tile
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Su paleta va en las últimas paletas de la mitad baja de CGRAM, que el
    ; fondo de 8 bits deja libres. Cuántas y desde dónde lo decidió el
    ; conversor mapa por mapa, así que viene en el registro.
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    sta CGADD
    ldy #M_PTR_ABOVE_CGRAM
    jsr dma_origen
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    asl a
    sta DAS0L
    sep #$20
.a8
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; La tabla de NPCs a la RAM, que es de donde build_oam la lee.
;
; Con un lazo y no con un DMA: para llegar a la WRAM el DMA tiene que pasar por
; el puerto $2180 y dejar la dirección puesta en $2181-$2183, que son tres
; registros más que acordarse de cargar. Son mil bytes como mucho y esto corre
; una vez por mapa, así que el lazo no le cuesta nada a nadie y no puede
; escribir en el lugar equivocado.
.proc load_npcs
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_NPC_TABLE
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x           ; los 16 bits bajos del puntero
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x       ; y su banco
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; por dieciséis: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "la cuenta de arriba multiplica por dieciséis a mano"
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq listo
    lda [npc_ptr], y
    sta npc_buf, y
    iny
    bra copiar
listo:
    rts
.endproc

; Y la tabla de gráficos de la orden 34, con el mismo lazo y el mismo puntero
; prestado. Son dieciséis bytes como mucho.
.proc load_ruta_graficos
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_RUTA_GRAFICO
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_RUTA_GRAFICO_COUNT, x
    asl a                       ; dos bytes por gráfico
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq listo
    lda [npc_ptr], y
    sta ruta_graf_buf, y
    iny
    bra copiar
listo:
    rts
.endproc

; La tabla de posiciones de eventos a la RAM, y las rutas que hubiera corriendo
; a la basura.
;
; Lo segundo es lo que hace RM2k al cambiar de mapa: las rutas forzadas son de
; los eventos del mapa que se deja, y allá no queda nadie caminando.
;
; Reusa `npc_ptr`, que sólo vive mientras se copia una tabla y nunca las dos a
; la vez.
.proc load_ev_pos
.a8
.i16
    rep #$20
.a16
    lda #M_PTR_EV_POS
    clc
    adc mapa_ofs
    tax
    lda f:mapa_tabla, x           ; los 16 bits bajos del puntero
    sta npc_ptr
    sep #$20
.a8
    lda f:mapa_tabla + 2, x       ; y su banco
    sta npc_ptr + 2

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_EV_COUNT, x
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    sta temp
    sep #$20
.a8
    ldy #$0000
copiar:
    cpy temp
    beq tablas
    lda [npc_ptr], y
    sta ev_pos_buf, y
    iny
    bra copiar

tablas:
    stz ruta_ev_tope            ; ninguna ranura usada todavía en este mapa
    ldx #$0000
libre:
    lda #RUTA_EV_LIBRE
    sta ruta_ev, x
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc libre

    ; Y los destellos, que también son de los eventos del mapa que se deja.
    ldx #$0000
sin_flash:
    lda #FLASH_LIBRE
    sta flash_ev, x
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc sin_flash
    stz flash_pend              ; la RAM arranca con basura y esto se lee
    stz ruta_paso
    rts
.endproc

; --- las rutas forzadas de los eventos --------------------------------------
;
; Un evento con ruta forzada camina como el héroe: girar no consume cuadro,
; esperar sí, y moverse arranca un paso de una celda que dura CUADROS_POR_CELDA.
; La diferencia con el héroe es que su posición vive en celdas y no en pixeles,
; y que —por ahora— no se dibuja: las rutas que compilan son sobre eventos sin
; gráfico. Lo único que se ve de ellas es cuánto tardan, que es lo que espera
; `ProceedWithMovement`.

; Le da una ruta al evento `ruta_blanco - 1`: busca su ranura, y si no la tiene
; agarra una libre. Pisar la que ya tenía es lo correcto —RM2k sobrescribe la
; ruta forzada anterior, no la encadena— y si no hay ninguna libre la ruta se
; descarta, que es preferible a escribir al lado de la tabla.
;
; Lo que se conserva al pisarla es lo que `ForceMoveRoute` conserva: el paso o
; el salto en curso se terminan, hacia dónde mira queda, y atravesar paredes y
; la animación parada siguen como estaban. Se cortan la espera —la primera
; orden corre ya— y las órdenes. Antes se reseteaba la ranura entera, y el
; evento volvía a mirar adonde decía su página hasta que la ruta nueva lo
; girara: era el centinela que dejaba afuera a `face_hero`.
;
; Entra con Y apuntando a la primera orden dentro del bytecode.
.proc ruta_para_evento
.a8
.i16
    phy
    lda ruta_blanco
    dec a
    jsr giro_por_ruta           ; con ruta, adónde mira lo decide ella
    ply
    lda ruta_blanco
    dec a
    sta temp                    ; el índice del evento

    ; Primero la ranura que ya sea suya, y si no una libre. Las dos búsquedas
    ; estaban copiadas acá y son exactamente `ranura_del_evento` y
    ; `ranura_libre`: llamarlas ahorra banco 0 y, la primera, se lleva de
    ; regalo el tope de `ruta_ev_tope`.
    lda temp
    jsr ranura_del_evento
    cpx #$FFFF
    bne reusada
    jsr ranura_libre
    cpx #$FFFF
    bne puesta
    rts                         ; no hay lugar: la ruta se pierde

puesta:
    lda temp
    sta ruta_ev + 0, x
    stz ruta_ev + 6, x
    stz ruta_ev + 7, x          ; sin paso en curso
    stz ruta_ev + 22, x
    stz ruta_ev + 23, x
    lda #RUTA_EV_SIN_MIRAR
    sta ruta_ev + 8, x          ; mira adonde diga su página hasta que gire
    stz ruta_ev + 12, x         ; sin banderas
    stz ruta_ev + 13, x         ; ni salto
    lda #1
    sta ruta_ev + 10, x         ; el frame del medio, como `animate_hero`
    stz ruta_ev + 11, x
    stz ruta_ev + 18, x
    stz ruta_ev + 27, x         ; sin página a la que volver
    rep #$20
.a16
    lda #$FFFF
    sta ruta_ev + 20, x
    sep #$20
.a8
    ; A la velocidad de la página con que se dibuja, que la fila del NPC trae
    ; en +13: es la que RM2k le deja a una ruta forzada. Un evento sin fila
    ; —sin gráfico— va a la 3, la de una página por defecto.
    phy                         ; Y es el cursor del bytecode, y se necesita
    lda temp                    ; después: `npc_de_evento` lo pisa
    jsr npc_de_evento           ; Y = su fila, o $FFFF; A se pierde
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 13, y
    bra con_velocidad
sin_fila:
    lda #3
con_velocidad:
    ply
    sta ruta_ev + 17, x
    lda temp
    jsr capa_activa             ; su capa, una vez y no en cada paso
    sta ruta_ev + 31, x
reusada:
    lda ruta_ev + 18, x
    and #$FE                    ; la forzada pisa a la de página, si había
    ora #$04                    ; y lo bloqueado se saltea
    sta ruta_ev + 18, x
    ; El puntero a la primera orden: el del código más lo que Y llevaba andado.
    ; La suma no se lleva nada al byte de banco porque el bloque de código del
    ; mapa entra entero en uno —lo garantiza el acomodo de bancos del
    ; conversor, `tools/ensamblado/bancos.py`—, que es el mismo argumento que el del bloque de mensajes.
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta ruta_ev + 1, x
    sep #$20
.a8
    lda cod_ptr + 2
    sta ruta_ev + 3, x
    lda ruta_cuantas
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x          ; recién empieza
    stz ruta_ev + 9, x          ; y sin espera en curso: la primera orden corre ya
    lda ruta_frec_op
    sta ruta_ev + 16, x
    rts
.endproc

; Cuántos cuadros se queda quieto un personaje después de un paso y después de
; un giro con la frecuencia que trae A. Es el contador de parada de RM2k
; —`SetMaxStopCountForStep` y `ForTurn`— y con la 8 los dos dan cero, que es
; por lo que "girar es gratis y los pasos van seguidos" era exacto sin saberlo.
; Las tablas las emite el conversor con las mismas funciones que usa la
; referencia. Usan Y y no X, porque X es la ranura de quien pregunta.
.proc tras_paso
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_paso, y
    rts
.endproc

.proc tras_giro
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_giro, y
    rts
.endproc

; Hacia dónde mira quien está en (celda_x, celda_y) para encarar al héroe. Es
; `GetDirectionToCharacter`: manda el eje con más distancia y en empate el
; vertical; sobre la misma celda, o con el héroe más abajo, mira abajo.
; Devuelve la dirección en A.
.proc hacia_el_heroe
.a8
.i16
    rep #$20
.a16
    lda celda_x
    sec
    sbc tile_x
    sta temp                    ; sx, con signo: positivo es "el héroe está a la izquierda"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_a                   ; |sx|
    lda celda_y
    sec
    sbc tile_y
    sta temp + 2                ; sy: positivo es "el héroe está más arriba"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_b                   ; |sy|
    lda cmp_a
    cmp cmp_b
    beq vertical
    bcc vertical                ; |sx| <= |sy|: manda el eje vertical
    sep #$20
.a8
    lda temp + 1                ; el signo de sx
    bmi derecha
    lda #DIR_LEFT
    rts
derecha:
    lda #DIR_RIGHT
    rts
vertical:
.a16
    sep #$20
.a8
    lda temp + 3                ; el signo de sy
    bmi abajo
    lda temp + 2
    ora temp + 3
    beq abajo                   ; la misma celda: abajo
    lda #DIR_UP
    rts
abajo:
    lda #DIR_DOWN
    rts
.endproc

; Un cuadro de todas las rutas de eventos que estén corriendo.
.proc mover_eventos
.a8
.i16
    stz rutas_movieron
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    ; El que ya dio su paso pegado a su intérprete paralelo no lo da otra vez:
    ; la marca se consume acá, así que dura un cuadro. Ver `un_paralelo`.
    lda ruta_ev + 18, x
    and #$40
    beq no_movido
    lda ruta_ev + 18, x
    and #$BF
    sta ruta_ev + 18, x
    bra siguiente
no_movido:
    phx
    jsr cuadro_de_ruta_ev
    plx
    phx
    jsr animar_ruta_ev
    plx
    phx
    jsr refrescar_npc
    plx
    lda #1
    sta rutas_movieron
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc otra
    ; De acá en adelante el que se mueve es el héroe otra vez.
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    rts
.endproc

; Un cuadro de la ruta de la ranura que apunta X. Es el mismo programa que
; `paso_de_ruta` para el héroe, y por eso las dos hacen lo mismo con las mismas
; órdenes: si acá se contara distinto, una ruta terminaría en otro cuadro que en
; la referencia y `ProceedWithMovement` soltaría la página cuando no toca.
; Los saltos de acá adentro van con `jmp` y no con `bra`, por lo mismo que en
; `paso_de_ruta`: el cuerpo creció y los 127 bytes de alcance se quedaron cortos.
.proc cuadro_de_ruta_ev
.a8
.i16
    stz ruta_ev + 6, x
    lda ruta_ev + 18, x
    and #$DF                    ; la recarga de `repeat`, una por cuadro
    sta ruta_ev + 18, x
    lda ruta_ev + 7, x
    beq sin_paso
    ; El paso avanza lo que dice la velocidad, de 256 por celda; +7 sólo dice
    ; que hay uno en curso.
    jsr paso_de_ranura
    rep #$20
.a16
    lda ruta_ev + 22, x
    sec
    sbc temp
    bcs no_negativo
    lda #0
no_negativo:
    sta ruta_ev + 22, x
    sep #$20
.a8
    bne moviendo
    stz ruta_ev + 7, x          ; el paso terminó en este cuadro
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc con_ordenes
    lda ruta_ev + 18, x         ; sin órdenes: sólo la de página que se repite
    and #$03                    ; sigue esperando
    cmp #$03
    bne moviendo
con_ordenes:
    lda ruta_ev + 16, x
    jsr tras_paso
    sta ruta_ev + 9, x
moviendo:
    lda #1
    sta ruta_ev + 6, x
    rts
sin_paso:
    lda ruta_ev + 13, x
    beq sin_salto
    jsr salto_de_ranura
    sta temp
    lda ruta_ev + 13, x
    sec
    sbc temp
    bcs guardar_salto
    lda #0
guardar_salto:
    sta ruta_ev + 13, x
    rts
sin_salto:
    ; Y un `wait` en curso se lleva el cuadro entero, igual que el del héroe.
    lda ruta_ev + 9, x
    beq sin_espera
    dec a
    sta ruta_ev + 9, x
    rts
sin_espera:
    ; La ruta propia de la página no lee órdenes nuevas mientras el intérprete
    ; tiene una página corriendo: es el `IsRunning()` de
    ; `UpdateNextMovementAction`. El paso en curso ya se terminó arriba y las
    ; esperas siguen contando.
    lda ruta_ev + 18, x
    and #$01
    beq no_congelada
    lda ev_activo
    bne congelada
    lda esperando_n
    bne congelada
no_congelada:
    ; El puntero de la ruta a la página directa, que es de donde se puede leer
    ; con `[ptr], y`.
    rep #$20
.a16
    lda ruta_ev + 1, x
    sta ruta_ptr
    sep #$20
.a8
    lda ruta_ev + 3, x
    sta ruta_ptr + 2

otra_orden:
    lda ruta_ev + 5, x          ; en cuál va
    cmp ruta_ev + 4, x          ; cuántas trae
    bcc hay_orden
    ; Se acabaron las órdenes. La de página que se repite vuelve al principio
    ; en el mismo cuadro, y una sola vez por cuadro —el `current_index ==
    ; start_index` de `UpdateMoveRoute`—; y una forzada que termina sobre un
    ; evento con ruta propia le devuelve la suya, desde el principio.
    lda ruta_ev + 18, x
    and #$23
    cmp #$03
    bne no_repite
    stz ruta_ev + 5, x
    lda ruta_ev + 18, x
    ora #$20
    sta ruta_ev + 18, x
    jmp otra_orden
no_repite:
    lda ruta_ev + 18, x
    and #$01
    bne congelada               ; la de página, terminada: listo
    lda ruta_ev + 27, x
    beq congelada               ; sin página a la que volver
    jsr retomar_pagina
congelada:
    jmp listo
hay_orden:
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x

    cmp #23                     ; wait: éste y los RUTA_ESPERA - 1 que siguen,
    bne no_es_wait              ; más los del giro si la frecuencia es baja
    lda ruta_ev + 16, x
    jsr tras_giro
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_ev + 9, x
    jmp listo
no_es_wait:
    cmp #12
    bcs no_mueve
    cmp #9
    bne :+
    ; `move_towards_hero`. No es una orden aparte sino las dos que ya están
    ; pegadas: `UpdateMoveRoute` hace `TurnTowardCharacter(hero)` y después
    ; `Move(GetDirection())`, o sea la 21 y un `move_*` en el mismo cuadro.
    ; Por eso sale la dirección de acá y cae en `mover` sin tocar nada más:
    ; el giro, el paso y lo que cuesta son los de siempre.
    ; `hacia_el_heroe` no pisa X, que es la ranura.
    jsr celda_del_evento
    jsr hacia_el_heroe
:   jmp mover                   ; 0..3 son los move_*, y la 9 ya trae la suya
no_mueve:
    cmp #16
    bcs :+
    jmp face                    ; 12..15 son los face_*; queda lejos
:
    cmp #21
    bne no_encara
    ; face_hero: la celda del evento contra la del héroe, y a `mirar` con la
    ; dirección en A.
    jsr celda_del_evento
    jsr hacia_el_heroe
    jmp mirar
no_encara:
    ; Girar sin moverse no se compila: acá no llega.
    cmp #24
    bne no_es_salto
    jsr preparar_movil          ; quién salta, para chocar con los demás
    lda ruta_ev + 5, x
    dec a
    sta salto_orden             ; dónde está el 24, por si hay que volver
    jsr armar_salto_ev
    lda ruta_ev + 13, x
    bne salto_arranco
    ; No se pudo caer ahí. Con la ruta salteable el salto se saltea; sin eso
    ; RM2k vuelve el cursor al `begin_jump` y corta el cuadro —`current_index
    ; = saved_index`—, y el salto se reintenta cuadro a cuadro hasta que la
    ; celda se libere. Sin `end_jump` no hay a qué volver: se saltea siempre.
    lda salto_trabado
    beq saltear
    lda ruta_ev + 18, x
    and #$04
    bne saltear
    lda salto_orden
    sta ruta_ev + 5, x
    jmp listo
saltear:
    jmp otra_orden
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    beq seguir
    cmp #26
    bcc seguir                  ; los demás no hacen nada
    cmp #32
    bcc fijar_o_velocidad       ; 26 y 27 la mirada, 28 y 29 la velocidad,
    cmp #34                     ; 30 y 31 la frecuencia
    bne no_es_grafico           ; y la 34 el gráfico, que lleva operando
    jmp cambiar_grafico         ; queda lejos para un salto corto
no_es_grafico:
    cmp #36
    bcc seguir
    cmp #38
    bcs anim
    ; 36 prende atravesar y 37 lo apaga.
    and #$01
    eor #$01
    beq apagar_atraviesa
    lda ruta_ev + 12, x
    ora #$01
    bra guardar_banderas
apagar_atraviesa:
    lda ruta_ev + 12, x
    and #$FE
    bra guardar_banderas
anim:
    cmp #40
    bcs seguir
    ; 38 para la animación y 39 la sigue.
    cmp #38
    bne seguir_anim
    lda ruta_ev + 12, x
    ora #$02
    bra guardar_banderas
seguir_anim:
    lda ruta_ev + 12, x
    and #$FD
guardar_banderas:
    sta ruta_ev + 12, x
seguir:
    jmp otra_orden
fijar_o_velocidad:
    cmp #30
    bcs ev_frecuencia
    cmp #28
    bcs velocidad
    ; 26 fija hacia dónde mira, 27 lo suelta: `lock_facing`.
    and #$01
    beq fijar
    lda ruta_ev + 18, x
    and #$F7
    bra guardar_18
fijar:
    lda ruta_ev + 18, x
    ora #$08
    bra guardar_18
velocidad:
    ; 28 sube la velocidad y 29 la baja, entre 1 y 6.
    and #$01
    bne mas_lenta
    lda ruta_ev + 17, x
    cmp #6
    bcs seguir
    inc ruta_ev + 17, x
    bra seguir
mas_lenta:
    lda ruta_ev + 17, x
    cmp #2
    bcc seguir
    dec ruta_ev + 17, x
    bra seguir
ev_frecuencia:
    ; 30 sube la frecuencia y 31 la baja, entre 1 y 8. Ver `frecuencia` en
    ; `paso_de_ruta`, que es lo mismo para el héroe: de acá salen los cuadros
    ; quieto tras cada orden, y la 1 la rechaza el conversor.
    and #$01
    bne menos_frec
    lda ruta_ev + 16, x
    cmp #RUTA_FRECUENCIA
    bcs seguir
    inc ruta_ev + 16, x
    bra seguir
menos_frec:
    lda ruta_ev + 16, x
    cmp #2
    bcc seguir
    dec ruta_ev + 16, x
    bra seguir
guardar_18:
    sta ruta_ev + 18, x
    bra seguir

; `change_graphic`: la única orden con operando. Detrás del 34 va el índice del
; gráfico en la tabla del mapa —dos bytes por gráfico, ver `load_ruta_graficos`—
; y de ahí salen de qué personaje sacar las doce poses y con qué paleta
; dibujarlas.
;
; No cuesta un cuadro: en `UpdateMoveRoute` cae en la rama que no toca el
; contador de parada, así que la orden que sigue corre en este mismo cuadro.
; Tampoco toca la pose: el ciclo de caminata sigue donde estaba, que es lo que
; hace `SetSpriteGraphic`.
cambiar_grafico:
    lda ruta_ev + 5, x          ; el cursor ya avanzó al leer la orden
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x          ; y ahora por el operando
    asl a                       ; dos bytes por entrada
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_graf_buf, y
    sta graf_k                  ; su entrada en `npc_poses`, o $FF
    lda ruta_graf_buf + 1, y
    sta graf_pal

    lda ruta_ev + 0, x
    phx
    jsr npc_de_evento           ; su fila, que es lo que hay que cambiar
    plx
    cpy #$FFFF
    beq listo_graf              ; un evento sin gráfico no tiene fila
    lda #$FF
    sta npc_buf + 15, y         ; un CharSet no le impone nada a la celda
    lda graf_k
    cmp #$FF
    bne con_grafico
    ; Un CharSet sin un solo pixel opaco: el evento desaparece. Es lo mismo
    ; que hace `esconder_npc`, y son 185 de las 437 órdenes 34 del juego
    ; —`nobodyhere`—, así que no es el caso raro sino el más común.
    lda #0
    sta npc_buf + 14, y
    bra listo_graf
con_grafico:
    sta npc_buf + 9, y          ; de qué personaje salen sus poses
    lda npc_buf + 7, y
    and #$F1                    ; la paleta vive en los bits 1 a 3 de vhoopppN
    sta temp
    lda graf_pal
    asl a
    and #$0E
    ora temp
    sta npc_buf + 7, y
    lda #$FF
    sta npc_buf + 12, y         ; la pose que hay en la VRAM ya no es la suya
    lda #1
    sta npc_buf + 14, y         ; y se ve, por si venía escondido
listo_graf:
    jmp otra_orden
face:
    sec
    sbc #12
mirar:
    sta ruta_ev + 8, x          ; face_*: con la frecuencia 8 es instantáneo y
    lda ruta_ev + 16, x         ; sigue el que viene; con otra, se queda
    jsr tras_giro               ; quieto los cuadros del giro
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_ev + 9, x
    jmp listo


mover:
    sta ruta_dir
    stz ruta_dir + 1
    lda ruta_ev + 18, x
    and #$08
    bne sin_girar               ; mira siempre igual: `lock_facing` o el tipo
                                ; de animación de la página
    lda ruta_dir
    cmp #4
    bcc derecho                 ; los cuatro de siempre miran hacia donde van
    jsr encarar_diagonal        ; una diagonal no tiene pose propia: ver ahí
derecho:
    sta ruta_ev + 8, x          ; move_* mira hacia donde va
sin_girar:
    phx
    jsr celda_del_evento        ; deja su posición en celda_x/celda_y
    jsr preparar_movil          ; y quién es, para chocar con los demás
    lda ruta_ev + 12, x
    and #$01
    sta atravesando             ; walk_everywhere: `puede_celda` lo mira
    stz atravesando + 1
    lda ruta_dir
    cmp #4
    bcc recto
    jsr puede_celda_diag        ; las dos eles: nadie mira la celda diagonal
    bra probado
recto:
    jsr puede_celda
probado:
    plx
    stz atravesando
    stz atravesando + 1
    ; `plx` pone Z según lo que saca de la pila, así que la respuesta hay que
    ; volver a mirarla: con el `beq` pegado al `plx`, la ranura 0 —que es X = 0—
    ; daba "bloqueado" siempre y ninguna ruta se movía nunca.
    cmp #0
    bne no_bloqueado
    ; Bloqueado. Con `skippable` —las forzadas, y las de página que lo pidan—
    ; se saltea y se prueba la siguiente; sin él, la orden se reintenta el
    ; cuadro que viene, y así hasta que el paso salga.
    lda ruta_ev + 18, x
    and #$04
    beq reintenta
    jmp otra_orden
reintenta:
    dec ruta_ev + 5, x
    jmp listo
no_bloqueado:
    phx
    lda ruta_dir
    jsr mover_celda_del_evento
    plx
    lda ruta_dir
    sta ruta_ev + 30, x         ; hacia dónde va el paso, que con la mirada
    lda #1                      ; fija no es hacia donde mira
    sta ruta_ev + 7, x          ; hay un paso en curso
    jsr paso_de_ranura
    rep #$20
.a16
    lda #SALTO_PASO
    sec
    sbc temp
    sta ruta_ev + 22, x         ; y ya avanzó lo de este cuadro
    sep #$20
.a8
    lda #1
    sta ruta_ev + 6, x
listo:
    rts
.endproc

; La ruta forzada terminó sobre un evento que tiene ruta propia: vuelve la de
; la página, guardada en +24 a +29, desde el principio y con la espera del
; giro. RM2k la retoma por donde iba; acá arranca de nuevo.
.proc retomar_pagina
.a8
.i16
    lda ruta_ev + 24, x
    sta ruta_ev + 1, x
    lda ruta_ev + 25, x
    sta ruta_ev + 2, x
    lda ruta_ev + 26, x
    sta ruta_ev + 3, x
    lda ruta_ev + 27, x
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x
    lda ruta_ev + 28, x
    sta ruta_ev + 16, x
    lda ruta_ev + 29, x
    sta ruta_ev + 17, x
    lda ruta_ev + 18, x
    ora #$01
    sta ruta_ev + 18, x
    lda ruta_ev + 28, x
    jsr tras_giro
    sta ruta_ev + 9, x
    rts
.endproc

; La posición del evento de la ranura X, a celda_x/celda_y.
.proc celda_del_evento
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tay
    lda ev_pos_buf, y
    sta celda_x
    lda ev_pos_buf + 2, y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; Y la mueve una celda en la dirección que trae A. Se hace al **empezar** el
; paso, no al terminarlo: es lo que hace `begin_step` con el héroe, y contarlo
; distinto dejaría a los dos lados con la celda cambiada en cuadros distintos.
; Pone la celda del evento de la ranura X en `celda_x`, `celda_y`. Lo usa el
; salto, que la mueve de una en vez de de a un paso.
.proc mover_celda_a_evento
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    rts
.endproc

.proc mover_celda_del_evento
.a8
.i16
    sta ruta_dir
    stz ruta_dir + 1            ; se usa como índice de dieciséis
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    sep #$20
.a8
    ; Por tabla y no por cuatro comparaciones: con las diagonales la celda se
    ; corre en los dos ejes a la vez, y así el caso derecho es el que tiene un
    ; cero de un lado. X queda pisado; el que llama ya lo guardó.
    ldx ruta_dir
    lda f:paso_dx, x
    beq sin_dx
    jsr con_signo_16
.a16
    clc                         ; vuelve con el acumulador en dieciséis
    adc ev_pos_buf + 0, y
    sta ev_pos_buf + 0, y
    sep #$20
.a8
sin_dx:
    lda f:paso_dy, x
    beq sin_dy
    jsr con_signo_16
.a16
    clc
    adc ev_pos_buf + 2, y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
sin_dy:
    rts
.endproc

; El byte con signo que trae A, extendido a dieciséis bits. Sale con el
; acumulador **en dieciséis**, que es donde lo quieren los que suman celdas.
.proc con_signo_16
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc listo
    ora #$FF00
listo:
    rts
.endproc

; --- la tecla de acción -----------------------------------------------------
;
; Hablarle a algo. Es lo que convierte a esto en un juego y no en una cinemática:
; de las 1599 páginas de este juego que se disparan así, 1006 ya compilan, contra
; 110 automáticas.
;
; La regla sale de `Game_Player::CheckActionEvent`: se mira la celda del héroe y
; después la de adelante. Lo que allá va antes —los eventos que se disparan al
; tocarlos— todavía no está, y el lazo de hasta tres mostradores tampoco.

; ¿Hay un evento en (celda_x, celda_y)? Devuelve su índice en A, o $FF.
.proc evento_en_celda
.a8
.i16
    ldy #$0000
    ldx #$0000
buscar:
    cpx ev_total
    beq no_hay
    rep #$20
.a16
    lda ev_pos_buf, y
    cmp celda_x
    bne siguiente
    lda ev_pos_buf + 2, y
    cmp celda_y
    bne siguiente
    sep #$20
.a8
    txa                         ; el índice cabe en un byte: EV_MAX es 128
    rts
siguiente:
.a16                            ; se llega en dieciséis, del `bne` de arriba
    tya
    clc
    adc #EV_STRIDE
    tay
    sep #$20
.a8
    inx
    bra buscar
no_hay:
    lda #$FF
    rts
.endproc

; Encola la página activa del evento `ev_buscado` si la dispara la tecla de
; acción. Devuelve A distinto de cero si encoló algo.
;
; Es la misma regla de selección que `encolar_eventos` —gana la de número más
; alto que cumpla sus condiciones— pero para un evento solo, y sin tocar el
; cursor de la cola de los automáticos.
; La página activa del evento `ev_buscado`, a `elegida`. Sin mirar el trigger:
; quien llama decide qué hacer con ella. Es la misma regla de siempre —gana la
; de número más alto cuyas condiciones se cumplen— y se resuelve **en el
; momento de usarla**, no cuando se marcó el evento, que es lo que hace
; `Game_Map::Update` al empujar el evento que estaba esperando.
.proc buscar_pagina_de_evento
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PAGINA_COUNT, x
    beq sin_paginas
    sta pag_restan
    lda f:mapa_tabla + M_PTR_PAGINAS, x
    sta pag_ptr
    stz pag_ofs
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PAGINAS + 2, x
    sta pag_ptr + 2
    stz elegida_hay

recorrer:
    jsr leer_pagina
    rep #$20
.a16
    lda pg_evento
    cmp ev_buscado
    sep #$20
.a8
    bne siguiente               ; no es el evento que estamos mirando
    jsr condiciones_ok
    beq siguiente
    lda pg_trigger
    sta elegida_trigger
    lda pg_capa
    sta elegida_capa
    rep #$20
.a16
    lda pg_cod
    sta elegida
    sep #$20
.a8
    lda pg_cod + 2
    sta elegida + 2
    lda #1
    sta elegida_hay
    ; Y su giro, el +30 y el +31: ver `giro_disparar` y `giro_revisar`.
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #30
    tay
    sep #$20
.a8
    lda [pag_ptr], y
    sta f:ELEG_K
    iny
    lda [pag_ptr], y
    sta f:ELEG_POSE

siguiente:
    rep #$20
.a16
    lda pag_ofs
    clc
    adc #PAGINA_BYTES
    sta pag_ofs
    dec pag_restan
    sep #$20
.a8
    bne recorrer

    rts
sin_paginas:
.a16                            ; se llega en dieciséis; el `sep` lo achica
    sep #$20
.a8
    stz elegida_hay
    rts
.endproc

; El disparo por tecla de acción o por contacto: busca la página activa del
; evento y, si es del trigger que se pide y compiló, marca al evento.
.proc encolar_por_accion
.a8
.i16
    jsr buscar_pagina_de_evento
    lda elegida_hay
    beq no
    lda elegida_trigger
    cmp trigger_buscado
    bne no
    ; La regla de capa, opuesta según qué celda se mire: la de adelante sólo
    ; dispara eventos de la capa del héroe —`CheckEventTriggerThere` pide
    ; `Layers_same`— y la propia sólo los de otra capa —`CheckEventTriggerHere`
    ; pide `!= Layers_same`—. No es simetría de adorno: un evento de la capa del
    ; héroe le cierra el paso, así que nunca se podría parar encima.
    ;
    ; Sólo para la tecla de acción; el contacto tiene su regla y se resuelve al
    ; compilar.
    lda trigger_buscado
    cmp #TRIGGER_ACCION
    bne sin_capa
    lda elegida_capa
    cmp #HERO_LAYER
    beq era_del_heroe
    lda accion_propia
    beq no                      ; otra capa, pero se está mirando adelante
    bra sin_capa
era_del_heroe:
    lda accion_propia
    bne no                      ; la del héroe, pero se está mirando la propia
sin_capa:
    lda elegida
    ora elegida + 1
    ora elegida + 2
    beq no                      ; la página activa no se pudo compilar
    ldx ev_buscado
    jsr marcar_esperando
    jsr giro_disparar           ; y se da vuelta hacia el héroe, si gira
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; La celda que trae (celda_x, celda_y): si hay un evento y su página activa la
; dispara la tecla, se encola. Devuelve A distinto de cero si encoló.
.proc accion_en_celda
.a8
.i16
    jsr evento_en_celda
    cmp #$FF
    beq no
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jmp encolar_por_accion
no:
    lda #0
    rts
.endproc

; El evento de contacto de la celda donde el héroe acaba de pararse.
;
; Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`. Las puertas
; son un caso particular de esto —un teletransporte en una página de contacto— y
; se atienden antes, aparte: si hubo puerta, el mapa ya cambió y acá no queda
; nada que mirar.
; Con una página corriendo **también** se mira, y la página que dispare va a
; la cola detrás de la que está corriendo: en RM2k `UpdateMovement` no pregunta
; por el intérprete, `ScheduleForegroundExecution` deja al evento esperando y
; `Game_Map` lo arranca cuando el intérprete se desocupa. Acá había un guard
; que descartaba el contacto en ese caso, escrito para el pad —y para el pad
; sobra, porque `move_hero` no arranca un paso con una página en el frente—;
; con una ruta forzada sí pasaba: una página que manda a caminar al héroe y
; después espera terminaba con el contacto perdido. La cola es la misma que la
; de los automáticos, de a uno detrás del otro, que es lo que hace RM2k.
;
; Lo que no se modela, de ningún lado: un evento que se dispare dos veces antes
; de correr entra dos veces acá y una sola en RM2k, que lo marca con un bit.
.proc probar_contacto
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda #TRIGGER_TOCA_HEROE
    sta trigger_buscado
    jsr accion_en_celda
    ldx #TRIGGER_ACCION
    stx trigger_buscado         ; queda como lo espera la tecla de acción
    rts
.endproc

; La tecla de acción, desde el lazo principal.
.proc probar_accion
.a8
.i16
    ; Las dos celdas, en el orden de `Game_Player::CheckActionEvent`: primero la
    ; propia —`CheckEventTriggerHere`, que pide una capa distinta de la del
    ; héroe— y después la de adelante —`CheckEventTriggerThere`, que pide la
    ; suya—. La propia estuvo sin hacer hasta el 2026-09-07 y taro la encontró
    ; jugando: la puerta que sale del pad de Talan es `TalDoorTop`, de acción y
    ; capa 2, y se abre parándose encima.
    lda #TRIGGER_ACCION
    sta trigger_buscado
    lda #1
    sta accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    jsr accion_en_celda
    beq mirar_adelante
    rts                         ; encoló el de abajo del héroe
mirar_adelante:
    stz accion_propia
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    lda hero_dir
    cmp #DIR_UP
    bne no_arriba
    rep #$20
.a16
    dec celda_y
    sep #$20
.a8
    bra mirar
no_arriba:
    cmp #DIR_DOWN
    bne no_abajo
    rep #$20
.a16
    inc celda_y
    sep #$20
.a8
    bra mirar
no_abajo:
    cmp #DIR_LEFT
    bne no_izquierda
    rep #$20
.a16
    dec celda_x
    sep #$20
.a8
    bra mirar
no_izquierda:
    rep #$20
.a16
    inc celda_x
    sep #$20
.a8
mirar:
    jmp accion_en_celda
.endproc

; --- los destellos ----------------------------------------------------------
;
; RM2k destella un personaje mezclando su dibujo hacia un color durante unos
; cuadros. Acá el dibujo es una paleta de CGRAM, así que destellar es subir esa
; paleta mezclada, y apagarlo es volver a subirla como estaba.
;
; La mezcla se hace **antes** de que el color llegue a CGRAM, con las mismas
; tablas de canal que el tinte de pantalla: se arman con el tinte y el destello
; juntos, se sube la paleta del personaje, y se vuelven a armar como estaban. Así
; el camino de la paleta es uno solo y no hay dos lugares que puedan diferir.

; Guarda el destello que traen los seis operandos que siguen a Y.
.proc flash_empezar
.a8
.i16
    ldx #$0000
buscar:
    lda flash_ev, x
    cmp #FLASH_LIBRE
    beq puesta
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc buscar
    rts                         ; no hay ranura: este destello se pierde

puesta:
    lda [cod_ptr], y            ; el blanco
    sta flash_ev + 0, x
    iny
    lda [cod_ptr], y
    sta flash_ev + 1, x         ; r
    iny
    lda [cod_ptr], y
    sta flash_ev + 2, x         ; g
    iny
    lda [cod_ptr], y
    sta flash_ev + 3, x         ; b
    iny
    lda [cod_ptr], y
    sta flash_ev + 4, x         ; potencia
    iny
    lda [cod_ptr], y
    sta flash_ev + 5, x         ; cuántos cuadros
    stz flash_ev + 6, x         ; recién empieza
    rts
.endproc

; En qué paleta de sprite se dibuja el blanco que trae A, o $FF si no se
; dibuja. El héroe la lleva en `hero_pal`, ya corrida; un evento, en el byte de
; atributos de su fila.
.proc paleta_del_blanco
.a8
.i16
    cmp #$00
    bne de_evento
    lda hero_pal
    lsr a                       ; hero_pal viene corrido un lugar
    and #$07
    rts
de_evento:
    dec a
    jsr npc_de_evento
    cpy #$FFFF
    bne hay
    lda #$FF
    rts
hay:
    lda npc_buf + 7, y
    lsr a
    and #$07
    rts
.endproc

; Un cuadro de todos los destellos.
.proc flashes_tick
.a8
.i16
    ldx #$0000
otra:
    lda flash_ev, x
    cmp #FLASH_LIBRE
    beq siguiente
    phx
    jsr un_flash
    plx
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #FLASH_STRIDE
    tax
    cmp #FLASH_MAX * FLASH_STRIDE
    sep #$20
.a8
    bcc otra
    rts
.endproc

; Un cuadro del destello de la ranura X: avanza, calcula con cuánta fuerza toca
; y sube la paleta. Cuando se pasa de los cuadros que dura, la ranura se libera:
; el cuadro anterior ya la subió con fuerza cero, o sea como estaba.
.proc un_flash
.a8
.i16
    lda flash_ev + 6, x
    inc a
    sta flash_ev + 6, x
    cmp flash_ev + 5, x
    bcc todavia
    beq todavia                 ; el último cuadro va con fuerza cero
    lda #FLASH_LIBRE
    sta flash_ev + 0, x
    rts

todavia:
    ; La fuerza: potencia * (cuadros - k) / cuadros, que es la forma cerrada de
    ; la cuenta que easyrpg hace cuadro a cuadro.
    lda flash_ev + 5, x
    sec
    sbc flash_ev + 6, x
    sta WRMPYA
    lda flash_ev + 4, x
    sta WRMPYB                  ; el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL
    sep #$20
.a8
    lda flash_ev + 5, x
    sta WRDIVB                  ; el cociente tarda dieciséis
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    asl a
    asl a
    asl a                       ; el alfa de easyrpg es la fuerza por ocho
    sta flash_alfa
    jmp pintar_flash
.endproc

; Sube la paleta del blanco de la ranura X con la fuerza que ya está en
; `flash_alfa`.
.proc pintar_flash
.a8
.i16
    lda flash_ev + 0, x
    jsr paleta_del_blanco
    cmp #$FF
    beq listo                   ; no se dibuja: no hay paleta que tocar
    rep #$20
.a16
    and #$00FF
    sta flash_slot
    sep #$20
.a8
    jsr paleta_con_destello
listo:
    rts
.endproc

; Sube la paleta del personaje `flash_slot` con el tinte y el destello puestos.
; Los colores del destello salen de la ranura X.
.proc paleta_con_destello
.a8
.i16
    stx flash_ranura            ; `tabla_canal_flash` usa X para la tabla
    lda flash_ev + 1, x
    sta flash_dest
    lda tinte_r
    ldx #.loword(tabla_r)
    ldy #0                       ; el rojo de `puro`, o el verde, o el azul
    jsr tabla_canal_flash
    ldx flash_ranura
    lda flash_ev + 2, x
    sta flash_dest
    lda tinte_g
    ldx #.loword(tabla_g)
    ldy #32                       ; el rojo de `puro`, o el verde, o el azul
    jsr tabla_canal_flash
    ldx flash_ranura
    lda flash_ev + 3, x
    sta flash_dest
    lda tinte_b
    ldx #.loword(tabla_b)
    ldy #64                       ; el rojo de `puro`, o el verde, o el azul
    jsr tabla_canal_flash

    ; La paleta del personaje: dieciséis colores de dos bytes, y en CGRAM la
    ; mitad de arriba arranca en el color 128.
    rep #$20
.a16
    lda flash_slot
    asl a
    asl a
    asl a
    asl a
    asl a                       ; treinta y dos bytes por paleta
    sta temp
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_SPRITE_CGRAM, x
    clc
    adc temp
    sta tin_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_SPRITE_CGRAM + 2, x
    sta tin_ptr + 2
    rep #$20
.a16
    lda #16
    sta tin_count
    lda flash_slot
    asl a
    asl a
    asl a
    asl a                       ; dieciséis colores por paleta
    clc
    adc #128
    sep #$20
.a8
    sta tin_cgadd
    jsr armar_paleta

    ; La paleta armada se guarda aparte y se sube en el vblank que viene, no
    ; acá. Escribir CGRAM en mitad del cuadro deja la mitad de arriba de la
    ; pantalla con la paleta vieja y la de abajo con la nueva: el sprite sale
    ; con un nivel y el resto con otro, y la referencia no modela eso. Es la
    ; misma razón por la que el tinte apaga la pantalla para aplicarse.
    ldy #$0000
copiar:
    lda pal_buf, y
    sta flash_buf, y
    iny
    cpy #32
    bne copiar
    lda tin_cgadd
    sta flash_pend_cgadd
    lda #1
    sta flash_pend

    ; Y las tablas vuelven a ser las del tinte solo, que es lo que espera todo
    ; el resto. Copiando, no rehaciéndolas: ver `tablas_de_tinte`.
    jmp restaurar_tablas
.endproc

; Las tres tablas de canal del tinte, sin destello, y su copia en `puro`.
;
; La copia existe por el presupuesto de cuadro. `paleta_con_destello` corre en
; todos los cuadros mientras dura un destello y antes terminaba rehaciendo estas
; tres tablas —noventa y seis productos y noventa y seis divisiones—; ahora
; `restaurar_tablas` copia noventa y seis bytes. Y de paso `tabla_canal_flash`
; se ahorra la cuenta del tinte por entrada: la busca acá.
.proc tablas_de_tinte
.a8
.i16
    lda tinte_r
    ldx #.loword(puro)
    jsr tabla_canal
    lda tinte_g
    ldx #.loword(puro) + 32
    jsr tabla_canal
    lda tinte_b
    ldx #.loword(puro) + 64
    jsr tabla_canal
    ; fallthrough
.endproc

; Las tablas de trabajo, tal cual quedaron las del tinte solo.
.proc restaurar_tablas
.a8
.i16
    ldx #$0000
copiar:
    lda puro + 0, x
    sta tabla_r, x
    lda puro + 32, x
    sta tabla_g, x
    lda puro + 64, x
    sta tabla_b, x
    inx
    cpx #32
    bne copiar
    rts
.endproc

; Como `tabla_canal`, pero mezclando antes hacia el color del destello. A trae
; el valor del tinte, X dónde va la tabla, `flash_dest` el canal del destello y
; `flash_alfa` con cuánta fuerza.
;
; La mezcla es la de easyrpg puesta en cinco bits: `destino * a + canal *
; (255 - a)` sobre 255, con `a` el nivel por ocho —`Flash::MakeColor` y el
; `PIXMAN_OP_OVER` de `BlendBlit`—. Que el espacio sea de cinco y no de ocho es
; lo que hace que el resultado no sea el de RM2k sino el que da la misma cuenta
; con cinco bits. Es una deuda declarada, y de las que no se pueden medir con
; una comparación: hace falta una captura de EasyRPG tomada durante un destello.
;
; **Y va antes del tinte, no después.** easyrpg hace al revés —`ToneBlit` y
; después `BlendBlit`— pero allá el tono es del sprite y acá el tinte se aplica
; a la pantalla entera al final, del lado de la referencia. Con el tinte neutro
; da lo mismo; con tinte, los dos lados hacen `tinte(destello(c))` y RM2k
; `destello(tono(c))`. Es otra deuda declarada del mismo tipo que la de los
; cinco bits, y la única que se ve es en una página que tiña y destelle a la vez.
;
; **Con saturación se suma una segunda de la misma familia.** `armar_paleta`
; satura el color crudo, antes de esta mezcla, porque la saturación necesita los
; tres canales juntos y esta tabla es de a uno; la referencia satura al final,
; sobre el pixel ya destellado. O sea `hardlight(destello(saturar(c)))` contra
; `hardlight(saturar(destello(c)))`. Medido con `snes-destello` y el tinte
; `12 0 0 50 0`: 49 pixeles de 57344 en el cuadro 25, todos de un valor de 31.
; Sin destello o sin saturación no hay diferencia, y ninguna página del juego
; combina las dos cosas hoy.
.proc tabla_canal_flash
.a8
.i16
    stx temp + 2                ; dónde va la tabla
    sty puro_ofs                ; y cuál de las tres de `puro` le toca: 0, 32
                                ; o 64, que lo dice el llamador
    ldy #$0000
cada:
    ; Primero la mezcla del destello, sobre el canal crudo.
    lda #255
    sec
    sbc flash_alfa
    sta WRMPYA
    tya
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta flash_parcial
    sep #$20
.a8
    lda flash_dest
    sta WRMPYA
    lda flash_alfa
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    clc
    adc flash_parcial
    sta WRDIVL
    sep #$20
.a8
    lda #255
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    cmp #32
    bcc mezclado
    lda #31
mezclado:
    ; Y ahora el tinte, que ya está resuelto: buscar el canal mezclado en la
    ; tabla del tinte solo **es** el hard light, y saca del lazo un producto y
    ; una división por entrada.
    rep #$20
.a16
    and #$00FF
    clc
    adc puro_ofs
    tax
    sep #$20
.a8
    lda puro, x
    sta (temp + 2), y
    iny
    cpy #32
    beq fin
    jmp cada                    ; `bne` no llega: el lazo es largo
fin:
    rts
.endproc

; --- los eventos que se dibujan caminando ------------------------------------
;
; Un evento con gráfico que camina cambia de tres cosas por cuadro: dónde está
; en pixeles, qué pose le toca del ciclo, y con qué clave se ordena contra los
; demás. Las tres se escriben en su fila de la tabla de NPCs, que es de donde
; `build_oam` lee.

; Un cuadro del ciclo de caminata de la ranura X. Es `animate_hero`, letra por
; letra, y por eso las dos hacen lo mismo: la referencia usa una sola fórmula
; —`columna_de_caminata`— para el héroe y para los eventos.
.proc animar_ruta_ev
.a8
.i16
    ; `Game_Character::UpdateAnimation`, sin el giro en el lugar. +10 es el
    ; frame del ciclo, 0 a 3 —el 3 dibuja la columna 1—, y +11 cuántos cuadros
    ; lleva en él. Con la animación parada o saltando, el frame del medio.
    lda ruta_ev + 12, x
    and #$02
    bne quieta
    lda ruta_ev + 13, x
    bne quieta
    ; Los límites, por velocidad.
    lda ruta_ev + 17, x
    dec a
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda anim_parado, y
    sta temp
    lda anim_continua, y
    sta temp + 1
    ; La cuenta sube caminando, siempre con la animación continua, y quieto
    ; sólo hasta llegar al frame del medio.
    lda ruta_ev + 18, x
    and #$10
    bne suma
    lda ruta_ev + 6, x
    bne suma
    lda ruta_ev + 10, x
    and #$01
    beq suma                    ; en el frame 0 o 2 sigue hasta el del medio
    lda ruta_ev + 11, x
    inc a
    cmp temp
    bcc suma                    ; cuenta < parado - 1
    bra ver_cambio
suma:
    inc ruta_ev + 11, x
ver_cambio:
    lda ruta_ev + 11, x
    cmp temp + 1
    bcs cambia                  ; llegó a la de continua
    lda ruta_ev + 6, x
    beq listo
    lda ruta_ev + 11, x
    cmp temp
    bcc listo                   ; caminando, a la de parado
cambia:
    lda ruta_ev + 10, x
    inc a
    and #$03                    ; el ciclo son cuatro pasos
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
listo:
    rts
quieta:
    lda #1
    sta ruta_ev + 10, x
    stz ruta_ev + 11, x
    rts
.endproc

; La fila de la tabla de NPCs del evento que trae A, en Y, o $FFFF si no tiene.
; Todas las filas llevan su índice de evento, y los índices son únicos, así que
; a lo sumo matchea una. Un evento sin gráfico no tiene fila y devuelve $FFFF.
.proc npc_de_evento
.a8
.i16
    sta temp
    ldy #$0000
buscar:
    cpy npc_total
    beq no_hay
    lda npc_buf + 8, y
    cmp temp
    beq listo
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra buscar
no_hay:
    ldy #$FFFF
listo:
    rts
.endproc

; Lo que le falta a `op_place` después de escribir la celda: que el dibujo la
; siga. Entra con el índice del evento en `temp`.
;
; Si el evento tiene ranura de ruta alcanza con cortarle el paso y el salto:
; `mover_eventos` corre después en este mismo cuadro y `refrescar_npc` lo deja
; sobre la celda nueva, con la pose que venía. Si no la tiene —un evento que
; nadie mandó a caminar— no se le da una: no se lleva ranura por esto, y su
; fila se mueve a mano, sin tocarle el tile, que es la pose de su página. La
; referencia hace lo mismo: sin `Ruta`, dibuja la pose de la página en la
; celda de `pos_ev`.
.proc plantar_evento
.a8
.i16
    ldx #$0000
buscar:
    lda ruta_ev, x
    cmp temp
    beq con_ranura
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc buscar

    ; Sin ranura. Si tampoco tiene gráfico no hay nada que mover.
    lda temp
    jsr npc_de_evento
    cpy #$FFFF
    beq listo
    sty npc_fila
    lda temp
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tax
    lda ev_pos_buf + 0, x       ; la celda por dieciséis: está parado en ella
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 0, y
    lda ev_pos_buf + 2, x
    asl a
    asl a
    asl a
    asl a
    sta npc_buf + 2, y
    sta npc_py
    lda npc_buf + 4, y
    and #$F000                  ; la capa se queda; la Y se reemplaza
    sta temp + 2
    lda npc_py
    and #$0FFF
    ora temp + 2
    sta npc_buf + 4, y
    sep #$20
.a8
    lda #0
    sta npc_buf + 11, y         ; sin salto: nada que levantar
    jmp acomodar_npc            ; y la fila, a donde le toque ahora

con_ranura:
    lda #0
    sta ruta_ev + 7, x          ; sin paso en curso
    sta ruta_ev + 22, x
    sta ruta_ev + 23, x
    sta ruta_ev + 13, x         ; ni salto
listo:
    rts
.endproc

; --- guardar y cargar la partida -------------------------------------------
;
; El cartucho lleva SRAM con batería y **una sola ranura**. RM2k abre un menú de
; quince; acá el save point guarda y sigue, que es el alcance que acordamos con
; taro el 2026-09-09: lo mínimo que se puede jugar y probar de verdad.
;
; Qué se guarda lo dice `partida_tabla` y nada más: pares de (dirección en la
; WRAM del banco 0, cuántos bytes), terminados en un largo cero. Tenerlo en una
; tabla y no en código es lo que hace que guardar y cargar no se puedan ir uno
; del otro —los dos la recorren— y que agregar un campo sea una línea.
;
; La copia va por DMA en las dos direcciones, y la ventana de la WRAM es la que
; lo hace posible: el bus B no llega a la SRAM, pero sí a `WMDATA`, así que la
; SRAM va del lado del bus A y la WRAM del otro. Guardar es un DMA de B a A —el
; bit 7 de DMAP— y cargar el mismo al revés.
;
; La partida arranca en $0100 y no en $0000 por el ensamblador: `ca65` elige
; página directa cuando la dirección entra en un byte, así que
; con la partida en $0000 un `lda SRAM_MAGIA, x` leería la página directa en vez
; de la SRAM. Los 256 bytes que quedan abajo no los usa nadie.
SRAM_BANCO = $70            ; en LoROM la SRAM se ve desde $70:0000

; **Cuatro ranuras**, que es lo que pidió taro: RM2k abre un menú de quince y
; para este juego no tiene sentido. En la SRAM entrarían muchas más —son 8 KB y
; una ranura ocupa 165 bytes— así que el número no sale de acá sino de cuántas
; se pueden mostrar y elegir sin que la pantalla se vuelva una lista.
SRAM_RANURAS = 4

; Cada ranura arranca en un múltiplo de 256, que es lo que hace que su
; desplazamiento sea la ranura por 256 —un `xba`— y no una multiplicación. Se
; pagan 91 bytes de relleno por ranura y sobra SRAM de todas formas: cuatro
; ranuras terminan en $0500 de los $2000 que hay.
;
; **Si `PARTIDA_BYTES` pasara de 250, esto se rompe en silencio**: la ranura
; siguiente empieza a pisar el final de la anterior. Hoy son 159, y crecen cada
; vez que se agrega un campo a la partida —ya pasó con la música—. El
; ensamblador no lo puede cortar, así que lo cuida
; `pruebas/rpgmaker/test_guardar.py::test_las_cuatro_ranuras_entran_en_la_sram`.
SRAM_STRIDE = 2048

; Y dentro de cada ranura, contando desde su base. `SRAM_MAGIA` sigue siendo
; $0100 y no $0000 por lo de siempre: un operando que entra en un byte lo
; resuelve el ensamblador como página directa y leería la WRAM. Ese error costó
; que la partida no cargara en mednafen, en Mesen ni en la consola.
SRAM_MAGIA = $0100          ; cuatro bytes: "ABLS", $41 $42 $4C $53
SRAM_SUMA  = $0104          ; la suma de los bytes de la partida
SRAM_DATOS = $0106

; `partida_tabla` vive en RODATA —ver "lo que no hace falta que viva en el
; banco 0"— y se lee con `lda f:partida_tabla, x`.
; Los mismos largos, sumados, para poder recorrer la partida en la SRAM sin
; volver a mirar la tabla. Está duplicado a propósito y **la ROM lo comprueba**:
; `guardar_partida` compara con lo que le quedó a `partida_copiar` y si no dan
; iguales entra en pánico. Duplicar un número que nadie verifica es la forma de
; error que este repo ya pagó tres veces.
PARTIDA_BYTES = 2 + 2 + 1 + 2 + 2 + 2 + 6 + 3 + 1 + 5 + 3 + SWITCH_BYTES + 1 + 2 + VARIABLES_N * 2 + 1 + ITEMS_N + 1 + ACTORES_N * 10 + ACTORES_N * 2 + ACTORES_N * 2 + ACTORES_N
; Dónde cae el grupo adentro de la partida: después de la posición, la
; dirección, la celda y el mapa. Lo lee la pantalla de ranuras desde la SRAM
; para poner el nombre del líder y las caras. Es la misma suma que arriba,
; cortada en el sexto renglón de la tabla; si `partida_tabla` cambia de orden,
; esto cambia con ella.
PARTIDA_GRUPO   = 2 + 2 + 1 + 2 + 2 + 2   ; el mapa ocupa dos desde que su
                                          ; índice es de dieciséis bits
PARTIDA_GRUPO_N = PARTIDA_GRUPO + 4

; Pone la ranura con la que van a trabajar `guardar_partida` y `cargar_partida`,
; y calcula su desplazamiento. A trae el número de ranura.
;
; El desplazamiento es la ranura por 2048, o sea un `xba` y tres `asl`: de ahí
; sale que `SRAM_STRIDE` valga 2048 y no el largo justo de una partida.
; Multiplicar por ese largo pediría el multiplicador del hardware y ocho
; ciclos de espera, para ahorrar unos bytes de una SRAM que sobra. Era 256
; hasta que las 81 variables del juego entraron en la partida, 512 hasta el
; inventario y 1024 hasta el equipo, que son 610 bytes más. Con 2048 cuatro
; ranuras no entran en 8 KB, y el cartucho declara 32 KB, que en LoROM es un
; banco entero de SRAM en $70.
.proc poner_ranura
.a8
.i16
    sta ranura
    rts
.endproc

; El desplazamiento de la ranura en la SRAM, en X. **Pide el banco de datos
; normal**: lee `ranura`, que vive en la WRAM.
;
; Es la ranura por 2048, o sea un `xba` y tres `asl`: ver `poner_ranura`.
.proc ranura_en_x
.a8
.i16
    rep #$20
.a16
    lda ranura
    and #$00FF
    xba                         ; por 256...
    asl a
    asl a
    asl a                       ; ...y por ocho: SRAM_STRIDE, que es 2048
    tax
    sep #$20
.a8
    rts
.endproc

; Recorre `partida_tabla` copiando cada tramo. A trae el DMAP: $80 guarda —de la
; ventana de la WRAM a la SRAM— y $00 carga. Deja en `temp` dónde terminó la
; partida adentro de la SRAM.
.proc partida_copiar
.a8
.i16
    sta DMAP0
    lda #$80
    sta BBAD0                   ; el otro lado es siempre WMDATA
    lda #SRAM_BANCO
    sta A1B0
    ldx #$0000                  ; por dónde va la tabla
    phx
    jsr ranura_en_x             ; banco de datos normal: acá todavía lo es
    rep #$20
.a16
    txa
    clc
    adc #SRAM_DATOS
    sta temp                    ; y por dónde va la SRAM, dentro de su ranura
    sep #$20
.a8
    plx
    rep #$20
.a16
    sep #$20
.a8
otra:
    rep #$20
.a16
    lda f:partida_tabla + 2, x
    beq listo                   ; largo cero: se terminó la tabla
    sta DAS0L
    lda temp
    sta A1T0L
    clc
    adc DAS0L
    sta temp
    lda f:partida_tabla, x
    sta WMADDL                  ; la WRAM, que va siempre en el banco 0
    sep #$20
.a8
    stz WMADDH
    lda #$01
    sta MDMAEN
    rep #$20
.a16
    txa
    clc
    adc #4
    tax
    sep #$20
.a8
    bra otra
listo:
.a16
    sep #$20
.a8
    rts
.endproc

; La suma de los bytes de la partida que hay en la SRAM, en `temp + 2`. Pide el
; banco de datos ya puesto en la SRAM y **X con el desplazamiento de la
; ranura**: no lo lee de `ranura_ofs` porque con el banco en $70 eso leería la
; SRAM. Se lleva X.
;
; **El índice va desde cero y la dirección la pone la base.** Escrito al revés
; —`ldx #SRAM_DATOS` y después `lda $0000, x`— parece lo mismo y no lo es: el
; operando `$0000` entra en un byte, así que el ensamblador elige página
; directa igual que ca65, y el bucle terminaba sumando **la WRAM baja** en vez
; de la SRAM. Es exactamente la trampa que el comentario de `SRAM_MAGIA`
; advierte veinte líneas más arriba, cometida en la línea de al lado.
;
; Lo que lo mantuvo escondido es que el error es **simétrico**: guardar y
; cargar suman los dos la misma basura, así que mientras la WRAM no cambie
; entre una cosa y la otra los números coinciden y la partida carga. Eso pasa
; en el arranque de snes9x, que llena la RAM siempre con lo mismo y llama a
; `cargar_partida` a los microsegundos del reset. Con la WRAM de mednafen, de
; Mesen o de la consola de verdad, no coinciden y la partida no carga nunca;
; y desde el menú del título tampoco, porque para entonces la WRAM ya se movió.
; Tres reportes de taro y un `xfail` eran todos este bug.
.proc partida_suma
.a8
.i16
    rep #$20
.a16
    lda #$0000
    sta temp + 2
    sep #$20
.a8
    ldy #$0000                  ; X ya viene con el principio de su ranura
suma:
    lda SRAM_DATOS, x           ; la base no entra en un byte: absoluto, y el
                                ; banco de datos es la SRAM
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    inx
    iny                         ; X anda por la SRAM e Y cuenta: la ranura no
    cpy #PARTIDA_BYTES          ; arranca en cero y las dos cosas no son la misma
    bne suma
    rts
.endproc

; Guarda la partida. Es lo que hace `OP_SAVE`, o sea el `OpenSaveMenu` del
; save point de Lashe City.
.proc guardar_partida
.a8
.i16
    lda #$80                    ; de la ventana de la WRAM a la SRAM
    jsr partida_copiar
    ; Lo que se copió tiene que ser lo que `PARTIDA_BYTES` dice. Si no, la suma
    ; miraría otro tramo y la ranura quedaría inválida para siempre sin decir
    ; por qué.
    rep #$20
.a16
    sep #$20
.a8
    jsr ranura_en_x
    rep #$20
.a16
    txa
    clc
    adc #(SRAM_DATOS + PARTIDA_BYTES)
    cmp temp                    ; dónde tendría que haber terminado la copia
    sep #$20
.a8
    beq cuadra
    jmp entrar_en_panico
cuadra:
    ; La magia y la suma son lo que dice que la ranura vale. El banco de datos
    ; se muda a la SRAM: es la única forma de direccionarla sin un puntero en la
    ; página directa, que está llena.
    ;
    ; El desplazamiento de la ranura se lee **antes** de mudarlo, y de ahí en
    ; más viaja en X: con el banco en $70, `lda ranura_ofs` leería la SRAM.
    jsr ranura_en_x
    phb
    lda #SRAM_BANCO
    pha
    plb
    phx
    jsr partida_suma            ; se lleva X
    plx
    rep #$20
.a16
    lda temp + 2
    sta SRAM_SUMA, x
    sep #$20
.a8
    lda #$41
    sta SRAM_MAGIA, x
    lda #$42
    sta SRAM_MAGIA + 1, x
    lda #$4C
    sta SRAM_MAGIA + 2, x
    lda #$53
    sta SRAM_MAGIA + 3, x
    plb
    rts
.endproc

; Si la SRAM tiene una partida, la carga y devuelve A distinto de cero. Corre en
; el arranque, antes de cargar el mapa: los switches deciden qué página está
; activa en cada evento, así que tienen que estar puestos antes.
;
; La magia se compara contra inmediatos y no contra una tabla de la ROM porque
; con el banco de datos en la SRAM no hay cómo leer la ROM: el ensamblador no
; tiene direccionamiento largo y la página directa está llena.
.proc cargar_partida
.a8
.i16
    jsr ranura_en_x             ; antes de mudar el banco: ver `guardar_partida`
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_MAGIA, x
    cmp #$41
    bne no_hay
    lda SRAM_MAGIA + 1, x
    cmp #$42
    bne no_hay
    lda SRAM_MAGIA + 2, x
    cmp #$4C
    bne no_hay
    lda SRAM_MAGIA + 3, x
    cmp #$53
    bne no_hay
    phx
    jsr partida_suma            ; se lleva X
    plx
    rep #$20
.a16
    lda temp + 2
    cmp SRAM_SUMA, x
    sep #$20
.a8
    bne no_hay
    plb
    lda #$00                    ; de la SRAM a la ventana de la WRAM
    jsr partida_copiar
    lda #$01
    rts
no_hay:
    plb
    lda #$FF
    sta ranura                  ; el centinela: no hay partida cargada
    lda #$00
    rts
.endproc

; La celda donde quedó guardada la partida, puesta como entrada del mapa: es
; como una puerta le dice a `cargar_mapa` dónde plantar al héroe. Lo usan el
; arranque —cuando la ROM no lleva título y la partida se carga sola— y el menú
; del título cuando el jugador elige seguir. Estaba escrito en el arranque nomás
; y copiarlo al menú habría sido el segundo lugar donde equivocarse.
.proc entrada_de_la_partida
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta entrada_x
    lda tile_y
    sta entrada_y
    sep #$20
.a8
    rts
.endproc

; --- la pantalla de título -------------------------------------------------
;
; La imagen del LDB —`title_name`, que en el ABL es ABL20Title— con su tema
; —`title_music`, Fantasia_Of_The_Wind—, y de ahí a la partida.
;
; **Vive sola en la VRAM.** Mientras se ve no hay mapa cargado, así que no hay
; reparto que negociar: la imagen va en BG1, que en modo 3 tiene ocho bits por
; pixel y direcciona CGRAM entera. Un mapa reparte sus colores en paletas de
; dieciséis porque los sprites necesitan las suyas; acá no hay sprites.
;
; Los 496 tiles entran en $4000 —la base de tiles de BG1 va de a 4096 palabras,
; y 15872 palabras desde ahí terminan en 32256 de las 32768 que hay— y el
; tilemap en $0000. Al salir, `cargar_mapa` repone las dos bases y pisa todo.
;
; **Corre con su propio lazo y no con el principal.** El lazo principal mueve al
; héroe, corre el intérprete y arma el OAM, y acá no hay nada de eso: lo único
; que tiene que pasar por cuadro es leer el control y seguir la música.
.proc pantalla_titulo
.a8
.i16
    ; ¿Esta ROM lleva pantalla de título? TITULO_TILES no entra en ocho bits,
    ; así que la pregunta son los dos bytes.
    lda #<TITULO_TILES
    ora #>TITULO_TILES
    bne hay
    rts
hay:
    jsr titulo_subir
    ; El tema del título. $FF quiere decir que esta ROM no lo lleva —o que no
    ; entró en la ARAM—, y entonces la pantalla se ve callada.
    ;
    ; Va **acá y no en `titulo_subir`**: ésa corre también al volver de la
    ; pantalla de ranuras, y ahí el tema sigue sonando y no hay que tocarlo.
    ; Hasta el 2026-09-10 lo reiniciaba, con un comentario que decía que eso
    ; hacía RM2k, y no: `Scene_Title::Continue` al volver de la pantalla de
    ; cargar no pasa por `Start()`, y `Game_System::BgmPlay` con el mismo tema
    ; que ya suena no lo reinicia. taro lo escuchó en la consola.
    lda #TEMA_TITULO
    cmp #$FF
    beq mudo
    jsr music_start
mudo:
    jmp titulo_lazo
.endproc

; Sube la pantalla de título entera —la imagen, el menú, los colores— y la
; enciende. Está aparte del lazo porque hay dos caminos que llegan acá: entrar,
; y **volver de la pantalla de ranuras después de cancelar**, que pisó la VRAM y
; CGRAM con lo suyo.
.proc titulo_subir
.a8
.i16
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    stz HDMAEN                  ; y sin la ventana de mensaje encima

    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda #TITULO_VRAM
    sta VMADDL
    lda #(TITULO_TILES * BYTES_POR_TILE)
    sta DAS0L
    lda #<(titulo_tiles)
    ora #(>(titulo_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_tiles)
    sta A1B0
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- el tilemap ---
    rep #$20
.a16
    lda #TITULO_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(titulo_celdas)
    ora #(>(titulo_celdas) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_celdas)
    sta A1B0
    lda #$01
    sta MDMAEN

    ; --- los tiles del menú ---
    ; Van en BG2, que en modo 3 tiene cuatro bits por pixel, así que cuestan la
    ; mitad. El tile 0 es transparente y le toca a casi toda la pantalla: es lo
    ; que deja ver la imagen debajo.
    rep #$20
.a16
    lda #TITULO_MENU_VRAM
    sta VMADDL
    lda #(TITULO_MENU_TILES * 32)
    sta DAS0L
    lda #<(titulo_menu_tiles)
    ora #(>(titulo_menu_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_menu_tiles)
    sta A1B0
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    ; CGRAM entera y desde el índice 0: acá no hay ni ventana de mensaje ni
    ; color de fondo que respetar, que es lo que en un mapa se lleva las de
    ; abajo.
    stz CGADD
    rep #$20
.a16
    ; CGRAM entera: las TITULO_MENU_CGRAM de abajo son del menú y las
    ; TITULO_COLORES de arriba, de la imagen. Subir sólo las de la imagen
    ; dejaba las últimas dieciséis sin escribir, y ahí viven los colores menos
    ; usados —el degradé de los créditos—: 145 pixeles de diferencia contra la
    ; referencia, todos en el mismo par de renglones.
    lda #((TITULO_COLORES + TITULO_MENU_CGRAM) * 2)
    sta DAS0L
    lda #<(titulo_cgram)
    ora #(>(titulo_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_cgram)
    sta A1B0
    stz DMAP0                   ; un registro, escribiendo de a un byte
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; --- y el PPU apuntando a todo eso ---
    lda #(TITULO_MAP / 1024 * 4)
    sta BG1SC                   ; tilemap de 32x32: los dos bits bajos en cero
    lda #(TITULO_MENU_MAP / 1024 * 4)
    sta BG2SC                   ; y el del menú, del mismo tamaño
    ; Las dos bases de tiles, que van de a 4096 palabras: BG1 en el nibble bajo
    ; y BG2 en el alto. La imagen arranca en $4000 porque 15872 palabras desde
    ; ahí terminan en 32256 de las 32768 que hay; el menú, en $1000, entra en el
    ; hueco que queda debajo junto con los dos tilemaps.
    lda #((TITULO_MENU_VRAM / 4096 * 16) | (TITULO_VRAM / 4096))
    sta BG12NBA
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    ; El PPU muestra la línea vofs+1 en el primer scanline, igual que en el
    ; mapa: con 0 la imagen sale corrida una línea hacia arriba.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$03
    sta TM                      ; la imagen y el menú; sprites no hay

    stz titulo_sel              ; se entra con la primera opción elegida
    jsl f:titulo_subir_menu

    lda #$0F
    sta INIDISP                 ; y la pantalla encendida, al máximo
    rts
.endproc

; El lazo del menú. Arriba y abajo mueven el cursor por **flanco** y dando la
; vuelta, igual que `eleccion_tick` con el ShowChoice: es el
; `Window_Selectable::Update` de RM2k con una sola columna, y sostener abajo no
; baja un renglón por cuadro.
.proc titulo_lazo
.a8
.i16
espera:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_ant
    and pad                     ; lo que se apretó en este cuadro
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube_una
    lda #TITULO_MENU_N          ; desde la primera, arriba da la vuelta
sube_una:
    dec a
    sta titulo_sel
    jsl f:titulo_subir_menu
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #TITULO_MENU_N
    bcc baja_una
    lda #0                      ; y desde la última, abajo también
baja_una:
    sta titulo_sel
    jsl f:titulo_subir_menu
    bra espera
no_abajo:
    ; Elegir es A o START. START no lo mira RM2k —allá el menú es del ratón y
    ; del teclado— pero en una consola la pantalla de título se pasa con START
    ; y no tenerlo se siente roto.
    lda pad_a
    beq mira_start
    lda pad_a_ant
    beq elige                   ; flanco, no estado
mira_start:
    lda titulo_flancos
    and #PAD_START
    beq espera
elige:
    ; La segunda opción es 'Resume the Story': se carga la partida y, si hay,
    ; el mapa y la celda salen de ella. Si no hay, empieza igual que la
    ; primera, que es lo que hace RM2k cuando no hay nada que cargar.
    lda titulo_sel
    beq salir
    ; 'Resume the Story': la pantalla de ranuras, en modo cargar. Si el jugador
    ; cancela con B se vuelve al título, y como esa pantalla pisó la VRAM y
    ; CGRAM hay que subirlo de nuevo entero.
    lda #0
    jsr ranuras_pantalla
    cmp #$FF
    bne la_elegida
    jsr titulo_subir
    jmp titulo_lazo
la_elegida:
    jsr poner_ranura
    jsr cargar_partida
    beq salir                   ; la ranura estaba vacía o la suma no cuadra
    jsr entrada_de_la_partida
    rep #$20
.a16
    lda mapa_actual             ; el índice va en dieciséis bits
    bra cargar_el_mapa
.a8
salir:
    rep #$20
.a16
    lda #MAPA_INICIAL
cargar_el_mapa:
    ; La VRAM quedó con la imagen del título, así que el mapa hay que volver a
    ; cargarlo entero. Pero la VRAM no es lo único que esta pantalla movió: los
    ; **registros del PPU** también, y ésos no los repone `cargar_mapa`.
    ;
    ; `BG1SC`, `BG2SC`, los scrolls y `TM` los escribe `ppu_init`, que hasta
    ; ahora corría una sola vez en el arranque porque nadie los tocaba después.
    ; Sin volver a llamarlo el juego arranca con el tilemap de BG1 apuntando al
    ; del título —o sea todos los tiles corridos, que es lo que taro vio en
    ; `demo-titulo`— y con `TM` en cero, que es la pantalla en negro con la
    ; lógica y la música corriendo detrás.
    ;
    ; **snes9x y la comparación de pixeles no lo vieron**, y por una razón que
    ; conviene recordar: la tanda mira la pantalla de título y no lo que pasa
    ; después de salir de ella. El cuadro que lo habría cobrado no existía.
    pha                         ; el índice del mapa, de dieciséis bits
    sep #$20
.a8
    lda #$80
    sta INIDISP
    stz TM                      ; y sin el menú encima mientras se rehace todo
    jsr ppu_init                ; los registros del PPU, como los dejó el reset
    rep #$20
.a16
    pla
    jsr cargar_mapa
    sep #$20
.a8
    jsr clear_oam
    jsr build_oam
    jsr flush_video

    ; La música. Sin esto el tema del título se queda sonando adentro del
    ; juego, que es lo que taro vio el 2026-09-10: `Fantasia_Of_The_Wind` en el
    ; pasillo de la apertura. `music_boot` es exactamente lo que hace una ROM
    ; sin pantalla de título al arrancar —el tema del mapa inicial, o callar si
    ; no tiene—, así que las dos siguen sonando igual.
    jsr music_boot
    lda music_apagada
    beq listo_musica
    ; `TEMA_ARRANQUE` en $FF quiere decir que el mapa arranca callado y que lo
    ; prende un `PlayBGM`, que es lo normal en este juego. `music_boot` no le
    ; escribe nada al DSP porque en el arranque no hay nada sonando; **acá sí
    ; lo hay**, así que el volumen general hay que bajarlo a mano. El
    ; `PlayBGM` que venga lo vuelve a subir: su stream escribe los dos
    ; registros al arrancar.
    php
    sei                         ; el SPC700 atiende de a uno: ver `irq_musica`
    stz dsp_valor
    lda #DSP_MVOL_L
    jsr escribir_dsp
    lda #DSP_MVOL_R
    jsr escribir_dsp
    plp
listo_musica:
    lda #$0F
    sta INIDISP
    rts
.endproc

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

; --- la pantalla de ranuras ------------------------------------------------
;
; La usan las dos puntas: "Resume the Story" en el título, y el save point de
; Lashe City. Es una pantalla propia y no una capa encima del título, así que
; **comparte la VRAM del menú**: cuando una se ve la otra no, y las dos se
; suben enteras cada vez que se entra.
;
; Todo el texto viene pre-renderizado del conversor, incluidas las dos
; variantes de cada ranura —vacía y llena—. Lo único que se decide en caliente
; es qué bloque de celdas le toca a cada fila, y **de qué bloque se trata lo
; dice una tabla de punteros**, no una multiplicación: calcular el
; desplazamiento con corrimientos habría puesto la misma cuenta acá y en el
; conversor, que es la forma de error que este repo ya pagó tres veces.
;
; Mover el cursor reescribe **dos filas** de 96 celdas, no el tilemap entero.

; Si la ranura que viene en A tiene una partida. Devuelve A distinto de cero, y
; **se lleva `ranura`**: `ranuras_pantalla` la guarda al entrar y la repone al
; salir.
;
; Mira sólo la magia y no la suma: es para pintar la lista, y recorrer los 159
; bytes de cada ranura para dibujar una pantalla sería pagar de más. La suma la
; comprueba `cargar_partida` cuando el jugador elige, que es donde importa.
.proc ranura_llena
.a8
.i16
    jsr poner_ranura
    jsr ranura_en_x             ; con el banco de datos todavía normal
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_MAGIA, x
    cmp #$41
    bne no
    lda SRAM_MAGIA + 1, x
    cmp #$42
    bne no
    lda SRAM_MAGIA + 2, x
    cmp #$4C
    bne no
    lda SRAM_MAGIA + 3, x
    cmp #$53
    bne no
    plb
    lda #$01
    rts
no:
    plb
    lda #$00
    rts
.endproc

; Sube un bloque de celdas al tilemap. X trae el índice del bloque en
; `ranura_bloque_lo/hi/bk`, Y la dirección de VRAM en palabras y `temp` cuántas
; celdas son.
;
; Con la pantalla apagada al entrar y adentro del vblank al mover el cursor:
; 192 bytes por DMA entran de sobra en un vblank que no tiene nada más que
; hacer.
.proc ranura_bloque_subir
.a8
.i16
    sty VMADDL
    lda #$80
    sta VMAIN
    lda ranura_bloque_lo, x
    sta A1T0L
    lda ranura_bloque_hi, x
    sta A1T0L + 1
    lda ranura_bloque_bk, x
    sta A1B0
    rep #$20
.a16
    lda temp
    asl a                       ; celdas a bytes
    sta DAS0L
    sep #$20
.a8
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Pinta la fila de la ranura que viene en A: con cursor si `titulo_sel` la
; señala, y llena si la SRAM dice que lo está.
;
; El estado de llenado se vuelve a preguntar en cada repintado en vez de
; guardarse: son cuatro bytes de la SRAM y pasa sólo cuando el cursor se mueve.
; Guardarlo pediría RAM que no hay —ver `ranura`— y una forma de invalidarlo
; después de guardar.
.proc ranura_pintar
.a8
.i16
    pha
    jsr ranura_llena
    asl a                       ; llena vale 2 en el índice de variante
    sta temp + 2
    pla
    pha
    cmp titulo_sel
    bne sin_cursor
    inc temp + 2                ; y el cursor, 1
sin_cursor:
    ; El índice del bloque: las dos cabeceras primero, y después cuatro
    ; variantes por ranura.
    pla
    pha
    asl a
    asl a
    clc
    adc temp + 2
    clc
    adc #RANURA_BLOQUE_FILAS
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    ; Y a dónde va, que lo dice la tabla y no una cuenta.
    pla
    pha                         ; la ranura, para el grupo de después
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por entrada
    tay
    lda ranura_vram, y
    tay
    lda #RANURA_CELDAS
    sta temp
    sep #$20
.a8
    jsr ranura_bloque_subir
    ; Y encima de la fila, si tiene partida, el nombre del líder y las caras
    ; del grupo que guardó. `temp + 2` quedó con la variante: llena vale 2 o 3.
    pla
    lda temp + 2
    cmp #2
    bcc sin_grupo
    jmp ranura_grupo_pintar
sin_grupo:
    rts
.endproc

; Sube un rectángulo de celdas al tilemap, fila por fila. X trae el índice del
; bloque en `ranura_bloque_lo/hi/bk`, Y la dirección de VRAM de su primera
; celda, `temp` cuántos bytes tiene cada fila y `temp + 2` cuántas filas son.
;
; Un solo puntero de origen para todas las filas: el DMA deja `A1T0` apuntando
; a donde terminó, así que la fila siguiente arranca de ahí sin volver a
; cargarlo. Lo que cambia por fila es el destino, que baja 32 celdas.
.proc ranura_rect_subir
.a8
.i16
    lda #$80
    sta VMAIN
    lda ranura_bloque_lo, x
    sta A1T0L
    lda ranura_bloque_hi, x
    sta A1T0L + 1
    lda ranura_bloque_bk, x
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
fila:
    sty VMADDL
    rep #$20
.a16
    lda temp
    sta DAS0L
    tya
    clc
    adc #32
    tay
    sep #$20
.a8
    lda #$01
    sta MDMAEN
    dec temp + 2
    bne fila
    rts
.endproc

; El grupo de la partida de la ranura que está en `ranura`: las caras de los
; primeros RANURA_CARAS_MAX, y el nombre del primero. Es lo que
; `Window_SaveFile::Refresh` dibuja por archivo, menos los puntos de vida, que
; este port no tiene.
;
; El grupo se lee de la SRAM de la ranura, con el banco de datos en $70 el
; tiempo justo de leer un byte: las tablas de bloques y los registros del DMA
; direccionan el banco 0. Un actor sin cara —DummyHero— no dibuja nada, que es
; lo que hace `DrawFace` con un nombre vacío. Y a dónde va cada cara y cada
; nombre lo dicen dos tablas del conversor, `ranura_cara_vram` y
; `ranura_nombre_vram`, como `ranura_vram` para las filas: la cuenta vive en
; un solo lado.
;
; El escritorio, que está justo: `temp` y `temp + 2` son del rectángulo,
; `temp + 3` guarda cuántos son, y **`titulo_flancos` hace de índice de
; miembro**. En la página directa no hay otro byte, y los flancos ya se miraron
; cuando se llega acá.
.proc ranura_grupo_pintar
.a8
.i16
    jsr ranura_en_x
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_DATOS + PARTIDA_GRUPO_N, x
    plb
    cmp #RANURA_CARAS_MAX
    bcc caben
    lda #RANURA_CARAS_MAX
caben:
    sta temp + 3
    stz titulo_flancos
otro_miembro:
    lda titulo_flancos
    cmp temp + 3
    bcs las_caras_listas
    jsr actor_del_miembro
    cmp #RANURA_ACTORES_N
    bcs siguiente               ; un actor que esta ROM no conoce
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ranura_cara_bloque, x
    cmp #$FF
    beq siguiente               ; sin cara
    pha                         ; el bloque, mientras se arma el destino
    ; La tabla va de a cuatro por ranura: la ranura por cuatro más el lugar.
    lda ranura
    asl a
    asl a
    ora titulo_flancos
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por entrada
    tax
    lda ranura_cara_vram, x
    tay
    lda #(RANURA_CARA_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #RANURA_CARA_FILAS
    sta temp + 2
    pla
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr ranura_rect_subir
siguiente:
    inc titulo_flancos
    bra otro_miembro
las_caras_listas:
    ; El nombre del líder, que es el primero.
    lda temp + 3
    beq listo                   ; un grupo vacío no tiene líder
    stz titulo_flancos
    jsr actor_del_miembro
    cmp #RANURA_ACTORES_N
    bcs listo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ranura_nombre_bloque, x
    cmp #$FF
    beq listo
    pha
    lda ranura
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda ranura_nombre_vram, x
    tay
    lda #(RANURA_NOMBRE_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #RANURA_NOMBRE_FILAS
    sta temp + 2
    pla
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    jsr ranura_rect_subir
listo:
    rts

; El actor que está en el lugar `titulo_flancos` del grupo de la ranura, leído
; de la SRAM. Devuelve A y se lleva X. El desplazamiento es la ranura por 1024
; —`SRAM_STRIDE`— más el lugar, armado con dos `xba` y sin tocar los vecinos
; de la página directa: leer `titulo_flancos` a dieciséis bits se llevaría
; `menu_abierto`. El byte alto es la ranura por cuatro, que entra: son cuatro
; ranuras.
actor_del_miembro:
    lda titulo_flancos
    xba
    lda ranura
    asl a
    asl a
    asl a
    xba                         ; C = ranura * 2048 + lugar
    rep #$20
.a16
    tax
    sep #$20
.a8
    phb
    lda #SRAM_BANCO
    pha
    plb
    lda SRAM_DATOS + PARTIDA_GRUPO, x
    plb
    rts
.endproc

; La pantalla entera: la sube, la muestra y la maneja hasta que el jugador
; elija o cancele. A trae el modo —0 cargar, 1 guardar— y vuelve con la ranura
; elegida, o **$FF si canceló con B**.
;
; Deja la VRAM y CGRAM pisadas, así que el llamador repone lo suyo: el título
; vuelve a subir su imagen y su menú, y el save point recarga el mapa. Es lo
; mismo que hace `pantalla_titulo` al salir, y por la misma razón: mientras esta
; pantalla se ve no hay ni mapa ni título que preservar.
.proc ranuras_pantalla
.a8
.i16
    ; El banco de datos, al 0. **Desde el título ya lo es; desde el save point
    ; no tiene por qué**: el intérprete corre con el banco puesto donde vive el
    ; bytecode del evento. Y todo lo de acá abajo escribe los registros del PPU
    ; y del DMA con direccionamiento absoluto, que usa el banco de datos, así
    ; que con el banco corrido la pantalla se dibujaba en negro con basura
    ; arriba.
    phb
    phk
    plb
    ; Y el tamaño de los registros, explícito. Desde el título se llega con A
    ; de ocho bits y X/Y de dieciséis; **desde el intérprete no hay tal
    ; promesa**, y una `lda #$80` interpretada como de dieciséis bits se come el
    ; byte siguiente y descoloca todo lo que sigue.
    sep #$20
    rep #$10
    pha                         ; el modo, hasta que se dibuje la cabecera
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM                      ; nada a la vista mientras se arma

    jsr ranura_banco_subir

    ; --- la cabecera, según el modo ---
    pla
    pha                         ; el modo, otra vez: decide dónde arranca el cursor
    rep #$20
.a16
    and #$00FF
    tax                         ; los dos primeros bloques son las cabeceras
    lda #RANURA_CAB_CELDAS
    sta temp
    ldy #(RANURA_MAP + RANURA_CAB_VRAM)
    sep #$20
.a8
    jsr ranura_bloque_subir

    ; --- dónde arranca el cursor ---
    ; Cargando, en la primera. Guardando, en la ranura que se está usando —de
    ; la que se cargó, o en la que se guardó la última vez—: es el
    ; `index = latest_slot` de `Scene_File::Start`, que allá es la de fecha más
    ; nueva y acá, sin fechas, la que está en uso. Sin partida cargada, la
    ; primera.
    pla
    beq primera
    lda ranura
    cmp #$FF
    bne arranca_ahi
primera:
    lda #0
arranca_ahi:
    sta titulo_sel

    ; `ranura` a la pila. Pintar una fila la pisa —`ranura_llena` la escribe
    ; para direccionar la SRAM— y al salir tiene que valer lo que valía, elija
    ; el jugador o cancele: quien elige la pone después con `poner_ranura`.
    ; Desde el título daba lo mismo porque valía $FF y se ponía al elegir;
    ; desde el save point, cancelar dejaría a la partida "cargada" de la última
    ; fila pintada.
    lda ranura
    pha

    ; --- y las cuatro filas ---
    lda #0
pintar_todas:
    pha
    jsr ranura_pintar
    pla
    inc a
    cmp #SRAM_RANURAS_N
    bcc pintar_todas

    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto

espera:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube
    lda #SRAM_RANURAS_N         ; desde la primera, arriba da la vuelta
sube:
    dec a
    jsr mover_cursor
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #SRAM_RANURAS_N
    bcc baja
    lda #0
baja:
    jsr mover_cursor
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    jsr cerrar
    lda #$FF                    ; cancelar
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    jsr cerrar
    lda titulo_sel
    rts

; Lo que las dos salidas tienen en común: `ranura` como estaba, el banco de
; datos como estaba, el testigo abajo. Y `nmi_visto` al día, para que
; `contar_perdidos` no cuente como perdidos los cuadros que el jugador pasó
; eligiendo: desde el save point esto corre adentro de una vuelta del lazo, y
; sin esto la vuelta mediría cientos de cuadros y saturaría el contador.
;
; La pila trae, de arriba abajo: la dirección de vuelta de este `jsr`, `ranura`
; y el banco. Se saca la de vuelta primero para llegar a los otros dos.
cerrar:
    plx                         ; la dirección de vuelta, aparte
    pla
    sta ranura
    plb
    phx
    ; Y los flancos de B y de A, consumidos: el que cerró la pantalla es de
    ; ella. Sin esto, desde el save point, el B de cancelar le llegaba a
    ; `pedir_menu` en la misma vuelta —si la página terminaba ahí— y abría el
    ; menú de pausa; y el A de elegir podía hablarle a un evento.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    rts

; El cursor a la ranura que trae A: se repintan **las dos filas que cambian** y
; ninguna más. Adentro del vblank, que es donde estamos al salir de
; `wait_vblank`.
mover_cursor:
    sta temp + 3                ; la nueva
    lda titulo_sel
    pha                         ; y la vieja, a la pila
    lda temp + 3
    sta titulo_sel
    pla
    jsr ranura_pintar           ; se despinta el cursor de donde estaba
    lda titulo_sel
    jmp ranura_pintar           ; y se pinta donde va
.endproc

; Sube el banco de tiles de la pantalla de ranuras y del menú, deja el tilemap
; en blanco y sube sus colores. Con la pantalla apagada. Salió de
; `ranuras_pantalla` el día que el menú de pausa empezó a usar el mismo banco.
.proc ranura_banco_subir
.a8
.i16
    ; --- los tiles ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(RANURA_TILES * 32)
    sta DAS0L
    lda #<(ranura_tiles)
    ora #(>(ranura_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; --- el tilemap, en blanco ---
    ; Un DMA con la dirección de origen **fija** —el bit 3 de DMAP— repitiendo
    ; una palabra en cero. El origen es el primer tile del banco, que es el
    ; transparente y por lo tanto son 32 bytes de cero: no hace falta un bloque
    ; aparte para tener dos ceros a mano.
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(ranura_tiles)
    ora #(>(ranura_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_tiles)
    sta A1B0
    lda #$09                    ; dos registros, sin avanzar el origen
    sta DMAP0
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    ; La paleta 0 del texto y una por cara: RANURA_CGRAM_N entradas, seguidas.
    stz CGADD
    rep #$20
.a16
    lda #(RANURA_CGRAM_N * 2)
    sta DAS0L
    lda #<(ranura_cgram)
    ora #(>(ranura_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(ranura_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN

    rts
.endproc

; BG2 con el tilemap de la pantalla de ranuras, y la pantalla prendida.
.proc ranura_ppu_prender
.a8
.i16
    ; --- el PPU ---
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(RANURA_VRAM / 4096 * 16)
    sta BG12NBA                 ; sólo BG2; BG1 no se dibuja
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    lda #$02
    sta TM
    lda #$0F
    sta INIDISP
    rts
.endproc

; --- el menú de pausa --------------------------------------------------------
;
; `Scene_Menu`, sobre el banco de la pantalla de ranuras: la geometría y los
; bloques salen de `titulo.py`, y `render_menu` es la referencia. Se abre con
; B, cuando el héroe está quieto: `pedir_menu` anota el pedido y `move_hero`
; lo atiende, que es como lo hace RM2k con `menu_calling`. El reloj del juego
; no corre mientras se ve —como en la pantalla de ranuras— así que para la
; referencia el menú no cuesta ningún tick.
;
; Hoy hacen algo usar ítems —la pantalla de ítems, más abajo— y guardar, que
; abre la pantalla de ranuras y vuelve al menú. Las otras tres se dibujan en
; gris y A no hace nada con ellas.

; El byte de permisos, en A. Sólo A, y las banderas del `lda`: el bit 7 queda
; en N.
.proc acceso_leer
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; --- el sprite que un `ChangeSpriteAssociation` le puso a un actor -----------
;
; Un byte por número de actor en `FAR_ACTOR_GRAF`, con el índice en la tabla de
; gráficos del mapa o `ACTOR_GRAF_NINGUNO`. Vive lejos, así que se apunta WMADD
; y se pasa por el puerto, como las variables.

; A: el actor. Deja WMADD apuntando a su byte.
.proc actor_graf_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ACTOR_GRAF
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: el actor. Vuelve con su gráfico en A, o `ACTOR_GRAF_NINGUNO`.
.proc actor_graf_leer
.a8
.i16
    jsr actor_graf_apuntar
    lda WMDATA
    rts
.endproc

; A: el actor; `temp + 1`: el gráfico.
.proc actor_graf_escribir
.a8
.i16
    jsr actor_graf_apuntar
    lda temp + 1
    sta WMDATA
    rts
.endproc

; Ningún actor con el sprite cambiado. Corre en el reset, antes de cargar la
; partida, que lo pisa.
.proc actor_graf_limpiar
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACTOR_GRAF
    sta WMADDL
    ldx #ACTORES_N
    sep #$20
.a8
    stz WMADDH
    lda #ACTOR_GRAF_NINGUNO
otro:
    sta WMDATA
    dex
    bne otro
    rts
.endproc

; El valor que `KeyInputProc` le guarda a la variable, en A, o 0 si todavía no
; hay tecla. `temp + 1` trae las banderas.
;
; **Las tres cosas, y las tres por flanco**: cancelar, la tecla de acción y la
; cruceta. El orden es el de `CheckInput` —de mayor valor a menor, que es lo
; que dice "RPG processes keys from highest variable value to lowest"— y es el
; mismo que corre `eventos.tecla_de` del lado del modelo; los números salen del
; conversor y no están escritos acá dos veces.
;
; Hasta el 2026-09-13 esto miraba sólo la tecla de acción, y lo que lo tenía
; cortado no era la ROM sino el arnés: la tanda sostenía una dirección desde el
; arranque, así que un flanco de cruceta no lo podía producir ningún caso.
; Ahora lo produce `--tocar`, y lo cobra el caso `tecla-dir` de la tanda.
;
; El flanco es `Input::IsTriggered`: `pad` contra `pad_ant` para B y las
; direcciones, `pad_a` contra `pad_a_ant` para A —A vive en el otro byte del
; control—, que es lo mismo con lo que se cierra un mensaje.
;
; `temp + 3` es el único de los cuatro que está libre acá: `temp` trae la
; ranura y `temp + 1` las banderas, y `op_key` guarda la respuesta en
; `temp + 2` **después** de volver de acá.
.proc tecla_valor
.a8
.i16
    lda pad
    eor pad_ant
    and pad
    sta temp + 3                ; los flancos de JOY1H: B y las cuatro flechas
    lda temp + 1
    and #TECLA_CANCELAR
    beq sin_cancelar
    lda temp + 3
    and #PAD_B
    beq sin_cancelar
    lda #TECLA_VALOR_CANCELAR
    rts
sin_cancelar:
    lda temp + 1
    and #TECLA_DECISION
    beq sin_decision
    lda pad_a
    eor pad_a_ant
    and pad_a
    beq sin_decision
    lda #TECLA_VALOR_DECISION
    rts
sin_decision:
    lda temp + 1
    and #TECLA_DIRS
    beq ninguna
    ; Las cuatro, en el orden de `CheckInput`, por tabla: escritas a mano son
    ; cuatro `bit`/`bne` más cuatro `lda`/`rts`, y el banco 0 no los tiene.
    ; La tabla termina en cero, que no es ningún botón.
    ldx #$0000
dir_otra:
    lda f:tecla_dir_bit, x
    beq ninguna
    and temp + 3
    bne dir_hay
    inx
    bra dir_otra
dir_hay:
    lda f:tecla_dir_val, x
    rts
ninguna:
    lda #0
    rts
.endproc

; A: el byte de permisos nuevo.
.proc acceso_escribir
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; Se tira el pedido de menú, si había. Sólo A.
.proc menu_olvidar
.a8
.i16
    jsr acceso_leer
    bpl listo
    and #$7F
    jsr acceso_escribir
listo:
    rts
.endproc

; B recién apretado pide el menú, si está permitido, no hay mensaje y no hay
; página corriendo: es el final de `Game_Player::Update`. Corre después de
; `move_hero`, así que el menú se abre en el cuadro que viene —o cuando
; termine el paso, si se estaba caminando—.
.proc pedir_menu
.a8
.i16
    lda pad
    eor pad_ant
    and pad
    and #PAD_B
    beq listo
    lda msg_abierto
    bne listo
    lda ev_activo
    bne listo
    jsr acceso_leer
    bit #ACCESO_SIN_MENU
    bne listo
    ora #ACCESO_PEDIDO
    jsr acceso_escribir
listo:
    rts
.endproc

; ¿La orden A hace algo? Vuelve con A = 1 y Z=0 si sí. Se lleva X.
.proc menu_habilitada
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda menu_hecha, x
    beq listo
    cpx #MENU_GUARDAR
    bne listo
    jsr acceso_leer
    and #ACCESO_SIN_GUARDAR
    eor #ACCESO_SIN_GUARDAR     ; 1 si está permitido
listo:
    rts
.endproc

; El cursor en la orden A: `temp + 3` en 1 lo pinta y en 0 lo borra. Son dos
; celdas, una abajo de la otra, escritas de a una palabra. Con la pantalla
; apagada o adentro del vblank.
.proc menu_cursor_escribir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_cursor_vram, x
    tay
    sep #$20
.a8
    lda #$80
    sta VMAIN
    sty VMADDL
    lda temp + 3
    rep #$20
.a16
    beq borra
    lda menu_cursor_celdas
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_celdas + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
borra:
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    rts
.endproc

; El oro, alineado a la derecha contra la moneda: se divide por diez de a un
; byte —el divisor del hardware es de 16 por 8, y con el resto de arrastre el
; dividendo nunca pasa de 2559— y cada resto es una cifra, de derecha a
; izquierda. El cero se escribe "0".
.proc menu_oro_escribir
.a8
.i16
    rep #$20
.a16
    lda oro
    sta temp
    sep #$20
.a8
    lda oro + 2
    sta temp + 2
    lda #$80
    sta VMAIN
    ldy #(MENU_MONEDA_VRAM - 1)
cifra:
    stz temp + 3                ; el resto que se arrastra
    ldx #2
dividir:
    lda temp, x
    sta WRDIVL
    lda temp + 3
    sta WRDIVH
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
    lda RDDIVL
    sta temp, x
    lda RDMPYL                  ; el resto
    sta temp + 3
    dex
    bpl dividir
    rep #$20
.a16
    sty VMADDL
    lda temp + 3
    and #$00FF
    asl a
    asl a
    tax
    lda menu_cifra_celdas, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cifra_celdas + 2, x
    sta VMDATAL
    dey
    lda temp                    ; ¿queda algo?
    bne otra
    sep #$20
.a8
    lda temp + 2
    bne cifra
    rts
.a16
otra:
    sep #$20
.a8
    bra cifra
.endproc

; La pantalla entera, con la pantalla apagada: el banco, las cinco órdenes, el
; cursor en `titulo_sel`, el oro y el grupo. Al final la prende.
.proc menu_subir
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir

    ; --- las órdenes, cada una en su variante ---
    lda #0
otra_opcion:
    pha
    jsr menu_habilitada
    eor #1
    sta temp + 3                ; 1 si va en gris
    pla
    pha
    asl a
    ora temp + 3
    clc
    adc #MENU_BLQ_OPCION
    sta temp + 3                ; el bloque
    pla
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_opcion_vram, x
    tay
    lda temp + 3
    and #$00FF
    tax
    lda #(MENU_OPC_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir
    pla
    inc a
    cmp #MENU_OPCIONES
    bcc otra_opcion

    ; --- el cursor ---
    lda #1
    sta temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir

    ; --- el oro y la moneda ---
    jsr menu_oro_escribir
    rep #$20
.a16
    ldx #MENU_BLQ_MONEDA
    ldy #MENU_MONEDA_VRAM
    lda #(MENU_MONEDA_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir

    jsr menu_grupo_pintar
    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto
    rts
.endproc

; El grupo, de a una fila por actor: cara, nombre, nivel, estado y HP. Lo
; comparten el menú y la elección de actor.
.proc menu_grupo_pintar
.a8
.i16
    lda #0
otro_miembro:
    cmp grupo_n
    bcs grupo_listo
    cmp #MENU_FILAS_GRUPO
    bcs grupo_listo
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x                ; el actor
    cmp #MENU_ACTORES_N
    bcs sin_bloque              ; uno que esta ROM no conoce
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda menu_actor_bloque, x
    cmp #$FF
    beq sin_bloque
    sta temp + 3
    pla
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_fila_vram, x
    tay
    lda temp + 3
    and #$00FF
    tax
    lda #(MENU_ACTOR_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #MENU_ACTOR_FILAS
    sta temp + 2
    jsr ranura_rect_subir
    ; Y los HP de ahora encima del bloque, que no los trae: el bloque se
    ; hornea al convertir. El actor se vuelve a buscar en `grupo` en vez de
    ; guardarlo, porque los dos bytes que sobraban de `temp` los usa
    ; `ranura_rect_subir`.
    pla
    pha
    sta temp + 2                ; la fila
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    sta temp                    ; el actor
    jsl f:menu_hp_escribir
sin_bloque:
    pla
    inc a
    bra otro_miembro
grupo_listo:
    rts
.endproc

; El menú, hasta que el jugador lo cierra con B. Vuelve al mapa repuesto,
; como la pantalla de ranuras desde el save point.
.proc menu_pantalla
.a8
.i16
    phb
    phk
    plb
    sep #$20
    rep #$10
    stz titulo_sel              ; RM2k abre con el cursor en la primera
armar:
    jsr menu_subir
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube
    lda #MENU_OPCIONES          ; desde la primera, arriba da la vuelta
sube:
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #MENU_OPCIONES
    bcc baja
    lda #0
baja:
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    bne cerrar
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda titulo_sel
    jsr menu_habilitada
    beq espera                  ; en gris: RM2k suena y no hace nada
    lda titulo_sel
    cmp #2
    bne no_equipo
    ; El equipo: a quién, y su pantalla. Las dos vuelven al menú.
    lda #1
    sta eleg_cancel             ; para elegir
    jsr objetivo_pantalla
    cmp #$FF
    beq volver_de_equipo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    jsr equipo_pantalla
volver_de_equipo:
    lda #2
    sta titulo_sel
    jmp armar
no_equipo:
    lda titulo_sel
    bne no_items
    ; Los ítems: B vuelve al menú, y usar uno vuelve derecho al mapa.
    jsr items_pantalla
    beq volver_de_items
    jmp cerrar
volver_de_items:
    stz titulo_sel
    jmp armar
no_items:
    ; Guardar: la pantalla de ranuras y, elija
    ; o cancele, de vuelta al menú con el cursor en "Save", como `Scene_Save`
    ; cuando vuelve a `Scene_Menu`.
    lda #1
    jsr ranuras_pantalla
    cmp #$FF
    beq guardar_listo
    jsr poner_ranura
    jsr guardar_partida
guardar_listo:
    lda #MENU_GUARDAR
    sta titulo_sel
    jmp armar
cerrar:
    ; El B que cierra y el A de antes quedan consumidos: sin esto `pedir_menu`
    ; vería el flanco en esta misma vuelta y el menú se volvería a abrir.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    plb
    jsr volver_al_mapa
    rts

; El cursor a la orden que trae A: se borra de donde estaba y se pinta ahí.
mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jmp menu_cursor_escribir
.endproc

; --- la elección de actor ----------------------------------------------------
;
; `Scene_ActorTarget`, sobre el banco del menú: el panel del grupo y un cursor
; al costado de la fila marcada. `eleg_cancel` dice para qué: en 0, para una
; medicina, y A no hace nada —`UseItem` sólo la gasta si sube algo, y fuera de
; batalla nadie tiene los HP ni los SP por debajo del máximo ni un estado, ver
; CHANGE_HP en eventos.py—; en 1, para elegir a quién equipar, y A vuelve con
; la fila. B vuelve con $FF. `render_objetivo` en titulo.py es la referencia.

; El cursor en la fila A del grupo: `temp + 3` en 1 lo pinta y en 0 lo borra.
.proc objetivo_cursor_escribir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_fila_vram, x
    clc
    adc #OBJETIVO_CURSOR_DESPL
    tay
    sep #$20
.a8
    lda #$80
    sta VMAIN
    sty VMADDL
    lda temp + 3
    rep #$20
.a16
    beq borra
    lda menu_cursor_celdas
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_celdas + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
borra:
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    rts
.endproc

.proc objetivo_pantalla
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir
    jsr menu_grupo_pintar
    stz titulo_sel
    lda #1
    sta temp + 3
    lda #0
    jsr objetivo_cursor_escribir
    jsr ranura_ppu_prender
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    beq espera
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp grupo_n
    bcs espera
    cmp #MENU_FILAS_GRUPO
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    lda #$FF                    ; B: sin elegir
    rts
mira_a:
    lda eleg_cancel
    beq espera                  ; con una medicina A no tiene efecto: ver arriba
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda titulo_sel              ; eligiendo: la fila elegida
    rts

mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsr objetivo_cursor_escribir
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jmp objetivo_cursor_escribir
.endproc

; --- las pantallas de texto -----------------------------------------------------
;
; El equipo y la tienda son pantallas de puro texto sobre la fuente de la
; pantalla de ítems. Se componen **enteras** en `texto_buf` —el tilemap de 32
; por 28 celdas, 1792 bytes— y suben de un DMA al empezar cada vblank, así que
; componer no tiene apuro de tiempo. `pantallas.py` es la referencia. Una
; posición es un byte del búfer: fila * 64 + columna * 2; la celda de abajo de
; cada letra está 64 bytes más adelante.
;
; El escritorio son variables prestadas: las del compositor de mensajes,
; `comp_*`, que se recalculan con cada carácter y con el menú abierto no hay
; mensaje; y `eleg_tabla`, que es la posición donde se escribe.
PANT_BYTES = 32 * 28 * 2
;   pant_valor   es comp_dup       ; el número que se escribe, dos bytes
;   pant_ancho   es comp_dup + 2   ; en cuántas cifras
;   pant_tope    es comp_dup + 3   ; cuántas letras de un texto, a lo sumo

; El búfer en blanco.
.proc pant_limpiar
.a8
.i16
    rep #$20
.a16
    ldx #0
otra:
    stz texto_buf, x
    inx
    inx
    cpx #PANT_BYTES
    bcc otra
    sep #$20
.a8
    rts
.endproc

; El búfer al tilemap: un DMA, en el vblank.
.proc pant_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #PANT_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el búfer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Una letra: A el carácter, `temp + 1` la variante —0 blanco, 1 gris—. Va en
; `eleg_tabla`, que avanza una celda. Se lleva X e Y.
.proc pant_glifo
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    tax
    lda temp + 1
    and #$00FF
    beq blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
blanco:
    ldy eleg_tabla
    lda f:item_glifo_celdas, x
    sta texto_buf, y
    lda f:item_glifo_celdas + 2, x
    sta texto_buf + 64, y
    iny
    iny
    sty eleg_tabla
    sep #$20
.a8
    rts
.endproc

; Un texto: X su número —ver `item_txt_*`—, en `eleg_tabla` y con la variante
; de `temp + 1`, y no más de `pant_tope` letras.
.proc pant_texto
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    cmp comp_dup + 3
    bcc cabe
    lda comp_dup + 3
cabe:
    sta temp                    ; cuántas letras
    stz temp + 2                ; por cuál va
letra:
    lda temp + 2
    cmp temp
    bcs listo
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [msg_ptr], y
    jsr pant_glifo
    inc temp + 2
    bra letra
listo:
    lda #255
    sta comp_dup + 3               ; el tope es de un texto solo
    rts
.endproc

; Un número de `pant_valor`, de 0 a 999, en `pant_ancho` cifras —2 o 3— con
; espacios adelante, en `eleg_tabla` y con la variante de `temp + 1`.
.proc pant_numero
.a8
.i16
    stz temp + 3                ; ya salió una cifra
    lda comp_dup + 2
    cmp #3
    bcc decenas
    rep #$20
.a16
    ldx #0
cien:
    lda comp_dup
    cmp #100
    bcc cien_listo
    sbc #100
    sta comp_dup
    inx
    bra cien
cien_listo:
    sep #$20
.a8
    jsr cifra
decenas:
    rep #$20
.a16
    ldx #0
diez:
    lda comp_dup
    cmp #10
    bcc diez_listo
    sbc #10
    sta comp_dup
    inx
    bra diez
diez_listo:
    sep #$20
.a8
    jsr cifra
    lda comp_dup              ; las unidades, siempre
    clc
    adc #$30
    jmp pant_glifo

; X: la cifra. Un cero adelante de todo va como espacio.
cifra:
    txa
    bne escribir
    lda temp + 3
    bne escribir_cero
    lda #$20
    jmp pant_glifo
escribir_cero:
    lda #0
escribir:
    clc
    adc #$30
    pha
    lda #1
    sta temp + 3
    pla
    jmp pant_glifo
.endproc

; --- el equipo -----------------------------------------------------------------
;
; `Scene_Equip`: el actor, sus cuatro parámetros, las cinco ranuras con lo que
; tiene puesto; A sobre una ranura muestra la lista de lo que puede ponerse
; ahí —reemplaza a las ranuras mientras dura— con los parámetros que
; quedarían. La línea vacía del final es sacarse lo de la ranura. B vuelve.
; `pantallas.pantalla_equipo` es la referencia, y `pantallas.equipar` la regla.
;   eq_actor     es comp_char      ; el número de actor
;   eq_ranura    es comp_col       ; la ranura marcada, 0 a 4
;   eq_eligiendo es comp_col + 1   ; si se muestra la lista
;   eq_elegido   es comp_fase      ; el lugar del cursor en la lista
;   eq_arriba    es comp_fase + 1  ; y el primero que se ve
;   eq_n         es comp_base      ; cuántos hay en la lista, con la vacía
;   eq_cand      es comp_mask      ; el ítem que marca el cursor, 0 si ninguno
;   eq_suma      es comp_or01      ; un parámetro, mientras se suma
;   eq_param     es comp_or01 + 2  ; cuál
;   eq_s         es comp_or01 + 3  ; la ranura que se mira
;   eq_id        es comp_or23      ; un ítem, dos bytes
;   eq_tmp       es comp_and       ; escritorio de `eq_apuntar`, cuatro bytes

; A: la ranura. Deja apuntada la ventana de la WRAM a esa ranura del actor:
; `FAR_EQUIPO` + actor * 10 + ranura * 2.
.proc eq_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta comp_and                  ; la ranura por dos
    lda comp_char
    and #$00FF
    asl a
    sta comp_and + 2              ; el actor por dos
    asl a
    asl a                       ; por ocho
    clc
    adc comp_and + 2
    clc
    adc comp_and
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: la ranura. Vuelve con el ítem en `eq_id`.
.proc eq_leer
.a8
.i16
    jsr eq_apuntar
    lda WMDATA
    sta comp_or23
    lda WMDATA
    sta comp_or23 + 1
    rts
.endproc

; A: la ranura; `eq_id`: el ítem nuevo.
.proc eq_escribir
.a8
.i16
    jsr eq_apuntar
    lda comp_or23
    sta WMDATA
    lda comp_or23 + 1
    sta WMDATA
    rts
.endproc

; El `k` del ítem de `eq_id`, en X, y Z=1 si es ninguno o uno que la ROM no
; conoce.
.proc eq_k
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    beq ninguno
    cmp #ITEMS_N
    bcs ninguno
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq ninguno8
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
.a16
ninguno:
    sep #$20
.a8
ninguno8:
    lda #0                      ; Z=1
    rts
.endproc

; Cuántos hay en el inventario del ítem `eq_id`, en A.
.proc eq_inv_apuntar
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; Uno más —topado en 99— o uno menos del ítem `eq_id`. A: 1 suma, 0 resta.
.proc eq_inv_mover
.a8
.i16
    pha
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_and
    jsr eq_inv_apuntar
    pla
    beq resta
    lda comp_and
    cmp #ITEM_MAX
    bcs listo
    inc a
    bra escribir
resta:
    lda comp_and
    beq listo
    dec a
escribir:
    sta WMDATA
listo:
    rts
.endproc

; ¿El ítem `eq_id` es un arma a dos manos? Z=0 si sí.
.proc eq_dos_manos
.a8
.i16
    jsr eq_k
    beq no
    lda item_uso, x
    and #8
    rts
no:
    lda #0
    rts
.endproc

; El ítem que tendría la ranura A: el que tiene, o —eligiendo— el que marca
; el cursor si es la ranura elegida, y ninguno en la otra si el arma es a dos
; manos. Es `pantallas.equipar` sin tocar nada. Vuelve en `eq_id`.
.proc eq_efectivo
.a8
.i16
    sta comp_or01 + 3
    lda comp_col + 1
    beq tiene
    lda comp_or01 + 3
    cmp comp_col
    bne otra
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    rts
otra:
    ; Un arma a dos manos saca el escudo; un escudo saca el arma a dos manos.
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_or01 + 3
    cmp #1
    bne no_escudo
    lda comp_col
    bne tiene                   ; no se está eligiendo el arma
    jsr eq_dos_manos
    bne ninguno
    bra tiene
no_escudo:
    lda comp_or01 + 3
    bne tiene                   ; ni escudo ni arma: la de siempre
    lda comp_col
    cmp #1
    bne tiene                   ; no se está eligiendo el escudo
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq tiene                   ; sacarse el escudo no toca el arma
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    bne ninguno
    rts                         ; `eq_id` ya es el arma
tiene:
    lda comp_or01 + 3
    jmp eq_leer
ninguno:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; El parámetro `eq_param` —0 ataque, 1 defensa, 2 espíritu, 3 agilidad— con el
; equipo que dice `eq_efectivo`, en `pant_valor`, topado en [1, 999].
.proc eq_parametro
.a8
.i16
    ; El del nivel: `actor_params`, cuatro palabras por actor.
    rep #$20
.a16
    lda comp_char
    and #$00FF
    asl a
    asl a
    asl a
    sta comp_or01
    lda comp_or01 + 2
    and #$00FF
    asl a
    clc
    adc comp_or01
    tax
    lda f:actor_params, x       ; fuera del banco 0: ver `actor_params`
    sta comp_or01
    sep #$20
.a8
    lda #0
ranura:
    pha
    jsr eq_efectivo
    jsr eq_k
    beq sin_puntos
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; ocho bytes por ítem
    sta comp_and
    lda comp_or01 + 2
    and #$00FF
    asl a
    clc
    adc comp_and
    tax
    lda f:item_puntos, x
    clc
    adc comp_or01
    sta comp_or01
    sep #$20
.a8
sin_puntos:
    pla
    inc a
    cmp #5
    bcc ranura
    rep #$20
.a16
    lda comp_or01
    bmi uno                     ; con signo: el equipo puede restar
    beq uno
    cmp #1000
    bcc listo
    lda #999
    bra listo
uno:
    lda #1
listo:
    sta comp_dup
    sep #$20
.a8
    rts
.endproc

; La lista de lo que el actor puede ponerse en `eq_ranura`, como `k` en
; `FAR_ITEM_LISTA`, y al final un $FF que es la línea vacía. Cuántos en
; `eq_n`. Es `pantallas.candidatos`.
.proc eq_lista_armar
.a8
.i16
    stz comp_base
    ldx #1
otro:
    rep #$20
.a16
    txa
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq siguiente
    lda f:item_k, x
    cmp #$FF
    beq siguiente
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; X = k
    sep #$20
.a8
    lda comp_col
    inc a
    cmp item_tipo, x
    bne no_va
    ; ¿Lo puede usar el actor? Un bit por actor, ocho bytes por ítem.
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta comp_and
    lda comp_char
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc comp_and
    sta comp_and                ; el byte; `comp_and` ya no lleva k por ocho
    pla
    and #$0007
    sta comp_and + 2              ; y el bit
    sep #$20
.a8
    ; Con `f:` porque `item_actores` se mudó a RODATA el 2026-09-13: son 496
    ; bytes y el área del banco 0 ya se pasaba por quince antes de las
    ; habilidades. Cuesta un byte y un ciclo por lectura, y esto corre una vez
    ; por ítem al abrir la pantalla de equipo.
    ;
    ; **Por X y no por Y**: el 65816 no tiene `lda long, y`, sólo `long, x`. X
    ; trae el `k` del ítem y lo necesita más abajo, así que va y vuelve por la
    ; pila. El `plx` no deja ninguna bandera mirada: lo que sigue es un `and`.
    ;
    ; El índice sale de `comp_and` y no de Y, y eso no es indistinto: dos ramas
    ; mudaron este mismo código a RODATA por separado, una dejando el byte en Y
    ; —`tay`— y la otra en `comp_and`. En el merge git se quedó con el `sta
    ; comp_and` de una y dejó el `tyx` de la otra en conflicto: juntas
    ; ensamblaban y leían un registro que ya nadie cargaba.
    phx
    ldx comp_and
    lda f:item_actores, x
    plx
    ldy comp_and + 2
    beq bit_listo
correr:
    lsr a
    dey
    bne correr
bit_listo:
    and #1
    beq no_va
    txa                         ; el k, que entra en un byte
    pha
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_base
no_va:
    plx
siguiente:
    inx
    cpx #ITEMS_N
    bcs lista_lista
    jmp otro                    ; los 127 bytes de un `bcc` se quedaron cortos
                                ; al leer `item_actores` larga
lista_lista:
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda #$FF                    ; la línea vacía
    sta WMDATA
    inc comp_base
    rts
.endproc

; El ítem del lugar A de la lista, en `eq_id`: 0 si es la línea vacía.
.proc eq_de_lista
.a8
.i16
    jsr item_de_lista
    cmp #$FF
    beq vacia
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    sta comp_or23
    sep #$20
.a8
    rts
vacia:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Escribe en `eleg_tabla` el nombre del ítem `eq_id`, si la ROM lo conoce, con
; no más de A letras.
.proc eq_nombre
.a8
.i16
    sta comp_dup + 3
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax                         ; 3k, el nombre
    sep #$20
.a8
    stz temp + 1
    jmp pant_texto
nada:
    lda #255
    sta comp_dup + 3
    rts
.endproc

; La descripción del ítem `eq_id`, en los dos renglones de arriba.
.proc eq_desc
.a8
.i16
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    inc a                       ; 3k + 1
    pha
    lda #PANT_DESC_POS
    sta eleg_tabla
    plx
    phx
    sep #$20
.a8
    stz temp + 1
    jsr pant_texto
    rep #$20
.a16
    lda #(PANT_DESC_POS + 128)
    sta eleg_tabla
    plx
    inx
    sep #$20
.a8
    stz temp + 1
    jmp pant_texto
nada:
    rts
.endproc

; La pantalla entera, en el búfer: `pantallas.pantalla_equipo`.
.proc eq_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsr pant_limpiar
    stz temp + 1
    ; --- el nombre del actor ---
    rep #$20
.a16
    lda #EQ_ACTOR_POS
    sta eleg_tabla
    lda comp_char
    and #$00FF
    asl a
    tax
    lda actor_txt, x
    tax
    cmp #$FFFF                  ; un actor sin nombre en esta ROM
    sep #$20                    ; `sep` no toca Z
.a8
    beq sin_nombre
    jsr pant_texto
sin_nombre:
    ; --- la descripción ---
    lda comp_col + 1
    beq la_puesta
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    bra desc
la_puesta:
    lda comp_col
    jsr eq_leer
desc:
    jsr eq_desc
    ; --- los parámetros: ahora y, eligiendo, después ---
    stz comp_or01 + 2
param:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    sta eleg_tabla
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #EQ_TEXTO_PARAM
    tax
    sep #$20
.a8
    stz temp + 1
    jsr pant_texto
    lda comp_col + 1
    pha
    stz comp_col + 1            ; ahora: lo puesto
    jsr eq_parametro
    pla
    sta comp_col + 1
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_VALOR
    sta eleg_tabla
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsr pant_numero
    lda comp_col + 1
    beq sin_flecha
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_FLECHA
    sta eleg_tabla
    sep #$20
.a8
    lda #$3E                    ; '>'
    jsr pant_glifo
    jsr eq_parametro            ; después: con lo que marca el cursor
    lda #3
    sta comp_dup + 2
    jsr pant_numero
sin_flecha:
    inc comp_or01 + 2
    lda comp_or01 + 2
    cmp #4
    bcc param
    lda comp_col + 1
    bne lista
    ; --- las ranuras ---
    lda #0
ranura:
    pha
    cmp comp_col
    bne sin_cursor
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    lda #$3E
    jsr pant_glifo
sin_cursor:
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_TERM
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    rep #$20
.a16
    and #$00FF
    clc
    adc #EQ_TEXTO_RANURA
    tax
    sep #$20
.a8
    jsr pant_texto
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    jsr eq_leer
    lda #EQ_RANURA_ANCHO
    jsr eq_nombre
    pla
    inc a
    cmp #5
    bcc ranura
    rts

    ; --- la lista ---
lista:
    lda #0
lista_fila:
    pha
    clc
    adc comp_fase + 1
    cmp comp_base
    bcs lista_listo
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    clc
    adc comp_fase + 1
    cmp comp_fase
    bne sin_cursor_lista
    lda #$3E
    jsr pant_glifo
sin_cursor_lista:
    pla
    pha
    clc
    adc comp_fase + 1
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq lista_siguiente         ; la línea vacía
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #PANT_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    lda #255
    jsr eq_nombre
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #PANT_DOS_PUNTOS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$3A                    ; ':'
    jsr pant_glifo
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsr pant_numero
lista_siguiente:
    pla
    inc a
    cmp #EQ_LISTA_FILAS
    bcc lista_fila
    rts
lista_listo:
    pla
    rts

; A16 = la posición del parámetro `eq_param`.
param_pos:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    rts
.a8

; A: la ranura. A16 = la posición de su fila.
fila_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; por 128: dos filas de celdas
    clc
    adc #EQ_RANURA_POS0
    rts
.a8

; A: la fila de la lista. A16 = la posición de su fila.
fila_pos_lista:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #EQ_LISTA_POS0
    rts
.a8
.endproc

; A sobre la lista: `pantallas.equipar` con lo que marca el cursor.
.proc eq_equipar
.a8
.i16
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    lda comp_col
    jsr sacar
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq listo
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda #0
    jsr eq_inv_mover            ; uno menos en el inventario
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_col
    jsr eq_escribir
    ; Las dos manos.
    lda comp_col
    bne no_arma
    jsr eq_dos_manos            ; `eq_id` es el arma nueva
    beq listo
    lda #1
    jmp sacar
no_arma:
    cmp #1
    bne listo
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    beq listo
    lda #0
    jmp sacar
listo:
    rts

; A: la ranura. Lo que tiene vuelve al inventario y queda vacía.
sacar:
    pha
    jsr eq_leer
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq vacia
    lda #1
    jsr eq_inv_mover
    stz comp_or23
    stz comp_or23 + 1
    pla
    jmp eq_escribir
vacia:
    pla
    rts
.endproc

; La pantalla de equipo del actor A, hasta que el jugador vuelve con B.
.proc equipo_pantalla
.a8
.i16
    sta comp_char
    stz comp_col
    stz comp_col + 1
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_banco_subir
    jsr eq_componer
    jsr pant_subir
    jsr ranura_ppu_prender
espera:
    jsr wait_vblank
    ; El control primero y el DMA después. Al revés, los 1792 bytes duran
    ; unas diez líneas y `read_pad` llegaba con la lectura automática del
    ; control ya terminada: esperaba la del cuadro siguiente, cada vuelta
    ; duraba dos cuadros, y un toque de un cuadro se perdía la mitad de las
    ; veces. Con el control leído, el DMA entra igual en el vblank.
    jsr read_pad
    jsr pant_subir
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    lda comp_col + 1
    beq en_ranuras
    jmp en_lista
en_ranuras:
    lda titulo_flancos
    and #PAD_UP
    beq r_no_arriba
    lda comp_col
    beq espera
    dec comp_col
    jmp recomponer
r_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq r_no_abajo
    lda comp_col
    cmp #4
    bcs espera
    inc comp_col
    jmp recomponer
r_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq r_mira_a
    rts
r_mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera
    jsr eq_lista_armar
    stz comp_fase
    stz comp_fase + 1
    lda #1
    sta comp_col + 1
    jmp recomponer
en_lista:
    lda titulo_flancos
    and #PAD_UP
    beq l_no_arriba
    lda comp_fase
    beq espera2
    dec comp_fase
    lda comp_fase
    cmp comp_fase + 1
    bcs recomponer
    sta comp_fase + 1
    bra recomponer
l_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq l_no_abajo
    lda comp_fase
    inc a
    cmp comp_base
    bcs espera2
    sta comp_fase
    sec
    sbc comp_fase + 1
    cmp #EQ_LISTA_FILAS
    bcc recomponer
    inc comp_fase + 1
    bra recomponer
l_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq l_mira_a
    stz comp_col + 1
    bra recomponer
l_mira_a:
    lda pad_a
    beq espera2
    lda pad_a_ant
    bne espera2
    jsr eq_equipar
    stz comp_col + 1
recomponer:
    jsr eq_componer
espera2:
    jmp espera
.endproc

; --- la tienda -----------------------------------------------------------------
;
; `Scene_Shop`, abierta por `OP_SHOP` desde el intérprete, como guardar: la
; pantalla bloquea adentro de la página, no cuesta ningún tick, y al salir el
; mapa vuelve y la página sigue. Es una pantalla de texto —ver "las pantallas
; de texto"— y `pantallas.pantalla_tienda` es la referencia de cada modo. Lo
; que vende va como `k` en `FAR_TIENDA`; la lista de vender, en
; `FAR_ITEM_LISTA`.
;
; El escritorio, prestado del compositor de mensajes:
;   ti_modo      es comp_col       ; TI_PRINCIPAL ... TI_VENDIDO
;   ti_tipo      es comp_col + 1   ; 0 compra y vende, 1 compra, 2 vende
;   ti_juego     es comp_fase      ; el juego de mensajes, 0 a 2
;   ti_resaludo  es comp_fase + 1  ; si ya se volvió a la principal
;   ti_elegido   es comp_base      ; el cursor
;   ti_arriba    es comp_base + 1  ; el primero que se ve de la lista
;   ti_n         es comp_mask      ; cuántos hay en la lista del modo
;   ti_nt        es comp_mask + 1  ; cuántos vende la tienda
;   ti_cuantos   es comp_color     ; la cantidad que se elige
;   ti_max       es comp_fila      ; y hasta cuánto
;   ti_timer     es comp_glifo     ; los cuadros del "listo"
;   ti_pos       es comp_glifo + 1 ; dos bytes: dónde va la cifra
;   ti_num       es comp_or01      ; tres bytes: un número de 24 bits
FAR_TIENDA = $2B00
TI_PRINCIPAL = 0
TI_COMPRAR = 1
TI_CUANTOS_COMPRA = 2
TI_COMPRADO = 3
TI_VENDER = 4
TI_CUANTOS_VENTA = 5
TI_VENDIDO = 6

; A: un lugar de la lista del modo. Vuelve con A = su `k`.
.proc ti_k_de
.a8
.i16
    pha
    lda comp_col
    cmp #TI_VENDER
    bcs de_venta
    pla
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_TIENDA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
de_venta:
    pla
    jmp item_de_lista
.endproc

; El ítem que marca el cursor, en `eq_id`, y su `k` en X.
.proc ti_item
.a8
.i16
    lda comp_base
    jsr ti_k_de
    rep #$20
.a16
    and #$00FF
    tax
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    rts
.endproc

; El precio del `k` de X, en `ti_num`, a la mitad si se vende.
.proc ti_precio
.a8
.i16
    rep #$20
.a16
    txa
    asl a
    tay
    lda item_precio, y
    sta comp_or01
    sep #$20
.a8
    stz comp_or01 + 2
    lda comp_col
    cmp #TI_VENDER
    bcc listo
    rep #$20
.a16
    lsr comp_or01
    sep #$20
.a8
listo:
    rts
.endproc

; ¿Alcanza el oro para el `k` de X, y tiene menos de 99? Z=0 si se puede
; comprar. `Window_ShopBuy::CheckEnable`.
.proc ti_puede
.a8
.i16
    phx
    jsr ti_precio
    plx
    ; oro >= precio, de 24 bits
    lda oro + 2
    bne alcanza
    rep #$20
.a16
    lda oro
    cmp comp_or01
    sep #$20
.a8
    bcc no
alcanza:
    rep #$20
.a16
    txa
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    jsr eq_inv_apuntar
    lda WMDATA
    cmp #ITEM_MAX
    bcs no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Un número de 24 bits de `ti_num` —se pierde—, alineado a la derecha con su
; última cifra en `ti_pos`, en la variante de `temp + 1`. Se divide por diez
; de a un byte, como el oro del menú.
.proc pant_numero24
.a8
.i16
cifra:
    stz temp + 3                ; el resto que se arrastra
    ldx #2
dividir:
    lda comp_or01, x
    sta WRDIVL
    lda temp + 3
    sta WRDIVH
    lda #10
    sta WRDIVB
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta comp_or01, x
    lda RDMPYL
    sta temp + 3
    dex
    bpl dividir
    rep #$20
.a16
    lda comp_glifo + 1
    sta eleg_tabla
    dec a
    dec a
    sta comp_glifo + 1
    sep #$20
.a8
    lda temp + 3
    clc
    adc #$30
    jsr pant_glifo
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    bne cifra
    lda comp_or01 + 2
    bne cifra
    rts
.endproc

; Cuántos del ítem `eq_id` lleva puestos el grupo: `GetEquippedItemCount`.
; Vuelve en `pant_valor`.
.proc ti_llevados
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    sta comp_or01                  ; el que se busca
    stz comp_dup
    sep #$20
.a8
    lda #0
miembro:
    cmp grupo_n
    bcs listo
    pha
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    sta comp_char
    lda #0
ranura:
    pha
    jsr eq_leer
    rep #$20
.a16
    lda comp_or23
    cmp comp_or01
    bne otra
    inc comp_dup
otra:
    sep #$20
.a8
    pla
    inc a
    cmp #5
    bcc ranura
    pla
    inc a
    bra miembro
listo:
    rep #$20
.a16
    lda comp_or01
    sta comp_or23
    sep #$20
.a8
    rts
.endproc

; El mensaje A del juego de la tienda, en los dos renglones de arriba.
.proc ti_mensaje
.a8
.i16
    sta temp + 3
    lda comp_fase
    asl a
    asl a
    asl a                       ; por 8
    clc
    adc comp_fase
    adc comp_fase
    adc comp_fase                ; por 11
    clc
    adc temp + 3
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos renglones cada uno
    clc
    adc #TI_TEXTO
    pha
    lda #PANT_DESC_POS
    sta eleg_tabla
    plx
    phx
    sep #$20
.a8
    stz temp + 1
    jsr pant_texto
    rep #$20
.a16
    lda #(PANT_DESC_POS + 128)
    sta eleg_tabla
    plx
    inx
    sep #$20
.a8
    stz temp + 1
    jmp pant_texto
.endproc

; La moneda en `eleg_tabla`.
.proc ti_moneda
.a8
.i16
    stz temp + 1
    ldx #TI_TEXTO_MONEDA
    jmp pant_texto
.endproc

; La pantalla entera, en el búfer: `pantallas.pantalla_tienda`.
.proc ti_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsr pant_limpiar
    ; --- el mensaje: saludo, resaludo, o el del modo ---
    lda comp_col
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda mensaje_de, x
    bne con_mensaje
    lda comp_fase + 1             ; la principal: saludo o resaludo
con_mensaje:
    jsr ti_mensaje
    lda comp_col
    bne no_principal
    jmp principal
no_principal:
    ; --- el oro, y cuántos tiene y lleva puestos del que marca el cursor ---
    lda comp_col
    cmp #TI_VENDER
    bne cerca_12209
    jmp sin_oro
cerca_12209:
    rep #$20
.a16
    lda oro
    sta comp_or01
    lda #TI_ORO_POS
    sta comp_glifo + 1
    clc
    adc #2
    pha
    sep #$20
.a8
    lda oro + 2
    sta comp_or01 + 2
    stz temp + 1
    jsr pant_numero24
    rep #$20
.a16
    pla
    sta eleg_tabla
    sep #$20
.a8
    jsr ti_moneda
    lda comp_mask
    beq sin_oro
    jsr ti_item
    rep #$20
.a16
    lda #TI_TENGO_POS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    ldx #TI_TEXTO_TENGO
    jsr pant_texto
    jsr ti_item
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    rep #$20
.a16
    lda #TI_TENGO_NUM
    sta eleg_tabla
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    jsr pant_numero
    rep #$20
.a16
    lda #TI_LLEVO_POS
    sta eleg_tabla
    sep #$20
.a8
    ldx #TI_TEXTO_LLEVO
    jsr pant_texto
    jsr ti_item
    jsr ti_llevados
    rep #$20
.a16
    lda #TI_LLEVO_NUM
    sta eleg_tabla
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    jsr pant_numero
sin_oro:
    lda comp_col
    cmp #TI_CUANTOS_COMPRA
    beq cuantos
    cmp #TI_CUANTOS_VENTA
    beq cuantos
    jmp lista

    ; --- la cantidad: el ítem, "x" y cuántos, y el total ---
cuantos:
    jsr ti_item
    rep #$20
.a16
    lda #(TI_LISTA_POS0 + PANT_NOMBRE)
    sta eleg_tabla
    sep #$20
.a8
    lda #255
    jsr eq_nombre
    rep #$20
.a16
    lda #(TI_LISTA_POS0 + TI_CUANTOS)
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$78                    ; 'x'
    jsr pant_glifo
    lda comp_color
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsr pant_numero
    jsr ti_item
    jsr ti_precio
    jsr ti_por_cuantos          ; ti_num = precio * cuantos
    rep #$20
.a16
    lda #TI_TOTAL_POS
    sta comp_glifo + 1
    sep #$20
.a8
    stz temp + 1
    jsr pant_numero24
    rep #$20
.a16
    lda #(TI_TOTAL_POS + 2)
    sta eleg_tabla
    sep #$20
.a8
    jmp ti_moneda

    ; --- la principal: las órdenes ---
principal:
    lda #0
orden:
    pha
    cmp comp_base
    bne sin_cursor
    jsr orden_pos
    rep #$20
.a16
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$3E
    jsr pant_glifo
sin_cursor:
    pla
    pha
    jsr orden_pos
    rep #$20
.a16
    clc
    adc #PANT_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    jsr orden_mensaje           ; qué término: comprar, vender o salir
    jsr ti_renglon1
    pla
    inc a
    cmp comp_mask
    bcc orden
    rts

    ; --- la lista: comprar o vender ---
lista:
    lda #0
lista_fila:
    pha
    clc
    adc comp_base + 1
    bcc cerca_12378
    jmp lista_listo
cerca_12378:
    cmp comp_mask
    bcc cerca_12382
    jmp lista_listo
cerca_12382:
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    sta eleg_tabla
    sta comp_glifo + 1                  ; la fila, para las posiciones de abajo
    sep #$20
.a8
    pla
    pha
    clc
    adc comp_base + 1
    pha
    jsr ti_k_de
    rep #$20
.a16
    and #$00FF
    tax
    asl a
    tay
    lda item_id, y
    sta comp_or23
    sep #$20
.a8
    phx
    ; el color: comprando, si alcanza; vendiendo, si vale algo
    lda comp_col
    cmp #TI_VENDER
    bcs color_venta
    jsr ti_puede
    bra color
color_venta:
    jsr ti_precio
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
color:
    beq gris
    lda #0
    bra color_listo
gris:
    lda #1
color_listo:
    sta temp + 1
    plx
    pla                         ; el lugar en la lista
    cmp comp_base
    bne sin_cursor_lista
    lda comp_col
    cmp #TI_COMPRAR
    beq con_cursor
    cmp #TI_VENDER
    bne sin_cursor_lista
con_cursor:
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #EQ_CURSOR
    sta eleg_tabla
    sep #$20
.a8
    lda temp + 1
    pha
    stz temp + 1
    phx                         ; `pant_glifo` se lleva X, que es el `k`
    lda #$3E
    jsr pant_glifo
    plx
    pla
    sta temp + 1
sin_cursor_lista:
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #PANT_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    phx
    lda temp + 1
    pha
    lda #255
    sta comp_dup + 3
    jsr eq_k                    ; el nombre, con la variante puesta
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax
    sep #$20
.a8
    pla
    sta temp + 1
    pha
    jsr pant_texto
    pla
    sta temp + 1
    plx
    lda comp_col
    cmp #TI_VENDER
    bcs cuenta
    ; comprando: el precio, alineado a la derecha
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #TI_PRECIO
    pha
    sep #$20
.a8
    jsr ti_precio
    rep #$20
.a16
    pla
    sta comp_glifo + 1
    sep #$20
.a8
    jsr pant_numero24
    bra lista_siguiente
cuenta:
    ; vendiendo: cuántos tiene
    rep #$20
.a16
    lda comp_glifo + 1
    clc
    adc #PANT_DOS_PUNTOS
    sta eleg_tabla
    sep #$20
.a8
    lda #$3A
    jsr pant_glifo
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsr pant_numero
lista_siguiente:
    pla
    inc a
    cmp #TI_LISTA_FILAS
    bcs lista_fin
    jmp lista_fila
lista_fin:
    rts
lista_listo:
    pla
    rts

; A: la orden de la principal. A16 = la posición de su fila.
orden_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_ORDEN_POS0
    rts
.a8

; A: la fila de la lista. A16 = la posición de su fila.
fila_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #TI_LISTA_POS0
    rts
.a8

; A: la orden. A = el número de mensaje: 2 comprar, 3 vender, 4 salir; con
; una sola orden, la que dice el tipo.
orden_mensaje:
    pha
    lda comp_col + 1
    beq tres
    pla
    lda comp_col + 1                 ; 1 compra: 2; 2 vende: 3
    inc a
    rts
tres:
    pla
    clc
    adc #2
    rts

; A: el número de mensaje. Su primer renglón, en `eleg_tabla`, en blanco.
ti_renglon1:
    sta temp + 3
    lda comp_fase
    asl a
    asl a
    asl a
    clc
    adc comp_fase
    adc comp_fase
    adc comp_fase
    clc
    adc temp + 3
    rep #$20
.a16
    and #$00FF
    asl a
    clc
    adc #TI_TEXTO
    tax
    sep #$20
.a8
    stz temp + 1
    jmp pant_texto

; El mensaje de cada modo: 0 es "el saludo o el resaludo".
mensaje_de:
    .byte 0, 5, 6, 7, 8, 9, 10
.endproc

; `ti_num` por `ti_cuantos`, sumando: son 99 vueltas a lo sumo.
.proc ti_por_cuantos
.a8
.i16
    rep #$20
.a16
    lda comp_or01
    sta comp_and
    stz comp_or01
    sep #$20
.a8
    lda comp_or01 + 2
    sta comp_and + 2
    stz comp_or01 + 2
    lda comp_color
    beq listo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
otra:
    rep #$20
.a16
    lda comp_or01
    clc
    adc comp_and
    sta comp_or01
    sep #$20
.a8
    lda comp_or01 + 2
    adc comp_and + 2
    sta comp_or01 + 2
    dex
    bne otra
listo:
    rts
.endproc

; Hasta cuántos se pueden comprar del que marca el cursor: los que faltan para
; 99, y no más de los que paga el oro. Vendiendo, los que tiene. En `ti_max`.
.proc ti_maximo
.a8
.i16
    jsr ti_item
    phx
    jsr eq_inv_apuntar
    lda WMDATA
    plx
    sta temp + 3                ; cuántos tiene
    lda comp_col
    cmp #TI_VENDER
    bcc comprando
    lda temp + 3
    sta comp_fila
    rts
comprando:
    lda #ITEM_MAX
    sec
    sbc temp + 3
    sta temp + 3                ; los que faltan
    jsr ti_precio
    rep #$20
.a16
    lda oro
    sta comp_and
    sep #$20
.a8
    lda oro + 2
    sta comp_and + 2
    stz comp_fila
otro:
    lda comp_fila
    cmp temp + 3
    bcs listo
    ; ¿eq_tmp >= precio? Si el precio es cero, siempre.
    rep #$20
.a16
    lda comp_and
    sec
    sbc comp_or01
    tay
    sep #$20
.a8
    lda comp_and + 2
    sbc comp_or01 + 2
    bcc listo
    sta comp_and + 2
    rep #$20
.a16
    tya
    sta comp_and
    sep #$20
.a8
    inc comp_fila
    bra otro
listo:
    rts
.endproc

; Comprar o vender `ti_cuantos` del que marca el cursor: el oro y el
; inventario, como `UpdateNumberInput`.
.proc ti_cerrar_trato
.a8
.i16
    jsr ti_item
    jsr ti_precio
    jsr ti_por_cuantos
    lda comp_col
    cmp #TI_CUANTOS_VENTA
    beq vender
    ; --- comprar: el oro baja y los ítems suben ---
    rep #$20
.a16
    lda oro
    sec
    sbc comp_or01
    sta oro
    sep #$20
.a8
    lda oro + 2
    sbc comp_or01 + 2
    sta oro + 2
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
suma:
    phx
    jsr ti_item
    lda #1
    jsr eq_inv_mover
    plx
    dex
    bne suma
    rts
vender:
    ; --- vender: el oro sube, topado en ORO_MAX, y los ítems bajan ---
    rep #$20
.a16
    lda oro
    clc
    adc comp_or01
    sta oro
    sep #$20
.a8
    lda oro + 2
    adc comp_or01 + 2
    sta oro + 2
    cmp #^ORO_MAX
    bcc resta
    bne tope
    rep #$20
.a16
    lda oro
    cmp #.loword(ORO_MAX)
    sep #$20
.a8
    bcc resta
    beq resta
tope:
    rep #$20
.a16
    lda #.loword(ORO_MAX)
    sta oro
    sep #$20
.a8
    lda #^ORO_MAX
    sta oro + 2
resta:
    lda comp_color
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
quita:
    phx
    jsr ti_item
    lda #0
    jsr eq_inv_mover
    plx
    dex
    bne quita
    rts
.endproc

; La lista de vender: el inventario que la ROM conoce, en `FAR_ITEM_LISTA`.
.proc ti_lista_venta
.a8
.i16
    jsr items_armar_lista
    lda eleg_n
    sta comp_mask
    lda comp_base
    cmp comp_mask
    bcc listo
    lda comp_mask                    ; se vendió el último: el cursor sube
    beq cero
    dec a
cero:
    sta comp_base
listo:
    rts
.endproc

; A: el modo nuevo. Pone lo que hace falta para entrar: la lista, el cursor.
.proc ti_modo_poner
.a8
.i16
    sta comp_col
    cmp #TI_PRINCIPAL
    bne no_principal
    lda comp_col + 1
    beq tres
    lda #1
    bra n_listo
tres:
    lda #3
n_listo:
    sta comp_mask
    rts
no_principal:
    cmp #TI_COMPRAR
    bne no_comprar
    lda comp_mask + 1
    sta comp_mask
    rts
no_comprar:
    cmp #TI_VENDER
    bne listo
    jmp ti_lista_venta
listo:
    rts
.endproc

; El cursor de la lista, con la vista que lo sigue.
.proc ti_mover
.a8
.i16
    sta comp_base
    cmp comp_base + 1
    bcs no_arriba
    sta comp_base + 1
    rts
no_arriba:
    sec
    sbc comp_base + 1
    cmp #TI_LISTA_FILAS
    bcc listo
    lda comp_base
    sec
    sbc #(TI_LISTA_FILAS - 1)
    sta comp_base + 1
listo:
    rts
.endproc

; La tienda: `ti_tipo`, `ti_juego` y `FAR_TIENDA` con `ti_nt` ítems, puestos
; por `op_shop`. Vuelve cuando el jugador sale.
.proc tienda_pantalla
.a8
.i16
    stz comp_fase + 1
    stz comp_base
    stz comp_base + 1
    lda comp_col + 1
    beq a_principal
    cmp #1
    beq a_comprar
    lda #TI_VENDER
    bra empieza
a_comprar:
    lda #TI_COMPRAR
    bra empieza
a_principal:
    lda #TI_PRINCIPAL
empieza:
    jsr ti_modo_poner
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_banco_subir
    jsr ti_componer
    jsr pant_subir
    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto
espera:
    jsr wait_vblank
    jsr read_pad                ; el control antes del DMA: ver el equipo
    jsr pant_subir
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    ; Según el modo. Sin `jmp (tabla, x)` en el ensamblador, una cadena.
    lda comp_col
    bne no_es_principal
    jmp principal
no_es_principal:
    cmp #TI_CUANTOS_COMPRA
    bne :+
    jmp cuantos
:   cmp #TI_CUANTOS_VENTA
    bne :+
    jmp cuantos
:   cmp #TI_COMPRADO
    bne :+
    jmp listo_trato
:   cmp #TI_VENDIDO
    bne :+
    jmp listo_trato
:   jmp comprar                 ; comprar y vender comparten el código

    ; --- la principal ---
principal:
    lda titulo_flancos
    and #PAD_UP
    beq p_no_arriba
    lda comp_base
    beq espera
    dec comp_base
    jmp recomponer
p_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq p_no_abajo
    lda comp_base
    inc a
    cmp comp_mask
    bcs espera
    sta comp_base
    jmp recomponer
p_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq p_mira_a
    jmp salir
p_mira_a:
    jsr flanco_a
    beq espera
    lda comp_base
    cmp #2
    bne p_no_salir
    jmp salir
p_no_salir:
    cmp #1
    beq p_vender
    lda #TI_COMPRAR
    bra p_entrar
p_vender:
    lda #TI_VENDER
p_entrar:
    stz comp_base
    stz comp_base + 1
    jsr ti_modo_poner
    jmp recomponer

    ; --- las listas ---
comprar:
vender:
    lda titulo_flancos
    and #PAD_UP
    beq l_no_arriba
    lda comp_base
    beq espera2
    dec a
    jsr ti_mover
    jmp recomponer
l_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq l_no_abajo
    lda comp_base
    inc a
    cmp comp_mask
    bcs espera2
    jsr ti_mover
    jmp recomponer
l_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq l_mira_a
    ; B: a la principal, con el resaludo; sin principal, afuera.
    lda comp_col + 1
    beq a_la_principal
    jmp salir
a_la_principal:
    lda comp_col
    cmp #TI_VENDER
    lda #0
    bcc cursor_listo
    lda #1                      ; el cursor sobre la orden de donde se vuelve
cursor_listo:
    sta comp_base
    lda #1
    sta comp_fase + 1
    lda #TI_PRINCIPAL
    jsr ti_modo_poner
    jmp recomponer
l_mira_a:
    jsr flanco_a
    beq espera2
    lda comp_mask
    beq espera2
    lda comp_col
    cmp #TI_VENDER
    bcs l_vender
    jsr ti_item                 ; X = k
    jsr ti_puede
    beq espera2                 ; en gris: suena y no hace nada
    lda #TI_CUANTOS_COMPRA
    bra l_cuantos
l_vender:
    jsr ti_item
    jsr ti_precio
    rep #$20
.a16
    lda comp_or01
    sep #$20
.a8
    beq espera2                 ; no vale nada
    lda #TI_CUANTOS_VENTA
l_cuantos:
    pha
    jsr ti_maximo
    pla
    sta comp_col
    lda #1
    sta comp_color
    jmp recomponer
espera2:
    jmp espera

    ; --- la cantidad ---
cuantos:
    lda titulo_flancos
    and #PAD_RIGHT
    beq c_no_derecha
    lda #1
    bra c_sumar
c_no_derecha:
    lda titulo_flancos
    and #PAD_LEFT
    beq c_no_izquierda
    lda #$FF
    bra c_sumar
c_no_izquierda:
    lda titulo_flancos
    and #PAD_UP
    beq c_no_arriba
    lda #10
    bra c_sumar
c_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq c_no_abajo
    lda #$F6                    ; -10
c_sumar:
    ; Con signo, y topado en [1, ti_max].
    clc
    adc comp_color
    bmi c_uno                   ; bajó de cero: son 99 como mucho
    beq c_uno
    cmp comp_fila
    bcc c_poner
    beq c_poner
    lda comp_fila
    bra c_poner
c_uno:
    lda #1
c_poner:
    sta comp_color
    jmp recomponer
c_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq c_mira_a
    lda comp_col
    cmp #TI_CUANTOS_VENTA
    beq c_a_vender
    lda #TI_COMPRAR
    sta comp_col
    jmp recomponer
c_a_vender:
    lda #TI_VENDER
    sta comp_col
    jmp recomponer
c_mira_a:
    jsr flanco_a
    beq espera2
    jsr ti_cerrar_trato
    lda #TI_SEGUNDO
    sta comp_glifo
    lda comp_col
    inc a                       ; CUANTOS_COMPRA -> COMPRADO, y la venta igual
    sta comp_col
    cmp #TI_VENDIDO
    bne recomponer
    jsr ti_lista_venta          ; lo vendido puede no estar más
    jmp recomponer

    ; --- el "listo", un segundo ---
listo_trato:
    dec comp_glifo
    bne espera2
    lda comp_col
    dec a
    dec a                       ; COMPRADO -> COMPRAR, VENDIDO -> VENDER
    sta comp_col
recomponer:
    jsr ti_componer
    jmp espera

salir:
    rts

; Z=0 si A se acaba de apretar.
flanco_a:
    lda pad_a
    beq no_a
    lda pad_a_ant
    beq si_a
no_a:
    lda #0
    rts
si_a:
    lda #1
    rts
.endproc

; --- la batalla -----------------------------------------------------------------
;
; `EnemyEncounter`, abierto por `OP_BATTLE` desde el intérprete: como la
; tienda y como guardar, la pantalla bloquea adentro de la página, `vueltas` no
; avanza mientras se ve y **no cuesta ningún tick**. Lo que la diferencia de
; las otras dos es que el resultado **elige por dónde sigue la página**: el
; opcode lleva los tres destinos y acá se le asigna al cursor el que toque.
;
; Las reglas —daño, acierto, crítico, varianza, orden de turnos, huida— salen
; de easyrpg-player y están escritas dos veces: acá y en `tools/port/batalla.py`,
; que es lo que le permite a `pruebas/rpgmaker/test_batalla.py` predecir el número
; exacto que cada HP va a tener. La pantalla es de texto, sobre negro.
;
; **El código de la pelea no vive en el banco 0**: son unos dos kilobytes y en
; el banco 0 quedaban trescientos bytes. Vive en RODATA —ver `batalla_correr`,
; al final del archivo— y se entra con `jsl`. De allá para acá no se puede
; volver con `jsr`, que no cambia el banco de programa, así que las rutinas del
; banco 0 que la pelea necesita se llaman por estos puentes de cuatro bytes.
; El banco de datos sigue siendo el 0 en los dos lados, así que un puente no
; tiene que tocarlo: lo único que hace es cambiar de banco de programa y
; volver.
;
; **Cada puente repone el banco de datos**, que del otro lado es $7E. No es un
; detalle: `eq_parametro` lee `actor_params` y `ranura_ppu_prender` escribe
; BG2SC, las dos con direccionamiento absoluto, y con el banco en $7E la
; primera leería WRAM y la segunda escribiría en la RAM en vez del PPU. Costó
; una tarde: los tres parámetros de cada actor salían en 999.
;
; `phk` acá empuja el banco de este código, que es el 0 porque el `jsl` llega
; con una dirección de $00xxxx.
ba_t_vblank:
    phb
    phk
    plb
    jsr wait_vblank
    plb
    rtl
ba_t_pad:
    phb
    phk
    plb
    jsr read_pad
    plb
    rtl
ba_t_subir:
    phb
    phk
    plb
    jsr pant_subir
    plb
    rtl
ba_t_limpiar:
    phb
    phk
    plb
    jsr pant_limpiar
    plb
    rtl
ba_t_texto:
    phb
    phk
    plb
    jsr pant_texto
    plb
    rtl
ba_t_numero:
    phb
    phk
    plb
    jsr pant_numero
    plb
    rtl
ba_t_glifo:
    phb
    phk
    plb
    jsr pant_glifo
    plb
    rtl
ba_t_banco:
    phb
    phk
    plb
    jsl f:items_banco_subir
    plb
    rtl
ba_t_ppu:
    phb
    phk
    plb
    jsr ranura_ppu_prender
    plb
    rtl
ba_t_param:
    phb
    phk
    plb
    jsr eq_parametro
    plb
    rtl
; Los dos del audio, que son de esta vuelta: un efecto de sonido —A16 el
; índice en `sonido_tabla`, $FFFF ninguno— y el tema, con A8.
ba_t_sonido:
    phb
    phk
    plb
    jsr sonido_tocar
    plb
    rtl
ba_t_bgm:
    phb
    phk
    plb
    jsr batalla_bgm
    plb
    rtl

; El paquete de audio A —el de la pelea al entrar, el del mapa al salir—, con
; la música callada primero.
;
; Callar antes no es un detalle: `paquete_cargar` deja **quietas** las muestras
; del tema que dice estar sonando, y ésas son justamente las que hay que
; desalojar para hacerle lugar al paquete nuevo. Es lo mismo que hace
; `tema_asegurar` antes de rearmar.
;
; El índice viene en **X y de dieciséis bits**, no en A: el paquete de la pelea
; va detrás de los de los mapas, así que con los 328 del juego entero no entra
; en un byte —y `mapa_actual`, que es lo que se pasa al salir, tampoco—.
;
; Con `BA_PAQUETE` en $FFFF —una ROM sin peleas— no hay nada que cargar; no
; puede pasar, porque acá se llega desde `op_battle`, pero el opcode existe
; en el bytecode de todas.
.proc batalla_audio_cargar
.a8
.i16
    cpx #$FFFF
    beq listo
    phx
    lda #$FF
    jsr batalla_bgm             ; callar, para que nada quede fijo
    plx
    rep #$20
.a16
    txa
    sta f:PAQ_MAPA
    sep #$20
.a8
    jsr paquete_cargar_ya
listo:
    rts
.endproc

; El tema de la pelea: A es el índice, o $FF para dejarla callada. Lo llaman
; `op_battle` —al entrar y al salir— y la pelea al ganar, por el puente de
; arriba.
;
; Callar no es `FadeOutBGM`: es lo mismo que hace `tema_asegurar` antes de
; rearmar el paquete, o sea soltar las ocho voces y poner `music_apagada`. Un
; mapa sin música es lo normal en este juego —los primeros no traen y la
; prende un `PlayBGM`—, así que volver de una pelea a un mapa callado tiene
; que callar de verdad y no dejar sonando el tema de batalla.
.proc batalla_bgm
.a8
.i16
    cmp #$FF
    beq callar
    jmp music_start
callar:
    php
    sei
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; las ocho voces sueltan
    plp
    rts
.endproc

; --- la lluvia ------------------------------------------------------------------
;
; `Game_Screen::UpdateRain` y `Weather::DrawRain`, con la regla de RM2k sobre
; la pantalla de 256x224: ver OP_WEATHER en eventos.py, que es la referencia. El
; estado vive en la RAM lejana: el tipo y la fuerza del clima, cuántas gotas
; hay y el azar de la lluvia —un xorshift propio, sembrado cada vez que el
; clima cambia— en `FAR_CLIMA`, y tres bytes por gota —x, y y la vida— en
; `FAR_LLUVIA`. La x y la y son de la superficie de 256x256 que va pegada al
; mapa, así que un byte alcanza y el paso de cada cuadro da la vuelta solo; en
; pantalla es eso menos el scroll. El clima no viaja en la partida: al cargar
; no llueve.
;
; `lluvia_tick` y `lluvia_oam` corren en cada cuadro que llueve y leen con el
; direccionamiento largo, que va de a una instrucción por byte: con la
; ventana de WMADD cada gota pagaba apuntarla.
FAR_CLIMA  = $2EF0
FAR_LLUVIA = $2F00
CLIMA_L    = $7E0000 + FAR_CLIMA
LLUVIA_L   = $7E0000 + FAR_LLUVIA

; El clima en cero: sin lluvia. En el reset.
.proc clima_limpiar
.a8
.i16
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    ldx #5
otro:
    stz WMDATA
    dex
    bne otro
    rts
.endproc

; `SetWeatherEffect`: `temp` el tipo, `temp + 1` la fuerza. Si no cambia nada
; no toca nada; si cambia, las gotas arrancan apagadas y el azar vuelve a su
; semilla. Se llama desde el intérprete, con el banco de datos donde esté el
; bytecode: sólo toca registros y la RAM baja.
.proc clima_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    cmp temp
    bne cambia
    lda WMDATA
    cmp temp + 1
    bne cambia
    rts
cambia:
    rep #$20
.a16
    lda #FAR_CLIMA
    sta WMADDL
    sep #$20
.a8
    lda temp
    sta WMDATA
    lda temp + 1
    sta WMDATA
    lda temp
    cmp #CLIMA_LLUVIA
    bne ninguna
    lda temp + 1
    beq debil
    cmp #1
    beq media
    lda #LLUVIA_GOTAS_2
    bra cuantas
media:
    lda #LLUVIA_GOTAS_1
    bra cuantas
debil:
    lda #LLUVIA_GOTAS_0
    bra cuantas
ninguna:
    lda #0
cuantas:
    sta WMDATA
    lda #<LLUVIA_SEMILLA
    sta WMDATA
    lda #>LLUVIA_SEMILLA
    sta WMDATA
    ; Todas apagadas.
    rep #$20
.a16
    lda #FAR_LLUVIA
    sta WMADDL
    sep #$20
.a8
    ldx #(LLUVIA_GOTAS_MAX * 3)
apagar:
    stz WMDATA
    dex
    bne apagar
    rts
.endproc

; El azar de la lluvia, en `comp_mask`: el mismo xorshift que
; `eventos.azar_siguiente`. Vuelve con el número nuevo en A, de dieciséis.
.proc lluvia_azar
.a8
.i16
    rep #$20
.a16
    lda comp_mask
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor comp_mask
    sta comp_mask
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor comp_mask
    sta comp_mask
    xba
    and #$FF00
    eor comp_mask
    sta comp_mask
    rts
.endproc

; Un cuadro de la lluvia —`Game_Screen::UpdateRain`—: la gota viva baja y se
; corre, y la que se quedó sin vida vuelve a nacer donde diga el azar. `comp_col`
; cuenta las gotas y `comp_mask` lleva el azar; son del compositor de
; mensajes, que las recalcula en cada carácter. X es la gota, de a tres bytes.
.proc lluvia_tick
.a8
.i16
    lda f:CLIMA_L + 2
    bne hay
    rts
hay:
    sta comp_col                ; cuántas
    rep #$20
.a16
    lda f:CLIMA_L + 3
    sta comp_mask
    sep #$20
.a8
    ldx #0
gota:
    lda f:LLUVIA_L + 2, x       ; la vida
    beq apagada
    ; Viva: baja cuatro, corre uno a la izquierda, y le queda uno menos.
    dec a
    sta f:LLUVIA_L + 2, x
    lda f:LLUVIA_L, x
    dec a
    sta f:LLUVIA_L, x
    lda f:LLUVIA_L + 1, x
    clc
    adc #4
    sta f:LLUVIA_L + 1, x
    bra siguiente
apagada:
    ; Nace con LLUVIA_NACE de 256 de chance, en un lugar al azar.
    ; `lluvia_azar` vuelve con A de dieciséis y no toca X.
    jsr lluvia_azar
    sep #$20
.a8
    cmp #LLUVIA_NACE
    bcs siguiente
    lda #LLUVIA_VIDA
    sta f:LLUVIA_L + 2, x
    jsr lluvia_azar
    sep #$20
.a8
    sta f:LLUVIA_L, x
    jsr lluvia_azar
    sep #$20
.a8
    sta f:LLUVIA_L + 1, x
siguiente:
    inx
    inx
    inx
    dec comp_col
    bne gota
    rep #$20
.a16
    lda comp_mask
    sta f:CLIMA_L + 3           ; el azar, de vuelta a su lugar
    sep #$20
.a8
    rts
.endproc

; Las gotas en OAM: dos objetos de 8x8 por gota viva, con prioridad 2, al
; final de todo —cualquier personaje las tapa— y hasta que se llene la OAM.
; Un mapa sin lugar para sus colores tiene `M_LLUVIA_BASE` en cero y no dibuja
; lluvia. Ver `gotas_en_oam` en snes_expect.py, que tiene la regla de qué se
; descarta.
;
; No pasa por `emit_object`, que para 150 objetos era más de media pantalla:
; la X de una gota queda siempre entre 0 y 255 —el noveno bit y el tamaño son
; cero—, así que se escribe directo. X es la gota y Y el objeto.
.proc lluvia_oam
.a8
.i16
    ldx mapa_ofs
    lda f:mapa_tabla + M_LLUVIA_BASE, x
    ora f:mapa_tabla + M_LLUVIA_BASE + 1, x
    bne con_gotas
    rts
con_gotas:
    lda f:CLIMA_L + 2
    bne hay
    rts
hay:
    sta comp_col                ; cuántas
    rep #$20
.a16
    lda f:mapa_tabla + M_LLUVIA_BASE, x
    sta comp_base               ; el primer tile
    sep #$20
.a8
    ; vhoopppN: prioridad 2 y la paleta de las gotas; el noveno bit va aparte.
    lda f:mapa_tabla + M_LLUVIA_PAL, x
    and #$07
    asl a
    ora #$20
    sta comp_color
    stz comp_dup + 3
    ldx #0
gota:
    lda f:LLUVIA_L + 2, x
    bne viva
    jmp siguiente
viva:
    ; El tono: 0 con nueve o más de vida, 1 con cinco o más, 2 si no.
    cmp #9
    bcs tono0
    cmp #5
    bcs tono1
    lda #2
    bra tono
tono0:
    lda #0
    bra tono
tono1:
    lda #1
tono:
    sta comp_dup + 2
    ; En pantalla: menos el scroll del mapa, en ocho bits.
    lda f:LLUVIA_L, x
    sec
    sbc pantalla_x
    sta comp_dup
    lda f:LLUVIA_L + 1, x
    sec
    sbc camara_y
    sta comp_dup + 1
    stz comp_fila               ; la mitad: 0 arriba, 1 abajo
mitad:
    lda comp_dup + 1
    cmp #224
    bcc se_ve
    cmp #248
    bcs se_ve                   ; asoma por arriba
    jmp otra_mitad
se_ve:
    rep #$20
.a16
    lda oam_slot
    cmp #128
    bcc queda_lugar
    sep #$20
.a8
    rts
.a16
queda_lugar:
    asl a
    asl a
    tay
    ; El tile: base + 16 * mitad + tono, de nueve bits.
    lda comp_fila
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc comp_dup + 2
    clc
    adc comp_base
    sep #$20
.a8
    sta oam + 2, y
    xba
    and #$01
    ora comp_color
    sta oam + 3, y
    lda comp_dup
    sta oam, y
    lda comp_dup + 1
    sta oam + 1, y
    ; Sus dos bits en la tabla chica, los dos en cero: `push_high`.
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    lda oam_slot
    and #$03
    cmp #$03
    bne sin_byte
    phx
    jsr store_high
    plx
sin_byte:
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
otra_mitad:
    lda comp_dup + 1
    clc
    adc #8
    sta comp_dup + 1
    inc comp_fila
    lda comp_fila
    cmp #2
    bcs siguiente
    jmp mitad
siguiente:
    inx
    inx
    inx
    dec comp_col
    beq listo
    jmp gota
listo:
    rts
.endproc


; --- el MSU-1 ---------------------------------------------------------------
;
; El MSU-1 no es hardware de la consola: es una extensión que soportan el FX
; Pak Pro y los emuladores, con la música en archivos PCM al lado de la ROM.
; Cuando el tema que se prende tiene pista —`tema_msu`, que emite el
; conversor—, el SPC700 se calla y suena la pista; los efectos de sonido
; siguen en el SPC700 como siempre. Sin MSU-1 no cambia nada: la firma no
; está y todo sigue saliendo del SPC700.
;
; Los registros viven en $2000..$2007 de cualquier banco del área baja:
;
;   $2000  leer: bit 7 datos ocupados, 6 pista cargando, 5 repitiendo,
;          4 tocando, 3 pista ausente, 2..0 revisión
;   $2002..$2007  leer: la firma "S-MSU1"
;   $2004  escribir: qué pista, dos bytes
;   $2006  el volumen, de 0 a 255
;   $2007  bit 0 tocar, bit 1 repetir
MSU_ESTADO  = $2000
MSU_FIRMA   = $2002
MSU_PISTA   = $2004
MSU_VOLUMEN = $2006
MSU_CONTROL = $2007
MSU_HAY     = $7E30E8           ; si la firma está
MSU_SUENA   = $7E30E9           ; si la pista está tocando ahora

; El volumen con que suena la pista, de 0 a 255, y **no es 255**: el MSU-1 se
; suma a la salida del SPC700 en vez de mezclarse con ella, así que la música a
; fondo no deja margen para los efectos de sonido. Con 255, en la apertura, 42
; muestras llegaban al tope —y las 42 en cuadros con un efecto sonando—,
; mientras que la misma corrida por el SPC700 no clavetea ni una vez. Medido
; también: la música por pista picaba 28933 contra 23867 del SPC700, o sea
; 1,21 veces más alta, que es lo que taro escuchó como "los efectos se oyen
; mucho más bajos".
;
; $D8 es ese 0,85. Baja la música hasta donde estaba y devuelve el margen, sin
; tocar las pistas: normalizarlas más abajo serían 195 MB a rehacer por ROM y
; encima perdería la referencia de nivel entre un tema y otro.
MSU_VOLUMEN_MAX = $D8

; Y dos bytes para el factor del fundido, en la RAM lejana porque la del banco 0
; está llena. El byte alto queda siempre en cero: el lazo lo suma de a dieciséis
; bits. Vive acá y no en `temp` porque el fundido corre adentro de `irq_musica`.
MSU_FACTOR  = $7E30EA

; La firma, una vez, en el reset.
.proc msu_detectar
.a8
.i16
    lda #0
    sta f:MSU_SUENA
    ldx #$0000
mirar:
    lda MSU_FIRMA, x
    cmp msu_firma, x
    bne no_hay
    inx
    cpx #6
    bcc mirar
    lda #1
    sta f:MSU_HAY
    rts
no_hay:
    lda #0
    sta f:MSU_HAY
    rts
.endproc

msu_firma:
    .byte "S-MSU1"

; Calla la pista, si había una.
.proc msu_parar
.a8
.i16
    lda f:MSU_SUENA
    beq listo
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
listo:
    rts
.endproc

; Espera a que el MSU-1 suelte `AUDIO_BUSY`. Vuelve con el acarreo limpio si lo
; soltó y puesto si se acabó el tiempo. Se lleva X.
;
; **Este lazo no lo ejercita ningún emulador.** bsnes no pone `io.audioBusy`
; nunca —arranca en falso en `power()` y no se escribe en ningún lado; está en
; `/extras/ref/bsnes-libretro/bsnes/sfc/coprocessor/msu1/msu1.cpp`—, así que en
; la tanda, en las pruebas de estado y en cualquier corrida de acá adentro sale
; en la primera vuelta. En el FX Pak la pista sale de la tarjeta SD y abrirla
; lleva tiempo de verdad, así que **el único lugar donde esto corre es el
; hardware**, que es la definición de camino sin red.
;
; Por eso el tope es generoso y no ajustado: son $FFFF vueltas de unos dieciséis
; ciclos, del orden de tres décimas de segundo. Antes eran $4000 —setenta
; milisegundos— y el precio de quedarse corto no es un cuadro perdido sino que
; el tema entero suene por el SPC700.
MSU_ESPERA = $FFFF

.proc msu_esperar
.a8
.i16
    ldx #$0000
otra:
    lda MSU_ESTADO
    and #$40                    ; la está cargando
    beq listo
    inx
    cpx #MSU_ESPERA
    bcc otra
    sec
    rts
listo:
    clc
    rts
.endproc

; Arranca la pista del tema A, si tiene y si hay MSU-1. Vuelve con A distinto
; de cero si la pista quedó sonando, y ahí la música del SPC700 no va.
.proc msu_arrancar
.a8
.i16
    pha
    lda f:MSU_HAY               ; de a un byte: con `ldx` se leía el de al lado
    beq sin_msu1
    pla
    cmp #TEMA_TOTAL
    bcs no
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda tema_msu, x
    cmp #$FF
    beq no
    ; **Antes de escribir la pista, esperar a que el MSU-1 esté libre.** Con
    ; `AUDIO_BUSY` puesto el hardware ignora las escrituras a los registros de
    ; audio —en bsnes se ve en `writeIO`, `case 0x2007: if(io.audioBusy)
    ; break;`—, así que un `PlayBGM` que llega mientras la pista anterior
    ; todavía se está abriendo se pierde entero. Acá pasa de verdad: con
    ; pantalla de título hay dos pistas pedidas con 1,8 s de diferencia —la del
    ; título y la de la apertura—, y en `demo-ciudad` la primera es la única.
    ;
    ; La pista se guarda en Y mientras tanto: la espera usa X.
    tay
    jsr msu_esperar
    bcs no                      ; sigue ocupado: que suene el SPC700
    tya
    sta MSU_PISTA
    stz MSU_PISTA + 1
    jsr msu_esperar             ; y ahora, que termine de abrirla
    bcs no
    lda MSU_ESTADO
    and #$08                    ; la pista no está en la tarjeta
    bne no
    lda #MSU_VOLUMEN_MAX
    sta MSU_VOLUMEN
    lda #$03                    ; tocar y repetir
    sta MSU_CONTROL
    lda #1
    sta f:MSU_SUENA
    rts
sin_msu1:
    pla
no:
    lda #0
    rts
.endproc

; --- el paquete de audio de cada mapa ----------------------------------------
;
; La ARAM no alcanza para todas las muestras del cartucho —la música de los
; temas de la demo son 53 KB y los efectos que piden los mapas 2 y 3, 43 y
; 55 más—, así que se suben por mapa: al cargar uno, los temas que sus páginas
; pueden prender y los efectos que piden, en el orden en que aparecen. Es la
; tabla `paquetes` que arma el conversor. Los que no entran no suenan.
;
; Las muestras tienen número fijo en todo el cartucho —el SRCN que el stream
; de la música ya escribe— y el directorio del SPC700 tiene una entrada por
; cada una. La que no está en la ARAM apunta al silencio. `FAR_ARAM_DE` dice
; dónde está cada una, o 0.
;
; **Las del tema que está sonando no se mueven**: la música sigue durante el
; fundido del salto, y pisarle una muestra que está tocando sería ruido. Todo
; lo demás se vuelve a acomodar desde el principio de la ARAM, saltando esas.
; Ver "El paquete de audio de cada mapa" en el README.
FAR_ARAM_DE = $7E3100           ; una palabra por muestra
FAR_QUIERE  = $7E3300           ; un byte por muestra: 2 las que no se mueven
APU_LISTO   = $7E30D0           ; si el driver ya corre
PAQ_EXTRA   = $7E30D1           ; un tema que va primero, o $FF
PAQ_CURSOR  = $7E30D2           ; dónde se acomoda la que sigue
PAQ_LARGO   = $7E30D4
PAQ_DEST    = $7E30D6
PAQ_S       = $7E30D8           ; la muestra que se acomoda
PAQ_X7      = $7E30DA           ; su fila en `muestra_tabla`
PAQ_A       = $7E30DC           ; dónde se prueba ponerla
PAQ_MAPA    = $7E30DE           ; el mapa del paquete, en un word desde que
                                ; el índice de mapa no entra en un byte.
                                ; $30E0 a $30E7 siguen libres: lo próximo
                                ; que hay es MSU_HAY en $30E8
INT_N       = $7E30E0           ; cuántos ocupados, en bytes: dos por cada uno
INT_INI     = $7E3400           ; lo ocupado, en orden: dónde empieza
INT_FIN     = $7E3500           ; y dónde termina

; Nada en la ARAM. En el reset: el driver todavía no corre.
.proc aram_limpiar
.a8
.i16
    lda #0
    sta f:APU_LISTO
    lda #$FF
    sta f:PAQ_EXTRA
    ldx #0
otra:
    lda #0
    sta f:FAR_ARAM_DE, x
    inx
    cpx #(2 * MUESTRAS_N)
    bcc otra
    rts
.endproc

; El testigo: el comando ya está en los puertos, y el driver lo toma cuando
; cambia. Se espera el acuse.
.proc apu_testigo
.a8
.i16
    inc token
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; El puntero de la ARAM, a PAQ_DEST. Con las interrupciones cortadas: la
; música usa los mismos puertos, y el puerto 2 tiene que volver a 0 antes de
; que ella mande su próximo par.
.proc aram_apuntar
.a8
.i16
    php
    sei
    lda #2
    sta APUIO2
    lda f:PAQ_DEST
    sta APUIO0
    lda f:PAQ_DEST + 1
    sta APUIO1
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; Un byte, el de A, donde apunta el puntero; el puntero avanza.
.proc aram_byte
.a8
.i16
    php
    sei
    sta APUIO0
    lda #1
    sta APUIO2
    jsr apu_testigo
    stz APUIO2
    plp
    rts
.endproc

; La muestra de la fila PAQ_X7 de `muestra_tabla`, a PAQ_DEST. De a ternas
; por el comando 3, en tandas de hasta 128 con las interrupciones cortadas
; —unos cinco milisegundos: la música se atrasa, no se pierde—, y lo que
; sobra de a un byte.
.proc subir_muestra
.a8
.i16
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla, x
    sta comp_glifo
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    sep #$20
.a8
    lda f:muestra_tabla + 2, x
    sta comp_glifo + 2
    ldy #0
tanda:
    ; El puntero, a donde va la terna que sigue: el bloque no lo avanza.
    rep #$20
.a16
    tya
    clc
    adc f:PAQ_A
    sta f:PAQ_DEST
    sty temp
    lda f:PAQ_LARGO
    sec
    sbc temp                    ; lo que falta
    sta temp + 2
    sep #$20
.a8
    jsr aram_apuntar
    rep #$20
.a16
    lda temp + 2
    cmp #3
    bcs hay_ternas
    jmp resto
hay_ternas:
    sta WRDIVL
    sep #$20
.a8
    lda #3
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL                  ; cuántas ternas quedan, si entran en un byte
    ldx RDDIVL
    cpx #85
    bcc cuantas
    lda #85                     ; el índice del driver es de un byte
cuantas:
    rep #$20
.a16
    and #$00FF                  ; la cuenta, en X
    tax
    sep #$20
.a8
    php
    sei
    sta APUIO0
    lda #3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
acuse_bloque:
    cmp APUIO3
    bne acuse_bloque
    ; La primera terna, leída antes; las demás se leen mientras el SPC700
    ; guarda la anterior, que es lo que más tarda. Nunca una de más: pasado el
    ; final del bloque puede haber registros que se alteran al leerlos.
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
terna:
    lda temp
    sta APUIO0
    lda temp + 1
    sta APUIO1
    lda temp + 3
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    dex
    beq ultima
    lda [comp_glifo], y
    sta temp
    iny
    lda [comp_glifo], y
    sta temp + 1
    iny
    lda [comp_glifo], y
    sta temp + 3
    iny
    lda token
acuse:
    cmp APUIO3
    bne acuse
    bra terna
ultima:
    lda token
acuse_ultima:
    cmp APUIO3
    bne acuse_ultima
    stz APUIO2
    plp
    jmp tanda
.a16
resto:
    sep #$20
.a8
    ; Lo que falta, 0, 1 o 2, de a un byte: el puntero ya está donde va.
    lda temp + 2
    beq listo
    sta temp
un_byte:
    lda [comp_glifo], y
    iny
    jsr aram_byte
    dec temp
    bne un_byte
listo:
    rts
.endproc

; La muestra PAQ_S, ya subida a PAQ_A: su entrada del directorio, con dónde
; empieza y dónde vuelve.
.proc escribir_directorio
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_S
    and #$00FF
    asl a
    asl a
    clc
    adc #SPC_SAMPLES_ADDR
    sta f:PAQ_DEST
    sep #$20
.a8
    jsr aram_apuntar
    lda f:PAQ_A
    jsr aram_byte
    lda f:PAQ_A + 1
    jsr aram_byte
    rep #$30
.a16
    lda f:PAQ_X7
    tax
    lda f:muestra_tabla + 5, x  ; el loop, desde el principio
    clc
    adc f:PAQ_A
    sta temp
    sep #$20
.a8
    lda temp
    jsr aram_byte
    lda temp + 1
    jmp aram_byte
.endproc

; X7 de la muestra A: A * 7, en PAQ_X7 y en X.
.proc fila_de_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp
    sta f:PAQ_X7
    tax
    sep #$20
.a8
    rts
.endproc

; Acomoda y sube la muestra A, si no está. En el primer lugar desde
; PAQ_CURSOR que no pise a ninguna de las que no se mueven; si no entra antes
; de ARAM_FIN, no sube y no suena.
.proc colocar_muestra
.a8
.i16
    sta f:PAQ_S
    rep #$30
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    beq no_esta
    rts                         ; ya está
no_esta:
    lda f:PAQ_S
    jsr fila_de_muestra
    rep #$30
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    ; El primer hueco donde entre: se recorren los ocupados en orden, con
    ; PAQ_A en el principio del hueco que se mira.
    lda #ARAM_DATOS
    sta f:PAQ_A
    ldx #0
hueco:
    txa
    cmp f:INT_N
    bcs al_final
    lda f:INT_INI, x
    sec
    sbc f:PAQ_A                 ; cuánto hay antes de este ocupado
    bcc sigue                   ; empieza antes: no hay hueco
    cmp f:PAQ_LARGO
    bcs aca                     ; entra
sigue:
    lda f:INT_FIN, x
    cmp f:PAQ_A
    bcc no_avanza
    sta f:PAQ_A                 ; el hueco que sigue empieza detrás
no_avanza:
    inx
    inx
    bra hueco
al_final:
    lda #ARAM_FIN
    sec
    sbc f:PAQ_A
    bcc no_entra
    cmp f:PAQ_LARGO
    bcs aca
no_entra:
    sep #$20
.a8
    rts                         ; no entra: no suena
.a16
aca:
    ; Entra en PAQ_A, delante del ocupado X: se hace lugar en la lista.
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    ; Y se anota, se sube y se pone en el directorio.
    lda f:PAQ_S
    and #$00FF
    asl a
    tax
    lda f:PAQ_A
    sta f:FAR_ARAM_DE, x
    lda f:PAQ_S
    sep #$20
.a8
    jsr fila_de_muestra
    jsr subir_muestra
    jmp escribir_directorio
.endproc

; Las muestras del tema A: X al principio de su lista en `tema_muestras`.
.proc lista_del_tema
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:tema_muestras, x
    tax
    sep #$20
.a8
    rts
.endproc

; Acomoda las muestras del tema A.
.proc colocar_tema
.a8
.i16
    jsr lista_del_tema
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr colocar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; Calla el efecto de sonido que esté sonando: sus muestras se van a mover.
.proc se_callar
.a8
.i16
    php
    sei
    lda #0
    sta f:SE_CUADROS
    sta f:SE_CUADROS + 1
    sta f:SE_PENDIENTE
    sta f:SE_BAJAR
    lda #1
    sta f:SE_DEVOLVER           ; la música recupera la voz
    lda #SE_BIT
    ldx #SE_KOF
    jsr dsp_par
    plp
    rts
.endproc

; El paquete de `mapa_actual`: ver arriba. PAQ_EXTRA es un tema que va antes
; que los del mapa —el que un `PlayBGM` pide y no estaba—, o $FF.
;
; El mapa sale de `mapa_actual` y no de A desde que el índice es de dieciséis
; bits: los tres que llamaban acá le pasaban `mapa_actual` en A, así que no se
; perdió ningún caso y el que llama no tiene que acordarse del ancho.
.proc paquete_cargar
.a8
.i16
    rep #$20
.a16
    lda mapa_actual
    sta f:PAQ_MAPA
    sep #$20
.a8
    jmp paquete_cargar_ya
.endproc

; Y el paquete cuyo índice ya está escrito en `PAQ_MAPA`, que es por donde
; entra la pelea: el suyo no es el de ningún mapa —va detrás de todos, ver
; `BA_PAQUETE`— así que no puede salir de `mapa_actual`.
;
; Existe porque acá hubo un error que ningún conflicto de git marcó: cuando el
; índice pasó a dieciséis bits, `paquete_cargar` dejó de leer el paquete de A
; para leerlo de `mapa_actual`, y `batalla_audio_cargar` —que venía de la otra
; rama— siguió pasándoselo en A. Las dos ramas mergearon limpio porque tocaban
; líneas distintas, y desde entonces la pelea cargaba el paquete del mapa: el
; tema de batalla sonaba con seis muestras sin subir y el golpe erraba con la
; muestra 0. Lo cobraron las dos pruebas de audio de `test_batalla.py`.
.proc paquete_cargar_ya
.a8
.i16
    lda f:APU_LISTO
    bne listo_apu
    rts                         ; en el reset, antes de que corra el driver
listo_apu:
    jsr se_callar
    ldx #0
limpiar:
    lda #0
    sta f:FAR_QUIERE, x
    inx
    cpx #MUESTRAS_N
    bcc limpiar
    ; Las del tema que suena no se mueven: 2.
    lda music_apagada
    bne sin_fijas
    lda tema_actual
    cmp #TEMA_TOTAL
    bcs sin_fijas
    ldy #2
    jsr marcar_tema
sin_fijas:
    ; Las que el paquete quiere: 1, si no eran ya 2.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra
    ldy #1
    jsr marcar_tema
sin_extra:
    jsr lista_del_paquete
temas_q:
    lda f:paquetes, x
    cmp #$FF
    beq efectos_q
    phx
    ldy #1
    jsr marcar_tema
    plx
    inx
    bra temas_q
efectos_q:
    inx
otro_q:
    lda f:paquetes, x
    cmp #$FF
    beq marcadas
    phx
    ldy #1
    jsr marcar_muestra
    plx
    inx
    bra otro_q
marcadas:
    ; Las que nadie quiere se olvidan, y con las que quedan se arma la lista
    ; de lo ocupado, en orden: es donde `colocar_muestra` busca los huecos.
    rep #$20
.a16
    lda #0
    sta f:INT_N
    sep #$20
.a8
    ldx #0
olvidar:
    lda f:FAR_QUIERE, x
    phx
    rep #$20
.a16
    pha
    txa
    asl a
    tax
    pla
    and #$00FF
    bne quiere
    sta f:FAR_ARAM_DE, x        ; nadie la quiere: afuera
    bra proxima
quiere:
    lda f:FAR_ARAM_DE, x
    beq proxima                 ; la quieren pero no está: la sube el paso que sigue
    sta f:PAQ_A
    txa
    lsr a
    sep #$20
.a8
    jsr fila_de_muestra
    rep #$20
.a16
    lda f:muestra_tabla + 3, x
    sta f:PAQ_LARGO
    jsr intervalo_ordenado
proxima:
    sep #$20
.a8
    plx
    inx
    cpx #MUESTRAS_N
    bcc olvidar
    ; Y se acomodan las que faltan, en orden de prioridad: el tema extra, los
    ; del mapa y sus efectos.
    lda f:PAQ_EXTRA
    cmp #$FF
    beq sin_extra2
    jsr colocar_tema
sin_extra2:
    jsr lista_del_paquete
temas:
    lda f:paquetes, x
    cmp #$FF
    beq efectos
    phx
    jsr colocar_tema
    plx
    inx
    bra temas
efectos:
    inx
otro_efecto:
    lda f:paquetes, x
    cmp #$FF
    beq listo
    phx
    jsr colocar_muestra
    plx
    inx
    bra otro_efecto
listo:
    rts
.endproc

; X al principio de la lista del paquete de PAQ_MAPA.
.proc lista_del_paquete
.a8
.i16
    rep #$20
.a16
    lda f:PAQ_MAPA
    asl a
    tax
    lda f:paquetes, x
    tax
    sep #$20
.a8
    rts
.endproc

; La muestra A, marcada con Y en FAR_QUIERE si no tenía algo mayor.
.proc marcar_muestra
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    tya
    cmp f:FAR_QUIERE, x
    bcc listo
    sta f:FAR_QUIERE, x
listo:
    rts
.endproc

; Las muestras del tema A, marcadas con Y.
.proc marcar_tema
.a8
.i16
    phy
    jsr lista_del_tema
    ply
otra:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo
    phx
    jsr marcar_muestra
    plx
    inx
    bra otra
listo:
    rts
.endproc

; Agrega a la lista de lo ocupado el intervalo [PAQ_A, PAQ_A + PAQ_LARGO),
; en orden. A de dieciséis.
.proc intervalo_ordenado
.a16
.i16
    ldx #0
buscar:
    txa
    cmp f:INT_N
    bcs lugar
    lda f:INT_INI, x
    cmp f:PAQ_A
    bcs lugar                   ; éste empieza después: va delante
    inx
    inx
    bra buscar
lugar:
    stx temp
    lda f:INT_N
    tax
correr:
    cpx temp
    beq corrido
    dex
    dex
    lda f:INT_INI, x
    sta f:INT_INI + 2, x
    lda f:INT_FIN, x
    sta f:INT_FIN + 2, x
    bra correr
corrido:
    lda f:PAQ_A
    sta f:INT_INI, x
    clc
    adc f:PAQ_LARGO
    sta f:INT_FIN, x
    lda f:INT_N
    clc
    adc #2
    sta f:INT_N
    rts
.endproc

; Antes de prender el tema A: si le falta alguna muestra, se calla la música,
; se suelta todo y se rearma el paquete del mapa con él adelante. Pasa con un
; `PlayBGM` de un tema que el mapa no traía —el del título, o uno de un evento
; común— y congela la imagen lo que tarde en subir.
.proc tema_asegurar
.a8
.i16
    sta temp + 1
    lda f:APU_LISTO
    beq listo
    lda temp + 1
    cmp #TEMA_TOTAL
    bcs listo
    jsr lista_del_tema
mirar:
    lda f:tema_muestras, x
    cmp #$FF
    beq listo                   ; están todas
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    plx
    cmp #0                      ; **la Z de acá la pone `plx`, no el `lda`**:
                                ; PLX deja N y Z del valor que saca de la pila,
                                ; que es el índice de la lista y nunca es cero.
                                ; Sin este `cmp` la respuesta era siempre
                                ; "están todas" y el tema del título sonaba
                                ; contra un directorio de silencios. Es de
                                ; dieciséis bits, como la dirección: el mismo
                                ; cuidado que `op_sound` se toma con `xba`.
    sep #$20
.a8
    beq falta
    inx
    bra mirar
falta:
    php
    sei
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; todas las voces sueltan
    plp
    lda temp + 1
    sta f:PAQ_EXTRA
    jsr paquete_cargar
    lda #$FF
    sta f:PAQ_EXTRA
listo:
    rts
.endproc

; --- los efectos de sonido -------------------------------------------------------
;
; `PlaySound`, en la voz SE_VOZ, que se le roba a la música mientras dura. Ver
; `build_efectos` en snes_music.py. El estado vive en la RAM lejana, porque la
; página directa y la BSS están llenas:
;
;   SE_CUADROS   cuántos cuadros le quedan al efecto, dos bytes
;   SE_PENDIENTE hay uno pendiente de arrancar
;   SE_DEVOLVER  hay que devolverle la voz a la música en este cuadro
;   SE_BAJAR     hay que bajar el disparo de KON en este cuadro
;   SE_NUEVO     el pendiente: la muestra, la altura (dos), el volumen de
;                cada lado y los cuadros (dos), siete bytes
;   SE_SOMBRA    lo último que la música le escribió a los ocho registros de
;                la voz, y a KOF en el noveno: con eso se le devuelve la voz
;
; La música sigue escribiéndole a la voz mientras el efecto suena: se guarda
; en la sombra y no se manda, y a sus KON y KOF se les saca el bit de la voz.
;
; Todo esto corre adentro de `irq_musica`, así que **no usa la ventana de
; WMADD ni `temp`**: la interrupción cae en cualquier punto del código
; principal, y si ése estaba recorriendo la RAM lejana o usando `temp`, se lo
; pisaría. Se llega con el direccionamiento largo, que lleva el banco en la
; instrucción. Lo único que escribe acá el código principal es el pendiente,
; en `op_sound`, y lo hace con las interrupciones cortadas.
FAR_SE       = $30A0
SE_CUADROS   = $7E0000 + FAR_SE
SE_PENDIENTE = SE_CUADROS + 2
SE_DEVOLVER  = SE_CUADROS + 3
SE_BAJAR     = SE_CUADROS + 4
SE_NUEVO     = SE_CUADROS + 5
SE_SOMBRA    = $7E0000 + $30B0
; SE_BIT y SE_REG —el bit de la voz en KON y KOF, y su primer registro— los
; emite snes_music.py junto con SE_VOZ.
SE_KON     = $4C
SE_KOF     = $5C

; Z=0 si hay un efecto sonando, pendiente o devolviendo la voz. No toca B.
.proc se_ocupada
.a8
.i16
    lda f:SE_CUADROS
    ora f:SE_CUADROS + 1
    ora f:SE_PENDIENTE
    ora f:SE_DEVOLVER
    rts
.endproc

; Un par al DSP: X el registro, A el valor. Es lo que hace `write_dsp`.
.proc dsp_par
.a8
.i16
    xba
    txa
    sta APUIO0
    xba
    sta APUIO1
    inc token
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; Una escritura del stream de la música: X el registro, A el valor. Si es de
; la voz del efecto, va a la sombra, y si hay un efecto no se manda; KON y KOF
; salen sin el bit de la voz mientras dure.
.proc dsp_musica
.a8
.i16
    xba                         ; B = el valor
    txa
    and #$F0
    cmp #SE_REG
    bne no_voz
    txa
    and #$0F
    cmp #8
    bcs no_voz                  ; ENVX y OUTX no se escriben nunca
    phx
    rep #$20
.a16
    and #$000F
    tax
    sep #$20
.a8
    xba
    sta f:SE_SOMBRA, x          ; a la sombra
    xba
    plx
    jsr se_ocupada
    beq enviar
    rts                         ; la voz es del efecto
no_voz:
    txa
    cmp #SE_KOF
    bne no_kof
    ; KOF: a la sombra siempre, y sin el bit mientras haya efecto.
    xba
    sta f:SE_SOMBRA + 8
    xba
    bra mascara
no_kof:
    cmp #SE_KON
    bne enviar
mascara:
    jsr se_ocupada
    beq enviar
    xba
    and #($FF - SE_BIT)
    xba
enviar:
    xba                         ; A = el valor, y X sigue con el registro
    jmp dsp_par
.endproc

; Antes de la música, en cada cuadro: bajar el disparo que dejó el efecto, y
; devolverle la voz a la música si terminó en el cuadro anterior.
.proc se_antes
.a8
.i16
    lda f:SE_BAJAR
    beq sin_bajar
    lda #0
    sta f:SE_BAJAR
    ldx #SE_KON
    jsr dsp_par
sin_bajar:
    lda f:SE_DEVOLVER
    beq listo
    lda #0
    sta f:SE_DEVOLVER
    ; KOF como lo tenía la música, y los ocho registros de la voz.
    lda f:SE_SOMBRA + 8
    ldx #SE_KOF
    jsr dsp_par
    ldy #0
registro:
    tyx
    lda f:SE_SOMBRA, x
    pha
    rep #$20
.a16
    tya
    clc
    adc #SE_REG
    tax
    sep #$20
.a8
    pla
    jsr dsp_par
    iny
    cpy #8
    bcc registro
listo:
    rts
.endproc

; Después de la música: arrancar el pendiente, o contar el que suena y
; apagarlo cuando termina.
.proc se_despues
.a8
.i16
    lda f:SE_PENDIENTE
    bne arrancar
    jmp contar
arrancar:
    lda #0
    sta f:SE_PENDIENTE          ; ya no está pendiente
    ; KOF sin el bit de la voz, que la música pudo haber dejado puesto.
    lda f:SE_SOMBRA + 8
    and #($FF - SE_BIT)
    ldx #SE_KOF
    jsr dsp_par
    ; La muestra, la altura, el volumen y la envolvente, desde el pendiente.
    lda f:SE_NUEVO + 4
    ldx #(SE_REG + 1)
    jsr dsp_par                 ; VOLR
    lda f:SE_NUEVO + 3
    ldx #(SE_REG + 0)
    jsr dsp_par                 ; VOLL
    lda f:SE_NUEVO + 2
    ldx #(SE_REG + 3)
    jsr dsp_par                 ; la altura alta
    lda f:SE_NUEVO + 1
    ldx #(SE_REG + 2)
    jsr dsp_par                 ; y la baja
    lda f:SE_NUEVO
    ldx #(SE_REG + 4)
    jsr dsp_par                 ; SRCN
    lda #$FF                    ; ADSR prendido, ataque y caída al máximo
    ldx #(SE_REG + 5)
    jsr dsp_par
    lda #$E0                    ; sostenido al máximo y sin caer
    ldx #(SE_REG + 6)
    jsr dsp_par
    lda #SE_BIT
    ldx #SE_KON
    jsr dsp_par                 ; y el disparo
    rep #$20
.a16
    lda f:SE_NUEVO + 5
    sta f:SE_CUADROS
    sep #$20
.a8
    lda #1
    sta f:SE_BAJAR              ; el cuadro que viene se baja el disparo
    rts
contar:
    rep #$20
.a16
    lda f:SE_CUADROS
    beq nada
    dec a
    sta f:SE_CUADROS
    bne nada
    sep #$20
.a8
    ; Terminó: KOF con el bit de la voz, y en el cuadro que viene la música
    ; la recupera.
    lda f:SE_SOMBRA + 8
    ora #SE_BIT
    ldx #SE_KOF
    jsr dsp_par
    lda #1
    sta f:SE_DEVOLVER
    rts
.a16
nada:
    sep #$20
.a8
    rts
.endproc

; El estado en cero: nada sonando. En el reset.
.proc se_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:SE_CUADROS, x
    inx
    cpx #12
    bcc otro
    rts
.endproc

; --- la pantalla de ítems -------------------------------------------------------
;
; `Scene_Item`: arriba la descripción del ítem marcado, abajo la lista del
; inventario con cuántos hay. Tiene **banco de tiles propio**, `items_tiles`:
; cada carácter de la fuente en dos celdas, en blanco y en gris, y el texto
; —nombre y dos renglones de descripción por ítem— va en ASCII en
; `item_textos`. Escribir una letra son dos palabras del tilemap. La
; geometría es de `titulo.py` y `render_items` es la referencia.
;
; La lista se arma al entrar: los ítems que hay y que esta ROM conoce, en
; orden de número como `Game_Party`, guardados como su lugar `k` en las
; tablas del conversor, en `FAR_ITEM_LISTA`. Cuántos son, el primero que se ve
; y el cursor van en variables prestadas: `eleg_n`, `eleg_sel` y `titulo_sel`.
; La elección no puede estar abierta con el menú —el menú no se abre con un
; mensaje— así que sus bytes están libres; `eleg_cancel`, `eleg_flancos` y
; `eleg_tabla` hacen de escritorio, y `msg_ptr` apunta al texto que se
; escribe.
FAR_ITEM_LISTA = $2A00

; A: un lugar de la lista. Vuelve con A = su `k`. Sólo A.
.proc item_de_lista
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: un `k`. Vuelve con A = cuántos hay de ese ítem. Se lleva X.
.proc item_cuantos
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; La lista, en `FAR_ITEM_LISTA`, y cuántos son en `eleg_n`.
.proc items_armar_lista
.a8
.i16
    stz eleg_n
    ldx #1
otro:
    rep #$20
.a16
    txa
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq siguiente
    lda f:item_k, x
    cmp #$FF
    beq siguiente               ; uno que esta ROM no sabe mostrar
    pha
    rep #$20
.a16
    lda eleg_n
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
    inc eleg_n
siguiente:
    inx
    cpx #ITEMS_N
    bcc otro
    rts
.endproc

; Una letra: A el carácter, Y la dirección de la celda de arriba y `temp + 1`
; la variante, 0 blanco y 1 gris. Se lleva X.
.proc glifo_par
.a8
.i16
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a                       ; cuatro bytes por carácter
    tax
    lda temp + 1
    and #$00FF
    beq blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
blanco:
    sep #$20
.a8
    lda #$80
    sta VMAIN
    rep #$20
.a16
    sty VMADDL
    lda f:item_glifo_celdas, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda f:item_glifo_celdas + 2, x
    sta VMDATAL
    sep #$20
.a8
    rts
.endproc

; Un texto de un ítem: X el número de texto —`3k` el nombre, `3k + 1` y
; `3k + 2` los renglones de la descripción—, `eleg_tabla` la dirección de la
; celda de arriba de su primera letra y `temp + 1` la variante. Primero las
; celdas de arriba de todas las letras, que van seguidas en la VRAM, y
; después las de abajo.
.proc texto_escribir
.a8
.i16
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; cuántas letras
    beq listo
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #0                      ; las celdas de arriba
    sta temp + 2
    lda eleg_tabla
    sta VMADDL
    sep #$20
.a8
    jsr renglon
    rep #$20
.a16
    lda #2                      ; y las de abajo
    sta temp + 2
    lda eleg_tabla
    clc
    adc #32
    sta VMADDL
    sep #$20
.a8
    jsr renglon
listo:
    rts

renglon:
    ldy #0
letra:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    clc
    adc temp + 2                ; arriba o abajo
    tax
    lda temp + 1
    and #$00FF
    beq en_blanco
    txa
    clc
    adc #ITEM_GLIFOS_GRIS
    tax
en_blanco:
    lda f:item_glifo_celdas, x
    sta VMDATAL                 ; y la VRAM avanza una palabra
    sep #$20
.a8
    iny
    tya                         ; de a una letra: son menos de 256
    cmp temp
    bcc letra
    rts
.endproc

; El cursor en la fila A de la pantalla: `temp + 3` en 1 lo pinta y en 0 lo
; borra, que es escribir un espacio.
.proc item_cursor_escribir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_CURSOR_COL
    tay
    sep #$20
.a8
    stz temp + 1
    lda temp + 3                ; con A: `ldx temp + 3` se llevaría dos bytes
    beq borra
    lda #$3E                    ; '>'
    jmp glifo_par
borra:
    lda #$20                    ; ' '
    jmp glifo_par
.endproc

; La descripción del ítem que marca el cursor, compuesta en `texto_buf` y no
; en la VRAM: son cuatro filas de celdas enteras —256 bytes— que
; `items_desc_subir` sube de un DMA. Escribirlas de a una palabra no entraba
; en el vblank: al mover el cursor el segundo renglón salía cortado, porque la
; VRAM ignora lo que se le escribe con la pantalla dibujando. El búfer es el
; del compositor de mensajes, que con el menú abierto no hay. Con la lista
; vacía queda en blanco.
ITEM_DESC_BYTES = 4 * 64

.proc items_desc_pintar
.a8
.i16
    ldx #0
borrar:
    stz texto_buf, x
    inx
    cpx #ITEM_DESC_BYTES
    bcc borrar
    lda eleg_n
    beq listo
    lda titulo_sel
    jsr item_de_lista
    rep #$20
.a16
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    inc a                       ; 3k + 1, el primer renglón
    tax
    lda #(ITEM_DESC_COL * 2)
    sta eleg_tabla              ; dónde va, en bytes del búfer
    sep #$20
.a8
    phx
    jsr renglon
    plx
    inx                         ; 3k + 2, el segundo
    rep #$20
.a16
    lda #(128 + ITEM_DESC_COL * 2)
    sta eleg_tabla
    sep #$20
.a8
    jsr renglon
listo:
    rts

; El texto X al búfer, desde el byte `eleg_tabla`: la celda de arriba de cada
; letra ahí y la de abajo 64 bytes más adelante.
renglon:
    lda f:item_txt_lo, x
    sta msg_ptr
    lda f:item_txt_hi, x
    sta msg_ptr + 1
    lda f:item_txt_bk, x
    sta msg_ptr + 2
    lda f:item_txt_n, x
    sta temp                    ; cuántas letras
    beq fin
    ldy #0
letra:
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sec
    sbc #ITEM_PRIMER_CARACTER
    asl a
    asl a
    tax
    lda f:item_glifo_celdas, x
    pha
    lda f:item_glifo_celdas + 2, x
    ldx eleg_tabla
    sta texto_buf + 64, x
    pla
    sta texto_buf, x
    inx
    inx
    stx eleg_tabla
    sep #$20
.a8
    iny
    tya                         ; de a una letra: son menos de 256
    cmp temp
    bcc letra
fin:
    rts
.endproc

; Sube la descripción compuesta: un DMA de 256 bytes, que entra en cualquier
; vblank.
.proc items_desc_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(ITEM_DESC_VRAM - ITEM_DESC_COL)
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #ITEM_DESC_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el búfer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; La fila A de la pantalla, que tiene que tener un ítem: el cursor si toca, el
; nombre, los dos puntos y la cantidad, en gris si A no lo usa.
.proc items_fila_pintar
.a8
.i16
    sta eleg_cancel             ; la fila
    lda eleg_cancel
    clc
    adc eleg_sel                ; su lugar en la lista
    pha
    jsr item_de_lista
    sta eleg_flancos            ; su `k`
    pla
    cmp titulo_sel
    bne sin_cursor
    lda #1
    sta temp + 3
    lda eleg_cancel
    jsr item_cursor_escribir
sin_cursor:
    ; --- el color: gris si A no lo usa ---
    lda eleg_flancos
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda item_uso, x
    and #1
    eor #1
    sta temp + 1
    ; --- el nombre ---
    lda eleg_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_NOMBRE_COL
    sta eleg_tabla
    lda eleg_flancos
    and #$00FF
    sta temp + 2
    asl a
    clc
    adc temp + 2
    tax                         ; 3k, el nombre
    sep #$20
.a8
    jsr texto_escribir
    ; --- los dos puntos y la cantidad ---
    lda eleg_flancos
    jsr item_cuantos
    cmp #100
    bcc cabe
    lda #99
cabe:
    stz temp + 3                ; las decenas
decenas:
    cmp #10
    bcc unidades
    sbc #10                     ; el `cmp` dejó el acarreo puesto
    inc temp + 3
    bra decenas
unidades:
    pha                         ; las unidades
    lda eleg_cancel
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_fila_vram, x
    clc
    adc #ITEM_DOS_PUNTOS_COL
    sta eleg_tabla
    tay
    sep #$20
.a8
    lda #$3A                    ; ':'
    jsr glifo_par
    rep #$20
.a16
    lda eleg_tabla
    inc a
    tay
    sep #$20
.a8
    lda temp + 3
    beq sin_decenas             ; un 7 es " 7", no "07"
    clc
    adc #$30                    ; '0'
    jsr glifo_par
sin_decenas:
    rep #$20
.a16
    lda eleg_tabla
    inc a
    inc a
    tay
    sep #$20
.a8
    pla
    clc
    adc #$30                    ; '0'
    jmp glifo_par
.endproc


; Las filas que se ven, sobre el tilemap en blanco.
.proc items_filas_pintar
.a8
.i16
    lda #0
fila:
    pha
    clc
    adc eleg_sel
    bcs termina
    cmp eleg_n
    bcs termina                 ; no hay más ítems
    pla
    pha
    jsr items_fila_pintar
    pla
    inc a
    cmp #ITEM_FILAS
    bcc fila
    rts
termina:
    pla
    rts
.endproc

; La pantalla de ítems, hasta que el jugador vuelve con B —A = 0, al menú— o
; usa un ítem —A = 1: RM2k vuelve derecho al mapa, `PopUntil(Scene::Map)`—.
.proc items_pantalla
.a8
.i16
    jsr items_armar_lista
    stz titulo_sel
    stz eleg_sel
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:items_banco_subir
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto
espera:
    jsr wait_vblank
    jsr items_desc_subir        ; lo primero del vblank: la descripción
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    beq espera                  ; RM2k no da la vuelta en una lista
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp eleg_n
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    lda #0
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda eleg_n
    beq espera                  ; la lista vacía
    lda titulo_sel
    jsr item_de_lista
    sta eleg_flancos            ; su `k`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda item_uso, x
    and #1
    beq espera                  ; en gris: RM2k suena y no hace nada
    lda item_uso, x
    and #4
    beq de_switch
    ; Una medicina: la elección de actor, y de vuelta a la lista con el cursor
    ; donde estaba. La elección usa `titulo_sel`, así que se guarda.
    lda titulo_sel
    pha
    lda eleg_sel
    pha
    stz eleg_cancel             ; para una medicina
    jsr objetivo_pantalla
    pla
    sta eleg_sel
    pla
    sta titulo_sel
    lda #$80
    sta INIDISP
    jsl f:items_banco_subir
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    jsr ranura_ppu_prender
    jmp espera
de_switch:
    ; Un ítem de switch: `ConsumeItemUse` si tiene usos, el switch prendido y
    ; derecho al mapa. `poner_switch` pide el refresco de páginas, que es el
    ; `SetNeedRefresh(true)` de allá.
    lda item_uso, x
    and #2
    beq sin_gastar
    lda eleg_flancos
    jsr item_cuantos
    dec a
    pha
    lda eleg_flancos
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    pla
    sta WMDATA
sin_gastar:
    lda eleg_flancos
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_switch, x        ; vive en RODATA: ver el conversor
    sta temp
    sep #$20
.a8
    lda #1
    jsr poner_switch
    lda #1
    rts

; El cursor al lugar que trae A. Si queda a la vista se mueve el cursor y se
; cambia la descripción, adentro del vblank; si no, la lista se corre y se
; repinta entera con la pantalla apagada, que es un cuadro en negro.
mover:
    pha
    stz temp + 3
    lda titulo_sel
    sec
    sbc eleg_sel
    jsr item_cursor_escribir
    pla
    sta titulo_sel
    cmp eleg_sel
    bcc sube_la_vista
    sec
    sbc eleg_sel
    cmp #ITEM_FILAS
    bcs baja_la_vista
    lda #1
    sta temp + 3
    lda titulo_sel
    sec
    sbc eleg_sel
    jsr item_cursor_escribir
    jmp items_desc_pintar
sube_la_vista:
    lda titulo_sel
    sta eleg_sel
    bra repintar
baja_la_vista:
    lda titulo_sel
    sec
    sbc #(ITEM_FILAS - 1)
    sta eleg_sel
repintar:
    lda #$80
    sta INIDISP
    jsl f:items_banco_subir       ; el tilemap en blanco, y de paso el resto
    jsr items_desc_pintar
    jsr items_desc_subir
    jsr items_filas_pintar
    lda #$0F
    sta INIDISP
    rts
.endproc

; Repone lo que la pantalla de ranuras le pisó al mapa, y nada más. Es para el
; save point, que la abre con el juego andando; el título no la necesita porque
; al salir carga el mapa entero.
;
; Qué pisó, en palabras de VRAM: los tiles en RANURA_VRAM y el tilemap en
; RANURA_MAP, que están elegidos para caer adentro del banco de tiles de BG1
; **en los cuatro repartos** de `vram_layout` —el conversor lo comprueba—. Los
; sprites, la capa de encima, la ventana y los dos tilemaps del mapa quedan
; afuera. No era así con las direcciones del menú del título: en el reparto
; ancho los sprites arrancan en $4000 y el tilemap en $4400 les caía encima,
; que se vio como 267 pixeles en el héroe del mapa 73 con el grupo 11 —el del
; bloque 0 se salvaba—. Y en CGRAM, la paleta 0: el color de fondo y la ventana
; de mensaje, más los primeros colores del mapa. Los registros: BG2SC,
; BG12NBA, TM y el scroll de BG2.
;
; Así que se vuelve a subir el banco de tiles con `load_map` —que además trae
; la CGRAM de abajo y la del mapa, y el dibujo de la animación que toca—, se
; tiñe de nuevo porque lo que subió viene sin teñir, y los registros los pone
; `ppu_init` más el BG12NBA del mapa. Es un subconjunto de
; `cargar_mapa_sin_eventos`, elegido a mano: lo que falta de ahí es estado
; —eventos, rutas, poses, la cola de VRAM— y reponerlo reiniciaría el juego.
;
; La pantalla se apaga a mano y **no se vuelve a prender acá**: `flush_video`
; escribe `brillo` en el vblank que viene, y así el mapa aparece en un cuadro
; entero y no a mitad de uno. Se llega apenas empezado un vblank —la pantalla
; de ranuras sale justo después de su `read_pad`—, así que el apagado también
; cae en un borde de cuadro. Medido: se ven **dos** cuadros negros y después el
; mapa, porque los 30 KB de `load_map` no entran en un vblank y ese tick dura
; dos cuadros —`cuadros_perdidos` cuenta uno—. En RM2k cerrar la escena lleva
; una transición, así que no desentona.
.proc volver_al_mapa
.a8
.i16
    lda #$80
    sta INIDISP
    jsr ppu_init
    ldx mapa_ofs
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA
    jsr load_map
    ; Y la capa de encima, por su paleta: las caras de la pantalla usan hasta
    ; ocho paletas de BG2, o sea las entradas 16 a 127, y `load_map` repone
    ; sólo las del fondo. Las de encima empiezan en ABOVE_FIRST, que puede
    ; caer ahí adentro.
    jsr load_above
    jsr aplicar_tinte
    stz destello_listo          ; `pal_buf` era de antes; si el destello sigue,
                                ; el cuadro que viene lo vuelve a armar
    jsr subir_tinte
    rts
.endproc

; Y volver de una **pelea**, que pisa mucho más que la pantalla de ranuras.
;
; `volver_al_mapa` alcanza para la tienda, el menú y las ranuras porque las tres
; escriben nada más que `RANURA_VRAM` y `RANURA_MAP`, elegidos para caer adentro
; del banco de tiles de BG1 en los cuatro repartos. La escena de la batalla no:
; `escena_subir` sube **32 KB**, o sea las palabras $4000 a $8000, más su
; tilemap en $3800 y 64 bytes en la palabra 0. En los tres repartos de
; `vram_layout` eso se lleva puesto, además del banco de BG1:
;
;   $5800  el tilemap del mapa          lo llena `fill_window`
;   $7800  el de la capa de encima      el mismo
;   $6800  los tiles de la ventana      `load_ventana`, con su tilemap y su HDMA
;   los sprites                         `load_sprite`: arrancan en 0, y la
;                                       palabra 0 se lleva los dos primeros
;                                       tiles del héroe
;
; Nada de eso lo repone `load_map`, así que hasta el 2026-09-13 el mapa volvía
; de la pelea con el fondo hecho basura. Lo que **no** va acá es `load_npcs` ni
; `load_ruta_graficos`: copian tablas del cartucho a RAM, la pelea no las toca,
; y reponerlas borraría lo que los eventos hayan movido antes de pelear.
;
; Va aparte de `volver_al_mapa` y no adentro para no cobrarle a la tienda, al
; menú y a las ranuras las 64 columnas de `fill_window`, que son el único
; momento en que se escribe tanto tilemap de una vez: ellas no lo necesitan, y
; un cuadro perdido de más se lo comerían los casos de la tanda que las miran.
.proc volver_de_batalla
.a8
.i16
    lda #$80
    sta INIDISP                 ; lo que sigue escribe VRAM por DMA
    jsr load_sprite             ; el banco de poses, la paleta de objetos y OBSEL
    jsr poses_npc_olvidar
    jsr load_ventana
    jsr fill_window
    jmp volver_al_mapa
.endproc

; La cola de poses en caliente después de reponer el banco: cada ranura tiene
; ahora la pose que el conversor dejó en el cartucho, y no la que su NPC venía
; mostrando. `load_sprite` arregla la del héroe —deja `hero_pose_vram` en $FF—
; y las de los NPC viven en `npc_buf + 12`, que es la única parte de esa tabla
; que esto toca: es una sombra de lo que hay en la VRAM, no estado del juego.
;
; Con $FF ninguna pose coincide, así que el próximo `subir_pose_npc` de cada
; fila la vuelve a encolar. Sin esto la sombra mentiría y un NPC que ya
; estuviera en su pose se quedaría con la del cartucho para siempre.
.proc poses_npc_olvidar
.a8
.i16
    ldy #$0000
otra:
    cpy npc_total               ; viene en bytes, no en filas
    beq listo
    lda #$FF
    sta npc_buf + 12, y
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
    rts
.endproc

; --- los eventos quietos que animan igual ---------------------------------
;
; `animation_type` 1 y 3 de RM2k —"Continuous" y "Fixed Dir/Continuous"— hacen
; que el evento recorra el ciclo de caminata **sin moverse**. El save point de
; Lashe City es del segundo tipo, y taro lo pidió el 2026-09-07.
;
; Los que caminan ya lo hacen: su ranura de ruta lleva el contador y `.proc
; animar_ruta_ev` lo avanza. Los quietos no tienen ranura, y no hay dónde
; guardarles un contador: la fila del NPC no tiene un byte libre —el +11 es el
; alto del salto— y la BSS está llena. Así que la columna sale del reloj del
; juego, igual que la animación del ChipSet: `vueltas` dividido por cada cuántos
; cuadros cambia, que es `anim_continua` por velocidad, y el ciclo de cuatro
; pasos con el tercero repitiendo el primero.
;
; **La fase no es la de RM2k**, que arranca el contador de cada personaje cuando
; el mapa lo crea; acá es global. Está declarado en assets/LIMITACIONES.md, y lo
; único que cambia es en cuál de los cuatro pasos del ciclo entra cada evento.
;
; Va antes de `mover_eventos` a propósito: si una ruta forzada agarra a uno de
; éstos, la ranura le pisa la pose después y gana ella, que es la que lleva el
; contador de verdad.
.proc animar_quietos
.a8
.i16
    ; ¿Este mapa tiene alguno? Lo dice el relleno de la última familia de
    ; `anim_tabla`; sin esto habría que recorrer las cuarenta filas siempre.
    ldy #(ANIM_FAMILIAS - 1)
    jsr anim_donde
    lda f:anim_tabla + 7, x
    bne hay
    rts
hay:
    ldy #$0000
otra:
    cpy npc_total
    beq listo
    lda npc_buf + 14, y
    beq siguiente               ; escondido: no se dibuja
    lda npc_buf + 13, y
    bpl siguiente               ; el bit 7 es "quieto y animando"
    and #$7F
    dec a                       ; la velocidad, de 0 a 5
    phy
    rep #$20
.a16
    and #$00FF
    tax
    ; El tick que dibuja la referencia es `vueltas + 1` visto desde acá, que es
    ; el mismo número que mira la animación del ChipSet —ella lo lee después
    ; del `inc vueltas`—. Medido: sin el `inc`, el save point del mapa 8 se
    ; queda una columna atrás y son 76 pixeles. Sin los ticks congelados, como
    ; ella: ver `vueltas_congeladas`.
    lda vueltas
    sec
    sbc f:vueltas_congeladas
    inc a
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda anim_continua, x        ; cada cuántos cuadros cambia de columna
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    and #(AGUA_CICLO_N - 1)
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ciclo_tres, x           ; la columna: 0, 1, 2 o de vuelta la 1
    ply
    sta temp + 3
    ; La pose: hacia dónde mira su página por tres, más la columna. Con la
    ; mirada fija —que es lo que pide `animation_type` 3— nadie la gira.
    jsr mirada_de_fila          ; la de su página, o la del giro
    sta temp + 2
    asl a
    clc
    adc temp + 2
    clc
    adc temp + 3
    sty npc_fila
    jsr subir_pose_npc
    ldy npc_fila
siguiente:
    rep #$20
.a16
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
    rts
.endproc


.proc sonido_de_codigo
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el índice
    iny
    iny
    phy
    jsr sonido_tocar            ; con A de dieciséis; vuelve con A de ocho
.a8
    ply
    rts
.endproc

; El efecto cuyo índice en `sonido_tabla` trae A de dieciséis bits, o nada si
; trae $FFFF. Se separó de `sonido_de_codigo` cuando la batalla empezó a tocar
; efectos: los suyos no salen del bytecode sino de las constantes `BA_SE_*`
; que emite el conversor, así que el índice llega en el acumulador.
;
; Entra con A de dieciséis bits y sale con A de ocho, que es como la dejaba
; antes. El banco de datos no importa: todo lo que lee va con `f:`.
.proc sonido_tocar
.a16
.i16
    cmp #$FFFF
    bne hay
    sep #$20
.a8
    rts
hay:
.a16
    phb
    pha
    sep #$20
.a8
    phk
    plb                         ; la tabla vive en el banco del código
    rep #$20
.a16
    pla
    sta temp
    asl a
    asl a
    asl a
    sec
    sbc temp                    ; por siete
    tax
    sep #$20
.a8
    lda f:sonido_tabla, x
    cmp #$FF
    beq listo         ; no hay efecto
    ; Y sólo si su muestra está en la ARAM: el paquete del mapa puede no
    ; haberla subido. Ver `paquete_cargar`.
    phx
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:FAR_ARAM_DE, x
    sep #$20
.a8
    plx
    cmp #0
    bne esta
    xba
    cmp #0
    bne esta
    bra listo
esta:
    ; Sin interrupciones mientras se copia: `irq_musica` lee el pendiente, y
    ; uno a medio escribir arrancaría con la muestra de uno y la altura de
    ; otro. La interrupción no se pierde, se atrasa hasta el `plp`.
    php
    sei
    ldy #0
copiar:
    lda f:sonido_tabla, x
    phx
    tyx
    sta f:SE_NUEVO, x
    plx
    inx
    iny
    cpy #7
    bcc copiar
    lda #1
    sta f:SE_PENDIENTE
    plp
listo:
    plb
    rts
.endproc

.proc destello_de_codigo
.a8
.i16
    lda [cod_ptr], y            ; r
    sta destello_rgb
    iny
    lda [cod_ptr], y            ; g
    sta destello_rgb + 1
    iny
    lda [cod_ptr], y            ; b
    sta destello_rgb + 2
    iny
    lda [cod_ptr], y            ; la fuerza, que es el nivel de arranque
    sta destello_nivel + 1
    stz destello_nivel
    iny
    lda [cod_ptr], y            ; cuadros
    sta destello_resta
    iny
    rts
.endproc

; --- el cartel del ShowPicture ----------------------------------------------
;
; Seis objetos de 32x32 con una paleta de sprite para ellos solos, y un fundido
; que es un tinte de esos quince colores cuadro a cuadro. Ver `tools/port/imagen.py`,
; que es donde está escrito dónde cae y de qué color es cada pixel, y OP_PICTURE
; en eventos.py.
;
; El cartel vive en **un solo mapa** de la ROM —el que se llevó sus tiles al
; banco de sprites; el conversor corta si otro lo muestra— y se borra al
; cambiar de mapa, que es el
; `erase_on_map_change` de `Game_Pictures`. Las dos cosas son la misma: sin sus
; tiles en VRAM no habría qué dibujar.

; Un cuadro de la rampa. `Game_Pictures::Picture::Update` interpola con
; `(finish - current) / dt` sobre `double`, y el resultado exacto de esa
; sucesión es lineal: `desde + (hasta - desde) * paso / pasos`. Acá va con
; enteros, y el signo se saca antes de dividir: el divisor del hardware no lo
; tiene.
;
; La paleta se rehace **sólo cuando el tono cambió de verdad**. En la rampa de
; 210 cuadros del "1 year earlier" el rojo sube de 0 a 100, o sea que cambia
; uno de cada dos cuadros: rehacerla igual costaba 96 productos y 96 divisiones
; por cuadro para escribir los mismos treinta y dos bytes.
.proc imagen_tick
.a8
.i16
    lda f:CARTEL_ACTIVA
    beq listo
    lda f:CARTEL_PASOS
    beq listo                   ; puesto y quieto
    lda f:CARTEL_PASO
    cmp f:CARTEL_PASOS
    bcs listo                   ; la rampa ya llegó
    lda f:CARTEL_PASO           ; `inc` no tiene forma larga
    inc a
    sta f:CARTEL_PASO
    jsr imagen_tono_ahora
    beq listo                   ; el mismo tono que el cuadro pasado
    jmp imagen_paleta
listo:
    rts
.endproc

; El tono de este cuadro, canal por canal. Deja en A si cambió alguno.
;
; La resta va siempre del lado positivo, como en `una_tabla_de_destello`: el
; divisor del hardware no tiene signo, y `//` de Python redondea para el otro
; lado con negativos. Los dos lados hacen esta misma cuenta partida en dos.
.proc imagen_tono_ahora
.a8
.i16
    lda #0
    sta f:CARTEL_CAMBIO
    ldx #$0000
canal:
    lda f:CARTEL_HASTA, x
    cmp f:CARTEL_DESDE, x
    bcc baja
    sec
    sbc f:CARTEL_DESDE, x
    jsr imagen_parte
    clc
    adc f:CARTEL_DESDE, x
    bra guardar
baja:
    lda f:CARTEL_DESDE, x
    sec
    sbc f:CARTEL_HASTA, x
    jsr imagen_parte
    eor #$FF                    ; `desde - parte` sin una variable de por medio:
    sec                         ; el complemento a uno más el acarreo es el menos
    adc f:CARTEL_DESDE, x
guardar:
    cmp f:CARTEL_TONO, x
    beq igual
    sta f:CARTEL_TONO, x
    lda #1
    sta f:CARTEL_CAMBIO
igual:
    inx
    cpx #3
    bne canal
    lda f:CARTEL_CAMBIO
    rts
.endproc

; A = A * CARTEL_PASO / CARTEL_PASOS, con el multiplicador y el divisor del
; hardware. El producto llega a 200 * 255 y entra en dieciséis bits; el
; cociente no pasa de 200, así que alcanza con el byte bajo.
.proc imagen_parte
.a8
.i16
    sta WRMPYA
    lda f:CARTEL_PASO
    sta WRMPYB
    nop                         ; ocho ciclos hasta que el producto está
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, de dieciséis bits
    sep #$20
.a8
    lda f:CARTEL_PASOS
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    rts
.endproc

; Los dieciséis colores del cartel teñidos con su tono, en su lugar de
; `cgram_sombra`. Los sube `flush_video` en el vblank con un DMA propio.
;
; Se reusan `tabla_canal` y `armar_paleta`, que es lo que el tinte de pantalla
; ya hacía: la única diferencia es de dónde salen los tres valores y que la
; saturación del cartel es siempre neutra —`imagen_aceptable` no acepta otra—,
; así que se le pone la neutra a `tinte_s` mientras dura y se la devuelve.
; Las tres tablas de trabajo quedan con el tinte del cartel; `restaurar_tablas`
; las vuelve a dejar como las del tinte de pantalla, copiando `puro`, que es
; mucho más barato que rehacerlas.
.proc imagen_paleta
.a8
.i16
    ; **Y se guarda.** `armar_paleta` la usa de cursor de la paleta y la deja
    ; en 32, y quien llama a esto desde un opcode la tiene apuntando al
    ; bytecode: sin esto el intérprete seguía leyendo treinta y dos bytes más
    ; adelante y corría lo que hubiera ahí. Fue el primer rojo de este cartel,
    ; y de los que no se ven: la página seguía corriendo, sólo que otra.
    phy
    lda tinte_s
    pha
    lda #TINTE_NEUTRO
    sta tinte_s
    lda f:CARTEL_TONO + 0
    ldx #.loword(tabla_r)
    jsr tabla_canal
    lda f:CARTEL_TONO + 1
    ldx #.loword(tabla_g)
    jsr tabla_canal
    lda f:CARTEL_TONO + 2
    ldx #.loword(tabla_b)
    jsr tabla_canal
    rep #$20
.a16
    lda #.loword(imagen_cgram)
    sta tin_ptr
    lda #16
    sta tin_count
    sep #$20
.a8
    lda #^imagen_cgram
    sta tin_ptr + 2
    jsr armar_paleta            ; los dieciséis, teñidos, en `pal_buf`
    ; Y de ahí a la sombra, **sin tocar `tinte_listo`**: prenderlo mandaría a
    ; subir las tres paletas del mapa en cada cuadro de la rampa, y eso le come
    ; al vblank el presupuesto de poses.
    ldx #$0000
copia:
    lda pal_buf, x
    sta cgram_sombra + 2 * (128 + 16 * IMAGEN_PAL), x
    inx
    cpx #32
    bne copia
    pla
    sta tinte_s
    lda #1
    sta f:CARTEL_LISTO
    jsr restaurar_tablas
    ply
    rts
.endproc

; Los objetos del cartel, si está puesto.
;
; Van **después del cronómetro y antes de los personajes**, que es el orden de
; RM2k: `Priority_Timer` es 140, `Priority_PictureOld` 120 y `Priority_Player`
; 40. En OAM eso es el orden de la lista, porque gana el índice más bajo; y la
; prioridad 3 los pone adelante de las dos capas.
;
; Cuestan **veinticuatro de los treinta y cuatro tiles por línea** en las
; veintinueve líneas que ocupan, así que ahí entran dos personajes más y no
; más. La referencia cuenta lo mismo y declara las líneas donde no alcanza.
.proc imagen_oam
.a8
.i16
    lda f:CARTEL_ACTIVA
    bne hay
    rts
hay:
    lda #$02
    sta obj_grande              ; los objetos del cartel son de 32x32
    lda #0
    sta f:CARTEL_I
cada:
    rep #$20
.a16
    lda f:CARTEL_I
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; treinta y dos por objeto
    clc
    adc #IMAGEN_X & $FFFF       ; es negativo, y ca65 no acepta un inmediato negativo
    sta obj_x
    lda #IMAGEN_Y
    sta obj_y
    ; Y qué tile. Un objeto de 32x32 lee cuatro tiles de cuatro filas seguidas
    ; de la grilla de nombres, que es de dieciséis: o sea que en una fila de
    ; bloques entran cuatro objetos y el quinto arranca 64 tiles más adelante.
    lda f:CARTEL_I
    and #$0003
    asl a
    asl a                       ; los cuatro de ancho del objeto
    sta temp
    lda f:CARTEL_I
    and #$00FC
    asl a
    asl a
    asl a
    asl a                       ; y la fila de bloques, que son 64 por cada 4
    clc
    adc temp
    clc
    adc #IMAGEN_BASE
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: prioridad 3 —adelante de las dos capas—, la paleta del cartel,
    ; y el noveno bit del tile.
    lda temp + 1
    and #$01
    ora #($30 | (IMAGEN_PAL * 2))
    sta obj_attr
    jsr emit_object
    lda f:CARTEL_I
    inc a
    sta f:CARTEL_I
    cmp #IMAGEN_OBJETOS
    beq salir
    jmp cada
salir:
    rts
.endproc

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

; El reparto de este mapa, al cargarlo. El byte es 0 —"acá no se dibuja"— o el
; bit 7 prendido con el bloque de 64 tiles y la paleta, de tres bits cada uno.
; Ver `animaciones_asm` en snes_convert.py.
.proc animacion_dibujo_mapa
.a8
.i16
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
    ; Qué cuadro: el primero de esta animación más el que toca, y de ahí su
    ; puntero de 24 bits. Van uno por cuadro y no un bloque seguido por
    ; animación porque 28 cuadros son 57 KB y un banco tiene 32.
    rep #$20
.a16
    lda f:ANIMB_FILA
    tax
    lda f:anim_batalla_tabla + 4, x
    clc
    adc f:ANIMB_CUADRO
    asl a
    asl a                       ; cuatro bytes por puntero
    tax
    lda f:anim_batalla_cuadros, x
    sta A1T0L
    lda f:ANIMB_VRAM
    sta VMADDL
    lda #ANIM_B_BYTES
    sta DAS0L
    sep #$20
.a8
    lda f:anim_batalla_cuadros + 2, x
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

; --- el giro hacia el héroe ------------------------------------------------
;
; `Game_Event::ScheduleForegroundExecution`: el evento que el héroe dispara
; —con la tecla de acción o por contacto— se da vuelta hacia él, salvo que su
; animación fije la dirección. Mira para ahí mientras dura su página y al
; terminar vuelve a su pose, que es el `UpdateFacing` de
; `OnFinishForegroundEvent`. Las reglas —cuándo gira, cuándo se deshace— están
; en `giro_disparar` y `giro_revisar`, acá abajo.
;
; Hay un solo giro a la vez: sólo gira el evento que disparó el héroe, y el
; anterior terminó su página antes. Su estado vive en la RAM lejana:
;
;   GIRO_EV     el evento, o $FF. **No se guarda su fila**: las filas se
;               reordenan cuando alguien camina —`acomodar_npc`—, y la fila
;               guardada pasaba a ser de otro. La primera versión le devolvía
;               el tile del Bum de Lashe City al evento que había quedado en su
;               lugar; lo encontró `bum-vuelve`. Se la busca con
;               `npc_de_evento` cada vez.
;   GIRO_K      la entrada de `npc_poses` de su gráfico, y GIRO_PPOSE la pose
;               de su página: con las dos, un refresco sabe si la página
;               nueva trae el mismo gráfico
;   GIRO_DIR    hacia dónde mira
;   GIRO_*_ANT  el tile, los atributos y la pose de la fila antes de girar,
;               para devolvérselos
;   ELEG_K, ELEG_POSE   el +30 y el +31 de la página que ganó la última vez
;               que corrió `buscar_pagina_de_evento`
;
; Un quieto comparte su ranura de VRAM con los otros quietos de la misma pose,
; así que para girar se muda a la ranura de giro del mapa, `M_GIRO_TILE4`, y
; se le sube ahí la pose nueva. Uno que camina o que anima quieto tiene la
; suya y gira en el lugar.
FAR_GIRO   = $30C0
GIRO_EV    = $7E0000 + FAR_GIRO
GIRO_K     = GIRO_EV + 3
GIRO_PPOSE = GIRO_EV + 4
GIRO_TILE_ANT = GIRO_EV + 5
GIRO_ATTR_ANT = GIRO_EV + 6
GIRO_POSE_ANT = GIRO_EV + 7
GIRO_DIR   = GIRO_EV + 8
ELEG_K     = GIRO_EV + 9
ELEG_POSE  = GIRO_EV + 10

; Sin giro. En el reset y al cargar un mapa: las filas son otras.
.proc giro_limpiar
.a8
.i16
    lda #$FF
    sta f:GIRO_EV
    rts
.endproc

; La página de `ev_buscado` acaba de encolarse por el héroe: si gira, que
; mire hacia él. La celda del evento es (celda_x, celda_y) y la del héroe
; (tile_x, tile_y). Entra con ELEG_K y ELEG_POSE de su página.
.proc giro_disparar
.a8
.i16
    lda f:ELEG_K
    cmp #$FF
    bne gira
    rts                         ; la página no gira
gira:
    lda ev_buscado
    jsr ranura_del_evento
    cpx #$FFFF
    beq sin_ruta
    jsr ruta_ocupada
    beq sin_ruta                ; la ranura quedó de una ruta que ya terminó
    rts                         ; una ruta andando: ella decide adónde mira
sin_ruta:
    lda ev_buscado
    jsr npc_de_evento
    cpy #$FFFF
    bne con_fila
    rts
con_fila:
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne puede
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    cmp #$FF
    bne puede
    rts                         ; un quieto sin ranura de giro
puede:
    phy
    jsr giro_deshacer           ; si quedaba otro, vuelve a lo suyo
    ply

    ; Hacia dónde: `GetDirectionToCharacter`, con sx y sy del evento menos el
    ; héroe. Si |sx| > |sy| gana el horizontal; si no, el vertical.
    rep #$20
.a16
    lda celda_x
    sec
    sbc tile_x
    pha                         ; sx
    bpl sx_pos
    eor #$FFFF
    inc a
sx_pos:
    sta temp                    ; |sx|
    lda celda_y
    sec
    sbc tile_y
    sta temp + 2                ; sy
    bpl sy_pos
    eor #$FFFF
    inc a
sy_pos:
    cmp temp
    bcs vertical                ; |sy| >= |sx|
    pla
    bmi a_la_derecha            ; el evento a la izquierda del héroe
    lda #DIR_LEFT
    bra dir_lista
a_la_derecha:
    lda #DIR_RIGHT
    bra dir_lista
vertical:
    pla
    lda temp + 2
    beq abajo
    bmi abajo                   ; el evento arriba del héroe
    lda #DIR_UP
    bra dir_lista
abajo:
    lda #DIR_DOWN
dir_lista:
    sep #$20
.a8
    sta f:GIRO_DIR

    lda ev_buscado
    sta f:GIRO_EV
    lda f:ELEG_K
    sta f:GIRO_K
    lda f:ELEG_POSE
    sta f:GIRO_PPOSE
    lda npc_buf + 6, y
    sta f:GIRO_TILE_ANT
    lda npc_buf + 7, y
    sta f:GIRO_ATTR_ANT
    lda npc_buf + 12, y
    sta f:GIRO_POSE_ANT
    jmp giro_aplicar
.endproc

; La pose que mira hacia GIRO_DIR, en la fila Y: la columna de la de antes
; y la fila de la dirección.
.proc giro_aplicar
.a8
.i16
    lda f:GIRO_POSE_ANT
columna:
    cmp #3
    bcc con_columna
    sbc #3                      ; el carry quedó en 1
    bra columna
con_columna:
    sta temp
    lda f:GIRO_DIR
    asl a
    clc
    adc f:GIRO_DIR
    clc
    adc temp
    sta temp                    ; la pose nueva
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    beq quieto
    lda npc_buf + 13, y
    bmi listo                   ; anima quieto: `animar_quietos` la sube
    sty npc_fila
    lda temp
    jmp subir_pose_npc
quieto:
    ; A la ranura de giro: su tile, con el bit 8 en los atributos.
    lda temp
    sta npc_buf + 12, y
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    asl a
    asl a                       ; el tile: el byte por cuatro, y el bit 8
    sta npc_buf + 6, y
    lda #0
    rol a
    sta temp + 1
    lda npc_buf + 7, y
    and #$FE
    ora temp + 1
    sta npc_buf + 7, y
    ; Y la pose, de las doce de su gráfico: (k * 12 + pose) * 3 en `npc_poses`.
    lda f:GIRO_K
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; por cuatro
    sta temp + 2
    asl a
    asl a
    asl a                       ; por treinta y dos
    clc
    adc temp + 2                ; treinta y seis por gráfico
    sta temp + 2
    lda temp
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; la pose por tres
    clc
    adc temp + 2
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2
    ldx mapa_ofs
    lda f:mapa_tabla + M_GIRO_TILE4, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; el tile
    asl a
    asl a
    asl a
    asl a                       ; dieciséis palabras por tile
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne listo
    jsr giro_deshacer           ; la cola estaba llena: no gira
listo:
    rts
.endproc

; Si la ranura de ruta X tiene algo andando: la ruta propia de su página,
; órdenes por dar, un paso, una espera o un salto. Z=1 si está libre. Es
; `Ruta.pendiente or Ruta.de_pagina` en eventos.py. Una ranura no se suelta
; hasta que se carga otro mapa, así que "tiene ranura" no alcanzaba: el
; `GangMember1` de Lashe City, al que una escena ya había movido, no giraba
; nunca más. taro lo encontró jugando.
.proc ruta_ocupada
.a8
.i16
    lda ruta_ev + 18, x
    and #$01
    bne si
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc si
    lda ruta_ev + 7, x
    ora ruta_ev + 9, x
    ora ruta_ev + 13, x
    bne si
    lda #0
    rts
si:
    lda #1
    rts
.endproc

; Se terminó el giro: la fila vuelve a lo suyo. No toca nada si no hay.
.proc giro_deshacer
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    jsr npc_de_evento
    lda #$FF
    sta f:GIRO_EV
    cpy #$FFFF
    beq nada
    lda npc_buf + 9, y
    cmp #NPC_QUIETO
    bne propia
    lda f:GIRO_TILE_ANT
    sta npc_buf + 6, y
    lda f:GIRO_ATTR_ANT
    sta npc_buf + 7, y
    lda f:GIRO_POSE_ANT
    sta npc_buf + 12, y
    rts
propia:
    lda npc_buf + 13, y
    bmi nada                    ; anima quieto: vuelve solo, el cuadro que viene
    sty npc_fila
    lda f:GIRO_POSE_ANT
    jmp subir_pose_npc
nada:
    rts
.endproc

; A: un evento que se queda con una ranura de ruta. Si era el que giraba, el
; giro se termina: desde ahora adónde mira lo decide la ruta.
.proc giro_por_ruta
.a8
.i16
    cmp f:GIRO_EV
    bne nada
    jmp giro_deshacer
nada:
    rts
.endproc

; Al empezar un refresco que aplica páginas: si el evento que gira cambió a
; una página que no gira o con otro gráfico, el giro se termina. Es el
; `SetFacing(page->character_direction)` de `Game_Event::RefreshPage`, que
; sólo pasa si la página nueva es otra.
.proc giro_revisar
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    rep #$20
.a16
    and #$00FF
    sta ev_buscado
    sep #$20
.a8
    jsr buscar_pagina_de_evento
    lda elegida_hay
    beq deshacer                ; se quedó sin página
    lda f:ELEG_K
    cmp #$FF
    beq deshacer
    cmp f:GIRO_K
    bne deshacer
    lda f:ELEG_POSE
    cmp f:GIRO_PPOSE
    bne deshacer
nada:
    rts
deshacer:
    jmp giro_deshacer
.endproc

; La fila Y acaba de recibir el gráfico de su página: si es la del evento que
; gira y el giro sigue, se lo vuelve a poner encima.
.proc giro_reponer
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq nada
    cmp npc_buf + 8, y
    bne nada
    lda npc_buf + 12, y
    sta f:GIRO_POSE_ANT
    lda npc_buf + 6, y
    sta f:GIRO_TILE_ANT
    lda npc_buf + 7, y
    sta f:GIRO_ATTR_ANT
    jmp giro_aplicar
nada:
    rts
.endproc

; Hacia dónde mira la fila Y para `animar_quietos`: la de su página, o la del
; giro si es la que gira. Devuelve A.
.proc mirada_de_fila
.a8
.i16
    lda f:GIRO_EV
    cmp #$FF
    beq propia
    cmp npc_buf + 8, y
    bne propia
    lda f:GIRO_DIR
    rts
propia:
    lda npc_buf + 10, y
    rts
.endproc

; Sube la pose A del NPC de la fila Y, si no es la que ya está en la VRAM.
;
; Salió de adentro de `refrescar_npc`, que era el único que la necesitaba, el
; día que hubo un segundo: `animar_quietos`. `npc_fila` tiene que traer la misma
; fila que Y, que es como venía.
.proc subir_pose_npc
.a8
.i16
    ; El tile de la fila es fijo —es su ranura— y lo que cambia son los tiles de
    ; la ranura, que se encolan acá y suben en el vblank que viene con la OAM.
    cmp npc_buf + 12, y
    bne cambia
    rts
cambia:
    sta npc_buf + 12, y
    sta temp                    ; la pose

    ; El puntero a la pose, de `npc_poses`: doce punteros de tres bytes por
    ; personaje animado, o sea (k * 12 + pose) * 3.
    lda npc_buf + 9, y
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; por cuatro
    sta temp + 2
    asl a
    asl a
    asl a                       ; por treinta y dos
    clc
    adc temp + 2                ; treinta y seis por personaje
    sta temp + 2
    lda temp
    and #$00FF
    sta temp
    asl a
    clc
    adc temp                    ; la pose por tres
    clc
    adc temp + 2
    tay
    lda [poses_ptr], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [poses_ptr], y
    sta vq_src + 2

    ; El destino: su ranura, que es el tile de la fila por dieciséis palabras
    ; desde donde arranca el banco de sprites.
    ldy npc_fila
    lda npc_buf + 7, y
    and #$01                    ; el bit 8 del tile vive en los atributos
    xba
    lda npc_buf + 6, y
    rep #$20
.a16
    asl a
    asl a
    asl a
    asl a                       ; dieciséis palabras por tile
    ldx mapa_ofs
    clc
    adc f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne listo
    ; La cola estaba llena: se vuelve a pedir el cuadro que viene.
    ldy npc_fila
    lda #$FF
    sta npc_buf + 12, y
listo:
    rts
.endproc

; Deja la fila del NPC de la ranura X donde el evento está ahora: la posición en
; pixeles, la clave con la que se ordena, y el tile de la pose que le toca.
;
; Lo primero que hace es copiarse de la ranura lo que necesita, y recién después
; usa X para otra cosa. Es más largo de leer y mucho más difícil de romper:
; adentro se llaman tres rutinas y todas usan índices.
.proc refrescar_npc
.a8
.i16
    stz salto_alto
    stz salto_alto + 1
    jsr celda_del_evento        ; deja su celda en celda_x/celda_y, y usa X
    lda ruta_ev + 7, x
    sta slot_cuadros            ; si hay un paso en curso
    rep #$20
.a16
    lda ruta_ev + 22, x         ; y cuánto le falta, de 256 por celda: a
    lsr a                       ; pixeles, tirando los dieciseisavos
    lsr a
    lsr a
    lsr a
    sta slot_px
    sep #$20
.a8
    lda ruta_ev + 8, x
    sta slot_mira
    lda ruta_ev + 30, x
    sta slot_dir                ; la dirección del paso en curso
    lda ruta_ev + 10, x
    sta slot_paso
    lda ruta_ev + 0, x
    jsr npc_de_evento
    sty npc_fila
    cpy #$FFFF
    bne hay_fila
    rts                         ; el evento no tiene gráfico: no hay qué mover
hay_fila:

    ; Dónde está, en pixeles: la celda por dieciséis, menos lo que le falte al
    ; paso en curso a WALK_SPEED por cuadro.
    rep #$20
.a16
    lda celda_x
    asl a
    asl a
    asl a
    asl a
    sta npc_px
    lda celda_y
    asl a
    asl a
    asl a
    asl a
    sta npc_py
    lda slot_px                 ; los pixeles que faltan del paso
    sta temp
    sep #$20
.a8
    lda slot_cuadros
    beq sin_paso_npc            ; sin paso en curso, ya está en su celda
    bra con_paso_npc
sin_paso_npc:
    ; ¿Está saltando? Entonces la celda es la de destino y el dibujo va detrás,
    ; con el arco encima. La clave de orden sale de la posición **sin** el arco:
    ; es `GetScreenY(false)`, así que quien está en el aire no se adelanta.
    lda ruta_ev + 13, x
    beq puesto
    sta salto_resta
    lda ruta_ev + 14, x
    sta salto_dx
    lda ruta_ev + 15, x
    sta salto_dy
    phx
    jsr salto_posicion_npc
    jsr alto_del_salto
    plx
    bra puesto
con_paso_npc:

    ; La dirección del paso, que va aparte de hacia dónde mira: con la mirada
    ; fija —los droides del mapa 2— sube mirando abajo. Por tabla, porque en
    ; diagonal hay que descontar en los dos ejes: los pixeles que faltan se le
    ; restan al sentido del paso, o sea que quien va hacia la derecha se dibuja
    ; todavía a la izquierda de su celda. X se pisa y no lo necesita nadie
    ; más: de acá en adelante el índice es `npc_fila`.
    lda slot_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:paso_dx, x
    beq sin_dx_npc
    bmi mas_px                  ; $FF, o sea hacia la izquierda
    jsr restar_a_px
    bra sin_dx_npc
mas_px:
    jsr sumar_a_px
sin_dx_npc:
    lda f:paso_dy, x
    beq puesto
    bmi mas_py                  ; venía de abajo: todavía le falta subir
    jsr restar_a_py
    bra puesto
mas_py:
    jsr sumar_a_py

puesto:
    ; A la fila: la posición, y la clave con la capa que ya traía.
    ldy npc_fila
    rep #$20
.a16
    lda npc_px
    sta npc_buf + 0, y
    lda npc_py
    sta npc_buf + 2, y
    sep #$20
.a8
    lda salto_alto
    sta npc_buf + 11, y         ; cuánto levantar el dibujo, sin tocar la clave
    rep #$20
.a16
    lda npc_buf + 4, y
    and #$F000                  ; la capa se queda; la Y se reemplaza
    sta temp
    lda npc_py
    and #$0FFF
    ora temp
    sta npc_buf + 4, y
    sep #$20
.a8

    ; La pose: hacia dónde mira por tres, más la columna del ciclo. La columna 3
    ; dibuja la misma que la 1, que es como RM2k arma un ciclo de cuatro con
    ; tres columnas.
    lda slot_mira
    cmp #RUTA_EV_SIN_MIRAR
    bne tiene_dir
    lda npc_buf + 10, y         ; todavía no giró: mira adonde dice su página
tiene_dir:
    ; Y si es el que mira al héroe, adonde dice el giro: su ranura está
    ; libre, porque con una ruta andando no gira. Ver `giro_disparar`.
    pha
    lda f:GIRO_EV
    cmp npc_buf + 8, y
    bne sin_giro
    pla
    lda f:GIRO_DIR
    pha
sin_giro:
    pla
    sta temp
    asl a
    clc
    adc temp                    ; por tres
    sta temp
    lda slot_paso
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    clc
    adc temp                    ; la pose, de 0 a 11
    jsr subir_pose_npc
acomodar:
    jmp acomodar_npc            ; y la fila, a donde le toque ahora
.endproc

; Si la fila `cmp_a` va **antes** que la `cmp_b` en el orden de dibujado.
; Devuelve A distinto de cero si sí.
;
; El orden es el de RM2k: mayor Y —que va adentro de la clave, junto con la
; capa—, después mayor X, y después mayor id. Los tres desempates hacen falta
; porque un evento que camina cambia de fila todo el tiempo y empata con
; cualquiera; con NPCs quietos casi nunca se notaba.
.proc npc_va_antes
.a8
.i16
    rep #$20
.a16
    ldy cmp_a
    lda npc_buf + 4, y
    ldy cmp_b
    cmp npc_buf + 4, y
    beq por_x
    sep #$20
.a8
    bcc no
    bra si
por_x:
.a16                            ; se llega en dieciséis, desde el `beq` de arriba
    ldy cmp_a
    lda npc_buf + 0, y
    ldy cmp_b
    cmp npc_buf + 0, y
    beq por_evento
    sep #$20
.a8
    bcc no
    bra si
por_evento:
.a16                            ; ídem: el `sep` de abajo lo achica
    sep #$20
.a8
    ldy cmp_a
    lda npc_buf + 8, y
    ldy cmp_b
    cmp npc_buf + 8, y
    bcc no
    beq no                      ; iguales: no hay nada que reacomodar
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Intercambia las dos filas que apuntan `cmp_a` y `cmp_b`, de a palabras.
.proc npc_swap
.a8
.i16
    ldx #$0000
otra:
    rep #$20
.a16
    txa
    clc
    adc cmp_a
    tay
    lda npc_buf, y
    sta temp
    txa
    clc
    adc cmp_b
    tay
    lda npc_buf, y
    pha
    lda temp
    sta npc_buf, y
    txa
    clc
    adc cmp_a
    tay
    pla
    sta npc_buf, y
    txa
    clc
    adc #2
    tax
    cpx #NPC_STRIDE
    sep #$20
.a8
    bcc otra
    rts
.endproc

; Deja la fila `npc_fila` donde le toca ahora, con la tabla ya ordenada.
;
; Sólo se mueve la que cambió, y a lo sumo unos pocos lugares: la Y cambia de a
; dos pixeles por cuadro. Ordenar la tabla entera todos los cuadros costaría lo
; mismo aunque no se moviera nadie.
.proc acomodar_npc
.a8
.i16
subir:
    lda npc_fila
    ora npc_fila + 1
    beq bajar                   ; ya es la primera
    rep #$20
.a16
    lda npc_fila
    sta cmp_a
    sec
    sbc #NPC_STRIDE
    sta cmp_b
    sep #$20
.a8
    jsr npc_va_antes
    beq bajar
    jsr npc_swap
    rep #$20
.a16
    lda cmp_b
    sta npc_fila
    sep #$20
.a8
    bra subir

bajar:
    rep #$20
.a16
    lda npc_fila
    clc
    adc #NPC_STRIDE
    cmp npc_total
    sep #$20
.a8
    bcs listo                   ; ya es la última
    rep #$20
.a16
    lda npc_fila
    sta cmp_b
    clc
    adc #NPC_STRIDE
    sta cmp_a
    sep #$20
.a8
    jsr npc_va_antes
    beq listo
    jsr npc_swap
    rep #$20
.a16
    lda cmp_a
    sta npc_fila
    sep #$20
.a8
    bra bajar
listo:
    rts
.endproc

; Las cuatro sumas del paso en curso, con `temp` trayendo los pixeles que
; faltan. Están aparte porque el `rep`/`sep` de cada una adentro del `cmp`
; alargaba el procedimiento hasta que los saltos no llegaban.
.proc sumar_a_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    clc
    adc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc restar_a_py
.a8
.i16
    rep #$20
.a16
    lda npc_py
    sec
    sbc temp
    sta npc_py
    sep #$20
.a8
    rts
.endproc

.proc sumar_a_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    clc
    adc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

.proc restar_a_px
.a8
.i16
    rep #$20
.a16
    lda npc_px
    sec
    sbc temp
    sta npc_px
    sep #$20
.a8
    rts
.endproc

; Si la celda de al lado en la dirección que trae A existe, o sea si no se cae
; del mapa. Devuelve A distinto de cero si existe.
;
; Está separado de `puede_celda` por una razón de alcance y no de diseño: junto,
; el `beq` del primer control quedaba a 130 bytes de la salida y el ensamblador
; cortaba. `sep`/`rep` no tocan Z ni C, así que el resultado de la comparación
; de dieciséis bits sobrevive al cambio de ancho.
.proc celda_vecina_existe
.a8
.i16
    cmp #DIR_UP
    bne prueba_abajo
    rep #$20
.a16
    lda celda_y
    sep #$20
.a8
    beq no                      ; ya está en la fila de arriba
    bra si
prueba_abajo:
    cmp #DIR_DOWN
    bne prueba_izquierda
    rep #$20
.a16
    lda celda_y
    inc a
    cmp mapa_alto
    sep #$20
.a8
    bcs no
    bra si
prueba_izquierda:
    cmp #DIR_LEFT
    bne prueba_derecha
    rep #$20
.a16
    lda celda_x
    sep #$20
.a8
    beq no
    bra si
prueba_derecha:
    rep #$20
.a16
    lda celda_x
    inc a
    cmp mapa_ancho
    sep #$20
.a8
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si desde (celda_x, celda_y) se puede dar un paso en la dirección que trae A.
; Devuelve A distinto de cero si se puede.
;
; Es la misma regla que la del héroe —se consultan las dos caras, la que se deja
; y la que se entra— pero desde una celda cualquiera, y sin mirar quién está
; parado dónde, que es lo que hace también la ruta forzada del héroe.
;
; Un movimiento bloqueado se saltea. En las 26 rutas de eventos que este juego
; compila eso pasa **una sola vez**, en el mapa 117, y por esa sola vez hay que
; modelarlo: si los dos lados lo ignoraran igual, esa ruta duraría ocho cuadros
; de más de los dos lados y la comparación daría cero.
.proc puede_celda
.a8
.i16
    sta celda_dir
    stz celda_dir + 1
    jsr celda_vecina_existe
    bne :+
    jmp no                      ; queda lejos para un salto corto
:
    ; Atravesando paredes las dos caras dan que sí, pero la celda tiene que
    ; existir: es el `if (self.GetThrough()) return true;` de
    ; `Game_Map::CheckOrMakeWayEx`, que va después del `IsValid`.
    lda atravesando
    beq con_colision
    lda #1
    rts
con_colision:

    ; La cara que se deja.
    jsr ptr_de_celda
    rep #$20
.a16
    lda celda_x                 ; la celda que se deja, para lo que un evento
    sta pasa_x                  ; de tile le imponga
    lda celda_y
    sta pasa_y
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_salir, x
    bne :+
    jmp no                      ; queda lejos para un salto corto
:

    ; Y la cara del destino, que es la celda de al lado.
    lda celda_dir
    cmp #DIR_UP
    bne baja
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_menos
    bra entra
    ; Las tres etiquetas que siguen se alcanzan con el acumulador **en ocho
    ; bits**, aunque lo último que el ensamblador leyó fue un `.a16`: el `bra`
    ; de arriba se saltea el cambio de ancho. Sin este `.a8` el `cmp` se emite
    ; con un inmediato de dos bytes, la CPU lee sólo uno, y el segundo —un
    ; $00— se ejecuta como BRK.
baja:
.a8
    cmp #DIR_DOWN
    bne izquierda
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_mas
    bra entra
izquierda:
.a8
    cmp #DIR_LEFT
    bne derecha
    rep #$20
.a16
    lda #2
    jsr ptr_menos
    bra entra
derecha:
.a8
    rep #$20
.a16
    lda #2
    jsr ptr_mas
entra:
.a16
    lda celda_x                 ; y la celda a la que se entra
    sta pasa_x
    lda celda_y
    sta pasa_y
    sep #$20
.a8
    ldx celda_dir
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_entrar, x
    bne :+
    jmp no
:
    ; Y que no haya nadie parado en la celda de al lado. Con `atravesando`
    ; no se llega acá: es el `GetThrough()` de arriba.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_dest_x
    lda f:paso_dy, x
    jsr sumar_a_dest_y
    jsr celda_bloqueada
    bne no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si desde (celda_x, celda_y) se puede dar el paso diagonal que trae A, 4 a 7.
; Devuelve A distinto de cero si se puede, y deja la celda donde la encontró.
;
; RM2k **no mira la celda diagonal**: es `Game_Character::Move`, que prueba las
; dos eles. Primero la vertical y después la horizontal desde el codo, y si esa
; no sale, la horizontal y después la vertical; alcanza con que una de las dos
; esté libre entera. Por eso no se cruza el vértice de dos paredes en diagonal,
; y sí se pasa si hay por dónde rodear.
;
; Cada pata es una llamada a `puede_celda`, o sea las mismas dos caras y el
; mismo chequeo de quién está parado dónde que un paso derecho. Del lado de
; Python es `puede_en_diagonal`, con la misma forma.
.proc puede_celda_diag
.a8
.i16
    sec
    sbc #4
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    sta diag_h
    rep #$20
.a16
    lda celda_x                 ; de dónde sale, para volver entre ele y ele
    sta diag_x
    lda celda_y
    sta diag_y
    sep #$20
.a8

    lda diag_v                  ; la ele vertical: arriba y después al costado
    jsr puede_celda
    beq otra_ele
    lda diag_v
    jsr celda_al_codo
    lda diag_h
    jsr puede_celda
    bne si
otra_ele:
    jsr celda_al_origen         ; la ele horizontal: al costado y después arriba
    lda diag_h
    jsr puede_celda
    beq no
    lda diag_h
    jsr celda_al_codo
    lda diag_v
    jsr puede_celda
    bne si
no:
    jsr celda_al_origen
    lda #0
    rts
si:
    jsr celda_al_origen
    lda #1
    rts
.endproc

; La celda pasa a ser la de origen más el paso de la dirección que trae A: el
; codo de la ele, de donde arranca la segunda pata.
.proc celda_al_codo
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    lda f:paso_dx, x
    beq sin_x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_x
    ora #$FF00
mas_x:
    clc
    adc celda_x
    sta celda_x
    sep #$20
.a8
sin_x:
    lda f:paso_dy, x
    beq sin_y
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_y
    ora #$FF00
mas_y:
    clc
    adc celda_y
    sta celda_y
    sep #$20
.a8
sin_y:
    rts
.endproc

; Y la celda vuelve a ser la de origen.
.proc celda_al_origen
.a8
.i16
    rep #$20
.a16
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; Hacia dónde queda mirando el evento de la ranura X después de un paso en la
; diagonal de `ruta_dir`. La pose nueva sale en A.
;
; Es `Game_Character::UpdateFacing`, y la respuesta no es "hacia la diagonal":
; el charset tiene cuatro poses y ninguna apunta a un rincón. Se conserva la
; que ya tenía si es una de las dos componentes del paso, y si no se da vuelta
; 180°. Del lado de Python es `encarar_en_diagonal`.
;
; Lo primero es de dónde sale el giro, y no es sólo leer +8: veinte de las
; veintiséis rutas con diagonales de este juego arrancan **con** la diagonal,
; sin girar antes, así que ahí todavía está RUTA_EV_SIN_MIRAR y la pose de
; verdad es la de su página, que vive en la fila del NPC. Del lado de Python
; es `Ruta.mirando_pagina`.
.proc encarar_diagonal
.a8
.i16
    lda ruta_ev + 8, x
    cmp #RUTA_EV_SIN_MIRAR
    bne con_pose
    phx
    lda ruta_ev + 0, x
    jsr npc_de_evento
    plx
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 10, y
    bra con_pose
sin_fila:
    lda #DIR_DOWN               ; sin gráfico: no se le ve la pose a nadie
con_pose:
    sta diag_mira
    lda ruta_dir
    sec
    sbc #4
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    plx
    cmp diag_mira
    beq queda
    lda diag_v
    cmp diag_mira
    beq queda
    lda diag_mira               ; ninguna de las dos: 180°
    clc
    adc #2
    and #$03
    rts
queda:
    lda diag_mira
    rts
.endproc

; Le suman a dest_x / dest_y el byte con signo que trae A.
.proc sumar_a_dest_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc dest_x
    sta dest_x
    sep #$20
.a8
    rts
.endproc

.proc sumar_a_dest_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc dest_y
    sta dest_y
    sep #$20
.a8
    rts
.endproc

; --- el destello de pantalla -------------------------------------------------
; Un cuadro del destello de pantalla: `Flash::Update` de easyrpg, con la cuenta
; entera que sigue. El nivel va a
; escala 256 y baja en `nivel / cuadros_que_quedan` por cuadro, con el divisor
; del hardware; en el último cuadro cae a cero.
;
; RM2k dibuja el destello como un rectángulo del color con alfa encima de la
; pantalla compuesta. Acá es una transformación de CGRAM, como el tinte: cada
; canal de cada color de las tres paletas del mapa se acerca al del destello en
; `nivel / 31` del camino —`destellar_canal`—, y el resultado va a
; `pal_buf`, que `flush_video` sube en el vblank en lugar de la sombra.
; La sombra queda como está: es el mapa teñido sin destello, y cuando el
; destello se apaga vuelve a subirse tal cual.
;
; Pasar las tres paletas —doscientas y pico entradas, a más de cien ciclos
; cada una— no entra en un cuadro junto con todo lo demás: medido con
; `cuadros_perdidos`, se perdía uno por cuadro, y el resto de la escena
; quedaba treinta cuadros atrás de la referencia. Así que va en dos cuadros:
; con la resta impar se arman las tablas y se pasan el fondo y la capa de
; encima; con la resta par se pasan los sprites y se sube todo. Lo que se ve
; cambia cuadro por medio. Un tinte que cambie en el cuadro impar pisa
; `pal_buf` con la paleta recién teñida, y además no puede subirse sin
; destello; en ese cuadro se hace todo de una, y en el par se rehace el fondo.
;
; La ventana de mensaje y el cronómetro no reciben el destello, y tampoco allá:
; `Priority_Screen` es 90 contra 130 de la ventana y 140 del cronómetro.
.proc destello_tick
.a8
.i16
    rep #$20
.a16
    lda destello_nivel
    bne hay
    sep #$20
.a8
    rts
.a16
hay:
    sep #$20
.a8
    lda destello_resta
    beq apagar
    rep #$20
.a16
    lda destello_nivel
    sta WRDIVL                  ; el dividendo, de 16 bits
    sep #$20
.a8
    lda destello_resta
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    dec destello_resta          ; seis ciclos, y los nops que faltan
    nop
    nop
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda destello_nivel
    sec
    sbc RDDIVL
    sta destello_nivel
    sep #$20
.a8
    lda destello_resta
    beq apagar
    and #$01
    beq fase_par
    jsr tablas_de_destello
    jsr destellar_fondo
    lda tinte_listo
    beq listo                   ; lo normal: los sprites van el cuadro que viene
    jsr destellar_sprites
    bra subir
fase_par:
    lda tinte_listo
    beq sprites
    jsr destellar_fondo         ; el tinte nuevo pisó el fondo ya pasado
sprites:
    jsr destellar_sprites
subir:
    lda #1
    sta destello_listo
listo:
    rts
apagar:
    ; Se terminó: el nivel cae a cero y la sombra sin destello vuelve a CGRAM.
    stz destello_nivel
    stz destello_nivel + 1
    stz destello_resta
    lda #1
    sta tinte_listo
    rts
.endproc

; Las tres tablas del destello, una por canal: qué queda de cada valor de
; cinco bits con el nivel de este cuadro. Son bytes y no palabras ya corridas
; a su lugar del color, que le ahorrarían los corrimientos a
; `destellar_rango`: la RAM del banco 0 no daba para los 96 bytes de más.
.proc tablas_de_destello
.a8
.i16
    lda destello_nivel + 1      ; la parte entera del nivel, de 0 a 31
    sta dest_nivel
    rep #$20
.a16
    lda #.loword(dest_tab_r)
    sta temp
    sep #$20
.a8
    lda destello_rgb
    jsr una_tabla_de_destello
    rep #$20
.a16
    lda #.loword(dest_tab_g)
    sta temp
    sep #$20
.a8
    lda destello_rgb + 1
    jsr una_tabla_de_destello
    rep #$20
.a16
    lda #.loword(dest_tab_b)
    sta temp
    sep #$20
.a8
    lda destello_rgb + 2
    jmp una_tabla_de_destello
.endproc

; Una tabla: A es el canal del color del destello y `temp` apunta a la tabla.
; Es `destellar_canal`:
;
;     hacia >= canal:  canal + (hacia - canal) * nivel / 31
;     hacia <  canal:  canal - (canal - hacia) * nivel / 31
;
; La resta va siempre del lado positivo, porque el divisor no tiene signo.
.proc una_tabla_de_destello
.a8
.i16
    sta dest_hacia
    ; La fila del nivel en `prod31_tabla`, en temp + 2: temp es el puntero.
    lda dest_nivel
    rep #$20
.a16
    and #$001F
    asl a
    asl a
    asl a
    asl a
    asl a
    sta temp + 2
    sep #$20
.a8
    ldy #0
valor:
    tya                         ; el valor, de 0 a 31
    sta dest_v
    cmp dest_hacia
    bcc sube
    beq sube
    sec
    sbc dest_hacia
    jsr producto_sobre_31
    sta dest_d
    lda dest_v
    sec
    sbc dest_d
    bra guardar
sube:
    lda dest_hacia
    sec
    sbc dest_v
    jsr producto_sobre_31
    clc
    adc dest_v
guardar:
    sta (temp), y
    iny
    cpy #32
    bne valor
    rts

; A = A * nivel / 31, de `prod31_tabla`, que el conversor arma con la misma
; cuenta. Hasta el 2026-09-11 salía del multiplicador y el divisor, con sus
; esperas, y las 96 entradas de un cuadro impar costaban unas 45 líneas.
producto_sobre_31:
    rep #$20
.a16
    and #$001F
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    lda f:prod31_tabla, x
    rts
.endproc

; Las paletas del fondo y de la capa de encima, de la sombra a `pal_buf`
; pasadas por las tablas. Son las mismas entradas y cuentas que `subir_tinte`.
.proc destellar_fondo
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_MAP_CGRAM, x
    sta tin_count
    sep #$20
.a8
    ; Desde `CGRAM_BASE`, igual que `aplicar_tinte` y que `subir_paletas`: el
    ; fondo no arranca en la entrada 0 sino arriba de la ventana de mensaje.
    ; Acá decía 0, que era lo correcto hasta que la ventana se mudó a la paleta
    ; 0 y el fondo se corrió nueve entradas —ver el commit 5015868, que arregló
    ; los otros dos lugares y **se olvidó de éste**—. Con el 0, las últimas
    ; nueve entradas del fondo no se destellaban: se subían con lo que hubiera
    ; quedado en `pal_buf`, así que unos pocos tiles no se iluminaban y encima
    ; cambiaban de color. taro lo vio el 2026-09-08 en los relámpagos de la
    ; apertura —las vallas amarillas y negras, y los bordes del autotile 17 del
    ; ChipSet3—, que son el **primer** `FlashScreen` que corrió este port.
    ; Ninguna prueba lo cubría: la página de prueba de `destello` destella un
    ; sprite —`FlashSprite`—, nunca la pantalla, así que este camino no lo
    ; ejecutaba nadie.
    lda #CGRAM_BASE
    jsr destellar_rango
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ABOVE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda f:mapa_tabla + M_ABOVE_FIRST, x
    jmp destellar_rango
.endproc

; Y las de los sprites.
.proc destellar_sprites
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_SPRITE_CGRAM, x
    sta tin_count
    sep #$20
.a8
    lda #128
    jmp destellar_rango
.endproc

; `tin_count` colores desde la entrada A: cada uno se parte en sus tres
; canales, cada canal pasa por su tabla, y las tres palabras se juntan.
.proc destellar_rango
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por color
    tax
    lda tin_count
    asl a
    beq nada
    sta dest_fin
    txa
    clc
    adc dest_fin
    sta dest_fin
color:
    lda cgram_sombra, x
    sta temp                    ; el color, y en temp + 2 lo que se va armando
    and #$001F
    tay
    lda dest_tab_r, y           ; y el byte que sigue, que se enmascara
    and #$00FF
    sta temp + 2
    lda temp
    and #$03E0
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    tay
    lda dest_tab_g, y
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    ora temp + 2
    sta temp + 2
    lda temp
    xba                         ; el azul queda en los bits 2 a 6
    and #$007C
    lsr a
    lsr a
    tay
    lda dest_tab_b, y
    and #$00FF
    xba                         ; por 256, y dos más son los diez bits
    asl a
    asl a
    ora temp + 2
    sta pal_buf, x
    inx
    inx
    cpx dest_fin
    bne color
nada:
    sep #$20
.a8
    rts
.endproc

; Cuántos cuadros espera la página que pidió el pan: lo que le falta al eje que
; más falta, dividido por el paso y redondeado para arriba. Es `GetPanWait`.
; Devuelve el número en A de dieciséis bits.
;
; Lo que falta llega hasta quince celdas —3840 dieciseisavos— y el paso no pasa
; de 128, así que entran justo en el dividendo de dieciséis y el divisor de ocho
; del hardware.
.proc pan_cuadros
.a8
.i16
    rep #$20
.a16
    lda pan_dest_x
    sec
    sbc pan_x
    bpl falta_x
    eor #$FFFF
    inc a
falta_x:
    sta temp
    lda pan_dest_y
    sec
    sbc pan_y
    bpl falta_y
    eor #$FFFF
    inc a
falta_y:
    cmp temp
    bcs mayor
    lda temp
mayor:
    ; Redondear para arriba es sumarle el paso menos uno antes de dividir.
    clc
    adc pan_paso
    sec
    sbc #1
    sta WRDIVL                  ; el dividendo, en una escritura de dieciséis
    sep #$20
.a8
    lda pan_paso
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
    sep #$20
.a8
    rts
.endproc

; --- la cámara corrida sin el héroe ----------------------------------------
; `Game_Player::UpdatePan`: cada eje se acerca a su destino de a `pan_paso`
; dieciseisavos de pixel, sin pasarse. Y de paso se baja a pixeles enteros, que
; es lo que `follow_camera` suma: la división es **al piso** y con signo, que es
; lo que hace `Spriteset_Map` dividiendo `GetDisplayX()` por 16.
;
; Se guarda en pixeles en vez de dividir en cada uso porque `follow_camera`
; corre una vez por cuadro y esto también, pero acá la cuenta se hace una sola
; vez por eje.
.proc pan_tick
.a8
.i16
    rep #$20
.a16
    ldx #0                      ; el eje: 0 es la x, 2 la y
otro_eje:
    lda pan_dest_x, x
    sec
    sbc pan_x, x
    beq en_su_lugar             ; ya llegó
    bpl hacia_adelante
    ; Falta hacia atrás: se resta el paso, o lo que quede si es menos.
    eor #$FFFF
    inc a                       ; el valor absoluto de lo que falta
    cmp pan_paso
    bcc corto
    lda pan_paso
corto:
    eor #$FFFF
    inc a                       ; y de vuelta con signo
    bra sumar
hacia_adelante:
    cmp pan_paso
    bcc sumar
    lda pan_paso
sumar:
    clc
    adc pan_x, x
    sta pan_x, x
en_su_lugar:
    ; A pixeles: cuatro corrimientos aritméticos, que conservan el signo.
    lda pan_x, x
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    cmp #$8000
    ror a
    sta pan_px, x
    inx
    inx
    cpx #4
    bcc otro_eje
    sep #$20
.a8
    rts
.endproc

; --- la cámara -------------------------------------------------------------
; Sigue al héroe: lo deja en el centro de la pantalla salvo cerca de los bordes
; del mapa, donde se queda pegada para no mostrar el vacío de afuera.
;
; El scroll es por hardware, así que esto son dos restas y dos escrituras. No
; hay que redibujar nada: el mapa entero ya está en el tilemap.
; Un cuadro de la sacudida de pantalla: `Shake::Update` y `NextPosition` de
; easyrpg, con la cuenta entera que sigue:
;
;     amplitud = 1 + 2 * fuerza
;     nuevo    = -amplitud * seno[(resta * 4 * (velocidad + 2)) % 256] / 127
;     corte    = velocidad * amplitud / 8 + 1
;     posicion = clamp(nuevo, posicion - corte, posicion + corte)
;
; Los productos van por el multiplicador del hardware y la división por el
; divisor, que son los que ya usa `aplicar_tinte`. El seno es `seno_sacudida`,
; en el banco 0, con signo y a escala 127; el signo se saca antes de multiplicar
; y se vuelve a poner después, que es truncar hacia cero como hace `int`.
.proc sacudida_tick
.a8
.i16
    rep #$20
.a16
    lda sacudida_resta
    beq nada16
    dec a
    sta sacudida_resta
    bne sigue
    stz sacudida_pos            ; el último cuadro: la pantalla vuelve
nada16:
    sep #$20
.a8
    rts
.a16
sigue:
    ; t = (resta * 4 * (velocidad + 2)) % 256: alcanza con el byte bajo de
    ; resta * 4, porque lo que sobra de 256 se va igual.
    asl a
    asl a
    sep #$20
.a8
    sta WRMPYA
    lda sacudida_vel
    inc a
    inc a
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    lda sacudida_fuerza         ; mientras tanto, la amplitud
    asl a
    inc a
    sta sac_amp
    nop
    nop
    lda RDMPYL                  ; el byte bajo del producto es t
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:seno_sacudida, x      ; fuera del banco 0: ver `tabla_de_senos`
    sta sac_seno
    bpl positivo
    eor #$FF
    inc a                       ; |seno|
positivo:
    sta WRMPYA
    lda sac_amp
    sta WRMPYB                  ; |seno| * amplitud
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #127
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
    sta sac_nuevo               ; |nuevo|
    sep #$20
.a8
    lda sac_seno
    bmi con_signo               ; seno negativo: nuevo queda positivo
    rep #$20
.a16
    lda sac_nuevo
    eor #$FFFF
    inc a
    sta sac_nuevo               ; seno positivo: nuevo es negativo
    sep #$20
.a8
con_signo:
    ; corte = velocidad * amplitud / 8 + 1
    lda sacudida_vel
    sta WRMPYA
    lda sac_amp
    sta WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    lsr a
    lsr a
    lsr a
    inc a
    sta sac_corte
    lda sacudida_pos
    sec
    sbc sac_corte
    sta sac_lo
    lda sacudida_pos
    clc
    adc sac_corte
    sta sac_hi
    ; Los números son chicos —la amplitud no pasa de 19— así que el signo de
    ; la resta alcanza para comparar con signo.
    lda sac_nuevo
    sec
    sbc sac_lo
    bmi usar_lo
    lda sac_hi
    sec
    sbc sac_nuevo
    bmi usar_hi
    lda sac_nuevo
    bra guardar
usar_lo:
    lda sac_lo
    bra guardar
usar_hi:
    lda sac_hi
guardar:
    sta sacudida_pos
    sep #$20
.a8
    rts
.endproc

.proc follow_camera
.a8
.i16
    rep #$20
.a16
    lda hero_x
    clc
    adc #8                      ; el centro de su celda de 16x16
    sec
    sbc #128                    ; media pantalla de ancho
    clc
    adc pan_px                  ; y la cámara corrida sin el héroe
    bpl limite_x
    lda #0                      ; el héroe está cerca del borde izquierdo
limite_x:
    cmp cam_max_x
    bcc guarda_x
    lda cam_max_x
guarda_x:
    sta camara_x

    lda hero_y
    clc
    adc #8
    sec
    sbc #112                    ; media pantalla de alto
    clc
    adc pan_py
    bpl limite_y
    lda #0
limite_y:
    cmp cam_max_y
    bcc guarda_y
    lda cam_max_y
guarda_y:
    sta camara_y

    ; El PPU muestra la línea vofs+1 en el primer scanline, así que lo que se le
    ; escribe es siempre uno menos que dónde queremos mirar.
    dec a
    sta scroll_y
    ; Y lo que ve el dibujo: la cámara más la sacudida de pantalla.
    lda camara_x
    clc
    adc sacudida_pos
    sta pantalla_x
    sep #$20
.a8
    rts
.endproc

; --- la ventana móvil del mapa ---------------------------------------------
; El tilemap del PPU son 64x32 celdas y los mapas del juego llegan a 1000x80:
; el mapa entero nunca está en la VRAM. Lo que hay es una ventana que se trata
; como un toro —la celda (mx,my) vive siempre en la ranura (mx mod 64, my mod
; 32)— y que se mantiene reescribiendo la columna o la fila que acaba de entrar
; en pantalla. La que sale queda 32 columnas o 4 filas afuera, así que nadie la
; ve mientras se la pisa.
;
; El scroll por hardware hace la vuelta solo: el registro son 10 bits, o sea
; 1024 pixeles, y 1024 es múltiplo de los 512 que mide la ventana a lo ancho.
; Se le escribe la posición de la cámara tal cual y cae donde tiene que caer.
;
; De la ROM no sale un tilemap sino una grilla de bloques: la celda de 16x16 de
; RM2k, que es la unidad con la que el juego fue dibujado y que se repite
; muchísimo. El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa
; de encima y su pasabilidad, todo junto. Guardarlo así es lo que hace que el
; mapa más grande pase de 175 KB —más que la ROM entera— a 40.

; La grilla llega a 40 KB y no entra en un banco, así que se recorre con un
; puntero de 24 bits. En LoROM un banco sólo tiene sus 32 K de arriba: pasarse
; del $FFFF no lleva al $0000 del banco siguiente sino a su $8000, y estas dos
; rutinas son las únicas que saben eso.
.proc ptr_mas
.a16
.i16
    clc
    adc celdas_ptr
    sta celdas_ptr
    bcc listo
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    inc a
    sta celdas_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

.proc ptr_menos
.a16
.i16
    eor #$FFFF                  ; restar es sumar el complemento
    sec
    adc celdas_ptr
    cmp #$8000
    bcs guarda                  ; sigue dentro de la mitad alta del banco
    clc
    adc #$8000
    sta celdas_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    dec a
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
guarda:
    sta celdas_ptr
    rts
.endproc

.proc ptr_desde_celdas
.a16
.i16
    lda celdas
    sta celdas_ptr
    sep #$20
.a8
    lda celdas + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_celdas
.a16
.i16
    lda celdas_ptr
    sta celdas
    sep #$20
.a8
    lda celdas_ptr + 2
    sta celdas + 2
    rep #$20
.a16
    rts
.endproc

; Arma la columna X del mapa —en celdas de 8x8— y deja en col_addr dónde va.
;
; Se llenan las 32 filas de la ventana, no las 29 que se ven. La ranura de cada
; fila es fija, fila mod 32, así que escribir de más no puede pisar nada que se
; esté mirando, y ahorra tener que llevar la cuenta de qué parte de la columna
; ya estaba bien.
.proc build_column
.a16
.i16
    stz col_addr
    cpx mapa_cw
    bcc dentro
    rts                         ; más allá del borde: no hay nada que dibujar
dentro:

    ; Dónde cae en la VRAM. La ventana son dos pantallas de 32x32 pegadas, y la
    ; de la derecha vive 1024 palabras más adelante, no al lado.
    txa
    and #(WINDOW_COLS - 1)
    sta temp
    and #$001F
    clc
    adc #VRAM_MAP
    sta col_addr
    lda temp
    and #$0020
    beq izquierda
    lda col_addr
    clc
    adc #1024
    sta col_addr
izquierda:

    ; El bloque mide 16x16: la columna de bloques es la mitad de la de celdas y
    ; el bit que sobra dice cuál de sus dos mitades toca.
    txa
    and #$0001
    asl a                       ; 0 la mitad izquierda, 2 la derecha
    sta tira_ofs
    txa
    lsr a
    asl a                       ; la columna de bloques, en bytes
    sta temp

    jsr ptr_desde_celdas
    lda temp
    jsr ptr_mas

    ; La fila de arriba de la ventana decide la ranura donde arranca y en qué
    ; mitad del bloque cae.
    lda win_row
    and #$0001
    beq desde_arriba
    lda tira_ofs
    ora #$0004                  ; arranca por la mitad de abajo del bloque
    sta tira_ofs
desde_arriba:
    lda win_row
    and #(WINDOW_ROWS - 1)
    asl a
    tax                         ; la ranura, en bytes

    ; Cuántas filas hay por delante: la ventana entera, o lo que quede de mapa.
    lda mapa_ch
    sec
    sbc win_row
    cmp #WINDOW_ROWS
    bcc corta
    lda #WINDOW_ROWS
corta:
    sta tira_resta

    ; El índice del bloque va en Y y la ranura en X, y no al revés: la tabla de
    ; bloques ya no vive en el banco 0 —con varios mapas no entra— así que se
    ; lee con un puntero de 24 bits, y ese modo sólo indexa por Y.
fila:
    lda [celdas_ptr]            ; el bloque de esta celda
    asl a
    asl a
    asl a
    asl a                       ; su registro mide 16 bytes
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_col, x             ; la celda del fondo
    lda [bloques8_ptr], y
    sta tira_col2, x            ; y la de la capa de encima

    inx
    inx
    txa
    and #(WINDOW_ROWS * 2 - 1)  ; la ventana da la vuelta
    tax

    lda tira_ofs
    eor #$0004                  ; la otra mitad del bloque
    sta tira_ofs
    and #$0004
    bne misma                   ; sigue en el mismo bloque
    lda tira_paso_col
    jsr ptr_mas                 ; a la fila de bloques siguiente
misma:
    dec tira_resta
    bne fila
    rts
.endproc

; La imagen espejada de la anterior: arma la fila X del mapa en tira_row. Lo
; único que cambia es cuál de los dos ejes alterna dentro del bloque y cuánto
; avanza el puntero al pasar de uno al siguiente.
.proc build_row
.a16
.i16
    stz row_addr
    cpx mapa_ch
    bcc dentro
    rts                         ; más allá del borde de abajo
dentro:
    txa
    and #(WINDOW_ROWS - 1)
    asl a
    asl a
    asl a
    asl a
    asl a                       ; cada fila de la pantalla mide 32 palabras
    clc
    adc #VRAM_MAP
    sta row_addr

    txa
    and #$0001
    asl a
    asl a                       ; 0 la mitad de arriba del bloque, 4 la de abajo
    sta tira_ofs
    txa
    lsr a
    sta temp                    ; la fila de bloques que entra

    ; El ancla apunta a la fila de bloques de arriba de la ventana; la que entra
    ; puede estar hasta catorce filas más abajo, si es la del pie de la pantalla.
    jsr ptr_desde_celdas
    lda temp
    sec
    sbc win_block
    beq en_la_fila
    tax
baja:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne baja
en_la_fila:
    ; La fila arranca MARGEN_COLS columnas antes de la ventana, que es el mismo
    ; rango que cargan `fill_window` y `stream_map`: [win_col - MARGEN_COLS,
    ; win_col + 60). Si arrancara en win_col, las cuatro últimas columnas de la
    ; fila —win_col + 60 a 63— pisarían en el toro las ranuras del margen de la
    ; izquierda, y eso se vio: la esquina de la pantalla del mapa 2 mostraba
    ; columnas de 64 más adelante. Las columnas negativas y las que caen más
    ; allá del borde derecho van vacías, como en `build_column`.
    lda win_col
    sec
    sbc #MARGEN_COLS
    sta fila_col
    and #(WINDOW_COLS - 1)
    asl a
    tax                         ; la ranura de la primera columna, en bytes
    lda #WINDOW_COLS
    sta tira_total
vacias_izq:
    lda fila_col
    bpl con_mapa
    stz tira_row, x
    stz tira_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    inc fila_col
    dec tira_total
    bra vacias_izq
con_mapa:
    lda fila_col
    and #$0001
    beq desde_izquierda
    lda tira_ofs
    ora #$0002
    sta tira_ofs
desde_izquierda:
    lda fila_col
    lsr a
    asl a                       ; la columna de bloques de la izquierda, en bytes
    jsr ptr_mas
    lda mapa_cw
    sec
    sbc fila_col
    cmp tira_total
    bcc corta
    lda tira_total
corta:
    sta tira_resta
    lda tira_resta
    beq vacias_der              ; toda la fila cae fuera del mapa
columna:
    lda [celdas_ptr]
    asl a
    asl a
    asl a
    asl a
    clc
    adc tira_ofs
    tay
    lda [bloques_ptr], y
    sta tira_row, x
    lda [bloques8_ptr], y
    sta tira_row2, x

    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax

    lda tira_ofs
    eor #$0002                  ; la otra mitad del bloque, ahora a lo ancho
    sta tira_ofs
    and #$0002
    bne mismo
    lda #2
    jsr ptr_mas                 ; al bloque de al lado
mismo:
    dec tira_total
    dec tira_resta
    bne columna
vacias_der:
    lda tira_total
    beq listo
    stz tira_row, x
    stz tira_row2, x
    inx
    inx
    txa
    and #(WINDOW_COLS * 2 - 1)
    tax
    dec tira_total
    bra vacias_der
listo:
    rts
.endproc

; Qué hay que redibujar este cuadro. La cámara se mueve como mucho dos pixeles
; por vuelta y sólo por un eje, así que cruza a lo sumo el borde de una celda:
; alcanza con mirar si la esquina de la ventana cambió de celda. Si algún día
; la cámara pudiera saltar —un teleport, un cambio de mapa— eso no es un ajuste
; de esta rutina sino un fill_window entero, con la pantalla apagada.
.proc stream_map
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr

    lda camara_y
    lsr a
    lsr a
    lsr a
    cmp win_row
    beq sin_fila
    bcs bajando
    tax                         ; sube: entra la fila de arriba de la pantalla
    bra guarda_fila
bajando:
    pha
    clc
    adc #(VIEW_ROWS - 1)
    tax                         ; baja: entra la del pie
    pla
guarda_fila:
    sta win_row

    ; El ancla de bloques sigue a la fila de arriba de la ventana.
    lsr a
    cmp win_block
    beq mismo_bloque
    pha
    bcs baja_bloque
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_menos
    jsr ptr_a_celdas
    bra guarda_bloque
baja_bloque:
    jsr ptr_desde_celdas
    lda tira_paso_col
    jsr ptr_mas
    jsr ptr_a_celdas
guarda_bloque:
    pla
    sta win_block
mismo_bloque:
    jsr build_row               ; X sigue siendo la fila que entra

sin_fila:
    lda camara_x
    lsr a
    lsr a
    lsr a
    cmp win_col
    beq sin_columna
    bcs derecha
    pha
    sec
    sbc #MARGEN_COLS            ; sube: entra la del margen de la izquierda
    tax
    pla
    bra guarda_col
derecha:
    pha
    clc
    adc #(VIEW_COLS - 1 + MARGEN_COLS)
    tax
    pla
guarda_col:
    sta win_col
    jsr build_column
sin_columna:
    sep #$20
.a8
    rts
.endproc

; Llena la ventana entera desde cero: las 64 columnas, una por una. Va con la
; pantalla apagada, al arrancar, y es el único momento en que se escribe tanto
; tilemap de una vez.
; Los dos tilemaps del mapa —el fondo y la capa de encima— en cero, y las
; cuatro tiras con que se llenan.
;
; `build_column` y `build_row` **saltean** lo que cae afuera del mapa, y las
; tiras sólo se escriben hasta donde el mapa llega. En el arranque eso deja
; ceros, que es la celda vacía y se ve negro, porque el reset limpió la VRAM
; entera. Después de un teletransporte o de una puerta, en cambio, dejaba lo
; que hubiera puesto el mapa anterior: lo destapa `ShakeScreen` contra el
; borde, que corre la pantalla más allá de la primera columna. Lo encontró el
; paso 9e, cuando los casos de `sacudir-borde` y `tram-viaje` pasaron a
; llegar a su mapa con un `Teleport` en vez de arrancar ahí.
;
; Corre con la pantalla en blanking forzado, que es como corre toda carga de
; mapa: son dos DMA de 4 KB a la VRAM.
.proc limpiar_tilemaps
.a8
.i16
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    ldx #VRAM_MAP
    jsr cero_a_tilemap
    ldx #VRAM_ABOVE_MAP
    jsr cero_a_tilemap
    ldx #$0000
tiras:
    stz tira_col, x             ; las cuatro son contiguas: ver su .res
    inx
    cpx #(WINDOW_ROWS * 2 * 2 + WINDOW_COLS * 2 * 2)
    bne tiras
    rts
.endproc

; Un tilemap de dos pantallas de 32x32, desde la palabra X de la VRAM, en cero.
.proc cero_a_tilemap
.a8
.i16
    stx VMADDL
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #(32 * 32 * 2 * 2)      ; dos pantallas, de a palabras
    stx DAS0L
    lda #$09                    ; dos registros, de a palabras, fuente fija
    sta DMAP0
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

.proc fill_window
.a8
.i16
    rep #$20
.a16
    stz col_addr
    stz row_addr
    lda mapa_ancho
    asl a
    sta tira_paso_col           ; lo que mide una fila de bloques, en bytes

    lda camara_x
    lsr a
    lsr a
    lsr a
    sta win_col
    lda camara_y
    lsr a
    lsr a
    lsr a
    sta win_row
    lsr a
    sta win_block

    ; celdas = la grilla del mapa + win_block filas. Se suma de a una en vez de
    ; multiplicar: pasa una sola vez y el 65816 no multiplica.
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_MAP_CELDAS, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_CELDAS + 2, x
    sta celdas_ptr + 2
    rep #$20
.a16
    ldx win_block
    beq sin_filas
suma:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne suma
sin_filas:
    jsr ptr_a_celdas

    lda win_col
    sec
    sbc #MARGEN_COLS            ; con el margen de la izquierda; las columnas
    sta temp + 2                ; negativas las saltea `build_column`
    ldy #WINDOW_COLS
columna:
    phy
    ldx temp + 2
    jsr build_column
    sep #$20
.a8
    jsr push_strips
    rep #$20
.a16
    inc temp + 2
    ply
    dey
    bne columna
    sep #$20
.a8
    rts
.endproc

; `hdma_mascara` y `tabla_fila_buf` **vivían acá** y bajaron a RODATA el
; 2026-09-13, las dos por separado y el mismo día: ver allá abajo. El HDMA lee
; de donde diga `A1B3`, así que no necesita banco 0, y el compositor la indexa
; con X, que sí tiene modo largo.

; --- la ventana de mensaje -------------------------------------------------
; Sus tiles y su paleta se suben una sola vez, con la pantalla apagada, igual
; que los de la capa de encima. Viven en el banco que sigue al de encima, y BG2
; los alcanza con la misma base: del índice 0 al 255 cae el de encima y del 256
; al 511 la ventana. Por eso el conversor ya emitió las celdas con ese
; corrimiento sumado.
;
; Su paleta es la **0**, o sea las entradas que están debajo del fondo, y la
; sube `cargar_mapa_sin_eventos` junto con el color de fondo de la pantalla.
.proc load_ventana
.a8
.i16
    ldx mapa_ofs
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(ventana_tiles)
    sta A1T0L
    lda #(VENTANA_TILES * 32)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_tiles
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; La paleta de la ventana no se sube acá: es la **0**, o sea las entradas
    ; que `cargar_mapa_sin_eventos` ya subió junto con el color de fondo. Antes
    ; iba flotando debajo de la capa de encima más baja de la ROM y se subía
    ; por su cuenta; con eso el fondo de todos los mapas quedaba apretado
    ; abajo de ella —47 colores— aunque tuvieran media CGRAM libre arriba.

    ; El tilemap propio y las tablas del HDMA, que son de este mapa: la ventana
    ; vive en un lugar de la VRAM que depende del reparto.
    jsr estampar_ventana
    jsr armar_hdma
    rts
.endproc

; Escribe el tilemap propio de la ventana: 320 celdas seguidas, un solo DMA.
;
; Acá está toda la diferencia con lo que había antes. La ventana ya no se
; estampa en el tilemap del mapa —que se scrollea— sino en uno suyo, de 32x32,
; que no comparte con nadie. Como es propio, sus diez filas de 32 celdas son
; 320 palabras contiguas: no hay tramos, ni envoltura, ni columna 32 que
; esquivar. Y como nadie más lo toca, esto corre **una sola vez por mapa**,
; desde `load_ventana` y con la pantalla ya apagada.
;
; Quién lo muestra y dónde lo decide el HDMA; ver `armar_hdma`.
.proc estampar_ventana
.a8
.i16
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP, x
    sta VMADDL
    lda #.loword(ventana_celdas)
    sta A1T0L
    lda #(VENTANA_FILAS * VENTANA_COLS * 2)
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_celdas
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Deja armadas las dos tablas del HDMA y programa sus canales. Corre una vez por
; mapa, junto con el resto de la carga.
;
; Lo que el HDMA consigue, y que ninguna cantidad de estampado conseguía: BG2
; cambia de tilemap y de scroll **a mitad de cuadro**. De la línea 0 a la 143
; sigue siendo la capa de encima del mapa, con la cámara; de la 144 a la 223 es
; el tilemap propio de la ventana, con el scroll clavado. Por eso la ventana no
; se mueve aunque la cámara sí, y por eso no hay una sola escritura de VRAM
; mientras un mensaje está en pantalla.
;
; Las dos primeras entradas llevan justo lo que `flush_video` ya escribía en los
; registros, así que arriba de la línea 144 no cambia nada. Van en dos tramos
; porque el contador de líneas de una entrada es de 7 bits y 144 no entra.
.proc armar_hdma
.a8
.i16
    lda #127
    sta hdma_sc
    sta hdma_ofs
    lda #(VENTANA_LINEA - 127)
    sta hdma_sc + 2
    sta hdma_ofs + 5
    lda #(LINEAS - VENTANA_LINEA)
    sta hdma_sc + 4
    sta hdma_ofs + 10

    ; El tilemap del mapa arriba y el de la ventana abajo. BG2SC lleva la
    ; dirección en el byte alto; el tamaño de la ventana es 0, que es 32x32.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta hdma_sc + 1
    sta hdma_sc + 3
    ldx mapa_ofs
    lda f:mapa_tabla + M_VRAM_VENTANA_MAP + 1, x
    sta hdma_sc + 5
    stz hdma_sc + 6             ; fin de tabla

    ; Y el scroll clavado de las líneas de la ventana. Los dos tramos de arriba
    ; los llena `flush_video` con la cámara de cada cuadro.
    stz hdma_ofs + 11
    stz hdma_ofs + 12
    lda #<VENTANA_VOFS
    sta hdma_ofs + 13
    lda #>VENTANA_VOFS
    sta hdma_ofs + 14
    stz hdma_ofs + 15           ; fin de tabla

    lda #$00                    ; un registro, una escritura por tramo
    sta DMAP1
    lda #<BG2SC
    sta BBAD1
    ldx #hdma_sc
    stx A1T1L
    stz A1B1                    ; las tablas viven en el banco 0

    lda #$03                    ; dos registros, dos escrituras cada uno, que
    sta DMAP2                   ; es lo que piden BG2HOFS y BG2VOFS
    lda #<BG2HOFS
    sta BBAD2
    ldx #hdma_ofs
    stx A1T2L
    stz A1B2

    ; Y el tercer canal esconde los objetos debajo de la ventana. En RM2k la
    ; ventana de mensaje tapa todo —`Priority_Window` es 130 y los personajes
    ; van por debajo—, pero acá es BG2 con prioridad 1, y un evento marcado
    ; "above" va en objetos con prioridad 2, que en el modo 3 queda *adelante*
    ; de BG2: se veía a través de la ventana. Lo cobró la tanda con la puerta
    ; del mapa 7 apenas los eventos dibujados con un tile pasaron a sprites.
    ; La máscara es la ventana 1 del PPU, de punta a punta, prendida para los
    ; objetos sólo en las líneas de la ventana de mensaje: `hdma_mascara`,
    ; que no cambia nunca y vive en la ROM.
    lda #$00
    sta DMAP3
    lda #<WOBJSEL
    sta BBAD3
    ldx #.loword(hdma_mascara)
    stx A1T3L
    lda #^hdma_mascara          ; ya no es el banco 0: vive en RODATA
    sta A1B3
    rts
.endproc

; --- el compositor de texto ------------------------------------------------
;
; Lo que hace que esto entre en un 65816. RM2k dibuja cada glifo usando sus
; pixeles como **máscara** sobre un bloque de 16x16 del System, y leído así
; pide muestrear el bloque pixel por pixel. Medido, no hace falta: cada fila
; del glifo toma un solo color —el degradé es vertical— y la sombra es un color
; plano. O sea que todo el color se reduce a doce bytes, `fuente_color`, más
; `FUENTE_SOMBRA`. Es la medición que volvió barato esto.
;
; El área de texto son 30 celdas de ancho por 8 de alto y sus 240 tiles **no
; están deduplicados**: cada celda tiene el suyo, fijo, así que componer es
; escribir un buffer y subirlo. Se hace de a un renglón —dos filas de celda, 60
; tiles, 1920 bytes— y se sube en el vblank siguiente.
;
; Un renglón se ceba con el fondo de la ventana antes de escribirle el texto,
; porque los glifos no se dibujan sobre negro sino sobre el degradé del skin.
; Eso es un DMA de la ROM a la RAM, que el DMA normal no sabe hacer: va por la
; ventana que la WRAM tiene en el bus B, o sea WMADD más $2180.

; Cuántos caracteres por vuelta del lazo. El número está **medido**, no
; elegido: componiendo el mensaje de `snes-anclada` sobre el mapa 6, con 5 no se
; pierde un cuadro, con 6 tampoco y con 8 se pierde uno. Va en 5 y no en 7 por
; margen, porque la vuelta cuesta distinto en cada mapa —el streaming del fondo,
; los NPCs, la música— y perder cuadros no se ve mirando: lo que pasa es que el
; héroe camina más lento que en la referencia.
;
; Lo que cuesta: el mensaje de tres renglones y 51 caracteres de `snes-ventana`
; tarda unos 15 cuadros en aparecer, y uno de cuatro renglones llenos tardaría
; unos 36. Es un cuarto de segundo, que en RM2k tampoco desentona: allá la
; ventana se abre con una animación.
MSG_CHARS = 5

; Dónde empieza el texto adentro de la ventana, en pixeles. Es el `border_x` de
; `Window`, el mismo que usa `tools/port/ventana.py`.
VENTANA_BORDE = 8

; La fila del glifo cae dos pixeles abajo del borde de la celda, y eso no
; depende del renglón: los cuatro empiezan en 10, 26, 42 y 58, que módulo 8 dan
; todos 2. Por eso un glifo de doce filas entra siempre en las mismas dos filas
; de celda y el buffer puede ser de dos.
TEXTO_OFS_Y = 2

; Un byte más adelante en el bloque de textos, cruzando la ventana de banco.
;
; `msg_ptr` es un puntero largo pero el compositor lo avanzaba con un `inc` de
; dieciséis bits, así que al pasar de $FFFF volvía al $0000 del **mismo** banco.
; En LoROM ahí no hay ROM: lo que sigue a $FFFF es el $8000 del banco siguiente,
; que es lo que ya sabían `ptr_mas` y `msg_empezar`.
;
; No es teórico y no bastaba con arreglar `msg_empezar`: el bloque de textos de
; `demo-ciudad` mide 56 KB, o sea que cruza, y **un cuadro cuyos bytes caen
; encima del borde** empieza bien y sigue leyendo basura. Es la cinemática de
; los Neon Vipers del mapa 14: de la basura salía un largo de renglón de 76
; caracteres y con él la pantalla hecha basura, por el camino que el tope de
; `mensaje_tick` ahora corta.
.proc msg_ptr_sig
.a16
.i16
    inc msg_ptr
    bne listo
    lda #$8000
    sta msg_ptr
    sep #$20
.a8
    inc msg_ptr + 2
    rep #$20
.a16
listo:
    rts
.endproc

; Arranca un mensaje: deja el puntero en su primer renglón y el compositor en
; marcha. La ventana no aparece hasta que termine.
;
; **A trae el desplazamiento del cuadro dentro de `mensajes`, en 16 bits**, y
; hay que sumárselo a un puntero largo cruzando bancos: ver el lazo de abajo y
; `msg_ptr_sig`, que es la misma cuenta para avanzar de a un byte.
.proc msg_empezar
.a16
.i16
    ; El desplazamiento es de dieciséis bits y el bloque de textos puede medir
    ; hasta 64 KB, o sea **más que la ventana de un banco de LoROM**: con los
    ; 29 mapas de `demo-ciudad` son 48972 bytes y arranca en $46:8000, así que
    ; desde el desplazamiento $8000 la suma se pasa de $FFFF. Lo que sigue a
    ; $FFFF no es el $0000 del banco que viene sino su $8000, que es lo mismo
    ; que ya sabía `ptr_mas` para la grilla del mapa; acá se sumaba de a
    ; dieciséis bits y el acarreo se perdía, así que **todo cuadro de texto
    ; pasado el primer banco leía de otro lado**: la cabecera y los largos de
    ; renglón salían de cualquier cosa. El lazo suma un banco por vuelta porque
    ; un bloque de 64 KB cruza hasta dos veces.
    phx
    ldx #^mensajes
    clc
    adc #.loword(mensajes)
otro_banco:
    bcc en_el_banco
    inx
    clc
    adc #$8000
    bra otro_banco
en_el_banco:
    sta msg_ptr
    sep #$20
.a8
    txa
    sta msg_ptr + 2
    rep #$20
.a16
    plx
    ; La cola de escapes arranca limpia antes de leer la cabecera: una pausa de
    ; basura ahí dejaría la página frenada para siempre.
    lda #0
    sta f:FAR_MSG_PAUSA         ; `stz` no tiene modo largo
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ldy #0
    lda [msg_ptr], y            ; la cabecera: los renglones en los tres bits
    sta msg_lineas              ; de abajo, el autocierre en el 3 y las pausas
                                ; en el nibble de arriba. Se guarda entera y la
                                ; enmascara quien la lea; un byte más en el
                                ; banco 0 es justo lo que no hay.
    and #CABECERA_AUTOCIERRE
    sta f:FAR_MSG_AUTO
    lda msg_lineas
    lsr
    lsr
    lsr
    lsr                         ; cuántas pausas trae
    beq sin_pausa
    ; Y cuánto duran: `CUADROS_DE_PAUSA` cada una, que son 61 y no 60. El
    ; producto va en 16 bits porque quince pausas son 915 cuadros, así que lo
    ; hace el hardware, como el tinte.
    sta WRMPYA
    lda #CUADROS_DE_PAUSA
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta f:FAR_MSG_PAUSA
    sep #$20
.a8
sin_pausa:
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
    stz msg_linea
    stz msg_cebada
    stz msg_subir
    lda #1
    sta msg_estado
    rts
.endproc

; Un cuadro del compositor, desde el lazo principal.
.proc mensaje_tick
.a8
.i16
    lda msg_estado
    cmp #1
    beq trabajando
    rts
trabajando:
    lda msg_subir
    beq sin_subir
    rts                         ; el renglón anterior todavía no subió
sin_subir:
    lda msg_cebada
    bne componiendo

    ; Renglón nuevo: se le copia el fondo y se lee su largo. Los renglones que
    ; el mensaje no trae igual se ceban y se suben: en la VRAM está el texto del
    ; mensaje anterior y hay que taparlo.
    jsr cebar_linea
    stz msg_largo
    lda msg_lineas
    and #CABECERA_LINEAS        ; la cabecera trae además la cola de escapes
    sta temp
    lda msg_linea
    cmp temp
    bcs vacio
    ldy #0
    lda [msg_ptr], y
    sta msg_largo
    rep #$20
.a16
    jsr msg_ptr_sig
    sep #$20
.a8
vacio:
    stz msg_col
    lda #1
    sta msg_cebada

componiendo:
    ldx #MSG_CHARS
otro:
    lda msg_col
    cmp msg_largo
    bcs fin_linea
    ldy #0
    lda [msg_ptr], y
    rep #$20
.a16
    and #$00FF
    sta comp_char
    lda msg_col
    and #$00FF
    sta comp_col
    jsr msg_ptr_sig
    sep #$20
.a8
    inc msg_col
    ; El tope de la columna. El byte se consume igual —si no, el puntero
    ; quedaría desfasado y el renglón que sigue leería del medio de éste— pero
    ; no se dibuja: `componer_char` escribe en `texto_buf` con un desplazamiento
    ; que sale de la columna, y a partir de la 39 eso cae **afuera** del buffer,
    ; encima del HDMA de la ventana, de la imagen de OAM y de `vq_n`. Ver el
    ; comentario de `componer_char`, más abajo.
    ;
    ; Y el tope va acá aunque el conversor no emita nunca un renglón más largo,
    ; porque **el síntoma no señala al texto**: con `vq_n` pisado, `vram_drenar`
    ; sube bloques de 128 bytes a direcciones cualquiera de la VRAM, así que un
    ; largo de renglón malo se ve como la pantalla entera hecha basura unos
    ; cuadros más tarde y en otro mapa.
    lda comp_col
    cmp #MENSAJE_COLS
    bcs sin_dibujar
    phx
    jsr componer_char
    plx
sin_dibujar:
    dex
    bne otro
    rts

fin_linea:
    ; El renglón está listo: se sube en el vblank que viene y se pasa al que
    ; sigue. El fondo del próximo no se ceba en este mismo cuadro a propósito:
    ; el buffer todavía tiene lo que hay que subir.
    lda #1
    sta msg_subir
    stz msg_cebada
    inc msg_linea
    lda msg_linea
    cmp #VENTANA_LINEAS_TEXTO
    bcc mas
    lda #2
    sta msg_estado              ; ya está: `flush_video` prende el HDMA
mas:
    rts
.endproc

; Copia al buffer el fondo de las dos filas de celda del renglón en curso. Es
; la única forma de que los glifos queden sobre el degradé del skin y no sobre
; negro, y va por DMA de la ROM a la RAM.
.proc cebar_linea
.a8
.i16
    rep #$20
.a16
    ; El destino: siempre el principio del buffer.
    lda #.loword(texto_buf)
    sta WMADDL
    sep #$20
.a8
    stz WMADDH                  ; el buffer vive en el banco 0 de la WRAM

    rep #$20
.a16
    ; El origen: dos filas de celda por renglón, 60 tiles de 32 bytes.
    lda msg_linea
    and #$00FF
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; renglón * 64
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; renglón * 60, o sea los tiles que ya pasaron
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32 bytes cada uno
    clc
    adc #.loword(ventana_fondo)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    lda #^ventana_fondo
    sta A1B0
    lda #$00                    ; un registro, de a un byte
    sta DMAP0
    lda #<WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Sube el renglón compuesto al banco de tiles de la ventana. Va en el vblank,
; desde `flush_video`, y son 1920 bytes de un solo DMA.
.proc subir_linea
.a8
.i16
    stz msg_subir
    lda #$80
    sta VMAIN
    ldx mapa_ofs
    rep #$20
.a16
    ; El tile donde arranca este renglón, en palabras de VRAM. El renglón que
    ; hay que subir es el anterior: `mensaje_tick` ya pasó al siguiente.
    lda msg_linea
    and #$00FF
    dec a
    sta temp
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc temp
    sbc temp
    sbc temp
    sbc temp                    ; renglón * 60 tiles
    clc
    adc #VENTANA_TEXTO_BASE
    asl a
    asl a
    asl a
    asl a                       ; por 16 palabras cada tile
    clc
    adc f:mapa_tabla + M_VRAM_VENTANA, x
    sta VMADDL
    lda #.loword(texto_buf)
    sta A1T0L
    lda #TEXTO_BUF_BYTES
    sta DAS0L
    sep #$20
.a8
    stz A1B0                    ; el buffer vive en el banco 0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; Un caracter, desde sus datos ya compuestos: `fuente_pre0` a `fuente_pre3`,
; una tabla por fase, que arma `fuente_prerender` en el conversor. Por cada
; una de las FUENTE_PRE_FILAS filas y cada una de las dos celdas que puede
; pisar vienen tres palabras —qué se conserva del buffer, y qué se prende en
; los planos 0-1 y en los 2-3—, así que pintar es leer, enmascarar y
; escribir. Una celda que no toca nada viene con la máscara en $FFFF y se
; saltea.
;
; **La columna la topa `mensaje_tick`**, no esto: acá `comp_col` ya llegó como
; buena y el desplazamiento que sale de ella se usa sin mirar. El tope está allá
; porque el byte hay que consumirlo igual aunque no se dibuje.
;
; Hasta el 2026-09-11 esto pintaba cada fila dos veces —la sombra y después
; el glifo, con una rutina `pintar` que armaba las máscaras en cada llamada—
; y corría la fila de a un bit hasta su fase: unas 25 líneas por carácter, y
; con MSG_CHARS en 5 era lo que más costaba del cuadro mientras se armaba un
; mensaje. taro lo notó en la apertura, con lluvia. El resultado es el mismo
; byte por byte: el orden de `Font::Render` —la sombra de una fila la pisa el
; glifo de la siguiente— ya viene resuelto en las tablas.
.proc componer_char
.a8
.i16
    lda comp_char
    sta WRMPYA
    lda #FUENTE_PRE_CHAR
    sta WRMPYB                  ; arranca: lo que sigue le da los ocho ciclos

    ; Dónde cae: x = borde + 6 por columna, y de ahí la celda y la fase.
    rep #$20
.a16
    lda comp_col
    sta temp
    asl a
    clc
    adc temp
    asl a                       ; por 6
    clc
    adc #VENTANA_BORDE
    sta temp                    ; x adentro de la ventana
    and #$0007
    sta comp_fase               ; 0, 2, 4 o 6
    lda temp
    lsr a
    lsr a
    lsr a
    sec
    sbc #VENTANA_TEXTO_COL      ; la columna de celda, contada desde el texto
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 32 bytes de tile
    sta comp_base

    ; Sus datos: la tabla de su fase, más el carácter por FUENTE_PRE_CHAR.
    ldx comp_fase
    lda f:fuente_pre_lo, x
    clc
    adc RDMPYL
    sta comp_glifo
    sep #$20
.a8
    lda f:fuente_pre_bk, x
    sta comp_glifo + 2

    ldy #0
    lda #(TEXTO_OFS_Y * 2)
    sta comp_fila               ; de a dos: es el índice en `tabla_fila_buf`
fila:
    rep #$20
.a16
    lda comp_fila
    and #$00FF
    tax
    lda f:tabla_fila_buf, x
    clc
    adc comp_base
    tax                         ; X = el byte del buffer donde arranca la fila
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_primera
    sta comp_and
    iny
    iny
    lda texto_buf, x            ; planos 0 y 1 de la primera celda
    and comp_and
    ora [comp_glifo], y
    sta texto_buf, x
    iny
    iny
    lda texto_buf + 16, x       ; planos 2 y 3
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 16, x
    iny
    iny
    bra segunda
sin_primera:
    tya
    clc
    adc #6
    tay
segunda:
    lda [comp_glifo], y
    cmp #$FFFF
    beq sin_segunda
    sta comp_and
    iny
    iny
    lda texto_buf + 32, x       ; la celda de al lado, un tile más adelante
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 32, x
    iny
    iny
    lda texto_buf + 48, x
    and comp_and
    ora [comp_glifo], y
    sta texto_buf + 48, x
    iny
    iny
    bra otra_fila
sin_segunda:
    tya
    clc
    adc #6
    tay
otra_fila:
    sep #$20
.a8
    lda comp_fila
    clc
    adc #2
    sta comp_fila
    cmp #((TEXTO_OFS_Y + FUENTE_PRE_FILAS) * 2)
    bcc fila
    rts
.endproc

; --- lo que va sí o sí dentro del vblank -----------------------------------
; OAM sólo se puede escribir mientras el PPU no la está leyendo, o sea en el
; vblank. Armarla lleva su tiempo —con treinta y pico de personajes, más de un
; milisegundo— así que armarla y subirla en el mismo vblank no entra: la subida
; termina cayendo afuera y los objetos salen en cualquier lado.
;
; Por eso se sube lo del cuadro anterior apenas empieza el vblank, y recién
; después se arma la del siguiente. El scroll va junto, para que el fondo y los
; sprites correspondan al mismo momento.
.proc flush_video
.a8
.i16
    jsr push_oam
    lda destello_listo
    beq sin_destello
    jsr subir_destello          ; el destello, o el tinte, van antes que las
    lda #2                      ; poses y les comen presupuesto en este
    sta vq_tope                 ; mismo vblank
    bra sin_tinte
sin_destello:
    lda tinte_listo
    beq sin_tinte
    jsr subir_tinte
    lda #2
    sta vq_tope
sin_tinte:
    ; Y un renglón de la ventana esperando también les come presupuesto: son
    ; 1920 bytes de un solo DMA, casi cuatro poses. Con las cinco de siempre el
    ; vblank se termina en el medio y lo que falta del renglón se escribe con
    ; la pantalla encendida, o sea que no se escribe: queda una franja de
    ; basura en la ventana, **fija**, y sólo en un mapa con muchos eventos
    ; moviéndose. taro la vio en Lashe City el 2026-09-08 hablándole al
    ; mecánico y al linyera; apareció con los eventos paralelos, que sumaron
    ; nueve personajes que se mueven y por lo tanto nueve poses por subir.
    lda msg_subir
    beq sin_renglon
    lda #1
    sta vq_tope
sin_renglon:
    ; Y una tira del mapa esperando —la fila o la columna que la cámara
    ; destapó— también: `push_strips` corre después de las poses y hasta el
    ; 2026-09-10 no descontaba nada, así que en un vblank con las cinco poses
    ; sus DMA caían con la pantalla encendida y la VRAM los ignoraba. La fila
    ; quedaba sin dibujar hasta que la cámara volviera a pasar por ahí. taro lo
    ; vio jugando el 2026-09-09, "medio random", y lo reproduce EV0041 del
    ; mapa 8: el salto del héroe encola poses nuevas justo cuando la cámara
    ; cruza una fila. Una fila son cuatro DMA de 64 bytes, media pose: se le
    ; descuenta una entera para no andar midiendo el borde.
    lda row_addr
    ora row_addr + 1
    ora col_addr
    ora col_addr + 1
    beq sin_tira
    lda vq_tope
    beq sin_tira
    dec a
    sta vq_tope
sin_tira:
    ; Y un paso de la animación del ChipSet, que también sale de este vblank:
    ; hasta 26 tiles de fondo, o sea 1664 bytes, que es más de tres poses. Se lo
    ; descuenta al presupuesto en vez de fijarlo, para que se sume a lo que ya
    ; se hayan llevado el tinte o un renglón de la ventana.
    jsr anim_flush
    ; Y los 2 KB del cuadro de la animación de batalla, si el tick pidió uno
    ; nuevo. Es lo más caro que se sube en un vblank —cuatro poses de las
    ; cinco— y pasa una vez cada dos cuadros. Va **antes** de `vram_drenar` por
    ; lo mismo que `anim_flush`: lo que se lleva tiene que salir del
    ; presupuesto de este vblank, y tres líneas más abajo `vq_tope` ya se
    ; resetea para el que viene. Ver `animacion_dibujo_dma`.
    lda f:ANIMB_SUBIR
    beq sin_anim_cuadro
    lda #0
    sta f:ANIMB_SUBIR
    jsr animacion_dibujo_dma
sin_anim_cuadro:
    jsr vram_drenar             ; las poses que esta OAM ya da por subidas
    lda #VQ_POR_CUADRO
    sta vq_tope                 ; el vblank que viene arranca con todo

    ; La paleta de un destello, si quedó una pendiente del cuadro anterior.
    lda flash_pend
    beq sin_flash
    stz flash_pend
    lda flash_pend_cgadd
    sta CGADD
    rep #$20
.a16
    lda #.loword(flash_buf)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_flash:

    ; Y la paleta del cartel, si la rampa la rehizo este cuadro. Son treinta y
    ; dos bytes y van aparte de las tres del mapa: la entrada del cartel cae
    ; arriba de `SPRITE_CGRAM`, o sea afuera de lo que sube `subir_paletas`.
    lda f:CARTEL_LISTO
    beq sin_imagen
    lda #0
    sta f:CARTEL_LISTO
    lda #(128 + 16 * IMAGEN_PAL)
    sta CGADD
    rep #$20
.a16
    lda #.loword(cgram_sombra + 2 * (128 + 16 * IMAGEN_PAL))
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_imagen:

    ; Y la paleta de la animación de batalla, si acaba de empezar una. Son los
    ; mismos treinta y dos bytes que el cartel y por lo mismo: su entrada cae
    ; arriba de `SPRITE_CGRAM` y `subir_paletas` no la toca.
    lda f:ANIMB_PAL
    beq sin_anim_pal
    lda #0
    sta f:ANIMB_PAL
    lda f:ANIMB_CGADD
    sta CGADD
    rep #$20
.a16
    lda f:ANIMB_SOMBRA
    clc
    adc #.loword(cgram_sombra)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    stz A1B0
    lda #$00
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
sin_anim_pal:

    ; Los dos registros de scroll son de escritura doble: primero el byte bajo
    ; y después el alto.
    ; Cada registro se completa antes de pasar al siguiente. Los de scroll
    ; comparten un único latch entre todos los planos, así que intercalar las
    ; escrituras —BG1 bajo, BG2 bajo, BG1 alto, BG2 alto— mezcla los valores y
    ; el plano queda desplazado dentro de su celda, moviéndose en el lugar.
    lda pantalla_x              ; la cámara más la sacudida, si la hay
    sta BG1HOFS
    lda pantalla_x + 1
    sta BG1HOFS
    lda pantalla_x
    sta BG2HOFS
    lda pantalla_x + 1
    sta BG2HOFS

    lda scroll_y
    sta BG1VOFS
    lda scroll_y + 1
    sta BG1VOFS
    lda scroll_y
    sta BG2VOFS
    lda scroll_y + 1
    sta BG2VOFS

    jsr push_strips

    ; Y el HDMA de la ventana de mensaje: prendido mientras haya una en
    ; pantalla, apagado cuando no. Eso es **todo** lo que cuesta abrirla y
    ; cerrarla; el tilemap propio ya está escrito desde que se cargó el mapa.
    ;
    ; Los dos tramos de arriba de la tabla de scroll llevan la cámara de este
    ; cuadro, la misma que se acaba de escribir en los registros: el HDMA los
    ; vuelve a escribir en la línea 0 y no cambia nada. Lo que cambia es la
    ; línea 144 para abajo.
    ; Primero el compositor: el renglón que dejó listo, y la ventana entera
    ; cuando ya no queda ninguno.
    lda msg_subir
    beq sin_subir
    jsr subir_linea
sin_subir:
    lda msg_estado
    cmp #2
    bne no_termino
    stz msg_estado
    lda #1
    sta msg_abierto
no_termino:

    lda msg_abierto
    beq sin_ventana
    lda pantalla_x
    sta hdma_ofs + 1
    sta hdma_ofs + 6
    lda pantalla_x + 1
    sta hdma_ofs + 2
    sta hdma_ofs + 7
    lda scroll_y
    sta hdma_ofs + 3
    sta hdma_ofs + 8
    lda scroll_y + 1
    sta hdma_ofs + 4
    sta hdma_ofs + 9
    lda #HDMA_VENTANA
    sta HDMAEN
    bra prender
sin_ventana:
    stz HDMAEN
    ; Sin HDMA la máscara de objetos queda como la dejó la última línea, que
    ; es prendida: se apaga a mano, como BG2SC acá abajo.
    stz WOBJSEL
    ; BG2SC hay que devolverlo a mano: el HDMA lo dejó con el tilemap de la
    ; ventana en la última línea que escribió, y sin HDMA nadie lo vuelve a
    ; tocar. Cuesta dos instrucciones y evita tener que acordarse de esto al
    ; cerrar un mensaje.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC

    ; Y último de todo, el brillo maestro.
    ;
    ; **INIDISP se escribe únicamente acá**, y eso no es prolijidad: es lo que
    ; hace que el brillo cambie entre dos cuadros y no a mitad de uno. Escribirlo
    ; desde el lazo dibuja el cuadro partido —lo de arriba con el brillo viejo y
    ; lo de abajo con el nuevo—, que es exactamente el defecto que se veía en
    ; cada teletransporte: la pantalla volvía a prenderse cuando terminaba la
    ; carga, o sea a mitad de cuadro, y encima con el scroll y OAM del mapa
    ; viejo, porque esos también se escriben acá y sólo en el vblank.
    ;
    ; Quien quiera cambiar el brillo escribe `brillo` y espera al vblank
    ; siguiente, igual que quien mueve un sprite escribe OAM y espera. La única
    ; excepción es el blanking forzado de una carga, que `fundido_tick` escribe
    ; a mano: ahí la pantalla ya está en negro y el cambio no se ve.
prender:
    lda brillo
    sta INIDISP
    rts
.endproc

; Sube Y bytes desde la dirección X de la RAM a la VRAM, que ya quedó apuntada.
.proc dma_a_vram
.a8
.i16
    stx A1T0L
    stz A1B0                    ; las tiras viven en el banco 0
    sty DAS0L
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    rts
.endproc

; Las tiras que dejó armadas stream_map. Van acá y no donde se arman porque la
; VRAM sólo se puede escribir en el vblank; armarlas adentro no entraría.
;
; Una columna sale de un DMA por capa: el PPU puede avanzar de a 32 palabras
; tras cada escritura, que es justo lo que mide una fila del tilemap. Una fila
; sale de dos, porque las dos pantallas de 32x32 no son contiguas.
.proc push_strips
.a8
.i16
    ldx col_addr
    beq sin_columna
    lda #$81                    ; avanzar 32 palabras tras el byte alto
    sta VMAIN
    stx VMADDL
    ldx #.loword(tira_col)
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram

    rep #$20
.a16
    lda col_addr
    clc
    adc #(VRAM_ABOVE_MAP - VRAM_MAP)
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_col2)
    ldy #(WINDOW_ROWS * 2)
    jsr dma_a_vram
    stz col_addr
    stz col_addr + 1
sin_columna:

    ldx row_addr
    beq sin_fila
    lda #$80                    ; avanzar una palabra: la fila es contigua
    sta VMAIN
    stx VMADDL
    ldx #.loword(tira_row)
    ldy #(WINDOW_COLS)          ; las ranuras 0 a 31, la pantalla izquierda
    jsr dma_a_vram

    rep #$20
.a16
    lda row_addr
    clc
    adc #1024                   ; la pantalla de la derecha vive acá
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row + WINDOW_COLS)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram

    ; Y lo mismo para la capa de encima, media ventana más adelante.
    rep #$20
.a16
    lda row_addr
    clc
    adc #(VRAM_ABOVE_MAP - VRAM_MAP)
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row2)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram

    rep #$20
.a16
    lda temp
    clc
    adc #1024
    sta temp
    sep #$20
.a8
    ldx temp
    stx VMADDL
    ldx #.loword(tira_row2 + WINDOW_COLS)
    ldy #(WINDOW_COLS)
    jsr dma_a_vram
    stz row_addr
    stz row_addr + 1
sin_fila:
    rts
.endproc

; --- la animación del ChipSet ----------------------------------------------
;
; Dos animaciones que corren a la vez y a cadencias distintas: los autotiles de
; agua, que cambian cada AGUA_CUADROS y recorren el ciclo 0,1,2,1, y los "tiles
; animados", que cambian cada ANIMADO_CUADROS y dan la vuelta entre cuatro.
;
; Animar es **pisar el dato de unos pocos tiles de la VRAM**; el tilemap no se
; toca. El conversor deja los que cambian en una corrida contigua al final del
; banco del mapa, sin compartir ninguno con las celdas quietas, así que un paso
; es un DMA solo: entre 128 y 1664 bytes según el mapa. Ver `convert` en
; tools/port/snes_convert.py.
;
; **No guarda en qué punto va y no lee nada del cartucho para decidir**, y las
; dos cosas eran obligatorias y no elegancia: la BSS estaba en 7680 de 7680 y la
; página directa en 255 de 256, así que no había dónde poner ni un contador ni
; un puntero para `lda [puntero], y`. En qué punto del ciclo va cada familia
; sale de dividir `vueltas` —menos `vueltas_congeladas`, los ticks del fundido—
; por su cadencia con el divisor del hardware; dónde están sus tiles y sus
; dibujos lo trae `anim_tabla`, que arma el conversor.
;
; El resto de esa división dice además **si este tick es el del cambio**, que es
; lo único que hay que preguntar para saber si hace falta el DMA.
;
; El ciclo del agua: cuatro pasos, y el cuarto vuelve a dibujar el segundo. Es
; `animation_step_ab` de easyrpg, tilemap_layer.cpp:289, con `animation_type` en
; 0, que es el default y lo que tienen todos los ChipSets de este juego.
; Tres dibujos en cuatro pasos, con el cuarto repitiendo el segundo. Lo usan
; las dos animaciones que hay: el agua del ChipSet —`animation_step_ab` de
; easyrpg— y el ciclo de caminata de un personaje, que tiene tres columnas y
; dibuja la 1 cuando el paso es el 3. Es `CICLO_TRES` en tools/rpgmaker/rm2k.py.
ciclo_tres:
    .byte 0, 1, 2, 1

; Cuánto avanza el héroe por cuadro según su velocidad, en **medias unidades**
; de RM2k: RM2k cuenta 256 por celda y avanza `1 << (1 + velocidad)`, o sea 4,
; 8, 16, 32, 64 y 128 —`PASO_POR_VELOCIDAD` en eventos.py—, y acá `step_left`
; es un byte, así que se cuenta de a dos: 128 por celda y la mitad de cada
; paso. Los pixeles que faltan son `step_left >> 3`: la división entera tira
; los dieciseisavos, y a las velocidades con medio pixel por cuadro eso es lo
; mismo que contar los cuadros por dos.
paso_medio_por_vel:
    .byte 2, 4, 8, 16, 32, 64
; Y cada cuántos cuadros cambia el frame de la caminata: `ANIM_PARADO`.
anim_por_vel:
    .byte 12, 10, 8, 6, 5, 4

; Deja en X la entrada de la familia Y adentro de `anim_tabla`. Cuál es el mapa
; sale de `mapa_ofs` sin guardar nada: los dos pasos son potencias de dos.
.proc anim_donde
.a8
.i16
    rep #$20
.a16
    lda mapa_ofs
    lsr a
    lsr a
    lsr a
.assert MAPA_STRIDE = 128, error, "las tres divisiones de arriba son MAPA_STRIDE/ANIM_STRIDE"
.assert ANIM_STRIDE = 16, error, "ídem"
    sta temp
    tya
    asl a
    asl a
    asl a
.assert ANIM_FAM_STRIDE = 8, error, "las tres multiplicaciones son ANIM_FAM_STRIDE"
    clc
    adc temp
    tax
    sep #$20
.a8
    rts
.endproc

; Qué dibujo le toca a la familia Y en el tick que venga en X. Devuelve el
; dibujo en A y en `temp + 3` un 1 si **este** tick es aquel en que cambia, o
; sea si el reloj cayó justo en el borde.
;
; El tick es `vueltas`, el mismo número que cuenta la referencia. Como es de
; dieciséis bits, cada 65536 ticks —dieciocho minutos— da la vuelta y el ciclo
; se saltea un dibujo; RM2k cuenta en treinta y dos. La referencia da la misma
; vuelta —ver `TICK_BITS` en tools/rpgmaker/rm2k.py— así que los dos lados siguen
; diciendo lo mismo, y lo que se pierde está declarado en LIMITACIONES.md.
.proc anim_paso
.a8
.i16
    rep #$20
.a16
    txa
    sta WRDIVL                  ; el dividendo, en una sola escritura de 16
    sep #$20
.a8
    lda #AGUA_CUADROS
    cpy #$0000
    beq divisor
    lda #ANIMADO_CUADROS
divisor:
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    stz temp + 3
    lda RDMPYL                  ; el resto: cero es el tick del cambio
    ora RDMPYL + 1
    bne no_cambia
    inc temp + 3
no_cambia:
    lda RDDIVL
    and #(AGUA_CICLO_N - 1)
.assert AGUA_CICLO_N = 4, error, "el ciclo se recorta con un and de dos bits"
.assert ANIMADO_PASOS = 4, error, "y los dos ciclos miden lo mismo"
    cpy #$0000
    bne listo                   ; los tiles animados dan la vuelta y ya está
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ciclo_tres, x
    plx
listo:
    rts
.endproc

; El DMA de una familia: X su entrada en `anim_tabla` e Y el dibujo. El modo del
; DMA lo deja puesto quien llama, que siempre pide lo mismo.
.proc anim_subir
.a8
.i16
    pha                         ; el dibujo, que las cuentas de abajo pisan
    lda f:anim_tabla + 6, x
    bne hay
    pla
    rts                         ; esta familia no anima en este mapa
hay:
    rep #$20
.a16
    lda f:anim_tabla + 0, x
    sta VMADDL
    lda f:anim_tabla + 4, x
    sta DAS0L
    sta temp                    ; cuánto mide un dibujo
    lda f:anim_tabla + 2, x
    sta temp + 2                ; y dónde está el 0, adentro del bloque
    sep #$20
.a8
    ; El dibujo se ensancha acá y no en quien llama: `ldy` con X e Y anchos se
    ; lleva el byte de al lado, y eso ya costó una tarde dos veces —ver
    ; `anim_tick`—. Con `and #$00FF` sobre el acumulador ancho, el byte alto
    ; queda en cero venga de donde venga.
    pla
    rep #$20
.a16
    and #$00FF
    tay
saltar:
    cpy #$0000
    beq puesto
    lda temp + 2
    clc
    adc temp
    sta temp + 2
    dey
    bra saltar
puesto:
    ; El bloque vive en el cartucho y su puntero está en el registro del mapa.
    ; El acomodo de `tools/ensamblado/bancos.py` garantiza que entra entero en un banco,
    ; así que la suma de
    ; dieciséis bits no se sale.
    phx
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_ANIM_TILES, x
    clc
    adc temp + 2
    sta A1T0L
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_ANIM_TILES + 2, x
    sta A1B0
    plx
    lda #$01
    sta MDMAEN
    rts
.endproc

; El modo del DMA que piden los dos de abajo: tiles de fondo a la VRAM.
.proc anim_modo
.a8
.i16
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    rts
.endproc

; Las dos familias, ya mismo y sin presupuesto: es lo que hace `load_map`, con
; la pantalla apagada. El mapa nuevo trae en la VRAM el dibujo 0 de cada
; corrida y el reloj puede estar en cualquier otro, porque es de la partida y no
; del mapa.
.proc anim_cargar
.a8
.i16
    stz anim_pend               ; lo que hubiera pendiente se sube acá
    jsr anim_modo
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; el reloj de las animaciones: ver ahí
    tax
    sep #$20
.a8
    jsr anim_paso               ; Y sigue siendo la familia
    ply
    phy
    pha
    jsr anim_donde
    pla
    jsr anim_subir
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; Qué hay que subir en el vblank que viene, decidido en el cuerpo del lazo.
;
; Va **después** del `inc vueltas`, así que el tick que mira es el de la vuelta
; que sigue, que es la que va a mostrar el dibujo. Que sea ése y no el anterior
; está medido y no razonado: ver `anim_flush`.
.proc anim_tick
.a8
.i16
    stz anim_pend
    ldy #$0000
otra:
    phy
    rep #$20
.a16
    lda vueltas
    sec
    sbc f:vueltas_congeladas    ; el reloj de las animaciones: ver ahí
    tax
    sep #$20
.a8
    jsr anim_paso
    inc a                       ; el dibujo, más uno: el cero es "nada"
    sta temp + 2
    ; Y si este tick es el del cambio. Se mira con el acumulador en ocho bits y
    ; no con `ldx`: con X ancho la lectura se lleva también `temp + 4`, que es
    ; el byte bajo de `hero_x`, y entonces todos los ticks parecen el del
    ; cambio. Subir el dibujo que ya está subido no se ve, así que el error
    ; sobrevive a la comparación de pixeles; lo que se ve es el presupuesto de
    ; poses bajando todos los cuadros.
    lda temp + 3
    beq siguiente
    ply
    phy
    jsr anim_donde
    lda f:anim_tabla + 6, x
    beq siguiente               ; esta familia no anima en este mapa
    lda temp + 2
    cpy #$0000
    beq baja
    asl a
    asl a
    asl a                       ; tres bits por familia
.assert ANIM_FAMILIAS = 2, error, "los dos nibbles de anim_pend entran en un byte"
baja:
    ora anim_pend
    sta anim_pend
siguiente:
    ply
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    rts
.endproc

; El paso que toque, en el vblank, y sólo en el tick en que cambia.
;
; El tick que se mira es `vueltas` tal cual, sin corregir nada por el cuadro que
; el video va atrasado. Está medido y no razonado: con `vueltas - 1` la tanda da
; rojo en **un tick de cada 24** —el del cambio— y en ninguno más, que es 32%
; de la pantalla en el mapa 5. El caso que lo cobra es `snes-caminando 5 left`
; con el avance 46, o sea el tick 24 justo.
;
; Lo que sube se le descuenta al presupuesto de poses en vez de fijarlo, para
; que se sume a lo que ya se hayan llevado el tinte o un renglón de la ventana.
.proc anim_flush
.a8
.i16
    lda anim_pend
    bne hay
    rts                         ; el caso de siempre: un lda y un beq
hay:
    jsr anim_modo
    ldy #$0000
otra:
    ; Los tres bits de esta familia, leídos de `anim_pend` cada vuelta y no de
    ; una copia en `temp`: `anim_subir` guarda ahí una palabra y se llevaba
    ; puesta la copia. Cuando las dos familias cambiaban en el mismo tick —cada
    ; 24, que es múltiplo de 6— la segunda se perdía y se quedaba con el dibujo
    ; viejo hasta el cambio siguiente. Se veía en 8 pixeles del mapa 2.
    lda anim_pend
    cpy #$0000
    beq baja
    lsr a
    lsr a
    lsr a
baja:
    and #$07
    beq siguiente
    dec a                       ; el dibujo que pidió `anim_tick`
    phy
    pha
    jsr anim_donde
    pla
    jsr anim_subir
    ; Lo que se llevó, en poses: una pose son 512 bytes y un tile de fondo 64.
    ; Se le descuenta al presupuesto en vez de fijarlo, para que se sume a lo
    ; que ya se hayan llevado el tinte o un renglón de la ventana.
    lda f:anim_tabla + 6, x
    lsr a
    lsr a
    lsr a
.assert BYTES_POR_TILE = 64, error, "ocho tiles de fondo entran en una pose de 512"
    inc a
    sta temp + 2
    lda vq_tope
    sec
    sbc temp + 2
    bcc una
    bne queda
una:
    lda #1                      ; siempre queda para una pose
queda:
    sta vq_tope
    ply
siguiente:
    iny
    cpy #ANIM_FAMILIAS
    bne otra
    stz anim_pend
    rts
.endproc

; --- el héroe --------------------------------------------------------------
; RM2k no mueve al personaje libremente: se compromete a una celda vecina y
; recorre los 16 pixeles hasta ella sin poder frenar. Por eso el estado es la
; celda donde está más cuántos pixeles le faltan del paso en curso, y mientras
; falten no se acepta otra dirección.
;
; Los cuatro bits de pasabilidad son: abajo $01, izquierda $02, derecha $04,
; arriba $08. Cruzar de una celda a la de al lado pide permiso a las dos: la de
; origen tiene que dejar salir por ese lado y la de destino dejar entrar por el
; opuesto. Todo lo demás —que la capa alta manda salvo que sea decorado, que las
; caras de pared se cruzan siempre— ya lo resolvió el conversor.

PASS_DOWN  = $01
PASS_LEFT  = $02
PASS_RIGHT = $04
PASS_UP    = $08

.proc move_hero
.a8
.i16
    ; Si hay un paso en curso, se termina: no se puede frenar a mitad de celda.
    lda step_left
    beq quieto
    jsr advance_step
    rts

quieto:
    stz moving
    ; Sin paso en curso no hay paso de ruta que anotar. Se limpia acá y no al
    ; terminar la ruta porque lo que interesa es el paso, no la ruta.
    stz ruta_paso
    ; Una ruta forzada manda sobre el pad: mientras quede, el jugador no mueve
    ; al héroe. Es lo que hace RM2k, y es lo que permite que una cinemática lo
    ; camine sola.
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta
    jsr paso_de_ruta
    rts
sin_ruta:
    ; El pedido de menú, en el orden de `UpdateNextMovementAction`: con una
    ; página corriendo se tira; con un mensaje abierto espera; y si no, se
    ; abre el menú y el héroe no camina en este cuadro. Va antes de mirar
    ; `esperando_n` porque RM2k mira `IsAnyEventStarting` después.
    lda ev_activo
    beq menu_sin_pagina
    jsr menu_olvidar
    rts
menu_sin_pagina:
    lda msg_abierto
    bne no_derecha
    ; El encuentro que quedó pendiente se cobra acá: sin página corriendo, sin
    ; mensaje abierto y sin ruta forzada, que es el orden de
    ; `Game_Player::UpdateNextMovementAction` —el encuentro va **antes** del
    ; pedido de menú—. `encuentro_probar` deja la tropa en `BA_TROPA`.
    jsl f:encuentro_probar
    cmp #0                      ; el `plx` de allá dejó sus propias banderas
    beq sin_encuentro
    jsr pelea_arrancar
    ; Y perderla es Game Over, igual que una pelea de página sin manejador de
    ; derrota: un encuentro al azar **nunca** los trae, porque no hay página
    ; que los emita. Sin esto la derrota devolvía el control al mapa con todo
    ; el grupo en cero HP, y de ahí en más cada pelea se perdía sola antes de
    ; abrirse —`batalla_correr` contesta derrota con nadie en pie—. Ver
    ; `op_battle_destination`, que hace lo mismo con `BATALLA_PERDER`.
    lda f:BAT_LARGO + BA_RESULT
    cmp #BA_DERROTA
    bne sin_derrota
    jml f:reset
sin_derrota:
    rts
sin_encuentro:
    jsr acceso_leer
    bpl menu_sin_pedido         ; el bit 7 es el pedido
    and #$7F
    jsr acceso_escribir
    jsr menu_pantalla
    rts
menu_sin_pedido:
    ; Y un mensaje en pantalla manda sobre el pad, igual que la ruta forzada.
    ; Es lo que hace `Game_Player::UpdateNextMovementAction` de easyrpg, que
    ; vuelve sin mirar el input si `Game_Message::IsMessageActive()`. Va acá
    ; abajo y no arriba de todo a propósito: la ruta forzada **sí** camina con
    ; el mensaje abierto —`UpdateMoveRoute` corre antes del guard— y un paso ya
    ; empezado se termina, porque en RM2k no se frena a mitad de celda.
    lda msg_abierto
    bne no_derecha
    ; Y una página corriendo también manda sobre el pad. Es el
    ; `if (Game_Map::IsAnyEventStarting()) return;` de
    ; `Game_Player::UpdateNextMovementAction`: mientras el intérprete tiene algo
    ; en el frente, el jugador no camina.
    ;
    ; Sin esto, un evento de contacto se disparaba y el héroe daba **un paso
    ; más** mientras el mensaje se componía: el mensaje tarda unos cuadros en
    ; abrirse y `msg_abierto` recién se prende al final.
    lda ev_activo
    bne no_derecha
    lda esperando_n
    bne no_derecha
    lda pad
    and #PAD_UP
    beq no_arriba
    lda #DIR_UP
    sta hero_dir
    jsr try_up
    bra tras_paso
no_arriba:
    lda pad
    and #PAD_DOWN
    beq no_abajo
    lda #DIR_DOWN
    sta hero_dir
    jsr try_down
    bra tras_paso
no_abajo:
    lda pad
    and #PAD_LEFT
    beq no_izquierda
    lda #DIR_LEFT
    sta hero_dir
    jsr try_left
    bra tras_paso
no_izquierda:
    lda pad
    and #PAD_RIGHT
    beq no_derecha
    lda #DIR_RIGHT
    sta hero_dir
    jsr try_right
tras_paso:
    ; Un paso que arrancó de verdad —`step_left` lo dice— es un paso de RM2k:
    ; `IncSteps` y `UpdateEncounterSteps`, que allá corren después de `Move()`
    ; y sólo si el héroe se movió. Va en la rama del pad y no adentro de
    ; `advance_step` porque **los pasos de una ruta forzada no cuentan**: allá
    ; se vuelve antes, por `IsMoveRouteOverwritten`.
    lda step_left
    beq no_derecha
    jsl f:encuentro_paso
no_derecha:
    rts
.endproc

; Cada intento comprueba el borde del mapa, después los dos permisos, y recién
; ahí arranca el paso.
; Los cuatro trabajan con el acumulador de 16 bits: la celda del héroe ya no
; entra en un byte —hay mapas de 500 celdas de ancho— y los permisos se buscan
; con índices de 16.
.proc try_up
.a8
.i16
    rep #$20
.a16
    lda tile_y
    beq no                      ; ya está en la fila de arriba
    lda #PASS_UP
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_menos               ; el destino: una fila de bloques más arriba
    lda #PASS_DOWN              ; y esa celda tiene que dejar entrar
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    dec a
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    dec tile_y
    lda #0
    sta step_dx
    lda #$FFFF              ; -1: ca65 no acepta un inmediato negativo
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_down
.a8
.i16
    rep #$20
.a16
    lda tile_y
    inc a
    cmp mapa_alto
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_mas                 ; una fila de bloques más abajo
    lda #PASS_UP
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    inc a
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    inc tile_y
    lda #0
    sta step_dx
    lda #1
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_left
.a8
.i16
    rep #$20
.a16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_menos               ; la celda de al lado
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    lda tile_x
    dec a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    dec tile_x
    lda #$FFFF              ; -1: ca65 no acepta un inmediato negativo
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_right
.a8
.i16
    rep #$20
.a16
    lda tile_x
    inc a
    cmp mapa_ancho
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_mas
    lda #PASS_LEFT
    jsr can_enter
    beq no
    lda tile_x
    inc a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    inc tile_x
    lda #1
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

; --- la pasabilidad --------------------------------------------------------
; Ya no hay una tabla con un byte por celda: los permisos viajan en el bloque.
; Son dos saltos —la celda dice qué bloque es, el bloque dice qué permisos
; tiene— y a cambio el mapa más grande se ahorra veinte kilobytes. Que dos
; celdas dibujadas igual pero con permisos distintos no se confundan lo
; garantiza el conversor, que mete la pasabilidad en la clave del bloque.
;
; Dónde está el héroe dentro de la grilla tampoco es un índice: es un puntero
; que se mueve con él, una celda o una fila por paso. Así nunca hay que
; multiplicar ni recalcular una dirección de 24 bits desde cero, que en LoROM
; es incómodo porque los bancos no son contiguos.

; A = el bit que hace falta. Devuelve con Z apagado si la celda lo tiene.
.proc can_leave
.a16
.i16
    sta temp
    lda tile_x                  ; la celda que se deja, para lo que un evento
    sta pasa_x                  ; de tile le imponga
    lda tile_y
    sta pasa_y
    jsr ptr_desde_hero
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando             ; con walk_everywhere la respuesta es que sí
    rts
.endproc

; Igual, pero sobre la celda a la que celdas_ptr ya quedó apuntando: cada
; dirección lo corre por su cuenta antes de llamar, y si el paso se acepta
; begin_step lo copia a hero_ptr. Así el destino se calcula una sola vez.
.proc can_enter
.a16
.i16
    sta temp
    ; La celda de destino: la del héroe más el paso en `hero_dir`, que es
    ; siempre la dirección del paso, también en una ruta forzada.
    lda tile_x
    sta pasa_x
    lda tile_y
    sta pasa_y
    sep #$20
.a8
    lda hero_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando
    rts
.endproc

; Los bits de paso de la celda `pasa_x`/`pasa_y`: los que trae A —los del
; terreno, de `pass_del_ptr`— salvo que un evento de tile en la capa de abajo
; le imponga los suyos. Es `Game_Map::IsPassableTile`: de los eventos parados
; ahí con página activa y gráfico de tile en esa capa gana el de id más alto,
; y si su tile no es de los que van por encima, manda. Los bits los dejó el
; refresco en la fila del NPC, +15, o $FF si no impone nada; así esto es un
; recorrido de la tabla de NPCs por paso y no una pasada por las páginas. Lo
; que no se modela: el "conflicto consigo mismo" de un evento de tile que
; camina, porque ninguno camina. Entra y sale en dieciséis bits.
.proc pasa_con_evento
.a16
.i16
    sta temp + 2
    sep #$20
.a8
    lda #$FF
    sta pasa_hallada
    ldy #$0000
otra:
    cpy npc_total
    beq listo
    lda npc_buf + 14, y
    beq siguiente               ; escondido: no está
    lda npc_buf + 15, y
    cmp #$FF
    beq siguiente               ; no impone nada
    lda npc_buf + 8, y          ; su evento, y con él su celda
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; por EV_STRIDE
.assert EV_STRIDE = 4, error, "la cuenta de arriba multiplica por cuatro a mano"
    tax
    lda ev_pos_buf, x
    cmp pasa_x
    bne siguiente16
    lda ev_pos_buf + 2, x
    cmp pasa_y
    bne siguiente16
    sep #$20
.a8
    lda npc_buf + 15, y
    sta pasa_hallada            ; gana el último: el de id más alto
siguiente:
    rep #$20
.a16
siguiente16:
    tya
    clc
    adc #NPC_STRIDE
    tay
    sep #$20
.a8
    bra otra
listo:
    lda pasa_hallada
    cmp #$FF
    beq del_terreno
    sta temp + 2                ; el byte alto quedó en cero de `pass_del_ptr`
del_terreno:
    rep #$20
.a16
    lda temp + 2
    rts
.endproc

.proc sumar_a_pasa_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_x
    sta pasa_x
    sep #$20
.a8
    rts
.endproc
.proc sumar_a_pasa_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_y
    sta pasa_y
    sep #$20
.a8
    rts
.endproc

.proc pass_del_ptr
.a16
.i16
    lda [celdas_ptr]            ; qué bloque es esta celda
    tay
    sep #$20
.a8
    lda [pass_ptr], y
    rep #$20
.a16
    and #$00FF
    rts
.endproc

.proc ptr_desde_hero
.a16
.i16
    lda hero_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda hero_ptr + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_hero
.a16
.i16
    lda celdas_ptr
    sta hero_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    sta hero_ptr + 2
    rep #$20
.a16
    rts
.endproc

; El puntero a la celda (celda_x, celda_y) de la grilla. Se camina hasta ahí
; sumando: una fila de bloques por cada fila que baja y después las columnas de
; una vez.
;
; Está separado de `init_hero_ptr` porque ahora hay más de uno que camina: las
; rutas forzadas de los eventos consultan celdas que no son la del héroe, y
; tener la cuenta escrita dos veces es cómo se separan.
.proc ptr_de_celda
.a8
.i16
    rep #$20
.a16
    ldx mapa_ofs
    lda f:mapa_tabla + M_PTR_MAP_CELDAS, x
    sta celdas_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_CELDAS + 2, x
    sta celdas_ptr + 2
    rep #$20
.a16
    ldx celda_y
    beq sin_filas
filas:
    lda tira_paso_col
    jsr ptr_mas
    dex
    bne filas
sin_filas:
    lda celda_x
    asl a                       ; cada celda ocupa dos bytes
    jsr ptr_mas
    sep #$20
.a8
    rts
.endproc

; Dónde arranca el héroe dentro de la grilla.
.proc init_hero_ptr
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    jsr ptr_de_celda
    rep #$20
.a16
    jsr ptr_a_hero
    sep #$20
.a8
    rts
.endproc

; Arranca el paso: una celda entera por recorrer —128 medias unidades, ver
; `paso_medio_por_vel`— y el índice ya en la celda nueva, que es como RM2k
; lleva la cuenta.
.proc begin_step
.a8
.i16
    lda #128
    sta step_left
    rep #$20
.a16
    jsr ptr_a_hero              ; RM2k cuenta desde la celda de destino, que es
    sep #$20                    ; adonde can_enter dejó apuntado el puntero
.a8
    jsr advance_step
    rts
.endproc

; Avanza los pixeles de este cuadro y, si con eso se completa el paso, deja al
; personaje exactamente sobre la celda.
.proc advance_step
.a8
.i16
    lda #$01
    sta moving
    ; Lo que falta del paso baja lo que diga la velocidad, y los pixeles se
    ; **recalculan** desde la celda de destino y no se acumulan: con medio
    ; pixel por cuadro no hay nada entero que sumar. `step_dx` y `step_dy` son
    ; el sentido del paso, -1, 0 o 1.
    jsr anim_cuadros_del_heroe  ; de paso deja X en la velocidad menos uno
    lda step_left
    sec
    sbc paso_medio_por_vel, x
    bcs no_negativo
    lda #0
no_negativo:
    sta step_left
    lsr a
    lsr a
    lsr a                       ; los pixeles que faltan
    rep #$20
.a16
    and #$00FF
    sta temp                    ; nadie lo tiene tomado en un paso
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    ldx step_dx
    beq x_listo
    bmi x_desde_la_derecha
    sec
    sbc temp
    bra x_listo
x_desde_la_derecha:
    clc
    adc temp
x_listo:
    sta hero_x
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    ldx step_dy
    beq y_listo
    bmi y_desde_abajo
    sec
    sbc temp
    bra y_listo
y_desde_abajo:
    clc
    adc temp
y_listo:
    sta hero_y
    sep #$20
.a8
    lda step_left
    bne sigue                   ; el paso todavía no terminó
    ; Mientras al héroe le quede ruta forzada no se pisa nada: ni puerta ni
    ; evento de contacto. Es el `!IsMoveRouteOverwritten()` de
    ; `Game_Player::UpdateMovement`, y el último paso sí cuenta porque en
    ; `Game_Character::UpdateMovement` un movimiento que es la última orden
    ; cancela la ruta entera **antes** del chequeo —está comentado ahí: "If
    ; the last command of a move route is a move or jump, RPG_RT cancels the
    ; entire move route immediately"—. Con `ruta_i` ya pasado de la última
    ; orden, la ruta está cancelada; con órdenes por leer, no. Es lo que deja
    ; a la cinemática de apertura pisar el evento que apaga el tinte: son tres
    ; celdas para arriba y el evento está en la tercera.
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta                ; no quedan órdenes: puerta y contacto
    ; Quedan: el paso es del medio, y la frecuencia dice cuántos cuadros
    ; quieto antes de leer la siguiente. Vale aunque el paso lo haya arrancado
    ; el pad: en RM2k `UpdateMovement` pone el contador en cero al terminar
    ; cualquier paso, y `ForceMoveRoute` ya dejó el tope de la ruta.
    lda ruta_frec
    jsr tras_paso
    sta ruta_espera
    bra sigue
sin_ruta:
    jsr cruzar_puerta           ; recién parado en la celda: ¿había puerta?
    bne sigue                   ; la hubo: el mapa ya cambió y la celda de
                                ; llegada no se pisa, igual que en RM2k
    jsr probar_contacto         ; y si no, ¿hay un evento de contacto?
sigue:
    rts
.endproc

; Si la celda donde el héroe acaba de pararse tiene una puerta, cargar el mapa
; al que lleva. Se mira al terminar el paso y no al empezarlo, que es lo que
; hace RM2k: el evento se dispara cuando el héroe ocupa la celda, no cuando la
; encara. Devuelve A distinto de cero si cruzó.
;
; La tabla se recorre entera comparando. Son pocas —el mapa con más puertas del
; juego tiene un puñado— y esto corre una vez cada dieciséis pixeles.
.proc cruzar_puerta
.a8
.i16
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_PUERTA_COUNT, x
    beq no_hay
    sta temp                    ; cuántas quedan por mirar
    lda f:mapa_tabla + M_PTR_PUERTAS, x
    sta temp + 2
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_PUERTAS + 2, x
    sta puerta_ptr + 2
    rep #$20
.a16
    lda temp + 2
    sta puerta_ptr

    ldy #$0000
buscar:
    lda [puerta_ptr], y
    cmp tile_x
    bne siguiente
    iny
    iny
    lda [puerta_ptr], y
    dey
    dey
    cmp tile_y
    beq cruzar
siguiente:
    tya
    clc
    adc #PUERTA_BYTES
    tay
    dec temp
    bne buscar
no_hay:
    sep #$20
.a8
    lda #0
    rts

cruzar:
.a16
    ; Acá se llega con A en 16 bits, desde el `beq` de arriba. El `.a16` no es
    ; decoración: sin él el ensamblador viene creyendo lo que dejó dicho `no_hay`
    ; y le pone un solo byte al `and #$00FF`, que el CPU lee como dos y se come
    ; la instrucción siguiente.
    ;
    ; El destino está en el mismo registro: primero a dónde, después a qué mapa.
    iny
    iny
    iny
    iny
    lda [puerta_ptr], y         ; la celda de destino, en X
    sta entrada_x
    iny
    iny
    lda [puerta_ptr], y         ; y en Y
    sta entrada_y
    iny
    iny
    lda [puerta_ptr], y         ; el índice del mapa al que lleva, en un word

    ; Y el mapa no se carga acá: RM2k funde a negro al cruzar una puerta —una
    ; puerta es un teletransporte y le toca la misma transición—, así que se
    ; pide el fundido y la carga pasa adentro, con la pantalla ya apagada. El
    ; héroe se queda visible en la celda de la puerta mientras la pantalla baja,
    ; que es lo que se ve en el original.
    sta fundido_mapa
    ; **Una puerta al mismo mapa no recarga nada**, igual que un `Teleport` al
    ; mismo mapa: ver `hubo_salto`. Recargar vuelve a leer del cartucho las
    ; posiciones de los eventos, y con eso se pierde todo lo que los haya movido
    ; —un `ChangeEventLocation`, un `TradeEventLocations`— aunque el jugador
    ; nunca haya salido del mapa.
    ;
    ; Eso es lo que taro vio el 2026-09-07 con la puerta de arriba a la
    ; izquierda del mapa 2. Abrirla mueve el `LBDoorTop` a (94,97) y truequea el
    ; `LBDoorBottom` con el `MovinDoor`, así que el hueco queda negro. Cruzarla
    ; anda bien —eso va por `OP_TELEPORT`, que sí distingue—; volver, no: el
    ; evento 20 es una **puerta**, y al recargar el mapa las dos cosas volvían a
    ; su lugar y reaparecían las franjas amarillas. Los dos cuartos son el mismo
    ; mapa 2, separados lo suficiente como para que jugando parezcan dos.
    cmp mapa_actual
    sep #$20
.a8
    bne otro_mapa_puerta        ; `sep` no toca Z: el salto mira el `cmp`
    lda #FUNDIDO_MISMO
    bra pedir_puerta
otro_mapa_puerta:
    lda #FUNDIDO_PUERTA
pedir_puerta:
    jsr empezar_fundido
    lda #1
    rts                         ; cruzó: la celda de llegada no se pisa
.endproc

; --- animación de caminata -------------------------------------------------
; El ciclo son cuatro pasos sobre tres frames del CharSet: 0, 1, 2, 1. El del
; medio es la pose parada, y es a la que se vuelve al soltar la cruceta.
.proc animate_hero
.a8
.i16
    ; Con la animación parada por una ruta la pose se queda en la del medio,
    ; camine o no: RM2k llama a `ResetAnimation` en cada cuadro mientras
    ; `IsAnimPaused()`, que deja el frame del medio y el contador en cero.
    lda ruta_anim_para
    bne quieto
    lda moving
    bne caminando
quieto:
    lda #1                      ; quieto: el frame del medio
    sta anim_step
    stz anim_timer
    rts

caminando:
    ; La cuenta sube y se compara con el tope **de la velocidad de ahora**,
    ; como `GetAnimCount() >= stationary_limit`: si una ruta cambia la
    ; velocidad a mitad de un frame, el frame que viene ya sale con la nueva.
    ; Contando para abajo desde el tope, como antes, la nueva recién valía un
    ; frame después, y la referencia y la ROM diferían en un cuadro.
    inc anim_timer
    jsr anim_cuadros_del_heroe
    cmp anim_timer
    beq cambia
    bcs listo                   ; la cuenta todavía no llegó al tope
cambia:
    stz anim_timer
    lda anim_step
    inc a
    and #$03                    ; el ciclo son cuatro pasos
    sta anim_step
listo:
    rts
.endproc

; --- el cronómetro ---------------------------------------------------------
; Un cuadro de la cuenta. Es `Game_Party::UpdateTimers`, y lo que importa es el
; final: al llegar a cero segundos RM2k llama a `StopTimer`, que apaga la cuenta
; **y la esconde**. O sea que el último valor que se ve es 00:01 y después no
; queda nada dibujado, no un 00:00 congelado.
.proc timer_tick
.a8
.i16
    lda timer_activo
    bne corre
    rts
corre:
    lda timer_sub
    beq otro_segundo
    dec timer_sub
    rts
otro_segundo:
    lda #(TIMER_CUADROS - 1)
    sta timer_sub
    rep #$20
.a16
    lda timer_seg
    beq apagar_16               ; ya estaba en cero: no hay qué bajar
    dec a
    sta timer_seg
    sep #$20
.a8
    jsr timer_digitos
    lda timer_seg
    ora timer_seg + 1
    beq apagar
    rts
.a16
apagar_16:
    sep #$20
.a8
apagar:
    stz timer_activo
    stz timer_visible
    rts
.endproc

; Los cuatro dígitos de `timer_seg`, de los minutos a los segundos. Se llama
; cuando el segundo cambia y no en cada cuadro: son dos divisiones por restas
; sucesivas, y a 60 hercios serían sesenta veces el mismo resultado.
;
; Los minutos entran en dos dígitos porque el conversor no deja pasar un
; cronómetro de más de 1092 segundos: el tope se lo pone la cuenta de cuadros
; en dieciséis bits, no la pantalla.
.proc timer_digitos
.a8
.i16
    rep #$20
.a16
    lda timer_seg
    ldx #0
menos_60:
    cmp #60
    bcc listo_60
    sec
    sbc #60
    inx
    bra menos_60
listo_60:
    sta temp                    ; los segundos sueltos
    txa
    sta temp + 2                ; y los minutos
    sep #$20
.a8

    lda temp + 2                ; los minutos, en dos dígitos
    ldx #0
menos_10a:
    cmp #10
    bcc listo_10a
    sec
    sbc #10
    inx
    bra menos_10a
listo_10a:
    sta timer_dig + 1
    txa                         ; con A de ocho bits es el byte bajo de X
    sta timer_dig + 0

    lda temp                    ; y los segundos
    ldx #0
menos_10b:
    cmp #10
    bcc listo_10b
    sec
    sbc #10
    inx
    bra menos_10b
listo_10b:
    sta timer_dig + 3
    txa
    sta timer_dig + 2
    rts
.endproc

; Los cinco glifos del cronómetro en OAM, cada uno como dos objetos de 8x8
; apilados. Van **primero**, o sea en los objetos de índice más bajo, que son
; los que la consola pone adelante: en RM2k el cronómetro es `Priority_Timer`,
; que está por encima de todo lo demás, ventana de mensaje incluida. Acá eso lo
; da la prioridad 3 de objeto, que gana contra las dos capas.
;
; Los dos puntos parpadean: se dibujan sólo en la mitad de arriba del segundo,
; que es el `frames % 60 < 30 -> continue` de `Sprite_Timer::Draw`.
.proc timer_oam
.a8
.i16
    lda timer_visible
    bne hay
    rts
hay:
    ldx mapa_ofs
    lda f:mapa_tabla + M_TIMER_BASE, x
    ora f:mapa_tabla + M_TIMER_BASE + 1, x
    bne dibujar
    rts                         ; esta ROM no lleva los glifos
dibujar:
    stz obj_grande              ; los dígitos son de 8x8
    stz timer_i
cada_glifo:
    lda timer_i
    cmp #5
    bcc hay_glifo
    jmp fin
hay_glifo:
    cmp #2
    bne es_digito
    ; Los dos puntos, y sólo si toca.
    lda timer_sub
    cmp #(TIMER_CUADROS / 2)
    bcc siguiente
    lda #TIMER_DOS_PUNTOS
    bra con_glifo
es_digito:
    ; El índice en `timer_dig`: la posición, menos uno si va detrás de los dos
    ; puntos, que no tienen dígito propio.
    cmp #2
    bcc sin_ajuste
    dec a
sin_ajuste:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda timer_dig, x
con_glifo:
    sta timer_glifo
    stz timer_mitad
cada_mitad:
    ; Dónde cae en pantalla. La X no lleva el corrimiento de los personajes:
    ; los dígitos son de 8x8 y su esquina es su esquina.
    rep #$20
.a16
    lda timer_i
    and #$00FF
    ; Ocho por glifo, que es un corrimiento y no una multiplicación.
    asl a
    asl a
    asl a
    clc
    adc #TIMER_X
    sta obj_x
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    clc
    adc #TIMER_Y
    sta obj_y

    ; Y qué tile: los once glifos entran en una fila de dieciséis, así que la
    ; mitad de abajo está justo dieciséis más adelante.
    lda timer_mitad
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    clc
    adc timer_glifo             ; en dieciséis bits se lleva al byte de al
    and #$00FF                  ; lado, y por eso el `and`
    ldx mapa_ofs
    clc
    adc f:mapa_tabla + M_TIMER_BASE, x
    sta temp
    sep #$20
.a8
    lda temp
    sta obj_tile
    ; vhoopppN: prioridad 3 —adelante de las dos capas—, la paleta del
    ; cronómetro, y el noveno bit del tile.
    lda temp + 1
    and #$01
    sta temp + 2
    lda f:mapa_tabla + M_TIMER_PAL, x
    and #$07
    asl a
    ora #$30
    ora temp + 2
    sta obj_attr
    jsr emit_object

    inc timer_mitad
    lda timer_mitad
    cmp #2
    bcc cada_mitad
siguiente:
    inc timer_i
    jmp cada_glifo
fin:
    lda #$02                    ; y lo que siga vuelve a ser de 32x32
    sta obj_grande
    rts
.endproc

; --- armado de OAM ---------------------------------------------------------
; Un objeto por NPC más uno para el héroe, en el orden en que RM2k los dibuja:
; primero por capa y recién después por Y. En la consola el objeto con índice
; más bajo de OAM es el que se ve encima, así que se recorre del frente hacia el
; fondo — que es como el conversor dejó ordenada la tabla.
;
; El héroe se intercala donde le toca por su clave, no va siempre primero ni
; siempre último: un evento "below" tiene que quedar debajo de él aunque esté
; más adelante en pantalla, y uno "above" taparlo siempre.
.proc build_oam
.a8
.i16
    ; Todo escondido antes de empezar. Esconder sólo la cola al terminar deja
    ; los objetos que este cuadro no usó con los datos del anterior, y basta con
    ; que la cámara se mueva para que la cuenta cambie y alguno reaparezca donde
    ; no va. Son 128 escrituras y sacan de encima toda esa clase de error.
    jsr clear_oam
    stz high_acc
    stz hero_drawn
    rep #$20
.a16
    stz high_ptr
    stz oam_slot
    stz npc_ofs
    ; La clave del héroe: su capa arriba y su Y abajo, igual que en la tabla.
    lda hero_y
    and #$0FFF
    ora #(HERO_LAYER * 4096)
    sta hero_key
    sep #$20
.a8
    ; El cronómetro va antes que nadie: sus objetos son los de índice más bajo
    ; y por eso los que se ven adelante. Deja `obj_grande` en 32x32.
    lda #$02
    sta obj_grande
    jsr timer_oam
    jsr imagen_oam              ; y el cartel detrás de él: ver `imagen_oam`
    jsr animacion_dibujo_oam    ; y la animación de batalla detrás del cartel:
                                ; `Priority_BattleAnimation` es 110 contra los
                                ; 120 de `Priority_PictureOld`

recorrer:
    rep #$20
.a16
    lda npc_ofs
    cmp npc_total
    sep #$20
.a8
    beq ultimos

    lda hero_drawn
    bne toca_npc
    ; ¿Va el héroe antes que este NPC? Sí si su clave es mayor o igual, porque
    ; la tabla va de mayor a menor.
    ldx npc_ofs
    rep #$20
.a16
    lda hero_key
    cmp npc_buf + 4, x
    sep #$20
.a8
    bcc toca_npc
    jsr place_hero
    bra recorrer

toca_npc:
    ldx npc_ofs
    lda npc_buf + 14, x
    beq escondido               ; su página activa no dibuja nada
    jsr place_npc
escondido:
    rep #$20
.a16
    lda npc_ofs
    clc
    adc #NPC_STRIDE
    sta npc_ofs
    sep #$20
.a8
    bra recorrer

ultimos:
    lda hero_drawn
    bne cerrar
    jsr place_hero
cerrar:
    jsr lluvia_oam              ; las gotas, al final de todo
    jsr flush_high
    rts
.endproc

; El salto del héroe: consume las órdenes hasta `end_jump`, suma lo que aportan
; y lo pone del otro lado de una. Los once cuadros que dura no dependen de la
; distancia: `remaining_step` baja de 256 a 0 a SALTO_VELOCIDAD por cuadro,
; salte una celda o cinco.
.proc armar_salto_heroe
.a8
.i16
    stz salto_dx
    stz salto_dy
buscar:
    lda ruta_i
    cmp ruta_n
    bcs sin_fin
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i
    cmp #25
    beq con_fin
    jsr acumular_salto
    bra buscar
sin_fin:
    ; Sin `end_jump` el salto se saltea y lo que quedaba de ruta se pierde, que
    ; es lo que hace RM2k al llegar al final.
    stz ruta_salto
    rts

con_fin:
    jsr salto_a_celdas          ; el desplazamiento, con signo y en dieciséis
    rep #$20
.a16
    lda tile_x
    clc
    adc salto_dx16
    sta celda_x
    lda tile_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    ; Atravesando paredes se cae en cualquier celda: es el mismo
    ; `if (self.GetThrough()) return true;` que mira un paso, y `puede_caer`
    ; lo lee de `atravesando`, que acá nadie ponía. La ruta de EV0041 del mapa
    ; 8 —`through`, salto de una celda sobre la reja, cuatro pasos— saltaba
    ; en la referencia y en la ROM caminaba: el salto se salteaba por la reja y
    ; los pasos de después sí atravesaban. Medido el 2026-09-10, 40840
    ; pixeles en el cuadro 60.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    jsr puede_caer
    php
    stz atravesando
    stz atravesando + 1
    plp
    bne se_puede
    stz ruta_salto              ; no se puede caer ahí: el salto se saltea
    rts
se_puede:
    rep #$20
.a16
    lda celda_x
    sta tile_x
    lda celda_y
    sta tile_y
    sep #$20
.a8
    jsr init_hero_ptr
    ; Hacia dónde queda mirando. En el lugar no cambia nada: RM2k sólo fija el
    ; mirado cuando el salto se mueve.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    jsr direccion_del_salto
    sta hero_dir
sin_girar:
    lda #(SALTO_PASO - SALTO_VELOCIDAD)
    sta ruta_salto
    ; La celda ya es la de destino y los pixeles van detrás, igual que en un
    ; paso: así la cámara acompaña el arco en vez de saltar de una.
    jsr salto_posicion_heroe
    rts
.endproc

; `hero_x` y `hero_y` desde la celda de destino y lo que le queda al salto. Es
; `GetSpriteX` de RM2k: `x * 256 - dx * restante` y **después** la división por
; dieciséis, que es lo que evita el pixel de más o de menos cada vez que el
; descuento no es múltiplo de dieciséis.
.proc salto_posicion_heroe
.a8
.i16
    jsr salto_a_celdas
    lda ruta_salto
    sta salto_resta
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; la celda en las unidades de RM2k: por 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_x
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_y
    sep #$20
.a8
    rts
.endproc

; `salto_dx` y `salto_dy` con el signo extendido a dieciséis bits.
.proc salto_a_celdas
.a8
.i16
    rep #$20
.a16
    lda salto_dx
    and #$00FF
    cmp #$0080
    bcc dx_positivo
    ora #$FF00
dx_positivo:
    sta salto_dx16
    lda salto_dy
    and #$00FF
    cmp #$0080
    bcc dy_positivo
    ora #$FF00
dy_positivo:
    sta salto_dy16
    sep #$20
.a8
    rts
.endproc

; Hacia dónde queda mirando quien salta: gana el eje de mayor recorrido y con
; empate el vertical. Es el `if (abs(dy) >= abs(dx))` de `Game_Character::Jump`.
.proc direccion_del_salto
.a8
.i16
    rep #$20
.a16
    lda salto_dx16
    bpl dx_pos
    eor #$FFFF
    inc a
dx_pos:
    sta mirar_abs
    lda salto_dy16
    bpl dy_pos
    eor #$FFFF
    inc a
dy_pos:
    cmp mirar_abs
    bcc horizontal
    lda salto_dy16
    sep #$20
.a8
    bmi arriba
    lda #DIR_DOWN
    rts
arriba:
    lda #DIR_UP
    rts
.a16
horizontal:
    lda salto_dx16
    sep #$20
.a8
    bmi izquierda
    lda #DIR_RIGHT
    rts
izquierda:
    lda #DIR_LEFT
    rts
.endproc

; Corre `salto_px`/`salto_py` hacia atrás por lo que le falta al salto y deja en
; `salto_alto` cuánto hay que levantar el dibujo.
;
; La altura es `GetJumpHeight`: sube y baja con lo que queda, y la curva no es
; lineal sino la tabla de RM2k. Sólo mueve el **dibujo**: el orden contra los
; demás sale de `GetScreenY(false)`, o sea sin el salto, así que quien está en
; el aire no se adelanta.
.proc alto_del_salto
.a8
.i16
    stz salto_alto
    stz salto_alto + 1
    lda salto_resta
    bne hay
    rts
hay:
    ; Lo que queda o lo que se recorrió, el menor de los dos, sobre ocho; y
    ; después la tabla de RM2k, que no es lineal. Es `GetJumpHeight`, y sólo
    ; mueve el **dibujo**: el orden contra los demás sale de `GetScreenY(false)`,
    ; o sea sin el salto, así que quien está en el aire no se adelanta.
    cmp #(SALTO_PASO / 2)
    bcc de_bajada
    eor #$FF                    ; 256 - resta, con resta de un byte
    inc a
de_bajada:
    lsr a
    lsr a
    lsr a
    cmp #5
    bcs mediana
    asl a                       ; menos de cinco: el doble
    bra guardar
mediana:
    cmp #13
    bcs tope
    clc
    adc #4                      ; de cinco a doce: más cuatro
    bra guardar
tope:
    lda #16
guardar:
    sta salto_alto
    rts
.endproc

; `salto_val` por `salto_resta`, con signo, en `salto_prod`. La unidad de la
; consola multiplica sin signo y de a ocho bits, así que se hace sobre el valor
; absoluto y se le devuelve el signo al final.
.proc producto_salto
.a8
.i16
    rep #$20
.a16
    lda salto_val
    sta salto_signo
    bpl positivo
    eor #$FFFF
    inc a
    sta salto_val
positivo:
    sep #$20
.a8
    lda salto_val
    sta WRMPYA
    lda salto_resta
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta salto_prod
    lda salto_signo
    bpl listo
    lda #0
    sec
    sbc salto_prod
    sta salto_prod
listo:
    sep #$20
.a8
    rts
.endproc

; El salto de un evento. Igual que el del héroe, pero leyendo la ruta del
; cartucho y guardando el estado en la ranura. X es la ranura y hay que
; devolverla intacta.
.proc armar_salto_ev
.a8
.i16
    stz salto_dx
    stz salto_dy
    stz salto_trabado
buscar:
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcs sin_fin
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x
    cmp #25
    beq con_fin
    phx
    jsr acumular_salto
    plx
    bra buscar
sin_fin:
    ; Sin `end_jump` el salto se saltea y lo que quedaba de ruta se pierde.
    stz ruta_ev + 13, x
    rts

con_fin:
    ; `walk_everywhere`: `CheckOrMakeWayEx` corta con `if (self.GetThrough())
    ; return true;` apenas pasa el chequeo de límites, así que el que atraviesa
    ; paredes cae donde sea. Sin esto, la piedra del recuerdo de Core es una
    ; celda cerrada y el salto se saltea; taro lo vio como que Core se mueve
    ; arriba de su islita y no salta nunca, y la ruta que lo mueve arranca
    ; justamente con un `atravesar_on`.
    lda ruta_ev + 12, x
    and #$01
    sta atravesando
    stz atravesando + 1
    phx
    jsr celda_del_evento        ; su celda, que `puede_caer` necesita
    jsr salto_a_celdas
    rep #$20
.a16
    lda celda_x
    clc
    adc salto_dx16
    sta celda_x
    lda celda_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    jsr puede_caer
    plx
    stz atravesando
    stz atravesando + 1
    cmp #0                      ; `plx` pone Z según lo que saca de la pila
    bne se_puede
    stz ruta_ev + 13, x
    inc salto_trabado           ; había `end_jump` y la celda está ocupada
    rts
se_puede:
    ; La celda de destino, que `celda_del_evento` dejó en celda_x/celda_y.
    phx
    jsr mover_celda_a_evento
    plx
    lda salto_dx
    sta ruta_ev + 14, x
    lda salto_dy
    sta ruta_ev + 15, x
    ; Hacia dónde queda mirando. En el lugar no cambia nada.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    phx
    jsr direccion_del_salto
    plx
    sta ruta_ev + 8, x
sin_girar:
    jsr salto_de_ranura
    sta temp
    lda #0                      ; 256 menos lo de este cuadro, en ocho bits
    sec
    sbc temp
    sta ruta_ev + 13, x
    rts
.endproc

; `npc_px` y `npc_py` desde la celda de destino y lo que le queda al salto. Es
; la misma cuenta que `salto_posicion_heroe`, con la división al final.
.proc salto_posicion_npc
.a8
.i16
    jsr salto_a_celdas
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; la celda en las unidades de RM2k: por 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_px
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_py
    sep #$20
.a8
    rts
.endproc

; --- el salto de una ruta --------------------------------------------------
; Suma al salto lo que aporta una orden. Es el lazo de `BeginMoveRouteJump`: lo
; que hay entre `begin_jump` y `end_jump` **no se camina**, se suma, y sólo
; cuentan los `move_*` y los que giran. Todo lo demás —una espera, parar la
; animación, cambiar la velocidad— RM2k lo consume ahí adentro sin hacer nada,
; y el juego mete de las tres cosas.
;
; Entra en A el código de la orden; deja `salto_dx` y `salto_dy`.
.proc acumular_salto
.a8
.i16
    cmp #8                      ; los cuatro derechos y las cuatro diagonales:
    bcs no_mueve                ; adentro de un salto una diagonal aporta sus
                                ; dos ejes, que es lo que suma RM2k
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda salto_dx
    clc
    adc f:paso_dx, x
    sta salto_dx
    lda salto_dy
    clc
    adc f:paso_dy, x
    sta salto_dy
    rts
no_mueve:
    ; Los `face_*` no aportan desplazamiento, y girar sin moverse no se
    ; compila, así que adentro de un salto no queda nada más que hacer: RM2k
    ; consume el resto sin tocar nada, ni siquiera un `wait`.
    rts
.endproc

; ¿Se puede caer en la celda `celda_x`, `celda_y`? Vuelve con Z=0 si sí.
;
; No es lo mismo que poder pisarla caminando: es `CheckOrMakeWayEx` con el
; personaje saltando, que **saltea la cara que se deja** —de ahí que se pueda
; saltar desde un lugar del que no se podría caminar— y pide que la de destino
; sea pasable por los cuatro lados, no sólo por la que se entra.
.proc puede_caer
.a8
.i16
    rep #$20
.a16
    lda celda_x
    bmi no_16
    cmp mapa_ancho
    bcs no_16
    lda celda_y
    bmi no_16
    cmp mapa_alto
    bcs no_16
    sep #$20
.a8
    ; El que atraviesa paredes cae en cualquier celda del mapa: es el
    ; `if (self.GetThrough()) return true;` de `CheckOrMakeWayEx`, que va
    ; **después** de mirar los límites y antes de todo lo demás.
    lda atravesando
    beq mira_el_paso
    lda #1
    rts
mira_el_paso:
    jsr ptr_de_celda
    rep #$20
.a16
    jsr pass_del_ptr
    sep #$20
.a8
    and #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    cmp #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    bne no
    ; Y que no haya nadie parado ahí: el salto también es `MakeWay`, y mira a
    ; los demás igual que un paso.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    jsr celda_bloqueada
    bne no
    lda #1
    rts
.a16
no_16:
    sep #$20
.a8
no:
    lda #0
    rts
.endproc


; --- un NPC ----------------------------------------------------------------
.proc place_npc
.a8
.i16
    ldx npc_ofs
    rep #$20
.a16
    lda npc_buf + 0, x        ; su posición en el mapa
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda npc_buf + 2, x
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    ; Y el arco del salto, si está saltando. Va aparte y en ocho bits porque el
    ; byte 11 de la fila es el último de la ranura: leerlo de a dos se llevaría
    ; el primero de la siguiente.
    sep #$20
.a8
    stz temp + 1
    lda npc_buf + 11, x
    sta temp
    rep #$20
.a16
    lda obj_y
    sec
    sbc temp
    sta obj_y
    sep #$20
.a8
    lda npc_buf + 6, x
    sta obj_tile
    lda npc_buf + 7, x
    sta obj_attr
    jsr emit_object
    rts
.endproc

; --- el héroe --------------------------------------------------------------
.proc place_hero
.a8
.i16
    inc hero_drawn

    ; El frame del CharSet: los pasos 0 y 2 son los de los costados, y los
    ; pasos 1 y 3 son los dos la pose del medio.
    lda anim_step
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    sta temp

    ; La pose es dirección*3 + frame, y qué tile le toca lo dice la tabla del
    ; actor que está al frente del grupo. Antes se calculaba —el héroe era
    ; siempre el personaje 0 del banco, así que su bloque salía de una cuenta—,
    ; y eso dejó de valer cuando `ChangePartyMembers` puede cambiar el líder en
    ; caliente. La tabla además da lugar a tiles de más de ocho bits, que es lo
    ; que pasa en cuanto hay unos cuantos personajes en el banco.
    lda hero_dir
    asl a
    clc
    adc hero_dir                ; dirección * 3
    clc
    adc temp                    ; más el frame
    sta pose_heroe
    ; Sin grupo el puntero a la tabla queda en cero: no se dibuja nada.
    lda hero_poses + 2
    beq sin_dibujar
    ; El puntero a la pose: tres bytes por pose en la tabla del actor.
    lda pose_heroe
    asl a
    clc
    adc pose_heroe              ; por tres
    rep #$20
.a16
    and #$00FF
    tay
    lda [hero_poses], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [hero_poses], y
    sta vq_src + 2
    ; $FFFFFF es el centinela de "este actor no tiene gráfico". Le pasa al
    ; actor 10, DummyHero, que es con el que el juego arranca: RM2k tampoco
    ; dibuja nada.
    lda vq_src
    and vq_src + 1
    cmp #$FF
    beq sin_dibujar

    ; El tile es fijo: el héroe vive en el bloque 0 del banco, y lo que cambia
    ; son los tiles del bloque. Si la pose que hay en VRAM es otra, se encola
    ; la nueva y sube en el vblank que viene, junto con esta OAM.
    stz obj_tile
    lda #HERO_PRIORITY          ; por debajo de la capa que lo tapa
    ora hero_pal
    sta obj_attr
    lda pose_heroe
    cmp hero_pose_vram
    beq misma_pose
    sta hero_pose_vram
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne misma_pose
    lda #$FF
    sta hero_pose_vram          ; la cola estaba llena: el cuadro que viene
misma_pose:

    ; Un salto en curso corre el dibujo hacia atrás y lo levanta. La posición
    ; es la de RM2k, con la división **al final**: `x * 256 - dx * restante`
    ; sobre 16. Dividir el descuento por separado da un pixel de más o de menos
    ; cada vez que no es múltiplo de 16, o sea la mitad de los cuadros.
    lda ruta_salto
    sta salto_resta
    jsr alto_del_salto
    rep #$20
.a16
    lda hero_x
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda hero_y
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sec
    sbc salto_alto              ; el arco levanta el dibujo, no el orden
    sta obj_y
    sep #$20
.a8
    jsr emit_object
sin_dibujar:
    rts
.endproc

; --- un objeto en OAM ------------------------------------------------------
; Descarta lo que caiga fuera de la pantalla: la X del objeto tiene nueve bits y
; la Y sólo ocho, así que un objeto lejano daría la vuelta y aparecería del otro
; lado. Se corren los rangos 32 pixeles para poder compararlos sin signo.
; El +32 de las dos comparaciones corre el origen para que un objeto que asoma
; por arriba o por la izquierda —y que llega acá con la coordenada negativa— dé
; un número chico en vez de uno gigante, y una sola comparación sin signo
; resuelva los dos bordes.
.proc emit_object
.a8
.i16
    rep #$20
.a16
    lda obj_x
    clc
    adc #32
    cmp #(256 + 32)
    sep #$20
.a8
    bcs fuera
    rep #$20
.a16
    lda obj_y
    clc
    adc #32
    ; El borde de abajo no se descarta en 256 sino en 224, y no es lo mismo. La
    ; Y de OAM tiene 8 bits y la pantalla 224 líneas, así que los valores 224 a
    ; 255 quedan ambiguos: el PPU los lee siempre como "un poco más arriba del
    ; borde de arriba" y dibuja el objeto envuelto. Con el corte en 256, un NPC
    ; que se iba por abajo se guardaba con una Y de esa banda y reaparecía
    ; arriba, mostrando primero los pies y después entero.
    ;
    ; La ambigüedad hace falta y no se puede sacar: es la que hace que un objeto
    ; en y = -31 muestre su última línea en la línea 0. Lo que no puede pasar es
    ; que le llegue un objeto que de verdad está abajo.
    cmp #(224 + 32)
    sep #$20
.a8
    bcs fuera

    rep #$20
.a16
    lda oam_slot
    asl a
    asl a
    tax                         ; cuatro bytes por objeto
    sep #$20
.a8
    lda obj_x
    sta oam, x
    lda obj_y
    sta oam + 1, x
    lda obj_tile
    sta oam + 2, x
    lda obj_attr
    sta oam + 3, x

    ; Sus dos bits en la tabla chica: el noveno de la X y el tamaño.
    lda obj_x + 1
    and #$01
    ora obj_grande              ; 32x32 los personajes, 8x8 los dígitos
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
fuera:
    rts
.endproc

; Mete dos bits arriba del acumulador y lo corre. Después de cuatro objetos el
; byte queda armado en el orden que la consola espera.
.proc push_high
.a8
.i16
    pha
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    pla
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    ora high_acc
    sta high_acc

    lda oam_slot
    and #$03
    cmp #$03
    bne listo                   ; todavía no se completó el byte
    jsr store_high
listo:
    rts
.endproc

.proc store_high
.a8
.i16
    lda high_acc
    ldx high_ptr
    sta oam_high, x
    stz high_acc
    rep #$20
.a16
    inc high_ptr
    sep #$20
.a8
    rts
.endproc

; Al cerrar puede quedar un byte a medias. Se completa con objetos escondidos,
; que igual van a quedar con la Y fuera de pantalla.
.proc flush_high
.a8
.i16
completar:
    lda oam_slot
    and #$03
    beq listo
    lda #$02
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
    bra completar
listo:
    rts
.endproc

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
    and #PAD_A
    sta pad_a
    rts
.endproc

; --- carga al SPC700 -------------------------------------------------------
; El protocolo de la ROM interna del SPC700:
;
;   1. Espera a que salude con $AA en el puerto 0 y $BB en el 1.
;   2. Se le manda la dirección de destino por los puertos 2 y 3, un valor
;      distinto de cero por el 1, y $CC por el 0. Contesta con el mismo $CC.
;   3. Cada byte va por el puerto 1 y su índice por el 0; contesta el índice.
;   4. Para empezar otro bloque: la dirección nueva, algo distinto de cero por
;      el puerto 1, y el último índice más dos por el 0.
;   5. Para terminar: la dirección de entrada, un cero por el puerto 1, y el
;      último índice más dos por el 0. Ahí salta y arranca el driver.
;
; El $CC del paso 2 va sólo la primera vez; después manda el índice más dos.
.proc spc_upload
.a8
.i16
wait_ready:
    lda APUIO0
    cmp #$AA
    bne wait_ready
    lda APUIO1
    cmp #$BB
    bne wait_ready

    lda #$CC                    ; el arranque del primer bloque es fijo
    sta port0

    ; --- el driver ---
    ldx #.loword(spc_driver)
    stx source
    lda #^spc_driver
    sta source + 2
    ldx #SPC_DRIVER_ADDR
    ldy #SPC_DRIVER_SIZE
    jsr spc_block

    ; --- las muestras y su directorio ---
    ; Un mapa sin música no tiene muestras, y un bloque de cero bytes no es un
    ; bloque: el protocolo del IPL pide dirección, un puerto en no-cero y el
    ; índice, y del otro lado nadie contesta. La ROM se quedaba esperando en
    ; `wait_start` con la pantalla ya encendida y el mapa dibujado, o sea con
    ; toda la pinta de andar. Estuvo escondido mientras `musicdata.inc` lo
    ; generaba una receta aparte y siempre tenía un tema; apareció apenas el
    ; conversor empezó a emitir la música del mapa, y la mayoría no tiene.
    ldy #SPC_SAMPLES_SIZE
    cpy #$0000
    beq sin_muestras
    ldx #.loword(spc_samples)
    stx source
    lda #^spc_samples
    sta source + 2
    ldx #SPC_SAMPLES_ADDR
    ldy #SPC_SAMPLES_SIZE
    jsr spc_block
sin_muestras:

    ; --- cerrar y saltar al driver ---
    ldx #SPC_DRIVER_ADDR
    stx APUIO2
    stz APUIO1                  ; cero por el puerto 1 = ejecutar
    lda port0
    sta APUIO0
wait_jump:
    cmp APUIO0
    bne wait_jump

    stz token
    rts
.endproc

; --- un bloque de la carga -------------------------------------------------
; X = dirección de destino, Y = cuántos bytes, source = de dónde salen.
; port0 trae con qué valor arrancar y queda listo para el bloque siguiente.
.proc spc_block
.a8
.i16
    stx APUIO2                  ; dirección de destino
    lda #$01
    sta APUIO1                  ; distinto de cero = seguir transfiriendo
    lda port0
    sta APUIO0
wait_start:
    cmp APUIO0
    bne wait_start

    ldx #$0000                  ; el índice arranca en cero en cada bloque
send:
    cpy #$0000
    beq done
    lda [source]
    sta APUIO1
    txa
    sta APUIO0
wait_byte:
    cmp APUIO0
    bne wait_byte

    inx
    dey
    ; El mismo salto de banco que en `advance`: las muestras pasan de 32 KB,
    ; así que la subida al SPC700 también cruza de un banco de LoROM al otro.
    inc source
    bne send
    inc source + 1
    bne send
    lda #$80
    sta source + 1
    inc source + 2
    bra send

done:
    ; El próximo bloque arranca con el último índice más dos.
    txa
    inc a
    inc a
    sta port0
    rts
.endproc

.segment "BSS"
; Cuántas vueltas del lazo pasaron con el mundo congelado por un fundido. Las
; animaciones del mapa —la del ChipSet y la de los que animan quietos— cuentan
; `vueltas` **menos** éstas, así que no avanzan mientras la pantalla funde, y
; es lo que hace easyrpg-player: en una transición `Player::Update(false)` no
; llama a `IncFrame`, y el `GetFrameCounter` que mira `tilemap_layer.cpp:288`
; se queda quieto. `vueltas` no se puede frenar ahí: es el reloj del fundido
; mismo y el del arnés. Contándolas, el agua salía de un teletransporte con
; setenta ticks de fase de más.
vueltas_congeladas: .res 2


; Dos bits por evento, en vez de una cola. `FLAG_AUTO` dice si la página activa
; del evento es una automática que compiló —lo rehace el refresco— y
; `FLAG_ESPERA` es el `waiting_execution` de EasyRPG: quién tiene una página
; esperando turno, la haya puesto el barrido de las automáticas, la tecla de
; acción o un contacto.
;
; Reemplazan a una cola de ocho punteros que se llenaba y descartaba. Un bit
; por evento no puede desbordar ni marcar dos veces al mismo, que es justamente
; lo que hace posible remarcar en cada cuadro. Los dos bits van en la misma
; tabla y no en dos: 128 bytes más no entraban en los 7680 de RAM.
ev_flags:     .res EV_MAX
esperando_n:  .res 1     ; cuántos esperan, para no barrer 128 bytes por gusto
ev_corriendo: .res 2     ; de qué evento es la página que corre, o $FFFF
solo_auto:    .res 1     ; la pasada corta de `elegir_automaticas`
auto_n:       .res 1     ; cuántos eventos tienen una automática activa
refresco_cuadro: .res 1  ; un refresco a mitad de comando dejó la pasada larga
rp_ev_ant:    .res 2     ; el evento de la página anterior, en el refresco
arranques:    .res 1     ; presupuesto de páginas por cuadro; ver ARRANQUES_MAX
port0: .res 1

; Lo que `flush_video` le escribe a INIDISP al final del vblank: el brillo
; maestro de 0 a BRILLO_MAX. Nadie más lo escribe, y el porqué está en
; `prender`. Va en la BSS y no en la página directa porque se toca una vez por
; cuadro, en ningún lazo cerrado —y la página cero está llena—.
brillo:      .res 1

; El `FadeOutBGM`: si hay uno corriendo, cuánto le queda al volumen —de 65535 a
; cero— y cuánto baja por cuadro. El paso lo emite el conversor; ver
; `eventos.paso_de_fundido`.
bgm_fundido: .res 1
bgm_nivel:   .res 2
bgm_paso:    .res 2
dsp_valor:   .res 1     ; el byte que `escribir_dsp` le manda al SPC700

; La cámara corrida sin el héroe: `PanScreen`. Dónde está y adónde va, las dos
; en 1/16 de pixel y con signo, y cuánto corre por cuadro. `pan_px` y `pan_py`
; son lo mismo ya bajado a pixeles enteros, que es lo que suma `follow_camera`:
; se calcula una vez por cuadro en `pan_tick` y no en cada uso.
pan_x:      .res 2
pan_y:      .res 2
pan_dest_x: .res 2
pan_dest_y: .res 2
pan_paso:   .res 2
pan_px:     .res 2
pan_py:     .res 2

; El fundido de un teletransporte. Ver `fundido_tick`.
fundido:      .res 1    ; si hay uno corriendo
fundido_base: .res 1    ; el byte bajo de `vueltas` cuando arrancó
fundido_que:  .res 1    ; qué hay que hacer en el cuadro negro, y ya no
fundido_mapa: .res 2    ; a qué mapa, para los dos casos que cargan
FUNDIDO_NADA   = 0      ; ya se hizo
FUNDIDO_PUERTA = 1      ; una puerta: `cargar_mapa`, con su tope de saltos
FUNDIDO_SALTO  = 2      ; un Teleport a otro mapa
FUNDIDO_MISMO  = 3      ; un Teleport al mismo: sólo mover al héroe

; La ruta forzada del héroe, hasta RUTA_MAX órdenes. Vivía en la página cero y
; se mudó acá cuando el compositor de texto necesitó lugar: `paso_de_ruta` la
; lee una vez por cuadro, así que el ciclo de más por acceso no se nota.
ruta:        .res 32
; La frecuencia de la ruta puesta sobre el héroe, y la que trae el OP_ROUTE que
; se está leyendo. Es el contador de parada de RM2k: ver `ruta_tras_paso`.
ruta_frec:    .res 1
ruta_frec_op: .res 1

; La ventana de mensaje. `msg_abierto` es si hay una en pantalla, y los otros
; dos son pedidos que el lazo principal atiende al final del cuadro, con la
; pantalla apagada: no se puede escribir el tilemap con el PPU dibujando.
;
; Van acá y no en la página cero porque no se tocan en ningún lazo cerrado, y
; la página cero la necesita el compositor de texto.
msg_abierto: .res 1

; El estado del compositor. Un mensaje no aparece en el cuadro en que se lo
; pide: se compone de a MSG_CHARS caracteres por vuelta del lazo, renglón por
; renglón, y recién cuando está entero se prende el HDMA.
;
; El presupuesto por vuelta no es una optimización sino lo que mantiene honesta
; la comparación: si una vuelta se pasara del cuadro, `wait_vblank` agarraría el
; siguiente y el héroe caminaría la mitad de rápido que en la referencia.
msg_estado:  .res 1     ; 0 quieto, 1 componiendo, 2 listo
msg_linea:   .res 1     ; qué renglón se está armando
msg_lineas:  .res 1     ; cuántos trae el mensaje
msg_col:     .res 1     ; por qué caracter va
msg_largo:   .res 1     ; cuántos tiene el renglón
msg_cebada:  .res 1     ; si el buffer ya tiene el fondo del renglón
msg_subir:   .res 1     ; si hay un renglón listo para subir a la VRAM

; El renglón que se está componiendo: dos filas de celda por 30 columnas, en el
; formato de tiles de la consola. Los 48 bytes de más son para que la máscara
; del último caracter pueda escribir su segunda columna sin salirse: ahí siempre
; escribe cero, pero leer y escribir fuera del buffer sería pisarle a otro.
texto_buf:   .res (VENTANA_TEXTO_COLS * 2 * 32 + 48)

; Las dos tablas del HDMA de la ventana. Viven en RAM porque las dos primeras
; entradas llevan la cámara de este cuadro; la última, que es la de la ventana,
; no cambia nunca.
;
;   hdma_sc    [127][BG2SC mapa] [17][BG2SC mapa] [80][BG2SC ventana] [0]
;   hdma_ofs   [127][hofs][vofs] [17][hofs][vofs] [80][0][VENTANA_VOFS] [0]
;
; Los 144 scanlines de arriba van en dos tramos porque el contador de líneas de
; una entrada es de 7 bits y no llega a 144.
hdma_sc:  .res 7
hdma_ofs: .res 16

; OAM se arma en RAM y se manda entero por DMA cada cuadro. Es más simple que
; escribir entradas sueltas, y es lo que va a hacer falta cuando haya NPCs.
; Son 128 objetos de cuatro bytes más una tabla chica de dos bits por objeto.
oam:      .res 512
oam_high: .res 32

; La cola de subidas a VRAM: lo que hay que subir en el vblank que viene y no
; se puede subir ahora. Cada entrada son tres bytes de origen en el cartucho y
; dos de destino en palabras de VRAM, y lo que se sube es siempre una pose:
; 512 bytes en cuatro filas de 128, porque un objeto de 32x32 son cuatro filas
; de la grilla de nombres. Hasta VQ_POR_CUADRO por vblank; lo que sobra espera
; al siguiente, y quien lo encoló se entera de que no entró y lo vuelve a
; pedir. Ver `vram_encolar` y `vram_drenar`.
VQ_MAX = 8
VQ_POR_CUADRO = 5
VQ_STRIDE = 5
vq_n:      .res 1
vq:        .res VQ_MAX * VQ_STRIDE
vq_src:    .res 3
vq_dest:   .res 2
vq_hechas: .res 1
vq_filas:  .res 1
; La pose del héroe que hay en VRAM, o $FF si hay que subir la que toque.
hero_pose_vram: .res 1
pose_heroe:     .res 1

; Las tiras del mapa se arman acá fuera del vblank y se suben desde acá cuando
; empieza el siguiente, igual que OAM. Armarlas dentro del vblank no entraría, y
; escribirlas a la VRAM fuera de él las mostraría a medio hacer.
;
; Una columna son las 32 celdas de la ventana; una fila, las 64. Se indexan por
; la ranura, no por la celda del mapa: así el orden del buffer es exactamente el
; orden en que la VRAM las quiere y cada tira sale de un DMA.
; Las cuatro seguidas y en este orden: `limpiar_tilemaps` las borra de corrido.
tira_col:   .res WINDOW_ROWS * 2
tira_col2:  .res WINDOW_ROWS * 2
tira_row:   .res WINDOW_COLS * 2
tira_row2:  .res WINDOW_COLS * 2

; La tabla de NPCs del mapa cargado. Es la única de las tablas del mapa que se
; copia a RAM en vez de leerse con un puntero, y por una razón concreta:
; build_oam la recorre con un índice y en cinco desplazamientos distintos, así
; que con `lda tabla, x` sale una instrucción por campo y con un puntero salen
; tres. Copiarla cuesta un DMA por carga de mapa y entra de sobra: el mapa con
; más NPCs de todo el juego tiene 89, y acá entran 127, que es el tope que
; impone OAM.
npc_buf:  .res NPC_MAX * NPC_STRIDE
; Los gráficos a los que las rutas de este mapa cambian con la orden 34: dos
; bytes por gráfico, la entrada en `npc_poses` y la paleta. Se copia acá al
; cargar el mapa, como la tabla de NPCs, y por lo mismo: se lee con un índice
; —`lda ruta_graf_buf, x`— y eso direcciona el banco de datos.
;
; Copiarla y no leerla del cartucho con un puntero largo es lo que la hace
; barata: un `lda [ptr], y` pide el puntero en la página directa, y la página
; directa está llena. Cabe de sobra: el mapa que más pide de todo el juego
; pide seis. Ver RUTA_GRAF_MAX en snes_convert.py.
ruta_graf_buf: .res RUTA_GRAF_MAX * 2

; Dónde está cada evento del mapa, en celdas, por índice de la tabla. Se copia
; de la ROM al cargar el mapa, igual que la de NPCs, y por una razón que no es
; comodidad: **una ruta forzada la cambia**, y la siguiente ruta sobre el mismo
; evento arranca de donde quedó. Hay una página de este juego que manda a
; caminar nueve veces al mismo evento.
;
; Va todo el mapa y no sólo los eventos con gráfico: la mitad de las rutas de
; este juego caen sobre eventos invisibles, que no se dibujan pero sí tardan, y
; lo que tardan es lo que espera `ProceedWithMovement`.
ev_pos_buf: .res EV_MAX * EV_STRIDE

; Las rutas forzadas que están corriendo sobre eventos. Una ranura por ruta y no
; por evento: son pocas a la vez —la página que más manda a caminar mueve
; cuatro— y así la tabla no depende de cuántos eventos tenga el mapa.
;
;   +0  evento     el índice del evento, o $FF si la ranura está libre
;   +1  ptr        puntero de 24 bits a la primera orden, en el bytecode
;   +4  n          cuántas órdenes trae
;   +5  i          en cuál va
;   +6  movio      si este cuadro fue parte de un paso, que es lo que hace
;                  avanzar el ciclo de caminata
;   +7  cuadros    cuántos cuadros le faltan al paso en curso
;   +8  mirando    hacia dónde mira, o $FF si la ruta todavía no lo giró: ahí
;                  vale la dirección que trae su página
;   +9  espera     los cuadros que faltan de un `wait`
;   +12 banderas   bit 0 atraviesa paredes, bit 1 animación parada
;   +13 salto      lo que le queda al salto en curso, 0 si no hay
;   +14 salto_dx   y de dónde salió, en celdas y con signo
;   +15 salto_dy
;   +10 paso       en qué punto del ciclo de caminata va
;   +11 timer      cuántos cuadros faltan para el frame siguiente
;
; El paso es de 16 y no de 9 para que la ranura se indexe con cuatro
; corrimientos en vez de con una multiplicación.
; Los campos de la ranura: +0 el evento, +1..+3 el puntero a las órdenes, +4
; cuántas, +5 en cuál va, +6 si se movió en este cuadro, +7 lo que le falta al
; paso, +8 hacia dónde mira, +9 la espera, +10 y +11 la animación, +12 las
; banderas, +13 lo que le falta al salto y +14/+15 de dónde salió, +16 la
; frecuencia. El paso es potencia de dos por costumbre; sobra lugar.
RUTA_EV_STRIDE = 32
RUTA_EV_LIBRE = $FF
RUTA_EV_SIN_MIRAR = $FF     ; en +8: la ruta todavía no lo giró
ruta_ev:  .res RUTA_EV_MAX * RUTA_EV_STRIDE
; Cuántas de las doce vale la pena mirar: la más alta que se llegó a usar desde
; que se cargó el mapa, más una. **No baja** al liberarse una, y no hace falta
; que baje: una ranura que nunca se tomó tiene $FF en +0, así que buscar más
; allá no puede encontrar nada.
;
; Existe por `ranura_del_evento`, que corre **una vez por evento paralelo y por
; cuadro** y recorría las doce siempre. En el HQ de los Lazer Teeth hay once
; eventos con página paralela y **una sola ranura usada**: eran once recorridas
; de doce para encontrar una, y con eso el lazo se pasaba del cuadro. Es un byte
; porque en la BSS del banco 0 quedaba exactamente uno.
ruta_ev_tope: .res 1

; Los destellos corriendo. Una ranura por destello:
;
;   +0 blanco   0 el héroe, o el índice del evento más uno; $FF libre
;   +1 r, +2 g, +3 b   el color, de 0 a 31
;   +4 potencia, +5 cuadros, +6 k
;
; El paso es ocho para que la ranura se indexe con tres corrimientos.
FLASH_STRIDE = 8
FLASH_LIBRE = $FF
flash_ev:  .res FLASH_MAX * FLASH_STRIDE
; Lo que `paleta_con_destello` necesita mientras arma las tablas.
flash_dest: .res 1
flash_alfa: .res 1
flash_slot: .res 2
flash_ranura: .res 2
flash_parcial: .res 2
; La paleta de un destello, esperando el vblank para subirse.
flash_pend: .res 1
flash_pend_cgadd: .res 1
flash_buf: .res 32

; La celda que se está consultando, para `ptr_de_celda` y `puede_celda`. Va acá
; y no en la página directa porque se lee con direccionamiento absoluto, que
; alcanza: en la página directa sólo tiene que estar lo que se use como puntero
; con `[dp], y`, y ahí quedan doce bytes contados.
celda_x:  .res 2
celda_y:  .res 2
; Cuántos eventos tiene el mapa —para buscarlos por celda— y cuál se está
; mirando. Van acá y no en la página directa porque se leen con
; direccionamiento absoluto.
ev_total:   .res 2
ev_buscado: .res 2
; Qué disparo se está buscando: la tecla de acción o el contacto. Los dos usan
; la misma búsqueda —el evento de una celda y su página activa— y sólo cambia
; con qué trigger tiene que coincidir.
trigger_buscado: .res 2
; La fila del NPC que se está refrescando, y dónde queda en pixeles.
npc_fila: .res 2
npc_px:   .res 2
npc_py:   .res 2
; Lo que `refrescar_npc` se copia de la ranura antes de usar X para otra cosa.
; Si en este cuadro alguna ranura de ruta hizo algo. Es lo que decide si hay que
; volver a ordenar la tabla de NPCs, que si no cuesta todos los cuadros.
rutas_movieron: .res 1
; Las dos filas que se están comparando o intercambiando.
cmp_a:    .res 2
cmp_b:    .res 2
slot_cuadros: .res 1
slot_mira:    .res 1
slot_paso:    .res 1
; Las dos direcciones en curso. Van en dos bytes con el alto en cero porque se
; usan como índice, y X e Y son de dieciséis: `ldx dir` de un byte se llevaría
; puesto el de al lado. `ruta_dir` es la de la orden que se está ejecutando y
; tiene que sobrevivir a la llamada que usa `celda_dir`.
ruta_dir:  .res 2
celda_dir: .res 2
; Lo que la orden 34 saca de la tabla del mapa: de qué personaje van a salir
; las poses —$FF es "esconder la fila"— y con qué paleta.
graf_k:   .res 1
graf_pal: .res 1
; Lo que un paso en diagonal necesita mientras prueba sus dos eles: las dos
; componentes, y la celda de la que sale, porque `puede_celda` trabaja sobre
; `celda_x`/`celda_y` y hay que correrla hasta el codo y devolverla.
diag_v: .res 1
diag_h: .res 1
; Y la pose de la que sale el giro de una diagonal, ya resuelta: +8 puede
; traer todavía RUTA_EV_SIN_MIRAR.
diag_mira: .res 1
diag_x: .res 2
diag_y: .res 2

; El cronómetro. Los cuadros no se guardan enteros sino partidos en segundos y
; el resto adentro del segundo, y eso no es una optimización: es lo que evita
; dividir por 60 en cada cuadro. Bajar uno es `sub - 1`, y cuando `sub` da la
; vuelta baja un segundo; que el cronómetro esté en cero es `timer_seg = 0`,
; que es lo mismo que `cuadros / 60 == 0` de `Game_Party::UpdateTimers`.
;
; Los dos puntos parpadean con `sub`, que es `cuadros % 60`.
timer_seg:  .res 2
timer_sub:  .res 1
timer_activo:  .res 1
timer_visible: .res 1
; Los cuatro dígitos ya separados, de los minutos a los segundos. Se recalculan
; cuando cambia el segundo y no en cada cuadro: dividir por 60 y por 10 sesenta
; veces por segundo sería trabajo para nada.
timer_dig:  .res 4
; Y lo que `timer_oam` va llevando mientras dibuja: cuál de los cinco glifos
; va, cuál de sus dos mitades, y qué glifo le tocó.
timer_i:     .res 1
timer_mitad: .res 1
timer_glifo: .res 1
; El tamaño con el que sale el próximo objeto, ya corrido a su lugar en la
; tabla chica de OAM: $02 son los 32x32 de los personajes y $00 los 8x8 de los
; dígitos. Es lo único que los dos tamaños de OBSEL necesitan distinguir.
obj_grande:  .res 1

; Un bit por switch de RM2k. El juego consulta hasta el 1003 en las condiciones
; de página, así que con 1024 alcanza. Se limpian una sola vez al arrancar: en
; RM2k una partida nueva empieza con todos apagados.
; El oro del grupo, de 24 bits porque el tope de RM2k son 999999. Todavía no se
; muestra en ningún lado —el menú no existe— pero la rama de oro de
; `ConditionalBranch` lo pregunta, y `ChangeGold` lo mueve.
oro:      .res 3
switches: .res SWITCH_BYTES

; El tinte de pantalla escala cada canal por el mismo factor para todos los
; colores, así que en vez de hacer la cuenta 256 veces se hace 32: una tabla por
; canal, indexada por el valor de 5 bits que tenía.
; La saturación del tinte, en las mismas unidades que los otros tres. Va en la
; BSS y no en la página directa —donde están `tinte_r`, `tinte_g` y `tinte_b`—
; porque ahí ya no entra: sólo tiene que estar lo que se use como puntero con
; `[dp], y`, y quedaban doce bytes contados.
; Lo que la ruta forzada del héroe lleva además del cursor. Va en la BSS y no
; en la página directa —donde están `ruta_i` y `ruta_n`— porque ahí ya no entra:
; sólo tiene que estar lo que se use como puntero con `[dp], y`.
ruta_atraviesa: .res 1  ; walk_everywhere: la ruta ignora la colisión
ruta_anim_para: .res 1  ; stop_animation: la pose se queda en la del medio
ruta_salto:  .res 1     ; lo que le queda al salto en curso, 0 si no hay
; `ruta_salto_dx` y `ruta_salto_dy` vivían acá y no los leía nadie; su byte
; de más es el que paga `fundido_mapa` de dieciséis bits.
; Prendida mientras se prueba un paso de una ruta que atraviesa paredes. La
; miran `can_leave` y `can_enter`, que también usa la caminata con el pad: por
; eso vive acá y no adentro de la ruta.
atravesando: .res 2
; Quién está probando un paso o un salto, para chocar con los demás: el índice
; del evento, o MOVIL_HEROE. Y la capa de su página activa, o $FF si no tiene
; ninguna, que es un evento que no está —`IsActive()`— y no choca con nadie.
; Los pone `preparar_movil` para un evento y `heroe_bloqueado` para el héroe,
; y `mover_eventos` los devuelve al héroe al terminar, así que fuera de una
; ruta de evento siempre dicen "el héroe".
movil:       .res 1
movil_capa:  .res 1
; En qué capa está la página que `leer_pagina` acaba de leer. Va acá y no con
; los otros `pg_*` porque la página directa está llena —257 bytes en 256 con
; éste adentro— y se lee con direccionamiento absoluto, que alcanza.
pg_capa:     .res 1
; Y su ruta propia, la que camina sola: las banderas —bit 0 la tiene, 1 se
; repite, 2 se saltea lo bloqueado, 3 mira siempre igual, 4 la animación sigue
; quieto—, la frecuencia y la velocidad, y dónde están sus órdenes y cuántas.
; La velocidad va en todas las páginas, con ruta o sin ella: es la que usa una
; ruta forzada sobre el evento, como en RM2k.
pg_flags:    .res 1
pg_tile:     .res 1     ; +20..+23: lo que dibuja la página, ver leer_pagina
pg_attr:     .res 1
pg_pose:     .res 1
pg_pasa:     .res 1
; La celda que `pasa_con_evento` mira, y lo que encontró.
pasa_x:      .res 2
pasa_y:      .res 2
pasa_hallada: .res 1
pg_frec:     .res 1
pg_vel:      .res 1
pg_ruta:     .res 3
pg_ruta_n:   .res 1
; +24..+27, la condición por variable, no se copia: `condiciones_ok` la lee
; de la tabla, que es la única que la mira. La BSS está llena.
; Que un switch o el grupo cambió y hay que volver a mirar qué página está
; activa en cada evento: `rutas_de_pagina`, al empezar el cuadro siguiente.
refresco:    .res 1
; Lo que `rutas_de_pagina` va juntando: la página activa de cada evento con
; rutas propias, por su desplazamiento en la tabla; $FFFF si el evento no tiene
; rutas y $FFFE si las tiene y ninguna página cumple.
eleg_por_ev: .res EV_MAX * 2
rp_ev:       .res 2
slot_px:     .res 2
slot_dir:    .res 1
MOVIL_HEROE = $FF
CAPA_HEROE  = 1
; La celda a la que se quiere entrar, y lo que `celda_bloqueada` va mirando.
dest_x:      .res 2
; Por dónde va `build_row`: la columna que arma, con signo, y cuántas le
; faltan de las 64.
fila_col:    .res 2
tira_total:  .res 2
dest_y:      .res 2
otro_ev:     .res 1
trueque_a:   .res 1
trueque_b:   .res 1
; La sacudida de pantalla: dónde está en pixeles, con signo; cuántos cuadros le
; quedan; y con qué fuerza y velocidad. Y `pantalla_x`, que es la cámara más la
; sacudida: es lo que ven el scroll, la tabla HDMA y la OAM, mientras que el
; streaming del tilemap sigue mirando `camara_x`, porque la sacudida es un
; corrimiento del dibujo y no de lo que hay que tener cargado.
; El tinte se arma acá durante el cuadro —las tres paletas del mapa, teñidas,
; en su lugar de CGRAM— y se sube por DMA en el vblank siguiente. Antes
; `tinte_de_evento` apagaba la pantalla a mitad del cuadro para escribir CGRAM
; directo, y eso es un cuadro teñido a medias en el emulador y una franja
; negra en el hardware; lo delató la sacudida, que compara cuadro por cuadro.
cgram_sombra: .res 512
tinte_listo:  .res 1
; Y el destello de pantalla: si hay uno armado en `pal_buf` para subir,
; de dónde sube `dma_sombra`, y el destello en sí.
destello_listo: .res 1
sombra_origen:  .res 2
destello_rgb:   .res 3
destello_nivel: .res 2  ; a escala 256: el byte alto es lo que se dibuja
destello_resta: .res 1
dest_tab_r:  .res 32    ; las tres tablas, de 32 bytes cada una
dest_tab_g:  .res 32
dest_tab_b:  .res 32
dest_nivel:  .res 1
dest_hacia:  .res 1
dest_v:      .res 1
dest_d:      .res 1
dest_fin:    .res 2
; Cuántas poses puede subir `vram_drenar` este vblank: VQ_POR_CUADRO, salvo
; que el tinte ya se haya llevado parte del presupuesto.
vq_tope:      .res 1
; Los cuadros que van del reset, contados por la NMI: el arranque espera a que
; sean BOOT_CUADROS, y después sigue contando para `contar_perdidos`.
boot_cuadros: .res 1
nmi_visto:        .res 1  ; lo que valía al final de la vuelta anterior
cuadros_perdidos: .res 1  ; los que el lazo principal dejó pasar, saturado

sacudida_pos:    .res 2
sacudida_resta:  .res 2
sacudida_fuerza: .res 1
sacudida_vel:    .res 1
pantalla_x:      .res 2
sac_amp:   .res 1
sac_seno:  .res 1
sac_nuevo: .res 2
sac_corte: .res 2
sac_lo:    .res 2
sac_hi:    .res 2
capa_ev:     .res 2
capa_hallada: .res 1
salto_orden:   .res 1  ; el índice del `begin_jump` que se está armando
salto_trabado: .res 1  ; 1 si el salto no arrancó porque la celda está ocupada
; Lo que `armar_salto` va juntando mientras recorre las órdenes de un salto:
; cuánto se desplaza en celdas —con signo— y hacia dónde queda apuntando.
salto_dx:  .res 1
salto_dy:  .res 1
; Y el valor absoluto con el que `direccion_del_salto` compara los dos ejes.
mirar_abs: .res 2


; 1 mientras no haya ningún tema sonando. Va en la BSS y no en la página directa
; —donde vive el resto del estado de la música— porque ahí ya no entra.
music_apagada: .res 1
; Qué tema está sonando, en dos bytes con el alto en cero porque se usa como
; índice de las tres tablas de punteros y X es de dieciséis.
tema_actual: .res 2
; El desplazamiento del salto con el signo ya extendido a dieciséis bits, que
; es como se suma a la celda.
salto_dx16: .res 2
salto_dy16: .res 2
; Y lo que `dibujo_del_salto` recibe y devuelve: la posición en pixeles de quien
; salta, cuánto le queda al salto, y cuánto hay que levantar el dibujo.
salto_px:  .res 2
salto_py:  .res 2
salto_resta: .res 1
salto_alto: .res 2
salto_val:  .res 2
salto_prod: .res 2
salto_signo: .res 2

tinte_s:  .res 1
; Lo que la saturación necesita mientras corre. Los tres canales van en
; palabras y no en bytes para poder hacer `ldx sat_r` derecho: los índices son
; de dieciséis bits, así que un `ldx` sobre un byte se llevaría el de al lado.
sat_r:    .res 2
sat_g:    .res 2
sat_b:    .res 2
sat_luz:  .res 1     ; el gris del color, de cinco bits
sat_ch:   .res 1     ; el canal que se está saturando
sat_sube_marca: .res 1  ; si al sobresaturar el canal se aleja hacia arriba
sat_acc:  .res 3     ; la suma de los tres pesos, de 24 bits
peso_lo:  .res 1
peso_hi:  .res 1
peso_ch:  .res 1
; Si la tabla que se está armando es la mitad de arriba del hard light, o sea
; la que aclara. Ver `tabla_canal`.
tinte_espejo: .res 1
; Donde se copia una tabla mientras se la espeja. Ver `tabla_canal`.
tinte_tmp: .res 32

tabla_r:  .res 32
tabla_g:  .res 32
tabla_b:  .res 32
; Y las tres del tinte solo, que es de donde salen las otras. Van en un solo
; arreglo —el rojo en 0, el verde en 32 y el azul en 64— para poder indexarlas
; con un desplazamiento; el llamador dice cuál.
puro:     .res 96
puro_ofs: .res 2

; Y la paleta teñida se arma acá antes de subirla. No se puede teñir en CGRAM
; leyéndola y volviéndola a escribir: un segundo tinte se compondría con el
; primero. Siempre se parte de la paleta original, que está en la ROM.
pal_buf:  .res 512
; La sombra con el destello de pantalla encima —lo que arma `destellar_rango`
; y sube `subir_destello`— vive en este mismo lugar: la paleta teñida se arma y
; se copia a la sombra en el mismo cuadro, antes de que `destello_tick` escriba
; acá, y lo que hay se sube en el vblank que sigue. La RAM del banco 0 no daba
; para otros 512 bytes.

.segment "CODE"

; --- música ----------------------------------------------------------------
; El stream son opcodes: escribir un registro del DSP, esperar cuadros, o fin.
; Los tres los declara `tools/protocol/music.toml` y el equate sale generado: hasta
; el 2026-09-15 estaban escritos a mano acá **y** en tools/audio/snes_music.py, que
; es el que escribe el stream, sin nada que atara las dos copias.

; Un cuadro de música por cuadro de video, más uno extra cada cinco si la
; consola es PAL: seis cada cinco son exactamente 60 por cada 50.
.proc irq_musica
    jml f:rapida + RAPIDO       ; el vector cae en el banco 0: ver MEMSEL
rapida:
    ; Todo lo que se toca se guarda, B y D incluidos: se cae en el medio de
    ; cualquier cosa, el intérprete con B apuntando al bytecode entre ellas.
    rep #$30
.a16
.i16
    pha
    phx
    phy
    phb
    phd
    lda #0
    pha
    pld                         ; la página directa en cero
    sep #$20
.a8
    phk
    plb                         ; las tablas de la música, en el banco 0
    lda TIMEUP                  ; baja la bandera: si no, vuelve a entrar
    jsr music_tick
    rep #$30
.a16
.i16
    pld
    plb
    ply
    plx
    pla
    rti
.endproc

.proc music_tick
.a8
.i16
    ; El `FadeOutBGM` primero, y **afuera** del guard de `music_apagada`: es lo
    ; que lo va a prender cuando el volumen llegue a cero.
    lda bgm_fundido
    beq sin_fundido
    jsr bgm_fundido_tick
sin_fundido:
    ; Los efectos de sonido rodean a la música, y corren aunque esté callada:
    ; ver "los efectos de sonido".
    jsr se_antes
    lda music_apagada
    bne listo
    jsr music_frame
    lda es_pal
    beq listo
    inc pal_tick
    lda pal_tick
    cmp #5
    bcc listo
    stz pal_tick
    jsr music_frame             ; el cuadro que le falta a PAL
listo:
    jmp se_despues
.endproc

; Arranca desde el principio el tema cuyo índice trae A. El comienzo del stream
; trae la puesta a punto del DSP —los volúmenes, el directorio de muestras— así
; que volver a llamar acá es exactamente lo que hace un `PlayBGM`: empezar de
; cero.
;
; El cartucho lleva varios temas desde el 2026-09-06 y **todos comparten el
; banco de muestras**, que se sube una sola vez al arrancar: cambiar de tema es
; cambiar de stream y nada más, o sea que no cuesta ni un cuadro. De ahí que
; acá no haya nada que subir. Ver `Banco` en tools/audio/snes_music.py.
;
; Qué índice está sonando queda en `tema_actual`, que es lo que `music_frame`
; necesita para volver a empezar cuando el stream termina: sin eso el loop
; volvía siempre al primero.
.proc music_start
.a8
.i16
    ; El código principal la llama con la música andando —`PlayBGM`, el
    ; título—, y cambiar el puntero a medias con `irq_musica` leyéndolo sería
    ; tocar un tema desde la mitad de otro.
    pha
    jsr msu_parar               ; la pista de antes, si había
    pla
    pha
    jsr msu_arrancar
    beq sin_pista
    ; Con pista, el SPC700 se calla: el stream no corre y las voces sueltan.
    pla
    sta tema_actual
    stz tema_actual + 1
    php
    sei
    lda #1
    sta music_apagada
    stz bgm_fundido
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; las ocho voces sueltan, y KOF queda puesto
    ; Y el DSP hay que ponerlo a punto acá, que es lo que no estaba: lo hace
    ; el comienzo del stream —FLG sin el mute con que arranca el SPC700, el
    ; volumen general, y dónde está el directorio de muestras— y con pista el
    ; stream no corre nunca. Sin esto los efectos de sonido se disparan contra
    ; un DSP mudo: medido en la apertura, correr con el efecto y con el efecto
    ; suprimido daba **cero** muestras de diferencia.
    ;
    ; KOF se queda en $FF, que es lo que mantiene calladas las voces de la
    ; música; `se_despues` lo limpia solo cuando arranca un efecto.
    ldy #0
otro_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_listo
    tax                         ; dsp_par mira sólo el byte bajo de X
    lda dsp_init_val, y
    jsr dsp_par
    iny
    bra otro_init
init_listo:
    plp
    rts
sin_pista:
    ; El tema se queda en la pila: `tema_asegurar` pisa el acumulador, y
    ; `music_start_ya` lo necesita. Sacarlo antes dejaba el tema en $FF, el
    ; puntero del stream fuera de su tabla y la ROM muda a los diez cuadros.
    pla
    pha
    jsr tema_asegurar           ; que sus muestras estén en la ARAM
    pla
    php
    sei
    jsr music_start_ya
    plp
    rts
.endproc

.proc music_start_ya
.a8
.i16
    sta tema_actual
    stz tema_actual + 1
    ldx tema_actual
    lda tema_lo, x
    sta music
    lda tema_hi, x
    sta music + 1
    lda tema_bk, x
    sta music + 2
    stz wait_frames
    stz music_apagada
    ; Y se cancela el fundido que hubiera: el stream vuelve a escribir el
    ; volumen general al arrancar, así que seguir bajándolo apagaría el tema
    ; que el `PlayBGM` acaba de prender.
    stz bgm_fundido
    rts
.endproc

; Un cuadro del `FadeOutBGM`: baja el volumen general del DSP y, cuando llega a
; cero, corta el tema. Es `Game_System::BgmFade`, que en RM2k tampoco bloquea a
; la página que lo pidió.
;
; El nivel es de dieciséis bits y va de 65535 a cero; el volumen que se escribe
; es `TEMA_VOLUMEN` por su byte alto, con el multiplicador del hardware. La
; alternativa —bajar el registro de siete bits de a uno— daría noventa y seis
; escalones para un fundido de trescientos cuadros y se oiría a escalones.
.proc bgm_fundido_tick
.a8
.i16
    rep #$20
.a16
    lda bgm_nivel
    sec
    sbc bgm_paso
    bcs baja                    ; todavía queda
    lda #0
baja:
    sta bgm_nivel
    sep #$20
.a8
    lda bgm_nivel
    ora bgm_nivel + 1
    bne sigue
    stz bgm_fundido
    lda #1
    sta music_apagada           ; el tema se corta, como `BgmFade`
sigue:
    ; TEMA_VOLUMEN por el nivel, entre 256. **No con el multiplicador**: esto
    ; corre en `irq_musica`, y el código principal lo usa en treinta lugares
    ; —el divisor comparte el registro del resultado—; una interrupción entre
    ; su escritura y su lectura le cambiaría la cuenta. Así que a mano, de a
    ; un bit del nivel, con `dsp_valor` de lugar: es sólo de la música.
    ; El factor es el techo de lo que se está fundiendo: el volumen del tema
    ; si suena el SPC700, y el de la pista si hay MSU-1 —que no es 255, ver
    ; MSU_VOLUMEN_MAX—. Es un solo producto y un solo camino: con dos, el del
    ; MSU-1 se equivocaría solo.
    ldy #TEMA_VOLUMEN
    lda f:MSU_SUENA
    beq con_factor
    ldy #MSU_VOLUMEN_MAX
con_factor:
    rep #$20
.a16
    tya
    sta f:MSU_FACTOR            ; el lazo lo suma con `adc f:`: no hay dónde
    sep #$20                    ; tener un parcial, y `,s` no existe acá
.a8
    lda bgm_nivel + 1
    sta dsp_valor
    ldx #8
    rep #$20
.a16
    lda #0
bit_del_nivel:
    asl a
    sep #$20
.a8
    asl dsp_valor               ; sep y rep no tocan el carry
    rep #$20
.a16
    bcc sin_sumar
    clc
    adc f:MSU_FACTOR
sin_sumar:
    dex
    bne bit_del_nivel
    xba                         ; el byte alto del producto, o sea entre 256
    sep #$20
.a8
    sta dsp_valor
    ; Y lo mismo para la pista del MSU-1, que es la que suena si hay: el
    ; `FadeOutBGM` la baja igual. Al llegar a cero se corta.
    lda f:MSU_SUENA
    beq sin_msu
    ; Con pista, el fundido baja **su** volumen y no el del DSP. El volumen
    ; general del SPC700 es el que oyen los efectos de sonido, así que bajarlo
    ; acá los dejaba mudos hasta el `PlayBGM` siguiente, que es el único que lo
    ; repone.
    ;
    ; El producto ya está hecho arriba, y con el factor de la pista: `dsp_valor`
    ; es el nivel escalado contra MSU_VOLUMEN_MAX, que es el techo de la pista y
    ; no 255. Acá no hay ninguna cuenta que rehacer.
    lda dsp_valor
    sta MSU_VOLUMEN
    bne listo_msu
    jsr msu_parar               ; llegó a cero: la pista se corta
listo_msu:
    rts
sin_msu:
    lda #DSP_MVOL_L
    jsr escribir_dsp
    lda #DSP_MVOL_R
    jsr escribir_dsp
    rts
.endproc

; Le escribe `dsp_valor` al registro que trae A, con el testigo del SPC700. Es
; el mismo protocolo que usa `music_frame` con cada escritura del stream.
.proc escribir_dsp
.a8
.i16
    sta APUIO0
    lda dsp_valor
    sta APUIO1
    inc token                   ; el testigo le avisa al SPC700 que hay algo
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; La música al arrancar la ROM. `TEMA_ARRANQUE` es el tema del mapa donde la
; ROM arranca, o $FF si ese mapa no tiene —que es lo normal en este juego: los
; primeros mapas no traen música y la prende un `PlayBGM`—. Callado quiere
; decir que al DSP no se le escribe nada, así que no hay nada que silenciar.
.proc music_boot
.a8
.i16
    php
    sei
    jsr music_boot_ya
    plp
    rts
.endproc

.proc music_boot_ya
.a8
.i16
    ; Una partida cargada trae su propio tema —el que prendió el `PlayBGM` del
    ; evento— y `cargar_partida` ya lo dejó en `tema_actual` y `music_apagada`.
    ; Sin esto la partida arrancaría con el tema del mapa inicial de la ROM,
    ; que es el de la apertura y no el del lugar donde uno guardó.
    lda ranura
    cmp #$FF
    beq del_mapa                ; ninguna ranura cargada: el tema del mapa
    lda music_apagada
    bne callado                 ; se guardó en un momento sin música
    lda tema_actual
    jmp music_start
del_mapa:
    lda #TEMA_ARRANQUE
    cmp #$FF
    bne suena
callado:
    lda #1
    sta music_apagada
    rts
suena:
    jmp music_start
.endproc

; Un cuadro de música. El stream se recorre hasta toparse con una espera, y al
; llegar al final vuelve a empezar.
;
; Volver a empezar tiene una trampa: un stream **vacío** es un OP_END solo, así
; que reiniciar lleva a leer OP_END otra vez y el lazo no sale nunca. La ROM se
; colgaba en el primer cuadro, con la pantalla ya encendida y el mapa dibujado
; —o sea que parecía andar—. Estuvo escondido todo este tiempo porque
; `musicdata.inc` lo generaba una receta aparte y siempre tenía un tema de
; verdad; apareció apenas el conversor empezó a emitir la música del mapa, y la
; mayoría de los mapas del juego no tienen ninguna.
;
; La guarda es no reiniciar dos veces en el mismo cuadro: si después de volver
; al principio lo primero que hay es otro final, no hay nada que tocar.
.proc music_frame
.a8
.i16
    stz reinicio
    lda wait_frames
    beq run
    dec wait_frames
    rts

run:
    lda [music]
    jsr advance
    cmp #OP_END
    bne check_wait
    lda reinicio
    bne mudo
    inc reinicio
    lda tema_actual             ; se terminó: el mismo, de nuevo desde arriba
    jsr music_start_ya          ; adentro de la IRQ: sin `sei` y sin paquete
    bra run
mudo:
    ; Un stream vacío: nada que tocar, ni en este cuadro ni en los que vienen.
    ; Y hay que decirlo con la bandera, porque `advance` dejó el puntero **un
    ; byte más allá del final** y volver acá al cuadro siguiente leía ese byte
    ; como opcode. Era $FF de casualidad —el primer byte del bloque de al
    ; lado— hasta que las poses en caliente cambiaron el reparto de la ROM y
    ; pasó a ser $00: una escritura al DSP con su espera del SPC700, y otra, y
    ; otra, media pantalla por cuadro, y el lazo a la mitad de velocidad. Lo
    ; delataron tres casos de la tanda con un cuadro repetido, y una sonda de
    ; la línea de barrido al final de cada fase del lazo.
    lda #1
    sta music_apagada
    rts

check_wait:
    cmp #OP_WAIT
    bne write_dsp
    lda [music]
    jsr advance
    sta wait_frames
    beq run
    dec wait_frames
    rts

write_dsp:
    ; El registro y el valor, y los manda `dsp_musica`, que es la que sabe
    ; que la voz del efecto de sonido puede no ser de la música ahora.
    lda [music]                 ; registro del DSP
    jsr advance
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda [music]                 ; valor
    jsr advance
    jsr dsp_musica
    jmp run
.endproc

; Avanza el puntero de música un byte, devolviendo en A lo que ya se leyó.
;
; En LoROM cada banco expone sólo su mitad alta, $8000-$FFFF, así que el byte
; que sigue a $00FFFF no es $010000 sino $018000. Un incremento común de 24 bits
; caería en la RAM del banco 1 y leería basura. Con el tema entero más las
; muestras pasando los 64 KB, esto no es teórico: se cruza sí o sí.
.proc advance
.a8
.i16
; El acumulador trae el byte que el llamador acaba de leer, así que hay que
; devolverlo intacto: por eso el pha/pla en la rama del salto de banco.
    inc music
    bne done
    inc music + 1
    bne done                    ; si la parte alta no dio la vuelta, listo
    pha
    lda #$80                    ; dio la vuelta: al banco siguiente, en $8000
    sta music + 1
    pla
    inc music + 2
done:
    rts
.endproc


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
; `pruebas/herramientas/test_bancos.py`, sobre la tabla de símbolos.
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
; `armar_salto`. Son RUTA_PASOS de eventos.py.
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
; celda, y cuánto el salto: PASO_POR_VELOCIDAD y SALTO_VELOCIDADES de
; eventos.py. La 4 es la del héroe: 32 por cuadro, dos pixeles.
paso_por_vel:
    .word 4, 8, 16, 32, 64, 128

; `paso_por_vel` bajó a RODATA el 2026-09-13: tiene un solo acceso, y pasarlo
; por X cuesta cuatro bytes contra los doce de la tabla.
salto_por_vel:
    .byte 8, 12, 16, 24, 32, 64

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
; la regla de RM2k, y la misma que `rm2k.puede_pasar` escribe del lado de
; Python.
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


; Los HP de todos los actores llenos, a `FAR_HP`: el mismo DMA que el equipo,
; desde `actor_hpmax`. Corre en el reset, antes de cargar la partida, que lo
; pisa.
;
; Vive **fuera del banco 0** —se la llama con `jsl`— y por eso sus registros
; van con `f:`: en el banco 0 quedaban setenta bytes libres y ésta son
; cuarenta. Es el mismo motivo por el que la batalla entera vive allá.
;
; Existe desde que hay batallas. Hasta el 2026-09-12 los HP no eran estado —el
; menú los mostraba llenos siempre y `ChangeHP` compilaba a nada— y ahora una
; pelea los baja, así que tienen que arrancar en algún lado y viajar en la
; partida. Que arranquen llenos es RM2k: `Game_Actor::Setup`.
;
; Desde el 2026-09-13 hace lo mismo con los SP, que son estado por el mismo
; motivo: una habilidad cuesta su `sp_cost`. Son dos DMA iguales y no un lazo
; porque escribirlo dos veces cuesta menos que un lazo con tabla, y esto vive
; en RODATA, donde el cartucho sobra.
.proc hp_inicial_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_HP
    sta f:WMADDL
    lda #<(actor_hpmax)
    ora #(>(actor_hpmax) * 256)
    sta f:A1T0L
    lda #(ACTORES_N * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(actor_hpmax)
    sta f:A1B0
    lda #0
    sta f:DMAP0                 ; de A a B, de a un byte
    lda #$80                    ; WMDATA
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    ; y los SP, desde `actor_spmax`
    rep #$20
.a16
    lda #FAR_SP
    sta f:WMADDL
    lda #<(actor_spmax)
    ora #(>(actor_spmax) * 256)
    sta f:A1T0L
    lda #(ACTORES_N * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #0
    sta f:WMADDH
    lda #^(actor_spmax)
    sta f:A1B0
    lda #0
    sta f:DMAP0
    lda #$80
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
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
; Las cifras son las mismas celdas que el oro —`menu_cifra_celdas`, una por
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
    lda menu_cifra_celdas, x
    sta VMDATAL
    tya
    clc
    adc #32                     ; la celda de abajo
    sta VMADDL
    lda menu_cifra_celdas + 2, x
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

; El xorshift de la pelea, el mismo que `eventos.azar_siguiente` y que
; `lluvia_azar`, pero sobre `BA_SEM`, que tiene **semilla propia**: pelear no
; le corre el azar del mapa, que es lo que la referencia de pixeles supone
; cuando dice que una batalla no cuesta ningún tick.
.proc ba_azar
.a16
.i16
    lda BA_SEM
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor BA_SEM
    sta BA_SEM
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor BA_SEM
    sta BA_SEM
    xba
    and #$FF00
    eor BA_SEM
    sta BA_SEM
    rts
.endproc

; `temp` dividido `temp + 2`: el cociente queda en `temp` y el resto en
; `comp_and`. Desplazar y restar, dieciséis vueltas.
;
; Existe porque el divisor del hardware es de **ocho bits** y acá hay dos
; divisiones que no entran: el ajuste de acierto por agilidad divide por dos
; veces la agilidad —hasta 600 en este juego— y la varianza del daño, por el
; ajuste, que llega a lo mismo. Hacerlas con el divisor del hardware pedía
; recortar, y recortar cambia el número: los dos lados dejarían de dar igual.
;
; **El divisor tiene que ser menor que 32768**: el resto entra por un `rol` y
; uno más grande se saldría por arriba. Ninguno de los que se usan se acerca.
.proc ba_div
.a16
.i16
    stz comp_and
    ldy #16
lazo:
    asl temp
    rol comp_and
    lda comp_and
    sec
    sbc temp + 2
    bcc no_entra
    sta comp_and
    inc temp                    ; el bit del cociente que acaba de entrar
no_entra:
    dey
    bne lazo
    lda temp
    rts
.endproc

; A16 = n; vuelve con A16 = un número de 0 a n, inclusive. Es
; `Rand::GetRandomNumber(0, n)` de easyrpg con nuestro azar: ver
; `batalla.Azar.hasta`.
.proc ba_hasta
.a16
.i16
    inc a
    sta temp + 2
    jsr ba_azar
    sta temp
    jsr ba_div
    lda comp_and
    rts
.endproc

; A8 = el tanto por ciento; vuelve con A8 en 1 si salió y Z puesto según eso.
; Es `Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.
.proc ba_pct
.a8
.i16
    sta BA_T2
    rep #$20
.a16
    lda #99
    jsr ba_hasta
    sta BA_T0
    lda BA_T2
    and #$00FF
    cmp BA_T0                 ; C=1 si el tanto >= la tirada
    sep #$20
.a8
    beq no                      ; iguales: la tirada no es menor
    bcc no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; A16 por el byte de `BA_T2`, en A16. Dos productos del hardware, que es de
; ocho por ocho.
;
; Los registros van con `f:` y no absolutos: acá el banco de datos es $7E, así
; que un `sta WRMPYA` pelado escribiría en la WRAM y el producto saldría de un
; registro que nadie tocó. Costó una tarde y se veía como que todos los golpes
; fallaban.
.proc ba_mul
.a16
.i16
    sta temp
    sep #$20
.a8
    lda temp
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    sta comp_or23
    sep #$20
.a8
    lda temp + 1
    sta f:WRMPYA
    lda BA_T2
    sta f:WRMPYB
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda f:RDMPYL
    xba                         ; por 256: el byte alto pesa eso
    and #$FF00
    clc
    adc comp_or23
    rts
.endproc

; A8 a X, con el byte de arriba en cero. Existe para no escribir `ldx` sobre
; una variable de un byte: con los índices de dieciséis se llevaría el byte de
; al lado, que es la trampa que AGENTS.md nombra.
.proc ba_ax
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = el combatiente; X = su desplazamiento adentro de `BA_UNO`. Son 40 bytes,
; o sea treinta y dos más ocho: dos desplazamientos y una suma, sin tabla.
.proc ba_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por ocho
    sta temp + 2
    asl a
    asl a                       ; por treinta y dos
    clc
    adc temp + 2
    tax
    sep #$20
.a8
    rts
.endproc

; A8 = el combatiente; Z=0 si está vivo, o sea si la ranura existe y le quedan
; HP. **No usa `pl*`**: la trampa de siempre.
.proc ba_vivo
.a8
.i16
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #BAF_HAY
    beq no
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sep #$20
.a8
    beq no
    lda #1
    rts
no:
    lda #0
    rts
.endproc


; --- armar la pelea -------------------------------------------------------
;
; El grupo en las ranuras 0 a 3 y la tropa en las 4 a 11. Que el lugar sea fijo
; y no una lista compactada es lo que hace que un muerto se siga viendo en su
; renglón, como en la pantalla.

; El parámetro `A` —0 ataque, 1 defensa, 3 agilidad— del actor de `BA_S0`, en
; `BA_T2`. Va por memoria y no por el acumulador a propósito: una rutina que
; entra con A de ocho y sale con A de dieciséis deja al ensamblador creyendo
; otra cosa, y el `lda #1` que viniera detrás se comería el opcode siguiente.
; Ya pasó, y lo que se veía era un ataque de 999. Es `eq_parametro`, la misma que usa la pantalla de equipo: el del nivel
; más lo que suma cada pieza, topado en [1, 999]. `comp_col + 1` en cero es "no
; se está eligiendo nada", el camino simple de `eq_efectivo`. **Se lleva X.**
.proc ba_param
.a8
.i16
    sta comp_or01 + 2
    stz comp_or01 + 3
    stz comp_col + 1
    lda BA_S0
    sta comp_char
    stz comp_char + 1
    jsl f:ba_t_param
    rep #$20
.a16
    lda comp_dup
    sta BA_T2
    sep #$20
.a8
    rts
.endproc

.proc ba_armar
.a8
.i16
    ; Todas las ranuras vacías: la pantalla y los barridos miran `BAF_HAY`.
    lda #0
otra_ranura:
    pha
    jsr ba_x
    lda #0
    sta BA_UNO + BA_FLAGS, x
    pla
    inc a
    cmp #BA_COMB_MAX
    bcc otra_ranura
    stz BA_NACT
    stz BA_NENE

    ; --- el grupo ---
    lda #0
    sta BA_S1                 ; el lugar en el grupo
otro_actor:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    cmp grupo_n
    sep #$20
.a8
    bcc hay_lugar
    jmp grupo_listo
hay_lugar:
    lda BA_S1
    cmp #BA_GRUPO_MAX
    bcc hay_ranura
    jmp grupo_listo
hay_ranura:
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    bne con_actor
    jmp siguiente_actor         ; una ranura del grupo sin nadie
con_actor:
    sta BA_S0                 ; el actor del LDB
    ; Todo lo suyo a las palabras de paso: `ba_param` se lleva X, así que
    ; primero se junta y después se escribe con X puesto de una sola vez.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:actor_hpmax, x
    sta BA_S2                 ; los HP máximos del nivel
    lda f:actor_txt, x
    sta BA_S3                 ; y el número de texto de su nombre
    lda FAR_HP, x
    sta BA_S4                 ; los HP que trae la partida
    sep #$20
.a8
    lda #0
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S5                   ; el ataque
    sep #$20
.a8
    lda #1
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_S6                   ; la defensa
    sep #$20
.a8
    lda #3
    jsr ba_param
    rep #$20
.a16
    lda BA_T2
    sta BA_T0                   ; la agilidad
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S2
    sta BA_UNO + BA_HPMAX, x
    lda BA_S4
    sta BA_UNO + BA_HP, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_S3
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda #BA_ACIERTO_ACTOR
    sta BA_UNO + BA_HIT, x
    lda #0
    sta BA_UNO + BA_CRIT, x   ; ningún actor del ABL tiene golpe crítico
    lda BA_S0
    sta BA_UNO + BA_NUMERO, x
    lda #(BAF_HAY | BAF_ACTOR)
    sta BA_UNO + BA_FLAGS, x
    ; Y lo que las habilidades necesitan: los SP —que vienen de la partida,
    ; como los HP— y el espíritu, que hasta el 2026-09-13 no se leía porque
    ; ninguna cuenta lo pedía. Va en un segundo paso porque `ba_param` se
    ; lleva X y hay que volver a ponerlo.
    lda #2
    jsr ba_param                ; el espíritu, `eq_parametro` como los otros
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:actor_spmax, x
    sta BA_S3
    lda FAR_SP, x
    sta BA_S4
    sep #$20
.a8
    lda BA_S1
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_UNO + BA_SP, x
    lda BA_S3
    sta BA_UNO + BA_SPMAX, x
    lda BA_T2
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_S5
    sta BA_UNO + BA_BATK, x
    lda BA_S6
    sta BA_UNO + BA_BDEF, x
    lda BA_T0
    sta BA_UNO + BA_BAGI, x
    lda #0                      ; sin modificadores: la pelea recién empieza
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    inc BA_NACT
siguiente_actor:
    inc BA_S1
    jmp otro_actor
grupo_listo:

    ; --- la tropa ---
    ; El bytecode lleva el número de RM2k, así que hay que buscarlo. Una tropa
    ; que este cartucho no lleve es una pelea sin enemigos, y `batalla_correr`
    ; la gana sola: es lo mismo que hace el conversor con un tema que no entró.
    lda #$FF
    sta BA_TROPA_K
    lda #0
    sta BA_S1
busca:
    lda BA_S1
    cmp #TROPAS_N
    bcs sin_tropa
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    asl a
    tax
    lda f:tropa_id, x
    cmp BA_TROPA
    sep #$20
.a8
    beq la_tengo
    inc BA_S1
    bra busca
sin_tropa:
    rts
la_tengo:
    lda BA_S1
    sta BA_TROPA_K              ; para `escena_de`
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_n, x
    sta BA_S2                 ; cuántos miembros
    lda f:tropa_ini, x
    sta BA_S3                 ; dónde arranca su lista
    lda #0
    sta BA_S1                 ; el lugar en la tropa
otro_enemigo:
    lda BA_S1
    cmp BA_S2
    bcc hay_miembro
    jmp tropa_lista
hay_miembro:
    cmp #BA_ENEMIGOS_MAX
    bcc hay_ranura_ene
    jmp tropa_lista
hay_ranura_ene:
    rep #$20
.a16
    lda BA_S1
    clc
    adc BA_S3
    and #$00FF
    tax
    sep #$20
.a8
    lda f:tropa_miembro, x      ; el enemigo, como lugar en las tablas
    sta BA_S0
    ; Como con el actor: primero se junta todo y después se escribe, porque el
    ; índice largo es X y hay dos tablas que recorrer con él.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:enemigo_hp, x
    sta BA_S4
    lda f:enemigo_atk, x
    sta BA_S5
    lda f:enemigo_def, x
    sta BA_S6
    lda f:enemigo_agi, x
    sta BA_T0
    lda f:enemigo_txt, x
    sta BA_T1
    sep #$20
.a8
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enemigo_hit, x
    sta BA_T2
    lda f:enemigo_crit, x
    sta BA_T2 + 1
    lda BA_S1
    clc
    adc #BA_GRUPO_MAX
    jsr ba_x
    rep #$20
.a16
    lda BA_S4
    sta BA_UNO + BA_HP, x
    sta BA_UNO + BA_HPMAX, x
    lda BA_S5
    sta BA_UNO + BA_ATK, x
    lda BA_S6
    sta BA_UNO + BA_DEF, x
    lda BA_T0
    sta BA_UNO + BA_AGI, x
    lda BA_T1
    sta BA_UNO + BA_TXT, x
    sep #$20
.a8
    lda BA_T2
    sta BA_UNO + BA_HIT, x
    lda BA_T2 + 1
    sta BA_UNO + BA_CRIT, x
    lda BA_S1
    sta BA_UNO + BA_NUMERO, x
    lda #BAF_HAY
    sta BA_UNO + BA_FLAGS, x
    ; Lo de las habilidades: los SP, el espíritu y las cuatro bases. Un enemigo
    ; de este port no usa ninguna —`CreateEnemyActions` sólo le da el ataque
    ; básico— pero **las recibe**: Mental Hack le baja la defensa y el
    ; espíritu, y para eso hacen falta la base y el modificador.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    phx
    tax
    lda f:enemigo_sp, x
    sta BA_T0
    lda f:enemigo_spi, x
    sta BA_T1
    plx
    lda BA_T0
    sta BA_UNO + BA_SP, x
    sta BA_UNO + BA_SPMAX, x
    lda BA_T1
    sta BA_UNO + BA_SPI, x
    sta BA_UNO + BA_BSPI, x
    lda BA_UNO + BA_ATK, x
    sta BA_UNO + BA_BATK, x
    lda BA_UNO + BA_DEF, x
    sta BA_UNO + BA_BDEF, x
    lda BA_UNO + BA_AGI, x
    sta BA_UNO + BA_BAGI, x
    lda #0
    sta BA_UNO + BA_MATK, x
    sta BA_UNO + BA_MDEF, x
    sta BA_UNO + BA_MSPI, x
    sta BA_UNO + BA_MAGI, x
    sep #$20
.a8
    inc BA_NENE
    inc BA_S1
    jmp otro_enemigo
tropa_lista:
    rts
.endproc

; --- el golpe -------------------------------------------------------------
;
; `Normal::vExecute` de easyrpg: **tres tiros en este orden** —acierto,
; crítico y varianza— y el del crítico se hace aunque la chance sea cero. Ese
; orden es el contrato con `tools/port/batalla.py`: cambiarlo de un lado desfasa el
; azar del otro y no se ve hasta que un golpe da distinto.
;
; La fuente en `BA_MQUIEN` y el blanco en `BA_MBLA`. Deja el daño en
; `BA_MDANO`, con $FFFF si el golpe falló, y le baja los HP al blanco.
.proc ba_atacar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; el desplazamiento de la fuente
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; y el del blanco
    sep #$20
.a8

    ; --- el acierto, con el ajuste por agilidad ---
    ldx BA_S0
    lda #100
    sec
    sbc BA_UNO + BA_HIT, x      ; X es el desplazamiento, ya de dieciséis
    sta BA_T2                   ; 100 - acierto, que es el byte del producto
    rep #$20
.a16
    lda BA_UNO + BA_AGI, x
    bne agi_hay
    lda #1                      ; `max(1, GetAgi())` de CalcToHitAgiAdjustment
agi_hay:
    sta BA_S2                   ; la agilidad de la fuente
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_S2
    jsr ba_mul                  ; (100 - acierto) * (agiF + agiB)
    sta BA_S3
    lda BA_S2
    asl a
    sta temp + 2                ; el divisor: dos veces la agilidad
    ; Hacia arriba, que es lo que hace el truncado de easyrpg sobre `100 - x`:
    ; ver `batalla.acierto_por_agilidad`.
    lda BA_S3
    clc
    adc temp + 2
    dec a
    sta temp
    jsr ba_div
    sta BA_S3
    lda #100
    sec
    sbc BA_S3
    bpl acierto_listo
    lda #0
acierto_listo:
    sep #$20
.a8
    jsr ba_pct
    sta BA_S4                   ; 1 si pegó
    beq crit_cero
    lda BA_S0
    jsr ba_ax
    lda BA_UNO + BA_CRIT, x
    bra crit_tira
crit_cero:
    lda #0
crit_tira:
    jsr ba_pct
    sta BA_S5                   ; 1 si fue crítico
    lda BA_S4
    bne pega
    rep #$20
.a16
    lda #$FFFF
    sta BA_MDANO
    sep #$20
.a8
    rts

    ; --- el daño: max(0, atk / 2 - def / 4) ---
pega:
    rep #$20
.a16
    ldx BA_S0
    lda BA_UNO + BA_ATK, x
    lsr a
    sta BA_S2
    ldx BA_S1
    lda BA_UNO + BA_DEF, x
    lsr a
    lsr a
    cmp BA_S2
    bcc hay_dano
    lda #0
    sta BA_S2
    bra sin_varianza
hay_dano:
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    sta BA_S2
    sep #$20
.a8
    lda BA_S5
    beq sin_critico
    rep #$20
.a16
    ; El crítico triplica: `dmg *= 3`.
    lda BA_S2
    asl a
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
sin_critico:
    rep #$20
.a16
    ; La varianza de `VarianceAdjustEffect` con var = 4:
    ;     adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2
    lda BA_S2
    asl a
    asl a
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne ajuste_listo
    lda #1
ajuste_listo:
    sta BA_S3
    jsr ba_hasta                ; A16 sigue siendo el ajuste
    clc
    adc BA_S2
    sta BA_S2
    lda BA_S3
    lsr a
    sta BA_S3
    lda BA_S2
    sec
    sbc BA_S3
    bpl varianza_listo
    lda #0                      ; no puede pasar: 0,8 por el daño es positivo
varianza_listo:
    sta BA_S2
sin_varianza:
    sep #$20
.a8
    ; El que se defiende recibe la mitad: `AdjustDamageForDefend`.
    ldx BA_S1
    lda BA_UNO + BA_FLAGS, x
    and #BAF_DEF
    beq sin_defensa
    rep #$20
.a16
    lda BA_S2
    lsr a
    sta BA_S2
    sep #$20
.a8
sin_defensa:
    rep #$20
.a16
    lda BA_S2
    cmp #(BA_DANO_MAX + 1)
    bcc dano_listo
    lda #BA_DANO_MAX
dano_listo:
    sta BA_MDANO
    ldx BA_S1
    lda BA_UNO + BA_HP, x
    sec
    sbc BA_MDANO
    bpl hp_listo
    lda #0
hp_listo:
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; --- el turno -------------------------------------------------------------

; Las acciones de los enemigos: cada uno vivo ataca a un actor vivo al azar.
; Es `CreateEnemyActions`, con la única acción que los enemigos de las dos
; peleas de la intro tienen —"básica: atacar"—. **Un tiro por enemigo**, y va
; antes del orden de ejecución, que es como lo llama `SelectNextActor`.
;
; Si no queda ningún actor vivo se corta y los enemigos que faltaban se quedan
; sin acción, que es el `break` de `batalla.acciones_de_los_enemigos`: sin eso
; los dos lados tirarían distinta cantidad de veces.
.proc ba_acciones_enemigas
.a8
.i16
    lda #BA_GRUPO_MAX
    sta BA_S0
otro:
    lda BA_S0
    cmp #BA_COMB_MAX
    bcs listo
    lda BA_S0
    jsr ba_vivo
    beq siguiente
    ; Los actores vivos, en una lista, para elegir uno.
    lda #0
    sta BA_S1                   ; cuántos hay
    sta BA_S2
busca:
    lda BA_S2
    cmp #BA_GRUPO_MAX
    bcs buscados
    lda BA_S2
    jsr ba_vivo
    beq no_vive
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_CAND, x
    inc BA_S1
no_vive:
    inc BA_S2
    bra busca
buscados:
    lda BA_S1
    beq listo                   ; no queda nadie a quien pegarle
    rep #$20
.a16
    lda BA_S1
    and #$00FF
    dec a
    jsr ba_hasta
    tax
    sep #$20
.a8
    lda BA_CAND, x
    sta BA_T0                   ; el blanco elegido
    lda BA_S0
    asl a
    jsr ba_ax                   ; dos bytes de acción por combatiente
    lda #BA_ATACAR
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACC
    jsr ba_ax
    lda BA_S0
    sta BA_EJEC, x
    inc BA_NACC
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; El orden de ejecución: `agi + rand(0, agi / 4 + 3)` por cada uno que actúa,
; de mayor a menor y con un orden **estable**, que es lo que hace `std::sort`
; sobre una lista que ya viene apilada en el orden en que se empujó. Es
; `CreateExecutionOrder`. **Un tiro por acción**, en ese mismo orden: primero
; el grupo y después la tropa.
.proc ba_orden_ejecucion
.a8
.i16
    lda #0
    sta BA_S0
tira:
    lda BA_S0
    cmp BA_NACC
    bcs tirados
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; su desplazamiento
    lda BA_UNO + BA_AGI, x
    lsr a
    lsr a
    clc
    adc #3
    jsr ba_hasta
    sta BA_T0
    ldx BA_S1
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_T0
    sta BA_UNO + BA_SORT, x
    sep #$20
.a8
    inc BA_S0
    bra tira
tirados:
    ; Y el orden, por inserción: son doce como mucho, y queda **estable** si
    ; sólo se corre al que tiene arriba a uno estrictamente menor.
    lda #1
    sta BA_S0
afuera:
    lda BA_S0
    cmp BA_NACC
    bcs ordenado
    lda BA_S0
    jsr ba_ax
    lda BA_EJEC, x
    sta BA_S2                   ; el que se acomoda
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    sta BA_S3
    sep #$20
.a8
    lda BA_S0
    sta BA_S1
adentro:
    lda BA_S1
    beq poner
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SORT, x
    cmp BA_S3
    sep #$20
.a8
    bcs poner                   ; el de arriba es mayor o igual: se queda ahí
    lda BA_S1
    dec a
    jsr ba_ax
    lda BA_EJEC, x
    inx
    sta BA_EJEC, x
    dec BA_S1
    bra adentro
poner:
    lda BA_S1
    jsr ba_ax
    lda BA_S2
    sta BA_EJEC, x
    inc BA_S0
    bra afuera
ordenado:
    rts
.endproc

; --- la pantalla ----------------------------------------------------------
;
; De texto y sobre negro, en la misma grilla de 32 por 28 celdas que el equipo
; y la tienda. La geometría sale de `tools/port/pantallas.py` y el conversor emite
; las posiciones, así que la escribe **uno solo de los dos lados**. Arriba los enemigos, abajo el grupo, y el último renglón es o el
; menú de órdenes o los dos renglones del mensaje.

; `BA_T1` = A16 + `BA_S0` por lo que mide un renglón: dónde arranca el renglón
; número `BA_S0` de la lista que empieza en A16.
.proc ba_fila
.a16
.i16
    sta BA_T2
    lda BA_S0
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    clc
    adc BA_T2
    sta BA_T1
    rts
.endproc

; El cursor de escritura en la columna A16 del renglón `BA_T1`.
.proc ba_ir
.a16
.i16
    clc
    adc BA_T1
    sta eleg_tabla
    rts
.endproc

; El renglón de un combatiente: su nombre y sus HP, en gris si está muerto.
; A8 = el combatiente, `BA_T1` = dónde arranca su renglón, y el bit 0 de
; `BA_CONMAX` dice si además van los HP máximos —o sea si es del grupo—.
.proc ba_renglon
.a8
.i16
    sta BA_S4
    jsr ba_vivo
    beq muerto
    lda #0
    bra variante
muerto:
    lda #1
variante:
    sta temp + 1
    lda BA_S4
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S5                   ; su desplazamiento, que `pant_texto` pisa
    lda #BA_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_NOMBRE_ANCHO
    sta comp_dup + 3
    ldx BA_S5
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; "HP"
    rep #$20
.a16
    lda #BA_HP_DX
    jsr ba_ir
    sep #$20
.a8
    ldx #BA_TXT_HP
    jsl f:ba_t_texto
    ; y el número, de tres cifras, topado en 999 como en la referencia
    rep #$20
.a16
    lda #BA_HP_NUM_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HP, x
    cmp #1000
    bcc hp_cabe
    lda #999
hp_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    lda BA_CONMAX
    and #$01
    bne con_maximo
    rts
con_maximo:
    rep #$20
.a16
    lda #BA_BARRA_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$2F                    ; la barra entre los HP y su máximo
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda #BA_HPMAX_DX
    jsr ba_ir
    ldx BA_S5
    lda BA_UNO + BA_HPMAX, x
    cmp #1000
    bcc max_cabe
    lda #999
max_cabe:
    sta comp_dup
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    rts
.endproc

; El cursor ">" al principio del renglón `BA_T1`.
.proc ba_cursor
.a8
.i16
    stz temp + 1
    rep #$20
.a16
    lda #BA_CURSOR_DX
    jsr ba_ir
    sep #$20
.a8
    lda #$3E                    ; el cursor
    jsl f:ba_t_glifo
    rts
.endproc

; Un número sin espacios adelante, en `BA_T0`, donde diga `eleg_tabla`. Es lo
; que hace easyrpg al armar el mensaje de daño, que pega el número al nombre
; sin rellenar; `pant_numero` rellena, así que hay que decirle el ancho justo.
.proc ba_numero_justo
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    sta comp_dup
    ldx #1
    cmp #10
    bcc ancho_listo
    ldx #2
    cmp #100
    bcc ancho_listo
    ldx #3
ancho_listo:
    sep #$20
.a8
    txa                         ; el ancho: con M en 8 sólo viaja el byte bajo
    sta comp_dup + 2
    stz temp + 1
    jsl f:ba_t_numero
    rts
.endproc

; El nombre del combatiente A8 donde diga `eleg_tabla`, entero.
.proc ba_nombre
.a8
.i16
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_TXT, x
    tax
    sep #$20
.a8
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; Un término del juego —X ya puesto— donde diga `eleg_tabla`, entero.
.proc ba_termino
.a8
.i16
    lda #255
    sta comp_dup + 3
    stz temp + 1
    jsl f:ba_t_texto
    rts
.endproc

; Los dos renglones del mensaje, según `BA_MTIPO`. Todas las palabras salen
; del LDB —`attacking`, `enemy_damaged`, `victory`...— y se arman como
; `game_message_terms.cpp`: el nombre pegado al término, y en el de daño el
; número en el medio. Ninguna es nuestra.
; --- usar un ítem en la pelea ---------------------------------------------
;
; `Game_BattleAlgorithm::Item` con lo que este port sabe hacer: las medicinas
; que recuperan HP. Qué entra en la lista y cuánto cura no se decide acá sino
; en `batalla.item_usable_en_batalla` y `batalla.curacion`, que es el modelo con
; el que `pruebas/rpgmaker/test_batalla.py` predice el HP exacto; el conversor emite el
; resultado en `item_batalla`, `item_cura_rate` e `item_cura_hp`.
;
; Todo esto corre con el banco de datos en $7E, así que **el inventario se lee
; con direccionamiento absoluto**: `FAR_ITEMS` vive en ese banco y en él las
; direcciones son las mismas. Las tablas del cartucho van con `f:`.

; La lista de lo que se puede usar: un `k` por byte en `BA_ITEM_LISTA` y
; cuántos en `BA_ITEM_N`. Recorre los ítems que la ROM conoce en el orden del
; conversor, que es el del número de RM2k, como `Game_Party`.
.proc ba_items_lista
.a8
.i16
    lda #0
    sta BA_ITEM_N
    sta BA_S0                   ; el `k` que se mira
otro:
    lda BA_S0
    cmp #ITEMS_ROM
    bcs listo
    lda BA_S0
    jsr ba_ax
    lda f:item_batalla, x
    beq siguiente
    lda BA_S0
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x            ; su número de RM2k
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x            ; cuántos hay en el inventario
    beq siguiente
    lda BA_ITEM_N
    jsr ba_ax
    lda BA_S0
    sta BA_ITEM_LISTA, x
    inc BA_ITEM_N
    lda BA_ITEM_N
    cmp #BA_ITEM_MAX
    bcs listo
siguiente:
    inc BA_S0
    bra otro
listo:
    rts
.endproc

; El `k` del lugar A de la lista. Sólo A y X.
.proc ba_item_de_lista
.a8
.i16
    jsr ba_ax
    lda BA_ITEM_LISTA, x
    rts
.endproc

; Uno menos en el inventario del `k` que trae A. Es lo que hace RM2k al
; elegirlo y no al usarlo: si no, el último de un ítem se podría repartir entre
; dos actores en el mismo turno.
.proc ba_item_gastar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    beq listo
    dec a
    sta FAR_ITEMS, x
listo:
    rts
.endproc

; Cuánto cura el `k` de A sobre el combatiente `BA_MBLA`. Entra con A de ocho
; bits y sale con A de dieciséis.
;
;     hp = recover_hp_rate * GetMaxHp() / 100 + recover_hp
;
; topado contra lo que le falta al blanco, que es el `ChangeHp` de easyrpg. El
; producto entra en una palabra porque el conversor corta si algún actor tiene
; más de 655 HP.
.proc ba_item_cura
.a8
.i16
    sta BA_S3                   ; el `k`
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4                   ; el desplazamiento del blanco
    sep #$20
.a8
    lda BA_S3
    jsr ba_ax
    lda f:item_cura_rate, x
    sta BA_T2                   ; el byte del producto
    ldx BA_S4
    rep #$20
.a16
    lda BA_UNO + BA_HPMAX, x
    jsr ba_mul                  ; rate * hp_max, en una palabra
    sta temp
    lda #100
    sta temp + 2
    jsr ba_div
    sta BA_S5
    lda BA_S3
    and #$00FF
    asl a
    tax
    lda f:item_cura_hp, x
    clc
    adc BA_S5
    sta BA_S5                   ; lo que curaría
    ; y lo que le falta al blanco, que es el tope
    ldx BA_S4
    lda BA_UNO + BA_HPMAX, x
    sec
    sbc BA_UNO + BA_HP, x
    cmp BA_S5
    bcc topado
    lda BA_S5
topado:
.a16
    rts
.endproc

; El ítem que eligió el actor `BA_MQUIEN`, sobre `BA_MBLA`: cura, anota cuánto
; y deja el mensaje listo. No tira azar: un ítem no falla ni lo esquiva nadie,
; y **el blanco muerto no se reapunta**, que es lo contrario de un ataque.
.proc ba_item_usar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_ax
    lda BA_ACC_ITEM, x
    sta BA_MITEM
    jsr ba_item_cura
.a16
    sta BA_MCURA
    ldx BA_S4                   ; el desplazamiento del blanco, de `ba_item_cura`
    lda BA_UNO + BA_HP, x
    clc
    adc BA_MCURA
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; --- ejecutar una habilidad -----------------------------------------------
;
; `Game_BattleAlgorithm::Skill::vStart` y `vExecute`. **El orden en que consume
; azar es el contrato con `batalla.Batalla.usar_habilidad`**: una de switch
; termina antes de cualquier tiro; después va el crítico, que se tira siempre
; aunque la chance sea cero; después la varianza; y después un tiro contra el
; acierto por cada cosa que la habilidad afecta, en el orden HP, SP, ataque,
; defensa, espíritu y agilidad.

; `Algo::VarianceAdjustEffect`: A16 = el efecto, `BA_S5` = la varianza.
;
;     adj = max(1, var * efecto / 10); efecto += rand(0, adj) - adj / 2
;
; **Sólo tira si la varianza y el efecto son mayores que cero**, que es el `if`
; de easyrpg: sin esa condición los dos lados se irían de fase en el tiro
; siguiente cada vez que pasara por acá una habilidad que no hace daño.
;
; El golpe normal tiene la suya escrita adentro de `ba_atacar` con la varianza
; en cuatro; ésta salió para las habilidades, que traen la suya en el LDB.
.proc ba_varianza
.a16
.i16
    sta BA_T0
    bmi sin_tirar
    beq sin_tirar
    sep #$20
.a8
    lda BA_S5
    beq sin_varianza
    sta BA_T2
    rep #$20
.a16
    lda BA_T0
    jsr ba_mul                  ; la varianza por el efecto
    sta temp
    lda #10
    sta temp + 2
    jsr ba_div
    bne ajuste_listo
    lda #1                      ; `max(1, ...)`
ajuste_listo:
    sta BA_T1
    jsr ba_hasta                ; A16 sigue siendo el ajuste
    clc
    adc BA_T0
    sta BA_T0
    lda BA_T1
    lsr a
    sta BA_T1
    lda BA_T0
    sec
    sbc BA_T1
    sta BA_T0
sin_tirar:
    lda BA_T0
    rts
sin_varianza:
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    rts
.endproc

; Un modificador de parámetro se mueve `BA_MEFECTO` y el parámetro efectivo se
; rehace: `CanChangeAtkModifier` y sus hermanas, más `AdjustParam`.
;
;   BA_S4 = el desplazamiento del blanco adentro de `BA_UNO`
;   BA_S5 = el del modificador, BA_S6 = el del base, BA_T1 = el del efectivo
.proc ba_mod
.a8
.i16
    rep #$20
.a16
    lda BA_S4
    clc
    adc BA_S5
    tax
    lda BA_UNO, x
    clc
    adc BA_MEFECTO
    sta temp                    ; el modificador que se pide
    lda BA_S4
    clc
    adc BA_S6
    tax
    lda BA_UNO, x
    sta BA_T0                   ; el parámetro base. **Las dos de paso son
                                ; `BA_T0` y `BA_T2` y no `BA_S2` y `BA_S3`**:
                                ; el que llama lleva en `BA_S3` qué toca la
                                ; habilidad y en `BA_S0` su acierto, y los
                                ; necesita en las cuatro vueltas
    ; El tope de arriba es el base, y el de abajo su mitad con signo menos.
    ; Los números de este juego andan en centenas, así que el `bmi` sobre la
    ; resta alcanza: nada se acerca a los 32768 donde se daría vuelta.
    lda temp
    sec
    sbc BA_T0
    bmi arriba_ok
    lda BA_T0
    sta temp
arriba_ok:
    lda BA_T0
    lsr a
    eor #$FFFF
    inc a
    sta BA_T2                   ; -(base / 2)
    lda temp
    sec
    sbc BA_T2
    bpl abajo_ok
    lda BA_T2
    sta temp
abajo_ok:
    lda BA_S4
    clc
    adc BA_S5
    tax
    lda temp
    sta BA_UNO, x               ; el modificador nuevo
    clc
    adc BA_T0                   ; base + modificador
    bmi al_uno
    cmp #1
    bcs no_es_cero
al_uno:
    lda #1
    bra efectivo_listo
no_es_cero:
    cmp #(BA_PARAM_MAX + 1)
    bcc efectivo_listo
    lda #BA_PARAM_MAX
efectivo_listo:
    sta BA_T2
    lda BA_S4
    clc
    adc BA_T1
    tax
    lda BA_T2
    sta BA_UNO, x
    sep #$20
.a8
    rts
.endproc

; Prende el switch de `BA_T0`, que es el `switch_id` del LDB tal cual, como
; hace `item_switch` con el suyo. No se llama a `poner_switch`: vive en el
; banco 0 y la pelea corre con el banco de datos en $7E, así que la máscara se
; arma acá con un corrimiento en vez de leerse de una tabla del cartucho.
.proc ba_switch
.a8
.i16
    rep #$20
.a16
    lda BA_T0
    lsr a
    lsr a
    lsr a
    tax                         ; qué byte del bitmap
    lda BA_T0
    and #$0007
    tay                         ; y qué bit
    sep #$20
.a8
    lda #1
corre:
    cpy #0
    beq mascara_lista
    asl a
    dey
    bra corre
mascara_lista:
    ora switches, x
    sta switches, x
    lda #1
    sta refresco                ; las páginas que lo piden pueden cambiar
    rts
.endproc

; El efecto de la habilidad `BA_MHAB` de `BA_MQUIEN` sobre `BA_MBLA`, **sin la
; varianza**: `Algo::CalcSkillEffect`. Deja el resultado en `BA_MEFECTO`, ya
; recortado por abajo en cero.
.proc ba_hab_efecto
.a8
.i16
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S0                   ; el desplazamiento de la fuente
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S1                   ; y el del blanco
    ; el `k` de la habilidad, por dos para las tablas de palabra
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_power, x
    sta BA_S2                   ; el acumulador del efecto
    sep #$20
.a8
    ; + physical_rate * atk / 20
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_fis, x
    sta BA_T2
    beq sin_fisico
    ldx BA_S0
    rep #$20
.a16
    lda BA_UNO + BA_ATK, x
    jsr ba_mul
    sta temp
    lda #20
    sta temp + 2
    jsr ba_div
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
sin_fisico:
    ; + magical_rate * spi / 40
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_mag, x
    sta BA_T2
    beq sin_magico
    ldx BA_S0
    rep #$20
.a16
    lda BA_UNO + BA_SPI, x
    jsr ba_mul
    sta temp
    lda #40
    sta temp + 2
    jsr ba_div
    clc
    adc BA_S2
    sta BA_S2
    sep #$20
.a8
sin_magico:
    ; Contra un enemigo y sin `ignore_defense`, se le restan su defensa y su
    ; espíritu. `SkillTargetsEnemies` es el bit 6 de `hab_afecta` y el bit 7 es
    ; `ignore_defense`.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_afecta, x
    sta BA_S3
    and #$40
    beq sin_resta
    lda BA_S3
    and #$80
    bne sin_resta
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_fis, x
    sta BA_T2
    beq sin_resta_fis
    ldx BA_S1
    rep #$20
.a16
    lda BA_UNO + BA_DEF, x
    jsr ba_mul
    sta temp
    lda #40
    sta temp + 2
    jsr ba_div
    sta BA_T0
    lda BA_S2
    sec
    sbc BA_T0
    sta BA_S2
    sep #$20
.a8
sin_resta_fis:
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_mag, x
    sta BA_T2
    beq sin_resta
    ldx BA_S1
    rep #$20
.a16
    lda BA_UNO + BA_SPI, x
    jsr ba_mul
    sta temp
    lda #80
    sta temp + 2
    jsr ba_div
    sta BA_T0
    lda BA_S2
    sec
    sbc BA_T0
    sta BA_S2
    sep #$20
.a8
sin_resta:
    rep #$20
.a16
    lda BA_S2
    bpl no_negativo
    lda #0                      ; `max(0, effect)`
no_negativo:
    sta BA_MEFECTO
    sep #$20
.a8
    ; El crítico, que para una habilidad del LDB **siempre da que no**: la
    ; chance que `CalcCriticalHitChance` recibe es
    ; `easyrpg_critical_hit_chance`, que vale 0 y no -1. El tiro se hace igual,
    ; porque si no los dos lados se irían de fase.
    lda #0
    jsr ba_pct
    beq sin_critico
    rep #$20
.a16
    lda BA_MEFECTO
    sta temp
    asl a
    clc
    adc temp                    ; por tres
    sta BA_MEFECTO
    sep #$20
.a8
sin_critico:
    rts
.endproc

; Los HP del blanco se mueven `BA_MEFECTO`. Curar no mata —el
; `max(-(cur_hp - 1), hp_effect)` de `vExecute`— y el daño lo parte al medio el
; que se está defendiendo, con la división de C++, que **trunca hacia cero**.
.proc ba_hab_hp
.a8
.i16
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    lda BA_MEFECTO
    bmi hace_dano
    sta BA_T0
    bra aplica
hace_dano:
    sep #$20
.a8
    ldx BA_S4
    lda BA_UNO + BA_FLAGS, x
    and #BAF_DEF
    beq sin_defensa
    rep #$20
.a16
    lda BA_MEFECTO
    eor #$FFFF
    inc a
    lsr a
    eor #$FFFF
    inc a                       ; la mitad truncada hacia cero
    sta BA_T0
    bra aplica
sin_defensa:
.a8
.i16
    rep #$20
.a16
    lda BA_MEFECTO
    sta BA_T0
aplica:
.a16
.i16
    ldx BA_S4
    lda BA_UNO + BA_HP, x
    clc
    adc BA_T0
    bmi en_cero
    cmp BA_UNO + BA_HPMAX, x
    bcc cabe
    lda BA_UNO + BA_HPMAX, x
    bra cabe
en_cero:
    lda #0
cabe:
    sta BA_UNO + BA_HP, x
    sep #$20
.a8
    rts
.endproc

; Y los SP, igual pero sin defensa que valga. Ninguna de las siete lo usa; está
; porque `vExecute` lo hace y porque el tiro que lo precede ya se hizo.
.proc ba_hab_sp
.a8
.i16
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    clc
    adc BA_MEFECTO
    bmi sp_en_cero
    cmp BA_UNO + BA_SPMAX, x
    bcc sp_cabe
    lda BA_UNO + BA_SPMAX, x
    bra sp_cabe
sp_en_cero:
    lda #0
sp_cabe:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
    rts
.endproc

; La habilidad que eligió `BA_MQUIEN`, sobre `BA_MBLA`. Deja el mensaje listo.
.proc ba_hab_usar
.a8
.i16
    lda BA_MQUIEN
    jsr ba_ax
    lda BA_ACC_HAB, x
    sta BA_MHAB
    ; --- `vStart`: el costo, antes que nada y sin tirar azar ---
    jsr ba_hab_costo
    sta BA_T2
    stz BA_T2 + 1               ; la resta de abajo es de dieciséis bits y
                                ; `hab_sp` es de ocho: sin esto el byte de
                                ; arriba es el que dejó el que pasó por acá
                                ; antes, y los SP quedaban en cero
    lda BA_MQUIEN
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_SP, x
    sec
    sbc BA_T2
    bpl sp_ok
    lda #0                      ; no puede pasar: sin SP no se elige
sp_ok:
    sta BA_UNO + BA_SP, x
    sep #$20
.a8
    ; --- una de switch prende su switch y no hace nada más ---
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_tipo, x
    cmp #BA_HAB_TIPO_SWITCH
    bne no_es_switch
    rep #$20
.a16
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_switch, x
    sta BA_T0
    lda #0
    sta BA_MEFECTO
    sep #$20
.a8
    jmp ba_switch
no_es_switch:
    jsr ba_hab_efecto
    ; la varianza, con el `variance` de la habilidad
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_var, x
    sta BA_S5
    rep #$20
.a16
    lda BA_MEFECTO
    jsr ba_varianza
    ; el tope del daño, que es el mismo de un golpe
    cmp #(BA_DANO_MAX + 1)
    bcc efecto_cabe
    lda #BA_DANO_MAX
efecto_cabe:
    sta BA_MEFECTO
    sep #$20
.a8
    ; Si apunta a enemigos el efecto es negativo: `SetIsPositive` es
    ; `SkillTargetsAllies`, y `vExecute` da vuelta el signo cuando no lo es.
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_afecta, x
    sta BA_S3                   ; qué toca, que ya no se vuelve a leer
    and #$40
    beq es_positivo
    rep #$20
.a16
    lda BA_MEFECTO
    eor #$FFFF
    inc a
    sta BA_MEFECTO
    sep #$20
.a8
es_positivo:
    ; el acierto, que las siete traen en 100
    lda BA_MHAB
    jsr ba_ax
    lda f:hab_hit, x
    sta BA_S0                   ; el acierto, que sobrevive a los `jsr`
    ; --- los HP ---
    lda BA_S3
    and #$01
    beq sin_hp
    lda BA_S0
    jsr ba_pct
    beq sin_hp
    jsr ba_hab_hp
sin_hp:
    ; --- los SP ---
    ;
    ; Ninguna de las siete que el grupo de la intro sabe los toca, **pero el
    ; tiro va igual**: `vExecute` lo hace y sacarlo desfasaría el azar.
    lda BA_S3
    and #$02
    beq sin_sp
    lda BA_S0
    jsr ba_pct
    beq sin_sp
    jsr ba_hab_sp
sin_sp:
    ; --- los cuatro parámetros, en el orden de `vExecute` ---
    lda BA_MBLA
    jsr ba_x
    rep #$20
.a16
    txa
    sta BA_S4
    sep #$20
.a8
    lda BA_S3
    and #$04
    beq sin_atk
    lda BA_S0
    jsr ba_pct
    beq sin_atk
    rep #$20
.a16
    lda #BA_MATK
    sta BA_S5
    lda #BA_BATK
    sta BA_S6
    lda #BA_ATK
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
sin_atk:
    lda BA_S3
    and #$08
    beq sin_def
    lda BA_S0
    jsr ba_pct
    beq sin_def
    rep #$20
.a16
    lda #BA_MDEF
    sta BA_S5
    lda #BA_BDEF
    sta BA_S6
    lda #BA_DEF
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
sin_def:
    lda BA_S3
    and #$10
    beq sin_spi
    lda BA_S0
    jsr ba_pct
    beq sin_spi
    rep #$20
.a16
    lda #BA_MSPI
    sta BA_S5
    lda #BA_BSPI
    sta BA_S6
    lda #BA_SPI
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
sin_spi:
    lda BA_S3
    and #$20
    beq sin_agi
    lda BA_S0
    jsr ba_pct
    beq sin_agi
    rep #$20
.a16
    lda #BA_MAGI
    sta BA_S5
    lda #BA_BAGI
    sta BA_S6
    lda #BA_AGI
    sta BA_T1
    sep #$20
.a8
    jsr ba_mod
sin_agi:
    rts
.endproc

.proc ba_mensaje
.a8
.i16
    rep #$20
.a16
    lda #0
    sta BA_T1
    lda #BA_MSG_POS1
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MTIPO
    cmp #BA_MSG_ATAQUE
    beq ataque
    cmp #BA_MSG_DEFIENDE
    beq defiende
    cmp #BA_MSG_NO_HUYO
    beq no_huyo
    cmp #BA_MSG_HUYO
    beq huyo
    cmp #BA_MSG_VICTORIA
    beq victoria
    cmp #BA_MSG_ITEM
    beq usa_item
    cmp #BA_MSG_HAB
    beq usa_hab
    ldx #BA_TXT_DERROTA
    jmp solo
usa_hab:
    jmp habilidad
usa_item:
    jmp item
victoria:
    ldx #BA_TXT_VICTORIA
    jmp solo
huyo:
    ldx #BA_TXT_HUYO
    jmp solo
no_huyo:
    ldx #BA_TXT_NO_HUYO
solo:
    jsr ba_termino
    rts
defiende:
    lda BA_MQUIEN
    jsr ba_nombre
    ldx #BA_TXT_DEFIENDE
    jsr ba_termino
    rts
ataque:
    lda BA_MQUIEN
    jsr ba_nombre
    ldx #BA_TXT_ATACA
    jsr ba_termino
    ; El segundo renglón: el resultado sobre el blanco.
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_nombre
    rep #$20
.a16
    lda BA_MDANO
    cmp #$FFFF
    sep #$20
.a8
    bne pego
    jmp fallo
pego:
    ; `<nombre> <daño> health lost.`
    lda #$20                    ; el espacio entre el nombre y el número
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_MDANO
    sta BA_T0
    sep #$20
.a8
    jsr ba_numero_justo
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs es_enemigo
    ldx #BA_TXT_DANO_ACTOR
    bra dice
es_enemigo:
    ldx #BA_TXT_DANO_ENEMIGO
dice:
    jsr ba_termino
    rts
item:
    ; `<quien> <ítem> used.`, que es
    ; `source.GetName() + " " + item.name + terms.use_item` de
    ; `GetItemStartMessage2k`.
    lda BA_MQUIEN
    jsr ba_nombre
    lda #$20
    jsl f:ba_t_glifo
    lda #255
    sta comp_dup + 3
    stz temp + 1
    rep #$20
.a16
    lda BA_MITEM
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; por tres: `3k` es el nombre del ítem
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ldx #BA_TXT_USO
    jsr ba_termino
    ; `<blanco> HP <n> Recovered`, que es `GetHpSpRecoveredMessage`.
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MBLA
    jsr ba_nombre
    lda #$20
    jsl f:ba_t_glifo
    ldx #BA_TXT_HP
    jsr ba_termino
    lda #$20
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_MCURA
    sta BA_T0
    sep #$20
.a8
    jsr ba_numero_justo
    ldx #BA_TXT_RECUPERO
    jsr ba_termino
    rts
habilidad:
    ; `<quien><using_message1>` arriba y `<using_message2>` abajo, que es
    ; `GetSkillFirstStartMessage2k` y su hermana. Los dos renglones son del
    ; LDB, como todo lo que esta pantalla escribe.
    lda BA_MQUIEN
    jsr ba_nombre
    lda #255
    sta comp_dup + 3
    stz temp + 1
    rep #$20
.a16
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_msg1, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    rep #$20
.a16
    lda #BA_MSG_POS2
    sta BA_T1
    lda #BA_MSG_DX
    jsr ba_ir
    lda BA_MHAB
    and #$00FF
    asl a
    tax
    lda f:hab_msg2, x
    tax
    sep #$20
.a8
    jsr ba_termino
    rts
fallo:
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs falla_enemigo
    ldx #BA_TXT_SIN_DANO_ACTOR
    bra falla_dice
falla_enemigo:
    ldx #BA_TXT_SIN_DANO_ENEMIGO
falla_dice:
    jsr ba_termino
    rts
.endproc

; --- las habilidades en la pelea -------------------------------------------
;
; `Game_BattleAlgorithm::Skill` con lo que este port sabe hacer. Qué sabe cada
; actor, cuánto cuesta y cuánto hace **no se decide acá**: sale de
; `batalla.habilidades_de`, `batalla.costo_de` y `batalla.efecto_habilidad`,
; que es el modelo con el que `pruebas/rpgmaker/test_batalla.py` predice el número
; exacto, y el conversor lo emite en `actor_hab*` y `hab_*`.

; A8 = el número de actor del LDB del combatiente `BA_ACTOR`. Es lo que indexa
; `actor_hab_ini`, `actor_hab_n` y `actor_hab_txt`, que son por número de
; actor y no por lugar en el grupo.
.proc ba_actor_ldb
.a8
.i16
    lda BA_ACTOR
    jsr ba_x
    lda BA_UNO + BA_NUMERO, x
    rts
.endproc

; La lista de habilidades del actor que está ordenando, a `BA_HAB_LISTA`, con
; cuántas en `BA_HAB_N`. Son los `k` de `actor_hab`, que el conversor ya dejó
; ordenados por número de RM2k: ver `batalla.habilidades_de`.
.proc ba_hab_lista
.a8
.i16
    lda #0
    sta BA_HAB_N
    jsr ba_actor_ldb
    jsr ba_ax
    lda f:actor_hab_n, x
    beq listo
    sta BA_S1                   ; cuántas
    lda f:actor_hab_ini, x
    sta BA_S2                   ; dónde arrancan
    lda #0
    sta BA_S3
otra:
    lda BA_S3
    cmp BA_S1
    bcs listo
    cmp #BA_HAB_MAX
    bcs listo
    clc
    adc BA_S2
    jsr ba_ax
    lda f:actor_hab, x
    pha
    lda BA_S3
    jsr ba_ax
    pla
    sta BA_HAB_LISTA, x
    inc BA_S3
    inc BA_HAB_N
    bra otra
listo:
    rts
.endproc

; El `k` del lugar A8 de la lista. Sólo A y X.
.proc ba_hab_de_lista
.a8
.i16
    jsr ba_ax
    lda BA_HAB_LISTA, x
    rts
.endproc

; El costo en SP del `k` de A8, en A8. `Algo::CalcSkillCost`: el `sp_cost` a
; secas, que es lo que RM2k hace.
.proc ba_hab_costo
.a8
.i16
    jsr ba_ax
    lda f:hab_sp, x
    rts
.endproc

; Si el combatiente `BA_ACTOR` puede pagar el `k` de A8: Z=0 si sí. **No usa el
; flag que deja un `pl*`**: la trampa de siempre.
.proc ba_hab_alcanza
.a8
.i16
    jsr ba_hab_costo
    sta BA_T2
    lda BA_ACTOR
    jsr ba_x
    rep #$20
.a16
    lda BA_T2
    and #$00FF
    cmp BA_UNO + BA_SP, x
    sep #$20
.a8
    beq si                      ; justo los que tiene alcanza
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; La pantalla entera, en `texto_buf`.
.proc ba_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    ; --- los enemigos, o la lista de ítems mientras se elige uno ---
    ;
    ; Van en los mismos renglones a propósito: eligiendo qué usar lo que hace
    ; falta ver es el grupo, que es a quién se cura, y no los enemigos.
    ; **Eligiendo a quién se le da, arriba va la lista de la orden en curso**:
    ; la de ítems o la de habilidades, en gris las dos. Cuál de las dos lo dice
    ; `BA_ORDEN`, que sigue puesto mientras se elige el blanco.
    lda BA_MODO
    cmp #BA_M_HAB
    beq a_la_lista_hab
    cmp #BA_M_ACTOR
    bne no_es_hab
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne no_es_hab
a_la_lista_hab:
    jmp la_lista_hab
no_es_hab:
    lda BA_MODO
    cmp #BA_M_ITEM
    beq a_la_lista
    cmp #BA_M_ACTOR
    bne sin_lista
a_la_lista:
    jmp la_lista
sin_lista:
    lda #0
    sta BA_S0
enemigo:
    lda BA_S0
    cmp BA_NENE
    bcs enemigos_listos
    rep #$20
.a16
    lda #BA_ENEMIGO_POS0
    jsr ba_fila
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_BLANCO
    bne sin_cursor_ene
    lda BA_S0
    cmp BA_BLANCO
    bne sin_cursor_ene
    jsr ba_cursor
sin_cursor_ene:
    stz BA_CONMAX               ; un enemigo no muestra su máximo
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_renglon
    inc BA_S0
    bra enemigo
enemigos_listos:
    ; --- el grupo ---
    lda #0
    sta BA_S0
actor:
    lda BA_S0
    cmp BA_NACT
    bcs actores_listos
    rep #$20
.a16
    lda #BA_GRUPO_POS0
    jsr ba_fila
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_MENSAJE
    bcs sin_cursor_act
    cmp #BA_M_ACTOR
    bne cursor_en_el_que_ordena
    lda BA_S0
    cmp BA_ITEM_BLA             ; eligiendo a quién curar
    bne sin_cursor_act
    bra pone_cursor_act
cursor_en_el_que_ordena:
    lda BA_S0
    cmp BA_ACTOR
    bne sin_cursor_act
pone_cursor_act:
    jsr ba_cursor
sin_cursor_act:
    lda #1
    sta BA_CONMAX
    lda BA_S0
    jsr ba_renglon
    inc BA_S0
    bra actor
actores_listos:
    ; --- el último renglón ---
    lda BA_MODO
    cmp #BA_M_MENSAJE
    bcc ordenes
    jmp ba_mensaje
ordenes:
    lda #0
    sta BA_S0
orden:
    lda BA_S0
    cmp #BA_ORDENES_N
    bcc hay_orden
    jmp ordenes_listas
hay_orden:
    ; En qué renglón cae ésta: desde el 2026-09-13 son cinco y van en dos.
    lda BA_S0
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda f:ba_orden_fila, x
    sta BA_T1
    sep #$20
.a8
    ; En gris mientras se elige otra cosa —el menú ya no manda— y siempre la
    ; que no está hecha, que es lo que el menú de pausa hace con las suyas.
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne en_gris
    lda BA_S0
    jsr ba_ax
    lda f:ba_orden_gris, x
    bne en_gris
    ; Y la habilidad de un actor que no sabe ninguna —Talan, que es de nivel
    ; 1— también va en gris, como el menú de pausa con lo que no lleva a
    ; ningún lado.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    bne sin_gris_orden
    jsr ba_actor_ldb
    jsr ba_ax
    lda f:actor_hab_n, x
    cmp #0
    beq en_gris
sin_gris_orden:
    lda #0
    bra pone_variante
en_gris:
    lda #1
pone_variante:
    sta BA_S1
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:ba_orden_dx, x
    sta BA_T2
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne sin_cursor_orden
    lda BA_S0
    cmp BA_ORDEN
    bne sin_cursor_orden
    stz temp + 1
    rep #$20
.a16
    lda BA_T2
    sec
    sbc #2
    jsr ba_ir
    sep #$20
.a8
    lda #$3E                    ; el cursor
    jsl f:ba_t_glifo
sin_cursor_orden:
    rep #$20
.a16
    lda BA_T2
    jsr ba_ir
    sep #$20
.a8
    lda BA_S1
    sta temp + 1
    lda #255
    sta comp_dup + 3
    ; **La segunda orden no dice "Tech Skill"**: dice el `skill_name` del actor
    ; que está ordenando —"AgentTrain", "Telepathy", "Slicing"—, que es
    ; `Game_Actor::GetSkillName`. Por eso su texto sale de `actor_hab_txt`, que
    ; es por número de actor, y no de `ba_orden_txt`, que es fijo.
    lda BA_S0
    cmp #BA_ORDEN_HABILIDAD
    beq texto_de_la_habilidad
    ; **De dos bytes**, como `actor_hab_txt` y `enemigo_txt`: el índice de un
    ; texto no entra en uno. Con los 29 mapas de `demo-ciudad` los textos de la
    ; batalla arrancan en el 273, así que la tabla de un byte que estaba acá
    ; hasta el 2026-09-14 los truncaba a 17, 18, 19 y 32, que son renglones de
    ; la descripción de un ítem: el menú dibujaba cuatro textos largos, uno
    ; encima del otro. Ningún cartucho de la tanda llega a 256 textos.
    rep #$20
.a16
    lda BA_S0
    and #$00FF
    asl a
    tax
    lda f:ba_orden_txt, x
    tax
    bra texto_puesto
texto_de_la_habilidad:
.a8
.i16
    jsr ba_actor_ldb
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:actor_hab_txt, x
    tax
texto_puesto:
.a16
    sep #$20
.a8
    jsl f:ba_t_texto
    inc BA_S0
    jmp orden
ordenes_listas:
    rts

    ; --- la lista de ítems, donde van los enemigos ---
la_lista:
    lda #0
    sta BA_S0
fila_item:
    lda BA_S0
    cmp #BA_ENEMIGOS_MAX
    bcs no_hay_mas
    clc
    adc BA_ITEM_ARR
    cmp BA_ITEM_N
    bcc hay_item
no_hay_mas:
    jmp items_listos
hay_item:
    sta BA_S6                   ; el lugar en la lista
    rep #$20
.a16
    lda #BA_ENEMIGO_POS0
    jsr ba_fila
    sep #$20
.a8
    ; El cursor, sólo mientras se elige el ítem: eligiendo el blanco la lista
    ; queda en gris y el cursor se va al grupo.
    lda BA_MODO
    cmp #BA_M_ITEM
    bne gris_item
    lda BA_S6
    cmp BA_ITEM_SEL
    bne sin_cursor_item
    jsr ba_cursor
sin_cursor_item:
    lda #0
    bra variante_item
gris_item:
    lda #1
variante_item:
    sta temp + 1
    ; el nombre
    rep #$20
.a16
    lda #BA_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_NOMBRE_ANCHO
    sta comp_dup + 3
    lda BA_S6
    jsr ba_item_de_lista
    sta BA_S1                   ; el `k`
    rep #$20
.a16
    and #$00FF
    sta BA_T0
    asl a
    clc
    adc BA_T0                   ; por tres: `3k` es el nombre
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; y cuántos hay, con los dos puntos adelante
    rep #$20
.a16
    lda #BA_ITEM_CUENTA_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_MODO
    cmp #BA_M_ITEM
    beq cuenta_blanca
    lda #1
    bra cuenta_variante
cuenta_blanca:
    lda #0
cuenta_variante:
    sta temp + 1
    lda #$3A                    ; los dos puntos
    jsl f:ba_t_glifo
    lda BA_S1
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:item_id, x
    tax
    sep #$20
.a8
    lda FAR_ITEMS, x
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_numero
    inc BA_S0
    jmp fila_item
items_listos:
    jmp enemigos_listos

    ; --- la lista de habilidades, donde van los enemigos ---
    ;
    ; La forma es la del original —ver
    ; `pruebas-manuales/capturas-batalla/auto_20260912_123023.png`—: la
    ; descripción de la que marca el cursor arriba de todo, y abajo dos
    ; columnas con el nombre a la izquierda y el costo en SP a la derecha, con
    ; un guión delante. Se lee **por filas**, que es lo que la captura muestra.
la_lista_hab:
    jsr ba_hab_lista
    lda BA_HAB_N
    bne hay_alguna
    jmp hab_listas
hay_alguna:
    lda BA_MODO
    cmp #BA_M_HAB
    bne hab_en_gris             ; eligiendo el blanco: sin descripción
    ; la descripción de la que marca el cursor
    rep #$20
.a16
    lda #BA_HAB_DESC_POS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #255
    sta comp_dup + 3
    lda BA_HAB_SEL
    jsr ba_hab_de_lista
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:hab_desc, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
hab_en_gris:
    lda #0
    sta BA_S3                   ; el lugar en la lista
fila_hab:
    lda BA_S3
    cmp BA_HAB_N
    bcc hay_hab
    jmp hab_listas
hay_hab:
    cmp #(BA_HAB_FILAS * BA_HAB_COLUMNAS)
    bcc hay_lugar_hab
    jmp hab_listas
hay_lugar_hab:
    ; Fila y columna: con dos columnas son un `lsr` y el bit 0. Si alguna vez
    ; fueran otras, esto es lo que hay que cambiar; el conversor emite
    ; `BA_HAB_COLUMNAS` para que se vea desde acá que son dos.
    lda BA_S3
    lsr a
    sta BA_S0
    lda BA_S3
    and #$01
    sta BA_S4
    rep #$20
.a16
    lda #BA_HAB_POS0
    jsr ba_fila
    lda BA_S4
    and #$00FF
    beq columna_cero
    lda #BA_HAB_COLUMNA_DX
    bra columna_puesta
columna_cero:
    lda #0
columna_puesta:
    sta BA_S5                   ; el desplazamiento de la columna
    sep #$20
.a8
    ; El `k` de esta habilidad, y si se puede pagar: la que no alcanza va en
    ; gris, que es lo que RM2k hace con una que no se puede usar.
    lda BA_S3
    jsr ba_hab_de_lista
    sta BA_S6
    lda BA_MODO
    cmp #BA_M_HAB
    bne gris_hab                ; eligiendo el blanco, la lista entera en gris
    lda BA_S6
    jsr ba_hab_alcanza
    bne se_puede
gris_hab:
    lda #1
    bra variante_hab
se_puede:
    lda #0
variante_hab:
    sta BA_S2
    ; el cursor, sólo mientras se elige la habilidad
    lda BA_MODO
    cmp #BA_M_HAB
    bne sin_cursor_hab
    lda BA_S3
    cmp BA_HAB_SEL
    bne sin_cursor_hab
    stz temp + 1
    rep #$20
.a16
    lda BA_S5
    jsr ba_ir
    sep #$20
.a8
    lda #$3E
    jsl f:ba_t_glifo
sin_cursor_hab:
    ; el nombre
    lda BA_S2
    sta temp + 1
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_NOMBRE_DX
    jsr ba_ir
    sep #$20
.a8
    lda #BA_HAB_NOMBRE_ANCHO
    sta comp_dup + 3
    rep #$20
.a16
    lda BA_S6
    and #$00FF
    asl a
    tax
    lda f:hab_txt, x
    tax
    sep #$20
.a8
    jsl f:ba_t_texto
    ; el guión y el costo
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_GUION_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_S2
    sta temp + 1
    lda #$2D                    ; el guión
    jsl f:ba_t_glifo
    rep #$20
.a16
    lda BA_S5
    clc
    adc #BA_HAB_COSTO_DX
    jsr ba_ir
    sep #$20
.a8
    lda BA_S6
    jsr ba_hab_costo
    rep #$20
.a16
    and #$00FF
    sta comp_dup
    sep #$20
.a8
    lda #BA_HAB_COSTO_CIFRAS
    sta comp_dup + 2
    lda BA_S2
    sta temp + 1
    jsl f:ba_t_numero
    inc BA_S3
    jmp fila_hab
hab_listas:
    jmp enemigos_listos
.endproc

; --- el lazo de la pelea --------------------------------------------------

; El promedio de agilidad de un lado: A8 en 0 el grupo y en 1 la tropa. Si no
; queda nadie vivo cuentan todos, que es el `or list(quienes)` de
; `batalla.Batalla._promedio`. El resultado va en `BA_T1`, topado en
; `BA_AGI_TOPE`: por memoria y no por el acumulador, por lo mismo que
; `ba_param`.
.proc ba_promedio
.a8
.i16
    sta BA_S6
    ; Dos vueltas: la primera cuenta sólo a los vivos y, si no hubo ninguno,
    ; la segunda cuenta a todos.
    lda #1
    sta BA_S5                   ; ¿sólo los vivos?
vuelta:
    rep #$20
.a16
    lda #0
    sta BA_T0                   ; la suma
    sep #$20
.a8
    lda #0
    sta BA_S4                   ; cuántos
    lda BA_S6
    beq desde_el_grupo
    lda #BA_GRUPO_MAX
    sta BA_S0
    lda BA_NENE
    clc
    adc #BA_GRUPO_MAX
    sta BA_S3
    bra suma
desde_el_grupo:
    lda #0
    sta BA_S0
    lda BA_NACT
    sta BA_S3
suma:
    lda BA_S0
    cmp BA_S3
    bcs sumados
    lda BA_S5
    beq cuenta
    lda BA_S0
    jsr ba_vivo
    beq siguiente
cuenta:
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_AGI, x
    clc
    adc BA_T0
    sta BA_T0
    sep #$20
.a8
    inc BA_S4
siguiente:
    inc BA_S0
    bra suma
sumados:
    lda BA_S4
    bne dividir
    lda BA_S5
    beq dividir                 ; ni vivos ni muertos: no hay nadie
    stz BA_S5
    bra vuelta
dividir:
    rep #$20
.a16
    lda BA_S4
    and #$00FF
    bne hay
    lda #1
hay:
    sta temp + 2
    lda BA_T0
    sta temp
    jsr ba_div
    cmp #(BA_AGI_TOPE + 1)
    bcc listo
    lda #BA_AGI_TOPE
listo:
    sta BA_T1
    sep #$20
.a8
    rts
.endproc

; La chance de escapar: `Scene_Battle::InitEscapeChance`.
;
;     base   = redondear(100 * agi_enemigos / agi_grupo)
;     chance = recortar(150 - base, 0, 100)
;
; El redondeo es `(2a + b) / (2b)`, que es `RoundTo` con enteros y sin
; flotantes: ver `batalla.Batalla._chance_de_huir`.
.proc ba_chance_huir
.a8
.i16
    lda #0
    jsr ba_promedio
    rep #$20
.a16
    lda BA_T1
    bne grupo_hay
    lda #1
grupo_hay:
    sta BA_S1                   ; el promedio del grupo
    sep #$20
.a8
    lda #1
    jsr ba_promedio
    rep #$20
.a16
    lda BA_T1
    sta BA_S2                   ; el de la tropa
    lda #200
    sta BA_T2
    lda BA_S2
    jsr ba_mul                  ; 200 por el promedio de la tropa
    clc
    adc BA_S1
    sta temp
    lda BA_S1
    asl a
    sta temp + 2
    jsr ba_div                  ; A16 = la base
    sta BA_S3
    lda #150
    sec
    sbc BA_S3
    bpl no_negativa
    lda #0
no_negativa:
    cmp #101
    bcc chance_lista
    lda #100
chance_lista:
    sep #$20
.a8
    sta BA_HUIDA
    rts
.endproc

; `TryEscape`: se tira contra la chance y, si falla, sube diez. Vuelve con A8
; en 1 si se escapó.
.proc ba_huir
.a8
.i16
    lda BA_HUIDA
    jsr ba_pct
    bne salio
    lda BA_HUIDA
    clc
    adc #10
    cmp #101
    bcc guarda
    lda #100
guarda:
    sta BA_HUIDA
    lda #0
    rts
salio:
    lda #1
    rts
.endproc

; El primer actor vivo desde `BA_ACTOR`, o A8 en $FF si no queda ninguno.
.proc ba_actor_siguiente
.a8
.i16
busca:
    lda BA_ACTOR
    cmp BA_NACT
    bcs ninguno
    lda BA_ACTOR
    jsr ba_vivo
    bne hay
    inc BA_ACTOR
    bra busca
hay:
    lda BA_ACTOR
    rts
ninguno:
    lda #$FF
    rts
.endproc

; El primer enemigo vivo, en A8, o $FF.
.proc ba_enemigo_vivo
.a8
.i16
    lda #0
    sta BA_S0
busca:
    lda BA_S0
    cmp BA_NENE
    bcs ninguno
    lda BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne hay
    inc BA_S0
    bra busca
hay:
    lda BA_S0
    rts
ninguno:
    lda #$FF
    rts
.endproc

; Le anota la orden A8 al actor `BA_ACTOR`, con el blanco de `BA_T0`, y la
; apila en la lista de ejecución. El orden en que se apila **importa**: el
; desempate del orden de turnos es estable, así que primero va el grupo y
; después la tropa, como en `batalla.Batalla.jugar_turno`.
.proc ba_anotar
.a8
.i16
    sta BA_S1
    lda BA_ACTOR
    asl a
    jsr ba_ax
    lda BA_S1
    sta BA_ACC, x
    lda BA_T0
    sta BA_ACC + 1, x
    lda BA_NACC
    jsr ba_ax
    lda BA_ACTOR
    sta BA_EJEC, x
    inc BA_NACC
    inc BA_ACTOR
    rts
.endproc

; El mensaje de `BA_MTIPO` en pantalla, por `BA_MSG_CUADROS` cuadros o hasta
; que alguien apriete A.
.proc ba_mostrar
.a8
.i16
    ; El efecto que hubiera quedado pendiente no sobrevive al mensaje que lo
    ; dejó: quien quiera uno en éste lo anota después de llamar acá.
    rep #$20
.a16
    lda #$FFFF
    sta BA_SE2
    sep #$20
.a8
    lda #BA_M_MENSAJE
    sta BA_MODO
    lda #BA_MSG_CUADROS
    sta BA_ESPERA
    jsr ba_componer
    rts
.endproc

; Qué suena en el golpe que se acaba de resolver, y cuándo.
;
; RM2k toca **dos** efectos por golpe: el del ataque al empezar la acción
; —`Normal::GetStartSe`, y sólo cuando el que pega es un enemigo— y el del
; resultado en el sub-estado del mensaje, unos cuadros más tarde. Acá los
; efectos tienen **una sola voz**, así que los dos juntos serían uno solo: el
; del resultado queda pendiente en `BA_SE2` y sale a los `BA_MSG_CUADROS -
; BA_SE2_CUADROS` cuadros. Cuando el que pega es del grupo no hay primero, así
; que el del resultado suena ya.
;
; El del resultado sale de easyrpg y no de memoria: errar es `GetFailureSe`
; —dodge_se—, pegarle a un actor es actor_damaged_se y a un enemigo
; enemy_damaged_se, salvo que lo mate, que es el enemy_death_se de
; `ProcessBattleActionDeath`.
.proc ba_sonido_del_golpe
.a8
.i16
    lda BA_MBLA
    jsr ba_x                    ; X: el desplazamiento del blanco
    rep #$20
.a16
    lda BA_MDANO
    cmp #$FFFF
    beq erro
    sep #$20
.a8
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcc al_actor
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    beq murio
    lda #BA_SE_DANO_ENEMIGO
    bra anotado
murio:
.a16
    lda #BA_SE_MUERTE
    bra anotado
erro:
.a16
    lda #BA_SE_ERRAR
    bra anotado
al_actor:
.a8
    rep #$20
.a16
    lda #BA_SE_DANO_ACTOR
anotado:
.a16
    sta BA_SE2
    sep #$20
.a8
    lda BA_MQUIEN
    cmp #BA_GRUPO_MAX
    bcs del_enemigo
    ; Pega alguien del grupo: RM2k no le pone efecto de ataque, así que el del
    ; resultado no tiene a qué esperar y sale en el acto.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sonido
.a8
    rts
del_enemigo:
.a8
    rep #$20
.a16
    lda #BA_SE_ATAQUE
    jsl f:ba_t_sonido
.a8
    rts
.endproc

; El turno, ya con las órdenes del grupo anotadas: las de la tropa, el orden de
; ejecución, y a ejecutar.
.proc ba_empezar_turno
.a8
.i16
    lda #0
    sta BA_S0
limpia:
    lda BA_S0
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    and #(BAF_HAY | BAF_ACTOR)   ; sin BAF_DEF: la defensa dura un turno
    sta BA_UNO + BA_FLAGS, x
    inc BA_S0
    lda BA_S0
    cmp #BA_COMB_MAX
    bcc limpia
    jsr ba_acciones_enemigas
    jsr ba_orden_ejecucion
    lda #0
    sta BA_I
    jmp ba_ejecutar
.endproc

; El fin del turno: o se acabó la pelea, o se vuelve a pedir órdenes.
.proc ba_fin_de_turno
.a8
.i16
    jsr ba_enemigo_vivo
    cmp #$FF
    bne siguen
    lda #BA_VICTORIA
    sta BA_RESULT
    lda #BA_MSG_VICTORIA
    sta BA_MTIPO
    ; El `BGM_Victory` de `Scene_Battle_Rpg2k`. En el ABL es **el mismo tema
    ; que el de la pelea** —los dos campos del LDB dicen T_VGFighterMAX_Masako—
    ; así que en la práctica vuelve a empezar; que sean dos constantes y no una
    ; es porque el dato es del juego y no nuestro.
    lda #BA_TEMA_FIN
    jsl f:ba_t_bgm
    bra termina
siguen:
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    bne otro_turno
    lda #BA_DERROTA
    sta BA_RESULT
    lda #BA_MSG_DERROTA
    sta BA_MTIPO
termina:
    jsr ba_mostrar
    lda #BA_M_FIN
    sta BA_MODO
    rts
otro_turno:
    lda #0
    sta BA_NACC
    sta BA_ORDEN
    lda #BA_M_ORDEN
    sta BA_MODO
    jsr ba_componer
    rts
.endproc

; La acción que sigue, salteando a los que murieron en el camino.
.proc ba_ejecutar
.a8
.i16
otra:
    lda BA_I
    cmp BA_NACC
    bcc hay
    jmp ba_fin_de_turno
hay:
    lda BA_I
    jsr ba_ax
    lda BA_EJEC, x
    sta BA_MQUIEN
    inc BA_I
    lda BA_MQUIEN
    jsr ba_vivo
    beq otra
    lda BA_MQUIEN
    asl a
    jsr ba_ax
    lda BA_ACC, x
    sta BA_S1                   ; la orden
    lda BA_ACC + 1, x
    sta BA_MBLA                 ; y el blanco
    lda BA_S1
    cmp #BA_DEFENDER
    beq a_defiende
    cmp #BA_HUIR
    beq a_no_huyo
    cmp #BA_ITEM
    beq usa_un_item
    cmp #BA_HABILIDAD
    beq usa_una_habilidad
    bra ataca
a_defiende:
    jmp defiende
a_no_huyo:
    jmp no_huyo
ataca:
    ; Atacar. Si el blanco murió antes de que le tocara, se reapunta al primero
    ; vivo de ese lado, como hace `Game_BattleAlgorithm`.
    lda BA_MBLA
    jsr ba_vivo
    bne pega
    lda BA_MBLA
    cmp #BA_GRUPO_MAX
    bcs busca_enemigo
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    beq otra
    sta BA_MBLA
    bra pega
busca_enemigo:
    jsr ba_enemigo_vivo
    cmp #$FF
    beq otra
    clc
    adc #BA_GRUPO_MAX
    sta BA_MBLA
pega:
    jsr ba_atacar
    lda #BA_MSG_ATAQUE
    sta BA_MTIPO
    jsr ba_mostrar              ; que limpia el pendiente, así que va antes
    jmp ba_sonido_del_golpe
usa_una_habilidad:
    ; El blanco muerto **no se reapunta**, como con un ítem: `IsTargetValid`
    ; de `Skill` lo descarta y la acción se pierde. Con una que apunta al
    ; grupo eso es lo que pasa si al que se iba a curar lo mataron antes.
    lda BA_MBLA
    jsr ba_vivo
    beq otra_hab
    jsr ba_hab_usar
    lda #BA_MSG_HAB
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_ITEM             ; el mismo que un ítem: RM2k no tiene otro
    jsl f:ba_t_sonido
.a8
    rts
otra_hab:
    jmp otra
usa_un_item:
    ; El ítem no falla ni lo esquiva nadie, así que no tira azar; y el blanco
    ; muerto **no se reapunta**, que es lo contrario de un ataque.
    jsr ba_item_usar
    lda #BA_MSG_ITEM
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_ITEM
    jsl f:ba_t_sonido
.a8
    rts
defiende:
    lda BA_MQUIEN
    jsr ba_x
    lda BA_UNO + BA_FLAGS, x
    ora #BAF_DEF
    sta BA_UNO + BA_FLAGS, x
    lda #BA_MSG_DEFIENDE
    sta BA_MTIPO
    jmp ba_mostrar
no_huyo:
    lda #BA_MSG_NO_HUYO
    sta BA_MTIPO
    jmp ba_mostrar
.endproc

; --- la escena de la pelea --------------------------------------------------
;
; El fondo de batalla con los monstruos **ya horneados encima**: una sola capa
; de 8bpp de 256x128 en BG1, que son los siete renglones de texto de arriba.
; El porqué, el presupuesto y lo que cuesta están en tools/port/escena.py; acá sólo
; se sube.
;
; Corre desde `batalla_correr` con la pantalla apagada y con el banco de datos
; en $7E, así que los registros del PPU y las tablas del cartucho van todos
; con `f:`.
;
; Dos cosas del PPU que no son obvias:
;
; * **El texto lleva el bit de prioridad.** En modo 3 el orden del PPU deja
;   BG1 de prioridad 0 arriba de BG2 de prioridad 0, así que sin eso la escena
;   taparía las letras. Lo pone el conversor en `item_glifo_celdas`.
; * **El tile con que se tapa lo que queda abajo de la escena es el 512**, que
;   cae fuera del bloque: los 512 tiles de 8bpp son las 16.384 palabras que
;   van de `ESCENA_VRAM` al final de la VRAM, así que el 512 da la vuelta y
;   queda en la palabra 0. Mientras dura la pelea esa palabra es VRAM del mapa
;   y no la usa nadie; al salir, `volver_al_mapa` rehace todo.
;
; A: el índice de tropa. Deja el número de escena en `BA_ESCENA`, o $FF.
.proc escena_subir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #ESCENA_N
    beq no_hay
    lda f:escena_de, x
    cmp #$FF
    bne hay
no_hay:
    jmp sin_escena              ; esta ROM no lleva escena para esta tropa
hay:
    sta BA_ESCENA

    ; --- los 32 KB de tiles, de a trozos ---
    lda #$80
    sta f:VMAIN                 ; una palabra por escritura
    stz BA_S0 + 1
    lda BA_ESCENA
    sta BA_S0
    rep #$20
.a16
    lda BA_S0
    asl a
    asl a
    asl a
    asl a                       ; por ESCENA_TROZOS * 4: la fila de punteros
    sta BA_S0
    lda #ESCENA_VRAM
    sta BA_S1
    sep #$20
.a8
    lda #0
    sta BA_S2
trozo:
    rep #$20
.a16
    lda BA_S1
    sta f:VMADDL
    lda #ESCENA_TROZO
    sta f:DAS0L
    ldx BA_S0
    lda f:escena_trozo, x
    sta f:A1T0L
    sep #$20
.a8
    lda f:escena_trozo + 2, x
    sta f:A1B0
    lda #$01                    ; dos registros: VMDATAL y VMDATAH
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rep #$20
.a16
    lda BA_S0
    clc
    adc #4
    sta BA_S0
    lda BA_S1
    clc
    adc #(ESCENA_TROZO / 2)     ; el trozo, en palabras
    sta BA_S1
    sep #$20
.a8
    inc BA_S2
    lda BA_S2
    cmp #ESCENA_TROZOS
    bcc trozo

    ; --- el tile transparente, en la palabra 0 ---
    rep #$20
.a16
    lda #0
    sta f:VMADDL
    lda #64
    sta f:DAS0L
    lda #.loword(escena_cero)
    sta f:A1T0L
    sep #$20
.a8
    lda #^escena_cero
    sta f:A1B0
    lda #$01
    sta f:DMAP0
    lda #$18
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN

    ; --- el tilemap: los 512 tiles en orden y el resto tapado ---
    ;
    ; Se escribe a mano y no por DMA: son los números 0, 1, 2... y emitirlos
    ; serían dos kilobytes de cartucho por escena para decir eso.
    rep #$20
.a16
    lda #ESCENA_MAPA
    sta f:VMADDL
    lda #0
    sta BA_S0                   ; el tile que va en la celda
    ldx #0
celda:
    cpx #ESCENA_TILES
    bcc celda_escena
    lda #ESCENA_BLANCO
    bra celda_pone
celda_escena:
.a16
    lda BA_S0
celda_pone:
.a16
    sta f:VMDATAL
    inc BA_S0
    inx
    cpx #(32 * 32)
    bcc celda
    sep #$20
.a8

    ; --- los 96 colores, desde la entrada ESCENA_CGRAM ---
    lda #ESCENA_CGRAM
    sta f:CGADD
    stz BA_S0 + 1
    lda BA_ESCENA
    sta BA_S0
    rep #$20
.a16
    lda BA_S0
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por 64
    sta BA_S1
    asl a                       ; por 128
    clc
    adc BA_S1                   ; y por 192, que son ESCENA_COLORES * 2
    clc
    adc #.loword(escena_cgram)
    sta f:A1T0L
    lda #(ESCENA_COLORES * 2)
    sta f:DAS0L
    sep #$20
.a8
    lda #^escena_cgram
    sta f:A1B0
    lda #0
    sta f:DMAP0                 ; `stz` no tiene modo largo
    lda #$22
    sta f:BBAD0
    lda #$01
    sta f:MDMAEN
    rts
sin_escena:
.a8
    lda #$FF
    sta BA_ESCENA
    rts
.endproc

; BG1 con la escena, después de que `ranura_ppu_prender` haya puesto BG2 y
; prendido la pantalla. Si esta pelea no tiene escena no toca nada y la
; pantalla queda sobre negro, como antes del 2026-09-13.
.proc escena_prender
.a8
.i16
    lda BA_ESCENA
    cmp #$FF
    beq listo
    lda #((ESCENA_MAPA / 1024) * 4)
    sta f:BG1SC                 ; 32x32, que es lo que tapa la pantalla entera
    lda #((RANURA_VRAM / 4096) * 16 + (ESCENA_VRAM / 4096))
    sta f:BG12NBA               ; el texto en BG2 y la escena en BG1
    lda #0
    sta f:BG1HOFS               ; `stz` no tiene modo largo
    sta f:BG1HOFS
    lda #$FF
    sta f:BG1VOFS               ; el PPU muestra vofs+1: con -1 cae en su lugar
    sta f:BG1VOFS
    lda #$03
    sta f:TM                    ; BG1 y BG2
listo:
    rts
.endproc

; La pelea entera. Se entra con `jsl` desde `op_battle`, con el banco de datos
; ya en $7E, y se vuelve con el resultado en `BA_RESULT`.
;
; Corre **su propio lazo de cuadros**, como `ranuras_pantalla` y como la
; tienda: `vueltas` no avanza mientras se ve, así que para la referencia la
; pelea no cuesta ningún tick, tarde lo que tarde el jugador. Ver `OP_BATTLE`
; en tools/port/eventos.py.
.proc batalla_correr
.a8
.i16
    rep #$20
.a16
    lda #BATALLA_SEMILLA
    sta BA_SEM                  ; el azar arranca igual en toda pelea
    lda #$FFFF
    sta BA_SE2                  ; sin efecto pendiente
    sep #$20
.a8
    lda #BA_VICTORIA
    sta BA_RESULT
    lda #0
    sta BA_NACC
    sta BA_ORDEN
    sta BA_ACTOR
    sta BA_I
    jsr ba_armar
    lda BA_NENE
    bne hay_tropa
    rtl                         ; una tropa que este cartucho no lleva
hay_tropa:
    lda #0
    sta BA_ACTOR
    jsr ba_actor_siguiente
    cmp #$FF
    bne hay_grupo
    lda #BA_DERROTA             ; nadie en pie: se pierde sin pelear
    sta BA_RESULT
    rtl
hay_grupo:
    jsr ba_chance_huir
    ; Apagar la pantalla, desde acá: los tres registros van con `f:` porque el
    ; banco de datos es $7E y absolutos caerían en la RAM.
    lda #$80
    sta f:INIDISP
    lda #0
    sta f:HDMAEN
    sta f:TM
    jsl f:ba_t_banco
    ; Y la escena: el fondo con los monstruos, en BG1. Va con la pantalla
    ; apagada porque son 32 KB de VRAM más el tilemap y la paleta.
    lda BA_TROPA_K
    jsr escena_subir
    lda #BA_M_ORDEN
    sta BA_MODO
    jsr ba_componer
    jsl f:ba_t_subir
    jsl f:ba_t_ppu
    jsr escena_prender
    lda #1
    sta menu_abierto

espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad                ; el control antes del DMA, como en la tienda
    jsl f:ba_t_subir
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    lda BA_MODO
    cmp #BA_M_ORDEN
    bne :+
    jmp modo_orden
:   cmp #BA_M_BLANCO
    bne :+
    jmp modo_blanco
:   cmp #BA_M_ITEM
    bne :+
    jmp modo_item
:   cmp #BA_M_ACTOR
    bne :+
    jmp modo_actor
:   cmp #BA_M_HAB
    bne :+
    jmp modo_hab
:   cmp #BA_M_MENSAJE
    bne :+
    jmp modo_mensaje
:   jmp modo_fin

    ; --- eligiendo la orden ---
espera5:
    jmp espera
modo_orden:
    lda titulo_flancos
    and #PAD_LEFT
    beq o_no_izq
    lda BA_ORDEN
    beq espera5
    dec BA_ORDEN
    jmp recomponer
o_no_izq:
    lda titulo_flancos
    and #PAD_RIGHT
    beq o_no_der
    lda BA_ORDEN
    cmp #(BA_ORDENES_N - 1)
    bcs espera5
    inc BA_ORDEN
    jmp recomponer
o_no_der:
    jsr ba_flanco_a
    beq espera5
    lda BA_ORDEN
    cmp #BA_ORDEN_ATACAR
    bne o_no_ataca
    jsr ba_enemigo_vivo
    cmp #$FF
    beq espera5
    sta BA_BLANCO
    lda #BA_M_BLANCO
    sta BA_MODO
    jmp recomponer
o_no_ataca:
    cmp #BA_ORDEN_DEFENDER
    bne o_no_defiende
    lda #0
    sta BA_T0
    lda #BA_DEFENDER
    jsr ba_anotar
    jmp siguiente_actor
o_no_defiende:
    cmp #BA_ORDEN_USAR
    bne o_no_usa
    ; `Use Item`: la lista de lo que se puede usar. Vacía, no pasa nada, que
    ; es lo que hace el menú de pausa con una orden que no lleva a ningún
    ; lado.
    jsr ba_items_lista
    lda BA_ITEM_N
    beq espera5
    lda #0
    sta BA_ITEM_SEL
    sta BA_ITEM_ARR
    lda #BA_M_ITEM
    sta BA_MODO
    jmp recomponer
o_no_usa:
    cmp #BA_ORDEN_HABILIDAD
    bne o_no_habilidad
    ; La lista de habilidades del que ordena. Vacía —Talan, que es de nivel
    ; 1— no pasa nada, que es lo que el menú hace con una orden que no lleva a
    ; ningún lado.
    jsr ba_hab_lista
    lda BA_HAB_N
    beq espera5
    lda #0
    sta BA_HAB_SEL
    lda #BA_M_HAB
    sta BA_MODO
    jmp recomponer
o_no_habilidad:
    cmp #BA_ORDEN_HUIR
    beq o_huye
    jmp espera
o_huye:
    jsr ba_huir
    beq o_no_huyo
    lda #BA_HUIDA_R
    sta BA_RESULT
    lda #BA_MSG_HUYO
    sta BA_MTIPO
    jsr ba_mostrar
    rep #$20
.a16
    lda #BA_SE_HUIR             ; el escape_se de `Scene_Battle_Rpg2k`
    jsl f:ba_t_sonido
.a8
    lda #BA_M_FIN
    sta BA_MODO
    jmp espera
o_no_huyo:
    lda #0
    sta BA_T0
    lda #BA_HUIR
    jsr ba_anotar
    jmp siguiente_actor
espera2:
    jmp espera

    ; --- eligiendo el blanco ---
modo_blanco:
    lda titulo_flancos
    and #PAD_UP
    beq b_no_arriba
    jsr ba_blanco_arriba
    jmp recomponer
b_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq b_no_abajo
    jsr ba_blanco_abajo
    jmp recomponer
b_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq b_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
b_mira_a:
    jsr ba_flanco_a
    beq espera2
    lda BA_BLANCO
    clc
    adc #BA_GRUPO_MAX
    sta BA_T0
    ; El modo del blanco lo comparten atacar y una habilidad que apunta a los
    ; enemigos; cuál de las dos es lo dice `BA_ORDEN`, que sigue puesto.
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne b_ataca
    lda #BA_HABILIDAD
    bra b_anota
b_ataca:
    lda #BA_ATACAR
b_anota:
    jsr ba_anotar
    jmp siguiente_actor         ; los dos modos de abajo quedaron en el medio

    ; --- eligiendo qué ítem ---
modo_item:
    lda titulo_flancos
    and #PAD_UP
    beq i_no_arriba
    lda BA_ITEM_SEL
    beq espera4
    dec BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq i_no_abajo
    lda BA_ITEM_SEL
    inc a
    cmp BA_ITEM_N
    bcs espera4
    sta BA_ITEM_SEL
    jsr ba_item_ver
    jmp recomponer
i_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq i_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
i_mira_a:
    jsr ba_flanco_a
    beq espera4
    ; A quién curárselo: al primero vivo del grupo.
    lda #0
    sta BA_ACTOR2
busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera4                 ; no puede pasar: el que ordena está vivo
    jsr ba_vivo
    bne hay_blanco_act
    inc BA_ACTOR2
    bra busca_vivo
hay_blanco_act:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODO
    jmp recomponer
espera4:
    jmp espera

    ; --- eligiendo a quién se le da ---
modo_actor:
    lda titulo_flancos
    and #PAD_UP
    beq a_no_arriba
    jsr ba_blanco_act_arriba
    jmp recomponer
a_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq a_no_abajo
    jsr ba_blanco_act_abajo
    jmp recomponer
a_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq a_mira_a
    ; B vuelve a la lista de la que se vino: la de ítems o la de habilidades.
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne a_vuelve_a_items
    lda #BA_M_HAB
    sta BA_MODO
    jmp recomponer
a_vuelve_a_items:
    lda #BA_M_ITEM
    sta BA_MODO
    jmp recomponer
a_mira_a:
    jsr ba_flanco_a
    beq espera4
    lda BA_ORDEN
    cmp #BA_ORDEN_HABILIDAD
    bne a_es_item
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_HABILIDAD
    jsr ba_anotar
    jmp siguiente_actor
a_es_item:
    ; Se anota la orden y **se gasta el ítem ya**, que es lo que hace RM2k al
    ; elegirlo: si no, el último de un ítem se podría repartir entre dos
    ; actores en el mismo turno.
    lda BA_ITEM_SEL
    jsr ba_item_de_lista
    pha
    lda BA_ACTOR
    jsr ba_ax
    pla
    sta BA_ACC_ITEM, x
    jsr ba_item_gastar
    lda BA_ITEM_BLA
    sta BA_T0
    lda #BA_ITEM
    jsr ba_anotar
    jmp siguiente_actor

    ; --- eligiendo qué habilidad ---
    ;
    ; La lista es de dos columnas y se lee por filas, así que izquierda y
    ; derecha se mueven de a uno y arriba y abajo de a dos.
modo_hab:
    lda titulo_flancos
    and #PAD_LEFT
    bne h_izq
    jmp h_no_izq
h_izq:
    lda BA_HAB_SEL
    beq espera6
    dec BA_HAB_SEL
    jmp recomponer
h_no_izq:
    lda titulo_flancos
    and #PAD_RIGHT
    beq h_no_der
    lda BA_HAB_SEL
    inc a
    cmp BA_HAB_N
    bcs espera6
    sta BA_HAB_SEL
    jmp recomponer
h_no_der:
    lda titulo_flancos
    and #PAD_UP
    beq h_no_arriba
    lda BA_HAB_SEL
    cmp #BA_HAB_COLUMNAS
    bcc espera6
    sec
    sbc #BA_HAB_COLUMNAS
    sta BA_HAB_SEL
    jmp recomponer
h_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq h_no_abajo
    lda BA_HAB_SEL
    clc
    adc #BA_HAB_COLUMNAS
    cmp BA_HAB_N
    bcs espera6
    sta BA_HAB_SEL
    jmp recomponer
espera6:
    jmp espera
h_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq h_mira_a
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
h_mira_a:
    jsr ba_flanco_a
    beq espera7
    ; La que no se puede pagar no se elige, que es lo que RM2k hace con una
    ; habilidad en gris. El costo se descuenta **al ejecutarla** y no acá:
    ; `Skill::vStart` corre cuando le toca el turno.
    lda BA_HAB_SEL
    jsr ba_hab_de_lista
    sta BA_S0
    jsr ba_hab_alcanza
    beq espera6
    lda BA_ACTOR
    jsr ba_ax
    lda BA_S0
    sta BA_ACC_HAB, x
    ; A quién apunta: el bit 6 de `hab_afecta` es `SkillTargetsEnemies`.
    lda BA_S0
    jsr ba_ax
    lda f:hab_afecta, x
    and #$40
    beq h_a_un_aliado
    jsr ba_enemigo_vivo
    cmp #$FF
    beq espera7
    sta BA_BLANCO
    lda #BA_M_BLANCO
    sta BA_MODO
    jmp recomponer
h_a_un_aliado:
    ; Al primero vivo del grupo, como con un ítem.
    lda #0
    sta BA_ACTOR2
h_busca_vivo:
    lda BA_ACTOR2
    cmp BA_NACT
    bcs espera7                 ; no puede pasar: el que ordena está vivo
    lda BA_ACTOR2
    jsr ba_vivo
    bne h_hay_blanco
    inc BA_ACTOR2
    bra h_busca_vivo
espera7:
    jmp espera
h_hay_blanco:
    lda BA_ACTOR2
    sta BA_ITEM_BLA
    lda #BA_M_ACTOR
    sta BA_MODO
    jmp recomponer

siguiente_actor:
    ; Al que sigue; si no queda ninguno, empieza el turno.
    jsr ba_actor_siguiente
    cmp #$FF
    beq arranca_turno
    lda #0
    sta BA_ORDEN
    lda #BA_M_ORDEN
    sta BA_MODO
    jmp recomponer
arranca_turno:
    jsr ba_empezar_turno
    jmp espera

    ; --- un mensaje en pantalla ---
modo_mensaje:
    jsr ba_flanco_a
    bne pasa
    dec BA_ESPERA
    lda BA_ESPERA
    cmp #BA_SE2_CUADROS
    bne sin_segundo
    ; El segundo efecto del golpe, el que RM2k toca en el sub-estado del
    ; mensaje. Se saca de `BA_SE2` al dispararlo para que no vuelva a salir si
    ; el mensaje se alarga.
    rep #$20
.a16
    lda BA_SE2
    ldx #$FFFF
    stx BA_SE2
    jsl f:ba_t_sonido
.a8
sin_segundo:
    lda BA_ESPERA
    bne espera3
pasa:
    jsr ba_ejecutar
espera3:
    jmp espera

    ; --- la pelea terminó ---
modo_fin:
    jsr ba_flanco_a
    beq espera3
    ; Los HP y los SP del grupo vuelven a la partida: desde que hay batallas
    ; son estado de verdad y viajan en la ranura de SRAM.
    lda #0
    sta BA_S0
guarda:
    lda BA_S0
    cmp BA_NACT
    bcs guardados
    lda BA_S0
    jsr ba_x
    rep #$20
.a16
    lda BA_UNO + BA_HP, x
    sta BA_T0
    lda BA_UNO + BA_SP, x
    sta BA_T1
    sep #$20
.a8
    lda BA_UNO + BA_NUMERO, x
    jsr ba_ax
    rep #$20
.a16
    txa
    asl a
    tax
    lda BA_T0
    sta FAR_HP, x
    lda BA_T1
    sta FAR_SP, x
    sep #$20
.a8
    inc BA_S0
    bra guarda
guardados:
    rtl

recomponer:
    jsr ba_componer
    jmp espera

; Z=0 si A se acaba de apretar. Es el mismo de la tienda: `pad_a` y su anterior
; los pone `read_pad`.
ba_flanco_a:
    lda pad_a
    beq no_a
    lda pad_a_ant
    beq si_a
no_a:
    lda #0
    rts
si_a:
    lda #1
    rts

; Que el ítem marcado se vea: corre la ventana de ocho renglones lo justo.
ba_item_ver:
    lda BA_ITEM_SEL
    cmp BA_ITEM_ARR
    bcs ver_abajo
    sta BA_ITEM_ARR             ; se fue por arriba: la ventana lo sigue
    rts
ver_abajo:
    sec
    sbc #BA_ENEMIGOS_MAX
    bcc listo_ver               ; entra sin mover nada
    inc a                       ; el primero que tendría que verse
    cmp BA_ITEM_ARR
    bcc listo_ver
    sta BA_ITEM_ARR
listo_ver:
    rts

; El cursor de a quién se le da el ítem, al actor vivo de arriba o de abajo.
; Si para ese lado no queda ninguno vivo, se queda donde está. Es el hermano
; de `ba_blanco_arriba`, sobre el grupo en vez de sobre la tropa.
ba_blanco_act_arriba:
    lda BA_ITEM_BLA
mira_arriba_act:
    beq nada_act
    dec a
    sta BA_S0
    jsr ba_vivo
    bne pone_act
    lda BA_S0
    bra mira_arriba_act
ba_blanco_act_abajo:
    lda BA_ITEM_BLA
mira_abajo_act:
    inc a
    cmp BA_NACT
    bcs nada_act
    sta BA_S0
    jsr ba_vivo
    bne pone_act
    lda BA_S0
    bra mira_abajo_act
pone_act:
    lda BA_S0
    sta BA_ITEM_BLA
nada_act:
    rts

; El cursor del blanco, al enemigo vivo de arriba o de abajo. Si para ese lado
; no queda ninguno vivo, se queda donde está.
ba_blanco_arriba:
    lda BA_BLANCO
mira_arriba:
    beq nada
    dec a
    sta BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne pone
    lda BA_S0
    bra mira_arriba
ba_blanco_abajo:
    lda BA_BLANCO
mira_abajo:
    inc a
    cmp BA_NENE
    bcs nada
    sta BA_S0
    clc
    adc #BA_GRUPO_MAX
    jsr ba_vivo
    bne pone
    lda BA_S0
    bra mira_abajo
pone:
    lda BA_S0
    sta BA_BLANCO
nada:
    rts
.endproc

; --- el banco de la pantalla, también fuera del banco 0 ---------------------
;
; Se mudó acá el 2026-09-13, cuando `volver_de_batalla` pidió cuarenta y seis
; bytes que el banco 0 ya no tenía: `demo-ciudad` quedaba en 32748 de 32704, y
; antes de eso le sobraban **dos**. Ésta es la que sale más barata de mudar de
; todo lo que mide más de cien bytes: no llama a nadie —son escrituras de
; registro y cuatro DMA— así que no hace falta ningún puente, y no corre por
; cuadro sino al abrir una pantalla con el PPU apagado, o sea que el ciclo de
; más del `jsl` no se nota.
;
; Lo que sí obliga: **se entra con `jsl` y vuelve con `rtl`**, y el banco de
; datos tiene que seguir siendo uno donde $2100..$21FF sea la consola, porque
; escribe los registros en absoluto. Los seis llamadores están todos en el
; banco 0; el de la pelea entra por el puente `ba_t_banco`, que es justo el que
; pone el banco de datos en cero antes de llamar.

; El banco de la pantalla, con la pantalla apagada: la fuente, el tilemap en
; blanco y las dos paletas.
.proc items_banco_subir
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(ITEMS_TILES * 32)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; El tilemap en blanco: un DMA de origen fijo desde el primer tile, que
    ; es transparente.
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(items_tiles)
    ora #(>(items_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_tiles)
    sta A1B0
    lda #$09                    ; dos registros, sin avanzar el origen
    sta DMAP0
    lda #$01
    sta MDMAEN
    ; Los colores.
    stz CGADD
    rep #$20
.a16
    lda #(ITEMS_CGRAM_N * 2)
    sta DAS0L
    lda #<(items_cgram)
    ora #(>(items_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(items_cgram)
    sta A1B0
    stz DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rtl
.endproc

; --- los encuentros al azar, fuera del banco 0 -------------------------------
;
; Lo que RM2k hace, de `Game_Player::UpdateEncounterSteps`, `GetEncountersAt` y
; `PrepareEncounter`, y escrito igual en `eventos.Encuentros`, que es contra lo
; que se compara:
;
;   * cada paso del héroe **con el pad** —una ruta forzada sale antes, por
;     `IsMoveRouteOverwritten`— suma el `encounter_rate` del terreno y mira si
;     salió un encuentro;
;   * la chance es `pmod / encounter_steps`, con `pmod` una potencia de dos que
;     sube a medida que se camina sin que salga nada;
;   * si sale, queda pendiente y se cobra en el cuadro siguiente, con el héroe
;     ya parado: se juntan las tropas del mapa y las de cada área que tape su
;     celda, y se elige una al azar.
;
; **Todas las cuentas son enteras**, que es lo que la consola puede hacer: el
; conversor precalcula `1 / encounter_steps` en 1/65536 —`enc_base`— y en qué
; paso se cruza cada fila de la tabla —`enc_umbral_n`—, así que acá no hay ni
; una división. Ver `eventos.enc_base` y `eventos.enc_umbrales_de_paso`, que son
; las mismas cuentas del otro lado.
;
; Vive acá y no en el banco 0 porque allá quedaban ochenta y cinco bytes: lo
; único que queda del otro lado son los cuatro `jsl` y el puente a la pelea.
; **El banco de datos es $7E mientras esto corre**, como en la batalla: así el
; estado de $3900 se lee con direccionamiento absoluto y la RAM baja —`temp`,
; `tile_x`, `mapa_actual`— se sigue leyendo igual, porque en el banco $7E las
; direcciones de $0000 a $1FFF **son** las del banco 0.

; La semilla del azar de los encuentros, en el reset. Es otra que la del mapa y
; otra que la de la pelea: ver `enc_azar`.
.proc encuentro_arranque
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda #ENC_SEMILLA
    sta ENC_SEM
    sep #$20
.a8
    plb
    rtl
.endproc

; El registro del mapa actual, o que este mapa no tiene encuentros.
.proc encuentro_mapa
.a8
.i16
    phx
    phb
    lda #$7E
    pha
    plb
    ldx mapa_actual
    lda f:enc_mapa, x
    sta ENC_REG
    cmp #ENC_SIN
    beq sin_encuentros
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda f:enc_base, x
    bra con_base
sin_encuentros:
.a8
    rep #$20
.a16
    lda #0
con_base:
.a16
    sta ENC_BASE
    sep #$20
.a8
    ; Y el acumulado en cero, como en todo `MoveTo`: entrar a un mapa es uno.
    stz ENC_N
    stz ENC_IDX
    stz ENC_PIDE
    plb
    plx
    rtl
.endproc

; El `SetTotalEncounterRate(0)` de `Game_Player::MoveTo`: un teletransporte
; —una puerta, un `Teleport`, un `ChangeEventLocation` sobre el héroe— borra lo
; caminado. No toca `ENC_BASE`: el mapa puede ser el mismo.
.proc encuentro_mover
.a8
.i16
    phb
    lda #$7E
    pha
    plb
    stz ENC_N
    stz ENC_IDX
    stz ENC_PIDE
    plb
    rtl
.endproc

; Un paso del héroe. Entra y sale con el acumulador en ocho bits.
.proc encuentro_paso
.a8
.i16
    phx
    phb
    lda #$7E
    pha
    plb
    rep #$20
.a16
    lda ENC_BASE
    bne hay
    ; Apagados: `encounter_steps` en cero, o un mapa sin tropas ni áreas.
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    bra fin
hay:
.a16
    sep #$20
.a8
    lda ENC_N
    inc a
    beq sigue_arriba            ; 255 pasos sin encuentro: no da la vuelta
    sta ENC_N
sigue_arriba:
.a8
    ; La fila de la tabla, que **no baja nunca**: es el `last_encounter_idx` de
    ; allá. X apunta al umbral de la fila que sigue, `reg * 8 + idx`.
    rep #$20
.a16
    lda ENC_REG
    and #$00FF
    asl a
    asl a
    asl a
    sta temp
    lda ENC_IDX
    and #$00FF
    clc
    adc temp
    tax
    sep #$20
.a8
sube:
.a8
    lda ENC_IDX
    cmp #(ENC_FILAS - 1)
    bcs con_fila                ; la última fila no sube más
    lda ENC_N
    cmp f:enc_umbral_n, x       ; ¿llegó al umbral de la que sigue?
    bcc con_fila
    inx
    lda ENC_IDX
    inc a
    sta ENC_IDX
    bra sube
con_fila:
.a8
    ; El umbral del azar: `base` corrido por el `pmod` de la fila. Las filas 0
    ; a 3 son 1/16, 1/8, 1/4 y 1/2; las 4 a 7 son 2, 4, 8 y 16.
    rep #$20
.a16
    lda ENC_IDX
    and #$00FF
    tax
    lda ENC_BASE
    cpx #4
    bcs a_la_izquierda
derecha:
.a16
    lsr a
    inx
    cpx #4
    bcc derecha
    bra con_umbral
a_la_izquierda:
.a16
    dex
    dex
    dex
izquierda:
.a16
    asl a
    bcs siempre                 ; pasó de 1: es certeza, como `PercentChance`
    dex
    bne izquierda
con_umbral:
.a16
    sta temp
    jsr enc_azar
    cmp temp
    bcc salio
    sep #$20
.a8
    bra fin
siempre:
.a16
salio:
.a16
    sep #$20
.a8
    stz ENC_N
    stz ENC_IDX
    lda #1
    sta ENC_PIDE
fin:
.a8
    plb
    plx
    rtl
.endproc

; ¿Hay un encuentro pendiente que pelear acá? Vuelve con A en ocho bits: 1 si
; hay que pelear, y con la tropa ya puesta en `BA_TROPA`.
;
; Es `PrepareEncounter`: si en la celda no tapa ninguna zona, el pendiente se
; consume y no pasa nada, que es lo que hace allá al volver `false`.
.proc encuentro_probar
.a8
.i16
    phx
    phy
    phb
    lda #$7E
    pha
    plb
    lda ENC_PIDE
    bne pendiente
    jmp no_hay
pendiente:
.a8
    stz ENC_PIDE
    lda ENC_REG
    cmp #ENC_SIN
    bne con_registro
    jmp no_hay
con_registro:
.a8
    ; El rango de zonas del mapa: la suya y una por área.
    jsr enc_zonas
    ; Primera pasada: cuántas tropas tapan la celda del héroe.
    rep #$20
.a16
    lda #0
    sta comp_and
contar:
.a16
    lda temp
    cmp temp + 2
    bcs contadas
    jsr enc_tapa
    bcc sin_tapar
    sep #$20
.a8
    lda f:enc_tropa_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    sta comp_and
sin_tapar:
.a16
    inc temp
    bra contar
contadas:
.a16
    lda comp_and
    bne hay_tropas
    sep #$20
.a8
    bra no_hay
hay_tropas:
.a16
    ; Una al azar, `Rand::GetRandomNumber(0, n - 1)`: el resto de dividir el
    ; azar por cuántas hay. La división es la de toda la vida, a mano, porque
    ; el 65816 no divide y la de la pelea vive en otro banco.
    sta comp_and + 2
    jsr enc_azar
    sta comp_or23
    lda #0
    sta comp_or23 + 2
    ldy #16
divide:
.a16
    asl comp_or23
    rol comp_or23 + 2
    lda comp_or23 + 2
    cmp comp_and + 2
    bcc sin_restar
    sec
    sbc comp_and + 2
    sta comp_or23 + 2
sin_restar:
.a16
    dey
    bne divide
    lda comp_or23 + 2
    sta comp_and                ; cuántas hay que saltear
    ; Segunda pasada: la que le toca.
    sep #$20
.a8
    jsr enc_zonas
    rep #$20
.a16
elegir:
.a16
    lda temp
    cmp temp + 2
    bcs no_hay16                ; no puede pasar: el total salió de estas zonas
    jsr enc_tapa
    bcc sigue_eligiendo
    sep #$20
.a8
    lda f:enc_tropa_n, x
    rep #$20
.a16
    and #$00FF
    sta comp_or23
    lda comp_and
    cmp comp_or23
    bcc es_de_esta
    sec
    sbc comp_or23
    sta comp_and
sigue_eligiendo:
.a16
    inc temp
    bra elegir
es_de_esta:
.a16
    sep #$20
.a8
    lda f:enc_tropa_ini, x
    rep #$20
.a16
    and #$00FF
    clc
    adc comp_and
    asl a
    tax
    lda f:enc_tropa, x
    sta BA_TROPA
    sep #$20
.a8
    lda #1
    bra fin
no_hay16:
.a16
    sep #$20
.a8
no_hay:
.a8
    lda #0
fin:
.a8
    plb
    ply
    plx
    rtl
.endproc

; De qué zona a qué zona son las del mapa: `temp` la primera y `temp + 2` una
; más que la última. Entra con el acumulador en ocho bits y sale igual.
.proc enc_zonas
.a8
.i16
    lda ENC_REG
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:enc_zona_ini, x
    rep #$20
.a16
    and #$00FF
    sta temp
    sta temp + 2
    sep #$20
.a8
    lda f:enc_zona_n, x
    rep #$20
.a16
    and #$00FF
    clc
    adc temp + 2
    sta temp + 2
    sep #$20
.a8
    rts
.endproc

; ¿La zona `temp` tapa la celda donde está parado el héroe? Vuelve con el
; acarreo puesto si sí, y con X en el número de zona, que es lo que indexan las
; tablas de un byte. El rectángulo es **semiabierto** —`l <= x < r`—, que es lo
; que dice `Rect::IsOutOfBounds` de easyrpg con el héroe como un rectángulo de
; una celda.
.proc enc_tapa
.a16
.i16
    lda temp
    asl a
    tax
    lda tile_x
    cmp f:enc_izq, x
    bcc afuera
    cmp f:enc_der, x
    bcs afuera
    lda tile_y
    cmp f:enc_arr, x
    bcc afuera
    cmp f:enc_aba, x
    bcs afuera
    ldx temp
    sec
    rts
afuera:
.a16
    ldx temp
    clc
    rts
.endproc

; El paso del xorshift de los encuentros: el mismo de `azar_siguiente` y de
; `ba_azar`, sobre `ENC_SEM`, que tiene **semilla propia**. Caminar no le corre
; el azar al mapa: un `ControlVars` al azar tiene que dar lo mismo con
; encuentros y sin ellos. Es `eventos.Encuentros._azar`.
.proc enc_azar
.a16
.i16
    lda ENC_SEM
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor ENC_SEM
    sta ENC_SEM
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor ENC_SEM
    sta ENC_SEM
    xba
    and #$FF00
    eor ENC_SEM
    sta ENC_SEM
    rts
.endproc

; Hasta el próximo banco: los datos generados arrancan pegados a uno, que es lo
; único que `tools/ensamblado/bancos.py` supone del mapa de memoria.
.align $8000

; --- cabecera y vectores ---------------------------------------------------
.segment "HEADER"
    ; Es lo que muestra el menú del FX Pak y lo que lee cualquier base de datos
    ; de ROMs. Decía "ABL SNES MUSIC POC" hasta el 2026-09-09, de cuando esto era
    ; una prueba de audio; en hardware se ve, así que dejó de dar igual.
    .byte "A BLURRED LINE       "  ; 21 caracteres
    .byte $30                      ; LoROM, FastROM: ver MEMSEL
    .byte $02                      ; ROM y RAM con batería: la partida guardada
    .byte $0C                      ; tamaño: 4 MB (el byte es log2 de los KB)
    .byte $05                      ; SRAM: 32 KB, y se usan cuatro ranuras de 2048
    .byte $01                      ; región
    .byte $00                      ; desarrollador
    .byte $00                      ; versión
    .word $FFFF                    ; complemento del checksum
    .word $0000                    ; checksum

.segment "VECTORS"
; De $FFE0 a $FFFF. Los primeros ocho son los vectores del modo nativo y los
; otros ocho los del modo emulación, que es en el que arranca la consola. El
; que importa es RESET, en $FFFC.
    .word $0000     ; $FFE0  sin usar
    .word $0000     ; $FFE2  sin usar
    .word $0000     ; $FFE4  COP nativo
    .word $0000     ; $FFE6  BRK nativo
    .word $0000     ; $FFE8  ABORT nativo
    .word nmi_boot  ; $FFEA  NMI nativo: cuenta los cuadros del arranque
    .word $0000     ; $FFEC  sin usar
    .word irq_musica ; $FFEE  IRQ nativo: la música, ver `irq_musica`
    .word $0000     ; $FFF0  sin usar
    .word $0000     ; $FFF2  sin usar
    .word $0000     ; $FFF4  COP en emulación
    .word $0000     ; $FFF6  sin usar
    .word $0000     ; $FFF8  ABORT en emulación
    .word $0000     ; $FFFA  NMI en emulación
    .word reset     ; $FFFC  RESET
    .word $0000     ; $FFFE  IRQ y BRK en emulación
