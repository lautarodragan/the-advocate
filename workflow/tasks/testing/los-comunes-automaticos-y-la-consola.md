---
name: "Los comunes automáticos, el CallEvent compartido y \\V[n]"
description: "Fases 4 y 5 del sistema de imágenes: lo que le falta al compilador y al intérprete para la portable console de ABL, todo genérico"
type: feature
assignee: taro
---

Fases 4 y 5 de `docs/research/2026-10-01-el-sistema-de-imagenes.md`
(Jilguero), de taro el 2026-10-02. La portable console no hace falta para
jugar, pero sus piezas sirven a los sistemas custom de muchos juegos. Lo que
falta: los eventos comunes automáticos (los paralelos no), un `CallEvent`
que comparta el cuerpo en vez de pegarlo (pegado, el común 39 son 140.193
comandos; compartido, unos 2.400), y `\V[n]` en los mensajes. `Label` y
`JumpToLabel` ya están (`testing/label-y-jumptolabel.md`, Pitogüé).

## Qué hace RM2k con los comunes automáticos

De easyrpg, `Game_Map::UpdateForegroundEvents`, `Game_CommonEvent` y
`Game_Interpreter`:

- **Cuándo**: cada vez que el intérprete de primer plano queda libre, el
  primer común automático —en orden de número— con su switch prendido se
  empuja a la pila. No hace falta que algo lo marque: lo mira en cada vuelta,
  así que mientras su switch siga prendido vuelve a correr, como una página
  automática del mapa. Uno sin switch corre siempre; acá no se toma —una ROM
  que corre uno para siempre no se juega— y el juego no tiene ninguno.
- **El orden contra las del mapa**: en la misma vuelta empuja primero el común
  y **después** el evento del mapa que esté esperando, que queda arriba y
  corre primero. O sea: la página del mapa, y en el mismo cuadro el común.
  Acá el común espera a que la cola del mapa se vacíe: es lo mismo con un
  evento esperando, y el común unos turnos después con varios. Declarado en
  `common_start`.
- **Con un mensaje abierto**: se empuja, pero `Game_Interpreter::Update`
  corta en `IsMessagePending` antes del primer comando. Acá `events_tick`
  sale antes de mirar nada con un mensaje abierto, así que tampoco arranca.
- **Al cambiar de mapa a la mitad**: el marco es una copia de la lista de
  comandos, así que sigue en el mapa nuevo. Acá el cuerpo vive en el
  cartucho y no se mueve.
- **"Este evento"** en un común es nadie: el marco de un común tiene
  `event_id` 0. Sin mapa, lo que lo nombra no compila.
- **El héroe**: `IsAnyEventStarting` mira también los comunes automáticos,
  así que con uno por arrancar el héroe no camina. Acá `common_waiting`, en
  `move_hero`.
- **`EndEventProcessing`** termina **sólo el marco** en que corre, no la pila:
  en un cuerpo compartido, escapar de una pelea con `escape_mode` 1 es un
  `OP_RETURN`.

## Qué se hizo

**Un cuerpo por común, en el cartucho, y `OP_CALL`/`OP_RETURN`** (`0x3F` y
`0x40`). `tools/rm2k-snes/events/src/commons.rs` decide antes de compilar
ninguna página qué comunes tienen cuerpo —los automáticos, los que llaman las
páginas de primer plano y lo que ésos llaman, si compilan sin mapa— y los
compila al final, cada uno una vez. `rm2k-snes-mapdata` emite las tablas, y
`tools/runtime/common_events.s` arranca los automáticos, empuja y saca
marcos.

**La pila de llamadas** es una sola, la del primer plano: tres niveles de
cinco bytes. La cadena más honda del juego son cuatro marcos —39, 21, 25 y
uno de los 23 a 31—, o sea tres niveles: entra justo. El conversor la emite
como `COMMON_DEPTH` y el ensamblado se niega si no entra. Una llamada con la
pila llena se saltea.

**Una página del mapa llama en vez de pegar** cuando corre en primer plano y
el cuerpo compilado con su mapa es byte por byte el de sin mapa; si no, pega
como siempre. Lo que se perdona es el refresco de variables, y por qué está
en `shares` y en `decisiones/call-event-a-un-cuerpo-compartido.md`. Las
paralelas pegan siempre: comparten las globales del primer plano.

**`CODE_CARRY` con la pila**: un cuerpo vive en el cartucho y no se mueve,
pero la página que lo llamó está en la WRAM; `code_carry_before` muda ahora
también los marcos de la pila.

**`\V[n]`**: el compilador lo cambia por una marca con la ranura de la
variable, y el bloque de textos lo lleva como el byte `$FF` y la ranura. El
`$FF` era el último par de letras: la tabla de pares baja de 161 a 160. El
compositor (`msg_letter`) escribe el número al abrir la caja, con el menos si
es negativo, y le suma al largo del renglón lo que mide menos uno —el
conversor lo contó como una letra—; si se pasa de la ventana, el tope de
columnas lo corta en el borde. Sólo la forma simple, `\V[` dígitos `]`,
mayúscula o minúscula; la anidada sigue sin compilar.

## Lo que se encontró en el camino

- **La RAM que me tocó, `$2560` a `$256F`, está adentro de
  `FAR_PAIR_LIST`**: son `PARALLEL_MAX` (48) entradas de ocho bytes desde
  `$2400`, hasta `$257F`, y la persecución del auto tiene cuarenta paralelas.
  Usé `$6110` a `$6127`, detrás de `MAP_SONG` (un byte) y antes de `FAR_EXP`;
  verificado con grep sobre `tools/runtime/` que nada más cae ahí. **Lo de
  Aguilucho, si le tocó `$2570`, tiene el mismo problema.**
- **Los opcodes `0x39` a `0x3E` no existen en `main`**, y la tabla del
  despacho no admite huecos: los declaré como `OP_RESERVED_39` a `_3E`, que
  terminan la página. El que traiga el de verdad reemplaza su entrada; los de
  Aguilucho son `0x3D` y `0x3E`.
- **La WRAM no arranca en cero**, y el núcleo de la tanda la llena de `$55`:
  la primera versión no ponía la pila en cero al arrancar una página del
  mapa, y la profundidad basura salteaba todas las llamadas. Lo cobraron
  cuatro pruebas —el común 35 después de la pelea dejaba el 498 prendido y
  el héroe trabado—; ahora `start_waiting` y `common_start` la ponen en cero.
- **El signo de `\V`**: un `ldx` entre la lectura y el `bpl` le pisaba la N,
  y -1234 salía como 64302. Lo cobró `test_variable_en_texto.py`.
- **El efecto con otra muestra en un mapa**: `shares` compilaba el cuerpo
  "sin mapa" con el paquete del mapa puesto, y un efecto que en ese mapa
  suena con otra muestra salía igual en los dos. Lo cobró la prueba de
  `compile.rs`; ahora se compila sin paquete, como el del cartucho.

## Cuántas páginas compilan

- **Del juego, por página**: las mismas que antes, 5560 —`rm2k-snes-events
  scan` sobre todos los mapas, el binario global contra el nuevo—. Ninguna
  página de mapa usa `\V`, y lo compartido no cambia qué compila.
- **Los comunes**: en `release` hay 25 cuerpos, 8.176 bytes. Corren los
  automáticos 7 (`AbsorbAuraAbilities`), 11 (el menú viejo, que nadie
  prende), **39 (la consola)**, 43 (la cinta de Emily) y 50 (`RadinUses`).
  No compilan: el 16 (`DisplayNameMenu`, del menú viejo), y el 42 y el 44,
  los menús de Radin y de Sern, que mandan al héroe una ruta que le cambia
  el gráfico —el comando 34 necesita el banco de sprites de un mapa, y un
  cuerpo no tiene mapa—. Los de la consola compilan todos: 39, 21, 25, 23
  a 31, 40, 48 y 49 (el 22 compila a nada: son sólo imágenes).
- **Las llamadas de las páginas**: 32 `OP_CALL` en 24 mapas de `release`,
  casi todas al común 35 desde `AfterBattleMint`. El bytecode de los mapas
  pasó de 136,4 KB crudos (89,1 en LZ2) a 89,4 (46,8); sin ninguna llamada
  serían 81,5.

## La consola

**Anda**, sin imágenes: el ítem 81 desde el menú prende el 710 y el común
39 corre; las flechas recorren personajes y rótulos; A sobre Skills de Sern
abre su mensaje con las almas (`\V[0173]`); B la cierra; el héroe no camina
mientras está abierta. **No se ve ninguna imagen**: las de la consola no las
lleva ningún mapa, y las grandes —las páginas de texto, la tabla de auras,
la ventana de 302x202 al 50%— son de Aguilucho. Faltan todas: 17
(`NewMenu<nombre>`, `<nombre>Skill1`, `<nombre>Tutorial1`), 18
(`SkillSelect`, `TutorialSelect`), 19 (`ArrowTest`), y las del 21 y del 23
a 31 (`Aura<color>Menu`, `Aura0` a `Aura24`). Además los efectos de un común
automático (`Decision1`, `Cansel1`, `Failure1`) suenan sólo si el paquete
del mapa ya los lleva: un cuerpo sin mapa no anota nada en ninguno.

## Pruebas, y su rojo

- `rpgmaker/test_consola_portatil.py` (cuatro): el ítem 81 corre el común,
  las flechas, el héroe quieto y el mensaje de Sern contra el mismo escrito
  con 42. **Rojo**: con `common_start` devolviendo cero, las cuatro.
- `rpgmaker/test_variable_en_texto.py`: tres `\V` —negativo, cero, dos en un
  renglón, con ceros adelante y en minúscula— contra el mismo mensaje escrito
  a mano. **Rojo**: con el compilador de la base, `just cartuchos` se niega
  ("a test page's text box does not compile"); y con el signo mal, 776
  pixeles.
- `rpgmaker/test_llamada_compartida.py` (dos): una página llama al común
  43, se pide un salto con la elección abierta, y la página sigue después.
  Las dos variantes: la página en su mapa y ya acarreada. **Rojo**: sin mirar
  los marcos de la pila en `code_carry_before`, las dos. Ningún común que hoy
  se comparta salta de mapa, así que **es el único camino que lo ejecuta**.
- Unitarias en `compile.rs` y `messages.rs`: los cuerpos y sus índices, el
  automático que no compila, la pelea que termina sólo su marco, la
  profundidad de un lazo, una página que llama o pega según el mapa, `\V`
  como ranura y lo que no compila, y que un par no salte una variable.
- `test_compositor.py` pone en cero también los dígitos pendientes, que es lo
  otro que el arranque del renglón deja puesto.
- `empujon.json`: el bloque de textos se movió —un par menos y los textos de
  los comunes—, y el cuadro de `texto-cruza` quedó del otro lado del borde.
  Le saqué los dos cuadros de relleno del final, `Z1` y `Z2`.
- `rm2k-snes-mapdata/tests/python.rs`: las tablas de los comunes se sacan
  antes del hash, como la de pares; los hashes no cambiaron.

Las dos tandas en verde: `just pruebas` da 988 (981 + 7) y `just -f
tools/justfile test` 39. `cargo test -p rm2k-snes-events -p
rm2k-snes-mapdata` en verde.

## Goldens

**Ninguna se movió.** Las tres ROMs cambian —tablas nuevas, el par de menos,
los comunes—, pero ninguna golden.

## Espacio, en `release`

Contra la base (`57ce2e2a…`), con `just espacio`: de 62 bancos de datos a
61; el banco 0 de 1.340 a 1.275 bytes libres; el banco 1 de 2.000 a 1.498;
el bloque de textos de 112.697 a 116.014 bytes. `NO_CACHE=1 just
cartuchos` da las mismas tres ROMs que con caché.

## Lo que falta

- **Las imágenes de la consola**: Aguilucho.
- **Los menús de Radin y de Sern (42, 44)**: un cuerpo compartido no puede
  cambiar el gráfico de una ruta, porque eso es del banco de sprites de cada
  mapa. Serviría si el gráfico fuera uno de los `associations`, que todos los
  mapas reservan en el mismo lugar; no se miró si lo es.
- **Los comunes paralelos**: no se hicieron. Lo que harían falta: un
  intérprete paralelo por común —estado como el de `FAR_PAIR_STATE`, que hoy
  es por evento del mapa— corriendo en `parallel_tick` en cualquier mapa, y
  decidir qué pasa con el 2, `DisableSaving`, que no tiene switch y correría
  siempre. Los de equipo ya corren a su manera (`equipment_commons`).
- **Las llamadas de las paralelas** siguen pegando: necesitarían una pila por
  intérprete.
- **Los efectos de un común automático** suenan sólo donde el paquete del
  mapa los trae.

## Al mergear

- **Instalar** `events`, `mapdata` y `cartridge`: `just -f tools/justfile
  install events mapdata cartridge`. Y `install-scripts` no hace falta: no
  hay scripts nuevos ni renombrados.
- Los opcodes reservados `0x39` a `0x3E`: los de Aguilucho reemplazan
  `OP_RESERVED_3D` y `_3E`, y `op_reserved_3d`/`_3e` de `interpreter.s` se
  van con ellos.
- La RAM: `$6110` a `$6127` es mía, no `$2560`.
- `test_musica_techos.py` pasó; no corrí `just techos`.
- Para jugar: los comunes automáticos 7, 43 y 50 ahora corren en el juego
  —las auras de Talan, la cinta de Emily y lo que Radin repara—, y la
  consola se abre con el ítem 81.
