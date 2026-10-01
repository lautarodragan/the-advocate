# Qué

**El cartucho pasa a 8 MB, ExHiROM**, para que el juego entero entre
jugable sin MSU-1. Reemplaza a "el cartucho se queda en 4 MB", del
2026-09-13.

Y **la pelea sin MSU-1 lleva los efectos de sonido de sus animaciones**,
aunque las animaciones mismas vayan sólo en el `.msu`: 92 KB.

# Por qué

De taro, el 2026-10-01, con la cuenta de
`docs/research/2026-10-01-el-juego-entero-sin-msu-1.md` delante: el juego
entero, con todo lo que faltaba, son unos 8.073 KB. En 4 MB no entra con
ningún recorte; en 8 MB entra **sin bajar la calidad de nada** una vez
aplicados los recortes sin pérdida (LZ2 donde va crudo, DTE en los textos,
saltos en las secuencias: 7.151 KB), con unos 850 KB de margen. Y
`decisiones/el-juego-se-juega-sin-msu-1.md` descarta la otra salida, la de
leer los mapas del `.msu`.

La decisión de 2026-09-13 decía "se revisa al llegar al 85-90% del
cartucho"; `release` llegó a 124 de 124 bancos con Tangle Forest.

# Cómo se aplica

- Primero una ROM de prueba de ExHiROM en el FX Pak, antes de mudar el juego.
- Los recortes de calidad del estudio (fondos por ChipSet, efectos a menor
  tasa, el techo de las muestras) quedan para cuando 8 MB apriete, y los
  elige taro de oído y a la vista.
