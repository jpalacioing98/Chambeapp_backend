"""Pytest configuration for ChambeApp backend tests."""

import os
import sys
import types
import pytest

# Set testing environment before importing app
os.environ["TESTING"] = "1"
os.environ["FLASK_TESTING"] = "1"

# ---------------------------------------------------------------------------
# GeoAlchemy2 + SQLite workaround
# Without SpatiaLite, Geometry columns fail on create (RecoverGeometryColumn)
# and on query (AsEWKB wraps columns that don't exist).
#
# Strategy: replace geoalchemy2 with a stub module that provides Geometry
# as a plain String column BEFORE any model code is imported.
# This must happen before `app` is imported by any test module.
# ---------------------------------------------------------------------------

from sqlalchemy import String as _String


class _StubGeometry(_String):
    """Geometry replacement for SQLite tests — plain VARCHAR."""

    def __init__(self, *args, **kwargs):
        super().__init__(length=255)


class _StubGeography(_String):
    """Geography replacement for SQLite tests — plain VARCHAR."""

    def __init__(self, *args, **kwargs):
        super().__init__(length=255)


class _StubRaster(_String):
    """Raster replacement for SQLite tests — plain VARCHAR."""

    def __init__(self, *args, **kwargs):
        super().__init__(length=255)


class _StubGeometryAdmin(types.ModuleType):
    """No-op geoalchemy2.admin replacement."""

    def __init__(self, name="geoalchemy2.admin"):
        super().__init__(name)

    def setup_ddl_event_listeners(self):
        pass

    def select_dialect(self, name):
        mod = types.ModuleType(f"ga2_admin_{name}")
        for attr in (
            "before_create", "after_create", "before_drop", "after_drop",
            "reflect_geometry_column",
        ):
            setattr(mod, attr, lambda *a, **k: None)
        return mod


class _StubGeoAlchemy2(types.ModuleType):
    """Minimal geoalchemy2 stub for SQLite test env."""

    Geometry = _StubGeometry
    Geography = _StubGeography
    Raster = _StubRaster

    def __init__(self, name):
        super().__init__(name)
        self.admin = _StubGeometryAdmin("geoalchemy2.admin")
        self.functions = types.ModuleType("geoalchemy2.functions")
        self.elements = types.ModuleType("geoalchemy2.elements")

    def __getattr__(self, name):
        # Return a no-op for any other geoalchemy2 attribute
        return lambda *a, **k: None


# Install the stub BEFORE any model/app code imports geoalchemy2
_stub = _StubGeoAlchemy2("geoalchemy2")
sys.modules["geoalchemy2"] = _stub
sys.modules["geoalchemy2.admin"] = _stub.admin
sys.modules["geoalchemy2.admin.dialects"] = types.ModuleType("geoalchemy2.admin.dialects")
sys.modules["geoalchemy2.admin.dialects.sqlite"] = types.ModuleType("geoalchemy2.admin.dialects.sqlite")
sys.modules["geoalchemy2.functions"] = _stub.functions
sys.modules["geoalchemy2.elements"] = _stub.elements
