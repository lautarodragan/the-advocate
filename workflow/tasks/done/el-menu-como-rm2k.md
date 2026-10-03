---
name: "El menú como RM2k"
description: "La experiencia en el menú, el HP de los enemigos en la pelea y el color del número que cambia al equipar"
type: feature
assignee: Tero
---

# El menú como RM2k

Lo que pidió taro, el 2026-09-28:

> - el menú debería mostrar cuánta experiencia tiene cada héroe y en cuánta
>   pasa al siguiente nivel
> - las batallas no muestran el hp de los enemigos en el original. no sé si
>   hay alguna tecnica o item que te permita verlos, o si siempre es
>   imposible. no sé si quitar la funcionalidad completamente o dejarla
>   escondida
> - en la pantalla de equipar item, en el juego original muestra el numero
>   que subiría en otro color (amarillo, creo). puede que use rojo o algo si
>   bajaría — no lo sé

Las tres se miraron en easyrpg-player y en el original corriendo con Wine
(el RPG_RT de 2015), con una copia del juego cuyo mapa 4 arranca con Kersh y
Core en el grupo y los ítems de las pruebas en el inventario: así se llega al
menú sin jugar la intro. Las capturas están en
`/shared/capturas/2026-09-28-el-menu/`.

## 1. La experiencia en el menú — hecho

**Dónde la muestra RM2k**: sólo en el menú principal. El 2000 no tiene
pantalla de estado —eso es del 2003—, y la elección de actor
(`Window_ActorTarget`) no la muestra. En la fila de cada actor es la tercera
línea: `Ex 14522/ 16708`, el término `exp_short` en el color 1 y
`"%6d/%6d"` —la de ahora y la acumulada que pide el nivel que sigue,
`GetNextExp`— (`Window_Base::DrawActorExp`). En el tope, guiones: easyrpg
los pone sólo en la segunda mitad, y su comentario dice que el RPG_RT los
pone en las dos; seguimos al RPG_RT. El original, capturado, da Kersh
`14522/ 16708` y Core `6473/ 7750`, y la ROM da esos números.

**Cómo va**: en sprites, doce pixeles debajo de los HP y a los seis pixeles
de la fuente —el formato exacto de RM2k—. Es lo único de la pantalla fuera
de la grilla de celdas, y el porqué está en `MENU_EXP_X` (titulo.py): en 256
pixeles no caben las dos columnas de RM2k con letras de ocho, ni una cuarta
línea de celdas en los 56 pixeles de la fila. La rutina es
`rom/src/experiencia_en_el_menu.s`.

Lo que sigue siendo distinto, cosmético y ya declarado en el menú: sin el
título del actor ni los SP, y los HP debajo del nivel y no a su derecha.

## 2. El HP de los enemigos en la pelea — investigado, sin implementar

**RM2k no lo muestra nunca.** En el 2000 la elección de blanco es una lista
de nombres (`Scene_Battle_Rpg2k`), y no hay comando de evento que dibuje los
HP de un enemigo.

**El ABL tampoco tiene cómo verlo**, medido sobre `data/`:

- ningún `ControlVariables` de mapas, eventos comunes ni tropas lee los HP de
  un enemigo (el operando 8, "enemigo", no aparece ni una vez), así que ningún
  mensaje puede decirlos con `\V[]`;
- ningún mensaje de tropa ni de evento común los nombra: los que dicen "HP"
  son de ítems que se ganan o de curas del grupo;
- la única habilidad que "mira" al enemigo, `MindProbe` (144, de Manta), es de
  tipo switch y lo que prende es aprender sus técnicas, no ver sus HP;
- ningún ítem lo hace.

**Dónde lo dibuja la ROM**: en `ba_renglon` (`rom/src/batalla.s`), que escribe
el renglón de cada combatiente: el nombre, "HP" y el número, y la barra con el
máximo sólo si es del grupo —el bit 0 de `BA_CONMAX`—. La geometría es
`BA_HP_COL`/`BA_HP_NUM` de `pantallas.py`, y la decisión de mostrarlo está
escrita ahí mismo, arriba de `BA_ENEMIGO_FILA0`: *"se ven los HP de los
enemigos. RM2k no los muestra. Acá sí, porque lo que esta vuelta tiene que
dejar ver es justamente la mecánica"*.

**Propuesta**: esconderlo por defecto, como el original, con un flag de armado
para depurar, igual que `CON_MAPA_DE_DEBUG`:

- `CON_HP_DE_ENEMIGOS = False` en `tools/ensamblado/cartuchos.py`, que pasa
  `--hp-de-enemigos` al conversor; el conversor emite `BA_HP_ENEMIGOS = 0/1`
  junto a `BA_HP_NUM_DX`;
- en `ba_renglon`, detrás del nombre: `.if BA_HP_ENEMIGOS = 0` / `lda
  BA_CONMAX` / `and #$01` / `bne` al "HP" / `rts` / `.endif`. Son siete bytes
  en el banco de la pelea con el flag apagado y cero prendido; el banco 0 no
  se toca;
- `pantallas.py` lo mismo en la referencia de la pantalla de pelea, con el
  mismo flag;
- mueve todas las goldens donde se ve la lista de enemigos —las `batalla*`
  seguro; las demás las dice la tanda—, así que va en un commit con su
  porqué.

Cuesta poco, pero **no lo implementé**: hay otro agente en la pelea
(`batalla*.s`, `batalla.py`, `eventos.py`) y chocaríamos justo en esas
goldens. Queda para después de que eso se mergee.

## 3. Equipar: el valor que cambia, en color — hecho

`Window_EquipStatus::GetNewParameterColor`: el valor que quedaría va en el
color 0 si es igual, en el 2 si sube y en el 3 si baja. En el skin del ABL el
2 es un durazno (no amarillo) y el 3 el gris de "no se puede". La captura del
original lo confirma: con el Leather Jacket en vez del Trenchcoat, la defensa
`147> 55` en gris, la agilidad `82> 85` en durazno, el ataque y la mente en
blanco. Los colores de la ROM y los del original coinciden a 15 bits.

La fuente de la pantalla trae la variante 2 **sólo con cifras** (`ITEM_SUBE`
en titulo.py): la fuente entera en un color más no entraba, porque el banco
tiene un techo que la pelea impone —`ITEMS_TILES_MAX`—.

Lo que el original tiene y acá sigue faltando, cosmético: los términos de los
parámetros y de las ranuras en el color 1 (rojo), y la flecha `>` también
mientras se elige la ranura, sin el valor nuevo.

## Pruebas

- `menu`, `menu-2` cambian —la línea de la experiencia—; nueva `menu-grupo`
  (caso `menu-grupo`: Kersh, Core y Talan).
- `equipo-lista` cambia —el 95 del Bow, que baja, en gris—; nuevas
  `equipo-sube-baja` y `equipo-sube` (caso `equipo-colores`).
- `test_el_menu_muestra_guiones_en_el_nivel_tope`, el camino del tope.
- `render_menu` dibuja la experiencia, y las pruebas que comparan el menú
  después de subir o de pelear le pasan la de la partida.
- Los techos de la música se volvieron a medir (`just techos`): el cambio de
  la ROM corrió el pico de `dcbest` hasta recortar, como la prueba avisa que
  puede pasar con cualquier cambio.
- Verificado con `just cartuchos` y `just pruebas` sobre `main` mergeado: todo
  en verde.

## Qué tiene que mirar taro

- Abrir el menú con el grupo de la intro y con más de uno: la línea "Ex"
  debajo de los HP, que se lea y no se pegue con la fila de abajo.
- Ganar una pelea y volver a abrirlo: la experiencia sube; si sube de nivel,
  el segundo número cambia.
- Equipar algo que sube y algo que baja: durazno y gris.
- Cerrar el menú: el héroe y los NPC con sus colores de siempre (los sprites
  del menú le toman prestada una paleta al mapa).
