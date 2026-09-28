---
name: "Todos los temas tienen pista de MSU-1"
description: "Hoy sólo algunos temas tienen pista (PISTAS_MSU); taro quiere que todos, siempre"
type: feature
---

taro, el 2026-09-26: **todos los temas siempre deberían tener su versión
MSU-1**. Hoy la tienen los de `PISTAS_MSU` (`tools/audio/snes_music.py`), y
los informes de audio de estos días hablaban de "los temas que tienen pista"
como si fuera normal que algunos no.

Qué implica:

* Renderizar la pista de cada tema que no la tiene (`tools/audio/msu.py`, con
  fluidsynth y el SoundFont, o el reemplazo de audio si hay), y que la lista
  deje de escribirse a mano: **todo tema que entra en el cartucho tiene pista**,
  y una prueba (o una aserción del conversor) que falle si alguno no la tiene.
* El número de pista de cada tema lo decide hoy `PISTAS_MSU`; con todos, la
  numeración puede salir del índice del tema.
* Consecuencias en la ROM: con MSU-1 **ninguna** muestra de música se sube
  (`done/` o `testing/con-msu-1-no-se-suben-las-muestras-del-tema.md`), así
  que la ARAM entera queda para los efectos; conviene hacerlo **después** de la
  tarea de los efectos con MSU-1, o coordinado con ella.
* Las pistas van a `/shared/msu/` con `just entregar --actualizar-msu`
  (cambia la huella).
* Tocar `msu.py` rehace todas las pistas: se hace una vez.

# Status

**Hecho el 2026-09-26, falta que taro lo escuche.** Todo tema del cartucho
tiene pista: en `release` son 32, los 22 de antes y diez nuevos.

**La numeración sale de `Music/` del juego**, no del cartucho: el número de
un tema es su lugar en la lista ordenada —sin mayúsculas, desde 1— de los
`.mid` y `.wav` de `Music/` (`pista_msu` en `snes_music.py`). El índice del
tema en el cartucho lo decide el orden en que aparecen los `PlayBGM` al
compilar, así que un mapa nuevo habría corrido los números de los que vienen
detrás, y cada corrimiento son cientos de megas que rehacer y que volver a
copiar a la tarjeta. `Music/` es del juego original y no cambia: un tema
nuevo es un archivo nuevo, y los demás quedan donde estaban. Los números
salen salteados (2, 4, 15 … 224), y al MSU-1 le da igual.

Lo que costó: **renumerar una vez los 22 de antes**. Las pistas de
`/shared/msu/` hay que reemplazarlas enteras con `just entregar
--actualizar-msu` —la huella cambia—: con esta ROM, las `abl-1` a `abl-22`
de antes suenan temas equivocados.

Cómo se arma ahora:

* El conversor le pone su `pista` a cada tema (`build_varios`), la escribe en
  la `tema_msu` de la ROM y en el `musica.json` de al lado.
* `msu.py` arma **las del `musica.json`** y borra los `<rom>-N.pcm` que ya no
  son de ningún tema, porque `just entregar` copia todos los que encuentra.
  Un tema que en el juego es un WAV tiene pista también, por ffmpeg (hoy no
  hay ninguno en el cartucho).
* `cartuchos.py` arma las pistas **detrás** de la conversión de `release`,
  y no a la par: las necesita del `musica.json`.

**La prueba** es `test_todo_tema_tiene_su_pista` (`pruebas/abl/test_msu.py`):
todo tema con música en `Music/` tiene número en `musica.json`, el mismo en
la `tema_msu` de la ROM, y su `.pcm` al lado; y ningún `.pcm` sobra. Se la
vio fallar sacando `abl-148.pcm` a mano, agregando un `abl-5.pcm` de más y
poniendo en `null` la pista de `prepara` en el `musica.json`.

**Las nuevas** —`11h035`, `bubstix`, `Deflector1`, `Fire_Mustang…`,
`MML2_MotherZone`, `pn28year`, `prepara`, `T_ProjectJustice_DiscLoad`,
`Tnt07`, `wb3town`— pesan 177 MB juntas. El volumen, por pico como las demás
(ver `msu.py`); la mediana del nivel, medida como el RMS de ventanas de 1 s
en el percentil 90, da lo mismo en las nuevas que en las de antes, y todas
caen dentro del rango de las 22. Las 22 re-renderizadas salen byte por byte
iguales a las de antes, con otro nombre.

**Lo que cambió en los efectos de calidad con MSU-1**, contra `main`
(`ee55226`), en la salida del conversor:

    paquete 121: 5000 Hz: 1                       -> 22050 Hz: 1
    paquete 261: 22050 Hz: 3, 6000 Hz: 3, 5500: 1 -> 22050 Hz: 3, 18000 Hz: 4
    paquete  52: 22050 Hz: 1, 20000 Hz: 2         -> 22050 Hz: 3

Sin MSU-1 no cambia nada: contra la de `main`, la ROM difiere en 134 bytes,
y todos caen en la `tema_msu`, en las tablas de los efectos del `.msu`
(`se_msu_filas`, `se_msu_altura`) y en su firma (`msu_datos_firma`).
