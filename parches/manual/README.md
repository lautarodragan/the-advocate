# `parches/manual/`: lo nuestro, que manda sobre `data/`

`data/` es *A Blurred Line* tal como lo escribió su autor: el volcado de Ditto,
que es **derivado** —`just datos` lo rehace entero— y del que nada de acá sale.
Esto es lo contrario: entrada escrita por nosotros que el pipeline usa **en
lugar** de la de `data/`.

Un fork **no describe cambios: es el archivo entero.** Por qué está separado de
`parches/auto/`, en `parches/README.md`.

El diff contra el original no se pierde: `data/` sigue versionado y `unpack`
escribe ahí y nunca acá, así que se computa cuando haga falta.

    mapas/MapNNNN.json     el mapa forkeado
    mapas/MapNNNN.tiles    y sus dos capas, que viven afuera del JSON
    chipsets/NNNN.json     un ChipSet que se **suma** a la base, con la receta
                           de su imagen

Lo que lo hace cumplir es `tools/rpgmaker/fork.py`, y lo miran las pruebas
`pruebas/herramientas/test_fork_mapas.py`.

## Las tres reglas, que son el mismo miedo

**Un mapa forkeado es todo o nada.** Las capas de tiles viven afuera del JSON,
así que un `.json` sin su `.tiles` dejaría el build con las capas viejas y los
eventos nuevos: **se ve bien hasta que no**. Falta una pieza, el build se
niega.

**El id de adentro es el del nombre.** Por eso —y sólo por eso— el JSON de un
mapa forkeado lleva un campo `id` que el volcado de Ditto no tiene: el
pipeline elige el mapa por el **nombre del archivo** y los teleports lo nombran
por su **id**, así que un fork copiado de otro mapa y renombrado a medias no
falla, pisa el mapa equivocado y manda al jugador adentro de una pared.

**Un fork de mapa reemplaza a uno que existe.** Un nombre mal escrito no hace
nada, en silencio, y eso es peor que un error.

## Los ChipSets se suman, no reemplazan

Un id que ya esté en `data/db/chipsets.json` es un error. Un fork que pisa una
entrada de la base envejece sin avisar el día que `just datos` la cambie;
agregando una entrada nueva no hay nada que pueda quedar viejo.

**Y su imagen no se versiona: se arma.** El arte del juego no es nuestro para
redistribuir —no está en el repo, ver `docs/rpgmaker/rtp.md`—, así que el fork
guarda la **receta**: qué bloque de autotile y qué tile alto se copian adónde.
El PNG sale a `rom/build/parches-manual/ChipSet/`, que es un directorio de build como
cualquier otro.

Duplicar un tile del ChipSet **no cuesta tiles en el cartucho**: Voodoo
deduplica a nivel 8x8 y reusa el espejado, así que un tile repetido son cuatro
celdas que ya estaban.

### Y lo que el mapa no dibuja se poda

`podar` es la operación que no dibuja nada: borra del ChipSet todo lo que su
mapa no usa. Vale porque el ChipSet de un fork es **privado de su mapa**, así
que no hay otro que pueda pedirle un tile que éste no dibuje.

Lo que se gana no son pixeles sino **índices de paleta**. El PNG es indexado y
tiene 256, y ése es el techo contra el que choca traer un dibujo de afuera:
podado, el ChipSet del mapa 32 pasa de 122 índices libres a 174.

Qué guardar sale del mapa **ya forkeado** y no de una lista escrita al lado,
que es lo que hace que no se puedan desincronizar. Y no alcanza con las dos
capas: **un evento sin CharSet se dibuja con un tile de la página alta** que no
aparece en ninguna capa. Podando sin contarlos, el mapa 32 perdía la ranura 13
y la ROM salía distinta; lo cobró la comparación byte por byte y hoy lo cuida
`test_podar_conserva_las_ranuras_que_solo_nombra_un_evento`.

Con `ChangeMapTileset` o `TileSubstitution` adentro, las capas dejan de decir
qué dibuja el mapa y **el podado se planta** en vez de adivinar.

### Y una pose de CharSet también entra

`desde_charset` es la tercera operación de la receta, y la primera que **trae
pixeles de afuera del ChipSet**: mete una pose de un CharSet en dos tiles
altos, la cabeza y el cuerpo. Es lo que convierte en mapa a un NPC que no hace
nada más que estar parado —el público del Auditorio—, y sale de que el sprite
se dibuja en `(x*16 - 4, y*16 - 16)`: sus columnas 4 a 19 caen clavadas en la
celda y su mitad de arriba cae en la celda de arriba.

Lo que no se ve venir: **los dos PNG son indexados y sus índices no quieren
decir lo mismo.** Copiar los bytes da un sprite pintado con la paleta del
ChipSet, que es basura que se ve; así que se copia por color y el que falta se
agrega en un índice que el ChipSet no use.

### Y un PNG que no es ni ChipSet ni CharSet también entra

`desde_imagen` es la cuarta operación: escala un PNG cualquiera —una imagen de
`Picture/`, por ejemplo— y lo corta en celdas de 16x16 que van a ranuras altas.
Escala con **vecino más cercano**, que es lo que hace RM2k, y `desfase` dice
dónde cae su pixel (0,0) adentro de la primera celda, porque una imagen del
juego no tiene por qué estar alineada a la grilla de 16.

Los colores se redondean a **15 bits** antes de entrar. No pierde nada que el
cartucho pueda dibujar —el asignador cuantiza con `>>3` igual— y es lo que hace
entrar el dibujo en los 256 índices del PNG: el Hover Tram son 206 colores a 24
bits y 148 a 15. Que el PNG del ChipSet quede con colores que el arte original
no tiene no importa, porque **esa imagen no se versiona, se arma**.

Una celda puede llevar un cuarto número: la ranura de la que sale su **fondo**.
Con él, el dibujo se compone encima en vez de pisarla, que es lo que deja viva
una pared donde el dibujo sólo apoya unos pixeles.

Y **la pasabilidad del tile es una decisión, no una herencia**: acá no hay un
tile de origen del que copiarla. Un evento en la capa del héroe es una pared,
así que el tile del cuerpo tiene que cerrar la celda o el jugador camina por
encima de la gente; el de la cabeza deja pasar, porque por esa celda se camina.
Lo mira `test_fork_donde_borro_un_evento_del_piso_la_celda_sigue_cerrada`.

## Qué hay forkeado hoy, y por qué

El **mapa 11**, el HQ de los Lazer Teeth, con el minijuego de las piedras
rediseñado: sus 52 baldosas de luz dejaron de ser eventos y pasaron a ser tiles
del mapa. El porqué, con todo lo medido, está en
`workflow/tasks/done/el-mapa-11-se-rediseno.md`.

Y el **mapa 18**, el Auditorio, con su público horneado: 31 eventos que no
hacían nada más que estar sentados mirando al escenario pasaron a ser ocho
tiles de un ChipSet propio, y con eso el mapa se bajó del techo de paletas de
sprite donde estaba clavado. El porqué, con todo lo medido, está en
`workflow/tasks/done/hornear-la-decoracion-en-un-chipset.md`.

Y el **mapa 36**, `LasheCityVehicle`, donde termina la demo: la pregunta de
irse de Lashe City —"We've got to get out of here"— llevaba con un `Teleport`
a la carrera, el mapa 49, que no está en el cartucho. En sus cuatro lugares ese
`Teleport` pasó a ser un mensaje de fin de demo y un `ReturntoTitleScreen`. Lo
decidió taro el 2026-09-26, en vez de meter la carrera o de hacer que el
conversor compile todo `Teleport` a un mapa ausente como fin de demo, que
cambiaba qué hacían muchas páginas del juego. Sin el fork, la segunda vuelta al
auto dejaba al jugador trabado en negro: la página no compilaba. **Se borra el
día que entre la carrera.** Sus capas son las del original, byte por byte.

Lo que el horneado del 18 **no** conserva: el público era de la capa del héroe
y se ordenaba con él por Y, y ahora es fondo. Vale porque en ese mapa no se
camina libremente —la cinemática es autostart y no suelta al jugador—, y las
tres posiciones por las que pasa el héroe están en el pasillo del medio o
detrás de todos. Es lo primero que hay que volver a mirar si alguna vez se le
devuelve el control ahí.

Y lo que el rediseño del 11 **no** conserva, que es una sola cosa y conviene
tenerla escrita: las baldosas atrapaban al héroe con un trigger de **contacto**, que
dispara en el paso, y ahora lo atrapa un **proceso paralelo**, que mira en qué
celda está. Es un cuadro de diferencia en cuándo salta, no en si salta. No está
medido: se ve jugando. Que salte lo cuida `pruebas/abl/test_luces.py`.
