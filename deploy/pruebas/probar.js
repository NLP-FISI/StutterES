// Carga la web en un DOM de verdad contra el servidor local y avisa de
// cualquier error de JavaScript. Uso: node probar.js http://127.0.0.1:8765 '#/'
const { JSDOM, VirtualConsole } = require('jsdom')

const base = process.argv[2] || 'http://127.0.0.1:8765'
const ruta = process.argv[3] || '#/'
const errores = []

const vc = new VirtualConsole()
const RUIDO = /scrollTo|scrollIntoView|Not implemented: HTMLMediaElement|navigation/i
vc.on('jsdomError', e => {
  const m = e.stack || e.message
  if (!RUIDO.test(m)) errores.push('jsdomError: ' + m)
})
vc.on('error', (...a) => errores.push('console.error: ' + a.join(' ')))

;(async () => {
  const html = await (await fetch(base + '/')).text()
  const dom = new JSDOM(html, {
    url: base + '/' + ruta,
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse (w) {
      // jsdom no trae fetch: se lo pasamos apuntando al servidor
      w.fetch = (u, o) => fetch(new URL(u, base), o)
      w.Headers = Headers; w.Request = Request; w.Response = Response
      // jsdom tampoco trae estos, pero los navegadores si
      w.ResizeObserver = class { observe () {} unobserve () {} disconnect () {} }
      w.IntersectionObserver = class {
        constructor (cb) { this.cb = cb }
        observe (n) { this.cb([{ isIntersecting: true, target: n }]) }
        unobserve () {} disconnect () {}
      }
    }
  })
  const w = dom.window
  w.HTMLCanvasElement.prototype.getContext = () => ({
    clearRect () {}, fillRect () {}, strokeRect () {}, fillText () {},
    measureText: () => ({ width: 10 }), set fillStyle (v) {}, set strokeStyle (v) {},
    set lineWidth (v) {}, set font (v) {}
  })
  w.HTMLMediaElement.prototype.play = () => Promise.resolve()
  w.HTMLMediaElement.prototype.pause = () => {}
  w.prompt = () => 'probador'
  w.confirm = () => true
  w.addEventListener('error', e => errores.push('window.onerror: ' + (e.error?.stack || e.message)))
  w.addEventListener('unhandledrejection', e => errores.push('promesa: ' + (e.reason?.stack || e.reason)))

  await new Promise(r => setTimeout(r, 4000))
  const vista = w.document.querySelector('#vista')
  const texto = (vista?.textContent || '').trim().slice(0, 160)
  console.log('ruta      :', ruta)
  console.log('#vista    :', texto || '(vacío)')
  console.log('tarjetas  :', w.document.querySelectorAll('.tarjeta, .ora').length)
  console.log('errores   :', errores.length)
  errores.forEach(e => console.log('  · ' + e.split('\n')[0]))
  process.exit(errores.length || /cargando…/.test(texto) ? 1 : 0)
})()
