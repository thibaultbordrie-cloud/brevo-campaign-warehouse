"""Anonymity guard: nothing in this public repository may point to a real company, person,
internal tool or cloud project. The forbidden terms are stored only as hashes, so this file
does not reveal them either. Also: e-mail addresses must be example ones, and no public IP.
"""
import hashlib
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "08f6f59e0540944622c9",
    "0a13fe27742142ab0a55",
    "2384ec0e2963ba2a2c71",
    "3462ee2ec1e78c77d7f0",
    "3af7d17d9a4bc5308c57",
    "43b54885c5690ed70656",
    "44b1d90c896f767137f4",
    "54557012f65abc5908f3",
    "5845901d0e075c9bb3ab",
    "69185407befe30912e51",
    "7cbdf191488e3c89e8ce",
    "844ebbe693aaaf6a39d3",
    "915f4a517d06ef5fbf31",
    "91ae1deae4b736c50156",
    "9768f993f262761fe41e",
    "9be83f38bdcd57c6fe98",
    "abb81aaf9978b9966fed",
}
ALLOWED_MAIL_DOMAINS = ("example.com", "example.org", "users.noreply.github.com")
TEXT = {".py", ".sql", ".md", ".yml", ".yaml", ".toml", ".json", ".bat", ".sh", ".txt", ".example", ""}


def _norm(text: str) -> list[str]:
    text = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:20]


def _files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        paths = [ROOT / f for f in out]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", "data", "logs", "reports", ".venv", "__pycache__", "target", ".ruff_cache"}
        paths = [p for p in ROOT.rglob("*") if p.is_file() and not skip.intersection(p.relative_to(ROOT).parts)]
    return [p for p in paths if p.is_file() and (p.suffix in TEXT or p.name in ("LICENSE", ".gitignore", ".gitattributes"))
            and p.name != ".env"]


def test_no_identifying_term_anywhere():
    hits = []
    for path in _files():
        words = _norm(path.read_text(encoding="utf-8", errors="ignore") + " " + str(path.relative_to(ROOT)))
        grams = set(words) | {" ".join(words[i:i + 2]) for i in range(len(words) - 1)} \
            | {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
        if any(_h(g) in FORBIDDEN for g in grams):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"identifying term found in: {hits}"


def test_only_example_email_addresses():
    bad = []
    for path in _files():
        for mail in re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", path.read_text(encoding="utf-8", errors="ignore")):
            if not mail.lower().endswith(ALLOWED_MAIL_DOMAINS):
                bad.append(f"{path.relative_to(ROOT)}: @{mail}")
    assert bad == []


def test_no_public_ip_address():
    bad = []
    for path in _files():
        for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", path.read_text(encoding="utf-8", errors="ignore")):
            if not ip.startswith(("127.", "0.", "10.", "192.168.")):
                bad.append(f"{path.relative_to(ROOT)}: {ip}")
    assert bad == []
