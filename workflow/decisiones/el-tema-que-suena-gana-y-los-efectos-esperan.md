# Qué

**Cuando el tema que viene sonando y el paquete del mapa nuevo no entran
juntos en la ARAM, gana el tema: los efectos que no entraron esperan al
próximo `PlayBGM`**, que calla el tema viejo y completa el paquete.

Es del 2026-09-26, con el presupuesto por paquete (ver
`un-solo-banco-de-muestras.md`), y la decidió taro al elegir la opción A del
paso 6 de `tasks/todo/la-calidad-de-la-musica.md`.

# Por qué

Casi ningún mapa del juego trae tema propio: lo prende una página, y hasta
entonces sigue el del mapa anterior. `package_load_done` no mueve sus
muestras —la música sigue durante el fundido, y pisar una muestra que está
sonando sería ruido—, así que el paquete nuevo se acomoda al lado.

Presupuestar la herencia entera, efectos incluidos, dejaba el polysynth de
`escape_newyork` a 4 kHz y las cuerdas y la onda cuadrada a 6: peor que antes
del presupuesto por paquete en los temas que más importan. Contar el tema
heredado **sólo como tema** es lo que hace que el presupuesto por paquete
valga la pena. Lo que se paga: los efectos del mapa no suenan entre la
llegada y el `PlayBGM`, y ese `PlayBGM` congela lo que tarde en subir lo que
faltaba. En el juego, los mapas 2 y 3 prenden su tema antes de usar sus
efectos.

Dónde vive: el conversor presupuesta cada paquete con los temas que pueden
venir sonando (`inherited_songs` en `tools/port/music.py`), la ROM
anota `PKG_PARTIAL` y `song_ensure` completa el paquete. Lo cobra
`test_el_paquete_que_no_entro_con_otro_tema_sonando_se_completa`.
