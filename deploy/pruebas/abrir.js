// Abre un audio de YouTube como lo haria una persona y comprueba que sale la
// onda, que se puede recortar y que el recorte aparece con su reproductor.
const { JSDOM, VirtualConsole } = require('jsdom')
const base = process.argv[2] || 'http://127.0.0.1:8765'
const errores = []
const vc = new VirtualConsole()
const RUIDO = /scrollTo|scrollIntoView|Not implemented|navigation/i
vc.on('jsdomError', e => { const m = e.stack || e.message; if (!RUIDO.test(m)) errores.push(m.split('\n')[0]) })
vc.on('error', (...a) => errores.push('console.error: ' + a.join(' ')))

;(async () => {
  const html = await (await fetch(base + '/')).text()
  const dom = new JSDOM(html, {
    url: base + '/#/yt', runScripts: 'dangerously', resources: 'usable',
    pretendToBeVisual: true, virtualConsole: vc,
    beforeParse (w) {
      w.fetch = (u, o) => fetch(new URL(u, base), o)
      w.Headers = Headers; w.Request = Request; w.Response = Response
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
    set lineWidth (v) {}, set font (v) {} })
  w.HTMLMediaElement.prototype.play = () => Promise.resolve()
  w.HTMLMediaElement.prototype.pause = () => {}
  w.prompt = () => 'probador'
  w.confirm = () => true
  await new Promise(r => setTimeout(r, 3000))

  const abrir = [...w.document.querySelectorAll('button')].find(b => b.textContent === 'Abrir')
  if (!abrir) { console.log('no hay ningun audio para abrir'); process.exit(2) }
  abrir.click()
  await new Promise(r => setTimeout(r, 2500))

  const onda = w.document.querySelector('canvas.wf')
  console.log('onda dibujada     :', !!onda)
  console.log('titulo mostrado   :', (w.document.querySelector('.texto')?.textContent || '').slice(0, 60))

  if (onda) {                                   // doble clic = recorte
    onda.getBoundingClientRect = () => ({ left: 0, width: 500 })
    onda.dispatchEvent(new w.MouseEvent('dblclick', { clientX: 120, bubbles: true }))
    await new Promise(r => setTimeout(r, 2000))
  }
  const filas = w.document.querySelectorAll('#trec tr')
  console.log('recortes en tabla :', filas.length)
  console.log('reproductor       :', !!w.document.querySelector('#trec audio'))
  console.log('errores           :', errores.length)
  errores.forEach(e => console.log('  · ' + e))
  process.exit(errores.length || !onda || !filas.length ? 1 : 0)
})()
