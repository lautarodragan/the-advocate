# Qué

**Se dibujan todos los eventos, aunque sea con una paleta ajena.**

# Por qué

Es de taro, el 2026-09-08: *"si no podemos incluir todos los eventos, el
proyecto entero se cae"*. El que no consigue paleta propia se cuelga de la que
menos colores le falte, y cada color ausente va al más cercano por luma. Un
sprite con los colores cambiados es un error que se ve; uno que no se dibuja es
una pared invisible que dispara y cierra el paso, y ya costó una tarde con la
puerta que Core rompe.

# Medido

Lo que cuesta, medido antes de decidirlo. Por gráfico, el porcentaje de sus
pixeles que cambia de color y el salto peor en un canal, sobre 31:

    @tile:BLchp1:112     0%
    Chara2:0            21%, salto 9
    @tile:BLchp1:53     23%, salto 11
    Future1:7           38%, salto 15
    @tile:BLchp1:117    42%, salto 1     ← la puerta del pad de Talan
    Future3:1           49%, salto 17
    @tile:BLchp1:111    70%, salto 13

El caso de la puerta es el que muestra por qué el porcentaje solo no alcanza:
cambia el 42% de sus pixeles pero ninguno se mueve más de 1 sobre 31, así que a
ojo es la misma puerta.

Lo que destrabó: el mapa 8 —la calle a la que da el pad— pedía trece paletas de
ocho y no había reparto posible, y pasó a entrar con seis gráficos prestados,
entre ellos el save point; el Hover-Tram (mapa 13) pedía once y pasó a entrar
con dos. El tope dejó de ser la cantidad de paletas y pasó a ser el presupuesto
de tiles de sprite en VRAM: ver `docs/port/vram.md`.
