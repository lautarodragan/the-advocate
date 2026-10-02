# Qué

Desde el 2026-09-27 los enemigos eligen qué hacer como `Game_Enemy`: la
lista de acciones del LDB, el `rating` de cada una y
`SelectEnemyAiActionRpgRtCompat` de easyrpg —cada posible pesa
`max(0, rating - máximo + 10)`— y usan habilidades. Lo decide
`batalla.accion_del_enemigo` y lo copia `ba_enemy_action`
(`tools/runtime/battle.s`). Lo que queda distinto:

* **Con una sola acción de peso no se tira el dado.** RM2k tira
  `rand(0, suma - 1)` igual. Es la misma distribución, y deja el azar de las
  peleas que ya estaban —enemigos que sólo atacan— exactamente como era: sin
  eso cambiaba cada golpe de cada pelea de `release`. El generador de RPG_RT
  tampoco es el nuestro.
* **Sólo el ataque básico y las habilidades.** Defenderse, cargar,
  autodestruirse, huir, no hacer nada, transformarse y el ataque doble salen de
  la lista, como si su condición no se cumpliera. Las habilidades de switch,
  también.
* **Sólo la condición "siempre".** Las de turno, HP, SP, cantidad de enemigos,
  nivel y cansancio del grupo sacan a la acción de la lista.
* **Los switches que una acción prende o apaga al elegirse** (`switch_on`,
  `switch_off`) sacan a la acción de la lista.
* **Los estados no existen**, así que una habilidad que sólo pone o saca
  estados no hace nada, y la IA la descarta como easyrpg descarta la que no
  tiene a quién afectar.
* **Sin animación.** `ShortCircuit` trae la 62 y no se dibuja, igual que las
  habilidades del grupo: ver `tasks/wishlist/animaciones-en-la-pelea.md`.

Si a un enemigo no le queda ninguna acción, ataca, que es lo que hacían todos
hasta ese día.

# Medido

El 2026-09-27, sobre las tropas de `release` (`troop_id` del `mapdata.inc`),
16 enemigos traían algo más que el ataque solo. Con los pesos de RM2k **usan una habilidad
cuatro**: el Tangle Wire (`ShortCircuit`, la mitad de las veces), el KingRat
de los Rat Tracks (`RoyalRatBite`, la mitad: su ataque doble es de turno y
sale de la lista), el Risen Dead (`PowerDrain`, un tercio) y el Securibot Type
I (`Static Shielding`, sobre sí mismo, la mitad). Los otros la traen con diez
o más puntos menos que el ataque, y no la usarían nunca: el Scrapped Droid, el
Trash Hauler y el Junkbot de la planta, entre ellos.

Lo cobran `test_la_tropa_es_la_que_se_espera` y
`test_el_tangle_wire_usa_short_circuit_y_deja_el_hp_del_modelo`, en
`pruebas/rpgmaker/test_ag7_y_la_planta.py` de ABL, y `test_la_pelea_de_la_planta` en
`test_cores.py`.

# Cómo se ve hoy

En la planta, el Tangle Wire alterna entre pegar y "ShortCircuit"; los otros
tres de la planta sólo pegan, que es lo que harían en RM2k. El jefe de los
Rat Tracks muerde.

# Cuándo deja de alcanzar

Un enemigo cuya pelea dependa de una condición —un jefe que cambia de acciones
por turno o con poca vida— o que se defienda o huya.
