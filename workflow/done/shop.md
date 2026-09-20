### La tienda

`OpenShop` abre `Scene_Shop`. Compila a `OP_SHOP` —el
tipo, el juego de mensajes y la lista de lo que vende, de largo variable como
`OP_CHOICE`— y, como guardar, la pantalla se abre adentro del intérprete y no
cuesta ningún tick: al salir el mapa vuelve y la página sigue. Es una pantalla
de texto, y cada modo es el de RM2k:

    principal       el saludo —o el resaludo al volver— y Buy, Sell, Leave
    comprar         lo que vende con su precio, en gris lo que no alcanza el
                    oro o ya se tiene 99; el oro, y cuántos se tienen y lleva
                    puestos el grupo del que marca el cursor
    cuántos         derecha e izquierda de a uno, arriba y abajo de a diez,
                    entre 1 y lo que se puede; el total
    listo           el "Done" o el "Thanks.", un segundo, y de vuelta
    vender          el inventario a mitad de precio, en gris lo que vale 0

Con una sola orden —sólo comprar o sólo vender— no hay principal. Los
mensajes salen de los tres juegos de términos del LDB, partidos en dos
renglones; las ramas de "compró" y "no compró" no compilan, y ninguna tienda
del juego las usa. El caso `tienda` de la tanda entra y sale de la del mapa
10, y `pruebas/rpgmaker/test_tienda.py` la recorre entera pixel por pixel contra
`pantallas.pantalla_tienda`: comprar, el tope del oro, vender, el oro y el
inventario que quedan.
