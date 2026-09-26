---
name: "Autofire de A con X"
description: "Sostener X aprieta y suelta A solo, para pasar textos y repetir elecciones sin machacar el botón"
type: feature
---

Idea de taro, el 2026-09-25: RM2k usa dos botones y el control de la SNES
tiene muchos más, así que uno que sobra puede hacer de autofire, como en los
emuladores. **Sólo A, con X.** Con B se descartó: en el mapa B abre el menú
de pausa y adentro lo cierra, así que sostenerlo lo abriría y cerraría sin
parar.

**Dónde:** todo el control pasa por `read_pad` (`rom/src/control.s`), que deja
`pad` (JOY1H) y `pad_a` una vez por cuadro; nadie más lee `JOY1H`/`JOY1L`, y X
no lo mira nadie. Con X apretado, `pad_a` se prende y se apaga cada **cuatro
cuadros** —unos 7,5 toques por segundo; taro pidió entre 3 y 4 para
arrancar—, como una constante con nombre para ajustarla jugando. Como el juego
mira el flanco de A (RM2k cierra el mensaje con `Input::IsTriggered`), cada
vuelta a "apretado" es un toque nuevo.

**Cuidar:** que A apretado de verdad gane sobre el autofire; que soltar X no
deje A trabado en apretado ni dispare un toque de más; que el contador no
viva en memoria sin inicializar (`test_cores.py`).

**Es una divergencia de RM2k, aunque sólo suma**: va anotada en
`workflow/divergencias/` para que nadie la tome por un error.

**Pruebas:** ninguna golden debería cambiar —el arnés nunca aprieta X—. Una
prueba nueva sostiene X y cuenta los toques de A que ve el juego (por ejemplo,
cuántos mensajes seguidos cierra), y otra que soltar X no deje nada trabado.

## Cómo quedó

En `read_pad`: con X apretado, `pad_a` es la A de verdad OR la fase del
autofire, que sale del bit `AUTOFIRE_CUADROS` de un contador de vueltas; con X
suelto el contador vuelve a cero, así que el próximo X toca en su primer
cuadro. El contador está en la RAM baja (`autofire`, al final de
`ram_baja.s`) y no en página cero, donde quedaban tres bytes: en absoluto
cuesta cuatro bytes más de código, y es seguro porque `read_pad` ya lee
`JOY1L` en absoluto. `arranque` lo pone en cero.

Costo, medido con el `.res` de `AGENTS.md` contra el árbol de antes: **29
bytes** de `TABLAS`/`CODE` en los tres cartuchos (`release`, `tests/main`,
`tests/special`), uno de BSS, nada de página cero. El caso nuevo no suma nada
al banco 0.

Pruebas: `pruebas/rpgmaker/test_autofire.py` y `test_cores.py::test_autofire`,
con el caso `autofire` —cinco mensajes seguidos, y la variable 17 cuenta los
cerrados—. Vistas en rojo rompiendo el feature cuatro veces:

* `bit #PAD_X` cambiado por `bit #0` (sin autofire): cuatro en rojo —los
  mensajes, el ritmo, soltar X y soltar X a mitad—.
* `sta pad_a` del camino sin X cambiado por `tsb pad_a` (soltar X deja A
  trabado): rojo `test_soltar_x_no_deja_a_trabado_ni_toca_de_mas`, fase 1.
* `and #PAD_A` + `sta pad_a` del camino con X cambiado por `stz pad_a` (la A
  de verdad no gana): rojo `test_la_a_de_verdad_gana` y
  `test_soltar_x_con_a_apretado_no_suelta_a`.
* sin el `stz autofire` del camino sin X: rojo la parte de "el próximo X toca
  ya", fase 4.

Lo que ninguna prueba cubre: el `stz autofire` de `arranque`, que sólo importa
con X apretado desde el encendido —el arnés aprieta después del arranque—.

## Para taro

* Sostener X en un diálogo largo: los mensajes se pasan solos, ¿7,5 por
  segundo es mucho? Es `AUTOFIRE_CUADROS` en `rom/src/control.s` (potencia de
  dos: 4 da 7,5/s, 8 daría 3,75/s).
* Sostener X frente a alguien que habla: vuelve a hablarle al cerrar.
* En los menús, la tienda, la pelea y el título: X repite A (elige, compra).
* A y X juntos: tiene que sentirse como A sola.
* Soltar X a mitad: no tiene que quedar nada apretado ni salir un toque más.

**Confirmado por taro jugando el 2026-09-26: anda bien.**
