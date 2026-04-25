
import math
from datetime import datetime, timedelta, date
from html import escape

import pandas as pd
import requests
import streamlit as st


# ==========================================================
# PAGE CONFIG
# ==========================================================
st.set_page_config(page_title="VIBE ANALİZ", layout="wide", page_icon="⚡")


# ==========================================================
# BASIC STYLE
# ==========================================================
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
.main .block-container {
    padding-top: 1rem;
    max-width: 1500px;
}
section[data-testid="stSidebar"] {
    background: #eef3fb !important;
    border-right: 1px solid #d6e0ef;
}
.stButton > button {
    background: linear-gradient(180deg,#0d1a2f 0%, #0b1526 100%) !important;
    color: #f8fafc !important;
    border: 1px solid #284977 !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
}
.stButton > button:hover {
    border-color: #facc15 !important;
}
.top-title {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:16px;
    margin-bottom:10px;
}
.top-title h1 {
    margin:0;
    color:#0b1f3a;
    font-family:'Rajdhani',sans-serif;
    font-size:2.1rem;
    letter-spacing:.5px;
}
.sub {
    color:#64748b;
    font-size:.92rem;
}
.notice {
    background:#fff7ed;
    border:1px solid #fdba74;
    border-radius:12px;
    padding:11px 14px;
    color:#7c2d12;
    font-size:.86rem;
    margin:8px 0 14px;
}
.control-card {
    background:#ffffff;
    border:1px solid #dbe4f0;
    border-radius:16px;
    padding:14px;
    box-shadow:0 8px 25px rgba(15,23,42,.06);
}
.control-label {
    color:#64748b;
    font-size:.75rem;
    font-weight:800;
    text-transform:uppercase;
    letter-spacing:.7px;
    margin-bottom:8px;
}
.metric-card {
    background:linear-gradient(135deg,#07111f,#0a1830);
    border:1px solid #223c63;
    border-radius:16px;
    padding:16px 18px;
    color:#f8fafc;
}
.metric-card .k {font-size:.72rem;color:#9db2d1;font-weight:800;letter-spacing:.8px;text-transform:uppercase;}
.metric-card .v {font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:800;margin-top:4px;}
.match-card {
    background:#111827;
    border:1px solid #1f2a44;
    border-radius:16px;
    padding:14px 16px;
    color:#f8fafc;
    margin-bottom:10px;
}
.match-top {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:12px;
}
.badge {
    display:inline-block;
    padding:4px 10px;
    border-radius:999px;
    font-size:.72rem;
    font-weight:800;
}
.badge-green {background:#12351f;color:#4ade80;border:1px solid #166534;}
.badge-yellow {background:#3a2b0b;color:#facc15;border:1px solid #854d0e;}
.badge-red {background:#3a1212;color:#f87171;border:1px solid #7f1d1d;}
.badge-blue {background:#0b2745;color:#7dd3fc;border:1px solid #075985;}
.small-muted {color:#94a3b8;font-size:.78rem;}
.pred-line {font-size:.9rem;margin-top:8px;line-height:1.6;}
.top10-card {
    background:#0f172a;
    border:1px solid #1f2a44;
    border-radius:14px;
    padding:14px 16px;
    color:#f8fafc;
    margin-bottom:10px;
}
.detail-box {
    background:linear-gradient(135deg,#0f172a,#111827);
    border:1px solid #1f2a44;
    color:#f8fafc;
    border-radius:16px;
    padding:18px;
    margin-bottom:12px;
}
.history-card {
    background:#0f172a;
    border:1px solid #1f2a44;
    color:#f8fafc;
    border-radius:16px;
    padding:16px;
}
div[data-testid="stExpander"] {
    border-radius:14px !important;
}
</style>
""", unsafe_allow_html=True)


# ==========================================================
# APP VERSION / SESSION
# ==========================================================
APP_SCHEMA_VERSION = 31
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION


# ==========================================================
# API KEY SYSTEM
# ==========================================================
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


def api_key_panel():
    with st.sidebar:
        st.markdown("### 🔑 API Key")
        api_key_input = st.text_input(
            "ODDS API KEY",
            value=st.session_state.get("user_api_key", ""),
            type="password",
            placeholder="API key gir...",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Kaydet", use_container_width=True, key="save_api_key"):
                st.session_state["user_api_key"] = api_key_input.strip()
                st.success("API key kaydedildi.")
                st.rerun()
        with c2:
            if st.button("Temizle", use_container_width=True, key="clear_api_key"):
                st.session_state.pop("user_api_key", None)
                st.success("API key temizlendi.")
                st.rerun()

        if get_app_api_key():
            st.success("API key aktif ✅")
        else:
            st.warning("Maçları çekmek için API key gerekiyor.")

        st.markdown("---")
        with st.expander("⚖️ Disclaimer", expanded=False):
            st.markdown("""
Bu platform yalnızca **istatistiksel analiz** ve **geçmiş veri karşılaştırması** sunar.

Sunulan içerikler kesinlik içermez ve yatırım tavsiyesi değildir.  
Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.
            """)


def require_api_key():
    if not get_app_api_key():
        st.warning("Devam etmek için sol menüden ODDS API KEY girmen gerekiyor.")
        st.stop()


api_key_panel()


# ==========================================================
# LEGAL TOP NOTICE
# ==========================================================
st.markdown("""
<div class="notice">
<b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler ve geçmiş veri karşılaştırmaları sunar.
Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir ve bağımlılık oluşturabilir.
</div>
""", unsafe_allow_html=True)


# ==========================================================
# DATE HELPERS
# ==========================================================
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


def tarih_secimine_gore_date(secim, bugun, ozel):
    if secim == "Bugün":
        return bugun
    if secim == "Yarın":
        return bugun + timedelta(days=1)
    if secim == "2 gün sonra":
        return bugun + timedelta(days=2)
    if secim == "3 gün sonra":
        return bugun + timedelta(days=3)
    return ozel


def mac_canli_durumu(mac_zamani):
    now = datetime.now()
    if now < mac_zamani:
        return "Başlamamış"
    if now <= mac_zamani + timedelta(hours=2, minutes=15):
        return "Canlı"
    return "Bitti"


# ==========================================================
# LEAGUES
# ==========================================================
KARARLI_CEKIRDEK_LIGLER = {
    "Premier League": "soccer_epl",
    "Championship": "soccer_efl_champ",
    "La Liga": "soccer_spain_la_liga",
    "La Liga 2": "soccer_spain_segunda_division",
    "Serie A": "soccer_italy_serie_a",
    "Serie B": "soccer_italy_serie_b",
    "Bundesliga": "soccer_germany_bundesliga",
    "Bundesliga 2": "soccer_germany_bundesliga2",
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Süper Lig": "soccer_turkey_super_league",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Eliteserien": "soccer_norway_eliteserien",
    "Swiss Super League": "soccer_switzerland_superleague",
    "MLS": "soccer_usa_mls",
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
}

KARLI_VALUE_LIGLER = {
    "Portugal Primeira Liga": "soccer_portugal_primeira_liga",
    "Belgium Pro League": "soccer_belgium_first_div",
    "Austria Bundesliga": "soccer_austria_bundesliga",
    "Denmark Superliga": "soccer_denmark_superliga",
    "Sweden Allsvenskan": "soccer_sweden_allsvenskan",
    "Finland Veikkausliiga": "soccer_finland_veikkausliiga",
    "Scotland Premiership": "soccer_spl",
    "Poland Ekstraklasa": "soccer_poland_ekstraklasa",
    "Greece Super League": "soccer_greece_super_league",
    "Brazil Serie A": "soccer_brazil_campeonato",
    "Argentina Primera": "soccer_argentina_primera_division",
    "Japan J League": "soccer_japan_j_league",
    "Korea K League 1": "soccer_korea_kleague1",
    "Mexico Liga MX": "soccer_mexico_ligamx",
}


LEAGUE_EMOJIS = {
    "Premier League": "🏴",
    "Championship": "🏴",
    "La Liga": "🇪🇸",
    "La Liga 2": "🇪🇸",
    "Serie A": "🇮🇹",
    "Serie B": "🇮🇹",
    "Bundesliga": "🇩🇪",
    "Bundesliga 2": "🇩🇪",
    "Ligue 1": "🇫🇷",
    "Ligue 2": "🇫🇷",
    "Süper Lig": "🇹🇷",
    "Eredivisie": "🇳🇱",
    "Eliteserien": "🇳🇴",
    "Swiss Super League": "🇨🇭",
    "MLS": "🇺🇸",
    "Champions League": "🏆",
    "Europa League": "🏆",
    "Conference League": "🏆",
    "Portugal Primeira Liga": "🇵🇹",
    "Belgium Pro League": "🇧🇪",
    "Austria Bundesliga": "🇦🇹",
    "Denmark Superliga": "🇩🇰",
    "Sweden Allsvenskan": "🇸🇪",
    "Finland Veikkausliiga": "🇫🇮",
    "Scotland Premiership": "🏴",
    "Poland Ekstraklasa": "🇵🇱",
    "Greece Super League": "🇬🇷",
    "Brazil Serie A": "🇧🇷",
    "Argentina Primera": "🇦🇷",
    "Japan J League": "🇯🇵",
    "Korea K League 1": "🇰🇷",
    "Mexico Liga MX": "🇲🇽",
}


def lig_label(name):
    return f"{LEAGUE_EMOJIS.get(name, '⚽')} {name}"


# ==========================================================
# HISTORICAL DATA
# ==========================================================
@st.cache_data(ttl=86400, show_spinner=False)
def futbol_veri_motoru(sezonlar):
    if not sezonlar:
        return pd.DataFrame()

    # football-data.co.uk codes
    lig_map = [
        "E0", "E1", "E2",
        "SP1", "SP2",
        "D1", "D2",
        "I1", "I2",
        "F1", "F2",
        "T1",
        "N1", "B1", "P1", "SC0",
    ]

    liste = []
    for k in lig_map:
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = [
                    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG",
                    "FTR", "HTR", "B365H", "B365D", "B365A", "HC", "AC", "HY", "AY"
                ]
                df = df[df.columns.intersection(cols)]
                df = df.dropna(subset=["B365H", "B365D", "B365A"]).copy()
                df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
                df["LeagueCode"] = k
                liste.append(df)
            except Exception:
                continue

    if not liste:
        return pd.DataFrame()
    out = pd.concat(liste, ignore_index=True)
    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.dropna(subset=["B365H", "B365D", "B365A"]).reset_index(drop=True)


# ==========================================================
# ODDS API FETCH
# ==========================================================
@st.cache_data(ttl=1800, show_spinner=False)
def bulten_cek_cached(key_last4, full_key, kodlar_tuple, target_date_iso):
    # key_last4 only helps cache identity without exposing secret in UI.
    key = full_key
    kodlar = list(kodlar_tuple)
    target_date = datetime.strptime(target_date_iso, "%Y-%m-%d").date()

    res = []
    for k in kodlar:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{k}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue

            data = r.json()
            if not isinstance(data, list):
                continue

            for m in data:
                try:
                    tm = datetime.strptime(m["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except Exception:
                    continue

                if tm.date() != target_date:
                    continue

                bookies = m.get("bookmakers", [])
                if not bookies:
                    continue

                market = None
                for bk in bookies:
                    for mk in bk.get("markets", []):
                        if mk.get("key") == "h2h":
                            market = mk
                            break
                    if market:
                        break

                if not market:
                    continue

                outcomes = market.get("outcomes", [])
                home = m.get("home_team", "")
                away = m.get("away_team", "")

                if not away:
                    teams = m.get("teams", [])
                    for team in teams:
                        if team != home:
                            away = team
                            break

                h = next((x.get("price") for x in outcomes if x.get("name") == home), None)
                a = next((x.get("price") for x in outcomes if x.get("name") == away), None)
                d = next((x.get("price") for x in outcomes if str(x.get("name", "")).lower() in ["draw", "tie", "beraberlik"]), None)

                if h is None or a is None or d is None:
                    continue

                res.append({
                    "lig": m.get("sport_title", k),
                    "kod": k,
                    "zaman": tm,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "b": float(d),
                    "a": float(a),
                    "durum": mac_canli_durumu(tm),
                })
        except Exception:
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    return df.sort_values("zaman").reset_index(drop=True)


def bulten_cek(key, kodlar, target_date):
    if not key:
        return pd.DataFrame()
    key_last4 = key[-4:] if len(key) >= 4 else "key"
    return bulten_cek_cached(key_last4, key, tuple(kodlar), target_date.isoformat())


# ==========================================================
# ANALYSIS HELPERS
# ==========================================================
def fmt_odd(odd):
    if odd is None or odd == "":
        return "-"
    try:
        return f"{float(odd):.2f}"
    except Exception:
        return "-"


def pct100(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:
        return 0


def dinamik_min_mac(tolerans):
    tolerans = float(tolerans)
    if tolerans <= 0.02:
        return 1
    if tolerans <= 0.05:
        return 3
    if tolerans <= 0.08:
        return 5
    if tolerans <= 0.12:
        return 10
    return 20


def sample_factor_hesapla(sample, tolerans):
    if tolerans <= 0.02:
        hedef = 5
    elif tolerans <= 0.05:
        hedef = 10
    elif tolerans <= 0.08:
        hedef = 15
    elif tolerans <= 0.12:
        hedef = 25
    else:
        hedef = 40
    return min(0.75 + 0.25 * (sample / max(hedef, 1)), 1.0)


def guven_label_color(pct):
    pct = int(pct)
    if pct >= 70:
        return "Yüksek", "#22c55e", "badge-green"
    if pct >= 55:
        return "Orta", "#facc15", "badge-yellow"
    return "Düşük", "#f87171", "badge-red"


def risk_seviyesi(pct, flip_p):
    if pct >= 70 and flip_p < 0.15:
        return "DÜŞÜK"
    if pct >= 55:
        return "ORTA"
    return "YÜKSEK"


def mac_tipi(h, a):
    if abs(float(h) - float(a)) <= 0.50:
        return "Dengeli"
    if float(h) < 2.0 or float(a) < 2.0:
        return "Favori"
    return "Sürpriz Açık"


def gol_profili(avg_goal):
    if avg_goal < 2.2:
        return "Düşük Gollü"
    if avg_goal < 3.0:
        return "Dengeli"
    return "Yüksek Gollü"


def fake_confidence_duzelt(conf_prob, sample, tolerans):
    carpan = 1.0
    if tolerans <= 0.05 and sample < 10 and conf_prob > 0.80:
        carpan *= 0.75
    elif tolerans <= 0.08 and sample < 8 and conf_prob > 0.75:
        carpan *= 0.82
    return conf_prob * carpan, carpan < 1.0


def skoru_tahmine_uydur(eg, dg, ana_label, ms_mod):
    ana = str(ana_label or "")
    if "2.5 Alt" in ana:
        return (1, 0) if ms_mod == "H" else (0, 1) if ms_mod == "A" else (1, 1)
    if "2.5 Üst" in ana:
        return (2, 1) if ms_mod == "H" else (1, 2) if ms_mod == "A" else (2, 2)
    if ana == "KG Yok":
        return (2, 0) if ms_mod == "H" else (0, 2) if ms_mod == "A" else (0, 0)
    if ana == "KG Var":
        return (2, 1) if ms_mod == "H" else (1, 2) if ms_mod == "A" else (1, 1)

    eg, dg = int(eg), int(dg)
    if ana == "MS 1" and eg <= dg:
        eg = dg + 1
    elif ana == "MS 2" and dg <= eg:
        dg = eg + 1
    elif ana == "Beraberlik":
        mx = max(eg, dg, 1)
        eg = dg = mx
    return eg, dg


def hesapla(b_df, m_row, tolerans):
    if b_df is None or b_df.empty:
        return None, pd.DataFrame()

    h = float(m_row["h"])
    d = float(m_row["b"])
    a = float(m_row["a"])

    b = b_df[
        (b_df["B365H"].between(h - tolerans, h + tolerans)) &
        (b_df["B365D"].between(d - tolerans, d + tolerans)) &
        (b_df["B365A"].between(a - tolerans, a + tolerans))
    ].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG"]:
        if c not in b.columns:
            b[c] = 0
        b[c] = pd.to_numeric(b[c], errors="coerce").fillna(0)

    sample = len(b)
    min_mac = dinamik_min_mac(float(tolerans))

    home_win = (b["FTHG"] > b["FTAG"]).mean()
    draw = (b["FTHG"] == b["FTAG"]).mean()
    away_win = (b["FTHG"] < b["FTAG"]).mean()

    over25 = ((b["FTHG"] + b["FTAG"]) >= 3).mean()
    under25 = 1 - over25
    over15 = ((b["FTHG"] + b["FTAG"]) >= 2).mean()
    under35 = ((b["FTHG"] + b["FTAG"]) <= 3).mean()
    btts_yes = ((b["FTHG"] > 0) & (b["FTAG"] > 0)).mean()
    btts_no = 1 - btts_yes
    iy05 = ((b["HTHG"] + b["HTAG"]) >= 1).mean()

    ms_probs = {
        "MS 1": home_win,
        "Beraberlik": draw,
        "MS 2": away_win,
    }
    ms_label = max(ms_probs, key=ms_probs.get)
    ms_p_raw = ms_probs[ms_label]

    alt_label = "2.5 Üst" if over25 >= under25 else "2.5 Alt"
    alt_p_raw = max(over25, under25)

    kg_label = "KG Var" if btts_yes >= btts_no else "KG Yok"
    kg_p_raw = max(btts_yes, btts_no)

    iy05_label = "İY 0.5 Üst" if iy05 >= 0.55 else ""
    iy05_p_raw = iy05 if iy05_label else 0

    # Ana tahmin: ekranda ana maç için en güçlü yalın market seçilsin.
    ana_adaylar = [
        ("MS", ms_label, ms_p_raw),
        ("Alt/Üst", alt_label, alt_p_raw),
        ("KG", kg_label, kg_p_raw),
    ]
    ana_tip, ana_label, ana_prob = max(ana_adaylar, key=lambda x: x[2])

    adj_prob, fake_drop = fake_confidence_duzelt(float(ana_prob), sample, float(tolerans))
    sample_factor = sample_factor_hesapla(sample, float(tolerans))
    ana_p = pct100(adj_prob * sample_factor * 100)

    ms_mod = "H" if ms_label == "MS 1" else "A" if ms_label == "MS 2" else "D"
    eg = math.floor(b["FTHG"].mean() + 0.5)
    dg = math.floor(b["FTAG"].mean() + 0.5)
    eg, dg = skoru_tahmine_uydur(eg, dg, ana_label, ms_mod)

    avg_goal = float((b["FTHG"] + b["FTAG"]).mean())
    match_type = mac_tipi(h, a)
    goal_profile = gol_profili(avg_goal)

    flip_probs = [home_win, draw, away_win]
    flip_p = min(flip_probs) if flip_probs else 0

    # Kombo mantığı: çok agresif değil, sadece uyumlu senaryoyu gösterir.
    combo_label = ""
    combo_p = 0
    combo_hit = 0

    if ms_label == "MS 1" and over25 >= 0.55:
        combo_label = "MS 1 + 2.5 Üst"
        combo_hit = int(((b["FTHG"] > b["FTAG"]) & ((b["FTHG"] + b["FTAG"]) >= 3)).sum())
        combo_p = pct100(combo_hit / max(sample, 1) * 100)
    elif ms_label == "MS 2" and over25 >= 0.55:
        combo_label = "MS 2 + 2.5 Üst"
        combo_hit = int(((b["FTHG"] < b["FTAG"]) & ((b["FTHG"] + b["FTAG"]) >= 3)).sum())
        combo_p = pct100(combo_hit / max(sample, 1) * 100)
    elif ms_label == "MS 1" and btts_yes >= 0.55:
        combo_label = "MS 1 + KG Var"
        combo_hit = int(((b["FTHG"] > b["FTAG"]) & (b["FTHG"] > 0) & (b["FTAG"] > 0)).sum())
        combo_p = pct100(combo_hit / max(sample, 1) * 100)
    elif ms_label == "MS 2" and btts_yes >= 0.55:
        combo_label = "MS 2 + KG Var"
        combo_hit = int(((b["FTHG"] < b["FTAG"]) & (b["FTHG"] > 0) & (b["FTAG"] > 0)).sum())
        combo_p = pct100(combo_hit / max(sample, 1) * 100)
    elif under25 >= 0.58 and btts_no >= 0.55:
        combo_label = "2.5 Alt + KG Yok"
        combo_hit = int((((b["FTHG"] + b["FTAG"]) <= 2) & ~((b["FTHG"] > 0) & (b["FTAG"] > 0))).sum())
        combo_p = pct100(combo_hit / max(sample, 1) * 100)

    ana_odd = h if ms_label == "MS 1" else a if ms_label == "MS 2" else d

    playable_score = round(
        ana_p
        + min(sample, 30) * 0.20
        - (8 if fake_drop else 0)
        - (4 if sample < min_mac else 0),
        1,
    )

    risk_label = risk_seviyesi(ana_p, flip_p)

    t = {
        "ana_tip": ana_tip,
        "ana_label": ana_label,
        "ana_p": ana_p,
        "ana_odd": ana_odd,
        "ms_label": ms_label,
        "ms_p": pct100(ms_p_raw * sample_factor * 100),
        "alt_label": alt_label,
        "alt_p": pct100(alt_p_raw * sample_factor * 100),
        "kg_label": kg_label,
        "kg_p": pct100(kg_p_raw * sample_factor * 100),
        "iy05_label": iy05_label,
        "iy05_p": pct100(iy05_p_raw * sample_factor * 100),
        "combo_label": combo_label,
        "combo_p": combo_p,
        "combo_hit": combo_hit,
        "ornek": int(sample),
        "onerilen_min_mac": int(min_mac),
        "eg": int(eg),
        "dg": int(dg),
        "playable_score": playable_score,
        "risk_label": risk_label,
        "fake_drop": bool(fake_drop),
        "match_type": match_type,
        "goal_profile": goal_profile,
        "avg_goal": round(avg_goal, 2),
        "belirsiz": sample < min_mac and ana_p < 60,
        "oynanabilir": ana_p >= 55 and sample >= 1,
    }
    return t, b


def kombo_tahmini_oran(label, ana_odd):
    try:
        ana_odd = float(ana_odd or 1.0)
    except Exception:
        ana_odd = 1.0

    lbl = str(label or "")
    if not lbl:
        return ana_odd
    if "HT/FT" in lbl:
        return max(ana_odd * 2.40, 2.40)
    if "KG Var" in lbl or "KG Yok" in lbl:
        return max(ana_odd * 1.55, 1.55)
    if "2.5 Üst" in lbl or "2.5 Alt" in lbl:
        return max(ana_odd * 1.45, 1.45)
    if "+" in lbl:
        return max(ana_odd * 1.60, 1.60)
    return ana_odd


def top10_market_adaylari(t):
    marketler = []

    if t.get("ms_label") and int(t.get("ms_p", 0)) >= 50:
        marketler.append({
            "label": t.get("ms_label"),
            "guven": int(t.get("ms_p", 0)),
            "tip": "MS",
            "oran": t.get("ana_odd"),
            "bonus": 0,
        })

    if t.get("alt_label") and int(t.get("alt_p", 0)) >= 52:
        marketler.append({
            "label": t.get("alt_label"),
            "guven": int(t.get("alt_p", 0)),
            "tip": "Alt/Üst",
            "oran": None,
            "bonus": 9,
        })

    if t.get("kg_label") and int(t.get("kg_p", 0)) >= 52:
        marketler.append({
            "label": t.get("kg_label"),
            "guven": int(t.get("kg_p", 0)),
            "tip": "KG",
            "oran": None,
            "bonus": 9,
        })

    if t.get("iy05_label") and int(t.get("iy05_p", 0)) >= 55:
        marketler.append({
            "label": t.get("iy05_label"),
            "guven": int(t.get("iy05_p", 0)),
            "tip": "İlk Yarı",
            "oran": None,
            "bonus": 6,
        })

    if t.get("combo_label") and int(t.get("combo_p", 0)) >= 42:
        marketler.append({
            "label": t.get("combo_label"),
            "guven": int(t.get("combo_p", 0)),
            "tip": "Kombo",
            "oran": kombo_tahmini_oran(t.get("combo_label"), t.get("ana_odd")),
            "bonus": 5,
        })

    return marketler


def gunun_en_iyi_10_uret(b_df, maclar, min_ornek=1, limit=10):
    sonuc = []
    toleranslar = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10]

    if b_df is None or maclar is None or getattr(b_df, "empty", True) or getattr(maclar, "empty", True):
        return []

    for real_idx, m in maclar.iterrows():
        en_iyi = None

        for tol in toleranslar:
            try:
                t, b_det = hesapla(b_df, m, tol)
            except Exception:
                continue

            if not t or t.get("belirsiz"):
                continue

            if int(t.get("ornek", 0)) < int(min_ornek):
                continue

            marketler = top10_market_adaylari(t)
            if not marketler:
                continue

            secilen = max(marketler, key=lambda x: x["guven"] + x["bonus"])

            tol_ceza = float(tol) * 100
            skor = (
                float(t.get("playable_score", 0))
                + secilen["guven"] * 0.45
                + min(int(t.get("ornek", 0)), 30) * 0.20
                + secilen["bonus"]
                - tol_ceza
            )

            if en_iyi is None or skor > en_iyi["skor"]:
                en_iyi = {
                    "real_idx": int(real_idx),
                    "m": m.to_dict(),
                    "t": t,
                    "b": b_det,
                    "label": secilen["label"],
                    "guven": secilen["guven"],
                    "tip": secilen["tip"],
                    "oran": secilen["oran"],
                    "tol": tol,
                    "skor": round(skor, 1),
                }

        if en_iyi:
            sonuc.append(en_iyi)

    return sorted(sonuc, key=lambda x: x["skor"], reverse=True)[:limit]


def ai_yorum_uret(t):
    ana = t.get("ana_label", "")
    guven = int(t.get("ana_p", 0))
    ornek = int(t.get("ornek", 0))
    mac_tipi_txt = t.get("match_type", "")
    gol_profili_txt = t.get("goal_profile", "")
    combo = t.get("combo_label", "")

    if t.get("belirsiz"):
        return "Model bu maçta yeterince net örnek bulamıyor. Canlı başlangıç temposunu izlemek daha mantıklı."

    yorum = f"Model ana senaryoda {ana} tarafını öne çıkarıyor."
    if guven >= 70:
        yorum += " Güven seviyesi yüksek görünüyor."
    elif guven >= 55:
        yorum += " Güven orta bölgede; tek başına abartmamak gerekir."
    else:
        yorum += " Güven sınırlı; dikkatli yaklaşılmalı."

    detay = []
    if mac_tipi_txt:
        detay.append(f"maç tipi {mac_tipi_txt.lower()}")
    if gol_profili_txt:
        detay.append(f"gol profili {gol_profili_txt.lower()}")
    if combo:
        detay.append(f"kombo desteği: {combo}")
    if ornek < 5:
        detay.append("örnek sayısı düşük")
    elif ornek >= 20:
        detay.append("örnek sayısı sağlıklı")

    if detay:
        yorum += " " + " · ".join(detay).capitalize() + "."
    return yorum


# ==========================================================
# HEADER
# ==========================================================
st.markdown("""
<div class="top-title">
    <div>
        <h1>⚡ VIBE ANALİZ</h1>
        <div class="sub">Kararlı çekirdek ligler + kârlı/value lig filtresi · Multi-market Top 10 · API cache aktif</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================================
# CONTROL BAR
# ==========================================================
today = datetime.now().date()

bar1, bar2, bar3, bar4, bar5 = st.columns([1.3, 1.2, 1, 1, 1.2])

with bar1:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Tarih</div>', unsafe_allow_html=True)
    tarih_secim = st.selectbox(
        "Tarih",
        ["Bugün", "Yarın", "2 gün sonra", "3 gün sonra", "Özel tarih"],
        label_visibility="collapsed",
        key="tarih_secim",
    )
    ozel_tarih = st.date_input(
        "Özel tarih",
        value=today,
        label_visibility="collapsed",
        key="ozel_tarih",
    )
    secili_tarih = tarih_secimine_gore_date(tarih_secim, today, ozel_tarih)
    st.caption(format_tr_date(secili_tarih))
    st.markdown('</div>', unsafe_allow_html=True)

with bar2:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Sezonlar</div>', unsafe_allow_html=True)
    sezonlar = st.multiselect(
        "Sezonlar",
        ["2122", "2223", "2324", "2425", "2526"],
        default=["2122", "2223", "2324", "2425", "2526"],
        label_visibility="collapsed",
        key="sezonlar",
    )
    st.caption("Geçmiş oran benzerliği için.")
    st.markdown('</div>', unsafe_allow_html=True)

with bar3:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Min. Örnek</div>', unsafe_allow_html=True)
    min_ornek = st.number_input(
        "Min örnek",
        min_value=1,
        max_value=50,
        value=1,
        step=1,
        label_visibility="collapsed",
        key="min_ornek",
    )
    st.markdown('</div>', unsafe_allow_html=True)

with bar4:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Hassasiyet</div>', unsafe_allow_html=True)
    TOLERANS = st.slider(
        "Oran Hassasiyeti",
        0.00,
        0.30,
        0.08,
        step=0.01,
        label_visibility="collapsed",
        key="tolerans",
    )
    st.markdown(f"<b style='color:#0b1f3a'>{TOLERANS:.2f}</b>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with bar5:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Filtre</div>', unsafe_allow_html=True)
    oynanabilir_esik = st.selectbox(
        "Güven eşiği",
        [0, 50, 55, 60, 65, 70, 75],
        index=2,
        format_func=lambda x: "Tümü" if x == 0 else f"Güven ≥ %{x}",
        label_visibility="collapsed",
        key="oynanabilir_esik",
    )
    canli_filtre = st.selectbox(
        "Canlı filtre",
        ["Tümü", "Canlı", "Başlamamış", "Bitti"],
        index=0,
        label_visibility="collapsed",
        key="canli_filtre",
    )
    st.markdown('</div>', unsafe_allow_html=True)


# ==========================================================
# LEAGUE FILTERS
# ==========================================================
st.markdown("### 🏟️ Lig Filtreleri")

with st.expander("✅ Kararlı Çekirdek Ligler", expanded=True):
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Çekirdek tümünü seç", use_container_width=True, key="core_all"):
            st.session_state["secili_cekirdek_ligler"] = list(KARARLI_CEKIRDEK_LIGLER.keys())
            st.rerun()
    with c2:
        if st.button("Çekirdek temizle", use_container_width=True, key="core_clear"):
            st.session_state["secili_cekirdek_ligler"] = []
            st.rerun()

    secili_cekirdek = st.multiselect(
        "Ana analiz için lig seç",
        options=list(KARARLI_CEKIRDEK_LIGLER.keys()),
        default=[
            "Premier League", "Championship", "La Liga", "La Liga 2", "Serie A",
            "Bundesliga", "Bundesliga 2", "Ligue 1", "Süper Lig",
            "Eredivisie", "Eliteserien", "MLS", "Champions League", "Europa League", "Conference League"
        ],
        format_func=lig_label,
        key="secili_cekirdek_ligler",
    )

with st.expander("💎 Kârlı / Value Ligleri", expanded=False):
    value_aktif = st.checkbox(
        "Value liglerini de taramaya dahil et",
        value=False,
        key="value_ligleri_aktif",
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Value tümünü seç", use_container_width=True, key="value_all"):
            st.session_state["secili_value_ligler"] = list(KARLI_VALUE_LIGLER.keys())
            st.rerun()
    with c2:
        if st.button("Value temizle", use_container_width=True, key="value_clear"):
            st.session_state["secili_value_ligler"] = []
            st.rerun()

    secili_value = st.multiselect(
        "Value odaklı lig seç",
        options=list(KARLI_VALUE_LIGLER.keys()),
        default=[
            "Portugal Primeira Liga",
            "Belgium Pro League",
            "Austria Bundesliga",
            "Denmark Superliga",
            "Sweden Allsvenskan",
            "Finland Veikkausliiga",
        ],
        format_func=lig_label,
        key="secili_value_ligler",
    )

secili_lig_kodlari = [
    KARARLI_CEKIRDEK_LIGLER[x]
    for x in secili_cekirdek
    if x in KARARLI_CEKIRDEK_LIGLER
]

if value_aktif:
    secili_lig_kodlari += [
        KARLI_VALUE_LIGLER[x]
        for x in secili_value
        if x in KARLI_VALUE_LIGLER
    ]

secili_lig_kodlari = list(dict.fromkeys(secili_lig_kodlari))

if value_aktif:
    st.info(f"✅ {len(secili_cekirdek)} çekirdek lig + {len(secili_value)} value lig taranacak. Toplam API lig çağrısı: {len(secili_lig_kodlari)}")
else:
    st.info(f"✅ Sadece {len(secili_cekirdek)} kararlı çekirdek lig taranacak. API lig çağrısı: {len(secili_lig_kodlari)}")


# ==========================================================
# FETCH / ANALYZE BUTTONS
# ==========================================================
btn1, btn2, btn3 = st.columns([1.2, 1.2, 1])

with btn1:
    mac_yukle = st.button("⚡ Maçları Yükle", use_container_width=True, key="mac_yukle_btn")
with btn2:
    analiz_baslat = st.button("🔁 Tekrar Analiz Başlat", use_container_width=True, key="analiz_baslat_btn")
with btn3:
    if st.button("🧹 Veriyi Temizle", use_container_width=True, key="clear_data_btn"):
        for k in ["last_bulten_df", "last_gecmis_df", "analiz_sonuclari", "top10_list", "detay_item"]:
            st.session_state.pop(k, None)
        st.rerun()

if mac_yukle:
    require_api_key()
    if not secili_lig_kodlari:
        st.warning("En az bir lig seçmelisin.")
        st.stop()

    with st.spinner("Geçmiş veri hazırlanıyor..."):
        gecmis = futbol_veri_motoru(sezonlar)

    with st.spinner("The Odds API bülteni çekiliyor..."):
        bulten = bulten_cek(get_app_api_key(), secili_lig_kodlari, secili_tarih)

    st.session_state["last_gecmis_df"] = gecmis
    st.session_state["last_bulten_df"] = bulten

    st.success(f"Maçlar yüklendi. Bulunan maç: {0 if bulten is None else len(bulten)}")

if analiz_baslat or mac_yukle:
    gecmis = st.session_state.get("last_gecmis_df", pd.DataFrame())
    bulten = st.session_state.get("last_bulten_df", pd.DataFrame())

    if gecmis is None or gecmis.empty:
        st.warning("Geçmiş veri yok. Önce maçları yükle.")
    elif bulten is None or bulten.empty:
        st.warning("Seçili tarih/liglerde maç bulunamadı.")
    else:
        analiz_sonuclari = []
        with st.spinner("Analiz hesaplanıyor..."):
            for real_idx, m in bulten.iterrows():
                try:
                    t, b_det = hesapla(gecmis, m, float(TOLERANS))
                except Exception:
                    continue
                if not t:
                    continue

                if int(t.get("ornek", 0)) < int(min_ornek):
                    continue

                if oynanabilir_esik and int(t.get("ana_p", 0)) < int(oynanabilir_esik):
                    continue

                if canli_filtre != "Tümü" and str(m.get("durum", "")) != canli_filtre:
                    continue

                analiz_sonuclari.append({
                    "real_idx": int(real_idx),
                    "m": m.to_dict(),
                    "t": t,
                    "b": b_det,
                })

        analiz_sonuclari.sort(
            key=lambda x: (
                float(x["t"].get("playable_score", 0)),
                int(x["t"].get("ana_p", 0)),
                int(x["t"].get("ornek", 0)),
            ),
            reverse=True,
        )
        st.session_state["analiz_sonuclari"] = analiz_sonuclari

        # Top10 seçili hassasiyetten bağımsızdır.
        st.session_state["top10_list"] = gunun_en_iyi_10_uret(
            gecmis,
            bulten,
            min_ornek=min_ornek,
            limit=10,
        )

        st.success(f"Analiz tamamlandı. Listelenen maç: {len(analiz_sonuclari)}")


# ==========================================================
# DATA REFERENCES
# ==========================================================
gecmis = st.session_state.get("last_gecmis_df", pd.DataFrame())
bulten = st.session_state.get("last_bulten_df", pd.DataFrame())
analiz_sonuclari = st.session_state.get("analiz_sonuclari", [])
top10_list = st.session_state.get("top10_list", [])


# ==========================================================
# METRICS
# ==========================================================
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f"<div class='metric-card'><div class='k'>Ham Maç</div><div class='v'>{0 if bulten is None else len(bulten)}</div></div>", unsafe_allow_html=True)
with m2:
    st.markdown(f"<div class='metric-card'><div class='k'>Analiz Listesi</div><div class='v'>{len(analiz_sonuclari)}</div></div>", unsafe_allow_html=True)
with m3:
    st.markdown(f"<div class='metric-card'><div class='k'>Top 10</div><div class='v'>{len(top10_list)}</div></div>", unsafe_allow_html=True)
with m4:
    last_info = "Yok"
    if bulten is not None and not getattr(bulten, "empty", True):
        last_info = datetime.now().strftime("%H:%M")
    st.markdown(f"<div class='metric-card'><div class='k'>Son İşlem</div><div class='v'>{last_info}</div></div>", unsafe_allow_html=True)


# ==========================================================
# TOP 10 EXPANDER
# ==========================================================
with st.expander("🔥 Günün En İyi 10 Maçı", expanded=False):
    if not top10_list:
        st.info("Top 10 için önce maçları yükleyip analiz başlat.")
    else:
        st.caption("Bu bölüm seçili hassasiyete bağlı değildir. Her maç 0.00 / 0.02 / 0.04 / 0.06 / 0.08 / 0.10 ile denenir ve en iyi market seçilir.")

        for sira, item in enumerate(top10_list, start=1):
            m = item["m"]
            t = item["t"]
            guven_label, guven_color, badge_cls = guven_label_color(item["guven"])

            col1, col2 = st.columns([7, 1])
            with col1:
                st.markdown(f"""
                <div class="top10-card">
                    <div style="font-size:.82rem;color:#facc15;font-weight:900;">
                        #{sira} · {escape(str(m.get('lig','')))} · {m.get('zaman').strftime('%H:%M') if hasattr(m.get('zaman'), 'strftime') else ''}
                    </div>
                    <div style="font-size:1.08rem;font-weight:900;margin-top:4px;">
                        {escape(str(m.get('ev','')))} - {escape(str(m.get('dep','')))}
                    </div>
                    <div class="pred-line">
                        Market: <b>{escape(str(item.get('tip','')))}</b> ·
                        Tahmin: <b>{escape(str(item.get('label','')))}</b> ·
                        Güven: <b style="color:{guven_color}">%{item.get('guven',0)} ({guven_label})</b> ·
                        Tolerans: <b>{item.get('tol',0):.2f}</b> ·
                        Örnek: <b>{t.get('ornek',0)}</b> ·
                        Skor: <b>{t.get('eg','')}-{t.get('dg','')}</b> ·
                        Oran: <b>{fmt_odd(item.get('oran'))}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                if st.button("Detay →", key=f"top10_detail_{sira}", use_container_width=True):
                    st.session_state["detay_item"] = item
                    st.rerun()


# ==========================================================
# DETAIL SCREEN
# ==========================================================
if st.session_state.get("detay_item"):
    item = st.session_state["detay_item"]
    m = item["m"]
    t = item["t"]
    b_det = item.get("b", pd.DataFrame())

    st.markdown("## 📊 Maç Detayı")

    if st.button("← Detayı Kapat", key="close_detail"):
        st.session_state.pop("detay_item", None)
        st.rerun()

    st.markdown(f"""
    <div class="detail-box">
        <div style="font-size:.86rem;color:#facc15;font-weight:900;">{escape(str(m.get('lig','')))} · {m.get('zaman').strftime('%d.%m %H:%M') if hasattr(m.get('zaman'), 'strftime') else ''}</div>
        <div style="font-family:Rajdhani,sans-serif;font-size:1.8rem;font-weight:900;margin-top:5px;">
            {escape(str(m.get('ev','')))} - {escape(str(m.get('dep','')))}
        </div>
        <div style="margin-top:8px;color:#cbd5e1;">
            Oranlar: MS1 <b>{fmt_odd(m.get('h'))}</b> · X <b>{fmt_odd(m.get('b'))}</b> · MS2 <b>{fmt_odd(m.get('a'))}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown(f"""
        <div class="detail-box">
            <b>Ana Tahmin</b><br><br>
            Tahmin: <b>{escape(str(t.get('ana_label','-')))}</b><br>
            Güven: <b>%{t.get('ana_p',0)}</b><br>
            Risk: <b>{escape(str(t.get('risk_label','-')))}</b><br>
            Tahmini Skor: <b>{t.get('eg','')}-{t.get('dg','')}</b>
        </div>
        """, unsafe_allow_html=True)
    with d2:
        st.markdown(f"""
        <div class="detail-box">
            <b>Marketler</b><br><br>
            MS: <b>{escape(str(t.get('ms_label','-')))} · %{t.get('ms_p',0)}</b><br>
            Alt/Üst: <b>{escape(str(t.get('alt_label','-')))} · %{t.get('alt_p',0)}</b><br>
            KG: <b>{escape(str(t.get('kg_label','-')))} · %{t.get('kg_p',0)}</b><br>
            İlk Yarı: <b>{escape(str(t.get('iy05_label','-')))} · %{t.get('iy05_p',0)}</b>
        </div>
        """, unsafe_allow_html=True)
    with d3:
        st.markdown(f"""
        <div class="detail-box">
            <b>Veri Kalitesi</b><br><br>
            Örnek: <b>{t.get('ornek',0)}</b><br>
            Önerilen min: <b>{t.get('onerilen_min_mac',0)}</b><br>
            Maç tipi: <b>{escape(str(t.get('match_type','-')))}</b><br>
            Gol profili: <b>{escape(str(t.get('goal_profile','-')))}</b>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="detail-box">
        <b>Yorum</b><br>
        {escape(ai_yorum_uret(t))}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Benzer Oranlı Geçmiş Maçlar", expanded=False):
        if b_det is None or b_det.empty:
            st.info("Benzer geçmiş maç bulunamadı.")
        else:
            show_cols = [c for c in ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"] if c in b_det.columns]
            st.dataframe(b_det[show_cols].tail(20), use_container_width=True, hide_index=True)


# ==========================================================
# MAIN MATCH LIST
# ==========================================================
st.markdown("## 📌 Anlık Maç Tahminleri")

if not analiz_sonuclari:
    st.info("Henüz analiz sonucu yok. Önce maçları yükle ve analiz başlat.")
else:
    for i, item in enumerate(analiz_sonuclari):
        m = item["m"]
        t = item["t"]

        guven_label, guven_color, badge_cls = guven_label_color(t.get("ana_p", 0))
        durum = m.get("durum", "")
        durum_cls = "badge-blue" if durum == "Başlamamış" else "badge-green" if durum == "Canlı" else "badge-red"

        col1, col2 = st.columns([7, 1])
        with col1:
            st.markdown(f"""
            <div class="match-card">
                <div class="match-top">
                    <div>
                        <span class="badge {durum_cls}">{escape(str(durum))}</span>
                        <span class="small-muted"> {escape(str(m.get('lig','')))} · {m.get('zaman').strftime('%H:%M') if hasattr(m.get('zaman'), 'strftime') else ''}</span>
                    </div>
                    <div class="small-muted">Örnek: <b>{t.get('ornek',0)}</b></div>
                </div>
                <div style="font-size:1.08rem;font-weight:900;margin-top:8px;">
                    {escape(str(m.get('ev','')))} - {escape(str(m.get('dep','')))}
                </div>
                <div class="pred-line">
                    Ana Tahmin: <b>{escape(str(t.get('ana_label','-')))}</b> ·
                    Güven: <b style="color:{guven_color}">%{t.get('ana_p',0)} ({guven_label})</b> ·
                    Risk: <b>{escape(str(t.get('risk_label','-')))}</b> ·
                    Tahmini Skor: <b>{t.get('eg','')}-{t.get('dg','')}</b> ·
                    Playable: <b>{t.get('playable_score',0)}</b>
                </div>
                <div class="small-muted" style="margin-top:6px;">
                    MS: {escape(str(t.get('ms_label','-')))} %{t.get('ms_p',0)} ·
                    Alt/Üst: {escape(str(t.get('alt_label','-')))} %{t.get('alt_p',0)} ·
                    KG: {escape(str(t.get('kg_label','-')))} %{t.get('kg_p',0)}
                    {(' · Kombo: ' + escape(str(t.get('combo_label',''))) + ' %' + str(t.get('combo_p',0))) if t.get('combo_label') else ''}
                </div>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            if st.button("Detay →", key=f"list_detail_{i}", use_container_width=True):
                st.session_state["detay_item"] = item
                st.rerun()


# ==========================================================
# FOOTER
# ==========================================================
st.markdown("""
---
<div style="text-align:center;font-size:12px;color:#64748b;line-height:1.55;padding:10px 0 4px 0;">
    <b>Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analiz ve geçmiş veri karşılaştırması sunar.
    Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir.
</div>
""", unsafe_allow_html=True)
