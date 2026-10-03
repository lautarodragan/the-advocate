# Qué

La ventana de mensaje se lleva **8 KB de tiles y 2 KB de tilemap propio** de
los 64 KB de VRAM, y eso es lo que le achica el banco al fondo en todos los
repartos que la llevan.

Los tiles del área de texto son 240 porque **el glifo no mide 8 pixeles**: no
alinea con la celda, así que cada celda es un tile propio que la ROM compone
pixel por pixel. Es lo que hace Final Fantasy, y se verificó contra su
decompilación antes de descartar alternativas.

Hasta el 2026-10-03 el glifo medía 6, el de RM2k, y la línea tenía 39
caracteres. Desde ese día la fuente es de ancho variable —la hoja
`low-variable` de `tools/rm2k-snes/text/fonts/`, o la que el juego nombre en
`[text] font`— y la línea mide **240 pixeles**: con esa fuente entran unas 49
letras, casi las de la ventana de RM2k, que a 320 de ancho y 6 por letra toma
unas 50.

# Medido

La alternativa que existe y no se tomó: glifos de 8 pixeles, alineados a la
celda. Ahorraría unos 48 tiles —1,5 KB, o sea 24 tiles de fondo— y bajaría la
línea a **30 caracteres**. Medido el 2026-10-03: con 39 se rearmaban 1245
cajas del ABL y 299 no entraban en una sola; con la de ancho variable se
rearma una.

# Cómo se ve hoy

Casi como en RM2k: las cajas del ABL entran como las escribió el autor. Lo
que cuesta es VRAM, no algo que se vea. El ancho de la línea está en el
`layout.rs` de `rm2k-snes-screens`, al lado de los 240 tiles.

# Cuándo deja de alcanzar

Una caja que no entra se rearma —`refit` en `rm2k-snes-text`, que mide en
pixeles con la misma fuente—, así que lo que no entra deja de ser texto
cortado y pasa a ser una caja de más. Pasar a 30 columnas sería sólo un costo
estético; con la fuente de ancho variable, uno grande.
