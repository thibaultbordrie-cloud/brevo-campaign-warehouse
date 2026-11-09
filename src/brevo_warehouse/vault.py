"""Secrets kept in the Windows Credential Manager instead of plain-text files.

Windows encrypts these entries with the user's session (DPAPI): copying the project
folder, the .env file or a backup does not give the keys away. Nothing to install:
the Windows functions are called directly through ctypes.

Commands (python run.py secret ...):
  secret set NAME     ask for the value (hidden typing) and store it
  secret check        say where each secret is found, warn if one is still in .env
  secret delete NAME  remove it from the Credential Manager
"""
from __future__ import annotations

import os
from pathlib import Path

SERVICE = "brevo-warehouse"
SECRET_NAMES = ("BREVO_API_KEY", "ALERT_SMTP_PASSWORD")


class VaultError(RuntimeError):
    pass


class WindowsCredentials:
    """Minimal access to the Windows Credential Manager (generic credentials)."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        self.ctypes, self.CREDENTIAL = ctypes, CREDENTIAL
        try:
            self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise VaultError("Windows Credential Manager not available on this system") from exc
        PCRED = ctypes.POINTER(CREDENTIAL)
        self.advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                          ctypes.POINTER(PCRED)]
        self.advapi.CredWriteW.argtypes = [PCRED, wintypes.DWORD]
        self.advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.advapi.CredFree.argtypes = [ctypes.c_void_p]

    @staticmethod
    def target(name: str) -> str:
        return f"{SERVICE}:{name}"

    def read(self, name: str) -> str | None:
        ctypes = self.ctypes
        pcred = ctypes.POINTER(self.CREDENTIAL)()
        if not self.advapi.CredReadW(self.target(name), self.CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            if ctypes.get_last_error() == self.ERROR_NOT_FOUND:
                return None
            raise VaultError(f"CredReadW failed (error {ctypes.get_last_error()})")
        try:
            cred = pcred.contents
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self.advapi.CredFree(pcred)

    def write(self, name: str, value: str) -> None:
        ctypes = self.ctypes
        blob = value.encode("utf-16-le")
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = self.CREDENTIAL()
        cred.Type = self.CRED_TYPE_GENERIC
        cred.TargetName = self.target(name)
        cred.UserName = name
        cred.Comment = "brevo-warehouse (python run.py secret)"
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        if not self.advapi.CredWriteW(ctypes.byref(cred), 0):
            raise VaultError(f"CredWriteW failed (error {ctypes.get_last_error()})")

    def delete(self, name: str) -> bool:
        if self.advapi.CredDeleteW(self.target(name), self.CRED_TYPE_GENERIC, 0):
            return True
        if self.ctypes.get_last_error() == self.ERROR_NOT_FOUND:
            return False
        raise VaultError(f"CredDeleteW failed (error {self.ctypes.get_last_error()})")


_store = None


def default_store():
    """The Windows store, or None elsewhere (Linux CI, tests)."""
    global _store
    if _store is None:
        try:
            _store = WindowsCredentials()
        except VaultError:
            _store = False
    return _store or None


def fill_env(store=None, names=SECRET_NAMES) -> list[str]:
    """Put secrets from the vault into the environment when they are not already set.

    Returns the names taken from the vault. A failing vault never blocks the run:
    the program then behaves as before (environment / .env only).
    """
    store = store if store is not None else default_store()
    taken = []
    if not store:
        return taken
    for name in names:
        if os.environ.get(name):
            continue
        try:
            value = store.read(name)
        except VaultError:
            continue
        if value:
            os.environ[name] = value
            taken.append(name)
    return taken


def dotenv_names(path: Path) -> set[str]:
    """Names that have a non-empty value in a .env file."""
    if not path.is_file():
        return set()
    found = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip().strip('"').strip("'"):
                found.add(key.strip())
    return found


def check(env_file: Path, store=None, names=SECRET_NAMES) -> tuple[list[str], bool]:
    """Report lines, and True if every secret is out of the .env file."""
    store = store if store is not None else default_store()
    in_dotenv = dotenv_names(env_file)
    lines, clean = [], True
    for name in names:
        in_vault = bool(store and store.read(name))
        if name in in_dotenv:
            clean = False
            where = "EN CLAIR dans .env" + (" (et aussi dans le coffre)" if in_vault else "")
            lines.append(f"[A CORRIGER] {name} : {where} -> supprimer la ligne de .env")
        elif in_vault:
            lines.append(f"[OK] {name} : coffre Windows")
        else:
            lines.append(f"[--] {name} : absent (normal s'il ne sert pas)")
    return lines, clean
