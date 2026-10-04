# El menú custom: la portable console como datos y no como imágenes

> **Escrito el 2026-10-04 sobre `43b552f5`**, por Lagartija, con ABL en
> `5b29ba9`. Es una foto: los números son de ese día y este archivo no se
> actualiza. Cómo rehacer cada cuenta está al final, en "Cómo se midió".
> Las capturas del original y las maquetas se entregaron aparte: ver
> `workflow/tasks/*/el-menu-custom-de-la-consola.md`.

## Resumen

* **La consola no hace falta para avanzar, pero sí para jugar bien.** Los
  quince comunes que la forman (39, 40, 21 a 31, 48 y 49) sólo usan
  saltos, switches, variables, imágenes, mensajes, sonidos y
  `KeyInputProc`: ningún ítem, grupo, habilidad ni teletransporte. Escriben
  17 switches y 10 variables y **nadie fuera de ellos lee ninguno** —medido
  sobre los comunes, los 2.656 lugares de los mapas y las tropas—. Lo que
  se pierde sin ella es información: las guías de cada personaje y los
  contadores —cuántas veces absorbió Talan cada técnica y cuántas le
  faltan, las almas de Sern, las técnicas de Saldra y de Lerle—. Las auras
  **no se eligen** ahí: la tabla sólo lee las variables 70 a 122, que
  escriben las peleas.
* **Casi todo es texto.** De las 61 imágenes, 13 son páginas de texto
  blanco sobre negro, 6 son tablas de auras con los nombres y el "cuántas
  hacen falta" pintados, 26 son los números de las tablas, y 3 son la
  ventana y sus resaltados. **Arte de verdad son 10 retratos**: los otros
  tres (Radin, Drago y Sern) son un cartel de "Picture Unavailable".
* **La propuesta**: una pantalla del motor, **un menú custom descripto como
  datos** —ventanas del System, texto compuesto de ancho variable, listas
  con cursor, números que salen de variables, y la cara del actor o un
  retrato—, que se abre desde **una opción más del menú de pausa** y
  **siempre a pantalla completa**, como el menú de ítems. El juego lo
  declara en un archivo propio que nombra el `rm2k-snes.toml`, y se
  engancha con la lógica de eventos por dos lados: reemplaza al común que
  abría el menu de imágenes —así el ítem 81 sigue andando— y puede correr
  un común antes de dibujar una página, para las cuentas que hoy hacen los
  comunes 48 y 49.
* **Cuesta poco**: unos pocos KB de texto y de tablas, unos 2 KB de código
  —estimado— que reusa la capa de texto y las ventanas de las pantallas, y
  **cero o 48 KB de arte**, según se usen las caras que el cartucho ya lleva
  o los diez retratos a 4bpp. Las imágenes de la consola eran **128 a 208
  KB** (`2026-10-01-el-sistema-de-imagenes.md`).

## 1. El inventario

Mirado en el original, con el RPG_RT de 2015 corriendo con Wine sobre una
copia del juego cuyo mapa 4 arma un grupo de cuatro —Talan, Sern, Emily y
Arden—, prende el 133, pone unos contadores de aura y las almas de Sern
en 42, y abre la consola en el departamento de Talan. Y leyendo los
comunes en el volcado.

### Cómo funciona

El ítem 81, *Portable Console*, es de switch: prende el 710, que dispara el
común 39, automático. El 39 es una máquina de estados hecha de
`Label`/`JumpToLabel` y `KeyInputProc`, que dibuja una ventana encima del
mapa —el mapa se sigue viendo alrededor— con tres imágenes:

    17  NewMenu<nombre>   el retrato a la izquierda y los rótulos "Skills" y
                          "Tutorials", al 50%
    18  SkillSelect o     un rectángulo rojo al 50% sobre el rótulo elegido
        TutorialSelect
    19  ArrowTest         dos flechas: ↑↓ a la derecha y → abajo

* **Izquierda y derecha** recorren los personajes **del grupo**, en un orden
  fijo del común —Kersh, Manta, Core, Talan, Saldra, Arden, AG7-17, Dalia,
  Radin, Lerle, Sern, Drago, Emily, Kersh2—; cada uno prende su switch
  (712 a 725). Izquierda en realidad no hace nada: sólo suena.
* **Arriba y abajo** eligen "Skills" (856) o "Tutorials" (857).
* **A** abre la página; **B** cierra la consola (`EraseAllPictures` y el
  710 apagado).
* **Al volver de una página** el común salta a la etiqueta 20 y de ahí a la
  15, que **vuelve a elegir al primer personaje del grupo**: después de
  leer la guía de Emily, la consola está otra vez en Talan. Se ve en las
  capturas; no parece buscado.

### Página por página

Fijo quiere decir pintado en la imagen; variable, que sale del estado.

**La ventana principal** (`NewMenu<nombre>`, 302x202 al 50%):

* arte: el retrato, unos 150x188 pixeles del original; diez personajes lo
  tienen, Radin, Drago y Sern tienen el cartel;
* fijo: "Skills", "Tutorials" y las flechas;
* variable: qué personaje (los del grupo) y qué rótulo.

**Las guías** ("Tutorials", `<nombre>Tutorial1`, 301x202 al 100%, blanco
sobre negro, tapan casi toda la pantalla):

* todo fijo: un párrafo de cuatro a doce renglones. Hay diez —Talan,
  Arden, Emily, Lerle, Radin, Sern, Saldra, Kersh2, AG7-17, y una segunda
  de Talan—;
* variable: **cuál**. Talan tiene dos y elige por el switch 133: sin él
  dice que "no tiene sistemas especiales", con él explica DETECT AURA y
  ABSORB AURA. Manta, Core, Drago y Dalia no tienen: un mensaje dice "There
  is no tutorial screen available for MANTA at the current time."

**Las habilidades** ("Skills"), que son cinco cosas distintas:

* **Talan, con el 133 prendido**: la tabla de auras, el común 21. Seis
  tablas, una por color —Blue, Red, Green, Yellow, Black, White—, que se
  recorren con izquierda y derecha, en círculo. Cada una es una imagen de
  pantalla entera con el título, ocho nombres de técnica y "/ N", lo que
  hace falta para aprenderla —fijo—, y encima ocho números de 12x13 en
  imágenes sueltas: **cuántas veces la absorbió**, una variable por
  técnica (70 a 77 la azul, 79 a 86 la roja… hasta 115 a 122 la blanca).
  De 0 a 24 dibuja el número; **99 dibuja una raya**, que es lo que el
  juego pone cuando la técnica ya es suya. B vuelve.
* **Talan sin el 133**: una página fija, "TALAN does not have any skills."
* **Emily y Arden**: una página fija cada una —los efectos de radio por
  cinta de Emily, las técnicas por nivel de Arden—.
* **Sern, Saldra y Lerle**: un mensaje con una variable. Sern dice sus
  almas, la 173, que escriben las peleas. Saldra y Lerle **la calculan al
  abrir**: los comunes 48 y 49 cuentan cuántas de ciertas técnicas sabe el
  actor —con `ConditionalBranch` de "sabe la habilidad"— y la ponen en la
  195 o la 196: "SALDRA has learned 3 of the 8 skills necessary…".
* **Los demás**: un mensaje, "There is no skill screen available for RADIN
  at the current time."

Ningún contador se escribe desde la consola: los lee. El único estado que
la consola guarda es por dónde va el cursor, en sus propios switches.

## 2. El diseño

### Lo que decidió taro

* **Es una opción más del menú de pausa**, al lado de Items, Skills,
  Equipment, Save y End Game, con el rótulo que el juego declare
  ("Console", "Guide"…): "ya tenerlo en el menú lo haría más unificado y
  tal vez más simple, también".
* **Siempre a pantalla completa**: "este sistema no permite renderizar
  sobre el mapa. Así solucionamos desafíos de VRAM etc." Como el menú de
  pausa, que ya tapa el mapa y al cerrarse lo repone.
* Es una feature del motor, de RPG Maker 2000 PLUS
  (`decisiones/rm2k-plus.md`): la usa ABL, la puede usar cualquier juego.

### Qué es: una pantalla que el motor recorre

Un menú custom es un **árbol corto de pantallas declaradas**, que el motor
dibuja y navega solo, con las reglas de las pantallas que ya tiene:

    menú            el rótulo en el menú de pausa, cuándo aparece, a qué
                    común reemplaza
      sujetos       una lista: quién o qué se mira —un actor del grupo, o
                    una entrada fija—, con su arte y su condición
        pestañas    lo que se puede mirar de cada sujeto: "Skills", "Guide"
          página    lo que se ve: la primera de su lista cuya condición se
                    cumple; ninguna, y la pestaña sale gris

**Una página es de uno de tres tipos**, que son lo que la consola de ABL y
los menús de imágenes que se conocen usan:

* **texto**: un párrafo, que el conversor parte al ancho de la ventana con
  la fuente del juego —lo mismo que hace con los mensajes—, con `\V[n]`
  para una variable y `\N[n]` para el nombre de un actor. Si no entra,
  baja con arriba y abajo.
* **tabla**: renglones de *nombre, valor y tope*: el valor es una variable,
  el tope una constante o otra variable, y la tabla declara qué se
  escribe en lugar de un valor especial —el 99 de las auras como
  "Learned"—. Una tabla puede tener **hojas**, que se recorren con
  izquierda y derecha: los seis colores de aura son una tabla de seis
  hojas, cada una con su título y su color de letra.
* **contadores**: dos o tres renglones de "rótulo … número", arriba de un
  texto. Es la página de Sern; con un común antes, las de Saldra y Lerle.

**Los colores son los del System**, como en todas las pantallas: rojo
para los rótulos —el color de "HP" y "L" en el menú—, gris para lo que no
está —la técnica ya aprendida, la pestaña sin página—, y los demás para lo
que el juego quiera, como el título de cada aura en su color.

### Cómo se navega

Como el original, que es lo que el jugador de ABL ya conoce, y con las
teclas del menú de pausa:

* **Izquierda y derecha**: el sujeto anterior y el siguiente —en una tabla
  con hojas, la hoja—. La cabecera dice "< 2 / 4 >".
* **Arriba y abajo**: la pestaña, con la barra del System; en una página
  larga, desplaza.
* **A**: abre la página. **B**: vuelve un nivel; desde los sujetos, al menú
  de pausa, con el cursor en la opción.
* **Al volver de una página se queda en el mismo sujeto**: es lo que el
  original no hacía.

### Cómo lo declara un juego

**En un archivo propio, que nombra el `rm2k-snes.toml`**:

    [menus]
    # Cada menú custom, por el archivo que lo describe. Ver
    # docs/research/2026-10-04-el-menu-custom.md.
    console = "menus/consola.toml"

Y el archivo, abreviado:

    label = "Console"
    # Aparece en el menú de pausa sólo con el ítem 81 en el inventario: es
    # cuando el original deja usar la consola —el juego lo saca y lo
    # devuelve alrededor de los menús de Radin y de Sern—.
    visible = { item = 81 }
    # El común que abría el menú de imágenes: abre éste.
    replaces_common = 39

    [[subject]]
    actor = 14                      # Talan; sale si está en el grupo
    art = "picture:NewMenuTalan"    # o "face", la del actor
    crop = [6, 6, 150, 188]

    [[subject.tab]]
    label = "Skills"
    [[subject.tab.page]]
    when = { switch = 133 }
    table = "auras"
    [[subject.tab.page]]
    text = "TALAN does not have any skills."

    [[subject.tab]]
    label = "Guide"
    [[subject.tab.page]]
    when = { switch = 133 }
    text = """TALAN can equip clubs and other similar weapons. …"""

    [[table.auras.sheet]]
    title = "Red"
    color = 1
    rows = [["Candle Flame", "v79", 5], ["Minor Fire", "v80", 5], …]
    special = { 99 = "Learned" }

    [[subject]]
    actor = 17                      # Saldra
    [[subject.tab]]
    label = "Skills"
    [[subject.tab.page]]
    before = { common = 48 }        # cuenta las técnicas en la 195
    counters = [["FD techniques", "v195", 8]]
    text = "SALDRA can learn more techniques by reading …"

Las condiciones son **las de las páginas de RM2k** —switch, variable `>=`,
ítem en el inventario, actor en el grupo—, que el compilador de eventos ya
sabe compilar: no hay un lenguaje nuevo de condiciones.

**Por qué un archivo propio y no otra cosa**:

* **No en el `rm2k-snes.toml`**: son decenas de párrafos de texto, y ese
  archivo es de perillas y listas cortas. Allá va
  sólo qué menús hay.
* **No en los comunes**, como comentarios o comandos nuevos que el editor
  no conoce: el juego tendría que reescribir su máquina de estados para
  dibujar texto en vez de imágenes, y la navegación quedaría de nuevo en
  manos de cada juego, que es lo que hizo feo al original. Y el volcado es
  derivado: lo nuestro vive al lado (`parches/README.md` de ABL).
* **TOML**, como el resto del proyecto, y que el juego **transcribe** el
  texto de sus imágenes: es el único paso que no se automatiza, porque
  leer texto de una imagen es adivinar. Para ABL son trece páginas y seis
  tablas.

### Cómo se conecta con los eventos

* **El común reemplazado** (`replaces_common = 39`): el compilador no
  compila su cuerpo, sino un opcode nuevo, `OP_MENU_OPEN menú`, y **apaga
  su switch**, porque un automático que no lo apaga corre para siempre. El
  ítem 81 prende el 710 como siempre, y el 710 abre el menú custom: el
  ítem sigue sirviendo, y la opción del menú de pausa es la otra puerta.
  Así no hace falta un parche del ítem, y un juego que no declara
  `replaces_common` no toca ningún evento.
* **Lo que el 39 llama queda sin llamar**: el 40, el 21 y los 23 a 31 sólo
  dibujaban. **Los que calculan** —el 48 y el 49— se nombran como `before`
  de su página: el motor los corre con el mismo cuerpo compartido que ya
  tienen los comunes (`OP_CALL`, `commons.rs` en `rm2k-snes-events`), sin
  imágenes ni mensajes, y después dibuja.
* **El menú no escribe estado del juego**: sólo lee. Los switches 712 a
  725, 856 y 857 quedan sin usar, que es lo mismo que pasaba con el
  original para el resto del juego.

**Por qué el motor navega y no los eventos.** La otra opción era dejar la
lógica en los comunes y sumar opcodes para dibujar texto —una "imagen de
texto", como hacen otros parches de RM2k—. Se descarta porque la máquina
de estados de la consola **no tiene lógica de juego**: sólo existe para
imitar un menú con `KeyInputProc`. Declarado, el menú se navega igual que
el de pausa, el cursor no se pierde al volver de una página, y otro juego
lo usa sin programar eventos. Si un juego necesita que una entrada **haga**
algo —un menú de misiones que marca una—, el paso siguiente es un renglón
con `action = { common = N }` que corre ese común con A: el mismo
mecanismo que `before`. La consola de ABL no lo pide.

### Para otros juegos

Lo que la feature no asume de ABL: los sujetos pueden ser actores o
entradas fijas —un bestiario, un diario, un menú de misiones—; las
condiciones son las de RM2k; el arte es opcional; las tablas leen
variables cualesquiera. Lo que un juego con un menú de imágenes hace
para portarlo es lo mismo que ABL: transcribir el texto, declarar las
páginas y nombrar el común que reemplaza.

## 3. A pantalla completa: qué da la VRAM entera

Con el mapa tapado, la pantalla tiene la VRAM entera, como el menú de
pausa y la pelea, y al cerrarse la repone la misma carga que vuelve del
menú. Eso alcanza para todo sin repartos:

* **El texto en BG2**, con la capa de texto de las pantallas
  (`tools/runtime/text_layer.s`): hasta 447 pares de tiles, una pantalla
  con todas sus celdas entintadas.
* **Las ventanas en BG1**, con el marco y el fondo del System a 8bpp, como
  las de los ítems (`screen_bank.s`): el conversor arma un tilemap por
  disposición de ventanas —son cuatro: la de los sujetos, la de texto, la
  de tabla y la de contadores— y la barra del cursor como hoy.
* **El arte en objetos**: los 512 tiles de objeto son del menú mientras
  está abierto, porque los personajes del mapa no se ven. Un retrato de
  96x120 son 180 tiles; uno de 128x160 cabría (320). Y los objetos tienen
  **ocho paletas** de 15 colores, que Adeleine reparte por bloque como lo
  hace para las imágenes chicas: un retrato de hasta 120 colores sin
  tocar la CGRAM de las ventanas ni del texto.
* Lo que se pierde respecto del original: **el mapa no se ve alrededor**.
  Es la decisión.

## 4. Las maquetas

Dibujadas con `rm2k-snes-screens` como biblioteca —la ventana y el cursor
del System de ABL (`Skin::window`, `Skin::cursor`), su fuente de ancho
variable con el espaciado de 1 (`Skin::draw_line`), y el menú de pausa de
`render::menu`—, a 256x224 y a 15 bits, lado a lado con la captura del
original:

1. **El menú de pausa** con "Console" entre Equipment y Save.
2. **La consola en Talan**: la cabecera con "< 1 / 4 >", el retrato a la
   izquierda en 96x120, el nombre y la clase, las pestañas con la barra, y
   abajo qué hay en la pestaña elegida.
3. **La guía de Talan**: `TalanTutorial2` como texto, partido al ancho de
   la ventana.
4. **Las auras rojas**: "Aura skills - Red" con "< 2 / 6 >", los ocho
   renglones de *nombre, absorbidas / necesarias*, el 99 como "Learned" en
   gris.
5. **Las almas de Sern**: un contador y el texto del mensaje original.

Los números de las maquetas son los de la partida de prueba, no del juego.
Los nombres de las técnicas van separados ("Candle Flame") y no pegados
como en la imagen ("CandleFlame"): lo decide el juego al transcribir.

## 5. Lo que costaría

**ROM**:

* **Texto y tablas**: las trece páginas son unos 4 a 6 KB de letras, y las
  seis tablas unos 700 bytes de nombres y topes —estimado sobre lo
  transcripto para las maquetas, no medido entero—. Más el tilemap de
  cada disposición de ventanas: 1.792 bytes crudos cada uno, que es
  propiedad de la pantalla —32x28 palabras—, y casi todo repetido.
* **Arte**, medido sobre los trece `NewMenu*` recortados a 96x120, en
  tiles de 8x8 deduplicados, con el tilemap y los colores, con LZ2:

      sin arte, o la cara del actor           0      la cara ya va en el
                                                     cartucho, por el menú
      13 retratos, 4bpp, 15 colores       48 KB      1.974 tiles
      13 retratos, 8bpp, 96 colores      100 KB      2.017 tiles

  Los tres carteles de "Picture Unavailable" no tendrían que ir: un sujeto
  sin arte usa la cara.
* **Código**: una pantalla nueva, que recorre las páginas, compone con la
  capa de texto y pinta la barra con lo de los ítems. Como orden, la
  pantalla de ítems entera son 618 bytes y el menú de pausa 641 (medido
  en el `.dbg` de `release`), así que **unos 2 KB** fuera del banco 0, con
  `jsl` como `screen_bank.s`. En el banco 0, lo que suma una opción al
  menú de pausa: pocos bytes, que hay que medir con `just espacio` porque
  ese banco es el más apretado.
* Contra **128 a 208 KB** de las 61 imágenes en la ROM (el estudio del
  2026-10-01), o el `.msu`.

**RAM**: el estado de la pantalla —menú, sujeto, pestaña, hoja, primer
renglón visible y a qué nivel está— son unos 8 bytes, que pueden ser los
`pick_*` prestados como hace la pantalla de ítems, porque no hay mensaje
abierto con el menú. La capa de texto usa la suya (`FAR_TEXT_LAYER`) y su
escenario en `ANIMB_BUF`, como cualquier pantalla.

**VRAM**: la entera, mientras está abierto, y nada en el mapa.

**Opcodes**: uno, `OP_MENU_OPEN`, para el común reemplazado. La opción del
menú de pausa no pide ninguno. `before` reusa `OP_CALL`.

**Qué se reusa del runtime**:

* el menú de pausa: `menu_screen`, su lista de opciones y la vuelta al mapa;
* la capa de texto de las pantallas: `scr_text`, `scr_number` y el número
  alineado a la derecha (`tl_right`), y la composición sólo de lo que cambió;
* las ventanas y la barra del cursor de `screen_bank.s`;
* los comunes compartidos, para `before`;
* y la carga de objetos de las imágenes chicas, para el arte.

**Qué se reusa del conversor**: el partido de cajas de los mensajes para
el texto (`boxes` y `refit` de `rm2k-snes-screens`), las ventanas como
tilemap (`borders.rs`), Adeleine y Voodoo para el arte, y `render` para la
golden de cada página, que es como se prueban las demás pantallas.

## Lo que no se decidió

* **El arte: cara o retrato.** La cara no cuesta nada y ya se ve en el menú
  de pausa; el retrato es lo único que el original tenía de lindo. Las
  maquetas usan el retrato.
* **El rótulo**: la columna del menú son nueve celdas, 72 pixeles
  (`MENU_OPT_COLS`). Con la fuente de ABL y su espaciado, "Console" mide
  39 y entra; "Portable Console" mide 88 y no. "Guide" también entra. El
  conversor ya avisa cuando un rótulo se corta.
* **Qué pasa con la opción sin sujetos**: si el grupo no tiene a nadie que
  el menú conozca, la opción podría salir gris, como Tech Skill hoy.

## Cómo se midió

* **Los comunes**: un recorrido de los `CallEvent` desde el 39 en
  `data/db/commonevents.json` de ABL, juntando los códigos de comando, los
  switches y variables que escriben y las imágenes que muestran.
* **Quién lee lo que escriben**: las condiciones de página de los mapas,
  los disparadores de los comunes, las condiciones de las tropas y, en
  todos los comandos de mapas, comunes y tropas, `ConditionalBranch` de
  switch y de variable, los operandos de `ControlVars` por variable, los
  índices por variable y `\V[n]`. Con todos los switches y variables
  puestos como blanco, el mismo recorrido encuentra 2.656 lugares en los
  mapas: el recorrido mira donde tiene que mirar.
* **El original**: RPG_RT de 2015 con Wine y Xvfb, sobre una copia del
  juego con el mapa 4 reescrito con Ditto (una página automática que arma
  el grupo, prende el 133, pone variables, da el ítem 81, lleva al mapa 7 y
  prende el 710), y `xdotool` para las teclas.
* **Las maquetas**: un programa descartable con `rm2k-snes-screens` como
  dependencia, con el volcado y el juego de ABL y su `[text]`.
* **El peso del arte**: cada `NewMenu*` recortado a (6, 6, 150, 188),
  reescalado con LANCZOS a 96x120, reducido con `quantize` de Pillow
  (MEDIANCUT, sin difuminado) a 15 y a 96 colores, en tiles de 8x8
  únicos, planares, con el tilemap y los colores, comprimido con el `lz2`
  instalado.
* **El código**: los `scope` con `size` del `abl.sfc.dbg` de `release`.
