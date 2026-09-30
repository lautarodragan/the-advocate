---
name: "A quién equipar, desde el menú"
description: "Elegir a quién equipar sobre el menú principal, como Scene_Menu, y no en la pantalla de la elección de actor con la mitad izquierda vacía"
type: feature
assignee: taro
---

Apareció el 2026-09-28, mirando la golden `equipo-a-quien` de la elección de
actor (`testing/la-eleccion-de-actor-como-el-original.md`, Ñandú): elegir a
quién equipar usa la pantalla de la elección de actor sin las ventanas del
ítem, y la mitad izquierda queda negra. Antes de ese cambio ya estaba así,
sobre negro y con el ">".

En RM2k no hay una pantalla aparte: `Scene_Menu`, con Equipment, pasa el
cursor al panel del grupo del mismo menú —los comandos siguen a la
izquierda— y A abre `Scene_Equip` con ese actor. Hay que confirmarlo en
easyrpg (`scene_menu.cpp`) y con el RPG_RT con Wine.

taro todavía no la pidió: la anotó Hornero al proponerla.

## Qué hace el original

**El RPG_RT de 2015 con Wine**, desde la partida nueva —después de la intro
el grupo es Kersh, Core y Manta—. Las capturas, a 640x480, en
`/extras/capturas/2026-09-30-a-quien-equipar-wine/` y copiadas a
`/shared/capturas/2026-09-30-a-quien-equipar/original/`:

- `05-equipo-elegir`: A sobre Equipment deja **el mismo menú**, con la barra
  roja quieta sobre "Equipment" y otra sobre **el texto del primer actor** —las
  tres líneas, nombre, nivel y Ex, sin la cara—. No hay pantalla aparte.
- `06-segundo`: abajo la pasa a Core.
- `07-equip-core`: A abre `Scene_Equip` de Core.
- `08-vuelve`: B desde el equipo vuelve al menú **con el cursor en los
  comandos**, sobre Equipment, y ninguna barra en el grupo: no a la elección.
- `09-arriba-da-vuelta`: arriba desde el primero va al último (Manta).
- `10-b-vuelve`: B en la elección vuelve a los comandos, sobre Equipment.
- `11-tech-elegir` a `13-tech-vuelve`: **Tech Skill hace lo mismo**: la barra
  sobre el grupo, A abre la lista de técnicas de ese actor (`Scene_Skill`),
  y B vuelve a los comandos.

**easyrpg** (`scene_menu.cpp`) dice lo mismo, y coincide con el RPG_RT en
todo lo que se miró: `UpdateCommand`, con Skill, Equipment, Status o Row,
desactiva los comandos, activa `menustatus_window` y le pone el índice en
**0** —siempre el primero, no el último elegido—; `UpdateActorSelection`, con
B, vuelve a los comandos con el índice en -1 —sin barra—; con A empuja la
escena con `menustatus_window->GetIndex()` y, al volver, los comandos quedan
activos. El cursor de `Window_MenuStatus` es `{48 + 4, index * 58, 168, 48}`:
arranca después de la cara. Una ventana inactiva deja de animar el cursor
(`Window::Update` sólo avanza `cursor_frame` si está activa), pero lo sigue
dibujando: por eso la barra de "Equipment" queda.

## Habilidades

En RM2k elige actor igual que Equipment —easyrpg y el RPG_RT—, y con A
suena el error si el actor no puede actuar (`CanAct`). **En la ROM "Tech
Skill" va en gris y A no hace nada** (`MENU_DONE` en el layout de
`rm2k-snes-screens`, `menu_done` en la ROM): no hay pantalla de habilidades
fuera de la pelea, así que no hay una elección aparte que arreglar. Cuando
se haga la pantalla, la elección es la misma que ésta.

## Qué se hizo

- **La elección, en el menú mismo** (`menu_choose`, en `actor_choice.s`): A
  sobre Equipment deja el menú como está, con el ">" en la orden, y pone la
  barra roja sobre la fila del primero del grupo; arriba y abajo dan la
  vuelta; B la borra y vuelve a las órdenes sin rearmar la pantalla; A abre
  el equipo del de la barra, y al volver el menú se rearma con el cursor en
  Equipment, como antes. Vive en el banco lejano porque en el banco 0 no
  entraba: se pasaba por 86 bytes. Llama a `wait_vblank` y `read_pad` por
  los puentes de la pelea (`ba_t_vblank`, `ba_t_pad`), como el equipo.
- **La barra** es la de la elección de actor, con sus tiles y sus colores,
  pero sobre nada: el menú no tiene ventanas, así que afuera de la barra BG1
  está vacío y borrarla es escribir ceros. Es `MENU_BAR` en el layout de
  `rm2k-snes-screens`: de x = 148 al borde, como la de la elección, y de
  y = 2 a y = 53 de la fila —dos pixeles adentro arriba y abajo—, porque la
  fila del menú tiene una cuarta línea, la experiencia, y RM2k tapa las
  tres suyas. Así las celdas de abajo son las de arriba espejadas: **en el
  juego no cuesta ni un tile** (siguen siendo 60 de 64) ni un color; se
  guarda sólo su rectángulo, 7 x 14 celdas, `menu_bar_cells`.
- **BG1 prendido en el menú**, vacío, con la base de la elección
  (`TARGET_VRAM`): `menu_bar_upload` sube los tiles, los colores y un
  tilemap en cero al armar el menú, con la pantalla apagada.
- **La experiencia pasa a la paleta 1 de los sprites** (colores 144..159):
  la 0, 128..143, es la de la barra —ya lo era en la elección de actor, que
  no tiene sprites—. `menu_exp_close` repone ahora 128..159 al cerrar.
- **La referencia**: `render::menu` con `choosing`, y `pantallas.menu(...,
  eligiendo=k)` y `menu.comparar(..., eligiendo=k)` del lado de las pruebas.
- **Lo que quedó muerto se fue**, en su propio commit: la elección de actor
  sin ítem —las guardas de `pick_cancel`, las celdas borradas de la
  izquierda, la capa sin ítem de `rm2k-snes-screens` y sus campos
  `erase_*`—. La prosa que la nombraba, en otro, con las ROMs byte por byte
  iguales.
- **No se usó RAM nueva**: durante la elección, la fila va en `title_sel`,
  y al salir vuelve a ser la orden.

## Qué no entra

- **La barra en la orden**: en RM2k la orden queda marcada con la barra
  roja, quieta. La ROM marca las órdenes con un ">" desde antes, y sigue así.
- **El latido de la barra**: la de RM2k late mientras está activa
  (`cursor_frame`); la de la ROM es fija, como en todas las pantallas.
- **Habilidades**: ver arriba; en la ROM no hace nada todavía.

## Pruebas

- Nueva `test_a_quien_equipar_se_elige_en_el_menu`
  (`test_menu_equipo_dibujo.py`): el menú con la barra en el primero, en el
  segundo, dando la vuelta desde el primero, después de B y otra vez en el
  primero, contra `render::menu`; que A abra el equipo del segundo
  (`comp_char`) y se vea como `pantallas.equipo`; y que el equipo vuelva al
  menú con el cursor en Equipment y sin barra. **Antes del cambio de la ROM
  dio rojo** en la primera comparación, con 6.661 pixeles distintos.
- `rm2k-snes-screens`: un caso nuevo del menú con la barra, y el hash de la
  conversión de su juego de prueba cambia: la barra del menú le suma tres
  tiles —41 a 44— y la capa sin ítem se fue.
- **Cambia una sola golden, `equipo-a-quien`**, en su commit. El antes, el
  después y el original lado a lado, y las capturas del RPG_RT, en
  `/shared/capturas/2026-09-30-a-quien-equipar/`. **El merge espera el
  visto bueno de taro.** Las escenas de `test_menu_golden.py` son una
  captura por caso, así que no hay más cuadros que cambien: la tanda entera
  corrió y ésa fue la única en rojo.
- `just pruebas`, `just -f tools/justfile test` y `cargo test -p
  rm2k-snes-screens`, en verde sobre la rama con `main` mergeado
  (`d0979c06`): **894** y **49**. `test_musica_techos.py` y `test_cores.py`
  pasaron.

## Espacio

`just espacio`, `release`: contra `main` en `3afc8199`, el banco 0 pasó de
50 a 51 bytes libres, el banco 1 de 3.126 a 2.769, y los huecos de datos de
8.799 a 8.603 (los 196 de `menu_bar_cells`). Con `main` en `d0979c06`
mergeado, el banco 0 queda en **14** —`main` solo tenía 13— y el banco 1 en
4.697.

## Al mergear

Instalar en el global `screens` y `cartridge` —`just -f tools/justfile
install screens cartridge`—, además de lo que pide el merge de Yarará
(`events battle`). Ningún `.py` se renombró ni se agregó.

## Qué tiene que mirar taro

- Menú, Equipment: el menú queda como está, con el ">" en Equipment, y la
  barra roja sobre Kersh —las cuatro líneas, sin la cara—. Abajo y arriba la
  mueven y dan la vuelta; B vuelve a las órdenes.
- A sobre el segundo abre su equipo; B desde el equipo vuelve al menú con
  el cursor en Equipment y sin barra.
- La línea "Ex" se sigue viendo, también debajo de la barra, y al cerrar el
  menú el héroe y los NPC tienen sus colores de siempre: la experiencia se
  mudó a la paleta 1 de los sprites y el cierre repone las dos.
- Ítems, una medicina: la elección de actor, igual que antes.
