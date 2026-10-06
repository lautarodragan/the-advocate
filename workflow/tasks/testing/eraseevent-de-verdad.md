---
name: "EraseEvent de verdad"
description: "EraseEvent de verdad en las páginas de mapa: el evento que lo corre desaparece hasta que se recarga el mapa, y una paralela se corta ahí; en un común no hace nada"
type: feature
agents: [Aguará, Hurón]
assignee: taro
---

Del estudio de Aguará, `docs/research/2026-10-05-los-comandos-que-faltan.md`; lo midió `rm2k-snes-events culprits`. taro, el 2026-10-05: dejarlas en todo, sin lanzar todavía. Es lo primero que recomienda: uno chico y uno mediano.

2026-10-06, Hornero: en Desert Nightmare `EraseEvent` es lo que más páginas
deja afuera solo —127 de las 157 que lo usan, medido con `culprits
--every-map`—, y es el sospechoso de que su intro se congele: una página
automática que se borra sola, si no compila, no deja seguir la escena. El
Dorado tiene 3. Se hace entero: borrar el evento hasta que se recargue el
mapa, en mapas y en la cantera de ABL; el del común sigue sin hacer nada.
taro: "vamos con esos dos en paralelo", con Sonnet.

## Hurón, 2026-10-06

**Qué hay**: `OP_ERASE_EVENT = 0x49` (un operando: el evento, su índice más
uno, como `OP_ROUTE`). Compila en la página de un evento de un mapa; en un
común —sin mapa, o pegado en la página que lo llama— y después de un salto a
otro mapa sigue sin hacer nada, como en RM2k. Un salto **al mismo mapa** no
cuenta como salto: es el de la cantera, y ahí borra de verdad. Un `MapEvents`
sin dueño —una página de nadie— se corta, como cualquier "este evento" sin
evento.

**En la ROM**: `FLAG_ERASED` en `ev_flags`, sin RAM nueva. Lo prende
`op_erase_event` (`interpreter_movement.s`) y pide un refresco; lo mira
`conditions_ok` —ninguna página de un evento borrado se cumple: no arranca,
no se elige, no es de la lista de paralelas— y `apply_pages`, que le esconde
la fila y le suelta la ruta aunque el evento no tenga páginas que el sorteo
mire. Sólo `clear_waits`, que corre en cada carga de mapa, lo limpia: por
eso un salto al mismo mapa no lo deshace. **Una paralela que lo corre se
corta ahí** —`pair_ev`—, como `CommandEraseEvent` con `main_flag` en falso;
una de primer plano sigue hasta el final, como allá. Lo que no se modela, en
`divergencias/lo-que-borrar-un-evento-no-modela.md`.

**Medido** (`culprits --every-map`): Desert Nightmare, `EraseEvent` era el
primero —157 páginas, 127 solas— y ya no está; El Dorado, tres solas, ya no
está; ABL, el del 150 y el del común 36 compilan. Las 157 de Desert son
paralelas sin gráfico.

**Lo de la intro de Desert Nightmare: no era esto.** La intro termina igual
antes y después: en negro en la calle (mapa 9), porque su última página hace
un `Teleport` al mapa 2, que el relevamiento dejó afuera (`[maps] excluded`).
Lo que sí cambia es la escena del WC (mapa 7): su evento 4 es una paralela
que muestra la imagen `Lichteffekt_Tankstelle_WC` y se borra, y antes no
compilaba. Ahora la imagen —una máscara oscura al 35% en RM2k— sale opaca y
tapa el cuarto durante ~480 cuadros: parece que se cuelga, pero sigue. Es la
transparencia de las imágenes, no el borrado; está en
`/shared/capturas/2026-10-06-eraseevent/`.

**Pruebas**: tres en el crate (`erasing_the_event_*`, una mostrada en rojo
antes del arreglo) y `pruebas/rpgmaker/test_borrar_evento_de_verdad.py` en
ABL, con dos casos nuevos que van en `test-special` —en `release` el mapa de
arranque es la apertura y no deja correr la página—. **No cubre** que el
evento se deje de dibujar, que deje de bloquear ni que la paralela se corte:
el evento de prueba no tiene gráfico ni es paralelo. Eso se miró jugando
Desert Nightmare, no lo cobra ninguna prueba.

**Tanda de ABL con las herramientas del cambio**: 1150 verdes (los 1147 de
antes y los tres nuevos), ninguna golden se movió. `abl.sfc` cambia
(`602b60e0…` a `8bb36b99…`) por tres cosas, las tres esperadas: el runtime,
el mapa 150 y el común 36, que ahora compilan.

**Al mergear**: reinstalar `events cartridge convert rm2k-snes-audio` (el
opcode nuevo cambia lo que compila `bytecode`), y en ABL traer la rama
`huron/eraseevent`.
