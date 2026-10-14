// BARKAV read-only dashboard prototype.
// Talks to Python only through window.pywebview.api (webui/bridge.py);
// every call returns {ok, data|error, meta}.  Data is inserted with
// textContent only - project fields can originate from Telegram text.
'use strict';

const numberFormat = new Intl.NumberFormat('fa-IR');
const timeFormat = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
});

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function amount(value, { sign = false } = {}) {
  const span = el('span', 'num');
  if (value === null || value === undefined || value === '') {
    span.textContent = '—';
    return span;
  }
  const n = Number(value);
  span.textContent = numberFormat.format(n);
  if (sign && n !== 0) span.classList.add(n > 0 ? 'pos' : 'neg');
  return span;
}

function count(value) {
  const span = el('span', 'num');
  span.textContent = value === null || value === undefined ? '—' : numberFormat.format(Number(value));
  return span;
}

// rows: [label, node]
function fillCard(id, rows) {
  const dl = $(id).querySelector('dl');
  dl.replaceChildren();
  for (const [label, node] of rows) {
    dl.append(el('dt', null, label));
    const dd = el('dd');
    dd.append(node);
    dl.append(dd);
  }
}

function kpi(label, value, opts) {
  const box = el('div', 'kpi');
  box.append(el('div', 'label', label));
  const v = el('div', 'value');
  v.append(amount(value, opts));
  v.append(el('span', 'unit', 'تومان'));
  box.append(v);
  return box;
}

function render(data) {
  const p = data.project || {};
  $('project-name').textContent = p.name || 'پروژه';
  $('project-address').textContent = [
    p.address,
    p.registration_plate && `پلاک ثبتی ${p.registration_plate}`,
    p.municipal_file_no && `پرونده شهرداری ${p.municipal_file_no}`,
  ].filter(Boolean).join('  |  ');

  const o = data.overview || {};
  const f = data.flows || {};
  $('kpis').replaceChildren(
    kpi('موجودی نقد', o.cash_balance, { sign: true }),
    kpi('هزینه ساخت', o.construction_cost),
    kpi('نقد آزاد پس از چک‌ها', o.free_cash_after_cheques, { sign: true }),
    kpi('مانده حساب مدیر', o.manager_balance),
    kpi('کل ورودی‌ها', f.total_in),
    kpi('کل خروجی‌ها', f.total_out),
  );

  const s = data.sales_30d || {};
  fillCard('card-sales', [
    ['فروش قراردادی', amount(s.contract_sales)],
    ['دریافتی از خریداران', amount(s.cash_received)],
    ['مطالبات', amount(s.receivable)],
    ['معوق', amount(s.overdue_amount)],
    ['سررسید ۳۰ روز آینده', amount(s.upcoming_amount)],
  ]);

  const l = data.liquidity_30d || {};
  // Same rows and labels as the Tk ۳۰ روز آینده dialog; values come
  // computed from liquidity_service - nothing is calculated here.
  fillCard('card-liquidity', [
    ['تعهدات ۳۰ روز', amount(l.commitments)],
    ['چک‌ها ۳۰ روز', amount(l.cheques)],
    ['اقساط ۳۰ روز', amount(l.installments)],
    ['مطالبات ۳۰ روز', amount(l.claims)],
    ['تراز مالی ۳۰ روز', amount(l.balance, { sign: true })],
    ['مانده نقدی', amount(l.cash, { sign: true })],
    ['نقدینگی مورد نیاز', amount(l.liquidity_needed, { sign: true })],
  ]);
  // Overdue schedule amounts are reported beside, not inside, the 30-day
  // figures above (they are not part of the balance).
  const liqList = $('card-liquidity').querySelector('dl');
  const overdueLabel = el('dt', 'separated', 'تعهدات معوق (خارج از محاسبه)');
  const overdueValue = el('dd', 'separated');
  const overdueAmount = amount(l.overdue_commitments);
  if (Number(l.overdue_commitments) > 0) overdueAmount.classList.add('warn-text');
  overdueValue.append(overdueAmount);
  liqList.append(overdueLabel, overdueValue);

  const loans = data.loans_30d || {};
  fillCard('card-loans', [
    ['اصل تسهیلات', amount(loans.principal)],
    ['پرداخت‌شده', amount(loans.paid)],
    ['مانده', amount(loans.remaining)],
    ['قسط ۳۰ روز آینده', amount(loans.upcoming_amount)],
  ]);

  const ch = data.cheques || {};
  fillCard('card-cheques', [
    ['تعداد کل چک‌های باز', count((ch.all || {}).count)],
    ['مبلغ کل', amount((ch.all || {}).amount)],
    ['تعداد ۳۰ روز آینده', count((ch.next_30d || {}).count)],
    ['مبلغ ۳۰ روز آینده', amount((ch.next_30d || {}).amount)],
  ]);

  const pending = data.pending;
  fillCard('card-pending', pending ? [
    ['کل', count(pending.total)],
    ['در دست بررسی', count(pending.review)],
    ['تاییدی', count(pending.approved)],
    ['رد شده', count(pending.rejected)],
  ] : [['وضعیت', el('span', 'warn-text', 'خوانده نشد')]]);

  const integrity = el('span', o.sqlite_integrity === 'ok' ? 'pos' : 'neg',
    o.sqlite_integrity === 'ok' ? 'سالم' : String(o.sqlite_integrity || '—'));
  const failed = count(o.failed_sync);
  if (Number(o.failed_sync) > 0) failed.classList.add('neg');
  fillCard('card-health', [
    ['سلامت دیتابیس', integrity],
    ['در صف همگام‌سازی', count(o.pending_sync)],
    ['همگام‌سازی ناموفق', failed],
    ['آخرین تطبیق بانک', el('span', null, o.bank_reconciled_shamsi || '—')],
  ]);

  const snap = data.snapshot || {};
  $('snapshot-time').textContent = snap.taken_at
    ? `کپی لحظه‌ای: ${timeFormat.format(new Date(snap.taken_at))}` : '';
  $('content').hidden = false;
}

function showStatus(text, isError) {
  const box = $('status');
  box.textContent = text || '';
  box.classList.toggle('error', Boolean(isError));
}

async function load(force) {
  const button = $('refresh');
  button.disabled = true;
  if (!force) showStatus('در حال خواندن داده‌ها…');
  try {
    const result = await window.pywebview.api.get_dashboard_summary(Boolean(force));
    if (!result || !result.ok) {
      const err = (result && result.error) || {};
      showStatus(`${err.message || 'خطای ناشناخته.'}${err.retryable ? ' دوباره «بروزرسانی» را بزنید.' : ''}`, true);
      return;
    }
    render(result.data);
    showStatus('');
  } catch (e) {
    showStatus('ارتباط با برنامه برقرار نشد.', true);
  } finally {
    button.disabled = false;
  }
}

async function start() {
  $('refresh').addEventListener('click', () => load(true));
  try {
    const info = await window.pywebview.api.get_app_info();
    if (info && info.ok) {
      $('footer').textContent = `نسخه ${info.data.app_version || '—'} · نمونهٔ آزمایشی pywebview · بدون ثبت یا تغییر داده`;
    }
  } catch (e) { /* footer is optional */ }
  load(false);
}

if (window.pywebview && window.pywebview.api) {
  start();
} else {
  window.addEventListener('pywebviewready', start, { once: true });
}
