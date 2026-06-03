"""Test ortami: gecici DATA_DIR, repo config, sabit JWT secret.

Bu dosya pytest tarafindan testlerden ONCE yuklenir; auth/usage/audit
modulleri import edilmeden once ortam degiskenlerini ayarlar (DB yollari
modul seviyesinde DATA_DIR'den turetildigi icin sira onemli).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="onprem-test-data-"))
os.environ.setdefault("CONFIG_DIR", str(ROOT / "config"))
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-characters-abcdef")
