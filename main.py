
import io
import math
from datetime import datetime, timedelta
from html import escape

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

APP_SCHEMA_VERSION = 17
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


def pct100(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:
        return 0


def skoru_tahmine_uydur(eg, dg, ana_label, ms_mod):
    ana = str(ana_label)
    ms_mod = str(ms_mod)

    # Öncelik ana tahmin: Alt / Üst / KG.
    # Böylece ana tahmin 2.5 Alt iken skor 1-2 gibi çelişkili çıkmaz.
    if "2.5 Alt" in ana:
        if ms_mod == "H":
            return 1, 0
        elif ms_mod == "A":
            return 0, 1
        else:
            return 1, 1

    if "2.5 Üst" in ana:
        if ms_mod == "H":
            return 2, 1
        elif ms_mod == "A":
            return 1, 2
        else:
            return 2, 2

    if ana == "KG Yok":
        if ms_mod == "H":
            return 2, 0
        elif ms_mod == "A":
            return 0, 2
        else:
            return 0, 0

    if ana == "KG Var":
        if ms_mod == "H":
            return 2, 1
        elif ms_mod == "A":
            return 1, 2
        else:
            return 1, 1

    eg = int(eg)
    dg = int(dg)

    if ana == "MS 1" and eg <= dg:
        eg = dg + 1
    elif ana == "MS 2" and dg <= eg:
        dg = eg + 1
    elif ana == "Beraberlik":
        mx = max(eg, dg, 1)
        eg = dg = mx

    return eg, dg


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




# ==========================================================
# AI GUNLUK TARAMA + AUTO KUPON BUILDER + KASA PLANI
# ==========================================================

def global_ai_tarama(b_df, maclar, limit=120):
    """
    Tüm maçları 0.00 - 0.30 arası çoklu oran hassasiyetiyle tek seferde tarar.
    Ana AI seçim/kupon/top10 sadece 0.00 / 0.02 / 0.04 / 0.06 / 0.08 / 0.10 bandından yapılır.
    0.12 - 0.30 sonuçları arka plan ve Excel/diagnostic için tutulur.
    Tolerans büyüdükçe güven ve playable_score bilinçli düşürülür.
    0.00 toleransta minimum 3 örnek yeterlidir; 3-4 örnekte sahte güven kırılır.
    """
    TOLERANSLAR = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]
    ANA_TOLERANSLAR = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10]

    tol_guven_cezasi_map = {
       0.00: 0,
       0.02: 2,
       0.04: 4,
       0.06: 6,
       0.08: 9,
       0.10: 12,
       0.12: 16,
       0.15: 20,
       0.20: 28,
       0.25: 35,
       0.30: 45,
    }
 
    tum_sonuclar = []

    if b_df is None or maclar is None:
        return []
    if getattr(b_df, "empty", True) or getattr(maclar, "empty", True):
        return []

    for _, m in maclar.iterrows():
        en_iyi = None
        tolerans_sonuclari = []

        for tol in TOLERANSLAR:
            try:
                t, b_det = hesapla(b_df, m, tol)
            except Exception:
                continue

            if not t or t.get("belirsiz"):
                continue
            if t.get("ana_odd") is None:
                continue

            t = t.copy()
            sample = int(t.get("ornek", 0) or 0)

            # 0.00 sniper tolerans: 3 örnek yeterli, ama 3-4 örnekte güven kırılır.
            if round(float(tol), 2) == 0.00:
                if sample < 3:
                    continue
                if sample == 3:
                    t["ana_p"] = max(1, int(t.get("ana_p", 0) - 8))
                    t["playable_score"] = max(1, float(t.get("playable_score", 0)) - 8)
                elif sample == 4:
                    t["ana_p"] = max(1, int(t.get("ana_p", 0) - 4))
                    t["playable_score"] = max(1, float(t.get("playable_score", 0)) - 4)
                if int(t.get("ana_p", 0)) > 85 and sample == 3:
                    t["ana_p"] = max(1, int(t.get("ana_p", 0) - 10))

            # Tolerans büyüdükçe güven kademeli düşsün.
            tol_key = round(float(tol), 2)
            tol_ceza = tol_guven_cezasi_map.get(tol_key, 20)
            if tol_ceza:
                t["ana_p"] = max(1, int(t.get("ana_p", 0) - tol_ceza))
                t["playable_score"] = max(1, float(t.get("playable_score", 0)) - tol_ceza)
            # Düşük tolerans bonusu
            if tol_key <= 0.04:
                t["ana_p"] = min(100, int(t.get("ana_p", 0) + 3))
                t["playable_score"] = min(100, float(t.get("playable_score", 0)) + 3)
            elif tol_key <= 0.06:
                t["ana_p"] = min(100, int(t.get("ana_p", 0) + 1))
                t["playable_score"] = min(100, float(t.get("playable_score", 0)) + 1)
    
            # Ceza sonrası temel kalite filtresi.
            if t.get("ana_p", 0) < 52:
                continue
            if sample < 1:
                continue
            if t.get("risk_label") == "YÜKSEK" and t.get("ana_p", 0) < 64:
                continue

            stabil_bonus = 0
            for stab_tol in TOLERANSLAR:
                try:
                    st_t, _ = hesapla(b_df, m, stab_tol)
                    if (
                        st_t
                        and st_t.get("ana_label") == t.get("ana_label")
                        and st_t.get("ornek", 0) >= st_t.get("onerilen_min_mac", 1)
                    ):
                        stabil_bonus += 1
                except Exception:
                    pass

            # 0.00-0.05 ana bölgeye küçük ödül, 0.10'a küçük ceza.
            tol_bonus = 0
            if tol_key == 0.00:
                tol_bonus = 4
            elif tol_key <= 0.05:
                tol_bonus = 3
            elif tol_key <= 0.08:
                tol_bonus = 1
            elif tol_key == 0.10:
                tol_bonus = -2
            else:
                tol_bonus = -8

            ai_skor = (
                float(t.get("playable_score", 0))
                + float(t.get("ana_p", 0)) * 0.20
                + min(float(sample), 30) * 0.15
                + stabil_bonus * 1.6
                + tol_bonus
                - (6 if t.get("fake_drop") else 0)
                - (5 if t.get("risk_label") == "YÜKSEK" else 0)
            )

            sonuc = {
                "tolerans": tol,
                "t": t,
                "b": b_det,
                "ai_skor": round(ai_skor, 1),
                "stabil_bonus": stabil_bonus,
            }
            tolerans_sonuclari.append(sonuc)

            # Ana seçim yalnızca 0.00 / 0.02 / 0.04 / 0.06 / 0.08 / 0.10 içinden yapılsın.
            if tol in ANA_TOLERANSLAR and (en_iyi is None or ai_skor > en_iyi["ai_skor"]):
                m_dict = m.to_dict()
                m_dict["durum"] = mac_canli_durumu(m_dict.get("zaman"))
                en_iyi = {
                    "mac": m_dict,
                    "t": t,
                    "b": b_det,
                    "tolerans": tol,
                    "ai_skor": round(ai_skor, 1),
                    "stabil_bonus": stabil_bonus,
                    "tum_toleranslar": [],
                }

        if en_iyi:
            en_iyi["tum_toleranslar"] = tolerans_sonuclari
            tum_sonuclar.append(en_iyi)

    tum_sonuclar.sort(key=lambda x: x.get("ai_skor", 0), reverse=True)
    return tum_sonuclar[:limit]

def ai_sonuclari_excel_buffer(ai_sonuclar, paketler=None):
    rows = []

    for item in ai_sonuclar or []:
        m = item.get("mac", {})
        t = item.get("t", {})
        z = m.get("zaman")

        rows.append({
            "Tarih": z.strftime("%Y-%m-%d %H:%M") if hasattr(z, "strftime") else str(z),
            "Lig": m.get("lig", ""),
            "Ev": m.get("ev", ""),
            "Dep": m.get("dep", ""),
            "Tolerans": item.get("tolerans"),
            "Ana Tahmin": t.get("ana_label", ""),
            "Oran": t.get("ana_odd", ""),
            "Güven %": t.get("ana_p", ""),
            "AI Skor": item.get("ai_skor", ""),
            "Risk": t.get("risk_label", ""),
            "Oynanabilir": t.get("oynanabilir", ""),
            "Örnek Sayısı": t.get("ornek", ""),
            "Tahmini Skor": f"{t.get('eg','')}-{t.get('dg','')}",
            "Maç Tipi": t.get("match_type", ""),
            "Gol Profili": t.get("goal_profile", ""),
            "Kombo": t.get("combo_label", ""),
            "Kombo Güven": t.get("combo_p", ""),
        })

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Tüm Maçlar", index=False)

        if not df.empty:
            oynanabilir_df = df[df["Oynanabilir"] == True]
            oynanabilir_df.to_excel(writer, sheet_name="Oynanabilir", index=False)
            df.sort_values("AI Skor", ascending=False).head(10).to_excel(writer, sheet_name="AI Top 10", index=False)

        if paketler:
            for key, sheet_name in [
                ("guvenli", "Güvenli Yol"),
                ("value", "Oynanılabilir Yol"),
                ("agresif", "Agresif Yol"),
            ]:
                kupon, toplam_oran = paketler.get(key, ([], 1.0))
                k_rows = []
                for item in kupon:
                    m = item.get("mac", {})
                    t = item.get("t", {})
                    k_rows.append({
                        "Lig": m.get("lig", ""),
                        "Maç": f"{m.get('ev','')} - {m.get('dep','')}",
                        "Tahmin": item.get("pick_label", t.get("ana_label", "")),
                        "Oran": item.get("oran", ""),
                        "Güven": item.get("pick_guven", t.get("ana_p", "")),
                        "Risk": t.get("risk_label", ""),
                        "Tolerans": item.get("tolerans", ""),
                        "AI Skor": item.get("final_skor", ""),
                        "Toplam Oran": toplam_oran,
                    })
                pd.DataFrame(k_rows).to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)
    return buffer





def top10_market_cesitli(ai_sonuclar, limit=None):
    """
    0.00 - 0.10 arası TÜM uygun maçları getirir.
    Limit yok, market kotası yok, lig kotası yok.
    MS / Alt-Üst / KG / Kombo adayları içinden her maç için en iyi market seçilir.
    """
    ANA_TOLERANSLAR = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10]

    def tol_float(item):
        try:
            return round(float(item.get("tolerans", 0)), 2)
        except Exception:
            return 0.30

    def market_turu(label):
        label = str(label or "")
        if label.startswith("MS") or label == "Beraberlik":
            return "MS"
        if "2.5" in label or "3.5" in label or "1.5" in label or "Alt" in label or "Üst" in label:
            return "Alt/Üst"
        if "KG" in label:
            return "KG"
        if "HT/FT" in label or "/" in label:
            return "Kombo"
        return "Diğer"

    def tol_bonus(tol):
        # 0.00 iyi, 0.05 denge, 0.10 normal.
        if tol == 0.00:
            return 15
        if tol <= 0.02:
            return 12
        if tol <= 0.04:
            return 9
        if tol <= 0.06:
            return 5
        if tol <= 0.08:
            return 1
        return -5

    adaylar = []

    for item in ai_sonuclar or []:
        tol = tol_float(item)

        # Sadece 0.00 - 0.10 aralığı
        if tol not in ANA_TOLERANSLAR or tol > 0.10:
            continue

        t = item.get("t", {})
        marketler = []

        # Ana market
        if t.get("ana_label"):
            marketler.append({
                "label": t.get("ana_label"),
                "guven": int(t.get("ana_p", 0) or 0),
                "oran": t.get("ana_odd"),
                "tip": "Ana",
                "ek_bonus": 0,
            })

        # Alt/Üst marketi
        if t.get("alt_label") and int(t.get("alt_p", 0) or 0) >= 58:
            marketler.append({
                "label": t.get("alt_label"),
                "guven": int(t.get("alt_p", 0) or 0),
                "oran": None,
                "tip": "Alt/Üst",
                "ek_bonus": 10,
            })

        # KG marketi
        if t.get("kg_label") and int(t.get("kg_p", 0) or 0) >= 58:
            marketler.append({
                "label": t.get("kg_label"),
                "guven": int(t.get("kg_p", 0) or 0),
                "oran": None,
                "tip": "KG",
                "ek_bonus": 9,
            })

        # Kombo marketi
        if t.get("combo_label") and int(t.get("combo_p", 0) or 0) >= 45:
            marketler.append({
                "label": t.get("combo_label"),
                "guven": int(t.get("combo_p", 0) or 0),
                "oran": kombo_tahmini_oran(t.get("combo_label"), t.get("ana_odd")),
                "tip": "Kombo",
                "ek_bonus": 5,
            })

        if not marketler:
            continue

        # Her maçtan en iyi marketi seç
        en_iyi_mk = None
        en_iyi_skor = -9999

        for mk in marketler:
            label = mk.get("label")
            guven = int(mk.get("guven", 0) or 0)

            if not label or label in ["Tahmin Zayıf", "Belirsiz Maç"]:
                continue

            if mk.get("tip") == "Ana" and guven < 52:
                continue

            if mk.get("tip") != "Ana" and guven < 58:
                continue

            skor = (
                float(item.get("ai_skor", 0) or 0)
                + guven * 0.35
                + tol_bonus(tol)
                + mk.get("ek_bonus", 0)
            )

            if skor > en_iyi_skor:
                en_iyi_skor = skor
                en_iyi_mk = mk

        if not en_iyi_mk:
            continue

        yeni = item.copy()
        yeni["top10_label"] = en_iyi_mk.get("label")
        yeni["top10_guven"] = int(en_iyi_mk.get("guven", 0) or 0)
        yeni["top10_oran"] = en_iyi_mk.get("oran") if en_iyi_mk.get("oran") is not None else t.get("ana_odd")
        yeni["top10_tip"] = en_iyi_mk.get("tip", "Ana")
        yeni["top10_market_turu"] = market_turu(en_iyi_mk.get("label"))
        yeni["top10_skor"] = round(en_iyi_skor, 1)
        adaylar.append(yeni)

    adaylar.sort(key=lambda x: x.get("top10_skor", 0), reverse=True)

    return adaylar


def tolerans_label(tol):
    try:
        tol = round(float(tol), 2)
    except Exception:
        tol = 0.30

    if tol == 0.00:
        return "🔥 0.00 Ultra Net"
    if tol <= 0.04:
        return "✅ Çok İyi"
    if tol <= 0.06:
        return "⚖️ Dengeli"
    if tol <= 0.08:
        return "👍 Normal"
    if tol <= 0.10:
        return "⚠️ Geniş / Güven Düşük"
    return "❌ Sadece Arka Plan"

def ai_sonuclarini_toleransa_gore_filtrele(ai_sonuclar, secilen_tolerans):
    """AI Otomatik dışında seçilen tolerans için aynı maçların o toleranstaki sonucunu gösterir."""
    if secilen_tolerans == "AI Otomatik":
        return sorted(ai_sonuclar or [], key=lambda x: x.get("ai_skor", 0), reverse=True)

    filtreli = []
    try:
        hedef_tol = round(float(secilen_tolerans), 2)
    except Exception:
        return sorted(ai_sonuclar or [], key=lambda x: x.get("ai_skor", 0), reverse=True)

    for item in ai_sonuclar or []:
        secilen_alt = None
        for alt in item.get("tum_toleranslar", []):
            try:
                if round(float(alt.get("tolerans")), 2) == hedef_tol:
                    secilen_alt = alt
                    break
            except Exception:
                continue

        if secilen_alt:
            yeni_item = item.copy()
            yeni_item["t"] = secilen_alt.get("t", {})
            yeni_item["b"] = secilen_alt.get("b")
            yeni_item["tolerans"] = secilen_alt.get("tolerans")
            yeni_item["ai_skor"] = secilen_alt.get("ai_skor", 0)
            yeni_item["stabil_bonus"] = secilen_alt.get("stabil_bonus", 0)
            yeni_item["tum_toleranslar"] = item.get("tum_toleranslar", [])
            filtreli.append(yeni_item)

    return sorted(filtreli, key=lambda x: x.get("ai_skor", 0), reverse=True)


def kombo_tahmini_oran(label, ana_odd):
    """Combo oranı API'den gelmiyorsa agresif kupon için yaklaşık oran üretir."""
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
    return ana_odd


def agresif_pick_label(t):
    """Agresifte, tutarlı ve yeterli güvenli kombo varsa ana tahmin yerine kombo seçer."""
    combo = str(t.get("combo_label", "") or "").strip()
    combo_p = int(t.get("combo_p", 0) or 0)
    combo_hit = int(t.get("combo_hit", 0) or 0)

    if combo and combo_p >= 45 and combo_hit >= 3 and t.get("risk_label") != "YÜKSEK":
        return combo, combo_p, "combo", kombo_tahmini_oran(combo, t.get("ana_odd"))

    return t.get("ana_label", "-"), int(t.get("ana_p", 0) or 0), "ana", t.get("ana_odd")


def mac_key(m):
    return f"{m.get('ev','')}::{m.get('dep','')}::{m.get('zaman','')}"


def _toplam_oran(kupon):
    toplam = 1.0
    for item in kupon or []:
        try:
            toplam *= float(item.get("oran", 1.0) or 1.0)
        except Exception:
            toplam *= 1.0
    return round(toplam, 2)


def smart_kupon_builder(ai_sonuclar):
    """
    3 ayrı kupon üretir. Aynı maç yalnızca 1 kuponda olabilir.
    v8 mantık: Güvenli yol artık listedeki ilk uygun maçı değil, AI skoru en yüksek + risk düşük maçları seçer.
    Value oran/AI dengesi, Agresif ise yüksek oran/kombo önceliği kullanır.
    """
    used = set()

    def safe_float(v, default=0.0):
        try:
            return float(v)
        except Exception:
            return default

    def safe_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def risk_ceza(t):
        r = str(t.get("risk_label", ""))
        if r == "YÜKSEK":
            return 999
        if r == "ORTA":
            return 8
        return 0

    def base_item(item, pick_label=None, pick_guven=None, pick_type="ana", pick_odd=None, estimated=False):
        m = item.get("mac", {})
        t = item.get("t", {})
        oran = pick_odd if pick_odd is not None else t.get("ana_odd")
        oran = safe_float(oran, 1.0)
        return {
            "mac": m,
            "t": t,
            "oran": oran,
            "oran_tahmini": bool(estimated),
            "market": pick_label or t.get("ana_label", ""),
            "pick_label": pick_label or t.get("ana_label", ""),
            "pick_guven": safe_int(pick_guven if pick_guven is not None else t.get("ana_p", 0)),
            "pick_type": pick_type,
            "lig": m.get("lig", ""),
            "tolerans": item.get("tolerans"),
            "final_skor": round(safe_float(item.get("ai_skor", t.get("playable_score", 0))) + oran * 2, 1),
        }

    temiz = []
    for item in ai_sonuclar or []:
        t = item.get("t", {})
        if t.get("belirsiz") or t.get("ana_odd") is None:
            continue
        if t.get("risk_label") == "YÜKSEK":
            continue
        temiz.append(item)

    # 🟢 GÜVENLİ: AI skoru ana belirleyici. Düşük risk, yüksek güven, stabilite bonus.
    guvenli = []
    guvenli_aday = []
    for item in temiz:
        t = item.get("t", {})
        if safe_int(t.get("ana_p", 0)) < 68:
            continue
        odd = safe_float(t.get("ana_odd"), 9.0)
        score = (
            safe_float(item.get("ai_skor", 0)) * 1.00
            + safe_int(t.get("ana_p", 0)) * 0.25
            + safe_float(item.get("stabil_bonus", 0)) * 2.0
            - risk_ceza(t)
            - max(0, odd - 1.90) * 6.0
        )
        guvenli_aday.append((score, item))

    guvenli_aday.sort(key=lambda x: x[0], reverse=True)
    for _, item in guvenli_aday:
        m = item.get("mac", {})
        key = mac_key(m)
        if key in used:
            continue
        guvenli.append(base_item(item))
        used.add(key)
        if len(guvenli) >= 2:
            break

    # 🟡 VALUE: AI skoru + oran dengesi. Güvenli ile maç çakışmaz.
    value = []
    market_say = {}
    lig_say = {}
    value_aday = []
    for item in temiz:
        m, t = item.get("mac", {}), item.get("t", {})
        key = mac_key(m)
        if key in used or safe_int(t.get("ana_p", 0)) < 60:
            continue
        odd = safe_float(t.get("ana_odd"), 1.0)
        score = (
            safe_float(item.get("ai_skor", 0)) * 0.65
            + odd * 22
            + safe_int(t.get("ana_p", 0)) * 0.12
            + safe_float(item.get("stabil_bonus", 0))
            - risk_ceza(t) * 0.5
        )
        value_aday.append((score, item))

    value_aday.sort(key=lambda x: x[0], reverse=True)
    for _, item in value_aday:
        m, t = item.get("mac", {}), item.get("t", {})
        key = mac_key(m)
        if key in used:
            continue
        market = t.get("ana_label", "")
        lig = m.get("lig", "")
        if market_say.get(market, 0) >= 2 or lig_say.get(lig, 0) >= 1:
            continue
        value.append(base_item(item))
        used.add(key)
        market_say[market] = market_say.get(market, 0) + 1
        lig_say[lig] = lig_say.get(lig, 0) + 1
        if len(value) >= 3:
            break

    # 🔴 AGRESİF: yüksek oran/kombo öncelikli ama AI skoru çok düşük olanı alma.
    agresif = []
    market_say = {}
    lig_say = {}
    adaylar = []
    for item in temiz:
        m, t = item.get("mac", {}), item.get("t", {})
        key = mac_key(m)
        if key in used or safe_int(t.get("ana_p", 0)) < 58:
            continue
        pick_label, pick_guven, pick_type, pick_odd = agresif_pick_label(t)
        odd_val = safe_float(pick_odd or t.get("ana_odd"), 1.0)
        if pick_type != "combo" and odd_val < 1.70:
            continue
        if pick_type == "combo" and odd_val < 2.10:
            continue
        est = pick_type == "combo"
        score = (
            odd_val * 30
            + safe_float(item.get("ai_skor", 0)) * 0.42
            + (20 if pick_type == "combo" else 0)
            + safe_int(pick_guven, 0) * 0.15
            - risk_ceza(t) * 0.35
        )
        adaylar.append((score, item, pick_label, pick_guven, pick_type, odd_val, est))

    adaylar.sort(key=lambda x: x[0], reverse=True)
    for _, item, pick_label, pick_guven, pick_type, odd_val, est in adaylar:
        m = item.get("mac", {})
        key = mac_key(m)
        if key in used:
            continue
        market = pick_label
        lig = m.get("lig", "")
        if market_say.get(market, 0) >= 2 or lig_say.get(lig, 0) >= 2:
            continue
        agresif.append(base_item(item, pick_label, pick_guven, pick_type, odd_val, est))
        used.add(key)
        market_say[market] = market_say.get(market, 0) + 1
        lig_say[lig] = lig_say.get(lig, 0) + 1
        if len(agresif) >= 4:
            break

    if len(agresif) < 3:
        fallback = []
        for item in temiz:
            m, t = item.get("mac", {}), item.get("t", {})
            key = mac_key(m)
            if key in used or safe_int(t.get("ana_p", 0)) < 58:
                continue
            odd = safe_float(t.get("ana_odd"), 1.0)
            if odd >= 1.65:
                score = odd * 20 + safe_float(item.get("ai_skor", 0)) * 0.5
                fallback.append((score, item))
        fallback.sort(key=lambda x: x[0], reverse=True)
        for _, item in fallback:
            m = item.get("mac", {})
            key = mac_key(m)
            if key in used:
                continue
            agresif.append(base_item(item))
            used.add(key)
            if len(agresif) >= 3:
                break

    # Oynanılabilir Yol toplam oran maksimum 6.00 kalsın.
    while _toplam_oran(value) > 6.00 and len(value) > 1:
        value.sort(key=lambda x: x.get("oran", 1.0), reverse=True)
        value.pop(0)

    return {
        "guvenli": (guvenli, _toplam_oran(guvenli)),
        "value": (value, _toplam_oran(value)),
        "agresif": (agresif, _toplam_oran(agresif)),
    }

def auto_kupon_builder(ai_sonuclar, mod="guvenli"):
    paketler = smart_kupon_builder(ai_sonuclar)
    return paketler.get(mod, ([], 1.0))

def gun_riski_belirle(ai_sonuclar):
    guclu = [
        x for x in (ai_sonuclar or [])
        if x.get("t", {}).get("ana_p", 0) >= 70
        and x.get("t", {}).get("risk_label") != "YÜKSEK"
    ]
    orta = [
        x for x in (ai_sonuclar or [])
        if x.get("t", {}).get("ana_p", 0) >= 62
        and x.get("t", {}).get("risk_label") != "YÜKSEK"
    ]

    if len(guclu) >= 5:
        return "dusuk"
    if len(guclu) >= 3 or len(orta) >= 5:
        return "normal"
    if len(orta) >= 2:
        return "yuksek"
    return "pas"


def gunluk_kasa_plani(kasa, hedef=100000, kalan_gun=30, gun_risk="normal"):
    """
    Genel hedef planı. Bu fonksiyon artık tek toplam stake dağıtmaz.
    Her kuponun stake'i, kendi toplam oranına göre ayrıca hesaplanır.
    """
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)

    hedef_acigi = max(hedef - kasa, 0.0)
    gerekli_carpan = (hedef / kasa) ** (1 / kalan_gun)
    gerekli_yuzde = (gerekli_carpan - 1) * 100
    bugunku_hedef_kasa = kasa * gerekli_carpan
    bugunku_hedef_kar = max(bugunku_hedef_kasa - kasa, 0.0)

    return {
        "kasa": round(kasa, 2),
        "hedef": round(hedef, 2),
        "kalan_gun": kalan_gun,
        "hedef_acigi": round(hedef_acigi, 2),
        "gerekli_gunluk_yuzde": round(gerekli_yuzde, 2),
        "bugunku_hedef_kasa": round(bugunku_hedef_kasa, 2),
        "bugunku_hedef_kar": round(bugunku_hedef_kar, 2),
        "onerilen_stake": 0.0,
        "stake_orani": 0.0,
    }


def kupon_stake_hesapla(kasa, hedef, kalan_gun, toplam_oran, gun_risk, mod="value"):
    """
    3 yolun da hedefi aynı: ay sonu hedef.
    Ama oran düşükse stake yüksek, oran yüksekse stake düşük çıkar.
    """
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)
    toplam_oran = max(float(toplam_oran or 1.0), 1.01)

    if gun_risk == "pas":
        return {
            "stake": 0.0,
            "stake_orani": 0.0,
            "bugunku_hedef_kar": 0.0,
            "beklenen_net_kar": 0.0,
            "limit_mesaji": "Bugün yeterli kalite yok; pas önerildi.",
        }

    gerekli_carpan = (hedef / kasa) ** (1 / kalan_gun)
    bugunku_hedef_kasa = kasa * gerekli_carpan
    bugunku_hedef_kar = max(bugunku_hedef_kasa - kasa, 0.0)
    teorik_stake = bugunku_hedef_kar / (toplam_oran - 1)

    risk_limitleri = {
        "dusuk":  {"guvenli": 0.18, "value": 0.10, "agresif": 0.04},
        "normal": {"guvenli": 0.12, "value": 0.07, "agresif": 0.03},
        "yuksek": {"guvenli": 0.00, "value": 0.00, "agresif": 0.015},
    }
    max_oran = risk_limitleri.get(gun_risk, risk_limitleri["normal"]).get(mod, 0.10)
    max_stake = kasa * max_oran

    stake = min(teorik_stake, max_stake)
    stake = max(stake, 0.0)
    beklenen_net_kar = stake * (toplam_oran - 1)

    if teorik_stake > max_stake:
        limit_mesaji = "Hedef için gereken stake risk limitini aştı; limitli önerildi."
    else:
        limit_mesaji = "Bu kupon oranıyla günlük hedef kâr teorik olarak yakalanabilir."

    return {
        "stake": round(stake, 2),
        "stake_orani": round((stake / kasa) * 100, 1),
        "bugunku_hedef_kar": round(bugunku_hedef_kar, 2),
        "beklenen_net_kar": round(beklenen_net_kar, 2),
        "limit_mesaji": limit_mesaji,
    }



def ai_yol_oner(kasa, hedef, kalan_gun, paketler, stake_bilgileri, gun_risk):
    """
    AI hangi yolu takip etmen gerektiğini seçer.
    Mantık: hedef baskısı düşükse güvenli/value, hedef baskısı yüksekse agresif.
    Gün çok zayıfsa PAS.
    """
    kasa = max(float(kasa), 1.0)
    hedef = max(float(hedef), kasa)
    kalan_gun = max(int(kalan_gun), 1)

    gerekli_yuzde = ((hedef / kasa) ** (1 / kalan_gun) - 1) * 100

    if gun_risk == "pas":
        return {
            "key": "pas",
            "baslik": "⛔ PAS",
            "sebep": "Bugün yeterli sayıda kaliteli maç yok. Kasa hedefi ne olursa olsun pas geçmek daha doğru.",
            "gerekli_yuzde": round(gerekli_yuzde, 2),
        }

    def info(mod):
        kupon, oran = paketler.get(mod, ([], 1.0))
        stake_info = stake_bilgileri.get(mod, {}) or {}
        stake = float(stake_info.get("stake", 0) or 0)
        stake_orani = float(stake_info.get("stake_orani", 0) or 0)
        beklenen = float(stake_info.get("beklenen_net_kar", 0) or 0)
        return kupon, float(oran or 1.0), stake, stake_orani, beklenen

    g_k, g_o, g_s, g_so, g_b = info("guvenli")
    v_k, v_o, v_s, v_so, v_b = info("value")
    a_k, a_o, a_s, a_so, a_b = info("agresif")

    # Hedef baskısı çok düşükse güvenli veya value yeterli olabilir.
    if gerekli_yuzde <= 4:
        if g_k and g_s > 0 and g_so <= 8:
            return {"key": "guvenli", "baslik": "🟢 Güvenli Yol", "sebep": "Hedef baskısı düşük; düşük riskli kupon hedefe yetişmek için yeterli.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
        if v_k and v_s > 0:
            return {"key": "value", "baslik": "🟡 Oynanılabilir Yol", "sebep": "Güvenli yol stake’i yüksek kaldı; oynanılabilir yol daha dengeli.", "gerekli_yuzde": round(gerekli_yuzde, 2)}

    # Orta baskıda value ana yol olsun.
    if gerekli_yuzde <= 12:
        if v_k and v_o >= 3 and v_s > 0:
            return {"key": "value", "baslik": "🟡 Oynanılabilir Yol", "sebep": "Hedef için güvenli yol yavaş kalabilir; value oran/stake dengesi daha uygun.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
        if g_k and g_s > 0 and g_so <= 12:
            return {"key": "guvenli", "baslik": "🟢 Güvenli Yol", "sebep": "Oynanılabilir yol kalitesi yeterli değil; güvenli yol daha kontrollü.", "gerekli_yuzde": round(gerekli_yuzde, 2)}

    # Yüksek baskıda agresif yol gerekir; özellikle 1000→100k gibi hedeflerde.
    if a_k and a_o >= 8 and a_s > 0:
        if gun_risk == "yuksek" and a_o < 20:
            return {"key": "pas", "baslik": "⛔ PAS", "sebep": "Gün riski yüksek ve agresif oran hedef için yeterince güçlü değil. Pas daha doğru.", "gerekli_yuzde": round(gerekli_yuzde, 2)}
        return {"key": "agresif", "baslik": "🔴 Agresif Yol", "sebep": "Hedef baskısı yüksek; güvenli/oynanılabilir yolları çok fazla stake ister. Düşük stake ile agresif yol daha mantıklı.", "gerekli_yuzde": round(gerekli_yuzde, 2)}

    if v_k and v_o >= 4 and v_s > 0 and gun_risk != "yuksek":
        return {"key": "value", "baslik": "🟡 Oynanılabilir Yol", "sebep": "Agresif kupon yeterli değil; oynanılabilir yol en dengeli alternatif.", "gerekli_yuzde": round(gerekli_yuzde, 2)}

    return {
        "key": "pas",
        "baslik": "⛔ PAS",
        "sebep": "Hedefe uygun oran/kalite kombinasyonu yok. Bugün zorlamak yerine pas geçmek daha mantıklı.",
        "gerekli_yuzde": round(gerekli_yuzde, 2),
    }

def stake_dagilimi(toplam_stake, gun_risk):
    return {"guvenli": 0.0, "value": 0.0, "agresif": 0.0}
def kuponu_session_formatina_cevir(kupon):
    sonuc = []

    for item in kupon or []:
        m = item.get("mac", {})
        t = item.get("t", {})
        z = m.get("zaman")

        try:
            zaman_iso = z.strftime("%Y-%m-%d %H:%M:%S")
            zaman_text = z.strftime("%d.%m %H:%M")
        except Exception:
            zaman_iso = ""
            zaman_text = "-"

        sonuc.append({
            "ev": m.get("ev", ""),
            "dep": m.get("dep", ""),
            "lig": m.get("lig", ""),
            "zaman_iso": zaman_iso,
            "zaman_text": zaman_text,
            "tahmin": f"{item.get('pick_label', t.get('ana_label', '-'))} ({fmt_odd(item.get('oran'))}{' tahmini' if item.get('oran_tahmini') else ''})",
            "guven": int(t.get("ana_p", 0)),
        })

    return sonuc

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
    eg, dg = skoru_tahmine_uydur(eg, dg, ana_label, ms_mod)
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
    ("last_gecmis_df", None),
    ("last_bulten_df", None),
    ("ai_global_sonuclar", []),
    ("ai_auto_kuponlar", None),
    ("kasa_plani", None),
    ("gun_risk", None),
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
    if secim == "2 gün sonra":
        return bugun_tarih + timedelta(days=2)
    if secim == "3 gün sonra":
        return bugun_tarih + timedelta(days=3)
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
                options=['Bugün', 'Yarın', '2 gün sonra', '3 gün sonra', 'Özel Tarih'],
                index=['Bugün', 'Yarın', '2 gün sonra', '3 gün sonra', 'Özel Tarih'].index(st.session_state.get('date_mode', 'Bugün')),
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
        default=['2122', '2223', '2324', '2425', '2526'],
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
        st.session_state.coupon_popup_open = True
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
            st.session_state.last_gecmis_df = gecmis
            st.session_state.last_bulten_df = bulten

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
        final = sorted(
            final,
            key=lambda x: (
                x.get("t", {}).get("playable_score", 0),
                x.get("t", {}).get("ana_p", 0),
            ),
            reverse=True
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
    <div class="history-card">
      <div class="history-title" style="color:#f8fbff !important">Benzer Oranlı Geçmiş Maçlar (Son {min(len(b_det), 10)})</div>
      <div class="history-sub" style="color:#f8fbff !important">ℹ️ Tablodaki maçlar seçili oran aralığına (±{t['kullanilan_tolerans']:.2f}) en yakın bulunan benzer maçlardır.</div>
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


# ==========================================================
# AI KUPON BUILDER + 30 GUNLUK KASA TAKIBI
# Bu panel final_list bos olsa bile gorunur; bulten/gecmis hafizada varsa calisir.
# ==========================================================
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("🧠 AI Günlük Tarama + Auto Kupon Builder + 30 Günlük Kasa Planı", expanded=True):
    st.caption("Günün tüm maçlarını 0.00 - 0.30 arası çoklu hassasiyetle tarar. Güvenli / Oynanılabilir / Agresif kupon üretir. Takip manuel: gün, kasa ve hedefi sen girersin.")

    k1, k2, k3 = st.columns(3)
    with k1:
        takip_gun = st.number_input("Kaçıncı gün?", min_value=1, max_value=30, value=1, step=1, key="takip_gun_input")
    with k2:
        gun_kasa = st.number_input("Güncel kasa (TL)", min_value=0.0, value=1000.0, step=50.0, key="gun_kasa_input")
    with k3:
        ay_hedef = st.number_input("Ay sonu hedef (TL)", min_value=1.0, value=100000.0, step=1000.0, key="ay_hedef_input")

    kalan_gun = max(1, 31 - int(takip_gun))
    st.caption(f"Kalan gün: {kalan_gun} · Not: 1000 TL → 100.000 TL hedefi çok agresiftir; sistem garanti değil, risk kontrollü plan verir.")

    if st.button("🎯 Günün Tüm Maçlarını Tara + AI Kupon + Kasa Planı Oluştur", use_container_width=True, key="ai_kasa_kupon_btn"):
        gecmis_df = st.session_state.get("last_gecmis_df")
        bulten_df = st.session_state.get("last_bulten_df")

        if gecmis_df is None or bulten_df is None or getattr(gecmis_df, "empty", True) or getattr(bulten_df, "empty", True):
            st.warning("Önce üstten API key + lig seçip ANALİZİ BAŞLAT'a bas. Normal liste 0 maç bulsa bile bu panel ham bülteni kullanıp tekrar tarar.")
        else:
            with st.spinner("AI tüm maçları 0.00 - 0.30 arası çoklu hassasiyetle tek seferde tarıyor..."):
                ai_sonuclar = global_ai_tarama(gecmis_df, bulten_df, limit=100)

                gun_risk = gun_riski_belirle(ai_sonuclar)
                plan = gunluk_kasa_plani(gun_kasa, ay_hedef, kalan_gun, gun_risk)

                st.session_state.ai_global_sonuclar = ai_sonuclar
                st.session_state.kasa_plani = plan
                st.session_state.gun_risk = gun_risk

                paketler = smart_kupon_builder(ai_sonuclar)
                guvenli, guvenli_oran = paketler["guvenli"]
                value, value_oran = paketler["value"]
                agresif, agresif_oran = paketler["agresif"]

                stake_bilgileri = {
                    "guvenli": kupon_stake_hesapla(gun_kasa, ay_hedef, kalan_gun, guvenli_oran, gun_risk, "guvenli"),
                    "value": kupon_stake_hesapla(gun_kasa, ay_hedef, kalan_gun, value_oran, gun_risk, "value"),
                    "agresif": kupon_stake_hesapla(gun_kasa, ay_hedef, kalan_gun, agresif_oran, gun_risk, "agresif"),
                }

                yol_oneri = ai_yol_oner(gun_kasa, ay_hedef, kalan_gun, paketler, stake_bilgileri, gun_risk)

                st.session_state.ai_yol_oneri = yol_oneri
                st.session_state.ai_pas_mesaji = "" if yol_oneri.get("key") != "pas" else yol_oneri.get("sebep", "Bugün pas önerildi.")
                st.session_state.ai_auto_kuponlar = {
                    "🟢 Güvenli Yol": (guvenli, guvenli_oran, stake_bilgileri["guvenli"], "guvenli"),
                    "🟡 Oynanılabilir Yol": (value, value_oran, stake_bilgileri["value"], "value"),
                    "🔴 Agresif Yol": (agresif, agresif_oran, stake_bilgileri["agresif"], "agresif"),
                }
            st.rerun()

    if st.session_state.get("kasa_plani"):
        p = st.session_state.kasa_plani
        risk = st.session_state.get("gun_risk", "-")
        risk_text = {"dusuk": "DÜŞÜK", "normal": "NORMAL", "yuksek": "YÜKSEK", "pas": "PAS"}.get(risk, str(risk).upper())
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#07111f,#0a1830);border:1px solid #284977;border-radius:16px;padding:16px 18px;margin:12px 0;color:#f8fbff">
          <div style="font-family:Rajdhani,sans-serif;font-size:1.3rem;font-weight:800;margin-bottom:8px">🎯 30 Günlük Kasa Planı</div>
          <div>Gün riski: <b>{risk_text}</b></div>
          <div>Güncel kasa: <b>{p['kasa']} TL</b> · Hedef: <b>{p['hedef']} TL</b> · Kalan gün: <b>{p['kalan_gun']}</b></div>
          <div>Hedef açığı: <b>{p.get('hedef_acigi', 0)} TL</b></div>
          <div>Hedefe yetişmek için gerekli ortalama günlük büyüme: <b>%{p['gerekli_gunluk_yuzde']}</b></div>
          <div>Bugünkü hedef kasa: <b>{p.get('bugunku_hedef_kasa', 0)} TL</b> · Bugünkü hedef kâr: <b>{p.get('bugunku_hedef_kar', 0)} TL</b></div>
          <div style="color:#9db2d1;margin-top:4px">Stake kupon oranına göre ayrı hesaplanır. AI ayrıca hedef baskısına göre bugün hangi yolun takip edileceğini seçer.</div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.get("ai_yol_oneri"):
        y = st.session_state.ai_yol_oneri
        renk = {"guvenli":"#22c55e", "value":"#facc15", "agresif":"#ef4444", "pas":"#94a3b8"}.get(y.get("key"), "#94a3b8")
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#101827,#0b1628);border:1px solid {renk};border-radius:16px;padding:16px 18px;margin:12px 0;color:#f8fbff">
          <div style="font-family:Rajdhani,sans-serif;font-size:1.35rem;font-weight:900;margin-bottom:8px">🤖 AI Yol Önerisi: {y.get('baslik','-')}</div>
          <div>Gerekli günlük büyüme: <b>%{y.get('gerekli_yuzde','-')}</b></div>
          <div style="color:#dbeafe;margin-top:4px">{y.get('sebep','')}</div>
          <div style="color:#9db2d1;margin-top:6px">Diğer yollar aşağıda alternatif olarak görünür; ana takip için AI'nın seçtiği yolu kullan.</div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.get("ai_pas_mesaji"):
        st.warning(st.session_state.ai_pas_mesaji)

    if st.session_state.get("ai_auto_kuponlar"):
        st.markdown("### 🧠 AI Günlük Kupon Önerileri")

        for baslik, (kupon, toplam_oran, stake_info, mod_key) in st.session_state.ai_auto_kuponlar.items():
            # v6 güvenli okuma: eski session tuple/list ise app patlamasın.
            if isinstance(stake_info, dict):
                stake = stake_info.get("stake", 0)
                stake_orani = stake_info.get("stake_orani", 0)
                hedef_kar = stake_info.get("bugunku_hedef_kar", 0)
                beklenen_kar = stake_info.get("beklenen_net_kar", 0)
                limit_mesaji = stake_info.get("limit_mesaji", "")
            elif isinstance(stake_info, (list, tuple)):
                stake = stake_info[0] if len(stake_info) > 0 else 0
                hedef_kar = stake_info[1] if len(stake_info) > 1 else 0
                stake_orani = round((float(stake) / max(float(gun_kasa), 1.0)) * 100, 1)
                beklenen_kar = round(float(stake) * (float(toplam_oran or 1) - 1), 2)
                limit_mesaji = "Eski stake formatı otomatik düzeltildi. Tekrar butona basarsan yeni formatla hesaplanır."
            else:
                stake = 0
                stake_orani = 0
                hedef_kar = 0
                beklenen_kar = 0
                limit_mesaji = "Stake bilgisi okunamadı. Tekrar kupon oluşturmayı dene."
            onerilen_key = (st.session_state.get("ai_yol_oneri") or {}).get("key")
            etiket = " ⭐ AI ÖNERİSİ" if onerilen_key == mod_key else " · Alternatif"
            st.markdown(f"#### {baslik}{etiket} — Toplam oran: **{toplam_oran}** · Önerilen stake: **{stake} TL** (%{stake_orani})")
            st.caption(f"Bugünkü hedef kâr: {hedef_kar} TL · Bu kupon kazanırsa net: {beklenen_kar} TL · {limit_mesaji}")

            if not kupon:
                st.warning("Bu mod için yeterince sağlam maç bulunamadı.")
                continue

            for item in kupon:
                m = item["mac"]
                t = item["t"]
                pick_label = item.get("pick_label", t.get("ana_label", "-"))
                pick_type = "Kombo" if item.get("pick_type") == "combo" else "Ana"
                oran_not = " tahmini" if item.get("oran_tahmini") else ""
                guven_txt = item.get("pick_guven", t.get("ana_p", 0))
                st.markdown(
                    f"- **{m.get('ev','')} - {m.get('dep','')}** | "
                    f"{pick_label} / **{pick_type}** (**{item['oran']:.2f}{oran_not}**) | "
                    f"Güven **%{guven_txt}** | "
                    f"AI Skor **{item.get('final_skor',0)}** | "
                    f"Tol **{item.get('tolerans')}** | "
                    f"Skor **{t.get('eg',1)}-{t.get('dg',1)}** | "
                    f"Risk **{t.get('risk_label','-')}**"
                )

            if st.button(f"🎫 {baslik} Kupona Aktar", key=f"aktar_{mod_key}", use_container_width=True):
                st.session_state.kupona = kuponu_session_formatina_cevir(kupon)
                st.session_state.coupon_popup_open = True
                st.rerun()

    if st.session_state.get("ai_global_sonuclar"):
        st.markdown("#### 🎚️ AI Hassasiyet Filtresi")
        secilen_ai_tolerans = st.selectbox(
            "Sonuçları hangi hassasiyete göre gösterelim?",
            ["AI Otomatik", 0.00, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30],
            index=0,
            key="ai_tolerans_filtresi",
            help="Kupon ana seçimi 0.00-0.10 bandından yapılır. 0.12-0.30 sadece kontrol/Excel için gösterilebilir."
        )

        ai_gosterilecek_sonuclar = ai_sonuclarini_toleransa_gore_filtrele(
            st.session_state.ai_global_sonuclar,
            secilen_ai_tolerans
        )

        if secilen_ai_tolerans != "AI Otomatik" and not ai_gosterilecek_sonuclar:
            st.warning("Bu hassasiyette gösterilecek uygun maç bulunamadı.")

        paketler_excel = smart_kupon_builder(ai_gosterilecek_sonuclar)
        excel_buffer = ai_sonuclari_excel_buffer(ai_gosterilecek_sonuclar, paketler_excel)

        st.download_button(
            label="📥 Tüm Maçları Excel İndir",
            data=excel_buffer.getvalue(),
            file_name=f"vibe_ai_maclar_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="ai_excel_download_btn",
        )

        with st.expander("🔎 AI taramasında 0.00 - 0.10 arası tüm uygun maçlar"):
            for item in top10_market_cesitli(ai_gosterilecek_sonuclar):
                    m = item.get("mac", {})
                    t = item.get("t", {})
                    st.markdown(
                        f"**{m.get('ev','')} - {m.get('dep','')}** · "
                        f"{item.get('top10_label', t.get('ana_label','-'))} · "
                        f"Güven %{item.get('top10_guven', t.get('ana_p',0))} · "
                        f"{item.get('top10_tip','Ana')} · "
                        f"{tolerans_label(item.get('tolerans'))} · "
                        f"Tol {item.get('tolerans')} · "
                        f"AI Skor {item.get('top10_skor', item.get('ai_skor'))} · "
                        f"Oran {fmt_odd(item.get('top10_oran', t.get('ana_odd')))}"
                    )

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
            st.session_state.coupon_popup_open = True
            st.rerun()
    with cc2:
        if st.button("🎯 Günün En Yüksek Oranlı 3 Favorisi", use_container_width=True, key="top3_highfav_btn"):
            st.session_state.kupona = build_top3_coupon(indexed_fl, mode="high_favorites")
            st.session_state.coupon_popup_open = True
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
    st.markdown("""<div class="list-heading">⚡ ANLIK MAÇ TAHMİNLERİ</div>""", unsafe_allow_html=True)

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
        belirsiz_html = '<div class="mk-mini" style="color:#ff8b8b">⚠️ Belirsiz maç</div>' if t.get("belirsiz") else ''
        combo_html = ''
        skor_html = f'<div style="margin-top:8px;font-size:0.76rem;color:#cbd5e1">🎯 Tahmini skor: <b style="color:#f8fbff">{t.get("eg", 1)}-{t.get("dg", 1)}</b></div>'
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
                {ai_comment_html}
              </div>

              <div>
                <div class="mk-label">ANA TAHMİN</div>
                <span class="ana-pill {pill_cls}">{t['ana_label']}</span>
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
                mevcutlar = set()
                for x in st.session_state.kupona:
                    if isinstance(x, dict):
                        mevcutlar.add((x.get("ev", ""), x.get("dep", ""), x.get("tahmin", "")))
                    else:
                        raw_text = str(x)
                        ev, dep, tahmin = raw_text, "", ""
                        if " — " in raw_text:
                            match_text, tahmin = raw_text.split(" — ", 1)
                            if " vs " in match_text:
                                ev, dep = [p.strip() for p in match_text.split(" vs ", 1)]
                            else:
                                ev = match_text.strip()
                        mevcutlar.add((ev, dep, tahmin.strip()))
                if (coupon_item["ev"], coupon_item["dep"], coupon_item["tahmin"]) not in mevcutlar:
                    st.session_state.kupona.append(coupon_item)
                    st.session_state.coupon_popup_open = True
                st.rerun()

    # Kuponlarım: dialog/modal yerine normal, engellemeyen panel.
    # Boşken arama sırasında "Henüz kupona maç eklemedin" uyarısı göstermez.
    if st.session_state.get("coupon_popup_open") and st.session_state.get("kupona"):
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

        with st.container(border=True):
            st.markdown("### 🎫 Kuponlarım")
            for del_i, item in enumerate(list(st.session_state.kupona)):
                mac_dt = parse_mac_datetime(item.get("zaman_iso", ""))
                durum = mac_canli_durumu(mac_dt) if item.get("zaman_iso") else "Takipte"
                mac_ad = f"{item.get('ev', '')} - {item.get('dep', '')}".strip(" -")
                alt_satir = (
                    f"{item.get('lig', '-')} | {item.get('zaman_text', '-')} | "
                    f"{item.get('tahmin', '-')} | Güven %{int(item.get('guven', 0))}"
                    if item.get("guven", 0)
                    else f"{item.get('lig', '-')} | {item.get('zaman_text', '-')} | {item.get('tahmin', '-')}"
                )
                c1, c2 = st.columns([8, 1])
                with c1:
                    st.markdown(f"**{mac_ad}**  \n{alt_satir}  \n`{durum}`")
                with c2:
                    if st.button("🗑️", key=f"coupon_delete_{del_i}", use_container_width=True):
                        st.session_state.kupona.pop(del_i)
                        if not st.session_state.kupona:
                            st.session_state.coupon_popup_open = False
                        st.rerun()

            b1, b2 = st.columns([1, 1])
            with b1:
                if st.button("🧹 Hepsini Temizle", key="coupon_clear_inside_panel", use_container_width=True):
                    st.session_state.kupona = []
                    st.session_state.coupon_popup_open = False
                    st.rerun()
            with b2:
                if st.button("Kapat", key="coupon_close_inside_panel", use_container_width=True):
                    st.session_state.coupon_popup_open = False
                    st.rerun()

