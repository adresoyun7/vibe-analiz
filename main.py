import math
import random
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st


# =========================================================
# VIBE PRO EXPERT - 3 KUPON AI SÜRÜMÜ
# =========================================================
# Amaç:
# 1) Ultra Güvenli: 1-2 maç, en düşük riskli marketler
# 2) Oynanabilir: 2-3 maç, güven + oran dengesi
# 3) Yüksek Oran: 3-5 maç, risk kontrollü yüksek oran
#
# AH0 ve +1 handikap YOKTUR.
# Kullanılan final marketler:
# 4.5 Alt, 3.5 Alt, 1X/X2, 1.5 Üst, Takım 0.5 Üst,
# MS Favori, KG Yok, KG Var, 2.5 Üst, Kombo
# =========================================================


# -----------------------------
# SAYFA AYARI
# -----------------------------
st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")

APP_SCHEMA_VERSION = 30
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION


# -----------------------------
# CSS
# -----------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif;background:#f6f8fc;color:#0f172a;}
.stApp {background:linear-gradient(180deg,#f8fbff 0%,#f3f6fb 100%);} 
.main .block-container {max-width:1500px;padding-top:1.2rem;}
section[data-testid="stSidebar"] {background:#eef3fb!important;border-right:1px solid #d6e0ef;}
section[data-testid="stSidebar"] * {color:#334155!important;}

.topbar {background:linear-gradient(90deg,#07111f 0%,#0a1830 100%);border:1px solid #223c63;border-radius:18px;padding:18px 22px;margin-bottom:16px;color:#f8fafc;}
.topbar h1 {font-family:'Rajdhani',sans-serif;font-size:2.2rem;margin:0;color:#fff;letter-spacing:.7px;}
.topbar .sub {color:#9db2d1;font-size:.92rem;margin-top:5px;}

.metric-card {background:linear-gradient(135deg,#0f172a,#111827);border:1px solid #1f2a44;border-radius:16px;padding:16px 18px;color:#fff;}
.metric-label {font-size:.72rem;color:#9db2d1;text-transform:uppercase;letter-spacing:1.4px;}
.metric-value {font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:700;color:#fff;line-height:1;}
.metric-sub {font-size:.78rem;color:#cbd5e1;margin-top:6px;}

.coupon-card {background:linear-gradient(135deg,#0f172a,#111827);border:1px solid #1f2a44;border-radius:18px;padding:16px 18px;min-height:430px;color:#f8fafc;box-shadow:0 10px 30px rgba(0,0,0,.18);} 
.coupon-title {font-family:'Rajdhani',sans-serif;font-size:1.42rem;font-weight:800;color:#fff;margin-bottom:3px;}
.coupon-sub {font-size:.78rem;color:#9db2d1;margin-bottom:12px;}
.pick-box {background:#0b1628;border:1px solid #223c63;border-radius:14px;padding:11px 12px;margin-bottom:10px;}
.pick-top {display:flex;justify-content:space-between;gap:10px;align-items:flex-start;}
.pick-match {font-weight:800;color:#f8fafc;font-size:.88rem;}
.pick-market {display:inline-block;margin-top:7px;background:#facc15;color:#111827;border-radius:8px;padding:4px 9px;font-weight:900;font-size:.78rem;}
.pick-odd {font-family:'Rajdhani',sans-serif;font-size:1.28rem;font-weight:800;color:#fff;}
.pick-mini {font-size:.74rem;color:#9db2d1;margin-top:7px;line-height:1.42;}
.reason {font-size:.74rem;color:#e5e7eb;background:#0f1b31;border:1px solid #1f2a44;border-radius:10px;padding:8px 10px;margin-top:8px;line-height:1.4;}

.green-border {border-color:#1f8d53!important;}
.yellow-border {border-color:#d7a417!important;}
.red-border {border-color:#dc2626!important;}
.status-pill {display:inline-block;border-radius:999px;padding:4px 10px;font-size:.72rem;font-weight:900;}
.ok {background:#183925;color:#3ddb7c;}
.warn {background:#37290f;color:#facc15;}
.bad {background:#391212;color:#ff6b6b;}

.match-card {background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:15px 18px;margin-bottom:12px;color:#f8fafc;}
.match-title {font-weight:900;font-size:1.05rem;color:#fff;}
.match-sub {font-size:.76rem;color:#9db2d1;margin-top:4px;}
.market-row {display:grid;grid-template-columns:1.2fr .5fr .5fr .6fr .9fr;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid #1f2a44;font-size:.82rem;}
.market-row:last-child {border-bottom:none;}
.header-row {color:#9db2d1;text-transform:uppercase;font-size:.7rem;letter-spacing:1px;font-weight:800;}

.stButton>button {background:linear-gradient(180deg,#0d1a2f 0%,#0b1526 100%)!important;color:#f8fafc!important;border:1px solid #284977!important;border-radius:12px!important;font-weight:800!important;}
.stButton>button:hover {border-color:#facc15!important;}
div[data-baseweb="select"]>div, div[data-testid="stTextInput"] div[data-baseweb="input"]>div, div[data-testid="stNumberInput"] div[data-baseweb="input"]>div, div[data-testid="stDateInput"] div[data-baseweb="input"]>div {background:#0f1b31!important;border-color:#284977!important;color:#f8fafc!important;}
input, textarea {color:#f8fafc!important;}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# YARDIMCI FONKSİYONLAR
# -----------------------------

def safe_float(v, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def safe_int(v, default: int = 0) -> int:
    try:
        if pd.isna(v):
            return default
        return int(round(float(v)))
    except Exception:
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct(v: float) -> str:
    return f"%{int(round(clamp(v, 0, 1) * 100))}"


def pct_int(v: float) -> int:
    return int(round(clamp(v, 0, 1) * 100))


def fmt_odd(odd) -> str:
    try:
        return f"{float(odd):.2f}"
    except Exception:
        return "-"


def implied_prob(odd: Optional[float]) -> float:
    try:
        odd = float(odd)
        if odd <= 1:
            return 0.0
        return 1 / odd
    except Exception:
        return 0.0


def fair_odd(prob: float, margin: float = 0.06) -> float:
    prob = clamp(prob, 0.02, 0.98)
    return round(max(1.05, (1 / prob) * (1 - margin)), 2)


def parse_mac_datetime(value):
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return datetime.now()


def format_tr_date(d: date) -> str:
    aylar = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}
    gunler = {0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}
    return f"{d.day} {aylar[d.month]} {d.year} {gunler[d.weekday()]}"


def dinamik_min_mac(tolerans: float) -> int:
    if tolerans <= 0.02:
        return 1
    if tolerans <= 0.05:
        return 3
    if tolerans <= 0.08:
        return 5
    if tolerans <= 0.12:
        return 10
    return 20


def sample_factor_hesapla(sample: int, tolerans: float) -> float:
    hedef = 5 if tolerans <= 0.02 else 10 if tolerans <= 0.05 else 15 if tolerans <= 0.08 else 25 if tolerans <= 0.12 else 40
    return clamp(0.72 + 0.28 * (sample / max(hedef, 1)), 0.72, 1.0)


def mac_key(m: Dict) -> str:
    return f"{m.get('ev','')}::{m.get('dep','')}::{m.get('zaman','')}"


def mac_tipi(h: float, a: float) -> str:
    if abs(h - a) <= 0.50:
        return "Dengeli"
    if h < 2.0 or a < 2.0:
        return "Favori"
    return "Sürpriz Açık"


def gol_profili(avg_goal: float) -> str:
    if avg_goal < 2.20:
        return "Düşük Gollü"
    if avg_goal < 3.00:
        return "Dengeli"
    return "Yüksek Gollü"


def market_grubu(label: str) -> str:
    label = str(label)
    if label in ["4.5 Alt", "3.5 Alt"]:
        return "ultra_alt"
    if label in ["1X", "X2"]:
        return "cifte_sans"
    if label == "1.5 Üst":
        return "temel_gol"
    if "0.5 Üst" in label:
        return "takim_golu"
    if label in ["MS 1", "MS 2"]:
        return "ms_favori"
    if label == "KG Yok":
        return "kg_yok"
    if label == "KG Var":
        return "kg_var"
    if label == "2.5 Üst":
        return "ust25"
    if "+" in label or "Combo" in label:
        return "kombo"
    return "diger"


def market_sira(label: str) -> int:
    # En güvenliden riskliye doğru. AH0 ve +1 yok.
    siralar = {
        "4.5 Alt": 1,
        "3.5 Alt": 2,
        "1X": 3,
        "X2": 3,
        "1.5 Üst": 4,
        "Ev Sahibi 0.5 Üst": 5,
        "Deplasman 0.5 Üst": 5,
        "MS 1": 6,
        "MS 2": 6,
        "KG Yok": 7,
        "KG Var": 8,
        "2.5 Üst": 9,
    }
    return siralar.get(str(label), 10)


def risk_label(prob: float, label: str) -> str:
    g = market_grubu(label)
    p = pct_int(prob)
    if g in ["ultra_alt", "cifte_sans"] and p >= 75:
        return "DÜŞÜK"
    if p >= 78:
        return "DÜŞÜK"
    if p >= 66:
        return "ORTA"
    return "YÜKSEK"


def risk_ceza(label: str, prob: float) -> float:
    r = risk_label(prob, label)
    if r == "YÜKSEK":
        return 18
    if r == "ORTA":
        return 6
    return 0


def normalize_outcome_name(name: str) -> str:
    return str(name).lower().strip()


# -----------------------------
# VERİ ÇEKME
# -----------------------------

@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar: List[str]) -> pd.DataFrame:
    if not sezonlar:
        return pd.DataFrame()

    lig_map = [
        "T1",
        "E0", "E1", "E2",
        "SP1", "SP2",
        "D1", "D2",
        "I1", "I2",
        "F1", "F2",
        "N1", "B1", "P1", "SC0",
    ]

    liste = []
    for lig in lig_map:
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{lig}.csv"
                df = pd.read_csv(url)
                cols = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "FTR", "HTR", "B365H", "B365D", "B365A"]
                df = df[df.columns.intersection(cols)].copy()
                needed = ["FTHG", "FTAG", "B365H", "B365D", "B365A"]
                df = df.dropna(subset=[c for c in needed if c in df.columns])
                if "HTHG" not in df.columns:
                    df["HTHG"] = 0
                if "HTAG" not in df.columns:
                    df["HTAG"] = 0
                if "FTR" not in df.columns:
                    df["FTR"] = np.where(df["FTHG"] > df["FTAG"], "H", np.where(df["FTHG"] < df["FTAG"], "A", "D"))
                if "HTR" not in df.columns:
                    df["HTR"] = "D"
                df["LigKod"] = lig
                liste.append(df)
            except Exception:
                continue

    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()


def bulten_cek(api_key: str, kodlar: List[str], gun: date) -> pd.DataFrame:
    res = []
    if not api_key:
        return pd.DataFrame()

    for kod in kodlar:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{kod}/odds/",
                params={"apiKey": api_key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue

            for item in data:
                try:
                    tm = datetime.strptime(item["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except Exception:
                    continue
                if tm.date() != gun:
                    continue

                home = item.get("home_team", "")
                away = item.get("away_team", "")
                if not away:
                    teams = item.get("teams", [])
                    away = next((x for x in teams if x != home), "")
                if not home or not away:
                    continue

                h = d = a = None
                for bk in item.get("bookmakers", []):
                    for mk in bk.get("markets", []):
                        if mk.get("key") != "h2h":
                            continue
                        outcomes = mk.get("outcomes", [])
                        h = next((x.get("price") for x in outcomes if x.get("name") == home), None)
                        a = next((x.get("price") for x in outcomes if x.get("name") == away), None)
                        d = next((x.get("price") for x in outcomes if normalize_outcome_name(x.get("name")) in ["draw", "tie", "beraberlik"]), None)
                        if h and d and a:
                            break
                    if h and d and a:
                        break

                if h and d and a:
                    res.append({
                        "lig": item.get("sport_title", kod),
                        "zaman": tm,
                        "ev": home,
                        "dep": away,
                        "h": float(h),
                        "b": float(d),
                        "a": float(a),
                    })
        except Exception:
            continue

    if not res:
        return pd.DataFrame()
    return pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"]).sort_values("zaman").reset_index(drop=True)


def demo_bulten() -> pd.DataFrame:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    return pd.DataFrame([
        {"lig":"Premier League", "zaman":now + timedelta(hours=3), "ev":"Arsenal", "dep":"Everton", "h":1.42, "b":4.60, "a":7.20},
        {"lig":"La Liga", "zaman":now + timedelta(hours=4), "ev":"Real Valladolid", "dep":"Girona", "h":3.10, "b":3.25, "a":2.32},
        {"lig":"Süper Lig", "zaman":now + timedelta(hours=5), "ev":"Göztepe", "dep":"Kasımpaşa", "h":2.05, "b":3.35, "a":3.45},
        {"lig":"Eredivisie", "zaman":now + timedelta(hours=6), "ev":"PSV", "dep":"Sparta Rotterdam", "h":1.22, "b":6.30, "a":10.50},
        {"lig":"Serie A", "zaman":now + timedelta(hours=7), "ev":"Inter", "dep":"Udinese", "h":1.35, "b":4.90, "a":8.50},
        {"lig":"Bundesliga", "zaman":now + timedelta(hours=8), "ev":"Stuttgart", "dep":"Freiburg", "h":1.95, "b":3.60, "a":3.80},
    ])


def demo_history(n: int = 1200) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        h = round(random.uniform(1.18, 4.80), 2)
        a = round(random.uniform(1.45, 8.80), 2)
        b = round(random.uniform(2.85, 5.30), 2)
        strength = (1 / h) - (1 / a)
        total_lambda = random.uniform(2.25, 2.95)
        home_lambda = clamp(total_lambda / 2 + strength * 1.15, 0.45, 3.20)
        away_lambda = clamp(total_lambda / 2 - strength * 1.15, 0.35, 3.00)
        hg = np.random.poisson(home_lambda)
        ag = np.random.poisson(away_lambda)
        hthg = np.random.binomial(max(hg, 0), 0.42) if hg > 0 else 0
        htag = np.random.binomial(max(ag, 0), 0.42) if ag > 0 else 0
        ftr = "H" if hg > ag else "A" if ag > hg else "D"
        htr = "H" if hthg > htag else "A" if htag > hthg else "D"
        rows.append({"HomeTeam":"A", "AwayTeam":"B", "FTHG":hg, "FTAG":ag, "HTHG":hthg, "HTAG":htag, "FTR":ftr, "HTR":htr, "B365H":h, "B365D":b, "B365A":a})
    return pd.DataFrame(rows)


# -----------------------------
# ANALİZ MOTORU
# -----------------------------

def benzer_maclari_bul(b_df: pd.DataFrame, m_row: pd.Series, tolerans: float) -> pd.DataFrame:
    required = ["B365H", "B365D", "B365A", "FTHG", "FTAG"]
    if b_df is None or b_df.empty or not all(c in b_df.columns for c in required):
        return pd.DataFrame()

    df = b_df.copy()
    for c in ["B365H", "B365D", "B365A", "FTHG", "FTAG", "HTHG", "HTAG"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    b = df[
        df["B365H"].between(float(m_row["h"]) - tolerans, float(m_row["h"]) + tolerans)
        & df["B365D"].between(float(m_row["b"]) - tolerans, float(m_row["b"]) + tolerans)
        & df["B365A"].between(float(m_row["a"]) - tolerans, float(m_row["a"]) + tolerans)
    ].copy()

    b = b.dropna(subset=["B365H", "B365D", "B365A", "FTHG", "FTAG"])
    if "HTHG" not in b.columns:
        b["HTHG"] = 0
    if "HTAG" not in b.columns:
        b["HTAG"] = 0
    if "FTR" not in b.columns:
        b["FTR"] = np.where(b["FTHG"] > b["FTAG"], "H", np.where(b["FTHG"] < b["FTAG"], "A", "D"))
    if "HTR" not in b.columns:
        b["HTR"] = "D"
    return b


def poisson_probs_from_odds(h: float, b: float, a: float, max_goals: int = 7) -> Dict[Tuple[int, int], float]:
    probs = [implied_prob(h), implied_prob(b), implied_prob(a)]
    s = sum(probs) or 1
    p_home, p_draw, p_away = [x / s for x in probs]
    diff = clamp((p_home - p_away) * 1.45, -1.05, 1.05)
    total_lambda = 2.55
    home_lambda = clamp(total_lambda / 2 + diff, 0.50, 3.30)
    away_lambda = clamp(total_lambda / 2 - diff, 0.40, 3.10)

    out = {}
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            ph = math.exp(-home_lambda) * (home_lambda ** hg) / math.factorial(hg)
            pa = math.exp(-away_lambda) * (away_lambda ** ag) / math.factorial(ag)
            out[(hg, ag)] = ph * pa
    total = sum(out.values()) or 1
    return {k: v / total for k, v in out.items()}


def model_market_probs(score_probs: Dict[Tuple[int, int], float]) -> Dict[str, float]:
    p = {}
    p["MS 1"] = sum(v for (h, a), v in score_probs.items() if h > a)
    p["Beraberlik"] = sum(v for (h, a), v in score_probs.items() if h == a)
    p["MS 2"] = sum(v for (h, a), v in score_probs.items() if h < a)
    p["1X"] = p["MS 1"] + p["Beraberlik"]
    p["X2"] = p["MS 2"] + p["Beraberlik"]
    p["1.5 Üst"] = sum(v for (h, a), v in score_probs.items() if h + a >= 2)
    p["2.5 Üst"] = sum(v for (h, a), v in score_probs.items() if h + a >= 3)
    p["3.5 Alt"] = sum(v for (h, a), v in score_probs.items() if h + a <= 3)
    p["4.5 Alt"] = sum(v for (h, a), v in score_probs.items() if h + a <= 4)
    p["KG Var"] = sum(v for (h, a), v in score_probs.items() if h >= 1 and a >= 1)
    p["KG Yok"] = 1 - p["KG Var"]
    p["Ev Sahibi 0.5 Üst"] = sum(v for (h, a), v in score_probs.items() if h >= 1)
    p["Deplasman 0.5 Üst"] = sum(v for (h, a), v in score_probs.items() if a >= 1)
    p["_scores"] = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:5]
    return p


def history_market_probs(b: pd.DataFrame) -> Dict[str, float]:
    if b is None or b.empty:
        return {}
    total = b["FTHG"] + b["FTAG"]
    home = b["FTHG"] > b["FTAG"]
    draw = b["FTHG"] == b["FTAG"]
    away = b["FTHG"] < b["FTAG"]
    p = {
        "MS 1": float(home.mean()),
        "Beraberlik": float(draw.mean()),
        "MS 2": float(away.mean()),
        "1X": float((home | draw).mean()),
        "X2": float((away | draw).mean()),
        "1.5 Üst": float((total >= 2).mean()),
        "2.5 Üst": float((total >= 3).mean()),
        "3.5 Alt": float((total <= 3).mean()),
        "4.5 Alt": float((total <= 4).mean()),
        "KG Var": float(((b["FTHG"] >= 1) & (b["FTAG"] >= 1)).mean()),
        "KG Yok": float(((b["FTHG"] == 0) | (b["FTAG"] == 0)).mean()),
        "Ev Sahibi 0.5 Üst": float((b["FTHG"] >= 1).mean()),
        "Deplasman 0.5 Üst": float((b["FTAG"] >= 1).mean()),
    }
    return p


def merge_probs(model_p: Dict[str, float], hist_p: Dict[str, float], sample: int, tolerans: float) -> Dict[str, float]:
    out = {}
    hist_weight = clamp(sample / 35, 0.15, 0.62) if sample > 0 else 0.0
    if tolerans >= 0.10:
        hist_weight *= 0.85
    model_weight = 1 - hist_weight
    for k, v in model_p.items():
        if k.startswith("_"):
            out[k] = v
            continue
        hv = hist_p.get(k)
        out[k] = float(v if hv is None else model_weight * v + hist_weight * hv)
    return out


def tahmini_skor_from_probs(score_items: List[Tuple[Tuple[int, int], float]], ana_label: str) -> str:
    if not score_items:
        return "-"
    scores = [s[0] for s in score_items[:3]]
    # Ana tahminle çelişen skorları azalt.
    filtered = []
    for hg, ag in scores:
        if ana_label == "2.5 Üst" and hg + ag < 3:
            continue
        if ana_label in ["3.5 Alt", "4.5 Alt"] and hg + ag > 4:
            continue
        if ana_label == "KG Yok" and hg > 0 and ag > 0:
            continue
        if ana_label == "KG Var" and (hg == 0 or ag == 0):
            continue
        filtered.append((hg, ag))
    use = filtered or scores
    return ", ".join([f"{hg}-{ag}" for hg, ag in use[:3]])


def market_odd(label: str, prob: float, m: Dict) -> Tuple[float, bool]:
    # API sadece MS veriyor. Diğer marketler fair oran tahminidir.
    if label == "MS 1":
        return safe_float(m.get("h"), fair_odd(prob)), False
    if label == "MS 2":
        return safe_float(m.get("a"), fair_odd(prob)), False
    if label == "Beraberlik":
        return safe_float(m.get("b"), fair_odd(prob)), False

    # Tahmini oranlar: bookmaker marjı düşülmüş fair oran.
    adj = 0.90 if label in ["4.5 Alt", "1X", "X2"] else 0.93 if label in ["3.5 Alt", "1.5 Üst"] else 0.95
    return round(max(1.05, fair_odd(prob, margin=0.02) * adj), 2), True


def combo_adaylari(base: Dict, probs: Dict[str, float], m: Dict) -> List[Dict]:
    combos = []
    home_fav = safe_float(m.get("h")) < safe_float(m.get("a"))
    ms_label = "MS 1" if home_fav else "MS 2"
    dc_label = "1X" if home_fav else "X2"

    def add(label, p, reason):
        if p <= 0:
            return
        odd = fair_odd(p, margin=0.10)
        combos.append({
            "label": label,
            "prob": p,
            "odd": odd,
            "estimated": True,
            "reason": reason,
        })

    # Agresif ama saçma olmayan kombolar.
    ms_p = probs.get(ms_label, 0)
    over15 = probs.get("1.5 Üst", 0)
    kg_var = probs.get("KG Var", 0)
    kg_yok = probs.get("KG Yok", 0)
    alt35 = probs.get("3.5 Alt", 0)

    if ms_p >= 0.55 and over15 >= 0.70:
        add(f"{ms_label} + 1.5 Üst", ms_p * over15 * 0.88, "Favori yönü ve minimum gol beklentisi aynı anda destekleniyor.")
    if dc_label in probs and probs.get(dc_label, 0) >= 0.72 and alt35 >= 0.66:
        add(f"{dc_label} + 3.5 Alt", probs[dc_label] * alt35 * 0.90, "Kaybetmez senaryo ve skor aralığı birlikte güçlü.")
    if ms_p >= 0.55 and kg_var >= 0.52:
        add(f"{ms_label} + KG Var", ms_p * kg_var * 0.82, "Favori kazanır ama rakibin gol bulma ihtimali de var.")
    if ms_p >= 0.58 and kg_yok >= 0.56:
        add(f"{ms_label} + KG Yok", ms_p * kg_yok * 0.86, "Favori kazanır ve rakibi golsüz tutabilir senaryosu.")

    return sorted(combos, key=lambda x: (x["prob"] * x["odd"], x["odd"]), reverse=True)


def secim_puanla(label: str, prob: float, odd: float, sample: int, tolerans: float, stabil: int, mod: str, estimated: bool) -> float:
    p = pct_int(prob)
    s_factor = sample_factor_hesapla(sample, tolerans)
    base = p * 1.00 + stabil * 4.0 + min(sample, 30) * 0.22 + s_factor * 8.0

    # Market önceliği: küçük sıra daha güvenli.
    guven_bonus = max(0, 12 - market_sira(label)) * 1.6
    value_bonus = max(0, odd - 1.30) * 12
    risk = risk_ceza(label, prob)
    estimated_penalty = 2.0 if estimated else 0.0

    if mod == "ultra":
        return base + guven_bonus * 2.3 - value_bonus * 0.35 - risk * 1.8 - estimated_penalty
    if mod == "value":
        return base + guven_bonus * 1.1 + value_bonus * 0.75 - risk * 1.0 - estimated_penalty * 0.5
    if mod == "agresif":
        return base * 0.72 + value_bonus * 2.15 + (18 if market_grubu(label) == "kombo" else 0) - risk * 0.75 - estimated_penalty * 0.2
    return base


def pick_reason(label: str, prob: float, sample: int, stabil: int, mod: str, score_hint: str) -> str:
    r = risk_label(prob, label)
    if mod == "ultra":
        return f"Ultra güvenli seçim: {label} daha az bozulan market grubunda. Güven {pct(prob)}, risk {r}, stabilite {stabil}/6, skor ihtimali {score_hint}."
    if mod == "value":
        return f"Oynanabilir seçim: güven/oran dengesi iyi. Güven {pct(prob)}, risk {r}, benzer maç {sample}, skor ihtimali {score_hint}."
    return f"Yüksek oran seçimi: oran yükseltmek için seçildi ama tamamen zayıf sinyal değil. Güven {pct(prob)}, risk {r}, stabilite {stabil}/6."


def hesapla(b_df: pd.DataFrame, m_row: pd.Series, tolerans: float) -> Tuple[Optional[Dict], pd.DataFrame]:
    m = {
        "lig": m_row.get("lig", "Lig"),
        "zaman": m_row.get("zaman", ""),
        "ev": m_row.get("ev", "Ev"),
        "dep": m_row.get("dep", "Dep"),
        "h": safe_float(m_row.get("h")),
        "b": safe_float(m_row.get("b")),
        "a": safe_float(m_row.get("a")),
    }

    if not all([m["h"], m["b"], m["a"]]):
        return None, pd.DataFrame()

    b = benzer_maclari_bul(b_df, pd.Series(m), tolerans)
    if b.empty:
        return None, b

    sample = len(b)
    total_goals = b["FTHG"] + b["FTAG"]
    avg_goal = float(total_goals.mean())

    score_probs = poisson_probs_from_odds(m["h"], m["b"], m["a"])
    model_p = model_market_probs(score_probs)
    hist_p = history_market_probs(b)
    probs = merge_probs(model_p, hist_p, sample, tolerans)
    score_items = probs.get("_scores", [])

    ms1 = probs.get("MS 1", 0)
    msx = probs.get("Beraberlik", 0)
    ms2 = probs.get("MS 2", 0)
    fav_label = "MS 1" if ms1 >= ms2 else "MS 2"
    fav_prob = max(ms1, ms2)
    dc_label = "1X" if fav_label == "MS 1" else "X2"

    # Ana tahmin: önce klasik model ne diyor?
    candidate_main = []
    for label in ["MS 1", "MS 2", "2.5 Üst", "KG Var", "KG Yok", "3.5 Alt"]:
        if label in probs:
            candidate_main.append((probs[label], label))
    ana_prob, ana_label = max(candidate_main, key=lambda x: x[0]) if candidate_main else (fav_prob, fav_label)
    ana_odd, ana_est = market_odd(ana_label, ana_prob, m)

    # Tüm izinli market adayları.
    allowed = [
        "4.5 Alt", "3.5 Alt", "1X", "X2", "1.5 Üst",
        "Ev Sahibi 0.5 Üst", "Deplasman 0.5 Üst",
        "MS 1", "MS 2", "KG Yok", "KG Var", "2.5 Üst",
    ]

    picks = []
    for label in allowed:
        if label not in probs:
            continue
        prob = probs[label]

        # Beraberlik ana market olarak kullanılmıyor; MS sadece favori taraf olacak.
        if label in ["MS 1", "MS 2"] and label != fav_label:
            continue

        odd, estimated = market_odd(label, prob, m)
        score_hint = tahmini_skor_from_probs(score_items, label)
        picks.append({
            "label": label,
            "prob": float(prob),
            "p": pct_int(prob),
            "odd": float(odd),
            "estimated": estimated,
            "risk": risk_label(prob, label),
            "group": market_grubu(label),
            "order": market_sira(label),
            "score_hint": score_hint,
        })

    # Kombo adayları sadece agresif için.
    for combo in combo_adaylari({}, probs, m):
        combo["p"] = pct_int(combo["prob"])
        combo["risk"] = risk_label(combo["prob"], combo["label"])
        combo["group"] = "kombo"
        combo["order"] = 10
        combo["score_hint"] = tahmini_skor_from_probs(score_items, combo["label"])
        picks.append(combo)

    return {
        "mac": m,
        "ornek": sample,
        "tolerans": tolerans,
        "onerilen_min_mac": dinamik_min_mac(tolerans),
        "match_type": mac_tipi(m["h"], m["a"]),
        "goal_profile": gol_profili(avg_goal),
        "avg_goal": avg_goal,
        "ana_label": ana_label,
        "ana_p": pct_int(ana_prob),
        "ana_odd": ana_odd,
        "ana_estimated": ana_est,
        "fav_label": fav_label,
        "fav_prob": pct_int(fav_prob),
        "draw_prob": pct_int(msx),
        "dc_label": dc_label,
        "dc_prob": pct_int(probs.get(dc_label, 0)),
        "score_hint": tahmini_skor_from_probs(score_items, ana_label),
        "picks": picks,
        "belirsiz": fav_prob < 0.42 and max(probs.get("2.5 Üst", 0), probs.get("KG Var", 0), probs.get("3.5 Alt", 0)) < 0.62,
    }, b


def stabilite_say(b_df: pd.DataFrame, m_row: pd.Series, label: str, mod: str) -> int:
    toleranslar = [0.00, 0.02, 0.05, 0.08, 0.10, 0.12]
    count = 0
    for tol in toleranslar:
        try:
            t, _ = hesapla(b_df, m_row, tol)
            if not t:
                continue
            best = pick_for_mode(t, mod, stabil=0, skip_stabil=True)
            if best and best.get("label") == label:
                count += 1
        except Exception:
            continue
    return count


def pick_for_mode(t: Dict, mod: str, stabil: int = 0, skip_stabil: bool = False) -> Optional[Dict]:
    if not t or t.get("belirsiz"):
        return None

    picks = list(t.get("picks", []))
    if not picks:
        return None

    filtered = []
    for p in picks:
        label = p["label"]
        prob = float(p["prob"])
        odd = float(p.get("odd", 1.0))
        group = market_grubu(label)

        if mod == "ultra":
            if label not in ["4.5 Alt", "3.5 Alt", "1X", "X2"]:
                continue
            if pct_int(prob) < 75:
                continue
            if risk_label(prob, label) == "YÜKSEK":
                continue
            if t.get("ornek", 0) < max(1, t.get("onerilen_min_mac", 1)):
                continue

        elif mod == "value":
            if label not in ["3.5 Alt", "1X", "X2", "1.5 Üst", "Ev Sahibi 0.5 Üst", "Deplasman 0.5 Üst", "MS 1", "MS 2", "KG Yok"]:
                continue
            if pct_int(prob) < 65:
                continue
            if risk_label(prob, label) == "YÜKSEK":
                continue
            # MS sadece net favoriyse ve çifte şans zaten çok daha mantıklı değilse.
            if label in ["MS 1", "MS 2"]:
                if pct_int(prob) < 70:
                    continue
                dc_prob = t.get("dc_prob", 0)
                if dc_prob >= pct_int(prob) + 12 and odd < 1.65:
                    continue

        elif mod == "agresif":
            if label not in ["MS 1", "MS 2", "KG Yok", "KG Var", "2.5 Üst", "1.5 Üst"] and market_grubu(label) != "kombo":
                continue
            if pct_int(prob) < 55:
                continue
            if odd < 1.45 and market_grubu(label) != "kombo":
                continue
        else:
            continue

        score = secim_puanla(label, prob, odd, t.get("ornek", 0), t.get("tolerans", 0.08), stabil, mod, p.get("estimated", False))
        pp = dict(p)
        pp["score"] = score
        pp["reason"] = pick_reason(label, prob, t.get("ornek", 0), stabil, mod, p.get("score_hint", "-"))
        filtered.append(pp)

    if not filtered:
        return None
    filtered.sort(key=lambda x: x["score"], reverse=True)
    return filtered[0]


def global_ai_tarama(b_df: pd.DataFrame, maclar: pd.DataFrame, limit: int = 100) -> List[Dict]:
    toleranslar = [0.00, 0.02, 0.05, 0.08, 0.10, 0.12]
    results = []
    if b_df is None or maclar is None or b_df.empty or maclar.empty:
        return []

    for _, m_row in maclar.iterrows():
        best_item = None
        for tol in toleranslar:
            try:
                t, b_det = hesapla(b_df, m_row, tol)
            except Exception:
                continue
            if not t or t.get("belirsiz"):
                continue

            mode_best = {}
            total_score = 0
            for mod in ["ultra", "value", "agresif"]:
                preliminary = pick_for_mode(t, mod, stabil=0, skip_stabil=True)
                if preliminary:
                    stab = stabilite_say(b_df, m_row, preliminary["label"], mod)
                    final_pick = pick_for_mode(t, mod, stabil=stab)
                    if final_pick:
                        final_pick["stabil"] = stab
                        mode_best[mod] = final_pick
                        total_score += final_pick["score"]

            if not mode_best:
                continue

            # Her maç için genel AI skoru.
            ai_skor = total_score / max(len(mode_best), 1)
            ai_skor += min(t.get("ornek", 0), 30) * 0.20
            ai_skor += max([p.get("stabil", 0) for p in mode_best.values()] or [0]) * 1.5

            item = {
                "mac": t["mac"],
                "t": t,
                "b": b_det,
                "tolerans": tol,
                "ai_skor": round(ai_skor, 1),
                "mode_best": mode_best,
            }
            if best_item is None or ai_skor > best_item["ai_skor"]:
                best_item = item

        if best_item:
            results.append(best_item)

    results.sort(key=lambda x: x["ai_skor"], reverse=True)
    return results[:limit]


# -----------------------------
# 3 KUPON BUILDER
# -----------------------------

def toplam_oran(kupon: List[Dict]) -> float:
    o = 1.0
    for item in kupon:
        o *= safe_float(item.get("oran"), 1.0)
    return round(o, 2)


def combo_probability(kupon: List[Dict]) -> float:
    p = 1.0
    for item in kupon:
        p *= clamp(safe_float(item.get("prob"), 0.0), 0.01, 0.99)
    # Kupon bacağı arttıkça korelasyon/variance cezası.
    return p * (0.97 ** max(0, len(kupon) - 1))


def make_coupon_item(ai_item: Dict, pick: Dict, mod: str) -> Dict:
    m = ai_item["mac"]
    t = ai_item["t"]
    return {
        "mac": m,
        "ev": m.get("ev", ""),
        "dep": m.get("dep", ""),
        "lig": m.get("lig", ""),
        "zaman": m.get("zaman", ""),
        "market": pick.get("label", "-"),
        "oran": float(pick.get("odd", 1.0)),
        "oran_tahmini": bool(pick.get("estimated", False)),
        "prob": float(pick.get("prob", 0.0)),
        "guven": int(pick.get("p", pct_int(pick.get("prob", 0)))) if pick.get("p") is not None else pct_int(pick.get("prob", 0)),
        "risk": pick.get("risk", risk_label(float(pick.get("prob", 0)), pick.get("label", ""))),
        "score": float(pick.get("score", 0)),
        "reason": pick.get("reason", ""),
        "score_hint": pick.get("score_hint", t.get("score_hint", "-")),
        "stabil": int(pick.get("stabil", 0)),
        "ai_skor": ai_item.get("ai_skor", 0),
        "mod": mod,
        "ornek": t.get("ornek", 0),
        "tolerans": ai_item.get("tolerans", t.get("tolerans", 0.08)),
    }


def smart_3_kupon_builder(ai_sonuclar: List[Dict]) -> Dict[str, Tuple[List[Dict], float]]:
    # Aynı kupon içinde aynı maç yok. Farklı kuponlarda aynı maç olabilir; çünkü risk seviyesi farklı market seçebilir.
    paketler = {}

    configs = {
        "ultra": {"max_len": 2, "min_len": 1, "title": "Ultra Güvenli"},
        "value": {"max_len": 3, "min_len": 1, "title": "Oynanabilir"},
        "agresif": {"max_len": 5, "min_len": 1, "title": "Yüksek Oran"},
    }

    for mod, cfg in configs.items():
        adaylar = []
        for item in ai_sonuclar:
            pick = item.get("mode_best", {}).get(mod)
            if not pick:
                continue
            ci = make_coupon_item(item, pick, mod)

            # Mode özel son filtreler.
            if mod == "ultra":
                if ci["guven"] < 75 or ci["risk"] == "YÜKSEK":
                    continue
                if ci["stabil"] < 2 and ci["ornek"] < 8:
                    continue
            elif mod == "value":
                if ci["guven"] < 65 or ci["risk"] == "YÜKSEK":
                    continue
            elif mod == "agresif":
                if ci["guven"] < 55:
                    continue

            adaylar.append(ci)

        if mod == "ultra":
            adaylar.sort(key=lambda x: (x["guven"], x["stabil"], x["score"], -x["oran"]), reverse=True)
        elif mod == "value":
            adaylar.sort(key=lambda x: (x["score"], x["guven"], x["oran"]), reverse=True)
        else:
            adaylar.sort(key=lambda x: (x["oran"], x["score"], x["guven"]), reverse=True)

        kupon = []
        used_matches = set()
        used_markets = {}
        used_leagues = {}

        for c in adaylar:
            key = mac_key(c["mac"])
            if key in used_matches:
                continue
            market = c["market"]
            lig = c["lig"]

            # Value/agresif için çeşitlilik.
            if mod in ["value", "agresif"]:
                if used_markets.get(market, 0) >= (1 if mod == "value" else 2):
                    continue
                if used_leagues.get(lig, 0) >= (1 if mod == "value" else 2):
                    continue

            kupon.append(c)
            used_matches.add(key)
            used_markets[market] = used_markets.get(market, 0) + 1
            used_leagues[lig] = used_leagues.get(lig, 0) + 1
            if len(kupon) >= cfg["max_len"]:
                break

        # Ultra güvenli: 2 maç yoksa tek maç kabul. Tek maç bile yoksa pas.
        # Value/agresif: kalite yoksa zorlama yok.
        paketler[mod] = (kupon, toplam_oran(kupon))

    return paketler


# -----------------------------
# GÜN RİSKİ + KASA PLANI
# -----------------------------

def gun_riski_belirle(ai_sonuclar: List[Dict]) -> str:
    ultra = 0
    value = 0
    for item in ai_sonuclar or []:
        p1 = item.get("mode_best", {}).get("ultra")
        p2 = item.get("mode_best", {}).get("value")
        if p1 and pct_int(p1.get("prob", 0)) >= 75:
            ultra += 1
        if p2 and pct_int(p2.get("prob", 0)) >= 65:
            value += 1

    if ultra >= 4:
        return "dusuk"
    if ultra >= 2 or value >= 5:
        return "normal"
    if value >= 2:
        return "yuksek"
    return "pas"


def gunluk_kasa_plani(kasa: float, hedef: float, kalan_gun: int, gun_risk: str) -> Dict:
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)
    gerekli_carpan = (hedef / kasa) ** (1 / kalan_gun)
    gerekli_yuzde = (gerekli_carpan - 1) * 100
    bugunku_hedef_kar = max(kasa * gerekli_carpan - kasa, 0.0)
    return {
        "kasa": round(kasa, 2),
        "hedef": round(hedef, 2),
        "kalan_gun": kalan_gun,
        "gerekli_gunluk_yuzde": round(gerekli_yuzde, 2),
        "bugunku_hedef_kar": round(bugunku_hedef_kar, 2),
        "gun_risk": gun_risk,
    }


def kupon_stake_hesapla(kasa: float, hedef: float, kalan_gun: int, toplam: float, gun_risk: str, mod: str) -> Dict:
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)
    toplam = max(float(toplam or 1.0), 1.01)

    if gun_risk == "pas":
        return {"stake": 0.0, "stake_orani": 0.0, "beklenen_net_kar": 0.0, "mesaj": "Bugün kalite düşük; pas daha mantıklı."}

    gerekli_carpan = (hedef / kasa) ** (1 / kalan_gun)
    bugunku_hedef_kar = max(kasa * gerekli_carpan - kasa, 0.0)
    teorik_stake = bugunku_hedef_kar / (toplam - 1)

    limitler = {
        "dusuk": {"ultra": 0.10, "value": 0.07, "agresif": 0.025},
        "normal": {"ultra": 0.07, "value": 0.05, "agresif": 0.020},
        "yuksek": {"ultra": 0.035, "value": 0.025, "agresif": 0.010},
        "pas": {"ultra": 0.0, "value": 0.0, "agresif": 0.0},
    }
    max_oran = limitler.get(gun_risk, limitler["normal"]).get(mod, 0.03)
    max_stake = kasa * max_oran
    stake = min(teorik_stake, max_stake)
    stake = max(0.0, stake)
    beklenen = stake * (toplam - 1)

    mesaj = "Risk limitine göre stake hesaplandı."
    if teorik_stake > max_stake:
        mesaj = "Günlük hedef için gereken stake risk limitini aşıyor; limitli stake verildi."
    if stake <= 0:
        mesaj = "Bu mod için stake önerilmedi."

    return {
        "stake": round(stake, 2),
        "stake_orani": round((stake / kasa) * 100, 2),
        "beklenen_net_kar": round(beklenen, 2),
        "mesaj": mesaj,
    }


def ai_yol_oner(kasa: float, hedef: float, kalan_gun: int, paketler: Dict, stake_bilgileri: Dict, gun_risk: str) -> Dict:
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)
    gerekli_yuzde = ((hedef / kasa) ** (1 / kalan_gun) - 1) * 100

    if gun_risk == "pas":
        return {"key": "pas", "baslik": "⛔ PAS", "sebep": "Bugün yeterli kalite yok. Tek maç bile net değilse zorlama.", "gerekli_yuzde": round(gerekli_yuzde, 2)}

    ultra, ultra_oran = paketler.get("ultra", ([], 1.0))
    value, value_oran = paketler.get("value", ([], 1.0))
    agresif, agresif_oran = paketler.get("agresif", ([], 1.0))

    if gerekli_yuzde <= 4 and ultra:
        return {"key": "ultra", "baslik": "🟢 Ultra Güvenli", "sebep": "Hedef baskısı düşük; en az riskli seçim yeterli.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
    if gerekli_yuzde <= 12 and value:
        return {"key": "value", "baslik": "🟡 Oynanabilir", "sebep": "Güven ve oran dengesi hedef için daha uygun.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
    if agresif and agresif_oran >= 3.0:
        return {"key": "agresif", "baslik": "🔴 Yüksek Oran", "sebep": "Hedef baskısı yüksek; düşük stake ile daha yüksek oran gerekli.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
    if value:
        return {"key": "value", "baslik": "🟡 Oynanabilir", "sebep": "Agresif kalite yeterli değil; value en dengeli yol.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
    if ultra:
        return {"key": "ultra", "baslik": "🟢 Ultra Güvenli", "sebep": "Sadece düşük riskli seçim var; tek maç yaklaşımı daha doğru.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
    return {"key": "pas", "baslik": "⛔ PAS", "sebep": "Kaliteli market bulunamadı.", "gerekli_yuzde": round(gerekli_yuzde, 2)}


# -----------------------------
# UI RENDER
# -----------------------------

def render_metric(label: str, value: str, sub: str = ""):
    st.markdown(
        f"""
        <div class='metric-card'>
            <div class='metric-label'>{label}</div>
            <div class='metric-value'>{value}</div>
            <div class='metric-sub'>{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_coupon(title: str, subtitle: str, kupon: List[Dict], oran: float, stake_info: Dict, border_class: str):
    if not kupon:
        body = "<div class='pick-box'><div class='pick-match'>Bu mod için yeterli kalite yok.</div><div class='pick-mini'>AI zorlama kupon üretmedi. Pas daha doğru.</div></div>"
        prob_text = "-"
    else:
        rows = []
        for p in kupon:
            est = " tahmini" if p.get("oran_tahmini") else ""
            risk_cls = "ok" if p.get("risk") == "DÜŞÜK" else "warn" if p.get("risk") == "ORTA" else "bad"
            zaman = p.get("zaman")
            try:
                ztxt = zaman.strftime("%d.%m %H:%M") if isinstance(zaman, datetime) else str(zaman)
            except Exception:
                ztxt = "-"
            rows.append(
                f"""
                <div class='pick-box'>
                    <div class='pick-top'>
                        <div>
                            <div class='pick-match'>{p.get('ev')} - {p.get('dep')}</div>
                            <div class='pick-mini'>{p.get('lig')} · {ztxt} · Benzer maç: {p.get('ornek')} · Stabil: {p.get('stabil')}/6</div>
                            <span class='pick-market'>{p.get('market')}</span>
                        </div>
                        <div style='text-align:right'>
                            <div class='pick-odd'>{fmt_odd(p.get('oran'))}</div>
                            <div class='pick-mini'>{est}</div>
                            <span class='status-pill {risk_cls}'>{p.get('risk')}</span>
                        </div>
                    </div>
                    <div class='pick-mini'>Güven: <b>%{p.get('guven')}</b> · Skor: {p.get('score_hint')}</div>
                    <div class='reason'>{p.get('reason')}</div>
                </div>
                """
            )
        body = "".join(rows)
        prob_text = pct(combo_probability(kupon))

    st.markdown(
        f"""
        <div class='coupon-card {border_class}'>
            <div class='coupon-title'>{title}</div>
            <div class='coupon-sub'>{subtitle}</div>
            {body}
            <div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px;'>
                <div class='metric-card'><div class='metric-label'>Toplam Oran</div><div class='metric-value'>{fmt_odd(oran)}</div><div class='metric-sub'>Kupon oranı</div></div>
                <div class='metric-card'><div class='metric-label'>Tahmini Tutma</div><div class='metric-value'>{prob_text}</div><div class='metric-sub'>Korelasyon cezalı</div></div>
            </div>
            <div class='reason' style='margin-top:10px;'>Stake: <b>{stake_info.get('stake', 0)} TL</b> · Kasa oranı: <b>%{stake_info.get('stake_orani', 0)}</b> · Beklenen net: <b>{stake_info.get('beklenen_net_kar', 0)} TL</b><br>{stake_info.get('mesaj', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_match_detail(item: Dict):
    m = item.get("mac", {})
    t = item.get("t", {})
    mode_best = item.get("mode_best", {})
    with st.expander(f"{m.get('ev')} - {m.get('dep')} · AI skor {item.get('ai_skor')}"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Ana Tahmin", f"{t.get('ana_label')} %{t.get('ana_p')}")
        with c2:
            st.metric("Favori", f"{t.get('fav_label')} %{t.get('fav_prob')}")
        with c3:
            st.metric("Çifte Şans", f"{t.get('dc_label')} %{t.get('dc_prob')}")
        with c4:
            st.metric("Benzer Maç", t.get("ornek", 0))

        rows = []
        for p in sorted(t.get("picks", []), key=lambda x: (market_sira(x.get("label", "")), -x.get("prob", 0))):
            if market_grubu(p.get("label")) == "kombo":
                continue
            rows.append({
                "Market": p.get("label"),
                "Güven": f"%{p.get('p')}",
                "Oran": fmt_odd(p.get("odd")),
                "Tahmini Oran": "Evet" if p.get("estimated") else "Hayır",
                "Risk": p.get("risk"),
                "Skor": p.get("score_hint"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("**AI mod seçimleri**")
        cols = st.columns(3)
        labels = [("ultra", "🟢 Ultra"), ("value", "🟡 Oynanabilir"), ("agresif", "🔴 Yüksek Oran")]
        for col, (key, label) in zip(cols, labels):
            with col:
                p = mode_best.get(key)
                if not p:
                    st.info(f"{label}: Pas")
                else:
                    st.success(f"{label}: {p.get('label')} · %{p.get('p')} · {fmt_odd(p.get('odd'))}")
                    st.caption(p.get("reason", ""))

        sim = item.get("b")
        if sim is not None and not sim.empty:
            show_cols = [c for c in ["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A", "FTHG", "FTAG"] if c in sim.columns]
            st.markdown("**Benzer oranlı maçlar**")
            st.dataframe(sim[show_cols].head(20), use_container_width=True, hide_index=True)


# -----------------------------
# UYGULAMA
# -----------------------------
st.markdown(
    """
    <div class='topbar'>
        <h1>⚡ VIBE PRO EXPERT</h1>
        <div class='sub'>AI otomatik 3 kupon seçer: Ultra Güvenli · Oynanabilir · Yüksek Oran. MS analiz edilir ama daha güvenli alternatif varsa final seçim değişir.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ Ayarlar")
    api_key = st.text_input("The Odds API Key", type="password")
    target_date = st.date_input("Maç tarihi", value=datetime.now().date())

    sports_options = {
        "İngiltere Premier League": "soccer_epl",
        "İspanya La Liga": "soccer_spain_la_liga",
        "Almanya Bundesliga": "soccer_germany_bundesliga",
        "İtalya Serie A": "soccer_italy_serie_a",
        "Fransa Ligue 1": "soccer_france_ligue_one",
        "Türkiye Süper Lig": "soccer_turkey_super_league",
        "Hollanda Eredivisie": "soccer_netherlands_eredivisie",
        "Portekiz Primeira": "soccer_portugal_primeira_liga",
        "Belçika Pro League": "soccer_belgium_first_div",
        "MLS": "soccer_usa_mls",
        "Danimarka Superliga": "soccer_denmark_superliga",
        "Suudi Pro League": "soccer_saudi_arabia_pro_league",
    }
    selected_leagues = st.multiselect("Ligler", list(sports_options.keys()), default=list(sports_options.keys())[:6])
    sezonlar = st.multiselect("Geçmiş sezonlar", ["2526", "2425", "2324", "2223", "2122"], default=["2526", "2425", "2324", "2223"])

    st.divider()
    use_demo = st.checkbox("Demo veriyle çalıştır", value=False)
    csv_matches = st.file_uploader("Güncel maç CSV", type=["csv"])
    csv_history = st.file_uploader("Geçmiş veri CSV", type=["csv"])

    st.divider()
    takip_gun = st.number_input("Kaçıncı gün?", min_value=1, max_value=30, value=1, step=1)
    kasa = st.number_input("Güncel kasa", min_value=1.0, value=1000.0, step=50.0)
    hedef = st.number_input("Ay sonu hedef", min_value=1.0, value=100000.0, step=1000.0)
    kalan_gun = max(1, 31 - int(takip_gun))


# Veri hazırlığı
if csv_history is not None:
    gecmis_df = pd.read_csv(csv_history)
elif use_demo:
    gecmis_df = demo_history()
else:
    with st.spinner("Geçmiş veri hazırlanıyor..."):
        gecmis_df = futbol_veri_motoru(sezonlar)

if csv_matches is not None:
    bulten_df = pd.read_csv(csv_matches)
    if "zaman" in bulten_df.columns:
        bulten_df["zaman"] = bulten_df["zaman"].apply(parse_mac_datetime)
elif use_demo or not api_key:
    bulten_df = demo_bulten()
else:
    kodlar = [sports_options[x] for x in selected_leagues]
    with st.spinner("Bülten çekiliyor..."):
        bulten_df = bulten_cek(api_key, kodlar, target_date)

# Kolon kontrolü
needed_match_cols = {"lig", "zaman", "ev", "dep", "h", "b", "a"}
if bulten_df is None or bulten_df.empty:
    st.warning("Maç bulunamadı. API key, lig veya tarih kontrol et. Demo veriyle denemek için soldan demo modunu açabilirsin.")
    st.stop()
if not needed_match_cols.issubset(set(bulten_df.columns)):
    st.error(f"Güncel maç verisinde şu kolonlar olmalı: {', '.join(sorted(needed_match_cols))}")
    st.stop()

needed_hist_cols = {"B365H", "B365D", "B365A", "FTHG", "FTAG"}
if gecmis_df is None or gecmis_df.empty or not needed_hist_cols.issubset(set(gecmis_df.columns)):
    st.warning("Geçmiş veri eksik. Demo geçmiş veri kullanılacak.")
    gecmis_df = demo_history()

st.session_state["last_gecmis_df"] = gecmis_df
st.session_state["last_bulten_df"] = bulten_df

m1, m2, m3, m4 = st.columns(4)
with m1:
    render_metric("Bülten", str(len(bulten_df)), "Taranacak maç")
with m2:
    render_metric("Geçmiş Veri", str(len(gecmis_df)), "Benzer oran havuzu")
with m3:
    render_metric("Kalan Gün", str(kalan_gun), "Kasa planı")
with m4:
    render_metric("Tarih", format_tr_date(target_date), "Türkiye saati")

if st.button("🎯 AI TARA + 3 KUPON OLUŞTUR", use_container_width=True):
    with st.spinner("AI tüm maçları farklı hassasiyetlerde tarıyor ve 3 kupon modunu seçiyor..."):
        ai_sonuclar = global_ai_tarama(gecmis_df, bulten_df, limit=100)
        paketler = smart_3_kupon_builder(ai_sonuclar)
        gun_risk = gun_riski_belirle(ai_sonuclar)
        plan = gunluk_kasa_plani(kasa, hedef, kalan_gun, gun_risk)
        stake_bilgileri = {
            "ultra": kupon_stake_hesapla(kasa, hedef, kalan_gun, paketler["ultra"][1], gun_risk, "ultra"),
            "value": kupon_stake_hesapla(kasa, hedef, kalan_gun, paketler["value"][1], gun_risk, "value"),
            "agresif": kupon_stake_hesapla(kasa, hedef, kalan_gun, paketler["agresif"][1], gun_risk, "agresif"),
        }
        yol = ai_yol_oner(kasa, hedef, kalan_gun, paketler, stake_bilgileri, gun_risk)
        st.session_state["ai_sonuclar"] = ai_sonuclar
        st.session_state["paketler"] = paketler
        st.session_state["gun_risk"] = gun_risk
        st.session_state["plan"] = plan
        st.session_state["stake_bilgileri"] = stake_bilgileri
        st.session_state["yol"] = yol

ai_sonuclar = st.session_state.get("ai_sonuclar")
paketler = st.session_state.get("paketler")

if not ai_sonuclar:
    st.info("Henüz tarama yapılmadı. Butona basınca AI 3 kuponu otomatik oluşturacak.")
    st.stop()

plan = st.session_state.get("plan", {})
yol = st.session_state.get("yol", {})
stake_bilgileri = st.session_state.get("stake_bilgileri", {})
gun_risk = st.session_state.get("gun_risk", "normal")

st.markdown("---")
st.subheader("🧠 AI Gün Kararı")
cc1, cc2, cc3, cc4 = st.columns(4)
with cc1:
    render_metric("Gün Riski", gun_risk.upper(), "dusuk / normal / yuksek / pas")
with cc2:
    render_metric("AI Önerisi", yol.get("baslik", "-"), yol.get("sebep", ""))
with cc3:
    render_metric("Gerekli Günlük", f"%{plan.get('gerekli_gunluk_yuzde', 0)}", "Hedefe göre")
with cc4:
    render_metric("Bugünkü Hedef Kâr", f"{plan.get('bugunku_hedef_kar', 0)} TL", "Teorik")

st.markdown("---")
st.subheader("🎫 AI Otomatik 3 Kupon")

ultra, ultra_oran = paketler.get("ultra", ([], 1.0))
value, value_oran = paketler.get("value", ([], 1.0))
agresif, agresif_oran = paketler.get("agresif", ([], 1.0))

k1, k2, k3 = st.columns(3)
with k1:
    render_coupon(
        "🟢 Ultra Güvenli",
        "1-2 maç · en düşük riskli marketler · kalite yoksa tek maç/pas",
        ultra,
        ultra_oran,
        stake_bilgileri.get("ultra", {}),
        "green-border",
    )
with k2:
    render_coupon(
        "🟡 Oynanabilir",
        "2-3 maç · güven + oran dengesi · MS varsa alternatifi kontrol edilir",
        value,
        value_oran,
        stake_bilgileri.get("value", {}),
        "yellow-border",
    )
with k3:
    render_coupon(
        "🔴 Yüksek Oran",
        "3-5 maç · risk kontrollü yüksek oran · kombo sadece burada",
        agresif,
        agresif_oran,
        stake_bilgileri.get("agresif", {}),
        "red-border",
    )

st.markdown("---")
st.subheader("📋 AI Maç Detayları")
st.caption("Her maçta MS analiz edilir; ama finalde daha güvenli market daha mantıklıysa AI onu seçer. AH0 ve +1 handikap kullanılmaz.")

for item in ai_sonuclar:
    render_match_detail(item)

st.warning("Bu sistem tahmin ve risk analizi üretir; kesin kazanç garanti etmez. 8/10 hedefi için en önemli kural: AI kaliteli seçim bulamıyorsa PAS demelidir.")
