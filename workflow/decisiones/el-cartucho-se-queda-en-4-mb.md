# Qué

**El cartucho se queda en 4 MB**, y el paso siguiente no es agrandarlo.

# Por qué

Decidido con taro el 2026-09-13, con el número delante: la demo de 29 mapas,
siete animaciones, la batalla y 19 temas pesa **2,52 MB, el 60%**.

Para el juego entero **no alcanza** —`assets/README.md` tiene la cuenta: ~2,9 MB
de mapas, sprites, colisión y música, más 2,7 MB de arte que todavía no dibuja
nadie, y las 42 animaciones de batalla serían otros ~1,7 MB: unos 7 MB—. Pero
**LoROM topa en 4 MB** y pasar de ahí es ExHiROM, o sea cambiar cómo se calcula
cada dirección, con todo lo que eso rompe en hardware y no en el emulador.

Lo barato está antes, y está medido en `assets/README.md`: el conversor
**cuantiza por mapa**, así que dos mapas que comparten chipset reciben paletas
distintas y el mismo dibujo termina siendo bytes distintos.

**Se revisa al llegar al 85-90% del cartucho.**
