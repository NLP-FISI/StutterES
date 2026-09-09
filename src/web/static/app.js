import WaveSurfer from '/static/vendor/wavesurfer.esm.js'
import RegionsPlugin from '/static/vendor/regions.esm.js'

const $ = (s, e = document) => e.querySelector(s)
const el = (t, cls, txt) => { const n = document.createElement(t); if (cls) n.className = cls; if (txt != null) n.textContent = txt; return n }
const seg = s => s == null ? '—' : `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, '0')}`

const COLOR = {
  Prolongation: '#f2a541', Block: '#e5484d', SoundRep: '#8b5cf6',
  WordRep: '#2dd4bf', Interjection: '#f472b6', NoStutteredWords: '#5b6472'
}
const NOMBRE = {
  Prolongation: 'Prolongación', Block: 'Bloqueo', SoundRep: 'Rep. sonido',
  WordRep: 'Rep. palabra', Interjection: 'Interjección', NoStutteredWords: 'Sin tartamudeo'
}
const TIPOS = ['Prolongation', 'Block', 'SoundRep', 'WordRep', 'Interjection']
const DUR = 3      // todo clip que se saque dura exactamente 3 s

// Encaja un inicio suelto en una ventana de 3 s dentro del audio. Si la
// oracion dura menos de 3 s, la ventana es la oracion entera.
function ventana (ini, total) {
  if (!(total > 0)) total = DUR
  if (total <= DUR) return [0, total]
  const a = Math.min(Math.max(0, ini), total - DUR)
  return [+a.toFixed(3), +(a + DUR).toFixed(3)]
}

let META = null, ACTUAL = null, TIPO = 'Block', FOCO = 0
const WS = new Map()      // idx -> {ws, regions, mapa:Map(region->disfId)}

// -------------------------------------------------------------- red
const marca = (() => {
  const n = $('#guardado'); let t
  return estado => {
    n.textContent = estado === 'g' ? 'guardando…' : estado === 'ok' ? 'guardado ✓' : 'error'
    n.style.color = estado === 'err' ? 'var(--Block)' : ''
    clearTimeout(t); if (estado !== 'g') t = setTimeout(() => { n.textContent = '' }, 1600)
  }
})()

async function post (ruta, cuerpo) {
  marca('g')
  try {
    const r = await fetch(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) })
    const j = await r.json()
    if (j.error) throw new Error(j.error)
    marca('ok'); return j
  } catch (e) { marca('err'); console.error(e); return { error: String(e) } }
}
const get = async r => (await fetch(r)).json()

// -------------------------------------------------------------- vistas
function miga (partes) {
  const m = $('#miga'); m.innerHTML = ''
  partes.forEach((p, i) => {
    if (i) m.append(Object.assign(el('span', 'sep'), { textContent: '/' }))
    if (p.href) { const a = el('a', null, p.t); a.href = p.href; m.append(a) } else m.append(el('span', null, p.t))
  })
}

async function vistaSpeakers () {
  META = META || await get('/api/meta')
  miga([{ t: 'StutterES · anotador' }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, 'Hablantes'),
    el('div', 'sub', '5 hablantes · 100 lecturas cada uno · 1348 oraciones por hablante'))
  const g = el('div', 'rejilla sp')
  for (const s of META.speakers) {
    const a = el('a', 'tarjeta'); a.href = `#/${s.id}`
    a.append(el('div', 'tit', s.id),
      el('div', 'met', `${s.n_lecturas} lecturas · ${s.n_con_audio} oraciones con audio`),
      el('div', 'met', `${s.completadas} completadas`))
    const b = el('div', 'barra'); const i = el('i')
    i.style.width = `${100 * s.completadas / Math.max(s.n_con_audio, 1)}%`
    b.append(i); a.append(b); g.append(a)
  }
  v.append(g)
}

async function vistaLecturas (sp) {
  const d = await get(`/api/lecturas/${sp}`)
  miga([{ t: 'Hablantes', href: '#/' }, { t: sp }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, sp), el('div', 'sub', `${d.lecturas.length} lecturas`))
  const g = el('div', 'rejilla lec')
  for (const l of d.lecturas) {
    const a = el('a', 'tarjeta'); a.href = `#/${sp}/${l.num}`
    a.append(el('div', 'tit', l.nombre),
      el('div', 'met', `${l.n_con_audio}/${l.n_oraciones} con audio`),
      el('div', 'met', `${l.completadas} completadas${l.dudosas ? ` · ${l.dudosas} dudosas` : ''}`))
    const b = el('div', 'barra'); const i = el('i')
    i.style.width = `${100 * l.completadas / Math.max(l.n_con_audio, 1)}%`
    b.append(i); a.append(b); g.append(a)
  }
  v.append(g)
}

// -------------------------------------------------------------- lectura
async function vistaLectura (sp, num) {
  const d = await get(`/api/lectura/${sp}/${num}`)
  ACTUAL = d; FOCO = 0; WS.forEach(o => o.ws.destroy()); WS.clear()
  miga([{ t: 'Hablantes', href: '#/' }, { t: sp, href: `#/${sp}` }, { t: d.nombre }])
  const v = $('#vista'); v.innerHTML = ''
  v.append(el('h1', null, `${sp} · ${d.nombre}`),
    el('div', 'sub', `${d.oraciones.length} oraciones · grabación ${d.epid}`))
  d.oraciones.forEach(o => v.append(tarjetaOracion(o)))
  observarOndas()
}

function tarjetaOracion (o) {
  const c = el('div', `ora ${o.estado}${o.audio_url ? '' : ' sinaudio'}`)
  c.dataset.idx = o.idx
  c.addEventListener('mousedown', () => enfocar(o.idx, false))

  const fila = el('div', 'ofila')
  fila.append(el('div', 'num', `#${o.idx} · s${String(o.idx).padStart(3, '0')}`))
  const tx = el('div', 'texto'); tx.textContent = o.texto
  if (o.texto_asr) tx.append(el('div', 'asr', `asr: ${o.texto_asr}`))
  fila.append(tx)
  c.append(fila)

  if (!o.audio_url) {
    c.append(el('div', 'vacio', 'Este hablante no tiene audio para esta oración.'))
    return c
  }

  // ---- estado
  const chips = el('div', 'chips'); chips.style.marginTop = '10px'
  const bots = {}
  for (const [k, t] of [['pendiente', 'Pendiente'], ['en_progreso', 'En progreso'], ['completada', 'Completada'], ['dudosa', 'Dudosa']]) {
    const b = el('button', 'btn' + (o.estado === k ? ' act' : ''), t)
    b.onclick = () => ponerEstado(o, k)
    bots[k] = b; chips.append(b)
  }
  c._bots = bots
  chips.append(el('span', 'tiempo', `${o.dur_s}s · cobertura 3s ${(o.cobertura * 100).toFixed(0)}%`))
  c.append(chips)

  // ---- onda
  const onda = el('div', 'onda')
  onda.append(el('div', 'cargando', 'onda pendiente de cargar…'))
  onda.dataset.url = o.audio_url; onda.dataset.idx = o.idx
  c.append(onda)

  const ctrl = el('div', 'ctrl')
  const play = el('button', 'btn', '▶ Reproducir')
  play.onclick = () => { const w = WS.get(o.idx); if (w) w.ws.playPause() }
  const t = el('span', 'tiempo', '0:00.00')
  ctrl.append(play, t)
  for (const vel of [0.5, 0.75, 1]) {
    const b = el('button', 'btn' + (vel === 1 ? ' act' : ''), `${vel}×`)
    b.onclick = () => {
      const w = WS.get(o.idx); if (!w) return
      w.ws.setPlaybackRate(vel, false)
      ctrl.querySelectorAll('.btn').forEach(x => { if (x.textContent.endsWith('×')) x.classList.remove('act') })
      b.classList.add('act')
    }
    ctrl.append(b)
  }
  const tipos = el('div', 'tipos')
  for (const tp of TIPOS) {
    const b = el('span', 'tp' + (tp === TIPO ? ' on' : ''), NOMBRE[tp])
    b.dataset.tipo = tp
    if (tp === TIPO) b.style.background = COLOR[tp]
    b.onclick = () => ponerTipo(tp)
    tipos.append(b)
  }
  ctrl.append(el('span', 'tiempo', '· marcar como:'), tipos)
  c.append(ctrl)
  c._tiempo = t

  // ---- clips de 3 s
  const s1 = el('div', 'sec'); s1.append(el('h4', null, `Clips de 3 s anotados (${o.clips3s.length})`))
  if (!o.clips3s.length) s1.append(el('div', 'vacio', 'Ningún clip de 3 s cae dentro de esta oración.'))
  else {
    const tira = el('div', 'clips')
    for (const cl of o.clips3s) {
      const k = el('div', 'clip' + (cl.descartada ? ' desc' : ''))
      const cab = el('div', 'cid')
      cab.append(el('span', null, `#${cl.id}`), el('span', null, `${cl.rel_start.toFixed(1)}–${cl.rel_stop.toFixed(1)}s`))
      k.append(cab)
      const au = el('audio'); au.controls = true; au.preload = 'none'; au.src = cl.url
      k.append(au)
      const lb = el('div', 'lbl')
      for (const l of cl.labels) { const e2 = el('span', 'et', NOMBRE[l] || l); e2.style.background = COLOR[l] || '#5b6472'; lb.append(e2) }
      for (const l of cl.otras) lb.append(el('span', 'et gris', l))
      if (cl.descartada) lb.append(el('span', 'et gris', 'descartada'))
      k.append(lb); tira.append(k)
    }
    s1.append(tira)
  }
  c.append(s1)

  // ---- disfluencias
  const s2 = el('div', 'sec')
  const h = el('h4', null, 'Disfluencias')
  const add = el('button', 'btn', '+ añadir')
  add.style.cssText = 'float:right;margin-top:-4px;font-size:12px'
  add.onclick = () => {
    const w = WS.get(o.idx)
    if (!w) return crearDisf(o, null, null)
    const [a, b] = ventana(w.ws.getCurrentTime(), w.ws.getDuration())
    crearDisf(o, a, b)
  }
  h.append(add); s2.append(h)
  const tb = el('table', 'dis')
  tb.innerHTML = '<thead><tr><th>tipo</th><th>inicio</th><th>fin</th><th>origen</th><th>nota</th><th></th></tr></thead><tbody></tbody>'
  s2.append(tb)
  const vac = el('div', 'vacio', 'Sin disfluencias. Arrastra sobre la onda para marcar una.')
  s2.append(vac)
  c.append(s2)
  c._tbody = tb.querySelector('tbody'); c._vacio = vac

  const nota = el('textarea', 'nota'); nota.rows = 1
  nota.placeholder = 'Nota de la oración…'; nota.value = o.nota || ''
  let tn
  nota.oninput = () => { clearTimeout(tn); tn = setTimeout(() => guardarEstado(o, o.estado, nota.value), 500) }
  c.append(nota)

  c._ora = o
  o._card = c
  o.disfluencias.forEach(dd => filaDisf(o, dd))
  refrescarVacio(o)
  return c
}

function refrescarVacio (o) {
  o._card._vacio.hidden = o.disfluencias.length > 0
}

function ponerTipo (tp) {
  TIPO = tp
  WS.forEach(w => w.rearmar?.())
  document.querySelectorAll('.tp').forEach(b => {
    const on = b.dataset.tipo === tp
    b.classList.toggle('on', on)
    b.style.background = on ? COLOR[tp] : ''
  })
}

function ponerEstado (o, k) {
  o.estado = k
  const c = o._card
  c.className = `ora ${k}`
  Object.entries(c._bots).forEach(([kk, b]) => b.classList.toggle('act', kk === k))
  guardarEstado(o, k, c.querySelector('.nota').value)
}

function guardarEstado (o, estado, nota) {
  o.nota = nota
  return post('/api/estado', { speaker: ACTUAL.speaker, lectura: ACTUAL.num, sent_idx: o.idx, estado, nota })
}

// -------------------------------------------------------------- disfluencias
async function crearDisf (o, ini, fin, tipo = TIPO, pintar = true) {
  const d = { speaker: ACTUAL.speaker, lectura: ACTUAL.num, sent_idx: o.idx, tipo, start_s: ini, stop_s: fin, origen: 'manual', nota: '' }
  const r = await post('/api/disfluencia', d)
  if (r.error) return null
  d.id = r.id
  o.disfluencias.push(d)
  filaDisf(o, d)
  refrescarVacio(o)
  if (ini != null && pintar) pintarRegion(o, d)
  if (o.estado === 'pendiente') ponerEstado(o, 'en_progreso')
  return d
}

function filaDisf (o, d) {
  const tr = el('tr'); tr.dataset.id = d.id
  const sel = el('select')
  for (const t of TIPOS) { const op = el('option', null, NOMBRE[t]); op.value = t; sel.append(op) }
  sel.value = d.tipo
  sel.style.color = COLOR[d.tipo]
  sel.onchange = () => {
    d.tipo = sel.value; sel.style.color = COLOR[d.tipo]
    post('/api/disfluencia/editar', { id: d.id, tipo: d.tipo })
    const w = WS.get(o.idx); const r = w && [...w.mapa].find(([, id]) => id === d.id)
    if (r) r[0].setOptions({ color: COLOR[d.tipo] + '4d', content: NOMBRE[d.tipo] })
  }
  const ini = el('input', 't'); ini.value = d.start_s != null ? Number(d.start_s).toFixed(2) : ''
  const fin = el('input', 't'); fin.value = d.stop_s != null ? Number(d.stop_s).toFixed(2) : ''
  fin.readOnly = true; fin.title = 'siempre inicio + 3 s'
  ini.onchange = () => {
    if (ini.value === '') { d.start_s = d.stop_s = null } else {
      const w = WS.get(o.idx)
      const [a, b] = ventana(parseFloat(ini.value), w ? w.ws.getDuration() : o.dur_s)
      d.start_s = a; d.stop_s = b
    }
    ini.value = d.start_s != null ? d.start_s.toFixed(2) : ''
    fin.value = d.stop_s != null ? d.stop_s.toFixed(2) : ''
    post('/api/disfluencia/editar', { id: d.id, start_s: d.start_s, stop_s: d.stop_s })
    pintarRegion(o, d)
  }
  const nota = el('input', 'n'); nota.value = d.nota || ''
  let tn
  nota.oninput = () => { clearTimeout(tn); tn = setTimeout(() => { d.nota = nota.value; post('/api/disfluencia/editar', { id: d.id, nota: d.nota }) }, 500) }
  const x = el('span', 'x', '✕')
  x.onclick = () => borrarDisf(o, d)

  for (const [cont, nodo] of [[el('td'), sel], [el('td'), ini], [el('td'), fin],
    [el('td'), el('span', 'tiempo', d.origen === 'auto_3s' ? `3 s #${d.clip3s}` : 'manual')],
    [el('td'), nota], [el('td'), x]]) { cont.append(nodo); tr.append(cont) }

  tr.onclick = ev => { if (ev.target === x) return; seleccionar(o, d.id) }
  o._card._tbody.append(tr)
  d._tr = tr
}

async function borrarDisf (o, d) {
  await post('/api/disfluencia/borrar', { id: d.id })
  d._tr.remove()
  o.disfluencias.splice(o.disfluencias.indexOf(d), 1)
  const w = WS.get(o.idx)
  if (w) { for (const [r, id] of w.mapa) if (id === d.id) { w.mapa.delete(r); r.remove() } }
  refrescarVacio(o)
}

function seleccionar (o, id) {
  o._card._tbody.querySelectorAll('tr').forEach(t => t.classList.toggle('sel', +t.dataset.id === id))
  o._sel = id
}

function pintarRegion (o, d) {
  const w = WS.get(o.idx); if (!w) return
  for (const [r, id] of w.mapa) if (id === d.id) { w.mapa.delete(r); r.remove() }
  if (d.start_s == null || d.stop_s == null) return
  w.quieto = true
  const [a, b] = ventana(d.start_s, w.ws.getDuration())
  const r = w.regions.addRegion({
    start: a, end: b, color: COLOR[d.tipo] + '4d',
    content: NOMBRE[d.tipo], drag: true, resize: false
  })
  w.mapa.set(r, d.id)
  w.quieto = false
}

// -------------------------------------------------------------- ondas
function observarOndas () {
  const io = new IntersectionObserver(es => {
    for (const e of es) if (e.isIntersecting) { io.unobserve(e.target); montarOnda(e.target) }
  }, { rootMargin: '400px' })
  document.querySelectorAll('.onda[data-url]').forEach(n => io.observe(n))
}

function montarOnda (nodo) {
  const idx = +nodo.dataset.idx
  const o = ACTUAL.oraciones.find(x => x.idx === idx)
  const regions = RegionsPlugin.create()
  const ws = WaveSurfer.create({
    container: nodo, url: nodo.dataset.url, height: 80,
    waveColor: '#3c4454', progressColor: '#4c8dff',
    cursorColor: '#e6e8ec', cursorWidth: 1, normalize: true,
    plugins: [regions]
  })
  const w = { ws, regions, mapa: new Map(), quieto: false }
  WS.set(idx, w)

  ws.on('ready', () => {
    nodo.querySelector('.cargando')?.remove()
    w.rearmar = () => {
      w.soltar?.()
      w.soltar = regions.enableDragSelection({ color: COLOR[TIPO] + '4d' })
    }
    w.rearmar()
    o.disfluencias.forEach(d => pintarRegion(o, d))
  })
  ws.on('timeupdate', t => { if (o._card._tiempo) o._card._tiempo.textContent = seg(t) })
  ws.on('error', e => { const c = nodo.querySelector('.cargando'); if (c) c.textContent = 'no se pudo cargar el audio' ; console.error(e) })

  regions.on('region-created', async r => {
    if (w.quieto || w.mapa.has(r)) return
    const [a, b] = ventana(r.start, ws.getDuration())
    r.setOptions({ start: a, end: b, color: COLOR[TIPO] + '4d',
      content: NOMBRE[TIPO], resize: false })
    const d = await crearDisf(o, a, b, TIPO, false)
    if (!d) { r.remove(); return }
    w.mapa.set(r, d.id)
    seleccionar(o, d.id)
  })
  regions.on('region-updated', r => {
    const id = w.mapa.get(r); if (!id) return
    const d = o.disfluencias.find(x => x.id === id); if (!d) return
    const [a, b] = ventana(r.start, ws.getDuration())
    if (Math.abs(r.end - r.start - (b - a)) > 0.01 || Math.abs(r.start - a) > 0.01) {
      w.quieto = true; r.setOptions({ start: a, end: b }); w.quieto = false
    }
    d.start_s = a; d.stop_s = b
    d._tr.querySelectorAll('input.t')[0].value = d.start_s.toFixed(2)
    d._tr.querySelectorAll('input.t')[1].value = d.stop_s.toFixed(2)
    post('/api/disfluencia/editar', { id, start_s: d.start_s, stop_s: d.stop_s })
  })
  regions.on('region-clicked', (r, ev) => {
    ev.stopPropagation()
    const id = w.mapa.get(r); if (id) { seleccionar(o, id); enfocar(o.idx, false) }
    r.play()
  })
}

// -------------------------------------------------------------- foco y teclado
function enfocar (idx, ir = true) {
  FOCO = idx
  document.querySelectorAll('.ora').forEach(c => c.classList.toggle('foco', +c.dataset.idx === idx))
  if (ir) document.querySelector(`.ora[data-idx="${idx}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

document.addEventListener('keydown', ev => {
  if (!ACTUAL) return
  const t = ev.target.tagName
  if (t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') return
  const o = ACTUAL.oraciones.find(x => x.idx === FOCO)
  const conAudio = ACTUAL.oraciones.filter(x => x.audio_url)
  if (ev.code === 'Space') { ev.preventDefault(); WS.get(FOCO)?.ws.playPause(); return }
  if (ev.key >= '1' && ev.key <= '5') { ponerTipo(TIPOS[+ev.key - 1]); return }
  if (ev.key === 'c' && o) return ponerEstado(o, 'completada')
  if (ev.key === 'p' && o) return ponerEstado(o, 'pendiente')
  if (ev.key === 'd' && o) return ponerEstado(o, 'dudosa')
  if (ev.key === 'j' || ev.key === 'k') {
    const i = conAudio.findIndex(x => x.idx === FOCO)
    const s = conAudio[Math.min(conAudio.length - 1, Math.max(0, i + (ev.key === 'j' ? 1 : -1)))]
    if (s) enfocar(s.idx)
    return
  }
  if ((ev.key === 'Delete' || ev.key === 'Backspace') && o && o._sel) {
    const d = o.disfluencias.find(x => x.id === o._sel)
    if (d) { ev.preventDefault(); borrarDisf(o, d) }
  }
  if (ev.key === '?') $('#ayuda').hidden = !$('#ayuda').hidden
})

// -------------------------------------------------------------- router
async function ruta () {
  const p = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  try {
    if (p.length === 0) await vistaSpeakers()
    else if (p.length === 1) await vistaLecturas(p[0])
    else await vistaLectura(p[0], p[1])
  } catch (e) { $('#vista').innerHTML = `<div class="vacio">${e}</div>`; console.error(e) }
  window.scrollTo(0, 0)
}
addEventListener('hashchange', ruta)
ruta()

// botón de ayuda
const ba = el('button', 'btn', '?')
ba.id = 'toggleAyuda'
ba.onclick = () => { const a = $('#ayuda'); a.hidden = !a.hidden; ba.hidden = !a.hidden }
document.body.append(ba)
$('#ayuda').addEventListener('click', () => { $('#ayuda').hidden = true; ba.hidden = false })
