---
name: "Lashe 4: AG7 en la pelea"
description: "Las habilidades del droide según sus piezas, el SP de las armas, y ShortCircuit de los enemigos"
type: feature
---

# Qué

El hito 4 de `lashe-city-hasta-la-carrera.md` —el contexto está ahí—. Tiene dos
mitades que no se pisan:

- **los enemigos de la planta** (tropas 108 a 114);
- **AG7-17** (actor 18), que el hito 3 mete al grupo sin habilidades.

Lo que taro contestó el 2026-09-26 y manda acá: AG7 **no puede perder
habilidades** —o sea, las de a muchos entran— y las armas cobran SP porque
en el original lo cobran: **fiel al original**.

# Status

2026-09-27, en `testing/`: hecho en la rama del agente, sobre `main` en
a3140f1 y con `main` mergeado encima del hito 5 (6c4949d); `just cartuchos`
y la tanda entera en verde sobre el árbol mergeado. Lo que queda es de taro:
jugarlo (ver abajo). Las goldens no cambiaron.

# Lo hecho

**El espacio, primero y aparte.** Al banco 1 le quedaban ~350 B y el código
de la pelea vive ahí. El código y los mensajes de las páginas de tropa —casi
once KB— pasaron a RODATA en su propio commit, con la tanda en verde y sin
tocar ninguna golden: se leen con un puntero largo cuyo banco sale de
`^tropa_codigo`, así que alcanza con que cada bloque entre en un banco.

**Los enemigos eligen qué hacer** (`batalla.accion_del_enemigo`,
`ba_accion_enemiga`): la lista de acciones del LDB con su `rating`, y los
pesos de `SelectEnemyAiActionRpgRtCompat` —`max(0, rating - máximo + 10)`—.
Con eso **el único de la planta que tira `ShortCircuit` es el Tangle Wire**
(tropa 113), que la tiene en 50 como el ataque; el Scrapped Droid (10), el
Trash Hauler y el Junkbot (30) quedan diez puntos o más abajo y pesan cero,
en RM2k también. Una acción de peso sola no tira dado, para no mover el azar
de las peleas que ya estaban. Lo que no se modela —condiciones, las otras
acciones básicas, estados— en
`divergencias/lo-que-la-ia-de-los-enemigos-no-modela.md`.

**Los cinco alcances** (`batalla.blancos_de_la_habilidad`, `ba_hab_usar`):
`enemies` y `party` repiten el efecto sobre cada vivo del lado, con sus tiros
por blanco; `self` cae sobre el que la usa. Sólo `enemy` y `ally` piden
blanco. Con eso AG7 no pierde ninguna de sus diecisiete —las que tocan
estados (BioWarfare, HeadButt, RemoveStatus) hacen lo que se puede sin
estados— y de paso entran las de a muchos de todos los actores, Arden
incluido.

**El SP de las armas** (`batalla.sp_del_arma`, `ba_atacar`): el `sp_cost` del
arma de la ranura 0 se cobra antes del acierto, sin gris con los SP en cero.
Las armaduras que traen `sp_cost` (NetLauncher, SpikedHelmet) no cobran:
`ForEachEquipment<true, false>` sólo mira armas.

**El evento común 37: lo a medida.** `eventos.COMUNES_DEL_EQUIPO` reconoce
los comunes paralelos, con switch, que no tienen más que `ChangeSkills` y
ramas por el equipo. Su cuerpo se pega detrás del `ControlSwitches` que
prende su switch y la ROM lo corre al cerrar el menú
(`comunes_del_equipo`). Por qué no lo general, con los números:
`divergencias/los-comunes-del-equipo-corren-al-cerrar-el-menu.md`. En corto:

    general   ~0,13 cuadros de CPU por vuelta del cuerpo, en cada cuadro de
              todos los mapas desde que AG7 entra —medido con casos
              descartables: 0/10/20/30 corridas seguidas, 63/64/66/67 cuadros—,
              y prende además el 2 (DisableSaving, sin switch), el 3 y el 8
    a medida  8 B de banco 0, 117 de banco 1, 0 de RAM, 0 ciclos por cuadro;
              no cubre un `ChangeEquipment` de página sobre el 18 (el juego
              no tiene ninguno)

**La animación 62 no se dibuja**, ni la de ninguna habilidad: es un
subsistema nuevo adentro de la pelea (objetos, OAM, una paleta, los cuadros
por DMA), y queda con lo mirado en `wishlist/animaciones-en-la-pelea.md`.

# Números usados

- Opcode: ninguno.
- RAM lejana: `$7E7960`-`$7E797F`, en `rom/src/ram_lejana.s`: `BA_ARMA_SP`
  (4 bytes) y `BA_HAB_I` (1).
- Tuplas de `test_*_golden.py`: ninguna.

# Lo medido

Con `.res N, $00` y la tabla de símbolos, después del hito y con el 5
mergeado:

    release       banco 0: 211 libres (219 antes)   banco 1: ~10,2 KB
    test-special  banco 0: 981                      banco 1: ~11,3 KB

BSS y ZEROPAGE sin cambio.

**Una página de prueba de más de ~12 KB se cuelga**: la de 40 corridas del
37 (12,3 KB) no llegaba al final y la de 30 (9,2 KB) sí. No es de este hito
—ninguna página del juego se acerca— y queda anotado por si alguien arma una.

# Pruebas

`pruebas/rpgmaker/test_ag7_y_la_planta.py`, con dos páginas nuevas,
`ag7-componentes` y `pelea-113` (Talan y AG7 en el piso 1):

* al prenderse el 150 AG7 sabe ConcentratedSpray y nada más;
* cambiar el arma no cambia nada con el menú abierto, y al cerrarlo sabe
  ArmMissile y no ConcentratedSpray —en rojo sin la llamada desde el menú—;
* con el switch apagado, cerrar el menú no toca nada;
* la pelea contra la tropa 113, turno por turno contra el modelo: los HP de
  los cuatro, los SP de AG7 (su arma) y los del Tangle Wire (`ShortCircuit`),
  exigiendo que los dos hayan bajado;
* la lista de "Components" en la pelea;
* BombsAway, con el GrenadeLauncher: sin blanco, a los dos enemigos.

`test_cores.py` suma `test_la_pelea_de_la_planta`: dos turnos de la 113 en
snes9x y bsnes.

# Qué tiene que mirar taro jugando

Lo que se puede ver jugando es menos de lo que se hizo: **en lo que llega
hasta la carrera AG7 no consigue ninguna otra pieza** —ninguna tienda ni
ningún evento de esos mapas da una, y los enemigos de la planta no sueltan
nada—, así que tiene la ArmCannon y nada más. Lo que hay:

* **"Components" en la pelea**, con ConcentratedSpray.
* **Sacarle la ArmCannon** en el menú de equipo y salir: en la pelea que
  sigue "Components" está en gris. Volver a ponérsela y salir: vuelve.
* **El SP del arma.** La pelea no muestra SP y el menú de pausa tampoco, así
  que se ve por el gris: con 60 SP, nueve ConcentratedSpray dejan 6, que
  todavía alcanzan; un ataque más (1 SP) y la habilidad queda en gris. Sin
  el costo del arma seguiría disponible. Los SP pasan de una pelea a otra.
* **El Tangle Wire** —el cable, en la tropa con la rata— tirando
  `ShortCircuit` más o menos la mitad de las veces; los otros de la planta
  sólo pegan, como en RM2k.
* **De rebote, el jefe de los Rat Tracks** (el KingRat) ahora a veces muerde
  con `RoyalRatBite` en vez de pegar.

Las de a muchos (BombsAway, TillTheyGlow) y las piezas que cambian la
habilidad sólo se pueden ver hoy en las pruebas.

# Probado

taro, el 2026-09-27, en la SNES con el FX Pak: anduvo todo, incluido el camino
de vender el Idol, sobornar al guardia y llevar a AG7; la carrera sin lag ni
bugs (el compañero al volante, también). Queda aparte el héroe negro después
de cambiar de gráfico en el mismo mapa (HQ de Lazer Teeth, Boss Wick).
