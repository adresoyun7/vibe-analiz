
import math
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st


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

st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")

APP_SCHEMA_VERSION = 11
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

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
.floating-coupon {position:fixed;right:18px;bottom:18px;width:320px;z-index:999;background:linear-gradient(180deg,#07111f 0%, #0a1830 100%);border:1px solid #284977;border-radius:18px;box-shadow:0 18px 40px rgba(2,8,23,.28);padding:14px 16px;}
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
section[data-testid="stSidebar"] * {
    color: #334155 !important;
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
    border: 1px solid #284977 !important;
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
</style>
""", unsafe_allow_html=True)


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


def fake_confidence_duzelt(conf_prob: float, sample: int, tolerans: float):
    carpan = 1.0
    if tolerans <= 0.05 and sample < 10 and conf_prob > 0.80:
        carpan *= 0.75
    elif tolerans <= 0.08 and sample < 8 and conf_prob > 0.75:
        carpan *= 0.82
    return conf_prob * carpan, carpan < 1.0


@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar:
        return pd.DataFrame()

    lig_map = [
        # TÜRKİYE
        "T1",

        # İNGİLTERE
        "E0", "E1", "E2",

        # İSPANYA
        "SP1", "SP2",

        # ALMANYA
        "D1", "D2",

        # İTALYA
        "I1", "I2",

        # FRANSA
        "F1", "F2",

        # AVRUPA ANA VALUE
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
                temp = df.dropna(subset=["B365H", "B365D", "B365A"]).copy()
                temp["Date"] = pd.to_datetime(temp["Date"], dayfirst=True, errors="coerce")
                liste.append(temp)
            except Exception:
                continue

    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()


def bulten_cek(key, kodlar, t):
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
                timeout=12,
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

                if tm.date() != t:
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

                h = next((x["price"] for x in outcomes if x["name"] == home), None)
                a = next((x["price"] for x in outcomes if x["name"] == away), None)
                b = next((x["price"] for x in outcomes if str(x["name"]).lower() in ["draw", "tie", "beraberlik"]), None)

                if h is None or a is None or b is None:
                    continue

                res.append({
                    "lig": m.get("sport_title", k),
                    "zaman": tm,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "b": float(b),
                    "a": float(a),
                })
        except Exception:
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    return df.sort_values("zaman").reset_index(drop=True)






def fmt_odd(odd):
    if odd is None:
        return ""
    try:
        return f"{float(odd):.2f}"
    except Exception:
        return ""

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
        f"{c['m']['ev']} vs {c['m']['dep']} — {c['t']['ana_label']} ({fmt_odd(c['ana_odd'])})"
        for c in picks
    ]


def market_label_to_odd(m_row, label):
    if not isinstance(m_row, dict):
        try:
            m_row = m_row.to_dict()
        except Exception:
            pass
    if label == "MS 1":
        return m_row.get("h")
    if label == "MS 2":
        return m_row.get("a")
    if label == "Beraberlik":
        return m_row.get("b")
    return None

def hesapla(b_df, m_row, tolerans):
    rehber = tolerans_rehberi(float(tolerans))
    onerilen_min_mac = dinamik_min_mac(float(tolerans))

    b = b_df[
        (b_df["B365H"].between(m_row["h"] - tolerans, m_row["h"] + tolerans)) &
        (b_df["B365D"].between(m_row["b"] - tolerans, m_row["b"] + tolerans)) &
        (b_df["B365A"].between(m_row["a"] - tolerans, m_row["a"] + tolerans))
    ].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")

    b = b.dropna(subset=["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A", "FTR", "HTR"])
    if b.empty:
        return None, b

    sample = len(b)
    toplam_gol = b["FTHG"] + b["FTAG"]
    ilk_yari_gol = b["HTHG"] + b["HTAG"]

    ms_vc = b["FTR"].value_counts(normalize=True)
    iy_vc = b["HTR"].value_counts(normalize=True)

    ms_mod = ms_vc.idxmax() if not ms_vc.empty else "D"
    ms_raw = float(ms_vc.get(ms_mod, 0))
    ms_side = "MS 1" if ms_mod == "H" else "MS 2" if ms_mod == "A" else "Beraberlik"

    ms1_raw = float(ms_vc.get("H", 0))
    msx_raw = float(ms_vc.get("D", 0))
    ms2_raw = float(ms_vc.get("A", 0))

    ms25_raw = float((toplam_gol >= 3).mean())
    ms35_raw = float((toplam_gol >= 4).mean())
    ms15_raw = float((toplam_gol >= 2).mean())
    kg_raw = float(((b["FTHG"] > 0) & (b["FTAG"] > 0)).mean())
    iy05_raw = float((ilk_yari_gol >= 1).mean())
    iy15_raw = float((ilk_yari_gol >= 2).mean())

    htft_s = b["HTR"].replace({"H": "1", "A": "2", "D": "X"}) + "/" + b["FTR"].replace({"H": "1", "A": "2", "D": "X"})
    htft_mod = htft_s.mode()[0] if not htft_s.empty else "-"
    htft_raw = float(htft_s.value_counts(normalize=True).get(htft_mod, 0)) if not htft_s.empty else 0.0

    oran_ev = float(m_row["h"])
    oran_ber = float(m_row["b"])
    oran_dep = float(m_row["a"])

    sample_factor = sample_factor_hesapla(sample, float(tolerans))
    if oran_ev < 1.40 or oran_dep < 1.40:
        oran_factor = 0.93
    elif oran_ev > 6.50 or oran_dep > 6.50:
        oran_factor = 0.95
    else:
        oran_factor = 1.0

    guven_carpani = sample_factor * oran_factor
    match_type = mac_tipi(oran_ev, oran_dep)

    # maç tipine göre model davranışı
    ms_bias = 1.0
    goal_bias = 1.0
    combo_bias = 1.0
    if match_type == "Favori":
        ms_bias = 1.06
        goal_bias = 0.96
        combo_bias = 0.97
    elif match_type == "Dengeli":
        ms_bias = 0.95
        goal_bias = 1.05
        combo_bias = 1.02
    elif match_type == "Sürpriz Açık":
        ms_bias = 0.92
        goal_bias = 1.03
        combo_bias = 1.08

    ms_prob = min(ms_raw * guven_carpani * ms_bias, 0.99)
    ou25_best_raw = max(ms25_raw, 1 - ms25_raw)
    ou25_prob = min(ou25_best_raw * guven_carpani * goal_bias, 0.99)
    kg_best_raw = max(kg_raw, 1 - kg_raw)
    kg_prob = min(kg_best_raw * guven_carpani * goal_bias, 0.99)

    ms_label = ms_side
    ou_label = "2.5 Üst" if ms25_raw >= 0.5 else "2.5 Alt"
    kg_label = "KG Var" if kg_raw >= 0.5 else "KG Yok"

    # belirsiz maç tespiti
    ms_sorted = sorted([ms1_raw, msx_raw, ms2_raw], reverse=True)
    belirsiz = (max(ms1_raw, msx_raw, ms2_raw) < 0.42 and (ms_sorted[0] - ms_sorted[1]) < 0.06) or (abs(ms1_raw - ms2_raw) < 0.05 and abs(ms1_raw - msx_raw) < 0.05)

    cands = [
        {"label": ms_label, "raw_prob": ms_raw, "conf_prob": ms_prob, "market": "ms"},
        {"label": ou_label, "raw_prob": ou25_best_raw, "conf_prob": ou25_prob, "market": "ou25"},
        {"label": kg_label, "raw_prob": kg_best_raw, "conf_prob": kg_prob, "market": "kg"},
    ]

    best = max(cands, key=lambda x: x["raw_prob"])
    best_conf, fake_drop = fake_confidence_duzelt(best["conf_prob"], sample, float(tolerans))

    ana_label = best["label"]
    ana_p = int(round(best_conf * 100))
    ana_raw_p = int(round(best["raw_prob"] * 100))

    others = [c for c in cands if c["label"] != ana_label]
    alt = max(others, key=lambda x: x["raw_prob"]) if others else cands[1]
    alt_conf, _ = fake_confidence_duzelt(alt["conf_prob"], sample, float(tolerans))
    alt_label = alt["label"]
    alt_p = int(round(alt_conf * 100))

    def alt_destekli_mi(ana, alt_lbl):
        if not alt_lbl:
            return False
        destek = {
            "2.5 Üst": {"KG Var"},
            "2.5 Alt": {"KG Yok"},
            "KG Var": {"2.5 Üst"},
            "KG Yok": {"2.5 Alt"},
            "MS 1": {"2.5 Üst", "KG Var", "2.5 Alt", "KG Yok"},
            "MS 2": {"2.5 Üst", "KG Var", "2.5 Alt", "KG Yok"},
            "Beraberlik": {"KG Var", "2.5 Alt"},
        }
        return alt_lbl in destek.get(ana, set())

    if not alt_destekli_mi(ana_label, alt_label):
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
    htft_series = b["HTR"].replace({"H": "1", "D": "X", "A": "2"}) + "/" + b["FTR"].replace({"H": "1", "D": "X", "A": "2"})

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
    ]

    raw_combo_list = []
    for combo_label, combo_cond, combo_type in combo_defs:
        combo_hit = int(combo_cond.sum())
        combo_raw = float(combo_cond.mean())
        combo_conf = min(combo_raw * guven_carpani * combo_bias, 0.99)
        combo_conf, combo_fake_drop = fake_confidence_duzelt(combo_conf, sample, float(tolerans))

        if combo_type == "oukg":
            gerekli_raw = 0.30 if match_type != "Sürpriz Açık" else 0.27
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

    htft_counts = htft_series.value_counts(normalize=True)
    for htft_label, htft_raw_prob in htft_counts.items():
        htft_hit = int((htft_series == htft_label).sum())
        htft_conf = min(float(htft_raw_prob) * guven_carpani * combo_bias, 0.99)
        htft_conf, htft_fake_drop = fake_confidence_duzelt(htft_conf, sample, float(tolerans))
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

    flip_p = float((((b["HTR"] == "H") & (b["FTR"] == "A")) | ((b["HTR"] == "A") & (b["FTR"] == "H"))).mean())

    risk_l, risk_cls = risk_seviyesi(ana_p, flip_p)
    eg, dg = tahmini_skor(b, ms_mod)
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

    return {
        "ana_label": ana_label,
        "ana_p": ana_p,
        "playable_score": playable_score,
        "ana_raw_p": ana_raw_p,
        "ana_odd": ana_odd,
        "alt_label": alt_label,
        "alt_p": alt_p,
        "kg_label": kg_label,
        "kg_p": int(round(kg_raw * guven_carpani * 100)),
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
        "ms_side": ms_side,
        "ms_p": int(round(ms_raw * guven_carpani * ms_bias * 100)),
        "ms_mod": ms_mod,
        "ms1_p": int(round(ms1_raw * guven_carpani * ms_bias * 100)),
        "msx_p": int(round(msx_raw * guven_carpani * ms_bias * 100)),
        "ms2_p": int(round(ms2_raw * guven_carpani * ms_bias * 100)),
        "ms25_p": int(round(ms25_raw * guven_carpani * goal_bias * 100)),
        "ms25a_p": int(round((1 - ms25_raw) * guven_carpani * goal_bias * 100)),
        "ms15_p": int(round(ms15_raw * guven_carpani * goal_bias * 100)),
        "ms35_p": int(round(ms35_raw * guven_carpani * goal_bias * 100)),
        "kg_var_p": int(round(kg_raw * guven_carpani * goal_bias * 100)),
        "kg_yok_p": int(round((1 - kg_raw) * guven_carpani * goal_bias * 100)),
        "iy05_p": int(round(iy05_raw * guven_carpani * goal_bias * 100)),
        "iy05a_p": int(round((1 - iy05_raw) * guven_carpani * goal_bias * 100)),
        "iy15_p": int(round(iy15_raw * guven_carpani * goal_bias * 100)),
        "iy1_p": int(round(float(iy_vc.get("H", 0)) * guven_carpani * 100)),
        "iyx_p": int(round(float(iy_vc.get("D", 0)) * guven_carpani * 100)),
        "iy2_p": int(round(float(iy_vc.get("A", 0)) * guven_carpani * 100)),
        "htft_mod": htft_mod,
        "htft_p": int(round(htft_raw * guven_carpani * combo_bias * 100)),
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
        "goal_profile": goal_profile,
        "match_type": match_type,
        "nedenler": nedenler,
        "oynanabilir": oynanabilir,
        "oynanabilir_esik_ok": (ana_p >= 55),
        "fake_drop": fake_drop,
        "score": score,
        "stability_tols": [],
        "stability_count": 0,
        "stability_text": "",
        "stability_early_tols": [],
        "stability_late_tols": [],
        "stability_early_text": "",
        "stability_late_text": "",
    }, b.sort_values("Date", ascending=False)



for key, default in [
    ("final_list", []),
    ("detay_idx", None),
    ("filtre", "tumu"),
    ("kupona", []),
    ("coupon_popup_open", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

FUTBOL_LIGLERI = {
    "AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league",
    },
    "TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
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
    },
    "DÜNYA VALUE": {
        "MLS": "soccer_usa_mls",
        "Brezilya Serie A": "soccer_brazil_campeonato",
        "Arjantin Primera": "soccer_argentina_primera_division",
        "Japonya J League": "soccer_japan_j_league",
        "Meksika Liga MX": "soccer_mexico_ligamx",
        "Güney Kore K League 1": "soccer_korea_kleague1",
        "Şili Primera": "soccer_chile_campeonato",
    },
}


LEAGUE_EMOJIS = {
    "Şampiyonlar Ligi": "🏆",
    "Avrupa Ligi": "🟠",
    "Konferans Ligi": "🟢",
    "Süper Lig": "🇹🇷",
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


KARLI_LIG_PRESETLERI = {
    "cekirdek": [
        "soccer_epl",
        "soccer_efl_champ",
        "soccer_spain_la_liga",
        "soccer_spain_segunda_division",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_germany_bundesliga2",
        "soccer_france_ligue_one",
        "soccer_turkey_super_league",
        "soccer_netherlands_eredivisie",
        "soccer_norway_eliteserien",
        "soccer_usa_mls",
        "soccer_switzerland_superleague",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_uefa_europa_conference_league",
    ],
    "value": [
        "soccer_portugal_primeira_liga",
        "soccer_belgium_first_div",
        "soccer_austria_bundesliga",
        "soccer_denmark_superliga",
        "soccer_sweden_allsvenskan",
        "soccer_finland_veikkausliiga",
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
    if secim == "Cumartesi":
        return sonraki_hafta_gunu(bugun_tarih, 5)
    if secim == "Pazar":
        return sonraki_hafta_gunu(bugun_tarih, 6)
    return ozel_tarih


def mac_canli_durumu(mac_zamani):
    now = datetime.now()
    if now < mac_zamani:
        return "Başlamamış"
    if now <= mac_zamani + timedelta(hours=2, minutes=15):
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
bugun = datetime.now().date()
st.markdown('<div class="api-navy">', unsafe_allow_html=True)
with st.expander("🔑 API Ayarları", expanded=False):
    API_KEY = st.text_input("The Odds API Key", type="password", help="The Odds API anahtarını gir.")
st.markdown('</div>', unsafe_allow_html=True)

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
</style>
""", unsafe_allow_html=True)

def selected_league_codes():
    return [lig['kod'] for lig in tum_lig_listesi() if st.session_state.get(f"cb_{lig['kod']}", False)]

if 'date_mode' not in st.session_state:
    st.session_state['date_mode'] = 'Bugün'
if 'special_date' not in st.session_state:
    st.session_state['special_date'] = bugun

st.markdown("""
<div class="top-shell">
  <div class="brand-row">
    <div class="brand-title">
      <div class="brand-logo">⚡</div>
      <div class="brand-text">VIBE <span>PRO</span> EXPERT</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

bar1, bar2, bar3, bar4, bar5, bar6 = st.columns([2.6, 2.0, 1.4, 1.8, 1.8, 2.1], gap='small')

with bar1:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Tarih ve Lig Seçimi</div>', unsafe_allow_html=True)
    secili_tarih = tarih_secimine_gore_date(
        st.session_state.get('date_mode', 'Bugün'),
        bugun,
        st.session_state.get('special_date', bugun)
    )
    popover_title = f"⚽ Tarih ve Lig Seçimi · {len(selected_league_codes())} lig seçili · {format_tr_date(secili_tarih)}"
    with st.popover(popover_title, use_container_width=True):
        left_col, right_col = st.columns([1.0, 3.2], gap='medium')
        with left_col:
            st.markdown('<div class="pop-title">Tarih Seçimi</div>', unsafe_allow_html=True)
            date_mode = st.radio(
                'Tarih modu',
                options=['Bugün', 'Yarın', 'Cumartesi', 'Pazar', 'Özel Tarih'],
                index=['Bugün', 'Yarın', 'Cumartesi', 'Pazar', 'Özel Tarih'].index(st.session_state.get('date_mode', 'Bugün')),
                key='date_mode',
                label_visibility='collapsed'
            )
            if date_mode == 'Özel Tarih':
                st.date_input('Özel tarih', value=st.session_state.get('special_date', bugun), key='special_date')

            st.markdown('<div class="pop-title" style="margin-top:18px">Hızlı Filtreler</div>', unsafe_allow_html=True)
            if st.button('⭐ Kararlı Çekirdek', use_container_width=True, key='preset_core_top'):
                toggle_leagues(KARLI_LIG_PRESETLERI['cekirdek'])
                st.rerun()
            if st.button('💎 Karlı / Value', use_container_width=True, key='preset_val_top'):
                toggle_leagues(KARLI_LIG_PRESETLERI['value'])
                st.rerun()
            if st.button('🌍 Hepsini Aç', use_container_width=True, key='preset_all_top'):
                set_leagues(tum_lig_kodlari())
                st.rerun()
            if st.button('🧹 Temizle', use_container_width=True, key='preset_clear_top'):
                clear_leagues()
                st.rerun()

        with right_col:
            st.markdown('<div class="pop-title">Lig Seçimi</div>', unsafe_allow_html=True)
            lig_arama = st.text_input('Lig ara', placeholder='örn. Premier, Türkiye, MLS', key='lig_arama_popover', label_visibility='collapsed')
            filtreli_ligler = filtrelenmis_lig_listesi(lig_arama)
            st.markdown(f"<div class='league-chip-note'>Gösterilen lig: <b>{len(filtreli_ligler)}</b></div>", unsafe_allow_html=True)
            lig_box = st.container(height=360, border=True)
            with lig_box:
                lcol1, lcol2 = st.columns(2)
                for i, lig in enumerate(filtreli_ligler):
                    hedef_col = lcol1 if i % 2 == 0 else lcol2
                    with hedef_col:
                        st.checkbox(lig['label'], key=f"cb_{lig['kod']}")
            st.markdown(f"<div style='font-size:0.9rem;color:#ffd24a;font-weight:700;margin-top:8px'>{len(selected_league_codes())} lig seçili</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with bar2:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Sezonlar</div>', unsafe_allow_html=True)
    yillar = st.multiselect(
        'Sezonlar',
        options=['2122', '2223', '2324', '2425', '2526'],
        default=['2324', '2425', '2526'],
        label_visibility='collapsed',
        key='top_seasons'
    )
    st.markdown('</div>', unsafe_allow_html=True)

with bar3:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Min. Örnek Sayısı</div>', unsafe_allow_html=True)
    min_ornek = st.number_input('Min. Örnek Sayısı', min_value=1, value=1, label_visibility='collapsed', key='top_min_ornek')
    st.markdown('</div>', unsafe_allow_html=True)

with bar4:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Oran Hassasiyeti</div>', unsafe_allow_html=True)
    TOLERANS = st.slider('Oran Hassasiyeti', 0.00, 0.30, 0.08, step=0.01, label_visibility='collapsed', key='top_tol')
    st.markdown(f"<div style='margin-top:-6px;color:#ffd24a;font-weight:700'>{TOLERANS:.2f}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with bar5:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Oynanılabilir / Canlı</div>', unsafe_allow_html=True)
    oynanabilir_esik = st.selectbox(
        'Oynanılabilir eşik',
        options=[0, 55, 60, 65, 70, 75],
        index=2,
        format_func=lambda x: 'Tümü' if x == 0 else f'Güven ≥ %{x}',
        label_visibility='collapsed',
        key='oynanabilir_esik'
    )
    canli_filtre = st.selectbox(
        'Canlı filtre',
        options=['Tümü', 'Canlı', 'Başlamamış', 'Bitti'],
        index=0,
        label_visibility='collapsed',
        key='canli_filtre'
    )
    st.markdown('</div>', unsafe_allow_html=True)

secili_kodlar = selected_league_codes()
with bar6:
    st.markdown('<div class="control-card">', unsafe_allow_html=True)
    st.markdown('<div class="control-label">Analiz</div>', unsafe_allow_html=True)
    analiz_btn = st.button('▶ ANALİZİ BAŞLAT', use_container_width=True, type='primary', key='analiz_baslat_btn')
    if st.button('🎫 Kuponlarım', use_container_width=True, key='toggle_coupon_popup'):
        st.session_state.coupon_popup_open = not st.session_state.coupon_popup_open
        st.rerun()
    if 'son_analiz' in st.session_state:
        st.markdown(
            f"<div class='summary-note'>Son analiz: {st.session_state.son_analiz}<br>Toplam maç: {st.session_state.get('toplam_mac',0)}</div>",
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

rehber = tolerans_rehberi(TOLERANS)
st.markdown(f"""
<div class="helper-bar">
  <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center">
    <div style="font-size:0.72rem;color:#8ea2c7;letter-spacing:1px;text-transform:uppercase">Tolerans Rehberi</div>
    <div style="font-size:0.88rem;color:#fff">Önerilen tolerans: <b>{rehber['onerilen_tolerans']}</b></div>
    <div style="font-size:0.88rem;color:#c7cfdd">Dinamik min maç: <b>{rehber['onerilen_min_mac']}</b></div>
    <div style="font-size:0.84rem;color:#8fa0ba">{rehber['yorum']}</div>
  </div>
</div>
""", unsafe_allow_html=True)

if analiz_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("📊 Veriler çekiliyor ve analiz ediliyor..."):
            gecmis = futbol_veri_motoru(tuple(yillar))
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        final = []
        stability_tols = [0.00, 0.03, 0.05, 0.08, 0.10]
        if not bulten.empty and not gecmis.empty:
            for _, m in bulten.iterrows():
                t, b_det = hesapla(gecmis, m, TOLERANS)
                if t is None:
                    continue
                if len(b_det) < min_ornek:
                    continue

                stable_hits = []
                for stab_tol in stability_tols:
                    stab_t, stab_b = hesapla(gecmis, m, stab_tol)
                    if stab_t is None:
                        continue
                    if (
                        stab_t["ana_label"] == t["ana_label"]
                        and stab_t["ana_label"] not in ["Belirsiz Maç", "Tahmin Zayıf"]
                        and stab_t["ornek"] >= max(min_ornek, stab_t["onerilen_min_mac"])
                    ):
                        stable_hits.append(f"{stab_tol:.2f}")

                t["stability_tols"] = stable_hits
                t["stability_count"] = len(stable_hits)
                t["stability_text"] = " · ".join(stable_hits)
                early_hits = [x for x in stable_hits if float(x) <= 0.05]
                normal_hits = [x for x in stable_hits if float(x) > 0.05]
                t["stability_early_tols"] = early_hits
                t["stability_late_tols"] = normal_hits
                t["stability_early_text"] = " · ".join(early_hits)
                t["stability_late_text"] = " · ".join(normal_hits)

                t["score"] = round(
                    t["score"]
                    + min(7, t["stability_count"] * 1.4)
                    + min(4, len(early_hits) * 1.4)
                    + (2 if f"{TOLERANS:.2f}" in stable_hits else 0),
                    1
                )
                t["playable_score"] = round(
                    t.get("playable_score", t.get("ana_p", 0))
                    + min(5, t["stability_count"] * 1.0)
                    + min(4, len(early_hits) * 1.2),
                    1
                )

                if oynanabilir_esik and t.get("ana_p", 0) < oynanabilir_esik:
                    continue
                m_dict = m.to_dict()
                m_dict["durum"] = mac_canli_durumu(m_dict["zaman"])
                final.append({"m": m_dict, "t": t, "b": b_det})

        final = sorted(final, key=lambda x: (x["t"].get("score", 0), x["t"].get("ana_p", 0), x["t"].get("ornek", 0)), reverse=True)
        final = sorted(
            final,
            key=lambda x: (
                x["t"].get("playable_score", 0),
                x["t"].get("ana_p", 0),
                x["t"].get("score", 0),
                x["t"].get("ornek", 0),
            ),
            reverse=True,
        )
        st.session_state.final_list = final
        st.session_state.detay_idx = None
        st.session_state.son_analiz = datetime.now().strftime("%d/%m/%Y %H:%M")
        st.session_state.toplam_mac = len(final)
        st.rerun()

if st.session_state.detay_idx is not None:
    idx = st.session_state.detay_idx
    item = st.session_state.final_list[idx]
    m, t, b_det = item["m"], item["t"], item["b"]

    durum_color, durum_text = mac_durum_badge(m["zaman"])

    if st.button("← Geri", key="geri_btn"):
        st.session_state.detay_idx = None
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
        {"<div style='margin-top:8px;font-size:0.76rem;color:#ff8b8b'>⚠️ Model bu maçı net ayıramadı</div>" if t.get("belirsiz") else ""}
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

          <div class="risk-row">
            <span class="rk">RİSK SEVİYESİ</span>
            <span class="risk-pill {t['risk_cls']}">{t['risk_label']}</span>
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

    neden_html = "".join([f'<div class="neden-item">• {x}</div>' for x in t["nedenler"]])
    st.markdown(f"""
    <div class="neden-kart" style="margin-bottom:14px">
      <div class="tk-title">NEDEN BU TAHMİN?</div>
      {neden_html}
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:16px 22px;margin-bottom:0">
      <div class="tk-title" style="margin-bottom:4px">Benzer Oranlı Geçmiş Maçlar (Son {min(len(b_det), 10)})</div>
      <div style="font-size:0.72rem;color:#666">ℹ️ Tablodaki maçlar seçili oran aralığına (±{t['kullanilan_tolerans']:.2f}) en yakın bulunan benzer maçlardır.</div>
    </div>
    """, unsafe_allow_html=True)

    bd = b_det.head(10)
    dt = pd.DataFrame()
    dt["Tarih"] = bd["Date"].dt.strftime("%d.%m.%Y")
    dt["Ev Sahibi"] = bd["HomeTeam"]
    dt["Deplasman"] = bd["AwayTeam"]
    dt["İY Sonuç"] = bd["HTHG"].astype(int).astype(str) + "-" + bd["HTAG"].astype(int).astype(str)
    dt["MS Sonuç"] = bd["FTHG"].astype(int).astype(str) + "-" + bd["FTAG"].astype(int).astype(str)
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
    )

    st.stop()

fl = st.session_state.final_list

hc1, hc2 = st.columns([6, 1])
with hc1:
    st.markdown(f"""
    <div class="top-header">
      <div>
        <h2>ANA MAÇ EKRANI</h2>
        <div class="sub">{format_tr_date(secili_tarih)}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="top-filters">
      <div class="tf-chip">📅 Kartlı görünüm</div>
      <div class="tf-chip">🎯 Detaylı tahmin ekranı</div>
      <div class="tf-chip">🔥 Smart filter</div>
    </div>
    """, unsafe_allow_html=True)

with hc2:
    if fl:
        st.markdown(f"""<div class="mac-badge" style="margin-top:8px">{len(fl)}<span>MAÇ BULUNDU</span></div>""", unsafe_allow_html=True)

if not fl:
    st.markdown("""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:42px;text-align:center;margin-top:20px">
      <div style="font-size:2rem;margin-bottom:12px">⚡</div>
      <div style="font-family:Rajdhani,sans-serif;font-size:1.35rem;color:#fff;font-weight:700">Analizi Başlatın</div>
      <div style="font-size:0.9rem;color:#666;margin-top:6px">API ayarlarını açıp anahtarını gir, sonra üst bardan tarih ve lig seçip ANALİZİ BAŞLAT butonuna bas.</div>
    </div>
    """, unsafe_allow_html=True)
else:
    indexed_fl = list(enumerate(fl))
    yuksek = [(idx, x) for idx, x in indexed_fl if x["t"]["ana_p"] >= 70]
    orta = [(idx, x) for idx, x in indexed_fl if 55 <= x["t"]["ana_p"] < 70]
    kombolu = [(idx, x) for idx, x in indexed_fl if x["t"].get("combo_var", False)]

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

    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("🏆 Günün En Favori 3'lü Kuponu", use_container_width=True, key="top3_bestfav_btn"):
            st.session_state.kupona = build_top3_coupon(indexed_fl, mode="best_favorites")
            st.rerun()
    with cc2:
        if st.button("🎯 Günün En Yüksek Oranlı 3 Favorisi", use_container_width=True, key="top3_highfav_btn"):
            st.session_state.kupona = build_top3_coupon(indexed_fl, mode="high_favorites")
            st.rerun()

    filtre = st.session_state.filtre
    if filtre == "yuksek":
        goster = sorted(yuksek, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    elif filtre == "orta":
        goster = sorted(orta, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    elif filtre == "kombo":
        goster = sorted(kombolu, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    else:
        goster = indexed_fl

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div class="list-heading">⚡ ANLIK MAÇ TAHMİNLERİ</div>
    
    """, unsafe_allow_html=True)

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
        durum_bg, durum_lbl = mac_durum_badge(m["zaman"])
        belirsiz_html = '<div class="mk-mini" style="color:#ff8b8b">⚠️ Belirsiz maç</div>' if t.get("belirsiz") else ''
        combo_html = ''
        if combo_text:
            combo_level = t.get("combo_level", "")
            level_text = f' · {combo_level}' if combo_level else ''
            combo_html = f'<div style="margin-top:8px"><div class="mk-label">GÜÇLÜ KOMBO{level_text}</div><span class="combo-pill">{combo_text}</span></div>'
        stability_html = ""
        if t.get("stability_early_text"):
            stability_html += f'<div style="margin-top:4px;font-size:0.70rem;color:#ffb366">🎯 Dar stabil: {t.get("stability_early_text", "")}</div>'
        if t.get("stability_late_text"):
            stability_html += f'<div style="margin-top:4px;font-size:0.70rem;color:#7fb3ff">🎯 Stabil: {t.get("stability_late_text", "")}</div>'
        if not stability_html:
            stability_html = f'<div style="margin-top:4px;font-size:0.70rem;color:#7fb3ff">🎯 Stabil: {t.get("stability_text", "-")}</div>'

        alt_html = f'<span class="alt-pill">{t["alt_label"]}</span>' if t.get("alt_label") else '<span style="font-size:0.78rem;color:#6f7990">—</span>'

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
              </div>

              <div>
                <div class="mk-label">ANA TAHMİN</div>
                <span class="ana-pill {pill_cls}">{t['ana_label']}</span>
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
                <div style="margin-top:8px;font-size:0.72rem;color:#666">🏅 {t.get('playable_score', t['ana_p'])} puan · 📊 {int(t['ornek'])} örnek · {t.get('ornek_durum', 'Standart')}</div>
                <div style="margin-top:6px;font-size:0.72rem;color:#f6b26b">🏅 {t.get('score', 0):.1f} puan</div>
                {stability_html}
              </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
        with bc:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            if st.button("Detay →", key=f"d_{real_i}_{i}", use_container_width=True):
                st.session_state.detay_idx = real_i
                st.rerun()
            if st.button("+ Kupona", key=f"k_{real_i}_{i}", use_container_width=True):
                coupon_item = {
                    "ev": m["ev"],
                    "dep": m["dep"],
                    "lig": m["lig"],
                    "zaman_iso": m["zaman"].strftime("%Y-%m-%d %H:%M:%S"),
                    "zaman_text": m["zaman"].strftime("%d.%m %H:%M"),
                    "tahmin": t["ana_label"],
                    "guven": int(t["ana_p"]),
                }
                mevcutlar = {(x["ev"], x["dep"], x["tahmin"]) for x in st.session_state.kupona}
                if (coupon_item["ev"], coupon_item["dep"], coupon_item["tahmin"]) not in mevcutlar:
                    st.session_state.kupona.append(coupon_item)
                    st.session_state.coupon_popup_open = True
                st.rerun()

    if st.session_state.coupon_popup_open:
        if st.session_state.kupona:
            items_html = ""
            normalized_kupona = []
            for k in st.session_state.kupona:
                if isinstance(k, dict):
                    item = k
                else:
                    raw_text = str(k)
                    item = {
                        "ev": raw_text,
                        "dep": "",
                        "lig": "-",
                        "zaman_iso": "",
                        "zaman_text": "-",
                        "tahmin": "-",
                        "guven": 0,
                    }
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
                mac_dt = parse_mac_datetime(item.get("zaman_iso", ""))
                durum = mac_canli_durumu(mac_dt) if item.get("zaman_iso") else "Takipte"
                renk = "#16a34a" if durum == "Canlı" else "#2563eb" if durum in ["Başlamamış", "Takipte"] else "#64748b"
                mac_ad = f"{item.get('ev', '')} - {item.get('dep', '')}".strip(" -")
                alt_satir = f"{item.get('lig', '-')} | {item.get('zaman_text', '-')} | {item.get('tahmin', '-')} | Güven %{int(item.get('guven', 0))}" if item.get("guven", 0) else f"{item.get('lig', '-')} | {item.get('zaman_text', '-')} | {item.get('tahmin', '-')}"
                items_html += f"<div class='coupon-item'><div class='coupon-item-top'><span>{mac_ad}</span><span class='live-badge' style='background:{renk};color:white'>{durum}</span></div><div class='coupon-item-sub'>{alt_satir}</div></div>"
            st.session_state.kupona = normalized_kupona
            st.markdown(f"""
            <div class="floating-coupon">
              <div class="floating-coupon-title">🎫 Kuponlarım</div>
              <div class="floating-coupon-sub">Kaydettiğin maçları burada takip edebilirsin.</div>
              {items_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="floating-coupon">
              <div class="floating-coupon-title">🎫 Kuponlarım</div>
              <div class="floating-coupon-sub">Henüz kupona maç eklemedin.</div>
            </div>
            """, unsafe_allow_html=True)

        cp1, cp2 = st.columns([8, 2])
        with cp2:
            if st.button("Popup Kapat", key="kupon_popup_kapat_btn", use_container_width=True):
                st.session_state.coupon_popup_open = False
                st.rerun()
            if st.session_state.kupona and st.button("Kuponu Temizle", key="kupon_temizle_btn", use_container_width=True):
                st.session_state.kupona = []
                st.rerun()
