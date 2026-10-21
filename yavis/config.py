"""Einstellungen (JSON) und Speicherort."""
import copy
import json
import os
import threading
from pathlib import Path


def home_dir() -> Path:
    base = os.environ.get("YAVIS_HOME")
    if base:
        p = Path(base)
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / "YAVIS"
    else:
        p = Path.home() / ".yavis"
    p.mkdir(parents=True, exist_ok=True)
    return p


DEFAULTS = {
    "user_title": "Master",
    "wake_words": ["yavis", "jarvis"],
    "ollama_url": "http://localhost:11434",
    "model": "llama3.2:3b",
    "voice": "katja-warm",
    "voice_rate": 0,
    "voice_pitch": 0,
    "offline_voice": False,
    "mood": "auto",          # auto | neutral | nett | boese | traurig
    "show_text": False,      # Standard: nur Sprache
    "always_listen": True,
    "whisper_model": "small",
    "allowed_programs": None,  # None = Standardliste
    "custom_programs": {},     # Name -> Pfad
    "music_folder": "",
    "volume": 80,
}


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else home_dir() / "settings.json"
        self._lock = threading.RLock()
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            with self._lock:
                for k, v in loaded.items():
                    if k in DEFAULTS:
                        self.data[k] = v
        except Exception:
            pass

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, key):
        with self._lock:
            return copy.deepcopy(self.data.get(key, DEFAULTS.get(key)))

    def set(self, key, value):
        with self._lock:
            self.data[key] = value
        self.save()
