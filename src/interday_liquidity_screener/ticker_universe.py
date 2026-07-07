from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tickers import load_tickers

DEFAULT_UNIVERSE_ROOT = Path("data/input/universes")


@dataclass(frozen=True)
class UniversePreset:
    key: str
    label: str
    filename: str | None
    description: str

    @property
    def path(self) -> Path | None:
        return DEFAULT_UNIVERSE_ROOT / self.filename if self.filename else None


UNIVERSE_PRESETS = [
    UniversePreset(
        "manual",
        "Manual / upload sendiri",
        None,
        "Pakai file, upload, atau editor ticker seperti biasa.",
    ),
    UniversePreset(
        "all_idx",
        "Semua saham IDX",
        "all_idx.txt",
        "Daftar besar saham IDX dari file lokal. Update file ini jika ada emiten baru/delisting.",
    ),
    UniversePreset(
        "syariah",
        "Saham syariah",
        "syariah.txt",
        "Preset saham syariah lokal. Cocok untuk ISSI/JII-style screening dan bisa kamu update berkala.",
    ),
    UniversePreset(
        "lq45",
        "LQ45",
        "lq45.txt",
        "Preset LQ45 lokal. Update sesuai review BEI terbaru.",
    ),
    UniversePreset(
        "idx30",
        "IDX30",
        "idx30.txt",
        "Preset IDX30 lokal. Update sesuai review BEI terbaru.",
    ),
    UniversePreset(
        "idx80",
        "IDX80",
        "idx80.txt",
        "Preset IDX80 lokal. Update sesuai review BEI terbaru.",
    ),
    UniversePreset(
        "jii",
        "Jakarta Islamic Index (JII)",
        "jii.txt",
        "Preset JII lokal untuk saham syariah likuid.",
    ),
    UniversePreset(
        "kompas100",
        "Kompas100",
        "kompas100.txt",
        "Preset Kompas100 lokal. Isi bisa diperbarui dari daftar konstituen terbaru.",
    ),
    UniversePreset(
        "sri-kehati",
        "SRI-KEHATI",
        "sri-kehati.txt",
        "Preset SRI-KEHATI lokal.",
    ),
    UniversePreset(
        "bisnis27",
        "Bisnis-27",
        "bisnis27.txt",
        "Preset Bisnis-27 lokal.",
    ),
    UniversePreset(
        "pefindo25",
        "PEFINDO25",
        "pefindo25.txt",
        "Preset PEFINDO25 lokal.",
    ),
]

UNIVERSE_BY_KEY = {preset.key: preset for preset in UNIVERSE_PRESETS}


def get_universe_preset(key: str) -> UniversePreset:
    try:
        return UNIVERSE_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"Unknown ticker universe: {key}") from exc


def read_universe_text(key: str) -> str:
    preset = get_universe_preset(key)
    if preset.path is None:
        return ""
    if not preset.path.exists():
        return ""
    return preset.path.read_text(encoding="utf-8")


def load_universe_tickers(key: str) -> list[str]:
    preset = get_universe_preset(key)
    if preset.path is None:
        return []
    return load_tickers(preset.path)

