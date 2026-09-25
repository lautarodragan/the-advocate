# JetBrains

Lo que hace falta configurar en el IDE para trabajar en este repo. Es del
host: adentro del contenedor `.git/config` es de sólo lectura.

## Que el annotate atraviese el corte de `main.s`

El 2026-09-25 `rom/src/main.s` se partió en un archivo por subsistema. `git
blame` sólo sigue cada línea hasta su commit de verdad con
`-C --diff-algorithm=histogram` —el porqué está en `AGENTS.md`, en "`git blame`
y los cambios mecánicos"—; sin eso, cada línea de `rom/src/` dice "fue el
corte". El annotate de JetBrains no deja pasarle opciones a `blame`, así que:

    git config --global diff.algorithm histogram

y en el IDE, en las opciones del annotate, prender la detección de líneas
movidas entre archivos, que es la `-C`. No está medido que con esas dos
alcance: si el annotate sigue diciendo "fue el corte", anotarlo acá.
