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
