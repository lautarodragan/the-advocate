# Qué

La ventana de mensaje se lleva **8 KB de tiles y 2 KB de tilemap propio** de
los 64 KB de VRAM, y eso es lo que le achica el banco al fondo en todos los
repartos que la llevan.

Los tiles del área de texto son 240 porque **el glifo mide 6 pixeles de ancho
y la celda 8**: no alinean, así que cada celda es un tile propio que la ROM
compone pixel por pixel. Es lo que hace Final Fantasy, y se verificó contra su
decompilación antes de descartar alternativas. Así la línea tiene los 39
caracteres del original.

# Medido

La alternativa que existe y no se tomó: glifos de 8 pixeles, alineados a la
celda. Ahorraría unos 48 tiles —1,5 KB, o sea 24 tiles de fondo— y bajaría la
línea de **39 caracteres a 30**. Los textos del ABL están escritos para 39, así
que cortarían distinto que en el original.

# Cómo se ve hoy

Igual que en RM2k: 39 caracteres por línea. Lo que cuesta es VRAM, no algo que
se vea. Por qué 39 y no 40 está en `tools/port/snes_convert.py`, al lado de los
240 tiles.

# Cuándo deja de alcanzar

Queda como plan B por una razón concreta: **ya se trunca texto** por la
diferencia de resolución, así que en algún momento va a hacer falta un
algoritmo que rearme los saltos de línea. Hoy cada cuadro de texto es un comando
aparte y cada salto está puesto a mano, así que fusionar comandos consecutivos
pide decidir cuándo es razonable hacerlo —¿cambió quién habla?— y eso puede no
ser determinístico. El día que ese algoritmo exista, pasar a 30 columnas deja
de ser un costo técnico y pasa a ser sólo estético.
