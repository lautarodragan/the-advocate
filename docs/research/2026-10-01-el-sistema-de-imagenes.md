# El sistema de imágenes y la portable console

> **Medido el 2026-10-01 sobre `76d98bed`**, por Jilguero. Es una foto: los
> números son de ese día y este archivo no se actualiza. Las cuentas salieron
> de scripts descartables sobre `rom/data/` y las imágenes del juego; cómo
> rehacerlas está al final, en "Cómo se midió". Cuánto le queda **hoy** a
> cada cartucho lo dice `just espacio`.

## Resumen

* **El juego tiene 348 `ShowPicture`, 33 `MovePicture` y 162
  `ErasePicture`, con 97 imágenes distintas.** Separados por sistema:

      sistema                 ShowPicture  imágenes  dónde
      portable console            262         61     11 comunes, uno automático
      escenas                      28         18     21 páginas de 19 mapas
      contador (Fortitude)         35         11     el mapa 95 y los comunes 9 y 10
      menú viejo, muerto           23          7     comunes 11 a 20 y 34

  Las tres cuartas partes son de la portable console, y casi todas
  —208— son los números de las auras: 25 imágenes de 12x13 que se
  posicionan por variable.
* **La portable console no hace falta para jugar.** Escribe 17 switches y
  10 variables y **nadie fuera de ella lee ninguno**: muestra tutoriales,
  pantallas de habilidades y la cuenta de auras de Talan, y no cambia nada
  del juego. La abre el ítem 81, *Portable Console*, que el juego da en la
  primera escena.
* **Lo que pide además de las imágenes** son cuatro cosas, y ninguna es de
  ABL: los eventos comunes **automáticos** (los paralelos no hacen falta),
  `Label`/`JumpToLabel`, un `CallEvent` **compartido** en vez de pegado en
  el lugar —pegado, el menú son **140.193 comandos**—, y `\V[n]` en los
  mensajes. `KeyInputProc` ya compila tal como lo usa.
* **La idea de taro se confirma, con un matiz.** De las 21 situaciones con
  imagen de las escenas, **18 congelan al héroe** y en **12 el mapa ni
  siquiera se ve**: la escena tiñe la pantalla de negro antes de mostrar la
  imagen, y en RM2k las imágenes no se tiñen. Las tres con el héroe libre
  son imágenes chicas —humo, un cartel de "Ready", el contador—. La consola
  entera es una página automática: congela al héroe, pero el mapa **sí se
  ve** alrededor de su ventana.
* **Ninguna opción sola alcanza, y dos juntas cubren casi todo.** Los
  sprites no pueden con nada más grande que 256x128 pixeles —el tope de 512
  tiles de objeto es del hardware— y 27 de las 90 imágenes son de pantalla
  casi entera. Lo que se recomienda son **dos planos**: **objetos** para lo
  chico sobre el mapa —con los eventos ocultos cuando el mapa no deja
  lugar—, y **BG1 en modo 1** para lo grande con el mapa oculto, que no
  cuesta VRAM porque usa la del mapa y deja BG2 —la ventana de mensaje—
  igual que está. Cubren 20 de las 21 situaciones y toda la consola; lo que
  queda son translúcidos sobre el mapa, que van como deuda.
* **El espacio entra holgado**: todas las imágenes que se usan, a 4 bpp y
  con LZ2, son **unos 330 KB** (escenas 203, consola 128, contador 1),
  **5 o 6 de los 46 bancos** libres. Tucu-tucu estimó ~430 KB sobre las 97
  con 15 colores; con 15 colores también en los textos son 413 KB. Lo que
  infla es el reescalado de los textos, no el tamaño.
* **Primero las escenas, después la consola.** Las escenas son historia
  —"One year previously", "Meanwhile in Lashe City", las instrucciones de
  dos minijuegos, el cartel del final— y piden poco motor; la consola pide
  cuatro piezas de intérprete y no cambia el juego.

## 1. El uso real

### Las escenas

Todas las páginas de mapa que muestran una imagen, agrupadas por
situación. "Negro" quiere decir que la página tiñe la pantalla a (0, 0, 0)
antes, o que el mapa es el negro del arranque: el mapa no se ve y la imagen
sí, porque RM2k no tiñe las imágenes —`affected_by_tint` está apagado por
omisión en `Game_Pictures::ShowParams`, de easyrpg-player—.

    mapa  imagen               disparador   detrás   en la consola  opciones
     4    Oneyearprev          automática   negro    186x29         tono 0→100→0   (la que ya se dibuja)
    81    MeanwhileLashe       automática   negro    214x31         tono 0→100→0
   295    SevDaysPrev          automática   negro    199x30         tono 0→100→0
   309    ABLEndBox8           automática   negro    124x212        tono, el final del juego
    49    EscapeInst           automática   negro    221x191        espera una tecla: instrucciones
   285    AdvoInstr            automática   mapa     240x224        sube 100 px en 4 s: instrucciones
   285    Ready                paralela     mapa     63x31          el minijuego, héroe libre
   212    PhoneCallDiff        automática   negro¹   256x224        zoom 100→0 en 2 s
   213    SurlBroDiff          automática   negro¹   256x224        ídem
   214    SurlGravesDiff       automática   negro¹   256x224        ídem
   216    ThreeRubbleDiff      automática   negro¹   256x224        ídem
   217    las cuatro *Diff     paralela     mapa     256x224        50% translúcidas, una cada 6 cuadros
   208    GTest4               acción       negro    256x224²       ondas, saturación 200, con mensajes
   267    GTest4               paralela     negro    256x224²       ondas, saturación 200, con mensajes
   288    ShipFlash, GTest4    automática   negro    256x224²       ondas, saturación 200, con mensajes
    45    ABLrec               paralela     mapa     51x60          parpadea: "REC" del video de seguridad
    98    ABLrec               paralela     mapa     51x60          ídem
   207    smoke1, smoke2       paralela     mapa     25x59          con el mapa, por variable, 40% translúcido
    32    hovertram2           toque        mapa     132x141        con el mapa, y enseguida un Teleport
   311    hovershadow          toque/autom. mapa     112x119        con el mapa, transparencia 100→50 en 1 s
    95    Fortitude + 2 dígitos toque       mapa     88x23 + 2      el contador, héroe libre

¹ La imagen es una foto de la pantalla, opaca y entera: 15 cuadros
después la página tiñe de negro y la achica a cero en dos segundos.
² La imagen original es de 389x414 y pasa la pantalla; lo de 256x224 es lo
que se ve.

"En la consola" es el tamaño a la escala de la consola: x 256/320 de ancho,
x 224/240 de alto, que es lo que hace `picture.py` con la que ya se dibuja.

**Cuántas a la vez, como máximo:** tres, en el mapa 95 (el rótulo y dos
dígitos). En todas las demás, una.

**El 208** es un evento que se llama `Disabled`, de acción y sin gráfico.
No se averiguó si se puede pisar; está contado.

### La portable console

Es un menú hecho de imágenes y de `KeyInputProc`, y funciona así:

1. El ítem 81, **Portable Console**, es de tipo switch y se usa desde el
   menú: prende el 710. El juego lo da en el mapa 4, la primera escena, y lo
   saca y lo devuelve alrededor de los menús de Radin y de Sern (comunes 42 y
   44, mapas 298 y 321).
2. El 710 dispara el **común 39, `NewMenuActivated`**, automático: una
   ventana con el retrato del personaje (imagen 17, `NewMenu<nombre>`, de
   302x202 mostrada al 50%), dos rótulos "Skills" y "Tutorials" con un
   resaltado rojo translúcido encima (imagen 18, `SkillSelect`, un
   rectángulo de un solo color al 50%) y unas flechas (imagen 19,
   `ArrowTest`, casi todo transparente). Izquierda y derecha cambian de
   personaje entre trece; arriba y abajo, de rótulo.
3. Con la tecla de acción, según el personaje y el rótulo: una **página de
   texto** que tapa casi toda la pantalla (imagen 17 al 100%, 301x202:
   `<nombre>Skill1` o `<nombre>Tutorial1`, blanco sobre negro), un mensaje
   ("There is no skill screen available for…") o una cuenta en un mensaje
   (comunes 48 y 49, con `\V[n]`).
4. Para Talan, con el switch 133 prendido, "Skills" abre el **común 21,
   `ManageAuraMenu`**: una tabla por color de aura (imagen 1,
   `Aura<color>Menu`, 320x203, de pantalla entera) con ocho números encima
   (imágenes 2 a 9, `Aura0`…`Aura24`, que pone cada `DisplayAuraNums[n]`,
   los comunes 23 a 31, con la posición en las variables 67 y 68).
   Izquierda y derecha cambian de color.

Medido en la consola:

* **Cuántas a la vez:** nueve en la tabla de auras (la tabla y ocho
  números); tres en la ventana principal; una en las páginas de texto.
* **Las 61 imágenes**: trece retratos (de 39 a 256 colores), trece páginas
  de texto (2 colores), seis tablas de aura (7 u 8 colores), 26 números de
  aura (2 colores) y las tres piezas de la ventana.
* **Qué opciones usan**: color transparente en 228 de 262; posición por
  variable en 208 (los números de aura); zoom 50% en 23 (la ventana);
  translúcida en 7 (el resaltado). **Ningún** `MovePicture`: para mover algo
  la consola lo vuelve a mostrar. Nada con el mapa, nada de ondas ni
  rotación, ningún tono.
* **Qué tapa**: la ventana principal, 121x94 en la consola, un 20% de la
  pantalla; el mapa se ve alrededor, sin teñir. Las páginas de texto,
  241x189, dejan un marco de mapa de 8 a 17 pixeles. La tabla de auras deja
  sólo una franja arriba y abajo.
* **Nunca hay un mensaje abierto con una imagen grande**: antes de cada
  `ShowMessage`, la consola borra las imágenes 17 y 18.

### El menú viejo, que nadie abre

`CustomMenuHier1` (11), `DisplayNameMenu` (16), los cuatro `CustomMenu*`
(12 a 15), `DisplayNameSlot*` (17 a 19), `GoToHier1` (20) y `ExitTheMenu`
(34) son **un menú anterior que el juego ya no abre**: lo dispara el switch
335, que sólo se prende desde adentro de esos mismos comunes, o el ítem
150, que se llama `SCRATCHEDOUT` y no lo da ningún evento. Son 23
`ShowPicture`, 17 `MovePicture` y 7 imágenes que quedan fuera de todas las
cuentas de abajo. `ManageAuraMenu` sí está vivo: lo llama la consola nueva.

## 2. Qué más pide la portable console

Se compiló cada común como página automática de un mapa de prueba, entero y
comando por comando, con el `rm2k-snes-events` instalado. Hoy:

    común                      entero        lo que no compila
    39 NewMenuActivated        no            Label/JumpToLabel; \V[0173] en un mensaje
    21 ManageAuraMenu          no            Label/JumpToLabel
    48 All Saldra FDs?         no            \V[0195] en un mensaje
    49 All Lerle Memorizes     no            \V[0196] en un mensaje
    40, 22, 23, 25             sí            —
    (el resto de los 24 a 31 son el 23 con otras variables)

Las imágenes compilan porque hoy se aceptan sin hacerse
(`ACCEPTED_UNDONE`); `KeyInputProc` compila tal como lo usa la consola —las
15 son de cinco parámetros, con espera—. Lo que falta, de lo más chico a lo
más grande:

* **`Label` y `JumpToLabel`**: no tienen brazo en el compilador. La consola
  es una máquina de estados hecha con saltos: 15 etiquetas en el 39. En el
  juego hay **8 páginas de mapa** más con etiquetas. Es un `OP_GOTO`, que
  ya existe, con el destino resuelto al compilar.
* **`\V[n]` en un mensaje**: el valor de una variable. `escape_tail` sólo
  acepta las dos pausas al final, y en todo el juego hay tres mensajes con
  `\V`, los tres de la consola (las almas de Sern, las técnicas de Saldra y
  las de Lerle).
* **La posición por variable**: los números de aura se ubican con las
  variables 67 y 68, pero cada `DisplayAuraNums` las carga con constantes
  justo antes (240 y 49 en el primero). El compilador ya sigue las
  constantes —el mapa `constants` de `compile.rs`—, así que se resuelve al
  compilar.
* **Los comunes automáticos**: el 39 lo es. Hoy la ROM no corre ningún
  común por su disparador; sólo se compilan pegados donde los llama un
  `CallEvent`, y los de equipo, que son un caso aparte. Para el 39 alcanza
  con los **automáticos**: un cuerpo por común, compilado una vez en la
  ROM —como `equipment_commons`, que ya lo corre con el puntero de 24 bits—,
  y la ROM mirando su switch al refrescar páginas. Con eso prenden también
  los otros cinco automáticos vivos: el 7 (`AbsorbAuraAbilities`), el 42 y
  el 44 (los menús de Radin y de Sern, que teletransportan), el 43 (la cinta
  de Emily) y el 50 (`RadinUses`). **Los paralelos no hacen falta** para la
  consola, y son los que traían el problema conocido: el 2, `DisableSaving`,
  es paralelo sin switch (ver `party_common_events` en `indices.rs`).
* **Un `CallEvent` compartido**: el compilador pega el llamado en el lugar
  (`decisiones/call-event-se-compila-en-linea.md`), y la consola llama en
  cascada: el 21 llama 18 veces al 25, que llama a ocho de los 23 a 31 por
  color. **Pegado, el 39 son 140.193 comandos**; el 25 solo, compilado hoy,
  son 14.947 bytes. Hace falta un `OP_CALL` a un cuerpo compartido con su
  vuelta y una pila corta —ninguna llamada del juego es recursiva, y el
  anidamiento se topa en `LLAMADA_MAX`—. Sin pegar, los comunes de la
  consola suman unos 2.400 comandos.

**¿Hace falta para jugar? No.** Lo que la consola escribe —los switches 710,
712 a 725, 856 y 857; las variables 63, 64, 66, 67, 68, 156, 167, 192, 195 y
196— no lo lee **ningún** otro evento, común, tropa ni condición de página
del juego: cero lecturas. Las cuentas de auras que muestra —las variables
70 en adelante— las escriben las tropas y el mapa 13; la tabla sólo las
lee. Lo único que se pierde sin ella es información: cómo
funcionan los sistemas de cada personaje y cuántas técnicas le faltan a
cada uno.

## 3. Cómo dibujarlas

### Qué se congela en RM2k

Mientras una página automática, de acción o de toque corre, **el héroe no
se mueve**; tampoco con un mensaje abierto, aunque lo abra una paralela.
Lo demás **sigue**: las rutas de los eventos que nadie espera, los tiles
animados, los eventos paralelos y el cronómetro. Las imágenes no frenan
nada: son una capa más arriba, y se borran solas al cambiar de mapa
(`erase_on_map_change`, prendido por omisión en RM2k 2000).

Sobre las 21 situaciones de la tabla de las escenas —una por fila—:

    congelan al héroe                          18
      con el mapa en negro detrás               12   (4, 81, 295, 309, 49, 212, 213, 214, 216, 208, 267, 288)
      con el mapa visible                        6   (285 AdvoInstr, 217, 45, 98, 32, 311)
    con el héroe libre                          3   (207 humo, 285 Ready, 95 contador)
    tapan el 70% de la pantalla o más           10   (49, 285 AdvoInstr, las cuatro Diff, 217, 208, 267, 288)

Las paralelas del 45, 98 y 217 corren junto con una automática de la misma
escena, y la del 267 abre mensajes: congelan igual. Las tres con el héroe
libre son imágenes chicas: la más grande, el rótulo del contador, de 88x23. La consola entera
congela —es automática— y su mapa se ve.

### Las opciones

Lo que manda es el tamaño. **El tope de los sprites es del hardware**: 512
tiles de objeto (los dos bancos de nombres, `docs/port/vram.md`), 128
objetos, 32 por línea. A 4 bpp, 512 tiles son 256x128 pixeles: media
pantalla. Y **27 de las 90 imágenes que se usan pasan eso** —las 13
páginas de texto, las 6 tablas de aura, las 2 de instrucciones, las 6 de
pantalla entera—: no entran en sprites ni sacando todos los eventos.

**A. Sprites siempre**, que es lo que hace hoy `picture.py` con una sola.

* Cubre: lo chico. Los tres carteles de tiempo (6 o 7 objetos), Ready,
  ABLrec (dos mapas), el humo, el contador, la sombra del 311 (16 objetos,
  256 tiles); y la ventana principal de la consola (12 objetos, ~130 tiles,
  más ~6 objetos de flechas y 2 de resaltado) — **si el mapa tiene lugar**.
  Son 9 de las 21 situaciones de las escenas, y la ventana principal.
* No cubre: el hovertram del 32 (25 objetos, 400 tiles) ni ABLEndBox8 (28,
  448) salvo en un mapa casi vacío; ninguna imagen de más de media
  pantalla: las instrucciones, las fotos, GTest4, las páginas de la
  consola, la tabla de auras. Tampoco las ondas.
* VRAM: lo que cada mapa reserve de su banco de sprites, que ya está al
  tope en los mapas con mucha gente (Delcentric Factory usa 475 de 512).
  El conversor tendría que reservar, por mapa, lo de las imágenes que ese
  mapa puede mostrar; la consola, que se abre en cualquier mapa, no tiene
  lugar garantizado en ninguno.
* CGRAM: una paleta de sprite por imagen, 15 colores. Un retrato de 256
  colores queda en 15.
* ROM: un objeto de 32x32 no comparte tiles con otro, así que se guarda sin
  deduplicar; para lo chico da igual.
* Qué se ve distinto: los colores.

**B. Sin eventos, y la imagen en los sprites** (la segunda idea de taro).

* Cubre lo de A **en cualquier mapa**, porque se lleva los 256 a 512 tiles
  y las ocho paletas de sprite: la ventana de la consola puede tener hasta
  120 colores repartidos por objeto (Adeleine). Suma el hovertram del 32 y
  ABLEndBox8 en los repartos que dan 448 tiles o más: 11 de 21.
* No cubre: lo mismo que A de más de 256x128.
* VRAM y CGRAM: cero extra; al borrar la imagen se vuelven a subir las poses
  de los que estaban, que ya es lo que hace `vram_queue`.
* Qué se ve distinto: **con el mapa visible, desaparecen el héroe, los
  vecinos y el cronómetro** mientras dura. Con el mapa en negro, nada.

**C. Hornear la imagen en una capa del mapa, en caliente.**

* Mezclar una imagen con los tiles de 8 bpp de BG1 es trabajo por pixel en
  formato planar, en la CPU: cientos de tiles para la ventana de la
  consola, decenas de cuadros. Y hay que deshacerlo al borrar. **No se
  recomienda.** Hornearla en el conversor sólo sirve para lo que no se
  mueve ni cambia, y de eso no hay nada en el juego: el humo alterna, el
  resto se muestra y se borra.

**D. Prestar BG2** —la capa de encima y la ventana de mensaje— a la imagen.

* Cubre: lo que entre en los tiles de BG2: 384 tiles de 4 bpp en cinco de
  los seis repartos, 512 en "+encima". De las páginas de la consola entran
  16 de 19 en 384 (no entran Radin, Saldra y Kersh2) y 18 en 512. De las
  escenas, 11 de 21: las chicas, los carteles, ABLEndBox8 y EscapeInst; no
  las fotos de pantalla entera, ni AdvoInstr, ni las que abren mensajes con
  la imagen puesta.
* VRAM: cero extra; al borrar, se vuelven a subir los tiles de la capa de
  encima y de la ventana (unos 12 KB).
* CGRAM: sólo las paletas que la capa de encima tenía, de 1 a 7: la mitad
  baja es del fondo, que se sigue viendo.
* Qué se ve distinto: **la capa de encima desaparece** —techos, copas de
  árboles— en el marco que la imagen no tapa. Y **la ventana de mensaje no
  puede abrirse a la vez**: en la consola nunca pasa, en las escenas sí
  (208, 267, 288, 311).

**E. Otro modo mientras haya una imagen: BG1 en modo 1.**

El modo 1 tiene BG1 y BG2 a 4 bpp. **BG2 ya es de 4 bpp en el modo 3**, así
que cambiar `BGMODE` de 3 a 1 no le cambia nada a la ventana ni a la capa de
encima: sólo hace que BG1 se lea a 4 bpp. Con el mapa oculto, BG1 queda
libre para la imagen.

* Cubre: **todas las de pantalla entera con el mapa oculto**: las 12
  situaciones con el mapa en negro, y AdvoInstr con un marco negro, 13 de
  21. Y las ondas salen **exactas**: son un corrimiento horizontal por
  línea, un canal de HDMA sobre `BG1HOFS`. El tono, la paleta, como hoy.
* VRAM: **cero extra**. A 4 bpp, una pantalla de 256x224 son 896 tiles, 28
  KB, y el lugar de los tiles del fondo es de 24 a 34 KB según el reparto
  —768 a 1.088 tiles de 4 bpp—; deduplicando entran todas salvo cuatro en
  los repartos de 24 KB: SurlBroDiff, SurlGravesDiff y ThreeRubbleDiff (896
  tiles únicos) y GTest4 (888). Ésas piden un reparto de 28 KB o más, o
  llevarse también el lugar de los sprites, que con el mapa en negro no
  hacen falta. El tilemap de BG1 (2 KB) ya alcanza.
* CGRAM: las ocho paletas de fondo menos la de la ventana: **105 colores**,
  que reparte Adeleine por tile. A 8 bpp en el modo 3 habría 255, pero sólo
  entran las imágenes de menos de 384 a 544 tiles únicos —los tres
  carteles, ABLEndBox8 y EscapeInst—; las otras siete no.
* El costo: al borrar la imagen hay que volver a cargar el mapa: los 30 KB
  y los dos cuadros en negro de `back_to_map`. Con el mapa en negro no se
  ven.
* Qué se ve distinto: con el mapa visible (las páginas de la consola,
  AdvoInstr), **el marco de mapa alrededor de la imagen sale negro**.

**F. Modo 7, para el zoom de las fotos *Diff*.** El modo 7 escala, pero su
mapa admite 256 tiles de 8 bpp: una foto entera necesita 896. Entraría a
media resolución, agrandada al doble al principio. Para cuatro escenas de
dos segundos no vale el costo: **se recomienda reemplazar el zoom por un
fundido**, y declararlo.

### Lo que no cubre ninguna

* **Translúcido sobre el mapa visible**: el montaje del 217 (cuatro fotos al
  50% que cambian cada seis cuadros: 28 KB cada una, no se suben en seis
  vblanks), el humo del 207 al 40% y la sombra del 311. El color math está
  descartado (`decisiones/el-color-math-no-se-usa.md`). Opaco el humo y la
  sombra; el montaje, como destellos blancos sin foto. Las tres son deuda.
* **El resaltado de la consola** es un rectángulo rojo al 50% sobre un
  rótulo de la imagen 17, en dos lugares fijos. Se puede componer en el
  conversor: dos variantes de la ventana, una por rótulo. Es lo único de la
  consola que pide algo de ABL.

### Qué cubre cada combinación

    opción                     escenas (21)   consola                         qué se ve distinto
    A sprites                      9          ventana, si el mapa deja lugar  colores
    B sin eventos + sprites       11          ventana                         se van los eventos
    D BG2 prestado                11          ventana; 16 de 19 páginas       se va la capa de encima
    E BG1 en modo 1               13          páginas y auras, marco negro    marco negro; recarga del mapa
    A + B + E (recomendada)       20¹         todo²                           marco negro en las páginas

¹ Falta el montaje del 217, que queda como destellos sin foto. Y con deudas:
el humo del 207 y la sombra del 311 opacos, el zoom de las *Diff* como
fundido.
² La ventana principal en objetos —con los eventos ocultos (B) cuando el
mapa no deja lugar—; las páginas y la tabla de auras en BG1 (E).

## 4. El espacio

Todas las imágenes que se usan, a la escala de la consola, en tiles de 4
bpp deduplicados con espejos, con su tilemap, con LZ2:

                     imágenes   4 bpp, 15 col.   4 bpp, colores propios   8 bpp, 255 col.
    escenas             18         203 KB             203 KB                  421 KB
    portable console    61         208 KB             128 KB                  404 KB
    contador            11           2 KB               1 KB                    6 KB
    total               90         413 KB             332 KB                  831 KB

"Colores propios" quiere decir que una imagen de 2 colores se reduce a 2 y
no a 15: el reescalado de 301 a 241 pixeles mete grises en el texto, que
con 15 colores son tiles distintos. Con 2, las páginas de texto bajan a la
mitad. El menú viejo no está: son 7 imágenes que nadie muestra.

**Contra los 46 bancos libres de 64 KB, son 5 o 6.** La estimación de
Tucu-tucu, ~430 KB, era sobre las 97 y con 15 colores: da lo mismo, y queda
confirmada como orden.

**Con el `.msu`, la versión mejor** sería la de 8 bpp y 255 colores para las
siete fotos (las cuatro *Diff*, GTest4, ShipFlash, AdvoInstr: unos 400 KB
crudos en el `.msu`, que no ocupan ROM), leídas por el puerto de datos como los fondos de batalla
(`docs/port/msu-datos.md`): la ROM sigue llevando su versión de 4 bpp y usa
la otra sólo si la encuentra. Para las páginas de texto **el `.msu` no
mejora nada**: son 2 colores. Lo que las mejoraría es el modo 5 —texto sin
reescalar a 512 pixeles de ancho—, que es la idea de
`wishlist/un-menu-custom-propio.md` y no necesita MSU-1. No se recomienda
empezar por el `.msu`: 4 bpp con 105 colores alcanzan para que taro juzgue
a la vista.

## 5. Recomendación por fases

**Primero las escenas.** Son historia y piden poco motor: imágenes, dos
planos y un par de opcodes. La consola pide además cuatro piezas de
intérprete y no cambia el juego; va después, sobre las escenas, y el menú
propio en modo 5 después de ella.

**El plano lo elige el conversor, imagen por imagen**, como elige el
reparto de VRAM: objetos si entra en el banco de sprites del mapa (o en el
de los eventos ocultos), BG1 en modo 1 si no. La ROM no decide nada.

Lo genérico va en `tools/` —no sabe de ABL—; lo de ABL, en `rom/`:

1. **`Label` y `JumpToLabel`** (`tools/rm2k-snes/events/`). Un `OP_GOTO`
   con destino resuelto. Chico, suma 8 páginas de mapa y es de la consola.
2. **Varias imágenes, en objetos** (`tools/rm2k-snes/images/`,
   `tools/port/picture.py`, `tools/runtime/picture.s`, `events.toml`).
   Generaliza la que hay: los números de imagen de RM2k 2000 (1 a 20) con
   su paleta cada una, las que muestra cada mapa reservadas en su banco de
   sprites, posición —constante o resuelta por constantes—, `MovePicture`
   de posición y de tono, el color transparente, y borrar al cambiar de
   mapa. Suma los carteles del 81 y el 295, Ready, ABLrec, el humo opaco, el
   rótulo del contador y la sombra del 311.
3. **El plano de fondo: BG1 en modo 1** (`tools/runtime/`, `rm2k-snes-images`
   con Adeleine para las 7 paletas, el reparto de VRAM de `tools/rm2k-snes/mapdata/`). La imagen
   grande con el mapa oculto, la recarga del mapa al borrarla, y las ondas
   por HDMA. Suma ABLEndBox8, EscapeInst, AdvoInstr, las cuatro *Diff* (con
   el zoom como fundido) y GTest4/ShipFlash. **Con 2 y 3 se dibujan todas
   las imágenes de las escenas menos el montaje del 217**, con las deudas
   de translucidez escritas en `divergencias/`.
4. **Los comunes automáticos y el `CallEvent` compartido**
   (`tools/rm2k-snes/events/`, `tools/runtime/interpreter*.s`). Un cuerpo
   por común en la ROM, el switch mirado al refrescar páginas, y
   `OP_CALL`/vuelta con una pila corta. Suma de paso los menús de Radin y
   de Sern y la cinta de Emily, si sus mapas están en el cartucho. Los
   paralelos quedan para otra tarea, por el `DisableSaving`.
5. **`\V[n]` en los mensajes** (`tools/rm2k-snes/events/`, el texto
   compuesto en caliente del runtime). Tres mensajes, los tres de la
   consola.
6. **La portable console** (`rom/`: el parche del resaltado, el caso de
   prueba y su golden). Con 1 a 5, compila sola: la ventana principal en
   objetos —con los eventos ocultos si el mapa no deja lugar—, las páginas
   y la tabla de auras en el plano de fondo con el marco negro. Una prueba
   que abra el ítem 81 desde el menú y recorra Talan, sus auras y un
   tutorial.

Después, `wishlist/un-menu-custom-propio.md`: el mismo menú, descripto como
datos y dibujado en modo 5 con fuente, que es lo que arregla de verdad las
páginas de texto.

## Cómo se midió

Todo con scripts descartables en Python, desde la raíz del repo:

* **Los comandos**: recorriendo `rom/data/maps/Map*.json` (cada página),
  `rom/data/db/commonevents.json` y `rom/data/db/troops.json` por los
  códigos 11110, 11120 y 11130. Las tropas no tienen ninguno. Los nombres
  de los comandos, de `tools/rpgmaker/event_codes.json`; los índices de los
  parámetros, de `CommandShowPicture` y `CommandMovePicture` de
  easyrpg-player.
* **Las imágenes**: las de la carpeta `Picture` del juego con Pillow:
  tamaño, colores distintos, fracción de pixeles del índice 0.
* **Quién abre la consola y quién lee lo que escribe**: `ControlSwitches`,
  `ControlVars`, `KeyInputProc` de los comunes de la consola contra
  condiciones de página, `ConditionalBranch`, operandos de `ControlVars` y
  `\V[n]` en todo el resto del juego; los ítems de tipo switch de
  `rom/data/db/items.json` y los `ChangeItems` del 81 y el 150.
* **Qué compila**: un `Map0004.json` falso con una página automática por
  común entero y una por cada comando distinto de cada común (las ramas con
  su cierre), pasado a `rm2k-snes-events scan` por `map_files`; el campo
  `compiled` lo dice por índice de evento, desde 0. Los
  `ShowMessage_2` sueltos que no compilan son artefacto de la prueba.
* **El peso**: cada imagen al zoom con que se muestra, reescalada con
  LANCZOS a 256/320 x 224/240, recortada a la pantalla, reducida con
  `quantize` de Pillow (MEDIANCUT, sin difuminado), cortada en tiles de 8x8
  únicos con espejos, a 4 u 8 bpp planar, con el tilemap de 2 bytes por
  celda, y comprimida con el `lz2` instalado en flujos de hasta 64 KB.
* **Lo que congela**: el disparador de cada página y, en la misma página,
  el último `TintScreen` antes del `ShowPicture`.
