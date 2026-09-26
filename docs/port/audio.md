# El audio

Qué pieza hace qué y dónde está su porqué. Todo lo demás vive en el código.

El audio lo maneja el **SPC700**, un procesador aparte con sus 64 KB de ARAM;
el 65816 no toca el DSP, sólo le habla al SPC700 por cuatro puertos. **La
lógica vive en Python**: el conversor decide qué nota va a qué voz, con qué
muestra y con qué envolvente, y la consola sólo reproduce.

    MIDI + SoundFont  --snes_music.py-->  musicdata.inc: el banco, un stream por
                                          tema, los paquetes de cada mapa
    stream por nota   --music_frame-->    escrituras al DSP, cuadro a cuadro
    escrituras        --dsp_musica-->     el driver del SPC700

* **El arranque**: `spc_upload` (`rom/src/spc700.s`) sube por el IPL el
  driver y el directorio de muestras, nada más. Qué atiende el driver —pares
  (registro, valor) para el DSP, ternas para la ARAM, volver al IPL— está en
  `DRIVER`, en `tools/audio/snes_music.py`. Cuánto espera la ROM al encender
  es `BOOT_CUADROS` (`rom/src/ram_lejana.s`), y el conversor se corta si no
  alcanza: ver
  `workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md`.
* **El stream es por nota**: notas, releases, cambios de volumen o de altura,
  y esperas, que el 65816 expande a las mismas escrituras que antes iban en el
  stream. El formato está en "el formato por nota" de `snes_music.py` y los
  opcodes en `tools/protocol/music.toml`; `irq_musica` (`rom/src/musica.s`)
  corre un cuadro de música por cuadro de video.
* **Las ocho voces son de todos los canales** y se reparten nota a nota: una
  nota toma una voz libre o le roba a otra por prioridad. Ver `assign`,
  `_victima` y `_orden_del_cuadro` en `snes_music.py`.
* **El volumen tiene un techo por tema**, medido y versionado en
  `parches/auto/musica/techos.toml` (`just techos`): ver `leer_techos`.
* **Las muestras salen del SoundFont** con el que se compuso el juego
  (`tools/audio/snes_samples.py`; `ABL_SOUNDFONT` apunta a otro), y las pasa a
  BRR Gunter, por `tools/audio/muestras_brr.py`.
* **Un solo banco de muestras para todo el cartucho, subido de a paquetes, uno
  por mapa**, y cada muestra con el presupuesto de su peor paquete: `Banco` y
  `repartir` en `snes_music.py`, y el porqué en
  `workflow/decisiones/un-solo-banco-de-muestras.md`. Lo sube
  `paquete_cargar` (`rom/src/paquete_de_audio.s`) mientras la música suena;
  si el tema que viene sonando y el paquete nuevo no entran juntos, gana el
  tema: `workflow/decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`.
* **Los efectos de sonido** —`PlaySound`— le roban dos voces a la música
  mientras duran, las que el reparto llena primero con la percusión:
  `rom/src/efectos_de_sonido.s` y `build_efectos` en `snes_music.py`. Los
  que van enteros y a más tasa —`SE_ENTEROS`— se acomodan en lo que la música
  deja libre en cada paquete, así que no le bajan la tasa a ningún
  instrumento. Los de `SE_ENTEROS_PAGADOS` —el trueno de la apertura y los
  que taro eligió enteros aunque costaran— sí los paga la música de su
  paquete: `workflow/decisiones/el-trueno-va-entero-a-22-khz.md`. Uno que en
  un mapa suena con otra muestra es un alias: `SE_DEL_MAPA`.
* **El `FadeOutBGM` baja el tema y nada más**: el volumen de cada voz de la
  música, o el de la pista del MSU-1, y nunca el general del DSP, que es
  también el de los efectos. `bgm_fundido_tick`, en `rom/src/musica.s`.
* **El MSU-1**: los temas de `PISTAS_MSU` suenan desde un PCM al lado de la
  ROM, y la ROM calla el SPC700 mientras tanto. Las pistas las arma
  `tools/audio/msu.py`. Con MSU-1, el paquete no sube las muestras de los
  temas con pista, salvo que la pista haya faltado en la tarjeta:
  `tema_por_msu`, en `rom/src/paquete_de_audio.s`.

Qué prueba cubre qué: `pruebas/rpgmaker/test_musica_*.py` corren la ROM
—las escrituras, el reparto, el paquete, los techos— y
`pruebas/herramientas/test_musica_stream.py` mira el stream sin ROM.
