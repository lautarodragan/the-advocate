# Qué

El HQ de los Lazer Teeth —el mapa 11— **no entraba en el cuadro donde se juega
el minijuego de las piedras**, y lo que lo sacaba eran sus **52 baldosas de
luz**: 52 eventos dibujados con el mismo tile opaco del ChipSet, el charco de
luz en el piso.

Se arregló **rediseñando el minijuego**, no optimizando el motor: las baldosas
dejaron de ser eventos. La decisión, y los dos caminos de optimización que se
descartaron para llegar a ella, están abajo.

# Status

**Hecho el 2026-09-21.** Las 52 baldosas de luz dejaron de ser eventos: el
charco es un tile del mapa, apagar un cono es un `TileSubstitution` y atrapar
al héroe es un paralelo que mira el terreno de la celda. El mapa vive forkeado
en `juego/mapas/Map0011.json`, con ChipSet propio.

Cuadros perdidos caminando 1200 cuadros, medidos con
`/extras/scratch/mapa11-cierre/perdidos.py`:

    celda     diagnóstico   los dos caminos   rediseñado
    (50,50)       231             153              0
    (26,47)       625             475              2
    (18,50)      1200               9              0
    (19,46)      1196            1141             11
    ( 5,50)      1200              19              0

**La celda donde el minijuego se juega pasó de 30 fps clavados a once cuadros
perdidos de 1200**, por debajo del techo que el diagnóstico había medido —23—.
Los eventos dibujados del mapa pasan de 69 a 17.

Y se juega: `pruebas/abl/test_luces.py` mide que pararse en una baldosa
iluminada abra el mensaje del "me atraparon", y que la piedra en `Light5`
apague su cono y deje puesto el switch de la lámpara rota.

**Lo que se descartó**, y es la decisión que abrió todo esto: los caminos 3 y
4, que eran optimizaciones del motor. Ver "Por qué no se optimiza" más abajo.

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

# Por qué no se optimiza

## 3. Hornear cada posición conocida y prender/apagar el tilemap — DESCARTADO

Era el único camino que atacaba los 1141 cuadros: una baldosa que se mueve
**entre dos celdas conocidas** se hornea en la suya, y al apagarse el cono se
cambia el tile del mapa en vez de mover una fila de OAM. Techo medido, **1196 →
23 cuadros perdidos de 1200**.

La regla es general —es la del horneado de hoy con "nunca se mueve" cambiado
por "se mueve sólo a celdas constantes"— y **no sabe nada de ABL**. Lo que la
descartó es cuánto rinde, medido el 2026-09-21 sobre los 328 mapas con
`/extras/scratch/horneado-movil/contar.py`:

    mapa   eventos   posiciones por evento
      11      30       3
       3      24       2
      28       2       2
       2       1       2
      17       1       3
      83       1       3

**59 eventos en 6 mapas**, de 123 con dibujo fijo de ChipSet en todo el juego,
y es la cota de arriba: el script no mira opacidad ni si hornear abriría la
celda. O sea que **54 de los 59 están en dos mapas**, y el segundo —el 3, la
sala destrozada del Emitter Room, con unos veinte eventos en pantalla a la
vez— **no molesta jugando**: taro nunca notó lag ahí.

Decisión de taro: no se paga una tabla de celdas pisadas en RAM, más el
consultarla en `stream_map`, por un mapa. **Promediando otros juegos, rinde
menos de un mapa.**

## 4. Un caso especial del conversor para las baldosas — DESCARTADO

Lo descarta lo mismo que al 3, y antes ya lo descartaba que **reconoce este
minijuego por dentro**, que es lo que el port no hace en ningún lado.

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

# El rediseño

Decidido el 2026-09-21. **Las 52 baldosas dejan de ser eventos**: el charco de
luz pasa a ser un tile del mapa, y prender o apagar un cono es cambiar ese tile.
Con eso no queda nada que optimizar, y lo que el motor gana son **dos comandos
de RM2k que hoy no implementa**, útiles para cualquier juego que se porte.

Gana lo mismo que ganaba el camino 3 —de 1141 cuadros perdidos al piso— y
además saca 52 filas de la tabla de NPCs, que `pasa_con_evento` recorre en cada
paso.

## Los dos comandos, verificados contra liblcf y el intérprete de EasyRPG

* **`TileSubstitution` (11750)**, parámetros `[capa alta?, tile viejo, tile
  nuevo]`. Sustituye **todas** las celdas con ese tile, en esa capa, en todo el
  mapa. Es por **número de tile y no por celda**, así que en la ROM es una
  tabla chica en RAM que `stream_map` consulta al escribir cada tile —bastante
  más barato que la tabla de celdas pisadas que pedía el camino 3—.

  Que sea global por tile es lo que obliga a **duplicar el tile**: un número
  por cono, o apagar uno los apagaría todos. Y duplicar **sale gratis**: Voodoo
  deduplica a nivel 8x8 y reusa el espejado, así que un tile de ChipSet
  repetido son cuatro celdas que ya estaban.

* **`StoreTerrainID` (10910)**, parámetros `[modo, x, y, variable]`. El terreno
  sale del tile de la **capa de abajo** —"RPG_RT always uses the terrain of the
  first lower tile"—, no del de la capa alta. O sea que el terreno **no puede
  decir "estoy iluminada"**, porque esa capa no cambia al apagarse el cono:
  dice **"esta celda es del cono C"**, y si C está prendido ya lo sabe un
  switch que el juego tiene.

  De ahí sale que hagan falta unos pocos pisos duplicados y no 52: uno por
  cono. El paralelo queda en leer el terreno bajo el héroe, y si es de un cono,
  mirar su switch.

  **Son tres y no seis**, medido al hacerlo: sólo tres grupos de celdas
  atrapan. Los tres terrenos son el 27, el 28 y el 29, que no los usa ningún
  ChipSet del juego y traen los mismos valores que el 1 —el que el mapa tiene
  hoy en todas sus celdas—, así que estrenarlos no cambia nada más que lo que
  `StoreTerrainID` contesta.

El port tiene que emitir además la **tabla de terrenos por ChipSet**, que
`lcf.py` ya lee (`terrain_data`) y nadie usa. Va al banco 1, que tiene unos
21 KB libres.

## Lo medido del ChipSet

El mapa 11 usa el **ChipSet 10**, que comparten siete mapas. Entre todos ocupan
55 de los 144 tiles de la capa alta: **quedan 89 libres**. La capa de abajo
tiene 162 ranuras, y el `terrain_data` del ChipSet 10 es **todo 1** — ABL no usa
terrenos en ningún lado.

Aun así, el rediseño va con **un ChipSet propio para el mapa 11**, decisión de
taro: no comparte con nadie, así que duplicar pisos con su terreno no le toca
un pixel a los otros seis mapas, y la deduplicación hace que un ChipSet casi
igual al 10 no cueste tiles.

## Lo que el reset pide

`ResetPuzzle` reubica hoy 42 eventos **sin recargar el mapa**. Recargarlo no es
equivalente —movería también al héroe y a la piedra—, así que **la baldosa
apagada también es un tile propio**: prender es `80 → 80A` y apagar es
`80A → 80`, la sustitución es simétrica y el reset es volver a sustituir.

**Que `TileSubstitution` no persista es canon y se deja así**: en el intérprete
se aplica al spriteset de la escena, o sea que se pierde al recargar el mapa. En
ABL nunca se vuelve a este mapa, así que no hay nada que reaplicar.

El único caso donde el rediseño podría diferir del original es **volver de una
pelea**: en canon se perderían las sustituciones, pero los eventos de hoy
sobreviven. No pasa, y está verificado: `Lazer Teeth HQ` tiene `encounters: []`,
o sea ninguna tropa asignada. Queda anotado porque es lo que se reintroduce sin
querer el día que alguien le ponga tropas a un mapa.

De ahí sale una decisión de implementación que conviene tomar a propósito: **la
tabla de sustituciones vive lo que vive el mapa cargado, no lo que vive la
ventana del tilemap**. Limpiarla al cargar un mapa y no al rellenar la ventana
la deja canónica y además correcta si algún día se vuelve de una pelea.

## Las 33 baldosas con comandos

Se dieron por copy-paste y **no lo son**, aunque casi: al mirarlas una por una
—el 2026-09-21, antes de borrarlas— salieron cinco scripts distintos y cuatro
celdas con páginas propias.

Los cinco scripts son el mismo "me atraparon, se reinicia el minijuego" con el
guardia que mira y el texto cambiados: el del cono C lo agarra el `LTSentry2` y
no el `LTSentry1`, la `A1` dice "avoid the light" donde las del B dicen "avoid
the light, or not be seen", y hay una variante "avoid being seen" para cuando
el guardia está caminando. Se copian tal cual a un evento de cinco páginas y
el paralelo llama a la que toca, que es la forma que el mapa ya usaba.

Las cuatro celdas con páginas propias son del grupo B y miran dos switches: el
46 —el guardia se fue a ver el ruido— y el 51 —está caminando—. Una deja pasar,
dos contestan "Something behind me?!" y tres cambian el texto. El paralelo las
distingue por celda, y esa comparación **sólo corre cuando el héroe ya está
parado en una del grupo B**, o sea una vez por partida y no una por cuadro.

## El fork del mapa, no el parche

El mapa 11 rediseñado es un **reemplazo entero del archivo**, no una
descripción de cambios, y el pipeline ignora el original si existe. Tres cosas
que lo sostienen:

* **No va en `parches/`**, que hoy es **salida generada** —las fusiones de
  color que decidió el asignador—. Esto es entrada escrita a mano que manda
  sobre todo lo demás: dos direcciones opuestas en un directorio es lo que
  alguien regenera sin mirar.
* **El original sigue versionado en `data/`**, así que el diff no se pierde: se
  computa cuando haga falta. Y nada se pisa, porque `unpack` escribe en `data/`
  y nunca en el fork.
* **Es todo o nada.** Las capas viven afuera del JSON, así que un `.json` sin
  su `.tiles` dejaría el build con las capas viejas y los eventos nuevos, y eso
  **se ve bien** hasta que no. Falta una pieza, el build se niega.

Las pruebas que pide, de taro y de acá: que el **id de adentro coincida con el
nombre del archivo** —si no, se rompen los teleports—, y que **los teleports
que entran a ese mapa desde el resto del juego sigan cayendo en celdas
pisables**, que es la que rompe el juego de verdad y el id no cubre. El mapa 11
está en `abl`, así que su golden cubre lo demás.

Todo el fork es data y **Ditto lo puede escribir**: lee y escribe `.ldb`,
`.lmu` y `.lmt`, con round-trip sobre los 330 archivos. Son cuatro cosas: el
ChipSet nuevo en la base con su pasabilidad y sus terrenos, el `chipset_id` del
mapa, el `upper_layer` con los charcos horneados, y los 52 eventos reemplazados
por uno paralelo.

**Hecho el 2026-09-21**, con tres cosas que se decidieron al hacerlo y que este
documento no preveía —el porqué de cada una, en `juego/README.md`—:

* el fork del mapa lleva adentro un campo `id` que el volcado de Ditto no
  tiene. Es lo único que hace real la prueba que taro pidió: el pipeline elige
  el mapa por el **nombre del archivo** y los teleports lo nombran por su
  **id**, y sin ese campo no hay "id de adentro" que comparar;
* **el ChipSet nuevo no reemplaza la sección de la base: se agrega**, en un
  archivo propio. Un fork que pisara `db/chipsets.json` envejecería sin avisar
  el día que `just datos` la cambie;
* **su imagen no se versiona: se arma.** El arte del juego no es nuestro para
  redistribuir —vive en `/extras`—, así que lo commiteado es la receta —qué
  bloque y qué tile se copian adónde— y el PNG sale a `rom/build/juego/`.

## La trampa que apareció al armarlo: el bloque de destino

`TileSubstitution` cambia un tile por otro, pero la ROM dibuja **bloques de
16x16 con las dos capas juntas**. Si el mapa ya dibuja en alguna celda la
combinación que la sustitución va a dejar, el bloque existe y no hay nada que
armar; si no, el conversor lo arma, y **no puede cuando alguno de los dos tiles
se hornea en el fondo** —un tile alto sin el bit `Above` no va a BG2, y ahí las
dos mitades del bloque dejan de ser independientes—.

Los charcos de luz son exactamente ese caso: van **debajo** del héroe, así que
no llevan `Above`. Darles el bit para que el bloque se pueda armar los pondría
por encima, y el charco es opaco: **el jugador desaparecería al pararse en la
luz**.

La salida no toca cómo se ve: se le **dibujan al mapa las combinaciones que
faltan**, una celda cada una, en la última fila. El mapa es de 100x100 y todo
su contenido entra en x 1..28, y 35..58, así que ahí no llega ni el héroe ni la
cámara —es donde el propio juego estaciona los eventos que apaga—. Son quince,
y no son una lista escrita a mano: las deduce
`/extras/scratch/mapa11-cierre/faltantes.py` del mapa y de sus propias
sustituciones, y después de aplicarlas contesta cero.

**Le va a pasar a cualquier fork que sustituya un tile que no lleve `Above`.**

## Lo que queda distinto del original, y taro lo tiene que juzgar

* **El cono tarda en apagarse.** El tilemap se rehace de a una columna por
  cuadro, así que la sustitución no se ve en el acto como en RM2k: quieto puede
  tardar hasta `WINDOW_COLS` = 64 cuadros. Caminando se disimula. Subir dos
  columnas por cuadro no entra: `push_strips` sube una sola.
* **Cuándo salta el "me atraparon"**: antes era contacto —dispara en el paso—,
  ahora es un paralelo que mira la celda. Un cuadro de diferencia.

## El reparto

**Del motor, y general**: `TileSubstitution`, `StoreTerrainID`, la tabla de
terrenos, y el mecanismo del fork con sus pruebas. **Hecho**; lo que no
resultó como se había supuesto está arriba, en "Status", y es que la
sustitución tarda en verse.

Y dos cosas que el motor pide y este documento no preveía —las dos son lo que
hoy frena al mapa 11, ver "Status"—: **el tile hacia el que se sustituye tiene
que estar dibujado en alguna celda del mapa**, en su capa, porque los 8x8 que
entran en la VRAM son los de las celdas del mapa; y **si es un tile alto, con
el bit `Above` puesto**, porque sin él se hornea en el fondo y las dos capas
del bloque dejan de ser independientes.

**De ABL**: el ChipSet propio, los tiles duplicados, los terrenos por cono y el
mapa rediseñado. **Hecho.**

# Cómo se reproduce

Los scripts descartables quedaron en `/extras/scratch/mapa11/`: `grupos.py`
clasifica los 84, `porque_no.py` dice por qué la regla rechaza cada baldosa
quieta, `perdidos_zona.py` mide los cuadros perdidos por celda y `capturar.py`
saca las capturas. Las capturas y su `LEEME.txt` están en
`/extras/capturas/mapa11/`.

`perdidos_zona.py` lleva la raíz del worktree escrita adentro: hay que cambiarla
antes de correrlo, y hay que armar los cartuchos antes. Es el que da la tabla de
arriba, y tarda cinco segundos.
