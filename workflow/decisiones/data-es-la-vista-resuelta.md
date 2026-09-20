# Qué

`data/` es la **vista resuelta** del juego —todos los campos escritos y los
enums en número— y el volcado exacto **no se versiona**.

# Por qué

Del 2026-09-20. `ditto unpack` emite las dos en la misma corrida: `data/` y
`rom/build/ditto-exacto/`, con la forma del binario. Con eso
`tools/rpgmaker/lcf.py` no sabe ninguna regla del formato, que era lo que se
buscaba.

Perder los nombres en `data/` es aceptado: vuelven el día que el pipeline sea
Rust y Ditto sea una lib.

No versionar el exacto es lo que hace que **la única fuente del binario sea el
juego**, que es lo que `ditto pack` ya necesitaba tener al lado para comparar.

El porqué entero está en `DITTO.md`.
