"""Secrets in the Windows Credential Manager, and no key in plain text in the repo."""
import re
import subprocess
from pathlib import Path

from brevo_warehouse import vault

ROOT = Path(__file__).resolve().parents[1]


class FakeStore:
    def __init__(self, **values): self.values = dict(values)
    def read(self, name): return self.values.get(name)
    def write(self, name, value): self.values[name] = value
    def delete(self, name): return self.values.pop(name, None) is not None


def test_vault_fills_missing_secrets(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    assert vault.fill_env(FakeStore(BREVO_API_KEY="k-from-vault")) == ["BREVO_API_KEY"]
    import os
    assert os.environ["BREVO_API_KEY"] == "k-from-vault"


def test_environment_wins_over_vault(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "k-env")
    assert vault.fill_env(FakeStore(BREVO_API_KEY="k-vault")) == []


def test_no_vault_changes_nothing(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    assert vault.fill_env(store=False) == []


def test_check_flags_a_key_left_in_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BREVO_API_KEY=abc\nALERT_TO=me@example.com\n# ALERT_SMTP_PASSWORD=old\n", encoding="utf-8")
    lines, clean = vault.check(env, FakeStore(BREVO_API_KEY="abc"))
    assert not clean and "A CORRIGER" in lines[0] and "ALERT_SMTP_PASSWORD" in lines[1]
    env.write_text("BREVO_API_KEY=\nALERT_TO=me@example.com\n", encoding="utf-8")
    lines, clean = vault.check(env, FakeStore(BREVO_API_KEY="abc"))
    assert clean and lines[0].startswith("[OK]")


def test_windows_target_names_are_namespaced():
    assert vault.WindowsCredentials.target("BREVO_API_KEY") == "brevo-warehouse:BREVO_API_KEY"


KEY_PATTERN = re.compile(r"xkeysib-[0-9a-f]{20,}|xsmtpsib-[0-9a-f]{20,}")


def _project_files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", "data", "logs", "reports", ".venv", "__pycache__", "target"}
        return [p for p in ROOT.rglob("*") if p.is_file() and p.name != ".env"
                and not skip.intersection(p.relative_to(ROOT).parts)]


def test_no_brevo_key_in_plain_text_in_the_project():
    """Every file Git would publish is scanned (.env is ignored, so it is not)."""
    leaks = []
    for path in _project_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if KEY_PATTERN.search(text):
            leaks.append(str(path.relative_to(ROOT)))
    assert leaks == [], f"clé Brevo en clair dans : {leaks}"


def test_dotenv_is_ignored_by_git():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
