---
name: "Las flechas se repiten en el menú"
description: "Sostener una flecha en el menú mueve la selección sola después de una espera, como Input::IsRepeated de RM2k"
type: feature
assignee: taro
---

De taro, el 2026-09-28: "al mantener presionada una flecha direccional
dentro del menú, luego de ~1s, debería empezar a mover la selección
continuamente en esa dirección, a un ritmo de ~10 items por segundo
(revisar el código de easy rpg para confirmar)".

## Qué hace el original

- **easyrpg** (`src/input.cpp`): `start_repeat_time = 23` y `repeat_time =
  4`, en cuadros, con `repeated = press_time == 1 || (press_time >= 23 &&
  press_time % 4 == 0)`, y `press_time` vale 1 en el cuadro del flanco. O sea
  que dispara en el cuadro 0, en el 23, en el 27, en el 31…: **0,38 s de
  espera y 15 por segundo**, no el segundo y los diez que recordaba taro.
- **El RPG_RT, medido**: el de 2015 con Wine, grabando con `ffmpeg -f
  x11grab` a 60 cuadros la zona del cursor de la pantalla de título mientras
  `xdotool` sostenía abajo 2,5 s, y buscando la fila con la barra roja cuadro
  por cuadro. Los cambios caen a **23 cuadros del primero y después cada 4,
  sin una sola excepción** en treinta y tantas repeticiones, y dan la vuelta
  de la última a la primera. Coincide con easyrpg. El de 2000, que es el que
  usó el autor, no se midió (necesita la `Harmony.dll`).
- **Quién repite**: en easyrpg, todo lo que es `Window_Selectable` mueve el
  cursor con `IsRepeated` —el menú, ítems, equipo, el título, las elecciones
  de un mensaje, End Game—, y también `Window_Shop`, `Window_ShopNumber`,
  `Window_BattleStatus` y `Scene_File`. A, B y X no: son `IsTriggered`.
- **Dar la vuelta repitiendo**: `Window_Selectable` distingue toque y
  repetición, pero con `endless_scrolling = true` —el valor por omisión; sólo
  lo apaga un comando de Maniacs— la repetición da la vuelta igual. El título
  del RPG_RT también la da, medido. **`Scene_File` no**: ahí sólo el toque da
  la vuelta, y la repetición se queda en la punta.
- **La entrada de teclas** (`KeyInputProc`) con espera es `IsTriggered`
  (`game_interpreter.cpp:3222`): no repite.

## Qué difería en la ROM

Todas las pantallas miraban sólo el flanco: sostener una flecha movía el
cursor una vez.

## Qué se hizo

- **Un solo lugar, `read_pad`** (`rom/src/control.s`), que llama a
  `flechas_repetir` en el banco 1. Todas las pantallas calculan el flanco
  igual —`pad` contra `pad_ant`—, así que en el cuadro de la repetición se
  borran de `pad_ant` las flechas sostenidas y cada una lo ve como un toque
  nuevo. **Ninguna pantalla se tocó** para tener la repetición: la llevan el
  menú, ítems, equipo, ranuras, título, las elecciones de un mensaje, la
  tienda, la pelea y End Game. La elección de actor que está rehaciendo Ñandú
  también la va a tener si mira el flanco igual.
- Un contador, `flechas_cuadros`, que se pone en cero con una flecha nueva o
  con ninguna, y al llegar a 23 dispara y vuelve a 19. Nunca pasa de 23.
- `flechas_repetidas` dice qué bits se falsificaron este cuadro, para los dos
  lugares que tienen que distinguir:
  - `tecla_valor` (`menu.s`, la entrada de teclas con espera) los saca, con un
    `ora` y un `eor` que no tocan el acarreo del que depende.
  - `ranuras.s` no da la vuelta si la flecha viene de la repetición.
- Las dos variables en `ram_baja.s`, al final, y en cero en `arranque`.

## Qué no entra

- **Un contador por flecha**, como RM2k: es uno para las cuatro. Ver
  `workflow/divergencias/un-solo-contador-para-las-cuatro-flechas.md`.
- **Las demás diferencias toque/repetición de easyrpg** no se miraron una por
  una: `Window_Selectable` las tiene pero da la vuelta igual, y
  `Window_BattleStatus` y la tienda repiten sin distinguir. Si alguna otra
  pantalla del RPG_RT frena en la punta como las ranuras, no se sabe.
- `Scene_File` se tomó de easyrpg: no se midió en el RPG_RT.

## Pruebas

- `pruebas/rpgmaker/test_repeticion.py`, cuadro de hardware por cuadro:
  - en el menú de pausa, abajo y arriba sostenidos mueven en el cuadro del
    flanco, a los 23 y cada 4;
  - soltar corta, y volver a apretar espera los 23 enteros;
  - B sostenido no repite (el menú no se vuelve a abrir);
  - en las ranuras, abajo sostenido llega a la cuarta y se queda; un toque
    da la vuelta.
- `test_tecla.py::test_sostener_una_direccion_no_contesta` ya cubría la
  entrada de teclas: da **rojo** sin la guarda de `tecla_valor` (la variable
  queda en 2). Las de `test_repeticion.py` del menú dan rojo sin el `jsl`, y
  la de ranuras sin su guarda: las tres cosas verificadas quitándolas.
- **Lo que ninguna prueba ejecuta**: la repetición en el título, en las
  elecciones de un mensaje, en ítems, equipo, tienda, pelea y End Game. Es el
  mismo mecanismo y ninguna pantalla cambió, pero no hay caso que sostenga
  una flecha ahí.
- Ninguna golden cambió, y `test_musica_techos.py` sigue en verde: no hizo
  falta `just techos`.
- `just cartuchos` y `just pruebas` sobre la rama, con `main` adentro
  (`535b19fd`, sin commits nuevos): todo en verde menos
  `test_indice.py`, que pedía la prueba nueva en `pruebas/README.md`; se
  sumó y se corrió esa sola, en verde.

## Espacio

`just espacio`, antes y después, en `release` y `test-special`: el banco 0
cuesta 30 bytes (el `jsl`, la guarda de `tecla_valor`, las dos de las
ranuras y los dos `stz` del arranque); el resto, 48 bytes, va en el banco 1;
y 2 de BSS.

## Qué tiene que mirar taro

Jugando, en el menú de pausa, en ítems y en una elección de un mensaje:
sostener abajo, que a los 0,38 s baje solo y a quince por segundo. Si se
siente rápido, es lo que hace el original; los dos números son
`REPETIR_ESPERA` y `REPETIR_CADA` en `control.s`. Y en la pantalla de
guardar, que sostener abajo se quede en la última.
