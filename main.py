
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


MODEL_VERSION = "2026.09.12.1"
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
    series = pd.Series(values, index=getattr(values, "index", None))
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    text_values = series.astype("string").str.strip()
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    iso = text_values.str.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", na=False)
    result.loc[iso] = pd.to_datetime(text_values.loc[iso].str.slice(0, 10), format="%Y-%m-%d", errors="coerce")
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y"):
        remaining = result.isna() & ~iso
        if remaining.any():
            result.loc[remaining] = pd.to_datetime(text_values.loc[remaining], format=fmt, errors="coerce")
    return result


def mac_baslamadi_mi(value, simdi=None):
    kickoff = parse_mac_datetime(value)
    now = parse_mac_datetime(simdi) if simdi is not None else tr_simdi()
    return kickoff is not None and now is not None and kickoff > now


def tarih_oncesi_gecmis(df, value):
    """Saat bilgisi olmayan geçmişte hedef günün tamamını dışarıda bırakır."""
    kickoff = parse_mac_datetime(value)
    if kickoff is None or "Date" not in df.columns:
        return df.iloc[0:0].copy()
    dates = tarih_serisi_oku(df["Date"])
    return df.loc[dates < pd.Timestamp(kickoff).normalize()]


def tarih_oncesi_kayitlar(records, value):
    kickoff = parse_mac_datetime(value)
    if kickoff is None:
        return []
    cutoff = kickoff.date()
    return [record for record in records or []
            if (dt := parse_mac_datetime(record.get("Tarih", record.get("zaman")))) is not None
            and dt.date() < cutoff
            and (not record.get("calibration_trained_through")
                 or ((trained := parse_mac_datetime(record["calibration_trained_through"])) is not None
                     and trained.date() < cutoff))]


class KayitDeposu:
    """SQLite işlemi, okuma-değiştirme-yazmanın tamamını eşzamanlı kullanıma karşı korur.

    Eski JSON dosyaları ilk erişimde içe alınır ve yedek olarak yerinde bırakılır.
    Kalıcı disk kullanan kurulumlar YAPAIKUPON_DATA_DIR ile veri dizinini seçebilir.
    """

    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("CREATE TABLE IF NOT EXISTS documents (name TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _read(connection, name, legacy_path):
        row = connection.execute("SELECT payload FROM documents WHERE name=?", (name,)).fetchone()
        if row is not None:
            result = json.loads(row[0])
        elif legacy_path is not None and Path(legacy_path).exists():
            result = json.loads(Path(legacy_path).read_text(encoding="utf-8"))
        else:
            result = []
        if not isinstance(result, list):
            raise ValueError("Kayıt dosyası liste biçiminde değil; mevcut dosya korunuyor.")
        return result

    def read(self, name, legacy_path=None):
        with self._connection() as connection:
            return self._read(connection, name, legacy_path)

    def update(self, name, change, legacy_path=None):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                records = self._read(connection, name, legacy_path)
                updated = change(records)
                payload = json.dumps(_json_guvenli_deger(updated), ensure_ascii=False, allow_nan=False)
                connection.execute(
                    "INSERT INTO documents(name,payload,updated_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                    (name, payload, kayit_zamani_iso()),
                )
                connection.commit()
                return updated
            except Exception:
                connection.rollback()
                raise


def kayit_deposu():
    return KayitDeposu(APP_DATA_DIR / "yapaikupon.sqlite3")


def kayit_hatasi(operation, error):
    LOGGER.error("%s: %s", operation, type(error).__name__)
    st.error(f"{operation}. Kayıt işlemi tamamlanmadı; önceki veriler korundu.")


def kayitlari_degistir(name, change, legacy_path):
    try:
        kayit_deposu().update(name, change, legacy_path)
        return True
    except (OSError, ValueError, TypeError, sqlite3.Error) as error:
        kayit_hatasi("Veriler kaydedilemedi", error)
        return False


def oran_fazi(m, totals=False):
    """CSV has no quote clock: phase matching is approximate, never exact-time matching."""
    explicit = m.get("totals_phase" if totals else "odds_phase")
    if explicit in ("closing", "preclosing"):
        return explicit
    if explicit == "legacy_unknown" and m.get("history_detail_only"):
        return "legacy_unknown"
    key = "totals_updated_at" if totals else "odds_updated_at"
    quote = pd.to_datetime(m.get(key), utc=True, errors="coerce")
    kickoff = pd.to_datetime(m.get("zaman"), errors="coerce")
    if pd.notna(kickoff):
        kickoff = kickoff.tz_localize(TR_TIMEZONE) if kickoff.tzinfo is None else kickoff
        kickoff = kickoff.tz_convert("UTC")
    if pd.isna(quote) or pd.isna(kickoff):
        return "unknown"
    minutes = (kickoff - quote).total_seconds() / 60
    if minutes < 0:
        return "inplay"
    return "closing" if minutes <= 60 else "preclosing"


def zaman_uyumlu_gecmis(df, m):
    """Geçmiş 1-X-2 havuzunu B365 aynı-evre oranlarıyla kur.

    10.2'de güncel bookmaker'a göre WH/PS/BW/VC seçilmesi bazı ekstrem
    favori maçlarında geçmiş havuzunu gereksiz biçimde daraltıyordu.
    Eşleşme yeniden eski ve tutarlı referansa döndürüldü: closing için
    B365C, pre-closing için B365. Güncel bookmaker yalnızca veri kaynağıdır;
    geçmiş örnek seçimini değiştirmez.
    """
    if df is None:
        return pd.DataFrame()
    result = df.copy()
    phase = oran_fazi(m)

    if phase == "closing":
        columns = ["B365CH", "B365CD", "B365CA"]
    elif phase == "preclosing":
        columns = ["B365H", "B365D", "B365A"]
    elif phase == "legacy_unknown":
        # Eski/kimliği belirsiz hedeflerde önce kapanış, yoksa açılış kullan.
        closing = ["B365CH", "B365CD", "B365CA"]
        opening = ["B365H", "B365D", "B365A"]
        closing_ok = all(c in result.columns for c in closing)
        if closing_ok:
            cv = result[closing].apply(pd.to_numeric, errors="coerce")
            if ((cv.gt(1) & cv.lt(float("inf"))).all(axis=1)).any():
                columns = closing
            else:
                columns = opening
        else:
            columns = opening
    else:
        return result.iloc[0:0]

    for source, target in zip(columns, ["REF_H", "REF_D", "REF_A"]):
        result[target] = pd.to_numeric(result[source], errors="coerce") if source in result else float("nan")

    valid = (result[["REF_H", "REF_D", "REF_A"]].gt(1) &
             result[["REF_H", "REF_D", "REF_A"]].lt(float("inf"))).all(axis=1)
    result.attrs.update(
        odds_history_prefix="B365",
        odds_cross_bookmaker=False,
        odds_phase_used="closing" if columns[0].startswith("B365C") else "preclosing",
        odds_time_unknown=phase == "legacy_unknown",
    )
    return result.loc[valid].copy()


def eslesme_oranlari(df, m):
    """Ham 1-X-2 oranlarını doğrudan karşılaştır; hassasiyet mutlak oran farkıdır."""
    values = df[["REF_H", "REF_D", "REF_A"]].apply(pd.to_numeric, errors="coerce")
    target = pd.Series([float(m[key]) for key in ("h", "b", "a")], index=values.columns)
    return values, target


def oran_eslesme_maskesi(df, m, tolerans):
    """Üç 1-X-2 oranının da seçilen mutlak hassasiyet içinde olmasını ister."""
    values, target = eslesme_oranlari(df, m)
    return values.sub(target, axis=1).abs().le(float(tolerans) + 1e-9).all(axis=1)

def etkin_ornek(weights):
    weights = pd.to_numeric(weights, errors="coerce").fillna(0).clip(lower=0)
    return float(weights.sum() ** 2 / (weights ** 2).sum()) if (weights ** 2).sum() else 0.0


def agirlikli_oran(values, weights):
    weights = weights.reindex(values.index).fillna(0)
    return float((values.astype(float) * weights).sum() / weights.sum()) if weights.sum() else 0.0


def analiz_agirliklari(b, m, tolerans):
    # Mesafe de filtreyle aynı oran uzayında hesaplanır.
    values, target = eslesme_oranlari(b, m)
    distance = (values.sub(target, axis=1) / max(float(tolerans), 0.01)).pow(2).mean(axis=1)
    ms = 1.0 / (1.0 + distance)
    # Modest league preference; two-year half-life with a floor preserves old evidence.
    code = ODDS_TO_HISTORY.get(str(m.get("sport_key", "")))
    if code and "league_code" in b:
        ms *= b["league_code"].eq(code).map({True: MODEL_SETTINGS["league_weight"], False: 1.0})
    ms *= zaman_agirliklari(b, m)
    goals = ms.copy()
    note = "Gol oranı desteği yok; MS benzerliği kullanıldı"
    phase = oran_fazi(m)
    prefix = BOOKMAKER_HISTORY_PREFIX.get(str(m.get("totals_bookmaker_key", "")), "B365")
    prefix = "P" if prefix == "PS" else prefix
    cols = tuple(f'{prefix}{"C" if phase == "closing" else ""}{side}2.5' for side in (">", "<"))
    if any(column not in b for column in cols):
        cols = ("B365C>2.5", "B365C<2.5") if phase == "closing" else ("B365>2.5", "B365<2.5")
    try:
        over, under = float(m.get("o25_over")), float(m.get("o25_under"))
        if not all(math.isfinite(x) and x > 1 for x in (over, under)):
            return ms, goals, note
        if oran_fazi(m, totals=True) != phase or any(c not in b for c in cols):
            return ms, goals, note
        ov, un = (pd.to_numeric(b[c], errors="coerce") for c in cols)
        valid = ov.gt(1) & un.gt(1) & ov.lt(float("inf")) & un.lt(float("inf"))
        # Require broad coverage to avoid silently preferring a tiny, selected subset.
        if valid.sum() < 5 or valid.mean() < 0.6:
            return ms, goals, note
        target = (1 / over) / (1 / over + 1 / under)
        historical = (1 / ov) / (1 / ov + 1 / un)
        factor = 1 / (1 + ((historical - target) / 0.08) ** 2)
        goals = ms * factor.where(valid, 0.0)
        if etkin_ornek(goals) < 5:
            return ms, ms.copy(), note
        note = "2.5 gol oranı benzerliği aktif (aynı evre, marjdan arındırılmış profil)"
    except (TypeError, ValueError):
        pass
    return ms, goals, note


def gecmis_tabanlari(df, m):
    """Zaman ağırlıklı taban; tabanın kendi örnek azlığı da nötr dağılıma çekilir."""
    neutral = {"MS 1": 1/3, "Beraberlik": 1/3, "MS 2": 1/3,
               "2.5 Üst": .5, "2.5 Alt": .5, "KG Var": .5, "KG Yok": .5,
               "1.5 Üst": .5, "3.5 Üst": .5}
    if df.empty:
        return neutral
    frame = tarih_oncesi_gecmis(df, m.get("zaman")).copy()
    for key in ("FTHG", "FTAG"):
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
    frame = frame.dropna(subset=["FTHG", "FTAG"])
    if frame.empty:
        return neutral
    weights = zaman_agirliklari(frame, m)
    code = ODDS_TO_HISTORY.get(str(m.get("sport_key", "")))
    league = frame["league_code"].eq(code) if code and "league_code" in frame else pd.Series(False, index=frame.index)
    h, a = frame["FTHG"], frame["FTAG"]
    masks = {"MS 1": h > a, "Beraberlik": h == a, "MS 2": h < a,
             "2.5 Üst": h+a > 2, "2.5 Alt": h+a < 3,
             "KG Var": (h > 0) & (a > 0), "KG Yok": (h == 0) | (a == 0),
             "1.5 Üst": h+a > 1, "3.5 Üst": h+a > 3}
    strength = MODEL_SETTINGS["base_prior_strength"]
    global_mass = float(weights.sum())
    league_weights = weights.where(league, 0.0)
    league_mass = float(league_weights.sum())
    league_blend = league_mass / (league_mass + 100.0)
    result = {}
    for label, mask in masks.items():
        global_rate = (float((mask * weights).sum()) + neutral[label] * strength) / (global_mass + strength)
        league_rate = (float((mask * league_weights).sum()) + global_rate * strength) / (league_mass + strength)
        result[label] = (1-league_blend) * global_rate + league_blend * league_rate
    return result


def tabana_yaklastir(raw, count, prior, strength=5.0):
    return (float(raw) * max(0.0, count) + float(prior) * strength) / (max(0.0, count) + strength)


def birlesik_aday_puani(guven, kararlilik, medyan_ornek):
    """Güven %80 + hassasiyet kararlılığı %20; az etkin örneğe kademeli ceza."""
    ceza = 8.0 * max(0.0, min(1.0, (5.0 - float(medyan_ornek)) / 4.0))
    return round(float(guven) * .8 + min(int(kararlilik), 11) / 11 * 20 - ceza, 1)


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def hassasiyet_taramasi(gecmis_df, hedef, sadece_ayni_lig=False, model_version=MODEL_VERSION):
    """Tek maçı 11 kez tam veri setinde aramak yerine bir kez en geniş havuza indirir.

    DataFrame ve hedef önbellek anahtarına dahildir. Kalibrasyon/market seçimleri
    önbelleğe alınmaz; her çağrıda o ana ait geçmişle yeniden değerlendirilir.
    """
    havuz = zaman_uyumlu_gecmis(sadece_tam_verili_gecmis(gecmis_df), hedef)
    havuz = ayni_lig_gecmisi(havuz, hedef, sadece_ayni_lig)
    havuz = tarih_oncesi_gecmis(havuz, hedef.get("zaman", hedef.get("Date")))
    if havuz.empty:
        return {}
    hedef = dict(hedef)
    hedef["analysis_priors"] = gecmis_tabanlari(havuz, hedef)
    mask = oran_eslesme_maskesi(havuz, hedef, .10)
    havuz = havuz.loc[mask].copy()
    return {
        round(i / 100, 2): hesapla(
            havuz, hedef, round(i / 100, 2),
            sadece_ayni_lig=False, form_aktif=False, kalibrasyon_aktif=False,
            hazir_havuz=True,
        )
        for i in range(11)
    }


def tarama_hedefi(m):
    """Önbellekte API anahtarı veya geçici UI alanı tutulmaz."""
    keys = ("h", "b", "a", "ev", "dep", "zaman", "sport_key", "history_detail_only", *ORAN_KAYIT_ALANLARI)
    return {key: m.get(key) for key in keys}


def birlesik_market_havuzu(b_df, m, min_ornek, sadece_ayni_lig=False,
                          market_gecmis_kayitlari=None, ek_marketler=False,
                          filtreler=None, taramalar=None):
    """Top 50 ve birleşik model aynı yeterlilik, güven ve puanlama yolunu kullanır."""
    if taramalar is None:
        taramalar = hassasiyet_taramasi(b_df, tarama_hedefi(m), sadece_ayni_lig)
    if market_gecmis_kayitlari is None:
        market_gecmis_kayitlari = sabit_kalibrasyon_kayitlari()
    prior = tarih_oncesi_kayitlar(market_gecmis_kayitlari, m.get("zaman"))
    alanlar = {"MS 1": "ms1_p", "Beraberlik": "msx_p", "MS 2": "ms2_p",
               "2.5 Üst": "ms25_p", "2.5 Alt": "ms25a_p", "KG Var": "kg_var_p", "KG Yok": "kg_yok_p"}
    groups = {}
    for tol, (t, b) in taramalar.items():
        if t is None or t.get("belirsiz"):
            continue
        n = len(b)
        if n < max(int(min_ornek), dinamik_min_mac(tol)):
            continue
        candidates = (top10_market_adaylari(t, filtreler=filtreler, tum_guvenler=True) if ek_marketler else
                      [{"label": label, "guven": t.get(field, 0), "oran": market_label_to_odd(m, label)}
                       for label, field in alanlar.items()])
        for candidate in candidates:
            confidence = int(candidate.get("guven", 0))
            label = candidate["label"]
            effective = market_etkin_ornek(t, label)

            # 10.4: Effective sample artık hard-filter değildir. Gerçek örnek sayısı
            # yeterliyse adayı koruruz; düşük etkin örnek birlesik_aday_puani() içinde
            # kademeli az-örnek cezası olarak hesaba katılır.
            ms_soft_penalty = 0
            if t.get("ms_belirsiz") and _tahmin_market_ailesi(label) == "ms":
                # MS ailesi belirsiz diye tahmini tamamen silmek yerine güveni yumuşat.
                # Böylece 09.3'teki görünürlük korunurken 10.x'in belirsizlik bilgisi kaybolmaz.
                ms_soft_penalty = 6
                confidence = max(0, confidence - ms_soft_penalty)

            groups.setdefault(label, []).append(dict(guven=confidence, ornek=n, etkin=effective,
                                                     ms_belirsiz_ceza=ms_soft_penalty,
                                                     tol=tol, t=t, b=b, mk=candidate))
    result = []
    for label, records in groups.items():
        supported = [r for r in records if r["guven"] > 60]
        if len(supported) < 3:
            continue
        spread = float(pd.Series([r["guven"] for r in records]).std(ddof=0))
        raw = sum(record["guven"] for record in records) / len(records)
        confidence, historical_rate, count, delta = market_gecmis_guven_duzeltmesi(label, raw, prior)
        confidence = max(0, min(99, int(round(confidence))))
        if confidence <= 60:
            continue
        median = float(pd.Series([record["ornek"] for record in records]).median())
        effective_median = float(pd.Series([record["etkin"] for record in records]).median())
        ms_belirsiz_cezasi = float(pd.Series([record.get("ms_belirsiz_ceza", 0) for record in records]).median())
        sample_keys = [frozenset(pd.util.hash_pandas_object(
            record["b"][[column for column in ("Date", "league_code", "HomeTeam", "AwayTeam")
                         if column in record["b"]]], index=False).tolist()) for record in records]
        unique_pools = len(set(sample_keys))
        unique_samples = len(frozenset().union(*sample_keys))
        representative = max(records, key=lambda record: (record["guven"], -record["tol"]))
        result.append({
            "label": label, "guven": confidence, "ham_guven": round(raw, 1),
            "puan": round(birlesik_aday_puani(confidence, len(supported), effective_median) - min(6.0, spread * 0.3), 1),
            "ornek": int(round(median)), "kararlilik": len(supported), "guven_dalgalanmasi": round(spread, 2),
            "kararlilik_pct": len(supported) / 11 * 100,
            "az_ornek_cezasi": round(8.0 * max(0.0, min(1.0, (5.0-effective_median)/4.0)), 2),
            "ms_belirsiz_cezasi": round(ms_belirsiz_cezasi, 2),
            "effective_median": effective_median, "unique_pools": unique_pools,
            "unique_samples": unique_samples,
            "toleranslar": [f'{record["tol"]:.2f}' for record in supported], "temsilci": representative,
            "market_gecmis_basari": historical_rate, "market_gecmis_adet": count,
            "market_guven_delta": round(delta, 2),
        })
    return sorted(result, key=lambda item: (item["puan"], item["guven"], item["kararlilik"], item["label"]), reverse=True)


def birlesik_tahmin_olustur(ana, havuz, m):
    """Temsilci örnekleri taşırken ana/alternatif etiketleri ve puanları birlikte günceller."""
    t = dict(ana["temsilci"]["t"])
    b = ana["temsilci"]["b"]
    alt = next((candidate for candidate in havuz if candidate["label"] != ana["label"]
                and _tahmin_market_ailesi(candidate["label"]) != _tahmin_market_ailesi(ana["label"])), None)
    t.update({
        "confidence_spread": ana.get("guven_dalgalanmasi", 0),
        "effective_combined_samples": ana.get("effective_median", 0),
        "stability_unique_pools": ana.get("unique_pools", 0),
        "unique_history_samples": ana.get("unique_samples", 0),
        "ana_label": ana["label"], "ana_p": ana["guven"], "ana_ham_guven": ana["ham_guven"],
        "ana_odd": market_label_to_odd(m, ana["label"]),
        "score": ana["puan"], "playable_score": ana["puan"], "birlesik_puan": ana["puan"],
        "ornek": len(b), "birlesik_ornek_medyan": ana["ornek"],
        "kullanilan_tolerans": float(ana["temsilci"]["tol"]),
        "stability_tols": ana["toleranslar"], "stability_count": ana["kararlilik"],
        "stability_pct": ana["kararlilik_pct"], "stability_text": " · ".join(ana["toleranslar"]),
        "birlesik_model": True, "model_version": MODEL_VERSION,
        "az_ornek_cezasi": ana["az_ornek_cezasi"],
        "market_gecmis_basari": ana["market_gecmis_basari"], "market_gecmis_adet": ana["market_gecmis_adet"],
        "market_guven_delta": ana["market_guven_delta"], "puan_formulu": "Güven %80 + Kararlılık %20 − Dalgalanma cezası",
        "oynanabilir": ana["guven"] > 60, "oynanabilir_esik_ok": ana["guven"] > 60,
        "alt_label": alt["label"] if alt else "", "alt_p": alt["guven"] if alt else 0,
        "alt_ornek": alt["ornek"] if alt else 0, "alt_puan": alt["puan"] if alt else 0,
        "alt_kararlilik": alt["kararlilik"] if alt else 0,
        "alt_hassasiyetler": alt["toleranslar"] if alt else [],
        "alt_hassasiyet": float(alt["temsilci"]["tol"]) if alt else None,
        "alt_market_gecmis_basari": alt["market_gecmis_basari"] if alt else None,
        "alt_market_gecmis_adet": alt["market_gecmis_adet"] if alt else 0,
    })
    for band, condition in (("early", lambda tol: tol <= .05), ("late", lambda tol: tol > .05)):
        values = [tol for tol in ana["toleranslar"] if condition(float(tol))]
        t[f"stability_{band}_tols"] = values
        t[f"stability_{band}_text"] = " · ".join(values)
    raw_hits = [tahmin_tuttu_mu(ana["label"], row) for _, row in b.iterrows()]
    raw_hits = [hit for hit in raw_hits if hit is not None]
    t["ana_raw_p"] = round(sum(raw_hits) / len(raw_hits) * 100) if raw_hits else 0
    t["scenario_label"] = ana["label"]
    t["guven_renk"], t["guven_badge_cls"], t["guven_badge_lbl"] = guven_renk(t["ana_p"])
    # A different representative's combo must not contradict the selected market.
    previous_combo = {key: t.get(key) for key in ("combo_var", "combo_label", "combo_p", "combo_hit", "combo_raw_p", "combo_level")}
    t["combo_var"] = False
    t["combo_label"], t["combo_p"], t["combo_level"], t["combo_hit"], t["combo_raw_p"] = "", 0, "", 0, 0
    def compatible(label):
        return any(tahmin_tuttu_mu(ana["label"], {"FTHG": home, "FTAG": away})
                   and tahmin_tuttu_mu(label, {"FTHG": home, "FTAG": away})
                   for home in range(6) for away in range(6))
    combo = next((candidate for candidate in havuz if "+" in candidate["label"] and compatible(candidate["label"])), None)
    if combo and combo["label"] != ana["label"]:
        combo_examples = combo["temsilci"]["b"]
        hits = sum(bool(tahmin_tuttu_mu(combo["label"], row)) for _, row in combo_examples.iterrows())
        t.update(combo_var=True, combo_label=combo["label"], combo_p=combo["guven"], combo_hit=hits,
                 combo_raw_p=round(hits / len(combo_examples) * 100), combo_level="Premium")
    elif previous_combo.get("combo_var") and compatible(previous_combo.get("combo_label")):
        t.update(previous_combo)
    t["eg"], t["dg"] = skoru_tahmine_uydur(t.get("eg", 1), t.get("dg", 1), t["ana_label"], t.get("ms_mod", "D"), t["alt_label"], "")
    return t, b


def top50_liste_sec(adaylar, limit=50):
    """Canlı ve backtest listelerinde ortak sıralama ve maç başına tek tercih."""
    ordered = sorted(adaylar, key=lambda item: (item["t"]["score"], item["t"]["ana_p"], item["t"]["stability_count"], mac_key(item["m"])), reverse=True)
    unique, used = [], set()
    for item in ordered:
        key = mac_key(item["m"])
        if key in used:
            continue
        used.add(key)
        unique.append(item)
        if limit and len(unique) >= limit:
            break
    return unique


def backtest_verisini_hazirla(gecmis_df, test_sezonu, lig_kodlari, max_test):
    veri = sadece_tam_verili_gecmis(gecmis_df).copy()
    if veri.empty:
        return veri, veri
    veri["Date"] = tarih_serisi_oku(veri["Date"])
    veri = veri.dropna(subset=["Date", "FTHG", "FTAG", "FTR"])
    veri = veri.sort_values(["Date", "league_code", "HomeTeam", "AwayTeam"], kind="stable").drop_duplicates(
        subset=["Date", "league_code", "HomeTeam", "AwayTeam"], keep="last")
    test = veri[veri["season_code"].astype(str) == str(test_sezonu)]
    if lig_kodlari:
        test = test[test["league_code"].isin(lig_kodlari)]
    return veri, test.tail(int(max_test))


def backtest_hedefi(row):
    inverse = {code: sport for sport, code in ODDS_TO_HISTORY.items()}
    target = {"ev": row.get("HomeTeam", ""), "dep": row.get("AwayTeam", ""),
              "zaman": row["Date"], "sport_key": inverse.get(row.get("league_code"), ""), "lig": row.get("league_code", "")}
    def valid(value):
        try:
            return pd.notna(value) and math.isfinite(float(value)) and float(value) > 1
        except (TypeError, ValueError):
            return False
    chosen = None
    for phase in ("closing", "preclosing"):
        for key in ("williamhill", "pinnacle", "bwin", "betvictor", "bet365"):
            prefix = BOOKMAKER_HISTORY_PREFIX[key]
            columns = [f'{prefix}{"C" if phase == "closing" else ""}{side}' for side in "HDA"]
            if all(valid(row.get(column)) for column in columns):
                chosen = (key, prefix, phase, columns)
                break
        if chosen:
            break
    if not chosen:
        return None
    bookmaker, prefix, phase, columns = chosen
    target.update(odds_phase=phase, totals_phase=phase, bookmaker_key=bookmaker, totals_bookmaker_key=bookmaker)
    target.update({key: float(row[column]) for key, column in zip(("h", "b", "a"), columns)})
    prefix = "P" if prefix == "PS" else prefix
    goal_cols = [f'{prefix}{"C" if phase == "closing" else ""}{side}2.5' for side in (">", "<")]
    for key, column in zip(("o25_over", "o25_under"), goal_cols):
        target[key] = float(row[column]) if valid(row.get(column)) else None
    return target


def backtest_kaydi(row, target, t):
    label = t.get("ana_label", "")
    hit = tahmin_tuttu_mu(label, row)
    if hit is None or int(t.get("ana_p", 0)) <= 60:
        return None
    odd = market_label_to_odd(target, label)
    alt_label = t.get("alt_label", "") if int(t.get("alt_p", 0)) > 60 else ""
    alt_hit = tahmin_tuttu_mu(alt_label, row) if alt_label else None
    return {
        "Tarih": row["Date"].date(), "Lig": row.get("league_code", "-"),
        "Maç": f'{row.get("HomeTeam", "")} - {row.get("AwayTeam", "")}',
        "Tahmin": label, "Güven": int(t["ana_p"]),
        "Ana Puan": float(t.get("score", 0)), "Ana Medyan Örnek": int(t.get("birlesik_ornek_medyan", t.get("ornek", 0))),
        "Ana Kararlılık": int(t.get("stability_count", 0)), "Ana Hassasiyetler": " · ".join(t.get("stability_tols", [])),
        "Alternatif Tahmin": alt_label, "Alt. Güven": int(t.get("alt_p", 0)) if alt_label else None,
        "Alt. Örnek": t.get("alt_ornek") if alt_label else None, "Alt. Puan": t.get("alt_puan") if alt_label else None,
        "Alt. Kararlılık": t.get("alt_kararlilik") if alt_label else None,
        "Alt. Hassasiyetler": " · ".join(t.get("alt_hassasiyetler", [])) if alt_label else "",
        "Alt. Tuttu": bool(alt_hit) if alt_hit is not None else None, "Örnek": int(t.get("ornek", 0)),
        "Sonuç": f'{int(row["FTHG"])}-{int(row["FTAG"])}', "Tuttu": bool(hit),
        "Oran": odd, "Kâr (100 TL)": round((odd - 1) * 100 if hit else -100, 2) if odd else None,
    }




def kart_takim_adi(ad):
    """Kartlarda baştaki yaygın kulüp eklerini gizler; veri eşleştirmesini etkilemez."""
    s = str(ad or "").strip()
    s = re.sub(r"^(?:FC|CF|AFC|SC|AC)\s+", "", s, flags=re.IGNORECASE)
    return s.strip() or str(ad or "")

def parse_mac_datetime(value):
    """Ofsetli zamanı Türkiye saatine çevirir; bozuk tarihi 'şimdi' yapmaz."""
    if value is None or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt.astimezone(TR_TIMEZONE).replace(tzinfo=None) if dt.tzinfo else dt
    except (TypeError, ValueError, OverflowError):
        return None

st.set_page_config(page_title="YapAiKupon", layout="wide", page_icon="⚡")


# ==========================================================
# API KEY ACCESS SYSTEM
# ==========================================================

# Kullanım:
# 1) Kullanıcı sidebar'dan kendi ODDS API KEY'ini girebilir.
# 2) İstersen Streamlit Cloud > Settings > Secrets içine ODDS_API_KEY ekleyebilirsin.
#    Sidebar'dan girilen key, secrets key'in önüne geçer.

def get_secret_value(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_app_api_key():
    user_key = str(st.session_state.get("user_api_key", "")).strip()
    if user_key:
        return user_key
    return str(get_secret_value("ODDS_API_KEY", "")).strip()


def get_api_football_key():
    """API-Football anahtarı. Sidebar girişi secrets değerinin önüne geçer."""
    user_key = str(st.session_state.get("user_api_football_key", "")).strip()
    if user_key:
        return user_key
    for secret_name in ("API_FOOTBALL_KEY", "APIFOOTBALL_KEY", "API_FOOTBALL_API_KEY"):
        val = str(get_secret_value(secret_name, "") or "").strip()
        if val:
            return val
    return ""


def api_key_panel():
    with st.sidebar:
        st.markdown("### 🔑 API Key Girişi")

        current_key = st.session_state.get("user_api_key", "")
        api_key_input = st.text_input(
            "ODDS API KEY",
            value=current_key,
            placeholder="API key gir...",
            type="password",
            key="api_key_input",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Kaydet", use_container_width=True, key="save_api_key_btn"):
                st.session_state["user_api_key"] = api_key_input.strip()
                st.success("API Key kaydedildi ✅")
                st.rerun()

        with c2:
            if st.button("Temizle", use_container_width=True, key="clear_api_key_btn"):
                st.session_state.pop("user_api_key", None)
                st.success("API Key temizlendi")
                st.rerun()

        if get_app_api_key():
            st.success("Odds API key aktif ✅")
        else:
            st.warning("Odds API key yok. Kayıtlı bülten varsa açılır; yeni veri çekmek için API key gerekir.")

        st.markdown("##### ⚽ API-Football (bağlam fallback)")
        af_current = st.session_state.get("user_api_football_key", "")
        af_input = st.text_input(
            "API-FOOTBALL KEY",
            value=af_current,
            placeholder="H2H / son form fallback için...",
            type="password",
            key="api_football_key_input",
        )
        af1, af2 = st.columns(2)
        with af1:
            if st.button("AF Kaydet", use_container_width=True, key="save_api_football_key_btn"):
                st.session_state["user_api_football_key"] = af_input.strip()
                st.success("API-Football key kaydedildi ✅")
                st.rerun()
        with af2:
            if st.button("AF Temizle", use_container_width=True, key="clear_api_football_key_btn"):
                st.session_state.pop("user_api_football_key", None)
                st.rerun()
        if get_api_football_key():
            st.caption("API-Football fallback aktif ✅")
        else:
            st.caption("API-Football key yok: bağlam yalnızca yerel geçmiş + Odds API ile çalışır.")


def require_api_key():
    if not get_app_api_key():
        st.warning("Devam etmek için sol menüden ODDS API KEY girmen gerekiyor ⚠️")
        st.stop()


def limit_for_free(items, free_limit=999999):
    # Üyelik sistemi kaldırıldı. Artık sınırlama yok.
    return list(items or [])


def legal_notice_top():
    st.markdown(
        """
        <div style="background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:12px 14px;margin:8px 0;color:#7c2d12;font-size:0.86rem;">
        <b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler, geçmiş veri karşılaştırmaları ve yapay zekâ destekli tahminler sunar.
        Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir ve bağımlılık oluşturabilir.
        </div>
        """,
        unsafe_allow_html=True,
    )


def legal_sidebar_sections():
    """Sidebar içinde disclaimer ve kullanım şartları."""
    with st.sidebar:
        st.markdown("---")

        with st.expander("⚖️ Disclaimer", expanded=False):
            st.markdown("""
Bu platform yalnızca **istatistiksel analiz** ve **yapay zekâ destekli tahminler** sunar.

Sunulan içerikler kesinlik içermez ve yatırım tavsiyesi değildir.

Kullanıcılar kendi kararlarını kendileri verir. Bu platform üzerinden doğrudan bahis oynanmaz ve herhangi bir bahis hizmeti sunulmaz.

**Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.**
            """)

        with st.expander("📜 Kullanım Şartları", expanded=False):
            st.markdown("""
**1. Hizmet Tanımı**  
Bu platform, spor karşılaşmalarına ilişkin istatistiksel analizler ve yapay zekâ destekli tahminler sunar.

**2. Sorumluluk Reddi**  
Platformda yer alan hiçbir içerik kesin kazanç garantisi vermez. Kullanıcılar, elde ettikleri verileri kendi riskleri doğrultusunda değerlendirir.

**3. Bahis Hizmeti Sunulmaması**  
Bu platform bir bahis sitesi değildir. Kullanıcılara doğrudan bahis oynama imkânı sunulmaz ve herhangi bir bahis kuruluşu ile resmi bir bağlantısı bulunmaz.

**4. Kullanıcı Sorumluluğu**  
Kullanıcılar, platformu kullanırken yürürlükteki yasalara uymakla yükümlüdür.

**5. Hizmet Değişikliği**  
Platform, hizmet içeriğini önceden bildirmeksizin değiştirme hakkını saklı tutar.
            """)


def legal_footer():
    """Sayfanın en altında kısa hukuki footer."""
    uygula_tema_css(bool(st.session_state.get("koyu_mod", True)))
    st.markdown("""
    ---
    <div style="text-align:center;font-size:12px;color:#64748b;line-height:1.55;padding:10px 0 4px 0;">
        <b>Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analiz ve yapay zekâ destekli tahminler sunar.<br>
        Kesin kazanç garantisi verilmez. Kullanıcılar kararlarını kendi sorumluluğunda verir.<br>
        Bu platform üzerinden doğrudan bahis oynanmaz. Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.
    </div>
    """, unsafe_allow_html=True)



APP_SCHEMA_VERSION = 91
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    korunan = {key: st.session_state[key] for key in ("user_api_key", "user_api_football_key", "koyu_mod") if key in st.session_state}
    st.session_state.clear()
    st.session_state.update(korunan)
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

# Uygulama ilk açılışta varsayılan olarak koyu modda başlasın.
if "koyu_mod" not in st.session_state:
    st.session_state["koyu_mod"] = True

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #f6f8fc;
    color: #0f172a;
}

.stApp {
    background: linear-gradient(180deg, #f8fbff 0%, #f3f6fb 100%);
}
section[data-testid="stSidebar"] {
    background: #eef3fb !important;
    border-right: 1px solid #d6e0ef;
}
section[data-testid="stSidebar"] label {
    font-size: 0.82rem !important;
    color: #4b5563 !important;
}
button[data-testid="stSidebarCollapseButton"],
button[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"] button {
    background:#0b1b33 !important;
    border:1px solid #315487 !important;
    border-radius:9px !important;
    opacity:1 !important;
    box-shadow:0 3px 10px rgba(15,23,42,.18) !important;
}
button[data-testid="stSidebarCollapseButton"] svg,
button[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
    color:#ffffff !important;
    fill:#ffffff !important;
    stroke:#ffffff !important;
    opacity:1 !important;
}
.main .block-container {
    background: transparent;
    padding-top: 1.2rem;
    max-width: 1500px;
}
.top-header {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    margin-bottom:1.1rem;
}
.top-header h2 {
    font-family:'Rajdhani',sans-serif;
    font-size:1.9rem;
    font-weight:700;
    color:#0b1f3a;
    margin:0;
    letter-spacing:1px;
}
.top-header .sub {
    font-size:0.88rem;
    color:#64748b;
    margin-top:3px;
}
.top-filters {
    display:flex;
    gap:10px;
    margin:12px 0 18px 0;
    flex-wrap:wrap;
}
.tf-chip {
    background:#111926;
    border:1px solid #1f2b3f;
    color:#77b4ff;
    padding:8px 14px;
    border-radius:999px;
    font-size:0.8rem;
    font-weight:600;
}
.mac-badge {
    background:#121826;
    border:1px solid #22304a;
    border-radius:12px;
    padding:8px 18px;
    font-family:'Rajdhani',sans-serif;
    font-size:1.5rem;
    font-weight:700;
    color:#27ae60;
    text-align:center;
    min-width:110px;
}
.mac-badge span {
    color:#7b8291;
    font-size:0.75rem;
    display:block;
    letter-spacing:1px;
}
.mac-kart {
    background:#13151e;
    border:1px solid #1e2130;
    border-radius:16px;
    padding:16px 18px;
    margin-bottom:12px;
    display:grid;
    grid-template-columns:90px 1.6fr 190px 180px 180px;
    gap:14px;
    align-items:center;
    transition:.2s ease;
}
.mac-kart:hover {
    border-color:#2a3a52;
    box-shadow:0 0 0 1px rgba(39,174,96,.12);
}
.mk-zaman { text-align:center; }
.mk-star {
    font-size:1rem;
    color:#596073;
    margin-bottom:4px;
    display:block;
}
.mk-saat {
    font-family:'Rajdhani',sans-serif;
    font-size:1.45rem;
    font-weight:700;
    color:#fff;
    line-height:1;
}
.mk-lig {
    font-size:0.68rem;
    color:#8b94a8;
    background:#1a1d26;
    border-radius:5px;
    padding:3px 8px;
    margin-top:8px;
    display:inline-block;
}
.mk-takimlar .mk-ev {
    font-size:1.06rem;
    font-weight:700;
    color:#fff;
    margin-bottom:8px;
}
.mk-takimlar .mk-dep {
    font-size:1.02rem;
    font-weight:600;
    color:#c6cfdd;
}
.mk-mini {
    font-size:0.75rem;
    color:#8f98ab;
    margin-top:8px;
}
.mk-label {
    font-size:0.66rem;
    color:#858ca0;
    letter-spacing:1px;
    text-transform:uppercase;
    margin-bottom:5px;
}
.ana-pill {
    background:#27ae60;
    color:#fff;
    font-family:'Rajdhani',sans-serif;
    font-size:1.08rem;
    font-weight:700;
    padding:5px 15px;
    border-radius:7px;
    display:inline-block;
}
.ana-pill.kirmizi { background:#c0392b; }
.ana-pill.sari { background:#c9a227; color:#111; }
.ana-pill.gri { background:#5d6779; color:#fff; }

.guven-pct {
    font-family:'Rajdhani',sans-serif;
    font-size:1.32rem;
    font-weight:700;
    color:#fff;
}
.guven-bar {
    height:6px;
    border-radius:6px;
    background:#1e2130;
    margin-top:5px;
    overflow:hidden;
}
.guven-fill { height:100%; border-radius:6px; }

.alt-pill {
    background:#17304d;
    color:#6ec1ff;
    font-size:0.82rem;
    font-weight:700;
    padding:4px 10px;
    border-radius:6px;
    display:inline-block;
    margin-bottom:8px;
}
.combo-pill {
    background:#1e2130;
    color:#f39c12;
    font-size:0.8rem;
    font-weight:700;
    padding:4px 10px;
    border-radius:6px;
    display:inline-block;
}
.oran-row {
    display:flex;
    gap:12px;
    align-items:center;
}
.oran-box { text-align:center; }
.oran-box .ov {
    font-size:0.65rem;
    color:#687084;
}
.oran-box .val {
    font-size:0.98rem;
    font-weight:700;
    color:#fff;
}

.hero-boxes {
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    gap:14px;
    margin-bottom:14px;
}
.hbox {
    border-radius:16px;
    padding:20px 24px;
    text-align:center;
}
.hbox.green {
    background:linear-gradient(135deg,#153b25,#1b5636);
    border:1px solid #1f8d53;
}
.hbox.blue {
    background:linear-gradient(135deg,#102340,#173764);
    border:1px solid #2c7be5;
}
.hbox.dark {
    background:linear-gradient(135deg,#1a1d28,#232845);
    border:1px solid #2c3152;
}
.hb-label {
    font-size:0.68rem;
    color:#aeb5c3;
    letter-spacing:2px;
    text-transform:uppercase;
    margin-bottom:10px;
}
.hb-val {
    font-family:'Rajdhani',sans-serif;
    font-size:2.35rem;
    font-weight:700;
    color:#fff;
    line-height:1;
}
.hb-sub {
    font-size:0.82rem;
    color:#c0c7d3;
    margin-top:7px;
}
.hb-badge {
    display:inline-block;
    margin-top:9px;
    padding:4px 12px;
    border-radius:999px;
    font-size:0.74rem;
    font-weight:700;
}
.badge-yuksek { background:#27ae60; color:#fff; }
.badge-orta   { background:#e67e22; color:#fff; }
.badge-dusuk  { background:#c0392b; color:#fff; }

.tahmin-kart, .diger-kart, .neden-kart, .kupon-kart {
    background:#13151e;
    border:1px solid #1e2130;
    border-radius:16px;
    padding:18px 22px;
}
.tk-title {
    font-family:'Rajdhani',sans-serif;
    font-size:1.05rem;
    font-weight:700;
    color:#fff;
    letter-spacing:1px;
    margin-bottom:14px;
    text-transform:uppercase;
}
.tk-row, .diger-row {
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:10px 0;
    border-bottom:1px solid #1a1d26;
}
.tk-row:last-child, .diger-row:last-child { border-bottom:none; }
.tk-key { font-size:0.84rem; color:#9098aa; }

.risk-row {
    background:#1a1d26;
    border-radius:10px;
    padding:10px 16px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-top:14px;
}
.rk {
    font-size:0.8rem;
    color:#8d95a8;
    font-weight:700;
    letter-spacing:1px;
}
.risk-pill {
    padding:5px 18px;
    border-radius:7px;
    font-family:'Rajdhani',sans-serif;
    font-size:1rem;
    font-weight:700;
}
.risk-dusuk  { background:#27ae60; color:#fff; }
.risk-orta   { background:#e67e22; color:#fff; }
.risk-yuksek { background:#c0392b; color:#fff; }

.diger-left {
    display:flex;
    align-items:center;
    gap:10px;
}
.diger-icon {
    font-size:1.05rem;
    width:20px;
    text-align:center;
}
.diger-name {
    font-size:0.86rem;
    font-weight:700;
    color:#fff;
}
.diger-sub {
    font-size:0.72rem;
    color:#666;
}
.diger-badge {
    padding:4px 12px;
    border-radius:6px;
    font-size:0.84rem;
    font-weight:700;
    font-family:'Rajdhani',sans-serif;
}
.db-green { background:#183925; color:#3ddb7c; }
.db-gold  { background:#37290f; color:#f1c40f; }
.db-red   { background:#391212; color:#ff6b6b; }
.db-blue  { background:#17304d; color:#6ec1ff; }

.surpriz-radar {
    background:#2d0a0a;
    border:1px solid #e74c3c;
    border-radius:10px;
    padding:12px 18px;
    color:#ff6f6f;
    font-weight:700;
    font-size:0.9rem;
    margin-bottom:12px;
}
.neden-item {
    padding:8px 0;
    border-bottom:1px solid #1a1d26;
    color:#c7cfdd;
    font-size:0.88rem;
}
.neden-item:last-child {
    border-bottom:none;
}

.list-heading {
    color:#0b1f3a !important;
    font-family:'Rajdhani',sans-serif;
    font-size:1.85rem;
    font-weight:800;
    letter-spacing:.5px;
    margin:8px 0 2px 0;
}
.stButton > button {
    box-shadow:none;
}
.api-navy details {background: linear-gradient(90deg,#07111f 0%, #0a1830 100%);border:1px solid #233e67;border-radius:12px;padding:6px 10px;}
.api-navy summary {color:#f8fbff;font-weight:700;}
.api-navy [data-testid="stTextInputRootElement"] > div, .api-navy div[data-baseweb="input"] > div {background:#0d1a2f !important;border-color:#33598c !important;}
.live-badge {display:inline-block;padding:4px 10px;border-radius:999px;font-size:0.72rem;font-weight:800;letter-spacing:.3px;}
.detail-header-box {background: linear-gradient(90deg,#07111f 0%, #0a1830 100%);border:1px solid #223c63;border-radius:18px;padding:14px 18px;margin-bottom:12px;}
.floating-coupon {
    position: fixed;
    right: 22px;
    bottom: 22px;
    width: 360px;
    max-height: 70vh;
    overflow-y: auto;
    z-index: 9999;
    background: linear-gradient(180deg,#07111f 0%, #0a1830 100%);
    border: 1px solid #284977;
    border-radius: 18px;
    box-shadow: 0 18px 45px rgba(2,8,23,.45);
    padding: 14px 16px;
}
.floating-coupon::-webkit-scrollbar {
    width: 6px;
}
.floating-coupon::-webkit-scrollbar-thumb {
    background: #facc15;
    border-radius: 99px;
}
.floating-coupon-title {font-family:"Rajdhani",sans-serif;color:#f8fbff;font-size:1.2rem;font-weight:700;margin-bottom:8px;}
.floating-coupon-sub {color:#9db2d1;font-size:.76rem;margin-bottom:10px;}
.coupon-item {border:1px solid #223c63;background:#0b1628;border-radius:12px;padding:10px 12px;margin-bottom:8px;}
.coupon-item-top {display:flex;align-items:center;justify-content:space-between;gap:10px;color:#f8fbff;font-size:.86rem;font-weight:700;}
.coupon-item-sub {color:#8fa0ba;font-size:.74rem;margin-top:5px;}


/* === LIGHT PAGE CONTRAST FIXES === */
html, body, [class*="css"] {
    background: #f6f8fc !important;
    color: #0f172a !important;
}
.stApp {
    background: linear-gradient(180deg, #f8fbff 0%, #f3f6fb 100%) !important;
}
.main .block-container {
    background: transparent !important;
}
section[data-testid="stSidebar"] {
    background: #eef3fb !important;
    border-right: 1px solid #d6e0ef !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] label *,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #334155 !important;
    -webkit-text-fill-color:#334155 !important;
}

/* Top controls */
.control-label, .section-kicker, .summary-note, .league-chip-note {
    color: #64748b !important;
}
div[data-baseweb="popover"],
div[data-testid="stPopover"] button,
div[data-testid="stPopoverButton"] > button {
    background: linear-gradient(180deg,#0d1a2f 0%, #0b1526 100%) !important;
    color: #f8fafc !important;
}
div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] div[data-baseweb="input"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
div[data-testid="stDateInput"] div[data-baseweb="input"] > div,
div[data-testid="stNumberInputContainer"],
div[data-testid="stTextInputRootElement"] {
    background: #0f1b31 !important;
    border-color: #284977 !important;
    color: #f8fafc !important;
}
input, textarea {
    color: #f8fafc !important;
}
.stSelectbox label, .stMultiSelect label, .stDateInput label, .stTextInput label, .stNumberInput label {
    color: #64748b !important;
}
.stCheckbox label, .stRadio label {
    color: #0f172a !important;
}
.stCheckbox label span, .stRadio label span {
    color: #0f172a !important;
}
.stMultiSelect [data-baseweb="tag"] {
    background: #ff5a52 !important;
    color: white !important;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(180deg,#0d1a2f 0%, #0b1526 100%) !important;
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
    border: 1px solid #284977 !important;
}
.stButton > button *,
section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] .stButton > button * {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    opacity:1 !important;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div *,
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] input,
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] button,
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] button * {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    opacity:1 !important;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] svg,
section[data-testid="stSidebar"] div[data-testid="stNumberInput"] svg {
    fill:#cbd5e1 !important;
    color:#cbd5e1 !important;
}
div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary *,
div[data-testid="stTabs"] button,
div[data-testid="stTabs"] button * {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    opacity:1 !important;
}
div[data-testid="stExpander"] summary svg {
    color:#f8fafc !important;
    fill:#f8fafc !important;
}
div[data-testid="stDialog"] div[data-testid="stExpander"] summary,
div[data-testid="stDialog"] div[data-testid="stExpander"] summary * {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
}
div[data-testid="stDialog"] h1,
div[data-testid="stDialog"] h2,
div[data-testid="stDialog"] h3 {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
}
.detail-form-sidebar-title {
    background:#0b1628;
    border:1px solid #284977;
    border-radius:12px;
    padding:12px 13px;
    margin-bottom:10px;
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    font-weight:900;
}
.detail-form-sidebar-title span {
    display:block;
    color:#9db2d1 !important;
    -webkit-text-fill-color:#9db2d1 !important;
    font-size:.70rem;
    font-weight:600;
    margin-top:4px;
}
.recent-match-list {
    display:flex;
    flex-direction:column;
    gap:6px;
    width:100%;
}
.recent-match-row {
    background:#0b1628;
    border:1px solid #223c63;
    border-radius:9px;
    padding:7px 9px;
    min-width:0;
}
.recent-top, .recent-bottom {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
}
.recent-top {
    color:#9db2d1 !important;
    -webkit-text-fill-color:#9db2d1 !important;
    font-size:.68rem;
}
.recent-bottom {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    font-size:.76rem;
    font-weight:700;
    margin-top:3px;
}
.recent-bottom span {
    min-width:0;
    white-space:normal;
    overflow-wrap:anywhere;
}
.recent-bottom strong { color:#ffd24a !important;-webkit-text-fill-color:#ffd24a !important;white-space:nowrap; }
.recent-top .win { color:#3ddb7c !important;-webkit-text-fill-color:#3ddb7c !important; }
.recent-top .draw { color:#facc15 !important;-webkit-text-fill-color:#facc15 !important; }
.recent-top .loss { color:#ff6b6b !important;-webkit-text-fill-color:#ff6b6b !important; }
.h2h-teams { align-items:flex-start; }
.h2h-teams span:last-child { text-align:right; }
.sidebar-high-market-title {
    background:#dbeafe;
    border:1px solid #93c5fd;
    border-radius:12px;
    padding:11px 12px;
    margin:4px 0 12px 0;
}
.sidebar-high-market-title b {
    display:block;
    color:#0f172a !important;
    -webkit-text-fill-color:#0f172a !important;
    font-size:.95rem;
}
.sidebar-high-market-title span {
    display:block;
    color:#334155 !important;
    -webkit-text-fill-color:#334155 !important;
    font-size:.75rem;
    font-weight:700;
    line-height:1.4;
    margin-top:4px;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4 {
    color:#0f172a !important;
    -webkit-text-fill-color:#0f172a !important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary,
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary * {
    color:#f8fafc !important;
    -webkit-text-fill-color:#f8fafc !important;
    opacity:1 !important;
}
div[data-testid="stSpinner"],
div[data-testid="stSpinner"] *,
div[data-testid="stStatusWidget"],
div[data-testid="stStatusWidget"] * {
    color:#0f172a !important;
    -webkit-text-fill-color:#0f172a !important;
    opacity:1 !important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] label,
section[data-testid="stSidebar"] div[data-testid="stExpander"] label *,
section[data-testid="stSidebar"] div[data-testid="stExpander"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {
    color:#cbd5e1 !important;
    -webkit-text-fill-color:#cbd5e1 !important;
}
.stButton > button:hover {
    border-color: #facc15 !important;
}
button[kind="primary"], .st-emotion-cache * button[kind="primary"] {
    color: #fff !important;
}

/* Cards remain dark */
.mac-kart,
.tahmin-kart, .diger-kart, .neden-kart, .kupon-kart,
.combo-kart, .canli-kart, .strateji-kart, .oranlar-kart,
.metrics-card, .control-card, .top-shell, .helper-bar,
.rehber-box, .top-hero, .topbar-wrap {
    color: #e5e7eb !important;
}

/* Detail screen white clash fixes */
.diger-kart,
.combo-kart,
.canli-kart,
.strateji-kart,
.oranlar-kart,
.tahmin-kart,
.neden-kart,
.kupon-kart {
    background: linear-gradient(135deg,#0f172a,#111827) !important;
    border: 1px solid #1f2a44 !important;
    color: #e5e7eb !important;
    box-shadow: 0 10px 30px rgba(0,0,0,0.22);
}
.diger-kart *,
.combo-kart *,
.canli-kart *,
.strateji-kart *,
.oranlar-kart *,
.tahmin-kart *,
.neden-kart *,
.kupon-kart * {
    color: inherit;
}
.diger-row, .tk-row, .neden-item {
    border-bottom: 1px solid #1f2a44 !important;
}
.tk-title, .diger-name, .panel-title, .list-heading {
    color: #0b1f3a !important;
}
.kupon-kart .tk-title,
.tahmin-kart .tk-title,
.diger-kart .tk-title,
.neden-kart .tk-title,
.combo-kart .tk-title,
.canli-kart .tk-title,
.strateji-kart .tk-title,
.oranlar-kart .tk-title {
    color: #f8fafc !important;
}
.tk-key, .diger-sub, .mk-mini, .panel-date, .list-subheading {
    color: #94a3b8 !important;
}
.diger-badge, .combo-badge {
    background: #1e293b !important;
    color: #facc15 !important;
}
.db-green { background:#183925 !important; color:#3ddb7c !important; }
.db-gold  { background:#37290f !important; color:#f1c40f !important; }
.db-red   { background:#391212 !important; color:#ff6b6b !important; }
.db-blue  { background:#17304d !important; color:#6ec1ff !important; }

/* Main titles on light background */
.top-header h2, .list-heading {
    color:#0b1f3a !important;
}
.top-header .sub, .panel-date, .summary-note, .list-subheading {
    color:#64748b !important;
}

/* Remove subtitle if exists by hiding */
.list-subheading {
    display:none !important;
}

/* Header / detail title bars */
.detail-title-bar, .detail-header-box {
    background: linear-gradient(90deg,#07111f 0%, #0a1830 100%) !important;
    color: #f8fafc !important;
    border: 1px solid #21334f !important;
    border-radius: 14px !important;
    padding: 10px 14px !important;
}

/* API expander */
details, summary {
    color: #f8fafc !important;
}
.streamlit-expanderHeader {
    background: linear-gradient(90deg,#07111f 0%, #0a1830 100%) !important;
    color: #f8fafc !important;
    border: 1px solid #21334f !important;
    border-radius: 12px !important;
}
div[data-testid="stExpander"] {
    background: linear-gradient(90deg,#07111f 0%, #0a1830 100%) !important;
    border: 1px solid #21334f !important;
    border-radius: 12px !important;
    padding: 4px 8px !important;
}
div[data-testid="stExpander"] * {
    color: #f8fafc !important;
}

/* Small info texts under dark blocks */
.metrics-card .sub,
.hb-sub,
.hb-label,
.mk-label,
.rk {
    color: #cbd5e1 !important;
}

.detail-header-box * {
    color: #f8fbff !important;
    text-shadow: none !important;
}
.detail-header-box {
    display:block !important;
}

/* Force white text in detail dark cards */
.tahmin-kart, .diger-kart, .neden-kart, .kupon-kart,
.tahmin-kart *, .diger-kart *, .neden-kart *, .kupon-kart * {
    color: #f8fbff !important;
}
.tahmin-kart small,
.diger-kart small,
.neden-kart small {
    color: #9db2d1 !important;
}
.tahmin-kart .tk-key,
.diger-kart .tk-key,
.neden-kart .tk-key,
.diger-kart .diger-name,
.diger-kart .diger-sub,
.neden-kart .neden-item {
    color: #f8fbff !important;
}
.tahmin-kart [style*="color:#666"],
.diger-kart [style*="color:#666"],
.neden-kart [style*="color:#666"] {
    color: #9db2d1 !important;
}

/* Extra readability for historical-match section and dark boxes */
.dark-white-text,
.dark-white-text * {
    color: #f8fbff !important;
}

/* Historical table title readability */
.history-card {
    background:#13151e !important;
    border:1px solid #1e2130 !important;
    border-radius:16px !important;
    padding:16px 22px !important;
    margin-bottom:0 !important;
}
.history-title {
    color:#f8fbff !important;
    font-family:'Rajdhani',sans-serif !important;
    font-size:1.05rem !important;
    font-weight:800 !important;
    letter-spacing:1px !important;
    margin-bottom:6px !important;
    text-transform:uppercase !important;
}
.history-sub {
    color:#e5e7eb !important;
    font-size:0.82rem !important;
    line-height:1.45 !important;
}
.ai-comment {
    margin-top:10px;
    padding:10px 12px;
    background:#0b1628;
    border:1px solid #1f2a44;
    border-radius:10px;
}
.ai-comment-title {
    color:#8fb3ff;
    font-size:0.72rem;
    font-weight:800;
    letter-spacing:.5px;
    margin-bottom:5px;
}
.ai-comment-text {
    color:#f8fbff;
    font-size:0.80rem;
    line-height:1.45;
}
.coupon-actions {
    margin-top:10px;
    padding-top:10px;
    border-top:1px solid #223c63;
}

.ai-inline {
    margin-top:10px;
    padding:10px 12px;
    background:#0b1628;
    border:1px solid #1f2a44;
    border-radius:12px;
}
.ai-line {
    color:#f8fbff;
    font-size:0.78rem;
    line-height:1.45;
    margin:3px 0;
}
.ai-line b {
    color:#ffd24a !important;
}
.history-title {
    color:#f8fbff !important;
}
.history-sub {
    color:#f8fbff !important;
}


/* === DETAIL POPUP / MODAL === */
div[data-testid="stDialog"] div[role="dialog"] {
    width: min(1540px, 98vw) !important;
    max-width: 98vw !important;
    max-height: 92vh !important;
    overflow-y: auto !important;
    background: linear-gradient(180deg,#07111f 0%, #0a1830 100%) !important;
    border: 1px solid #284977 !important;
    border-radius: 22px !important;
    box-shadow: 0 28px 80px rgba(2,8,23,.65) !important;
    padding: 18px !important;
}
div[data-testid="stDialog"] div[role="dialog"] * {
    color: inherit;
}
div[data-testid="stDialog"] div[role="dialog"]::-webkit-scrollbar {
    width: 8px;
}
div[data-testid="stDialog"] div[role="dialog"]::-webkit-scrollbar-thumb {
    background: #ffd24a;
    border-radius: 99px;
}


/* Compact Top 10 market filters in sidebar */
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] {
    margin-bottom: -8px !important;
}
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    min-height: 24px !important;
}
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p {
    margin: 0 !important;
    line-height: 1.1 !important;
}
/* tighter 2x2 market filter grid */
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
    gap: 0.28rem !important;
}
section[data-testid="stSidebar"] div[data-testid="column"] {
    padding-left: 0 !important;
    padding-right: 0 !important;
}

</style>
""", unsafe_allow_html=True)

legal_notice_top()


def format_tr_date(d):
    aylar = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    gunler = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
        4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    return f"{d.day} {aylar[d.month]} {d.year} {gunler[d.weekday()]}"


def dinamik_min_mac(tolerans: float) -> int:
    if tolerans <= 0.02:
        return 1
    elif tolerans <= 0.05:
        return 3
    elif tolerans <= 0.08:
        return 5
    elif tolerans <= 0.12:
        return 10
    return 20


def sample_factor_hesapla(sample: int, tolerans: float) -> float:
    """Örnek cezası: 0.00 hassasiyet muaf; diğerlerinde yalnızca 1 örnek cezalı."""
    sample = int(sample or 0)
    tolerans = float(tolerans or 0.0)

    # 0.00 hassasiyet dar eşleşme olduğu için tek örnek olsa bile ceza uygulanmaz.
    if abs(tolerans) < 1e-9:
        return 1.0

    # 0.01+ hassasiyetlerde yalnızca tek örnekli sonuçları törpüle.
    if sample == 1:
        return 0.80

    # 2 veya daha fazla örnekte örnek sayısından kaynaklı ceza yok.
    return 1.0


def tolerans_rehberi(tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if tolerans <= 0.02:
        yorum = "Çok dar filtre. Az ama çok yakın oranlı örnekler gelir."
    elif tolerans <= 0.05:
        yorum = "Dar filtre. Örnek az olabilir ama eşleşme kalitesi yüksektir."
    elif tolerans <= 0.08:
        yorum = "Dengeli filtre. Hem kalite hem örnek sayısı dengeli."
    elif tolerans <= 0.12:
        yorum = "Biraz geniş filtre. Veri artar, benzerlik biraz düşer."
    else:
        yorum = "Geniş filtre. Sonuçlar daha genel davranabilir."
    return {
        "onerilen_tolerans": "0.08 - 0.10",
        "onerilen_min_mac": min_mac,
        "yorum": yorum,
    }


def guven_metni(sample: int, tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if sample >= max(20, min_mac * 3):
        return "Çok Sağlam", "#27ae60"
    if sample >= max(10, min_mac * 2):
        return "Sağlıklı", "#2ecc71"
    if sample >= min_mac:
        return "Kullanılabilir", "#f39c12"
    return "Riskli", "#e74c3c"


def guven_renk(pct: int):
    if pct >= 70:
        return "#27ae60", "badge-yuksek", "Yüksek Güven"
    if pct >= 55:
        return "#e67e22", "badge-orta", "Orta Güven"
    return "#e74c3c", "badge-dusuk", "Düşük Güven"


def risk_seviyesi(pct: int, flip_p: float):
    if pct >= 70 and flip_p < 0.15:
        return "DÜŞÜK", "risk-dusuk"
    if pct >= 55:
        return "ORTA", "risk-orta"
    return "YÜKSEK", "risk-yuksek"


def tahmini_skor(b: pd.DataFrame, ms_mod: str):
    eg = math.floor(b["FTHG"].mean() + 0.5) if not b.empty else 1
    dg = math.floor(b["FTAG"].mean() + 0.5) if not b.empty else 1
    if ms_mod == "H" and eg <= dg:
        eg = dg + 1
    if ms_mod == "A" and dg <= eg:
        dg = eg + 1
    return eg, dg


def mac_tipi(h: float, a: float):
    if abs(h - a) <= 0.50:
        return "Dengeli"
    if h < 2.0 or a < 2.0:
        return "Favori"
    return "Sürpriz Açık"


def gol_profili(avg_goal: float):
    if avg_goal < 2.2:
        return "Düşük Gollü"
    if avg_goal < 3.0:
        return "Dengeli"
    return "Yüksek Gollü"


def fake_confidence_duzelt(conf_prob, sample, tolerans):
    """Küçük örnekte monoton Beta(1,1) düzeltmesi; hiçbir güven artırılmaz.

    Bu bir geçmiş frekans düzeltmesidir, kalibre edilmiş kazanma garantisi değildir.
    Aynı işlem ana, alternatif ve bütün market alanlarında bir kez uygulanır.
    """
    n = max(0.0, float(sample or 0))
    raw = max(0.0, min(0.99, float(conf_prob or 0)))
    adjusted = min(raw, (raw * n + 1.0) / (n + 2.0)) if n else 0.0
    return adjusted, adjusted < raw - 1e-9


GEÇMİŞ_VERİ_DOSYASI = APP_DATA_DIR / "yapaikupon_gecmis_cache.csv"
FOOTBALL_DATA_META_DOSYASI = APP_DATA_DIR / "yapaikupon_football_data_meta.json"

def _football_data_meta_yaz(indirilen_dosya=0, hata_sayisi=0):
    """Son başarılı gerçek Football-Data ağ çekimini kalıcı olarak kaydeder."""
    try:
        payload = {
            "last_successful_fetch": kayit_zamani_iso(),
            "downloaded_files": int(indirilen_dosya or 0),
            "error_count": int(hata_sayisi or 0),
        }
        FOOTBALL_DATA_META_DOSYASI.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError):
        pass

def football_data_son_cekim_bilgisi():
    """Sidebar için son gerçek çekim zamanı; eski kurulumda cache mtime'a geri düşer."""
    try:
        if FOOTBALL_DATA_META_DOSYASI.exists():
            payload = json.loads(FOOTBALL_DATA_META_DOSYASI.read_text(encoding="utf-8"))
            raw = payload.get("last_successful_fetch")
            if raw:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(TR_TIMEZONE)
                return dt.strftime("%d.%m.%Y %H:%M"), "Football-Data"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass

    try:
        if GEÇMİŞ_VERİ_DOSYASI.exists():
            dt = datetime.fromtimestamp(
                GEÇMİŞ_VERİ_DOSYASI.stat().st_mtime,
                tz=timezone.utc,
            ).astimezone(TR_TIMEZONE)
            return dt.strftime("%d.%m.%Y %H:%M"), "cache dosyası"
    except OSError:
        pass
    return "Henüz yok", "—"

def _gecmis_cache_yukle():
    """Uygulamanın yanındaki kalıcı geçmiş CSV'sini ana veri kaynağı olarak yükler."""
    try:
        if GEÇMİŞ_VERİ_DOSYASI.exists() and GEÇMİŞ_VERİ_DOSYASI.stat().st_size > 0:
            df = pd.read_csv(GEÇMİŞ_VERİ_DOSYASI)

            if "Date" in df.columns:
                df["Date"] = tarih_serisi_oku(df["Date"])

            # Extra/worldwide ligler bültende kalır; geçmiş model ve detay havuzundan çıkar.
            df = sadece_tam_verili_gecmis(df)

            # Football-Data extra/worldwide dosyaları season_code='2021+' olarak
            # kaydedilmişti. Backtest ve sezon filtrelerinin çalışması için tarihi
            # futbol sezonuna (Temmuz-Haziran) dönüştür.
            if "season_code" not in df.columns:
                df["season_code"] = ""
            if "Date" in df.columns:
                def _model_sezon_kodu(row):
                    mevcut = str(row.get("season_code", "") or "").strip()
                    if mevcut and mevcut not in {"2021+", "nan", "None"}:
                        return mevcut
                    dt = row.get("Date")
                    if pd.isna(dt):
                        return mevcut
                    y = int(dt.year)
                    bas = y if int(dt.month) >= 7 else y - 1
                    return f"{str(bas)[-2:]}{str(bas + 1)[-2:]}"
                df["season_code"] = df.apply(_model_sezon_kodu, axis=1)

            # CSV'den gelen sayısal alanları model için kesin numeric yap.
            for c in [
                "FTHG", "FTAG", "HTHG", "HTAG",
                "B365H", "B365D", "B365A",
                "B365CH", "B365CD", "B365CA",
                "REF_H", "REF_D", "REF_A",
            ]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            return df
    except Exception:
        pass
    return pd.DataFrame()

def _gecmis_cache_kaydet(df):
    if df is None or df.empty:
        return False
    tmp = None
    try:
        GEÇMİŞ_VERİ_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
        kayit = df.copy()
        if "Date" in kayit.columns:
            kayit["Date"] = tarih_serisi_oku(kayit["Date"]).dt.strftime("%Y-%m-%d")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".csv", prefix="history-", dir=GEÇMİŞ_VERİ_DOSYASI.parent, delete=False) as stream:
            tmp = Path(stream.name)
            kayit.to_csv(stream, index=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, GEÇMİŞ_VERİ_DOSYASI)
        return True
    except (OSError, ValueError) as error:
        kayit_hatasi("Geçmiş veri dosyası kaydedilemedi", error)
        return False
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

@st.cache_data(ttl=3600)
def futbol_veri_motoru(sezonlar, zorla_yenile=False):
    """Geçmiş maç verisini yerel cache + Football-Data ile güncel tutar."""
    if not sezonlar:
        return pd.DataFrame()

    secili_sezonlar = {str(x) for x in sezonlar}
    yerel_tum = _gecmis_cache_yukle()
    yerel = yerel_tum.copy()
    if not yerel.empty and "season_code" in yerel.columns:
        yerel = yerel[yerel["season_code"].astype(str).isin(secili_sezonlar)].copy()

    mevcut_sezonlar = set(yerel["season_code"].astype(str)) if not yerel.empty and "season_code" in yerel else set()
    today = tr_simdi()
    start_year = today.year if today.month >= 7 else today.year - 1
    current_season = f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"
    expired = not GEÇMİŞ_VERİ_DOSYASI.exists() or time.time() - GEÇMİŞ_VERİ_DOSYASI.stat().st_mtime >= 6 * 3600
    indirilecek = set(secili_sezonlar) if zorla_yenile else secili_sezonlar - mevcut_sezonlar
    if expired and current_season in secili_sezonlar:
        indirilecek.add(current_season)
    # Normal kullanımda hızlı yerel cache; backtestte zorla_yenile=True ile canlı güncelleme.
    if not indirilecek and not yerel.empty:
        try:
            yerel.attrs["kaynak"] = "yerel GitHub cache"
            yerel.attrs["kaynak_hata_sayisi"] = 0
            yerel.attrs["kaynak_hatalari"] = []
            yerel.attrs["cache_dosyasi"] = str(GEÇMİŞ_VERİ_DOSYASI.name)
        except Exception:
            pass
        return yerel.reset_index(drop=True)

    lig_map = [
        "T1", "E0", "E1", "E2", "E3", "SP1", "SP2", "D1", "D2",
        "I1", "I2", "F1", "F2", "N1", "B1", "P1", "SC0", "G1",
    ]
    liste, hatalar = [], []

    for k in lig_map:
        for sezon in sorted(indirilecek):
            url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{k}.csv"
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 YapAiKupon/1.0"})
                if r.status_code != 200 or not r.content:
                    hatalar.append(f"{k}-{sezon}: HTTP {r.status_code}")
                    continue
                ct = str(r.headers.get("content-type", "")).lower()
                ilk = r.content[:300].lower()
                if b"<html" in ilk or b"temporarily unavailable" in ilk or "text/html" in ct:
                    hatalar.append(f"{k}-{sezon}: geçici HTML/servis hatası")
                    continue

                df = pd.read_csv(io.BytesIO(r.content))
                cols = [
                    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "FTR", "HTR",
                    "B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA", "B365>2.5", "B365<2.5", "B365C>2.5", "B365C<2.5", "HC", "AC", "HY", "AY"
                ]
                # Şirket kimliğini koru; eski B365 dosyaları da desteklenir.
                cols += [f'{prefix}{closing}{side}' for prefix in ("WH", "PS", "BW", "VC")
                         for closing in ("", "C") for side in "HDA"]
                cols += [f'{prefix}{closing}{side}2.5' for prefix in ("P", "WH", "BW", "VC")
                         for closing in ("", "C") for side in (">", "<")]
                df = df[df.columns.intersection(cols)].copy()
                for c in ["B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA"]:
                    if c not in df.columns:
                        df[c] = pd.NA
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                df["REF_H"] = df["B365CH"].combine_first(df["B365H"])
                df["REF_D"] = df["B365CD"].combine_first(df["B365D"])
                df["REF_A"] = df["B365CA"].combine_first(df["B365A"])

                usable = pd.Series(False, index=df.index)
                for prefix in ("B365", "WH", "PS", "BW", "VC"):
                    for closing in ("", "C"):
                        triple = [f"{prefix}{closing}{side}" for side in "HDA"]
                        if all(column in df for column in triple):
                            numbers = df[triple].apply(pd.to_numeric, errors="coerce")
                            usable |= (numbers.gt(1) & numbers.lt(float("inf"))).all(axis=1)
                temp = df.loc[usable].copy()
                temp["Date"] = tarih_serisi_oku(temp["Date"])
                temp = temp.dropna(subset=["Date"])
                temp["league_code"] = k
                temp["season_code"] = str(sezon)
                if not temp.empty:
                    liste.append(temp)
                else:
                    hatalar.append(f"{k}-{sezon}: kullanılabilir oran satırı yok")
            except Exception as exc:
                hatalar.append(f"{k}-{sezon}: {type(exc).__name__}: {exc}")

    if liste:
        canli = pd.concat(liste, ignore_index=True)
        sonuc_tum = pd.concat([yerel_tum, canli], ignore_index=True, sort=False) if not yerel_tum.empty else canli.copy()
        sonuc_tum["Date"] = pd.to_datetime(sonuc_tum["Date"], errors="coerce")
        anahtar = ["Date", "league_code", "HomeTeam", "AwayTeam"]
        if all(c in sonuc_tum.columns for c in anahtar):
            sonuc_tum = sonuc_tum.sort_values("Date", kind="stable").drop_duplicates(subset=anahtar, keep="last")
        _gecmis_cache_kaydet(sonuc_tum)
        _football_data_meta_yaz(indirilen_dosya=len(liste), hata_sayisi=len(hatalar))

        sonuc = sonuc_tum.copy()
        if "season_code" in sonuc.columns:
            sonuc = sonuc[sonuc["season_code"].astype(str).isin(secili_sezonlar)].copy()
        try:
            sonuc.attrs["kaynak"] = "Football-Data güncel + yerel cache birleştirildi"
            sonuc.attrs["kaynak_hata_sayisi"] = len(hatalar)
            sonuc.attrs["kaynak_hatalari"] = hatalar[:12]
            sonuc.attrs["cache_dosyasi"] = str(GEÇMİŞ_VERİ_DOSYASI.name)
        except Exception:
            pass
        return sonuc.reset_index(drop=True)

    # Canlı yenileme başarısız olursa eski cache ile çalışmaya devam et.
    if not yerel.empty:
        try:
            yerel.attrs["kaynak"] = "yerel cache (canlı yenileme başarısız)"
            yerel.attrs["kaynak_hata_sayisi"] = len(hatalar)
            yerel.attrs["kaynak_hatalari"] = hatalar[:12]
        except Exception:
            pass
        return yerel.reset_index(drop=True)

    sonuc = pd.DataFrame()
    try:
        sonuc.attrs["kaynak"] = "veri yok"
        sonuc.attrs["kaynak_hata_sayisi"] = len(hatalar)
        sonuc.attrs["kaynak_hatalari"] = hatalar[:12]
    except Exception:
        pass
    return sonuc


def odds_spor_katalogu(key):
    try:
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/",
            params={"apiKey": key, "all": "true"}, timeout=12,
        )
        return r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
    except Exception:
        return []


def odds_lig_kodu_coz(key, kod):
    if kod != "auto_turkey_1_lig":
        return kod
    for item in odds_spor_katalogu(key):
        metin = f"{item.get('group','')} {item.get('title','')} {item.get('description','')}".lower()
        if "soccer" in metin and "turk" in metin and ("1. lig" in metin or "1 lig" in metin or "tff 1" in metin):
            return item.get("key")
    return None




def bulten_cek(key, kodlar, t):
    st.session_state["odds_api_last_error"] = None
    secret_key = get_app_api_key()
    if secret_key:
        key = secret_key
    if not key:
        st.session_state["odds_api_last_error"] = "ODDS API anahtarı gerekli."
        st.error("Maç bültenini çekmek için ODDS API key gerekli.")
        return pd.DataFrame()
    res = []

    for secili_kod in kodlar:
        k = odds_lig_kodu_coz(key, secili_kod)
        if not k:
            st.session_state["odds_api_last_error"] = f"Lig kodu çözülemedi: {secili_kod}"
            continue
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{k}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h,totals",
                    "oddsFormat": "decimal",
                },
                timeout=12,
            )

            # The Odds API kota bilgilerini son başarılı/başarısız yanıttan sakla.
            # Böylece kullanıcı kalan krediyi arayüzden görebilir.
            try:
                st.session_state["odds_api_quota"] = {
                    "remaining": r.headers.get("x-requests-remaining"),
                    "used": r.headers.get("x-requests-used"),
                    "last": r.headers.get("x-requests-last"),
                    "updated_at": time.time(),
                }
            except Exception:
                pass

            if r.status_code != 200:
                try:
                    hata_metni = r.text[:300]
                except Exception:
                    hata_metni = ""
                st.session_state["odds_api_last_error"] = f"{k}: HTTP {r.status_code} {hata_metni}".strip()
                continue

            data = r.json()
            if not isinstance(data, list):
                st.session_state["odds_api_last_error"] = f"{k}: Geçersiz bülten yanıtı"
                continue

            for m in data:
                try:
                    tm = parse_mac_datetime(m["commence_time"])
                except Exception:
                    continue

                if tm is None or tm.date() != t:
                    continue

                bookies = m.get("bookmakers", [])
                if not bookies:
                    continue

                home = m.get("home_team", "")
                away = m.get("away_team", "")
                if not away:
                    teams = m.get("teams", [])
                    for team in teams:
                        if team != home:
                            away = team
                            break

                match_key = str(m.get("id") or "|".join([
                    str(k), str(home), str(away), str(m.get("commence_time", ""))
                ]))

                # Her sorguda o andaki son oranı al. Karşılaştırılabilirlik için
                # Bet365 varsa onu, yoksa anahtara göre ilk bookmaker'ı kullan.
                def bk_priority(bk):
                    bk_key = str(bk.get("key", ""))
                    preferred = ("williamhill", "pinnacle", "bwin", "betvictor", "bet365")
                    return (preferred.index(bk_key) if bk_key in preferred else len(preferred), bk_key)

                market = None
                totals_market = None
                btts_market = None
                secilen_bk_key = ""
                odds_updated_at = None
                totals_updated_at = None
                totals_bk_key = ""
                btts_updated_at = None
                btts_bk_key = ""
                sirali_bk = sorted(bookies, key=bk_priority)

                # 1X2 için tercih edilen bookmaker'ı seç.
                for bk in sirali_bk:
                    markets_by_key = {str(mk.get("key", "")): mk for mk in bk.get("markets", [])}
                    h2h_mk = markets_by_key.get("h2h")
                    if h2h_mk is None:
                        continue
                    prices = {str(outcome.get("name", "")): outcome.get("price")
                              for outcome in h2h_mk.get("outcomes", [])}
                    draw = next((value for name, value in prices.items() if name.lower() in ("draw", "tie", "beraberlik")), None)
                    try:
                        if not all(math.isfinite(float(value)) and float(value) > 1
                                   for value in (prices.get(home), draw, prices.get(away))):
                            continue
                    except (TypeError, ValueError):
                        continue
                    market = h2h_mk
                    odds_updated_at = h2h_mk.get("last_update") or bk.get("last_update")
                    secilen_bk_key = str(bk.get("key", ""))
                    break

                if not market:
                    continue

                # 2.5 Alt/Üst bağımsız aranır. H2H aldığımız bookmaker totals
                # sunmuyorsa diğer bookmaker'larda gerçek 2.5 çizgisini ara.
                for bk in sorted(sirali_bk, key=lambda book: (book.get("key") != secilen_bk_key, bk_priority(book))):
                    markets_by_key = {str(mk.get("key", "")): mk for mk in bk.get("markets", [])}
                    tmkt = markets_by_key.get("totals")
                    if not tmkt:
                        continue
                    sides_25 = set()
                    for ox in tmkt.get("outcomes", []) or []:
                        try:
                            price = float(ox.get("price"))
                            if abs(float(ox.get("point")) - 2.5) <= 1e-9 and math.isfinite(price) and price > 1:
                                sides_25.add(str(ox.get("name", "")).lower())
                        except (TypeError, ValueError):
                            continue
                    if {"over", "under"}.issubset(sides_25):
                        totals_market = tmkt
                        totals_updated_at = tmkt.get("last_update") or bk.get("last_update")
                        totals_bk_key = str(bk.get("key", ""))
                        break

                # KG Var/Yok (BTTS) ek markettir ve The Odds API'de event bazlı
                # endpointten alınır. Yalnızca bugünkü, kartta kullanılacak maç için
                # tek ek market çağrısı yapılır; lig bülteni zaten 6 saat cache'lidir.
                # Önce 1X2 bookmaker'ını, yoksa diğer EU bookmaker'ları tercih et.
                try:
                    event_id = str(m.get("id", "") or "").strip()
                    if event_id:
                        rb = requests.get(
                            f"https://api.the-odds-api.com/v4/sports/{k}/events/{event_id}/odds",
                            params={
                                "apiKey": key,
                                "regions": "eu",
                                "markets": "btts",
                                "oddsFormat": "decimal",
                            },
                            timeout=12,
                        )
                        try:
                            st.session_state["odds_api_quota"] = {
                                "remaining": rb.headers.get("x-requests-remaining"),
                                "used": rb.headers.get("x-requests-used"),
                                "last": rb.headers.get("x-requests-last"),
                                "updated_at": time.time(),
                            }
                        except Exception:
                            pass
                        if rb.status_code == 200:
                            event_data = rb.json()
                            event_bookies = event_data.get("bookmakers", []) if isinstance(event_data, dict) else []
                            event_bookies = sorted(
                                event_bookies,
                                key=lambda book: (str(book.get("key", "")) != secilen_bk_key, bk_priority(book)),
                            )
                            for ebk in event_bookies:
                                ebmk = {str(mk.get("key", "")): mk for mk in ebk.get("markets", [])}.get("btts")
                                if not ebmk:
                                    continue
                                names = {}
                                for ox in ebmk.get("outcomes", []) or []:
                                    try:
                                        px = float(ox.get("price"))
                                    except (TypeError, ValueError):
                                        continue
                                    if not math.isfinite(px) or px <= 1:
                                        continue
                                    names[str(ox.get("name", "")).strip().lower()] = px
                                if "yes" in names and "no" in names:
                                    btts_market = ebmk
                                    btts_updated_at = ebmk.get("last_update") or ebk.get("last_update")
                                    btts_bk_key = str(ebk.get("key", ""))
                                    break
                        elif rb.status_code not in (404, 422):
                            # BTTS kapsamı olmayan maçlarda ana bülteni bozma; sadece
                            # gerçek BTTS oranı None kalır.
                            LOGGER.debug("BTTS odds alınamadı %s: HTTP %s", event_id, rb.status_code)
                except Exception as btts_exc:
                    LOGGER.debug("BTTS odds çağrısı başarısız: %s", type(btts_exc).__name__)

                outcomes = market.get("outcomes", [])
                h = next((x["price"] for x in outcomes if x["name"] == home), None)
                a = next((x["price"] for x in outcomes if x["name"] == away), None)
                b = next((x["price"] for x in outcomes if str(x["name"]).lower() in ["draw", "tie", "beraberlik"]), None)

                if h is None or a is None or b is None:
                    continue

                # The Odds API'nin featured totals marketi mevcutsa gerçek 2.5
                # Alt/Üst fiyatlarını da sakla. Bulunmayan lig/bookmaker için None kalır.
                o25_over = None
                o25_under = None
                if totals_market:
                    for x in totals_market.get("outcomes", []) or []:
                        try:
                            point = float(x.get("point"))
                            price = float(x.get("price"))
                        except Exception:
                            continue
                        if abs(point - 2.5) > 1e-9:
                            continue
                        name = str(x.get("name", "")).strip().lower()
                        if name == "over":
                            o25_over = price
                        elif name == "under":
                            o25_under = price

                btts_yes = None
                btts_no = None
                if btts_market:
                    for x in btts_market.get("outcomes", []) or []:
                        try:
                            price = float(x.get("price"))
                        except Exception:
                            continue
                        name = str(x.get("name", "")).strip().lower()
                        if name == "yes":
                            btts_yes = price
                        elif name == "no":
                            btts_no = price

                res.append({
                    "match_id": m.get("id", ""),
                    "match_key": match_key,
                    "sport_key": k,
                    "lig": m.get("sport_title", k),
                    "zaman": tm,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "b": float(b),
                    "a": float(a),
                    "bookmaker_key": secilen_bk_key,
                    "odds_updated_at": odds_updated_at,
                    "odds_fetched_at": kayit_zamani_iso(),
                    "totals_updated_at": totals_updated_at,
                    "totals_bookmaker_key": totals_bk_key,
                    "o25_over": o25_over,
                    "o25_under": o25_under,
                    "btts_updated_at": btts_updated_at,
                    "btts_bookmaker_key": btts_bk_key,
                    "btts_yes": btts_yes,
                    "btts_no": btts_no,
                })
        except Exception as exc:
            st.session_state["odds_api_last_error"] = f"{k}: {type(exc).__name__}: {exc}"
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    df = df.sort_values("zaman").reset_index(drop=True)
    return df



ODDS_BULTEN_CACHE_TTL = 6 * 60 * 60  # 6 saat; filtre değişiklikleri API kredisi tüketmesin


def odds_cache_key(kod, tarih, api_key=None):
    key = get_app_api_key() if api_key is None else api_key
    account = hashlib.sha256(str(key or "").encode()).hexdigest()[:16]
    return f"v3|{account}|{kod}|{tarih.isoformat()}"


def bulten_guncel_al(key, kodlar, t, zorla_yenile=False):
    """Yalnızca başarılı yanıtlar 6 saat saklanır; hatada son başarılı veri korunur."""
    key = get_app_api_key() or key
    cache = st.session_state.setdefault("odds_league_cache", {})
    now = time.time()
    parts, errors = [], []
    stale = False
    for code in dict.fromkeys(kodlar or []):
        ck = odds_cache_key(code, t, key)
        entry = cache.get(ck) or {}
        previous = entry.get("df")
        has_success = bool(entry.get("success")) and isinstance(previous, pd.DataFrame)
        fresh = has_success and now - float(entry.get("ts", 0)) < ODDS_BULTEN_CACHE_TTL
        waiting = now < float(entry.get("retry_after", 0))
        if not zorla_yenile and (fresh or waiting):
            if has_success:
                parts.append(previous.copy())
            if entry.get("error"):
                errors.append(entry["error"])
                stale |= has_success
            continue
        frame = bulten_cek(key, [code], t)
        error = st.session_state.get("odds_api_last_error")
        if error:
            errors.append(str(error))
            cache[ck] = dict(entry, error=str(error), retry_after=now + 60, last_attempt=now)
            if has_success:
                parts.append(previous.copy())
                stale = True
            continue
        frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        cache[ck] = {"ts": now, "df": frame.copy(), "success": True, "last_attempt": now}
        parts.append(frame)
    for ck, entry in list(cache.items()):
        if now - float(entry.get("last_attempt", entry.get("ts", 0))) > ODDS_BULTEN_CACHE_TTL * 4:
            cache.pop(ck, None)
    st.session_state["odds_api_last_error"] = " · ".join(dict.fromkeys(errors)) or None
    nonempty = [frame for frame in parts if not frame.empty]
    result = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()
    if not result.empty:
        result = result.drop_duplicates(subset=["ev", "dep", "zaman"]).sort_values("zaman").reset_index(drop=True)
    result.attrs.update(stale=stale, errors=errors)
    return result


def bulten_saglam_al(key, kodlar, t, zorla_yenile=False):
    """Aynı lig+tarih bültenini cache'ten kullanır; otomatik ikinci API çağrısı yapmaz."""
    # API hatasında otomatik zorla-yenile kaldırıldı. Kullanıcı isterse yalnızca
    # 'Oranları Yenile' butonuyla yeni çağrı yapar. Bu, checkbox/filtre değişimlerinde
    # gereksiz çift kredi tüketimini engeller.
    df = bulten_guncel_al(key, kodlar, t, zorla_yenile=zorla_yenile)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def odds_cache_bilgi(kodlar, t):
    cache = st.session_state.get("odds_league_cache", {})
    now = time.time()
    codes = list(dict.fromkeys(kodlar or []))
    valid = sum(bool((entry := cache.get(odds_cache_key(code, t), {})).get("success"))
                and not entry.get("error")
                and now - float(entry.get("ts", 0)) < ODDS_BULTEN_CACHE_TTL for code in codes)
    return int(valid), len(codes)





def fmt_odd(odd):
    if odd is None:
        return ""
    try:
        return f"{float(odd):.2f}"
    except Exception:
        return ""




def skor_etikete_uyuyor_mu(label, eg, dg):
    """Bir skorun tahmin etiketiyle çelişip çelişmediğini kontrol eder."""
    label = str(label or "").strip()
    if not label:
        return True
    if "+" in label:
        return all(skor_etikete_uyuyor_mu(parca.strip(), eg, dg) for parca in label.split("+"))

    toplam = int(eg) + int(dg)
    if label in {"MS 1", "MS1"}:
        return eg > dg
    if label in {"MS 2", "MS2"}:
        return dg > eg
    if label in {"Beraberlik", "MS X", "MSX"}:
        return eg == dg
    if label == "2.5 Alt":
        return toplam <= 2
    if label == "2.5 Üst":
        return toplam >= 3
    if label == "KG Var":
        return eg > 0 and dg > 0
    if label == "KG Yok":
        return eg == 0 or dg == 0
    return True


def skoru_tahmine_uydur(eg, dg, ana_label, ms_mod, alt_label="", combo_label=""):
    """Tahmini skoru ana tahmin ve güçlü kombo ile uyumlu seçer.

    Öncelik sırası: ana + güçlü kombo + alternatif -> ana + güçlü kombo
    -> ana + alternatif -> yalnızca ana. Böylece örneğin MS1 + KG Yok
    güçlü kombosunda 2-1 gibi komboyla çelişen bir skor gösterilmez.
    """
    baz_eg, baz_dg = int(eg), int(dg)
    ana = str(ana_label or "").strip()
    alt = str(alt_label or "").strip()
    combo = str(combo_label or "").strip()
    ms_mod = str(ms_mod or "")

    def ms_cezasi(h, a):
        if ms_mod == "H":
            return 0 if h > a else 2
        if ms_mod == "A":
            return 0 if a > h else 2
        if ms_mod == "D":
            return 0 if h == a else 1
        return 0

    # Güçlü kombo ekranda gösteriliyorsa skor önce onunla da uyuşmalı.
    # Alternatif tahmin kombo ile çelişirse alternatif bırakılır; ana ve
    # güçlü kombo korunur.
    denemeler = []
    if combo:
        denemeler.extend(([ana, combo, alt], [ana, combo]))
    denemeler.extend(([ana, alt], [ana]))

    for etiketler in denemeler:
        aktif = []
        for x in etiketler:
            if x and x not in aktif:
                aktif.append(x)
        adaylar = []
        for h in range(0, 6):
            for a in range(0, 6):
                if all(skor_etikete_uyuyor_mu(lbl, h, a) for lbl in aktif):
                    mesafe = abs(h - baz_eg) + abs(a - baz_dg)
                    toplam_fark = abs((h + a) - (baz_eg + baz_dg))
                    adaylar.append((mesafe, ms_cezasi(h, a), toplam_fark, h + a, h, a))
        if adaylar:
            adaylar.sort()
            return adaylar[0][-2], adaylar[0][-1]

    return baz_eg, baz_dg


def ai_kart_yorumlari(t, m):
    ana = t.get("ana_label", "")
    guven = int(t.get("ana_p", 0))
    puan = float(t.get("playable_score", guven))
    canli = t.get("canli_label", "İlk 15 dk izle")

    if t.get("belirsiz"):
        yorum = "Model bu maçta net bir yön bulamıyor; ana tahmin tek başına güçlü değil."
        risk = "Risk yüksek; maç başı tempo ve ilk 10-15 dakika izlenmeli."
        canlı = "İlk baskı ve şut hacmi oluşmadan giriş yapmak yerine beklemek daha iyi."
        return yorum, risk, canlı

    if ana in ["MS 1", "MS 2", "Beraberlik"]:
        taraf = "ev sahibi" if ana == "MS 1" else "deplasman" if ana == "MS 2" else "beraberlik"
        yorum = f"{taraf.capitalize()} tarafı oran benzerliğinde öne çıkıyor; ana senaryo {ana}."
    elif "Üst" in ana or "Alt" in ana:
        yorum = f"Gol marketinde {ana} senaryosu öne çıkıyor; skor beklentisi bu yöne göre dengelendi."
    elif "KG" in ana:
        yorum = f"Karşılıklı gol tarafında {ana} modeli daha güçlü görünüyor."
    else:
        yorum = f"Model ana senaryoda {ana} tarafını öne çıkarıyor."

    if guven >= 70 and puan >= 70:
        risk = "Güven ve puan iyi; yine de tek maç riski tamamen kaybolmaz."
    elif guven >= 60:
        risk = "Güven orta-iyi seviyede; beraberlik/tempo riski tamamen dışarıda değil."
    else:
        risk = "Güven sınırlı; kuponda düşük ağırlıkla değerlendirmek daha mantıklı."

    if "Canlı" in canli or "İzle" in canli:
        canlı = "İlk 15 dakikada baskı ve tempo oluşursa ana senaryo daha değerli olur."
    else:
        canlı = f"Canlı plan: {canli}. İlk 15 dakikadaki tempo mutlaka kontrol edilmeli."

    return yorum, risk, canlı


def pct100(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:
        return 0


def ai_yorum_uret(t):
    ana = t.get("ana_label", "")
    guven = int(t.get("ana_p", 0))
    puan = float(t.get("playable_score", guven))
    ornek = int(t.get("ornek", 0))
    mac_tipi_txt = t.get("match_type", "")
    gol_profili = t.get("goal_profile", "")
    combo = t.get("combo_label", "")
    canli = t.get("canli_label", "")

    if t.get("belirsiz"):
        return "Model bu maçta net taraf ayıramıyor. Ana tahmin yerine canlı başlangıç temposunu izlemek daha mantıklı."

    giris = f"Model ana senaryoda {ana} tarafını öne çıkarıyor."
    if guven >= 70 and puan >= 70:
        giris += " Güven ve puan birlikte güçlü olduğu için maç öncelikli izlenebilir."
    elif puan >= 65:
        giris += " Puan tarafı iyi, ancak güveni de maç temposuyla teyit etmek gerekir."
    elif guven >= 65:
        giris += " Güven iyi olsa da puan çok elit değil, kontrollü yaklaşmak daha doğru."
    else:
        giris += " Güven orta seviyede, agresif kupon için tek başına güçlü görünmüyor."

    detaylar = []
    if mac_tipi_txt:
        detaylar.append(f"maç tipi {mac_tipi_txt.lower()}")
    if gol_profili:
        detaylar.append(f"gol profili {gol_profili.lower()}")
    if combo:
        detaylar.append(f"kombo desteği: {combo}")
    if ornek < 8:
        detaylar.append("örnek sayısı düşük")
    elif ornek >= 20:
        detaylar.append("örnek sayısı sağlıklı")

    sonuc = giris
    if detaylar:
        sonuc += " " + " · ".join(detaylar).capitalize() + "."
    if canli:
        sonuc += f" Canlı plan: {canli}."
    return sonuc

def build_top3_coupon(indexed_items, mode="best_favorites"):
    candidates = []

    for idx, item in indexed_items:
        m, t = item["m"], item["t"]

        if t.get("belirsiz") or not t.get("oynanabilir"):
            continue

        ana_odd = t.get("ana_odd")
        if ana_odd is None:
            continue

        if t.get("match_type") != "Favori":
            continue

        candidates.append({
            "idx": idx,
            "m": m,
            "t": t,
            "ana_odd": ana_odd,
            "ana_label": t.get("ana_label", ""),
            "playable_score": t.get("playable_score", 0),
            "ana_p": t.get("ana_p", 0),
        })

    if mode == "best_favorites":
        # 🔥 GÜVEN ODAKLI
        candidates.sort(
            key=lambda c: (
                c["playable_score"],
                c["ana_p"],
                -c["ana_odd"]
            ),
            reverse=True
        )

        picks = []
        label_counts = {}

        for c in candidates:
            label = c["ana_label"]

            # aynı tahminden spam olmasın
            if label_counts.get(label, 0) >= 1:
                continue

            picks.append(c)
            label_counts[label] = 1

            if len(picks) == 3:
                break

        # 3'e tamamla
        if len(picks) < 3:
            used = {p["idx"] for p in picks}
            for c in candidates:
                if c["idx"] in used:
                    continue
                picks.append(c)
                if len(picks) == 3:
                    break

    else:
        # 🎯 ORAN ODAKLI
        candidates = [c for c in candidates if c["ana_odd"] >= 1.55]

        candidates.sort(
            key=lambda c: (
                c["ana_odd"],
                c["playable_score"],
                c["ana_p"]
            ),
            reverse=True
        )

        picks = candidates[:3]

    return [
        {
            "ev": c["m"]["ev"],
            "dep": c["m"]["dep"],
            "lig": c["m"]["lig"],
            "zaman_iso": c["m"]["zaman"].strftime("%Y-%m-%d %H:%M:%S"),
            "zaman_text": c["m"]["zaman"].strftime("%d.%m %H:%M"),
            "tahmin": f"{c['t']['ana_label']} ({fmt_odd(c['ana_odd'])})",
            "guven": int(c["t"].get("ana_p", 0)),
        }
        for c in picks
    ]


def gunun_kuponunu_olustur(final_list, profil="Dengeli", onceliksiz_secimler=None, haric_secimler=None, aday_listesi_modu=False):
    """Hassasiyet uzlaşması bulunan analizlerden kupon taslağı üretir."""
    ayarlar = {
        "Temkinli": {"min_guven": 66, "taban": 2, "maks": 3, "min_stabil": 1, "ek_stabil": 2, "min_oran": 1.0},
        "Dengeli": {"min_guven": 58, "taban": 3, "maks": 6, "min_stabil": 1, "ek_stabil": 2, "min_oran": 1.0},
        "Yüksek Oran": {"min_guven": 55, "taban": 2, "maks": 5, "min_stabil": 1, "ek_stabil": 2, "min_oran": 0.0},
    }
    cfg = ayarlar.get(profil, ayarlar["Dengeli"])
    simdi = tr_simdi()
    adaylar = []

    for item in final_list or []:
        m, t = item.get("m", {}), item.get("t", {})
        zaman = m.get("zaman")
        if not hasattr(zaman, "strftime") or zaman <= simdi:
            continue
        if t.get("belirsiz") or not t.get("oynanabilir", True):
            continue
        guven = int(t.get("ana_p", 0) or 0)
        ornek = int(t.get("ornek", 0) or 0)
        tolerans = hassasiyet_oku(t.get("kullanilan_tolerans"))
        stabil = int(t.get("stability_count", 0) or 0)
        dar_stabil = len(t.get("stability_early_tols", []) or [])
        oran = t.get("ana_odd")
        oran_sayi = float(oran) if oran is not None else None

        secim_label = str(t.get("ana_label", "-"))
        secim_guven = guven
        secim_oran = oran_sayi
        oran_tahmini = bool(t.get("top10_market_oran_tahmini", False))
        combo_label = str(t.get("combo_label", "") or "")
        combo_p = int(t.get("combo_p", 0) or 0)
        combo_hit = int(t.get("combo_hit", 0) or 0)
        combo_esigi = {"Temkinli": 65, "Dengeli": 52, "Yüksek Oran": 40}.get(profil, 52)
        combo_uygun = (
            bool(t.get("combo_var"))
            and combo_label
            and not combo_label.startswith("HT/FT")
            and combo_p >= combo_esigi
            and combo_hit >= max(5, dinamik_min_mac(tolerans))
        )
        if profil == "Temkinli":
            combo_uygun = combo_uygun and combo_p >= max(65, guven - 3)
        elif profil == "Dengeli":
            combo_uygun = combo_uygun and combo_p >= max(52, guven - 8)
        # Hassasiyet taramasında normal profillerde seçilen market korunur.
        # Ancak Yüksek Oran profili yalnızca kombo kabul ettiği için, mevcut güçlü
        # combo_label şartları sağlıyorsa hassasiyet taramalı kayıtta da komboya geç.
        combo_secildi = combo_uygun and (profil == "Yüksek Oran" or not t.get("hassasiyet_taramali"))
        if combo_secildi:
            secim_label = combo_label
            secim_guven = combo_p
            secim_oran = kombo_tahmini_oran(combo_label, oran_sayi)
            oran_tahmini = True

        kombinasyon_secimi = "+" in secim_label

        # Temkinli profil tekli marketler içindir. 2.5 Alt + KG Yok gibi
        # kombinasyonlar güveni yüksek olsa bile Temkinli aday/kuponuna girmesin.
        # Kombinasyonlar Dengeli'de kriterleri sağlarsa ve özellikle Yüksek Oran'da
        # değerlendirilmeye devam eder.
        if profil == "Temkinli" and kombinasyon_secimi:
            continue

        if guven < cfg["min_guven"]:
            continue
        if ornek < max(5, dinamik_min_mac(tolerans)):
            continue
        if stabil < cfg["min_stabil"]:
            continue
        if profil == "Yüksek Oran" and not kombinasyon_secimi:
            continue

        kalite = (
            float(t.get("playable_score", guven) or guven)
            + min(ornek, 40) * 0.20
            + stabil * 2.0
            + dar_stabil * 1.5
        )
        if profil == "Yüksek Oran" and secim_oran is not None:
            kalite += min(secim_oran, 5.0) * 3.0
        if combo_secildi:
            kalite += min(combo_hit, 20) * 0.20

        ekstra_uygun = stabil >= cfg["ek_stabil"]
        if profil == "Temkinli":
            ekstra_uygun = ekstra_uygun and guven >= 65 and (dar_stabil >= 1 or stabil >= 3)
        adaylar.append({
            "m": m, "t": t, "kalite": kalite, "oran": secim_oran,
            "secim_label": secim_label, "secim_guven": secim_guven,
            "oran_tahmini": oran_tahmini,
            "combo_secim": kombinasyon_secimi,
            "ekstra_uygun": ekstra_uygun,
            # Kartlarda hangi 0.00-0.10 hassasiyetlerinde aynı marketin
            # çıktığını kaybetmemek için ara adayda da sakla.
            "hassasiyetler": list(t.get("top10_hassasiyetler") or t.get("stability_tols") or []),
            "hassasiyet_sayisi": int(t.get("top10_hassasiyet_sayisi", t.get("stability_count", 0)) or 0),
        })

    if profil == "Temkinli":
        adaylar.sort(
            key=lambda x: (x["secim_guven"], x["t"].get("stability_count", 0), x["kalite"]),
            reverse=True,
        )
    elif profil == "Yüksek Oran":
        adaylar.sort(
            key=lambda x: (x["combo_secim"], x["oran"] or 0, x["kalite"]),
            reverse=True,
        )
    else:
        adaylar.sort(key=lambda x: (x["kalite"], x["secim_guven"]), reverse=True)

    # Profiller artık birbirinin seçimlerini geriye atmaz. Aynı güçlü seçim
    # Temkinli, Dengeli ve Yüksek Oran kriterlerini ayrı ayrı karşılıyorsa
    # birden fazla profilde yer alabilir.
    # haric_secimler yalnızca AYNI profil içinde ikinci/üçüncü kupon üretilirken
    # daha önce kullanılan maç+market seçimlerini tekrar kullanmamak içindir.
    haric_secimler = set(haric_secimler or [])
    secilenler, maclar = [], set()
    for aday in adaylar:
        m, t = aday["m"], aday["t"]
        mac_id = mac_key(m)
        secim_key = (mac_id, aday["secim_label"])
        lig = str(m.get("lig", ""))
        if secim_key in haric_secimler:
            continue
        if mac_id in maclar:
            continue
        # Profilin taban sayısından sonraki seçimler daha yüksek kararlılık ister.
        if len(secilenler) >= cfg["taban"] and not aday["ekstra_uygun"]:
            continue
        secilenler.append({
            "ev": m.get("ev", ""),
            "dep": m.get("dep", ""),
            "lig": lig,
            "zaman_iso": m["zaman"].strftime("%Y-%m-%d %H:%M:%S"),
            "zaman_text": m["zaman"].strftime("%d.%m %H:%M"),
            "tahmin": aday["secim_label"],
            "guven": int(aday["secim_guven"]),
            "oran": aday["oran"],
            "oran_tahmini": aday["oran_tahmini"],
            "hassasiyet": hassasiyet_oku(t.get("kullanilan_tolerans")),
            "hassasiyetler": list(aday.get("hassasiyetler") or t.get("top10_hassasiyetler") or t.get("stability_tols") or []),
            "hassasiyet_sayisi": int(aday.get("hassasiyet_sayisi") or len(aday.get("hassasiyetler") or []) or 0),
            "otomatik": True,
            "profil": profil,
            # Kupon geçmişinden maç detayını yeniden oluşturabilmek için
            # Son bültendeki temel maç/oran bilgilerini de sakla.
            **oran_kayit_bilgisi(m), "sport_key": m.get("sport_key", ""),
            "h": m.get("h"),
            "b": m.get("b"),
            "a": m.get("a"),
        })
        maclar.add(mac_id)
        if len(secilenler) >= cfg["maks"]:
            break

    # Kupon sayılabilmesi için en az iki bağımsız seçim gerekir.
    minimum_secim = 1 if (aday_listesi_modu or profil == "Yüksek Oran") else 2
    return secilenler if len(secilenler) >= minimum_secim else []



def gunun_kuponunu_profil_adaylarindan_olustur(gecmis_df, bulten_df, min_ornek=5, sadece_ayni_lig=False, maks=6):
    """Günün Kuponu sıkı filtresi boş kalırsa profil adaylarından tek kupon üretir.

    Temkinli, Dengeli ve Yüksek Oran aday havuzları ayrı ayrı oluşturulur.
    Aynı maçtan yalnızca en güçlü tek seçim alınır. Böylece profil adayları mevcutsa
    Günün Kuponu tamamen boş kalmaz.
    """
    profil_onceligi = {"Temkinli": 3, "Dengeli": 2, "Yüksek Oran": 1}
    tum_adaylar = []

    for profil_adi in ["Temkinli", "Dengeli", "Yüksek Oran"]:
        kaynak = gunun_en_iyi_10_uret(
            gecmis_df,
            bulten_df,
            min_ornek=min_ornek,
            limit=500,
            sadece_ayni_lig=sadece_ayni_lig,
            kupon_modu=True,
            kupon_profili=profil_adi,
            tum_marketler=True,
        )
        kullanilan = set()
        while True:
            parca = gunun_kuponunu_olustur(
                kaynak, profil_adi, haric_secimler=kullanilan, aday_listesi_modu=True
            )
            if not parca:
                break
            yeni = False
            for secim in parca:
                secim_key = (
                    f"{secim.get('ev','')}|{secim.get('dep','')}|{str(secim.get('zaman_iso',''))[:16]}",
                    secim.get("tahmin", ""),
                )
                if secim_key in kullanilan:
                    continue
                kullanilan.add(secim_key)
                aday = dict(secim)
                aday["kaynak_profil"] = profil_adi
                tum_adaylar.append(aday)
                yeni = True
            if not yeni:
                break

    # Güven ve 11 hassasiyetteki kararlılık ana sıralama ölçütü; profil yalnızca
    # yakın/eşit adaylarda daha temkinli olanı öne almak için eşitlik bozucudur.
    tum_adaylar.sort(
        key=lambda x: (
            int(x.get("guven", 0) or 0),
            int(x.get("hassasiyet_sayisi", 0) or 0),
            profil_onceligi.get(x.get("kaynak_profil"), 0),
            float(x.get("oran", 0) or 0),
        ),
        reverse=True,
    )

    secimler = []
    kullanilan_maclar = set()
    for aday in tum_adaylar:
        mac_id = (
            str(aday.get("ev", "")),
            str(aday.get("dep", "")),
            str(aday.get("zaman_iso", ""))[:16],
        )
        if mac_id in kullanilan_maclar:
            continue
        secim = dict(aday)
        secim.pop("kaynak_profil", None)
        secim["profil"] = "Günün Kuponu"
        secim["otomatik"] = True
        secim["profil_aday_fallback"] = True
        secimler.append(secim)
        kullanilan_maclar.add(mac_id)
        if len(secimler) >= int(maks):
            break

    return secimler


def gunun_kuponlarini_kaliteye_gore_bol(secimler, maks_kupon_mac=6, min_anlamli_dusus=4.0):
    """Sıralı Günün Kuponu seçimlerini kalite kırılımında ayrı kuponlara böler.

    Kalite = güven + 11 hassasiyet kararlılığı katkısı. Ardışık iki seçim arasında
    anlamlı bir düşüş varsa yeni kupon başlatılır. Ancak özellikle profil adaylarından
    gelen fallback seçimlerde, yeni kuponun ilk maçı minimum güven + kararlılık
    yeterliliğini geçmiyorsa sırf elde kaldığı için ayrı kupon oluşturulmaz.
    """
    if not secimler:
        return []

    def _kalite(x):
        # Sıkı Günün Kuponu seçimlerinde varsa daha zengin günün puanını kullan.
        if x.get("gunun_puani") is not None:
            try:
                return float(x.get("gunun_puani"))
            except Exception:
                pass
        guven = float(x.get("guven", 0) or 0)
        stabil = float(x.get("hassasiyet_sayisi", 0) or 0)
        return guven + stabil * 1.8

    def _yeni_kupon_baslangici_yeterli(x):
        # Sıkı Günün Kuponu filtresinden gelen seçimler zaten kendi kalite kapılarını geçti.
        if not x.get("profil_aday_fallback"):
            return True

        # Profil fallback adayları zaten Temkinli / Dengeli / Yüksek Oran
        # aday motorunun kendi uygunluk kapılarından geçmiştir. Burada ikinci kez
        # aşırı sert bir eşik uygulamak aday havuzu varken 0 kupon üretebiliyordu.
        # Yeni grubun başlangıcında yalnızca çok zayıf/boş kayıtları ele.
        guven = float(x.get("guven", 0) or 0)
        stabil = int(x.get("hassasiyet_sayisi", 0) or 0)
        return guven >= 40 and stabil >= 1

    sirali = sorted(
        [dict(x) for x in secimler if isinstance(x, dict)],
        key=lambda x: (_kalite(x), float(x.get("guven", 0) or 0), int(x.get("hassasiyet_sayisi", 0) or 0)),
        reverse=True,
    )
    if not sirali:
        return []

    # Profil aday havuzu boş değilse Günün Kuponu hiçbir zaman sırf bu ikinci
    # kalite kapısı yüzünden 0 kupona düşmesin. Önce uygun başlangıcı ara;
    # bulunamazsa havuzdaki en güçlü adayı tek başına başlangıç kabul et.
    ilk_index = next((i for i, x in enumerate(sirali) if _yeni_kupon_baslangici_yeterli(x)), None)
    if ilk_index is None:
        ilk_index = 0

    ilk = sirali[ilk_index]
    kuponlar = [[ilk]]
    onceki_kalite = _kalite(ilk)

    for secim in sirali[ilk_index + 1:]:
        kalite = _kalite(secim)
        mevcut = kuponlar[-1]
        anlamli_dusus = (onceki_kalite - kalite) >= float(min_anlamli_dusus)
        yeni_grup_gerekli = anlamli_dusus or len(mevcut) >= int(maks_kupon_mac)

        if yeni_grup_gerekli:
            # Yeni grubun ilk adayı yeterli değilse ayrı kupon oluşturma.
            # Mevcut güçlü kupona da geri ekleme; aday Günün Kuponu dışında kalır.
            if _yeni_kupon_baslangici_yeterli(secim):
                kuponlar.append([secim])
            else:
                continue
        else:
            mevcut.append(secim)

        onceki_kalite = kalite

    return [k for k in kuponlar if k]


def _secim_skorla_tuttu_mu(label, ev_gol, dep_gol, current_home_is_row_home=True):
    """Bir market etiketini skor üzerinde değerlendirir; H2H'de mevcut ev takımına göre yönü korur."""
    label = str(label or "").strip()
    if not label:
        return None
    if "+" in label:
        parcalar = [x.strip() for x in label.split("+") if x.strip()]
        sonuclar = [_secim_skorla_tuttu_mu(x, ev_gol, dep_gol, current_home_is_row_home) for x in parcalar]
        if any(x is None for x in sonuclar):
            return None
        return all(sonuclar)

    # ev_gol/dep_gol burada geçmiş satırın HomeTeam/AwayTeam skorlarıdır.
    cur_home_gf = ev_gol if current_home_is_row_home else dep_gol
    cur_home_ga = dep_gol if current_home_is_row_home else ev_gol
    toplam = int(ev_gol) + int(dep_gol)
    if label in {"MS 1", "MS1"}:
        return cur_home_gf > cur_home_ga
    if label in {"MS 2", "MS2"}:
        return cur_home_gf < cur_home_ga
    if label in {"Beraberlik", "MS X", "MSX"}:
        return cur_home_gf == cur_home_ga
    if label == "2.5 Üst":
        return toplam >= 3
    if label == "2.5 Alt":
        return toplam <= 2
    if label == "KG Var":
        return ev_gol > 0 and dep_gol > 0
    if label == "KG Yok":
        return ev_gol == 0 or dep_gol == 0
    return None


def _h2h_baglam_destegi(gecmis_df, m, label, limit=5):
    """Son H2H maçlarını küçük bir doğrulama katmanı olarak -4..+4 puana çevirir."""
    bos = {"puan": 0.0, "mac": 0, "tutan": 0, "oran": None, "sonuclar": []}
    if gecmis_df is None or getattr(gecmis_df, "empty", True):
        return bos
    kaynak = gecmis_df
    history_code = ODDS_TO_HISTORY.get(str(m.get("sport_key", "")))
    if history_code and "league_code" in kaynak.columns:
        dar = kaynak[kaynak["league_code"] == history_code]
        if not dar.empty:
            kaynak = dar
    h2h, _ = takimlar_arasi_maclar(kaynak, m.get("ev", ""), m.get("dep", ""), m.get("zaman"), limit=limit)
    if h2h is None or h2h.empty:
        return bos
    cur_home_norm = takim_adi_norm(m.get("ev", ""))
    tutan = toplam = 0
    sonuclar = []
    for _, r in h2h.iterrows():
        try:
            hg, ag = int(float(r.get("FTHG"))), int(float(r.get("FTAG")))
        except Exception:
            continue
        row_home_is_current_home = takim_adi_norm(r.get("HomeTeam", "")) == cur_home_norm
        tuttu = _secim_skorla_tuttu_mu(label, hg, ag, row_home_is_current_home)
        if tuttu is None:
            continue
        toplam += 1
        tutan += int(bool(tuttu))
        try:
            tarih_txt = pd.to_datetime(r.get("Date"), errors="coerce")
            tarih_txt = tarih_txt.strftime("%d.%m.%Y") if pd.notna(tarih_txt) else "-"
        except Exception:
            tarih_txt = "-"
        sonuclar.append({"tarih": tarih_txt, "ev": str(r.get("HomeTeam", "")), "dep": str(r.get("AwayTeam", "")), "skor": f"{hg}-{ag}", "tuttu": bool(tuttu)})
    if toplam < 3:
        return {**bos, "mac": toplam, "tutan": tutan, "sonuclar": sonuclar}
    oran = tutan / toplam
    # H2H yardımcı sinyal; modeli asla tek başına çevirmesin.
    puan = max(-4.0, min(4.0, (oran - 0.50) * 8.0))
    return {"puan": round(puan, 2), "mac": toplam, "tutan": tutan, "oran": oran, "sonuclar": sonuclar}


def _saha_form_ozeti(maclar, takim):
    """Önceden saha bazlı süzülmüş maçlardan basit form/market özeti üretir."""
    if maclar is None or maclar.empty:
        return {"mac": 0, "puan_orani": 0.5, "over25": 0.5, "btts": 0.5, "draw_rate": 0.33}
    hedef = takim_adi_norm(takim)
    pts = n = draws = overs = btts = 0
    for _, r in maclar.iterrows():
        try:
            hg, ag = int(float(r.get("FTHG"))), int(float(r.get("FTAG")))
        except Exception:
            continue
        row_home = takim_adi_norm(r.get("HomeTeam", "")) == hedef
        gf, ga = (hg, ag) if row_home else (ag, hg)
        n += 1
        pts += 3 if gf > ga else 1 if gf == ga else 0
        draws += int(gf == ga)
        overs += int(hg + ag >= 3)
        btts += int(hg > 0 and ag > 0)
    if not n:
        return {"mac": 0, "puan_orani": 0.5, "over25": 0.5, "btts": 0.5, "draw_rate": 0.33}
    return {"mac": n, "puan_orani": pts/(3*n), "over25": overs/n, "btts": btts/n, "draw_rate": draws/n}


def _saha_baglam_destegi(gecmis_df, m, label, limit=5):
    """Ev takımının iç saha + deplasman takımının dış saha formunu -2.5..+2.5 puanla değerlendirir."""
    if gecmis_df is None or getattr(gecmis_df, "empty", True):
        return {"puan": 0.0, "aktif": False}
    kaynak = gecmis_df
    history_code = ODDS_TO_HISTORY.get(str(m.get("sport_key", "")))
    if history_code and "league_code" in kaynak.columns:
        dar = kaynak[kaynak["league_code"] == history_code]
        if not dar.empty:
            kaynak = dar
    tarih = m.get("zaman")
    ev_all = takim_son_maclari(kaynak, takim_adi_eslestir(m.get("ev", ""), pd.unique(pd.concat([kaynak["HomeTeam"].astype(str), kaynak["AwayTeam"].astype(str)])).tolist()), tarih, limit=20)
    dep_all = takim_son_maclari(kaynak, takim_adi_eslestir(m.get("dep", ""), pd.unique(pd.concat([kaynak["HomeTeam"].astype(str), kaynak["AwayTeam"].astype(str)])).tolist()), tarih, limit=20)
    ev_saha = takim_maclarini_sahaya_gore_filtrele(ev_all, m.get("ev", ""), "Sadece iç saha").head(limit) if ev_all is not None else pd.DataFrame()
    dep_saha = takim_maclarini_sahaya_gore_filtrele(dep_all, m.get("dep", ""), "Sadece deplasman").head(limit) if dep_all is not None else pd.DataFrame()
    ev = _saha_form_ozeti(ev_saha, m.get("ev", ""))
    dep = _saha_form_ozeti(dep_saha, m.get("dep", ""))
    if ev["mac"] < 3 or dep["mac"] < 3:
        return {"puan": 0.0, "aktif": False, "ev_mac": ev["mac"], "dep_mac": dep["mac"], "ev": ev, "dep": dep}

    label = str(label or "")
    if label in {"MS 1", "MS1"}:
        signal = ev["puan_orani"] - dep["puan_orani"]
    elif label in {"MS 2", "MS2"}:
        signal = dep["puan_orani"] - ev["puan_orani"]
    elif label in {"Beraberlik", "MS X", "MSX"}:
        signal = (((ev["draw_rate"] + dep["draw_rate"])/2) - 0.33) * 2.2 - abs(ev["puan_orani"]-dep["puan_orani"])*0.5
    elif "2.5 Üst" in label:
        signal = (((ev["over25"] + dep["over25"])/2) - 0.5) * 2
    elif "2.5 Alt" in label:
        signal = (0.5 - ((ev["over25"] + dep["over25"])/2)) * 2
    elif "KG Var" in label:
        signal = (((ev["btts"] + dep["btts"])/2) - 0.5) * 2
    elif "KG Yok" in label:
        signal = (0.5 - ((ev["btts"] + dep["btts"])/2)) * 2
    else:
        signal = 0.0
    puan = max(-2.5, min(2.5, signal * 2.5))
    return {"puan": round(puan, 2), "aktif": True, "ev_mac": ev["mac"], "dep_mac": dep["mac"], "ev": ev, "dep": dep}



@st.cache_data(ttl=86400, show_spinner=False)
def _api_football_team_id_cached(api_key, takim_adi):
    """API-Football /teams search sonucundan en güvenli takım id'sini seçer."""
    if not api_key or not takim_adi:
        return None, "API-Football key/takım yok"
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/teams",
            headers={"x-apisports-key": api_key},
            params={"search": str(takim_adi)},
            timeout=12,
        )
        if r.status_code != 200:
            return None, f"teams HTTP {r.status_code}"
        data = r.json() or {}
        rows = data.get("response", []) or []
        if not rows:
            # Uzun kulüp adı sonuç vermediyse kanonik tokenlardan kısa arama yap.
            tokens = _takim_adi_ham_tokenlari(takim_adi)
            q = " ".join(tokens[-2:]) if tokens else str(takim_adi)
            if q and q.lower() != str(takim_adi).lower():
                r = requests.get(
                    "https://v3.football.api-sports.io/teams",
                    headers={"x-apisports-key": api_key}, params={"search": q}, timeout=12,
                )
                if r.status_code == 200:
                    rows = (r.json() or {}).get("response", []) or []
        if not rows:
            return None, "takım bulunamadı"
        hedef = takim_adi_norm(takim_adi)
        adaylar = []
        for row in rows:
            team = row.get("team", {}) or {}
            tid = team.get("id")
            name = str(team.get("name", "") or "")
            if not tid or not name:
                continue
            norm = takim_adi_norm(name)
            ratio = SequenceMatcher(None, hedef, norm).ratio() if hedef and norm else 0.0
            kisa, uzun = sorted((hedef, norm), key=len) if hedef and norm else ("", "")
            kapsama = len(kisa) / len(uzun) if kisa and kisa in uzun else 0.0
            adaylar.append((max(ratio, kapsama), int(tid), name))
        if not adaylar:
            return None, "takım id yok"
        adaylar.sort(reverse=True)
        score, tid, name = adaylar[0]
        if score < 0.62:
            return None, f"eşleşme zayıf: {name} ({score:.2f})"
        return tid, ""
    except Exception as e:
        return None, f"teams hata: {type(e).__name__}"


@st.cache_data(ttl=21600, show_spinner=False)
def _api_football_team_fixtures_cached(api_key, team_id, last=14):
    if not api_key or not team_id:
        return [], ""
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": api_key},
            params={"team": int(team_id), "last": int(last)},
            timeout=12,
        )
        if r.status_code != 200:
            return [], f"fixtures HTTP {r.status_code}"
        return (r.json() or {}).get("response", []) or [], ""
    except Exception as e:
        return [], f"fixtures hata: {type(e).__name__}"


@st.cache_data(ttl=21600, show_spinner=False)
def _api_football_h2h_cached(api_key, home_id, away_id, last=7):
    if not api_key or not home_id or not away_id:
        return [], ""
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures/headtohead",
            headers={"x-apisports-key": api_key},
            params={"h2h": f"{int(home_id)}-{int(away_id)}", "last": int(last)},
            timeout=12,
        )
        if r.status_code != 200:
            return [], f"h2h HTTP {r.status_code}"
        return (r.json() or {}).get("response", []) or [], ""
    except Exception as e:
        return [], f"h2h hata: {type(e).__name__}"


def _api_fixture_to_history_row(fx):
    try:
        fixture = fx.get("fixture", {}) or {}
        teams = fx.get("teams", {}) or {}
        goals = fx.get("goals", {}) or {}
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            return None
        home = str((teams.get("home", {}) or {}).get("name", "") or "")
        away = str((teams.get("away", {}) or {}).get("name", "") or "")
        dt = pd.to_datetime(fixture.get("date"), errors="coerce", utc=True)
        if pd.isna(dt) or not home or not away:
            return None
        try:
            dt = dt.tz_convert("Europe/Istanbul").tz_localize(None)
        except Exception:
            dt = dt.tz_localize(None) if getattr(dt, "tzinfo", None) else dt
        return {
            "Date": pd.Timestamp(dt), "HomeTeam": home, "AwayTeam": away,
            "FTHG": int(hg), "FTAG": int(ag), "league_code": "API_FOOTBALL",
            "context_source": "API-Football",
        }
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def _api_football_baglam_rows_cached(api_key, ev, dep, zaman_iso):
    """Bir maç için son form + saha formu + H2H'yi tamamlayacak satırları döndürür."""
    if not api_key:
        return [], {"aktif": False, "hata": "API-Football key yok"}
    ev_id, e1 = _api_football_team_id_cached(api_key, ev)
    dep_id, e2 = _api_football_team_id_cached(api_key, dep)
    if not ev_id or not dep_id:
        return [], {"aktif": False, "hata": "; ".join(x for x in [e1, e2] if x)}

    ev_fx, e3 = _api_football_team_fixtures_cached(api_key, ev_id, 16)
    dep_fx, e4 = _api_football_team_fixtures_cached(api_key, dep_id, 16)
    h2h_fx, e5 = _api_football_h2h_cached(api_key, ev_id, dep_id, 8)
    hedef_tarih = pd.to_datetime(zaman_iso, errors="coerce")
    rows, seen = [], set()
    for fx in list(ev_fx) + list(dep_fx) + list(h2h_fx):
        row = _api_fixture_to_history_row(fx)
        if not row:
            continue
        if pd.notna(hedef_tarih) and pd.to_datetime(row["Date"], errors="coerce") >= hedef_tarih:
            continue
        key = (str(row["Date"]), takim_adi_norm(row["HomeTeam"]), takim_adi_norm(row["AwayTeam"]), row["FTHG"], row["FTAG"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows, {
        "aktif": bool(rows), "ev_id": ev_id, "dep_id": dep_id,
        "satir": len(rows), "hata": "; ".join(x for x in [e3, e4, e5] if x),
    }


def _baglam_gecmisini_api_ile_tamamla(gecmis_df, m):
    """Yerel geçmiş yetersizse API-Football satırlarını yalnızca fallback olarak birleştirir."""
    api_key = get_api_football_key()
    if not api_key:
        return gecmis_df, {"aktif": False, "hata": "API-Football key yok"}
    zaman = m.get("zaman")
    zaman_iso = zaman.isoformat() if hasattr(zaman, "isoformat") else str(zaman or "")
    rows, meta = _api_football_baglam_rows_cached(
        api_key, str(m.get("ev", "")), str(m.get("dep", "")), zaman_iso
    )
    if not rows:
        return gecmis_df, meta
    api_df = pd.DataFrame(rows)
    # Desteklenen liglerde mevcut bağlam fonksiyonlarının league_code filtresi
    # API-Football fallback satırlarını yanlışlıkla dışlamasın.
    api_df["league_code"] = ODDS_TO_HISTORY.get(str(m.get("sport_key", "")), "API_FOOTBALL")
    if gecmis_df is None or getattr(gecmis_df, "empty", True):
        return api_df, meta
    cols = sorted(set(gecmis_df.columns).union(api_df.columns))
    a = gecmis_df.reindex(columns=cols)
    b = api_df.reindex(columns=cols)
    merged = pd.concat([a, b], ignore_index=True)
    if all(c in merged.columns for c in ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]):
        merged["_dedupe"] = merged.apply(
            lambda r: f"{pd.to_datetime(r.get('Date'), errors='coerce')}|{takim_adi_norm(r.get('HomeTeam'))}|{takim_adi_norm(r.get('AwayTeam'))}|{r.get('FTHG')}|{r.get('FTAG')}", axis=1
        )
        merged = merged.drop_duplicates("_dedupe", keep="first").drop(columns=["_dedupe"])
    return merged, meta

def _genel_form_baglam_destegi(gecmis_df, m, label):
    """Son 5 genel formu, mevcut form_market_carpani mantığıyla -3..+3 puana çevirir."""
    if gecmis_df is None or getattr(gecmis_df, "empty", True):
        return {"puan": 0.0, "aktif": False}
    profil = mac_form_profili(gecmis_df, m, limit=5)
    if not profil.get("aktif"):
        return {"puan": 0.0, "aktif": False}
    factor = float(form_market_carpani(label, profil))
    puan = max(-3.0, min(3.0, (factor - 1.0) * 60.0))
    return {"puan": round(puan, 2), "aktif": True, "profil": profil}


def _piyasa_25_baglam_destegi(m, label):
    """Gerçek 2.5 Alt/Üst oranlarından marjı ayıklayıp küçük piyasa doğrulaması verir."""
    label = str(label or "")
    if "2.5 Üst" not in label and "2.5 Alt" not in label:
        return {"puan": 0.0, "aktif": False, "olasilik": None}
    try:
        over = float(m.get("o25_over"))
        under = float(m.get("o25_under"))
        if over <= 1 or under <= 1:
            raise ValueError
    except Exception:
        return {"puan": 0.0, "aktif": False, "olasilik": None}
    io, iu = 1.0/over, 1.0/under
    den = io + iu
    if den <= 0:
        return {"puan": 0.0, "aktif": False, "olasilik": None}
    p_over, p_under = io/den, iu/den
    p = p_over if "2.5 Üst" in label else p_under
    puan = max(-3.0, min(3.0, (p - 0.50) * 12.0))
    return {"puan": round(puan, 2), "aktif": True, "olasilik": round(p*100, 1), "over": over, "under": under}


def gunun_baglam_puani(gecmis_df, m, label, api_fallback=True):
    """Günün Kuponu bağlamı.

    Her katman önce yerel geçmişten hesaplanır. Bir katman yetersizse API-Football
    fallback o katmanı ayrı ayrı tamamlamaya çalışır. Böylece örneğin ev iç saha
    verisi varken deplasman tarafının eksik olması tüm saha katmanını boşa çıkarmaz.
    """
    h2h = _h2h_baglam_destegi(gecmis_df, m, label)
    form = _genel_form_baglam_destegi(gecmis_df, m, label)
    saha = _saha_baglam_destegi(gecmis_df, m, label)
    api_meta = {"aktif": False, "hata": "", "katmanlar": {}}
    kaynaklar = {
        "h2h": "Yerel geçmiş" if int(h2h.get("mac", 0) or 0) >= 3 else "Veri yok",
        "form": "Yerel geçmiş" if bool(form.get("aktif")) else "Veri yok",
        "saha": "Yerel geçmiş" if bool(saha.get("aktif")) else "Veri yok",
    }

    yerel_yetersiz = (
        int(h2h.get("mac", 0) or 0) < 3
        or not bool(form.get("aktif"))
        or not bool(saha.get("aktif"))
    )

    if api_fallback and yerel_yetersiz:
        # Key yoksa da helper'ı çağır; Detay ekranında bunun nedenini açıkça gösterelim.
        tamamlanmis, api_meta = _baglam_gecmisini_api_ile_tamamla(gecmis_df, m)
        if api_meta.get("aktif") and tamamlanmis is not None and not getattr(tamamlanmis, "empty", True):
            h2h_api = _h2h_baglam_destegi(tamamlanmis, m, label)
            form_api = _genel_form_baglam_destegi(tamamlanmis, m, label)
            saha_api = _saha_baglam_destegi(tamamlanmis, m, label)

            # Katman bazında yalnız eksik veya daha dolu olanı değiştir.
            if int(h2h.get("mac", 0) or 0) < 3 and int(h2h_api.get("mac", 0) or 0) >= 3:
                h2h = h2h_api
                kaynaklar["h2h"] = "API-Football fallback"
            elif int(h2h_api.get("mac", 0) or 0) > int(h2h.get("mac", 0) or 0):
                h2h = h2h_api
                kaynaklar["h2h"] = "Yerel + API-Football"

            if not bool(form.get("aktif")) and bool(form_api.get("aktif")):
                form = form_api
                kaynaklar["form"] = "API-Football fallback"

            # Yerelde tek taraf eksik olsa bile API ile iki taraf tamamlandıysa kullan.
            if not bool(saha.get("aktif")) and bool(saha_api.get("aktif")):
                saha = saha_api
                kaynaklar["saha"] = "API-Football fallback"

        api_meta = dict(api_meta or {})
        api_meta["katmanlar"] = dict(kaynaklar)

    piyasa = _piyasa_25_baglam_destegi(m, label)
    toplam = (
        float(h2h.get("puan", 0) or 0)
        + float(form.get("puan", 0) or 0)
        + float(saha.get("puan", 0) or 0)
        + float(piyasa.get("puan", 0) or 0)
    )
    toplam = max(-7.5, min(7.5, toplam))
    kullanilan = [k for k, v in kaynaklar.items() if v != "Veri yok"]
    kaynak = " + ".join(sorted(set(kaynaklar[k] for k in kullanilan))) if kullanilan else "Bağlam geçmişi yok"
    return {
        "toplam": round(toplam, 2), "h2h": h2h, "form": form, "saha": saha,
        "piyasa25": piyasa, "kaynak": kaynak, "kaynaklar": kaynaklar,
        "api_fallback": api_meta,
    }

def gunun_en_guvenli_kuponunu_olustur(final_list, maks=6, min_guven=72, gecmis_df=None):
    """Kalite eşiğini geçen seçimlerden tek bir Günün Kuponu üretir.

    Amaç kuponu 5-6 maça doldurmak değil, gerçekten güçlü seçimlerde durmaktır.
    Aynı maçtan yalnızca bir seçim alınır. 1-6 seçim üretilebilir.
    Güven kadar 0.00-0.10 taramasındaki kararlılık da dikkate alınır.
    """
    simdi = tr_simdi()
    adaylar = []
    kontrollu_gevsek_adaylar = []

    for item in final_list or []:
        m, t = item.get("m", {}), item.get("t", {})
        zaman = m.get("zaman")
        if not hasattr(zaman, "strftime") or zaman <= simdi:
            continue
        if t.get("belirsiz") or not t.get("oynanabilir", True):
            continue

        guven = min(100, int(t.get("ana_p", 0) or 0))
        ornek = int(t.get("ornek", 0) or 0)
        tolerans = hassasiyet_oku(t.get("kullanilan_tolerans"))
        stabil = int(t.get("top10_hassasiyet_sayisi", t.get("stability_count", 0)) or 0)
        stabil_skor = float(t.get("top10_stabilite_skoru", item.get("top10_stabilite_skoru", 0)) or 0)
        min_ornek_gerekli = max(5, dinamik_min_mac(tolerans))
        secim_label = str(t.get("ana_label", "-"))
        baglam = gunun_baglam_puani(gecmis_df, m, secim_label) if gecmis_df is not None else {"toplam": 0.0}
        baglam_ayari = float(baglam.get("toplam", 0.0) or 0.0)

        if guven < int(min_guven) or ornek < min_ornek_gerekli or stabil < 3:
            continue
        # Güçlü H2H ters sinyali Günün Kuponu'nda gerçek bir kalite kapısıdır.
        # Son 5 H2H'nin hiçbiri ana tahmini desteklemiyorsa doğrudan ele.
        # Yalnız 1/5 destekliyorsa ancak çok güçlü ana model + yüksek kararlılık geçsin.
        h2h_b = baglam.get("h2h", {}) if isinstance(baglam, dict) else {}
        h2h_mac = int((h2h_b or {}).get("mac", 0) or 0)
        h2h_tutan = int((h2h_b or {}).get("tutan", 0) or 0)
        if h2h_mac >= 5:
            # H2H 0/5 artık doğrudan eleme değildir; toplam bağlam puanına negatif sinyal olarak yansır.
            if h2h_tutan == 1 and not (guven >= 90 and stabil >= 7):
                continue

        # Toplam bağlam artık yalnız sıralama bonusu/cezası değil, kalite kapısı da.
        # -2..-4 bandında yüksek güven + kararlılık, -4 altında ise çok daha güçlü
        # ana model gerekir. Pozitif bağlam minimum kalite eşiklerini gevşetmez.
        if baglam_ayari <= -4.0 and not (guven >= 94 and stabil >= 8):
            continue
        if -4.0 < baglam_ayari <= -2.0 and not (guven >= 90 and stabil >= 7):
            continue

        # Dinamik kalite kapısı. Yüksek güven, daha düşük kararlılığı bir ölçüde
        # telafi edebilir; güven düştükçe daha fazla hassasiyet noktasında aynı
        # marketin kararlı kalmasını isteriz. Böylece kupon 5-6 maça zorla dolmaz.
        kalite_gecer = (
            (guven >= 92 and stabil >= 3)
            or (guven >= 86 and stabil >= 4)
            or (guven >= 80 and stabil >= 6)
            or (guven >= 76 and stabil >= 8)
        )
        kontrollu_gevsek_gecer = (
            (guven >= 88 and stabil >= 3)
            or (guven >= 83 and stabil >= 4)
            or (guven >= 78 and stabil >= 5)
            or (guven >= 74 and stabil >= 7)
        )
        _sadece_gevsek = (not kalite_gecer) and kontrollu_gevsek_gecer
        if (not kalite_gecer) and (not kontrollu_gevsek_gecer):
            continue

        # Sıralamada güven ana unsur; kararlılık ciddi ağırlık taşır.
        # Örnek sayısı ve mevcut stabilite skoru eşitlik/ince ayar için kullanılır.
        gunun_puani = (
            guven
            + stabil * 1.8
            + min(ornek, 40) * 0.12
            + min(max(stabil_skor, 0.0), 200.0) * 0.015
            + baglam_ayari
        )

        aday = {
            "m": m,
            "t": t,
            "guven": guven,
            "stabil": stabil,
            "stabil_skor": stabil_skor,
            "ornek": ornek,
            "gunun_puani": gunun_puani,
            "baglam": baglam,
            "baglam_ayari": baglam_ayari,
            "kontrollu_gevsetme": bool(_sadece_gevsek),
        }
        if _sadece_gevsek:
            kontrollu_gevsek_adaylar.append(aday)
        else:
            adaylar.append(aday)

    # Sıkı kriterlerle en az iki farklı maç çıkmazsa yalnızca güvenli sınırdaki
    # adaylardan eksik seçim tamamlanır. Örnek/H2H/negatif bağlam kırmızı
    # bayrakları yukarıdaki filtrelerde aynen korunur.
    # Aday dict'inin kökünde match_id/home_team yok; maç bilgisi a["m"] içinde.
    # Önceki sürüm bu nedenle bütün adayları "|" anahtarına düşürüp tek maç
    # sanabiliyordu. Gerçek maç anahtarını kullan.
    _strict_maclar = {mac_key(a.get("m", {})) for a in adaylar}
    if len(_strict_maclar) < 2 and kontrollu_gevsek_adaylar:
        kontrollu_gevsek_adaylar.sort(
            key=lambda x: (
                float(x.get("gunun_puani", 0) or 0),
                float(x.get("guven", 0) or 0),
                int(x.get("stabil", 0) or 0),
                int(x.get("ornek", 0) or 0),
            ),
            reverse=True,
        )
        for _ek in kontrollu_gevsek_adaylar:
            _mid = mac_key(_ek.get("m", {}))
            if _mid in _strict_maclar:
                continue
            adaylar.append(_ek)
            _strict_maclar.add(_mid)
            if len(_strict_maclar) >= 2:
                break

    adaylar.sort(
        key=lambda x: (x["gunun_puani"], x["guven"], x["stabil"], x["ornek"]),
        reverse=True,
    )

    secimler = []
    kullanilan_maclar = set()
    for aday in adaylar:
        m, t = aday["m"], aday["t"]
        mac_id = mac_key(m)
        if mac_id in kullanilan_maclar:
            continue

        secim_label = str(t.get("ana_label", "-"))
        secim_oran = t.get("ana_odd")
        secimler.append({
            "ev": m.get("ev", ""),
            "dep": m.get("dep", ""),
            "lig": str(m.get("lig", "")),
            "zaman_iso": m["zaman"].strftime("%Y-%m-%d %H:%M:%S"),
            "zaman_text": m["zaman"].strftime("%d.%m %H:%M"),
            "tahmin": secim_label,
            "guven": int(aday["guven"]),
            "oran": float(secim_oran) if secim_oran is not None else None,
            "oran_tahmini": bool(t.get("top10_market_oran_tahmini", False)),
            "hassasiyet": hassasiyet_oku(t.get("kullanilan_tolerans")),
            "hassasiyetler": list(t.get("top10_hassasiyetler", t.get("stability_tols", [])) or []),
            "hassasiyet_sayisi": int(aday["stabil"]),
            "gunun_puani": round(float(aday["gunun_puani"]), 1),
            "baglam_ayari": round(float(aday["baglam_ayari"]), 2),
            "baglam": aday.get("baglam", {}),
            "kontrollu_gevsetme": bool(aday.get("kontrollu_gevsetme", False)),
            "otomatik": True,
            "profil": "Günün Kuponu",
            **oran_kayit_bilgisi(m), "sport_key": m.get("sport_key", ""),
            "h": m.get("h"),
            "b": m.get("b"),
            "a": m.get("a"),
            "o25_over": m.get("o25_over"),
            "o25_under": m.get("o25_under"),
            "totals_bookmaker_key": m.get("totals_bookmaker_key", ""),
        })
        # Sonuç Takibi bağlam performansını ölçebilsin diye seçim anındaki
        # bağlamı tahmin kaydına snapshot olarak yaz. Gelecekte yeniden hesaplanmaz.
        try:
            tahmin_loguna_baglam_yaz(m, secim_label, aday.get("baglam", {}))
        except Exception:
            pass
        kullanilan_maclar.add(mac_id)
        if len(secimler) >= int(maks):
            break

    # Kalite eşiğini geçen tek bir aday bile varsa Günün Kuponu'nu oluştur.
    # Böylece aday havuzu oluştuğu günlerde sırf ikinci seçim bulunamadığı için
    # kupon tamamen iptal edilmez.
    return kupon_secimlerini_tamamla(secimler, final_list)


KUPON_GECMISI_PATH = APP_DATA_DIR / "vibe_kupon_gecmisi.json"


def kupon_gecmisini_oku():
    try:
        return kayit_deposu().read("kuponlar", KUPON_GECMISI_PATH)
    except (OSError, ValueError, sqlite3.Error) as error:
        kayit_hatasi("Kupon geçmişi okunamadı", error)
        return []


def kupon_gecmisini_yaz(kayitlar):
    return kayitlari_degistir("kuponlar", lambda _: kayitlar, KUPON_GECMISI_PATH)


def kupon_secimlerini_tamamla(secimler, items=None):
    if items is None:
        items = list(st.session_state.get("final_list", []) or []) + list(st.session_state.get("top50_list", []) or [])
    result = []
    for original in secimler or []:
        secim = dict(original)
        kickoff = parse_mac_datetime(secim.get("zaman_iso", secim.get("zaman")))
        for item in items:
            m, t = item.get("m", {}), item.get("t", {})
            candidate_time = parse_mac_datetime(m.get("zaman"))
            if (kickoff is None or candidate_time is None or kickoff != candidate_time
                or str(secim.get("ev")) != str(m.get("ev")) or str(secim.get("dep")) != str(m.get("dep"))):
                continue
            # Kaydedilen markete ait analiz varsa onu tercih et.
            if str(secim.get("tahmin")) not in (str(t.get("ana_label")), str(t.get("combo_label")), str(t.get("alt_label"))):
                continue
            for key, value in oran_kayit_bilgisi(m).items():
                if secim.get(key) is None:
                    secim[key] = value
            if not secim.get("detay_snapshot"):
                secim["detay_snapshot"] = detay_snapshot_olustur(m, t, item.get("b"))
            if secim.get("hassasiyet") is None:
                secim["hassasiyet"] = hassasiyet_oku(t.get("kullanilan_tolerans"))
            break
        secim["model_version"] = secim.get("model_version") or MODEL_VERSION
        result.append(secim)
    return result


def kupon_gecmisine_ekle(secimler, profil, hassasiyet):
    secimler = kupon_secimlerini_tamamla(secimler)
    kayit = {
        "kupon_id": datetime.now(TR_TIMEZONE).strftime("%Y%m%d%H%M%S%f"),
        "profil": str(profil),
        "hassasiyet": round(float(hassasiyet), 2) if isinstance(hassasiyet, (int, float)) else str(hassasiyet),
        "olusturma_zamani": kayit_zamani_iso(),
        "secimler": _json_guvenli_deger(secimler),
        "model_version": MODEL_VERSION,
    }
    if not kayitlari_degistir("kuponlar", lambda records: [kayit, *records][:200], KUPON_GECMISI_PATH):
        return None
    return kayit


def manuel_kupona_ekle(m, t, tahmin, guven, oran=None, oran_tahmini=False):
    """Kullanıcının seçtiği ana veya kombo tercihi Kendi Kuponum'a ekler."""
    coupon_item = {
        "ev": m.get("ev", ""),
        "dep": m.get("dep", ""),
        "lig": m.get("lig", ""),
        "zaman_iso": m["zaman"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(m.get("zaman"), "strftime") else str(m.get("zaman", "")),
        "zaman_text": m["zaman"].strftime("%d.%m %H:%M") if hasattr(m.get("zaman"), "strftime") else "-",
        "tahmin": str(tahmin),
        "guven": int(guven or 0),
        "oran": oran,
        "oran_tahmini": bool(oran_tahmini),
        "profil": "Kendi Kuponum",
        "otomatik": False,
        **oran_kayit_bilgisi(m), "sport_key": m.get("sport_key", ""),
        "h": m.get("h"),
        "b": m.get("b"),
        "a": m.get("a"),
    }
    mevcutlar = {
        (x.get("ev", ""), x.get("dep", ""), x.get("tahmin", ""))
        for x in st.session_state.kupona if isinstance(x, dict)
    }
    imza = (coupon_item["ev"], coupon_item["dep"], coupon_item["tahmin"])
    if imza in mevcutlar:
        return False
    coupon_item.update(oran_kayit_bilgisi(m))
    coupon_item["hassasiyet"] = hassasiyet_oku(t.get("kullanilan_tolerans"))
    coupon_item["model_version"] = MODEL_VERSION
    coupon_item = kupon_secimlerini_tamamla([coupon_item])[0]
    st.session_state.kupona.append(coupon_item)
    st.session_state.coupon_popup_open = True
    st.session_state.scroll_to_coupon = True
    return True




# ==========================================================
# SADE ANALIZ MODU
# AI günlük tarama, auto kupon builder ve 30 günlük kasa planı kaldırıldı.
# Sistem artık sadece mevcut maç bültenini tek toleransla analiz eder.
# ==========================================================

def market_label_to_odd(m_row, label):
    """Tahmin etiketinin yalnızca GERÇEK bookmaker oranını döndürür.

    1-X-2 ve featured 2.5 totals lig bülteninden; KG Var/Yok ise event-bazlı
    BTTS marketinden gelir. Bir market için gerçek oran yoksa None döner; başka
    marketten oran türetmez ve tahmini kombo oranını burada kullanmaz.
    """
    if not isinstance(m_row, dict):
        try:
            m_row = m_row.to_dict()
        except Exception:
            pass
    label = str(label or "").strip()
    mapping = {
        "MS 1": "h", "MS1": "h",
        "MS 2": "a", "MS2": "a",
        "Beraberlik": "b", "MS X": "b", "MSX": "b",
        "2.5 Üst": "o25_over",
        "2.5 Alt": "o25_under",
        "KG Var": "btts_yes",
        "KG Yok": "btts_no",
    }
    key = mapping.get(label)
    if not key:
        return None
    value = m_row.get(key)
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 1 else None
    except (TypeError, ValueError):
        return None




EK_MARKET_CACHE_TTL = 15 * 60  # Detay oranlarını 15 dk cache'le; aynı maçı tekrar açmak kredi harcamasın.
EK_MARKET_KEYS = (
    "alternate_totals",
    "btts",
    "btts_h1",
    "halftime_fulltime",
    "correct_score",
    "alternate_totals_corners",
    "alternate_totals_cards",
)


def _ek_market_bk_priority(bk, preferred_key=""):
    """Ek marketlerde mevcut 1X2 bookmaker'ını öncele, sonra sabit tercih sırasını kullan."""
    bk_key = str((bk or {}).get("key", "") or "")
    preferred = ("williamhill", "pinnacle", "bwin", "betvictor", "bet365")
    if preferred_key and bk_key == str(preferred_key):
        return (0, -1, bk_key)
    return (1, preferred.index(bk_key) if bk_key in preferred else len(preferred), bk_key)


def _ek_market_outcome_text(outcome):
    """The Odds API outcome nesnesini kullanıcıya okunur etikete çevir."""
    name = str((outcome or {}).get("name", "") or "").strip()
    desc = str((outcome or {}).get("description", "") or "").strip()
    point = (outcome or {}).get("point")
    parts = []
    if desc and desc.lower() != name.lower():
        parts.append(desc)
    if name:
        parts.append(name)
    try:
        p = float(point)
        if math.isfinite(p):
            parts.append(f"{p:g}")
    except (TypeError, ValueError):
        pass
    return " · ".join(parts) if parts else "—"


def ek_market_oranlari_al(m_row, zorla_yenile=False):
    """Bir maçın additional soccer marketlerini yalnız detay açıldığında getirir.

    Tek event isteğinde alternate totals, BTTS, İY BTTS, İY/MS, doğru skor,
    korner ve kart toplamlarını ister. Sonuç session_state'te 15 dk cache'lenir.
    Gerçek bookmaker fiyatı olmayan hiçbir değeri tahmin etmez.
    """
    if not isinstance(m_row, dict):
        try:
            m_row = m_row.to_dict()
        except Exception:
            return {"markets": {}, "error": "Maç bilgisi okunamadı."}

    event_id = str(m_row.get("match_id", "") or "").strip()
    sport_key = str(m_row.get("sport_key", "") or "").strip()
    if not event_id or not sport_key:
        return {"markets": {}, "error": "Event ID / lig kodu bulunamadı."}

    api_key = get_app_api_key()
    if not api_key:
        return {"markets": {}, "error": "ODDS API anahtarı gerekli."}

    cache = st.session_state.setdefault("ek_market_odds_cache", {})
    cache_key = f"{sport_key}|{event_id}"
    now = time.time()
    cached = cache.get(cache_key)
    if (not zorla_yenile and isinstance(cached, dict)
            and now - float(cached.get("cached_at", 0) or 0) < EK_MARKET_CACHE_TTL):
        return cached

    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "eu",
                "markets": ",".join(EK_MARKET_KEYS),
                "oddsFormat": "decimal",
            },
            timeout=15,
        )
        try:
            st.session_state["odds_api_quota"] = {
                "remaining": r.headers.get("x-requests-remaining"),
                "used": r.headers.get("x-requests-used"),
                "last": r.headers.get("x-requests-last"),
                "updated_at": time.time(),
            }
        except Exception:
            pass

        if r.status_code != 200:
            try:
                err = r.text[:350]
            except Exception:
                err = ""
            result = {
                "markets": {},
                "error": f"Ek market oranları alınamadı (HTTP {r.status_code}). {err}".strip(),
                "cached_at": now,
            }
            # Hataları uzun süre cache'leme; 45 sn sonra yeniden denenebilsin.
            result["cached_at"] = now - EK_MARKET_CACHE_TTL + 45
            cache[cache_key] = result
            return result

        data = r.json()
        bookies = data.get("bookmakers", []) if isinstance(data, dict) else []
        preferred_key = str(m_row.get("bookmaker_key", "") or "")
        bookies = sorted(bookies, key=lambda bk: _ek_market_bk_priority(bk, preferred_key))

        selected = {}
        for market_key in EK_MARKET_KEYS:
            for bk in bookies:
                mk = next((x for x in (bk.get("markets", []) or [])
                           if str(x.get("key", "")) == market_key), None)
                if not mk:
                    continue
                rows = []
                for outcome in mk.get("outcomes", []) or []:
                    try:
                        price = float(outcome.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(price) or price <= 1:
                        continue
                    rows.append({
                        "Seçim": _ek_market_outcome_text(outcome),
                        "Oran": price,
                        "name": outcome.get("name"),
                        "description": outcome.get("description"),
                        "point": outcome.get("point"),
                    })
                if rows:
                    selected[market_key] = {
                        "bookmaker_key": str(bk.get("key", "") or ""),
                        "bookmaker_title": str(bk.get("title", "") or bk.get("key", "") or ""),
                        "last_update": mk.get("last_update") or bk.get("last_update"),
                        "rows": rows,
                    }
                    break

        result = {
            "markets": selected,
            "error": "" if selected else "Bu maç/bookmaker bölgesi için ek market oranı bulunamadı.",
            "cached_at": now,
        }
        cache[cache_key] = result
        return result
    except Exception as exc:
        LOGGER.debug("Ek market odds çağrısı başarısız: %s", type(exc).__name__)
        return {"markets": {}, "error": f"Ek market oranları alınamadı: {type(exc).__name__}"}


def detay_ek_market_oranlari_goster(m_row):
    """Detay ekranında gerçek ek market oranlarını kompakt tablolar halinde göster."""
    st.markdown("### 💹 Gerçek bookmaker oranları · Ek marketler")
    st.caption(
        "Bu bölüm yalnız maç detayı açıldığında The Odds API'den çekilir ve 15 dakika cache'lenir. "
        "Gösterilen fiyatlar gerçek API oranlarıdır; tahmini oran kullanılmaz."
    )

    veri = ek_market_oranlari_al(m_row)
    markets = veri.get("markets", {}) if isinstance(veri, dict) else {}
    hata = str(veri.get("error", "") or "") if isinstance(veri, dict) else ""
    if not markets:
        st.info(hata or "Ek market oranı bulunamadı.")
        return

    market_titles = [
        ("alternate_totals", "⚽ Alt / Üst · tüm çizgiler"),
        ("btts", "🤝 KG Var / Yok"),
        ("btts_h1", "⏱ İY KG Var / Yok"),
        ("halftime_fulltime", "🔁 İY / MS"),
        ("correct_score", "🎯 Doğru Skor"),
        ("alternate_totals_corners", "🚩 Korner Alt / Üst"),
        ("alternate_totals_cards", "🟨 Kart Alt / Üst"),
    ]

    for key, title in market_titles:
        mk = markets.get(key)
        if not mk:
            continue
        rows = mk.get("rows", []) or []
        if not rows:
            continue
        st.markdown(f"**{title}**")
        bk_title = mk.get("bookmaker_title") or mk.get("bookmaker_key") or "Bookmaker"
        updated = str(mk.get("last_update", "") or "")
        st.caption(f"{bk_title}" + (f" · güncelleme: {updated}" if updated else ""))
        tablo = pd.DataFrame([{"Seçim": r.get("Seçim", "—"), "Oran": r.get("Oran")} for r in rows])
        if not tablo.empty:
            try:
                tablo["Oran"] = pd.to_numeric(tablo["Oran"], errors="coerce").round(2)
            except Exception:
                pass
            st.dataframe(tablo, use_container_width=True, hide_index=True)

    eksik = [title for key, title in market_titles if key not in markets]
    if eksik:
        st.caption("Bu maçta API'den gelmeyen marketler: " + " · ".join(x.split(" ", 1)[-1] for x in eksik))

def ms_fair_probability(m_row, label):
    """1-X-2 bookmaker marjını normalize ederek fair piyasa olasılığını döndürür."""
    try:
        h = float(m_row.get("h"))
        d = float(m_row.get("b"))
        a = float(m_row.get("a"))
    except Exception:
        return None

    if min(h, d, a) <= 1.0:
        return None

    inv_h, inv_d, inv_a = 1.0 / h, 1.0 / d, 1.0 / a
    toplam = inv_h + inv_d + inv_a
    if toplam <= 0:
        return None

    label = str(label or "").strip()
    if label in ("MS 1", "MS1"):
        return inv_h / toplam
    if label in ("Beraberlik", "MS X", "MSX"):
        return inv_d / toplam
    if label in ("MS 2", "MS2"):
        return inv_a / toplam
    return None


def value_edge_hesapla(m_row, label, model_guven):
    """MS 1/X/2 için model olasılığı - marjsız piyasa olasılığı.
    Non-MS marketlerde gerçek bookmaker oranı olmadığı için None döner.
    """
    odd = market_label_to_odd(m_row, label)
    fair = ms_fair_probability(m_row, label)
    if odd is None or fair is None:
        return {
            "odd": None,
            "fair_prob": None,
            "raw_implied": None,
            "edge": None,
            "ev": None,
            "value_label": "N/A",
        }

    try:
        odd = float(odd)
        model = float(model_guven) / 100.0
    except Exception:
        return {
            "odd": None,
            "fair_prob": None,
            "raw_implied": None,
            "edge": None,
            "ev": None,
            "value_label": "N/A",
        }

    if odd <= 1.0:
        return {
            "odd": None,
            "fair_prob": None,
            "raw_implied": None,
            "edge": None,
            "ev": None,
            "value_label": "N/A",
        }

    raw_implied = 1.0 / odd
    edge = model - fair
    ev = model * odd - 1.0

    if edge >= 0.05:
        value_label = "Güçlü Value"
    elif edge >= 0.02:
        value_label = "Value"
    elif edge > 0:
        value_label = "Hafif Value"
    elif edge >= -0.02:
        value_label = "Nötr"
    else:
        value_label = "Negatif Value"

    return {
        "odd": round(odd, 3),
        "fair_prob": round(fair * 100.0, 2),
        "raw_implied": round(raw_implied * 100.0, 2),
        "edge": round(edge * 100.0, 2),
        "ev": round(ev * 100.0, 2),
        "value_label": value_label,
    }



def guven_bandi(guven):
    """%61+ güveni 5 puanlık kalibrasyon bantlarına ayırır."""
    try:
        g = int(round(float(guven)))
    except Exception:
        return "—"
    if g <= 60:
        return "≤60"
    alt = ((g - 61) // 5) * 5 + 61
    ust = min(alt + 4, 100)
    return f"{alt}-{ust}"


def rolling_kalibre_olasilik(onceki_kayitlar, label, ham_guven,
                              min_band=8, min_market=20, prior_strength=10):
    """Backtest sırasında yalnızca DAHA ÖNCEKİ test sonuçlarıyla kalibrasyon yapar.
    Aynı market+güven bandı yeterliyse onu, değilse market genelini kullanır.
    Beta-benzeri shrinkage ile küçük örneklemin aşırı etkisi azaltılır.
    """
    try:
        raw = max(0.01, min(0.99, float(ham_guven) / 100.0))
    except Exception:
        return None, "Ham güven", 0

    if not onceki_kayitlar:
        return raw * 100.0, "Ham güven (kalibrasyon verisi yok)", 0

    band = guven_bandi(ham_guven)
    ayni_band = [
        x for x in onceki_kayitlar
        if str(x.get("Tahmin")) == str(label) and str(x.get("Güven Bandı")) == band
    ]
    market = [x for x in onceki_kayitlar if str(x.get("Tahmin")) == str(label)]

    secim = None
    kaynak = ""
    if len(ayni_band) >= int(min_band):
        secim = ayni_band
        kaynak = f"{label} {band} ({len(secim)} geçmiş)"
    elif len(market) >= int(min_market):
        secim = market
        kaynak = f"{label} genel ({len(secim)} geçmiş)"
    else:
        return raw * 100.0, "Ham güven (yetersiz kalibrasyon)", len(market)

    wins = sum(1 for x in secim if bool(x.get("Tuttu")))
    n = len(secim)
    # Ham güveni zayıf prior olarak tut; veri arttıkça gerçekleşen oran baskınlaşır.
    calibrated = (wins + raw * float(prior_strength)) / (n + float(prior_strength))
    calibrated = max(0.01, min(0.99, calibrated))
    return calibrated * 100.0, kaynak, n


def kalibrasyon_haritasi_uret(bt, min_band=8, min_market=20, prior_strength=10):
    """Tamamlanmış backtestten gelecek maçlar için kalibrasyon haritası üretir."""
    if bt is None or getattr(bt, "empty", True):
        return {}

    gerekli = {"Tahmin", "Güven", "Tuttu"}
    if not gerekli.issubset(set(bt.columns)):
        return {}

    df = bt.copy()
    df = df[df["Tahmin"].isin(["MS 1", "Beraberlik", "MS 2"])].copy()
    if df.empty:
        return {}

    df["Güven Bandı"] = df["Güven"].apply(guven_bandi)
    sonuc = {"bands": {}, "markets": {}, "meta": {
        "min_band": int(min_band), "min_market": int(min_market),
        "prior_strength": int(prior_strength), "rows": int(len(df))
    }}

    for (label, band), g in df.groupby(["Tahmin", "Güven Bandı"]):
        n = len(g)
        if n >= int(min_band):
            raw_center = float(g["Güven"].mean()) / 100.0
            wins = int(g["Tuttu"].astype(bool).sum())
            p = (wins + raw_center * prior_strength) / (n + prior_strength)
            sonuc["bands"][f"{label}|{band}"] = {
                "p": round(p * 100.0, 2), "n": int(n),
                "empirical": round(wins / n * 100.0, 2),
                "raw_avg": round(raw_center * 100.0, 2),
            }

    for label, g in df.groupby("Tahmin"):
        n = len(g)
        if n >= int(min_market):
            raw_center = float(g["Güven"].mean()) / 100.0
            wins = int(g["Tuttu"].astype(bool).sum())
            p = (wins + raw_center * prior_strength) / (n + prior_strength)
            sonuc["markets"][str(label)] = {
                "p": round(p * 100.0, 2), "n": int(n),
                "empirical": round(wins / n * 100.0, 2),
                "raw_avg": round(raw_center * 100.0, 2),
            }
    return sonuc


def canli_kalibre_guven(label, ham_guven):
    """Son backtest kalibrasyonunu gelecek/canlı MS analizlerine uygular."""
    try:
        raw = float(ham_guven)
    except Exception:
        return ham_guven, "Ham güven"

    try:
        harita = st.session_state.get("value_calibration_map", {}) or {}
    except Exception:
        harita = {}

    if not harita:
        return raw, "Ham güven (kalibrasyon yok)"

    band = guven_bandi(raw)
    key = f"{label}|{band}"
    if key in harita.get("bands", {}):
        rec = harita["bands"][key]
        return float(rec["p"]), f"{label} {band}, n={rec['n']}"
    if str(label) in harita.get("markets", {}):
        rec = harita["markets"][str(label)]
        return float(rec["p"]), f"{label} genel, n={rec['n']}"
    return raw, "Ham güven (yetersiz kalibrasyon)"


def value_skor_bonusu(edge):
    """Kalibre Value doğrulanana kadar Top 50 sıralamasına etki ETMEZ."""
    return 0.0


def ayni_lig_gecmisi(gecmis_df, m_row, sadece_ayni_lig=False):
    """İstenirse güncel The Odds API ligini football-data ligine daraltır."""
    if not sadece_ayni_lig:
        return gecmis_df
    sport_key = m_row.get("sport_key", "") if hasattr(m_row, "get") else ""
    history_code = ODDS_TO_HISTORY.get(str(sport_key))
    if not history_code or "league_code" not in gecmis_df.columns:
        return gecmis_df.iloc[0:0].copy()
    return gecmis_df[gecmis_df["league_code"] == history_code].copy()


def ayni_lig_ornek_sayisi(ornek_df, m_row):
    """Seçilen benzer örneklerin kaçının güncel maçla aynı ligden olduğunu döndürür."""
    if ornek_df is None or getattr(ornek_df, "empty", True) or "league_code" not in ornek_df.columns:
        return 0
    sport_key = m_row.get("sport_key", "") if hasattr(m_row, "get") else ""
    history_code = ODDS_TO_HISTORY.get(str(sport_key))
    if not history_code:
        return 0
    return int((ornek_df["league_code"].astype(str) == str(history_code)).sum())


TAKIM_ADI_ALIASLARI = {
    # Türkiye
    "istanbulbasaksehir": "basaksehir",
    "istanbulbuyuksehirbelediyesi": "basaksehir",
    "istanbulbb": "basaksehir",
    "buyuksehyr": "basaksehir",       # football-data'nın eski kısa adı
    "gencbirligi": "genclerbirligi",
    "genclerbirligi": "genclerbirligi",
    "kasimpasa": "kasimpasa",
    # Beşiktaş / Erzurum: The Odds API, manuel Toto ve Football-Data adlarını aynı kulübe bağla.
    "besiktas": "besiktas",
    "besiktasjk": "besiktas",
    "besiktasjkas": "besiktas",
    "besiktasas": "besiktas",
    "erzurumbb": "erzurumspor",
    "erzurumspor": "erzurumspor",
    "erzurumsporfk": "erzurumspor",
    "bberzurumspor": "erzurumspor",
    "buyuksehirbelediyeerzurumspor": "erzurumspor",
    # İngiltere / İskoçya
    "manunited": "manchesterunited",
    "manutd": "manchesterunited",
    "manchesterutd": "manchesterunited",
    "mancity": "manchestercity",
    "tottenhamhotspur": "tottenham",
    "wolverhamptonwanderers": "wolves",
    "wolverhampton": "wolves",
    "newcastleutd": "newcastleunited",
    "westhamutd": "westhamunited",
    "nottmforest": "nottinghamforest",
    "nottingham": "nottinghamforest",
    "qpr": "queensparkrangers",
    # İspanya
    "athmadrid": "atleticomadrid",
    "atleticodemadrid": "atleticomadrid",
    "athbilbao": "athleticbilbao",
    "athleticclub": "athleticbilbao",
    "sociedad": "realsociedad",
    "betis": "realbetis",
    # İtalya
    "internazionale": "inter",
    "intermilan": "inter",
    "acmilan": "milan",
    "hellasverona": "verona",
    # Almanya
    "bayernmunich": "bayernmunchen",
    "fcbayernmunich": "bayernmunchen",
    "fcbayernmunchen": "bayernmunchen",
    "borussiadortmund": "dortmund",
    "bdortmund": "dortmund",
    "bvbdortmund": "dortmund",
    "bvb09dortmund": "dortmund",
    "tsghoffenheim": "hoffenheim",
    "tsg1899hoffenheim": "hoffenheim",
    "1899hoffenheim": "hoffenheim",
    "hoffenheim1899": "hoffenheim",
    "borussiamonchengladbach": "monchengladbach",
    "bmonchengladbach": "monchengladbach",
    "koln": "cologne",
    "fckoln": "cologne",
    "rbLeipzig".lower(): "leipzig",
    "rasenballsportleipzig": "leipzig",
    "bayer04leverkusen": "leverkusen",
    "bayerleverkusen": "leverkusen",
    "vflwolfsburg": "wolfsburg",
    "eintrachtfrankfurt": "frankfurt",
    "scfreiburg": "freiburg",
    "vfbStuttgart".lower(): "stuttgart",
    "werderbremen": "bremen",
    # Fransa / Hollanda / Portekiz
    "parissaintgermain": "parissg",
    "psg": "parissg",
    "marseilleolympique": "marseille",
    "lyonolympique": "lyon",
    "sportinglisbon": "sportingcp",
    "sportingclubdeportugal": "sportingcp",
    "psveindhoven": "psv",
    # Avrupa'da sık görülen alternatifler
    "fckobenhavn": "copenhagen",
    "kobenhavn": "copenhagen",
    "fc copenhagen": "copenhagen",
    "redbullsalzburg": "salzburg",
    "rbsalzburg": "salzburg",
}


def _takim_adi_ham_tokenlari(value):
    """Farklı kaynaklardaki kulüp adlarını karşılaştırılabilir tokenlara çevirir."""
    s = str(value or "").strip().casefold()
    # NFKD'nin tek başına ASCII'ye çeviremediği harfleri önce açıkça dönüştür.
    s = s.translate(str.maketrans({
        "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
        "đ": "d", "ð": "d", "þ": "th", "ł": "l", "ø": "o", "æ": "ae",
    }))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()

    token_esdegerleri = {
        "utd": "united", "st": "saint", "munich": "munchen",
        "kobenhavn": "copenhagen",
    }
    anlamsiz = {
        "fc", "cf", "afc", "sc", "ac", "fk", "sk", "bk", "sv", "as",
        "club", "football", "futbol", "calcio", "de", "the",
    }
    tokens = []
    for token in s.split():
        token = token_esdegerleri.get(token, token)
        if token in anlamsiz or re.fullmatch(r"(?:18|19|20)\d{2}", token):
            continue
        tokens.append(token)
    return tokens


def takim_adi_norm(value):
    """Takım adını bütün veri kaynakları için kanonik hale getirir."""
    tokens = _takim_adi_ham_tokenlari(value)
    birlesik = "".join(tokens)
    return TAKIM_ADI_ALIASLARI.get(birlesik, birlesik)


def takim_adi_eslestir(takim, adaylar):
    hedef = takim_adi_norm(takim)
    if not hedef:
        return None

    norm_map = {}
    for x in adaylar:
        if not str(x).strip():
            continue
        n = takim_adi_norm(x)
        if n and n not in norm_map:
            norm_map[n] = x

    if hedef in norm_map:
        return norm_map[hedef]

    skorlar = []
    for norm, orijinal in norm_map.items():
        oran = SequenceMatcher(None, hedef, norm).ratio()
        kisa, uzun = sorted((hedef, norm), key=len)
        kapsama = (len(kisa) / len(uzun)) if kisa and kisa in uzun else 0.0
        skorlar.append((max(oran, kapsama), orijinal))

    if not skorlar:
        return None
    skorlar.sort(key=lambda x: x[0], reverse=True)
    en_skor, en_iyi = skorlar[0]
    ikinci_skor = skorlar[1][0] if len(skorlar) > 1 else 0.0

    # Çok net bir benzerliği doğrudan kabul et. Daha zayıf eşleşmelerde yakın
    # ikinci aday varsa yanlış kulübe bağlamak yerine sonuç üretme.
    if en_skor >= 0.92:
        return en_iyi
    if en_skor >= 0.80 and (en_skor - ikinci_skor) >= 0.05:
        return en_iyi
    return None


def _takim_maskesi(series, takim):
    """Takım adını alias + kontrollü fuzzy eşleşme ile satırlara uygular.

    The Odds API'deki uzun adlar (örn. TSG Hoffenheim / Borussia Dortmund)
    football-data geçmişindeki kısa adlarla (Hoffenheim / Dortmund) aynı
    kanonik kulübe bağlanır. Yanlış eşleşmemek için önce exact/alias, sonra
    takim_adi_eslestir'in güvenli eşiklerini kullanır.
    """
    hedef = takim_adi_norm(takim)
    if not hedef:
        return pd.Series(False, index=series.index)

    norm_series = series.astype(str).map(takim_adi_norm)
    exact = norm_series.eq(hedef)
    if bool(exact.any()):
        return exact

    adaylar = pd.unique(series.astype(str)).tolist()
    eslesen = takim_adi_eslestir(takim, adaylar)
    if eslesen:
        return norm_series.eq(takim_adi_norm(eslesen))
    return pd.Series(False, index=series.index)


def takim_son_maclari(veri, eslesen_takim, mac_tarihi, limit=10):
    if veri is None or veri.empty or not eslesen_takim:
        return pd.DataFrame()

    tarih = pd.to_datetime(mac_tarihi, errors="coerce")
    ev_mask = _takim_maskesi(veri["HomeTeam"], eslesen_takim)
    dep_mask = _takim_maskesi(veri["AwayTeam"], eslesen_takim)
    v = veri[ev_mask | dep_mask].copy()

    if pd.notna(tarih):
        v = v[pd.to_datetime(v["Date"], errors="coerce") < tarih]

    return v.sort_values("Date", ascending=False).head(int(limit))


def takimlar_arasi_maclar(veri, ev_takim, dep_takim, mac_tarihi, limit=10):
    if veri is None or veri.empty or not ev_takim or not dep_takim:
        return pd.DataFrame(), 0

    ev_home = _takim_maskesi(veri["HomeTeam"], ev_takim)
    ev_away = _takim_maskesi(veri["AwayTeam"], ev_takim)
    dep_home = _takim_maskesi(veri["HomeTeam"], dep_takim)
    dep_away = _takim_maskesi(veri["AwayTeam"], dep_takim)

    maske = (ev_home & dep_away) | (dep_home & ev_away)
    v = veri[maske].copy()

    tarih = pd.to_datetime(mac_tarihi, errors="coerce")
    if pd.notna(tarih):
        v = v[pd.to_datetime(v["Date"], errors="coerce") < tarih]

    v = v.sort_values("Date", ascending=False)
    return v.head(int(limit)), len(v)


def son5_tablo_hazirla(maclar, takim):
    satirlar = []
    hedef_norm = takim_adi_norm(takim)
    for _, r in maclar.iterrows():
        evde = takim_adi_norm(r.get("HomeTeam")) == hedef_norm
        ev_gol = int(float(r.get("FTHG", 0))) if pd.notna(r.get("FTHG")) else 0
        dep_gol = int(float(r.get("FTAG", 0))) if pd.notna(r.get("FTAG")) else 0
        gf, ga = ev_gol, dep_gol
        if not evde:
            gf, ga = ga, gf
        sonuc = "🟢 G" if gf > ga else "🟡 B" if gf == ga else "🔴 M"
        satirlar.append({
            "Tarih": pd.to_datetime(r.get("Date"), errors="coerce").strftime("%d.%m.%Y"),
            "Maç": f"{kart_takim_adi(r.get('HomeTeam', ''))} – {kart_takim_adi(r.get('AwayTeam', ''))}",
            "Skor": f"{ev_gol}-{dep_gol}",
            "Sonuç": sonuc,
        })
    return pd.DataFrame(satirlar)


def takim_maclarini_sahaya_gore_filtrele(maclar, takim, secim):
    if maclar is None or maclar.empty or secim == "Tümü":
        return maclar
    if secim == "Sadece iç saha":
        return maclar[_takim_maskesi(maclar["HomeTeam"], takim)].copy()
    if secim == "Sadece deplasman":
        return maclar[_takim_maskesi(maclar["AwayTeam"], takim)].copy()
    return maclar


def h2h_tablo_hazirla(maclar):
    if maclar is None or maclar.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Tarih": pd.to_datetime(maclar["Date"], errors="coerce").dt.strftime("%d.%m.%Y"),
        "Ev sahibi": maclar["HomeTeam"].astype(str).map(kart_takim_adi),
        "Skor": maclar["FTHG"].astype(int).astype(str) + "-" + maclar["FTAG"].astype(int).astype(str),
        "Deplasman": maclar["AwayTeam"].astype(str).map(kart_takim_adi),
    })


def son_mac_kartlari_html(tablo):
    kartlar = []
    for _, r in tablo.iterrows():
        sonuc = str(r.get("Sonuç", ""))
        sonuc_cls = "win" if "G" in sonuc else "draw" if "B" in sonuc else "loss"
        tarih = escape(str(r.get("Tarih", "")))
        mac_adi = escape(str(r.get("Maç", "")))
        skor = escape(str(r.get("Skor", "")))
        sonuc_guvenli = escape(sonuc)
        kartlar.append(
            f'<div class="recent-match-row">'
            f'<div class="recent-top"><span>{tarih}</span>'
            f'<b class="{sonuc_cls}">{sonuc_guvenli}</b></div>'
            f'<div class="recent-bottom"><span title="{mac_adi}">{mac_adi}</span>'
            f'<strong>{skor}</strong></div></div>'
        )
    return '<div class="recent-match-list">' + "".join(kartlar) + "</div>"


def h2h_kartlari_html(tablo):
    kartlar = []
    for _, r in tablo.iterrows():
        tarih = escape(str(r.get("Tarih", "")))
        skor = escape(str(r.get("Skor", "")))
        ev = escape(str(r.get("Ev sahibi", "")))
        dep = escape(str(r.get("Deplasman", "")))
        kartlar.append(
            f'<div class="recent-match-row h2h-row">'
            f'<div class="recent-top"><span>{tarih}</span><b>{skor}</b></div>'
            f'<div class="recent-bottom h2h-teams"><span>{ev}</span>'
            f'<span>{dep}</span></div></div>'
        )
    return '<div class="recent-match-list">' + "".join(kartlar) + "</div>"


# ==========================================================
# GÜNCEL TAKIM FORMU - SON 5 MAÇ
# ==========================================================

def takim_form_ozeti(veri, takim_adi, mac_tarihi, limit=5):
    """Takımın hedef maçtan ÖNCEKİ son maçlarından form özeti üretir.
    Backtestte veri sızıntısını önlemek için mac_tarihi sonrası hiçbir maç kullanılmaz.
    """
    bos = {
        "takim": None, "mac": 0, "puan": 0, "puan_orani": 0.5,
        "galibiyet": 0, "beraberlik": 0, "maglubiyet": 0,
        "gf": 0.0, "ga": 0.0, "gol_farki": 0.0,
        "over25": 0.5, "btts": 0.5, "draw_rate": 0.33,
    }
    if veri is None or getattr(veri, "empty", True) or not str(takim_adi).strip():
        return bos

    adaylar = pd.unique(pd.concat([
        veri.get("HomeTeam", pd.Series(dtype=str)).astype(str),
        veri.get("AwayTeam", pd.Series(dtype=str)).astype(str),
    ], ignore_index=True)).tolist()
    eslesen = takim_adi_eslestir(takim_adi, adaylar)
    if not eslesen:
        return bos

    maclar = takim_son_maclari(veri, eslesen, mac_tarihi, limit=limit)
    if maclar is None or maclar.empty:
        return {**bos, "takim": eslesen}

    pts = wins = draws = losses = 0
    gf_list, ga_list, totals, btts_list = [], [], [], []

    for _, r in maclar.iterrows():
        try:
            home = str(r.get("HomeTeam", ""))
            hg = int(float(r.get("FTHG", 0)))
            ag = int(float(r.get("FTAG", 0)))
        except Exception:
            continue

        evde = home == str(eslesen)
        gf, ga = (hg, ag) if evde else (ag, hg)
        gf_list.append(gf)
        ga_list.append(ga)
        totals.append(hg + ag)
        btts_list.append(1 if hg > 0 and ag > 0 else 0)

        if gf > ga:
            wins += 1
            pts += 3
        elif gf == ga:
            draws += 1
            pts += 1
        else:
            losses += 1

    n = len(gf_list)
    if n == 0:
        return {**bos, "takim": eslesen}

    return {
        "takim": eslesen,
        "mac": n,
        "puan": pts,
        "puan_orani": pts / (3.0 * n),
        "galibiyet": wins,
        "beraberlik": draws,
        "maglubiyet": losses,
        "gf": sum(gf_list) / n,
        "ga": sum(ga_list) / n,
        "gol_farki": (sum(gf_list) - sum(ga_list)) / n,
        "over25": sum(1 for x in totals if x >= 3) / n,
        "btts": sum(btts_list) / n,
        "draw_rate": draws / n,
    }


def mac_form_profili(veri, m_row, limit=5):
    """Ev ve deplasman için form profili. Yeterli maç yoksa nötr döner."""
    tarih = m_row.get("zaman", m_row.get("Date", tr_simdi()))
    ev = takim_form_ozeti(veri, m_row.get("ev", m_row.get("HomeTeam", "")), tarih, limit=limit)
    dep = takim_form_ozeti(veri, m_row.get("dep", m_row.get("AwayTeam", "")), tarih, limit=limit)

    yeterli = ev.get("mac", 0) >= 3 and dep.get("mac", 0) >= 3
    if not yeterli:
        return {
            "aktif": False, "ev": ev, "dep": dep, "form_farki": 0.0,
            "goal_signal": 0.5, "btts_signal": 0.5, "draw_signal": 0.33,
            "durum": "Form için iki takımda da en az 3 geçmiş maç gerekli",
        }

    # Form gücü: puan oranı ana bileşen; gol farkı küçük destek.
    ev_strength = max(0.0, min(1.0, ev["puan_orani"] * 0.82 + max(0.0, min(1.0, (ev["gol_farki"] + 2) / 4)) * 0.18))
    dep_strength = max(0.0, min(1.0, dep["puan_orani"] * 0.82 + max(0.0, min(1.0, (dep["gol_farki"] + 2) / 4)) * 0.18))
    form_farki = max(-1.0, min(1.0, ev_strength - dep_strength))

    # Gol marketleri için iki takımın son maçlarının ortak profili.
    goal_signal = max(0.0, min(1.0, (ev["over25"] + dep["over25"]) / 2.0))
    btts_signal = max(0.0, min(1.0, (ev["btts"] + dep["btts"]) / 2.0))
    draw_signal = max(0.0, min(1.0, (ev["draw_rate"] + dep["draw_rate"]) / 2.0))

    return {
        "aktif": True,
        "ev": ev,
        "dep": dep,
        "form_farki": form_farki,
        "goal_signal": goal_signal,
        "btts_signal": btts_signal,
        "draw_signal": draw_signal,
        "durum": "Aktif",
    }


def form_market_carpani(label, profil):
    """Form sinyalini markete göre sınırlı biçimde uygular.
    Aralık yaklaşık 0.95–1.05. Market türüne keyfi bonus vermez;
    yalnızca o marketle ilgili form verisini kullanır.
    """
    if not profil or not profil.get("aktif"):
        return 1.0

    label = str(label or "")
    diff = float(profil.get("form_farki", 0.0))
    goal = float(profil.get("goal_signal", 0.5))
    btts = float(profil.get("btts_signal", 0.5))
    draw = float(profil.get("draw_signal", 0.33))

    if label in ("MS 1", "MS1"):
        signal = diff
    elif label in ("MS 2", "MS2"):
        signal = -diff
    elif label in ("Beraberlik", "MSX"):
        # Takımlar yakın güçteyse ve son maçlarda beraberlik yüksekse destek.
        closeness = 1.0 - min(abs(diff), 1.0)
        signal = ((closeness - 0.5) * 1.1) + ((draw - 0.33) * 0.9)
    elif "2.5 Üst" in label or "3.5 Üst" in label or "İY 0.5 Üst" in label or "İY 1.5 Üst" in label:
        signal = (goal - 0.5) * 2.0
    elif "2.5 Alt" in label or "KG Yok" in label:
        if "KG Yok" in label:
            signal = (0.5 - btts) * 2.0
        else:
            signal = (0.5 - goal) * 2.0
    elif "KG Var" in label:
        signal = (btts - 0.5) * 2.0
    elif label.startswith("HT/FT"):
        signal = diff * 0.55
    else:
        signal = 0.0

    signal = max(-1.0, min(1.0, signal))
    return max(0.95, min(1.05, 1.0 + signal * 0.05))


def form_ozet_yazi(profil):
    if not profil or not profil.get("aktif"):
        return "Form: yetersiz veri"
    ev, dep = profil["ev"], profil["dep"]
    return (
        f"Form (son {min(ev['mac'], dep['mac'])}): "
        f"Ev {ev['galibiyet']}G-{ev['beraberlik']}B-{ev['maglubiyet']}M "
        f"({ev['gf']:.1f}/{ev['ga']:.1f} gol) · "
        f"Dep {dep['galibiyet']}G-{dep['beraberlik']}B-{dep['maglubiyet']}M "
        f"({dep['gf']:.1f}/{dep['ga']:.1f} gol)"
    )

def hesapla(b_df, m_row, tolerans, sadece_ayni_lig=False, form_aktif=False, kalibrasyon_aktif=False, form_profili_override=None, hazir_havuz=False):
    # Kesin güvenlik filtresi:
    # İlk yarı verisi eksik 16 extra/worldwide lig hiçbir koşulda model örneği,
    # güven hesabı, örnek sayısı veya detay geçmişi olarak kullanılmasın.
    # hazir_havuz=True yalnızca hassasiyet_taramasi tarafından kullanılır:
    # tarih/lig ön hazırlığı bir kez yapılmış havuzu 11 kez yeniden hazırlamayız.
    if not hazir_havuz:
        b_df = zaman_uyumlu_gecmis(sadece_tam_verili_gecmis(b_df), m_row)
        b_df = tarih_oncesi_gecmis(b_df, m_row.get("zaman", m_row.get("Date")))
        if b_df is None or getattr(b_df, "empty", True):
            return None, pd.DataFrame()

        # Form, oran eşleşmesi yapılmadan önceki tarihsel takım maçlarından hesaplanır.
        form_kaynagi = ayni_lig_gecmisi(b_df, m_row, sadece_ayni_lig)
        b_df = form_kaynagi
    else:
        if b_df is None or getattr(b_df, "empty", True):
            return None, pd.DataFrame()
    if b_df.empty:
        return None, b_df
    priors = m_row.get("analysis_priors") or gecmis_tabanlari(b_df, m_row)
    rehber = tolerans_rehberi(float(tolerans))
    onerilen_min_mac = dinamik_min_mac(float(tolerans))

    # Güncel oranı geçmişte mümkünse gerçek kapanış (C) oranlarıyla karşılaştır.
    # Eski sezonlarda closing sütunu yoksa futbol_veri_motoru REF_* için pre-closing oranına düşer.
    ref_h = "REF_H" if "REF_H" in b_df.columns else "B365H"
    ref_d = "REF_D" if "REF_D" in b_df.columns else "B365D"
    ref_a = "REF_A" if "REF_A" in b_df.columns else "B365A"
    b = b_df.loc[oran_eslesme_maskesi(b_df, m_row, tolerans)].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A",
              "REF_H", "REF_D", "REF_A"]:
        if c in b.columns:
            b[c] = pd.to_numeric(b[c], errors="coerce")

    required_odds = [c for c in [ref_h, ref_d, ref_a] if c in b.columns]

    # Full-time analizleri için HT verisini zorunlu tutma.
    # Football-Data extra/worldwide liglerinde HTHG/HTAG/HTR bulunmayabiliyor.
    b = b.dropna(subset=["FTHG", "FTAG", *required_odds, "FTR"])
    if b.empty:
        return None, b

    sample = len(b)
    ms_weights, goal_weights, goal_note = analiz_agirliklari(b, m_row, tolerans)
    ms_n = etkin_ornek(ms_weights)
    goal_n = etkin_ornek(goal_weights)
    b["MS Ağırlık"] = ms_weights
    b["Gol Ağırlık"] = goal_weights
    toplam_gol = b["FTHG"] + b["FTAG"]

    ms_vc = ms_weights.groupby(b["FTR"]).sum() / ms_weights.sum()

    ms_mod = ms_vc.idxmax() if not ms_vc.empty else "D"
    ms_raw = float(ms_vc.get(ms_mod, 0))
    ms_side = "MS 1" if ms_mod == "H" else "MS 2" if ms_mod == "A" else "Beraberlik"

    ms1_raw = float(ms_vc.get("H", 0))
    msx_raw = float(ms_vc.get("D", 0))
    ms2_raw = float(ms_vc.get("A", 0))

    ms25_raw = agirlikli_oran((toplam_gol >= 3), goal_weights)
    ms35_raw = agirlikli_oran((toplam_gol >= 4), goal_weights)
    ms15_raw = agirlikli_oran((toplam_gol >= 2), goal_weights)
    kg_raw = agirlikli_oran(((b["FTHG"] > 0) & (b["FTAG"] > 0)), goal_weights)

    # İlk-yarı/HTFT yalnızca gerçekten HT verisi bulunan alt kümeden hesaplanır.
    if all(c in b.columns for c in ["HTHG", "HTAG", "HTR"]):
        b_ht = b.dropna(subset=["HTHG", "HTAG", "HTR"]).copy()
    else:
        b_ht = b.iloc[0:0].copy()

    if not b_ht.empty:
        ilk_yari_gol = b_ht["HTHG"] + b_ht["HTAG"]
        iy_vc = ms_weights.reindex(b_ht.index).groupby(b_ht["HTR"]).sum() / ms_weights.reindex(b_ht.index).sum()
        iy05_raw = agirlikli_oran(ilk_yari_gol >= 1, goal_weights)
        iy15_raw = agirlikli_oran(ilk_yari_gol >= 2, goal_weights)
        iykg_raw = agirlikli_oran((b_ht["HTHG"] > 0) & (b_ht["HTAG"] > 0), goal_weights.reindex(b_ht.index))
        htft_s = (
            b_ht["HTR"].replace({"H": "1", "A": "2", "D": "X"})
            + "/"
            + b_ht["FTR"].replace({"H": "1", "A": "2", "D": "X"})
        )
        htft_mod = htft_s.mode()[0] if not htft_s.empty else "-"
        htft_raw = float((ms_weights.reindex(htft_s.index).groupby(htft_s).sum() / ms_weights.reindex(htft_s.index).sum()).get(htft_mod, 0)) if not htft_s.empty else 0.0
    else:
        # HT verisi olmayan extra/worldwide liglerde ilk-yarı marketlerini
        # sıfırla; full-time MS/KG/Üst analizleri çalışmaya devam etsin.
        iy_vc = pd.Series(dtype="float64")
        iy05_raw = 0.0
        iy15_raw = 0.0
        iykg_raw = 0.0
        htft_s = pd.Series(dtype="object")
        htft_mod = "-"
        htft_raw = 0.0

    oran_ev = float(m_row["h"])
    oran_ber = float(m_row["b"])
    oran_dep = float(m_row["a"])

    # Güncel form: yalnızca hedef maçtan önceki son 5 maç.
    if form_aktif:
        form_profili = form_profili_override if form_profili_override is not None else mac_form_profili(form_kaynagi, m_row, limit=5)
    else:
        form_profili = {
            "aktif": False, "form_farki": 0.0, "goal_signal": 0.5, "btts_signal": 0.5,
            "draw_signal": 0.33, "durum": "Formsuz karşılaştırma"
        }

    sample_factor = sample_factor_hesapla(sample, float(tolerans))
    if oran_ev < 1.40 or oran_dep < 1.40:
        oran_factor = 0.93
    elif oran_ev > 6.50 or oran_dep > 6.50:
        oran_factor = 0.95
    else:
        oran_factor = 1.0

    # Model yalnızca analiz anında API'den alınan son oranı kullanır.
    guven_carpani = sample_factor * oran_factor
    match_type = mac_tipi(oran_ev, oran_dep)

    # Maç tipi bilgi amaçlıdır. Ortak çarpanlar olasılıkların toplamını bozmamalı.
    ms_bias = goal_bias = combo_bias = 1.0

    def _adj(raw, bias, label, n=None):
        goal_market = any(x in label for x in ("Üst", "Alt", "KG"))
        count = goal_n if goal_market else ms_n
        if n is not None:
            ht_weights = goal_weights if goal_market else ms_weights
            count = etkin_ornek(ht_weights.reindex(b_ht.index))
        if count <= 0:
            return 0.0
        if label in priors:
            return tabana_yaklastir(raw, count, priors[label], MODEL_SETTINGS["prior_strength"])
        # Tamamlayıcı ilk yarı sonuçları aynı simetrik prior ile düzeltilir.
        prior = 1/3 if label in ("İY 1", "İY X", "İY 2") else .5
        if label == "HT/FT":
            prior = 1/9
        return tabana_yaklastir(raw, count, prior, MODEL_SETTINGS["prior_strength"])

    ms_taraflar = [
        {"label": "MS 1", "raw_prob": ms1_raw, "conf_prob": _adj(ms1_raw, ms_bias, "MS 1"), "market": "ms", "mod": "H"},
        {"label": "Beraberlik", "raw_prob": msx_raw, "conf_prob": _adj(msx_raw, ms_bias, "Beraberlik"), "market": "ms", "mod": "D"},
        {"label": "MS 2", "raw_prob": ms2_raw, "conf_prob": _adj(ms2_raw, ms_bias, "MS 2"), "market": "ms", "mod": "A"},
    ]
    ou_taraflar = [
        {"label": "2.5 Üst", "raw_prob": ms25_raw, "conf_prob": _adj(ms25_raw, goal_bias, "2.5 Üst"), "market": "ou25"},
        {"label": "2.5 Alt", "raw_prob": 1-ms25_raw, "conf_prob": _adj(1-ms25_raw, goal_bias, "2.5 Alt"), "market": "ou25"},
    ]
    kg_taraflar = [
        {"label": "KG Var", "raw_prob": kg_raw, "conf_prob": _adj(kg_raw, goal_bias, "KG Var"), "market": "kg"},
        {"label": "KG Yok", "raw_prob": 1-kg_raw, "conf_prob": _adj(1-kg_raw, goal_bias, "KG Yok"), "market": "kg"},
    ]

    def _aile_kazanani(taraflar):
        sirali = sorted(taraflar, key=lambda x: (x["conf_prob"], x["raw_prob"]), reverse=True)
        kazanan = dict(sirali[0])
        fark = float(sirali[0]["conf_prob"]) - float(sirali[1]["conf_prob"])
        kazanan["aile_farki"] = fark
        # Karşıt iki taraf %4 güven puanından daha yakınsa bu aile kararsızdır.
        kazanan["aile_belirsiz"] = fark < 0.04
        return kazanan

    ms_best = _aile_kazanani(ms_taraflar)
    ou_best = _aile_kazanani(ou_taraflar)
    kg_best = _aile_kazanani(kg_taraflar)

    # Skor yönü ve yardımcı MS alanları da düzeltilmiş MS ailesinin kazananını izlesin.
    ms_label = ms_best["label"]
    ms_side = ms_label
    ms_mod = ms_best.get("mod", ms_mod)
    ms_raw = ms_best["raw_prob"]
    ou_label = ou_best["label"]
    kg_label = kg_best["label"]
    ou25_best_raw = ou_best["raw_prob"]
    kg_best_raw = kg_best["raw_prob"]
    ms_prob = ms_best["conf_prob"]
    ou25_prob = ou_best["conf_prob"]
    kg_prob = kg_best["conf_prob"]

    # belirsiz maç tespiti
    ms_sorted = sorted([ms1_raw, msx_raw, ms2_raw], reverse=True)
    ms_belirsiz = (max(ms1_raw, msx_raw, ms2_raw) < 0.42 and (ms_sorted[0] - ms_sorted[1]) < 0.06) or (abs(ms1_raw - ms2_raw) < 0.05 and abs(ms1_raw - msx_raw) < 0.05)
    ms_best["aile_belirsiz"] = ms_best["aile_belirsiz"] or ms_belirsiz
    belirsiz = all(candidate.get("aile_belirsiz") for candidate in (ms_best, ou_best, kg_best))

    cands = [ms_best, ou_best, kg_best]
    net_cands = [c for c in cands if not c.get("aile_belirsiz")]
    # Mümkünse karşıt tarafları birbirine çok yakın olan market ailesini ana tahmin yapma.
    secim_havuzu = net_cands or cands
    best = max(secim_havuzu, key=lambda x: (x["conf_prob"], x["raw_prob"]))
    best_conf = best["conf_prob"]
    fake_drop = best_conf < min(best["raw_prob"] * guven_carpani, 0.99) - 1e-9

    ana_label = best["label"]
    ana_p = int(round(best_conf * 100))
    ana_raw_p = int(round(best["raw_prob"] * 100))

    # Alternatif MUTLAKA başka market ailesinden gelir. Ana KG Var ise KG Yok,
    # ana 2.5 Üst ise 2.5 Alt alternatif olamaz.
    others = [c for c in cands if c["market"] != best["market"] and not c.get("aile_belirsiz")]
    if not others:
        others = [c for c in cands if c["market"] != best["market"]]
    if others:
        alt = max(others, key=lambda x: (x["conf_prob"], x["raw_prob"]))
        alt_conf = alt["conf_prob"]
        alt_label = alt["label"]
        alt_p = int(round(alt_conf * 100))
    else:
        alt_label, alt_p = "", 0

    # İkinci en güçlü farklı market yalnızca güveni %60'ın ÜSTÜNDEYSE alternatiftir.
    if alt_p <= 60:
        alt_label = ""
        alt_p = 0

    ana_odd = market_label_to_odd(m_row, ana_label)

    cond_ms1 = (b["FTR"] == "H")
    cond_msx = (b["FTR"] == "D")
    cond_ms2 = (b["FTR"] == "A")
    cond_ust25 = (toplam_gol >= 3)
    cond_alt25 = (toplam_gol <= 2)
    cond_kg_var = ((b["FTHG"] > 0) & (b["FTAG"] > 0))
    cond_kg_yok = ~cond_kg_var
    htft_series = htft_s

    # İlk yarı koşullarını tam veri indeksine taşı; HT verisi olmayan satırlar False kalır.
    cond_iy15 = pd.Series(False, index=b.index)
    cond_iykg = pd.Series(False, index=b.index)
    if not b_ht.empty:
        cond_iy15.loc[b_ht.index] = ((b_ht["HTHG"] + b_ht["HTAG"]) >= 2).astype(bool)
        cond_iykg.loc[b_ht.index] = ((b_ht["HTHG"] > 0) & (b_ht["HTAG"] > 0)).astype(bool)

    combo_defs = [
        ("MS1 + KG Var", cond_ms1 & cond_kg_var, "mskg"),
        ("MS1 + KG Yok", cond_ms1 & cond_kg_yok, "mskg"),
        ("MS1 + 2.5 Üst", cond_ms1 & cond_ust25, "msou"),
        ("MS1 + 2.5 Alt", cond_ms1 & cond_alt25, "msou"),
        ("MSX + KG Var", cond_msx & cond_kg_var, "mskg"),
        ("MSX + KG Yok", cond_msx & cond_kg_yok, "mskg"),
        ("MSX + 2.5 Üst", cond_msx & cond_ust25, "msou"),
        ("MSX + 2.5 Alt", cond_msx & cond_alt25, "msou"),
        ("MS2 + KG Var", cond_ms2 & cond_kg_var, "mskg"),
        ("MS2 + KG Yok", cond_ms2 & cond_kg_yok, "mskg"),
        ("MS2 + 2.5 Üst", cond_ms2 & cond_ust25, "msou"),
        ("MS2 + 2.5 Alt", cond_ms2 & cond_alt25, "msou"),
        ("2.5 Üst + KG Var", cond_ust25 & cond_kg_var, "oukg"),
        ("2.5 Alt + KG Yok", cond_alt25 & cond_kg_yok, "oukg"),
        ("İY 1.5 Üst + MS1", cond_iy15 & cond_ms1, "iyms"),
        ("İY 1.5 Üst + MS2", cond_iy15 & cond_ms2, "iyms"),
    ]

    raw_combo_list = []
    for combo_label, combo_cond, combo_type in combo_defs:
        combo_hit = int(combo_cond.sum())
        combo_raw = agirlikli_oran(combo_cond, goal_weights)
        combo_conf = min(combo_raw * guven_carpani * combo_bias * form_market_carpani(combo_label, form_profili), 0.99)
        combo_conf, combo_fake_drop = fake_confidence_duzelt(combo_conf, goal_n, float(tolerans))

        if combo_type == "oukg":
            gerekli_raw = 0.30 if match_type != "Sürpriz Açık" else 0.27
            gerekli_hit = max(4, onerilen_min_mac)
        elif combo_type == "iyms":
            # İlk yarı + maç sonucu komboları daha seyrektir; küçük örnekte öne çıkmasın.
            gerekli_raw = 0.22 if match_type != "Sürpriz Açık" else 0.20
            gerekli_hit = max(4, onerilen_min_mac)
        else:
            gerekli_raw = 0.26 if match_type != "Sürpriz Açık" else 0.23
            gerekli_hit = max(3, onerilen_min_mac)

        if combo_hit >= gerekli_hit and combo_raw >= gerekli_raw:
            raw_combo_list.append({
                "label": combo_label,
                "raw_prob": combo_raw,
                "conf_prob": combo_conf,
                "hit": combo_hit,
                "fake_drop": combo_fake_drop,
                "type": combo_type,
            })

    htft_counts = (ms_weights.reindex(htft_series.index).groupby(htft_series).sum() / ms_weights.reindex(htft_series.index).sum())
    for htft_label, htft_raw_prob in htft_counts.items():
        htft_hit = int((htft_series == htft_label).sum())
        htft_conf = min(float(htft_raw_prob) * guven_carpani * combo_bias * form_market_carpani(f"HT/FT {htft_label}", form_profili), 0.99)
        htft_conf, htft_fake_drop = fake_confidence_duzelt(htft_conf, etkin_ornek(ms_weights.reindex(b_ht.index)), float(tolerans))
        gerekli_raw = 0.22 if match_type != "Sürpriz Açık" else 0.20
        gerekli_hit = max(3, onerilen_min_mac)
        if htft_hit >= gerekli_hit and float(htft_raw_prob) >= gerekli_raw:
            raw_combo_list.append({
                "label": f"HT/FT {htft_label}",
                "raw_prob": float(htft_raw_prob),
                "conf_prob": htft_conf,
                "hit": htft_hit,
                "fake_drop": htft_fake_drop,
                "type": "htft",
            })

    def uyum_kontrol(label, ana):
        if ana == "2.5 Alt":
            return ("2.5 Alt" in label) or ("KG Yok" in label) or ("HT/FT X/X" in label) or ("HT/FT 1/X" in label) or ("HT/FT X/1" in label) or ("HT/FT 2/X" in label) or ("HT/FT X/2" in label)
        if ana == "2.5 Üst":
            return ("2.5 Üst" in label) or ("KG Var" in label) or ("HT/FT 1/1" in label) or ("HT/FT 2/2" in label) or ("HT/FT 1/2" in label) or ("HT/FT 2/1" in label)
        if ana == "KG Var":
            return ("KG Var" in label) or ("2.5 Üst + KG Var" in label) or ("HT/FT 1/1" in label) or ("HT/FT 2/2" in label)
        if ana == "KG Yok":
            return ("KG Yok" in label) or ("2.5 Alt + KG Yok" in label)
        if ana == "MS 1":
            return ("MS1" in label) or ("HT/FT 1/" in label) or ("HT/FT X/1" in label)
        if ana == "MS 2":
            return ("MS2" in label) or ("HT/FT 2/" in label) or ("HT/FT X/2" in label)
        if ana == "Beraberlik":
            return ("MSX" in label) or ("HT/FT X/X" in label)
        return True

    combo_list = [c for c in raw_combo_list if uyum_kontrol(c["label"], ana_label)]
    combo_list = sorted(combo_list, key=lambda x: (x["conf_prob"], x["raw_prob"], x["hit"]), reverse=True)

    if combo_list and combo_list[0]["conf_prob"] >= 0.33 and not belirsiz:
        best_combo = combo_list[0]
        combo_label = best_combo["label"]
        combo_p = int(round(best_combo["conf_prob"] * 100))
        combo_raw_p = int(round(best_combo["raw_prob"] * 100))
        combo_hit = int(best_combo["hit"])
        combo_var = True
    else:
        combo_label = ""
        combo_p = 0
        combo_raw_p = 0
        combo_hit = 0
        combo_var = False

    # kombo seviye
    combo_level = ""
    if combo_var:
        if combo_p >= 60:
            combo_level = "Premium"
        elif combo_p >= 45:
            combo_level = "Güçlü"
        else:
            combo_level = "Deneysel"

    if belirsiz:
        ana_p = min(ana_p, 50)
        combo_label = ""
        combo_var = False
        combo_level = ""

    if ana_p < 35 and not belirsiz:
        ana_label = "Tahmin Zayıf"

    # en uyumlu senaryo
    if belirsiz:
        scenario_label = "Net senaryo oluşmadı"
    else:
        senaryo_parts = []
        if ana_label not in ["Belirsiz Maç", "Tahmin Zayıf"]:
            senaryo_parts.append(ana_label)
        if combo_var and combo_label and combo_label != ana_label:
            combo_core = combo_label.replace("MS1 + ", "").replace("MS2 + ", "").replace("MSX + ", "")
            if combo_core not in senaryo_parts and combo_label not in senaryo_parts:
                if combo_label.startswith("HT/FT"):
                    senaryo_parts.append(combo_label)
                else:
                    senaryo_parts.append(combo_core)
        scenario_label = " + ".join(senaryo_parts[:3]) if senaryo_parts else ana_label

    # canlı strateji
    if belirsiz:
        canli_label, canli_p = "İlk 15 dk izle", 48
        canli_strateji = "İlk 15 dakikada yön netleşmezse bu maçı pas geç. Erken baskı oluşursa ancak o zaman markete gir."
    elif iy05_raw * guven_carpani >= 0.68:
        canli_label = "İY 0.5 Üst" + (
            " · 3.5 Üst" if ms35_raw * guven_carpani >= 0.60 else
            " · 2.5 Üst" if ms25_raw * guven_carpani >= 0.60 else
            ""
        )
        canli_p = int(round(iy05_raw * guven_carpani * 100))
        canli_strateji = "İlk 15 dakikada yüksek tempo ve şut hacmi varsa canlı üst tarafı güçlenir. Erken gol gelirse üst senaryosu desteklenir."
    elif iy15_raw * guven_carpani >= 0.55:
        canli_label = "İY 1.5 Üst"
        canli_p = int(round(iy15_raw * guven_carpani * 100))
        canli_strateji = "Maç hızlı başlarsa ilk yarı golleri değerlendir. 20. dakikaya kadar tempo yoksa bu senaryoyu zayıflat."
    elif ana_label == "2.5 Alt" or combo_label == "2.5 Alt + KG Yok":
        canli_label, canli_p = "Alt Senaryosu", max(50, int(round((1 - ms25_raw) * guven_carpani * 100)))
        canli_strateji = "İlk 15-20 dakikada tempo düşük ve ceza sahası aksiyonu azsa alt taraf güçlenir. Erken gol gelirse yeniden değerlendir."
    elif ana_label == "KG Yok":
        canli_label, canli_p = "Tek Taraf Gol", max(50, int(round((1 - kg_raw) * guven_carpani * 100)))
        canli_strateji = "Zayıf taraf üretim yapmıyorsa KG Yok korunur. İki takım da net pozisyona girerse bu görüşü düşür."
    else:
        canli_label, canli_p = "Canlı İzle", 50
        canli_strateji = "İlk 10-15 dakikada baskı, şut ve korner üstünlüğü hangi taraftaysa sadece o yönde canlı giriş düşün."

    flip_p = float((((b_ht["HTR"] == "H") & (b_ht["FTR"] == "A")) | ((b_ht["HTR"] == "A") & (b_ht["FTR"] == "H"))).mean()) if not b_ht.empty else 0.0

    risk_l, risk_cls = risk_seviyesi(ana_p, flip_p)
    eg, dg = tahmini_skor(b, ms_mod)
    eg, dg = skoru_tahmine_uydur(eg, dg, ana_label, ms_mod, alt_label, combo_label)
    gc, gb_cls, gb_lbl = guven_renk(ana_p)
    ornek_durum, ornek_renk = guven_metni(sample, float(tolerans))

    if sample < onerilen_min_mac:
        tavsiye = "Örnek az ama kullanılabilir"
    elif sample < max(10, onerilen_min_mac * 2):
        tavsiye = "Dengeli"
    elif sample > max(25, onerilen_min_mac * 3) and tolerans > 0.10:
        tavsiye = "Biraz düşürülebilir"
    else:
        tavsiye = "Uygun"

    avg_goal = float(toplam_gol.mean())
    goal_profile = gol_profili(avg_goal)

    nedenler = [
        f"Bu oran aralığında {sample} benzer maç bulundu.",
        f"Ham ana olasılık %{ana_raw_p} seviyesinde.",
        f"Ortalama toplam gol {avg_goal:.2f} ({goal_profile}).",
        f"Maç tipi: {match_type}.",
    ]
    if belirsiz:
        nedenler.append("1/X/2 dağılımı birbirine çok yakın olduğu için maç belirsiz işaretlendi.")
    if combo_var:
        nedenler.append(f"Güçlü kombo bulundu: {combo_label} (%{combo_raw_p}, {combo_hit} maç).")
    if fake_drop:
        nedenler.append("Düşük örnek + yüksek güven görüldüğü için fake confidence freni uygulandı.")
    kalibre_ana_p = float(ana_p)
    kalibrasyon_kaynagi = "Kaldırıldı"

    if form_profili.get("aktif"):
        nedenler.append(
            f"{form_ozet_yazi(form_profili)} · Ana market form çarpanı "
            f"{form_market_carpani(ana_label, form_profili):.3f}."
        )
    else:
        nedenler.append(f"Takım formu: {form_profili.get('durum', 'Yetersiz veri')}.")

    if flip_p >= 0.12:
        nedenler.append(f"HT/FT sürpriz riski %{int(round(flip_p * 100))}.")
    playable_score = ana_p
    if combo_var:
        playable_score += min(combo_p, 20) * 0.35
    playable_score += min(sample, 40) * 0.25
    if match_type == "Favori":
        playable_score += 4
    elif match_type == "Dengeli":
        playable_score += 2
    if belirsiz:
        playable_score -= 12
    if fake_drop:
        playable_score -= 6
    if flip_p >= 0.12:
        playable_score -= 4
    playable_score = round(playable_score, 1)

    oynanabilir = (ana_p >= 58 and sample >= onerilen_min_mac and not belirsiz)

    score = ana_p * 0.65
    if sample < onerilen_min_mac:
        score -= 18
    elif sample < max(onerilen_min_mac * 2, 10):
        score += 4
    elif sample < max(onerilen_min_mac * 3, 18):
        score += 8
    else:
        score += 10
    if combo_var:
        score += min(8, combo_p * 0.12)
    if belirsiz:
        score -= 20
    if fake_drop:
        score -= 6
    if oynanabilir:
        score += 6
    score = round(score, 1)


    sonuc = {
        "ana_label": ana_label,
        "ana_p": ana_p,
        "playable_score": round(ana_p * 0.8, 1),
        "ana_raw_p": ana_raw_p,
        "ana_odd": ana_odd,
        "odds_h": round(oran_ev, 3),
        "odds_d": round(oran_ber, 3),
        "odds_a": round(oran_dep, 3),
        "alt_label": alt_label,
        "alt_p": alt_p,
        "kg_label": kg_label,
        "kg_p": int(round(_adj(kg_best_raw, goal_bias, kg_label) * 100)),
        "combo_label": combo_label,
        "combo_p": combo_p,
        "combo_raw_p": combo_raw_p,
        "combo_hit": combo_hit,
        "combo_var": combo_var,
        "combo_level": combo_level,
        "scenario_label": scenario_label,
        "canli_label": canli_label,
        "canli_p": canli_p,
        "canli_strateji": canli_strateji,
        "belirsiz": belirsiz,
        "ms_belirsiz": bool(ms_belirsiz),
        "ms_side": ms_side,
        "ms_p": int(round(_adj(ms_raw, ms_bias, ms_side) * 100)),
        "ms_mod": ms_mod,
        "ms1_p": int(round(_adj(ms1_raw, ms_bias, "MS 1") * 100)),
        "msx_p": int(round(_adj(msx_raw, ms_bias, "Beraberlik") * 100)),
        "ms2_p": int(round(_adj(ms2_raw, ms_bias, "MS 2") * 100)),
        "ms25_p": int(round(_adj(ms25_raw, goal_bias, "2.5 Üst") * 100)),
        "ms25a_p": int(round(_adj(1-ms25_raw, goal_bias, "2.5 Alt") * 100)),
        "ms15_p": int(round(_adj(ms15_raw, goal_bias, "1.5 Üst") * 100)),
        "ms35_p": int(round(_adj(ms35_raw, goal_bias, "3.5 Üst") * 100)),
        "kg_var_p": int(round(_adj(kg_raw, goal_bias, "KG Var") * 100)),
        "kg_yok_p": int(round(_adj(1-kg_raw, goal_bias, "KG Yok") * 100)),
        "iy05_p": int(round(_adj(iy05_raw, goal_bias, "İY 0.5 Üst", n=len(b_ht)) * 100)),
        "iy05a_p": int(round(_adj(1-iy05_raw, goal_bias, "İY 0.5 Alt", n=len(b_ht)) * 100)),
        "iy15_p": int(round(_adj(iy15_raw, goal_bias, "İY 1.5 Üst", n=len(b_ht)) * 100)),
        "iykg_var_p": int(round(_adj(iykg_raw, goal_bias, "İY KG Var", n=len(b_ht)) * 100)),
        "iykg_yok_p": int(round(_adj(1-iykg_raw, goal_bias, "İY KG Yok", n=len(b_ht)) * 100)) if not b_ht.empty else 0,
        "iy1_p": int(round(_adj(float(iy_vc.get("H", 0)), 1.0, "İY 1", n=len(b_ht)) * 100)),
        "iyx_p": int(round(_adj(float(iy_vc.get("D", 0)), 1.0, "İY X", n=len(b_ht)) * 100)),
        "iy2_p": int(round(_adj(float(iy_vc.get("A", 0)), 1.0, "İY 2", n=len(b_ht)) * 100)),
        "htft_mod": htft_mod,
        "htft_p": int(round(_adj(htft_raw, combo_bias, "HT/FT", n=len(b_ht)) * 100)),
        "flip_p": flip_p,
        "risk_label": risk_l,
        "risk_cls": risk_cls,
        "eg": eg,
        "dg": dg,
        "guven_renk": gc,
        "guven_badge_cls": gb_cls,
        "guven_badge_lbl": gb_lbl,
        "ornek": sample,
        "ornek_durum": ornek_durum,
        "ornek_renk": ornek_renk,
        "onerilen_tolerans": rehber["onerilen_tolerans"],
        "onerilen_min_mac": onerilen_min_mac,
        "tolerans_yorumu": rehber["yorum"],
        "tolerans_tavsiyesi": tavsiye,
        "kullanilan_tolerans": round(float(tolerans), 2),
        "guven_carpani": round(guven_carpani, 3),
        "form_aktif": bool(form_profili.get("aktif")),
        "form_status": form_profili.get("durum", ""),
        "form_text": form_ozet_yazi(form_profili),
        "form_factor": round(form_market_carpani(ana_label, form_profili), 3),
        "form_ev_puan_orani": round(float(form_profili.get("ev", {}).get("puan_orani", 0.5)) * 100, 1) if form_profili.get("ev") else None,
        "form_dep_puan_orani": round(float(form_profili.get("dep", {}).get("puan_orani", 0.5)) * 100, 1) if form_profili.get("dep") else None,
        "form_farki": round(float(form_profili.get("form_farki", 0.0)), 3),
        "odds_basis": ("Eski kayıt: oran zamanı bilinmiyor; yaklaşık geçmiş karşılaştırması" if b.attrs.get("odds_time_unknown") else
                       "Kapanış evresi (yaklaşık)" if oran_fazi(m_row) == "closing" else "Maç öncesi evre (kesin saat bilinmiyor)"),
        "goal_matching": goal_note,
        "effective_ms_samples": round(ms_n, 6),
        "effective_goal_samples": round(goal_n, 6),
        "effective_ht_samples": round(min(etkin_ornek(ms_weights.reindex(b_ht.index)),
                                           etkin_ornek(goal_weights.reindex(b_ht.index))), 6),
        "odds_source": b.attrs.get("odds_history_prefix", "B365"),
        "odds_cross_bookmaker": bool(b.attrs.get("odds_cross_bookmaker")),
        "goal_profile": goal_profile,
        "match_type": match_type,
        "nedenler": nedenler,
        "oynanabilir": oynanabilir,
        "oynanabilir_esik_ok": (ana_p >= 55),
        "fake_drop": fake_drop,
        "score": round(ana_p * 0.8, 1),
        "model_version": MODEL_VERSION,
        "stability_tols": [],
        "stability_count": 0,
        "stability_text": "",
        "stability_early_tols": [],
        "stability_late_tols": [],
        "stability_early_text": "",
        "stability_late_text": "",
    }

    families = [
        (["ms1_p", "msx_p", "ms2_p"], [x["conf_prob"] for x in ms_taraflar]),
        (["ms25_p", "ms25a_p"], [x["conf_prob"] for x in ou_taraflar]),
        (["kg_var_p", "kg_yok_p"], [x["conf_prob"] for x in kg_taraflar]),
        (["iy05_p", "iy05a_p"], [_adj(iy05_raw, 1, "İY 0.5 Üst", n=len(b_ht)),
                                  _adj(1-iy05_raw, 1, "İY 0.5 Alt", n=len(b_ht))]),
        (["iy1_p", "iyx_p", "iy2_p"], [_adj(float(iy_vc.get(side, 0)), 1, label, n=len(b_ht))
                                           for side, label in (("H", "İY 1"), ("D", "İY X"), ("A", "İY 2"))]),
    ]
    for fields, probabilities in families:
        sonuc.update(zip(fields, olasilik_yuzdeleri(probabilities)))
    label_fields = {"MS 1": "ms1_p", "Beraberlik": "msx_p", "MS 2": "ms2_p",
                    "2.5 Üst": "ms25_p", "2.5 Alt": "ms25a_p", "KG Var": "kg_var_p", "KG Yok": "kg_yok_p"}
    if not belirsiz and sonuc["ana_label"] in label_fields:
        sonuc["ana_p"] = sonuc[label_fields[sonuc["ana_label"]]]
    if sonuc["alt_label"] in label_fields:
        sonuc["alt_p"] = sonuc[label_fields[sonuc["alt_label"]]]
    sonuc["ms_p"] = sonuc[label_fields[ms_side]]
    sonuc["kg_p"] = sonuc[label_fields[kg_label]]
    if sonuc["combo_var"]:
        combo_parts = [{"MS1": "MS 1", "MSX": "Beraberlik", "MS2": "MS 2"}.get(part.strip(), part.strip())
                       for part in sonuc["combo_label"].split("+")]
        bounds = [sonuc[label_fields[part]] for part in combo_parts if part in label_fields]
        if bounds:
            sonuc["combo_p"] = min(sonuc["combo_p"], *bounds)
    if sonuc["alt_p"] <= 60:
        sonuc["alt_label"], sonuc["alt_p"] = "", 0
    # Etkin örnek güven hesabında kullanılır; yeterlilik gerçek maç sayısına bağlıdır.
    sonuc["oynanabilir"] = (sonuc["ana_p"] >= 58 and not belirsiz
                             and sample >= onerilen_min_mac)
    sonuc["oynanabilir_esik_ok"] = sonuc["ana_p"] >= 55
    sonuc["score"] = sonuc["playable_score"] = round(sonuc["ana_p"] * .8, 1)
    gc, cls, badge = guven_renk(sonuc["ana_p"])
    sonuc.update(guven_renk=gc, guven_badge_cls=cls, guven_badge_lbl=badge)

    # Kullanıcıya gösterilen / aday sıralamasında kullanılan güven yüzdeleri
    # hiçbir koşulda %100'ü aşmasın. Puan/score alanları bundan bağımsız kalır.
    guven_alanlari = {
        "ana_p", "ana_raw_p", "alt_p", "kg_p", "combo_p", "combo_raw_p",
        "canli_p", "ms_p", "ms1_p", "msx_p", "ms2_p", "ms25_p",
        "ms25a_p", "ms15_p", "ms35_p", "kg_var_p", "kg_yok_p",
        "iy05_p", "iy05a_p", "iy15_p", "iy1_p", "iyx_p", "iy2_p", "htft_p",
    }
    for alan in guven_alanlari:
        if alan not in sonuc:
            continue
        try:
            sonuc[alan] = max(0, min(100, int(round(float(sonuc[alan] or 0)))))
        except Exception:
            pass

    return sonuc, b.sort_values("Date", ascending=False)



def market_gecmis_guven_duzeltmesi(etiket, ham_guven, kayitlar=None):
    """
    Marketin geçmiş backtest başarısını küçük bir güven düzeltmesi olarak kullanır.

    - Backtest içinde `kayitlar`, yalnızca o tarihten ÖNCE sonuçlanmış test kayıtlarıdır.
    - Canlı analizde `kayitlar=None` ise son çalıştırılmış backtest_df kullanılır.
    - Veri azsa düzeltme nötre yaklaştırılır; hiçbir zaman ana güvenin önüne geçmez.
    """
    try:
        ham = float(ham_guven)
    except Exception:
        ham = 0.0

    if kayitlar is None:
        kayitlar = sabit_kalibrasyon_kayitlari()

    ilgili = []
    for x in (kayitlar or []):
        if str(x.get("Tahmin", "")) != str(etiket):
            continue
        tuttu = x.get("Tuttu")
        if tuttu is None or (isinstance(tuttu, float) and pd.isna(tuttu)):
            continue
        ilgili.append(bool(tuttu))

    n = len(ilgili)
    if n == 0:
        return ham, None, 0, 0.0

    # Küçük örneğin aşırı etkisini azalt:
    # prior %60 ve 20 sanal gözlem. Sistem zaten %61+ tahminleri değerlendiriyor.
    prior_n = 20.0
    prior_success = 0.60
    wins = sum(ilgili)
    shrunk_success = (wins + prior_success * prior_n) / (n + prior_n) * 100.0

    # Market geçmişi yalnızca yardımcı sinyal:
    # 20 kayıtta etkisinin yarısı, 40+ kayıtta tamamı.
    veri_agirligi = min(n / 40.0, 1.0)
    # Ham güven %90, geçmiş market başarısı en fazla %10 etki eder.
    duzeltilmis = ham * (1.0 - 0.10 * veri_agirligi) + shrunk_success * (0.10 * veri_agirligi)
    delta = duzeltilmis - ham

    return duzeltilmis, shrunk_success, n, delta


def hassasiyet_birlesik_hesapla(b_df, m_row, min_ornek, sadece_ayni_lig=False,
                               market_gecmis_kayitlari=None, taramalar=None):
    havuz = birlesik_market_havuzu(b_df, m_row, min_ornek, sadece_ayni_lig,
                                 market_gecmis_kayitlari, taramalar=taramalar)
    return birlesik_tahmin_olustur(havuz[0], havuz, m_row) if havuz else (None, pd.DataFrame())

def kombo_tahmini_oran(label, ana_odd=None):
    """Top 10 Market içinde kombo marketler için yaklaşık oran üretir.
    Gerçek bookmaker kombo oranı API'den gelmediği için sadece tahmini gösterim amaçlıdır.
    """
    if not label:
        return None

    label = str(label)
    try:
        base = float(ana_odd) if ana_odd else 1.60
    except Exception:
        base = 1.60

    if label.startswith("HT/FT"):
        return 4.50
    if "KG Var" in label or "KG Yok" in label:
        return round(base * 1.55, 2)
    if "2.5 Üst" in label or "2.5 Alt" in label:
        return round(base * 1.50, 2)
    if "MS1" in label or "MS2" in label or "MSX" in label:
        return round(base * 1.45, 2)
    return round(base * 1.40, 2)


def top10_market_adaylari(t, filtreler=None, tum_guvenler=False):
    """
    Top 10 için gerçek multi-market aday havuzu.
    Sadece MS'e kilitlenmez; MS / Alt-Üst / KG / İlk Yarı / Kombo marketlerini aynı havuza alır.
    Market türüne göre keyfi bonus vermez; Value/Edge yalnızca gerçek MS oranı varsa hafif sinyal olur.
    """
    filtreler = st.session_state if filtreler is None else filtreler
    adaylar = []

    def safe_int(v, default=0):
        try:
            return int(round(float(v or 0)))
        except Exception:
            return default

    def infer_tip(label):
        label = str(label or "")
        if label.startswith("MS") or label == "Beraberlik":
            return "MS"
        if "KG" in label:
            return "KG"
        if "Üst" in label or "Alt" in label or "2.5" in label or "1.5" in label or "3.5" in label:
            return "Alt/Üst"
        if "İY" in label:
            return "İlk Yarı"
        if "HT/FT" in label:
            return "HT/FT"
        if "+" in label:
            return "Kombo"
        return "Market"

    def add(label, guven, tip=None, oran=None, bonus=0, min_guven=50):
        label = str(label or "").strip()
        if label == "İY 0.5 Üst":
            return
        guven = safe_int(guven)
        if not label or label in ["Belirsiz Maç", "Tahmin Zayıf", "None", "-"]:
            return
        if guven < min_guven and not tum_guvenler:
            return
        tip = tip or infer_tip(label)

        # Top 10 Market sayfasındaki market aç/kapat filtreleri.
        # Ana maç analizi tarafını etkilemez; sadece Top 10 aday havuzunu filtreler.
        if not filtreler.get("top10_filter_ms", True) and tip == "MS":
            return
        if not filtreler.get("top10_filter_25", True) and (tip == "Alt/Üst" or "2.5" in label):
            return
        if not filtreler.get("top10_filter_kg", True) and tip == "KG":
            return
        if not filtreler.get("top10_filter_iy15", True) and label in ("İY 1.5 Üst", "İY KG Var", "İY KG Yok"):
            return
        if not filtreler.get("top10_filter_combo", True) and tip in ["Kombo", "HT/FT"]:
            return

        # İlk yarı marketleri daha volatil olduğu için Top 10/Top 50'ye kontrollü girsin.
        if label == "İY 0.5 Üst":
            if guven < 70:
                return
            if safe_int(t.get("ornek", 0)) < 5:
                return
            if str(t.get("goal_profile", "")) == "Düşük Gollü":
                return

        if label in ("İY 1.5 Üst", "İY KG Var"):
            if guven < 55:
                return
            if safe_int(t.get("ornek", 0)) < 5:
                return
            if str(t.get("goal_profile", "")) == "Düşük Gollü" and label == "İY 1.5 Üst":
                return

        # Aynı label tekrar eklenirse en yüksek güvenli olanı tut.
        for a in adaylar:
            if a["label"] == label and a["tip"] == tip:
                if guven + bonus > a["guven"] + a["bonus"]:
                    a.update({"guven": guven, "oran": oran, "bonus": bonus})
                return

        adaylar.append({
            "label": label,
            "guven": guven,
            "tip": tip,
            "oran": oran,
            "bonus": bonus,
        })

    # Ana tahmin hangi market olursa olsun havuza girsin.
    ana_label = t.get("ana_label")
    ana_tip = infer_tip(ana_label)
    ana_bonus = 0  # Tüm marketler eşit: market türüne göre bonus/ceza yok.
    add(ana_label, t.get("ana_p", 0), ana_tip, t.get("ana_odd"), bonus=ana_bonus, min_guven=50)

    # Alternatif/uyumlu tahmin havuza girsin.
    alt_label = t.get("alt_label")
    alt_tip = infer_tip(alt_label)
    alt_bonus = 0  # Tüm marketler eşit: alternatif market bonusu yok.
    add(alt_label, t.get("alt_p", 0), alt_tip, None, bonus=alt_bonus, min_guven=50)

    # MS marketleri: diğer marketlerle aynı skor kuralları uygulanır.
    add("MS 1", t.get("ms1_p", 0), "MS", t.get("odds_h"), bonus=0, min_guven=52)
    add("Beraberlik", t.get("msx_p", 0), "MS", t.get("odds_d"), bonus=0, min_guven=52)
    add("MS 2", t.get("ms2_p", 0), "MS", t.get("odds_a"), bonus=0, min_guven=52)

    # Alt / Üst marketleri: market türüne özel bonus yok.
    add("2.5 Üst", t.get("ms25_p", 0), "Alt/Üst", None, bonus=0, min_guven=50)
    add("2.5 Alt", t.get("ms25a_p", 0), "Alt/Üst", None, bonus=0, min_guven=50)
    add("3.5 Üst", t.get("ms35_p", 0), "Alt/Üst", None, bonus=0, min_guven=54)

    # KG marketleri: market türüne özel bonus yok.
    add("KG Var", t.get("kg_var_p", t.get("kg_p", 0)), "KG", None, bonus=0, min_guven=50)
    add("KG Yok", t.get("kg_yok_p", 0), "KG", None, bonus=0, min_guven=50)

    # İlk yarı marketleri: market türüne özel skor bonusu yok.
    # Mevcut minimum güven/örnek kalite kontrolleri korunur.
    add("İY 0.5 Üst", t.get("iy05_p", 0), "İlk Yarı", None, bonus=0, min_guven=70)
    add("İY 1.5 Üst", t.get("iy15_p", 0), "İlk Yarı", None, bonus=0, min_guven=55)
    add("İY KG Var", t.get("iykg_var_p", 0), "İlk Yarı", None, bonus=0, min_guven=55)

    # Kombo.
    if t.get("combo_var") and t.get("combo_label"):
        combo_label_txt = str(t.get("combo_label", ""))
        # Top 10 / Top 50 listesinde HT/FT ana öneri gibi öne çıkmasın.
        # HT/FT detay ekranında görünmeye devam eder; liste önerisi MS / Alt-Üst / KG ağırlıklı kalır.
        if not combo_label_txt.startswith("HT/FT"):
            add(
                t.get("combo_label"),
                t.get("combo_p", 0),
                "Kombo",
                kombo_tahmini_oran(t.get("combo_label"), t.get("ana_odd")),
                bonus=0,
                min_guven=48,
            )

    # HT/FT tek başına Top 10 / Top 50 adayı yapılmaz.
    # Sebep: küçük örneklemde agresif öne çıkıp MS / 2.5 / KG marketlerinin önüne geçebiliyor.
    return adaylar



def mac_key(m):
    """Aynı maç + aynı market tekrarını engellemek için güvenli maç anahtarı."""
    try:
        if not isinstance(m, dict):
            try:
                m = m.to_dict()
            except Exception:
                m = {}

        zaman = m.get("zaman") or m.get("zaman_iso") or ""
        if hasattr(zaman, "strftime"):
            zaman = zaman.strftime("%Y-%m-%d %H:%M")
        else:
            zaman = str(zaman)

        return f"{m.get('ev', '')}|{m.get('dep', '')}|{zaman}"
    except Exception:
        return str(m)


TAHMIN_LOG_PATH = APP_DATA_DIR / "vibe_tahmin_sonuclari.json"


def _json_guvenli_deger(value):
    if isinstance(value, dict):
        return {str(k): _json_guvenli_deger(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_guvenli_deger(v) for v in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_guvenli_deger(value.item())
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def detay_snapshot_olustur(m, t, benzerler):
    """Sonuç detayını ana ekrandan bağımsız açmak için kompakt analiz kopyası."""
    gerekli = [
        "Date", "HomeTeam", "AwayTeam", "HTHG", "HTAG", "FTHG", "FTAG", "HTR", "FTR",
        "B365H", "B365D", "B365A", "REF_H", "REF_D", "REF_A",
    ]
    try:
        b = benzerler if isinstance(benzerler, pd.DataFrame) else pd.DataFrame()
        kolonlar = [c for c in gerekli if c in b.columns]
        b_records = json.loads(b[kolonlar].head(50).to_json(orient="records", date_format="iso")) if kolonlar else []
    except Exception:
        b_records = []
    return {
        "m": _json_guvenli_deger(dict(m)),
        "t": _json_guvenli_deger(dict(t)),
        "b": b_records,
    }


def tahmin_kaydi_mac_anahtari(kayit):
    """Marketten bağımsız tek maç anahtarı üretir."""
    match_id = str(kayit.get("match_id", "") or "").strip()
    if match_id:
        return match_id
    kayit_id = str(kayit.get("kayit_id", "") or "").strip()
    if kayit_id:
        return kayit_id
    zaman = str(kayit.get("zaman", ""))[:16]
    return "|".join([
        takim_adi_norm(kayit.get("ev", "")),
        takim_adi_norm(kayit.get("dep", "")),
        zaman,
    ])


def _tahmin_kaydi_sirasi(kayit):
    """Birleşik puan, güven, örnek sayısı ve son olarak dar hassasiyet."""
    try:
        guven = float(kayit.get("guven", 0) or 0)
    except Exception:
        guven = 0.0
    try:
        puan = float(kayit.get("ana_puan", 0) or 0)
    except Exception:
        puan = 0.0
    if puan <= 0:
        puan = guven
    try:
        ornek = int(kayit.get("ornek", 0) or 0)
    except Exception:
        ornek = 0
    try:
        hassasiyet = float(kayit.get("hassasiyet", 99) if kayit.get("hassasiyet") is not None else 99)
    except Exception:
        hassasiyet = 99.0
    return puan, guven, ornek, -hassasiyet


def _tahmin_market_ailesi(label):
    l = str(label or "").strip()
    if l in {"KG Var", "KG Yok"}:
        return "kg"
    if l in {"2.5 Üst", "2.5 Alt"}:
        return "ou25"
    if l in {"MS 1", "MS1", "Beraberlik", "MS X", "MSX", "MS 2", "MS2"}:
        return "ms"
    return l


def _en_iyi_alternatif(ana_label, kayitlar):
    """Aynı maçın kayıtlarından farklı market ailesindeki en güçlü %60+ alternatifi bulur."""
    adaylar = []
    for kayit in kayitlar or []:
        for etiket_alani, guven_alani, oran_alani in [
            ("tahmin", "guven", "oran"),
            ("alternatif_tahmin", "alternatif_guven", "alternatif_oran"),
        ]:
            etiket = str(kayit.get(etiket_alani, "") or "").strip()
            try:
                guven = float(kayit.get(guven_alani, 0) or 0)
            except Exception:
                guven = 0.0
            if (
                not etiket
                or etiket == "İY 0.5 Üst"
                or etiket == str(ana_label)
                or _tahmin_market_ailesi(etiket) == _tahmin_market_ailesi(ana_label)
                or guven <= 60
            ):
                continue
            adaylar.append((guven, etiket, kayit.get(oran_alani)))
    if not adaylar:
        return "", 0, None
    guven, etiket, oran = max(adaylar, key=lambda x: x[0])
    return etiket, int(round(guven)), oran


def tahmin_kayitlarini_tekillestir(kayitlar):
    """Eski/yeni kayıtlarda aynı maçtan yalnızca en güçlü resmî tahmini tutar."""
    gruplar = {}
    for kayit in kayitlar or []:
        if not isinstance(kayit, dict):
            continue
        anahtar = tahmin_kaydi_mac_anahtari(kayit)
        if not anahtar:
            continue
        gruplar.setdefault(anahtar, []).append(kayit)

    sonuc = []
    for anahtar, grup in gruplar.items():
        secilen = dict(max(grup, key=_tahmin_kaydi_sirasi))
        alt_etiket, alt_guven, alt_oran = _en_iyi_alternatif(secilen.get("tahmin"), grup)
        secilen["alternatif_tahmin"] = alt_etiket
        secilen["alternatif_guven"] = alt_guven
        secilen["alternatif_oran"] = alt_oran
        # Aynı maçın eski satırlarından biri tamamlandıysa skoru resmî tahmine taşı.
        tamamlanan = next((x for x in grup if x.get("durum") == "Tamamlandı" and x.get("ev_gol") is not None and x.get("dep_gol") is not None), None)
        if tamamlanan:
            ev_gol, dep_gol = int(tamamlanan["ev_gol"]), int(tamamlanan["dep_gol"])
            iy_ev, iy_dep = tamamlanan.get("iy_ev_gol"), tamamlanan.get("iy_dep_gol")
            tuttu = skor_tahmini_tuttu_mu(secilen.get("tahmin"), ev_gol, dep_gol, iy_ev, iy_dep)
            alternatif_tuttu = skor_tahmini_tuttu_mu(
                secilen.get("alternatif_tahmin"), ev_gol, dep_gol, iy_ev, iy_dep
            )
            secilen.update({
                "durum": "Tamamlandı" if tuttu is not None else "Bekliyor", "ev_gol": ev_gol, "dep_gol": dep_gol,
                "iy_ev_gol": iy_ev, "iy_dep_gol": iy_dep,
                "tuttu": bool(tuttu) if tuttu is not None else None,
                "alternatif_tuttu": bool(alternatif_tuttu) if alternatif_tuttu is not None else None,
                "sonuc_guncelleme": tamamlanan.get("sonuc_guncelleme"),
            })
        secilen["kayit_id"] = anahtar
        sonuc.append(secilen)
    return sonuc


def tahmin_logunu_oku():
    try:
        return tahmin_kayitlarini_tekillestir(kayit_deposu().read("tahminler", TAHMIN_LOG_PATH))
    except (OSError, ValueError, sqlite3.Error) as error:
        kayit_hatasi("Tahmin geçmişi okunamadı", error)
        return []


def tahmin_logunu_yaz(kayitlar):
    return kayitlari_degistir("tahminler", lambda _: kayitlar, TAHMIN_LOG_PATH)


def sonuc_takibini_sifirla():
    """Yalnızca Sonuç Takibi kayıtlarını temizler; API anahtarları ve kupon geçmişi korunur."""
    return tahmin_logunu_yaz([])


def tahmin_loguna_baglam_yaz(m, label, baglam):
    if not isinstance(baglam, dict) or not mac_baslamadi_mi(m.get("zaman")):
        return False
    target = str(m.get("match_id") or mac_key(m))
    def update(records):
        for record in records:
            if tahmin_kaydi_mac_anahtari(record) != target or record.get("tahmin") != label:
                continue
            if record.get("durum") == "Tamamlandı" or not mac_baslamadi_mi(record.get("zaman")):
                continue
            record.update(baglam_ayari=float(baglam.get("toplam", 0)), baglam_kaynak=str(baglam.get("kaynak", "")),
                          baglam_snapshot=_json_guvenli_deger(baglam), baglam_kaydedildi=kayit_zamani_iso())
        return records
    return kayitlari_degistir("tahminler", update, TAHMIN_LOG_PATH)


def analiz_tahminlerini_kaydet(final):
    """Maç öncesi tahmini atomik kaydeder; başlangıçtan sonra bütün tahmin alanları kilitlidir."""
    def update(kayitlar):
        kayitlar = tahmin_kayitlarini_tekillestir(kayitlar)
        mevcut = {tahmin_kaydi_mac_anahtari(x): x for x in kayitlar}
        for item in final:
            m, t = item.get("m", {}), item.get("t", {})
            label = str(t.get("ana_label", "")).strip()
            if not label or label in ["Belirsiz Maç", "Tahmin Zayıf", "İY 0.5 Üst"]:
                continue
            if not mac_baslamadi_mi(m.get("zaman")):
                continue
            zaman = m.get("zaman")
            zaman_iso = zaman.isoformat() if hasattr(zaman, "isoformat") else str(zaman)
            mac_anahtari = str(m.get("match_id") or mac_key(m))
            eski = mevcut.get(mac_anahtari, {})
            if eski.get("durum") == "Tamamlandı":
                continue
            aday = {
                "kayit_id": mac_anahtari,
                "match_id": str(m.get("match_id", "")),
                **oran_kayit_bilgisi(m), "sport_key": str(m.get("sport_key", "")),
                "lig": str(m.get("lig", "")),
                "zaman": zaman_iso,
                "ev": str(m.get("ev", "")),
                "dep": str(m.get("dep", "")),
                "h": float(m.get("h")) if m.get("h") is not None else None,
                "b": float(m.get("b")) if m.get("b") is not None else None,
                "a": float(m.get("a")) if m.get("a") is not None else None,
                "tahmin": label,
                "guven": int(t.get("ana_p", 0)),
                "alternatif_tahmin": str(t.get("alt_label", "") or ""),
                "alternatif_guven": int(t.get("alt_p", 0) or 0),
                "alternatif_ornek": int(t.get("alt_ornek", 0) or 0),
                "alternatif_puan": float(t.get("alt_puan", 0) or 0),
                "alternatif_kararlilik": int(t.get("alt_kararlilik", 0) or 0),
                "alternatif_hassasiyetler": list(t.get("alt_hassasiyetler", []) or []),
                "ornek": int(t.get("ornek", 0) or 0),
                "ana_ornek_medyan": int(t.get("birlesik_ornek_medyan", t.get("ornek", 0)) or 0),
                "ana_puan": float(t.get("birlesik_puan", t.get("score", 0)) or 0),
                "ana_kararlilik": int(t.get("stability_count", 0) or 0),
                "ana_hassasiyetler": list(t.get("stability_tols", []) or []),
                "hassasiyet": float(t.get("kullanilan_tolerans", 0) or 0),
                "oran": float(t.get("ana_odd")) if t.get("ana_odd") is not None else None,
                "alternatif_oran": (
                    float(market_label_to_odd(m, t.get("alt_label")))
                    if t.get("alt_label") and market_label_to_odd(m, t.get("alt_label")) is not None
                    else None
                ),
                "kaydedildi": kayit_zamani_iso(),
                "ilk_kayit_zamani": eski.get("ilk_kayit_zamani", eski.get("kaydedildi", kayit_zamani_iso())),
                "model_version": MODEL_VERSION,
                "durum": eski.get("durum", "Bekliyor"),
                "ev_gol": eski.get("ev_gol"),
                "dep_gol": eski.get("dep_gol"),
                "iy_ev_gol": eski.get("iy_ev_gol"), "iy_dep_gol": eski.get("iy_dep_gol"),
                "tuttu": eski.get("tuttu"),
                "alternatif_tuttu": eski.get("alternatif_tuttu"),
                "sonuc_guncelleme": eski.get("sonuc_guncelleme"),
                "detay_snapshot": detay_snapshot_olustur(m, t, item.get("b")),
            }
            if not eski or _tahmin_kaydi_sirasi(aday) > _tahmin_kaydi_sirasi(eski):
                aday["degisiklikler"] = list(eski.get("degisiklikler", []))
                if eski:
                    aday["degisiklikler"].append({"tahmin": eski.get("tahmin"), "guven": eski.get("guven"), "kaydedildi": eski.get("kaydedildi")})
                    aday["degisiklikler"] = aday["degisiklikler"][-20:]
                secilen = aday
            else:
                secilen = dict(eski)
            alt_etiket, alt_guven, alt_oran = _en_iyi_alternatif(
                secilen.get("tahmin"), [eski, aday]
            )
            secilen["alternatif_tahmin"] = alt_etiket
            secilen["alternatif_guven"] = alt_guven
            secilen["alternatif_oran"] = alt_oran
            mevcut[mac_anahtari] = secilen
        return tahmin_kayitlarini_tekillestir(list(mevcut.values()))
    return kayitlari_degistir("tahminler", update, TAHMIN_LOG_PATH)


def skor_tahmini_tuttu_mu(label, ev_gol, dep_gol, iy_ev_gol=None, iy_dep_gol=None):
    def side(home, away):
        if home is None or away is None or pd.isna(home) or pd.isna(away):
            return None
        return "H" if float(home) > float(away) else "A" if float(home) < float(away) else "D"
    return tahmin_tuttu_mu(label, {"FTHG": ev_gol, "FTAG": dep_gol,
                                  "HTHG": iy_ev_gol, "HTAG": iy_dep_gol,
                                  "FTR": side(ev_gol, dep_gol), "HTR": side(iy_ev_gol, iy_dep_gol)})


def takim_anahtari(ad):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(ad)).encode("ascii", "ignore").decode().lower())


def sonuc_skoru_dogrula(home, away, half_home=None, half_away=None):
    def goal(value):
        try:
            number = float(value)
            return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
        except (TypeError, ValueError):
            return None
    h, a = goal(home), goal(away)
    if h is None or a is None:
        return None
    hh, ha = goal(half_home), goal(half_away)
    if hh is None or ha is None or hh > h or ha > a:
        hh = ha = None
    return {"ev_gol": h, "dep_gol": a, "iy_ev_gol": hh, "iy_dep_gol": ha}


def gecmisten_sonuc_skoru(history, record):
    kickoff = parse_mac_datetime(record.get("zaman"))
    required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "league_code"}
    code = ODDS_TO_HISTORY.get(str(record.get("sport_key", "")))
    if kickoff is None or history is None or history.empty or not code or not required.issubset(history.columns):
        return None
    frame = history.loc[(tarih_serisi_oku(history["Date"]).dt.date == kickoff.date())
                        & history["league_code"].eq(code)]
    if frame.empty:
        return None
    # Sonuç yazarken yalnızca tam/alias eşleşme; benzer isim tahmini kullanılmaz.
    frame = frame.loc[frame["HomeTeam"].map(takim_adi_norm).eq(takim_adi_norm(record.get("ev")))
                      & frame["AwayTeam"].map(takim_adi_norm).eq(takim_adi_norm(record.get("dep")))]
    if len(frame) != 1:
        return None
    row = frame.iloc[0]
    return sonuc_skoru_dogrula(row.get("FTHG"), row.get("FTAG"), row.get("HTHG"), row.get("HTAG"))


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def api_tarih_skorlari(api_key, day):
    if not api_key:
        return [], ""
    try:
        response = requests.get("https://v3.football.api-sports.io/fixtures",
                                headers={"x-apisports-key": api_key},
                                params={"date": str(day), "timezone": "Europe/Istanbul"}, timeout=15)
        if response.status_code != 200:
            return [], f"İlk yarı skor servisi HTTP {response.status_code}"
        data = response.json()
        if data.get("errors"):
            return [], "İlk yarı skor servisi bu sorguyu tamamlayamadı."
        return data.get("response", []) or [], ""
    except (requests.RequestException, ValueError, TypeError):
        return [], "İlk yarı skor servisine ulaşılamadı."


def fixture_sonuc_skoru(fixtures, record):
    kickoff = parse_mac_datetime(record.get("zaman"))
    candidates = []
    for fixture in fixtures:
        meta, teams = fixture.get("fixture", {}), fixture.get("teams", {})
        status = (meta.get("status") or {}).get("short")
        date = parse_mac_datetime(meta.get("date"))
        if (status not in ("FT", "AET", "PEN") or kickoff is None or date is None
            or abs((kickoff-date).total_seconds()) > 900):
            continue
        if (takim_adi_norm((teams.get("home") or {}).get("name")) != takim_adi_norm(record.get("ev"))
            or takim_adi_norm((teams.get("away") or {}).get("name")) != takim_adi_norm(record.get("dep"))):
            continue
        score = fixture.get("score") or {}
        full = score.get("fulltime") or (fixture.get("goals", {}) if status == "FT" else {})
        half = score.get("halftime") or {}
        verified = sonuc_skoru_dogrula(full.get("home"), full.get("away"), half.get("home"), half.get("away"))
        if verified:
            candidates.append(verified)
    return candidates[0] if len(candidates) == 1 else None


def tahmin_sonuclarini_guncelle(api_key):
    records = tahmin_logunu_oku()
    pending = [record for record in records if record.get("durum") != "Tamamlandı"
               or (record.get("alternatif_tahmin") and record.get("alternatif_tuttu") is None)]
    leagues = sorted({record.get("sport_key") for record in pending if record.get("sport_key")})
    scores, errors = [], []
    for league in leagues:
        try:
            response = requests.get(f"https://api.the-odds-api.com/v4/sports/{league}/scores/",
                                    params={"apiKey": api_key, "daysFrom": 3, "dateFormat": "iso"}, timeout=15)
            if response.status_code != 200:
                errors.append(f"{league}: Skor servisi HTTP {response.status_code}")
                continue
            payload = response.json()
            if not isinstance(payload, list):
                errors.append(f"{league}: Geçersiz skor yanıtı")
                continue
            scores.extend(payload)
        except (requests.RequestException, ValueError):
            errors.append(f"{league}: Skor servisine ulaşılamadı")
    id_map = {str(match["id"]): match for match in scores if match.get("id")}
    history = _gecmis_cache_yukle()
    football_key = get_api_football_key()
    by_day, results = {}, {}
    missing_half = 0
    for record in pending:
        kickoff = parse_mac_datetime(record.get("zaman"))
        if kickoff is None or kickoff >= tr_simdi():
            continue
        match = id_map.get(str(record.get("match_id", "")))
        if match is not None and match.get("sport_key") != record.get("sport_key"):
            match = None
        if match is None:
            candidates = []
            for candidate in scores:
                date = parse_mac_datetime(candidate.get("commence_time"))
                if (date is not None and abs((kickoff-date).total_seconds()) <= 900
                    and candidate.get("sport_key") == record.get("sport_key")
                    and takim_anahtari(candidate.get("home_team")) == takim_anahtari(record.get("ev"))
                    and takim_anahtari(candidate.get("away_team")) == takim_anahtari(record.get("dep"))):
                    candidates.append(candidate)
            match = candidates[0] if len(candidates) == 1 else None
        result = sonuc_skoru_dogrula(record.get("ev_gol"), record.get("dep_gol"),
                                     record.get("iy_ev_gol"), record.get("iy_dep_gol"))
        if match and match.get("completed") and match.get("scores"):
            values = {takim_anahtari(value.get("name")): value.get("score") for value in match["scores"]}
            result = sonuc_skoru_dogrula(values.get(takim_anahtari(record.get("ev"))),
                                        values.get(takim_anahtari(record.get("dep")))) or result
        labels = [record.get("tahmin", ""), record.get("alternatif_tahmin", "")]
        needs_half = any(str(label).startswith(("İY ", "HT/FT")) for label in labels)
        if result is None or (needs_half and result.get("iy_ev_gol") is None):
            historical = gecmisten_sonuc_skoru(history, record)
            if historical is not None:
                # Kaynakların normal süre skorları uyuşmuyorsa ilk yarıyı birleştirme.
                if result is None or (historical["ev_gol"], historical["dep_gol"]) == (result["ev_gol"], result["dep_gol"]):
                    result = historical
        if football_key and (result is None or (needs_half and result.get("iy_ev_gol") is None)):
            day = kickoff.date().isoformat()
            if day not in by_day:
                by_day[day], error = api_tarih_skorlari(football_key, day)
                if error:
                    errors.append(error)
            verified = fixture_sonuc_skoru(by_day[day], record)
            if verified is not None:
                result = verified
        if result is not None:
            results[tahmin_kaydi_mac_anahtari(record)] = result
            if needs_half and result.get("iy_ev_gol") is None:
                missing_half += 1
    updated = []
    def update(current):
        for record in current:
            key = tahmin_kaydi_mac_anahtari(record)
            if key not in results:
                continue
            score = results[key]
            args = (score["ev_gol"], score["dep_gol"], score["iy_ev_gol"], score["iy_dep_gol"])
            hit = skor_tahmini_tuttu_mu(record.get("tahmin"), *args)
            alt_hit = skor_tahmini_tuttu_mu(record.get("alternatif_tahmin"), *args)
            previous = (record.get("tuttu"), record.get("alternatif_tuttu"), record.get("durum"))
            record.update(score)
            record.update(durum="Tamamlandı" if hit is not None else "Bekliyor",
                          tuttu=bool(hit) if hit is not None else None,
                          alternatif_tuttu=bool(alt_hit) if alt_hit is not None else None,
                          sonuc_eksik="İlk yarı skoru bekleniyor" if hit is None else "",
                          sonuc_guncelleme=kayit_zamani_iso())
            if previous != (record["tuttu"], record["alternatif_tuttu"], record["durum"]):
                updated.append(key)
        return current
    if results and not kayitlari_degistir("tahminler", update, TAHMIN_LOG_PATH):
        return 0, "Sonuçlar kaydedilemedi. Önceki kayıtlar korundu."
    if missing_half:
        errors.append(f"{missing_half} maçın ilk yarı skoru henüz bulunamadı; ilgili tahminler bekliyor. Geçmiş veriyi yenileyebilir veya API-Football anahtarı ekleyebilirsin.")
    return len(updated), " · ".join(dict.fromkeys(errors)) or None


def tahmini_mac_dakikasi(baslangic, simdi=None):
    """Başlangıç saatinden yaklaşık futbol dakikası üretir; API gerçek dakika sağlamaz."""
    simdi = simdi or (tr_simdi())
    gecen = max(0, int((simdi - baslangic).total_seconds() // 60))
    if gecen <= 50:
        return min(gecen, 45), f"~{min(gecen, 45)}'"
    if gecen <= 65:
        return 45, "Devre arası (~)"
    dakika = min(90, max(46, gecen - 15))
    return dakika, f"~{dakika}'"


def canli_tahmin_durumu(label, ev_gol, dep_gol, dakika):
    """Yalnızca skor ve tahmini dakikadan ihtiyatlı canlı durum üretir."""
    label = str(label or "").replace("MS1", "MS 1").replace("MS2", "MS 2").replace("MSX", "Beraberlik").replace("MS X", "Beraberlik")
    if "+" in label:
        parcalar = [x.strip() for x in label.split("+")]
        durumlar = [canli_tahmin_durumu(x, ev_gol, dep_gol, dakika) for x in parcalar]
        if any(x[0] == "zayif" for x in durumlar):
            return "zayif", "Kombinasyonun en az bir ayağı canlı skorla zayıfladı."
        if all(x[0] == "guclu" for x in durumlar):
            return "guclu", "Kombinasyonun bütün ayakları canlı skorla destekleniyor."
        return "bekle", "Kombinasyon için skor ve dakika henüz yeterli değil."

    toplam = int(ev_gol) + int(dep_gol)
    if label == "2.5 Üst":
        if toplam >= 3:
            return "guclu", "2.5 Üst tahmini şimdiden gerçekleşti."
        if (dakika <= 35 and toplam >= 1) or (dakika <= 60 and toplam >= 2):
            return "guclu", "Gol temposu 2.5 Üst tahminini destekliyor."
        if dakika >= 70 and toplam <= 1:
            return "zayif", "Kalan süreye göre gol sayısı düşük kaldı."
    elif label == "2.5 Alt":
        if toplam >= 3:
            return "zayif", "2.5 Alt tahmini artık gerçekleşemez."
        if dakika >= 65 and toplam <= 1:
            return "guclu", "Düşük skor 2.5 Alt tahminini destekliyor."
        if dakika <= 35 and toplam >= 2:
            return "zayif", "Erken gol temposu 2.5 Alt için olumsuz."
    elif label == "KG Var":
        if ev_gol > 0 and dep_gol > 0:
            return "guclu", "KG Var tahmini şimdiden gerçekleşti."
        if dakika >= 72:
            return "zayif", "Takımlardan biri henüz gol atamadı ve süre azalıyor."
        if dakika <= 35 and toplam >= 1:
            return "guclu", "Erken gol KG Var ihtimalini destekliyor."
    elif label == "KG Yok":
        if ev_gol > 0 and dep_gol > 0:
            return "zayif", "KG Yok tahmini artık gerçekleşemez."
        if dakika >= 70:
            return "guclu", "Takımlardan birinin golsüz kalması KG Yok'u destekliyor."
    elif label == "MS 1":
        if dakika >= 55 and ev_gol > dep_gol:
            return "guclu", "Ev sahibi önde; MS 1 tahmini destekleniyor."
        if dakika >= 55 and ev_gol < dep_gol:
            return "zayif", "Ev sahibi geride; MS 1 tahmini zayıfladı."
    elif label == "MS 2":
        if dakika >= 55 and dep_gol > ev_gol:
            return "guclu", "Deplasman önde; MS 2 tahmini destekleniyor."
        if dakika >= 55 and dep_gol < ev_gol:
            return "zayif", "Deplasman geride; MS 2 tahmini zayıfladı."
    elif label == "Beraberlik":
        if dakika >= 68 and ev_gol == dep_gol:
            return "guclu", "Skor eşit; beraberlik tahmini destekleniyor."
        if dakika >= 75 and abs(ev_gol - dep_gol) >= 2:
            return "zayif", "Skor farkı ve kalan süre beraberlik için olumsuz."
    return "bekle", "Skor ve dakika henüz net bir canlı sinyal üretmiyor."


def canli_analizleri_getir(api_key):
    """Kaydedilmiş maç önü analizlerini güncel canlı skorlarla eşleştirir."""
    kayitlar = tahmin_logunu_oku()
    bekleyen = [x for x in kayitlar if x.get("durum") != "Tamamlandı"]
    ligler = sorted({x.get("sport_key") for x in bekleyen if x.get("sport_key")})
    if not api_key:
        return [], "Canlı skorları yenilemek için API key gerekli."
    skorlar, hatalar = [], []
    for lig in ligler:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{lig}/scores/",
                params={"apiKey": api_key, "daysFrom": 1, "dateFormat": "iso"},
                timeout=15,
            )
            if r.status_code == 200 and isinstance(r.json(), list):
                skorlar.extend(r.json())
            else:
                hatalar.append(f"{lig}: HTTP {r.status_code}")
        except Exception as exc:
            hatalar.append(f"{lig}: {exc}")

    simdi = tr_simdi()
    canlilar = []
    for kayit in bekleyen:
        eslesen = next((s for s in skorlar if str(s.get("id", "")) == str(kayit.get("match_id", "")) and s.get("id")), None)
        if eslesen is None:
            eslesen = next((s for s in skorlar if takim_anahtari(s.get("home_team")) == takim_anahtari(kayit.get("ev")) and takim_anahtari(s.get("away_team")) == takim_anahtari(kayit.get("dep"))), None)
        if not eslesen or eslesen.get("completed"):
            continue
        try:
            baslangic = datetime.fromisoformat(str(eslesen.get("commence_time", "")).replace("Z", "+00:00")).replace(tzinfo=None) + timedelta(hours=3)
        except Exception:
            baslangic = parse_mac_datetime(kayit.get("zaman"))
        if baslangic is None or simdi < baslangic or simdi > baslangic + timedelta(hours=3):
            continue
        puanlar = {takim_anahtari(x.get("name")): int(x.get("score", 0)) for x in (eslesen.get("scores") or [])}
        try:
            ev_gol = puanlar[takim_anahtari(kayit.get("ev"))]
            dep_gol = puanlar[takim_anahtari(kayit.get("dep"))]
        except (KeyError, TypeError, ValueError):
            continue
        dakika, dakika_yazi = tahmini_mac_dakikasi(baslangic, simdi)
        durum, aciklama = canli_tahmin_durumu(kayit.get("tahmin"), ev_gol, dep_gol, dakika)
        canlilar.append({**kayit, "ev_gol": ev_gol, "dep_gol": dep_gol, "dakika": dakika, "dakika_yazi": dakika_yazi, "canli_durum": durum, "canli_aciklama": aciklama})
    return sorted(canlilar, key=lambda x: (x.get("canli_durum") == "guclu", x.get("guven", 0)), reverse=True), "; ".join(hatalar[:3]) or None


def kupon_marketi_uygun(label):
    """Kuponda yalnızca MS, 2.5 Alt/Üst, KG ve bunların kombinasyonlarına izin ver."""
    parcalar = [x.strip() for x in str(label or "").split("+")]
    izinli = {
        "MS 1", "MS1", "Beraberlik", "MS X", "MSX", "MS 2", "MS2",
        "2.5 Üst", "2.5 Alt", "KG Var", "KG Yok",
    }
    return bool(parcalar) and all(parca in izinli for parca in parcalar)


def gunun_en_iyi_10_uret(gecmis_df, bulten_df, min_ornek=1, limit=10,
                         sadece_ayni_lig=False, kupon_modu=False,
                         kupon_profili=None, tum_marketler=False,
                         market_gecmis_kayitlari=None, filtreler=None, taramalar=None):
    if gecmis_df is None or bulten_df is None or gecmis_df.empty or bulten_df.empty:
        return []
    adaylar = []
    for _, m in bulten_df.iterrows():
        scan = taramalar.get(mac_key(m.to_dict())) if taramalar is not None else None
        havuz = birlesik_market_havuzu(gecmis_df, m, min_ornek, sadece_ayni_lig,
                                      market_gecmis_kayitlari, ek_marketler=True,
                                      filtreler=filtreler, taramalar=scan)
        for candidate in havuz:
            if kupon_modu and not kupon_marketi_uygun(candidate["label"]):
                continue
            if kupon_modu and kupon_profili == "Yüksek Oran" and "+" not in candidate["label"]:
                continue
            if kupon_modu and kupon_profili == "Temkinli" and "+" in candidate["label"]:
                continue
            t, b = birlesik_tahmin_olustur(candidate, havuz, m)
            mk = dict(candidate["temsilci"]["mk"])
            label = candidate["label"]
            tip = mk.get("tip") or ("MS" if _tahmin_market_ailesi(label) == "ms" else "KG" if "KG" in label else "Alt/Üst")
            tols = [float(value) for value in candidate["toleranslar"]]
            mk.update(label=label, tip=tip, guven=t["ana_p"], oran=t["ana_odd"])
            t.update(top10_market_label=label, top10_market_tip=tip, top10_market_guven=t["ana_p"],
                     top10_market_oran=t["ana_odd"], top10_market_oran_tahmini=False,
                     top10_hassasiyetler=tols, top10_hassasiyet_sayisi=len(tols),
                     top10_stabilite_skoru=t["score"], top10_stabilite_orani=t["stability_pct"], hassasiyet_taramali=True)
            match = m.to_dict()
            match["durum"] = mac_canli_durumu(match.get("zaman"))
            adaylar.append({"m": match, "t": t, "b": b,
                            "top10_tol": t["kullanilan_tolerans"], "top10_skor": t["score"], "top10_market": mk,
                            "top10_hassasiyetler": tols, "top10_hassasiyet_sayisi": len(tols),
                            "top10_stabilite_skoru": t["score"], "top10_stabilite_orani": t["stability_pct"]})
            if not tum_marketler:
                break
    if tum_marketler:
        adaylar.sort(key=lambda item: (item["t"]["score"], item["t"]["ana_p"], item["t"]["stability_count"]), reverse=True)
        return adaylar[:int(limit)] if limit and int(limit) > 0 else adaylar
    return top50_liste_sec(adaylar, limit=limit)


def tahmin_tuttu_mu(label, row):
    label = str(label or "").strip()
    label = {"MS1": "MS 1", "MSX": "Beraberlik", "MS2": "MS 2", "MS X": "Beraberlik"}.get(label, label)
    if "+" in label:
        results = [tahmin_tuttu_mu(part.strip(), row) for part in label.split("+")]
        return None if any(result is None for result in results) else all(results)
    if label in ("1/2", "2/1"):
        label = "HT/FT " + label
    if label in ("İki yarıda da KG", "İki yarı 1.5 Üst", "İki Yarı 1.5 Üst Evet"):
        keys = ("FTHG", "FTAG", "HTHG", "HTAG")
        if any(row.get(key) is None or pd.isna(row.get(key)) for key in keys):
            return None
        h, a, hh, ha = (float(row[key]) for key in keys)
        if label == "İki yarıda da KG":
            return hh > 0 and ha > 0 and h-hh > 0 and a-ha > 0
        return hh + ha >= 2 and h + a - hh - ha >= 2
    if label.startswith("HT/FT "):
        if pd.isna(row.get("HTR")) or pd.isna(row.get("FTR")):
            return None
        translate = {"H": "1", "D": "X", "A": "2"}
        return f'{translate.get(row["HTR"], "?")}/{translate.get(row["FTR"], "?")}' == label[6:]
    if label in ("İY KG Var", "İY KG Yok"):
        hh, ha = row.get("HTHG"), row.get("HTAG")
        if hh is None or ha is None or pd.isna(hh) or pd.isna(ha):
            return None
        var = float(hh) > 0 and float(ha) > 0
        return var if label == "İY KG Var" else not var
    half = label.startswith("İY ")
    home, away = row.get("HTHG" if half else "FTHG"), row.get("HTAG" if half else "FTAG")
    if home is None or away is None or pd.isna(home) or pd.isna(away):
        return None
    home, away = float(home), float(away)
    known = {"MS 1": home > away, "Beraberlik": home == away, "MS 2": home < away,
             "KG Var": home > 0 and away > 0, "KG Yok": home == 0 or away == 0}
    if label in known:
        return known[label]
    match = re.fullmatch(r"(?:İY )?(0\.5|1\.5|2\.5|3\.5) (Üst|Alt)", label)
    if match:
        line = float(match.group(1))
        return home + away > line if match.group(2) == "Üst" else home + away < line
    return None


def backtest_calistir(gecmis_df, test_sezonu, tolerans, min_ornek,
                      sadece_ayni_lig=False, lig_kodlari=None, max_test=500,
                      birlesik_hassasiyet=False, top50_model=False,
                      filtreler=None, _taramalar=None):
    if gecmis_df is None or gecmis_df.empty:
        return pd.DataFrame()
    veri, test = backtest_verisini_hazirla(gecmis_df, test_sezonu, lig_kodlari, max_test)
    sonuclar = []
    for _, day in test.groupby("Date", sort=True):
        # Kalibrasyon gün başında sabitlenir. Gün içindeki satır sırası sonucu etkilemez.
        prior = sabit_kalibrasyon_kayitlari()
        candidates = []
        for _, row in day.iterrows():
            target = backtest_hedefi(row)
            if target is None:
                continue
            key = mac_key(target)
            scan = _taramalar.get(key) if _taramalar is not None else None
            if top50_model:
                items = gunun_en_iyi_10_uret(veri, pd.DataFrame([target]), min_ornek, limit=1,
                    sadece_ayni_lig=sadece_ayni_lig, market_gecmis_kayitlari=prior,
                    filtreler=filtreler, taramalar={key: scan} if scan is not None else None)
                if not items:
                    continue
                item = items[0]
                t, b = item["t"], item["b"]
            elif birlesik_hassasiyet:
                t, b = hassasiyet_birlesik_hesapla(veri, target, min_ornek, sadece_ayni_lig,
                                                 market_gecmis_kayitlari=prior, taramalar=scan)
            elif scan is not None and round(float(tolerans), 2) in scan:
                t, b = scan[round(float(tolerans), 2)]
            else:
                t, b = hesapla(veri, target, tolerans, sadece_ayni_lig=sadece_ayni_lig,
                               form_aktif=False, kalibrasyon_aktif=False)
            if t is None or len(b) < int(min_ornek):
                continue
            record = backtest_kaydi(row, target, t)
            if record is not None:
                candidates.append({"m": target, "t": t, "record": record})
        selected = top50_liste_sec(candidates, limit=50) if top50_model else candidates
        sonuclar.extend(item["record"] for item in selected)
    result = pd.DataFrame(sonuclar)
    if not result.empty:
        result = result.sort_values(["Tarih", "Lig", "Maç"], kind="stable").reset_index(drop=True)
    result.attrs.update(model_version=MODEL_VERSION, model="Top 50 Market" if top50_model else "Birleşik" if birlesik_hassasiyet else "Tekli")
    return result



def _backtest_uzlasi_ozeti(tolerans_sonuclari):
    """11 tekil hassasiyetin aynı maçta aynı ana tahminde birleşmesini ölçer.

    Not: Tekil backtest yalnızca güveni %60 üstü tahminleri döndürdüğü için bu analiz
    'oynanabilir tahmin uzlaşısı'nı ölçer. Bir hassasiyette oynanabilir tahmin yoksa
    11 üzerinden uzlaşı sayısına katkı yapmaz.
    """
    kayitlar = []
    for tol, bt in tolerans_sonuclari.items():
        if bt is None or bt.empty:
            continue
        x = bt.copy()
        x["_tol"] = float(tol)
        kayitlar.append(x)
    if not kayitlar:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    tum = pd.concat(kayitlar, ignore_index=True)
    anahtar = ["Tarih", "Lig", "Maç"]
    detay = []
    for key, g in tum.groupby(anahtar, dropna=False):
        labels = g["Tahmin"].fillna("").astype(str).str.strip()
        labels = labels[labels.ne("")]
        if labels.empty:
            continue
        sayim = labels.value_counts()
        ana_label = str(sayim.index[0])
        uzlasi = int(sayim.iloc[0])

        # 0.05–0.10 bandında aynı ana label kaç kez çıktı? (maksimum 6)
        yuksek = g[(g["_tol"] >= 0.05) & (g["_tol"] <= 0.10)].copy()
        yuksek_labels = yuksek["Tahmin"].fillna("").astype(str).str.strip()
        yuksek_uzlasi = int((yuksek_labels == ana_label).sum()) if not yuksek.empty else 0

        temsil = g[g["Tahmin"].astype(str) == ana_label].copy()
        if temsil.empty:
            continue
        temsil = temsil.sort_values(["Güven", "Örnek"], ascending=[False, False]).iloc[0]
        tuttu = bool(temsil["Tuttu"])
        oran = pd.to_numeric(pd.Series([temsil.get("Oran")]), errors="coerce").iloc[0]
        kar = ((float(oran) - 1.0) * 100.0 if tuttu else -100.0) if pd.notna(oran) else None

        detay.append({
            "Tarih": key[0], "Lig": key[1], "Maç": key[2],
            "Uzlaşı Tahmini": ana_label,
            "Uzlaşı": uzlasi,
            "Yüksek Bant Uzlaşı": yuksek_uzlasi,
            "Tuttu": tuttu,
            "Oran": float(oran) if pd.notna(oran) else None,
            "Kâr (100 TL)": kar,
        })
    if not detay:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    d = pd.DataFrame(detay)
    def grup(n):
        if n == 11: return "11/11"
        if n >= 9: return "9–10/11"
        if n >= 7: return "7–8/11"
        if n >= 5: return "5–6/11"
        if n >= 3: return "3–4/11"
        return "1–2/11"
    d["Uzlaşı Grubu"] = d["Uzlaşı"].apply(grup)

    rows = []
    sira = ["11/11", "9–10/11", "7–8/11", "5–6/11", "3–4/11", "1–2/11"]
    for grp in sira:
        z = d[d["Uzlaşı Grubu"] == grp]
        if z.empty:
            continue
        ms = z[z["Kâr (100 TL)"].notna()]
        roi = float(ms["Kâr (100 TL)"].sum()) / (len(ms) * 100.0) * 100.0 if len(ms) else None
        rows.append({
            "Uzlaşı": grp,
            "Tahmin": int(len(z)),
            "Kazanan": int(z["Tuttu"].sum()),
            "Başarı %": round(float(z["Tuttu"].mean() * 100.0), 1),
            "MS Tahmin": int(len(ms)),
            "MS ROI %": round(roi, 1) if roi is not None else None,
        })
    ozet = pd.DataFrame(rows)

    # Detay tablolarını ayrı DataFrame olarak döndür. Streamlit session_state
    # pandas .attrs bilgisini her rerun/serileştirmede güvenilir biçimde korumayabildiği
    # için detay tabloları attrs yerine ayrı session_state anahtarlarında tutulur.
    # 1) 11/11 -> 1/11 tek tek uzlaşı performansı
    tek_rows = []
    for n in range(11, 0, -1):
        z = d[d["Uzlaşı"] == n]
        if z.empty:
            continue
        ms = z[z["Kâr (100 TL)"].notna()]
        roi = float(ms["Kâr (100 TL)"].sum()) / (len(ms) * 100.0) * 100.0 if len(ms) else None
        tek_rows.append({
            "Uzlaşı": f"{n}/11",
            "Tahmin": int(len(z)),
            "Kazanan": int(z["Tuttu"].sum()),
            "Başarı %": round(float(z["Tuttu"].mean() * 100.0), 1),
            "MS Tahmin": int(len(ms)),
            "MS ROI %": round(roi, 1) if roi is not None else None,
        })
    tek_df = pd.DataFrame(tek_rows)

    # 2) Tahmin türü x uzlaşı: hangi market/tahmin hangi uzlaşı seviyesinde güçlü?
    capraz_rows = []
    for (label, n), z in d.groupby(["Uzlaşı Tahmini", "Uzlaşı"], dropna=False):
        if z.empty:
            continue
        ms = z[z["Kâr (100 TL)"].notna()]
        roi = float(ms["Kâr (100 TL)"].sum()) / (len(ms) * 100.0) * 100.0 if len(ms) else None
        capraz_rows.append({
            "Tahmin": str(label),
            "Uzlaşı": f"{int(n)}/11",
            "Örnek": int(len(z)),
            "Kazanan": int(z["Tuttu"].sum()),
            "Başarı %": round(float(z["Tuttu"].mean() * 100.0), 1),
            "MS Tahmin": int(len(ms)),
            "MS ROI %": round(roi, 1) if roi is not None else None,
        })
    capraz_df = pd.DataFrame(capraz_rows)
    if not capraz_df.empty:
        capraz_df["_uz"] = capraz_df["Uzlaşı"].str.extract(r"(\d+)")[0].astype(int)
        capraz_df = capraz_df.sort_values(["_uz", "Örnek", "Başarı %"], ascending=[False, False, False]).drop(columns=["_uz"])

    return ozet, tek_df, capraz_df


def backtest_11_hassasiyet_calistir(gecmis_df, test_sezonu, secili_tolerans, min_ornek,
                                    sadece_ayni_lig=False, lig_kodlari=None, max_test=500,
                                    top50_model=False, filtreler=None):
    if gecmis_df is None or gecmis_df.empty:
        return tuple(pd.DataFrame() for _ in range(5))
    veri, test = backtest_verisini_hazirla(gecmis_df, test_sezonu, lig_kodlari, max_test)
    tolerances = [round(i / 100, 2) for i in range(11)]
    records = {tolerance: [] for tolerance in tolerances}
    selected_records = []
    for _, day in test.groupby("Date", sort=True):
        prior = sabit_kalibrasyon_kayitlari()
        daily = []
        for _, row in day.iterrows():
            target = backtest_hedefi(row)
            if target is None:
                continue
            # Keep only the current match's eleven samples, not 2000 x 11 DataFrames.
            scan = hassasiyet_taramasi(veri, tarama_hedefi(target), sadece_ayni_lig)
            for tolerance in tolerances:
                t, examples = scan.get(tolerance, (None, pd.DataFrame()))
                if t is None or len(examples) < int(min_ornek):
                    continue
                record = backtest_kaydi(row, target, t)
                if record is not None:
                    records[tolerance].append(record)
            if top50_model:
                items = gunun_en_iyi_10_uret(veri, pd.DataFrame([target]), min_ornek, limit=1,
                    sadece_ayni_lig=sadece_ayni_lig, market_gecmis_kayitlari=prior,
                    filtreler=filtreler, taramalar={mac_key(target): scan})
                t = items[0]["t"] if items else None
            else:
                t, _ = hassasiyet_birlesik_hesapla(veri, target, min_ornek, sadece_ayni_lig,
                                                 market_gecmis_kayitlari=prior, taramalar=scan)
            if t is not None:
                record = backtest_kaydi(row, target, t)
                if record is not None:
                    daily.append({"m": target, "t": t, "record": record})
        chosen = top50_liste_sec(daily, 50) if top50_model else daily
        selected_records.extend(item["record"] for item in chosen)
    per_tolerance, summary = {}, []
    for tolerance in tolerances:
        result = pd.DataFrame(records[tolerance])
        per_tolerance[tolerance] = result
        ms = result[result["Kâr (100 TL)"].notna()] if not result.empty else result
        summary.append({"Hassasiyet": f"{tolerance:.2f}", "Tahmin": len(result),
                        "Başarı %": round(result["Tuttu"].mean() * 100, 1) if not result.empty else None,
                        "MS Tahmin": len(ms), "MS ROI %": round(ms["Kâr (100 TL)"].sum() / len(ms), 1) if not ms.empty else None})
    consensus, individual, cross = _backtest_uzlasi_ozeti(per_tolerance)
    selected = pd.DataFrame(selected_records)
    if not selected.empty:
        selected = selected.sort_values(["Tarih", "Lig", "Maç"], kind="stable").reset_index(drop=True)
    selected.attrs.update(model_version=MODEL_VERSION, model="Top 50 Market" if top50_model else "Birleşik")
    return pd.DataFrame(summary), selected, consensus, individual, cross

def gecmis_ornek_teshisi(gecmis_df, m_row, tolerans, sadece_ayni_lig=False):
    """Geçmiş örnek filtresinin hangi aşamada sıfıra düştüğünü gösterir.

    Yalnızca tanılama amaçlıdır; modelin eşleşme, hassasiyet veya tahmin
    mantığını değiştirmez.
    """
    sonuc = {
        "toplam": 0, "lig_sonrasi": 0, "evre_sonrasi": 0,
        "tarih_sonrasi": 0, "eslesen": 0, "history_code": None,
        "odds_phase": None, "phase_used": None, "target": None,
        "nearest": None, "min_tolerance": None,
    }
    if gecmis_df is None:
        return sonuc

    try:
        sonuc["toplam"] = int(len(gecmis_df))
        sport_key = str(m_row.get("sport_key", "")) if hasattr(m_row, "get") else ""
        sonuc["history_code"] = ODDS_TO_HISTORY.get(sport_key)
        sonuc["odds_phase"] = oran_fazi(m_row)
        sonuc["target"] = tuple(float(m_row.get(k)) for k in ("h", "b", "a"))

        lig_df = ayni_lig_gecmisi(gecmis_df, m_row, sadece_ayni_lig)
        sonuc["lig_sonrasi"] = int(len(lig_df))

        evre_df = zaman_uyumlu_gecmis(lig_df, m_row)
        sonuc["evre_sonrasi"] = int(len(evre_df))
        sonuc["phase_used"] = evre_df.attrs.get("odds_phase_used") if hasattr(evre_df, "attrs") else None

        tarih_df = tarih_oncesi_gecmis(evre_df, m_row.get("zaman"))
        sonuc["tarih_sonrasi"] = int(len(tarih_df))
        if tarih_df.empty:
            return sonuc

        mask = oran_eslesme_maskesi(tarih_df, m_row, tolerans)
        sonuc["eslesen"] = int(mask.sum())

        values, target = eslesme_oranlari(tarih_df, m_row)
        farklar = values.sub(target, axis=1).abs()
        max_fark = farklar.max(axis=1)
        max_fark = pd.to_numeric(max_fark, errors="coerce").dropna()
        if max_fark.empty:
            return sonuc

        idx = max_fark.idxmin()
        row = tarih_df.loc[idx]
        nearest_values = values.loc[idx]
        nearest_diffs = farklar.loc[idx]
        sonuc["min_tolerance"] = float(max_fark.loc[idx])
        sonuc["nearest"] = {
            "date": row.get("Date"),
            "home": row.get("HomeTeam", ""),
            "away": row.get("AwayTeam", ""),
            "odds": tuple(float(nearest_values[c]) for c in ("REF_H", "REF_D", "REF_A")),
            "diffs": tuple(float(nearest_diffs[c]) for c in ("REF_H", "REF_D", "REF_A")),
        }
    except (KeyError, TypeError, ValueError, IndexError):
        pass
    return sonuc


def gecmis_ornekleri_bul(gecmis_df, m_row, tolerans, sadece_ayni_lig=False,
                         filtre_12=False, filtre_21=False, filtre_cift_yari_kg=False,
                         filtre_cift_yari_15=False, limit=25):
    """Bir güncel maç için benzer oranlı geçmiş maçları ve özel senaryoları getirir."""
    kaynak = zaman_uyumlu_gecmis(ayni_lig_gecmisi(gecmis_df, m_row, sadece_ayni_lig), m_row)
    kaynak = tarih_oncesi_gecmis(kaynak, m_row.get("zaman"))
    if kaynak.empty:
        return pd.DataFrame()

    b = kaynak.loc[oran_eslesme_maskesi(kaynak, m_row, tolerans)].copy()
    gerekli = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "FTR", "HTR"]
    if b.empty or any(c not in b.columns for c in gerekli):
        return pd.DataFrame()
    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")
    b = b.dropna(subset=gerekli + ["REF_H", "REF_D", "REF_A"])

    b["olay_12"] = (b["HTR"] == "H") & (b["FTR"] == "A")
    b["olay_21"] = (b["HTR"] == "A") & (b["FTR"] == "H")
    ev_ikinci_yari = b["FTHG"] - b["HTHG"]
    dep_ikinci_yari = b["FTAG"] - b["HTAG"]
    b["olay_cift_yari_kg"] = (
        (b["HTHG"] > 0) & (b["HTAG"] > 0)
        & (ev_ikinci_yari > 0) & (dep_ikinci_yari > 0)
    )
    ilk_yari_gol = b["HTHG"] + b["HTAG"]
    ikinci_yari_gol = ev_ikinci_yari + dep_ikinci_yari
    b["olay_cift_yari_15"] = (ilk_yari_gol >= 2) & (ikinci_yari_gol >= 2)

    secili_maskeler = []
    if filtre_12:
        secili_maskeler.append(b["olay_12"])
    if filtre_21:
        secili_maskeler.append(b["olay_21"])
    if filtre_cift_yari_kg:
        secili_maskeler.append(b["olay_cift_yari_kg"])
    if filtre_cift_yari_15:
        secili_maskeler.append(b["olay_cift_yari_15"])
    if secili_maskeler:
        maske = secili_maskeler[0].copy()
        for ek_maske in secili_maskeler[1:]:
            maske = maske | ek_maske
        b = b[maske]

    if b.empty:
        return b
    b["Olay"] = b.apply(
        lambda r: " · ".join(
            x for x, ok in [
                ("1/2", r["olay_12"]),
                ("2/1", r["olay_21"]),
                ("İki yarıda da KG", r["olay_cift_yari_kg"]),
                ("İki yarı 1.5 Üst", r["olay_cift_yari_15"]),
            ] if bool(ok)
        ) or "—",
        axis=1,
    )
    return b.sort_values("Date", ascending=False).head(int(limit))



def gecmis_ornek_siralama_anahtari(item):
    """Geçmiş Örnekleri: en yüksek İY/MS/2.5/KG yüzdesi önce, eşitse örnek sayısı fazla olan önce."""
    ornekler = item.get("ornekler") if isinstance(item, dict) else None
    if ornekler is None or getattr(ornekler, "empty", True):
        return (0, 0.0, 0.0, 0)

    toplam_ornek = int(len(ornekler))
    if toplam_ornek <= 0:
        return (0, 0.0, 0.0, 0)

    yuzdeler = []

    def en_yuksek_yuzde(series):
        try:
            vc = series.value_counts(dropna=True)
            if vc.empty:
                return 0.0
            return float(vc.iloc[0]) / float(toplam_ornek) * 100.0
        except Exception:
            return 0.0

    try:
        iy = ornekler["HTR"].replace({"H": "1", "D": "X", "A": "2"})
        yuzdeler.append(en_yuksek_yuzde(iy))
    except Exception:
        pass

    try:
        ms = ornekler["FTR"].replace({"H": "1", "D": "X", "A": "2"})
        yuzdeler.append(en_yuksek_yuzde(ms))
    except Exception:
        pass

    try:
        alt_ust = ((ornekler["FTHG"] + ornekler["FTAG"]) >= 3).map({True: "Üst", False: "Alt"})
        yuzdeler.append(en_yuksek_yuzde(alt_ust))
    except Exception:
        pass

    try:
        kg = ((ornekler["FTHG"] > 0) & (ornekler["FTAG"] > 0)).map({True: "Var", False: "Yok"})
        yuzdeler.append(en_yuksek_yuzde(kg))
    except Exception:
        pass

    en_yuksek_pct = max(yuzdeler) if yuzdeler else 0.0

    # Örnek sayısı bonusu: yüksek örnekli maç, yüzdesi birkaç puan daha düşük olsa
    # bile sıralamada yukarı çıkabilsin. Bonus 25 örnekte +8 puanda tavan yapar.
    # 5 ve altı örnekte bonus verilmez; arası doğrusal artar.
    if toplam_ornek <= 5:
        ornek_bonusu = 0.0
    elif toplam_ornek >= 25:
        ornek_bonusu = 8.0
    else:
        ornek_bonusu = (toplam_ornek - 5) * (8.0 / 20.0)

    guc_puani = en_yuksek_pct + ornek_bonusu

    # Sıralama katmanı:
    # - 0.00 hassasiyette 1 örnek normal şekilde yüzde/güç puanına göre sıralanır.
    # - 0.01+ hassasiyette yalnızca 1 örnekli maçlar, tüm 2+ örnekli maçların
    #   altında; 0 örnekli maçların ise hemen üstünde tutulur.
    try:
        aktif_hassasiyet = float(st.session_state.get("top_tol", 0.0) or 0.0)
    except Exception:
        aktif_hassasiyet = 0.0

    if toplam_ornek == 1 and abs(aktif_hassasiyet) >= 1e-9:
        siralama_katmani = 1
    else:
        siralama_katmani = 2

    # Önce katman; sonra güç puanı, ham yüzde ve örnek sayısı.
    return (siralama_katmani, guc_puani, en_yuksek_pct, toplam_ornek)



def gecmis_ornek_ozeti(ornekler):
    """İY/MS/2.5/KG için en sık sonucu ve yüzdesini döndürür."""
    if ornekler is None or getattr(ornekler, "empty", True):
        return {
            "iy": ("—", 0, 0.0),
            "ms": ("—", 0, 0.0),
            "ou25": ("—", 0, 0.0),
            "kg": ("—", 0, 0.0),
        }

    toplam = max(1, int(len(ornekler)))

    def en_sik(series):
        try:
            vc = series.value_counts(dropna=True)
            if vc.empty:
                return ("—", 0, 0.0)
            sonuc = str(vc.index[0])
            adet = int(vc.iloc[0])
            yuzde = adet / toplam * 100.0
            return (sonuc, adet, yuzde)
        except Exception:
            return ("—", 0, 0.0)

    try:
        # İY: en sık ilk yarı sonucu (1/X/2), skor değil.
        iy = ornekler["HTR"].replace({"H": "1", "D": "X", "A": "2"})
    except Exception:
        iy = pd.Series(dtype="object")

    try:
        # MS: en sık maç sonucu (1/X/2), skor değil.
        ms = ornekler["FTR"].replace({"H": "1", "D": "X", "A": "2"})
    except Exception:
        ms = pd.Series(dtype="object")

    try:
        ou25 = ((ornekler["FTHG"] + ornekler["FTAG"]) >= 3).map({True: "Üst", False: "Alt"})
    except Exception:
        ou25 = pd.Series(dtype="object")

    try:
        kg = ((ornekler["FTHG"] > 0) & (ornekler["FTAG"] > 0)).map({True: "Var", False: "Yok"})
    except Exception:
        kg = pd.Series(dtype="object")

    return {
        "iy": en_sik(iy),
        "ms": en_sik(ms),
        "ou25": en_sik(ou25),
        "kg": en_sik(kg),
    }

def gecmis_tablo_stili(tablo):
    """Geçmiş sonuç tablolarını maç sonucu ve market tipine göre renklendirir."""
    def skor_renk(value):
        try:
            ev, dep = [int(x) for x in str(value).split("-", 1)]
        except (TypeError, ValueError):
            return ""
        if ev > dep:
            return "background-color:#166534;color:#f0fdf4;font-weight:800"
        if ev < dep:
            return "background-color:#991b1b;color:#fff1f2;font-weight:800"
        return "background-color:#854d0e;color:#fefce8;font-weight:800"

    def alt_ust_renk(value):
        if str(value) == "Üst":
            return "background-color:#166534;color:#f0fdf4;font-weight:800"
        if str(value) == "Alt":
            return "background-color:#9a3412;color:#fff7ed;font-weight:800"
        return ""

    def kg_renk(value):
        if str(value) == "Var":
            return "background-color:#075985;color:#f0f9ff;font-weight:800"
        if str(value) == "Yok":
            return "background-color:#374151;color:#f9fafb;font-weight:800"
        return ""

    def evet_hayir_renk(value):
        if str(value) == "Evet":
            return "background-color:#6b21a8;color:#faf5ff;font-weight:900"
        if str(value) == "Hayır":
            return "background-color:#991b1b;color:#fef2f2;font-weight:900"
        return ""

    def kombo_evet_hayir_renk(value):
        # Kombo Evet sonucu belirgin; Hayır ise nötr ve geri planda kalsın.
        # Bu tonlar MS / KG / 2.5 / özel olay renkleriyle çakışmaz.
        if str(value) == "Evet":
            return "background-color:#0f766e;color:#f0fdfa;font-weight:900"  # belirgin teal
        if str(value) == "Hayır":
            return "background-color:#27272a;color:#a1a1aa;font-weight:700"  # nötr koyu füme
        return ""

    def olay_renk(value):
        metin = str(value)
        if "İki yarıda da KG" in metin:
            return "background-color:#6b21a8;color:#faf5ff;font-weight:900"
        if "İki yarı 1.5 Üst" in metin:
            # İki yarı 1.5 Üst için diğer yüksek-oran olaylarından net ayrılan cyan ton.
            return "background-color:#0e7490;color:#ecfeff;font-weight:900"
        if "1/2" in metin:
            return "background-color:#9f1239;color:#fff1f2;font-weight:900"
        if "2/1" in metin:
            return "background-color:#1d4ed8;color:#eff6ff;font-weight:900"
        return "color:#94a3b8"

    stil = tablo.style
    skor_kolonlari = [c for c in ["İY", "MS"] if c in tablo.columns]
    if skor_kolonlari:
        stil = stil.map(skor_renk, subset=skor_kolonlari)
    if "2.5" in tablo.columns:
        stil = stil.map(alt_ust_renk, subset=["2.5"])
    if "KG" in tablo.columns:
        stil = stil.map(kg_renk, subset=["KG"])
    if "İki yarı 1.5 Üst" in tablo.columns:
        stil = stil.map(evet_hayir_renk, subset=["İki yarı 1.5 Üst"])

    # Oran Filtresi'ndeki ikili kombo sütunlarının Evet/Hayır sonuçlarını da renklendir.
    kombo_kolonlari = [
        c for c in tablo.columns
        if str(c) in {"MS+KG", "MS+2.5", "KG+2.5", "Kombo"}
        or str(c).startswith("MS+KG")
        or str(c).startswith("MS+2.5")
        or str(c).startswith("KG+2.5")
    ]
    if kombo_kolonlari:
        stil = stil.map(kombo_evet_hayir_renk, subset=kombo_kolonlari)

    olay_kolonlari = [c for c in ["Özel olay", "Yüksek oran olayı"] if c in tablo.columns]
    if olay_kolonlari:
        stil = stil.map(olay_renk, subset=olay_kolonlari)
    return stil


def yuksek_oran_istatistikleri(tum_ornekler, filtre_12=True, filtre_21=True,
                               filtre_cift_yari_kg=True, filtre_cift_yari_15=True):
    """Nadir senaryoları örnek büyüklüğünü de dikkate alarak sıralar."""
    toplam = len(tum_ornekler)
    tanimlar = [
        ("1/2", "olay_12", filtre_12),
        ("2/1", "olay_21", filtre_21),
        ("İki yarıda da KG", "olay_cift_yari_kg", filtre_cift_yari_kg),
        ("İki yarı 1.5 Üst", "olay_cift_yari_15", filtre_cift_yari_15),
    ]
    istatistikler = []
    for label, kolon, aktif in tanimlar:
        if not aktif or toplam == 0 or kolon not in tum_ornekler.columns:
            continue
        hit = int(tum_ornekler[kolon].sum())
        ham_oran = hit / toplam
        # Laplace düzeltmesi tek/az örnekli sonuçların gereksiz yükselmesini önler.
        duzeltilmis = (hit + 1) / (toplam + 2)
        ornek_guveni = min(toplam / 30.0, 1.0)
        denenebilirlik = duzeltilmis * 100 * (0.65 + 0.35 * ornek_guveni)
        istatistikler.append({
            "label": label,
            "hit": hit,
            "toplam": toplam,
            "oran": round(ham_oran * 100, 1),
            "puan": round(denenebilirlik, 1),
        })

    istatistikler.sort(key=lambda x: (x["puan"], x["hit"]), reverse=True)
    if not istatistikler:
        return [], {"label": "—", "hit": 0, "toplam": toplam, "oran": 0.0, "puan": 0.0}, "PAS"

    en_iyi = istatistikler[0]
    if toplam >= 20 and en_iyi["hit"] >= 5 and en_iyi["oran"] >= 10:
        oneri = "GÜÇLÜ DENENEBİLİR"
    elif toplam >= 12 and en_iyi["hit"] >= 3 and en_iyi["oran"] >= 6:
        oneri = "DENENEBİLİR"
    elif en_iyi["hit"] >= 2:
        oneri = "RİSKLİ DENEME"
    else:
        oneri = "PAS"
    return istatistikler, en_iyi, oneri


def oran_filtresi_istatistikleri(tum_ornekler, goster_ms=True, goster_kg=True,
                                 goster_25=True, goster_cift_yari_15=True):
    """Benzer oranlı geçmiş maçlardan temel market yüzdelerini çıkarır.

    Gösterilen marketler:
    - Maç Sonucu: 1 / X / 2
    - Karşılıklı Gol: Var / Yok
    - 2.5 Gol: Üst / Alt
    - İki Yarı 1.5 Üst: ilk yarı >=2 VE ikinci yarı >=2 gol
    """
    if tum_ornekler is None or getattr(tum_ornekler, "empty", True):
        return [], {"label": "—", "oran": 0.0, "hit": 0, "toplam": 0, "puan": 0.0}

    b = tum_ornekler.copy()
    toplam = int(len(b))
    if toplam <= 0:
        return [], {"label": "—", "oran": 0.0, "hit": 0, "toplam": 0, "puan": 0.0}

    for c in ["FTHG", "FTAG", "HTHG", "HTAG"]:
        if c in b.columns:
            b[c] = pd.to_numeric(b[c], errors="coerce")

    tanimlar = []
    if goster_ms and "FTR" in b.columns:
        tanimlar.extend([
            ("MS 1", b["FTR"] == "H", "MS"),
            ("MS X", b["FTR"] == "D", "MS"),
            ("MS 2", b["FTR"] == "A", "MS"),
        ])

    if goster_kg and all(c in b.columns for c in ["FTHG", "FTAG"]):
        kg_var = (b["FTHG"] > 0) & (b["FTAG"] > 0)
        tanimlar.extend([
            ("KG Var", kg_var, "KG"),
            ("KG Yok", ~kg_var, "KG"),
        ])

    if goster_25 and all(c in b.columns for c in ["FTHG", "FTAG"]):
        toplam_gol = b["FTHG"] + b["FTAG"]
        ust25 = toplam_gol >= 3
        tanimlar.extend([
            ("2.5 Üst", ust25, "2.5"),
            ("2.5 Alt", ~ust25, "2.5"),
        ])

    if goster_cift_yari_15 and all(c in b.columns for c in ["FTHG", "FTAG", "HTHG", "HTAG"]):
        ilk_yari_gol = b["HTHG"] + b["HTAG"]
        ikinci_yari_gol = (b["FTHG"] - b["HTHG"]) + (b["FTAG"] - b["HTAG"])
        iki_yari_15 = (ilk_yari_gol >= 2) & (ikinci_yari_gol >= 2)
        # Bu market yalnızca Evet oranı en az %50 ise görünür.
        # "Hayır" istatistiği başlıkta/detayda hiç gösterilmez.
        tanimlar.append(("İki Yarı 1.5 Üst Evet", iki_yari_15, "Yarılar"))

    istatistikler = []
    for label, mask, grup in tanimlar:
        try:
            hit = int(pd.Series(mask).fillna(False).astype(bool).sum())
        except Exception:
            hit = 0
        oran = (hit / toplam * 100.0) if toplam else 0.0
        # İki Yarı 1.5 Üst sadece Evet >= %50 olduğunda görünür.
        if grup == "Yarılar" and oran < 50.0:
            continue
        # Yüzde ana sinyal; örnek sayısı yalnızca sıralamada küçük güven katkısı verir.
        ornek_guveni = min(toplam / 30.0, 1.0)
        puan = oran * (0.82 + 0.18 * ornek_guveni)
        istatistikler.append({
            "label": label,
            "grup": grup,
            "hit": hit,
            "toplam": toplam,
            "oran": round(oran, 1),
            "puan": round(puan, 1),
        })

    istatistikler.sort(key=lambda x: (x["puan"], x["hit"]), reverse=True)
    en_iyi = istatistikler[0] if istatistikler else {"label": "—", "oran": 0.0, "hit": 0, "toplam": toplam, "puan": 0.0}
    return istatistikler, en_iyi


for key, default in [
    ("final_list", []),
    ("detay_idx", None),
    ("detay_item", None),
    ("detay_gecmis_acik", False),
    ("top10_list", []),
    ("top50_list", []),
    ("filtre", "tumu"),
    ("kupona", []),
    ("coupon_popup_open", False),
    ("scroll_to_coupon", False),
    ("last_gecmis_df", None),
    ("last_bulten_df", None),
    ("backtest_df", None),
    ("backtest_11_df", None),
    ("backtest_uzlasi_df", None),
    ("backtest_tek_uzlasi_df", None),
    ("backtest_tahmin_uzlasi_df", None),
    ("gecmis_inceleme_list", None),
    ("gecmis_tam_ekran_sira", None),
    ("yuksek_oran_list", None),
    ("oran_filtresi_list", None),
    ("odds_league_cache", {}),
    ("odds_api_quota", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

FUTBOL_LIGLERI = {
    "ULUSLARARASI": {
        "Dünya Kupası": "soccer_fifa_world_cup",
    },
    "AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league",
    },
    "TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
        "1. Lig": "auto_turkey_1_lig",
    },
    "İNGİLTERE": {
        "Premier League": "soccer_epl",
        "Championship": "soccer_efl_champ",
        "League 1": "soccer_england_league1",
        "League 2": "soccer_england_league2",
        "FA Cup": "soccer_fa_cup",
        "EFL Cup": "soccer_england_efl_cup",
    },
    "İSPANYA": {
        "La Liga": "soccer_spain_la_liga",
        "La Liga 2": "soccer_spain_segunda_division",
        "Copa del Rey": "soccer_spain_copa_del_rey",
    },
    "ALMANYA": {
        "Bundesliga": "soccer_germany_bundesliga",
        "Bundesliga 2": "soccer_germany_bundesliga2",
        "DFB-Pokal": "soccer_germany_dfb_pokal",
    },
    "İTALYA": {
        "Serie A": "soccer_italy_serie_a",
        "Serie B": "soccer_italy_serie_b",
        "Coppa Italia": "soccer_italy_coppa_italia",
    },
    "FRANSA": {
        "Ligue 1": "soccer_france_ligue_one",
        "Ligue 2": "soccer_france_ligue_two",
        "Coupe de France": "soccer_france_coupe_de_france",
    },
    "AVRUPA VALUE": {
        "Hollanda": "soccer_netherlands_eredivisie",
        "Belçika": "soccer_belgium_first_div",
        "Portekiz": "soccer_portugal_primeira_liga",
        "İskoçya": "soccer_spl",
        "Danimarka": "soccer_denmark_superliga",
        "Avusturya": "soccer_austria_bundesliga",
        "İsviçre": "soccer_switzerland_superleague",
        "İsveç": "soccer_sweden_allsvenskan",
        "Norveç": "soccer_norway_eliteserien",
        "Polonya": "soccer_poland_ekstraklasa",
        "Finlandiya": "soccer_finland_veikkausliiga",
        "İrlanda": "soccer_league_of_ireland",
        "Yunanistan": "soccer_greece_super_league",
        "Rusya Premier League": "soccer_russia_premier_league",
    },
    "DÜNYA VALUE": {
        "MLS": "soccer_usa_mls",
        "Brezilya Serie A": "soccer_brazil_campeonato",
        "Arjantin Primera": "soccer_argentina_primera_division",
        "Japonya J League": "soccer_japan_j_league",
        "Meksika Liga MX": "soccer_mexico_ligamx",
        "Güney Kore K League 1": "soccer_korea_kleague1",
        "Çin Süper Ligi": "soccer_china_superleague",
        "Suudi Pro League": "soccer_saudi_arabia_pro_league",
        "Şili Primera": "soccer_chile_campeonato",
    },
}


# The Odds API -> football-data.co.uk kod eşlemesi. Eşlemesi olmayan liglerde
# "sadece aynı lig" seçeneği bilinçli olarak sonuç üretmez.
ODDS_TO_HISTORY = {
    "soccer_turkey_super_league": "T1",
    "soccer_epl": "E0",
    "soccer_efl_champ": "E1",
    "soccer_england_league1": "E2",
    "soccer_england_league2": "E3",
    "soccer_spain_la_liga": "SP1",
    "soccer_spain_segunda_division": "SP2",
    "soccer_germany_bundesliga": "D1",
    "soccer_germany_bundesliga2": "D2",
    "soccer_italy_serie_a": "I1",
    "soccer_italy_serie_b": "I2",
    "soccer_france_ligue_one": "F1",
    "soccer_france_ligue_two": "F2",
    "soccer_netherlands_eredivisie": "N1",
    "soccer_belgium_first_div": "B1",
    "soccer_portugal_primeira_liga": "P1",
    "soccer_spl": "SC0",
    "soccer_greece_super_league": "G1",
    "soccer_denmark_superliga": "DNK",
    "soccer_austria_bundesliga": "AUT",
    "soccer_switzerland_superleague": "SWZ",
    "soccer_sweden_allsvenskan": "SWE",
    "soccer_norway_eliteserien": "NOR",
    "soccer_poland_ekstraklasa": "POL",
    "soccer_finland_veikkausliiga": "FIN",
    "soccer_league_of_ireland": "IRL",
    "soccer_russia_premier_league": "RUS",
    "soccer_usa_mls": "USA",
    "soccer_brazil_campeonato": "BRA",
    "soccer_argentina_primera_division": "ARG",
    "soccer_japan_j_league": "JPN",
    "soccer_mexico_ligamx": "MEX",
    "soccer_china_superleague": "CHN",
}

LEAGUE_EMOJIS = {
    "Dünya Kupası": "🌍",
    "Şampiyonlar Ligi": "🏆",
    "Avrupa Ligi": "🟠",
    "Konferans Ligi": "🟢",
    "Süper Lig": "🇹🇷",
    "1. Lig": "🇹🇷",
    "Premier League": "🏴",
    "Championship": "🏴",
    "League 1": "🏴",
    "League 2": "🏴",
    "FA Cup": "🏴",
    "EFL Cup": "🏴",
    "La Liga": "🇪🇸",
    "La Liga 2": "🇪🇸",
    "Copa del Rey": "🇪🇸",
    "Bundesliga": "🇩🇪",
    "Bundesliga 2": "🇩🇪",
    "DFB-Pokal": "🇩🇪",
    "Serie A": "🇮🇹",
    "Serie B": "🇮🇹",
    "Coppa Italia": "🇮🇹",
    "Ligue 1": "🇫🇷",
    "Ligue 2": "🇫🇷",
    "Coupe de France": "🇫🇷",
    "Hollanda": "🇳🇱",
    "Belçika": "🇧🇪",
    "Portekiz": "🇵🇹",
    "İskoçya": "🏴",
    "Danimarka": "🇩🇰",
    "Avusturya": "🇦🇹",
    "İsviçre": "🇨🇭",
    "İsveç": "🇸🇪",
    "Norveç": "🇳🇴",
    "Polonya": "🇵🇱",
    "Finlandiya": "🇫🇮",
    "İrlanda": "🇮🇪",
    "Yunanistan": "🇬🇷",
    "MLS": "🇺🇸",
    "Brezilya Serie A": "🇧🇷",
    "Arjantin Primera": "🇦🇷",
    "Japonya J League": "🇯🇵",
    "Meksika Liga MX": "🇲🇽",
    "Güney Kore K League 1": "🇰🇷",
    "Şili Primera": "🇨🇱",
}


def lig_etiketi(isim: str) -> str:
    emoji = LEAGUE_EMOJIS.get(isim, "⚽")
    return f"{emoji} {isim}"


def tum_lig_listesi():
    rows = []
    for kat, ligler in FUTBOL_LIGLERI.items():
        for isim, kod in ligler.items():
            rows.append({
                "kategori": kat,
                "isim": isim,
                "kod": kod,
                "label": lig_etiketi(isim),
            })
    return rows


def filtrelenmis_lig_listesi(arama_text: str):
    ligler = tum_lig_listesi()
    if not arama_text:
        return ligler

    q = arama_text.strip().lower()
    return [
        x for x in ligler
        if q in x["isim"].lower() or q in x["kategori"].lower()
    ]


EXTRA_GECMIS_ASKIDA_KODLARI = {
    "ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN",
    "MEX", "NOR", "POL", "ROU", "RUS", "SWE", "SWZ", "USA",
}

def sadece_tam_verili_gecmis(df):
    """İY verisi eksik extra/worldwide ligleri tüm geçmiş örnek görünümlerinden çıkar."""
    if df is None or getattr(df, "empty", True) or "league_code" not in df.columns:
        return df
    return df[
        ~df["league_code"].astype(str).str.upper().isin(EXTRA_GECMIS_ASKIDA_KODLARI)
    ].copy()


GECMISI_BULUNAN_LIGLER = [
    "soccer_turkey_super_league",
    "soccer_epl",
    "soccer_efl_champ",
    "soccer_england_league1",
    "soccer_england_league2",
    "soccer_spain_la_liga",
    "soccer_spain_segunda_division",
    "soccer_germany_bundesliga",
    "soccer_germany_bundesliga2",
    "soccer_italy_serie_a",
    "soccer_italy_serie_b",
    "soccer_france_ligue_one",
    "soccer_france_ligue_two",
    "soccer_netherlands_eredivisie",
    "soccer_belgium_first_div",
    "soccer_portugal_primeira_liga",
    "soccer_spl",
    "soccer_greece_super_league",
]


KARLI_LIG_PRESETLERI = {
    # Avrupa ana ligleri, mevcut alt ligleri ve UEFA kupaları.
    "cekirdek_value": [
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_uefa_europa_conference_league",
        "soccer_epl",
        "soccer_efl_champ",
        "soccer_england_league1",
        "soccer_england_league2",
        "soccer_spain_la_liga",
        "soccer_spain_segunda_division",
        "soccer_italy_serie_a",
        "soccer_italy_serie_b",
        "soccer_germany_bundesliga",
        "soccer_germany_bundesliga2",
        "soccer_france_ligue_one",
        "soccer_france_ligue_two",
        "soccer_turkey_super_league",
        "auto_turkey_1_lig",
        "soccer_netherlands_eredivisie",
        "soccer_portugal_primeira_liga",
        "soccer_belgium_first_div",
        "soccer_spl",
        "soccer_austria_bundesliga",
        "soccer_switzerland_superleague",
        "soccer_denmark_superliga",
    ],
}


def tum_lig_kodlari():
    return [kod for ligler in FUTBOL_LIGLERI.values() for kod in ligler.values()]


def init_league_states():
    for _, ligler in FUTBOL_LIGLERI.items():
        for _, kod in ligler.items():
            item_key = f"cb_{kod}"
            if item_key not in st.session_state:
                st.session_state[item_key] = False



def set_leagues(selected_codes):
    secili = set(selected_codes)
    for kod in tum_lig_kodlari():
        st.session_state[f"cb_{kod}"] = kod in secili



def clear_leagues():
    set_leagues([])


def toggle_leagues(selected_codes):
    secili = set(selected_codes)
    tumu_aktif = all(st.session_state.get(f"cb_{kod}", False) for kod in secili) if secili else False
    if tumu_aktif:
        for kod in secili:
            st.session_state[f"cb_{kod}"] = False
    else:
        set_leagues(selected_codes)

def sonraki_hafta_gunu(baslangic_tarihi, hedef_weekday: int):
    gun_farki = (hedef_weekday - baslangic_tarihi.weekday()) % 7
    return baslangic_tarihi + timedelta(days=gun_farki)


def tarih_secimine_gore_date(secim: str, bugun_tarih, ozel_tarih):
    if secim == "Bugün":
        return bugun_tarih
    if secim == "Yarın":
        return bugun_tarih + timedelta(days=1)
    if secim == "2 gün sonra":
        return bugun_tarih + timedelta(days=2)
    return ozel_tarih


def mac_canli_durumu(mac_zamani):
    kickoff = parse_mac_datetime(mac_zamani)
    if kickoff is None:
        return "Saat bilinmiyor"
    now = tr_simdi()
    if now < kickoff:
        return "Başlamamış"
    if now <= kickoff + timedelta(hours=2, minutes=15):
        return "Canlı"
    return "Bitti"


def mac_durum_badge(mac_zamani):
    durum = mac_canli_durumu(mac_zamani)
    if durum == "Canlı":
        return "#16a34a", "CANLI"
    if durum == "Başlamamış":
        return "#2563eb", "YAKINDA"
    return "#64748b", "BİTTİ"


init_league_states()
secili_kodlar = []


# ÜST KONTROL BAR
# Uygulama sunucusu UTC'de çalışsa bile tarih seçimi Türkiye gününe göre yapılır.
try:
    from zoneinfo import ZoneInfo
    sistem_simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
except Exception:
    sistem_simdi = tr_simdi()
bugun = sistem_simdi.date()
API_KEY = get_app_api_key()

st.markdown("""
<style>
.top-shell {
    background: linear-gradient(90deg,#07111f 0%, #0a1830 50%, #07111f 100%);
    border:1px solid #21334f;
    border-radius:20px;
    padding:18px 18px 14px 18px;
    margin-bottom:14px;
    box-shadow:0 16px 32px rgba(0,0,0,.34);
}
.brand-row {
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-bottom:12px;
}
.brand-title {
    display:flex;
    align-items:center;
    gap:12px;
}
.brand-logo {
    width:42px;
    height:42px;
    border-radius:12px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:linear-gradient(135deg,#ffd24a,#f4b400);
    color:#111;
    font-size:1.3rem;
    font-weight:900;
    box-shadow:0 10px 24px rgba(244,180,0,.18);
}
.brand-text {
    font-family:'Rajdhani',sans-serif;
    font-size:2rem;
    font-weight:700;
    line-height:1;
    color:#ecf3ff;
}
.brand-text span { color:#ffd24a; }
.control-card {
    background:linear-gradient(180deg,rgba(255,255,255,.04) 0%, rgba(255,255,255,.025) 100%);
    border:1px solid #233654;
    border-radius:16px;
    padding:12px 14px;
    height:100%;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.03);
}
.control-label {
    font-size:0.68rem;
    color:#8ea2c7;
    text-transform:uppercase;
    letter-spacing:1px;
    margin-bottom:6px;
}
.league-trigger {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    color:#f6fbff;
    font-weight:700;
    font-size:1rem;
}
.league-sub {
    font-size:0.82rem;
    color:#ffd24a;
    margin-top:4px;
    font-weight:700;
}
.helper-bar {
    background:linear-gradient(90deg,#0b1b33 0%, #0c213f 50%, #0b1b33 100%);
    border:1px solid #22416d;
    border-radius:14px;
    padding:12px 16px;
    margin-bottom:16px;
}
.summary-note {
    font-size:0.76rem;
    color:#90a3c0;
    margin-top:8px;
}
.pop-title {
    font-family:'Rajdhani',sans-serif;
    font-size:1.05rem;
    font-weight:700;
    color:#f4f7fb;
    margin-bottom:10px;
}
.preset-green button {
    border-color:#1f6f4d !important;
}
.preset-blue button {
    border-color:#1f4f85 !important;
}
.preset-red button {
    border-color:#7b2b34 !important;
}
.league-chip-note {
    font-size:0.78rem;
    color:#8ea2c7;
}

/* Sarı scrollbar */
* {
    scrollbar-width: thin;
    scrollbar-color: #f6c90e #0f1a2d;
}
*::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}
*::-webkit-scrollbar-track {
    background: #0f1a2d;
    border-radius: 999px;
}
*::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg,#ffd24a 0%, #f6c90e 100%);
    border-radius: 999px;
    border: 2px solid #0f1a2d;
}
*::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg,#ffe27a 0%, #ffd24a 100%);
}

/* popover ve input tonları */
div[data-baseweb="popover"] {
    border: 1px solid #243f68 !important;
    border-radius: 18px !important;
    background: linear-gradient(180deg,#07111f 0%, #09172a 100%) !important;
}

div[data-testid="stPopover"] button,
div[data-testid="stPopoverButton"] > button {
    background: linear-gradient(180deg,#0d1a2f 0%, #0b1526 100%) !important;
    border: 1px solid #284977 !important;
    color: #f7fbff !important;
    min-height: 54px !important;
    border-radius: 12px !important;
}

div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] div[data-baseweb="input"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
div[data-testid="stDateInput"] div[data-baseweb="input"] > div {
    background: #101a2c !important;
    border-color: #284977 !important;
}

.stMultiSelect [data-baseweb="tag"] {
    background: #ff5a52 !important;
    color: white !important;
}

.stSlider [data-baseweb="slider"] [role="slider"] {
    background: #ffd24a !important;
    border: 2px solid #ffe27a !important;
}
.stSlider [data-baseweb="slider"] > div > div:nth-child(1) {
    background: #ffd24a !important;
}
/* Sidebar sade preset butonları */
section[data-testid="stSidebar"] button[kind="secondary"] {
    min-height: 34px !important;
    padding: 5px 10px !important;
    font-size: 0.78rem !important;
}

/* Kupon paneli dark fix */
.coupon-panel-dark {
    background: linear-gradient(180deg,#07111f 0%, #0a1830 100%);
    border: 1px solid #284977;
    border-radius: 18px;
    box-shadow: 0 18px 45px rgba(2,8,23,.24);
    padding: 14px 16px;
    margin: 12px 0 18px 0;
}
.coupon-panel-dark h3 {
    color:#f8fbff !important;
    margin:0 0 8px 0 !important;
}
.coupon-panel-dark .coupon-sub {
    color:#9db2d1 !important;
    font-size:.76rem;
    margin-bottom:10px;
}
.coupon-panel-dark-item {
    background:#0b1628;
    border:1px solid #223c63;
    border-radius:12px;
    padding:10px 12px;
    margin-bottom:8px;
}
.coupon-panel-dark-item b { color:#f8fbff !important; }
.coupon-panel-dark-item .line { color:#9db2d1 !important;font-size:.78rem;margin-top:4px; }
.coupon-panel-dark-item code { background:#111827 !important;color:#ffd24a !important;border:1px solid #223c63;border-radius:6px;padding:2px 6px; }

</style>
""", unsafe_allow_html=True)

def clear_detail_on_filter_change():
    st.session_state.detay_idx = None
    st.session_state.detay_item = None


def sync_ayni_lig_globalden_gecmise():
    """Üstteki aynı-lig checkbox'ını Geçmiş Örnekleri toggle'ına yansıtır."""
    deger = bool(st.session_state.get("sadece_ayni_lig", False))
    st.session_state["gecmis_sadece_ayni_lig_toggle"] = deger
    # Geçmiş örnek listesi bu yeni duruma göre yeniden kurulmalı.
    st.session_state["gecmis_ayni_lig_uygulandi"] = not deger
    clear_detail_on_filter_change()


def sync_ayni_lig_gecmisten_globale():
    """Geçmiş Örnekleri toggle'ını üstteki aynı-lig checkbox'ına yansıtır."""
    deger = bool(st.session_state.get("gecmis_sadece_ayni_lig_toggle", False))
    st.session_state["sadece_ayni_lig"] = deger
    # Mevcut geçmiş liste yeni duruma göre yeniden kurulmalı.
    st.session_state["gecmis_ayni_lig_uygulandi"] = not deger
    clear_detail_on_filter_change()


def clear_backtest_on_change():
    st.session_state.backtest_df = None
    st.session_state.backtest_11_df = None
    clear_detail_on_filter_change()


def clear_detail_and_rebuild_top_markets():
    # Market filtresi değişince eski detay popup'ı açık kalmasın.
    st.session_state.detay_idx = None
    st.session_state.detay_item = None

    # Top 10 / Top 50 listeleri market filtrelerine bağlı olduğu için
    # geçmiş analiz verisi varsa listeyi anında yeniden üret.
    gecmis = st.session_state.get("last_gecmis_df")
    bulten = st.session_state.get("last_bulten_df")
    min_ornek_val = st.session_state.get("top_min_ornek", 1)

    try:
        if gecmis is not None and bulten is not None and not getattr(gecmis, "empty", True) and not getattr(bulten, "empty", True):
            ayni_lig = bool(st.session_state.get("sadece_ayni_lig", False))
            st.session_state.top50_list = gunun_en_iyi_10_uret(
                gecmis, bulten, min_ornek=min_ornek_val, limit=50, sadece_ayni_lig=ayni_lig
            )
    except Exception:
        # Filtre değişimi UI'ı bozmasın; gerekirse kullanıcı Analizi Başlat ile yeniden üretir.
        pass

def selected_league_codes():
    return [lig['kod'] for lig in tum_lig_listesi() if st.session_state.get(f"cb_{lig['kod']}", False)]

if 'date_mode' not in st.session_state:
    st.session_state['date_mode'] = 'Bugün'
if 'special_date' not in st.session_state:
    st.session_state['special_date'] = bugun
if st.session_state.get('date_mode') == '3 gün sonra':
    st.session_state['date_mode'] = 'Özel Tarih'
    st.session_state['special_date'] = bugun + timedelta(days=3)


def sistem_gununu_yenile():
    """Gece yarısından kalan oturum verilerini temizleyip gerçek bugüne döner."""
    yeni_bugun = (tr_simdi()).date()
    st.session_state["date_mode"] = "Bugün"
    st.session_state["special_date"] = yeni_bugun
    st.session_state["final_list"] = []
    st.session_state["top10_list"] = []
    st.session_state["top50_list"] = []
    st.session_state["last_bulten_df"] = None
    st.session_state["gecmis_inceleme_list"] = None
    st.session_state["yuksek_oran_list"] = None
    clear_detail_on_filter_change()


# En sık değiştirilen analiz ayarları ana ekranın üstünde normal akışta gösterilir.
with st.container(key="sticky_analysis_controls"):
    st.markdown(
        """
        <style>
        .st-key-sticky_analysis_controls {
            position:relative !important;
            z-index:1 !important;
            background:rgba(255,255,255,.97) !important;
            border:1px solid #cbd5e1 !important;
            border-radius:14px !important;
            padding:9px 16px 7px 16px !important;
            margin:0 0 14px 0 !important;
            box-shadow:0 8px 24px rgba(15,23,42,.16) !important;
            backdrop-filter:blur(8px);
        }
        .top-analysis-controls {
            margin:0 0 2px 0;
        }
        .top-analysis-controls b {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            font-size:1rem;
        }
        [data-testid="stMain"] div[data-testid="stSlider"] label,
        [data-testid="stMain"] div[data-testid="stSlider"] label *,
        [data-testid="stMain"] div[data-testid="stNumberInput"] label,
        [data-testid="stMain"] div[data-testid="stNumberInput"] label * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
            font-weight:800 !important;
        }
        @media (max-width:700px) {
            .st-key-sticky_analysis_controls {
                position:relative !important;
                top:auto !important;
                padding:6px 9px !important;
            }
            .top-analysis-controls { display:none; }
        }
        </style>
        <div class="top-analysis-controls"><b>🎛️ Ana Analiz Ayarları</b></div>
        """,
        unsafe_allow_html=True,
    )

    # Panel, sidebar tema anahtarından önce çizildiği için koyu modu doğrudan
    # session_state üzerinden burada da uygula. Böylece ilk CSS'teki beyaz
    # arka plan koyu modda hiçbir rerun/sıralama durumunda görünmez.
    if bool(st.session_state.get("koyu_mod", False)):
        st.markdown(
            """
            <style>
            .st-key-sticky_analysis_controls,
            div.st-key-sticky_analysis_controls {
                background:#0b1628 !important;
                background-color:#0b1628 !important;
                background-image:linear-gradient(180deg,#0b1628 0%,#0a1830 100%) !important;
                border:1px solid #315487 !important;
                box-shadow:0 8px 24px rgba(0,0,0,.30) !important;
            }
            .st-key-sticky_analysis_controls > div,
            .st-key-sticky_analysis_controls [data-testid="stVerticalBlock"],
            .st-key-sticky_analysis_controls [data-testid="stHorizontalBlock"],
            .st-key-sticky_analysis_controls [data-testid="column"],
            .st-key-sticky_analysis_controls div[data-testid="stElementContainer"] {
                background-color:transparent !important;
            }
            .st-key-sticky_analysis_controls .top-analysis-controls b,
            .st-key-sticky_analysis_controls label,
            .st-key-sticky_analysis_controls label *,
            .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"],
            .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"] * {
                color:#f8fafc !important;
                -webkit-text-fill-color:#f8fafc !important;
                opacity:1 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    ayar_tol_col, ayar_ornek_col, ayar_oynanabilir_col, ayar_buton_col = st.columns(
        [2.25, .95, 1.35, 1.25], gap="small"
    )
    with ayar_tol_col:
        if st.session_state.get("sayfa_modu") in ["Oran Filtresi", "Yüksek Oran Filtresi"]:
            # Bu iki görünüm tek hassasiyete bağlı değildir; 0.00-0.10 arası 11 seviye otomatik taranır.
            TOLERANS = 0.10
            st.markdown(
                "<div style='font-size:.82rem;color:#64748b;margin-bottom:4px;'>Oran Hassasiyeti</div>"
                "<div style='background:#0f1b31;border:1px solid #284977;border-radius:8px;padding:8px 10px;"
                "color:#f8fafc;font-weight:800;'>0.00–0.10 · Otomatik 11 tarama</div>",
                unsafe_allow_html=True,
            )
        else:
            TOLERANS = st.slider(
                "Oran Hassasiyeti",
                0.00, 0.30, 0.08,
                step=0.01,
                key="top_tol",
                on_change=clear_detail_on_filter_change,
                help="Seçilen değer, 1-X-2 oranlarının her biri için izin verilen yaklaşık mutlak oran farkıdır. Üç oran da sınır içinde olmalıdır.",
            )
    with ayar_ornek_col:
        min_ornek = st.number_input(
            "Minimum Örnek Sayısı",
            min_value=1,
            value=1,
            step=1,
            key="top_min_ornek",
            on_change=clear_detail_on_filter_change,
        )
    with ayar_oynanabilir_col:
        oynanabilir_esik = st.selectbox(
            "Oynanılabilir eşik",
            options=[0, 55, 60, 65, 70, 75],
            index=2,
            format_func=lambda x: "Tümü" if x == 0 else f"Güven ≥ %{x}",
            key="oynanabilir_esik",
            on_change=clear_detail_on_filter_change,
        )
    with ayar_buton_col:
        # Düğme, sidebar'da görünüm seçildikten sonra bu üst konuma yazdırılır.
        ust_analiz_buton_alani = st.empty()

    # Maç Analizi varsayılan olarak yalnızca seçili hassasiyetle tek hesap yapar.
    # İstenirse 0.00–0.10 arasındaki 11 hassasiyet ayrıca taranıp kartlarda gösterilir.
    if st.session_state.get("sayfa_modu") == "Maç Analizi":
        st.checkbox(
            "🎯 11 hassasiyet taramasını göster (0.00–0.10)",
            value=False,
            key="mac_analizi_stabilite_tarama",
            help="Kapalıyken Maç Analizi yalnızca seçtiğin Oran Hassasiyeti ile çalışır ve çok daha hızlıdır. Açıldığında her sonuç maçı için 0.00–0.10 arası 11 seviye ayrıca taranır.",
        )

    secim_ozet_tarih = tarih_secimine_gore_date(
        st.session_state.get("date_mode", "Bugün"), bugun,
        st.session_state.get("special_date", bugun),
    )
    with st.container(key="tarih_lig_sezon_paneli"):
      with st.expander("📅 Tarih, Lig ve Sezon Seçimi", expanded=False):
        tarih_col, sezon_col = st.columns([1.35, 1], gap="medium")
        with tarih_col:
            st.radio(
                "Tarih modu",
                options=["Bugün", "Yarın", "2 gün sonra", "Özel Tarih"],
                index=["Bugün", "Yarın", "2 gün sonra", "Özel Tarih"].index(st.session_state.get("date_mode", "Bugün")),
                key="date_mode",
                on_change=clear_detail_on_filter_change,
                horizontal=True,
            )
            if st.session_state.get("date_mode") == "Özel Tarih":
                st.date_input(
                    "Özel tarih", value=st.session_state.get("special_date", bugun),
                    key="special_date", on_change=clear_detail_on_filter_change,
                )
            secili_tarih = tarih_secimine_gore_date(
                st.session_state.get("date_mode", "Bugün"), bugun,
                st.session_state.get("special_date", bugun),
            )
            st.caption(f"Seçili tarih: {format_tr_date(secili_tarih)}")

        with sezon_col:
            sezon_secenekleri = ["2122", "2223", "2324", "2425", "2526", "2627"]
            yillar = st.multiselect(
                "Sezonlar", options=sezon_secenekleri, default=sezon_secenekleri,
                key="top_seasons", on_change=clear_backtest_on_change,
            )
            sadece_ayni_lig = st.checkbox(
                "Sadece aynı lig verilerini kullan", value=False,
                key="sadece_ayni_lig",
                help="Açıkken maç yalnızca kendi liginin geçmişiyle karşılaştırılır.",
                on_change=sync_ayni_lig_globalden_gecmise,
            )

        preset1, preset2, preset3, preset4 = st.columns(4, gap="small")
        with preset1:
            if st.button("Hepsini Aç", use_container_width=True, key="preset_all_top"):
                set_leagues(tum_lig_kodlari())
                st.rerun()
        with preset2:
            if st.button("Temizle", use_container_width=True, key="preset_clear_top"):
                clear_leagues()
                st.rerun()
        with preset3:
            if st.button("Tam Verili Ligler", use_container_width=True, key="preset_history_top",
                         help="Geçmiş sonuç ve ilk yarı verileri eksiksiz olan ligleri seçer."):
                set_leagues(GECMISI_BULUNAN_LIGLER)
                st.rerun()
        with preset4:
            if st.button("Avrupa Ana + Alt", use_container_width=True, key="preset_core_top"):
                toggle_leagues(KARLI_LIG_PRESETLERI["cekirdek_value"])
                st.rerun()

        lig_arama = st.text_input(
            "Lig ara", placeholder="örn. Premier, Türkiye, MLS",
            key="lig_arama_top", on_change=clear_detail_on_filter_change,
        )
        filtreli_ligler = filtrelenmis_lig_listesi(lig_arama)
        st.caption(f"Gösterilen lig: {len(filtreli_ligler)} · Seçili lig: {len(selected_league_codes())}")
        lig_box = st.container(height=300, border=True)
        with lig_box:
            lig_kolonlari = st.columns(3, gap="small")
            for lig_no, lig in enumerate(filtreli_ligler):
                with lig_kolonlari[lig_no % 3]:
                    st.checkbox(lig["label"], key=f"cb_{lig['kod']}", on_change=clear_detail_on_filter_change)

      secili_kodlar = selected_league_codes()
      secili_sezonlar_ozet = st.session_state.get("top_seasons", sezon_secenekleri)
      panel_ozeti = (
          f"🗓️ {format_tr_date(secim_ozet_tarih)}  ·  "
          f"🏆 {len(secili_kodlar)} lig  ·  "
          f"🗂️ {len(secili_sezonlar_ozet)} sezon"
      ).replace('"', '\\"')
      st.markdown(
          f"""
          <style>
          .st-key-tarih_lig_sezon_paneli details > summary::after {{
              content:"{panel_ozeti}";
              margin-left:auto;
              padding-left:16px;
              color:#f8fafc;
              -webkit-text-fill-color:#f8fafc;
              font-size:.82rem;
              font-weight:800;
              white-space:nowrap;
          }}
          @media (max-width:760px) {{
              .st-key-tarih_lig_sezon_paneli details > summary::after {{
                  content:"🗓️ {format_tr_date(secim_ozet_tarih)} · 🏆 {len(secili_kodlar)}";
                  font-size:.72rem;
                  white-space:normal;
                  text-align:right;
              }}
          }}
          </style>
          """,
          unsafe_allow_html=True,
      )


# ==========================================================
# AÇIK / KOYU TEMA
# ==========================================================
def uygula_tema_css(koyu_mod: bool):
    """Açık/koyu renkler ve tek kaydırma düzeni ortak kaynaktan uygulanır."""
    colors = {'bg': ('#07111f', '#f6f8fc'), 'bg2': ('#0a1830', '#eef3fb'), 'surface': ('#091526', '#eef3fb'), 'surface2': ('#0f1b31', '#ffffff'), 'card': ('#111827', '#ffffff'), 'border': ('#284977', '#cbd5e1'), 'border-soft': ('#223c63', '#d6e0ef'), 'text': ('#f8fafc', '#0f172a'), 'muted': ('#9db2d1', '#475569'), 'muted2': ('#cbd5e1', '#334155'), 'accent': ('#facc15', '#ca8a04'), 'blue': ('#77b4ff', '#1d4ed8')}
    variables = ";".join(f"--yk-{name}:{values[0 if koyu_mod else 1]}" for name, values in colors.items())
    scheme = "dark" if koyu_mod else "light"
    css = ":root {color-scheme:" + scheme + ";" + variables + ";}\n"
    css += 'html, body, [class*="css"], .stApp,\n        [data-testid="stAppViewContainer"], [data-testid="stMain"] {\nbackground:var(--yk-bg) !important;\n            color:var(--yk-text) !important;\n}\n.stApp, [data-testid="stAppViewContainer"] {\nbackground:linear-gradient(180deg,var(--yk-bg) 0%,var(--yk-bg2) 48%,var(--yk-bg2) 100%) !important;\n}\n[data-testid="stHeader"] {\nbackground:var(--yk-bg) !important;\n}\n.main .block-container, [data-testid="stMainBlockContainer"] {\nbackground:transparent !important;\n}\nsection[data-testid="stSidebar"] {\nbackground:var(--yk-surface) !important;\n            border-color:var(--yk-border-soft) !important;\n            \n            \n            \n            \n            \n            \n            \n            \n            z-index:100 !important;\n}\nsection[data-testid="stSidebar"] > div,\n        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {\nbackground:var(--yk-surface) !important;\n            border-color:var(--yk-border-soft) !important;\n}\nsection[data-testid="stSidebar"] label,\n        section[data-testid="stSidebar"] label *,\n        section[data-testid="stSidebar"] p,\n        section[data-testid="stSidebar"] span:not([data-baseweb="tag"] span),\n        section[data-testid="stSidebar"] h1,\n        section[data-testid="stSidebar"] h2,\n        section[data-testid="stSidebar"] h3,\n        section[data-testid="stSidebar"] h4 {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\nsection[data-testid="stSidebar"] [data-testid="stCaptionContainer"],\n        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {\ncolor:var(--yk-muted) !important;\n            -webkit-text-fill-color:var(--yk-muted) !important;\n}\n.st-key-koyu_mod_toggle {\nbackground:var(--yk-surface) !important;\n            border:1px solid var(--yk-border) !important;\n            border-radius:12px !important;\n            padding:7px 10px 4px 10px !important;\n            margin:2px 0 2px 0 !important;\n}\n.st-key-koyu_mod_toggle label,\n        .st-key-koyu_mod_toggle label * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            font-weight:800 !important;\n}\n.st-key-sidebar_system_clock {\nbackground:var(--yk-surface) !important;\n            border:1px solid var(--yk-border) !important;\n            box-shadow:0 4px 14px rgba(0,0,0,.28) !important;\n}\n.st-key-sidebar_system_clock .system-clock-label,\n        .st-key-sidebar_system_clock .system-clock-label *,\n        .st-key-sidebar_system_clock .system-clock-time {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.top-header h2, .list-heading, .panel-title,\n        .topbar-wrap h1, .topbar-wrap h2, .topbar-wrap h3,\n        [data-testid="stMain"] h1, [data-testid="stMain"] h2,\n        [data-testid="stMain"] h3, [data-testid="stMain"] h4,\n        [data-testid="stMain"] p, [data-testid="stMain"] label {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.top-header .sub, .panel-date, .summary-note, .list-subheading,\n        .control-label, .section-kicker, .league-chip-note {\ncolor:var(--yk-muted) !important;\n            -webkit-text-fill-color:var(--yk-muted) !important;\n}\n.top-shell, .topbar-wrap, .control-card, .metrics-card,\n        .helper-bar, .rehber-box, .top-hero {\nbackground:linear-gradient(180deg,var(--yk-surface) 0%,var(--yk-bg2) 100%) !important;\n            border-color:var(--yk-border) !important;\n            color:var(--yk-text) !important;\n            box-shadow:0 10px 30px rgba(0,0,0,.20) !important;\n}\ndiv[data-baseweb="select"] > div,\n        div[data-baseweb="input"] > div,\n        div[data-testid="stNumberInput"] div[data-baseweb="input"] > div,\n        div[data-testid="stTextInput"] div[data-baseweb="input"] > div,\n        div[data-testid="stDateInput"] div[data-baseweb="input"] > div,\n        div[data-testid="stNumberInputContainer"],\n        div[data-testid="stTextInputRootElement"],\n        textarea, input {\nbackground:var(--yk-surface2) !important;\n            border-color:var(--yk-border) !important;\n            color:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\ndiv[data-baseweb="select"] *,\n        [data-baseweb="popover"] *,\n        [role="listbox"] *, [role="option"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n[data-baseweb="popover"], [role="listbox"] {\nbackground:var(--yk-surface) !important;\n            border-color:var(--yk-border) !important;\n}\n[role="option"]:hover, [aria-selected="true"][role="option"] {\nbackground:#17304d !important;\n}\n.stButton > button,\n        div[data-testid="stPopover"] button,\n        div[data-testid="stPopoverButton"] > button,\n        [data-testid="baseButton-secondary"] {\nbackground:linear-gradient(180deg,var(--yk-surface2) 0%,var(--yk-surface) 100%) !important;\n            color:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            border-color:#315487 !important;\n}\n.stButton > button:hover,\n        div[data-testid="stPopoverButton"] > button:hover {\nborder-color:var(--yk-accent) !important;\n            color:var(--yk-text) !important;\n}\nbutton[kind="primary"], [data-testid="baseButton-primary"] {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\ndiv[data-testid="stExpander"],\n        div[data-testid="stExpander"] details,\n        div[data-testid="stExpander"] summary,\n        .streamlit-expanderHeader {\nbackground:linear-gradient(90deg,var(--yk-surface) 0%,var(--yk-bg2) 100%) !important;\n            border-color:var(--yk-border) !important;\n            color:var(--yk-text) !important;\n}\ndiv[data-testid="stExpander"] *,\n        .stCheckbox label *, .stRadio label *,\n        div[data-testid="stToggle"] label * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\ndiv[data-testid="stTabs"] button,\n        div[data-testid="stTabs"] button * {\ncolor:var(--yk-muted2) !important;\n            -webkit-text-fill-color:var(--yk-muted2) !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-child,\n        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] span:first-child {\nborder-radius:4px !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked ~ div:first-of-type,\n        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked + div {\nbackground:#ff4b55 !important;\n            background-color:#ff4b55 !important;\n            border-color:#ff4b55 !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked ~ div:first-of-type svg,\n        section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked + div svg {\ncolor:var(--yk-text) !important;\n            fill:var(--yk-text) !important;\n            stroke:var(--yk-text) !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] input:checked + div {\nbackground-color:#ef4444 !important;\n            border-color:#ef4444 !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] input:checked + div svg {\ncolor:var(--yk-text) !important;\n            fill:var(--yk-text) !important;\n            stroke:var(--yk-text) !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] [aria-checked="true"] {\nbackground-color:#ef4444 !important;\n            border-color:#ef4444 !important;\n}\nsection[data-testid="stSidebar"] div[data-testid="stCheckbox"] [aria-checked="true"] svg {\ncolor:var(--yk-text) !important;\n            fill:var(--yk-text) !important;\n            stroke:var(--yk-text) !important;\n}\n[data-testid="stMetric"], [data-testid="metric-container"] {\nbackground:var(--yk-surface) !important;\n            border:1px solid var(--yk-border-soft) !important;\n            border-radius:12px !important;\n            padding:10px !important;\n}\n[data-testid="stMetric"] *, [data-testid="metric-container"] * {\ncolor:var(--yk-text) !important;\n}\ndiv[data-testid="stAlert"] {\nbackground:var(--yk-surface) !important;\n            border-color:var(--yk-border) !important;\n            color:var(--yk-text) !important;\n}\ndiv[data-testid="stAlert"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n[data-testid="stDataFrame"], [data-testid="stTable"] {\nbackground:var(--yk-surface) !important;\n            border-radius:12px !important;\n            border:1px solid var(--yk-border-soft) !important;\n            overflow:hidden !important;\n}\n[data-testid="stDataFrame"] iframe {\nbackground:var(--yk-surface) !important;\n}\ntable, thead, tbody, tr, th, td {\nborder-color:var(--yk-border-soft) !important;\n}\n[data-testid="stTable"] table,\n        [data-testid="stTable"] th,\n        [data-testid="stTable"] td {\nbackground:var(--yk-surface) !important;\n            color:var(--yk-text) !important;\n}\n.mac-kart, .tahmin-kart, .diger-kart, .neden-kart, .kupon-kart,\n        .combo-kart, .canli-kart, .strateji-kart, .oranlar-kart,\n        .history-card, .ai-comment, .ai-inline, .coupon-item,\n        .recent-match-row, .detail-form-sidebar-title {\nbackground:linear-gradient(135deg,var(--yk-surface),var(--yk-card)) !important;\n            border-color:var(--yk-border-soft) !important;\n            color:var(--yk-text) !important;\n}\n.mac-kart *, .tahmin-kart *, .diger-kart *, .neden-kart *,\n        .kupon-kart *, .combo-kart *, .canli-kart *, .strateji-kart *,\n        .oranlar-kart *, .history-card *, .ai-comment *, .ai-inline * {\ncolor:var(--yk-text);\n}\n.history-sub, .mk-mini, .tk-key, .diger-sub, .hb-sub, .hb-label,\n        .mk-label, .recent-top {\ncolor:var(--yk-muted) !important;\n            -webkit-text-fill-color:var(--yk-muted) !important;\n}\ndiv[data-testid="stDialog"] div[role="dialog"] {\nbackground:linear-gradient(180deg,var(--yk-bg) 0%,var(--yk-bg2) 100%) !important;\n            border-color:var(--yk-border) !important;\n}\ndiv[data-testid="stDialog"] div[role="dialog"] p,\n        div[data-testid="stDialog"] div[role="dialog"] label,\n        div[data-testid="stDialog"] div[role="dialog"] h1,\n        div[data-testid="stDialog"] div[role="dialog"] h2,\n        div[data-testid="stDialog"] div[role="dialog"] h3 {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.sidebar-high-market-title {\nbackground:#102340 !important;\n            border-color:#315487 !important;\n}\n.sidebar-high-market-title b {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.sidebar-high-market-title span {\ncolor:var(--yk-muted2) !important;\n            -webkit-text-fill-color:var(--yk-muted2) !important;\n}\na {\ncolor:var(--yk-blue) !important;\n}\nhr {\nborder-color:var(--yk-border-soft) !important;\n}\ndiv[data-testid="stSpinner"], div[data-testid="stSpinner"] *,\n        div[data-testid="stStatusWidget"], div[data-testid="stStatusWidget"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.st-key-sticky_analysis_controls {\nbackground:linear-gradient(180deg,var(--yk-surface) 0%,var(--yk-bg2) 100%) !important;\n            border-color:#315487 !important;\n            box-shadow:0 8px 24px rgba(0,0,0,.30) !important;\n}\n.st-key-sticky_analysis_controls > div,\n        .st-key-sticky_analysis_controls [data-testid="stVerticalBlock"],\n        .st-key-sticky_analysis_controls [data-testid="stHorizontalBlock"],\n        .st-key-sticky_analysis_controls [data-testid="column"],\n        .st-key-sticky_analysis_controls div[data-testid="stElementContainer"] {\nbackground:transparent !important;\n}\n.st-key-sticky_analysis_controls {\nbackground-color:var(--yk-surface) !important;\n}\n.st-key-sticky_analysis_controls .top-analysis-controls b,\n        .st-key-sticky_analysis_controls label,\n        .st-key-sticky_analysis_controls label *,\n        .st-key-sticky_analysis_controls p,\n        .st-key-sticky_analysis_controls span,\n        .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"],\n        .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            opacity:1 !important;\n}\n.st-key-sticky_analysis_controls [data-testid="stSlider"] label,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] label *,\n        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] label,\n        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] label *,\n        .st-key-sticky_analysis_controls [data-testid="stSelectbox"] label,\n        .st-key-sticky_analysis_controls [data-testid="stSelectbox"] label * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            font-weight:800 !important;\n}\n.st-key-sticky_analysis_controls [data-baseweb="select"] > div,\n        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] div[data-baseweb="input"] > div {\nbackground:var(--yk-surface2) !important;\n            border-color:#315487 !important;\n}\n.st-key-sticky_analysis_controls [data-baseweb="select"] *,\n        .st-key-sticky_analysis_controls input {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n}\n.st-key-sayfa_modu,\n        .st-key-sayfa_modu [data-testid="stRadio"] {\ncolor:var(--yk-text) !important;\n}\n.st-key-sayfa_modu label,\n        .st-key-sayfa_modu label *,\n        .st-key-sayfa_modu p,\n        .st-key-sayfa_modu span,\n        .st-key-sayfa_modu [data-testid="stWidgetLabel"],\n        .st-key-sayfa_modu [data-testid="stWidgetLabel"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            opacity:1 !important;\n}\n.st-key-sayfa_modu [role="radiogroup"] label,\n        .st-key-sayfa_modu [role="radiogroup"] label *,\n        section[data-testid="stSidebar"] .st-key-sayfa_modu [role="radiogroup"] p {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            font-weight:700 !important;\n}\n.st-key-sticky_analysis_controls .top-analysis-controls,\n        .st-key-sticky_analysis_controls .top-analysis-controls *,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] label,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] label *,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stWidgetLabel"],\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stWidgetLabel"] *,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBar"],\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBar"] *,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBarMin"],\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBarMax"],\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"],\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"] * {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            opacity:1 !important;\n}\n.st-key-sticky_analysis_controls .top-analysis-controls b {\ncolor:var(--yk-text) !important;\n            -webkit-text-fill-color:var(--yk-text) !important;\n            text-shadow:0 1px 1px rgba(0,0,0,.35) !important;\n}\n.st-key-sticky_analysis_controls [data-testid="stSlider"] svg,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] button svg,\n        .st-key-sticky_analysis_controls [data-testid="stTooltipIcon"] svg {\ncolor:var(--yk-text) !important;\n            fill:var(--yk-text) !important;\n            stroke:var(--yk-text) !important;\n            opacity:1 !important;\n}\n.st-key-sticky_analysis_controls [data-testid="stSlider"] div,\n        .st-key-sticky_analysis_controls [data-testid="stSlider"] span {\n-webkit-text-fill-color:var(--yk-text) !important;\n}\n.st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"] {\nbackground:var(--yk-accent) !important;\n            border-color:#ffe27a !important;\n}\n[data-testid="stMain"] div[style*="text-align:center"][style*="font-size:12px"] {\ncolor:var(--yk-muted) !important;\n}\n/* Tek kaydırma düzeni. Sidebar ana içerikle birlikte hareket etmez. */\nhtml, body {height:100%; min-height:100%; overflow:hidden; background:var(--yk-bg); color:var(--yk-text);}\n.stApp, [data-testid="stAppViewContainer"] {\n    height:100dvh !important; min-height:0 !important; max-height:100dvh !important;\n    overflow:hidden !important; background:var(--yk-bg) !important;\n}\n[data-testid="stAppViewContainer"] > div {gap:0; background:var(--yk-bg);}\nsection[data-testid="stSidebar"] {\n    position:relative !important; top:auto !important; align-self:stretch !important;\n    height:100dvh !important; min-height:0 !important; max-height:100dvh !important;\n    overflow:hidden !important; margin-right:0; box-shadow:none;\n    background:var(--yk-surface) !important; border-color:var(--yk-border-soft) !important;\n}\nsection[data-testid="stSidebar"] > div,\nsection[data-testid="stSidebar"] [data-testid="stSidebarContent"] {\n    height:100% !important; min-height:0 !important; max-height:100% !important;\n    overflow-y:auto !important; overflow-x:hidden !important; background:var(--yk-surface) !important;\n}\n[data-testid="stMain"] {\n    height:100dvh !important; min-height:0 !important; max-height:100dvh !important; min-width:0;\n    overflow-y:auto !important; overflow-x:hidden !important; margin-left:0;\n    overscroll-behavior-y:contain; scrollbar-gutter:stable; background:var(--yk-bg) !important;\n}\n[data-testid="stMainBlockContainer"], .main .block-container {\n    height:auto !important; min-height:100% !important; max-height:none !important;\n    overflow:visible !important; padding-bottom:6rem; background:transparent !important;\n}\ndiv[data-testid="stExpander"], div[data-testid="stExpander"] details,\ndiv[data-testid="stExpanderDetails"], div[data-testid="stExpanderDetails"] > div {\n    max-height:none; overflow:visible; contain:none;\n}\n.st-key-koyu_mod_toggle {margin-bottom:0;}\n.st-key-sidebar_system_clock {\n    background:var(--yk-surface2) !important; border:1px solid var(--yk-border) !important;\n    border-radius:12px; padding:6px 8px; margin:0 0 8px; box-shadow:none;\n}\n.st-key-sidebar_system_clock [data-testid="stHorizontalBlock"] {align-items:center; gap:.45rem;}\n.st-key-sidebar_system_clock .system-clock-label {\n    width:100%; min-height:40px; display:flex; flex-direction:column; justify-content:center;\n    align-items:center; text-align:center; font-size:.72rem; line-height:1.18;\n    font-weight:700; padding:0; margin:0; color:var(--yk-text) !important;\n}\n.st-key-sidebar_system_clock .system-clock-label *,\n.st-key-sidebar_system_clock .system-clock-time {color:var(--yk-text) !important; -webkit-text-fill-color:var(--yk-text) !important;}\n.st-key-sidebar_system_clock .system-clock-time {display:block; margin-top:2px; font-size:.82rem; font-weight:900;}\n.st-key-sidebar_system_clock .system-clock-label > span:last-child {color:var(--yk-muted) !important; -webkit-text-fill-color:var(--yk-muted) !important;}\n.st-key-sidebar_system_clock button {min-height:40px; height:40px; font-weight:800;}\n.st-key-sticky_analysis_controls, .backtest-header-fix,\ndiv[data-testid="stMetric"] {background:var(--yk-surface2) !important; border-color:var(--yk-border) !important;}\n.backtest-header-fix, .backtest-header-fix *,\ndiv[data-testid="stMetric"] label, div[data-testid="stMetric"] label *,\ndiv[data-testid="stMetric"] [data-testid="stMetricValue"], div[data-testid="stMetric"] [data-testid="stMetricValue"] * {\n    color:var(--yk-text) !important; -webkit-text-fill-color:var(--yk-text) !important;\n}\n* {scrollbar-width:thin; scrollbar-color:var(--yk-accent) var(--yk-surface);}\n*::-webkit-scrollbar-track {background:var(--yk-surface);}\n*::-webkit-scrollbar-thumb {background:var(--yk-accent); border-color:var(--yk-surface);}\n'
    # Başlık renklerini uygulamanın açık/koyu tema seçimine bağla.
    css += """
    .stApp [data-testid="stHeading"] :is(h1,h2,h3,h4,h5,h6),
    .stApp [data-testid="stHeading"] :is(h1,h2,h3,h4,h5,h6) *,
    .stApp [data-testid="stMarkdownContainer"] :is(h1,h2,h3,h4,h5,h6),
    .stApp [data-testid="stMarkdownContainer"] :is(h1,h2,h3,h4,h5,h6) * {
        color:var(--yk-text) !important;
        -webkit-text-fill-color:var(--yk-text) !important;
        opacity:1 !important;
    }
    """
    st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)


# FİLTRELER ARTIK SOL SIDEBAR İÇİNDE
with st.sidebar:
    with st.container(key="koyu_mod_toggle"):
        koyu_mod = st.toggle("🌙 Koyu Mod", key="koyu_mod")
    uygula_tema_css(koyu_mod)

    with st.container(key="sidebar_system_clock"):
        sistem_bilgi_col, sistem_yenile_col = st.columns([1.55, 1], gap="small")
        with sistem_bilgi_col:
            st.markdown(
                f'<div class="system-clock-label">🕒 Sistem tarihi ve saati'
                f'<span class="system-clock-time">{sistem_simdi.strftime("%d.%m.%Y %H:%M")}</span>'
                f'<span>Türkiye</span></div>',
                unsafe_allow_html=True,
            )
        with sistem_yenile_col:
            st.button(
                "🔄 Yenile",
                key="sistem_gununu_yenile_btn",
                use_container_width=True,
                on_click=sistem_gununu_yenile,
                help="Tarihi gerçek bugüne alır ve önceki günden kalan maç listelerini temizler.",
            )
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;padding:10px 8px;border-radius:14px;background:linear-gradient(90deg,#07111f 0%,#0a1830 100%);border:1px solid #21334f;">
      <div class="brand-logo" style="width:36px;height:36px;font-size:1.1rem">⚡</div>
      <div class="brand-text" style="font-size:1.35rem">YapAi<span>Kupon</span></div>
    </div>
    """, unsafe_allow_html=True)
    with st.expander("🔑 API Key", expanded=False):
        current_key = st.session_state.get("user_api_key", "")
        api_key_input = st.text_input("ODDS API KEY", value=current_key, placeholder="API key gir...", type="password", key="api_key_input_sidebar_clean")
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Kaydet", use_container_width=True, key="save_api_key_sidebar_clean"):
                st.session_state["user_api_key"] = api_key_input.strip()
                st.success("API Key kaydedildi ✅")
                st.rerun()
        with a2:
            if st.button("Temizle", use_container_width=True, key="clear_api_key_sidebar_clean"):
                st.session_state.pop("user_api_key", None)
                st.success("API Key temizlendi")
                st.rerun()
        if get_app_api_key():
            st.success("Odds API key aktif ✅")
        else:
            st.warning("Kayıtlı analizler açılabilir; canlı skor ve yeni veri için Odds API key gerekir.")

        st.markdown("##### ⚽ API-Football · bağlam fallback")
        af_current = st.session_state.get("user_api_football_key", "")
        af_input = st.text_input(
            "API-FOOTBALL KEY",
            value=af_current,
            placeholder="Son form / saha formu / H2H için...",
            type="password",
            key="api_football_key_sidebar_clean",
        )
        af1, af2 = st.columns(2)
        with af1:
            if st.button("AF Kaydet", use_container_width=True, key="save_api_football_key_sidebar_clean"):
                st.session_state["user_api_football_key"] = af_input.strip()
                st.rerun()
        with af2:
            if st.button("AF Temizle", use_container_width=True, key="clear_api_football_key_sidebar_clean"):
                st.session_state.pop("user_api_football_key", None)
                st.rerun()
        if get_api_football_key():
            st.caption("✅ API-Football fallback aktif · yalnızca yerel bağlam eksikse çağrılır")
        else:
            st.caption("API-Football fallback kapalı")

    # API TASARRUF PANELİ: analiz butonları cache'teki aynı bülteni kullanır.
    cache_hazir, cache_toplam = odds_cache_bilgi(secili_kodlar, secili_tarih)
    kota = st.session_state.get("odds_api_quota", {}) or {}
    kalan = kota.get("remaining")
    kullanilan = kota.get("used")
    kota_yazi = "Kota bilgisi henüz yok"
    if kalan not in (None, ""):
        kota_yazi = f"Kalan kredi: {kalan}"
        if kullanilan not in (None, ""):
            kota_yazi += f" · Kullanılan: {kullanilan}"
    st.caption(f"🧠 Bülten cache: {cache_hazir}/{cache_toplam} lig · 6 saat · {kota_yazi}")
    fd_son_cekim, fd_kaynak = football_data_son_cekim_bilgisi()
    st.caption(f"⚽ Football-Data son çekim: {fd_son_cekim} · {fd_kaynak}")
    if st.button(
        "🔄 Oranları Yenile",
        use_container_width=True,
        key="oranlari_zorla_yenile_btn",
        help="Yalnızca seçili liglerin oranlarını yeniden API'den çeker. Filtre/checkbox değişiklikleri 6 saatlik cache'i kullanır ve kredi tüketmez.",
    ):
        if not API_KEY or not secili_kodlar:
            st.warning("API key ve en az bir lig gerekli.")
        else:
            with st.spinner("Seçili liglerin oranları yenileniyor..."):
                yenilenen_bulten = bulten_guncel_al(
                    API_KEY, secili_kodlar, secili_tarih, zorla_yenile=True
                )
                st.session_state.last_bulten_df = yenilenen_bulten
            st.success(f"Oranlar yenilendi · {len(yenilenen_bulten)} maç")

    # Sonuç Takibi resetinden sonra widget oluşturulmadan önce Maç Analizi'ne dön.
    # Böylece yeni kodla analiz otomatik olarak yeniden çalıştırılabilir.
    if st.session_state.pop("sonuc_reset_hedef_mac_analizi", False):
        st.session_state["sayfa_modu"] = "Maç Analizi"

    sayfa_modu = st.radio(
        "Görünüm",
        ["Maç Analizi", "Top 50 Market", "Geçmiş Örnekleri", "Oran Filtresi", "Yüksek Oran Filtresi", "Spor Toto", "Canlı Takip", "Sonuç Takibi", "Backtest"],
        index=0,
        key="sayfa_modu",
        on_change=clear_detail_on_filter_change,
    )

    if st.session_state.get("sayfa_modu") == "Top 50 Market":
        st.markdown("### Market Filtreleri")

        # Üst satır: 3 filtre
        c_ms, c_25, c_kg = st.columns([1, 1, 1], gap="small")
        with c_ms:
            st.checkbox("MS", value=True, key="top10_filter_ms", on_change=clear_detail_and_rebuild_top_markets)
        with c_25:
            st.checkbox("2.5", value=True, key="top10_filter_25", on_change=clear_detail_and_rebuild_top_markets)
        with c_kg:
            st.checkbox("KG", value=True, key="top10_filter_kg", on_change=clear_detail_and_rebuild_top_markets)

        # Alt satır: 2 filtre
        c_iy15, c_combo = st.columns([1, 1], gap="small")
        with c_iy15:
            st.checkbox("İY 1.5", value=True, key="top10_filter_iy15", on_change=clear_detail_and_rebuild_top_markets)
        with c_combo:
            st.checkbox("Kombo", value=True, key="top10_filter_combo", on_change=clear_detail_and_rebuild_top_markets)

    # Tarih, lig ve sezon ayarları üstteki yapışkan kontrol alanına taşındı.
    analiz_btn = False
    backtest_btn = False
    gecmis_btn = False
    oran_filtresi_btn = False
    yuksek_oran_btn = False
    spor_toto_btn = False
    canli_yenile_btn = False
    canli_otomatik = False
    sonuc_yenile_btn = False
    if st.session_state.get('sayfa_modu') == 'Backtest':
        backtest_sezonu = st.selectbox(
            'Test sezonu',
            options=sezon_secenekleri,
            index=sezon_secenekleri.index('2627'),
            key='backtest_sezonu',
            on_change=clear_backtest_on_change,
        )
        backtest_limit = st.number_input('En fazla test maçı', min_value=50, max_value=2000, value=500, step=50, key='backtest_limit')
        backtest_btn = False
    elif st.session_state.get('sayfa_modu') == 'Geçmiş Örnekleri':
        gecmis_limit = st.selectbox('Maç başına geçmiş örnek', [10, 25, 50, 100], index=1, key='gecmis_limit')
        gecmis_btn = False
    elif st.session_state.get('sayfa_modu') == 'Oran Filtresi':
        # Oran Filtresi kutuları kullanıcı tarafından açılıp kapatılabilir.
        of1, of2 = st.columns(2)
        with of1:
            oran_filter_ms = st.checkbox('Maç Sonucu', value=True, key='oran_filter_ms')
        with of2:
            oran_filter_kg = st.checkbox('Karşılıklı Gol', value=True, key='oran_filter_kg')
        oran_filter_25 = st.checkbox('2.5 Alt / Üst', value=True, key='oran_filter_25')
        # İki yarı 1.5 Üst Oran Filtresi'nden kaldırıldı; yalnızca Yüksek Oran Filtresi'nde kullanılır.
        oran_filter_cift_yari_15 = False
        # Kombo isteğe bağlıdır. İşaretli değilse hiçbir kombo hesabı yapılmaz.
        oran_filter_kombo = st.checkbox('Kombo', value=False, key='oran_filter_kombo')
        oran_filter_min_ornek = st.selectbox('Minimum benzer maç', [1, 2, 3, 5, 10, 15, 20], index=2, key='oran_filter_min_ornek')
        oran_filtresi_btn = False
    elif st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
        # Yüksek Oran Filtresi kutuları kullanıcı tarafından açılıp kapatılabilir.
        yf1, yf2 = st.columns(2)
        with yf1:
            yuksek_filtre_12 = st.checkbox('1/2', value=True, key='yuksek_filtre_12')
        with yf2:
            yuksek_filtre_21 = st.checkbox('2/1', value=True, key='yuksek_filtre_21')
        yf3, yf4 = st.columns(2)
        with yf3:
            yuksek_filtre_cift_yari_kg = st.checkbox(
                'İki yarıda da karşılıklı gol', value=True, key='yuksek_filtre_cift_yari_kg'
            )
        with yf4:
            yuksek_filtre_cift_yari_15 = st.checkbox(
                'İki yarı 1.5 Üst', value=True, key='yuksek_filtre_cift_yari_15'
            )
        yuksek_limit = st.selectbox('Maç başına geçmiş örnek', [10, 25, 50, 100], index=1, key='yuksek_limit')
        yuksek_oran_btn = False
    elif st.session_state.get('sayfa_modu') == 'Spor Toto':
        st.caption('15 maçı manuel tut; oranlar seçili liglerin The Odds API bülteninden eşleştirilir.')
        _spor_toto_varsayilan = '''11.09.2026 20:00 | Beşiktaş A.Ş. | Erzurumspor FK
12.09.2026 17:00 | Eyüpspor | Çaykur Rizespor A.Ş.
12.09.2026 17:00 | Samsunspor A.Ş. | Çorum FK
12.09.2026 20:00 | Alanyaspor | Göztepe A.Ş.
12.09.2026 20:00 | Konyaspor | Trabzonspor A.Ş.
13.09.2026 17:00 | Gençlerbirliği | Kasımpaşa A.Ş.
13.09.2026 20:00 | Amed Sportif | Başakşehir FK
13.09.2026 20:00 | Galatasaray A.Ş. | Kocaelispor
14.09.2026 20:00 | Gaziantep F.K. A.Ş. | Fenerbahçe A.Ş.
12.09.2026 16:30 | Augsburg | B. Leverkusen
11.09.2026 21:45 | Rennes | Marsilya
12.09.2026 17:00 | Chelsea | Hull City
13.09.2026 18:30 | Manchester United | Manchester City
13.09.2026 17:15 | Levante | Barcelona
12.09.2026 19:00 | Lazio | AC Milan'''
        spor_toto_metin = st.text_area(
            'Spor Toto maçları',
            value=st.session_state.get('spor_toto_metin', _spor_toto_varsayilan),
            height=330,
            key='spor_toto_metin',
            help='Her satır: GG.AA.YYYY SS:DD | Ev sahibi | Deplasman',
        )
        st.caption('Format: tarih saat | ev sahibi | deplasman · Haftalık yalnızca bu 15 satırı değiştirmen yeterli.')
    elif st.session_state.get('sayfa_modu') == 'Sonuç Takibi':
        st.caption("Kaydedilen analizlerin sonuçlarını buradan yenileyebilirsin.")
    elif st.session_state.get('sayfa_modu') == 'Canlı Takip':
        st.caption("Daha önce analiz edilmiş ve şu anda oynanan maçları takip eder.")
        canli_otomatik = st.toggle("5 dakikada otomatik yenile", value=False, key="canli_otomatik_yenile")
    else:
        analiz_btn = False

    if st.button('🎫 Kuponlarım', use_container_width=True, key='toggle_coupon_popup'):
        st.session_state.coupon_popup_open = True
        st.session_state.scroll_to_coupon = True
        st.rerun()

    if 'son_analiz' in st.session_state:
        st.markdown(
            f"<div class='summary-note'>Son analiz: {st.session_state.son_analiz}<br>Toplam maç: {st.session_state.get('toplam_mac',0)}</div>",
            unsafe_allow_html=True,
        )


legal_sidebar_sections()

# Ana analiz eylemi, sık kullanılan ayarlarla aynı üst satırda gösterilir.
if st.session_state.get('sayfa_modu') in ['Maç Analizi', 'Top 50 Market']:
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        analiz_btn = st.button(
            '▶ ANALİZİ BAŞLAT',
            use_container_width=True,
            type='primary',
            key='analiz_baslat_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Geçmiş Örnekleri':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        gecmis_btn = st.button(
            '🔎 ÖRNEKLERİ GETİR',
            use_container_width=True,
            type='primary',
            key='gecmis_getir_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Backtest':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        backtest_btn = st.button(
            '🧪 BACKTESTİ BAŞLAT',
            use_container_width=True,
            type='primary',
            key='backtest_baslat_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Oran Filtresi':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        oran_filtresi_btn = st.button(
            '🔎 ÖRNEKLERİ GETİR',
            use_container_width=True,
            type='primary',
            key='oran_filtresi_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        yuksek_oran_btn = st.button(
            '🔎 ÖRNEKLERİ GETİR',
            use_container_width=True,
            type='primary',
            key='yuksek_oran_getir_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Spor Toto':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        spor_toto_btn = st.button(
            '⚽ SPOR TOTO ANALİZ ET',
            use_container_width=True,
            type='primary',
            key='spor_toto_analiz_btn',
        )
elif st.session_state.get('sayfa_modu') == 'Sonuç Takibi':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        sonuc_yenile_btn = st.button(
            '🔄 SONUÇLARI YENİLE',
            use_container_width=True,
            type='primary',
            key='sonuclari_yenile_btn',
        )

def _spor_toto_satirlari_parse(metin):
    satirlar = []
    for no, raw in enumerate(str(metin or "").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        parca = [x.strip() for x in raw.split("|")]
        if len(parca) < 3:
            continue
        try:
            dt = datetime.strptime(parca[0], "%d.%m.%Y %H:%M")
        except Exception:
            try:
                dt = datetime.strptime(parca[0], "%d.%m.%Y")
            except Exception:
                continue
        satirlar.append({"no": no, "zaman": dt, "ev": parca[1], "dep": parca[2]})
    return satirlar


def _spor_toto_takim_benzerlik(a, b):
    """Spor Toto manuel takım adını API adlarıyla daha toleranslı eşleştir."""
    ka = takim_anahtari(a)
    kb = takim_anahtari(b)
    if not ka or not kb:
        return 0.0

    # Sık görülen manuel/API isim farklarını aynı kanonik ada indir.
    aliaslar = {
        "levante": "levanteud",
        "levanteud": "levanteud",
        "barcelona": "fcbarcelona",
        "fcbarcelona": "fcbarcelona",
        "bleverkusen": "bayerleverkusen",
        "bayer04leverkusen": "bayerleverkusen",
        "bayerleverkusen": "bayerleverkusen",
        "marsilya": "marseille",
        "olympiquedemarseille": "marseille",
        "marseille": "marseille",
        "basaksehirfk": "istanbulbasaksehir",
        "istanbulbasaksehir": "istanbulbasaksehir",
        "gaziantepfkas": "gaziantepfk",
        "gaziantepfk": "gaziantepfk",
        "galatasarayas": "galatasaray",
        "galatasaray": "galatasaray",
        "kocaelispor": "kocaelispor",
        "chelseafc": "chelsea",
        "chelsea": "chelsea",
        "hullcityafc": "hullcity",
        "hullcity": "hullcity",
        "besiktas": "besiktas",
        "besiktasjk": "besiktas",
        "besiktasjkas": "besiktas",
        "besiktasas": "besiktas",
        "erzurumspor": "erzurumspor",
        "erzurumsporfk": "erzurumspor",
        "bberzurumspor": "erzurumspor",
        "buyuksehirbelediyeerzurumspor": "erzurumspor",
    }
    ka = aliaslar.get(ka, ka)
    kb = aliaslar.get(kb, kb)

    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        return 0.94
    return SequenceMatcher(None, ka, kb).ratio()


def _spor_toto_eslestir(mac, bulten):
    """Önce aynı gün, bulunamazsa ±1 gün içinde güçlü takım adı eşleşmesi ara."""
    if bulten is None or getattr(bulten, "empty", True):
        return None, 0.0

    tum = bulten.copy()
    aramalar = []

    # 1) Önce manuel programdaki günün kendisi.
    if "zaman" in tum.columns:
        try:
            ayni_gun = tum[tum["zaman"].apply(lambda x: (dt := parse_mac_datetime(x)) is not None and dt.date() == mac["zaman"].date())]
            if not ayni_gun.empty:
                aramalar.append(ayni_gun)
        except Exception:
            pass

        # 2) Program/API tarihleri bir gün kayabiliyor. Takım adları güçlü eşleşiyorsa ±1 gün kabul et.
        try:
            yakin_gun = tum[tum["zaman"].apply(
                lambda x: (dt := parse_mac_datetime(x)) is not None and abs((dt.date() - mac["zaman"].date()).days) <= 1
            )]
            if not yakin_gun.empty:
                aramalar.append(yakin_gun)
        except Exception:
            pass

    if not aramalar:
        aramalar = [tum]

    en_iyi = None
    en_skor = 0.0
    for aday in aramalar:
        for _, row in aday.iterrows():
            evs = _spor_toto_takim_benzerlik(mac["ev"], row.get("ev", ""))
            deps = _spor_toto_takim_benzerlik(mac["dep"], row.get("dep", ""))
            skor = (evs + deps) / 2.0
            if skor > en_skor:
                en_skor = skor
                en_iyi = row
        # Çok güçlü eşleşme bulunduysa daha geniş tarih havuzuna gerek yok.
        if en_skor >= 0.88:
            break

    # Yanlış maça yapışmaması için iki takımın birlikte güçlü eşleşmesini şart koş.
    if en_skor < 0.72:
        return None, en_skor
    return en_iyi, en_skor


def _spor_toto_ms_tarama(gecmis_df, mac_row, min_ornek_val, toleranslar, ayni_lig=False):
    """Spor Toto MS taraması: tüm geçmiş liglerde 1/X/2 oran profili ara.

    Ana uygulamadaki hesapla() fonksiyonunu bilinçli olarak kullanmaz; çünkü o fonksiyon
    HT verisi eksik bazı ligleri güvenlik amacıyla tamamen dışarıda bırakır. Spor Toto
    burada yalnızca maç sonucu (1/X/2) kullandığı için FTR + kapanış oranı olan tüm
    geçmiş ligler güvenle örnek havuzuna dahil edilir.
    """
    if gecmis_df is None or getattr(gecmis_df, "empty", True):
        return []
    b0 = zaman_uyumlu_gecmis(tarih_oncesi_gecmis(gecmis_df, mac_row.get("zaman")), mac_row)
    if ayni_lig and "league_code" in b0.columns and mac_row.get("sport_key"):
        b0 = b0[b0["league_code"].astype(str) == str(ODDS_TO_HISTORY.get(mac_row.get("sport_key"), mac_row.get("sport_key")))].copy()
    if b0.empty or "FTR" not in b0.columns:
        return []

    ref_h = "REF_H" if "REF_H" in b0.columns else "B365H"
    ref_d = "REF_D" if "REF_D" in b0.columns else "B365D"
    ref_a = "REF_A" if "REF_A" in b0.columns else "B365A"
    if not all(c in b0.columns for c in [ref_h, ref_d, ref_a]):
        return []

    for c in [ref_h, ref_d, ref_a]:
        b0[c] = pd.to_numeric(b0[c], errors="coerce")
    b0 = b0.dropna(subset=[ref_h, ref_d, ref_a, "FTR"]).copy()
    if b0.empty:
        return []

    try:
        mh, md, ma = float(mac_row["h"]), float(mac_row["b"]), float(mac_row["a"])
    except Exception:
        return []

    taramalar = []
    gerekli = max(1, int(min_ornek_val or 1))
    for tol in toleranslar:
        tol = float(tol)
        b = b0.loc[oran_eslesme_maskesi(b0, mac_row, tol)].copy()
        if b.empty:
            continue
        seri = b["FTR"].dropna().astype(str)
        if len(seri) < gerekli:
            continue
        weights, _, _ = analiz_agirliklari(b, mac_row, tol)
        effective = etkin_ornek(weights)
        # Gerçek maç sayısı yukarıda denetlendi; etkin sayı yalnızca güveni dengeler.
        vc = weights.groupby(b["FTR"]).sum() / weights.sum()
        vc = pd.Series({side: tabana_yaklastir(float(vc.get(side, 0)), effective, 1/3)
                        for side in ("H", "D", "A")})
        taraf_map = {"H": "1", "D": "X", "A": "2"}
        mod = str(vc.idxmax()) if not vc.empty else "D"
        taraf = taraf_map.get(mod, "X")
        dagilim = {
            "1": float(vc.get("H", 0.0)) * 100.0,
            "X": float(vc.get("D", 0.0)) * 100.0,
            "2": float(vc.get("A", 0.0)) * 100.0,
        }
        yuzde = float(dagilim.get(taraf, 0.0))
        taramalar.append({
            "tol": tol, "taraf": taraf, "yuzde": yuzde, "ornek": len(seri),
            "p1": dagilim["1"], "px": dagilim["X"], "p2": dagilim["2"],
        })
    return taramalar


def _spor_toto_en_yakin_oran_fallback(gecmis_df, mac_row, min_ornek_val=5):
    """Hiç tolerans kutusu dolmazsa tüm liglerde en yakın oran profillerini kullan.

    Bu yalnızca Spor Toto için son çaredir. Toleransı sonsuza kadar büyütmek yerine
    H/X/A üçlüsüne log-oran mesafesi en düşük geçmiş maçlar seçilir.
    """
    if gecmis_df is None or getattr(gecmis_df, "empty", True) or "FTR" not in gecmis_df.columns:
        return None
    b = zaman_uyumlu_gecmis(tarih_oncesi_gecmis(gecmis_df, mac_row.get("zaman")), mac_row)
    ref_h = "REF_H" if "REF_H" in b.columns else "B365H"
    ref_d = "REF_D" if "REF_D" in b.columns else "B365D"
    ref_a = "REF_A" if "REF_A" in b.columns else "B365A"
    if not all(c in b.columns for c in [ref_h, ref_d, ref_a]):
        return None
    for c in [ref_h, ref_d, ref_a]:
        b[c] = pd.to_numeric(b[c], errors="coerce")
    b = b.dropna(subset=[ref_h, ref_d, ref_a, "FTR"]).copy()
    if b.empty:
        return None
    try:
        mh, md, ma = float(mac_row["h"]), float(mac_row["b"]), float(mac_row["a"])
    except Exception:
        return None
    if min(mh, md, ma) <= 0:
        return None

    import numpy as np
    # Şirketler farklıysa hem hedef hem geçmiş marjdan arındırılır.
    compare, current = eslesme_oranlari(b, mac_row)
    b["_st_dist"] = np.log(compare).sub(np.log(current), axis=1).pow(2).sum(axis=1).pow(.5)
    b = b.sort_values("_st_dist")
    n = max(5, min(12, int(min_ornek_val or 5)))
    yakin = b.head(n).copy()
    if len(yakin) < 3:
        return None
    seri = yakin["FTR"].dropna().astype(str)
    if len(seri) < 3:
        return None
    weights = 1 / (1 + yakin["_st_dist"].pow(2))
    weights *= zaman_agirliklari(yakin, mac_row)
    effective = etkin_ornek(weights)
    vc = weights.groupby(yakin["FTR"]).sum() / weights.sum()
    vc = pd.Series({side: tabana_yaklastir(float(vc.get(side, 0)), effective, 1/3)
                    for side in ("H", "D", "A")})
    dagilim = {
        "1": float(vc.get("H", 0.0)) * 100.0,
        "X": float(vc.get("D", 0.0)) * 100.0,
        "2": float(vc.get("A", 0.0)) * 100.0,
    }
    taraf = max(("1", "X", "2"), key=lambda x: (dagilim[x], {"X": 0, "1": 1, "2": 1}[x]))
    # Bu sonuç 11 hassasiyet uzlaşısı değildir; yalnızca en yakın gerçek oran profillerinin dağılımıdır.
    return {
        "secim": taraf,
        "guven": round(dagilim[taraf], 1),
        "kararlilik": 0,
        "gecerli": 0,
        "ornek": len(seri),
        "hass": [],
        "spor_toto_faz": "en yakın oran fallback",
        "spor_toto_min_ornek": len(seri),
        "spor_toto_dagilim": {k: round(v, 1) for k, v in dagilim.items()},
        "spor_toto_veri_kalitesi": "Çok düşük",
        "spor_toto_fallback": True,
    }

def _spor_toto_ms_11_hesapla(gecmis_df, mac_row, min_ornek_val, ayni_lig=False):
    """Normal 0.00–0.10 tarama; veri yoksa yalnız Spor Toto'da kontrollü fallback."""
    normal_min = max(1, int(min_ornek_val or 1))
    fazlar = [
        # Standart model: mevcut 11 hassasiyet aynen korunur.
        ([i / 100.0 for i in range(11)], normal_min, "standart"),
        # Örnek yoksa hassasiyet biraz genişletilir ve minimum örnek kontrollü düşürülür.
        ([i * 0.015 for i in range(11)], max(5, min(normal_min, max(5, normal_min // 2))), "fallback 0.15"),
        # Son çare: 0.00–0.20, en az 3 gerçek geçmiş maç. Veri yoksa tahmin yine üretilmez.
        ([i * 0.02 for i in range(11)], 3, "fallback 0.20"),
    ]

    taramalar = []
    kullanilan_faz = "standart"
    kullanilan_min = normal_min
    for toleranslar, faz_min, faz_adi in fazlar:
        taramalar = _spor_toto_ms_tarama(
            gecmis_df, mac_row, faz_min, toleranslar, ayni_lig=ayni_lig
        )
        if taramalar:
            kullanilan_faz = faz_adi
            kullanilan_min = faz_min
            break

    if not taramalar:
        # Tüm liglerde 0.00–0.20 kutusu yine boşsa en yakın gerçek oran profillerine git.
        return _spor_toto_en_yakin_oran_fallback(gecmis_df, mac_row, normal_min)

    sayim = pd.Series([x["taraf"] for x in taramalar]).value_counts()
    en_cok = int(sayim.max())
    aday_taraflar = list(sayim[sayim == en_cok].index)

    def _ort(taraf):
        vals = [x["yuzde"] for x in taramalar if x["taraf"] == taraf]
        return sum(vals) / len(vals) if vals else 0.0

    secim = max(aday_taraflar, key=_ort)
    secim_kayitlari = [x for x in taramalar if x["taraf"] == secim]

    # Kolon üretiminde mekanik 1->X/2 döngüsü yerine gerçek geçmiş 1/X/2
    # dağılımını kullan. Her geçerli hassasiyet eşit oy taşır; böylece geniş
    # toleransın yüksek örnek sayısı tek başına sonucu ezmez.
    dagilim = {
        "1": sum(float(x.get("p1", 0.0)) for x in taramalar) / len(taramalar),
        "X": sum(float(x.get("px", 0.0)) for x in taramalar) / len(taramalar),
        "2": sum(float(x.get("p2", 0.0)) for x in taramalar) / len(taramalar),
    }
    kalite = {
        "standart": "Yüksek",
        "fallback 0.15": "Orta",
        "fallback 0.20": "Düşük",
    }.get(kullanilan_faz, "Düşük")
    return {
        "secim": secim,
        # Güven artık yalnız secimin kazandığı hassasiyetlerin değil, tüm geçerli
        # hassasiyetlerdeki aynı taraf oranının ortalamasıdır.
        "guven": round(float(dagilim.get(secim, 0.0)), 1),
        "kararlilik": len(secim_kayitlari),
        "gecerli": len(taramalar),
        "ornek": max(x["ornek"] for x in secim_kayitlari),
        "hass": [x["tol"] for x in secim_kayitlari],
        "spor_toto_faz": kullanilan_faz,
        "spor_toto_min_ornek": kullanilan_min,
        "spor_toto_dagilim": {k: round(v, 1) for k, v in dagilim.items()},
        "spor_toto_veri_kalitesi": kalite,
        "spor_toto_fallback": kullanilan_faz != "standart",
    }


if spor_toto_btn:
    spor_maclar = _spor_toto_satirlari_parse(st.session_state.get('spor_toto_metin', ''))
    if len(spor_maclar) != 15:
        st.warning(f"Spor Toto için 15 geçerli maç bekleniyor; şu an {len(spor_maclar)} satır okundu.")
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Oranları eşleştirmek için API Key ve ilgili ligleri seçin.")
    elif spor_maclar:
        with st.spinner("⚽ Spor Toto maçları bültenle eşleştiriliyor ve 11 hassasiyet taranıyor..."):
            gecmis_st = futbol_veri_motoru(tuple(yillar))
            tarih_bultenleri = []
            for gun in sorted({x["zaman"].date() for x in spor_maclar}):
                df_gun = bulten_saglam_al(API_KEY, secili_kodlar, gun)
                if isinstance(df_gun, pd.DataFrame) and not df_gun.empty:
                    tarih_bultenleri.append(df_gun)
            st_bulten = pd.concat(tarih_bultenleri, ignore_index=True) if tarih_bultenleri else pd.DataFrame()
            if not st_bulten.empty and all(c in st_bulten.columns for c in ["ev", "dep", "zaman"]):
                st_bulten = st_bulten.drop_duplicates(subset=["ev", "dep", "zaman"])
            sonuclar = []
            for sm in spor_maclar:
                es, es_skor = _spor_toto_eslestir(sm, st_bulten)
                if es is None:
                    sonuclar.append({**sm, "durum": "Eşleşmedi", "es_skor": es_skor})
                    continue
                # Spor Toto: geçmiş örnekleri lig ayrımı yapmadan tüm seçili geçmiş liglerde ara.
                # Ana uygulamadaki "sadece_ayni_lig" ayarı Spor Toto'yu etkilemez.
                ist = _spor_toto_ms_11_hesapla(gecmis_st, es, min_ornek, False)
                if ist is None:
                    sonuclar.append({**sm, "durum": "Örnek yok", "es_skor": es_skor, "api_ev": es.get("ev"), "api_dep": es.get("dep")})
                    continue
                _faz = str(ist.get("spor_toto_faz", "standart"))
                _durum = "Tamam" if _faz == "standart" else f"Tamam · {_faz}"
                sonuclar.append({**sm, "durum": _durum, "es_skor": es_skor, "api_ev": es.get("ev"), "api_dep": es.get("dep"), **ist})
            st.session_state['spor_toto_sonuclar'] = sonuclar
        st.rerun()

if st.session_state.get('sayfa_modu') == 'Spor Toto':
    st.markdown("### ⚽ Spor Toto · 15 Maç")
    st.caption("Maç adları manuel; oranlar seçili liglerin cache'lenmiş The Odds API bülteninden eşleştirilir. MS 1/X/2 için önce 0.00–0.10 taranır; örnek yoksa yalnız Spor Toto'da kontrollü 0.15/0.20 ve en yakın oran fallback uygulanır.")
    _st_sonuclar = st.session_state.get('spor_toto_sonuclar', [])
    if not _st_sonuclar:
        st.info("15 maçı kontrol ettikten sonra **⚽ SPOR TOTO ANALİZ ET** butonuna bas.")
    else:
        tablo = []
        for r in _st_sonuclar:
            if str(r.get('durum', '')).startswith('Tamam'):
                tahmin = str(r.get('secim', '—'))
                guven = f"%{float(r.get('guven', 0)):.1f}"
                _faz = str(r.get('spor_toto_faz', 'standart'))
                kar = '—' if _faz == 'en yakın oran fallback' else f"{int(r.get('kararlilik',0))}/{max(int(r.get('gecerli',11)),1)}"
                dag = r.get('spor_toto_dagilim') or {}
                dag_txt = (f"1 %{float(dag.get('1',0)):.1f} · X %{float(dag.get('X',0)):.1f} · 2 %{float(dag.get('2',0)):.1f}" if dag else '—')
                kalite = str(r.get('spor_toto_veri_kalitesi', '—'))
            else:
                tahmin, guven, kar, dag_txt, kalite = '—', '—', '—', '—', '—'
            tablo.append({
                '#': r.get('no'),
                'Tarih': r.get('zaman').strftime('%d.%m.%Y %H:%M') if r.get('zaman') else '',
                'Maç': f"{r.get('ev')} - {r.get('dep')}",
                'Tahmin': tahmin,
                'Güven': guven,
                '1 / X / 2': dag_txt,
                'Kararlılık': kar,
                'Örnek': r.get('ornek', '—'),
                'Veri Kalitesi': kalite,
                'Durum': r.get('durum', ''),
            })
        st.dataframe(pd.DataFrame(tablo), use_container_width=True, hide_index=True)

        tamam = [r for r in _st_sonuclar if str(r.get('durum', '')).startswith('Tamam')]
        if tamam:
            st.markdown("#### Kolon önerileri")

            def _st_alternatifler(r, gevseklik=0):
                """Gerçek 1/X/2 dağılımından kademeli alternatif üret.

                gevseklik=0: çekirdek alternatifler
                gevseklik=1: orta güvenli alternatifler
                gevseklik=2: geniş kapsama (yalnız çok kolonlu kuponlarda)

                X'e yapay ayrıcalık verilmez; 1/X/2 aynı olasılık ve fark
                kurallarıyla değerlendirilir.
                """
                dag = r.get('spor_toto_dagilim') or {}
                if not dag:
                    return []
                ana = str(r.get('secim', ''))
                ana_p = float(dag.get(ana, r.get('guven', 0)) or 0)
                faz = str(r.get('spor_toto_faz', 'standart'))

                if faz == 'en yakın oran fallback':
                    esikler = [(28.0, 10.0), (26.0, 13.0), (24.0, 16.0)]
                else:
                    esikler = [(25.0, 12.0), (23.0, 15.0), (21.0, 18.0)]

                min_p, max_fark = esikler[max(0, min(int(gevseklik), 2))]
                adaylar = []
                for taraf in ('1', 'X', '2'):
                    if taraf == ana:
                        continue
                    p = float(dag.get(taraf, 0) or 0)
                    fark = ana_p - p
                    if p >= min_p and fark <= max_fark:
                        # Yakınlık skoru: yüksek olasılık + ana sonuca yakınlık.
                        yakinlik = p - max(0.0, fark) * 0.35
                        adaylar.append((taraf, p, fark, yakinlik))
                return sorted(adaylar, key=lambda x: (x[3], x[1], -x[2]), reverse=True)

            # Kuponun belirsizliğini ölç. Kolon sayısı artık 4/6/8/10'a kilitlenmez.
            guvenler = [float(r.get('guven', 0) or 0) for r in tamam]
            ort_guven = sum(guvenler) / len(guvenler) if guvenler else 0.0
            alternatifli_mac = sum(1 for r in tamam if _st_alternatifler(r, 0))
            fallback_mac = sum(
                1 for r in tamam
                if str(r.get('spor_toto_faz', 'standart')) != 'standart'
            )
            dusuk_guvenli_mac = sum(1 for g in guvenler if g < 55.0)

            # Her maç için modelin gerçek dağılımla desteklediği seçenekleri hazırla.
            # Geniş havuz kullanılır; zayıf alternatifler aşağıdaki olasılık/fayda
            # hesabında doğal olarak elenir. X'e özel ayrıcalık verilmez.
            mac_nolari = [r['no'] for r in tamam]
            secenek_havuzu = []
            ana_imza = []
            for r in tamam:
                dag = r.get('spor_toto_dagilim') or {}
                ana = str(r.get('secim', ''))
                ana_p = float(dag.get(ana, r.get('guven', 0)) or 0)
                ana_imza.append(ana)

                secenekler = [(ana, max(ana_p, 0.1))]
                for taraf, p, fark, yakinlik in _st_alternatifler(r, 2):
                    if taraf != ana:
                        secenekler.append((taraf, max(float(p), 0.1)))

                tekil = {}
                for taraf, p in secenekler:
                    tekil[taraf] = max(float(p), float(tekil.get(taraf, 0.0)))
                secenek_havuzu.append((r['no'], list(tekil.items())))

            ana_imza = tuple(ana_imza)

            # Zor haftalarda daha fazla senaryo aranabilir; kolay haftalarda gereksiz
            # uç kombinasyonlar üretilmez. Bu bir kolon hedefi değil, arama güvenliğidir.
            if ort_guven >= 62.0:
                MAX_DEGISIKLIK = 3
            elif ort_guven >= 56.0:
                MAX_DEGISIKLIK = 4
            elif ort_guven >= 50.0:
                MAX_DEGISIKLIK = 5
            else:
                MAX_DEGISIKLIK = 6
            if fallback_mac >= 3:
                MAX_DEGISIKLIK = min(7, MAX_DEGISIKLIK + 1)

            BEAM_LIMIT = 2000
            GUVENLIK_KOLON_TAVANI = 64

            # Beam-search: en olası gerçek 1/X/2 senaryolarını çıkar.
            beam = [(0.0, tuple(), 0)]
            for idx, (mac_no, secenekler) in enumerate(secenek_havuzu):
                ana = ana_imza[idx]
                yeni_beam = []
                for skor, imza, degisim in beam:
                    for taraf, p in secenekler:
                        yeni_degisim = degisim + (1 if taraf != ana else 0)
                        if yeni_degisim > MAX_DEGISIKLIK:
                            continue
                        yeni_skor = skor + math.log(max(float(p), 0.1) / 100.0)
                        yeni_beam.append((yeni_skor, imza + (taraf,), yeni_degisim))

                tekil_beam = {}
                for skor, imza, degisim in yeni_beam:
                    onceki = tekil_beam.get(imza)
                    if onceki is None or skor > onceki[0]:
                        tekil_beam[imza] = (skor, imza, degisim)
                beam = sorted(
                    tekil_beam.values(),
                    key=lambda x: (x[0], -x[2]),
                    reverse=True
                )[:BEAM_LIMIT]

            def _hamming(a, b):
                return sum(1 for x, y in zip(a, b) if x != y)

            # Ana kolonun log-olasılığı. Diğer kolonların göreli ihtimali bununla
            # kıyaslanır; böylece sırf farklı diye çok zayıf kolon eklenmez.
            ana_skor = 0.0
            for idx, (_, secenekler) in enumerate(secenek_havuzu):
                ana = ana_imza[idx]
                ana_p = next((float(p) for taraf, p in secenekler if taraf == ana), 0.1)
                ana_skor += math.log(max(ana_p, 0.1) / 100.0)

            adaylar = []
            for skor, imza, degisim in beam:
                if imza == ana_imza:
                    continue
                goreli_olasilik = math.exp(min(0.0, float(skor) - ana_skor))
                adaylar.append({
                    'skor': float(skor),
                    'imza': imza,
                    'degisim': int(degisim),
                    'goreli': float(goreli_olasilik),
                })

            secilen_imzalar = [ana_imza]

            # Ortalama güven düştükçe daha düşük marjinal faydaya sahip kolonlara
            # izin ver. Fallback arttıkça eşik biraz daha gevşer.
            if ort_guven >= 62.0:
                taban_fayda_esigi = 0.42
            elif ort_guven >= 56.0:
                taban_fayda_esigi = 0.32
            elif ort_guven >= 50.0:
                taban_fayda_esigi = 0.24
            else:
                taban_fayda_esigi = 0.18
            taban_fayda_esigi = max(0.12, taban_fayda_esigi - min(fallback_mac, 3) * 0.03)

            def _aday_degeri(aday):
                # Olasılık ana ölçüt. Çeşitlilik küçük bonus alır; bonus hiçbir zaman
                # zayıf bir senaryoyu güçlü bir senaryonun önüne tek başına taşımaz.
                min_mesafe = min(_hamming(aday['imza'], s) for s in secilen_imzalar)
                cesitlilik = 1.0 + 0.10 * min(min_mesafe, 3) + 0.04 * min(aday['degisim'], 4)
                return aday['goreli'] * cesitlilik

            # En az birkaç anlamlı alternatif varsa 4 kolona kadar kapsama sağla;
            # sonrasında yalnız ek faydası eşiğin üzerinde kalan kolonları ekle.
            MIN_KOLON = min(4, 1 + len(adaylar))
            son_fayda = None
            while adaylar and len(secilen_imzalar) < GUVENLIK_KOLON_TAVANI:
                uygun = [a for a in adaylar if a['imza'] not in secilen_imzalar]
                if not uygun:
                    break
                en_iyi = max(uygun, key=_aday_degeri)
                fayda = _aday_degeri(en_iyi)

                # Kolon sayısı büyüdükçe yeni kolonun kendini daha fazla hak etmesi gerekir.
                buyume_cezasi = 1.0 + max(0, len(secilen_imzalar) - 4) * 0.018
                etkin_esik = taban_fayda_esigi * buyume_cezasi
                if len(secilen_imzalar) >= MIN_KOLON and fayda < etkin_esik:
                    son_fayda = fayda
                    break

                secilen_imzalar.append(en_iyi['imza'])
                adaylar.remove(en_iyi)
                son_fayda = fayda

            kolonlar = {}
            for k, imza in enumerate(secilen_imzalar, start=1):
                kolonlar[k] = {no: secim for no, secim in zip(mac_nolari, imza)}
            kolon_sayisi = len(kolonlar)

            iki_farkli_sayisi = sum(
                1 for imza in secilen_imzalar[1:]
                if _hamming(imza, ana_imza) >= 2
            )
            st.caption(
                f"Dinamik sistem {kolon_sayisi} benzersiz kolon seçti. "
                f"Ortalama güven %{ort_guven:.1f} · çekirdek alternatifli maç {alternatifli_mac} · "
                f"fallback maç {fallback_mac} · arama değişiklik sınırı {MAX_DEGISIKLIK}. "
                f"1. kolon ana modeldir; diğer {max(0, kolon_sayisi-1)} kolonun "
                f"{iki_farkli_sayisi} tanesi ana kolondan en az 2 maç farklıdır. "
                "Kolon sayısı artık 4/6/8/10'a sabitlenmez; yalnızca marjinal faydası yeterli "
                f"senaryolar eklenir. {GUVENLIK_KOLON_TAVANI} kolon yalnız güvenlik tavanıdır, hedef değildir."
            )

            # Arka planda üretilen kolonlar kalite sırasındadır. Kullanıcı yalnızca
            # bu sıralamanın ilk N kolonunu görüntüler; seçim algoritmayı yeniden çalıştırmaz.
            gosterim_secenekleri = [n for n in (8, 16, 32, 64) if n <= kolon_sayisi]
            if kolon_sayisi not in gosterim_secenekleri:
                gosterim_secenekleri.append(kolon_sayisi)
            gosterim_secenekleri = sorted(set(gosterim_secenekleri))
            varsayilan_gosterim = 32 if 32 in gosterim_secenekleri else gosterim_secenekleri[-1]
            gosterilecek_kolon = st.selectbox(
                "Gösterilecek en iyi kolon",
                options=gosterim_secenekleri,
                index=gosterim_secenekleri.index(varsayilan_gosterim),
                format_func=lambda n: f"En iyi {n} kolon",
                key="spor_toto_gosterilecek_kolon",
                help="Model kolonları kalite sırasına dizer. Örneğin 8 seçersen üretilen havuzdaki en iyi ilk 8 kolon gösterilir.",
            )
            st.caption(
                f"Model toplam {kolon_sayisi} kolon üretti · Şu anda kalite sırasındaki "
                f"en iyi {gosterilecek_kolon} kolon gösteriliyor."
            )

            gor = []
            for r in _st_sonuclar:
                if not str(r.get('durum', '')).startswith('Tamam'):
                    continue
                dag = r.get('spor_toto_dagilim') or {}
                dag_txt = (f"1 %{float(dag.get('1',0)):.1f} · X %{float(dag.get('X',0)):.1f} · 2 %{float(dag.get('2',0)):.1f}" if dag else '—')
                satir = {
                    '#': r['no'], 'Maç': f"{r['ev']} - {r['dep']}",
                    'Dağılım': dag_txt,
                }
                for k in range(1, int(gosterilecek_kolon) + 1):
                    satir[f'{k}. Kolon'] = kolonlar[k].get(r['no'], '—')
                gor.append(satir)
            st.dataframe(pd.DataFrame(gor), use_container_width=True, hide_index=True)
    legal_footer()
    st.stop()

if gecmis_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("🔎 Günün maçları ve geçmiş benzer örnekler hazırlanıyor..."):
            gi_gecmis = futbol_veri_motoru(tuple(yillar))
            gi_bulten = bulten_saglam_al(API_KEY, secili_kodlar, secili_tarih)
            inceleme = []
            for _, gi_mac in gi_bulten.iterrows():
                ornekler = gecmis_ornekleri_bul(
                    gi_gecmis,
                    gi_mac,
                    TOLERANS,
                    sadece_ayni_lig=sadece_ayni_lig,
                    limit=gecmis_limit,
                )
                # Satır başlığında aynı lig / toplam örnek sayısını gösterebilmek için
                # toplam örnek sayısını ayrıca sakla. Aynı lig filtresi kapalıysa
                # mevcut sonuç zaten toplam örnek listesidir; ekstra hesap yapma.
                if sadece_ayni_lig:
                    tum_ornekler = gecmis_ornekleri_bul(
                        gi_gecmis,
                        gi_mac,
                        TOLERANS,
                        sadece_ayni_lig=False,
                        limit=gecmis_limit,
                    )
                    tum_ornek_sayisi = int(len(tum_ornekler))
                else:
                    tum_ornek_sayisi = int(len(ornekler))
                inceleme.append({
                    "m": gi_mac.to_dict(),
                    "ornekler": ornekler,
                    "tum_ornek_sayisi": tum_ornek_sayisi,
                })
            # Geçmiş Örnekleri sıralaması:
            # 1) İY, MS, 2.5 veya KG içindeki EN YÜKSEK YÜZDE çoktan aza
            # 2) En yüksek yüzde eşitse toplam örnek sayısı çoktan aza
            inceleme.sort(key=gecmis_ornek_siralama_anahtari, reverse=True)
            st.session_state.gecmis_inceleme_list = inceleme
            st.rerun()

if st.session_state.get('sayfa_modu') == 'Geçmiş Örnekleri':
    inceleme = st.session_state.get("gecmis_inceleme_list")
    if inceleme is None:
        st.info("Lig, tarih ve filtreleri seçip GEÇMİŞ ÖRNEKLERİ GETİR butonuna bas.")
    elif not inceleme:
        st.warning("Bu tarih ve özel filtrelerle eşleşen maç bulunamadı.")
    else:
        # Eski session verisi kalmış olsa bile aynı gelişmiş sıralamayı uygula.
        inceleme = sorted(
            inceleme,
            key=gecmis_ornek_siralama_anahtari,
            reverse=True,
        )
        st.success(f"{len(inceleme)} güncel maç bulundu.")

        # Geçmiş Örnekleri için hızlı görünüm/filtre anahtarları.
        # İki aynı-lig kontrolü çift yönlü callback ile tek ayar gibi çalışır.
        mevcut_ayni_lig = bool(st.session_state.get("sadece_ayni_lig", False))
        if "gecmis_sadece_ayni_lig_toggle" not in st.session_state:
            st.session_state["gecmis_sadece_ayni_lig_toggle"] = mevcut_ayni_lig
        if "gecmis_ayni_lig_uygulandi" not in st.session_state:
            st.session_state["gecmis_ayni_lig_uygulandi"] = mevcut_ayni_lig
        if "gecmis_oranlari_goster" not in st.session_state:
            st.session_state["gecmis_oranlari_goster"] = False

        ust_bos, ust_ayni, ust_oran = st.columns([6.2, 1.45, 1.25], gap="small")
        with ust_ayni:
            gecmis_ayni_lig = st.toggle(
                "Sadece aynı ligler",
                key="gecmis_sadece_ayni_lig_toggle",
                help="Açıkken geçmiş örnekler yalnızca güncel maçın kendi liginden alınır. Her maç satırında aynı lig / toplam örnek sayısı gösterilir.",
                on_change=sync_ayni_lig_gecmisten_globale,
            )
        with ust_oran:
            gecmis_oranlari_goster = st.toggle(
                "Oranları göster",
                key="gecmis_oranlari_goster",
                help="Kapatınca maç başlığındaki ve geçmiş tablo içindeki 1-X-2 oranları gizlenir.",
            )

        # Aynı lig anahtarı değiştiyse mevcut maç listesini API'ye tekrar gitmeden
        # yalnızca yerel/tarihsel veriyle yeniden hesapla. Karşılaştırmayı global
        # widget ile değil, bu listenin en son uygulanan durumuyla yapıyoruz; böylece
        # AÇIK -> KAPALI geçişinde de eski (tüm ligler) görünüm geri gelir.
        gecmis_ayni_lig_uygulandi = bool(st.session_state.get("gecmis_ayni_lig_uygulandi", mevcut_ayni_lig))
        if bool(gecmis_ayni_lig) != gecmis_ayni_lig_uygulandi:
            # `sadece_ayni_lig` anahtarı sayfanın başka yerinde zaten bir widget key'i
            # olarak oluşturulmuş olabilir. Widget oluşturulduktan sonra aynı key'e
            # session_state üzerinden değer yazmak StreamlitWidgetAlreadyInstantiatedError
            # üretir. Bu yüzden Geçmiş Örnekleri anahtarını bağımsız tutup yalnızca
            # bu görünümün örneklerini yeniden hesaplıyoruz.
            gi_gecmis_yeniden = futbol_veri_motoru(tuple(yillar))
            yeniden = []
            for eski_item in inceleme:
                gi_mac_dict = dict(eski_item.get("m", {}) or {})
                gi_mac_series = pd.Series(gi_mac_dict)
                yeni_ornekler = gecmis_ornekleri_bul(
                    gi_gecmis_yeniden,
                    gi_mac_series,
                    TOLERANS,
                    sadece_ayni_lig=bool(gecmis_ayni_lig),
                    limit=gecmis_limit,
                )
                # Toggle açıkken satırda "aynı lig / toplam" gösterebilmek için
                # toplam örnek sayısını filtresiz olarak ayrıca hesapla.
                if bool(gecmis_ayni_lig):
                    tum_ornekler = gecmis_ornekleri_bul(
                        gi_gecmis_yeniden,
                        gi_mac_series,
                        TOLERANS,
                        sadece_ayni_lig=False,
                        limit=gecmis_limit,
                    )
                    tum_ornek_sayisi = int(len(tum_ornekler))
                else:
                    tum_ornek_sayisi = int(len(yeni_ornekler))
                yeniden.append({
                    "m": gi_mac_dict,
                    "ornekler": yeni_ornekler,
                    "tum_ornek_sayisi": tum_ornek_sayisi,
                })
            yeniden.sort(key=gecmis_ornek_siralama_anahtari, reverse=True)
            st.session_state.gecmis_inceleme_list = yeniden
            st.session_state["gecmis_ayni_lig_uygulandi"] = bool(gecmis_ayni_lig)
            st.rerun()

        # Geçmiş maç başlıklarını eskisi gibi aralıksız/kompakt göster.
        # Key'li container'lar Streamlit'in varsayılan dikey boşluğunu taşıdığı için
        # negatif alt marj ile yalnızca bu görünümde arayı kapatıyoruz.
        st.markdown(
            """
            <style>
            [class*="st-key-gecmis_mac_baslik_"] {
                margin:0 !important;
                padding:0 !important;
            }
            [class*="st-key-gecmis_mac_baslik_"] > div[data-testid="stVerticalBlock"] {
                gap:0 !important;
                margin:0 !important;
                padding:0 !important;
            }
            /* Maç kartlarını taşıyan ana Streamlit dikey bloğunda ekstra satır aralığı bırakma. */
            div[data-testid="stVerticalBlock"]:has(> div [class*="st-key-gecmis_mac_baslik_"]) {
                gap:0 !important;
            }
            [class*="st-key-gecmis_mac_baslik_"] div[data-testid="stElementContainer"] {
                margin-top:0 !important;
                margin-bottom:0 !important;
            }
            /* Geçmiş maç başlıklarını olabildiğince dip dibe getir.
               Streamlit'in key'li container çevresinde bıraktığı dikey alanı da sıfırla. */
            [class*="st-key-gecmis_mac_baslik_"] {
                margin-top:0 !important;
                margin-bottom:-10px !important;
                padding-top:0 !important;
                padding-bottom:0 !important;
            }
            [class*="st-key-gecmis_mac_baslik_"] > div[data-testid="stVerticalBlock"],
            [class*="st-key-gecmis_mac_baslik_"] > div[data-testid="stVerticalBlockBorderWrapper"],
            [class*="st-key-gecmis_mac_baslik_"] [data-testid="stVerticalBlockBorderWrapper"] {
                margin-top:0 !important;
                margin-bottom:0 !important;
                padding-top:0 !important;
                padding-bottom:0 !important;
                gap:0 !important;
            }
            /* Kapalı maç satırının yüksekliğini de biraz azalt; içerik açılınca tablo etkilenmez. */
            [class*="st-key-gecmis_mac_baslik_"] [data-testid="stExpander"] summary {
                min-height:38px !important;
                padding-top:4px !important;
                padding-bottom:4px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        for sira, item in enumerate(inceleme, start=1):
            m = item["m"]
            ornekler = item["ornekler"]
            saat = m["zaman"].strftime("%H:%M") if hasattr(m.get("zaman"), "strftime") else ""
            ozet = gecmis_ornek_ozeti(ornekler)
            iy_sonuc, _, iy_pct = ozet["iy"]
            ms_sonuc, _, ms_pct = ozet["ms"]
            ou_sonuc, _, ou_pct = ozet["ou25"]
            kg_sonuc, _, kg_pct = ozet["kg"]
            # Sağdaki özet değerlerinden yüzdesi en yüksek olanı ayrı renkle vurgula.
            # Eşitlik varsa aynı en yüksek yüzdeye sahip olanların hepsi vurgulanır.
            # Geçmiş Örnekleri başlığında İlk Yarı (İY) özetini gösterme.
            # İY verisi detay/tablo tarafında korunur; yalnızca başlık özetinden çıkarılır.
            ozetler = [
                ("MS", ms_sonuc, float(ms_pct)),
                ("2.5", ou_sonuc, float(ou_pct)),
                ("KG", kg_sonuc, float(kg_pct)),
            ]
            max_ozet_pct = max((x[2] for x in ozetler), default=0.0)
            koyu_aktif = bool(st.session_state.get("koyu_mod", False))
            normal_renk = "#67e8f9" if koyu_aktif else "#0369a1"
            guclu_renk = "#facc15" if koyu_aktif else "#b45309"

            if len(ornekler) > 0:
                ozet_html_parcalar = []
                for idx_ozet, (etiket_ozet, sonuc_ozet, pct_ozet) in enumerate(ozetler):
                    guclu_class = " gecmis-ozet-en-guclu" if pct_ozet == max_ozet_pct else ""
                    ayirici = '<span class="gecmis-ozet-ayirici"> · </span>' if idx_ozet else ""
                    ozet_html_parcalar.append(
                        ayirici
                        + f'<span class="gecmis-ozet-deger{guclu_class}">{escape(etiket_ozet)} {escape(str(sonuc_ozet))} %{pct_ozet:.0f}</span>'
                    )
                tekrar_ozeti_html = "".join(ozet_html_parcalar)
            else:
                # 0 örnekte sağ tarafta anlamsız %0 değerleri gösterme.
                tekrar_ozeti_html = ""

            with st.container(key=f"gecmis_mac_baslik_{sira}"):
                st.markdown(
                    f"""
                    <style>
                    .st-key-gecmis_mac_baslik_{sira} {{
                        position:relative !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] summary {{
                        display:flex !important;
                        align-items:center !important;
                        width:100% !important;
                        padding-right:min(390px, 42vw) !important;
                        overflow:hidden !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] summary p {{
                        overflow:hidden !important;
                        text-overflow:ellipsis !important;
                        white-space:nowrap !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} .gecmis-ozet-sag {{
                        position:absolute !important;
                        right:14px !important;
                        top:54px !important;
                        transform:translateY(-50%) !important;
                        z-index:18 !important;
                        max-width:min(380px, 41vw) !important;
                        overflow:hidden !important;
                        text-overflow:ellipsis !important;
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                        font-weight:800 !important;
                        font-size:clamp(.68rem, .72vw, .84rem) !important;
                        letter-spacing:0 !important;
                        white-space:nowrap !important;
                        pointer-events:none !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} .gecmis-ozet-sag .gecmis-ozet-deger {{
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} .gecmis-ozet-sag .gecmis-ozet-en-guclu {{
                        color:{guclu_renk} !important;
                        -webkit-text-fill-color:{guclu_renk} !important;
                        font-weight:950 !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} .gecmis-ozet-sag .gecmis-ozet-ayirici {{
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                        opacity:.75 !important;
                    }}
                    @media (max-width: 1150px) {{
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] summary {{
                            padding-right:250px !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} .gecmis-ozet-sag {{
                            max-width:240px !important;
                            font-size:.68rem !important;
                        }}
                    }}
                    </style>
                    <div class="gecmis-ozet-sag" style="display:{'block' if tekrar_ozeti_html else 'none'}">{tekrar_ozeti_html}</div>
                    """,
                    unsafe_allow_html=True,
                )
                tam_ekran_aktif = st.session_state.get("gecmis_tam_ekran_sira") == sira

                # Sadece ikonlu düğme; expander başlığının SOLUNDA, aynı kutunun içinde görünür.
                # :has() ile butonun Streamlit element kabını akıştan çıkarıp başlık üzerine bindiriyoruz.
                st.markdown(
                    f"""
                    <style>
                    .st-key-gecmis_mac_baslik_{sira} {{
                        position:relative !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} div[data-testid="stElementContainer"]:has([data-testid="stBaseButton-secondary"]) {{
                        position:absolute !important;
                        left:42px !important;
                        top:39px !important;
                        z-index:20 !important;
                        width:30px !important;
                        min-width:30px !important;
                        height:30px !important;
                        margin:0 !important;
                        padding:0 !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} div[data-testid="stElementContainer"]:has([data-testid="stBaseButton-secondary"]) button {{
                        width:30px !important;
                        min-width:30px !important;
                        height:30px !important;
                        min-height:30px !important;
                        padding:0 !important;
                        border-radius:7px !important;
                        font-size:16px !important;
                        line-height:1 !important;
                    }}
                    .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] summary {{
                        padding-left:76px !important;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "↙" if tam_ekran_aktif else "⛶",
                    key=f"gecmis_tam_ekran_btn_{sira}",
                    help="Normal görünüme dön" if tam_ekran_aktif else "Tüm geçmiş sonuçları tek ekrana sığdır",
                ):
                    st.session_state.gecmis_tam_ekran_sira = None if tam_ekran_aktif else sira
                    st.rerun()

                if tam_ekran_aktif:
                    tam_arka = '#071426' if bool(st.session_state.get('koyu_mod', False)) else '#f8fafc'
                    st.markdown(
                        f"""
                        <style>
                        .st-key-gecmis_mac_baslik_{sira} {{
                            position:fixed !important;
                            inset:0 !important;
                            z-index:999999 !important;
                            background:{tam_arka} !important;
                            padding:8px 12px !important;
                            overflow-y:auto !important;
                            overflow-x:hidden !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] {{
                            width:100% !important;
                            max-width:none !important;
                            height:calc(100vh - 16px) !important;
                            overflow-y:auto !important;
                            overflow-x:hidden !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpanderDetails"] {{
                            height:calc(100vh - 62px) !important;
                            overflow-y:auto !important;
                            overflow-x:hidden !important;
                            padding:2px 4px 4px 4px !important;
                        }}
                        /* Tam ekranda tablo normal satır yüksekliğini korur.
                           Satırlar ekran yüksekliğini aşarsa tablonun kendi dikey kaydırması devreye girer. */
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stDataFrame"] {{
                            max-height:calc(100vh - 82px) !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpanderDetails"] > div,
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"] {{
                            gap:0 !important;
                            margin:0 !important;
                            padding:0 !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} div[data-testid="stElementContainer"]:has([data-testid="stBaseButton-secondary"]) {{
                            position:absolute !important;
                            left:42px !important;
                            top:14px !important;
                        }}
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )

                oran_baslik = (
                    f" · Oran {m.get('h', 0):.2f}/{m.get('b', 0):.2f}/{m.get('a', 0):.2f}"
                    if gecmis_oranlari_goster else ""
                )
                # Sadece aynı ligler açıkken sayı maç satırında gösterilir:
                # örn. 7/25 örnek = 7 aynı lig örneği / 25 toplam benzer örnek.
                if bool(gecmis_ayni_lig):
                    tum_ornek_sayisi = int(item.get("tum_ornek_sayisi", len(ornekler)) or 0)
                    ornek_baslik = f"{len(ornekler)}/{tum_ornek_sayisi} örnek"
                else:
                    ornek_baslik = f"{len(ornekler)} örnek"
                with st.expander(
                    f"{sira}. {m.get('ev', '')} - {m.get('dep', '')} · {saat}"
                    f"{oran_baslik} · {ornek_baslik}",
                    expanded=tam_ekran_aktif,
                ):
                    if ornekler.empty:
                        st.warning("Bu hassasiyet ve lig seçimiyle geçmiş örnek bulunamadı.")

                        # Tanılama: tahmin mantığına dokunmadan hangi filtrenin
                        # örnek havuzunu sıfırladığını ve en yakın geçmiş oranı göster.
                        try:
                            teshis_gecmis = futbol_veri_motoru(tuple(yillar))
                            teshis = gecmis_ornek_teshisi(
                                teshis_gecmis, pd.Series(dict(m)), TOLERANS,
                                sadece_ayni_lig=bool(gecmis_ayni_lig),
                            )
                            hedef = teshis.get("target")
                            if hedef:
                                st.caption(
                                    f"🔎 Tanı · Hedef oran: {hedef[0]:.2f} / {hedef[1]:.2f} / {hedef[2]:.2f} "
                                    f"· Seçili hassasiyet: {float(TOLERANS):.2f}"
                                )
                            st.caption(
                                "Filtre akışı: "
                                f"tüm geçmiş {teshis.get('toplam', 0):,} → "
                                f"lig {teshis.get('lig_sonrasi', 0):,} → "
                                f"oran evresi {teshis.get('evre_sonrasi', 0):,} → "
                                f"tarih öncesi {teshis.get('tarih_sonrasi', 0):,} → "
                                f"eşleşen {teshis.get('eslesen', 0):,}"
                            )
                            st.caption(
                                f"Lig kodu: {teshis.get('history_code') or 'yok'} · "
                                f"Güncel oran evresi: {teshis.get('odds_phase') or 'bilinmiyor'} · "
                                f"Geçmişte kullanılan evre: {teshis.get('phase_used') or 'yok'}"
                            )
                            en_yakin = teshis.get("nearest")
                            if en_yakin:
                                no = en_yakin["odds"]
                                nd = en_yakin["diffs"]
                                min_tol = float(teshis.get("min_tolerance") or 0.0)
                                st.caption(
                                    f"En yakın geçmiş: {en_yakin.get('home', '')} - {en_yakin.get('away', '')} "
                                    f"· {no[0]:.2f} / {no[1]:.2f} / {no[2]:.2f} "
                                    f"· fark {nd[0]:.2f} / {nd[1]:.2f} / {nd[2]:.2f} "
                                    f"· üçünün birden eşleşmesi için gereken en düşük hassasiyet ≈ {min_tol:.2f}"
                                )
                        except Exception as teshis_hatasi:
                            LOGGER.warning("Geçmiş örnek tanısı gösterilemedi: %s", type(teshis_hatasi).__name__)
                        continue
                    tablo_veri = {
                        "Tarih": pd.to_datetime(ornekler["Date"]).dt.strftime("%d.%m.%Y"),
                        "Lig": ornekler.get("league_code", pd.Series("-", index=ornekler.index)),
                        "Geçmiş maç": ornekler["HomeTeam"].astype(str) + " - " + ornekler["AwayTeam"].astype(str),
                    }
                    if gecmis_oranlari_goster:
                        # Filtre hangi oranı kullandıysa tabloda da yalnızca onu göster.
                        # REF_* kapanış oranıdır; eski sezonda yoksa yükleyici B365'e düşer.
                        tablo_veri.update({
                            "1": ornekler["REF_H"].round(2) if "REF_H" in ornekler.columns else ornekler["B365H"].round(2),
                            "X": ornekler["REF_D"].round(2) if "REF_D" in ornekler.columns else ornekler["B365D"].round(2),
                            "2": ornekler["REF_A"].round(2) if "REF_A" in ornekler.columns else ornekler["B365A"].round(2),
                        })
                    tablo_veri.update({
                        "İY": ornekler["HTHG"].astype(int).astype(str) + "-" + ornekler["HTAG"].astype(int).astype(str),
                        "MS": ornekler["FTHG"].astype(int).astype(str) + "-" + ornekler["FTAG"].astype(int).astype(str),
                        "2.5": ((ornekler["FTHG"] + ornekler["FTAG"]) >= 3).map({True: "Üst", False: "Alt"}),
                        "KG": ((ornekler["FTHG"] > 0) & (ornekler["FTAG"] > 0)).map({True: "Var", False: "Yok"}),
                        "Özel olay": ornekler["Olay"],
                    })
                    tablo = pd.DataFrame(tablo_veri)
                    if tam_ekran_aktif:
                        # Tam ekran yalnızca inceleme alanını büyütür; tablo görünümü normal modla aynıdır.
                        # Az örnekte satırlar gereksiz büyümez. Çok örnekte ise tablo kendi dikey
                        # kaydırma çubuğunu gösterir. Genişlik yetmezse Streamlit yatay kaydırmayı sağlar.
                        normal_satir_yuksekligi = 35
                        baslik_yuksekligi = 38
                        tam_ekran_tablo_yuksekligi = min(
                            900,
                            baslik_yuksekligi + max(1, len(tablo)) * normal_satir_yuksekligi,
                        )
                        st.dataframe(
                            gecmis_tablo_stili(tablo),
                            use_container_width=True,
                            hide_index=True,
                            height=tam_ekran_tablo_yuksekligi,
                        )
                    else:
                        st.dataframe(gecmis_tablo_stili(tablo), use_container_width=True, hide_index=True)
    legal_footer()
    st.stop()


# Oran ve Yüksek Oran filtrelerinde 0.00-0.10 arasındaki 11 hassasiyet otomatik taranır.
# Her seviye ayrı hesaplanır; aynı geçmiş maçlar 11 kez tek havuzda çoğaltılmaz.
OTOMATIK_HASSASIYETLER = [i / 100.0 for i in range(11)]

def _kombo_label_mask(df, label):
    """Oran Filtresi etiketini geçmiş maçlarda gerçekleşti/gerçekleşmedi maskesine çevirir."""
    label = str(label or '').strip()
    if label == 'MS 1':
        return df['FTHG'] > df['FTAG']
    if label == 'MS X':
        return df['FTHG'] == df['FTAG']
    if label == 'MS 2':
        return df['FTHG'] < df['FTAG']
    if label == 'KG Var':
        return (df['FTHG'] > 0) & (df['FTAG'] > 0)
    if label == 'KG Yok':
        return (df['FTHG'] == 0) | (df['FTAG'] == 0)
    if label == '2.5 Üst':
        return (df['FTHG'] + df['FTAG']) >= 3
    if label == '2.5 Alt':
        return (df['FTHG'] + df['FTAG']) <= 2
    return pd.Series(False, index=df.index)


def _oran_istatistik_sirasi(stat):
    """Başlık, kart ve tablo aynı gerçek yüzdeyle sıralanır; yuvarlama yalnızca gösterimdir."""
    toplam = int(stat.get('toplam', 0) or 0)
    gercek_oran = (float(stat.get('hit', 0) or 0) / toplam if toplam > 0
                  else float(stat.get('oran', 0) or 0) / 100.0)
    return (gercek_oran, int(stat.get('uzlasi', 0) or 0),
            float(stat.get('tarama_ortalama', 0) or 0))


def _kombo_ikili_stats(taramalar):
    """MS+KG (6), MS+2.5 (6), KG+2.5 (4): 16 gerçek ikili kesişimi karşılaştırır.

    Her aday aynı en geniş geçerli örnek havuzunda sayılır. Hassasiyet ortalaması
    ayrıca tutulur. Uzlaşı, kendi ikili grubunda en yüksek ortak sayıya ulaştığı
    hassasiyet sayısıdır; eşit en yüksekler de oy alır.
    """
    gruplar = {
        'MS': ('MS 1', 'MS X', 'MS 2'),
        'KG': ('KG Var', 'KG Yok'),
        '2.5': ('2.5 Üst', '2.5 Alt'),
    }
    pair_defs = [('MS', 'KG'), ('MS', '2.5'), ('KG', '2.5')]
    tanimlar = [(f'{l1} + {l2}', f'{g1}+{g2}', l1, l2)
                for g1, g2 in pair_defs for l1 in gruplar[g1] for l2 in gruplar[g2]]
    oranlar = {label: [] for label, _, _, _ in tanimlar}
    oylar = {label: 0 for label, _, _, _ in tanimlar}
    tablo_tol, tablo_toplam, tablo_hits = None, 0, {}

    for tol, b, _ in taramalar:
        if b is None or b.empty:
            continue
        # Tekli marketin kazananından bağımsız olarak her tarafı bir kez hesapla.
        masks = {label: _kombo_label_mask(b, label)
                 for labels in gruplar.values() for label in labels}
        hits = {label: int((masks[l1] & masks[l2]).sum())
                for label, _, l1, l2 in tanimlar}
        grup_max = {f'{g1}+{g2}': max(hits[label] for label, tip, _, _ in tanimlar
                                     if tip == f'{g1}+{g2}')
                    for g1, g2 in pair_defs}
        for label, tip, _, _ in tanimlar:
            oranlar[label].append(hits[label] / len(b) * 100.0)
            if hits[label] == grup_max[tip]:
                oylar[label] += 1
        if tablo_tol is None or tol > tablo_tol:
            tablo_tol, tablo_toplam, tablo_hits = tol, len(b), hits

    if not tablo_toplam:
        return []
    final = []
    for label, tip, _, _ in tanimlar:
        vals = oranlar[label]
        final.append({
            'label': label, 'grup': 'Kombo', 'kombo_tipi': tip,
            'hit': tablo_hits[label], 'toplam': tablo_toplam,
            'oran': round(tablo_hits[label] / tablo_toplam * 100.0, 1),
            'tarama_ortalama': round(sum(vals) / len(vals), 1),
            'uzlasi': oylar[label], 'gecerli_hassasiyet': len(vals),
        })
    final.sort(key=_oran_istatistik_sirasi, reverse=True)
    return final


def _oran_11_uzlasi(gecmis_df, mac_row, min_ornek, ayni_lig, ms, kg, gol25, yarilar, kombo=False):
    taramalar = []
    for tol in OTOMATIK_HASSASIYETLER:
        b = gecmis_ornekleri_bul(gecmis_df, mac_row, tol, sadece_ayni_lig=ayni_lig, limit=100000)
        if b is None or b.empty or len(b) < int(min_ornek):
            continue
        # Kombo, tekli market seçimlerinden bağımsız olarak aşağıda hesaplanır.
        stats, _ = oran_filtresi_istatistikleri(b, ms, kg, gol25, yarilar)
        taramalar.append((tol, b, stats))
    if not taramalar:
        return None

    # Tablo için en geniş geçerli hassasiyetin benzersiz örnekleri kullanılır.
    tol_max, tablo_ornekleri, _ = max(taramalar, key=lambda x: x[0])
    # Normal marketler yalnızca kullanıcı onları seçtiyse sonuç listesine eklenir.
    grup_sirasi = []
    if ms:
        grup_sirasi.append("MS")
    if kg:
        grup_sirasi.append("KG")
    if gol25:
        grup_sirasi.append("2.5")
    if yarilar:
        grup_sirasi.append("Yarılar")
    final_stats = []
    for grup in grup_sirasi:
        oylar = {}
        oranlar = {}
        for tol, b, stats in taramalar:
            adaylar = [x for x in stats if x.get("grup") == grup]
            if not adaylar:
                continue
            kazanan = max(adaylar, key=lambda x: (float(x.get("oran", 0)), int(x.get("hit", 0))))
            label = str(kazanan.get("label", "—"))
            oylar[label] = oylar.get(label, 0) + 1
            # Aynı label'ın o hassasiyetteki gerçek yüzdesini kaydet.
            es = next((x for x in adaylar if str(x.get("label")) == label), kazanan)
            oranlar.setdefault(label, []).append(float(es.get("oran", 0)))
        if not oylar:
            continue
        label = max(oylar, key=lambda k: (oylar[k], sum(oranlar[k]) / max(1, len(oranlar[k]))))
        # Seçilen ortak label'ın tüm geçerli taramalardaki yüzdesini ortala.
        tum_oranlar = []
        for tol, b, stats in taramalar:
            es = next((x for x in stats if x.get("grup") == grup and str(x.get("label")) == label), None)
            if es is not None:
                tum_oranlar.append(float(es.get("oran", 0)))
        ort = sum(tum_oranlar) / len(tum_oranlar) if tum_oranlar else 0.0
        if grup == "Yarılar" and ort < 50.0:
            continue
        uzlasi = int(oylar[label])
        gecerli = sum(1 for _, _, stats in taramalar if any(x.get("grup") == grup for x in stats))
        hits = [tahmin_tuttu_mu(label, row) for _, row in tablo_ornekleri.iterrows()]
        hit = sum(value is not None and bool(value) for value in hits)
        actual_pct = hit / len(tablo_ornekleri) * 100.0
        if grup == "Yarılar" and actual_pct < 50:
            continue
        ornek_guveni = min(len(tablo_ornekleri) / 30.0, 1.0)
        final_stats.append({
            "label": label, "grup": grup, "hit": hit, "toplam": len(tablo_ornekleri),
            "oran": round(actual_pct, 1), "tarama_ortalama": round(ort, 1),
            "puan": round(actual_pct * (0.82 + 0.18 * ornek_guveni), 1),
            "uzlasi": uzlasi, "gecerli_hassasiyet": gecerli,
        })

    # Kombo yalnızca kullanıcı Oran Filtresi'nde Kombo kutusunu seçtiğinde hesaplanır.
    # MS+KG, MS+2.5 ve KG+2.5 için 16 aday da aynı havuzda gerçek kesişimdir.
    if kombo:
        for c in _kombo_ikili_stats(taramalar):
            c['puan'] = round(float(c.get('oran', 0) or 0) * (0.82 + 0.18 * min(len(tablo_ornekleri) / 30.0, 1.0)), 1)
            final_stats.append(c)

    # Oran Filtresi içinde en güçlü marketi doğrudan başarı yüzdesine göre belirle.
    # Hassasiyet uzlaşısı artık yalnızca eşitlik bozucu olarak kullanılır.
    final_stats.sort(key=_oran_istatistik_sirasi, reverse=True)
    if not final_stats:
        return None
    return {
        "ornekler": tablo_ornekleri, "istatistikler": final_stats, "en_iyi": final_stats[0],
        "toplam_benzer": len(tablo_ornekleri), "tarama_sayisi": len(taramalar), "tablo_tol": tol_max,
    }

def _yuksek_11_uzlasi(gecmis_df, mac_row, ayni_lig, f12, f21, fkg, fy15, limit):
    taramalar = []
    for tol in OTOMATIK_HASSASIYETLER:
        tum = gecmis_ornekleri_bul(gecmis_df, mac_row, tol, sadece_ayni_lig=ayni_lig, limit=100000)
        if tum is None or tum.empty:
            continue
        stats, _, _ = yuksek_oran_istatistikleri(tum, f12, f21, fkg, fy15)
        taramalar.append((tol, tum, stats))
    if not taramalar:
        return None
    tol_max, tum_max, _ = max(taramalar, key=lambda x: x[0])
    olay_ornekleri = gecmis_ornekleri_bul(
        gecmis_df, mac_row, tol_max, sadece_ayni_lig=ayni_lig,
        filtre_12=f12, filtre_21=f21, filtre_cift_yari_kg=fkg, filtre_cift_yari_15=fy15, limit=limit,
    )
    if olay_ornekleri is None or olay_ornekleri.empty:
        return None
    labels = ["1/2", "2/1", "İki yarıda da KG", "İki yarı 1.5 Üst"]
    final_stats = []
    for label in labels:
        vals = []
        wins = 0
        for _, _, stats in taramalar:
            if not stats:
                continue
            es = next((x for x in stats if x.get("label") == label), None)
            if es is not None:
                vals.append(float(es.get("oran", 0)))
            winner = max(stats, key=lambda x: (float(x.get("puan", 0)), int(x.get("hit", 0))))
            if winner.get("label") == label:
                wins += 1
        if not vals:
            continue
        ort = sum(vals) / len(vals)
        hit = sum(bool(tahmin_tuttu_mu(label, row)) for _, row in tum_max.iterrows())
        actual_pct = hit / len(tum_max) * 100.0
        duz = (hit + 1) / (len(tum_max) + 2)
        og = min(len(tum_max) / 30.0, 1.0)
        puan = duz * 100 * (0.65 + 0.35 * og)
        final_stats.append({
            "label": label, "hit": hit, "toplam": len(tum_max), "oran": round(actual_pct, 1),
            "tarama_ortalama": round(ort, 1),
            "puan": round(puan, 1), "uzlasi": wins, "gecerli_hassasiyet": len(vals),
        })
    final_stats.sort(key=lambda x: (x.get("uzlasi", 0), x.get("puan", 0)), reverse=True)
    if not final_stats:
        return None
    en_iyi = final_stats[0]
    toplam = len(tum_max)
    if en_iyi["uzlasi"] >= 9 and toplam >= 20 and en_iyi["oran"] >= 10:
        oneri = "GÜÇLÜ DENENEBİLİR"
    elif en_iyi["uzlasi"] >= 7 and toplam >= 12 and en_iyi["oran"] >= 6:
        oneri = "DENENEBİLİR"
    elif en_iyi["uzlasi"] >= 5 and en_iyi["hit"] >= 2:
        oneri = "RİSKLİ DENEME"
    else:
        oneri = "PAS"
    return {
        "ornekler": olay_ornekleri, "istatistikler": final_stats, "en_iyi": en_iyi, "oneri": oneri,
        "toplam_benzer": toplam, "tarama_sayisi": len(taramalar), "tablo_tol": tol_max,
    }

# Oran filtresi yalnızca kullanıcı ÖRNEKLERİ GETİR'e bastığında yeniden hesaplanır.
if oran_filtresi_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("📊 0.00–0.10 arası 11 hassasiyet taranıyor..."):
            of_gecmis = futbol_veri_motoru(tuple(yillar))
            of_bulten = bulten_saglam_al(API_KEY, secili_kodlar, secili_tarih)
            oran_filtresi_list = []
            for _, of_mac in of_bulten.iterrows():
                sonuc = _oran_11_uzlasi(
                    of_gecmis, of_mac, oran_filter_min_ornek, sadece_ayni_lig,
                    oran_filter_ms, oran_filter_kg, oran_filter_25, oran_filter_cift_yari_15,
                    oran_filter_kombo,
                )
                if sonuc is None:
                    continue
                sonuc["m"] = of_mac.to_dict()
                oran_filtresi_list.append(sonuc)
            # Maçları hassasiyet uzlaşısına göre değil, en yüksek görünen yüzdeye göre sırala.
            # Eşit yüzde varsa önce uzlaşı, sonra örnek sayısı eşitlik bozucu olur.
            oran_filtresi_list.sort(
                key=lambda x: (
                    float(x.get("en_iyi", {}).get("oran", 0) or 0),
                    int(x.get("en_iyi", {}).get("uzlasi", 0) or 0),
                    int(x.get("toplam_benzer", 0) or 0),
                ),
                reverse=True,
            )
            st.session_state.oran_filtresi_list = oran_filtresi_list
            st.rerun()

# Yüksek oran filtresi de 11 hassasiyeti tek tıklamada tarar.
if yuksek_oran_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("💎 0.00–0.10 arası 11 hassasiyet taranıyor..."):
            yo_gecmis = futbol_veri_motoru(tuple(yillar))
            yo_bulten = bulten_saglam_al(API_KEY, secili_kodlar, secili_tarih)
            yuksek_liste = []
            for _, yo_mac in yo_bulten.iterrows():
                sonuc = _yuksek_11_uzlasi(
                    yo_gecmis, yo_mac, sadece_ayni_lig,
                    yuksek_filtre_12, yuksek_filtre_21, yuksek_filtre_cift_yari_kg, yuksek_filtre_cift_yari_15, yuksek_limit,
                )
                if sonuc is None:
                    continue
                sonuc["m"] = yo_mac.to_dict()
                yuksek_liste.append(sonuc)
            yuksek_liste.sort(
                key=lambda x: (x.get("en_iyi", {}).get("uzlasi", 0), x.get("en_iyi", {}).get("puan", 0), x.get("toplam_benzer", 0)),
                reverse=True,
            )
            st.session_state.yuksek_oran_list = yuksek_liste
            st.rerun()

elif st.session_state.get('sayfa_modu') == 'Oran Filtresi':
    oran_liste = st.session_state.get("oran_filtresi_list")
    if oran_liste is None:
        st.info("Lig, tarih ve marketleri seçip ORAN FİLTRESİNİ ÇALIŞTIR butonuna bas.")
    elif not oran_liste:
        st.warning("0.00–0.10 taramasında minimum örnek şartını karşılayan güncel maç bulunamadı.")
    else:
        st.success(f"{len(oran_liste)} güncel maç bulundu · 0.00–0.10 arası 11 hassasiyet otomatik tarandı.")

        # Geçmiş Örnekleri görünümü gibi kompakt maç satırları.
        st.markdown(
            """
            <style>
            [class*="st-key-oran_mac_baslik_"] {
                margin:0 !important;
                padding:0 !important;
                margin-bottom:-10px !important;
            }
            [class*="st-key-oran_mac_baslik_"] > div[data-testid="stVerticalBlock"] {
                gap:0 !important;
                margin:0 !important;
                padding:0 !important;
            }
            div[data-testid="stVerticalBlock"]:has(> div [class*="st-key-oran_mac_baslik_"]) {
                gap:0 !important;
            }
            [class*="st-key-oran_mac_baslik_"] div[data-testid="stElementContainer"] {
                margin-top:0 !important;
                margin-bottom:0 !important;
            }
            [class*="st-key-oran_mac_baslik_"] [data-testid="stExpander"] summary {
                min-height:38px !important;
                padding-top:4px !important;
                padding-bottom:4px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        for sira, item in enumerate(oran_liste, start=1):
            m = item["m"]
            ornekler = item["ornekler"]
            istatistikler = item.get("istatistikler", [])
            toplam_benzer = int(item.get("toplam_benzer", len(ornekler)))
            saat = m["zaman"].strftime("%H:%M") if hasattr(m.get("zaman"), "strftime") else ""

            # Her seçili market grubunda yalnızca en yüksek yüzdeli sonuç başlıkta gösterilir.
            # Örn. 2.5 Üst %68 ise aynı anda 2.5 Alt yazılmaz.
            grup_sirasi = ["MS", "KG", "2.5", "Yarılar"] + (["Kombo"] if oran_filter_kombo else [])
            grup_en_iyiler = []
            for grup in grup_sirasi:
                adaylar = [x for x in istatistikler if x.get("grup") == grup]
                if not adaylar:
                    continue
                en_iyi_grup = max(adaylar, key=_oran_istatistik_sirasi)
                label = str(en_iyi_grup.get("label", "—"))
                if grup == "Yarılar":
                    label = label.replace("Her İki Yarı 1.5 Üst ", "İki Yarı 1.5 Üst ")
                    label = label.replace("Her iki yarı 1.5 Üst ", "İki Yarı 1.5 Üst ")
                    label = label.replace("Her iki yarı 1.5 üst ", "İki Yarı 1.5 Üst ")
                grup_en_iyiler.append((label, float(en_iyi_grup.get("oran", 0) or 0), int(en_iyi_grup.get("uzlasi", 0) or 0), int(en_iyi_grup.get("gecerli_hassasiyet", 0) or 0)))

            # Gruplar arasındaki en yüksek yüzde sarı, diğerleri camgöbeği.
            max_baslik_pct = max((pct for _, pct, _, _ in grup_en_iyiler), default=0.0)
            koyu_aktif = bool(st.session_state.get("koyu_mod", False))
            normal_renk = "#67e8f9" if koyu_aktif else "#0369a1"
            guclu_renk = "#facc15" if koyu_aktif else "#b45309"
            baslik_parcalar = []
            for idx, (label, pct, uzlasi, gecerli_hass) in enumerate(grup_en_iyiler):
                guclu = abs(pct - max_baslik_pct) < 1e-9
                kombo_50_ustu = (" + " in str(label) or str(label).startswith(("MS+", "KG+"))) and pct > 50.0
                if kombo_50_ustu:
                    # Kombo %50 üstündeyse diğer marketlerden ayrı, yumuşak mor tonda göster.
                    cls = "oran-ozet-deger oran-ozet-kombo-guclu"
                elif guclu:
                    cls = "oran-ozet-deger oran-ozet-en-guclu"
                else:
                    cls = "oran-ozet-deger"
                ayirici = '<span class="oran-ozet-ayirici"> · </span>' if idx else ""
                # Başlıkta hassasiyet bilgisi gösterilmez; yalnızca maç detayında yer alır.
                baslik_parcalar.append(
                    ayirici + f'<span class="{cls}">{escape(label)} %{pct:.0f}</span>'
                )
            baslik_ozeti_html = "".join(baslik_parcalar)

            with st.container(key=f"oran_mac_baslik_{sira}"):
                st.markdown(
                    f"""
                    <style>
                    .st-key-oran_mac_baslik_{sira} {{
                        position:relative !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} [data-testid="stExpander"] summary {{
                        display:flex !important;
                        align-items:center !important;
                        width:100% !important;
                        padding-right:min(500px, 52vw) !important;
                        overflow:hidden !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} [data-testid="stExpander"] summary p {{
                        overflow:hidden !important;
                        text-overflow:ellipsis !important;
                        white-space:nowrap !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} .oran-ozet-sag {{
                        position:absolute !important;
                        right:14px !important;
                        top:29px !important;
                        transform:translateY(-50%) !important;
                        z-index:18 !important;
                        max-width:min(490px, 51vw) !important;
                        overflow:hidden !important;
                        text-overflow:ellipsis !important;
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                        font-weight:850 !important;
                        font-size:clamp(.68rem, .72vw, .84rem) !important;
                        white-space:nowrap !important;
                        pointer-events:none !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} .oran-ozet-deger {{
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} .oran-ozet-en-guclu {{
                        color:{guclu_renk} !important;
                        -webkit-text-fill-color:{guclu_renk} !important;
                        font-weight:950 !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} .oran-ozet-kombo-guclu {{
                        color:#a78bfa !important;
                        -webkit-text-fill-color:#a78bfa !important;
                        font-weight:850 !important;
                    }}
                    .st-key-oran_mac_baslik_{sira} .oran-ozet-ayirici {{
                        color:{normal_renk} !important;
                        -webkit-text-fill-color:{normal_renk} !important;
                        opacity:.75 !important;
                    }}
                    @media (max-width:1150px) {{
                        .st-key-oran_mac_baslik_{sira} [data-testid="stExpander"] summary {{
                            padding-right:280px !important;
                        }}
                        .st-key-oran_mac_baslik_{sira} .oran-ozet-sag {{
                            max-width:270px !important;
                            font-size:.66rem !important;
                        }}
                    }}
                    </style>
                    <div class="oran-ozet-sag" style="display:{'block' if baslik_ozeti_html else 'none'}">{baslik_ozeti_html}</div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander(
                    f"{sira}. {m.get('ev', '')} - {m.get('dep', '')} · {saat} · {toplam_benzer} örnek",
                    expanded=False,
                ):
                    ist_map = {x.get("label"): x for x in istatistikler}

                    # Açılır bölümde tüm seçili market gruplarını tek satırda, yan yana göster.
                    detay_kartlari = []
                    for grup, baslik, ikon in [
                        ("MS", "Maç Sonucu", "⚽"),
                        ("KG", "Karşılıklı Gol", "🔁"),
                        ("2.5", "2.5 Gol", "🎯"),
                        ("Yarılar", "İki Yarı 1.5 Üst", "⏱️"),
                    ]:
                        adaylar = [x for x in istatistikler if x.get("grup") == grup]
                        if not adaylar:
                            continue
                        en_iyi_detay = max(adaylar, key=_oran_istatistik_sirasi)
                        detay_label = str(en_iyi_detay.get("label", "—"))
                        if grup == "Yarılar":
                            detay_label = detay_label.replace("Her İki Yarı 1.5 Üst ", "")
                            detay_label = detay_label.replace("Her iki yarı 1.5 Üst ", "")
                            detay_label = detay_label.replace("Her iki yarı 1.5 üst ", "")
                            detay_label = detay_label.replace("İki Yarı 1.5 Üst ", "")
                        detay_kartlari.append((baslik, ikon, detay_label, en_iyi_detay))

                    # Kombo seçiliyse yalnızca en yüksek kombo da aynı detay satırına kart olarak eklenir.
                    if oran_filter_kombo:
                        kombo_stats = [x for x in istatistikler if x.get("grup") == "Kombo"]
                        if kombo_stats:
                            en_yuksek_kombo = max(kombo_stats, key=_oran_istatistik_sirasi)
                            kombo_tip = str(en_yuksek_kombo.get("kombo_tipi", "Kombo"))
                            kombo_label = str(en_yuksek_kombo.get("label", "—"))
                            detay_kartlari.append((f"Kombo · {kombo_tip}", "🔗", kombo_label, en_yuksek_kombo))

                    if detay_kartlari:
                        detay_cols = st.columns(len(detay_kartlari), gap="small")
                        for detay_i, (col, (baslik, ikon, detay_label, en_iyi_detay)) in enumerate(zip(detay_cols, detay_kartlari)):
                            with col:
                                st.markdown(f"**{ikon} {baslik}**")
                                detay_pct = float(en_iyi_detay.get('oran', 0) or 0)
                                detay_hass = int(en_iyi_detay.get('uzlasi', 0) or 0)
                                # Hassasiyet yalnızca maç detayında ve tüm istatistikler içindeki
                                # en yüksek yüzdeli kartta gösterilir.
                                detay_alt = (
                                    f"{detay_hass}/11 hass. · {toplam_benzer} örnek"
                                    if abs(detay_pct - max_baslik_pct) < 1e-9
                                    else f"{toplam_benzer} örnek"
                                )
                                st.metric(
                                    detay_label,
                                    f"%{detay_pct:.1f}",
                                    detay_alt,
                                    delta_color="off",
                                )
                                st.caption(f"Gerçek sayım: {int(en_iyi_detay.get('hit', 0))}/{int(en_iyi_detay.get('toplam', 0))} · "
                                           f"Hassasiyet ortalaması: %{float(en_iyi_detay.get('tarama_ortalama', detay_pct)):.1f}")

                    try:
                        ilk_yari_gol = ornekler["HTHG"] + ornekler["HTAG"]
                        ikinci_yari_gol = (ornekler["FTHG"] - ornekler["HTHG"]) + (ornekler["FTAG"] - ornekler["HTAG"])
                        iki_yari_15_txt = ((ilk_yari_gol >= 2) & (ikinci_yari_gol >= 2)).map({True: "Evet", False: "Hayır"})
                    except Exception:
                        iki_yari_15_txt = pd.Series("—", index=ornekler.index)

                    tablo_veri = {
                        "Tarih": pd.to_datetime(ornekler["Date"]).dt.strftime("%d.%m.%Y"),
                        "Lig": ornekler.get("league_code", pd.Series("-", index=ornekler.index)),
                        "Geçmiş maç": ornekler["HomeTeam"].astype(str) + " - " + ornekler["AwayTeam"].astype(str),
                        "Kapanış 1/X/2": (
                            (ornekler["REF_H"] if "REF_H" in ornekler.columns else ornekler["B365H"]).round(2).astype(str)
                            + " / "
                            + (ornekler["REF_D"] if "REF_D" in ornekler.columns else ornekler["B365D"]).round(2).astype(str)
                            + " / "
                            + (ornekler["REF_A"] if "REF_A" in ornekler.columns else ornekler["B365A"]).round(2).astype(str)
                        ),
                        "MS": ornekler["FTHG"].astype(int).astype(str) + "-" + ornekler["FTAG"].astype(int).astype(str),
                        "2.5": ((ornekler["FTHG"] + ornekler["FTAG"]) >= 3).map({True: "Üst", False: "Alt"}),
                        "KG": ((ornekler["FTHG"] > 0) & (ornekler["FTAG"] > 0)).map({True: "Var", False: "Yok"}),
                    }

                    # İki Yarı 1.5 Üst yalnızca maçın 11 hassasiyet ortak sonucunda
                    # Evet yüzdesi %50 veya üzerindeyse detaylı geçmiş tabloda da gösterilsin.
                    # %50'nin altındaysa Evet/Hayır sütunu tamamen gizlenir.
                    yarilar_stat = next(
                        (x for x in istatistikler if x.get("grup") == "Yarılar" and float(x.get("oran", 0) or 0) >= 50.0),
                        None,
                    )
                    if yarilar_stat is not None:
                        tablo_veri["İki yarı 1.5 Üst"] = iki_yari_15_txt

                    if oran_filter_kombo:
                        kombo_stats = [x for x in istatistikler if x.get('grup') == 'Kombo']
                        if kombo_stats:
                            c = max(kombo_stats, key=_oran_istatistik_sirasi)
                            label = str(c.get('label', ''))
                            if ' + ' in label:
                                l1, l2 = label.split(' + ', 1)
                                evet_hayir = (_kombo_label_mask(ornekler, l1) & _kombo_label_mask(ornekler, l2)).map({True: 'Evet', False: 'Hayır'})
                                tablo_veri[str(c.get('kombo_tipi', 'Kombo'))] = evet_hayir

                    tablo = pd.DataFrame(tablo_veri)
                    st.dataframe(gecmis_tablo_stili(tablo), use_container_width=True, hide_index=True)
    legal_footer()
    st.stop()


if st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
    yuksek_liste = st.session_state.get("yuksek_oran_list")
    if yuksek_liste is None:
        st.info("Lig, tarih ve marketleri seçip ÖRNEKLERİ GETİR butonuna bas.")
    elif not yuksek_liste:
        st.warning("Seçilen koşullarda 1/2, 2/1, iki yarıda da KG veya iki yarı 1.5 Üst geçmiş örneği bulunan güncel maç yok.")
    else:
        st.success(f"{len(yuksek_liste)} güncel maç filtreye takıldı · 0.00–0.10 arası 11 hassasiyet otomatik tarandı.")
        for sira, item in enumerate(yuksek_liste, start=1):
            m = item["m"]
            ornekler = item["ornekler"]
            istatistik_map = {x["label"]: x for x in item.get("istatistikler", [])}
            en_iyi = item.get("en_iyi", {})
            oneri = item.get("oneri", "PAS")
            toplam_benzer = int(item.get("toplam_benzer", len(ornekler)))
            saat = m["zaman"].strftime("%H:%M") if hasattr(m.get("zaman"), "strftime") else ""
            oneri_baslik = {
                "GÜÇLÜ DENENEBİLİR": "🟢 GÜÇLÜ DENENEBİLİR",
                "DENENEBİLİR": "🔵 DENENEBİLİR",
                "RİSKLİ DENEME": "🟠 RİSKLİ DENEME",
                "PAS": "⚪ PAS",
            }.get(oneri, f"⚪ {oneri}")
            with st.expander(
                f"#{sira}  {m.get('ev', '')} – {m.get('dep', '')}  ·  {saat}  ·  {oneri_baslik}",
                expanded=(sira == 1),
            ):
                oneri_renk = {
                    "GÜÇLÜ DENENEBİLİR": "#16a34a",
                    "DENENEBİLİR": "#2563eb",
                    "RİSKLİ DENEME": "#d97706",
                    "PAS": "#64748b",
                }.get(oneri, "#64748b")
                st.markdown(
                    f"""
                    <div style="background:#0f172a;border:1px solid #263650;border-radius:12px;padding:12px 14px;margin-bottom:12px;">
                      <div style="font-size:.72rem;color:#94a3b8;font-weight:800;letter-spacing:.08em;">İSTATİSTİKSEL ÖNERİ</div>
                      <div style="font-size:1.08rem;color:{oneri_renk};font-weight:900;margin-top:3px;">{escape(oneri)}</div>
                      <div style="font-size:.80rem;color:#cbd5e1;margin-top:4px;">
                        En uygun: <b>{escape(str(en_iyi.get('label', '—')))}</b> ·
                        Uzlaşı: <b>{int(en_iyi.get('uzlasi', 0))}/11 hass.</b> ·
                        Gerçekleşme oranı: <b>%{float(en_iyi.get('oran', 0)):.1f}</b> · Toplam benzer maç: <b>{toplam_benzer}</b>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                metrik_kolonlari = st.columns(4)
                for metrik_col, label in zip(metrik_kolonlari, ["1/2", "2/1", "İki yarıda da KG", "İki yarı 1.5 Üst"]):
                    bilgi = istatistik_map.get(label, {"hit": 0, "toplam": toplam_benzer, "oran": 0.0})
                    with metrik_col:
                        st.metric(
                            label,
                            f"{int(bilgi.get('hit', 0))} adet",
                            f"%{float(bilgi.get('oran', 0)):.1f} · {int(bilgi.get('uzlasi', 0))}/11 hass.",
                            delta_color="off",
                        )
                st.markdown(
                    f"**Güncel oran:** `{m.get('h', 0):.2f} / {m.get('b', 0):.2f} / {m.get('a', 0):.2f}`"
                )
                # Bir geçmiş maçta birden fazla yüksek oran olayı gerçekleşmişse
                # yalnızca sabit olay önceliğinde en yüksek olanı göster.
                # Öncelik: 1/2 ve 2/1 > İki yarıda da KG > İki yarı 1.5 Üst.
                olay_kolon_map = {
                    "1/2": "olay_12",
                    "2/1": "olay_21",
                    "İki yarıda da KG": "olay_cift_yari_kg",
                    "İki yarı 1.5 Üst": "olay_cift_yari_15",
                }
                olay_onceligi = ["1/2", "2/1", "İki yarıda da KG", "İki yarı 1.5 Üst"]

                def _tek_yuksek_oran_olayi(r):
                    for olay_label in olay_onceligi:
                        olay_kolon = olay_kolon_map[olay_label]
                        if olay_label not in istatistik_map or olay_kolon not in r.index:
                            continue
                        try:
                            if bool(r[olay_kolon]):
                                return olay_label
                        except Exception:
                            pass
                    return "—"

                yuksek_oran_olay_serisi = ornekler.apply(_tek_yuksek_oran_olayi, axis=1)

                tablo = pd.DataFrame({
                    "Tarih": pd.to_datetime(ornekler["Date"]).dt.strftime("%d.%m.%Y"),
                    "Lig": ornekler.get("league_code", pd.Series("-", index=ornekler.index)),
                    "Geçmiş maç": ornekler["HomeTeam"].astype(str) + " - " + ornekler["AwayTeam"].astype(str),
                    "Kapanış 1/X/2": (
                        (ornekler["REF_H"] if "REF_H" in ornekler.columns else ornekler["B365H"]).round(2).astype(str)
                        + " / "
                        + (ornekler["REF_D"] if "REF_D" in ornekler.columns else ornekler["B365D"]).round(2).astype(str)
                        + " / "
                        + (ornekler["REF_A"] if "REF_A" in ornekler.columns else ornekler["B365A"]).round(2).astype(str)
                    ),
                    "İY": ornekler["HTHG"].astype(int).astype(str) + "-" + ornekler["HTAG"].astype(int).astype(str),
                    "MS": ornekler["FTHG"].astype(int).astype(str) + "-" + ornekler["FTAG"].astype(int).astype(str),
                    "Yüksek oran olayı": yuksek_oran_olay_serisi,
                })
                st.dataframe(gecmis_tablo_stili(tablo), use_container_width=True, hide_index=True)
    legal_footer()
    st.stop()


if st.session_state.get('sayfa_modu') == 'Canlı Takip':
    simdi_canli = tr_simdi()
    son_yenileme = st.session_state.get("canli_son_yenileme")
    otomatik_zamani = (
        canli_otomatik
        and (son_yenileme is None or (simdi_canli - son_yenileme).total_seconds() >= 295)
    )
    # Minimum API tüketimi: Canlı Takip sayfasını yalnızca açmak skor isteği atmaz.
    # Manuel yenileme veya kullanıcı açıkça 5 dk otomatik yenilemeyi açarsa sorgulanır.
    if canli_yenile_btn or otomatik_zamani:
        takip_key = get_app_api_key()
        if not takip_key:
            st.session_state.canli_takip_hatasi = "Canlı skorları çekmek için API key gerekli."
            st.session_state.canli_takip_listesi = []
        else:
            with st.spinner("Canlı skorlar kontrol ediliyor..."):
                canli_liste, canli_hata = canli_analizleri_getir(takip_key)
            st.session_state.canli_takip_listesi = canli_liste
            st.session_state.canli_takip_hatasi = canli_hata
            st.session_state.canli_son_yenileme = simdi_canli

    canli_hata = st.session_state.get("canli_takip_hatasi")
    if canli_hata:
        st.warning(canli_hata)
    canli_liste = st.session_state.get("canli_takip_listesi", [])
    if not canli_liste:
        st.info("Şu anda canlı oynanan ve daha önce analizi kaydedilmiş eşleşen maç bulunamadı.")
    else:
        renkler = {
            "guclu": ("#14532d", "#4ade80", "🟢 TAHMİN GÜÇLENDİ"),
            "bekle": ("#422006", "#facc15", "🟡 BEKLE"),
            "zayif": ("#450a0a", "#f87171", "🔴 TAHMİN ZAYIFLADI"),
        }
        guclu_adet = sum(x.get("canli_durum") == "guclu" for x in canli_liste)
        bekle_adet = sum(x.get("canli_durum") == "bekle" for x in canli_liste)
        zayif_adet = sum(x.get("canli_durum") == "zayif" for x in canli_liste)
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Canlı maç", len(canli_liste))
        mc2.metric("Güçlendi", guclu_adet)
        mc3.metric("Bekle", bekle_adet)
        mc4.metric("Zayıfladı", zayif_adet)
        for item in canli_liste:
            arka, vurgu, durum_yazi = renkler.get(item.get("canli_durum"), renkler["bekle"])
            st.markdown(
                f"""
                <div style="background:{arka};border:1px solid {vurgu};border-radius:14px;padding:14px 16px;margin:10px 0;color:#f8fafc">
                  <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
                    <b style="font-size:1.06rem;color:#f8fafc">{escape(str(item.get('ev','')))} – {escape(str(item.get('dep','')))}</b>
                    <b style="color:{vurgu}">{escape(str(item.get('dakika_yazi','~')))} · {int(item.get('ev_gol',0))}-{int(item.get('dep_gol',0))}</b>
                  </div>
                  <div style="margin-top:7px;color:#e2e8f0">Maç önü: <b>{escape(str(item.get('tahmin','-')))}</b> · Güven %{int(item.get('guven',0))}</div>
                  <div style="margin-top:8px;color:{vurgu};font-weight:900">{durum_yazi}</div>
                  <div style="margin-top:4px;color:#e2e8f0;font-size:.86rem">{escape(str(item.get('canli_aciklama','')))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.caption("Dakika yaklaşık değerdir; devre arası hesaba katılarak başlangıç saatinden hesaplanır. Canlı giriş kararı garanti değildir.")
    if canli_otomatik:
        components.html(
            "<script>setTimeout(function(){window.parent.location.reload();},300000);</script>",
            height=0,
        )
    legal_footer()
    st.stop()


if st.session_state.get('sayfa_modu') == 'Sonuç Takibi':
    st.markdown(
        """
        <style>
        .result-track-header, .result-track-header * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        .result-track-header > div:last-child {
            color:#334155 !important;
            -webkit-text-fill-color:#334155 !important;
        }
        div[data-testid="stMetric"] {
            background:#ffffff !important;
            border:1px solid #cbd5e1 !important;
            border-radius:12px !important;
            padding:12px 14px !important;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] label *,
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        div[data-testid="stMarkdownContainer"] h4 {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        </style>
        <div class="result-track-header" style="background:#fff;border:1px solid #cbd5e1;border-radius:14px;padding:15px 18px;margin-bottom:14px">
          <div style="font-size:1.55rem;font-weight:900">📋 Sonuç Takibi</div>
          <div style="font-size:.90rem;margin-top:7px">Maç analizinde kaydedilen ana tahminleri ve gerçekleşen sonuçları gösterir.</div>
        </div>
        """, unsafe_allow_html=True,
    )
    yenile = sonuc_yenile_btn
    st.caption("Skor servisi son üç günü getirir; sonuçları en az üç günde bir üstteki SONUÇLARI YENİLE düğmesiyle kontrol et.")

    reset_sol, reset_sag = st.columns([3, 1])
    with reset_sag:
        if st.button(
            "🗑️ SONUÇ TAKİBİNİ SIFIRLA",
            use_container_width=True,
            key="sonuc_takibini_sifirla_btn",
            help="Eski Sonuç Takibi kayıtlarını temizler ve mevcut ayarlarla analizi yeni kod üzerinden yeniden çalıştırır.",
        ):
            if sonuc_takibini_sifirla():
                # Eski analiz çıktıları yeni Sonuç Takibi'ne tekrar yazılmasın.
                for _key in (
                    "final_list",
                    "top10_list",
                    "top50_list",
                    "tum_profil_aday_listeleri",
                ):
                    st.session_state.pop(_key, None)

                # API key, lig/tarih/sezon seçimleri ve kupon geçmişi korunur.
                # Bir sonraki rerun'da Maç Analizi'ne geçip ANALİZİ BAŞLAT akışını
                # otomatik tetikle.
                st.session_state["sonuc_reset_hedef_mac_analizi"] = True
                st.session_state["sonuc_reset_otomatik_analiz"] = True
                # Reset sonrası Sonuç Takibi tek manuel hassasiyetle değil,
                # 0.00–0.10 birleşik hassasiyet taramasıyla yeniden üretilir.
                st.session_state["sonuc_reset_genis_tarama"] = True
                st.session_state["sonuc_reset_bilgi"] = (
                    "Sonuç Takibi sıfırlandı. 0.00–0.10 birleşik hassasiyet taramasıyla "
                    "tahminler yeni kod üzerinden yeniden oluşturuluyor."
                )
                st.rerun()
            else:
                st.error("Sonuç Takibi sıfırlanamadı. JSON dosyasına yazma iznini kontrol et.")

    if yenile:
        takip_key = get_app_api_key()
        if not takip_key:
            st.error("Sonuçları yenilemek için API key gerekli.")
        else:
            with st.spinner("Maç sonuçları kontrol ediliyor..."):
                adet, hata = tahmin_sonuclarini_guncelle(takip_key)
            if hata:
                st.warning(hata)
            st.success(f"{adet} tahminin sonucu güncellendi.")

    takip = tahmin_logunu_oku()
    if not takip:
        st.info("Henüz kayıt yok. Maç Analizi çalıştırıldığında ana tahminler otomatik kaydedilir.")
    else:
        df = pd.DataFrame(takip)
        df["zaman_dt"] = pd.to_datetime(df["zaman"], errors="coerce").dt.tz_localize(None)
        baslangic = pd.Timestamp((tr_simdi()).date())
        # Varsayılan olarak bütün kayıtları göster. Böylece sayfa her açıldığında
        # yalnızca bugünün maçlarına daralmış gibi görünmez.
        donem = st.selectbox(
            "Dönem",
            ["Tümü", "Bugün", "Son 7 Gün", "Son 30 Gün"],
            index=0,
            key="sonuc_takibi_donem_v2",
        )
        if donem == "Bugün":
            gorunen = df[df["zaman_dt"].dt.date == baslangic.date()].copy()
        elif donem == "Son 7 Gün":
            gorunen = df[df["zaman_dt"] >= baslangic - pd.Timedelta(days=6)].copy()
        elif donem == "Son 30 Gün":
            gorunen = df[df["zaman_dt"] >= baslangic - pd.Timedelta(days=29)].copy()
        else:
            gorunen = df.copy()

        biten = gorunen[gorunen["durum"] == "Tamamlandı"].copy()
        kazanan = int(biten["tuttu"].fillna(False).astype(bool).sum()) if not biten.empty else 0
        basari = kazanan / len(biten) * 100 if len(biten) else 0.0
        alt_biten = biten[
            biten.get("alternatif_tuttu", pd.Series(index=biten.index, dtype=object)).notna()
        ].copy() if not biten.empty else pd.DataFrame()
        alt_kazanan = int(alt_biten["alternatif_tuttu"].astype(bool).sum()) if not alt_biten.empty else 0
        alt_basari = alt_kazanan / len(alt_biten) * 100 if len(alt_biten) else None
        oranli = biten[biten["oran"].notna()].copy() if not biten.empty else pd.DataFrame()
        if not oranli.empty:
            oranli["kar"] = oranli.apply(lambda x: (float(x["oran"]) - 1) * 100 if bool(x["tuttu"]) else -100, axis=1)
            roi = float(oranli["kar"].sum()) / (len(oranli) * 100) * 100
        else:
            roi = None
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Tamamlanan", len(biten))
        m2.metric("Kazanan", kazanan)
        m3.metric("Başarı", f"%{basari:.1f}")
        m4.metric("Bekleyen", int((gorunen["durum"] != "Tamamlandı").sum()))
        m5.metric("ROI", f"%{roi:.1f}" if roi is not None else "—", help="Oranı bulunan tahminlere eşit tutar yatırıldığı varsayılır.")
        st.caption(
            f"Alternatif tahmin: {len(alt_biten)} tamamlanan · "
            + (f"{alt_kazanan} kazanan · başarı %{alt_basari:.1f}" if alt_basari is not None else "henüz tamamlanan yok")
            + ". Ana başarı ve ROI hesabına dahil edilmez."
        )

        if not biten.empty:
            # Bağlam performansı yalnızca tahmin anında snapshot kaydı bulunan maçlarda ölçülür.
            # Böylece maç bittikten sonra yeni form/H2H kullanıp geçmişe veri sızıntısı yapılmaz.
            if "baglam_ayari" in biten.columns:
                bag_biten = biten[pd.to_numeric(biten["baglam_ayari"], errors="coerce").notna()].copy()
                if not bag_biten.empty:
                    bag_biten["Bağlam Puanı"] = pd.to_numeric(bag_biten["baglam_ayari"], errors="coerce")
                    bag_biten["Bağlam Grubu"] = pd.cut(
                        bag_biten["Bağlam Puanı"],
                        bins=[-float("inf"), -2.0, -0.5, 0.5, 2.0, float("inf")],
                        labels=["≤ -2", "-2 / -0.5", "Nötr", "+0.5 / +2", "+2 üzeri"],
                        right=False,
                    )
                    bag_ozet = (bag_biten.groupby("Bağlam Grubu", observed=False)
                        .agg(Tahmin=("tuttu", "size"), Kazanan=("tuttu", lambda values: int(values.fillna(False).astype("int64").sum())), Ortalama_Bağlam=("Bağlam Puanı", "mean"))
                        .reset_index())
                    bag_ozet = bag_ozet[bag_ozet["Tahmin"] > 0].copy()
                    bag_ozet["Başarı %"] = (bag_ozet["Kazanan"] / bag_ozet["Tahmin"] * 100).round(1)
                    bag_ozet["Ort. Bağlam"] = bag_ozet["Ortalama_Bağlam"].round(2)
                    bag_ozet = bag_ozet.drop(columns=["Ortalama_Bağlam"])
                    st.markdown("#### 🧭 Bağlam etkisi performansı")
                    st.caption(
                        f"{len(bag_biten)} tamamlanmış tahminde seçim anındaki bağlam snapshot'ı var. "
                        "Pozitif bağlam grupları zamanla daha başarılı oluyorsa ek katman fayda sağlıyor demektir."
                    )
                    st.dataframe(bag_ozet, use_container_width=True, hide_index=True)
                else:
                    st.caption("Bağlam performansı: henüz sonuçlanmış snapshot kaydı yok. Yeni Günün Kuponları sonuçlandıkça burada ölçülecek.")

            c1, c2, c3 = st.columns(3)
            for alan, baslik, kolon in [("tahmin", "Tahmin türü", c1), ("lig", "Lig", c2)]:
                ozet = biten.groupby(alan, dropna=False).agg(Tahmin=("tuttu", "size"), Kazanan=("tuttu", lambda values: int(values.fillna(False).astype("int64").sum()))).reset_index()
                ozet["Başarı %"] = (ozet["Kazanan"] / ozet["Tahmin"] * 100).round(1)
                ozet = ozet.rename(columns={alan: baslik}).sort_values(["Başarı %", "Tahmin"], ascending=False)
                with kolon:
                    st.markdown(f"#### {baslik} performansı")
                    st.dataframe(ozet, use_container_width=True, hide_index=True)
            with c3:
                st.markdown("#### Alternatif performansı")
                if alt_biten.empty:
                    st.info("Henüz sonuçlanmış alternatif tahmin yok.")
                else:
                    alt_ozet = (
                        alt_biten.groupby("alternatif_tahmin", dropna=False)
                        .agg(Tahmin=("alternatif_tuttu", "size"), Kazanan=("alternatif_tuttu", lambda values: int(values.fillna(False).astype("int64").sum())))
                        .reset_index()
                        .rename(columns={"alternatif_tahmin": "Alternatif Tahmin"})
                    )
                    alt_ozet["Başarı %"] = (
                        alt_ozet["Kazanan"] / alt_ozet["Tahmin"] * 100
                    ).round(1)
                    alt_ozet = alt_ozet.sort_values(["Başarı %", "Tahmin"], ascending=False)
                    st.dataframe(alt_ozet, use_container_width=True, hide_index=True)

        if gorunen.empty:
            st.warning("Seçilen dönemde kayıt yok.")
        else:
            liste = gorunen.sort_values("zaman_dt", ascending=False).reset_index(drop=True).copy()
            liste["Tarih"] = liste["zaman_dt"].dt.strftime("%d.%m.%Y %H:%M")
            liste["Maç"] = liste["ev"].astype(str) + " – " + liste["dep"].astype(str)
            liste["Sonuç"] = liste.apply(lambda x: f"{int(x['ev_gol'])}-{int(x['dep_gol'])}" if pd.notna(x.get("ev_gol")) and pd.notna(x.get("dep_gol")) else "—", axis=1)
            liste["Durum"] = liste.apply(
                lambda x: "⏳ Bekliyor" if pd.isna(x.get("tuttu")) else "✅ Tuttu" if bool(x.get("tuttu")) else "❌ Tutmadı",
                axis=1,
            )
            liste["Alternatif Durumu"] = liste.apply(
                lambda x: "—" if pd.isna(x.get("alternatif_tahmin")) or not str(x.get("alternatif_tahmin", "")).strip()
                else "⏳ Bekliyor" if pd.isna(x.get("alternatif_tuttu"))
                else "✅ Tuttu" if bool(x.get("alternatif_tuttu")) else "❌ Tutmadı",
                axis=1,
            )
            for kolon, varsayilan in [("alternatif_tahmin", ""), ("alternatif_guven", None), ("baglam_ayari", None)]:
                if kolon not in liste.columns:
                    liste[kolon] = varsayilan
            liste["alternatif_tahmin"] = liste["alternatif_tahmin"].fillna("").replace("None", "")
            liste["Bağlam"] = pd.to_numeric(liste["baglam_ayari"], errors="coerce").map(
                lambda x: f"{x:+.1f}" if pd.notna(x) else "—"
            )
            goster = liste[[
                "Tarih", "lig", "Maç", "tahmin", "guven", "Bağlam", "Sonuç", "Durum",
                "alternatif_tahmin", "alternatif_guven", "Alternatif Durumu",
            ]].rename(columns={
                "lig":"Lig", "tahmin":"Ana Tahmin", "guven":"Ana Güven %",
                "alternatif_tahmin":"Alternatif Tahmin", "alternatif_guven":"Alt. Güven %",
            })
            st.markdown("#### Kaydedilen tahminler")
            st.dataframe(goster, use_container_width=True, hide_index=True)
            st.download_button("CSV olarak indir", goster.to_csv(index=False).encode("utf-8-sig"), "vibe_sonuc_takibi.csv", "text/csv", use_container_width=True)
    legal_footer()
    st.stop()


if st.session_state.get("sayfa_modu") == "Backtest":
    st.selectbox("Test modeli", ["Birleşik model", "Top 50 Market"], key="backtest_model",
                 on_change=clear_backtest_on_change,
                 help="Top 50 testi, listedeki market filtrelerini ve günlük 50 maç sınırını da uygular.")

if backtest_btn:
    with st.spinner("🧪 11 hassasiyet test ediliyor (0.00–0.10)..."):
        bt_sezonlar = list(dict.fromkeys(list(yillar) + [backtest_sezonu]))
        # Backtest başlatılırken Football-Data'yı zorla yenile ve eski cache ile birleştir.
        futbol_veri_motoru.clear()
        bt_gecmis = futbol_veri_motoru(tuple(bt_sezonlar), zorla_yenile=True)
        if bt_gecmis is not None and not bt_gecmis.empty and "Date" in bt_gecmis.columns:
            _bt_son_tarih = pd.to_datetime(bt_gecmis["Date"], errors="coerce").max()
            if pd.notna(_bt_son_tarih):
                st.session_state["backtest_veri_son_tarih"] = _bt_son_tarih.strftime("%d.%m.%Y")
        secili_history_codes = [ODDS_TO_HISTORY[k] for k in secili_kodlar if k in ODDS_TO_HISTORY]
        bt11, bt_secili, bt_uzlasi, bt_tek_uzlasi, bt_tahmin_uzlasi = backtest_11_hassasiyet_calistir(
            bt_gecmis,
            backtest_sezonu,
            TOLERANS,
            min_ornek,
            sadece_ayni_lig=sadece_ayni_lig,
            lig_kodlari=secili_history_codes or None,
            max_test=backtest_limit,
            top50_model=st.session_state.get("backtest_model") == "Top 50 Market",
            filtreler={key: st.session_state.get(key, True) for key in ("top10_filter_ms", "top10_filter_25", "top10_filter_kg", "top10_filter_iy15", "top10_filter_combo")},
        )
        st.session_state.backtest_11_df = bt11
        st.session_state.backtest_uzlasi_df = bt_uzlasi
        st.session_state.backtest_tek_uzlasi_df = bt_tek_uzlasi
        st.session_state.backtest_tahmin_uzlasi_df = bt_tahmin_uzlasi
        st.session_state.backtest_df = bt_secili
        st.rerun()

if st.session_state.get('sayfa_modu') == 'Backtest':
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            background:#ffffff !important;
            border:1px solid #cbd5e1 !important;
            border-radius:12px !important;
            padding:12px 14px !important;
            box-shadow:0 3px 10px rgba(15,23,42,.08) !important;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] label *,
        div[data-testid="stMetric"] div[data-testid="stMetricValue"],
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] *,
        div[data-testid="stMetric"] div[data-testid="stMetricDelta"],
        div[data-testid="stMetric"] div[data-testid="stMetricDelta"] * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="backtest-header-fix" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:14px;padding:15px 18px;margin-bottom:14px;">
          <div class="backtest-title-fix" style="font-size:1.55rem;font-weight:900;line-height:1.2;">🧪 Tarih Sıralı Backtest</div>
          <div class="backtest-desc-fix" style="font-size:.90rem;margin-top:7px;line-height:1.5;">
            Her maç yalnızca kendisinden önce oynanmış karşılaşmalar kullanılarak analiz edilir; gelecek veri sızıntısı yapılmaz.
            Backtest yalnızca güveni %60'ın üstünde olan (%61+) tahminleri değerlendirir.
            Ana sonuç 0.00–0.10 arasındaki yeterli örnekli marketleri güven %80 ve
            hassasiyet kararlılığı %20 ile sıralar. Örnek sayısı puan kazandırmaz; yalnızca minimum yeterlilik
            koşuludur ve çok az örnekte ayrıca ceza uygulanır. Marketin geçmiş backtest başarısı güvene küçük,
            veri miktarına göre azaltılmış bir düzeltme yapar. 11 tekil hassasiyet ayrıca karşılaştırma için gösterilir.
            Form ve Value/Edge kullanılmaz.
          </div>
          <div class="backtest-season-fix" style="font-size:.82rem;font-weight:800;margin-top:7px;">Test sezonu: {escape(str(backtest_sezonu))}</div>
        </div>
        <style>
        .backtest-header-fix, .backtest-header-fix * {{
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }}
        .backtest-header-fix .backtest-desc-fix {{
            color:#334155 !important;
            -webkit-text-fill-color:#334155 !important;
        }}
        .backtest-header-fix .backtest-season-fix {{
            color:#1d4ed8 !important;
            -webkit-text-fill-color:#1d4ed8 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    _bt_veri_tarihi = st.session_state.get("backtest_veri_son_tarih")
    if _bt_veri_tarihi:
        st.caption(f"📅 Backtest veri setindeki son tamamlanmış maç tarihi: {_bt_veri_tarihi}")

    bt = st.session_state.get("backtest_df")
    if isinstance(bt, pd.DataFrame):
        st.caption("Test edilen model: " + str(bt.attrs.get("model", "Birleşik")))
    if bt is None:
        st.info("Sol menüden sezon ve filtreleri seçip BACKTESTİ BAŞLAT butonuna bas.")
    elif bt.empty:
        st.warning("Bu ayarlarla test edilebilir tahmin bulunamadı. Sezonları, ligleri veya minimum örnek sayısını kontrol et.")
    else:
        toplam = len(bt)
        kazanan = int(bt["Tuttu"].sum())
        basari = kazanan / toplam * 100 if toplam else 0

        # MS ROI: yalnızca gerçek 1/X/2 oranı ve hesaplanmış kârı olan MS seçimleri.
        ms_bt = bt[bt["Kâr (100 TL)"].notna()].copy() if "Kâr (100 TL)" in bt.columns else pd.DataFrame()
        if not ms_bt.empty:
            net_kar = float(ms_bt["Kâr (100 TL)"].sum())
            yatirilan = len(ms_bt) * 100.0
            roi = (net_kar / yatirilan * 100.0) if yatirilan else 0.0
        else:
            roi = 0.0

        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam tahmin", toplam)
        c2.metric("Başarı", f"%{basari:.1f}")
        c3.metric("MS ROI", f"%{roi:.1f}",
                  help="Yalnızca B365 1/X/2 oranı bulunan seçimler.")

        ozet = (
            bt.groupby("Tahmin", dropna=False)
            .agg(Tahmin_Sayısı=("Tuttu", "size"), Kazanan=("Tuttu", lambda values: int(values.fillna(False).astype("int64").sum())), Ortalama_Güven=("Güven", "mean"))
            .reset_index()
        )
        ozet["Başarı %"] = (ozet["Kazanan"] / ozet["Tahmin_Sayısı"] * 100).round(1)
        ozet["Ortalama_Güven"] = ozet["Ortalama_Güven"].round(1)
        def backtest_stili(df):
            return (
                df.style
                .set_properties(**{"background-color": "#ffffff", "color": "#0f172a", "font-weight": "600"})
                .set_table_styles([
                    {"selector": "th", "props": [("background-color", "#e2e8f0"), ("color", "#0f172a"), ("font-weight", "800")]},
                ])
            )
        bt11 = st.session_state.get("backtest_11_df")
        if bt11 is not None and not bt11.empty:
            st.markdown("### 11 Hassasiyet Otomatik Backtest")
            st.caption(
                "Aynı sezon ve aynı filtreler 0.00–0.10 arasında 0.01 adımlarla test edilir. "
                "Tahmin sayısını da dikkate al; yalnızca en yüksek başarı yüzdesine bakarak hassasiyet seçme."
            )
            bt11_goster = bt11.copy()
            st.dataframe(backtest_stili(bt11_goster), use_container_width=True, hide_index=True)

            # En iyi satırları sadece bilgi amaçlı göster; otomatik seçim yapılmaz.
            gec = bt11_goster[bt11_goster["Tahmin"] > 0].copy()
            if not gec.empty:
                en_basari = gec.loc[gec["Başarı %"].astype(float).idxmax()]
                roi_gec = gec[gec["MS ROI %"].notna()].copy()
                ic1, ic2, ic3 = st.columns(3)
                ic1.metric("En yüksek başarı hass.", str(en_basari["Hassasiyet"]))
                ic2.metric("En yüksek başarı", f"%{float(en_basari['Başarı %']):.1f}")
                if not roi_gec.empty:
                    en_roi = roi_gec.loc[roi_gec["MS ROI %"].astype(float).idxmax()]
                    ic3.metric("En yüksek MS ROI hass.", f"{en_roi['Hassasiyet']} · %{float(en_roi['MS ROI %']):.1f}")
                else:
                    ic3.metric("En yüksek MS ROI hass.", "—")

            uzlasi = st.session_state.get("backtest_uzlasi_df")
            if uzlasi is not None and not uzlasi.empty:
                st.markdown("### 11 Hassasiyet Uzlaşı Performansı")
                st.caption(
                    "Aynı maçta 0.00–0.10 arasındaki oynanabilir (%60 üstü güven) tekil modellerin "
                    "aynı ana tahminde kaç kez birleştiğini ölçer. Hassasiyetler iptal edilmez; "
                    "uzlaşı yükseldikçe başarı da yükseliyorsa bunu yeni bir kararlılık sinyali olarak kullanabiliriz."
                )
                st.dataframe(backtest_stili(uzlasi), use_container_width=True, hide_index=True)

                tek_uzlasi = st.session_state.get("backtest_tek_uzlasi_df")
                if tek_uzlasi is not None and not tek_uzlasi.empty:
                    st.markdown("#### Tek Tek Uzlaşı (11/11 → 1/11)")
                    st.caption("9–10/11 grubunu ayırır; başarıyı 9/11 mi yoksa 10/11 mi taşıyor doğrudan görürüz.")
                    st.dataframe(backtest_stili(tek_uzlasi), use_container_width=True, hide_index=True)
                else:
                    st.info("Tek tek uzlaşı tablosu bu çalıştırmada üretilemedi. BACKTESTİ BAŞLAT'a yeniden bas.")

                tahmin_uzlasi = st.session_state.get("backtest_tahmin_uzlasi_df")
                if tahmin_uzlasi is not None and not tahmin_uzlasi.empty:
                    st.markdown("#### Tahmin × Uzlaşı Performansı")
                    st.caption("MS1, MS2, KG Var, 2.5 Üst/Alt gibi ana tahminlerin her uzlaşı seviyesindeki gerçek başarısını gösterir. Az örnekli satırları tek başına güçlü sinyal sayma.")
                    st.dataframe(backtest_stili(tahmin_uzlasi), use_container_width=True, hide_index=True, height=420)
                else:
                    st.info("Tahmin × Uzlaşı tablosu bu çalıştırmada üretilemedi. BACKTESTİ BAŞLAT'a yeniden bas.")

        # Birleşik oynanabilirlik puanı gerçekten ayırt edici mi?
        # Puan yükseldikçe başarının da yükselmesi beklenir.
        if "Ana Puan" in bt.columns:
            puan_analizi = bt.copy()
            puan_analizi["Ana Puan"] = pd.to_numeric(puan_analizi["Ana Puan"], errors="coerce")
            puan_analizi["Güven"] = pd.to_numeric(puan_analizi["Güven"], errors="coerce")
            puan_analizi = puan_analizi.dropna(subset=["Ana Puan", "Tuttu"])
            if not puan_analizi.empty:
                puan_analizi["Puan Aralığı"] = pd.cut(
                    puan_analizi["Ana Puan"],
                    bins=[-float("inf"), 60, 70, 80, float("inf")],
                    labels=["60 altı", "60–69", "70–79", "80+"],
                    right=False,
                )
                puan_ozeti = (
                    puan_analizi.groupby("Puan Aralığı", observed=False)
                    .agg(
                        Tahmin=("Tuttu", "size"),
                        Kazanan=("Tuttu", lambda values: int(values.fillna(False).astype("int64").sum())),
                        Ortalama_Güven=("Güven", "mean"),
                    )
                    .reset_index()
                )
                puan_ozeti = puan_ozeti[puan_ozeti["Tahmin"] > 0].copy()
                puan_ozeti["Başarı %"] = (
                    puan_ozeti["Kazanan"] / puan_ozeti["Tahmin"] * 100
                ).round(1)
                puan_ozeti["Ortalama Güven %"] = puan_ozeti["Ortalama_Güven"].round(1)
                puan_ozeti = puan_ozeti.drop(columns=["Ortalama_Güven"])
                puan_ozeti["Puan Aralığı"] = puan_ozeti["Puan Aralığı"].astype(str)
                sira = {"80+": 0, "70–79": 1, "60–69": 2, "60 altı": 3}
                puan_ozeti["_sira"] = puan_ozeti["Puan Aralığı"].map(sira)
                puan_ozeti = puan_ozeti.sort_values("_sira").drop(columns=["_sira"])
                st.markdown("### Puan aralığı performansı")
                st.caption(
                    "Birleşik puanın ayırt etme gücünü gösterir. "
                    "Sistem sağlıklıysa yüksek puan grupları daha yüksek başarı üretmelidir."
                )
                st.dataframe(backtest_stili(puan_ozeti), use_container_width=True, hide_index=True)

        ozet_col, alt_ozet_col = st.columns(2)
        with ozet_col:
            st.markdown("### Ana market özeti")
            st.dataframe(backtest_stili(ozet), use_container_width=True, hide_index=True)
        with alt_ozet_col:
            st.markdown("### Alternatif market özeti")
            if "Alternatif Tahmin" not in bt.columns:
                st.info("Bu backtestte alternatif tahmin yok.")
            else:
                alt_bt = bt[
                    bt["Alternatif Tahmin"].fillna("").astype(str).str.strip().ne("")
                    & bt["Alt. Tuttu"].notna()
                ].copy()
                if alt_bt.empty:
                    st.info("Bu backtestte sonuçlanmış alternatif tahmin yok.")
                else:
                    alt_ozet = (
                        alt_bt.groupby("Alternatif Tahmin", dropna=False)
                        .agg(Tahmin_Sayısı=("Alt. Tuttu", "size"), Kazanan=("Alt. Tuttu", lambda values: int(values.fillna(False).astype("int64").sum())), Ortalama_Güven=("Alt. Güven", "mean"))
                        .reset_index()
                    )
                    alt_ozet["Başarı %"] = (alt_ozet["Kazanan"] / alt_ozet["Tahmin_Sayısı"] * 100).round(1)
                    alt_ozet["Ortalama_Güven"] = alt_ozet["Ortalama_Güven"].round(1)
                    st.dataframe(backtest_stili(alt_ozet), use_container_width=True, hide_index=True)

        st.markdown("### Test edilen maçlar")
        bt_goster = bt.sort_values("Tarih", ascending=False).copy()
        bt_goster = bt_goster.drop(columns=[
            "Ana Puan", "Ana Medyan Örnek", "Ana Kararlılık", "Ana Hassasiyetler",
            "Alt. Örnek", "Alt. Puan", "Alt. Kararlılık", "Alt. Hassasiyetler",
        ], errors="ignore")
        for bool_col in ["Tuttu", "Alt. Tuttu", "Formsuz Tuttu"]:
            if bool_col in bt_goster.columns:
                bt_goster[bool_col] = bt_goster[bool_col].map({True: "✅ Evet", False: "❌ Hayır"}).fillna("—")
        bt_goster = bt_goster.drop(columns=["Oran", "Kâr (100 TL)", "Formsuz Tuttu"], errors="ignore")
        bt_goster = bt_goster.rename(columns={
            "Sonuç": "Skor",
            "Tahmin": "Ana Tahmin",
            "Güven": "Ana Güven %",
            "Örnek": "Ana Örnek",
            "Tuttu": "Ana Durum",
            "Alt. Güven": "Alt. Güven %",
            "Alt. Tuttu": "Alt. Durum",
        })
        tablo_sirasi = [
            "Tarih", "Lig", "Maç", "Skor",
            "Ana Tahmin", "Ana Güven %", "Ana Örnek", "Ana Durum",
            "Alternatif Tahmin", "Alt. Güven %", "Alt. Durum",
        ]
        bt_goster = bt_goster[[kolon for kolon in tablo_sirasi if kolon in bt_goster.columns]]
        st.dataframe(backtest_stili(bt_goster), use_container_width=True, hide_index=True)
        st.download_button(
            "CSV olarak indir",
            data=bt_goster.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"vibe_backtest_{backtest_sezonu}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    legal_footer()
    st.stop()


# Sonuç Takibi sıfırlandıysa, eski final_list'i kullanmak yerine aynı analiz
# motorunu mevcut ayarlarla baştan çalıştır.
_sonuc_reset_genis_tarama = False
if st.session_state.pop("sonuc_reset_otomatik_analiz", False):
    analiz_btn = True
    _sonuc_reset_genis_tarama = bool(
        st.session_state.pop("sonuc_reset_genis_tarama", False)
    )
    _reset_bilgi = st.session_state.pop("sonuc_reset_bilgi", "")
    if _reset_bilgi:
        st.info(_reset_bilgi)

if analiz_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("📊 Bülten hazırlanıyor (cache varsa API kullanılmaz) ve analiz ediliyor..."):
            gecmis = futbol_veri_motoru(tuple(yillar))
            bulten = bulten_saglam_al(API_KEY, secili_kodlar, secili_tarih)
            st.session_state["son_gecmis_satir_sayisi"] = 0 if getattr(gecmis, "empty", True) else len(gecmis)
            try:
                st.session_state["son_gecmis_kaynak_hatalari"] = list(gecmis.attrs.get("kaynak_hatalari", []))
                st.session_state["son_gecmis_kaynak"] = str(gecmis.attrs.get("kaynak", ""))
            except Exception:
                st.session_state["son_gecmis_kaynak_hatalari"] = []
                st.session_state["son_gecmis_kaynak"] = ""
            st.session_state.last_gecmis_df = sadece_tam_verili_gecmis(gecmis)
            st.session_state.last_bulten_df = bulten
            st.session_state["son_bulten_mac_sayisi"] = 0 if getattr(bulten, "empty", True) else len(bulten)
            st.session_state["son_api_hatasi"] = st.session_state.get("odds_api_last_error")
            st.session_state["son_analiz_tarihi_secili"] = str(secili_tarih)

            if not getattr(bulten, "empty", True) and bulten.attrs.get("stale"):
                st.warning("Oranlar yenilenemedi; son başarılı bülten gösteriliyor. Oranları Yenile ile tekrar deneyebilirsin.")
            if getattr(bulten, "empty", True):
                son_hata = st.session_state.get("odds_api_last_error")
                if son_hata:
                    st.error(f"⚠️ The Odds API yanıtı alınamadı: {son_hata}")
                else:
                    st.warning("⚠️ Seçilen tarih ve liglerde aktif maç bulunamadı.")

        final = []
        # Analiz filtresi teşhisi: hangi aşamada kaç maç eleniyor?
        _sayac_toplam = 0
        _sayac_t_none = 0
        _sayac_ornek = 0
        _sayac_guven = 0
        _sayac_gecen = 0

        if not bulten.empty and not gecmis.empty and st.session_state.get("sayfa_modu") != "Top 50 Market":
            for _, m in bulten.iterrows():
                _sayac_toplam += 1
                # Maç Analizi: üstte seçilen manuel hassasiyetle TEK kez çalışır.
                # Top 50 Market: 0.00–0.10 birleşik hassasiyet modeli kullanılmaya devam eder.
                if _sonuc_reset_genis_tarama:
                    # Sonuç Takibi reseti: her maç için 0.00–0.10 hassasiyetleri
                    # birlikte tara. Karşıt-market tutarlılık kuralları
                    # hassasiyet_birlesik_hesapla içinde uygulanmaya devam eder.
                    t, b_det = hassasiyet_birlesik_hesapla(
                        gecmis, m, min_ornek, sadece_ayni_lig=sadece_ayni_lig
                    )
                elif st.session_state.get("sayfa_modu") == "Maç Analizi":
                    t, b_det = hesapla(
                        gecmis,
                        m,
                        TOLERANS,
                        sadece_ayni_lig=sadece_ayni_lig,
                        form_aktif=False,
                        kalibrasyon_aktif=False,
                    )
                else:
                    t, b_det = hassasiyet_birlesik_hesapla(
                        gecmis, m, min_ornek, sadece_ayni_lig=sadece_ayni_lig
                    )
                if t is None:
                    _sayac_t_none += 1
                    continue

                # Minimum Örnek Sayısı gerçek benzer maç sayısına uygulanır.
                # Manuel hassasiyet hesapla() içinde aday havuzu oluşsa bile, seçilen
                # minimumun altında kalan maçlar sonuç listesine/kuponlara giremez.
                try:
                    gercek_ornek = len(b_det) if b_det is not None else 0
                except Exception:
                    gercek_ornek = int(t.get("ornek", t.get("sample", 0)) or 0)
                if (not _sonuc_reset_genis_tarama) and gercek_ornek < max(1, int(min_ornek or 1)):
                    _sayac_ornek += 1
                    continue

                if oynanabilir_esik and t.get("ana_p", 0) < oynanabilir_esik:
                    _sayac_guven += 1
                    continue

                # Kartta toplam benzer örneğin kaçının aynı ligden geldiğini göster.
                # Bu bilgi sadece_ayni_lig kapalıyken de hesaplanır.
                try:
                    t["ayni_lig_ornek"] = ayni_lig_ornek_sayisi(b_det, m)
                except Exception:
                    t["ayni_lig_ornek"] = 0

                # 11 hassasiyetli stabilite taraması Maç Analizi'nde OPSİYONELDİR.
                # Kapalıyken her maç yalnızca seçili TOLERANS ile bir kez hesaplanır.
                if (
                    st.session_state.get("sayfa_modu") == "Maç Analizi"
                    and st.session_state.get("mac_analizi_stabilite_tarama", False)
                ):
                    try:
                        _ana_label = str(t.get("ana_label", "") or "").strip()
                        _taramalar = hassasiyet_taramasi(
                            gecmis, tarama_hedefi(m), sadece_ayni_lig
                        )
                        _ayni_hassasiyetler = []
                        for _tol, _sonuc in sorted(_taramalar.items()):
                            if not _sonuc:
                                continue
                            _tt, _bb = _sonuc
                            if _tt is None or str(_tt.get("ana_label", "") or "").strip() != _ana_label:
                                continue
                            try:
                                _n = len(_bb) if _bb is not None else 0
                            except Exception:
                                _n = int(_tt.get("ornek", 0) or 0)
                            if _n < max(1, int(min_ornek or 1)):
                                continue
                            _ayni_hassasiyetler.append(f"{float(_tol):.2f}")

                        t["stability_tols"] = _ayni_hassasiyetler
                        t["stability_count"] = len(_ayni_hassasiyetler)
                        t["stability_pct"] = len(_ayni_hassasiyetler) / 11 * 100
                        t["stability_text"] = " · ".join(_ayni_hassasiyetler)
                        t["stability_early_tols"] = [x for x in _ayni_hassasiyetler if float(x) <= .05]
                        t["stability_late_tols"] = [x for x in _ayni_hassasiyetler if float(x) > .05]
                        t["stability_early_text"] = " · ".join(t["stability_early_tols"])
                        t["stability_late_text"] = " · ".join(t["stability_late_tols"])
                    except Exception as _stability_error:
                        LOGGER.debug("Maç Analizi hassasiyet listesi üretilemedi: %s", type(_stability_error).__name__)

                m_dict = m.to_dict()
                m_dict["durum"] = mac_canli_durumu(m_dict["zaman"])
                final.append({"m": m_dict, "t": t, "b": b_det})
                _sayac_gecen += 1

        if st.session_state.get("sayfa_modu") == "Top 50 Market":
            final = gunun_en_iyi_10_uret(gecmis, bulten, min_ornek=min_ornek, limit=50, sadece_ayni_lig=sadece_ayni_lig)
            final = [item for item in final if int(item["t"]["ana_p"]) >= int(oynanabilir_esik or 0)]
            _sayac_toplam, _sayac_gecen = len(bulten), len(final)
        final.sort(key=lambda item: (item["t"].get("score", 0), item["t"].get("ana_p", 0),
                                     item["t"].get("stability_count", 0), mac_key(item["m"])), reverse=True)
        st.session_state.final_list = final
        st.session_state["son_final_mac_sayisi"] = len(final)
        st.session_state["analiz_filtre_sayaclari"] = {
            "toplam": _sayac_toplam,
            "t_none": _sayac_t_none,
            "ornek": _sayac_ornek,
            "guven": _sayac_guven,
            "gecen": _sayac_gecen,
            "min_ornek": int(min_ornek or 0),
            "oynanabilir_esik": int(oynanabilir_esik or 0),
            "tolerans": float(TOLERANS or 0.0),
        }
        analiz_tahminlerini_kaydet(final)
        st.session_state.top10_list = []
        # Normal Maç Analizi sırasında 11 hassasiyetli Top 50 taramasını boşuna çalıştırma.
        # Bu hem manuel hassasiyet mantığını net tutar hem de analizi hızlandırır.
        st.session_state.top50_list = final if st.session_state.get("sayfa_modu") == "Top 50 Market" else []
        st.session_state.detay_idx = None
        st.session_state.detay_item = None
        st.session_state.son_analiz = tr_simdi().strftime("%d/%m/%Y %H:%M")
        st.session_state.toplam_mac = len(final)
        st.rerun()

def secili_detay_itemi():
    if st.session_state.detay_item is not None:
        return st.session_state.detay_item
    idx = st.session_state.detay_idx
    return st.session_state.final_list[idx]


def kupon_seciminden_detay_itemi(secim, sadece_ayni_lig=False):
    """Otomatik/manüel kupon satırından normal Maç Detayı verisini yeniden üret.

    Önce son güncel bültende aynı maçı arar. Yeni oluşturulan kuponlarda
    saklanan 1-X-2 oranları sayesinde bülten değişmiş olsa bile detay yeniden
    hesaplanabilir. Çok eski kayıtlarda oran bilgisi yoksa None döner.
    """
    if not isinstance(secim, dict):
        return None

    snapshot = secim.get("detay_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("m") and snapshot.get("t") and snapshot.get("b"):
        try:
            snap_m = dict(snapshot["m"])
            snap_m["zaman"] = parse_mac_datetime(snap_m.get("zaman"))
            snap_t = dict(snapshot["t"])
            snap_b = pd.DataFrame(snapshot["b"])
            snap_b["Date"] = pd.to_datetime(snap_b["Date"], errors="coerce")
            for kolon in ["HTHG", "HTAG", "FTHG", "FTAG", "B365H", "B365D", "B365A", "REF_H", "REF_D", "REF_A"]:
                if kolon in snap_b.columns:
                    snap_b[kolon] = pd.to_numeric(snap_b[kolon], errors="coerce")
            if snap_m.get("zaman") is not None and not snap_b.empty:
                return {"m": snap_m, "t": snap_t, "b": snap_b, "kupon_secim": secim}
        except Exception:
            pass

    ev = str(secim.get("ev", ""))
    dep = str(secim.get("dep", ""))
    zaman_iso = str(secim.get("zaman_iso") or secim.get("zaman") or "")
    hedef_zaman = parse_mac_datetime(zaman_iso)

    m = None
    if hedef_zaman is not None:
        try:
            prices = [float(secim[key]) for key in ("h", "b", "a")]
            if all(math.isfinite(value) and value > 1 for value in prices):
                m = {"ev": ev, "dep": dep, "zaman": hedef_zaman, "lig": secim.get("lig", ""),
                     "sport_key": secim.get("sport_key", ""), **dict(zip(("h", "b", "a"), prices)),
                     **oran_kayit_bilgisi(secim)}
                if oran_fazi(m) == "unknown":
                    m.update(odds_phase="legacy_unknown", history_detail_only=True)
        except (KeyError, TypeError, ValueError):
            pass
    bulten = st.session_state.get("last_bulten_df")
    if m is None and bulten is not None and not getattr(bulten, "empty", True):
        try:
            aday = bulten[
                (bulten["ev"].astype(str) == ev) &
                (bulten["dep"].astype(str) == dep)
            ]
            if not aday.empty:
                if hedef_zaman is not None and "zaman" in aday.columns:
                    farklar = aday["zaman"].apply(
                        lambda z: abs((z - hedef_zaman).total_seconds())
                        if hasattr(z, "year") else float("inf")
                    )
                    row = aday.loc[farklar.idxmin()]
                else:
                    row = aday.iloc[0]
                m = row.to_dict()
        except Exception:
            m = None

    # Maç mevcut analiz kartlarında olmasa bile, oynanmamış eski kaydı kendi
    # liginden doğrudan sorgula ve 1-X-2 oranlarını yeniden al.
    if m is None and hedef_zaman is not None and secim.get("sport_key") and get_app_api_key():
        try:
            uzak_bulten = bulten_guncel_al(
                get_app_api_key(), [str(secim.get("sport_key"))], hedef_zaman.date()
            )
            if uzak_bulten is not None and not uzak_bulten.empty:
                match_id = str(secim.get("match_id", "") or "")
                if match_id and "match_id" in uzak_bulten.columns:
                    aday = uzak_bulten[uzak_bulten["match_id"].astype(str) == match_id]
                else:
                    aday = uzak_bulten[
                        (uzak_bulten["ev"].map(takim_adi_norm) == takim_adi_norm(ev))
                        & (uzak_bulten["dep"].map(takim_adi_norm) == takim_adi_norm(dep))
                    ]
                if not aday.empty:
                    m = aday.iloc[0].to_dict()
        except Exception:
            m = None

    # Bülten artık bellekte değilse yeni kuponlarda sakladığımız oranları kullan.
    if m is None:
        try:
            h, b, a = secim.get("h"), secim.get("b"), secim.get("a")
            if h is not None and b is not None and a is not None and pd.notna(h) and pd.notna(b) and pd.notna(a):
                m = {
                    "match_id": secim.get("match_id", ""),
                    "sport_key": secim.get("sport_key", ""),
                    "lig": secim.get("lig", ""),
                    "zaman": hedef_zaman,
                    "ev": ev,
                    "dep": dep,
                    "h": float(h), "b": float(b), "a": float(a),
                }
        except Exception:
            m = None

    gecmis = st.session_state.get("last_gecmis_df")
    if gecmis is None or getattr(gecmis, "empty", True):
        return None

    # Eski sonuç kayıtlarında oranlar saklanmamış olabilir. Aynı maçı tarihsel
    # veri içinde bulup o maçın kapanış 1-X-2 oranlarıyla detayı yeniden kur.
    if m is None and hedef_zaman is not None:
        try:
            tarih_serisi = pd.to_datetime(gecmis["Date"], errors="coerce")
            ev_norm, dep_norm = takim_adi_norm(ev), takim_adi_norm(dep)
            aday = gecmis[
                (tarih_serisi.dt.date == hedef_zaman.date())
                & (gecmis["HomeTeam"].map(takim_adi_norm) == ev_norm)
                & (gecmis["AwayTeam"].map(takim_adi_norm) == dep_norm)
            ]
            if not aday.empty:
                row = aday.iloc[-1]
                h_col = "REF_H" if "REF_H" in aday.columns else "B365H"
                d_col = "REF_D" if "REF_D" in aday.columns else "B365D"
                a_col = "REF_A" if "REF_A" in aday.columns else "B365A"
                m = {
                    "match_id": secim.get("match_id", ""),
                    "sport_key": secim.get("sport_key", ""),
                    "lig": secim.get("lig", row.get("league_code", "")),
                    "zaman": hedef_zaman, "ev": ev, "dep": dep,
                    "h": float(row[h_col]), "b": float(row[d_col]), "a": float(row[a_col]),
                }
        except Exception:
            m = None
    if m is None:
        return None
    if oran_fazi(m) == "unknown":
        m.update(odds_phase="legacy_unknown", history_detail_only=True)

    try:
        tolerans = hassasiyet_oku(secim.get("hassasiyet"))
    except Exception:
        tolerans = 0.08

    try:
        if secim.get("kayit_id"):
            t, b_det = hassasiyet_birlesik_hesapla(
                gecmis, m, max(1, int(st.session_state.get("top_min_ornek", 1) or 1)),
                sadece_ayni_lig=sadece_ayni_lig,
            )
        else:
            t, b_det = hesapla(gecmis, m, tolerans, sadece_ayni_lig=sadece_ayni_lig)
        if t is None:
            # Aynı lig filtresi eski kuponlarda eşleşmeyi engelliyorsa detayın
            # tamamen kaybolmaması için genel geçmişte bir kez daha dene.
            if secim.get("kayit_id"):
                t, b_det = hassasiyet_birlesik_hesapla(
                    gecmis, m, max(1, int(st.session_state.get("top_min_ornek", 1) or 1)),
                    sadece_ayni_lig=False,
                )
            else:
                t, b_det = hesapla(gecmis, m, tolerans, sadece_ayni_lig=False)
        if t is None:
            return None
        if m.get("history_detail_only"):
            t["nedenler"] = ["Eski kuponun oran saati bulunmuyor; bu detay yaklaşık geçmiş karşılaştırmasıdır.", *t.get("nedenler", [])]
        return {"m": m, "t": t, "b": b_det, "kupon_secim": secim}
    except Exception:
        return None


def ana_tahmin_gecmis_detayi(m, t, b_det):
    # Önce askıdaki/eksik İY verili ligleri çıkar; sayaç ve gösterim adedi
    # yalnızca gerçekten tabloda gösterilebilecek geçmiş maçlardan hesaplansın.
    b_det = sadece_tam_verili_gecmis(b_det)
    toplam_gecmis_ornek = len(b_det)

    gosterim_secimi = st.selectbox(
        "Gösterilecek geçmiş örnek",
        options=[10, 25, 50, "Tümü"],
        index=0,
        key=f"history_limit_{abs(hash(mac_key(m)))}",
    )
    gosterim_adedi = toplam_gecmis_ornek if gosterim_secimi == "Tümü" else min(int(gosterim_secimi), toplam_gecmis_ornek)

    st.markdown(f"""
    <div class="history-card">
      <div class="history-title" style="color:#f8fbff !important">Benzer Oranlı Geçmiş Maçlar (Gösterilen {gosterim_adedi} / Toplam {toplam_gecmis_ornek})</div>
      <div class="history-sub" style="color:#f8fbff !important">ℹ️ Tablodaki maçlar seçili oran aralığına (±{t['kullanilan_tolerans']:.2f}) en yakın bulunan benzer maçlardır.</div>
    </div>
    """, unsafe_allow_html=True)

    bd = b_det.head(gosterim_adedi).copy()
    dt = pd.DataFrame()
    dt["Tarih"] = bd["Date"].dt.strftime("%d.%m.%Y")
    dt["Ev Sahibi"] = bd["HomeTeam"]
    dt["Deplasman"] = bd["AwayTeam"]
    # Extra/worldwide geçmiş liglerde ilk yarı skorları (HTHG/HTAG) boş olabilir.
    # NaN değerlerini int'e çevirmek IntCastingNaNError üretir; eksik HT skorunu "-" göster.
    hthg_num = pd.to_numeric(bd.get("HTHG"), errors="coerce")
    htag_num = pd.to_numeric(bd.get("HTAG"), errors="coerce")
    iy_sonuc = (
        hthg_num.astype("Int64").astype(str)
        + "-"
        + htag_num.astype("Int64").astype(str)
    )
    dt["İY Sonuç"] = iy_sonuc.where(hthg_num.notna() & htag_num.notna(), "-")
    fthg_num = pd.to_numeric(bd.get("FTHG"), errors="coerce")
    ftag_num = pd.to_numeric(bd.get("FTAG"), errors="coerce")
    ms_sonuc = (
        fthg_num.astype("Int64").astype(str)
        + "-"
        + ftag_num.astype("Int64").astype(str)
    )
    dt["MS Sonuç"] = ms_sonuc.where(fthg_num.notna() & ftag_num.notna(), "-")
    dt["2.5 GOL"] = (bd["FTHG"] + bd["FTAG"] >= 3).map({True: "Üst", False: "Alt"})
    dt["KG"] = ((bd["FTHG"] > 0) & (bd["FTAG"] > 0)).map({True: "Var", False: "Yok"})
    dt["HT/FT"] = bd["HTR"].replace({"H": "1", "A": "2", "D": "X"}) + "/" + bd["FTR"].replace({"H": "1", "A": "2", "D": "X"})

    def color_cell(val):
        v = str(val)
        if v in ["Üst", "Var", "1/1", "2/2"]:
            return "background-color:#183925;color:#3ddb7c;font-weight:700"
        if v in ["Alt", "Yok"]:
            return "background-color:#391212;color:#ff6b6b;font-weight:700"
        if "1/2" in v or "2/1" in v or "X/1" in v or "1/X" in v or "X/2" in v or "2/X" in v:
            return "background-color:#37290f;color:#f1c40f;font-weight:700"
        return ""

    st.dataframe(
        dt.style.map(color_cell, subset=["2.5 GOL", "KG", "HT/FT"]),
        use_container_width=True,
        hide_index=True,
        height=min(700, 38 + len(dt) * 35),
    )



def baglam_analizi_goster(item):
    if not isinstance(item, dict):
        return
    m = item.get("m", {}) or {}
    t = item.get("t", {}) or {}
    secim = item.get("kupon_secim") if isinstance(item.get("kupon_secim"), dict) else {}
    label = str(secim.get("tahmin") or t.get("ana_label") or "")
    baglam = secim.get("baglam") if isinstance(secim.get("baglam"), dict) else None
    gecmis = st.session_state.get("last_gecmis_df")
    if not baglam:
        try:
            baglam = gunun_baglam_puani(gecmis, m, label) if gecmis is not None else None
        except Exception:
            baglam = None
    if not isinstance(baglam, dict):
        st.info("Bu maç için bağlam verisi bulunamadı.")
        return
    toplam = float(baglam.get("toplam", 0.0) or 0.0)
    h2h, form, saha, piyasa = baglam.get("h2h", {}) or {}, baglam.get("form", {}) or {}, baglam.get("saha", {}) or {}, baglam.get("piyasa25", {}) or {}
    def satir(ad, veri, aktif):
        puan=float(veri.get("puan",0.0) or 0.0)
        if not aktif:
            return f'<div style="color:#94a3b8"><b>{escape(ad)}:</b> Veri yok / uygulanmadı</div>'
        renk="#86efac" if puan>0 else "#fca5a5" if puan<0 else "#cbd5e1"
        return f'<div><b>{escape(ad)}:</b> <span style="color:{renk};font-weight:800">{puan:+.2f}</span> puan</div>'
    h2h_aktif=int(h2h.get("mac",0) or 0)>=3
    trenk="#86efac" if toplam>0 else "#fca5a5" if toplam<0 else "#cbd5e1"
    st.markdown(f'''<div style="background:#0d1728;border:1px solid #29415f;border-radius:14px;padding:14px 16px;margin:0 0 14px 0">
    <div style="font-family:Rajdhani,sans-serif;font-size:1.05rem;font-weight:800;color:#f8fafc;margin-bottom:8px">📊 BAĞLAM ANALİZİ · {escape(label)}</div>
    <div style="font-size:.82rem;color:#dbeafe;line-height:1.75">{satir("Son 5 genel form",form,bool(form.get("aktif")))}{satir("İç / dış saha formu",saha,bool(saha.get("aktif")))}{satir("H2H son karşılaşmalar",h2h,h2h_aktif)}{satir("2.5 piyasa doğrulaması",piyasa,bool(piyasa.get("aktif")))}</div>
    <div style="border-top:1px solid #26364d;margin-top:9px;padding-top:9px;font-size:.88rem;color:#e2e8f0">Toplam bağlam etkisi: <b style="color:{trenk}">{toplam:+.2f} puan</b></div></div>''', unsafe_allow_html=True)
    fp=form.get("profil",{}) if isinstance(form.get("profil"),dict) else {}
    if bool(form.get("aktif")) and fp:
        evf,depf=fp.get("ev",{}) or {},fp.get("dep",{}) or {}
        c1,c2=st.columns(2,gap="small")
        with c1:
            st.caption(f"🏠 {m.get('ev','')} · son {int(evf.get('mac',0) or 0)} genel maç")
            st.write(f"G/B/M: {int(evf.get('galibiyet',0))}/{int(evf.get('beraberlik',0))}/{int(evf.get('maglubiyet',0))} · 2.5 Üst %{float(evf.get('over25',0))*100:.0f} · KG Var %{float(evf.get('btts',0))*100:.0f} · Gol {float(evf.get('gf',0)):.1f}/{float(evf.get('ga',0)):.1f}")
        with c2:
            st.caption(f"✈️ {m.get('dep','')} · son {int(depf.get('mac',0) or 0)} genel maç")
            st.write(f"G/B/M: {int(depf.get('galibiyet',0))}/{int(depf.get('beraberlik',0))}/{int(depf.get('maglubiyet',0))} · 2.5 Üst %{float(depf.get('over25',0))*100:.0f} · KG Var %{float(depf.get('btts',0))*100:.0f} · Gol {float(depf.get('gf',0)):.1f}/{float(depf.get('ga',0)):.1f}")
    else:
        st.caption("Genel form: yeterli veri yok (iki takım için en az 3 geçmiş maç gerekli).")
    if bool(saha.get("aktif")):
        evs,deps=saha.get("ev",{}) or {},saha.get("dep",{}) or {}
        st.caption(f"🏟️ Saha formu: {int(saha.get('ev_mac',0) or 0)} iç saha + {int(saha.get('dep_mac',0) or 0)} dış saha maçı · Ev 2.5 Üst %{float(evs.get('over25',.5))*100:.0f}/KG %{float(evs.get('btts',.5))*100:.0f} · Dep 2.5 Üst %{float(deps.get('over25',.5))*100:.0f}/KG %{float(deps.get('btts',.5))*100:.0f}")
    else:
        st.caption(f"🏟️ Saha formu: yeterli veri yok (iç {int(saha.get('ev_mac',0) or 0)}, dış {int(saha.get('dep_mac',0) or 0)}; en az 3'er maç gerekli).")
    hmac,htutan=int(h2h.get("mac",0) or 0),int(h2h.get("tutan",0) or 0)
    if hmac:
        st.caption(f"🤝 H2H: {hmac} maçın {htutan} tanesi '{label}' seçimini destekledi.")
        rows=[]
        for r in (h2h.get("sonuclar",[]) or [])[:5]:
            rows.append({"Tarih":r.get("tarih","-"),"Maç":f"{r.get('ev','')} – {r.get('dep','')}","Skor":r.get("skor","-"),"Tahmine Uyum":"✅" if r.get("tuttu") else "❌"})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else:
        st.caption("🤝 H2H: geçmiş karşılaşma bulunamadı.")

    # API-Football fallback görünürlüğü: neden veri gelmediğini saklama.
    api_meta = baglam.get("api_fallback", {}) if isinstance(baglam.get("api_fallback"), dict) else {}
    kaynaklar = baglam.get("kaynaklar", {}) if isinstance(baglam.get("kaynaklar"), dict) else {}
    if kaynaklar:
        st.caption(
            "🛰️ Bağlam kaynakları: "
            f"Genel form = {kaynaklar.get('form','-')} · "
            f"Saha = {kaynaklar.get('saha','-')} · "
            f"H2H = {kaynaklar.get('h2h','-')}"
        )
    api_hata = str(api_meta.get("hata", "") or "").strip()
    if api_hata:
        st.caption(f"⚠️ API-Football fallback: {api_hata}")
    elif api_meta.get("aktif"):
        st.caption(f"🛰️ API-Football fallback: aktif · {int(api_meta.get('satir',0) or 0)} geçmiş maç satırı alındı.")

    if bool(piyasa.get("aktif")):
        st.caption(f"💹 2.5 piyasa: Üst {float(piyasa.get('over')):.2f} · Alt {float(piyasa.get('under')):.2f} · Seçimin marj-arındırılmış piyasa olasılığı ≈ %{float(piyasa.get('olasilik',0)):.1f}.")
    elif "2.5" in label:
        st.caption("💹 2.5 piyasa: bu maç için gerçek Üst/Alt oranı bulunamadı.")
    else:
        st.caption("💹 2.5 piyasa: seçilen market 2.5 Alt/Üst olmadığı için bu doğrulama uygulanmıyor.")

def detay_ana_icerik():
    item = secili_detay_itemi()
    m, t, b_det = item["m"], item["t"], item["b"]

    durum_color, durum_text = mac_durum_badge(m["zaman"])

    if st.button("✕ Kapat", key="close_detail_popup_btn", use_container_width=True):
        st.session_state.detay_idx = None
        st.session_state.detay_item = None
        st.rerun()

    st.markdown(
        f"""
        <div class="detail-header-box">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap">
            <div>
              <div style="font-family:Rajdhani,sans-serif;font-size:2rem;font-weight:700;color:#f8fbff;letter-spacing:1px;line-height:1.1">
                {m['ev'].upper()} – {m['dep'].upper()}
              </div>
              <div style="font-size:0.92rem;color:#9db2d1;margin-top:8px">
                {m['lig']} &nbsp;·&nbsp; {format_tr_date(m['zaman'].date())} &nbsp;·&nbsp; {m['zaman'].strftime('%H:%M')}
              </div>
            </div>
            <div style="text-align:right">
              <span class="live-badge" style="background:{durum_color};color:white">{durum_text}</span><br>
              <span style="font-size:0.82rem;color:#9db2d1;display:inline-block;margin-top:8px">📊 {int(t['ornek'])} örnek</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ms_label_long = "Ev Sahibi" if t["ms_mod"] == "H" else "Deplasman" if t["ms_mod"] == "A" else "Beraberlik"

    st.markdown(f"""
    <div class="hero-boxes">
      <div class="hbox green">
        <div class="hb-label">ANA TAHMİN</div>
        <div class="hb-val">{t['ana_label']}</div>
        <div class="hb-sub">Maç Sonucu: {ms_label_long}</div>
        {"<div style='margin-top:8px;font-size:0.76rem;color:#ff8b8b'>⚠️ Maç sonucu tarafı net değil</div>" if t.get("belirsiz") and t.get("ana_label") in ["MS 1", "Beraberlik", "MS 2"] else ""}
      </div>
      <div class="hbox blue">
        <div class="hb-label">GÜVEN SKORU</div>
        <div class="hb-val">{int(t['ana_p'])}%</div>
        <div><span class="hb-badge {t['guven_badge_cls']}">{t['guven_badge_lbl']}</span></div>
      </div>
      <div class="hbox dark">
        <div class="hb-label">TAHMİNİ SKOR</div>
        <div class="hb-val">{t['eg']} – {t['dg']}</div>
        <div class="hb-sub">En Olası Skor</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:14px 18px;margin-bottom:14px">
      <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between">
        <div style="font-size:0.82rem;color:#c7cfdd">Kullanılan tolerans: <b>{t['kullanilan_tolerans']:.2f}</b> · Önerilen: <b>{t['onerilen_tolerans']}</b></div>
        <div style="font-size:0.82rem;color:#c7cfdd">Örnek: <b>{int(t['ornek'])}</b> · Dinamik min maç: <b>{t['onerilen_min_mac']}</b></div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;align-items:center">
        <span style="background:{t.get('ornek_renk', '#44506b')};color:#fff;padding:4px 10px;border-radius:999px;font-size:0.75rem;font-weight:700">{t.get('ornek_durum', 'Standart')}</span>
        <span style="font-size:0.78rem;color:#8f98ab">{t['tolerans_yorumu']}</span>
        <span style="font-size:0.78rem;color:#77b4ff">Tavsiye: {t['tolerans_tavsiyesi']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Güven çarpanı: {t['guven_carpani']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Maç tipi: {t['match_type']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Gol profili: {t['goal_profile']}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption(f"Oran karşılaştırması: {t.get('odds_basis', 'Zaman bilgisi yok')} · "
               f"{t.get('goal_matching', '')}")
    if "desteği yok" in str(t.get("goal_matching", "")):
        st.caption("Gol oranı eşleştirmesi için geçmiş 2.5 oranları ve zaman uyumlu güncel oranlar gerekir. Eski veri dosyalarında geçmiş veriyi yenilemek gerekebilir.")
    st.caption(f"Etkin örnek: MS {t.get('effective_ms_samples', 0):.1f} / Gol {t.get('effective_goal_samples', 0):.1f} · "
               f"Güven dalgalanması: {t.get('confidence_spread', 0):.1f} puan")
    st.caption(f"Geçmiş oran kaynağı: {t.get('odds_source', 'B365')} · "
               + ("Farklı şirketler: marjdan arındırılmış yaklaşık profil" if t.get('odds_cross_bookmaker') else "Aynı şirket oranları"))
    if t.get("birlesik_model"):
        st.caption(f"{int(t.get('stability_count', 0))}/11 hassasiyet desteği · "
                   f"{int(t.get('stability_unique_pools', 0))} farklı örnek havuzu · "
                   f"{int(t.get('unique_history_samples', 0))} benzersiz maç. Hassasiyetler bağımsız deney değildir.")
    baglam_analizi_goster(item)

    if t["flip_p"] >= 0.12:
        st.markdown(f"""
        <div class="surpriz-radar">
        🔥 SÜRPRİZ RADARI — %{int(t['flip_p']*100)} ihtimalle HT/FT sürprizi (1/2 - 2/1) tespit edildi!
        </div>""", unsafe_allow_html=True)

    left, right = st.columns(2)

    with left:
        st.markdown(f"""
        <div class="tahmin-kart">
          <div class="tk-title">MAÇ TAHMİNLERİ</div>

          <div class="tk-row">
            <span class="tk-key">🏆 Maç Sonucu <small style="color:#8fa0ba">MS 1/X/2</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">1</div><div style="font-weight:700;color:#27ae60">%{int(t['ms1_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">X</div><div style="font-weight:700;color:#f1c40f">%{int(t['msx_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">2</div><div style="font-weight:700;color:#e74c3c">%{int(t['ms2_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⚽ 2.5 Üst/Alt <small style="color:#8fa0ba">Toplam Gol</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Üst</div><div style="font-weight:700;color:#27ae60">%{int(t['ms25_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Alt</div><div style="font-weight:700;color:#e74c3c">%{int(t['ms25a_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">🤝 Karşılıklı Gol <small style="color:#8fa0ba">KG Var / Yok</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Var</div><div style="font-weight:700;color:#27ae60">%{int(t['kg_var_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Yok</div><div style="font-weight:700;color:#e74c3c">%{int(t['kg_yok_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⏱ İlk Yarı Sonucu <small style="color:#8fa0ba">İY 1/X/2</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">1</div><div style="font-weight:700;color:#27ae60">%{int(t['iy1_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">X</div><div style="font-weight:700;color:#f1c40f">%{int(t['iyx_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">2</div><div style="font-weight:700;color:#e74c3c">%{int(t['iy2_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⏱ İlk Yarı 0.5 Üst/Alt</span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Üst</div><div style="font-weight:700;color:#27ae60">%{int(t['iy05_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Alt</div><div style="font-weight:700;color:#e74c3c">%{int(t['iy05a_p'])}</div></div>
            </div>
          </div>

        </div>
        """, unsafe_allow_html=True)

    with right:
        ms35a = 100 - int(t["ms35_p"])
        ms35_cls = "db-green" if t["ms35_p"] >= 50 else "db-gold"
        ms35_lbl = f"Üst %{int(t['ms35_p'])}" if t["ms35_p"] >= 50 else f"Alt %{ms35a}"

        kg_cls = "db-green" if t["kg_var_p"] >= 50 else "db-red"
        kg_lbl = f"Var %{int(t['kg_var_p'])}" if t["kg_var_p"] >= 50 else f"Yok %{int(t['kg_yok_p'])}"

        iy_cls = "db-green" if t["iy05_p"] >= 50 else "db-red"
        iy_lbl = f"Üst %{int(t['iy05_p'])}" if t["iy05_p"] >= 50 else f"Alt %{int(t['iy05a_p'])}"
        iy15_cls = "db-green" if t.get("iy15_p", 0) >= 55 else "db-gold"
        iy15_lbl = f"Üst %{int(t.get('iy15_p', 0))}"
        iykg_cls = "db-green" if t.get("iykg_var_p", 0) >= 50 else "db-red"
        iykg_lbl = f"Var %{int(t.get('iykg_var_p', 0))}" if t.get("iykg_var_p", 0) >= 50 else f"Yok %{int(t.get('iykg_yok_p', 0))}"

        htft_cls = "db-green" if t["htft_p"] >= 40 else "db-gold"
        combo_cls = "db-gold" if t.get("combo_var", False) else "db-red"
        combo_text = t.get("combo_label", "")
        combo_row = ""
        if combo_text:
            combo_row = f"""
          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🎯</span><div><div class="diger-name">Güçlü Kombo</div><div class="diger-sub">{t.get('combo_level', 'Destekli')}</div></div></div>
            <span class="diger-badge {combo_cls}">{combo_text} %{int(t.get('combo_p', 0))}</span>
          </div>"""

        st.markdown(f"""
        <div class="diger-kart">
          <div class="tk-title">DİĞER ÖNERİLER</div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🔁</span><div><div class="diger-name">HT/FT</div><div class="diger-sub">1. Yarı / Maç Sonu</div></div></div>
            <span class="diger-badge {htft_cls}">{t['htft_mod']} %{int(t['htft_p'])}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⚽</span><div><div class="diger-name">Toplam Gol 3.5</div><div class="diger-sub">Tahmini Gol Sayısı</div></div></div>
            <span class="diger-badge {ms35_cls}">{ms35_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⏱</span><div><div class="diger-name">İlk Yarı / 0.5 Üst</div><div class="diger-sub">İlk Yarı Toplam Gol</div></div></div>
            <span class="diger-badge {iy_cls}">{iy_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⏱</span><div><div class="diger-name">İlk Yarı / 1.5 Üst</div><div class="diger-sub">İlk yarıda 2+ gol</div></div></div>
            <span class="diger-badge {iy15_cls}">{iy15_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🤝</span><div><div class="diger-name">İlk Yarı KG</div><div class="diger-sub">İlk yarıda iki takım da gol</div></div></div>
            <span class="diger-badge {iykg_cls}">{iykg_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🤝</span><div><div class="diger-name">Karşılıklı Gol</div><div class="diger-sub">KG Var / Yok</div></div></div>
            <span class="diger-badge {kg_cls}">{kg_lbl}</span>
          </div>

          {combo_row}

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🧩</span><div><div class="diger-name">En Uyumlu Senaryo</div><div class="diger-sub">Model özeti</div></div></div>
            <span class="diger-badge db-blue">{t.get('scenario_label', '')}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">📍</span><div><div class="diger-name">Canlı Tercih</div><div class="diger-sub">{t['canli_label']}</div></div></div>
            <span class="diger-badge db-green">%{int(t['canli_p'])}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⚡</span><div><div class="diger-name">Canlı Strateji</div><div class="diger-sub">İlk 10-20 dakika</div></div></div>
            <span class="diger-badge db-blue">İzle</span>
          </div>

          <div style="font-size:0.78rem;color:#c7d2e3;line-height:1.5;padding:10px 12px 8px 12px;border:1px solid #1f2a44;background:#0b1628;border-radius:10px;margin-top:8px">
            {t.get('canli_strateji', '')}
          </div>

          <div class="risk-row" style="margin-top:14px">
            <span class="rk">ORANLAR</span>
            <div style="display:flex;gap:16px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#94a3b8">1</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['h']:.2f}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#94a3b8">X</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['b']:.2f}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#94a3b8">2</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['a']:.2f}</div></div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Ek marketler detay ekranında kullanıcı isterse yüklenir.
    # Toggle kapalıyken ek API çağrısı yapılmaz; uzun bültende gereksiz kredi/süre harcanmaz.
    _ek_market_key = f"detay_ek_market_goster_{abs(hash(mac_key(m)))}"
    _ek_market_acik = st.toggle(
        "💹 Ek marketleri göster",
        value=False,
        key=_ek_market_key,
        help="İY KG, İY/MS, doğru skor, alternatif Alt/Üst, korner ve kart oranlarını yükler.",
    )
    if _ek_market_acik:
        detay_ek_market_oranlari_goster(m)
    else:
        st.caption("Ek marketler kapalı · Açılmadıkça ilave The Odds API sorgusu yapılmaz.")

    st.markdown("<br>", unsafe_allow_html=True)

    neden_html = "".join([f'<div class="neden-item">• {x}</div>' for x in t["nedenler"]])
    st.markdown(f"""
    <div class="neden-kart" style="margin-bottom:14px">
      <div class="tk-title">NEDEN BU TAHMİN?</div>
      {neden_html}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📊 Ana tahminin benzer geçmiş maçları", expanded=True):
        ana_tahmin_gecmis_detayi(m, t, b_det)




def detay_gecmis_sidebar():
    item = secili_detay_itemi()
    m = item["m"]
    gecmis = st.session_state.get("last_gecmis_df")
    if gecmis is None or getattr(gecmis, "empty", True):
        st.info("Son maç geçmişi bulunamadı.")
        return
    adaylar = pd.unique(pd.concat([gecmis["HomeTeam"], gecmis["AwayTeam"]], ignore_index=True).dropna())
    eslesen_ev = takim_adi_eslestir(m.get("ev", ""), adaylar)
    eslesen_dep = takim_adi_eslestir(m.get("dep", ""), adaylar)
    # Saha filtresi seçildiğinde de gerçekten son 10 iç/deplasman maçını bulabilmek
    # için daha geniş geçmiş çekilir, filtre sonrasında 10 maçla sınırlandırılır.
    son_ev = takim_son_maclari(gecmis, eslesen_ev, m.get("zaman"), 100)
    son_dep = takim_son_maclari(gecmis, eslesen_dep, m.get("zaman"), 100)
    h2h_maclar, h2h_toplam = takimlar_arasi_maclar(
        gecmis, eslesen_ev, eslesen_dep, m.get("zaman"), 10
    )

    st.markdown(
        """
        <div class="detail-form-sidebar-title">
          <div>📈 FORM & GEÇMİŞ</div>
          <span>Manuel kontrol · Tahmine dahil değil</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mac_kimligi = abs(hash(mac_key(m)))
    ev_col, dep_col, h2h_col = st.columns(3, gap="small")

    with ev_col:
        with st.container(border=True):
            st.markdown(f"**🏠 {kart_takim_adi(m.get('ev', 'Ev sahibi'))} · Son 10**")
            ev_saha = st.selectbox(
                "Saha filtresi", ["Tümü", "Sadece iç saha", "Sadece deplasman"],
                key=f"ev_saha_filtre_{mac_kimligi}", label_visibility="collapsed",
            )
            ev_filtreli = takim_maclarini_sahaya_gore_filtrele(son_ev, eslesen_ev, ev_saha).head(10)
            ev_tablo = son5_tablo_hazirla(ev_filtreli, eslesen_ev)
            if ev_tablo.empty:
                st.info(f"Bu filtrede maç bulunamadı. Eşleşen takım: {kart_takim_adi(eslesen_ev) if eslesen_ev else 'yok'}")
            else:
                st.markdown(son_mac_kartlari_html(ev_tablo), unsafe_allow_html=True)

    with dep_col:
        with st.container(border=True):
            st.markdown(f"**✈️ {kart_takim_adi(m.get('dep', 'Deplasman'))} · Son 10**")
            dep_saha = st.selectbox(
                "Saha filtresi", ["Tümü", "Sadece iç saha", "Sadece deplasman"],
                key=f"dep_saha_filtre_{mac_kimligi}", label_visibility="collapsed",
            )
            dep_filtreli = takim_maclarini_sahaya_gore_filtrele(son_dep, eslesen_dep, dep_saha).head(10)
            dep_tablo = son5_tablo_hazirla(dep_filtreli, eslesen_dep)
            if dep_tablo.empty:
                st.info(f"Bu filtrede maç bulunamadı. Eşleşen takım: {kart_takim_adi(eslesen_dep) if eslesen_dep else 'yok'}")
            else:
                st.markdown(son_mac_kartlari_html(dep_tablo), unsafe_allow_html=True)

    with h2h_col:
        with st.container(border=True):
            st.markdown(f"**🤝 İkili rekabet · {h2h_toplam} maç**")
            h2h_tablo = h2h_tablo_hazirla(h2h_maclar)
            if h2h_tablo.empty:
                st.info("Geçmiş karşılaşma bulunamadı.")
            else:
                st.caption(f"En güncel {len(h2h_tablo)} karşılaşma")
                st.markdown(h2h_kartlari_html(h2h_tablo), unsafe_allow_html=True)


def detay_popup_icerigi():
    panel_acik = bool(st.session_state.get("detay_gecmis_acik", False))
    dugme_metni = "✕ Geçmişi Kapat" if panel_acik else "📈 Geçmişi Aç"

    _, dugme_col = st.columns([3.2, 1.3], gap="small")
    with dugme_col:
        if st.button(dugme_metni, key="toggle_detail_history", use_container_width=True):
            st.session_state.detay_gecmis_acik = not panel_acik
            st.rerun()

    if not panel_acik:
        detay_ana_icerik()
        return

    ana_col, side_col = st.columns([1.8, 2.2], gap="small")
    with ana_col:
        detay_ana_icerik()
    with side_col:
        with st.container(border=True):
            detay_gecmis_sidebar()


if st.session_state.detay_item is not None or st.session_state.detay_idx is not None:
    try:
        @st.dialog("Maç Detayı", width="large")
        def _detay_modal():
            detay_popup_icerigi()
        _detay_modal()
    except Exception:
        # Eski Streamlit sürümlerinde st.dialog yoksa detay yine sayfanın üstünde gösterilir.
        with st.container(border=True):
            detay_popup_icerigi()

fl = st.session_state.final_list

# Son analiz teşhisi rerun sonrasında da görünür kalsın.
if "son_bulten_mac_sayisi" in st.session_state:
    _bc = int(st.session_state.get("son_bulten_mac_sayisi", 0) or 0)
    _fc = int(st.session_state.get("son_final_mac_sayisi", 0) or 0)
    _ae = st.session_state.get("son_api_hatasi")
    _dt = st.session_state.get("son_analiz_tarihi_secili", "")
    _fs = st.session_state.get("analiz_filtre_sayaclari", {}) or {}

    if _ae:
        st.error(f"🔎 Son analiz teşhisi · Tarih: {_dt} · API/bülten: {_bc} maç · Analize kalan: {_fc} · Hata: {_ae}")
    elif _bc == 0:
        st.warning(f"🔎 Son analiz teşhisi · Tarih: {_dt} · The Odds API'den bu filtrelerle 0 maç geldi.")
    elif _fc == 0:
        _gr = int(st.session_state.get("son_gecmis_satir_sayisi", 0) or 0)
        _gh = st.session_state.get("son_gecmis_kaynak_hatalari", []) or []
        _gk = st.session_state.get("son_gecmis_kaynak", "") or ""
        if _gr == 0:
            st.error(
                f"🔎 Geçmiş veri yok · API: {_bc} maç geliyor ama Football-Data erişilemiyor ve henüz yerel cache oluşmamış."
            )
            st.caption(
                "İlk başarılı Football-Data bağlantısında yapaikupon_gecmis_cache.csv otomatik oluşturulacak. "
                "Sonraki kesintilerde uygulama bu dosyadan çalışmaya devam edecek."
            )
            if _gh:
                st.caption("Football-Data hataları: " + " | ".join(map(str, _gh[:6])))
        else:
            st.warning(
                f"🔎 Son analiz teşhisi · API: {_bc} · geçmiş veri: {_gr} satır · kaynak: {_gk} · "
                f"hesapla() sonuç yok: {_fs.get('t_none',0)} · minimum örnekten elenen: {_fs.get('ornek',0)} · "
                f"güven eşiğinden elenen: {_fs.get('guven',0)} · geçen: {_fs.get('gecen',0)} · "
                f"tolerans: {_fs.get('tolerans','?')} · min örnek: {_fs.get('min_ornek','?')} · "
                f"güven eşiği: {_fs.get('oynanabilir_esik','?')}"
            )
    else:
        # Analiz başarılıysa teşhis satırını kullanıcıya gösterme.
        # API/geçmiş veri problemi veya 0 sonuç olduğunda yukarıdaki uyarılar görünmeye devam eder.
        pass

st.markdown(
    f'<div style="font-size:.88rem;color:#475569;font-weight:800;margin-top:10px">📅 {format_tr_date(secili_tarih)}</div>',
    unsafe_allow_html=True,
)


# ==========================================================
# SADE ANALIZ PANELI
# Auto kupon builder ve 30 gunluk kasa plani kaldirildi.
# ==========================================================
st.markdown("<br>", unsafe_allow_html=True)

# Top 50 Market, ana analiz slider sonucundan bağımsızdır.
# Örneğin slider 0.00 iken ana analiz hiç eşleşme bulamasa bile
# Top 50 kendi 0.00–0.10 taramasını kullanarak gösterilmeye devam eder.
aktif_sayfa_modu = st.session_state.get("sayfa_modu", "Maç Analizi")

if not fl and aktif_sayfa_modu != "Top 50 Market":
    st.markdown("""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:42px;text-align:center;margin-top:20px">
      <div style="font-size:2rem;margin-bottom:12px">⚡</div>
      <div style="font-family:Rajdhani,sans-serif;font-size:1.35rem;color:#fff;font-weight:700">Analizi Başlatın</div>
      <div style="font-size:0.9rem;color:#666;margin-top:6px">Sol menüden API key ve filtreleri ayarla, sonra ANALİZİ BAŞLAT butonuna bas.</div>
    </div>
    """, unsafe_allow_html=True)
else:
    indexed_fl = list(enumerate(fl))
    yuksek = [(idx, x) for idx, x in indexed_fl if x["t"]["ana_p"] >= 70]
    orta = [(idx, x) for idx, x in indexed_fl if 55 <= x["t"]["ana_p"] < 70]
    kombolu = [(idx, x) for idx, x in indexed_fl if x["t"].get("combo_var", False)]

    # ==========================================================
    # GUNUN EN IYI 10 MACI - HASSASIYETTEN BAGIMSIZ
    # API kullanmaz; analizde cekilen maclar uzerinden 0.00 - 0.10 arasi en iyi toleransi secer.
    # ==========================================================
    gunun_top_liste = st.session_state.get("top50_list", [])
    top_baslik = "🔥 TOP 50 MARKET"

    if aktif_sayfa_modu == "Top 50 Market":
        if gunun_top_liste:
            st.markdown(f"""<div class="list-heading">{top_baslik}</div>""", unsafe_allow_html=True)
            st.markdown(
                """
                <div style="font-size:0.86rem;color:#64748b;margin:0 0 12px 0;">
                    Bu bölüm seçili hassasiyete bağlı değildir. Her maç 0.00–0.10 arasında 0.01 adımlarla denenir.
                    MS, Alt/Üst, KG, İlk Yarı ve Kombo adayları arasından en güçlü market seçilir.
                </div>
                """,
                unsafe_allow_html=True,
            )

            for sira, item in enumerate(gunun_top_liste, start=1):
                m = item["m"]
                t = item["t"]
                guven = int(t.get("top10_market_guven", t.get("ana_p", 0)) or 0)
                if guven >= 70:
                    renk = "#22c55e"
                    label = "Yüksek"
                elif guven >= 55:
                    renk = "#f59e0b"
                    label = "Orta"
                else:
                    renk = "#ef4444"
                    label = "Düşük"

                market_label = t.get("top10_market_label", t.get("ana_label", "-"))
                market_tip = t.get("top10_market_tip", "Market")
                skor = f"{t.get('eg', '')}-{t.get('dg', '')}"
                oran_raw = t.get("top10_market_oran", t.get("ana_odd"))
                oran = fmt_odd(oran_raw)
                if not oran:
                    oran = "—"
                saat = m["zaman"].strftime("%H:%M") if hasattr(m.get("zaman"), "strftime") else ""
                en_iyi_tol = float(item.get("top10_tol", t.get("kullanilan_tolerans", 0)) or 0)
                top10_skor = item.get("top10_skor", "")
                hassasiyetler = item.get("top10_hassasiyetler", t.get("top10_hassasiyetler", [])) or []
                hassasiyet_text = ", ".join([f"{float(x):.2f}" for x in hassasiyetler])
                if not hassasiyet_text:
                    hassasiyet_text = f"{en_iyi_tol:.2f}"
                hassasiyet_sayisi = int(item.get("top10_hassasiyet_sayisi", t.get("top10_hassasiyet_sayisi", len(hassasiyetler))) or 0)
                stabilite_skoru = item.get("top10_stabilite_skoru", t.get("top10_stabilite_skoru", top10_skor))
                edge_html = ""

                kart_col, btn_col = st.columns([7, 1])
                with kart_col:
                    st.markdown(
                        f"""
                        <div style="background:#0f172a;border:1px solid #1f2a44;border-radius:14px;padding:14px 16px;margin-bottom:10px;color:#f8fafc;">
                            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
                                <div>
                                    <div style="font-size:0.82rem;color:#facc15;font-weight:800;">#{sira} · {escape(str(m.get('lig','')))} · {saat}</div>
                                    <div style="font-size:1.05rem;font-weight:800;margin-top:4px;">{escape(str(m.get('ev','')))} - {escape(str(m.get('dep','')))}</div>
                                </div>
                                <div style="text-align:right;min-width:130px;">
                                    <div style="font-size:0.70rem;color:#94a3b8;font-weight:700;">GÜVEN</div>
                                    <div style="font-size:1.05rem;font-weight:900;color:{renk};">%{guven} ({label})</div>
                                </div>
                            </div>
                            <div style="margin-top:9px;font-size:0.88rem;color:#e5e7eb;">
                                Market: <b>{escape(str(market_label))}</b> <span style="color:#94a3b8;">({escape(str(market_tip))})</span> ·
                                Tahmini Skor: <b>{escape(str(skor))}</b> ·
                                Örnek: <b>{int(t.get('ornek',0) or 0)}</b> ·
                                Oran: <b>{escape(str(oran))}</b>
                            </div>
                            <div style="margin-top:7px;font-size:0.78rem;color:#9db2d1;">
                                Çıktığı hassasiyetler: <b style="color:#facc15;">{escape(str(hassasiyet_text))}</b> ·
                                Güven hassasiyet skoru: <b>{stabilite_skoru}</b> ·
                                Stabilite: <b>{hassasiyet_sayisi}/11</b>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with btn_col:
                    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
                    btn_key = f"top10_detay_{sira}_{abs(hash(str(m.get('ev','')) + str(m.get('dep','')) + str(m.get('zaman',''))))}"
                    if st.button("Detay →", key=btn_key, use_container_width=True):
                        st.session_state.detay_item = item
                        st.session_state.detay_idx = None
                        st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.info(f"{top_baslik} listesi için önce analizi başlatmalısın.")
        st.stop()

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        if st.button(f"Tümü {len(fl)}", use_container_width=True, key="f1"):
            st.session_state.filtre = "tumu"
            st.rerun()
    with fc2:
        if st.button(f"🔥 Yüksek Güven {len(yuksek)}", use_container_width=True, key="f2"):
            st.session_state.filtre = "yuksek"
            st.rerun()
    with fc3:
        if st.button(f"🟡 Orta Güven {len(orta)}", use_container_width=True, key="f3"):
            st.session_state.filtre = "orta"
            st.rerun()
    with fc4:
        if st.button(f"🎯 Güçlü Kombo {len(kombolu)}", use_container_width=True, key="f4"):
            st.session_state.filtre = "kombo"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    filtre = st.session_state.filtre
    if filtre == "yuksek":
        goster = list(yuksek)
    elif filtre == "orta":
        goster = list(orta)
    elif filtre == "kombo":
        goster = list(kombolu)
    else:
        goster = list(indexed_fl)

    # Maç Analizi kartlarını istenen güven ailesine göre sırala.
    # Tahminlerin kendisini değiştirmez; yalnızca ekrandaki kart sırasını değiştirir.
    # Oran filtresi değiştiğinde daha önce kapatılmış/son açılmış detay modalının
    # session_state üzerinden yeniden açılmasını engelle.
    def _mac_analizi_oran_filtresi_degisti():
        st.session_state.detay_idx = None
        st.session_state.detay_item = None
        st.session_state.detay_gecmis_acik = False

    sir_col, oran_col = st.columns([1.35, 1.0])
    with sir_col:
        siralama_secimi = st.selectbox(
            "Sırala",
            ["Güven", "Oran", "2.5 Alt / Üst", "KG", "Kombo", "Lig"],
            index=0,
            key="mac_analizi_siralama",
        )
    with oran_col:
        gosterilecek_min_oran = st.number_input(
            "Gösterilecek minimum oran",
            min_value=1.01,
            max_value=20.00,
            value=1.50,
            step=0.05,
            format="%.2f",
            key="mac_analizi_min_oran",
            help="Gerçek bookmaker oranı bu değerin altında olan tahmin gösterilmez. Ana tahmin geçmezse gerçek oranı bulunan alternatif kontrol edilir.",
            on_change=_mac_analizi_oran_filtresi_degisti,
        )

    # Minimum oran filtresi artık kartı doğrudan silmez.
    # Ana tahmin eşiği geçemiyorsa aynı maçın alternatif ve kombo seçeneğine bakılır.
    # Eşiği geçen yedekler arasından güveni en yüksek olan kartın ana gösterimi olur.
    # Böylece örneğin ana tahmin 1.35 ise, 1.70 oranlı güçlü alternatif/kombo varsa maç kaybolmaz.
    def _oran_filtresine_gore_secim(pair):
        real_i, item = pair
        m = item["m"]
        t0 = item["t"]

        try:
            min_odd = float(gosterilecek_min_oran)
        except (TypeError, ValueError):
            min_odd = 1.50

        ana_odd = t0.get("ana_odd")
        try:
            ana_odd_f = float(ana_odd) if ana_odd is not None else None
        except (TypeError, ValueError):
            ana_odd_f = None

        # Minimum oran filtresi yalnızca gerçek bookmaker oranıyla çalışır.
        # Oranı bilinmeyen market artık otomatik geçmez; önce gerçek oranı olan
        # alternatiflere bakılır. Böylece HT/FT / kombo tahmini oranları filtreyi
        # yanlışlıkla geçiremez.
        if ana_odd_f is not None and ana_odd_f >= min_odd:
            return pair

        adaylar = []

        # Alternatif tahminin gerçek 1/X/2 oranı mevcutsa kullan.
        alt_label = str(t0.get("alt_label", "") or "").strip()
        if alt_label:
            alt_odd = market_label_to_odd(m, alt_label)
            try:
                alt_odd_f = float(alt_odd) if alt_odd is not None else None
            except (TypeError, ValueError):
                alt_odd_f = None
            if alt_odd_f is not None and alt_odd_f >= min_odd:
                adaylar.append({
                    "tip": "Alternatif",
                    "label": alt_label,
                    "guven": float(t0.get("alt_p", 0) or 0),
                    "oran": alt_odd_f,
                })

        # Kombolar için gerçek market oranı yoksa minimum oran filtresinde
        # tahmini oran KULLANILMAZ. İleride exact combo marketi çekilirse
        # market_label_to_odd üzerinden otomatik olarak buraya dahil edilebilir.
        combo_label = str(t0.get("combo_label", "") or "").strip()
        if t0.get("combo_var") and combo_label:
            combo_odd = market_label_to_odd(m, combo_label)
            try:
                combo_odd_f = float(combo_odd) if combo_odd is not None else None
            except (TypeError, ValueError):
                combo_odd_f = None
            if combo_odd_f is not None and combo_odd_f >= min_odd:
                adaylar.append({
                    "tip": "Kombo",
                    "label": combo_label,
                    "guven": float(t0.get("combo_p", 0) or 0),
                    "oran": combo_odd_f,
                    "oran_tahmini": False,
                })

        if not adaylar:
            return None

        secim = max(adaylar, key=lambda x: (x["guven"], x["oran"]))
        yeni_item = dict(item)
        yeni_t = dict(t0)
        yeni_t["filtre_orijinal_ana_label"] = t0.get("ana_label")
        yeni_t["filtre_orijinal_ana_p"] = t0.get("ana_p")
        yeni_t["filtre_orijinal_ana_odd"] = t0.get("ana_odd")
        yeni_t["filtre_secim_tipi"] = secim["tip"]
        yeni_t["filtre_secim_oran_tahmini"] = bool(secim.get("oran_tahmini", False))
        yeni_t["ana_label"] = secim["label"]
        yeni_t["ana_p"] = int(round(secim["guven"]))
        yeni_t["ana_odd"] = float(secim["oran"])

        # Ana karta terfi eden seçeneği sağ tarafta tekrar göstermeyelim.
        if secim["tip"] == "Alternatif":
            yeni_t["alt_label"] = ""
            yeni_t["alt_p"] = 0
        elif secim["tip"] == "Kombo":
            yeni_t["combo_label"] = ""
            yeni_t["combo_var"] = False

        yeni_item["t"] = yeni_t
        return (real_i, yeni_item)

    _filtrelenmis_goster = []
    for _pair in goster:
        _secim_pair = _oran_filtresine_gore_secim(_pair)
        if _secim_pair is not None:
            _filtrelenmis_goster.append(_secim_pair)
    goster = _filtrelenmis_goster

    def _mac_analizi_siralama_anahtari(pair):
        t = pair[1]["t"]
        if siralama_secimi == "Oran":
            return (
                float(t.get("ana_odd", 0) or 0),
                float(t.get("ana_p", 0) or 0),
            )
        if siralama_secimi == "2.5 Alt / Üst":
            return (
                max(float(t.get("ms25_p", 0) or 0), float(t.get("ms25a_p", 0) or 0)),
                float(t.get("ana_p", 0) or 0),
            )
        if siralama_secimi == "KG":
            return (
                max(float(t.get("kg_var_p", 0) or 0), float(t.get("kg_yok_p", 0) or 0), float(t.get("kg_p", 0) or 0)),
                float(t.get("ana_p", 0) or 0),
            )
        if siralama_secimi == "Kombo":
            return (
                float(t.get("combo_p", 0) or 0),
                float(t.get("ana_p", 0) or 0),
            )
        return (
            float(t.get("ana_p", 0) or 0),
            float(t.get("playable_score", 0) or 0),
        )

    if siralama_secimi == "Lig":
        # Aynı ligden bulunan geçmiş örnek sayısı en yüksek olan maç üstte.
        # Eşitlikte toplam örnek, ardından güven oranı kullanılır.
        goster = sorted(
            goster,
            key=lambda pair: (
                int(pair[1]["t"].get("ayni_lig_ornek", 0) or 0),
                int(pair[1]["t"].get("ornek", 0) or 0),
                float(pair[1]["t"].get("ana_p", 0) or 0),
            ),
            reverse=True,
        )
    else:
        goster = sorted(goster, key=_mac_analizi_siralama_anahtari, reverse=True)

    st.markdown("<br>", unsafe_allow_html=True)

    for i, (real_i, item) in enumerate(goster):
        m, t = item["m"], item["t"]
        gc, _, _ = guven_renk(t["ana_p"])

        pill_cls = ""
        if "MS 2" in t["ana_label"]:
            pill_cls = "kirmizi"
        elif "Beraberlik" in t["ana_label"] or "2.5" in t["ana_label"]:
            pill_cls = "sari"
        elif "Zayıf" in t["ana_label"]:
            pill_cls = "gri"

        combo_text = t.get("combo_label", "")
        skor_html = f'<div style="margin-top:8px;font-size:0.76rem;color:#cbd5e1">🎯 Tahmini skor: <b style="color:#f8fbff">{t.get("eg", 1)}-{t.get("dg", 1)}</b></div>'
        ai_comment_html = ""
        durum_bg, durum_lbl = mac_durum_badge(m["zaman"])
        belirsiz_html = '<div class="mk-mini" style="color:#ff8b8b">⚠️ Maç sonucu tarafı net değil</div>' if t.get("belirsiz") and t.get("ana_label") in ["MS 1", "Beraberlik", "MS 2"] else ''
        _filtre_tipi = str(t.get("filtre_secim_tipi", "") or "").strip()
        _filtre_tahmini = bool(t.get("filtre_secim_oran_tahmini", False))
        if _filtre_tipi:
            _oran_notu = " · tahmini oran" if _filtre_tahmini else ""
            filtre_secim_html = (
                f'<div class="mk-mini" style="color:#7fb3ff;margin-top:4px">'
                f'↪ Minimum oran nedeniyle {_filtre_tipi.lower()} gösteriliyor{_oran_notu}</div>'
            )
        else:
            filtre_secim_html = ''
        combo_html = ''
        skor_html = f'<div style="margin-top:8px;font-size:0.76rem;color:#cbd5e1">🎯 Tahmini skor: <b style="color:#f8fbff">{t.get("eg", 1)}-{t.get("dg", 1)}</b></div>'
        if combo_text:
            combo_level = t.get("combo_level", "")
            level_text = f' · {combo_level}' if combo_level else ''
            combo_html = f'<div style="margin-top:8px"><div class="mk-label">GÜÇLÜ KOMBO{level_text}</div><span class="combo-pill">{combo_text}</span></div>'
        _hassasiyet_yazi = str(t.get("stability_text", "") or "").strip()
        _stabilite_tarama_acik = bool(st.session_state.get("mac_analizi_stabilite_tarama", False))
        if _hassasiyet_yazi:
            stability_html = (
                f'<div style="margin-top:5px;font-size:0.70rem;color:#7fb3ff">'
                f'🎯 Hassasiyetler: <b>{escape(_hassasiyet_yazi)}</b>'
                f' <span style="color:#94a3b8">({int(t.get("stability_count", 0) or 0)}/11)</span></div>'
            )
        elif _stabilite_tarama_acik:
            stability_html = '<div style="margin-top:5px;font-size:0.70rem;color:#64748b">🎯 Hassasiyetler: —</div>'
        else:
            stability_html = '<div style="margin-top:5px;font-size:0.70rem;color:#64748b">🎯 11 hassasiyet taraması: kapalı</div>'

        alt_html = f'<span class="alt-pill">{t["alt_label"]}</span>' if t.get("alt_label") else '<span style="font-size:0.78rem;color:#6f7990">—</span>'
        value_html = ''
        kc, bc = st.columns([9, 1.4])
        with kc:
            card_html = f"""
            <div class="mac-kart">
              <div class="mk-zaman">
                <span class="mk-star">☆</span>
                <div style="margin-bottom:6px"><span class="live-badge" style="background:{durum_bg};color:white">{durum_lbl}</span></div>
                <div class="mk-saat">{m['zaman'].strftime('%H:%M')}</div>
                <div class="mk-lig">{m['lig'][:14]}</div>
              </div>

              <div class="mk-takimlar">
                <div class="mk-ev">⬜ {m['ev']}</div>
                <div class="mk-dep">🟦 {m['dep']}</div>
                <div class="mk-mini">Maç tipi: {t['match_type']} · Gol profili: {t['goal_profile']}</div>
                {belirsiz_html}
                {ai_comment_html}
              </div>

              <div>
                <div class="mk-label">ANA TAHMİN</div>
                <span class="ana-pill {pill_cls}">{t['ana_label']}</span>
                {filtre_secim_html}
                {skor_html}
                <div style="margin-top:10px">
                  <div class="mk-label">GÜVEN</div>
                  <div class="guven-pct">{int(t['ana_p'])}%</div>
                  <div class="guven-bar"><div class="guven-fill" style="width:{int(t['ana_p'])}%;background:{gc}"></div></div>
                </div>
              </div>

              <div>
                <div class="mk-label">ALTERNATİF</div>
                {alt_html}
                {combo_html}
              </div>

              <div>
                <div class="mk-label">ORANLAR</div>
                <div class="oran-row">
                  <div class="oran-box"><div class="ov">1</div><div class="val">{m['h']:.2f}</div></div>
                  <div style="color:#2a2a2a">/</div>
                  <div class="oran-box"><div class="ov">X</div><div class="val">{m['b']:.2f}</div></div>
                  <div style="color:#2a2a2a">/</div>
                  <div class="oran-box"><div class="ov">2</div><div class="val">{m['a']:.2f}</div></div>
                </div>
                <div style="margin-top:8px;font-size:0.72rem;color:#666">🏅 {t.get('playable_score', t['ana_p'])} puan · 📊 {int(t['ornek'])} örnek · 🏟️ Aynı lig: {int(t.get('ayni_lig_ornek', 0) or 0)}/{int(t['ornek'])} · {t.get('ornek_durum', 'Standart')}</div>
                <div style="margin-top:6px;font-size:0.72rem;color:#f6b26b">🏅 {t.get('score', 0):.1f} puan</div>
                {stability_html}
              </div>
            </div>
            """
            # Streamlit'in Markdown ayrıştırıcısı boş satırdan sonra raw HTML bloğunu
            # kapatabildiği için kartı tek bir kesintisiz HTML satırı olarak gönder.
            _card_html_render = "".join(
                line.strip() for line in textwrap.dedent(card_html).splitlines() if line.strip()
            )
            st.markdown(_card_html_render, unsafe_allow_html=True)
        with bc:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            if st.button("Detay →", key=f"d_{real_i}_{i}", use_container_width=True):
                st.session_state.detay_idx = real_i
                st.session_state.detay_item = None
                st.rerun()
            with st.popover("+ Kupona", use_container_width=True):
                st.caption("Kupona eklenecek tercihi seç")
                if st.button(
                    f"Ana tercih · {t.get('ana_label', '-')}",
                    key=f"k_ana_{real_i}_{i}",
                    use_container_width=True,
                ):
                    manuel_kupona_ekle(
                        m, t, t.get("ana_label", "-"), t.get("ana_p", 0),
                        oran=t.get("ana_odd"), oran_tahmini=False,
                    )
                    st.rerun()
                combo_uygun = bool(t.get("combo_var") and t.get("combo_label"))
                combo_label = str(t.get("combo_label", "Kombo bulunamadı"))
                if st.button(
                    f"Kombo · {combo_label}",
                    key=f"k_kombo_{real_i}_{i}",
                    use_container_width=True,
                    disabled=not combo_uygun,
                ):
                    combo_oran = kombo_tahmini_oran(combo_label, t.get("ana_odd"))
                    manuel_kupona_ekle(
                        m, t, combo_label, t.get("combo_p", 0),
                        oran=combo_oran, oran_tahmini=True,
                    )
                    st.rerun()

    kupon_mesaji = None
    def _secim_hassasiyetleri(secim):
        """Eski/yeni kupon kayıtlarında hassasiyet listesini mümkün olan tüm alanlardan geri kazanır."""
        for key in ("hassasiyetler", "top10_hassasiyetler", "stability_tols", "ana_hassasiyetler"):
            vals = secim.get(key) if isinstance(secim, dict) else None
            if vals:
                out = []
                for x in vals:
                    try:
                        out.append(round(float(x), 2))
                    except Exception:
                        pass
                if out:
                    return sorted(set(out))
        return []

    with st.expander("🎫 Günün Kuponunu Oluştur", expanded=False):
        bilgi_col, gunun_col, olustur_col = st.columns([3.2, 1.15, 1.15], gap="small")
        with bilgi_col:
            st.caption(
                "Her maç 0.00 ile 0.10 arasında 0.01'er hassasiyet adımıyla toplam 11 noktada taranır. "
                "Günün Kuponu güven + kararlılık + örnek kalitesini birlikte değerlendirir; ayrıca son 5 takım formu, iç/dış saha formu, H2H ve mevcutsa gerçek 2.5 Alt/Üst piyasa oranından küçük artı/eksi puan uygular. 2-6 maç seçebilir ve sırf kuponu doldurmak için zayıf seçim eklemez. Aynı maçtan yalnızca bir seçim alır. "
                "Temkinli, Dengeli ve Yüksek Oran profilleri ise kendi kurallarıyla ayrı kuponlar üretir."
            )
        with gunun_col:
            gunun_tek_kupon_btn = st.button(
                "⭐ Günün kuponu", key="gunun_en_guvenli_tek_kupon_buton",
                use_container_width=True,
                help="Kalite eşiğini geçen en güvenilir seçimlerden tek kupon oluşturur. 2-6 maç olabilir; sırf doldurmak için seçim eklemez.",
            )
        with olustur_col:
            gunun_kupon_btn = st.button(
                "Kuponları oluştur", key="gunun_kuponu_tek_buton",
                use_container_width=True, type="primary",
            )

        liste_col1, liste_col2, liste_col3 = st.columns([2.05, 1.15, 1.15], gap="small")
        with liste_col2:
            tum_adaylari_goster_btn = st.button(
                "Tüm aday listeleri", key="tum_profil_adaylari_btn",
                use_container_width=True,
                help="Temkinli, Dengeli ve Yüksek Oran için uygun olan tüm seçimleri ayrı listelerde gösterir.",
            )
        with liste_col3:
            adaylari_temizle_btn = st.button(
                "Aday listelerini temizle", key="tum_profil_adaylari_temizle_btn",
                use_container_width=True,
                disabled=not isinstance(st.session_state.get("tum_profil_aday_listeleri"), dict),
                help="Ekrandaki Temkinli, Dengeli ve Yüksek Oran aday listelerini kapatır/temizler.",
            )

        if adaylari_temizle_btn:
            st.session_state.pop("tum_profil_aday_listeleri", None)
            st.rerun()

        if tum_adaylari_goster_btn:
            profil_aday_listeleri = {}
            for profil_adi in ["Temkinli", "Dengeli", "Yüksek Oran"]:
                kupon_kaynagi = gunun_en_iyi_10_uret(
                    st.session_state.get("last_gecmis_df"),
                    st.session_state.get("last_bulten_df"),
                    min_ornek=min_ornek,
                    limit=500,
                    sadece_ayni_lig=sadece_ayni_lig,
                    kupon_modu=True,
                    kupon_profili=profil_adi,
                    tum_marketler=True,
                )
                kullanilan = set()
                tum_secimler = []
                while True:
                    parca = gunun_kuponunu_olustur(
                        kupon_kaynagi, profil_adi, haric_secimler=kullanilan,
                        aday_listesi_modu=True,
                    )
                    if not parca:
                        break
                    yeni = False
                    for secim in parca:
                        key = (
                            f"{secim.get('ev','')}|{secim.get('dep','')}|{str(secim.get('zaman_iso',''))[:16]}",
                            secim.get("tahmin", ""),
                        )
                        if key in kullanilan:
                            continue
                        kullanilan.add(key)
                        tum_secimler.append(secim)
                        yeni = True
                    if not yeni:
                        break
                profil_aday_listeleri[profil_adi] = tum_secimler
            st.session_state["tum_profil_aday_listeleri"] = profil_aday_listeleri

        profil_aday_listeleri = st.session_state.get("tum_profil_aday_listeleri")
        if isinstance(profil_aday_listeleri, dict):
            st.markdown("#### 📋 Tüm profil adayları")
            st.caption(
                "Bunlar profil kriterlerini karşılayan tüm uygun marketlerdir. Aynı maçın birden fazla güçlü marketi burada görünebilir. "
                "Otomatik kupon oluştururken ise aynı maçtan yine yalnızca tek seçim alınır. Detay ile maç analizini açabilir, ＋ ile Kendi Kuponum'a ekleyebilirsin."
            )

            profil_renkleri_aday = {
                "Temkinli": ("#123d2d", "#36d98b", "🟢"),
                "Dengeli": ("#12345b", "#60a5fa", "🔵"),
                "Yüksek Oran": ("#4a2b12", "#f59e0b", "🟠"),
            }
            aday_cols = st.columns(3, gap="small")

            for aday_col, profil_adi in zip(aday_cols, ["Temkinli", "Dengeli", "Yüksek Oran"]):
                with aday_col:
                    arka, vurgu, ikon = profil_renkleri_aday[profil_adi]
                    secimler = profil_aday_listeleri.get(profil_adi, []) or []

                    st.markdown(
                        f"""
                        <div style="background:{arka};border:1px solid {vurgu};border-radius:12px;
                                    padding:10px 12px;margin-bottom:10px;text-align:center;
                                    color:#f8fafc;-webkit-text-fill-color:#f8fafc;font-size:1rem;
                                    font-weight:900;opacity:1">
                            {ikon} {escape(profil_adi)} · {len(secimler)} aday
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if not secimler:
                        st.info("Uygun aday yok.")
                        continue

                    for aday_i, secim in enumerate(secimler):
                        destekler = _secim_hassasiyetleri(secim)
                        try:
                            destek_yazi = ", ".join(f"{float(x):.2f}" for x in destekler)
                        except Exception:
                            destek_yazi = ", ".join(str(x) for x in destekler)

                        hassasiyet_alt = ""
                        if destekler:
                            try:
                                secilen_tol = float(secim.get("hassasiyet", 0) or 0)
                                hassasiyet_alt = (
                                    f'<div style="font-size:.70rem;color:#a7f3d0;margin-top:3px">'
                                    f'Seçilen: {secilen_tol:.2f} · Kararlı: '
                                    f'{escape(destek_yazi)} ({len(destekler)}/11)</div>'
                                )
                            except Exception:
                                pass

                        oran_yazi = ""
                        if secim.get("oran") is not None:
                            try:
                                oran_yazi = f" · Oran {float(secim.get('oran')):.2f}"
                            except Exception:
                                pass

                        # Streamlit container key CSS sınıfına dönüştürülürken Türkçe
                        # karakterler (özellikle "Yüksek Oran") seçiciyi bozabiliyor.
                        # CSS için yalnızca ASCII profil anahtarı kullan.
                        profil_css_key = {
                            "Temkinli": "temkinli",
                            "Dengeli": "dengeli",
                            "Yüksek Oran": "yuksek_oran",
                        }.get(profil_adi, "profil")
                        aday_key = (
                            f"profil_aday_kart_{profil_css_key}_"
                            f"{aday_i}_{abs(hash(str(secim.get('zaman_iso',''))))}"
                        )
                        st.markdown(
                            f"""
                            <style>
                            .st-key-{aday_key} {{
                                background: {arka};
                                border: 1px solid rgba(255,255,255,.16);
                                border-radius: 12px;
                                padding: 10px 12px 9px 14px;
                                margin: 0 0 12px 0;
                            }}
                            .st-key-{aday_key} [data-testid="stHorizontalBlock"] {{
                                align-items: center;
                            }}
                            .st-key-{aday_key} .stButton > button {{
                                min-height: 42px;
                                margin: 0;
                            }}
                            </style>
                            """,
                            unsafe_allow_html=True,
                        )

                        with st.container(key=aday_key, border=False):
                            bilgi_col, detay_col, ekle_col = st.columns([6.4, 2.3, 1.3], gap="small")

                            with bilgi_col:
                                st.markdown(
                                    f"""
                                    <div style="color:#f8fafc;padding:2px 0">
                                      <b style="font-size:.94rem">
                                        {escape(str(secim.get('ev','')))} – {escape(str(secim.get('dep','')))}
                                      </b>
                                      <div style="font-size:.80rem;color:#dbeafe;margin-top:5px">
                                        {escape(str(secim.get('tahmin','-')))} · Güven %{int(secim.get('guven',0) or 0)}{escape(oran_yazi)}
                                      </div>
                                      {hassasiyet_alt}
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

                            with detay_col:
                                if st.button(
                                    "Detay",
                                    key=f"profil_aday_detay_{profil_adi}_{aday_i}_{abs(hash(str(secim.get('zaman_iso',''))))}",
                                    use_container_width=True,
                                ):
                                    detay_item = kupon_seciminden_detay_itemi(
                                        secim, sadece_ayni_lig=sadece_ayni_lig
                                    )
                                    if detay_item is None:
                                        st.warning("Bu aday için detay verisi yeniden oluşturulamadı.")
                                    else:
                                        st.session_state.detay_item = detay_item
                                        st.session_state.detay_idx = None
                                        st.rerun()

                            with ekle_col:
                                if st.button(
                                    "＋",
                                    key=f"profil_aday_ekle_{profil_adi}_{aday_i}_{abs(hash(str(secim.get('zaman_iso',''))))}",
                                    use_container_width=True,
                                    help="Kendi Kuponuma ekle",
                                ):
                                    coupon_item = dict(secim)
                                    coupon_item["profil"] = "Kendi Kuponum"
                                    coupon_item["otomatik"] = False
                                    mevcutlar = {
                                        (x.get("ev", ""), x.get("dep", ""), x.get("tahmin", ""))
                                        for x in st.session_state.kupona if isinstance(x, dict)
                                    }
                                    imza = (
                                        coupon_item.get("ev", ""),
                                        coupon_item.get("dep", ""),
                                        coupon_item.get("tahmin", ""),
                                    )
                                    if imza not in mevcutlar:
                                        st.session_state.kupona.append(coupon_item)
                                        st.session_state.coupon_popup_open = True
                                        st.session_state.scroll_to_coupon = True
                                        st.rerun()
                                    else:
                                        st.toast("Bu seçim zaten Kendi Kuponum'da.")

        if gunun_tek_kupon_btn:
            gunun_kaynagi = gunun_en_iyi_10_uret(
                st.session_state.get("last_gecmis_df"),
                st.session_state.get("last_bulten_df"),
                min_ornek=min_ornek,
                limit=500,
                sadece_ayni_lig=sadece_ayni_lig,
                kupon_modu=True,
                kupon_profili="Günün Kuponu",
                tum_marketler=True,
            )
            gunun_secimleri = gunun_en_guvenli_kuponunu_olustur(
                gunun_kaynagi, maks=6, min_guven=72,
                gecmis_df=st.session_state.get("last_gecmis_df")
            )
            # Günün Kuponu'nun kendi sıkı kalite filtresi boş kalırsa, ekranda
            # aday üretebilen Temkinli / Dengeli / Yüksek Oran havuzlarını kullan.
            # Böylece profil adayları bulunduğu halde Günün Kuponu boş kalmaz.
            profil_aday_fallback = False
            if not gunun_secimleri:
                gunun_secimleri = gunun_kuponunu_profil_adaylarindan_olustur(
                    st.session_state.get("last_gecmis_df"),
                    st.session_state.get("last_bulten_df"),
                    min_ornek=min_ornek,
                    sadece_ayni_lig=sadece_ayni_lig,
                    maks=6,
                )
                profil_aday_fallback = bool(gunun_secimleri)

            if gunun_secimleri:
                # Adayları tek kupona 6 maç doldurmak yerine kalite kırılımında böl.
                # Ardışık kalite puanı 4+ düştüğünde yeni Günün Kuponu başlar.
                gunun_kuponlari = gunun_kuponlarini_kaliteye_gore_bol(
                    gunun_secimleri, maks_kupon_mac=6, min_anlamli_dusus=4.0
                )
                # Son güvenlik ağı: profil adayları gerçekten üretildiyse bölme
                # mantığı Günün Kuponu'nu tamamen boş bırakamaz.
                if not gunun_kuponlari and gunun_secimleri:
                    gunun_kuponlari = [[dict(gunun_secimleri[0])]]

                for kupon_no, kupon_secimleri in enumerate(gunun_kuponlari, start=1):
                    # Görünüm yalnızca tam "Günün Kuponu" profilini listeliyor.
                    # Birden fazla kupon üretildiğinde "Günün Kuponu 1/2" gibi
                    # farklı profil adları kullanmak kayıtların ekranda görünmemesine yol açıyordu.
                    # Her grup ayrı kayıt olarak tutulur, fakat aynı profil altında gösterilir.
                    kupon_gecmisine_ekle(kupon_secimleri, "Günün Kuponu", "0.00–0.10 tarama")
                st.session_state.coupon_popup_open = True
                st.session_state.scroll_to_coupon = True
                dagilim = " + ".join(str(len(k)) for k in gunun_kuponlari)
                if profil_aday_fallback:
                    kupon_mesaji = (
                        "success",
                        f"⭐ Günün Kuponu oluşturuldu: profil adayları kalite düştüğü noktalarda {len(gunun_kuponlari)} kupona bölündü ({dagilim} maç)."
                    )
                else:
                    kupon_mesaji = (
                        "success",
                        f"⭐ Günün Kuponu oluşturuldu: seçimler kalite düştüğü noktalarda {len(gunun_kuponlari)} kupona bölündü ({dagilim} maç)."
                    )
            else:
                kupon_mesaji = (
                    "warning",
                    "Günün Kuponu oluşturulamadı; Temkinli, Dengeli ve Yüksek Oran aday havuzlarında da uygun seçim yok."
                )

        if gunun_kupon_btn:
            olusan_profiller = []
            bulunamayan_profiller = []
            for profil_adi in ["Temkinli", "Dengeli", "Yüksek Oran"]:
                kupon_kaynagi = gunun_en_iyi_10_uret(
                    st.session_state.get("last_gecmis_df"),
                    st.session_state.get("last_bulten_df"),
                    min_ornek=min_ornek,
                    limit=50,
                    sadece_ayni_lig=sadece_ayni_lig,
                    kupon_modu=True,
                    kupon_profili=profil_adi,
                )

                # Her profil kendi aday havuzunu bağımsız kullanır. Böylece örneğin
                # Temkinli'deki güçlü bir kombinasyon Dengeli/Yüksek Oran'da da
                # kriterleri karşılıyorsa tekrar seçilebilir.
                profil_kullanilan = set()
                profil_kupon_sayisi = 0
                profil_toplam_secim = 0

                while True:
                    otomatik_secimler = gunun_kuponunu_olustur(
                        kupon_kaynagi,
                        profil_adi,
                        haric_secimler=profil_kullanilan,
                    )
                    if not otomatik_secimler:
                        break

                    kupon_gecmisine_ekle(otomatik_secimler, profil_adi, "0.00–0.10 tarama")
                    profil_kupon_sayisi += 1
                    profil_toplam_secim += len(otomatik_secimler)

                    yeni_secim_eklendi = False
                    for secim in otomatik_secimler:
                        secim_key = (
                            f"{secim.get('ev', '')}|{secim.get('dep', '')}|"
                            f"{str(secim.get('zaman_iso', ''))[:16]}",
                            secim.get("tahmin", ""),
                        )
                        if secim_key not in profil_kullanilan:
                            yeni_secim_eklendi = True
                        profil_kullanilan.add(secim_key)

                    # Güvenlik: anahtar eşleşmesinde beklenmeyen bir durum olursa
                    # sonsuz döngüye girme.
                    if not yeni_secim_eklendi:
                        break

                if profil_kupon_sayisi:
                    olusan_profiller.append(
                        f"{profil_adi} x{profil_kupon_sayisi} ({profil_toplam_secim} seçim)"
                    )
                else:
                    bulunamayan_profiller.append(profil_adi)
            if olusan_profiller:
                st.session_state.coupon_popup_open = True
                st.session_state.scroll_to_coupon = True
                ek_mesaj = (
                    f" Uygun seçim bulunamayan: {', '.join(bulunamayan_profiller)}."
                    if bulunamayan_profiller else ""
                )
                kupon_mesaji = (
                    "success",
                    f"{', '.join(olusan_profiller)} kaydedildi. Hassasiyet taraması: 0.00–0.10.{ek_mesaj}",
                )
            else:
                kupon_mesaji = ("warning", "Profiller için uygun seçim bulunamadı; kupon oluşturulmadı.")

    if kupon_mesaji:
        getattr(st, kupon_mesaji[0])(kupon_mesaji[1])

    # Kuponlarım: dialog/modal yerine normal, engellemeyen panel.
    if st.session_state.get("coupon_popup_open"):
        st.markdown('<div id="kuponlarim-anchor"></div>', unsafe_allow_html=True)
        if st.session_state.get("scroll_to_coupon"):
            components.html(
                """
                <script>
                setTimeout(function () {
                    if (window.frameElement) {
                        window.frameElement.scrollIntoView({behavior:'smooth', block:'start'});
                    }
                }, 350);
                </script>
                """,
                height=1,
            )
            st.session_state.scroll_to_coupon = False
        normalized_kupona = []
        for k in st.session_state.kupona:
            if isinstance(k, dict):
                normalized_kupona.append(k)
            else:
                raw_text = str(k)
                item = {"ev": raw_text, "dep": "", "lig": "-", "zaman_iso": "", "zaman_text": "-", "tahmin": "-", "guven": 0}
                if " — " in raw_text:
                    match_text, tahmin_text = raw_text.split(" — ", 1)
                    item["tahmin"] = tahmin_text.strip()
                    if " vs " in match_text:
                        ev, dep = match_text.split(" vs ", 1)
                        item["ev"] = ev.strip()
                        item["dep"] = dep.strip()
                    else:
                        item["ev"] = match_text.strip()
                normalized_kupona.append(item)
        st.session_state.kupona = normalized_kupona

        st.markdown(
            """
            <div class="coupon-panel-dark">
              <h3>🎫 Kuponlarım</h3>
              <div class="coupon-sub">Eklediğin maçlar aşağıda listelenir.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        kupon_gecmisi = kupon_gecmisini_oku()

        # Yalnızca otomatik oluşturulan kupon geçmişini tek seferde temizler.
        # Kullanıcının "Kendi Kuponum" seçimlerine dokunmaz.
        if kupon_gecmisi:
            temizle_bos, temizle_col = st.columns([7.8, 2.2], gap="small")
            with temizle_col:
                if st.button(
                    "🗑️ Tüm otomatik kuponları temizle",
                    key="auto_coupon_clear_all",
                    use_container_width=True,
                    help="Günün Kuponu, Temkinli, Dengeli ve Yüksek Oran altında oluşturulan tüm otomatik kupon kayıtlarını siler. Kendi Kuponum etkilenmez.",
                ):
                    kupon_gecmisini_yaz([])
                    st.rerun()

        if kupon_gecmisi or st.session_state.kupona:
            st.markdown(
                """
                <div style="color:#f8fafc;-webkit-text-fill-color:#f8fafc;font-size:1.18rem;
                            font-weight:900;margin:10px 0 12px;opacity:1">
                    📚 Otomatik kupon geçmişi
                </div>
                """,
                unsafe_allow_html=True,
            )
            profil_renkleri = {
                "Günün Kuponu": ("#0b3b46", "#22d3ee", "⭐"),
                "Temkinli": ("#123d2d", "#36d98b", "🟢"),
                "Dengeli": ("#12345b", "#60a5fa", "🔵"),
                "Yüksek Oran": ("#4a2b12", "#f59e0b", "🟠"),
            }
            def _otomatik_secim_kalite(secim):
                """Kupon görünümünde seçimleri ortak kalite ölçüsünde sıralar."""
                if not isinstance(secim, dict):
                    return 0.0
                if secim.get("gunun_puani") is not None:
                    try:
                        return float(secim.get("gunun_puani"))
                    except Exception:
                        pass
                guven = float(secim.get("guven", 0) or 0)
                stabil = int(secim.get("hassasiyet_sayisi", 0) or 0)
                if stabil <= 0:
                    stabil = len(_secim_hassasiyetleri(secim))
                return guven + stabil * 1.8

            def _otomatik_kupon_kalite_anahtari(kayit):
                """Maç sayısından bağımsız olarak kuponun ortalama kalitesini ölçer."""
                secimler = [x for x in kayit.get("secimler", []) if isinstance(x, dict)] if isinstance(kayit, dict) else []
                if not secimler:
                    return (0.0, 0.0, 0.0)
                kaliteler = [_otomatik_secim_kalite(x) for x in secimler]
                guvenler = [float(x.get("guven", 0) or 0) for x in secimler]
                stabiliteler = []
                for x in secimler:
                    stabil = int(x.get("hassasiyet_sayisi", 0) or 0)
                    if stabil <= 0:
                        stabil = len(_secim_hassasiyetleri(x))
                    stabiliteler.append(stabil)
                return (
                    sum(kaliteler) / len(kaliteler),
                    sum(guvenler) / len(guvenler),
                    sum(stabiliteler) / len(stabiliteler),
                )

            profil_sutunlari = st.columns(5, gap="small")
            for profil_col, profil_adi in zip(
                profil_sutunlari[:4],
                ["Günün Kuponu", "Temkinli", "Dengeli", "Yüksek Oran"],
            ):
                with profil_col:
                    arka, vurgu, ikon = profil_renkleri[profil_adi]
                    st.markdown(
                        f"""
                        <div style="background:{arka};border:1px solid {vurgu};border-radius:12px;
                                    padding:10px 12px;margin-bottom:10px;text-align:center;
                                    color:#f8fafc;-webkit-text-fill-color:#f8fafc;font-size:1rem;
                                    font-weight:900;opacity:1">
                            {ikon} {escape(profil_adi)}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    profil_kayitlari = [x for x in kupon_gecmisi if x.get("profil") == profil_adi]
                    # Günün Kuponu dahil tüm otomatik profillerde en güçlü kupon üstte.
                    # Maç sayısı avantaj sağlamasın diye toplam değil ortalama kalite kullanılır.
                    profil_kayitlari.sort(key=_otomatik_kupon_kalite_anahtari, reverse=True)
                    if not profil_kayitlari:
                        st.info(f"Henüz {profil_adi} kupon kaydı yok.")
                        continue
                    for kayit in profil_kayitlari:
                        try:
                            zaman_yazi = datetime.fromisoformat(kayit.get("olusturma_zamani", "")).strftime("%d.%m.%Y %H:%M")
                        except Exception:
                            zaman_yazi = kayit.get("olusturma_zamani", "-")
                        kayit_hassasiyet = kayit.get("hassasiyet", "-")
                        if isinstance(kayit_hassasiyet, (int, float)):
                            kayit_hassasiyet_yazi = f"{float(kayit_hassasiyet):.2f}"
                        else:
                            kayit_hassasiyet_yazi = str(kayit_hassasiyet)
                        # Kupon başlığı ayrı; her maç kendi satırında Detay ve + ile gösterilir.
                        st.markdown(
                            f"""
                            <div style="background:{arka};border:1px solid {vurgu};border-radius:13px 13px 8px 8px;
                                        padding:10px 12px;margin-bottom:6px;color:#f8fafc">
                              <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
                                <b style="color:{vurgu};font-size:1rem">{ikon} {escape(profil_adi)}</b>
                                <span style="font-size:.76rem;color:#dbeafe">{escape(zaman_yazi)}</span>
                              </div>
                              <div style="font-size:.78rem;color:#e2e8f0;margin-top:4px">
                                Hassasiyet: <b>{escape(kayit_hassasiyet_yazi)}</b> · {len(kayit.get('secimler', []))} maç
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        # Kuponun içindeki maçlar da en güçlü seçimden daha zayıfa doğru gösterilir.
                        gorunen_secimler = sorted(
                            [x for x in kayit.get("secimler", []) if isinstance(x, dict)],
                            key=lambda x: (
                                _otomatik_secim_kalite(x),
                                float(x.get("guven", 0) or 0),
                                len(_secim_hassasiyetleri(x)),
                            ),
                            reverse=True,
                        )
                        for secim_no, secim in enumerate(gorunen_secimler):
                            destekler = _secim_hassasiyetleri(secim)
                            destek_yazi = ", ".join(f"{float(x):.2f}" for x in destekler)
                            hassasiyet_alt = (
                                f'<div style="font-size:.70rem;color:#a7f3d0;margin-top:3px">'
                                f'Seçilen: {float(secim.get("hassasiyet", 0)):.2f} · Kararlı: '
                                f'{escape(destek_yazi)} ({len(destekler)}/11)</div>'
                                if destekler else ""
                            )
                            baglam_val = float(secim.get("baglam_ayari", 0.0) or 0.0)
                            baglam_alt = (
                                f'<div style="font-size:.70rem;color:{"#86efac" if baglam_val > 0 else "#fca5a5" if baglam_val < 0 else "#cbd5e1"};margin-top:3px">'
                                f'Bağlam ayarı: <b>{baglam_val:+.1f}</b> puan</div>'
                                if secim.get("profil") == "Günün Kuponu" or "baglam_ayari" in secim else ""
                            )
                            # Maç bilgileri ve aksiyonlar aynı görsel kartın içinde.
                            kart_key = f"auto_coupon_match_{abs(hash(str(kayit.get('kupon_id'))))}_{secim_no}"
                            st.markdown(
                                f"""
                                <style>
                                .st-key-{kart_key} {{
                                    background: {arka};
                                    border: 1px solid rgba(255,255,255,.16);
                                    border-radius: 12px;
                                    padding: 10px 12px 9px 14px;
                                    margin: 0 0 12px 0;
                                }}
                                .st-key-{kart_key} [data-testid="stHorizontalBlock"] {{
                                    align-items: center;
                                }}
                                .st-key-{kart_key} .stButton > button {{
                                    min-height: 42px;
                                    margin: 0;
                                }}
                                </style>
                                """,
                                unsafe_allow_html=True,
                            )

                            with st.container(key=kart_key, border=False):
                                bilgi_col, detay_col, ekle_col = st.columns([6.4, 2.3, 1.3], gap="small")

                                with bilgi_col:
                                    st.markdown(
                                        f"""
                                        <div style="color:#f8fafc;padding:2px 0">
                                          <b style="font-size:.94rem">
                                            {escape(str(secim.get('ev', '')))} – {escape(str(secim.get('dep', '')))}
                                          </b>
                                          <div style="font-size:.80rem;color:#dbeafe;margin-top:5px">
                                            {escape(str(secim.get('tahmin', '-')))} · Güven %{int(secim.get('guven', 0))}
                                          </div>
                                          {hassasiyet_alt}
                                          {baglam_alt}
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )

                                with detay_col:
                                    if st.button(
                                        "Detay",
                                        key=f"auto_coupon_detail_{kayit.get('kupon_id')}_{secim_no}",
                                        use_container_width=True,
                                    ):
                                        detay_item = kupon_seciminden_detay_itemi(
                                            secim, sadece_ayni_lig=sadece_ayni_lig
                                        )
                                        if detay_item is None:
                                            st.warning("Bu kupon kaydı için detay verisi yeniden oluşturulamadı.")
                                        else:
                                            st.session_state.detay_item = detay_item
                                            st.session_state.detay_idx = None
                                            st.rerun()

                                with ekle_col:
                                    if st.button(
                                        "＋",
                                        key=f"auto_to_manual_{kayit.get('kupon_id')}_{secim_no}",
                                        use_container_width=True,
                                        help="Kendi Kuponuma ekle",
                                    ):
                                        secim_m = {
                                            "ev": secim.get("ev", ""),
                                            "dep": secim.get("dep", ""),
                                            "lig": secim.get("lig", ""),
                                            "sport_key": secim.get("sport_key", ""),
                                            "h": secim.get("h"),
                                            "b": secim.get("b"),
                                            "a": secim.get("a"),
                                            "zaman": parse_mac_datetime(secim.get("zaman_iso", "")),
                                        }
                                        manuel_kupona_ekle(
                                            secim_m, {}, secim.get("tahmin", "-"), secim.get("guven", 0),
                                            oran=secim.get("oran"),
                                            oran_tahmini=bool(secim.get("oran_tahmini", False)),
                                        )
                                        st.rerun()

                        kart_col, sil_col = st.columns([8, 2])
                        with kart_col:
                            st.markdown("<div style='height:1px'></div>", unsafe_allow_html=True)
                        with sil_col:
                            if st.button("🗑️", key=f"auto_coupon_delete_{kayit.get('kupon_id')}", use_container_width=True):
                                yeni_gecmis = [x for x in kupon_gecmisi if x.get("kupon_id") != kayit.get("kupon_id")]
                                kupon_gecmisini_yaz(yeni_gecmis)
                                st.rerun()

            with profil_sutunlari[4]:
                st.markdown(
                    """
                    <div style="background:#312e81;border:1px solid #a78bfa;border-radius:12px;
                                padding:10px 12px;margin-bottom:10px;text-align:center;
                                color:#f8fafc;-webkit-text-fill-color:#f8fafc;font-size:1rem;
                                font-weight:900;opacity:1">
                        🟣 Kendi Kuponum
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if not st.session_state.kupona:
                    st.info("Henüz manuel seçim eklenmedi.")
                for del_i, item in enumerate(list(st.session_state.kupona)):
                    mac_dt = parse_mac_datetime(item.get("zaman_iso", ""))
                    durum = mac_canli_durumu(mac_dt) if item.get("zaman_iso") else "Takipte"
                    mac_ad = f"{item.get('ev', '')} – {item.get('dep', '')}".strip(" –")
                    kart_col, sil_col = st.columns([8, 2])
                    with kart_col:
                        st.markdown(
                            f"""
                            <div style="background:#1e1b4b;border:1px solid #7c3aed;border-radius:13px;
                                        padding:11px 12px;margin-bottom:8px;color:#f8fafc">
                              <b style="color:#c4b5fd">{escape(mac_ad)}</b>
                              <div style="font-size:.79rem;color:#e2e8f0;margin-top:5px">
                                {escape(str(item.get('tahmin','-')))} · Güven %{int(item.get('guven',0))}<br>
                                {escape(durum)}
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with sil_col:
                        if st.button("🗑️", key=f"coupon_delete_{del_i}", use_container_width=True):
                            st.session_state.kupona.pop(del_i)
                            st.rerun()
                if st.session_state.kupona and st.button(
                    "Kendi kuponumu temizle", key="coupon_clear_inside_panel", use_container_width=True
                ):
                    st.session_state.kupona = []
                    st.rerun()

        if not st.session_state.kupona and not kupon_gecmisi:
            st.info("Henüz kupon kaydı yok. Maç kartlarından seçim ekleyebilir veya Günün Kuponunu Oluştur bölümünü kullanabilirsin.")

        if st.button("Kapat", key="coupon_close_inside_panel", use_container_width=True):
            st.session_state.coupon_popup_open = False
            st.rerun()

legal_footer()
