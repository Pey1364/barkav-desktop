from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

try:
    import jdatetime  # type: ignore
except ModuleNotFoundError:  # local CI/test fallback; production may use jdatetime
    jdatetime = None

from .finance import FinanceDB, SCHEMA_VERSION, _id, _now


def _jalali_to_gregorian_parts(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 29 if (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def _gregorian_to_jalali_parts(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def normalize_shamsi(value: str | None) -> str:
    if not value:
        return ""
    s = str(value).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    s = s.replace("-", "/")
    parts = [p for p in s.split("/") if p != ""]
    if len(parts) != 3:
        return ""
    try:
        y, m, d = map(int, parts)
        if not (1200 <= y <= 1699 and 1 <= m <= 12):
            return ""
        max_day = 31 if m <= 6 else 30
        if not (1 <= d <= max_day):
            return ""
        # Conversion validates the date enough for our supported financial range.
        _jalali_to_gregorian_parts(y, m, d)
    except Exception:
        return ""
    return f"{y:04d}/{m:02d}/{d:02d}"


def shamsi_to_gregorian(value: str | None) -> str:
    s = normalize_shamsi(value)
    if not s:
        raise ValueError("تاریخ شمسی نامعتبر است")
    y, m, d = map(int, s.split("/"))
    if jdatetime is not None:
        g = jdatetime.date(y, m, d).togregorian()
        return g.isoformat()
    gy, gm, gd = _jalali_to_gregorian_parts(y, m, d)
    return date(gy, gm, gd).isoformat()


def gregorian_to_shamsi(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        d = date.fromisoformat(str(value)[:10])
    if jdatetime is not None:
        j = jdatetime.date.fromgregorian(date=d)
        return j.strftime("%Y/%m/%d")
    jy, jm, jd = _gregorian_to_jalali_parts(d.year, d.month, d.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _next_display_code(con, prefix: str, preferred: str = '') -> str:
    col={'U':'display_unit_id','P':'parking_display_id','S':'storage_display_id'}[prefix]
    used={str(r[0]).upper() for r in con.execute(f"SELECT {col} FROM units WHERE {col} IS NOT NULL AND TRIM({col})!=''").fetchall()}
    text=str(preferred or '').strip()
    if text.isdigit():
        cand=f'{prefix}-{int(text):03d}'
        if cand.upper() not in used:return cand
    import re as _re
    mx=0;pat=_re.compile(rf'^{prefix}-(\d+)$',_re.I)
    for v in used:
        m=pat.match(v)
        if m:mx=max(mx,int(m.group(1)))
    return f'{prefix}-{mx+1:03d}'


@dataclass(frozen=True)
class SaleSummary:
    sale_id: str
    unit_id: str
    buyer_name: str
    contract_amount: int
    cash_received: int
    matched_received: int
    receivable: int
    overdue_amount: int
    next_due_shamsi: str
    next_due_amount: int
    status: str


class RevenueService:
    """Stage 7 sale/receivable engine.

    Contractual revenue and cash are intentionally separate:
      * Sale/Installments = contractual receivable.
      * Transaction IN = real money entering petty cash.
      * Received payment starts UNMATCHED and only closes installments after an
        explicit user confirmation.
    """

    def __init__(self, db: FinanceDB):
        self.db = db
        self._migrate()

    def _migrate(self) -> None:
        with self.db.tx() as con:
            # Add fields without breaking older Stage 6 databases.
            cols = {r[1] for r in con.execute("PRAGMA table_info(sales)").fetchall()}
            if "buyer_phone" not in cols:
                con.execute("ALTER TABLE sales ADD COLUMN buyer_phone TEXT")
            if "notes" not in cols:
                con.execute("ALTER TABLE sales ADD COLUMN notes TEXT NOT NULL DEFAULT ''")

            cols = {r[1] for r in con.execute("PRAGMA table_info(installments)").fetchall()}
            if "sequence_no" not in cols:
                con.execute("ALTER TABLE installments ADD COLUMN sequence_no INTEGER")
            if "description" not in cols:
                con.execute("ALTER TABLE installments ADD COLUMN description TEXT NOT NULL DEFAULT ''")

            cols = {r[1] for r in con.execute("PRAGMA table_info(received_payments)").fetchall()}
            if "received_date_shamsi" not in cols:
                con.execute("ALTER TABLE received_payments ADD COLUMN received_date_shamsi TEXT")
            if "payer_name" not in cols:
                con.execute("ALTER TABLE received_payments ADD COLUMN payer_name TEXT")
            if "description" not in cols:
                con.execute("ALTER TABLE received_payments ADD COLUMN description TEXT NOT NULL DEFAULT ''")

            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS payment_allocations (
                    allocation_id TEXT PRIMARY KEY,
                    received_payment_id TEXT NOT NULL REFERENCES received_payments(received_payment_id),
                    installment_id TEXT NOT NULL REFERENCES installments(installment_id),
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    created_at TEXT NOT NULL,
                    UNIQUE(received_payment_id, installment_id)
                );
                CREATE INDEX IF NOT EXISTS idx_alloc_rp ON payment_allocations(received_payment_id);
                CREATE INDEX IF NOT EXISTS idx_alloc_installment ON payment_allocations(installment_id);
                """
            )
            con.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))

    # ---------- sale creation ----------
    def create_sale_bundle(
        self,
        *,
        project_name: str,
        block_name: str,
        unit_number: str,
        buyer_name: str,
        contract_date_shamsi: str,
        contract_amount: int,
        installments: Iterable[dict[str, Any]],
        floor: str = "",
        area: float | None = None,
        parking: str = "",
        storage: str = "",
        buyer_phone: str = "",
        contract_number: str = "",
        notes: str = "",
        source: str = "TELEGRAM",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        buyer_name = buyer_name.strip()
        unit_number = unit_number.strip()
        if not buyer_name or not unit_number:
            raise ValueError("نام خریدار و شماره واحد الزامی است")
        contract_amount = int(contract_amount)
        if contract_amount <= 0:
            raise ValueError("مبلغ قرارداد باید بیشتر از صفر باشد")
        sh_contract = normalize_shamsi(contract_date_shamsi)
        if not sh_contract:
            raise ValueError("تاریخ قرارداد شمسی معتبر نیست")
        g_contract = shamsi_to_gregorian(sh_contract)

        normalized_installments: list[dict[str, Any]] = []
        total = 0
        for i, item in enumerate(list(installments), start=1):
            amount = int(item.get("amount") or 0)
            sh_due = normalize_shamsi(item.get("due_date_shamsi"))
            if amount <= 0 or not sh_due:
                raise ValueError(f"قسط شماره {i} مبلغ/تاریخ معتبر ندارد")
            total += amount
            normalized_installments.append({
                "sequence_no": int(item.get("sequence_no") or i),
                "amount": amount,
                "due_date_shamsi": sh_due,
                "due_date": shamsi_to_gregorian(sh_due),
                "description": str(item.get("description") or f"قسط {i}").strip(),
            })
        if not normalized_installments:
            raise ValueError("حداقل یک قسط لازم است")
        if total != contract_amount:
            raise ValueError(
                f"جمع اقساط ({total:,}) با مبلغ قرارداد ({contract_amount:,}) برابر نیست"
            )

        now = _now()
        unit_id = _id("UNIT")
        sale_id = _id("SALE")
        installment_ids: list[str] = []
        with self.db.tx() as con:
            duplicate = con.execute(
                "SELECT unit_id,status FROM units WHERE COALESCE(project_name,'')=? AND COALESCE(block_name,'')=? AND unit_number=? AND status!='CANCELLED' LIMIT 1",
                (project_name.strip(), block_name.strip(), unit_number),
            ).fetchone()
            if duplicate:
                if str(duplicate['status']).upper() == 'SOLD':
                    raise ValueError("این واحد قبلاً فروخته شده است")
                unit_id = str(duplicate['unit_id'])
                existing=con.execute("SELECT display_unit_id,parking_display_id,storage_display_id FROM units WHERE unit_id=?",(unit_id,)).fetchone()
                du=(existing['display_unit_id'] if existing else None) or _next_display_code(con,'U',unit_number)
                dp=(existing['parking_display_id'] if existing else None) or (_next_display_code(con,'P',parking or unit_number) if parking.strip() else None)
                ds=(existing['storage_display_id'] if existing else None) or (_next_display_code(con,'S',storage or unit_number) if storage.strip() else None)
                con.execute(
                    "UPDATE units SET floor=COALESCE(NULLIF(?,''),floor), area=CASE WHEN ?>0 THEN ? ELSE area END, "
                    "parking=COALESCE(NULLIF(?,''),parking), storage=COALESCE(NULLIF(?,''),storage), display_unit_id=?,parking_display_id=?,storage_display_id=?, "
                    "status='SOLD',updated_at=? WHERE unit_id=?",
                    (floor.strip(), float(area or 0), float(area or 0), parking.strip(), storage.strip(), du,dp,ds,now, unit_id),
                )
            else:
                du=_next_display_code(con,'U',unit_number);dp=_next_display_code(con,'P',parking or unit_number) if parking.strip() else None;ds=_next_display_code(con,'S',storage or unit_number) if storage.strip() else None
                con.execute(
                    """INSERT INTO units(unit_id,project_name,block_name,unit_number,floor,area,parking,storage,status,created_at,updated_at,display_unit_id,parking_display_id,storage_display_id)
                       VALUES(?,?,?,?,?,?,?,?, 'SOLD', ?, ?,?,?,?)""",
                    (unit_id, project_name.strip(), block_name.strip(), unit_number, floor.strip(), area,
                     parking.strip(), storage.strip(), now, now,du,dp,ds),
                )
            con.execute(
                """INSERT INTO sales(sale_id,unit_id,buyer_name,contract_number,contract_date,contract_date_shamsi,
                   contract_amount,status,created_at,updated_at,buyer_phone,notes)
                   VALUES(?,?,?,?,?,?,?, 'ACTIVE', ?, ?, ?, ?)""",
                (sale_id, unit_id, buyer_name, contract_number.strip() or None, g_contract, sh_contract,
                 contract_amount, now, now, buyer_phone.strip() or None, notes.strip()),
            )
            for item in normalized_installments:
                ins_id = _id("INS")
                installment_ids.append(ins_id)
                con.execute(
                    """INSERT INTO installments(installment_id,sale_id,due_date,due_date_shamsi,amount,paid_amount,status,
                       created_at,updated_at,sequence_no,description)
                       VALUES(?,?,?,?,?,0,'UPCOMING',?,?,?,?)""",
                    (ins_id, sale_id, item["due_date"], item["due_date_shamsi"], item["amount"],
                     now, now, item["sequence_no"], item["description"]),
                )
            for et, eid in [("unit", unit_id), ("sale", sale_id)]:
                self.db._enqueue_sync(con, et, eid, "CREATE")
                self.db._audit(con, et, eid, "CREATE", source, after={"id": eid}, actor_id=actor_id)
            for iid in installment_ids:
                self.db._enqueue_sync(con, "installment", iid, "CREATE")
            self.db._audit(con, "sale", sale_id, "CREATE_INSTALLMENT_PLAN", source,
                           after={"contract_amount": contract_amount, "installments": normalized_installments}, actor_id=actor_id)

        self.refresh_installment_statuses(sale_id=sale_id)
        return {"unit_id": unit_id, "sale_id": sale_id, "installment_ids": installment_ids}

    def update_sale_metadata(self, sale_id: str, *, buyer_name: str | None = None, buyer_phone: str | None = None,
                             contract_number: str | None = None, contract_date_shamsi: str | None = None,
                             notes: str | None = None, source: str = 'GUI', actor_id: str | None = 'GUI') -> dict[str, Any]:
        with self.db.tx() as con:
            row = con.execute("SELECT * FROM sales WHERE sale_id=?", (sale_id,)).fetchone()
            if not row:
                raise KeyError(sale_id)
            before = dict(row); fields=[]; vals=[]
            if buyer_name is not None:
                val=str(buyer_name).strip()
                if not val: raise ValueError('نام خریدار الزامی است.')
                fields.append('buyer_name=?'); vals.append(val)
            if buyer_phone is not None:
                fields.append('buyer_phone=?'); vals.append(str(buyer_phone).strip() or None)
            if contract_number is not None:
                fields.append('contract_number=?'); vals.append(str(contract_number).strip() or None)
            if contract_date_shamsi is not None:
                sh=normalize_shamsi(contract_date_shamsi)
                if not sh: raise ValueError('تاریخ قرارداد شمسی معتبر نیست.')
                fields += ['contract_date_shamsi=?','contract_date=?']; vals += [sh,shamsi_to_gregorian(sh)]
            if notes is not None:
                fields.append('notes=?'); vals.append(str(notes).strip())
            if fields:
                fields.append('updated_at=?'); vals.append(_now()); vals.append(sale_id)
                con.execute(f"UPDATE sales SET {','.join(fields)} WHERE sale_id=?", vals)
            after=dict(con.execute("SELECT * FROM sales WHERE sale_id=?", (sale_id,)).fetchone())
            self.db._enqueue_sync(con, 'sale', sale_id, 'UPDATE')
            self.db._audit(con, 'sale', sale_id, 'UPDATE', source, before=before, after=after, actor_id=actor_id)
        return after

    def cancel_sale(self, sale_id: str, *, source: str = 'GUI', actor_id: str | None = 'GUI') -> None:
        with self.db.tx() as con:
            sale=con.execute("SELECT * FROM sales WHERE sale_id=?", (sale_id,)).fetchone()
            if not sale: raise KeyError(sale_id)
            received=int(con.execute("SELECT COALESCE(SUM(amount),0) FROM received_payments WHERE sale_id=? AND status!='CANCELLED'", (sale_id,)).fetchone()[0] or 0)
            if received:
                raise ValueError('برای لغو قرارداد، ابتدا وصول‌های ثبت‌شده این فروش باید تعیین تکلیف/لغو شوند.')
            before=dict(sale); now=_now()
            con.execute("UPDATE sales SET status='CANCELLED',updated_at=? WHERE sale_id=?", (now,sale_id))
            con.execute("UPDATE installments SET status='CANCELLED',updated_at=? WHERE sale_id=? AND status!='PAID'", (now,sale_id))
            con.execute("UPDATE units SET status='AVAILABLE',updated_at=? WHERE unit_id=? AND status='SOLD'", (now,sale['unit_id']))
            self.db._enqueue_sync(con,'sale',sale_id,'UPDATE')
            self.db._enqueue_sync(con,'unit',sale['unit_id'],'UPDATE')
            for r in con.execute("SELECT installment_id FROM installments WHERE sale_id=?", (sale_id,)).fetchall():
                self.db._enqueue_sync(con,'installment',r['installment_id'],'UPDATE')
                con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='INSTALLMENT' AND entity_id=? AND status='SCHEDULED'", (now,r['installment_id']))
            self.db._audit(con,'sale',sale_id,'CANCEL',source,before=before,after={'status':'CANCELLED'},actor_id=actor_id)

    # ---------- query ----------
    def list_sales(self, *, active_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        where = "WHERE s.status!='CANCELLED'" if active_only else ""
        with self.db.read() as con:
            rows = con.execute(
                f"""SELECT s.*,u.project_name,u.block_name,u.unit_number,u.floor,u.area,u.parking,u.storage
                    FROM sales s JOIN units u ON u.unit_id=s.unit_id {where}
                    ORDER BY s.contract_date DESC,s.sale_id DESC LIMIT ?""", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_sale(self, sale_id: str) -> Optional[dict[str, Any]]:
        with self.db.read() as con:
            row = con.execute(
                """SELECT s.*,u.project_name,u.block_name,u.unit_number,u.floor,u.area,u.parking,u.storage
                   FROM sales s JOIN units u ON u.unit_id=s.unit_id WHERE s.sale_id=?""", (sale_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_installment_details(self, installment_id: str, *, due_date_shamsi: str | None = None,
                                   amount: int | None = None, description: str | None = None,
                                   source: str = 'GUI', actor_id: str | None = 'GUI') -> dict[str, Any]:
        with self.db.tx() as con:
            row=con.execute("SELECT * FROM installments WHERE installment_id=?",(installment_id,)).fetchone()
            if not row: raise KeyError(installment_id)
            if str(row['status']).upper()=='CANCELLED': raise ValueError('قسط لغوشده قابل ویرایش نیست.')
            before=dict(row); fields=[];vals=[]
            if due_date_shamsi is not None:
                sh=normalize_shamsi(due_date_shamsi)
                if not sh: raise ValueError('تاریخ سررسید شمسی معتبر نیست.')
                fields += ['due_date_shamsi=?','due_date=?']; vals += [sh,shamsi_to_gregorian(sh)]
            if amount is not None:
                a=int(amount)
                if a<=0: raise ValueError('مبلغ قسط باید بیشتر از صفر باشد.')
                if a<int(row['paid_amount'] or 0): raise ValueError('مبلغ قسط نمی‌تواند از مبلغ پرداخت‌شده کمتر باشد.')
                fields.append('amount=?'); vals.append(a)
            if description is not None:
                fields.append('description=?'); vals.append(str(description).strip())
            if fields:
                now=_now();fields.append('updated_at=?');vals.append(now);vals.append(installment_id)
                con.execute(f"UPDATE installments SET {','.join(fields)} WHERE installment_id=?",vals)
                total=int(con.execute("SELECT COALESCE(SUM(amount),0) FROM installments WHERE sale_id=? AND status!='CANCELLED'",(row['sale_id'],)).fetchone()[0] or 0)
                con.execute("UPDATE sales SET contract_amount=?,updated_at=? WHERE sale_id=?",(total,now,row['sale_id']))
                after=dict(con.execute("SELECT * FROM installments WHERE installment_id=?",(installment_id,)).fetchone())
                self.db._enqueue_sync(con,'installment',installment_id,'UPDATE')
                self.db._enqueue_sync(con,'sale',row['sale_id'],'UPDATE')
                self.db._audit(con,'installment',installment_id,'UPDATE',source,before=before,after=after,actor_id=actor_id)
        self.refresh_installment_statuses(sale_id=str(row['sale_id']))
        self.ensure_installment_reminders(str(row['sale_id']))
        return self.get_installment(installment_id) or {}

    def cancel_installment(self, installment_id: str, *, source: str = 'GUI', actor_id: str | None = 'GUI') -> None:
        """Soft-cancel an unpaid sale installment and recompute the contract total.

        Paid/partially-paid installments are protected because cancelling them would
        orphan real cash allocations. Those must be corrected through the receipt
        workflow first.
        """
        with self.db.tx() as con:
            row=con.execute("SELECT * FROM installments WHERE installment_id=?",(installment_id,)).fetchone()
            if not row: raise KeyError(installment_id)
            if str(row['status']).upper()=='CANCELLED': return
            if int(row['paid_amount'] or 0)>0:
                raise ValueError('قسطی که پرداخت/تطبیق دارد قابل حذف نیست؛ ابتدا وصول مرتبط را تعیین تکلیف کن.')
            before=dict(row); now=_now(); sale_id=str(row['sale_id'])
            con.execute("UPDATE installments SET status='CANCELLED',updated_at=? WHERE installment_id=?",(now,installment_id))
            total=int(con.execute("SELECT COALESCE(SUM(amount),0) FROM installments WHERE sale_id=? AND status!='CANCELLED'",(sale_id,)).fetchone()[0] or 0)
            if total<=0:
                raise ValueError('قرارداد باید حداقل یک قسط فعال داشته باشد.')
            con.execute("UPDATE sales SET contract_amount=?,updated_at=? WHERE sale_id=?",(total,now,sale_id))
            con.execute("UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='INSTALLMENT' AND entity_id=? AND status='SCHEDULED'",(now,installment_id))
            self.db._enqueue_sync(con,'installment',installment_id,'UPDATE')
            self.db._enqueue_sync(con,'sale',sale_id,'UPDATE')
            self.db._audit(con,'installment',installment_id,'CANCEL',source,before=before,after={'status':'CANCELLED','sale_id':sale_id,'contract_amount':total},actor_id=actor_id)

    def list_installments(self, sale_id: str, *, include_cancelled: bool = False) -> list[dict[str, Any]]:
        where = "" if include_cancelled else "AND status!='CANCELLED'"
        with self.db.read() as con:
            rows = con.execute(
                f"SELECT * FROM installments WHERE sale_id=? {where} ORDER BY COALESCE(sequence_no,999999),due_date,installment_id",
                (sale_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def sale_summary(self, sale_id: str) -> SaleSummary:
        self.refresh_installment_statuses(sale_id=sale_id)
        sale = self.get_sale(sale_id)
        if not sale:
            raise KeyError(sale_id)
        with self.db.read() as con:
            rp = con.execute(
                "SELECT COALESCE(SUM(amount),0) v FROM received_payments WHERE sale_id=? AND status!='CANCELLED'",
                (sale_id,),
            ).fetchone()["v"]
            matched = con.execute(
                """SELECT COALESCE(SUM(a.amount),0) v FROM payment_allocations a
                   JOIN received_payments r ON r.received_payment_id=a.received_payment_id
                   WHERE r.sale_id=? AND r.status!='CANCELLED'""", (sale_id,),
            ).fetchone()["v"]
            overdue = con.execute(
                "SELECT COALESCE(SUM(amount-paid_amount),0) v FROM installments WHERE sale_id=? AND status!='CANCELLED' AND due_date<? AND paid_amount<amount",
                (sale_id, date.today().isoformat()),
            ).fetchone()["v"]
            next_row = con.execute(
                """SELECT due_date_shamsi,(amount-paid_amount) remain FROM installments
                   WHERE sale_id=? AND status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') AND amount>paid_amount
                   ORDER BY due_date,COALESCE(sequence_no,999999) LIMIT 1""", (sale_id,),
            ).fetchone()
        return SaleSummary(
            sale_id=sale_id,
            unit_id=str(sale["unit_id"]),
            buyer_name=str(sale["buyer_name"]),
            contract_amount=int(sale["contract_amount"]),
            cash_received=int(rp or 0),
            matched_received=int(matched or 0),
            receivable=max(0, int(sale["contract_amount"]) - int(rp or 0)),
            overdue_amount=int(overdue or 0),
            next_due_shamsi=str(next_row["due_date_shamsi"] if next_row else ""),
            next_due_amount=int(next_row["remain"] if next_row else 0),
            status=str(sale["status"]),
        )

    # ---------- cash receipt + explicit matching ----------
    def record_received_payment(
        self,
        *,
        sale_id: str,
        amount: int,
        received_date_shamsi: str,
        payer_name: str = "",
        description: str = "",
        source: str = "TELEGRAM",
        actor_id: str | None = None,
    ) -> dict[str, str]:
        sale = self.get_sale(sale_id)
        if not sale or sale.get("status") == "CANCELLED":
            raise ValueError("فروش فعال پیدا نشد")
        amount = int(amount)
        if amount <= 0:
            raise ValueError("مبلغ وصول باید بیشتر از صفر باشد")
        sh_date = normalize_shamsi(received_date_shamsi)
        if not sh_date:
            raise ValueError("تاریخ وصول شمسی معتبر نیست")
        g_date = shamsi_to_gregorian(sh_date)
        now = _now()
        tx_id = _id("TX")
        rp_id = _id("RCV")
        payer = payer_name.strip() or str(sale["buyer_name"])
        desc = description.strip() or f"وصول از خریدار {sale['buyer_name']}"
        with self.db.tx() as con:
            con.execute(
                """INSERT INTO transactions(transaction_id,event_date,shamsi_date,event_time,direction,amount,category,
                   payer_name,receiver_name,description,source_type,telegram_chat_id,telegram_message_id,expense_id,sale_id,
                   loan_id,status,sync_status,created_at,updated_at,deleted_at)
                   VALUES(?,?,?,?, 'IN',?,'BUYER_PAYMENT',?,NULL,?,?,NULL,NULL,NULL,?,NULL,'POSTED','PENDING',?,?,NULL)""",
                (tx_id, g_date, sh_date, datetime.now().strftime("%H:%M:%S"), amount, payer, desc, source, sale_id, now, now),
            )
            con.execute(
                """INSERT INTO received_payments(received_payment_id,sale_id,transaction_id,amount,received_date,status,
                   created_at,updated_at,received_date_shamsi,payer_name,description)
                   VALUES(?,?,?,?,?,'UNMATCHED',?,?,?,?,?)""",
                (rp_id, sale_id, tx_id, amount, g_date, now, now, sh_date, payer, desc),
            )
            self.db._enqueue_sync(con, "transaction", tx_id, "CREATE")
            self.db._enqueue_sync(con, "received_payment", rp_id, "CREATE")
            self.db._audit(con, "received_payment", rp_id, "CREATE_UNMATCHED", source,
                           after={"sale_id": sale_id, "amount": amount}, actor_id=actor_id)
        return {"received_payment_id": rp_id, "transaction_id": tx_id}

    def get_received_payment(self, received_payment_id: str) -> Optional[dict[str, Any]]:
        with self.db.read() as con:
            row = con.execute(
                """SELECT r.*,s.buyer_name,u.unit_number,u.block_name,u.project_name
                   FROM received_payments r JOIN sales s ON s.sale_id=r.sale_id
                   JOIN units u ON u.unit_id=s.unit_id WHERE r.received_payment_id=?""",
                (received_payment_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_unmatched_receipts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.read() as con:
            rows = con.execute(
                """SELECT r.*,s.buyer_name,u.unit_number,u.block_name FROM received_payments r
                   JOIN sales s ON s.sale_id=r.sale_id JOIN units u ON u.unit_id=s.unit_id
                   WHERE r.status='UNMATCHED' ORDER BY r.received_date,r.created_at LIMIT ?""", (int(limit),)
            ).fetchall()
        return [dict(r) for r in rows]

    def suggest_fifo_allocations(self, received_payment_id: str) -> dict[str, Any]:
        """Read-only FIFO allocation preview. No installment is changed here."""
        rp = self.get_received_payment(received_payment_id)
        if not rp:
            raise KeyError(received_payment_id)
        if rp["status"] == "CANCELLED":
            raise ValueError("وصول لغو شده است")
        sale_id = str(rp["sale_id"])
        self.refresh_installment_statuses(sale_id=sale_id)
        with self.db.read() as con:
            already = int(con.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payment_allocations WHERE received_payment_id=?",
                (received_payment_id,),
            ).fetchone()[0])
            rows = con.execute(
                """SELECT * FROM installments WHERE sale_id=? AND status!='CANCELLED' AND paid_amount<amount
                   ORDER BY due_date,COALESCE(sequence_no,999999),installment_id""",
                (sale_id,),
            ).fetchall()
        remaining = max(0, int(rp["amount"]) - already)
        suggestions: list[dict[str, Any]] = []
        for row in rows:
            if remaining <= 0:
                break
            due = int(row["amount"]) - int(row["paid_amount"])
            take = min(remaining, due)
            if take <= 0:
                continue
            suggestions.append({
                "installment_id": row["installment_id"],
                "sequence_no": row["sequence_no"],
                "due_date_shamsi": row["due_date_shamsi"],
                "installment_amount": int(row["amount"]),
                "already_paid": int(row["paid_amount"]),
                "allocate": int(take),
            })
            remaining -= take
        return {
            "sale_id": sale_id,
            "receipt_amount": int(rp["amount"]),
            "already_allocated": already,
            "allocations": suggestions,
            "unallocated": remaining,
        }

    def match_receipt_fifo(self, received_payment_id: str, *, source: str = "TELEGRAM", actor_id: str | None = None) -> dict[str, Any]:
        rp = self.get_received_payment(received_payment_id)
        if not rp:
            raise KeyError(received_payment_id)
        if rp["status"] == "CANCELLED":
            raise ValueError("وصول لغو شده است")
        if rp["status"] == "MATCHED":
            with self.db.read() as con:
                allocated = con.execute(
                    "SELECT COALESCE(SUM(amount),0) v FROM payment_allocations WHERE received_payment_id=?",
                    (received_payment_id,),
                ).fetchone()["v"]
            return {"allocated": int(allocated), "unallocated": max(0, int(rp["amount"]) - int(allocated)), "changed": False}

        sale_id = str(rp["sale_id"])
        self.refresh_installment_statuses(sale_id=sale_id)
        now = _now()
        remaining = int(rp["amount"])
        allocations: list[tuple[str, int]] = []
        with self.db.tx() as con:
            # Re-check inside the write transaction.
            existing = con.execute(
                "SELECT COALESCE(SUM(amount),0) v FROM payment_allocations WHERE received_payment_id=?",
                (received_payment_id,),
            ).fetchone()["v"]
            remaining -= int(existing or 0)
            rows = con.execute(
                """SELECT * FROM installments WHERE sale_id=? AND status!='CANCELLED' AND paid_amount<amount
                   ORDER BY due_date,COALESCE(sequence_no,999999),installment_id""", (sale_id,),
            ).fetchall()
            for row in rows:
                if remaining <= 0:
                    break
                due = int(row["amount"]) - int(row["paid_amount"])
                take = min(remaining, due)
                if take <= 0:
                    continue
                allocation_id = _id("ALLOC")
                con.execute(
                    "INSERT INTO payment_allocations(allocation_id,received_payment_id,installment_id,amount,created_at) VALUES(?,?,?,?,?)",
                    (allocation_id, received_payment_id, row["installment_id"], take, now),
                )
                new_paid = int(row["paid_amount"]) + take
                new_status = "PAID" if new_paid >= int(row["amount"]) else "PARTIALLY_PAID"
                con.execute(
                    "UPDATE installments SET paid_amount=?,status=?,updated_at=? WHERE installment_id=?",
                    (new_paid, new_status, now, row["installment_id"]),
                )
                self.db._enqueue_sync(con, "installment", row["installment_id"], "UPDATE")
                allocations.append((row["installment_id"], take))
                remaining -= take
            status = "MATCHED" if remaining == 0 else "UNMATCHED"
            con.execute("UPDATE received_payments SET status=?,updated_at=? WHERE received_payment_id=?", (status, now, received_payment_id))
            self.db._enqueue_sync(con, "received_payment", received_payment_id, "UPDATE")
            self.db._audit(con, "received_payment", received_payment_id, "MATCH_FIFO", source,
                           after={"allocations": allocations, "unallocated": remaining}, actor_id=actor_id)
        for installment_id, _ in allocations:
            self.cancel_future_installment_reminders(installment_id)
        self.refresh_sale_completion(sale_id)
        return {"allocated": int(rp["amount"]) - remaining, "unallocated": remaining, "changed": bool(allocations), "allocations": allocations}

    def get_installment(self, installment_id: str) -> Optional[dict[str, Any]]:
        with self.db.read() as con:
            row = con.execute(
                """SELECT i.*,s.buyer_name,u.unit_number,u.block_name,u.project_name
                   FROM installments i JOIN sales s ON s.sale_id=i.sale_id
                   JOIN units u ON u.unit_id=s.unit_id WHERE i.installment_id=?""",
                (installment_id,),
            ).fetchone()
        return dict(row) if row else None

    def cancel_unmatched_receipt(self, received_payment_id: str, *, source: str = "TELEGRAM", actor_id: str | None = None) -> bool:
        """Cancel a receipt only while it has no installment allocations.

        This voids the linked cash IN transaction so petty cash is recalculated
        from the ledger instead of being directly adjusted.
        """
        rp = self.get_received_payment(received_payment_id)
        if not rp:
            raise KeyError(received_payment_id)
        if rp["status"] == "CANCELLED":
            return False
        with self.db.tx() as con:
            allocated = int(con.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payment_allocations WHERE received_payment_id=?",
                (received_payment_id,),
            ).fetchone()[0])
            if allocated:
                raise ValueError("وصولی که به قسط تخصیص داده شده باید از مسیر اصلاح/برگشت تخصصی اصلاح شود")
            now = _now()
            con.execute("UPDATE received_payments SET status='CANCELLED',updated_at=? WHERE received_payment_id=?", (now, received_payment_id))
            con.execute("UPDATE transactions SET status='VOIDED',deleted_at=?,updated_at=?,sync_status='PENDING' WHERE transaction_id=?",
                        (now, now, rp["transaction_id"]))
            self.db._enqueue_sync(con, "received_payment", received_payment_id, "UPDATE")
            self.db._enqueue_sync(con, "transaction", rp["transaction_id"], "UPDATE")
            self.db._audit(con, "received_payment", received_payment_id, "CANCEL_UNMATCHED", source,
                           before={"amount": rp["amount"]}, after={"status": "CANCELLED"}, actor_id=actor_id)
        return True

    # ---------- installment state/reminders ----------
    def refresh_installment_statuses(self, *, sale_id: str | None = None, today: date | None = None) -> int:
        today = today or date.today()
        changed = 0
        now = _now()
        with self.db.tx() as con:
            sql = "SELECT * FROM installments WHERE status!='CANCELLED'"
            params: tuple[Any, ...] = ()
            if sale_id:
                sql += " AND sale_id=?"
                params = (sale_id,)
            for row in con.execute(sql, params).fetchall():
                amount, paid = int(row["amount"]), int(row["paid_amount"])
                due = date.fromisoformat(row["due_date"])
                if paid >= amount:
                    status = "PAID"
                elif paid > 0:
                    # Keep the payment state explicit even after the due date.
                    # Overdue amount is derived from due_date + remaining amount,
                    # so PARTIALLY_PAID can coexist conceptually with overdue debt.
                    status = "PARTIALLY_PAID"
                elif due < today:
                    status = "OVERDUE"
                elif due == today:
                    status = "DUE"
                else:
                    status = "UPCOMING"
                if status != row["status"]:
                    con.execute("UPDATE installments SET status=?,updated_at=? WHERE installment_id=?", (status, now, row["installment_id"]))
                    self.db._enqueue_sync(con, "installment", row["installment_id"], "UPDATE")
                    changed += 1
        return changed

    def refresh_sale_completion(self, sale_id: str) -> None:
        with self.db.tx() as con:
            sale = con.execute("SELECT * FROM sales WHERE sale_id=?", (sale_id,)).fetchone()
            if not sale or sale["status"] == "CANCELLED":
                return
            open_row = con.execute(
                "SELECT 1 FROM installments WHERE sale_id=? AND status!='CANCELLED' AND paid_amount<amount LIMIT 1",
                (sale_id,),
            ).fetchone()
            status = "ACTIVE" if open_row else "COMPLETED"
            if status != sale["status"]:
                con.execute("UPDATE sales SET status=?,updated_at=? WHERE sale_id=?", (status, _now(), sale_id))
                self.db._enqueue_sync(con, "sale", sale_id, "UPDATE")

    def ensure_installment_reminders(
        self,
        installment_id: str,
        *,
        reminder_time: str = "09:00",
        days_before: int = 3,
        days_after: int = 7,
        telegram: bool = True,
        email: bool = False,
    ) -> int:
        with self.db.read() as con:
            row = con.execute("SELECT * FROM installments WHERE installment_id=?", (installment_id,)).fetchone()
        if not row or row["status"] in {"PAID", "CANCELLED"}:
            return 0
        hh, mm = map(int, reminder_time.split(":"))
        due = date.fromisoformat(row["due_date"])
        slots: list[date] = [due - timedelta(days=days_before), due]
        slots.extend(due + timedelta(days=i) for i in range(1, days_after + 1))
        created = 0
        now = _now()
        with self.db.tx() as con:
            for d in slots:
                scheduled = datetime(d.year, d.month, d.day, hh, mm).isoformat(timespec="seconds")
                exists = con.execute(
                    "SELECT reminder_id FROM reminders WHERE entity_type='INSTALLMENT' AND entity_id=? AND scheduled_at=?",
                    (installment_id, scheduled),
                ).fetchone()
                if exists:
                    continue
                con.execute(
                    """INSERT INTO reminders(reminder_id,entity_type,entity_id,scheduled_at,channel_telegram,channel_email,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,'SCHEDULED',?,?)""",
                    (_id("REM"), "INSTALLMENT", installment_id, scheduled, int(bool(telegram)), int(bool(email)), now, now),
                )
                created += 1
        return created

    def ensure_all_open_installment_reminders(self, *, reminder_time: str = "09:00", days_before: int = 3, days_after: int = 7, telegram: bool = True, email: bool = False) -> int:
        self.refresh_installment_statuses()
        with self.db.read() as con:
            ids = [r[0] for r in con.execute("SELECT installment_id FROM installments WHERE status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') AND paid_amount<amount").fetchall()]
        return sum(self.ensure_installment_reminders(i, reminder_time=reminder_time, days_before=days_before, days_after=days_after, telegram=telegram, email=email) for i in ids)

    def get_due_installment_reminders(self, now_iso: str | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
        now_iso = now_iso or datetime.now().isoformat(timespec="seconds")
        with self.db.read() as con:
            rows = con.execute(
                """SELECT r.*,i.sale_id,i.due_date_shamsi,i.amount installment_amount,i.paid_amount,i.status installment_status,
                          s.buyer_name,u.unit_number,u.block_name,u.project_name
                   FROM reminders r JOIN installments i ON i.installment_id=r.entity_id
                   JOIN sales s ON s.sale_id=i.sale_id JOIN units u ON u.unit_id=s.unit_id
                   WHERE r.entity_type='INSTALLMENT' AND r.status='SCHEDULED' AND r.scheduled_at<=?
                     AND i.status IN ('UPCOMING','DUE','PARTIALLY_PAID','OVERDUE') AND i.paid_amount<i.amount
                   ORDER BY r.scheduled_at,r.reminder_id LIMIT ?""", (now_iso, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale_installment_reminders(self, before_iso: str) -> int:
        """Cancel old unsent buyer reminder slots to avoid a flood after downtime."""
        with self.db.tx() as con:
            cur = con.execute(
                "UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='INSTALLMENT' AND status='SCHEDULED' AND scheduled_at<?",
                (_now(), before_iso),
            )
            return int(cur.rowcount or 0)

    def cancel_future_installment_reminders(self, installment_id: str) -> int:
        with self.db.read() as con:
            row = con.execute("SELECT status,paid_amount,amount FROM installments WHERE installment_id=?", (installment_id,)).fetchone()
        if row and row["status"] not in {"PAID", "CANCELLED"} and int(row["paid_amount"]) < int(row["amount"]):
            return 0
        with self.db.tx() as con:
            cur = con.execute(
                "UPDATE reminders SET status='CANCELLED',updated_at=? WHERE entity_type='INSTALLMENT' AND entity_id=? AND status='SCHEDULED'",
                (_now(), installment_id),
            )
            return int(cur.rowcount)

    def buyer_dashboard(self) -> dict[str, int]:
        self.refresh_installment_statuses()
        with self.db.read() as con:
            contract = int(con.execute("SELECT COALESCE(SUM(contract_amount),0) FROM sales WHERE status!='CANCELLED'").fetchone()[0])
            received = int(con.execute("SELECT COALESCE(SUM(amount),0) FROM received_payments WHERE status!='CANCELLED'").fetchone()[0])
            unmatched = int(con.execute("SELECT COALESCE(SUM(amount),0) FROM received_payments WHERE status='UNMATCHED'").fetchone()[0])
            overdue = int(con.execute(
                "SELECT COALESCE(SUM(amount-paid_amount),0) FROM installments WHERE status!='CANCELLED' AND due_date<? AND paid_amount<amount",
                (date.today().isoformat(),),
            ).fetchone()[0])
            active_sales = int(con.execute("SELECT COUNT(*) FROM sales WHERE status='ACTIVE'").fetchone()[0])
        return {
            "contract_sales": contract,
            "cash_received": received,
            "receivable": max(0, contract - received),
            "unmatched_received": unmatched,
            "overdue": overdue,
            "active_sales": active_sales,
        }
