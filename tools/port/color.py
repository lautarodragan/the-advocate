"""El tinte de pantalla de RM2k sobre un color de 15 bits.

Es la cuenta de `ToneBlit` de easyrpg, puesta en los cinco bits por canal de la
consola. La ROM hace la misma cuenta al subir la paleta.
"""

# El tinte de RM2k va de 0 a 200 con 100 como neutro. En la ROM se guarda tal
# cual y se aplica al subir la paleta.
TINTE_NEUTRO = 100


# Los pesos de luminancia de RM2k, que son los de Y' del Y'CbCr: la cuenta de
# `saturation_tone` en easyrpg es `(7471*b + 38470*g + 19595*r) >> 16`. Suman
# exactamente 65536, así que aplicados a canales de cinco bits dan una
# luminancia de cinco bits sin tener que reescalar nada.
LUZ_R, LUZ_G, LUZ_B = 19595, 38470, 7471
LUZ_TOTAL = 65536


def luminancia(r, g, b):
    """La luminancia de un color de 15 bits, en cinco bits."""
    return (LUZ_R * r + LUZ_G * g + LUZ_B * b) // LUZ_TOTAL


def saturar(canal, luz, s):
    """Un canal acercado o alejado del gris, con `s` en las unidades de RM2k.

    Es `saturation_tone` de easyrpg puesto en cinco bits y en las unidades de
    RM2k en vez de las suyas. Allá el factor es
    `sat = gray > 128 ? 1024 + (gray - 128) * 16 : gray * 8` sobre 1024, con
    `gray = s * 128 / 100`; hecha la cuenta, eso es `s / 100` para `s <= 100` y
    `(2s - 100) / 100` para `s > 100`. O sea que 0 lleva todo al gris, 100 no
    hace nada, y 200 triplica la distancia al gris.

    El caso de más de 100 va con el signo separado y truncando, en vez de con
    el desplazamiento aritmético de easyrpg, que redondea hacia abajo también
    con números negativos. La diferencia es de un valor de 31 y sólo cuando
    sobresatura; hacerlo con signo en el 65816 costaría bastante más que eso.
    """
    if s <= TINTE_NEUTRO:
        # Una interpolación entre el gris y el color, con los dos términos
        # positivos: es la forma que el 65816 puede hacer sin signo.
        return (luz * (TINTE_NEUTRO - s) + canal * s) // TINTE_NEUTRO
    m = s - TINTE_NEUTRO
    if canal >= luz:
        return min(31, canal + (canal - luz) * m // TINTE_NEUTRO)
    return max(0, canal - (luz - canal) * m // TINTE_NEUTRO)


def tenir_canal(canal, valor):
    """Un canal de cinco bits pasado por el tinte de RM2k, que es un hard light.

    RM2k no escala el canal: lo compone con un *hard light* —`hard_light.table`
    en easyrpg, que es `2ab` para la mitad de abajo y el screen `1-2(1-a)(1-b)`
    para la de arriba—. En las unidades de RM2k, con 100 neutro, eso es:

        valor <= 100:  canal * valor / 100
        valor  > 100:  31 - (200 - valor) * (31 - canal) / 100

    La primera mitad es exactamente lo que este repo venía haciendo, y por eso
    los tintes que oscurecen no cambian. La segunda no lo era.
    `canal * valor / 100` con valor hasta 200 multiplica por dos y topa, y eso
    **no es** lo que hace RM2k: la diferencia llega a 31 de 31 con valor 200, o
    sea la pantalla entera. No lo cobró nadie porque ninguna página que
    compilara usaba un tinte que aclare; las dos que lo destraba la saturación
    —los mapas 229 y 230— sí, con (0, 120, 120).

    Medido contra la cuenta de easyrpg sobre ocho bits, esta versión difiere en
    **un valor de 31 como mucho**, para todos los tintes que el juego usa. Es la
    misma tolerancia que ya tenía la mitad de abajo, y viene de que RM2k hace la
    cuenta con ocho bits y la consola tiene cinco.
    """
    if valor <= TINTE_NEUTRO:
        return min(31, canal * valor // TINTE_NEUTRO)
    return min(31, 31 - (2 * TINTE_NEUTRO - valor) * (31 - canal) // TINTE_NEUTRO)


def tenir(palabra, tinte):
    """Un color de 15 bits pasado por el tinte de pantalla.

    Primero la saturación y después el color, que es el orden de `ToneBlit`:
    allá `saturation_tone` corre antes que `color_tone`. Hacerlo al revés da
    otra cosa —el gris se calcularía sobre el color ya teñido— y es de las que
    una golden no vería: se sacaría con el error puesto y lo defendería.

    La cuenta va con enteros y sobre los 15 bits, no sobre los 24 del PNG: la
    consola tiene cinco bits por canal y redondearía distinto.
    """
    canales = [palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F]
    if len(tinte) > 3 and tinte[3] != TINTE_NEUTRO:
        # Sólo cuando hace falta, igual que el `apply_sat` de easyrpg: la
        # saturación no se puede hacer canal por canal —necesita el gris del
        # color entero— y es lo caro de esto en la consola.
        luz = luminancia(*canales)
        canales = [saturar(c, luz, tinte[3]) for c in canales]
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= tenir_canal(canal, valor) << (numero * 5)
    return salida
