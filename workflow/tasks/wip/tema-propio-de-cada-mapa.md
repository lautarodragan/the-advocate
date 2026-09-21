**Que al entrar a un mapa suene su tema propio.**

RM2k guarda un tema por mapa en `maps.json` (`music_type`: 0 hereda del padre, 1 lo
decide un evento, 2 el que trae el mapa). El conversor hoy lo lee **sólo para el mapa
de arranque** —`temas_de_la_rom` en `snes_convert.py`—; en los demás la música
cambia únicamente con un `PlayBGM`.

Lo usan 73 mapas del juego. En `abl`: el 16 (`hzbreach`), el 21 y el 26
(`KSSMKEND`, los Rat Tracks, donde taro lo encontró). `lcf.map_music` ya resuelve la
herencia.

Hecho es: entrar a los Rat Tracks cambia a `KSSMKEND`, con una prueba que lo mire.
