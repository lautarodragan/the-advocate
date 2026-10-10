---
name: "El tanque de Dalia se vuelve Dalia en el puente"
description: "Jugando con Dalia, en el agency vehicle que la lleva a la base militar, el gráfico del tanque pasa a ser el de Dalia a mitad de camino —creo que al cruzar el puente— y sigue a pie, con animación de caminar"
type: bug
agents: [Hurón]
assignee: taro
---

De taro, el 2026-10-05: "cuando jugás con Dalia, y tomás el agency vehicle
que te lleva a la base militar, el gráfico del tanque se convierte en el
gráfico de Dalia a mitad de camino — y va el resto del camino a pie, con
animación de caminar y todo. Creo que siempre ocurre al cruzar el puente."

## La escena

`OutsideFactory` (mapa 84, evento 1, el "Transport"): saca a Dalia (21),
pone a DummyHero (10) y salta al 66 en (59, 20). Ahí la automática
`DaliaGoingToTasgarde` (66, evento 14, condición: el actor 10 en el grupo)
cambia el 10 por `MobilizedCar` (22, `BLVehicles` 5), le da al héroe una
ruta de 58 pasos **sin esperarla**, espera 8 segundos (`Wait 80`) y cambia
el 22 por Dalia. No hay vehículo de verdad, ni `ChangeSpriteAssociation`,
ni teletransporte en el camino: el tanque es el gráfico del actor 22, y lo
que lo saca es el `ChangePartyMembers` del final de la página.

Los 58 pasos cruzan el puente del mapa del mundo en los pasos 28 a 31
—(73, 7) a (76, 7)—. A velocidad 4 son 8 cuadros por paso, 464 contra los
480 de la espera: la ruta termina en (93, 4) justo antes del cambio. A
velocidad 3 son 16: a los 480 cuadros el héroe va por el paso 30, **en el
puente**, y sigue a pie con el gráfico de Dalia. Es lo que vio taro, y la
ROM lo hace igual con la velocidad puesta a mano en 3.

## Qué hace RM2k: lo mismo, a la misma velocidad

Medido en el original, con una copia armada con `ditto` que arranca en el
66 con el 10, baja la velocidad a 3 y corre la página del 14 con un
`OpenSaveMenu` detrás del cambio de grupo. Del `.lsd`:

| runtime        | velocidad | celda al cambiar | `route_index` |
|----------------|-----------|------------------|---------------|
| RPG_RT de 2015 | 3         | (76, 7)          | 30            |
| RPG_RT de 2015 | 4 (*)     | (93, 4)          | terminó       |
| RPG_RT de 2000 | 4 (*)     | (93, 4)          | terminó       |

(*) La misma copia con lo del Dr. Vago delante —ver abajo—: arranca a 3 y
sale a 4.

Así que el error no es la escena: es que **en la ROM Dalia maneja a
velocidad 3 y en RM2k a 4**.

## La causa: `TintScreen` no esperaba

La velocidad 3 la pone el 64 (evento 2, el `[29]` del tobillo de Talan), y
la devuelve a 4 el Dr. Vago al curarlo: mapa 81, evento 6, página 1,
"…able to walk quickly now". Ahí la página hace

    MoveEvent héroe [28]
    TintScreen negro, 0,5 s, esperar
    MoveEvent héroe [34 Future1 0]    ← reemplaza a la ruta anterior

En RM2k el `[28]` corre durante los 30 cuadros del fundido. En la ROM el
compilador tiraba la duración **y la espera** del `TintScreen`
(`compile.rs` del compilador de eventos, desde `c64e4d96`, el primer
intérprete: el comentario habla sólo del degradé, la espera se fue de
arrastre), la página seguía en el mismo cuadro, y la ruta del gráfico
reemplazaba al `[28]` sin leerlo. Talan, y después Dalia, quedaban a 3 el
resto del juego.

Son 508 `TintScreen` con espera en 247 páginas del juego: todas corrían
más rápido que en RM2k.

**El arreglo**, en las herramientas: con la espera, el `TintScreen` emite
un `OP_DELAY` de décimas × 6 detrás del `OP_TINT`, como ya hacía
`FlashSprite`. Sin opcode nuevo ni RAM nueva. El degradé sigue sin
hacerse: el tinte llega de una y la página espera lo que habría durado.

**Prueba**: `pruebas/rpgmaker/test_tinte_espera.py`, casos `tinte-espera`
(la ruta de después de un tinte de un segundo llega a los 60 cuadros) y
`tinte-espera-vago` (lo del Vago tal cual: el héroe sale a 4). Las dos
rojas con las herramientas de `main` —la ruta llega en el cuadro 1, el
héroe queda a 3— y verdes con el arreglo.

## Lo que se movió con eso

* **Las cinemáticas que tiñen llegan más tarde**: la apertura, 120 ticks
  desde el primer mensaje; el cartel, 60; la casa de Vago, ~150. Las
  goldens de tick fijo se movieron con su tick; las que salen idénticas
  se renombraron, y las de la apertura con lluvia son nuevas (cambian
  sólo las gotas). Los toques de A de la apertura, +120. Lado a lado en
  `/shared/capturas/2026-10-05-tanque-de-dalia/`.
* **El mapa de debug**: las puertas 7 y 8 se volcaron de la ROM con el
  error y dejaban la velocidad en 3. Ahora 4.
* **El mirador del 109 ya no deja trabado a Talan**: a 4 su ruta termina,
  como mide en el original la tarea del mirador de las herramientas. La
  prueba de la puerta de Paradise lo exige destrabado; hablar trabado y
  guardar la traba siguen cubiertos por sus casos.

## Las otras dos de la familia

* **Las compuertas de los misiles** (`las-compuertas-de-los-misiles.md`,
  mapa 92): no es esto. Ahí no hay `TintScreen` entre las rutas de las
  compuertas —son giros (14, 15) separados por `Wait`—, y el cambio de
  gráfico cae con los tres `ShowBattleAnimation` sobre los lanzadores. No
  lo reproduje.
* **Boss Wick** (`boss-wick-se-vuelve-una-de-sus-chicas.md`): no lo miré
  más que el volcado. El 40 cambia quién hace de Wick por página (el
  evento 1 pasa a `BLPeople` 3 y el 3 a `People7` 2 con el 160), que
  huele a páginas o a ranuras de sprites, no a esto. Los vidcasts sí
  tienen fundidos con espera, así que el tiempo cambia con este arreglo;
  no está bisectado.

## Para mergear

* Herramientas: la rama de Hurón. Reinstalar en el global `events` y
  `convert` —el compilador de eventos va adentro del conversor—. El otro
  commit es sólo comentarios del runtime y la tarea del mirador.
* ABL: la rama `huron-tanque` del clon de Hurón, con `main` (`c1b4cb9`)
  mergeado.

**Verificado**: la tanda entera de ABL, con `main` de los dos repos
mergeado (`c1b4cb9` y `d0e2e16c`) y las herramientas de la rama instaladas
en local, tres veces
seguidas en verde; `crate-test events` y `just -f tools/justfile test`.
Lo que **no** cubre: el tanque mismo jugado desde la fábrica (la prueba
cobra la causa, el Vago; el tanque a velocidad 4 lo miré con una prueba
descartable que llega al 66 y termina la ruta en (93, 4) antes del
cambio), y el resto de las 247 páginas con fundidos con espera, que
corren más lento y ninguna golden mira.
