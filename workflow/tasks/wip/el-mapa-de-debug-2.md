---
name: "El mapa de debug, 2: la rama la elige el compañero"
description: "Los Back Alleys dejan moverse, el grupo no se desordena ni se queda sin héroe al cruzar, y el NPC elige la rama que aplican las puertas"
type: bug
assignee: taro
---

# Qué reportó taro

Jugando `workflow/tasks/testing/el-mapa-de-debug.md` (sale de `main` en
`455f9fc1`, llevado a `8308033b` con el hito 4 del mundo):

> - Elegir los Back Alleys (AFTER THE DIRECTOR IS SHOT) te deja donde te
>   dejaría la cinemática del director, pero no hay cinemática activada, así
>   que quedo ahí, y no puedo moverme. [...] que Talan aparezca directamente
>   donde termina la cinemática normalmente, justo antes del puente que te
>   lleva al savepoint y bum/inn.
> - Elegir a Arden e ir al Talan's Pad (inicial) deja a Arden en el primer
>   lugar de la party, y al héroe en el mapa, invisible. Lo mismo pasa si
>   elijo a Saldra y voy a LASHE CITY WITH THE CAR [...]
> - [...] que los conjuntos de switches se prendan/apaguen como corresponde
>   para cada party member. Y [...] que no te permita agregar a más de un
>   party member: si tenés a Arden y sumás a Saldra, sale Arden.

Todo el arreglo está en `parches/manual/nuevos/Map0900.json`: **la ROM no se
tocó.**

# Los Back Alleys: la celda de (93,0) no es pisable

La puerta saltaba a `[20, 93, 0]`, el `Teleport` del evento 15 del mapa 19.
Pero la cinemática **sigue después del `Teleport`**: una ruta del héroe que,
atravesando, baja cinco, va tres a la izquierda, salta cinco, baja tres,
salta tres, y —ya sin atravesar— da un paso abajo. Sin la ruta, Talan queda
en (93,0), que no es pisable, y de una celda bloqueada no se sale.

Contada sobre la ruta y confirmada con la colisión del 20 (el `Mundo` del
arnés): termina en **(90,17)**, arriba del puente vertical que baja al save
point (88,27) y al Bum de la posada (91,27), mirando abajo. La ruta sube una
la velocidad: 5, que la puerta ya ponía. Ningún switch lo pone el final de la
cinemática: los de la escena (89 a 92) los prende la página del 19 antes.

# El grupo desordenado y el héroe invisible: el mapa, no la ROM

**El orden.** Las puertas del pad y del auto armaban el grupo como lo deja el
juego en ese punto: sacar a Talan y meter a DummyHero. Con un compañero
adentro, sacar a Talan lo deja a él primero, DummyHero entra detrás, y la
página del destino —la 3 del 4, la del 36— cambia DummyHero por Talan
**detrás** del compañero: `[Arden, Talan]`, o `[Saldra, Talan, Arden]` en el
36, que suma a Arden por el 54 que la puerta fijaba. Es exactamente lo que
hace RM2k: agregar va al final, sacar corre a los de atrás. La ROM hace lo
mismo.

**El héroe invisible.** El líder que queda es un compañero, y el conversor no
le prevé gráfico: `lideres_posibles` (snes_convert.py) suma a la tabla de
actores del cartucho sólo a los que alguna página deja **primeros**, porque
las poses de cada candidato son tiles de VRAM que se cargan con el mapa. Arden
y Saldra no lideran nunca en el juego, así que no están, y
`elegir_grafico_heroe` (grupo.s) sale por `sin_lider` con `hero_poses` en
cero: no se dibuja nada.

**¿El juego real llega a ese caso?** Se miraron todas las tandas de
`ChangePartyMembers` de los mapas del cartucho (script descartable): toda
tanda que saca a Talan con un compañero posible en el grupo saca también a
los compañeros (26, 33, 37, 38, 40, 41, 47, 48, 49, 52, 54, 64, 81), y las
que sacan sólo a Talan (12, 18, 45) corren con Talan solo —el 45 viene del
40, que ya los sacó a todos—. Así que en el cartucho de hoy no: sólo el mapa
de debug armaba ese grupo, y se arregla ahí. No se hizo `git blame` de la ROM
porque no se toca.

**Más adelante sí, y queda anotado para cuando entre**: el evento 2 del mapa
111 hace `+17 +18 -14` —Saldra y AG7 entran y Talan sale—, así que Saldra
lidera. `lideres_posibles` simula cada mapa desde el grupo del LDB, donde esa
tanda deja a DummyHero primero, y no la vería: el día que el 111 entre al
cartucho, Saldra se dibujaría sin gráfico igual que acá. Hay otras que sacan
sólo a Talan (113, 145, 168, 171, 173, 175, 232) y habría que ver con qué
grupo se llega a cada una. Es la aproximación que su docstring ya advierte.

**El arreglo**: ninguna puerta saca a Talan con un compañero adentro. Las que
dejan a DummyHero sacan antes a los tres compañeros (15, 17, 18); la de los
Back Alleys los saca y deja a Talan solo. Así Talan es siempre el primero, y
lo que agregan después las páginas del juego va detrás en su orden.

# La rama la elige el compañero

Hablarle a un NPC lo suma, **saca al otro** si había uno, prende el switch de
su rama y apaga los de las otras; hablarle otra vez lo saca y apaga el suyo.
Las ramas son las del juego:

    Arden    54 NVAlly            los Neon Vipers
    Saldra   56 LTAlly            los Lazer Teeth
    AG7-17   150 AG7-17 In Party  sin pandilla, con el droide
    ninguno  —                    sin pandilla, sin el droide

El cartel de cada NPC dice qué rama toman las puertas; los de las puertas
dicen "on your companion's path". AG7 sigue corriendo el común 37 al prender
el 150 (ver `divergencias/los-comunes-del-equipo-corren-al-cerrar-el-menu.md`).

Cada puerta lee el 54, el 56 y el 150 y pone lo de esa rama **en ese
tramo**, apagando los switches de las otras. De dónde sale cada uno lo dice el
`Comment` de la página; se buscó igual que la primera vez, cruzando qué se
pone antes de cada punto con qué mira alguien después (scripts descartables).

**Lo que pone cada rama en cada puerta:**

    NORMAL START   todas: apaga 54, 56 y 150 y saca a los compañeros.

    TALAN'S PAD    todas: nada. En el juego la rama no existe todavía —se
                   elige en el 12 o en el 9—, así que el compañero sale y el
                   54, el 56 y el 150 se apagan. El cartel lo dice.

    BACK ALLEYS    Arden:  48 (el espía, oído en la celda del 11), 54, 58
                           (el hotplate del 12 lo atrapa), 73 (la escena del
                           14). Oro 400.
                   Saldra: 38 (rechaza la misión), 55, 56 (el 9: le cuenta
                           del espía a los Lazer Teeth), 58. Oro 400.
                   AG7 y ninguno: el Hover-Tram, 69 y 72 —Stash se lleva
                           los 100 del despertador—, y su tarjeta (ítem 91).
                           Oro 300. El droide no existe todavía.
                   El compañero sale en las cuatro: en el juego se suma en
                   las Rat Tracks (26) y en la escena del 27 del 20.

    WITH THE CAR   Lo de los Back Alleys, más:
                   Arden y Saldra: nada más. Oro 845.
                   AG7: el droide ya en el grupo —183 (cartel de Stash), 203
                        (el chip, que Stash se queda), 205 (el túnel) y 150;
                        la puerta de Stash cerrada (185 apagado)—. No abre los
                        cofres de la planta. Oro 745.
                   Ninguno: sin el droide, que se puede ir a buscar. Oro 745.
                   El grupo queda en DummyHero; el 36 mete a Talan, al
                   compañero y a AG7 si está el 150.

    THE RACE       Lo del auto, más lo común del cierre (151, 156, 160-162,
                   166, 182, 238; 148 y 90-92 apagados: los apaga el 44) y la
                   condición de la página 2 del 36:
                   Arden:  159 (el vidcast de los Vipers), 167-169 (el caño,
                           el HQ vacío, el susurro) y los tres cofres del HQ,
                           que sólo se alcanzan por el caño (544-546, ítems
                           124 y 157, +250). Oro 1095.
                   Saldra: 158 (el vidcast de los Lazer Teeth), 181 (los
                           guardias del 47). Oro 845.
                   AG7:    el droide, como con auto. Oro 745.
                   Ninguno: **no hay rama**: sin el droide la página 2 del 36
                           no ofrece irse. La puerta dice "Talk to Arden,
                           Saldra or AG7-17 first" y no salta ni pone nada.

    THE WORLD      Lo de la carrera por rama, más las tres vueltas; el 53 y
                   el 64 hacen el resto según la rama. Ninguno: como la
                   carrera.

**Dos cosas que la primera versión ponía mal y se corrigieron de paso**: la
puerta de la carrera prendía el 158 y el 159 juntos (el 44 prende uno por
rama) y dejaba prendidos el 90 al 92 (el 44 los apaga).

**Para saber si hay compañero con una sola condición** las puertas de la
carrera y del mundo usan el switch **709**, que el juego no usa: sin nombre,
y ninguna página, común ni tropa lo pone ni lo mira. La ROM no compila
`EndEventProcessing` ni las etiquetas, y la puerta sin compañero no puede
poner nada antes de decir que no; la otra salida era repetir todo el estado
tres veces. Se prende y se apaga en la misma página.

# Pruebas

`pruebas/abl/test_mapa_de_debug.py`, sobre `release`:

* los Back Alleys con cada compañero y sin: la celda (90,17), Talan solo y
  visible, los switches de la rama y ninguno de las otras, el oro, y Talan
  **caminando** por el puente hasta (90,22);
* el pad con Arden sumado —el caso de taro—: Talan primero y visible, el 54
  apagado;
* el auto con cada compañero y sin: los switches y el oro al llegar, y en el
  Sector 35 el grupo `[Talan, compañero]` —con Saldra, el caso de taro— con
  Talan visible;
* la carrera con cada compañero: los switches y el oro; y sin compañero, que
  no salta y no pone nada;
* el mundo con Arden;
* cada NPC suma, prende su rama, y saca; y sumar a Saldra con Arden saca a
  Arden, y a AG7 con Saldra saca a Saldra.

"Visible" es Talan de líder y `hero_poses` distinto de cero: sin entrada en la
tabla de actores, `elegir_grafico_heroe` lo deja en cero.

**Contra el mapa de antes** (el `Map0900.json` de `8308033b`, con `release`
armado aparte): fallan 16 de las 21 —el pad espera a Talan en el grupo y
nunca llega, los Back Alleys quedan en (93,0), el auto con Saldra no tiene su
rama, los NPC no sacan al otro—.

La golden `mapa-de-debug-llegada` no cambió: los carteles y los NPC son
texto.

# Qué tiene que probar taro

* Cada NPC: el cartel dice la rama, y sumar uno saca al otro.
* Los Back Alleys con cada uno: que Talan se mueva, y jugar hasta las Rat
  Tracks —ahí se suma el compañero, o nadie sin pandilla—.
* El pad con un compañero sumado: Talan visible, sin compañero.
* El auto con Saldra, con Arden, con AG7 y sin nadie: el grupo en el sector,
  y con AG7 que Stash no vuelva a abrir.
* La carrera y el mundo con cada uno, y sin nadie: el cartel que no deja.
