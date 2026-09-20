# Qué

El HQ de los Lazer Teeth —el mapa 11— **no entra en el cuadro donde se juega el
minijuego de las piedras**, y lo que lo saca son sus **52 baldosas de luz**:
52 eventos dibujados con el mismo tile opaco del ChipSet, el charco de luz en
el piso. Hornear los 18 que caían en la regla de los eventos opacos bajó el lag
a la mitad **en una zona vacía del mapa**, que no es donde se juega.

# Status

**Diagnóstico hecho y medido, sin implementar nada.** Falta que taro elija
camino: están abajo, con lo que gana y lo que rompe cada uno.

El build con que se midió es descartable y **no va a `main`**: es una variable
de entorno en `snes_convert.py` que le apaga el dibujo a un grupo de eventos,
con el mismo mecanismo con que nacen escondidas las filas de los horneados.
Está en el commit marcado `DESCARTABLE` de la rama `worktree-agent-af33fbcd7a65c7dd1`,
revertido en el commit siguiente.

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
`collect_npcs` ya lo sabe: les da `cambia` falso—.

# Los caminos, con lo que cuesta cada uno

## 1. Aflojar la regla del horneado de "una sola página" a "todas sus páginas dibujan lo mismo"

**Es chico y es seguro, y es el único de la lista que yo recomendaría hacer sin
más discusión.** La condición pasa a ser: la primera página sin condición, y
todas las páginas con el mismo gráfico y la misma capa. El resto de la regla no
se toca.

Gana **+4 eventos en el mapa 11 y +1 en el mapa 2**: 26 → 31 sobre el juego
entero, preguntándole a `eventos_horneables` mapa por mapa. (El "32 en 12 mapas"
de `done/eventos-opacos-al-mapa.md` salió de un script aproximado, no de la
función; la función contesta 26 en 8 mapas.)

No mueve goldens —el tile dibujado es el mismo, en la misma celda y en la misma
capa— y `test_horneados.py` ya cuida las dos invariantes que ninguna captura ve.
Lo que hay que mirar: que la pasabilidad sea la misma en **todas** las páginas,
no sólo en la activa, porque la fila escondida deja de imponerla.

**Lo que no arregla**: nada del lag donde se juega. Esas cuatro baldosas están
dentro del grupo B, que ya está casi entero horneado.

## 2. No procesar la fila de un evento que cae fuera de pantalla

Un `cmp` contra la cámara en `build_oam`, antes de `place_npc`. Recupera parte
de los 156 cuadros de (50,50) y de los 52 de (19,46) —no todos: `emit_object`
ya descarta, así que lo que se ahorra es `place_npc` y la mitad de
`emit_object`—.

Gana poco pero **gana siempre y en todos los mapas**, no sólo en el 11, y se
lleva de arriba **todas las baldosas del cono apagado**, que es el estado en que
el jugador pasa la segunda mitad del minijuego. No mueve goldens: un objeto que
`emit_object` descarta no está en la captura.

Lo que hay que cuidar: el margen de la comparación. Un evento de 32x32 asoma
32 pixeles antes de entrar, y cortar con el rectángulo justo lo haría aparecer
de golpe. El rango tiene que ser el mismo que usa `emit_object`.

**No arregla el caso que importa**: con el cono prendido las baldosas están en
pantalla y siguen costando.

## 3. Hornear cada posición conocida y prender/apagar el tilemap

Es el camino de taro, y es el único que ataca los 1196 cuadros. Una baldosa que
se mueve **entre dos celdas conocidas** —la suya y una fuera del mapa— se puede
hornear en la suya, como ya se hornean las 18, y al apagarse el cono, en vez de
mover una fila de OAM, se cambia el tile del mapa.

Gana, en el peor caso medido, **1196 → 23 cuadros perdidos de 1200**: de 30 fps
clavados a fluido.

Lo que cuesta, y no es poco: hoy **el tilemap se llena desde el cartucho**
—`fill_window` al entrar y `stream_map` columna por columna al scrollear—, así
que no hay dónde escribir un cambio. Hace falta una tabla de celdas pisadas en
RAM que `stream_map` consulte, y volver a llenar la ventana cuando cambia. El
presupuesto de banco 0 es lo que hay que medir antes de empezar: con
`demo-ciudad` sobran 85 bytes.

Y hay una decisión de diseño adentro, que es la que taro puso en una línea:
**que no se dibuje la baldosa, o que no se dibuje el tile que la baldosa tapa,
pero no los dos**. Hornear la baldosa y dejar el tile del mapa debajo es lo que
ya se hace con las 18; lo nuevo es poder volver atrás.

Mueve goldens sólo si se equivoca. Si acierta, se ve igual.

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
