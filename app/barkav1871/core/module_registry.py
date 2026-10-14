"""Single registry for the product modules planned for 18.7.1.

This registry contains navigation and ownership metadata only. It does not
import UI, database, finance, or historical stage modules.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    title_fa: str
    layer: str


MODULES: Final[tuple[ModuleSpec, ...]] = (
    ModuleSpec("source_control", "گیت و کیفیت", "governance"),
    ModuleSpec("project_center", "مرکز پروژه", "shell"),
    ModuleSpec("application_shell", "اسکلت کلی برنامه", "shell"),
    ModuleSpec("design_system", "طراحی بصری، تم و لوگو", "design"),
    ModuleSpec("project_details", "مشخصات پروژه", "feature"),
    ModuleSpec("dashboard", "داشبورد", "feature"),
    ModuleSpec("data_entry", "ثبت دیتا", "feature"),
    ModuleSpec("transactions", "تراکنش‌ها", "feature"),
    ModuleSpec("sales_claims", "فروش و مطالبات", "feature"),
    ModuleSpec("contractors", "پیمانکاران", "feature"),
    ModuleSpec("reports", "گزارش‌گیری", "feature"),
    ModuleSpec("manager_account", "حساب مدیر", "feature"),
    ModuleSpec("telegram_reminders", "تلگرام و یادآوری", "integration"),
    ModuleSpec("quality_release", "تست و انتشار", "governance"),
    ModuleSpec("online_platform", "وب، VPS و فضای ابری", "future-integration"),
)


def module_by_id(module_id: str) -> ModuleSpec:
    """Return a registered module or fail loudly for an invalid route."""
    for module in MODULES:
        if module.module_id == module_id:
            return module
    raise KeyError(f"Unknown BARKAV module: {module_id}")
