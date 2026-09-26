import subprocess

from app import updates
from app.version import get_version


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True, capture_output=True)


def test_update_notice_when_origin_has_new_commits(tmp_path, monkeypatch):
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / "a.txt").write_text("1")
    _git(work, "add", "."), _git(work, "commit", "-m", "uno"), _git(work, "push", "origin", "HEAD:main")
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)

    monkeypatch.setattr(updates, "BASE_DIR", clone)
    monkeypatch.setattr(updates, "STATE", tmp_path / "estado.json")
    updates._status.update(disponible=False, commits=0)
    assert updates.check(force=True)["disponible"] is False

    (work / "a.txt").write_text("2")
    _git(work, "commit", "-am", "dos"), _git(work, "push", "origin", "HEAD:main")
    st = updates.check(force=True)
    assert st["disponible"] and st["commits"] == 1 and "git pull" in st["mensaje"]

    # no vuelve a consultar antes de 24 h (salvo force)
    assert updates.check()["comprobado"] is not None
    res = updates.apply()
    assert res["ok"] and (clone / "a.txt").read_text() == "2"
    assert updates.status()["disponible"] is False


def test_no_repo_or_no_network_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "BASE_DIR", tmp_path)          # carpeta sin git
    monkeypatch.setattr(updates, "STATE", tmp_path / "e.json")
    assert updates.check(force=True)["disponible"] is False


def test_version_comes_from_pyproject():
    import re
    assert re.match(r"^\d+\.\d+\.\d+", get_version())  # (S0) admite 3.0.0.devN


def test_shortcut_is_created_once_on_first_run(tmp_path, monkeypatch):
    from app import launcher
    calls = []
    monkeypatch.setattr(launcher, "MARKER", tmp_path / ".creado")
    monkeypatch.setattr(launcher, "BASE_DIR", tmp_path)
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    def fake(quiet=False):
        calls.append(1)
        launcher.MARKER.write_text("ok")
        (tmp_path / "FAVERVIEW.lnk").write_text("x")
        return True

    monkeypatch.setattr(launcher, "create_shortcut", fake)
    launcher.ensure_shortcut()
    launcher.ensure_shortcut()  # segunda vez: ya existe el marcador, no lo recrea
    assert len(calls) == 1
    assert (launcher.Path(__file__).resolve().parent.parent / "assets" / "faverview.ico").exists()
