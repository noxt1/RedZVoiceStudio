"""Сделать устройство микрофоном по умолчанию в Windows (через IAudioPolicyConfig).

Зачем: игра (RedM/Mumble) не показывает «Стерео микшер» в своём списке
микрофонов. Но если сделать его микрофоном по умолчанию и в игре выбрать
«Системное устройство» (Default), игра будет писать в голосовой канал
именно его — без установки стороннего софта.

Работает через COM-интерфейс IAudioPolicyConfig (Windows 10/11).
"""

from __future__ import annotations

import ctypes
import uuid


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        u = uuid.UUID(text)
        raw = u.bytes_le
        return cls.from_buffer_copy(raw)


CLSID_MM_DEVICE_ENUMERATOR = _GUID.parse("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMM_DEVICE_ENUMERATOR = _GUID.parse("A95664D2-9614-4F35-A746-DE8DB63617E6")
CLSID_POLICY_CONFIG_CLIENT = _GUID.parse("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")
IID_IAUDIO_POLICY_CONFIG = _GUID.parse("F8679F50-850A-41FC-A6C3-2FDCC88C8100")

E_CONSOLE = 0
E_MULTIMEDIA = 1
E_COMMUNICATIONS = 2


def _com_call(obj, index: int, restype, argtypes, *args):
    """Вызов метода по индексу в vtable."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    fn_ptr = vtbl[index]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    fn = proto(fn_ptr)
    return fn(obj, *args)


def _endpoint_id(device_name_part: str) -> str | None:
    """Найти endpoint по имени и вернуть его ID."""
    try:
        import comtypes.client as cc
    except ImportError:
        return None
    try:
        enumerator = cc.CreateObject(
            "MMDeviceEnumerator", interface=cc.IID_IMMDeviceEnumerator)
        collection = enumerator.EnumAudioEndpoints(1, 1)  # eRender=0? -> см. ниже
        for device in collection:
            try:
                if device_name_part.lower() in device.FriendlyName.lower():
                    return device.Id
            except Exception:
                continue
    except Exception:
        return None
    return None


def set_default_capture(device_id: str, role: int = E_CONSOLE) -> bool:
    """Сделать endpoint микрофоном по умолчанию. True — успех."""
    ole32 = ctypes.windll.ole32
    try:
        clsid = CLSID_POLICY_CONFIG_CLIENT
        iid = IID_IAUDIO_POLICY_CONFIG
        obj = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1,
                                    ctypes.byref(iid), ctypes.byref(obj))
        if hr != 0:
            return False
        # IAudioPolicyConfig::SetDefaultEndpointId — 4-й метод (после 3 из IUnknown)
        _com_call(obj, 4, ctypes.c_long, [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_ulong],
                  device_id, role, 0)
        ole32.CoUninitialize()
        return True
    except Exception:
        return False


def list_capture_endpoints() -> list[tuple[str, str]]:
    """(имя, id) всех входов — для выбора нужного."""
    try:
        import comtypes.client as cc
    except ImportError:
        return []
    out = []
    try:
        enumerator = cc.CreateObject(
            "MMDeviceEnumerator", interface=cc.IID_IMMDeviceEnumerator)
        for device in enumerator.EnumAudioEndpoints(1, 1):  # eCapture=1, DEVICE_STATE_ACTIVE=1
            try:
                out.append((device.FriendlyName, device.Id))
            except Exception:
                continue
    except Exception:
        return []
    return out
