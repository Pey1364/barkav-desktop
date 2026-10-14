"""Service boundaries that prevent feature modules from reaching SQLite directly."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ServiceContract:
    service_id: str
    purpose_fa: str
    financial_source_of_truth: bool = False


SERVICE_CONTRACTS: Final[tuple[ServiceContract, ...]] = (
    ServiceContract("project", "مشخصات، طبقات، واحدها و عوامل پروژه"),
    ServiceContract("finance", "محاسبات و ثبت‌های مالی تأییدشده", True),
    ServiceContract("transactions", "گردش Pending و ثبت رویدادهای تراکنشی", True),
    ServiceContract("documents", "اسناد و پیوست‌ها"),
    ServiceContract("contracts", "قراردادهای فروش و پیمانکار"),
    ServiceContract("exports", "پیش‌نمایش، Excel، CSV، PDF و چاپ"),
    ServiceContract("audit", "لاگ و تاریخچهٔ تغییرات"),
)
