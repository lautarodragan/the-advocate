---
name: "Las copias de muestras con temas que comparten muestras"
description: "Un tema nuevo que comparte muestras con los viejos cambia qué copias hace rm2k-snes-audio y les baja la tasa sin MSU-1"
type: feature
---

Del hito 4 del mundo (2026-09-27): los cinco temas del capítulo comparten
muestras con temas que ya estaban, y eso cambió qué copias hace
`copies`, en `tools/rm2k-snes/rm2k-snes-audio/src/bank.rs`. Sin MSU-1 bajaron 43 pares (tema, instrumento) de 15
temas y subieron 51. Con sólo jackalstg2 bajaban 36. taro escuchó el antes y
el después y los aceptó, así que no hubo que frenar el capítulo, pero **va a
volver a pasar con cada tema que se sume**.

Lo que se probó sin recuperarlos (ver
`testing/mundo-4-el-capitulo.md`, "La música de antes, sin MSU-1"):
`TEMAS_APARTE` (los nuevos ya van solos), `SE_DE_SIEMPRE` de 70 a 130 (lo
mejor, 29 pares, y mueve la tanda de efectos que taro aprobó), `COPIA_HASTA`
en 0,85 y 0,95, sin la herencia de jackalstg2, sin el paquete del 259. El
directorio no era la causa: sin la segunda tanda para los temas nuevos queda
con lugar libre y bajan igual 42.

Lo que falta: que `copias` elija qué copiar pensando en todos los temas que
usan una muestra, no en el orden en que llegan, y medirlo par por par con
`Banco` contra el `main` de antes del capítulo (93af39f no: el `main`
455f9fc1). Lo que no se recupere sin perder otra cosa, grabado para que
taro escuche.

# Lo que se pensó el 2026-09-30, y por qué pasa al wishlist

Con la radio de las páginas de tropa (`testing/el-comun-35-y-la-radio.md`)
volvió a pasar: sin MSU-1, el tema de batalla bajó de 11,5 a 10 kHz y otros
34 temas perdieron alguna muestra, las peores de 20,4 a 6,8 kHz. taro
propuso ir más allá de "elegir mejor qué copiar", y lo que salió de la charla:

1. **La pelea como caso especial, primero.** Sus instrumentos en una calidad
   y los del resto en otra, aunque se dupliquen muestras. Suena seguido y es
   donde más efectos hay, así que es probablemente lo de mejor costo contra
   lo que se oye.
2. **Pesar cada tema por cuánto suena.** Anotar en qué cuadro cambia el tema
   en una corrida del recorrido y contar cuadros por tema. Dos cuidados: el
   recorrido cubre el principio del juego y no el promedio, y la pelea se
   estima aparte, por los encuentros de cada mapa, o queda subrepresentada.
3. **El caso general: un grafo de instrumentos y temas**, particionado
   duplicando las muestras que más mejoran lo que se oye por byte de ROM, con
   esos pesos. Es la generalización de "lo que falta" de arriba.
4. **Los efectos en el mismo grafo**: sin MSU-1 comparten la ARAM con la
   música. Fuera de la pelea, el más común debe ser el del cofre.

Por qué no ahora: con MSU-1 la música va por pistas y esto no se oye;
duplicar muestras cuesta ROM, y a `release` le quedan pocos bancos, que va a
pedir el mundo; y la calidad se ajusta cuando el juego entero sea jugable
(`decisiones/primero-el-juego-entero-despues-la-calidad.md`).

**Cuando se tome**: primero un análisis y un plan —medir el grafo, los pesos
y cuánta ROM cuesta cada opción—, y de ese plan salen las tareas.
