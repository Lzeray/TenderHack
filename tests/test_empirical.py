"""Уровень 2 (типичность по выгрузкам СТЕ) на маленьком искусственном артефакте."""
import json
import sqlite3

import pytest

from ktru_assist.catalog.ste_stats import SCHEMA
from ktru_assist.empirical import SteStats, assess, presence
from ktru_assist.models import Feature


@pytest.fixture()
def stats_path(tmp_path):
    p = tmp_path / "ste_stats.sqlite"
    con = sqlite3.connect(p)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO manifest VALUES('ktru_snapshot', ?)", (json.dumps("SNAP"),))
    con.execute("INSERT INTO manifest VALUES('content_hash', ?)", (json.dumps("abc"),))
    con.execute("INSERT INTO types VALUES('дрель','tools',300,200,12)")
    con.execute("INSERT INTO types VALUES('стул','furniture',150,100,20)")
    q = json.dumps({"p01": "400", "p05": "450", "p25": "550", "p50": "650", "p75": "750", "p95": "850", "p99": "9000"})
    # мощность: 196 моделей в 400–900 Вт и 4 «эхо» по 9000 Вт (ошибка единицы в выгрузке)
    con.execute("INSERT INTO props VALUES(1,'дрель','мощность','Мощность','number','power',200,12,250,'1','0','0',0,"
                "?,'400','9000',12)", (q,))
    con.execute("INSERT INTO zones VALUES(1,0,'400','900',196,0)")
    con.execute("INSERT INTO zones VALUES(1,1,'9000','9000',4,1)")
    vals = [("400", 20), ("450", 20), ("500", 20), ("550", 20), ("600", 20), ("650", 20), ("700", 20), ("750", 20),
            ("800", 20), ("850", 10), ("900", 6), ("9000", 4)]
    con.executemany("INSERT INTO value_freq VALUES(1,?,?)", vals)
    # цвет: текстовое свойство
    con.execute("INSERT INTO props VALUES(2,'дрель','цвет','Цвет','text',NULL,200,12,250,'1','0','0',0,"
                "NULL,NULL,NULL,3)")
    con.executemany("INSERT INTO text_freq VALUES(2,?,?,?)", [("черный", "Черный", 150), ("зеленый", "Зеленый", 49),
                                                              ("розовый", "Розовый", 1)])
    # мало данных
    con.execute("INSERT INTO props VALUES(3,'дрель','вес','Вес','number','mass',10,2,10,'0,05','0','0',0,"
                "?,'1','3',3)", (q,))
    con.commit()
    con.close()
    return p


def feat(name, value, unit=None, op="eq", value_to=None):
    return Feature(id="f", source="text", status="bound", property_name=name, value=value, unit=unit, op=op,
                   value_to=value_to)


def test_numeric_statuses(stats_path):
    s = SteStats(stats_path, "SNAP")
    assert s.available
    assert assess(feat("Мощность", "600", "Вт"), ["дрель"], s).status == "typical"
    assert assess(feat("Мощность", "0,6", "кВт"), ["дрель"], s).status == "typical"   # перевод единиц
    assert assess(feat("Мощность", "9000", "Вт"), ["дрель"], s).status == "rare"      # только эхо-зона
    e = assess(feat("Мощность", "60000", "Вт"), ["дрель"], s)
    assert e.status == "unseen" and e.evidence["n_models"] == 200
    assert assess(feat("Мощность", "500", "Вт", op="ge"), ["дрель"], s).status == "typical"
    assert assess(feat("Мощность", "20000", "Вт", op="ge"), ["дрель"], s).status == "unseen"


def test_text_and_support(stats_path):
    s = SteStats(stats_path, "SNAP")
    assert assess(feat("Цвет", "Черный"), ["дрель"], s).status == "typical"
    assert assess(feat("Цвет", "розовый"), ["дрель"], s).status == "rare"
    # текст: «не встречается» не утверждаем — формулировки выгрузок и КТРУ не сопоставлены
    assert assess(feat("Цвет", "фиолетовый"), ["дрель"], s).reason == "text_not_found"
    assert assess(feat("Цвет", "черная"), ["дрель"], s).status == "typical"         # леммы: черная = черный
    both = Feature(id="f", source="text", status="bound", property_name="Цвет", op="in", value="черный и зеленый",
                   values=["Черный", "Зеленый"])
    assert assess(both, ["дрель"], s).status == "typical"
    assert assess(feat("Вес", "2", "кг"), ["дрель"], s).reason == "low_support"
    assert assess(feat("Длина", "2", "м"), ["дрель"], s).reason == "property_unmapped"
    # составной ключ типа: сначала «дрель|шуруповерт», затем каждое слово
    assert assess(feat("Мощность", "600", "Вт"), ["шуруповерт", "дрель"], s).status == "typical"


def test_artifact_missing_or_stale(stats_path, tmp_path):
    assert assess(feat("Мощность", "600", "Вт"), ["дрель"], SteStats(tmp_path / "нет.sqlite", "SNAP")).reason == \
        "no_artifact"
    assert assess(feat("Мощность", "600", "Вт"), ["дрель"], SteStats(stats_path, "OTHER")).reason == "stale_snapshot"


def test_presence_of_property_outside_ktru(stats_path):
    s = SteStats(stats_path, "SNAP")
    # у дрели в КТРУ нет «мощности», но в выгрузках это обычное свойство — значение оценивается
    f = Feature(id="u", source="text", status="unknown_property", value="600", unit="Вт", named_property="мощности")
    e = presence(f, ["дрель"], s)
    assert e.presence == "known_for_type" and e.status == "typical"
    # у стула «мощности» нет ни у одной из 100 моделей, а у дрели есть — подсказка про другой товар
    e2 = presence(f, ["стул"], s)
    assert e2.presence == "known_elsewhere" and "дрель" in e2.reason
    # реквизит карточки (страна) «чужим» не называется
    g = Feature(id="c", source="text", status="unknown_property", value="Китай", named_property="страна происхождения")
    assert presence(g, ["стул"], s) is None


def test_pair_relation_warning(stats_path):
    con = sqlite3.connect(stats_path)
    con.execute("INSERT INTO pair_le VALUES('стул','высота сиденья','высота','length',120,'0.995')")
    con.commit()
    con.close()
    from ktru_assist.suspicious import relations
    s = SteStats(stats_path, "SNAP")
    seat = Feature(id="a", source="text", status="bound", property_name="Высота сиденья", value="90", unit="см")
    total = Feature(id="b", source="text", status="bound", property_name="Высота", value="80", unit="см")
    w = relations([seat, total], ["стул"], s)
    assert len(w) == 1 and w[0].rule == "relation" and "перепутаны" in w[0].message
    ok = Feature(id="b", source="text", status="bound", property_name="Высота", value="1", unit="м")
    assert relations([seat, ok], ["стул"], s) == []                  # 90 см < 1 м — нарушения нет


def test_axis_order_prior(stats_path):
    con = sqlite3.connect(stats_path)
    con.executemany("INSERT INTO axis_order VALUES('стул','высота,ширина',?,?)",
                    [("высота,ширина", 95), ("ширина,высота", 5)])
    con.commit()
    con.close()
    from ktru_assist.dims import _order_prior
    s = SteStats(stats_path, "SNAP")
    tall = [("высота", "Высота", "90", "см"), ("ширина", "Ширина", "45", "см")]
    wide = [("высота", "Высота", "45", "см"), ("ширина", "Ширина", "90", "см")]
    assert _order_prior(s, ["стул"], tall) > 10 * _order_prior(s, ["стул"], wide)
