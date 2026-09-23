---
name: "La música en el SPC700"
description: "Un secuenciador en el SPC700 en vez del 65816"
---

# Qué

Que la música la toque el SPC700 y no el 65816: un secuenciador chico que lea
**el mismo stream de hoy** desde un buffer circular en la ARAM, a su propio
ritmo, y que el 65816 sólo mantenga lleno. Los efectos de sonido pasarían allá
también.

# Status

Anotado, sin empezar. Acordado con taro el 2026-09-11 como el paso que sigue.
**No** es un secuenciador en
el SPC700 como los de los juegos comerciales, y el conversor no cambia.

Se encara cuando haga falta el margen del lazo, o si en la consola el audio
muestra algo que el emulador no.

# Por qué

Hoy la música la toca el 65816 desde una IRQ —ver "La música no espera al lazo"
en `docs/events.md`— y funciona, pero cuesta **hasta veinte líneas por cuadro** y
obliga a las reglas de la interrupción.
