; --- la RAM del banco 1 ------------------------------------------------------
; La BSS del banco 0 está llena —7680 de 7680— y el ZEROPAGE también, 256 de
; 256; acá decía que al ZEROPAGE le sobraban doce y hace rato que no.
; La consola tiene 128 KB de WRAM y la ROM usa ocho: al resto se llega
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

; Y qué habilidades sabe cada actor, desde el 2026-09-21: un bit por par (actor,
; habilidad), con la ranura que el conversor le dio a cada par —ver
; `HABILIDAD_RANURA` en eventos.py—. Arranca con lo que el LDB dice a su nivel
; inicial, que `hab_inicial_poner` copia en el reset, `ChangeSkills` lo prende y
; lo apaga, y viaja en la partida. Cuántos bytes son lo dice `HAB_BYTES`, y el
; conversor se corta si pasan de 256.
;
; **$6000 a $60FF es de esto**: el tramo se reservó de antemano, al repartir
; entre tres trabajos que corrían a la vez y tocaban la RAM lejana.
FAR_HAB = $6000

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

; --- la experiencia y el nivel: su estado en la RAM lejana --------------------
;
; Cuatro bytes por actor que puede pelear, en el orden de `experiencia_ranuras`
; del conversor —`actor_exp_k` dice cuál le toca a cada número de actor, o $FF—:
; la experiencia de 24 bits, que en RM2k llega a 999999, y el nivel. Que el
; nivel vaya pegado a la experiencia es lo que hace que la partida lleve un solo
; renglón para los dos. Arranca desde `exp_inicial` en el reset y viaja en la
; partida.
;
; $6200 a $63FF es el lugar que se le dio a esto el 2026-09-21, repartido entre
; tres ramas: el mapa de arriba termina en la pelea, que no pasa de $3CFF.
FAR_EXP     = $6200
EXP_NIVEL   = 3             ; el nivel, el cuarto byte
; Y, al final del mismo lugar, ocho bytes donde `texto_nivel` y sus hermanas
; componen el nivel y el máximo que el menú escribe: son números de la partida
; y ya no tiras del cartucho. Las ranuras llegan a 128 antes de pisarlos, y el
; conversor corta mucho antes: ver `experiencia_asm`.
EXP_TEXTO   = $7E63F8
; `MaxExpValue()` de RM2k, en sus dos mitades.
EXP_TOPE_HI = $0F
EXP_TOPE_LO = $423F

; --- las páginas de tropa: su estado en la RAM lejana -------------------------
;
; $6400 a $65FF es el lugar que se le dio a esto el 2026-09-21. **No viaja en
; la partida**, como nada de la pelea. Se nombra con dirección de dieciséis
; bits, igual que `FAR_BATALLA`, porque lo lee el código de la pelea con el
; banco de datos en $7E; el puente del banco 0 le pone `BAT_LARGO` adelante.
FAR_PAG       = $6400
BA_PAG_N      = FAR_PAG + 0     ; cuántas páginas trae la tropa de esta pelea
BA_PAG_INI    = FAR_PAG + 1     ; palabra: la primera, en las tablas `tpag_*`
BA_PAG_COD    = FAR_PAG + 3     ; palabra: dónde empieza la que corre, en el
                                ; banco de `tropa_codigo`
BA_PAG_CUR    = FAR_PAG + 5     ; palabra: su cursor, el `ev_cur` de ella
BA_PAG_ACT    = FAR_PAG + 7     ; si todavía no terminó: su `ev_activo`
BA_PAG_MSG    = FAR_PAG + 8     ; palabra: el mensaje que pidió y está en
                                ; pantalla, en `mensajes_tropa`, o $FFFF
BA_PAG_VUELTA = FAR_PAG + 10    ; por dónde sigue la pelea cuando no quedan:
                                ; 0 la acción que sigue, 1 pedir las órdenes
BA_PAG_I      = FAR_PAG + 11    ; por cuál va el barrido
BA_PAG_G      = FAR_PAG + 12    ; palabra: esa misma, en las tablas `tpag_*`
BA_PAG_HECHA  = FAR_PAG + 16    ; TROPA_PAG_MAX bytes: ya corrió este turno

; --- una medicina fuera de la pelea: su escritorio en la RAM lejana ----------
;
; $6800 a $68FF es de esto, reservado el 2026-09-21 al repartir. **No viaja en
; la partida**: dura lo que dura un A en la elección de actor. Se nombra con
; dirección de dieciséis bits porque `medicina_usar` corre con el banco de
; datos en $7E.
FAR_MED       = $6800
MED_ACTOR     = FAR_MED + 0     ; el actor, por número del LDB
MED_BANDERAS  = FAR_MED + 1     ; los bits de `item_medicina` del ítem
MED_USADO     = FAR_MED + 2     ; si sirvió: el `was_used` de easyrpg
MED_REVIVIO   = FAR_MED + 3     ; palabra: 1 si lo levantó, el `revived`
MED_HP_MAX    = FAR_MED + 5     ; palabra: los HP máximos de su nivel
MED_SP_MAX    = FAR_MED + 7     ; palabra: y los SP
MED_HP        = FAR_MED + 9     ; palabra: el `hp_change`
MED_SP        = FAR_MED + 11    ; palabra: el `sp_change`
MED_P         = FAR_MED + 13    ; cuatro bytes: el producto, y el cociente
MED_R         = FAR_MED + 17    ; palabra: el resto
MED_ID        = FAR_MED + 19    ; palabra: el número de RM2k del ítem

; Lo que `par_ev` vale mientras corre una página de tropa: ni el primer plano
; ($FF) ni un evento del mapa, que son menos de EV_MAX. Es lo que le dice a
; `op_message` que el mensaje es de la pelea. Ver `ba_t_pagina`.
PAR_PELEA = $FE
.assert EV_MAX < PAR_PELEA, error, "PAR_PELEA tiene que no ser un evento"

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
; Si hay escena en BG1 —0— o esta pelea va sobre negro —$FF—: sin fondo y
; sin ningún battler. Ver `escena_subir`.
BA_ESCENA   = FAR_BATALLA + 44
; Y en qué lugar de `tropa_id` cayó la tropa de esta pelea, que es lo que
; `escena_tropa_fondo` indexa. $FF: el cartucho no la lleva.
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
; Corriendo una página de tropa, con su mensaje en pantalla o sin él: ver
; `modo_pagina`. Va detrás de los de mensaje porque no elige nada.
BA_M_PAGINA = 7
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
; segundo efecto sale veinticuatro cuadros más tarde. Los veinticuatro se
; eligieron cuando los efectos tenían una sola voz y el nuevo le pisaba la voz
; al anterior, así que tenían que quedar separados de oído; desde 8c9c182 son
; dos voces —ver `efectos_de_sonido.s`— y dos efectos distintos ya no se
; pisan; el mismo efecto dos veces sí, porque `sonido_tocar` lo vuelve a
; disparar en la voz que ya lo toca.
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

; --- las tiras de repuesto, en la RAM lejana --------------------------------
;
; La cámara destapa hasta **dos** filas o dos columnas por vuelta —ver
; `stream_map`—, así que hay que tener dos tiras armadas a la vez y el vblank
; sube las dos. El segundo juego vive acá y no en el banco 0 porque ahí no
; entra: a la BSS le quedan 84 bytes y esto pide 384.
;
; $6A00 a $6B7F es de esto, reservado el 2026-09-22. **No viaja en la
; partida**: dura lo que dura un cuadro.
FAR_TIRA_ROW  = $7E6A00         ; WINDOW_COLS * 2
FAR_TIRA_ROW2 = $7E6A80         ; y la capa de encima, pegada como en el banco 0
FAR_TIRA_COL  = $7E6B00         ; WINDOW_ROWS * 2
FAR_TIRA_COL2 = $7E6B40
; Pegadas, que es de lo que se aprovecha `push_una_fila` para llegar a la de la
; capa de encima sumando el largo de la otra, igual que con las del banco 0.
.assert FAR_TIRA_ROW2 = FAR_TIRA_ROW + WINDOW_COLS * 2, error, "tiras de fila separadas"
.assert FAR_TIRA_COL2 = FAR_TIRA_COL + WINDOW_ROWS * 2, error, "tiras de columna separadas"

; --- dónde está el tilemap del fondo, en la RAM lejana ----------------------
;
; La palabra de VRAM del tilemap de BG1 del mapa cargado. La copia `cargar_mapa`
; de `M_VRAM_MAP` y la suman `build_column` y `build_row`, que no pueden leer
; la tabla porque tienen la X ocupada. Es $5800 en todos los repartos menos uno:
; ver LAYOUT_VENTANA_AMBOS. En la BSS no entra.
;
; $6B80 y $6B81 son de esto, reservados el 2026-09-25. **No viaja en la
; partida**: cargarla carga el mapa, y eso la vuelve a poner.
FAR_VRAM_MAPA = $7E6B80

; --- las paletas de los destellos, en la RAM lejana -------------------------
;
; Una por ranura de destello, treinta y dos bytes cada una, y el vblank sube
; todas las que quedaron pendientes. Tiene que ser una por ranura: con una sola,
; dos destellos vivos en el mismo cuadro se la pisaban, subía la del último, y
; el cuadro que apaga al primero no llegaba nunca a CGRAM. En la BSS no entran.
;
; $6900 a $69FF es de esto, reservado el 2026-09-23. **No viaja en la
; partida**: dura lo que dura un cuadro.
FAR_FLASH_PAL = $7E6900         ; FLASH_MAX * 32
.assert FLASH_MAX * 32 <= $100, error, "las paletas de destello se salen de su lugar"

; --- el decodificador de la música, en la RAM lejana -------------------------
;
; El estado de `music_frame`, que expande el stream por nota a escrituras al
; DSP: ver "el formato por nota" en tools/audio/snes_music.py. Lo lee y lo
; escribe `irq_musica`, que cae en cualquier punto del código principal, así
; que se llega con direccionamiento largo y nunca por la ventana de WMADD.
;
; $6C00 a $6FFF es de esto, reservado el 2026-09-26. **No viaja en la
; partida**: arrancar el tema lo pone en cero.
;
;   MUS_SOMBRA   lo último que el stream le escribió a cada registro de voz,
;                indexado por el número del registro —$v0 a $v7—, y en el $v8,
;                que es ENVX y no se escribe, el GAIN del release del sonido
;                de la última nota de la voz
;   MUS_ESPERA   palabra: cuántos cuadros faltan para leer el stream
;   MUS_KON      las voces que recibieron nota en el cuadro que se está leyendo
;   MUS_SONANDO  las que se dispararon al cerrar el anterior: se bajan al abrir
;   MUS_BASE     palabra: dónde empiezan los sonidos del tema en `musica_sonidos`
;   MUS_VISTAS   las voces que ya tuvieron una nota desde que arrancó el tema
;   MUS_GAINS    las que ya recibieron un GAIN
;   MUS_BIT      el bit de la voz del evento que se está leyendo
;   MUS_T        palabra de paso
FAR_MUSICA   = $7E6C00
MUS_SOMBRA   = FAR_MUSICA
MUS_ESPERA   = FAR_MUSICA + $80
MUS_KON      = FAR_MUSICA + $82
MUS_SONANDO  = FAR_MUSICA + $83
MUS_BASE     = FAR_MUSICA + $84
MUS_VISTAS   = FAR_MUSICA + $86
MUS_GAINS    = FAR_MUSICA + $87
MUS_BIT      = FAR_MUSICA + $88
MUS_T        = FAR_MUSICA + $89
; Los bytes de MUS_ESPERA a MUS_T, que `musica_limpiar` pone en cero.
MUS_ESTADO_BYTES = $0B
; La bitácora de lo que el stream le pide al DSP: `dsp_musica` anota cada par
; (registro, valor) acá si MUS_BITACORA_SI no es cero, y MUS_BITACORA_I es
; dónde va el que sigue, en bytes. Es la red de `test_musica_escrituras.py`:
; la prende la prueba, que la lee cuadro a cuadro. Da la vuelta a los 512
; bytes, 256 escrituras, y un cuadro de música no pasa de cien. Cada cuadro
; de música empieza con una marca, el registro MUS_BITACORA_MARCA —que el DSP
; no tiene—: la IRQ de un cuadro pesado termina después de que el emulador
; entregó el cuadro, y sin la marca sus últimas escrituras parecerían del
; siguiente.
MUS_BITACORA_MARCA = $FF
MUS_BITACORA_SI = FAR_MUSICA + $F0
MUS_BITACORA_I  = FAR_MUSICA + $F2     ; palabra
MUS_BITACORA    = FAR_MUSICA + $200
MUS_BITACORA_LARGO = $200
.assert MUS_BITACORA + MUS_BITACORA_LARGO <= $7E7000, error, "la bitácora se sale de su lugar"

; --- el cuadro de la animación de batalla, en la RAM lejana -----------------
;
; Los 2 KB del cuadro que el vblank sube a la caja. El cartucho no los guarda
; enteros —sólo los tiles que no son todo cero, ver `cuadro_sin_vacios` en
; snes_convert.py— y `anim_cuadro_armar` los rearma acá, fuera del vblank. El
; DMA de `animacion_dibujo_dma` sale de acá y no del cartucho.
;
; $7000 a $77FF es de esto, reservado el 2026-09-26. **No viaja en la
; partida**: cargar un mapa lo pone en cero.
ANIMB_BUF = $7E7000

; --- LZ2: lo que el cartucho trae comprimido, en la WRAM --------------------
;
; Ver `lz2_descomprimir` en descomprimir.s. Reservado el 2026-09-26:
;
;   $7E7800  las dos trampas de `mvn`, cuatro bytes cada una, que se arman con
;            los bancos de cada llamada, y el banco de la salida
;   $7F0000  el buffer de carga: cada bloque de tiles se descomprime acá y se
;            sube a la VRAM con el mismo DMA de antes. Vale sólo mientras se
;            carga; la escena de la pelea usa el banco $7F entero —ver
;            `ESC_LIMPIO`—, y nada de acá tiene que sobrevivirle
;   $7F6000  los dibujos de la animación del ChipSet del mapa, que `anim_subir`
;            sube cada vez que cambia el reloj: **viven mientras se esté en el
;            mapa**, y por eso van arriba del buffer y se descomprimen después
;            de los tiles del fondo y antes de la capa de encima y los
;            sprites. Lo que sí se los lleva es la pelea, y `volver_al_mapa`
;            los vuelve a descomprimir
;
; Los topes de cada bloque los cobra `descomprimir.s` contra los que emite el
; conversor.
LZ2_TRAMPA_LIT = $7E7800        ; mvn salida, flujo; rtl
LZ2_TRAMPA_REP = $7E7804        ; mvn salida, salida; rtl
LZ2_BANCO      = $7E7808        ; el banco de la salida
LZ2_BUFFER     = $7F0000
ANIM_DIBUJOS   = $7F6000
ANIM_DIBUJOS_FIN = $7F8000

; En qué cuadro termina el arranque, contado desde el reset. El arranque
; —cargar el mapa, subir el driver al SPC700 y el paquete de audio del mapa—
; tarda lo que tarda, y eso cambiaba con cada cambio de código o de datos: un
; bucle más y el lazo principal arrancaba un cuadro después, y cada receta que
; compara cuadros en movimiento lleva ese número medido a mano. Ahora se espera
; hasta este cuadro y el lazo arranca siempre en el mismo. Una ROM cuyo
; arranque tarde más que esto sale sin esperar, más tarde, pero igual de fijo
; para ella.
;
; Está dimensionado para el paquete del mapa de arranque, y **el conversor se
; corta si no entra**: la cuenta, por lo alto, es `cuadros_del_arranque` en
; tools/audio/snes_music.py. Medido el 2026-09-26: el trabajo de `release`
; termina en el cuadro 30 y la cuenta da 34. Era 112 hasta ese día, pensado
; para subir la ARAM llena por el IPL; ver
; workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md.
BOOT_CUADROS = 40
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

