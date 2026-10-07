import json

import pytest

from apexlinux import config
from apexlinux.config import Defaults, DesktopWidget


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path / "APEX"


def test_data_dir_follows_xdg(data_home):
    assert config.data_dir() == data_home


def test_no_file_is_first_run():
    assert config.load_desktop() is None
    assert config.load_defaults() == Defaults()


def test_round_trip():
    items = [DesktopWidget("race", "race", "m"), DesktopWidget("a1", "wdc", "l", 40, 60)]
    config.save_desktop(items)
    assert config.load_desktop() == items
    config.save_defaults(Defaults("max_verstappen", "detailed"))
    assert config.load_defaults() == Defaults("max_verstappen", "detailed")


def test_reads_the_windows_schema(data_home):
    # Exactly what System.Text.Json writes for List<DesktopWidget> and WidgetSettings.
    data_home.mkdir()
    (data_home / "desktop.json").write_text('[{"Id":"fav","Kind":"fav","Size":"m","X":-1,"Y":-1}]')
    (data_home / "defaults.json").write_text('{"Driver":null,"Density":"minimal"}')
    assert config.load_desktop() == [DesktopWidget("fav", "fav", "m")]
    assert config.load_defaults() == Defaults(None, "minimal")


def test_writes_the_windows_schema(data_home):
    config.save_desktop([DesktopWidget("fav", "fav", "s", 1, 2)])
    assert json.loads((data_home / "desktop.json").read_text()) == [{"Id": "fav", "Kind": "fav", "Size": "s", "X": 1, "Y": 2}]


def test_invalid_entries_are_dropped(data_home):
    data_home.mkdir()
    (data_home / "desktop.json").write_text(json.dumps([
        {"Id": "ok", "Kind": "race", "Size": "l"},
        {"Id": "bad-size", "Kind": "race", "Size": "xl"},
        {"Kind": "race", "Size": "m"},
        "nonsense",
        {"Id": "bad-pos", "Kind": "next", "Size": "s", "X": "1", "Y": 2},
    ]))
    assert config.load_desktop() == [DesktopWidget("ok", "race", "l"), DesktopWidget("bad-pos", "next", "s")]


def test_malformed_files_are_empty_not_first_run(data_home):
    data_home.mkdir()
    (data_home / "desktop.json").write_text("{not json")
    (data_home / "defaults.json").write_text('{"Driver": 5, "Density": "huge"}')
    assert config.load_desktop() == []
    assert config.load_defaults() == Defaults()


def test_write_leaves_no_temp_files(data_home):
    config.save_desktop([DesktopWidget("race", "race", "m")])
    config.save_defaults(Defaults())
    assert sorted(p.name for p in data_home.iterdir()) == ["defaults.json", "desktop.json"]


def test_add_update_remove():
    added = config.add_widget("timing", "l")
    assert len(added.Id) == 8 and (added.X, added.Y) == (-1, -1)
    other = config.add_widget("wdc", "s")
    config.update_widget(DesktopWidget(added.Id, "timing", "m", 10, 20))
    assert config.load_desktop() == [DesktopWidget(added.Id, "timing", "m", 10, 20), other]
    config.remove_widget(added.Id)
    assert config.load_desktop() == [other]


def test_update_does_not_resurrect_a_removed_widget():
    item = config.add_widget("race", "m")
    config.remove_widget(item.Id)
    config.update_widget(item)
    assert config.load_desktop() == []


def test_rejects_unknown_size_and_density():
    with pytest.raises(ValueError):
        config.add_widget("race", "xl")
    with pytest.raises(ValueError):
        config.save_defaults(Defaults(None, "huge"))
