const $ = id => document.getElementById(id);

const NOTIFY = { mock: 'จำลอง', sent: 'ส่งแล้ว', failed: 'ส่งไม่สำเร็จ', '': '—' };
const KIND = { fan: 'พัดลม', ai: 'AI → servo', pick: 'หยิบเสื้อ', estop: 'หยุดฉุกเฉิน',
               humidity: 'ความชื้น', gas: 'ก๊าซ', boot: 'เริ่มระบบ' };
const fmtTime = ts => new Date(Number(ts) * 1000).toLocaleTimeString('th-TH', { hour12: false });
const num = v => (v === '' || v === null || v === undefined) ? null : Number(v);
const show = (v, digits, unit) => {
  const n = num(v);
  return n === null || Number.isNaN(n) ? '—' : n.toFixed(digits) + (unit || '');
};

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') el.className = v; else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

let state = null;

/* ---------------------------------------------------------------- pages */

const PAGES = {
  wardrobe: ['สถานะตู้เสื้อผ้า', 'จำนวนครั้งที่แต่ละชุดถูกหยิบไปใส่'],
  system: ['ภาพรวมระบบ', 'เส้นทางข้อมูล เซนเซอร์ และการตัดสินใจบน gateway'],
  raw: ['Raw data', 'แถวดิบที่ไหลจาก gateway ขึ้น cloud แบบเรียลไทม์'],
};

function currentPage() {
  const m = location.hash.match(/^#\/([a-z]+)/);
  return (m && PAGES[m[1]]) ? m[1] : 'wardrobe';
}

function setPage(name) {
  document.querySelectorAll('.page').forEach(p => { p.hidden = p.id !== 'page-' + name; });
  document.querySelectorAll('.nav-btn').forEach(b => {
    const on = b.dataset.page === name;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  const [title, sub] = PAGES[name];
  $('pageTitle').textContent = title;
  $('pageSub').textContent = sub;
  document.title = 'WearWise: ' + title;
}

/* ------------------------------------------------------- drawer menu */

const drawer = $('drawer');
const backdrop = $('backdrop');
const menuBtn = $('menuBtn');

function setDrawer(open) {
  drawer.classList.toggle('open', open);
  drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
  menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  backdrop.hidden = !open;
  document.body.classList.toggle('drawer-open', open);
  if (open) $('closeBtn').focus();
}

menuBtn.addEventListener('click', () => setDrawer(!drawer.classList.contains('open')));
$('closeBtn').addEventListener('click', () => { setDrawer(false); menuBtn.focus(); });
backdrop.addEventListener('click', () => setDrawer(false));
drawer.querySelectorAll('.nav-btn').forEach(a => a.addEventListener('click', () => setDrawer(false)));
document.addEventListener('keydown', e => { if (e.key === 'Escape') setDrawer(false); });

window.addEventListener('hashchange', () => { setDrawer(false); setPage(currentPage()); });

/* เปิดหน้าแรกที่ /#/wardrobe เสมอเมื่อยังไม่มี hash */
if (!location.hash) history.replaceState(null, '', '#/wardrobe');
setPage(currentPage());

/* ------------------------------------------------------------- wardrobe */

function renderWardrobe(s) {
  const items = (s.wardrobe || []).slice()
    .sort((a, b) => (b.uses || 0) - (a.uses || 0) || String(a.name).localeCompare(String(b.name), 'th'));
  const used = items.filter(w => w.uses > 0);
  const total = items.reduce((sum, w) => sum + (w.uses || 0), 0);
  const top = used[0] || null;
  const max = Math.max(1, ...items.map(w => w.uses || 0));

  const stats = $('wardrobeSummary');
  stats.replaceChildren(
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'ชุดในตู้'),
      h('div', { class: 'v' }, items.length, h('small', {}, 'ชุด'))),
    h('div', { class: 'stat used' }, h('div', { class: 'k' }, 'ชุดที่ถูกหยิบแล้ว'),
      h('div', { class: 'v' }, used.length, h('small', {}, 'ชุด'))),
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'หยิบไปทั้งหมด'),
      h('div', { class: 'v' }, total, h('small', {}, 'ครั้ง'))),
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'ใส่บ่อยที่สุด'),
      h('div', { class: 'v', style: 'font-size:1.05rem;line-height:1.5' },
        top ? top.name : '—',
        top ? h('small', {}, ` ${top.uses} ครั้ง`) : null)),
  );

  $('cooldownNote').textContent = s.pick_cooldown_s
    ? `(cooldown ${s.pick_cooldown_s} วินาที)` : '';

  const box = $('wardrobe');
  box.replaceChildren();
  if (!items.length) {
    box.append(h('div', { class: 'empty' }, 'ยังไม่มีรายการเสื้อผ้าใน cloud'));
    return;
  }
  const grid = h('div', { class: 'closet' });
  items.forEach(w => {
    grid.append(h('article', { class: 'cloth ' + (w.uses > 0 ? 'used' : 'unused') },
      h('div', { class: 'cloth-top' },
        h('span', { class: 'cloth-cat' }, w.category || 'อื่น ๆ'),
        h('span', { class: 'cloth-tag' }, w.uses > 0 ? 'หยิบแล้ว' : 'ยังไม่ถูกหยิบ')),
      h('h4', {}, w.name),
      h('div', { class: 'cloth-count' },
        h('strong', {}, w.uses || 0), 'ครั้ง',
        w.uses === 1 ? '' : ''),
      h('div', { class: 'bar' },
        h('i', { style: `width:${Math.round((w.uses || 0) / max * 100)}%` })),
    ));
  });
  box.append(grid);
}

/* ------------------------------------------------------------- pipeline */

function aiText(s) {
  const ai = s.ai || {};
  const det = ai.detector || {};
  if (!ai.ok && det.backend === 'none') {
    return 'AI service ไม่พร้อม: ' + (det.error || ai.error || 'ตรวจ AI_URL และ dependencies');
  }
  const parts = [];
  if (det.model) parts.push(det.model);
  else if (det.backend) parts.push('detector: ' + det.backend);
  if (ai.classifier) parts.push('garment: ' + (ai.classifier.backend || '—'));
  return 'AI: ' + (parts.join(' · ') || 'ออนไลน์') + (ai.ok ? '' : ' (ไม่สมบูรณ์)');
}

function renderFlow(s) {
  const box = $('flow'); box.replaceChildren();
  const newer = s.rows && s.rows[0];
  const fresh = newer && (s.now - Number(newer.ts)) < 5;
  const nodeRow = (s.nodes || []).filter(n => n.role === 'sensor' && n.last)
    .sort((a, b) => Number(b.last.ts) - Number(a.last.ts))[0];
  const gwRow = s.gateway && s.gateway.last;
  const cloud = s.cloud || {};

  const stages = [
    ['Sensor node', nodeRow ? nodeRow.id : 'NA709',
      nodeRow ? `DHT22 ${show(nodeRow.last.temp, 1, ' °C')} · ${show(nodeRow.last.hum, 0, ' %')} · MQ-135 ${show(nodeRow.last.gas, 0)} · BH1750 ${show(nodeRow.last.lux, 0, ' lx')}`
              : 'ยังไม่ได้รับข้อมูลจาก node',
      nodeRow ? `แพ็กเก็ต #${nodeRow.last.seq} · RTT ${show(nodeRow.last.hop_ms, 1, ' ms')}` : ''],
    ['Gateway', gwRow ? (Number(gwRow.fan) ? 'พัดลมเปิด' : 'พัดลมปิด') : 'ไม่พร้อม',
      gwRow ? `${gwRow.note || '—'} · servo ${show(gwRow.servo, 0, '°')}` : 'ยังไม่มีการตัดสินใจ',
      gwRow ? `HC-SR04 ${show(gwRow.dist_cm, 0, ' cm')} · ${Number(gwRow.person) ? 'มีคนหน้าตู้' : 'ไม่มีคน'}` : ''],
    ['Cloud', cloud.backend || '—',
      `${cloud.rows || 0} แถว${cloud.detail ? ' · ' + cloud.detail : ''}`,
      newer ? `แถวล่าสุด #${newer.seq} ${fmtTime(newer.ts)}` : 'ยังไม่มีแถว'],
    ['Dashboard', 'อ่านทุก 2 วินาที',
      newer ? `ข้อมูลอายุ ${(s.now - Number(newer.ts)).toFixed(1)} วินาที` : 'รอข้อมูล',
      `เซนเซอร์ครบ ${s.sensor_types || 0} ชนิด`],
  ];

  const flow = h('div', { class: 'flow' });
  stages.forEach((n, i) => {
    if (i) flow.append(h('div', { class: 'link' }));
    flow.append(h('div', { class: 'node' + (fresh && i < 3 ? ' fresh' : '') },
      h('div', { class: 'stage' }, n[0]),
      h('div', { class: 'main' }, n[1]),
      h('div', { class: 'detail' }, n[2]),
      n[3] ? h('div', { class: 'detail' }, n[3]) : null));
  });
  box.append(flow);
}

function renderNodes(s) {
  const body = $('nodes'); body.replaceChildren();
  (s.nodes || []).forEach(n => {
    const r = n.last;
    let values = '—';
    if (r && n.role === 'sensor') {
      values = `${show(r.temp, 1, ' °C')} / ${show(r.hum, 0, ' %')}\n${show(r.gas, 0)} / ${show(r.lux, 0, ' lx')}`;
    } else if (r) {
      values = `${show(r.dist_cm, 0, ' cm')}\n${Number(r.person) ? 'มีคน' : 'ไม่มีคน'}`;
    }
    const pkt = r ? `#${r.seq} · ${n.age_s}s ที่แล้ว` : 'ไม่มีข้อมูล';
    body.append(h('tr', {},
      h('td', {}, h('strong', {}, n.id),
        h('span', { class: 'badge' + (n.online ? '' : ' off') }, n.online ? 'ออนไลน์' : 'ออฟไลน์'),
        h('span', { class: 'cat' }, ' ' + n.board)),
      h('td', {}, (n.sensors && n.sensors.length) ? n.sensors.join(', ') : '—'),
      h('td', { class: 'num' }, ...String(values).split('\n').map(line => h('div', {}, line))),
      h('td', { class: 'num' }, pkt)));
  });
  $('nodeHint').textContent =
    `รวม ${s.sensor_types || 0} ชนิด: node 3 ชนิด, gateway 2 ชนิด — ครบเกณฑ์ M1`;
}

function row(label, value, note, warn) {
  return h('div', { class: warn ? 'warn' : '' },
    h('span', { class: 'k' }, label),
    h('span', { class: 'v' }, value, note ? h('span', { class: 'n' }, note) : null));
}

function renderGateway(s) {
  const box = $('gateway'); box.replaceChildren();
  const r = s.gateway && s.gateway.last;
  const aiEvent = (s.events || []).find(e => e.kind === 'ai');
  if (!r) {
    box.append(h('div', { class: 'empty' }, 'ยังไม่มีข้อมูลจาก gateway — เปิดบอร์ดแล้วหรือยัง?'));
    $('estopBtn').disabled = true;
    return;
  }
  $('estopBtn').disabled = false;
  const fanOn = Number(r.fan) === 1;
  const servo = num(r.servo);
  const bar = h('div', { class: 'bar' });
  const fill = h('i');
  fill.style.width = (servo === null ? 0 : Math.max(0, Math.min(100, servo / 180 * 100))) + '%';
  bar.append(fill);
  const servoRange = s.servo || { min: 20, max: 160, safe: 90 };

  box.append(
    row('ระยะจาก HC-SR04', show(r.dist_cm, 0, ' cm'),
      Number(r.person) ? 'มีคนอยู่หน้ากล้อง' : 'ไม่มีคน', false),
    row('พัดลม', fanOn ? 'เปิด' : 'ปิด', r.note || '', fanOn),
    h('div', {},
      h('span', { class: 'k' }, 'มุม servo (จากผล AI)'),
      h('span', { class: 'v' }, servo === null ? '—' : servo + '°',
        h('span', { class: 'n' }, `ขอบเขต ${servoRange.min}°–${servoRange.max}° · มุมปลอดภัย ${servoRange.safe}°`)),
      bar),
    row('หยุดฉุกเฉิน', Number(r.estop) ? 'ทำงานอยู่' : 'ปกติ',
      Number(r.estop) ? 'พัดลมถูกตัด กล้องกลับมุมปลอดภัย' : '', Number(r.estop) === 1),
    row('ผล AI ล่าสุด', aiEvent ? aiEvent.text : 'ยังไม่มี',
      aiEvent ? fmtTime(aiEvent.ts) : 'AI ทำงานเมื่อมีคนหน้าตู้', false));
  $('aiLine').textContent = aiText(s);
}

function renderEvents(s) {
  const box = $('events'); box.replaceChildren();
  if (!s.events || !s.events.length) {
    box.append(h('div', { class: 'empty' }, 'ยังไม่มีเหตุการณ์ — gateway จะบันทึกเมื่อสั่งพัดลมหรือให้ AI หมุนกล้อง'));
    return;
  }
  s.events.forEach(e => {
    box.append(h('div', { class: 'msg' },
      h('div', {}, e.text),
      h('div', { class: 'meta' },
        `${fmtTime(e.ts)} · ${KIND[e.kind] || e.kind} · ${e.node_id}` +
        (e.notify ? ' · Discord: ' + (NOTIFY[e.notify] || e.notify) : ''))));
  });
}

/* ------------------------------------------------------------- raw data */

function renderRaw(s) {
  const rows = s.rows || [];
  const cloud = s.cloud || {};
  const newest = rows[0];
  const age = newest ? Math.max(0, s.now - Number(newest.ts)) : null;

  const live = $('rawLive');
  live.className = 'live' +
    (age === null ? ' off' : age < 6 ? ' on' : age < 30 ? ' stale' : ' off');
  $('rawLiveText').textContent = age === null
    ? 'ยังไม่มีข้อมูลไหลเข้า cloud'
    : (age < 6 ? 'กำลังรับข้อมูล · ' : 'ข้อมูลหยุดไหล · ') +
      `แถวล่าสุด ${fmtTime(newest.ts)} (${age.toFixed(1)} วินาทีที่แล้ว)`;

  $('rawStats').replaceChildren(
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'แถวทั้งหมด'),
      h('div', { class: 'v' }, cloud.rows || 0, h('small', {}, 'แถว'))),
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'backend'),
      h('div', { class: 'v', style: 'font-size:1rem;line-height:1.6' }, cloud.backend || '—',
        cloud.detail ? h('small', {}, cloud.detail) : null)),
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'รอเขียนลงชีต'),
      h('div', { class: 'v' }, cloud.pending || 0, h('small', {}, 'แถว'))),
    h('div', { class: 'stat' }, h('div', { class: 'k' }, 'แถวล่าสุด'),
      h('div', { class: 'v', style: 'font-size:1rem;line-height:1.6' },
        newest ? fmtTime(newest.ts) : '—',
        newest ? h('small', {}, ` #${newest.seq} · ${newest.node_id}`) : null)),
  );

  const body = $('rows'); body.replaceChildren();
  if (!rows.length) {
    body.append(h('tr', {}, h('td', { colspan: '7' }, 'ยังไม่มีแถวใน cloud')));
  } else {
    rows.forEach((r, i) => {
      const isGw = r.node_id === 'CB302';
      body.append(h('tr', { class: i === 0 ? 'fresh' : '' },
        h('td', { class: 'num' }, fmtTime(r.ts)),
        h('td', {}, h('strong', {}, r.node_id)),
        h('td', { class: 'num' }, isGw ? '—' : `${show(r.temp, 1, ' °C')} / ${show(r.hum, 0, ' %')}`),
        h('td', { class: 'num' }, isGw ? '—' : `${show(r.gas, 0)} / ${show(r.lux, 0, ' lx')}`),
        h('td', { class: 'num' }, isGw ? `${show(r.dist_cm, 0, ' cm')} ${Number(r.person) ? '· มีคน' : ''}` : '—'),
        h('td', { class: 'num' }, isGw ? `${Number(r.fan) ? 'ON' : 'off'} / ${show(r.servo, 0, '°')}` : '—'),
        h('td', {}, r.note || '')));
    });
  }
  $('cloudHint').textContent = `${cloud.backend || '—'}${cloud.detail ? ' · ' + cloud.detail : ''} · ${cloud.rows || 0} แถว` +
    (cloud.error ? ` · ${cloud.error}` : '');
}

/* ---------------------------------------------------------------- estop */

async function toggleEstop() {
  const current = state && state.gateway && state.gateway.last
    ? Number(state.gateway.last.estop) === 1 : false;
  const btn = $('estopBtn');
  btn.disabled = true;
  try {
    const r = await (await fetch('/api/estop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: !current }),
    })).json();
    $('estopNote').textContent = r.ok
      ? (r.estop ? 'หยุดฉุกเฉินทำงาน: พัดลมปิดแล้ว' : 'ปลดล็อกแล้ว')
      : 'ส่งคำสั่งไม่ได้: ' + (r.error || 'gateway ไม่ตอบ');
  } catch (e) {
    $('estopNote').textContent = 'ส่งคำสั่งไม่ได้: ' + e;
  }
  btn.disabled = false;
  tick();
}

$('estopBtn').addEventListener('click', toggleEstop);

/* ----------------------------------------------------------------- tick */

async function tick() {
  try {
    const res = await fetch('/api/state', { cache: 'no-store' });
    state = await res.json();

    const pill = $('status');
    if (!state.ok) {
      pill.className = 'pill bad';
      $('statusText').textContent = state.error || 'cloud ตอบไม่ได้';
      $('flow').replaceChildren(h('div', { class: 'empty' }, 'ยังโหลดข้อมูลไม่ได้: ' + (state.error || 'ไม่ทราบสาเหตุ')));
      $('wardrobeSummary').replaceChildren();
      $('wardrobe').replaceChildren(h('div', { class: 'empty' }, 'โหลดข้อมูลจาก cloud ไม่ได้'));
      return;
    }

    pill.className = 'pill' + (state.gateway.online ? ' on' : '');
    $('statusText').textContent = state.gateway.online
      ? 'gateway ออนไลน์'
      : (state.gateway.last ? 'gateway หยุดส่งข้อมูล' : 'ยังไม่พบ gateway');

    const estopOn = state.gateway.last ? Number(state.gateway.last.estop) === 1 : false;
    const btn = $('estopBtn');
    btn.className = 'btn' + (estopOn ? ' armed' : '');
    btn.textContent = estopOn ? 'ปลดล็อกหยุดฉุกเฉิน' : 'หยุดฉุกเฉิน';
    if (!state.gateway.last) $('estopNote').textContent = 'ยังไม่พบ gateway';

    renderWardrobe(state);
    renderFlow(state); renderNodes(state); renderGateway(state); renderEvents(state);
    renderRaw(state);
  } catch (e) {
    $('status').className = 'pill bad';
    $('statusText').textContent = 'เชื่อมต่อ dashboard server ไม่ได้';
  }
}

tick();
setInterval(tick, 2000);
