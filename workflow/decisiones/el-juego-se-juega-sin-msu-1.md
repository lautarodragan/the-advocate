# Qué

**El juego entero tiene que poder jugarse sin MSU-1.** El MSU-1 es una
mejora opcional —música por pistas, efectos y fondos de mejor calidad, las
animaciones de la pelea—, nunca un requisito para llegar al final.

# Por qué

De taro, el 2026-10-01, al leer
`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`, que recomendaba un
cartucho `completo` que pidiera MSU-1: "quiero evitar depender del msu
completamente. Me gustaría que el juego sea jugable sin msu". Reemplaza esa
recomendación.

# Cómo se aplica

- **Lo que entra en la ROM tiene que alcanzar para jugar**: mapas, eventos,
  textos, música por el SPC700. Si no entra, se baja la calidad en la ROM
  (`decisiones/primero-el-juego-entero-despues-la-calidad.md`), no se manda
  al `.msu`.
- **El `.msu` lleva la versión mejor de lo mismo.** El criterio de taro, el
  mismo día: sin MSU-1 los fondos de los mapas se cuantizan como haga falta
  para no duplicar gráficos —compartiendo tiles entre mapas del mismo
  ChipSet, con menos colores—, y con MSU-1 se pueden leer del `.msu`
  cuantizados por mapa, con todos los colores.
- **Las animaciones de la pelea van sólo en el `.msu`**: sin MSU-1 no hay. Las
  que muestran los eventos en las cinemáticas se quedan en la ROM, salvo que
  haga falta sacarlas.
