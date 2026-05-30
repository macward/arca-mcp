"""Tests para wsfe/catalog_cache.py."""

import time

import pytest

from arca_mcp.wsfe import catalog_cache
from arca_mcp.wsfe.models import CatalogItem


def _fn_a():
    pass


def _fn_b():
    pass


ITEMS = [CatalogItem(id="1", description="Factura A")]


@pytest.fixture(autouse=True)
def clear_cache():
    catalog_cache.clear()
    yield
    catalog_cache.clear()


def test_miss_on_empty():
    assert catalog_cache.get(_fn_a, "homologacion") is None


def test_set_and_get():
    catalog_cache.set(_fn_a, "homologacion", ITEMS)
    result = catalog_cache.get(_fn_a, "homologacion")
    assert result == ITEMS


def test_different_fn_different_entry():
    catalog_cache.set(_fn_a, "homologacion", ITEMS)
    assert catalog_cache.get(_fn_b, "homologacion") is None


def test_different_environment_different_entry():
    catalog_cache.set(_fn_a, "homologacion", ITEMS)
    assert catalog_cache.get(_fn_a, "produccion") is None


def test_expired_entry_returns_none(monkeypatch):
    catalog_cache.set(_fn_a, "homologacion", ITEMS)
    # Simulate TTL expiry by patching monotonic to return a future time
    original = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: original + catalog_cache.TTL_SECONDS + 1)
    assert catalog_cache.get(_fn_a, "homologacion") is None


def test_clear_evicts_all():
    catalog_cache.set(_fn_a, "homologacion", ITEMS)
    catalog_cache.set(_fn_b, "produccion", ITEMS)
    catalog_cache.clear()
    assert catalog_cache.get(_fn_a, "homologacion") is None
    assert catalog_cache.get(_fn_b, "produccion") is None
