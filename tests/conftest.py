import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_ktru import write_fixture_dir  # noqa: E402
from ktru_assist.catalog.importer import run_import  # noqa: E402
from ktru_assist.catalog.repository import Catalog  # noqa: E402
from ktru_assist.config import Settings  # noqa: E402
from ktru_assist.engine import Engine  # noqa: E402
from ktru_assist.search.local_backend import LocalBM25Backend  # noqa: E402

AS_OF = dt.date(2026, 10, 9)
REAL_DB = ROOT / "data" / "ktru.sqlite"


@pytest.fixture(scope="session")
def fixture_src(tmp_path_factory):
    d = tmp_path_factory.mktemp("ktru_src")
    write_fixture_dir(d)
    return d


@pytest.fixture(scope="session")
def fixture_db(fixture_src, tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "fixture.sqlite"
    meta = run_import(fixture_src, db, AS_OF, log=lambda *_: None)
    return db, meta


def make_engine(db: Path, top_k: int = 50, type_fetch_limit: int = 1000) -> Engine:
    cat = Catalog(db)
    settings = Settings(db_path=db, search_backend="local", opensearch_url="", opensearch_index="",
                        top_k=top_k, type_fetch_limit=type_fetch_limit)
    return Engine(cat, LocalBM25Backend(cat.search_documents()), settings)


@pytest.fixture(scope="session")
def engine(fixture_db):
    return make_engine(fixture_db[0])


@pytest.fixture(scope="session")
def real_engine():
    if not REAL_DB.exists():
        pytest.skip("реальная база data/ktru.sqlite не импортирована")
    return make_engine(REAL_DB)
