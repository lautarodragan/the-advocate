---
name: "La pelea"
description: "EnemyEncounter abre una pelea por turnos"
---

### La batalla por turnos

`EnemyEncounter` abre una pelea. El alcance elegido fue la mecánica —turnos,
daño, HP, condición de victoria— antes que el dibujo, así que la pantalla es de
texto sobre negro, la misma grilla de 32 por 28 celdas del equipo y la tienda,
y el fondo con los battlers llegó después (ver más abajo).

Lo que sí es de RM2k son las palabras —todas del LDB— y **todas las cuentas**,
que salen de easyrpg-player y están escritas dos veces: en `main.s` y en
`tools/port/batalla.py`. Que las dos den lo mismo es lo que le permite a
`pruebas/rpgmaker/test_batalla.py` predecir **el número exacto** que cada HP va a tener
después de cada turno, en vez de conformarse con "bajó".

    daño            max(0, atk / 2 - def / 4), por 3 si es crítico, varianza
                    de 4 —`adj = max(1, 4 * dmg / 10)`— y la mitad al que se
                    defiende                        algo.cpp
    acierto         90 el actor, 70 u 90 el enemigo, ajustado por agilidad:
                    100 - (100 - hit) * (agiF + agiB) / (2 * agiF)
    orden de turnos agi + rand(0, agi / 4 + 3), de mayor a menor y estable
    huir            recortar(150 - redondear(100 * agiE / agiG), 0, 100), y
                    sube diez cada vez que falla

Tres tiros por golpe y **en este orden**: acierto, crítico y varianza, con el
del crítico hecho aunque la probabilidad sea cero, que es lo que hace
`Normal::vExecute`. Cambiar ese orden de un lado desfasa el azar del otro y no
se ve hasta que un golpe da distinto.

El azar es el xorshift de siempre —el de `ControlVars`— pero con **semilla
propia**: pelear no le corre el azar del mapa, que es lo que la referencia de
pixeles supone cuando dice que una batalla no cuesta ningún tick.

`OP_BATTLE` lleva la tropa y **los tres destinos**: victoria, huida y
derrota, absolutos dentro de la página y parcheados al cerrar el bloque, igual
que las opciones de un `ShowChoice`. El manejador que la página no tenga
apunta al final, que es lo que hace RM2k con un sub-índice sin rama. Como la
tienda y como guardar, la pantalla bloquea adentro del intérprete y `vueltas`
no avanza: los dos lados salen del opcode en el mismo tick tarde lo que tarde
el jugador.

#### La pelea sin manejadores, y el Game Over

Hay una forma de `EnemyEncounter` que no trae bloque de manejadores: RM2k no lo
emite cuando `defeat_mode` es 0, porque entonces perder no es una rama de la
página sino `Scene_Gameover`. Son **24 comandos en 15 páginas disparables** del
juego, tres de ellas el `EV0006` del mapa 26, o sea el jefe de los Rat Tracks.
Compilarlas fueron dos trabajos que sólo sirven juntos —el Game Over y el bloque
que sin `EndBattle` no cierra—: cualquiera de los dos solo destraba **+0**, y los
dos, **+15**.

El compilador mira adelante, como con las opciones de un `ShowChoice`: si
al `EnemyEncounter` no le sigue un manejador, emite el `OP_BATTLE` en el acto,
con victoria y huida en el comando de abajo y la derrota en `BATALLA_PERDER`.

**`BATALLA_PERDER` es $FFFF**, o sea un destino imposible —los tres son
absolutos adentro de la página y ninguna del juego llega a 64 KB—, así que el
Game Over no cuesta un opcode nuevo ni un byte más en las otras peleas. La ROM
lo mira en `op_battle` con un `iny`/`bne`, que es el `cmp #$FFFF` barato, y
responde con `jml reset`: **Game Over es volver al arranque**, o sea a la
pantalla de título si el cartucho la lleva, con la partida guardada esperando en
la SRAM. Es lo que `Scene_Gameover` hace al final, menos la imagen y menos el
tema; los dos están declarados en `assets/LIMITACIONES.md`.

Ese camino **la tanda de pixeles no lo puede ver**: una derrota reinicia la
consola, así que no hay cuadro que comparar contra una golden.
Lo cobra `pruebas/rpgmaker/test_game_over.py`, que pone el grupo entero en cero HP —con
nadie en pie `batalla_correr` contesta derrota sin abrir la pantalla— y exige
que la ROM se reinicie, con el control de la misma pelea apuntando a la página.

**Y el encuentro al azar pierde por el mismo camino.** Una pelea que arranca
del azar de los pasos no tiene bytecode detrás —la abre `pelea_arrancar` desde
`move_hero`— así que no hay destino que resolver ni manejadores que emitir:
perderla es siempre `Scene_Gameover`, y el llamador compara con `BA_DERROTA` y
hace el mismo `jml reset`. Sin eso la derrota devuelve el control al mapa y, como
`modo_fin` guarda los HP de la pelea en `FAR_HP`, el grupo queda en cero **para
siempre** y toda pelea siguiente se pierde sola antes de abrirse. Lo cobran dos
casos más de `test_game_over.py`, con el mapa 21 y `--encuentros-de-prueba`.

Y una aproximación declarada: las 24 peleas de esta forma traen `escape_mode` 0,
o sea huir prohibido, y la ROM deja huir igual porque el permiso no viaja en el
opcode. Huir sale por el mismo destino que ganar.

**El código de la pelea no vive en el banco 0.** Son unos tres kilobytes y ahí
quedaban trescientos bytes, así que vive en RODATA y se entra con `jsl`. De
allá no se puede volver con `jsr` —no cambia el banco de programa— así que las
rutinas del banco 0 que necesita se llaman por puentes de siete bytes que
además **reponen el banco de datos**: adentro de la pelea es $7E, para poder
usar direccionamiento absoluto sobre su estado, y en el banco 0 tiene que ser
el 0 o `eq_parametro` leería sus tablas de la WRAM.

**Los HP pasaron a ser estado.** Hasta ese día nadie bajaba de los máximos y
`ChangeHP` compilaba a nada; ahora viven en `FAR_HP`, arrancan llenos en el
reset como `Game_Actor::Setup` y **viajan en la partida**, detrás del equipo.

Lo que hay, y lo que no:

    atacar, con blanco elegible     sí
    defender                        sí, y vale sólo el turno en que le toca
    huir                            sí, pero es orden de cada actor y no del
                                    grupo, que es una simplificación declarada
    usar un ítem                    sí: ver abajo
    habilidades                     sí: ver abajo
    los estados                     no
    experiencia, oro, subir nivel   no: no hay niveles
    la música y los efectos         sí: ver abajo
    los battlers dibujados          sí, horneados en el fondo: ver abajo
    la imagen de fondo              sí
    las páginas de evento de tropa  no
    los encuentros aleatorios       sí: ver abajo

La pantalla muestra los HP de los enemigos, que RM2k no hace. Es a propósito:
lo que esta vuelta tiene que dejar ver es la mecánica, y sin eso un golpe que
pega y uno que falla se ven igual.

**De las 51 peleas del juego, la única que el jugador alcanza hoy es la del
droide del mapa 2.** La de los Lazer Teeth del mapa 9 —la tropa 86, cuatro
enemigos— no compila, y no por la batalla: la corta un `MoveEvent` con la
orden de ruta 9, "hacia el héroe", que la ROM no camina. Por eso la tropa de
cuatro la ejercita `test_batalla` con la página de prueba, que es el mismo
recurso que usan los casos de la pantalla de ranuras.

#### El menú: las cinco órdenes del ABL

Son las cinco del original, en los dos renglones del mensaje: tres arriba y dos
abajo, que mientras se elige está libre. Las palabras son las del LDB, y el ancho
es diez porque es lo que mide la orden más larga.

**El orden es el del original**: Attack, la habilidad, Defend, Use Item. Se ve
en `pruebas-manuales/capturas-batalla/auto_20260912_123013.png`, donde el menú
de Manta dice Attack / Slicing / Defend / Use Item. `Escape` no está allá —huir
es una orden del grupo, de un menú anterior— y acá va quinta, que es la
simplificación declarada.

**Y la segunda orden no dice "Tech Skill"**: dice el `skill_name` del actor que
está ordenando —"AgentTrain" con Kersh, "Telepathy" con Core, "Slicing" con
Manta, "Special" con Talan—, que es `Game_Actor::GetSkillName` con
`rename_skill` puesto. Su texto sale de `actor_hab_txt`, que es por número de
actor, y no de `ba_orden_txt`, que es fijo como el de las otras cuatro. La
columna en la que va tiene que dejarle **diez celdas libres**: "AgentTrain" y
"Tech Skill" miden diez justos y no le dejan lugar al cursor del que sigue, que
va una celda antes del texto.

**Las dos tablas son de dos bytes, y eso no es de adorno.** Un índice de texto
nombra un renglón del bloque que comparten las pantallas de ítems, equipo,
tienda y batalla, y ese bloque crece con el cartucho: con los 57 ítems de
`abl` los textos de la batalla arrancan en el 273, que en un byte no
entra. El caso que lo cuida es `batalla-textos-lejos`, y `ca65` **rechaza** un
`.byte` que no entre en un byte en vez de truncarlo.

`Use Item` anda. Abre la lista de lo que se puede usar **donde va la de los
enemigos**, porque eligiendo qué usar lo que hace falta ver es el grupo; se
elige el ítem, después a quién, y con eso queda anotada la orden de ese actor,
que se ejecuta en su turno como cualquier otra. B vuelve un paso.

Qué entra en la lista y cuánto cura sale de easyrpg-player:

* **Qué entra**: `Game_Party::IsItemUsable` con la pelea abierta, o sea una
  medicina que no esté marcada "sólo fuera de batalla". De ésas, este port
  ofrece las que **recuperan HP y no son `ko_only`**: las de SP quedan afuera
  porque la lista todavía sólo sabe curar HP —los SP **sí** son estado, así que
  eso pasó de imposible a deuda—, y las de revivir porque revivir es sacar el
  estado de muerto y los estados no existen. Son 12 de las 22 medicinas del
  juego, de la Potion de 50 a la Miracle Drop, que cura todo.
* **Cuánto cura**: `Game_BattleAlgorithm::Item::vExecute`, o sea
  `recover_hp_rate * GetMaxHp() / 100 + recover_hp`, topado contra lo que le
  falta al blanco, que es el `ChangeHp`. La cuenta está escrita dos veces
  —`main.s` y `batalla.curacion`— como todo lo demás de la pelea, y por eso
  `test_batalla.py` puede exigir el número exacto. El producto entra en una
  palabra: el conversor corta si algún actor pasa de 655 HP.

Dos cosas que son de RM2k y conviene no "arreglar": **el ítem se gasta al
elegirlo** y no al usarlo —si no, el último de un ítem se podría repartir entre
dos actores en el mismo turno— y **el blanco muerto no se reapunta**, que es lo
contrario de lo que hace un ataque: el ítem se gasta igual.

Lo cobran cinco casos. Dos de la tanda —la lista de ítems y la elección del
blanco, pixel por pixel contra `pantallas.py`— y tres de estado: que la lista
sea la que corresponde (con un ítem inusable en el inventario, o no mediría
nada), que la poción deje el HP exacto que dice el modelo topando contra el
máximo, y que el menú recorra las cinco órdenes en el orden del original.
Todos verificados en rojo con su defecto puesto.

#### Las habilidades

Lo que las destraba no es la pantalla sino leer el `initial_level` del LDB en vez
de mockear el nivel en 1. Con los niveles de verdad —Kersh 20, Core y Manta 15—
los tres saben las suyas desde la primera pelea: siete entre los tres, 131 y 146
Kersh, 129 y 150 Core, y 130, 143, 144 y 150 Manta.

**Qué sabe cada uno**: `Game_Actor::LearnLevelSkills` recorre la tabla de
aprendizaje del actor y aprende las de nivel menor o igual al suyo, y
`LearnSkill` las mete en `data.skills` **ordenadas por número**. Ése es el orden
en que la lista las muestra, y la captura del original lo confirma: las cuatro
de Manta salen Mental Hack y MindShield arriba, MindProbe y MindBlast abajo, o
sea 130, 143, 144, 150 leídos **por filas** en dos columnas.

**Los SP son estado**, por lo mismo que los HP desde que hay batallas: cada
habilidad cuesta su `sp_cost` y `Skill::vStart` se lo descuenta al que la usa.
Viven en `FAR_SP`, arrancan llenos desde `actor_spmax` y viajan en la partida,
detrás de los HP.

**La pantalla** es la de la captura `auto_20260912_123023.png`: donde va la
lista de enemigos, la descripción de la que marca el cursor arriba de todo y
abajo dos columnas con el nombre a la izquierda y el costo en SP a la derecha,
con un guión delante. En gris la que no se alcanza a pagar, y la lista entera
en gris mientras se elige el blanco, que es lo que la de ítems ya hacía.

**Qué hace cada una**, de `Game_BattleAlgorithm::Skill::vExecute`:

* una de tipo `switch` prende su `switch_id` y **termina ahí**, sin tirar
  ningún dado. Tres de las siete son de ésas —MindShield, MindProbe y
  MindBlast— y en el juego original son las que abren rama de trama más
  adelante: acá prenden el switch y falta el evento que lo mire.
* las demás calculan `Algo::CalcSkillEffect`:
  `power + physical_rate * atk / 20 + magical_rate * spi / 40`, menos
  `physical_rate * def / 40 + magical_rate * spi / 80` del blanco cuando apunta
  a enemigos, y después la varianza con el `variance` de la habilidad.
* y lo aplican a lo que la habilidad marque: HP —Fury Punch y Healing Syringe—
  o **los modificadores de parámetro** del blanco —Agency Badge le baja ataque,
  defensa y agilidad; Mental Hack, defensa y espíritu—.

Los modificadores son lo único que pidió estado nuevo por combatiente, y no es
el modificador solo: `CanChangeAtkModifier` topa la bajada en la mitad del
parámetro **base**, así que hacen falta el base y el modificador por separado
—de la resta no se despeja un modificador que sobrevivió al recorte—. Por eso
`BA_BYTES` pasó de 18 a 40, con los cuatro bases, los cuatro modificadores y
los SP; el efectivo que las cuentas leen es `clamp(base + mod, 1, 999)`, que es
`AdjustParam` de game_battler.cpp.

**El orden en que consume azar es el contrato con `batalla.py`**, y sale de
leer `vExecute` de arriba abajo: el switch vuelve antes de cualquier tiro; el
crítico se tira **siempre**, aunque la chance sea cero —y para una habilidad
del LDB siempre lo es, porque `CalcCriticalHitChance` recibe
`easyrpg_critical_hit_chance`, que por defecto vale 0 y no -1—; después la
varianza; y después un tiro contra el acierto por cada cosa que la habilidad
afecta, en el orden HP, SP, ataque, defensa, espíritu, agilidad.

Lo que **no** está, declarado en `batalla.habilidad_usable`: los alcances de a
muchos —`enemies`, `party`, `self`—, que pedirían repetir el efecto sobre cada
blanco y con eso el orden del azar de los dos lados. En el grupo de la intro no
hay ninguna; en un cartucho con más actores cae `Gamble for Credits`, la única
de Arden, y Arden aparece sin habilidades. Tampoco hay animación de batalla al
usarlas: el `animation_id` viaja en el LDB y el port ya sabe dibujar
animaciones, pero nadie las conectó.

**Y los SP no se ven en la pantalla de la pelea.** Los renglones del grupo son
nombre, HP y máximo, y en las 32 celdas no entra además "SP nnn" sin achicar la
columna del nombre, que la comparten con los enemigos —"GangMember LT" mide
trece—. El original los muestra. Hoy lo único que avisa de que uno se quedó sin
SP es que la habilidad se pone en gris.

Lo cobran diez casos. Tres de la tanda —la lista, la lista con el cursor en
otra habilidad y la lista en gris mientras se elige a quién curar, pixel por
pixel contra `pantallas.py`— y siete de estado, que comparan contra
`batalla.Batalla.usar_habilidad` exigiendo el número exacto: los HP y los SP
turno por turno con Fury Punch, el switch que prende MindShield —y que el azar
**no** se haya movido—, la cura de Healing Syringe sobre un aliado lastimado,
los tres parámetros que Agency Badge le baja al droide, que la lista de cada
actor sea la que el LDB dice, que el menú recorra las cinco órdenes, y que un
actor sin ninguna —Talan, que es de nivel 1— no abra la lista.

#### El fondo y los monstruos: una sola imagen

El fondo y los battlers van juntos **porque son el mismo dibujo**: el conversor
compone el fondo de batalla con los battlers de la
tropa encima y el cartucho lleva el resultado como una capa de 8bpp de
256x128, los siete renglones de texto de arriba. La consola no dibuja
battlers: sube una imagen. El porqué largo, el presupuesto y lo que se pierde
están en `tools/port/escena.py`; el titular:

* **El fondo sale del propio `EnemyEncounter`**, que trae el nombre en su
  string: `SJBackdropABL04` para el droide del mapa 2 y `ABLBackdropSJ03` para
  los Lazer Teeth del 9.
* **Todo al 80%.** El fondo de RM2k mide 320x160 en una pantalla de 320x240 y
  acá la pantalla es de 256x224, así que entra escalado a 256x128. Los
  battlers van al mismo 80%, con lo cual las posiciones del LDB —que son las
  del centro de cada uno— se mapean multiplicando por lo mismo. Lo único que
  no es de RM2k es el recorte: un battler alto se topa adentro de la escena,
  porque allá abajo le quedan otros ochenta pixeles de pantalla y acá no.
* **512 tiles, 32.768 B de VRAM y 96 colores**, las entradas 32 a 127 de la
  CGRAM: las 0 a 31 son las dos paletas del texto y de 128 para arriba son las
  de los objetos. Los tiles no se deduplican —una foto no repite: 490 y 503 de
  512 en los dos fondos del juego— y por eso el número es fijo.
* **Entra sin pelearle a nada** porque la pelea se lleva por delante media VRAM
  del mapa y lo que se lleva se rehace al salir. El texto vive en $2000, su
  tilemap en $3C00, el de la escena en $3800 y los tiles de la escena en
  $4000, que son las últimas 16.384 palabras de la VRAM.

  **Rehacerla no es `volver_al_mapa`.** Aquél repone lo que pisan la tienda, el
  menú y las ranuras, que escriben nada más que `RANURA_VRAM` y `RANURA_MAP`
  —elegidos para caer adentro del banco de tiles de BG1 en los cuatro repartos,
  y el conversor lo comprueba—. Los 32 KB de la escena se salen de esa caja: se
  llevan además el tilemap del mapa ($5800), el de la capa de encima ($7800),
  los tiles de la ventana de mensaje ($6800) y el banco de sprites. Volver de
  una pelea es `volver_de_batalla`, que repone eso con `load_sprite`,
  `load_ventana` y `fill_window` antes de llamar al otro. Lo cobra
  `vuelta-ventana`; sin el arreglo, el 77% de los pixeles.

Dos cosas del PPU que no son obvias —el bit de prioridad del texto y el tile
512 con que se tapa lo que queda abajo— están anotadas arriba de `escena_subir`
en `main.s`, que es donde muerden.

**Lo que cuesta, declarado**: un enemigo muerto se sigue viendo. En RM2k
desaparece; acá lo que dice que murió es su renglón —el nombre en gris y los
HP en cero—, que es la misma razón por la que esta pantalla muestra los HP de
los enemigos y RM2k no. Y una escena es **por tropa** y no por fondo: dos
tropas con el mismo fondo llevan las dos escenas, a 32 KB cada una.

Lo cobra la tanda, con los dos fondos del juego: `batalla` con la tropa
86 —cuatro battlers iguales, uno de ellos topado contra el borde— y con la 82
—uno solo—, los dos en cero. Verificado que da rojo corriéndole a la ROM el
`BG1VOFS` un scanline.

Y hay un tercer caso que no mira el dibujo sino **el índice**: la misma tropa
86 en un cartucho que además lleva el mapa 2, o sea con dos tropas y dos
escenas. Es el único donde la pelea no es la tropa 0, y para que exista hubo
que mover una línea: la tropa de la página de prueba se pide **al final** y no
antes de compilar los mapas, igual que `temas_de_la_rom` agrega el tema del
mapa al final. Pidiéndola antes le tocaba siempre el índice 0 y `escena_de` y
`tropa_id` acertaban sin indexar nada. Verificado que da rojo —53% de los
pixeles— con `escena_subir` clavado en la escena 0.

#### Los encuentros al azar

**Los datos no están en el `.lmu`, están en el árbol.** `RPG_RT.lmt` guarda por
nodo —mapa o área— tres campos que este port no leía: `encounters`, la lista de
tropas; `encounter_steps`, cada cuántos pasos; y `area_rect`. Un **área** es un
nodo de tipo 2: no tiene `.lmu`, cuelga de un mapa y le tapa un rectángulo —no
es una carpeta del editor, que es lo que parece—.

Medido sobre el juego entero:

    23 áreas, colgando de 20 mapas
    33 mapas con tropas propias, ninguno de ellos con área
    53 mapas donde puede salir un encuentro, de 328
    5 de los 29 de `abl`: el 20, el 21, el 26, el 28 y el 32
    129 tropas distintas

**Cómo se dispara**, de `Game_Player::UpdateEncounterSteps`. Cada paso del
héroe **con el pad** suma el `encounter_rate` del terreno a un acumulado; el
cociente entre el acumulado y `encounter_steps` elige una fila de una tabla de
ocho, y la fila da un multiplicador `pmod` que va de 1/16 a 16. La chance del
paso es `pmod / encounter_steps`, y la fila **no baja nunca** hasta que sale un
encuentro: por eso los primeros cincuenta pasos de un mapa casi no pasa nada y
después la cosa se acelera.

Los pasos de una **ruta forzada no cuentan**: allá `UpdateNextMovementAction`
vuelve antes de `IncSteps` si la ruta manda. Y todo teletransporte borra el
acumulado, porque `Game_Player::MoveTo` llama a `SetTotalEncounterRate(0)`.

Cuando sale, queda **pendiente** y se cobra en el cuadro siguiente, con el
héroe ya parado y sin página ni mensaje: ahí `PrepareEncounter` junta las
tropas del mapa más las de cada área que tape la celda y elige una al azar. Si
no lo tapa ninguna —el héroe está afuera del rectángulo— no pasa nada.

**Dos simplificaciones, las dos medidas y las dos cobradas por
`pruebas/herramientas/test_encuentros.py`:**

* **el terreno no cambia nada.** Los once tags que pisan los 53 mapas con
  encuentros tienen `encounter_rate` 100, así que el acumulado sube de a 100 y
  el factor `rate / 100` de la fórmula es 1. Leer el terreno celda por celda
  sería una capa más de datos por mapa para multiplicar siempre por uno;
* **ninguna tropa filtra por terreno.** Las 129 tienen el `terrain_set` vacío,
  y en RM2k vacío quiere decir "en todos".

Si alguna de las dos dejara de ser cierta, el modelo pasaría a ser mentira
**sin que ningún pixel se mueva**. Por eso lo cobra una prueba de datos y no la
tanda.

**Todas las cuentas son enteras**, que es lo que la consola puede hacer. El
conversor precalcula dos cosas por mapa: `1 / encounter_steps` en 1/65536
—`enc_base`— y en qué paso se cruza cada fila —`enc_umbral_n`—, que sale de
reescribir `acumulado / pasos >= fila` como `n >= ceil(fila * pasos / 100)`.
Con eso la consola no divide nunca: la chance es el corrimiento de una palabra
y la comparación contra un xorshift. `test_encuentros.py` comprueba las dos
reescrituras contra la cuenta de allá, para todos los `encounter_steps` del
juego.

**El azar es el de siempre pero con semilla propia** —`ENC_SEMILLA`—, como la
pelea con `BATALLA_SEMILLA`: caminar no le corre el azar al mapa, así que un
`ControlVars` al azar da lo mismo con encuentros y sin ellos, y
`eventos.Encuentros` sigue pudiendo predecir los dos. Se consume un número por
paso y uno más para elegir la tropa, y ése es el contrato con esa clase.

**Dónde vive cada cosa.** El estado son nueve bytes en la RAM lejana,
`FAR_ENCUENTRO` en `$7E3900`: en el banco 0 no entraban —la BSS está llena, y
medir cuánto falta es meterle un `.res N` y leer por cuánto se pasa, que `ld65`
lo dice—. Las tablas y las tres rutinas viven **fuera del banco 0**, en `FAR`, y
del lado de allá quedan nada más que cuatro `jsl` y el puente a la pelea, 43
bytes. Ni ésos entraban, así que bajó `item_switch` a RODATA —124 bytes, la
tabla más grande de las que se leen con X y no están en un lazo por cuadro—. Y
la pelea se arranca con `pelea_arrancar`, que es el cuerpo de `op_battle`
sacado a una rutina aparte: un encuentro al azar pelea **sin bytecode**, así
que no tiene cursor que guardar ni manejadores a los que saltar.

**Lo que cuesta, declarado:**

* **el fondo de batalla.** Un `EnemyEncounter` trae el nombre del suyo en el
  string del comando; un encuentro al azar no trae ninguno —en RM2k sale del
  terreno— así que se pelea sobre el color plano, como cualquier pelea sin
  fondo. Son 32 KB de cartucho por tropa los que se ahorran, y con 129 tropas
  eso no es un detalle.
* **perder no lleva a ninguna parte.** En RM2k un encuentro perdido es Game
  Over, y este port no tiene esa pantalla: la pelea vuelve al mapa. Es la misma
  deuda que ya tenía `EnemyEncounter` con `defeat_mode` 0.
* **el acumulado no viaja en la partida.** Al cargar arranca en cero, como al
  entrar a un mapa. En RM2k se guarda.
* **`ChangeEncounterSteps` sigue sin compilar.** Son 19 apariciones en nueve
  mapas —trece de ellas apagando los encuentros— y ninguno de esos mapas está
  cerca de los primeros diez minutos. Lo que lo frena no es la cuenta, que
  ahora está. Lo que lo frenaba era el cartucho de prueba del mapa 66, que se
  fue el 2026-09-17; ver el comentario de `ChangeEncounterSteps`, arriba de
  `ACEPTADOS_SIN_HACER` en eventos.py.

**Lo cobra `encuentro`**, el caso de la tanda: el mapa 21 —Rat Tracks B1—
caminando para arriba, con
`--encuentros-de-prueba 8` para que el encuentro salga en el paso 8 y no en el
130. Compara dos cuadros: el mapa un paso antes, y la pantalla de la pelea
contra `pantallas.py --batalla`, con la tropa que dice la referencia. Los dos
en cero. Verificado en rojo de tres maneras: con los encuentros apagados sólo
del lado de la ROM son el 100% de los pixeles; contra otra tropa de la misma
área, 338; y el cuadro de antes es el que no deja que salga antes de tiempo.

#### La música y los efectos de la pelea

Todo sale del LDB —`system.json`— y **quién suena en qué momento sale de
easyrpg-player**, no de memoria: está escrito con su función de
origen en `eventos.AUDIO_BATALLA`.

    battle_music      T_VGFighterMAX_Masako   `Scene_Battle`, al construirse
    battle_end_music  T_VGFighterMAX_Masako   `BGM_Victory`, al ganar
    dodge_se          Evasion1                `AlgorithmBase::GetFailureSe`
    enemy_attack_se   Attack2                 `Normal::GetStartSe`, fuente enemiga
    enemy_damaged_se  Damage1                 el mensaje del golpe, blanco enemigo
    actor_damaged_se  Bite                    ídem, blanco del grupo
    enemy_death_se    Monster1                `ProcessBattleActionDeath`
    escape_se         Escape                  cuando el grupo escapa

`battle_se` —el de empezar la pelea— está en `(OFF)` en este juego, así que no
se registra: sería una entrada muda para siempre.

Tres cosas que no son obvias:

* **El tema de batalla y el de victoria son el mismo**, y por eso ganar no
  cambia de tema sino que lo reinicia. Que sean dos constantes y no una es
  porque el dato es del juego: otro LDB podría tener dos.
* **Un golpe toca dos efectos y acá hay una sola voz.** RM2k pone el del
  ataque al empezar la acción y el del daño en el mensaje, con una espera en
  el medio. Acá el segundo queda pendiente en `BA_SE2` y sale veinticuatro
  cuadros más tarde; juntos serían uno solo, porque un efecto nuevo le pisa la
  voz al anterior. Cuando el que pega es del grupo no hay primero —RM2k no le
  pone efecto de ataque al actor— y el del daño sale en el acto.
* **La pelea tiene paquete de audio propio**, y eso está medido: el tema de
  batalla son 18 muestras y 51.480 B de los 64.512 de ARAM. Metiéndolo en el
  paquete del mapa 2, los 24 efectos de ese mapa —49.068 B, que hoy entran
  todos— se caían casi enteros. Con paquete aparte el mapa no paga nada
  mientras no se pelee: `op_battle` carga `BA_PAQUETE` al entrar y el del
  mapa al salir. Cuesta **65 cuadros medidos** de imagen congelada al volver,
  y otro tanto al entrar; es el mismo precio que paga cada cambio de mapa, con
  la diferencia de que allá lo tapa un fundido.

Lo que lo cobra es `pruebas/rpgmaker/test_batalla.py`, y **no la tanda de pixeles**: el
silencio no cambia un pixel, que es el mismo argumento de
`test_musica_paquete.py`. Son cuatro casos —el tema al entrar con sus muestras
en la ARAM, el de victoria, el del mapa al volver, y cuál de los cinco efectos
sale en cada golpe— y los cuatro están verificados en rojo con su defecto
puesto.
