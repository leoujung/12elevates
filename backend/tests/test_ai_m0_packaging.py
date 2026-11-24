"""M0 packaging checks: the AI runtime is importable from the API image and stays disabled.

These tests do not exercise matching logic (that lives in the prototype suite) and do not
touch any member data. They protect the M0 contract:
  - the AI package imports from the image layout (/app/ai),
  - the business matching flag is a constant False,
  - no AI HTTP route is exposed in M0 (routes are added in later milestones).
"""
import importlib

import pytest

AI_MODULES = [
    "ai.config",
    "ai.consent",
    "ai.rbac",
    "ai.synthetic_guard",
    "ai.field_policy",
    "ai.customer_matching",
    "ai.business_matching",
    "ai.matching_service",
]


@pytest.mark.parametrize("name", AI_MODULES)
def test_ai_module_imports(name):
    importlib.import_module(name)


def test_business_matching_flag_is_false():
    from ai import config

    assert config.BUSINESS_MATCHING_ENABLED is False


def test_no_ai_routes_exposed_in_m0(monkeypatch):
    monkeypatch.setenv("APP_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite:///:memory:")
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert not [p for p in paths if p.startswith("/v1/ai")], paths
