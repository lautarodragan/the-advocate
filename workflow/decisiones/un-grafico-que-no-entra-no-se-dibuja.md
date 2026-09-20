# Qué

**Un gráfico que no entra en las ocho paletas de sprite no se dibuja.** Lo
decide el conversor, con una sola función.

# Por qué

Vale para los eventos dibujados con un tile del chipset y, desde la orden 34,
para los gráficos a los que una ruta cambia: ahí la orden esconde al evento en
vez de cambiarlo.

**Forzarlos rompía tres mapas** —el 108, el 114 y el 207—.
