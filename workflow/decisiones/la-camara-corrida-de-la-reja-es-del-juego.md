# Qué

Al salir por la reja del mapa 12, Talan cae en (40,56) del mapa 8 y **la cámara
queda tres celdas más abajo de donde debería**: se lo ve pegado al borde de
arriba con media pantalla de mapa por debajo. **No se arregla.** Es así en el
juego original.

# Por qué

Lo hace el juego, no el port. La reja prende el switch 36, y con 36 prendido
arranca sola la página del **Bum** —el evento 10 de (38,55), "Woah! Where'd you
come from, Mister?"—, que hace un `PanScreen` de scroll de tres celdas para
abajo y **nunca lo devuelve**: no tiene la operación de volver.

Y el pan se queda pegado porque así es RM2k: la cámara **se lo sigue llevando
mientras el héroe camina** —`Game_Player::UpdateScroll` le resta el pan al
objetivo, y sólo lo saltea si el pan está fijado— y lo único que lo borra es
cambiar de mapa, en `PerformTeleport` con `map_changed`. Las dos cosas son las
que hace `rom/src/camara.s`, así que el port lo copia bien.

taro lo jugó en el RPG_RT original el 2026-09-23 —el de 2000, el que trae el
juego, corriendo con Wine— y la cámara queda igual de corrida. Las capturas
están en `/extras/capturas/reja-original/`.

# Qué hacer si aparece de nuevo

Nada. Si alguien ve la cámara descentrada después de la reja y quiere
"arreglarla", está por romper la fidelidad. El síntoma de un defecto **nuestro**
sería otro: que el mapa dibujado no coincida con la colisión —caminar sobre
paredes—, que es lo que cuida `pruebas/rpgmaker/test_camara.py`.
