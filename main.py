
import io
import os
import json
import math
import re
import time
import textwrap
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

import copy
import hashlib
import logging
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import timezone
from zoneinfo import ZoneInfo


MODEL_VERSION = "2026.09.13.2"
TR_TIMEZONE = ZoneInfo("Europe/Istanbul")
APP_DATA_DIR = Path(os.environ.get("YAPAIKUPON_DATA_DIR", str(Path(__file__).resolve().parent)))
LOGGER = logging.getLogger("yapaikupon")

# Bunlar doğrulanmış optimumlar değildir; canlı ve backtest aynı ayarları kullanır.
MODEL_SETTINGS = {"league_weight": 1.25, "half_life_days": 730.0,
                  "min_time_weight": 0.25, "prior_strength": 5.0,
                  "base_prior_strength": 20.0}
BOOKMAKER_HISTORY_PREFIX = {"bet365": "B365", "bet365_au": "B365",
                            "williamhill": "WH", "pinnacle": "PS",
                            "bwin": "BW", "betvictor": "VC"}
ORAN_KAYIT_ALANLARI = ("match_id", "bookmaker_key", "odds_updated_at", "odds_phase",
                      "totals_updated_at", "totals_phase", "totals_bookmaker_key",
                      "o25_over", "o25_under",
                      "btts_updated_at", "btts_bookmaker_key", "btts_yes", "btts_no",
                      "odds_fetched_at")


def hassasiyet_oku(value, default=0.08):
    """0.00 geçerli bir seçimdir; yalnızca eksik/bozuk değer varsayılana düşer."""
    try:
        result = float(value) if value is not None else float(default)
        return result if math.isfinite(result) and result >= 0 else float(default)
    except (TypeError, ValueError):
        return float(default)


def oran_kayit_bilgisi(m):
    return {key: m.get(key) for key in ORAN_KAYIT_ALANLARI if m.get(key) is not None}


def zaman_agirliklari(df, m):
    dates = tarih_serisi_oku(df["Date"])
    target = parse_mac_datetime(m.get("zaman"))
    if target is None:
        return pd.Series(0.0, index=df.index)
    age = (pd.Timestamp(target).normalize() - dates).dt.total_seconds().div(86400).clip(lower=0)
    return (0.5 ** (age / MODEL_SETTINGS["half_life_days"])).clip(
        lower=MODEL_SETTINGS["min_time_weight"]).fillna(0.0)


def olasilik_yuzdeleri(values):
    """Birbirini dışlayan sonuçları, yuvarlama dahil tam %100'e tamamlar."""
    values = [max(0.0, float(value)) if math.isfinite(float(value)) else 0.0 for value in values]
    total = sum(values)
    if not total:
        return [0] * len(values)
    scaled = [value / total * 100.0 for value in values]
    rounded = [math.floor(value) for value in scaled]
    order = sorted(range(len(values)), key=lambda i: (scaled[i] - rounded[i], -i), reverse=True)
    for i in order[:100 - sum(rounded)]:
        rounded[i] += 1
    return rounded


def market_etkin_ornek(t, label):
    if str(label).startswith(("İY ", "HT/FT")):
        key = "effective_ht_samples"
    elif any(part in str(label) for part in ("KG", "Üst", "Alt")):
        key = "effective_goal_samples"
    else:
        key = "effective_ms_samples"
    return float(t.get(key, t.get("ornek", 0)) or 0)


def sabit_kalibrasyon_kayitlari():
    """İsteğe bağlı, sürümü sabit eğitim çıktısı; son UI backtestine bağlı değildir.

    yapaikupon_kalibrasyon.json: model_version, trained_through (ISO tarih), records.
    Hedefi eğitim dönemi içinde kalan bir maç bu profil ile düzeltilemez.
    Dosya bulunmazsa canlı ve backtest aynı nötr düzeltmeyi kullanır.
    """
    path = APP_DATA_DIR / "yapaikupon_kalibrasyon.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
        cutoff = parse_mac_datetime(profile.get("trained_through"))
        records = profile.get("records", [])
        if profile.get("model_version") != MODEL_VERSION or cutoff is None or not isinstance(records, list):
            return []
        return [dict(record, calibration_trained_through=cutoff.isoformat()) for record in records
                if isinstance(record, dict) and parse_mac_datetime(record.get("Tarih")) is not None
                and parse_mac_datetime(record["Tarih"]).date() <= cutoff.date()]
    except (OSError, ValueError, TypeError):
        return []


def tr_simdi():
    """Uygulama içi karşılaştırmalar: her zaman Türkiye yerel saati (naive)."""
    return datetime.now(TR_TIMEZONE).replace(tzinfo=None)


def kayit_zamani_iso():
    """Kalıcı kayıtlar saat dilimini de taşır."""
    return datetime.now(TR_TIMEZONE).isoformat(timespec="seconds")


def tarih_serisi_oku(values):
    """ISO ve Football-Data tarihlerini açık biçimlerle, gün/ay değiştirmeden okur."""
