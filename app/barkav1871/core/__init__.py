"""Application lifecycle, identity and module-registration contracts."""

from .app_identity import APP_IDENTITY, AppIdentity
from .instance_guard import ProjectInstanceGuard
from .module_registry import MODULES, ModuleSpec
from .phase_catalog import PHASES, PhaseSpec, phase_by_number
from .project_registry import ProjectEntry, ProjectRegistry, apply_project_environment

__all__ = [
    "APP_IDENTITY",
    "AppIdentity",
    "MODULES",
    "ModuleSpec",
    "PHASES",
    "PhaseSpec",
    "ProjectEntry",
    "ProjectInstanceGuard",
    "ProjectRegistry",
    "apply_project_environment",
    "phase_by_number",
]
