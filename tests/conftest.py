"""Shared fixtures. Database tests skip when Postgres is not running."""
from __future__ import annotations

import os

import psycopg
import pytest

from idt_redteam.benchmark import load_clean

os.environ.setdefault("IDT_DISABLE_EMBEDDINGS", "1")  # keyword search keeps tests fast and offline


@pytest.fixture(scope="session")
def clean():
    return load_clean()


@pytest.fixture(scope="session")
def attack_db():
    from idt_redteam.loader import attack_database_url
    url = attack_database_url()
    try:
        psycopg.connect(url).close()
    except psycopg.Error:
        pytest.skip("attack database not reachable")
    return url
