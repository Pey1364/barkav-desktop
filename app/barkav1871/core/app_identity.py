"""The one canonical identity for the 18.7.1 migration target."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppIdentity:
    product_name: str
    product_tagline: str
    version: str
    language: str

    @property
    def window_title(self) -> str:
        return f"{self.product_name} — {self.product_tagline} — Version {self.version}"


APP_IDENTITY = AppIdentity(
    product_name="BARKAV",
    product_tagline="Engineering & Construction",
    version="18.7.1",
    language="fa-IR",
)
