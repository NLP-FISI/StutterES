// Simula al anotador trabajando mientras el servidor no responde.
const { JSDOM, VirtualConsole } = require('jsdom')
const base = 'http://127.0.0.1:8765'
const vc = new VirtualConsole()
const RUIDO = /scrollTo|scrollIntoView|Not implemented|navigation/i
vc.on('jsdomError', e => { if (!RUIDO.test(e.stack || e.message)) console.log('ERR', e.message) })

;(async () => {
  const html = await (await fetch(base + '/')).text()
  let caido = false
  const dom = new JSDOM(html, {
    url: base + '/#/ATMA/1', runScripts: 'dangerously', resources: 'usable',
    pretendToBeVisual: true, virtualConsole: vc,
    beforeParse (w) {
      w.fetch = (u, o) => {
        const m = (o && o.method) || 'GET'
        if (caido && m !== 'GET') return Promise.reject(new TypeError('failed to fetch'))
        return fetch(new URL(u, base), o)
      }
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
  await new Promise(r => setTimeout(r, 3500))

  const antes = (await (await fetch(base + '/rest/v1/disfluencia?autor=eq.probador&select=id')).json()).length
  console.log('marcas del probador antes :', antes)

  caido = true                                   // se cae el servidor
  const onda = w.document.querySelector('canvas.wf')
  for (let i = 0; i < 3; i++) {                  // el anotador sigue marcando
    const r = { left: 0, width: 400 }
    onda.getBoundingClientRect = () => r
    onda.dispatchEvent(new w.MouseEvent('dblclick', { clientX: 40 + i * 60, bubbles: true }))
    await new Promise(r2 => setTimeout(r2, 250))
  }
  await new Promise(r => setTimeout(r, 800))
  const cola = JSON.parse(w.localStorage.getItem('cola') || '[]')
  console.log('en la cola con el servidor caido:', cola.length)
  console.log('aviso en pantalla            :', w.document.querySelector('#pendientes').textContent)

  caido = false                                  // vuelve el servidor
  w.dispatchEvent(new w.Event('online'))
  await new Promise(r => setTimeout(r, 2500))
  const despues = (await (await fetch(base + '/rest/v1/disfluencia?autor=eq.probador&select=id')).json()).length
  console.log('en la cola despues           :', JSON.parse(w.localStorage.getItem('cola') || '[]').length)
  console.log('marcas del probador despues  :', despues)
  console.log(despues - antes === 3 ? 'OK: no se perdio ninguna' : 'FALLO: se perdieron marcas')
  process.exit(despues - antes === 3 ? 0 : 1)
})()
