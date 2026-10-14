from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

from barkav1871 import APP_IDENTITY
from barkav1871.core import ProjectEntry, ProjectRegistry
from barkav1871.features.project_center import project_label
from barkav1871.features.financial_calendar import _normalize_shamsi
from barkav1871.features.dashboard import toman
from barkav1871.services import FinanceDB, LedgerQueryService
from barkav1871.services import ProjectService
from barkav1871.services import MarketService
from barkav1871.features.reports import report_rows
from barkav1871.integrations import TelegramReviewWorkflow
from barkav1871.integrations import ReminderService
from barkav1871.core.module_registry import MODULES, module_by_id
from barkav1871.core import PHASES, phase_by_number
from barkav1871.design import DESIGN_SURFACES, ThemeManager
from barkav1871.services import FinanceDB, SERVICE_CONTRACTS


def test_identity_is_versioned_without_stage_names():
    assert APP_IDENTITY.version == "18.7.1"
    assert "stage" not in APP_IDENTITY.window_title.lower()


def test_module_registry_has_unique_feature_routes():
    module_ids = [module.module_id for module in MODULES]
    assert len(module_ids) == len(set(module_ids))
    assert module_by_id("transactions").title_fa == "تراکنش‌ها"


def test_project_reference_phase_catalog_is_stable_and_nonfinancial():
    assert len(PHASES) == 32
    assert phase_by_number(1).title_fa == "خرید زمین"
    assert phase_by_number("32").title_fa == "سند و فروش"


def test_core_contracts_keep_design_and_finance_boundaries_explicit():
    assert DESIGN_SURFACES
    assert any(contract.financial_source_of_truth for contract in SERVICE_CONTRACTS)


def test_canonical_design_system_has_a_theme_manager():
    assert ThemeManager().selection.mode == "dark"


def test_canonical_finance_service_import_has_no_stage_module_dependency():
    assert FinanceDB.__module__ == "barkav1871.services.finance"


def test_canonical_project_registry_uses_new_database_setting():
    with TemporaryDirectory() as temporary_dir, patch.dict(
        "os.environ", {"BARKAV_DB_PATH": "custom.sqlite3"}, clear=False
    ):
        entry = ProjectRegistry(temporary_dir).ensure_default_project({})
    assert entry.db_path.endswith("custom.sqlite3")


def test_historical_registry_metadata_never_reuses_an_external_database_path():
    with TemporaryDirectory() as temporary_dir:
        base = Path(temporary_dir)
        (base / "data").mkdir()
        (base / "data" / "project_registry.json").write_text(
            '{"projects":[{"project_id":"PRJ-001","name":"قدیمی","db_path":"C:/old/stage.sqlite3"}]}',
            encoding="utf-8",
        )
        entry = ProjectRegistry(base).ensure_default_project({})
        assert entry.name == "قدیمی"
        assert Path(entry.db_path).is_relative_to(base)


def test_project_center_label_uses_canonical_project_entry():
    project = ProjectEntry(project_id="PRJ-001", name="بارکاو", db_path="sample.sqlite3")
    assert project_label(project) == "بارکاو  (PRJ-001)"


def test_financial_calendar_normalizes_persian_dates_without_ui_runtime():
    assert _normalize_shamsi("۱۴۰۵-۰۶-۰۸") == "1405/06/08"


def test_dashboard_money_format_uses_toman_not_a_local_formula():
    assert "تومان" in toman(1_250_000)


def test_ledger_query_service_reads_an_empty_new_ledger():
    with TemporaryDirectory() as temporary_dir:
        service = LedgerQueryService(FinanceDB(Path(temporary_dir) / "ledger.sqlite3"))
        assert service.list_transactions() == []
        assert service.list_expenses() == []


def test_project_service_persists_the_canonical_profile_shape():
    with TemporaryDirectory() as temporary_dir:
        base = Path(temporary_dir)
        service = ProjectService(FinanceDB(base / "project.sqlite3"), base)
        service.save_project(name="بارکاو", address="تهران", postal_code="123", registration_plate="A", municipal_file_no="B")
        assert service.get_project()["name"] == "بارکاو"


def test_report_projection_reads_the_same_empty_ledger():
    with TemporaryDirectory() as temporary_dir:
        query = LedgerQueryService(FinanceDB(Path(temporary_dir) / "report.sqlite3"))
        assert report_rows(query) == []


def test_canonical_manual_entry_target_remains_an_audited_ledger_posting():
    with TemporaryDirectory() as temporary_dir:
        database = FinanceDB(Path(temporary_dir) / "entry.sqlite3")
        database.post_transaction(
            event_date="2026-08-30", direction="IN", amount=150_000,
            category="تست", payer_name="خریدار", source_type="TEST",
        )
        row = LedgerQueryService(database).list_transactions()[0]
        assert row["amount"] == 150_000
        assert row["direction"] == "IN"


def test_contractors_are_persisted_in_the_existing_market_schema():
    with TemporaryDirectory() as temporary_dir:
        base = Path(temporary_dir)
        market = MarketService(FinanceDB(base / "market.sqlite3"), base)
        market.save_entity({"entity_type": "CONTRACTOR", "company_name": "پیمانکار تست"})
        assert market.list_entities("CONTRACTOR")[0]["company_name"] == "پیمانکار تست"


def test_manager_account_uses_the_ledger_snapshot_calculation():
    with TemporaryDirectory() as temporary_dir:
        database = FinanceDB(Path(temporary_dir) / "manager.sqlite3")
        database.create_expense(
            event_date="2026-08-01", final_amount=1_000_000,
            construction_stage="اسکلت", description="ساخت",
        )
        database.create_expense(
            event_date="2026-08-02", final_amount=400_000,
            construction_stage="خرید زمین", description="زمین",
        )
        database.post_transaction(
            event_date="2026-08-03", direction="OUT", amount=100_000,
            category="CONTRACTOR_FEE", description="برداشت مدیر",
        )
        snapshot = database.snapshot()
        assert snapshot.manager_fee_accrued == 100_000
        assert snapshot.manager_balance == 90_000
        assert snapshot.manager_balance == database.manager_account_balance()

def test_telegram_review_stays_pending_until_a_human_approves_it():
    with TemporaryDirectory() as temporary_dir:
        workflow = TelegramReviewWorkflow(FinanceDB(Path(temporary_dir) / "telegram.sqlite3"))
        item = workflow.receive_message(
            chat_id=100, message_id=200, raw_text="واریز تست", content_type="TEXT",
            message_date="1405/06/09 10:00", analysis={"detected_type": "INCOME", "amount": 100},
        )
        assert item.state == "PENDING_REVIEW"
        assert workflow.approve(item.pending_id).state == "APPROVED"


def test_reminder_service_only_hands_due_rows_to_a_delivery_adapter():
    with TemporaryDirectory() as temporary_dir:
        database = FinanceDB(Path(temporary_dir) / "reminder.sqlite3")
        cheque_id = database.create_cheque(amount=500, issue_date="2026-08-01", due_date="2026-08-30")
        reminders = ReminderService(database)
        assert reminders.schedule_open_cheques(times=("09:00",), days_before=0) == 1
        assert reminders.due(now_iso="2026-08-30T10:00:00")[0]["entity_id"] == cheque_id
