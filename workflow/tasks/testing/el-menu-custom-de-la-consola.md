---
name: "El menú custom de la consola"
description: "La Portable Console de ABL como un menú custom del motor, descripto como datos, desde el menú de pausa y a pantalla completa, en vez de sus 61 imágenes: el estudio, y la implementación para cualquier juego con ABL como primer caso"
type: feature
assignee: taro
---

Nació el 2026-10-04 como "las imágenes de la consola, por el MSU-1": taro
había decidido que las más de 40 imágenes de la consola fueran sólo en el
`.msu`. Ese mismo día cambió de idea, antes de que hubiera nada
commiteado: "No tener la consola, creo, no es impedimento para jugar, pero
empeora algo la experiencia. […] creo que podemos convertir todo ese
sistema en algo custom pero genérico — una feature diseñada para armar
menús custom, que siga las mismas reglas que el resto del menú de
items/etc. Entonces no necesitaríamos ninguna imagen. O tal vez solo las
que muestran arte de los personajes". Es la idea de
`wishlist/un-menu-custom-propio.md`, sin el modo 5: hoy hay ancho variable
en baja.

Y dos decisiones suyas para el diseño: **es una opción más del menú de
pausa**, y **siempre a pantalla completa** ("este sistema no permite
renderizar sobre el mapa. Así solucionamos desafíos de VRAM etc.").

El encargo: un estudio con maquetas, **y frenar antes de tocar la ROM**,
porque es diseño y taro lo quiere ver. Lo hizo Lagartija, desde `main` en
`43b552f5`, con ABL en `5b29ba9`.

## Lo hecho

* **El estudio**: `docs/research/2026-10-04-el-menu-custom.md`. El
  inventario página por página, el diseño de la feature, lo que da la VRAM
  entera, y lo que costaría.
* **Las capturas del original y las maquetas**, en
  `/shared/capturas/2026-10-04-menu-custom/`, con su `LEEME.txt`: catorce
  capturas del original con Wine —la ventana de Talan, Arden, Sern y
  Emily, la guía de Talan, sus habilidades, cuatro tablas de auras, las
  almas de Sern y el menú de pausa— y cinco maquetas, cada una lado a lado
  con su original.
* No hay código: ni en la ROM, ni en el conversor, ni en ABL. Ninguna rama
  de ABL.

## Lo que contesta

* **Para avanzar no hace falta**: lo que la consola escribe no lo lee nadie
  más, y no elige nada —las auras no se eligen ahí—. **Para jugar bien,
  sí**: las guías y los contadores de absorción de Talan, las almas de
  Sern, las técnicas de Saldra y de Lerle.
* El diseño elegido: el motor dibuja y navega; el juego declara las
  páginas en un archivo propio que nombra el `rm2k-snes.toml`; el menú
  reemplaza al común 39, así el ítem 81 sigue abriéndolo; los comunes que
  calculan (48 y 49) corren antes de su página.

## Para taro

Mirar las cinco hojas `lado-*.png` y decidir:

* si el diseño va —sobre todo la navegación y que el motor la haga—;
* **el arte**: la cara de cada actor, que no cuesta nada, o los retratos,
  48 KB a 15 colores;
* **el rótulo**: "Console" entra en el menú de pausa, "Portable Console" no;
* si la opción aparece con el ítem 81 en el inventario, como se propone.

Con eso, la implementación es otra tarea: el conversor, la ROM, y en ABL la
transcripción de las trece páginas y seis tablas, con sus goldens.

## Lo que no se hizo

* Las maquetas están dibujadas con las funciones de `rm2k-snes-screens`,
  no capturadas de un cartucho: muestran cómo se vería con las ventanas y
  la fuente que hay, no lo que la ROM ya hace.
* La tanda no se corrió: no cambió nada que entre en una ROM.

# Lo que decidió taro

El 2026-10-04: "va el diseño, con retrato, \"Console\", y sólo con el ítem".
O sea: el diseño del estudio (`docs/research/2026-10-04-el-menu-custom.md`)
tal cual, con los retratos de los personajes y no sus caras, el rótulo
"Console" en el menú de pausa, y la opción visible sólo mientras el ítem 81
está en el inventario.

## Hecho (Aguará)

Worktree de las herramientas desde `60c1410c`, con `main` mergeado
(`afdaeab3`, el menú de la pelea de Cardón); ABL en el clon
`/extras/scratch/aguara/abl`, rama `menu-custom`, desde `a2b1d8a` con
`main` mergeado (`daf2d3b`).

### Qué quedó del diseño

Todo lo del estudio, tal cual: una pantalla del motor a pantalla completa,
una opción más del menú de pausa, el archivo propio que nombra `[menus]`,
sujetos con pestañas y la primera página cuya condición se cumple, páginas
de texto, de tabla con hojas y valores especiales, y de contadores, la
navegación del motor, `replaces_common` con `OP_MENU_OPEN` (el 0x45) y
`before` para los comunes 48 y 49. Retratos, "Console", y sólo con el ítem
81.

Lo que cambió o se agregó al hacerlo:

* **El formato** está en `custom_menu.rs` de `rm2k-snes-screens`, con un
  ejemplo arriba. Las condiciones son switch, variable `>=`, ítem y actor
  en el grupo. Una página puede tener `lines` además de `text`: renglones
  que van como están, con `center` y `color` —las listas y los títulos
  centrados de las imágenes—. Los contadores llevan un tope opcional, como
  las filas de tabla ("3 / 8" de Saldra).
* **`help` por pestaña**, abajo de los personajes: en ABL lleva lo que el
  original decía con un mensaje cuando no había página ("There is no skill
  screen available for RADIN at the current time."). No se inventó texto.
* **En una página, izquierda y derecha cambian de hoja** si es una tabla
  con varias, y si no, nada; el estudio decía que cambiaban de personaje.
  La cabecera de una página dice "Talan - Tutorials", y "< 2 / 6 >" sólo
  en las tablas.
* **Arriba y abajo corren una página de texto** que no entra (las once
  líneas de la ventana): la de Radin y la de habilidades de Emily.
* **`before` corre el común sin sus mensajes ni imágenes**, en un cuerpo
  compartido aparte. Si el común hace algo que espera, el conversor se
  niega (`before_commands` en `rm2k-snes-events`).
* **Un sujeto sin retrato** no tiene objetos; la cara del actor no se
  implementó, porque taro eligió retratos.
* Los nombres de las pestañas son los del original, "Skills" y
  "Tutorials", y no "Guide".

### Los textos

Todos se leían. Se transcribieron las diez guías, `TalanSkill1`,
`EmilySkill1`, `ArdenSkill1` y las seis tablas de auras (nombres pegados,
como en el juego, y lo que hace falta para aprender cada una). Las de
Saldra y Lerle, y las almas de Sern, son el texto de sus mensajes, con su
`\V`. Lo único que es nuestro son los rótulos de los contadores ("Enemy
souls", "FD Master skills", "Master Thespian skills") y los de las columnas
de la tabla ("Skill", "Absorbed"), que en las imágenes no estaban; y los
colores de las hojas, elegidos del System (rojo 1, azul 10, verde 18,
amarillo 4, negro como el gris 3, blanco 0).

### Lo que usa

* **ROM**: unos 61 KB de datos en `release` —el bloque del menú 8,2 KB,
  los trece retratos 44,7 KB en LZ2, tres disposiciones de ventanas de
  1,8 KB, 45 tiles de 8bpp—. Código, en `FAR2` ($C0): de 15.458 a 11.805
  bytes libres antes del merge con Cardón, unos 3,6 KB; banco 0, unos 110
  bytes (la tabla de filas y el despacho del menú de pausa). Medido con
  `just espacio release` en ABL; hoy da banco 0 2.522, $C0 10.415.
* **RAM**: `$7E3640`-`$7E367F`, entre la flecha del mensaje y `FAR_HP`.
* **VRAM**: la entera mientras está abierto. El texto de 0 a `SCENE_MAP`
  (447 pares, propios: la pelea bajó a 255), BG1 su tilemap en
  `SCENE_MAP` y sus tiles desde `$4000`, el retrato en objetos desde
  `$6000`. Al cerrarse, el mapa vuelve con `big_back_far`, más OBSEL y las
  paletas de objetos.
* **CGRAM**: las cuatro tintas de las pantallas de texto y hasta cuatro
  del menú (ABL usa tres), las ventanas desde la 128, el retrato en la
  paleta de objetos 7.
* **Opcodes**: `OP_MENU_OPEN` = 0x45; 0x44 queda reservado
  (`OP_RESERVED_44`, que termina la página como los otros reservados).
* `text_layer.s`: sólo se partió `tl_text` en dos, para que haya
  `tl_text_at`; no cambia ningún byte. `screen_bank.s`, nada.

### Pruebas

En ABL: `test_menu_custom_golden.py`, 24 goldens nuevas —la opción con y
sin el ítem, abrir desde el menú y desde el ítem y volver al menú y al
mapa, la navegación en redondo y por pestañas, las auras azules, rojas y
blancas con los contadores puestos a mano (el 99 como "Learned"), la guía
de Talan, Emily corrida, las almas de Sern, Saldra y Lerle con lo que
cuentan sus comunes, y volver al mismo personaje—. `test_consola_portatil.py`
pasó a mirar el común automático que abre el menú; el caso
`consola-portatil-escrita` se fue con la prueba del mensaje de Sern.
Ninguna golden existente cambió. `empujon` perdió su último cuadro (el
bloque de textos se corrió) y `test_items_vuelve` cierra la consola, que es
el ítem que usa.

En las herramientas: pruebas de `rm2k-snes-events` para el común
reemplazado y el `before`, y las de `rm2k-snes-mapdata` y
`rm2k-snes-screens` contra lo del Python sacan lo nuevo.

**Lo que no hay**: un `render` del menú custom en `rm2k-snes-screens`, que
es como se prueban con `_dibujo` las otras pantallas; las goldens son lo
único que lo mira, y una golden caza regresiones, no errores de
nacimiento. El menú de pausa con "Console" tampoco tiene `render`.

### Verificado

* **La tanda de ABL**, rama `menu-custom` con `main` de los dos repos
  mergeado y las herramientas de este worktree (`cartridge`, `events`,
  `screens`, `mapdata`, `convert` en local): **1078 en verde**, dos veces
  seguidas. Una tercera vuelta, en el medio, dio cinco rojas de
  "el Teleport no terminó de fundir": fue un `just espacio` mío que rearmó
  los cartuchos mientras corría; repetida sin tocar nada, verde.
* `abl.sfc`: `4e809540424fa129…`.
* **El rojo**: las pruebas nuevas con las herramientas globales, sin el
  cambio: las 8 de `test_menu_custom_golden.py` y
  `test_el_item_81_abre_el_menu_por_su_comun`.
* `just -f tools/justfile test`: 27. `cargo test` de `screens`, `events`,
  `mapdata`, `convert`, `cartridge` y `bytecode`.
* Lo que la tanda **no** cubre: un menú sin retratos o sin `replaces_common`
  (ABL no tiene), una condición de variable (el formato la tiene y ABL no
  la usa), y un `before` que llame a otro común.

### Lo que hay que mirar

Lado a lado con el original y la hoja de contacto en
`/shared/capturas/2026-10-04-consola/`. Las capturas del original son las
de Lagartija, del mismo día y el mismo Wine.

## Para taro

Jugar con la consola: abrirla desde el menú de pausa y desde el ítem,
recorrer, abrir las páginas, volver, cerrar el menú y caminar. Mirar el
retrato al cambiar de personaje (sube en unos ocho cuadros) y el negro
corto al entrar y salir de una página.

Al mergear, reinstalar `cartridge` —trae el runtime—, `events`, `screens`,
`mapdata` y `convert`; `bytecode` cambió y va adentro de `events` y de
`cartridge`. Y en ABL, la rama `menu-custom`.
