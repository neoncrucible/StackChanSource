"""Optional Windows Credential Manager storage; never a plaintext fallback."""
from __future__ import annotations
import ctypes
import json
import os
from ctypes import wintypes

KEYS = frozenset({"openai_api_key", "gemini_api_key", "wifi_password"})


class CredentialVault:
    def __init__(self, target="Kadence/Desktop/Providers"):
        if os.name != "nt": raise RuntimeError("Remembered credentials require Windows Credential Manager.")
        class Credential(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
        self.Credential = Credential
        self.target = target
        self.api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        self.api.CredWriteW.restype = wintypes.BOOL
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
        self.api.CredReadW.restype = wintypes.BOOL
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.api.CredDeleteW.restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None

    def save(self, values: dict):
        if set(values)-KEYS or any(not isinstance(v, str) or len(v)>1024 for v in values.values()):
            raise ValueError("Invalid credential fields")
        raw = json.dumps(values).encode("utf-8")
        if len(raw)>2500: raise ValueError("Credentials exceed vault size limit")
        blob = (ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
        credential = self.Credential(Type=1, TargetName=self.target, CredentialBlobSize=len(raw),
            CredentialBlob=blob, Persist=2, UserName="Kadence")
        try:
            if not self.api.CredWriteW(ctypes.byref(credential), 0): raise RuntimeError("Windows could not save the credentials.")
        finally: ctypes.memset(blob, 0, len(raw))

    def load(self) -> dict:
        pointer = ctypes.POINTER(self.Credential)()
        if not self.api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error()==1168: return {}
            raise RuntimeError("Windows could not read saved credentials.")
        try:
            size = pointer.contents.CredentialBlobSize
            if size>2500: raise RuntimeError("Saved credentials exceed the size limit.")
            values = json.loads(ctypes.string_at(pointer.contents.CredentialBlob, size))
            if not isinstance(values, dict) or set(values)-KEYS or any(not isinstance(v,str) for v in values.values()):
                raise RuntimeError("Saved credentials are invalid.")
            return values
        finally: self.api.CredFree(pointer)

    def forget(self):
        if not self.api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error()!=1168:
            raise RuntimeError("Windows could not delete saved credentials.")
