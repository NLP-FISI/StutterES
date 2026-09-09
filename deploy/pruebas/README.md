# Probar la web antes de desplegar

Carga la pagina en un DOM de verdad (jsdom), ejecuta su JavaScript y avisa de
cualquier error. Es lo unico que caza los fallos que solo se ven en el
navegador: curl contra la API los deja pasar.

    npm i jsdom
    node probar.js http://127.0.0.1:8765 '#/'
    node probar.js http://127.0.0.1:8765 '#/ATMA/1'
    node probar.js http://127.0.0.1:8765 '#/yt'

Sale con codigo 1 si hay errores o si la vista se queda en "cargando...".

`abrir.js` abre un audio de YouTube como lo haria una persona: pulsa *Abrir*,
comprueba que sale la onda, corta un trozo y verifica que aparece con su
reproductor.

    node abrir.js http://127.0.0.1:8765

`cola.js` simula al anotador marcando con el servidor caido y comprueba que
nada se pierde: encola en el navegador y lo suelta cuando el servidor vuelve.

    node cola.js
