# Qué

El HQ de los Lazer Teeth —el mapa 11— **no entra en el cuadro donde se juega el
minijuego de las piedras**, y lo que lo saca son sus **52 baldosas de luz**:
52 eventos dibujados con el mismo tile opaco del ChipSet, el charco de luz en
el piso. Hornear los 18 que caían en la regla de los eventos opacos bajó el lag
a la mitad **en una zona vacía del mapa**, que no es donde se juega.

# Status

**Los dos caminos baratos están hechos. Falta el tercero**, que es el único que
ataca el peor caso: hornear cada posición conocida y prender o apagar el tilemap.

Después de los dos, caminando 1200 cuadros:

    celda     diagnóstico   con los dos
    (50,50)       231           153
    (26,47)       625           475
    (18,50)      1200             9
    (19,46)      1196          1141
    ( 5,50)      1200            19

**Tres de las cinco celdas entran en el cuadro**, incluidas dos que estaban en
30 fps clavados. **La celda donde el minijuego se juega, (19,46), sigue sin
entrar**: ahí las baldosas están en pantalla, y ni hornear cuatro más ni dejar
de procesar las de afuera le sacan nada. Es exactamente lo que el diagnóstico
anticipaba de los dos.

El build con que se midió el diagnóstico es descartable y **no va a `main`**: es
una variable de entorno en `snes_convert.py` que le apaga el dibujo a un grupo
de eventos, con el mismo mecanismo con que nacen escondidas las filas de los
horneados. Está en el commit marcado `DESCARTABLE` de la rama
`worktree-agent-af33fbcd7a65c7dd1`, revertido en el commit siguiente.

# Lo medido

Cuadros perdidos caminando 1200 cuadros, con el contador leído y puesto en cero
cada 50 porque **`cuadros_perdidos` satura en 255**. Es el mismo método con que
salieron el 450 y el 228 de `done/eventos-opacos-al-mapa.md`, y ese 228 se
reprodujo clavado.

**La celda desde la que se mide cambia la respuesta por un factor de cinco**, y
eso es lo primero que hay que saber: el caso `en-11` deja al héroe en (50,50),
que es una **zona vacía**, y ahí **ninguna** baldosa cae en pantalla. Lo que se
venía midiendo era el costo de filas que nunca se dibujan.

    celda     en pantalla   como está hoy   sin las baldosas   sin nada dibujado
    (50,50)         0            231                75                 0
    (26,47)        17            625               108                73
    (18,50)        26           1200                 3                 3
    (19,46)        31           1196                23                10
    ( 5,50)        23           1200                 3                 3

"Como está hoy" son 50 filas dibujadas de 69 —los 18 horneados ya están
escondidos—; "sin las baldosas" son 16; "sin nada dibujado", 0.

**1200 de 1200 es 30 fps clavados**: perder el vblank cuesta el cuadro entero,
no medio. O sea que en la zona del minijuego el mapa hoy **no gana un solo
cuadro** caminando, y sin las baldosas pierde tres.

Quieto el margen es fino y alcanza: 176 vueltas en 180 cuadros con las baldosas
en pantalla, 179 sin ellas. Lo que lo tira abajo es el redibujado del scroll
sumado a los sprites.

## Un evento estacionado fuera del mapa **sí cuesta hoy**

Es la pregunta barata, y la respuesta es que cuesta, aunque menos que uno en
pantalla. Medido con una tercera variante que deja las 52 baldosas **dibujadas**
pero las estaciona en (97,97), que es lo que el juego hace al apagar una luz:

    celda     como está hoy   estacionadas afuera   sin dibujarlas
    (50,50)        231               231                  75
    (19,46)       1196                75                  23

La fila sigue costando su vuelta del lazo, la comparación contra la clave del
héroe y la cuenta de `place_npc`; lo único que se ahorra es el cuerpo de
`emit_object`, que descarta lo que cae fuera de pantalla. **34 filas escondidas
de más valen 156 cuadros de 1200 en (50,50) y 52 en (19,46).** Estar en pantalla
vale mucho más que existir: 75 contra 1196 en la misma celda.

## Los 84 eventos, por lo que hacen

    grupo                        n   dibujados  visibles  los reubican  tile
    baldosa de luz              52      52        52          30        80
    sin gráfico                 15       0         0           4        —
    fuente de luz (Light1..6)    6       6         6           4        73 (y 53)
    personaje (Chara3)           6       6         6           6        CharSet
    la piedra (Stone)            1       1         1           1        CharSet
    el ídolo (TheIdol)           1       1         1           1        65
    la consola del ResetPuzzle   1       1         1           0        33
    el LTComputer                1       1         1           0        49
    EV0017                       1       1         0           0        13

Las **52 baldosas** son el grupo, y el nombre las agrupa sin identificarlas: hay
19 eventos llamados `B3`. Son A 10, B 22, C 10, D 4, E 6. Las 52 se dibujan con
el tile 80 y ninguna camina. **33 tienen comandos en alguna página y 19 no
tienen ninguno**: ésas no hacen nada más que dibujarse.

**Dos mecanismos que conviene no mezclar**, porque conviven en el mismo
minijuego:

* las **fuentes** —las seis `Light*`, y con ellas la PC y el ídolo— tienen una
  **segunda página condicionada por un switch** con **otro tile**: es la lámpara
  rota. Su página paralela compara la posición de la piedra con la suya y, si
  coinciden, corre los `ChangeEventLocation`;
* las **baldosas** del cono **no cambian de página: se mueven**. Apagar un cono
  es mandar sus baldosas a (54,82), (97,97) o (98,97), y no vuelven salvo por
  `ResetPuzzle`, que reubica 42 eventos de un saque.

Los **15 sin gráfico** son los que no cuestan nada de dibujo: los cuatro
`Block*` del modo de tiro —que `ChangeEventLocation` pone alrededor del héroe—,
las tres rejillas, los dos `EV008x` de la escalera, y el resto son
disparadores de escena y carteles de examinar.

**Las cajas que se examinan y no tienen nada adentro son reales, y son las
rejillas**: `EV0078` (3,51) y `EV0079` (6,38) contestan "There's nothing in the
grate, except for a lot of dirt", y `Grate1` (26,51), una vez que le sacaron las
piedras, contesta "There's nothing else within the grate". **Ninguna de las tres
se dibuja**, así que no cuestan un solo cuadro y sacarlas no gana nada. Son
prosa del juego, no lastre.

## Cuatro baldosas quietas las rechaza la regla por una sola cosa

De las 52, **22 no las reubica nadie** y la regla del horneado hornea **18**.
Las cuatro que sobran son los eventos **31 (`B1`), 32 (`B2`), 33 (`B3`) y 46
(`B2`)**, y el motivo es uno solo: **tienen dos o tres páginas**, y la regla pide
una. Pero **todas sus páginas dibujan el mismo tile 80, en la misma capa, y la
primera no tiene condición**, así que su dibujo es tan fijo como el de las otras
18. Lo que cambia entre sus páginas es el script, no el gráfico —de hecho
`collect_npcs` ya lo sabe: les da `cambia` falso—. (Eso es el camino 1, que ya
está hecho: hoy la regla las hornea y son 22.)

# Los caminos, con lo que cuesta cada uno

## 1. Aflojar la regla del horneado — HECHO

La condición es la primera página sin condición y **todas** las páginas con el
mismo gráfico, la misma capa y sin animación continua. Está en
`eventos_horneables`, con el porqué de cada cosa.

Lo previsto era **26 → 31** con el mapa 2 sumándose. Lo que salió es **26 → 29
en 7 mapas**, con el mapa 11 de 18 a 22, porque el mapa 2 **movía una golden** y
eso obligó a una sexta condición: **hornear no puede abrir la celda**.

El `MovinDoor` del mapa 2 está en un rincón, fuera de cualquier cámara, y
hornearlo movía `puerta-izq-950` en 113 pixeles —una puerta a sesenta celdas de
ahí, con los mismos switches puestos—. Lo medido antes de decidir: la CGRAM del
mapa sale idéntica, el fondo dibuja lo mismo salvo la celda horneada, la tabla
de NPCs cambia **un solo byte** —el "se ve" de esa fila— y las páginas
compiladas no cambian. Lo único que queda es que **su celda está cerrada en la
tabla del mapa y su tile se pisa**, así que hornearlo la abría; `pasa_con_evento`
consulta la fila, pero la tabla la lee más de uno. **El mecanismo completo no se
desarmó**: si alguien quiere tirar de ese hilo, la comparación está en el commit.

Cerrar de más se sigue permitiendo, que es el caso normal. Sale también el
`EV0004` del mapa 141, que estaba en el mismo caso y no lo corre ninguna prueba.

**Lo que no arregla**, como estaba previsto: nada del lag donde se juega. Esas
cuatro baldosas están dentro del grupo B, que ya está casi entero horneado. En
(26,47) baja de 625 a 527 y en (19,46) de 1196 a 1150.

## 2. No procesar la fila de un evento que cae fuera de pantalla — HECHO

No quedó como un `cmp` en `build_oam` antes de `place_npc` sino **adentro de
`place_npc`**, partido en dos: la X apenas está calculada y la Y recién después
del salto. Sale más barato que el `cmp` de afuera —la mitad de los descartes no
lee nada más de la fila, y el que se dibuja no paga ninguna cuenta de más— y no
hay que elegir margen: es la misma comparación de `emit_object`, con el mismo
corrimiento de 32 y el mismo corte en 224 por abajo, así que descarta objeto por
objeto lo mismo y la OAM sale idéntica.

**Gana muchísimo más de lo previsto.** La estimación era "parte de los 156
cuadros de (50,50) y de los 52 de (19,46)"; lo medido es 231 → 153 en (50,50),
y **1200 → 9 en (18,50) y 1200 → 19 en (5,50)**: dos celdas que estaban en 30
fps clavados y ahora entran en el cuadro. Estaban justo del otro lado del borde.

Cuesta 21 bytes de banco 0 y **gana en todos los mapas**, no sólo en el 11.

**No arregla el caso que importa**, como estaba previsto: con el cono prendido
las baldosas están en pantalla y siguen costando. En (19,46) baja de 1150 a
1141.

## 3. Hornear cada posición conocida y prender/apagar el tilemap — LO QUE FALTA

Es el camino de taro, y es el único que ataca los 1141 cuadros que quedan. Una
baldosa que se mueve **entre dos celdas conocidas** —la suya y una fuera del
mapa— se puede hornear en la suya, como ya se hornean las 22, y al apagarse el
cono, en vez de mover una fila de OAM, se cambia el tile del mapa.

Gana, en el peor caso medido, **1196 → 23 cuadros perdidos de 1200**: de 30 fps
clavados a fluido. El diagnóstico lo midió antes de los caminos 1 y 2, y ésos ya
se llevaron lo que se podían llevar de esa celda: hoy son 1141, y el techo
—"sin las baldosas"— sigue siendo el mismo.

Lo que cuesta, y no es poco: hoy **el tilemap se llena desde el cartucho**
—`fill_window` al entrar y `stream_map` columna por columna al scrollear—, así
que no hay dónde escribir un cambio. Hace falta una tabla de celdas pisadas en
RAM que `stream_map` consulte, y volver a llenar la ventana cuando cambia. El
presupuesto de banco 0 es lo que hay que medir antes de empezar, y en el
cartucho más apretado de los que arma `cartuchos`: ver "Cuánto le sobra al
banco 0" en AGENTS.md.

Y hay una decisión de diseño adentro, que es la que taro puso en una línea:
**que no se dibuje la baldosa, o que no se dibuje el tile que la baldosa tapa,
pero no los dos**. Hornear la baldosa y dejar el tile del mapa debajo es lo que
ya se hace con las 22; lo nuevo es poder volver atrás.

Mueve goldens sólo si se equivoca. Si acierta, se ve igual.

### Cuántos eventos del juego entero califican

Medido el 2026-09-21 sobre los 328 mapas, con
`/extras/scratch/horneado-movil/contar.py`. La regla ampliada —dibujo fijo de
un tile del ChipSet, capa de abajo, sin animación continua, que no camina, y
cuyos únicos movimientos son `ChangeEventLocation` con celda **constante**—
da **59 eventos en 6 mapas**, de 123 con dibujo fijo de ChipSet en todo el
juego:

    mapa   eventos   posiciones por evento
      11      30       3
       3      24       2
      28       2       2
       2       1       2
      17       1       3
      83       1       3

Es la **cota de arriba**: el script no mira opacidad, ni si la celda tiene
lugar, ni si hornear la abriría, que son las condiciones caras.

Así que la regla es general pero **la ganancia está concentrada**: 54 de los 59
están en dos mapas. El segundo es el **mapa 3**, con 24 —`Black*`, `Broke*`,
`BustedConsole*`, `Link*` y `CoreBlood`—, casi todos entre x 59 y 73, o sea del
orden de veinte en pantalla a la vez. Con los siete cuadros por evento dibujado
que están medidos, eso es del orden de 140 cuadros de 1200: molesta, pero no es
el caso del mapa 11. **No está medido en la ROM**, y conviene medirlo antes de
usarlo como argumento: el mapa 3 está en `abl` y dibuja 35 eventos contra los
69 del 11.

Los otros cuatro mapas no justifican nada por sí solos.

## 4. Un caso especial del conversor para las baldosas

Emitir las 52 como una estructura propia —un mapa de bits de "esta celda está
iluminada"— en vez de 52 eventos. Gana lo mismo que el 3 y además ahorra 52
filas de la tabla de NPCs y 52 entradas del recorrido de `pasa_con_evento`.

Lo que rompe: es **reconocer este minijuego por dentro**, que es exactamente lo
que el port no hace en ningún lado. El resto del motor no sabe nada de ABL, y
esto lo sabría. Si el camino 3 alcanza, éste no hace falta.

## 5. Liberarles la paleta de sprite y la ranura de VRAM a los horneados

Está anotado en `done/eventos-opacos-al-mapa.md` y sigue valiendo: hoy un evento
horneado sigue entrando en el reparto de `npcs_dibujables` como si se dibujara.
Sacarlo libera una paleta y **cambia lo que se ve** —el mapa 11 tiene un gráfico
dibujado con una paleta ajena, `@tile:lasheint:49`—, así que **mueve goldens** y
es una decisión aparte. No gana cuadros: gana colores.

# Cómo se reproduce

Los scripts descartables quedaron en `/extras/scratch/mapa11/`: `grupos.py`
clasifica los 84, `porque_no.py` dice por qué la regla rechaza cada baldosa
quieta, `perdidos_zona.py` mide los cuadros perdidos por celda y `capturar.py`
saca las capturas. Las capturas y su `LEEME.txt` están en
`/extras/capturas/mapa11/`.

`perdidos_zona.py` lleva la raíz del worktree escrita adentro: hay que cambiarla
antes de correrlo, y hay que armar los cartuchos antes. Es el que da la tabla de
arriba, y tarda cinco segundos.
