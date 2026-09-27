---
name: "Carrera 1: entra y se corre, a 30 cuadros"
description: "La persecución en auto (49 a 54) y el 64 en release, el fin de la demo al final del 64, el Teleport desde un paralelo y el volante con IsPressed"
type: feature
assignee: taro
---

# Qué

El hito 1 de `todo/la-carrera-y-lo-que-sigue.md`, que tiene todo lo medido
antes de empezar: el recorrido, las faltas numeradas y el costo. Sale de `main`
en `49f0e2f`.

* 49 a 54 y el 64 en `release`; el 52 deja de ser mapa de prueba.
* El fin de la demo pasa al final de la escena del 64 (fork en
  `parches/manual/mapas/Map0064.json`), y el fork del 36 se borra.
* Falta 1: el `Teleport` desde una página paralela con el primer plano quieto.
* Falta 2: el `KeyInputProc` sin espera lee lo apretado (`IsPressed`), y
  `eventos.py` lo acepta sin el interruptor de medición.
* Las pruebas: el 52 fuera de `heroe`, las goldens del 52 revisadas, los
  recorridos de Lashe con "irse lleva a la carrera", y un recorrido de la
  carrera entera hasta el fin de la demo en el 64.

## Lo que quedó decidido

Las preguntas del plan las contestó quien lanzó el hito, con las
recomendaciones del plan; taro las puede revisar:

1. **X = 65**, excluidos 15, 22, 46, 55 y 58, más el 164. Hacerlo regla es el
   hito 4; acá la lista de `MAPAS_DEL_JUEGO` tiene que dar lo mismo que esa
   regla.
2. **La carrera a 30 cuadros vale como paso intermedio.**
3. **El fin de la demo va al final de la escena del 64**, en lugar del salto al
   mundo. El fork del 36 se borra.
4. **El 52 sale de `heroe` sin reemplazo**, y se revisan sus goldens.
5. El cartel de los controles (falta 4) y los sonidos del puente (falta 5) **no
   son de este hito**: van en el 3.

Números reservados: opcode 0x31 (no hizo falta) y la RAM lejana
$7E7980-$7E799F (no hizo falta).

# Cómo quedó

## El `Teleport` desde un paralelo

`eventos_tick` mira `salto_hay` sólo después de correr una página de primer
plano. El arreglo va en el lazo principal, detrás de `eventos_tick`: si quedó
un salto pendiente, se atiende con la misma mitad de `eventos_tick`
(`eventos_atender_salto`, un alias global de `eventos_tick::hubo_salto`,
porque `arranque.s` va antes en el ensamblado y `ca65` no resuelve un símbolo
de otro scope hacia adelante). Es lo que hace easyrpg en
`Scene_Map::UpdateStage2`: el salto pendiente se atiende después de
`Game_Map::Update`, corra lo que corra. Siete bytes de banco 0.

## El volante

`tecla_valor` miraba flancos en las dos formas. Ahora la que no espera mira lo
apretado: `TECLA_ESPERA` es el bit 0, un `lsr` lo pasa al acarreo, y el
acarreo llega entero hasta la tecla de acción porque nada en el medio lo toca.
Siete bytes. Un `.assert` en `menu.s` cuida que `TECLA_ESPERA` siga siendo el
bit 0.

El orden entre la ruta del héroe y el volante (lo que el plan dejaba para
mirar) no dio problema: sosteniendo arriba o abajo el auto cambia de carril y
sigue empujado a la derecha.

## Lo que se vio corriendo

Con los dos arreglos, un piloto de prueba que esquiva mirando las celdas de
los autos hace la carrera entera: 49, choque (50) y de vuelta al 49, 52, 54,
el puente (51), el premio (53) y el 64 hasta el cartel del fin de la demo.

Cuadros de hardware por tick manejando, con el volante corriendo (medido con
el piloto de la prueba, contando sólo los ticks con el 170 y sin fundido ni
mensaje):

    49   2,07
    52   2,04
    54   2,04
    51   1,00

O sea que las tres vueltas corren a 30 cuadros, como medía el plan, y el
puente a 60. Es el hito 2.

**El 53 sin compañero se traba**, en el original también: sus tres ramas
piden el 54 (Arden), el 56 (Saldra) o el 150 (AG7-17), y sin ninguno la página
termina sin saltar al 64. En el juego no pasa, porque el 36 sólo deja irse con
la condición de alguna de las tres ramas; se nota sólo si se arranca la
carrera a mano desde afuera.

## El fin de la demo

El fork del 64 cambia el `Teleport [66, 71, 29]` y lo que viene detrás —los
mensajes que corren en el mundo— por un cartel ("END OF THE DEMO / The world
beyond Lashe City is not in / the cartridge yet. Thanks for playing!") y un
`ReturntoTitleScreen`, igual que hacía el del 36. Las capas son las del
original.

## Espacio

Medido al final, sobre el merge con `main` (`9d6c0d3`), con el método de
`AGENTS.md`:

    cartucho      banco 0   banco 1   BSS   ZEROPAGE   ROM
    release       191 B     ~10,2 KB  109   4          72,6 %
    test-special  967 B     ~11,1 KB  109   4          18,7 %

Contra el plan (205 con los mapas), los dos arreglos costaron 14 bytes de
banco 0.

# Pruebas

`just pruebas` en verde sobre el merge con `main`: lo que imprime es el
número.

* **Nuevo: `pruebas/abl/test_recorrido_carrera_golden.py`**, con dos:
  * `test_la_carrera_entera`: con Arden, la intro del 49, las tres vueltas
    manejando con un piloto que mira en la RAM la celda de cada auto y
    sostiene arriba o abajo para esquivar, el puente, el premio (el oro, y la
    variable 38 igual a los choques que contó), la despedida del 64, el cartel
    del fin de la demo y el título.
  * `test_cinco_choques_y_maneja_saldra`: sin tocar el volante el auto choca
    siempre con el de (101, 26); cada choque pasa por el 50 y vuelve a largar
    en el 49, y al quinto Saldra se ofrece a manejar: "Yes" lleva al puente con
    el 173, y de ahí al 64 y al título.
  Las capturas van a `pruebas/snapshots/playthrough/carrera-*/` y no están
  bendecidas.
* **Los recorridos de Lashe**: "irse termina la demo" pasó a ser "irse lleva a
  la carrera" (`irse_lleva_a_la_carrera`): el 182, el mapa 49 y la celda
  (1, 26). La foto del fin de la demo de `lashe-fin` pasó a ser la de la
  largada.
* **`heroe` sin el 52**: se borraron sus cinco goldens y su plan, y el caso
  `grupo-11-en-52`, que sólo usaba él. Las demás del 52 —`pelea-en-52`, que es
  de estado— pasan sin tocar nada; `ev41` es del mapa 8.
* **Ninguna golden de la tanda cambió.**
* `Recorrido.foto` acepta una `imagen` tomada antes: el cartel del fin se
  reconoce recién cuando el toque siguiente vuelve al título.
* `just techos`: la mezcla cambió con los dos temas nuevos
  (`Fire_Mustang_…` y `prepara`), y la tabla se volvió a medir.

# Qué tiene que probar taro jugando

* Irse de Lashe City desde el 36 por cualquiera de las tres ramas y jugar la
  carrera: la intro con la pantalla negra (el cartel de los controles no está:
  es el hito 3; cualquier tecla arranca), el volante con arriba y abajo, que se
  sienta a media velocidad y nada más.
* Chocar: el 50 y la vuelta a la misma vuelta. Chocar cinco veces y dejar
  manejar al compañero.
* El puente (el salto va sin sus sonidos: hito 3), el premio y la despedida,
  con cada compañero —los textos del 53 y del 64 cambian con cada uno—, hasta
  el cartel del fin y el título.
