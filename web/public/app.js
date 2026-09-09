'use strict'
/* Anotador StutterES.
   La forma de onda viene precalculada en /data/<SP>/<NNN>.json y se dibuja en
   un canvas; el audio se reproduce por rangos desde /audio. */

const $ = (s, e = document) => e.querySelector(s)
const el = (t, c, x) => { const n = document.createElement(t); if (c) n.className = c; if (x != null) n.textContent = x; return n }
const seg = s => s == null ? '—' : `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, '0')}`

const DUR = 3
const TIPOS = ['Prolongation', 'Block', 'SoundRep', 'WordRep', 'Interjection']
const COLOR = {
  Prolongation: '#f2a541', Block: '#e5484d', SoundRep: '#8b5cf6',
  WordRep: '#2dd4bf', Interjection: '#f472b6', NoStutteredWords: '#5b6472'
}
const NOMBRE = {
  Prolongation: 'Prolongación', Block: 'Bloqueo', SoundRep: 'Rep. sonido',
  WordRep: 'Rep. palabra', Interjection: 'Interjección', NoStutteredWords: 'Sin tartamudeo'
}

let CFG = null, META = null, ACTUAL = null, TIPO = 'Block', FOCO = 0
let AUTOR = localStorage.getItem('autor') || ''
const ONDAS = new Map()
let ARRASTRANDO = null
addEventListener('mouseup', e => { const o = ARRASTRANDO; ARRASTRANDO = null; o?.sube(e) })

// ------------------------------------------------------------------ audio
const AU = new Audio()
AU.preload = 'metadata'
let HASTA = null, ACTIVA = null

// currentTime se ignora si aun no hay metadatos: se deja pedido.
function situar (t) {
  if (AU.readyState >= 1) { AU.currentTime = t; return }
  AU.addEventListener('loadedmetadata', () => { AU.currentTime = t }, { once: true })
}
AU.addEventListener('timeupdate', () => {
  if (HASTA != null && AU.currentTime >= HASTA) { AU.pause(); HASTA = null }
})
function urlAudio (d) {
  return `${(CFG.audio || '/audio').replace(/\/$/, '')}/${d.sp}/${d.epid}.${CFG.ext || 'opus'}`
}
function tocar (o, desde, hasta) {
  if (!ACTUAL) return
  const u = urlAudio(ACTUAL)
  if (AU.src !== u) AU.src = u
  ACTIVA = o
  situar(Math.max(0, desde))
  HASTA = hasta
  AU.play().catch(e => aviso('no se pudo reproducir: ' + e.message))
}
function irA (o, t, sonar) {
  const p = Math.max(0, Math.min(o.dur, t))
  if (!ACTUAL) return
  const u = urlAudio(ACTUAL)
  if (AU.src !== u) AU.src = u
  ACTIVA = o
  situar(o.a + p)
  HASTA = o.b
  if (sonar && AU.paused) AU.play().catch(() => {})
}

function alterna (o) {
  if (!AU.paused && ACTIVA === o) return AU.pause()
  tocar(o, o.a, o.b)
}
;(function pinta () {
  if (ACTIVA && ONDAS.has(ACTIVA.i)) {
    ONDAS.get(ACTIVA.i).dibuja()
    if (ACTIVA.card?.tm) ACTIVA.card.tm.textContent = seg(AU.currentTime - ACTIVA.a)
  }
  requestAnimationFrame(pinta)
})()

// ------------------------------------------------------------------- api
const marca = (() => {
  const n = $('#guardado'); let t
  return e => {
    n.textContent = e === 'g' ? 'guardando…' : e === 'ok' ? 'guardado ✓' : e
    n.style.color = (e === 'g' || e === 'ok') ? '' : 'var(--Block)'
    clearTimeout(t); if (e !== 'g') t = setTimeout(() => { n.textContent = '' }, e === 'ok' ? 1600 : 6000)
  }
})()
const aviso = m => marca(m)

async function api (ruta, { method = 'GET', body, prefer } = {}) {
  const h = {}
  if (body) h['Content-Type'] = 'application/json'
  if (prefer) h.Prefer = prefer
  if (method !== 'GET') marca('g')
  const r = await fetch(`/rest/v1/${ruta}`, {
    method, headers: h, body: body ? JSON.stringify(body) : undefined
  })
  if (!r.ok) { const t = await r.text(); marca('error: ' + t.slice(0, 90)); throw new Error(t) }
  if (method !== 'GET') marca('ok')
  return r.status === 204 ? null : r.json()
}

// ----------------------------------------------------------------- onda
class Onda {
  constructor (o) {
    this.o = o
    this.picos = Uint8Array.from(atob(o.pk), c => c.charCodeAt(0))
    this.cv = el('canvas', 'wf')
    this.cv.addEventListener('mousedown', e => this.baja(e))
    this.cv.addEventListener('mousemove', e => this.mueve(e))
    this.cv.addEventListener('dblclick', e => this.dobleClic(e))
    this.arr = null
    new ResizeObserver(() => this.dibuja()).observe(this.cv)
  }

  get disf () { return this.o.disf }
  tiempo (e) {
    const r = this.cv.getBoundingClientRect()
    return Math.max(0, Math.min(this.o.dur, (e.clientX - r.left) / r.width * this.o.dur))
  }
  encima (t) {
    for (let i = this.disf.length - 1; i >= 0; i--) {
      const d = this.disf[i]
      if (d.start_s != null && t >= d.start_s && t <= d.stop_s) return d
    }
    return null
  }

  baja (e) {
    const t = this.tiempo(e)
    const d = this.encima(t)
    this.arr = { x0: e.clientX, t0: t, d, movido: false, off: d ? t - d.start_s : 0 }
    ARRASTRANDO = this
    if (d) this.cv.classList.add('mover')
  }
  mueve (e) {
    if (!this.arr) {
      this.cv.classList.toggle('mover', !!this.encima(this.tiempo(e)))
      return
    }
    if (Math.abs(e.clientX - this.arr.x0) < 4) return
    this.arr.movido = true
    if (this.arr.d) {                    // arrastrar una marca la mueve
      const [a, b] = ventana(this.tiempo(e) - this.arr.off, this.o.dur)
      this.arr.d.start_s = a; this.arr.d.stop_s = b
      fila(this.o, this.arr.d)
      this.dibuja()
    } else {                             // arrastrar el fondo mueve el cursor
      irA(this.o, this.tiempo(e), false)
      this.dibuja()
    }
  }
  sube (e) {
    const s = this.arr; if (!s) return
    this.arr = null; this.cv.classList.remove('mover')
    if (s.movido) {
      if (s.d) guardarDisf(s.d)
      else irA(this.o, this.tiempo(e), true)
      return
    }
    if (s.d) {                           // clic en una marca: la oye entera
      seleccionar(this.o, s.d.id)
      tocar(this.o, this.o.a + s.d.start_s, this.o.a + s.d.stop_s)
      return
    }
    irA(this.o, s.t0, true)              // clic en el fondo: suena desde ahi
  }
  dobleClic (e) {
    const t = this.tiempo(e)
    if (!this.encima(t)) crearDisf(this.o, t)
  }

  dibuja () {
    const cv = this.cv, r = cv.getBoundingClientRect()
    if (!r.width) return
    const dpr = devicePixelRatio || 1
    const W = Math.round(r.width * dpr), H = Math.round(r.height * dpr)
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H }
    const g = cv.getContext('2d')
    g.clearRect(0, 0, W, H)
    g.fillStyle = '#1e222b'; g.fillRect(0, 0, W, H)

    // banda de los clips de 3 s ya anotados
    const hb = 5 * dpr
    for (const c of this.o.c3 || []) {
      g.fillStyle = c.et.some(x => x !== 'NoStutteredWords') ? '#8b5cf655' : '#3c445580'
      g.fillRect(c.a / this.o.dur * W, H - hb, (c.b - c.a) / this.o.dur * W, hb)
    }

    // envolvente
    const med = (H - hb) / 2, n = this.picos.length
    g.fillStyle = '#3c4454'
    for (let x = 0; x < W; x++) {
      const v = this.picos[Math.min(n - 1, Math.floor(x / W * n))] / 255
      const h = Math.max(1, v * (med - 2 * dpr))
      g.fillRect(x, med - h, 1, h * 2)
    }

    // marcas
    for (const d of this.disf) {
      if (d.start_s == null) continue
      const x0 = d.start_s / this.o.dur * W, x1 = d.stop_s / this.o.dur * W
      g.fillStyle = COLOR[d.tipo] + '3d'
      g.fillRect(x0, 0, x1 - x0, H - hb)
      g.fillStyle = COLOR[d.tipo]
      g.fillRect(x0, 0, 2 * dpr, H - hb); g.fillRect(x1 - 2 * dpr, 0, 2 * dpr, H - hb)
      if (d.id === this.o.sel) {
        g.strokeStyle = '#fff'; g.lineWidth = 1.5 * dpr
        g.strokeRect(x0 + 1, 1, x1 - x0 - 2, H - hb - 2)
      }
      g.font = `${11 * dpr}px ui-monospace,monospace`
      const et = NOMBRE[d.tipo]
      const w = g.measureText(et).width
      g.fillStyle = '#0f1115cc'; g.fillRect(x0 + 3 * dpr, 3 * dpr, w + 6 * dpr, 15 * dpr)
      g.fillStyle = COLOR[d.tipo]; g.fillText(et, x0 + 6 * dpr, 14 * dpr)
    }

    // cursor
    if (ACTIVA === this.o) {
      const t = AU.currentTime - this.o.a
      if (t >= 0 && t <= this.o.dur) {
        g.fillStyle = '#e6e8ec'; g.fillRect(t / this.o.dur * W, 0, dpr, H - hb)
      }
    }
  }
}

function urlFragmento (a, b) {
  return `/fragmento/${ACTUAL.sp}/${ACTUAL.epid}?a=${a.toFixed(3)}&b=${b.toFixed(3)}`
}

function reproductor (a, b, ancho) {
  const au = el('audio')
  au.controls = true
  au.preload = 'none'                  // no se recorta hasta darle al play
  au.src = urlFragmento(a, b)
  if (ancho) au.style.width = ancho
  au.addEventListener('play', () => AU.pause())
  return au
}

function ventana (ini, total) {
  if (!(total > 0)) total = DUR
  if (total <= DUR) return [0, +total.toFixed(3)]
  const a = Math.min(Math.max(0, ini), total - DUR)
  return [+a.toFixed(3), +(a + DUR).toFixed(3)]
}

// ------------------------------------------------------------ anotaciones
async function crearDisf (o, t) {
  const [a, b] = ventana(t, o.dur)
  const d = {
    speaker: ACTUAL.sp, lectura: ACTUAL.num, sent_idx: o.i, tipo: TIPO,
    start_s: a, stop_s: b, origen: 'manual', nota: '', autor: AUTOR
  }
  o.disf.push(d)                       // se pinta ya, sin esperar al servidor
  ONDAS.get(o.i)?.dibuja()
  try {
    const [g] = await api('disfluencia', { method: 'POST', body: d, prefer: 'return=representation' })
    Object.assign(d, g)
    fila(o, d); seleccionar(o, d.id)
    if (o.estado === 'pendiente') ponerEstado(o, 'en_progreso')
  } catch {
    o.disf.splice(o.disf.indexOf(d), 1); ONDAS.get(o.i)?.dibuja()
  }
  pintarTabla(o)
}

const guardarDisf = d => api(`disfluencia?id=eq.${d.id}`, {
  method: 'PATCH', body: { tipo: d.tipo, start_s: d.start_s, nota: d.nota, autor: AUTOR }
}).then(() => { pintarTabla(ACTUAL.ora.find(x => x.i === d.sent_idx)) })

async function borrarDisf (o, d) {
  await api(`disfluencia?id=eq.${d.id}`, { method: 'DELETE' })
  o.disf.splice(o.disf.indexOf(d), 1)
  if (o.sel === d.id) o.sel = null
  pintarTabla(o); ONDAS.get(o.i)?.dibuja()
}

function seleccionar (o, id) {
  o.sel = id
  pintarTabla(o); ONDAS.get(o.i)?.dibuja()
}

function ponerEstado (o, e) {
  o.estado = e
  const c = o.card
  c.className = `ora ${e}`
  Object.entries(c.bots).forEach(([k, b]) => b.classList.toggle('act', k === e))
  api('estado', {
    method: 'POST', prefer: 'resolution=merge-duplicates',
    body: {
      speaker: ACTUAL.sp, lectura: ACTUAL.num, sent_idx: o.i,
      estado: e, nota: o.nota || '', autor: AUTOR, actualizado: new Date().toISOString()
    }
  })
}

// ------------------------------------------------------------------ tabla
const fila = (o, d) => {
  if (!d.tr) return
  d.tr.querySelector('input.t').value = d.start_s != null ? d.start_s.toFixed(2) : ''
  d.tr.querySelectorAll('input.t')[1].value = d.stop_s != null ? d.stop_s.toFixed(2) : ''
}

function pintarTabla (o) {
  if (!o || !o.card) return
  const tb = o.card.tbody
  tb.innerHTML = ''
  o.card.vacio.hidden = o.disf.length > 0
  for (const d of [...o.disf].sort((x, y) => (x.start_s ?? 0) - (y.start_s ?? 0))) {
    const tr = el('tr'); if (d.id === o.sel) tr.className = 'sel'
    const sel = el('select')
    for (const t of TIPOS) { const op = el('option', null, NOMBRE[t]); op.value = t; sel.append(op) }
    sel.value = d.tipo; sel.style.color = COLOR[d.tipo]
    sel.onchange = () => { d.tipo = sel.value; guardarDisf(d); ONDAS.get(o.i)?.dibuja() }

    const ini = el('input', 't'); ini.value = d.start_s != null ? d.start_s.toFixed(2) : ''
    const fin = el('input', 't'); fin.value = d.stop_s != null ? d.stop_s.toFixed(2) : ''
    fin.readOnly = true; fin.title = 'siempre inicio + 3 s'
    ini.onchange = () => {
      const [a, b] = ventana(parseFloat(ini.value) || 0, o.dur)
      d.start_s = a; d.stop_s = b
      guardarDisf(d); ONDAS.get(o.i)?.dibuja()
    }
    const pl = d.start_s == null ? el('span', 'tiempo', '—')
      : reproductor(o.a + d.start_s, o.a + d.stop_s, '230px')
    const nota = el('input', 'n'); nota.value = d.nota || ''
    let tn
    nota.oninput = () => { clearTimeout(tn); tn = setTimeout(() => { d.nota = nota.value; guardarDisf(d) }, 600) }
    const x = el('span', 'x', '✕'); x.onclick = ev => { ev.stopPropagation(); borrarDisf(o, d) }
    const org = el('span', 'tiempo', d.origen === 'auto_3s' ? `3 s #${d.clip3s}` : (d.autor || 'manual'))

    for (const nodo of [sel, ini, fin, pl, org, nota, x]) {
      const td = el('td'); td.append(nodo); tr.append(td)
    }
    tr.onclick = ev => { if (ev.target !== x) seleccionar(o, d.id) }
    tb.append(tr)
    d.tr = tr
  }
}

// ------------------------------------------------------------------ vistas
function miga (ps) {
  const m = $('#miga'); m.innerHTML = ''
  ps.forEach((p, i) => {
    if (i) m.append(el('span', 'sep', '/'))
    if (p.href) { const a = el('a', null, p.t); a.href = p.href; m.append(a) } else m.append(el('span', null, p.t))
  })
}

async function progreso (sp) {
  const filas = await api(`progreso?speaker=eq.${sp}&select=*`)
  const m = {}
  for (const f of filas) m[f.lectura] = f
  return m
}

async function vistaSpeakers () {
  miga([{ t: 'StutterES · anotador' }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, 'Hablantes'),
    el('div', 'sub', '5 hablantes · 100 lecturas cada uno · marcas de 3 s'))
  const g = el('div', 'rejilla sp'); v.append(g)
  for (const s of META.speakers) {
    const a = el('a', 'tarjeta'); a.href = `#/${s.id}`
    a.append(el('div', 'tit', s.id),
      el('div', 'met', `${s.lecturas.length} lecturas · ${s.n_audio} oraciones con audio`))
    const met = el('div', 'met', '…'); a.append(met)
    const b = el('div', 'barra'); const i = el('i'); b.append(i); a.append(b)
    g.append(a)
    progreso(s.id).then(p => {
      const hechas = Object.values(p).reduce((n, x) => n + x.completadas, 0)
      met.textContent = `${hechas} completadas`
      i.style.width = `${100 * hechas / Math.max(s.n_audio, 1)}%`
    }).catch(() => { met.textContent = 'sin conexión con el servidor' })
  }
}

async function vistaLecturas (sp) {
  const s = META.speakers.find(x => x.id === sp)
  if (!s) throw new Error('hablante desconocido')
  miga([{ t: 'Hablantes', href: '#/' }, { t: sp }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, sp), el('div', 'sub', `${s.lecturas.length} lecturas`))
  const g = el('div', 'rejilla lec'); v.append(g)
  const p = await progreso(sp).catch(() => ({}))
  for (const l of s.lecturas) {
    const a = el('a', 'tarjeta'); a.href = `#/${sp}/${l.num}`
    const x = p[l.num] || { completadas: 0, dudosas: 0 }
    a.append(el('div', 'tit', l.nombre),
      el('div', 'met', `${l.audio}/${l.n} con audio`),
      el('div', 'met', `${x.completadas} completadas${x.dudosas ? ` · ${x.dudosas} dudosas` : ''}`))
    const b = el('div', 'barra'); const i = el('i')
    i.style.width = `${100 * x.completadas / Math.max(l.audio, 1)}%`
    b.append(i); a.append(b); g.append(a)
  }
}

async function vistaLectura (sp, num) {
  const d = await (await fetch(`/data/${sp}/${String(num).padStart(3, '0')}.json`)).json()
  ACTUAL = d; FOCO = 0; ONDAS.clear(); ACTIVA = null
  AU.pause(); AU.src = urlAudio(d)

  const [disf, est] = await Promise.all([
    api(`disfluencia?speaker=eq.${sp}&lectura=eq.${num}&select=*`).catch(() => []),
    api(`estado?speaker=eq.${sp}&lectura=eq.${num}&select=*`).catch(() => [])
  ])
  const pd = {}, pe = {}
  for (const x of disf) (pd[x.sent_idx] = pd[x.sent_idx] || []).push(x)
  for (const x of est) pe[x.sent_idx] = x
  for (const o of d.ora) {
    o.disf = pd[o.i] || []
    o.estado = pe[o.i]?.estado || 'pendiente'
    o.nota = pe[o.i]?.nota || ''
    o.sel = null
  }

  miga([{ t: 'Hablantes', href: '#/' }, { t: sp, href: `#/${sp}` }, { t: d.nombre }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, `${sp} · ${d.nombre}`),
    el('div', 'sub', `${d.ora.length} oraciones · grabación ${d.epid}`))
  d.ora.forEach(o => v.append(tarjeta(o)))
  d.ora.forEach(o => { if (o.pk) pintarTabla(o) })
}

function tarjeta (o) {
  const c = el('div', `ora ${o.estado || 'pendiente'}${o.pk ? '' : ' sinaudio'}`)
  c.dataset.idx = o.i
  o.card = c
  c.addEventListener('mousedown', () => enfocar(o.i, false))

  const f = el('div', 'ofila')
  f.append(el('div', 'num', `#${o.i} · s${String(o.i).padStart(3, '0')}`))
  const tx = el('div', 'texto'); tx.textContent = o.txt
  if (o.asr) tx.append(el('div', 'asr', `asr: ${o.asr}`))
  f.append(tx); c.append(f)
  if (!o.pk) { c.append(el('div', 'vacio', 'Este hablante no tiene audio para esta oración.')); return c }

  const chips = el('div', 'chips'); chips.style.marginTop = '10px'
  c.bots = {}
  for (const [k, t] of [['pendiente', 'Pendiente'], ['en_progreso', 'En progreso'],
    ['completada', 'Completada'], ['dudosa', 'Dudosa']]) {
    const b = el('button', 'btn' + (o.estado === k ? ' act' : ''), t)
    b.onclick = () => ponerEstado(o, k); c.bots[k] = b; chips.append(b)
  }
  chips.append(el('span', 'tiempo', `${o.dur}s`))
  c.append(chips)

  const onda = new Onda(o)
  ONDAS.set(o.i, onda)
  const caja = el('div', 'onda'); caja.append(onda.cv); c.append(caja)
  requestAnimationFrame(() => onda.dibuja())

  const ctrl = el('div', 'ctrl')
  const play = el('button', 'btn', '▶ Reproducir'); play.onclick = () => alterna(o)
  const tm = el('span', 'tiempo', '0:00.00')
  c.tm = tm
  ctrl.append(play, tm)
  for (const vel of [0.5, 0.75, 1]) {
    const b = el('button', 'btn' + (vel === 1 ? ' act' : ''), `${vel}×`)
    b.onclick = () => {
      AU.playbackRate = vel
      ctrl.querySelectorAll('.btn').forEach(x => { if (x.textContent.endsWith('×')) x.classList.remove('act') })
      b.classList.add('act')
    }
    ctrl.append(b)
  }
  const tipos = el('div', 'tipos')
  for (const t of TIPOS) {
    const b = el('span', 'tp' + (t === TIPO ? ' on' : ''), NOMBRE[t])
    b.dataset.tipo = t
    if (t === TIPO) b.style.background = COLOR[t]
    b.onclick = () => ponerTipo(t)
    tipos.append(b)
  }
  ctrl.append(el('span', 'tiempo', '· tipo activo:'), tipos)
  c.append(ctrl)

  const s1 = el('div', 'sec')
  s1.append(el('h4', null, `Clips de 3 s ya anotados (${o.c3.length})`))
  if (!o.c3.length) s1.append(el('div', 'vacio', 'Ningún clip de 3 s cae dentro de esta oración.'))
  else {
    const tira = el('div', 'clips')
    for (const cl of o.c3) {
      const k = el('div', 'clip' + (cl.desc ? ' desc' : ''))
      const cab = el('div', 'cid')
      cab.append(el('span', null, `#${cl.id}`), el('span', null, `${cl.a.toFixed(1)}–${cl.b.toFixed(1)}s`))
      k.append(cab)
      k.append(reproductor(o.a + cl.a, o.a + cl.b))
      const lb = el('div', 'lbl')
      for (const l of cl.et) { const e2 = el('span', 'et', NOMBRE[l] || l); e2.style.background = COLOR[l] || '#5b6472'; lb.append(e2) }
      for (const l of cl.otras) lb.append(el('span', 'et gris', l))
      if (cl.desc) lb.append(el('span', 'et gris', 'descartada'))
      k.append(lb); tira.append(k)
    }
    s1.append(tira)
  }
  c.append(s1)

  const s2 = el('div', 'sec')
  const h = el('h4', null, 'Disfluencias marcadas')
  const add = el('button', 'btn', '+ marcar en el cursor')
  add.style.cssText = 'float:right;margin-top:-4px;font-size:12px'
  add.onclick = () => crearDisf(o, ACTIVA === o ? AU.currentTime - o.a : 0)
  h.append(add); s2.append(h)
  const tb = el('table', 'dis')
  tb.innerHTML = '<thead><tr><th>tipo</th><th>inicio</th><th>fin</th><th></th><th>origen</th><th>nota</th><th></th></tr></thead><tbody></tbody>'
  s2.append(tb)
  const vac = el('div', 'vacio', 'Sin marcas. Doble clic en la onda para poner una de 3 s.')
  s2.append(vac); c.append(s2)
  c.tbody = tb.querySelector('tbody'); c.vacio = vac

  const nota = el('textarea', 'nota'); nota.rows = 1
  nota.placeholder = 'Nota de la oración…'; nota.value = o.nota || ''
  let tn
  nota.oninput = () => { clearTimeout(tn); tn = setTimeout(() => { o.nota = nota.value; ponerEstado(o, o.estado) }, 600) }
  c.append(nota)
  return c
}

function ponerTipo (t) {
  TIPO = t
  document.querySelectorAll('.tp').forEach(b => {
    const on = b.dataset.tipo === t
    b.classList.toggle('on', on); b.style.background = on ? COLOR[t] : ''
  })
}

function enfocar (i, ir = true) {
  FOCO = i
  document.querySelectorAll('.ora').forEach(c => c.classList.toggle('foco', +c.dataset.idx === i))
  if (ir) document.querySelector(`.ora[data-idx="${i}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

addEventListener('keydown', ev => {
  if (!ACTUAL || ['INPUT', 'TEXTAREA', 'SELECT'].includes(ev.target.tagName)) return
  const o = ACTUAL.ora.find(x => x.i === FOCO)
  const con = ACTUAL.ora.filter(x => x.pk)
  if (ev.code === 'Space') { ev.preventDefault(); if (o) alterna(o); return }
  if (ev.key >= '1' && ev.key <= '5') return ponerTipo(TIPOS[+ev.key - 1])
  if (o && ev.key === 'c') return ponerEstado(o, 'completada')
  if (o && ev.key === 'p') return ponerEstado(o, 'pendiente')
  if (o && ev.key === 'd') return ponerEstado(o, 'dudosa')
  if (ev.key === 'j' || ev.key === 'k') {
    const i = con.findIndex(x => x.i === FOCO)
    const s = con[Math.min(con.length - 1, Math.max(0, i + (ev.key === 'j' ? 1 : -1)))]
    if (s) enfocar(s.i)
    return
  }
  if ((ev.key === 'Delete' || ev.key === 'Backspace') && o && o.sel) {
    const d = o.disf.find(x => x.id === o.sel)
    if (d) { ev.preventDefault(); borrarDisf(o, d) }
  }
})

// ------------------------------------------------------------------ router
async function ruta () {
  const p = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  try {
    if (!p.length) await vistaSpeakers()
    else if (p.length === 1) await vistaLecturas(p[0])
    else await vistaLectura(p[0], +p[1])
  } catch (e) {
    $('#vista').innerHTML = `<div class="vacio">${e.message}</div>`
    console.error(e)
  }
  scrollTo(0, 0)
}

function pedirAutor (forzar) {
  if (!AUTOR || forzar) {
    const n = prompt('¿Quién anota? (aparece junto a cada marca)', AUTOR || '')
    if (n != null) { AUTOR = n.trim(); localStorage.setItem('autor', AUTOR) }
  }
  $('#quien').textContent = AUTOR ? `👤 ${AUTOR}` : '👤 ponerme nombre'
}

;(async function arranca () {
  $('#bayuda').onclick = () => { const a = $('#ayuda'); a.hidden = !a.hidden }
  $('#ayuda').onclick = () => { $('#ayuda').hidden = true }
  $('#quien').onclick = () => pedirAutor(true)
  try {
    CFG = await (await fetch('/api/config')).json()
    META = await (await fetch('/data/meta.json')).json()
  } catch (e) {
    $('#vista').innerHTML = `<div class="vacio">No arranca: ${e.message}</div>`
    return
  }
  pedirAutor(false)
  addEventListener('hashchange', ruta)
  ruta()
})()
