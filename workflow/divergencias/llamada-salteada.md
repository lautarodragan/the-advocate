# Qué

Cuando un `CallEvent` llama a un evento que no compila, **la llamada se
saltea**. Es lo que el port viene haciendo, y en la escena del Tram Officer se
midió lo que eso cuesta cuando la página que se saltea hace algo.

# Medido

El 2026-09-12, verificando `tram` en rojo: con `CallEvent` sin hacer **de los
dos lados** —que es como estuvo hasta ese día— el **cuadro 620** de esa escena
daba **34,64%** de pixeles distintos entre la ROM y la referencia. Con la
llamada hecha daba cero.

El sospechoso es el cronómetro, que esa rama arranca. No se investigó.

# Cómo se ve hoy

La página que lo destapaba ya no pasa por ahí —`CallEvent` se compila en línea
desde el 2026-09-12— pero **el camino sigue existiendo** para las **216
llamadas que se siguen salteando**, casi todas a eventos comunes que se cortan
en `ControlVars` y en los menús propios del original.
