"""Semantic design names; concrete theme values stay in one theme engine."""

from enum import StrEnum


class DesignSurface(StrEnum):
    APP = "app"
    HEADER = "header"
    FOOTER = "footer"
    PANEL = "panel"
    CARD = "card"
    TABLE = "table"
    DIALOG = "dialog"
    INPUT = "input"
    ACTION = "action"
    STATUS = "status"


DESIGN_SURFACES = tuple(DesignSurface)
