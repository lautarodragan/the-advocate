---
name: "Label y JumpToLabel"
description: "Los dos comandos que no tienen caso en el compilador de eventos: los usan la portable console y 8 páginas de mapas"
type: feature
assignee: taro
---

Fase 1 de `docs/research/2026-10-01-el-sistema-de-imagenes.md` (Jilguero),
de taro el 2026-10-01: "me parece perfecto avanzar con Label, JumpToLabel".

## Qué hace RM2k

Confirmado en easyrpg, `CommandJumpToLabel` y el despacho de `Cmd::Label`
(`game_interpreter.cpp`):

- `Label` no hace nada.
- `JumpToLabel` recorre **la lista entera del frame desde arriba** y salta
  a la **primera** `Label` con ese número: no mira la indentación ni si está
  antes o después del salto. Una segunda con el mismo número no se alcanza
  nunca.
- Si no hay ninguna con ese número, **no hace nada** y sigue.
- La lista es la del frame: un `CallEvent` sólo ve sus propias etiquetas.
- No hay pila de bloques. Lo que hay es un sub-índice por indentación
  (`subcommand_path`): un `ElseBranch`, un `ShowChoiceOption` o un manejador
  de pelea corre o saltea su cuerpo según lo que dejó ahí **el último bloque
  de esa indentación**. Saltar **hacia afuera** de un bloque no cuesta nada.
  Saltar **hacia adentro** del cuerpo de arriba de una rama con `else` hace
  que el `else` corra o no según ese resto: normalmente no, pero una rama
  falsa sin `else` deja "else" puesto y entonces sí.
- `Loop` sin el parche Maniac no guarda estado; `EndLoop` busca su `Loop`
  hacia atrás por indentación. Acá `Loop` no compila, así que no importa.

## Qué se hizo

`tools/rm2k-snes/events/src/compile.rs`: `label_targets` resuelve cada
salto como easyrpg —la primera del número, o nada— y `page` emite un
`OP_GOTO`: hacia atrás con la posición ya conocida, hacia adelante abierto y
parchado al final de la página. Sin opcode nuevo.

**Lo que no compila**: un salto que cae adentro de un cuerpo que **no es el
último** de su bloque —el de arriba de una rama con `else`, una opción que no
es la última, un manejador que no es el último—, porque ahí lo que sigue
depende del sub-índice viejo de RM2k y acá es siempre un salto al final. Si
la etiqueta está en el último cuerpo —un `else`, la última opción, una rama
sin `else`— después viene el fin del bloque, que no hace nada en ninguno de
los dos, y compila. Los 13 saltos del común 39 que entran a un bloque caen
todos en un `else`.

**Lo que queda como riesgo**: un salto hacia atrás sin nada que espere en
el medio cuelga la ROM —`run_code` no corta por cantidad de comandos, como
easyrpg, que cede el cuadro—. Medido sobre el juego: todos los saltos hacia
atrás de los comunes 16, 21 y 39 tienen un `KeyInputProc` con espera
adentro de la vuelta, salvo el `JumpToLabel 15` del 39 que sólo da la vuelta
si ninguno de los switches 712 a 725 está prendido.

## Cuántas páginas compilan ahora

**Ninguna más.** Medido con `rm2k-snes-events scan` sobre todos los mapas
del juego, el binario de la base contra el nuevo: 5560 y 5560. Las 8 páginas
de mapa son la misma página en los mapas 332 a 339 (Room B a Room I, evento
3), y además de las etiquetas usan dos cosas que no compilan: la rama por la
dirección del héroe (`ConditionalBranch` tipo 6) y `ControlVars` desde la
posición de un evento (operando 6: X e Y del héroe y del evento 7). Con esas
dos neutralizadas compila con el compilador nuevo y no con el viejo, que
pedía además sacar `Label`/`JumpToLabel`. Los comunes de la consola (16, 21
y 39) tienen los bloqueos que dice el estudio de Jilguero.

## Pruebas

- Unitarias en `compile.rs`: adelante, atrás, afuera de dos ramas, la
  primera del número gana, una que no está no hace nada, adentro del último
  cuerpo (`else`, rama sin `else`, última opción) compila, adentro de uno
  que no es el último no, y dentro del mismo cuerpo.
- `rom/pruebas/casos/etiquetas.json` y `rpgmaker/test_etiquetas.py`: una
  vuelta hacia atrás de tres pasadas, un salto adelante por encima de un
  switch, uno a una etiqueta que no está, y uno adentro de un `else`. **El
  rojo**: con el compilador de la base, `just cartuchos` se niega —"the test
  page doesn't compile"—.
- El juego chico de las pruebas de Python (`tests/game/`) usaba una `Label`
  suelta como "comando que no compila", en el común 3 y en la página 2 del
  evento 9: ahora compila y cambiaba el hash del scan. Se reemplazó por un
  `Loop`, que tampoco compila, y los hashes de `python.json` quedan como
  estaban, sin regenerar.
- Sin el caso, `abl.sfc` sale igual a la base (`645b6b86…`); con el caso
  cambia (una página de prueba más) y no se mueve ninguna golden.

## Al mergear

- Instalar `events` en el global: `just -f tools/justfile install events`.
- Ninguna golden cambia, y no hay nada que jugar todavía: ninguna página del
  juego compila por esto solo. Lo que se puede mirar es el caso `etiquetas`,
  que corre en la tanda.
