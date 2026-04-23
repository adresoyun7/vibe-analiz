# VIBE PRO EXPERT - Clean UI
# -*- coding: utf-8 -*-

import math
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")

APP_SCHEMA_VERSION = 31
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap');

:root {
  --bg: #f6f8fc;
  --panel: #071427;
  --panel-2: #0a1930;
  --card: #0b1628;
  --card-2: #0f1d33;
  --border: #17325f;
  --text: #f5f7fb;
  --muted: #90a3bf;
  --yellow: #facc15;
  --yellow-2: #fbbf24;
  --green: #22c55e;
  --red: #ff5a5f;
  --blue: #1d4ed8;
}

html, body, [class*="css"] {
  font-family: 'DM Sans', sans-serif;
  background: #f7f9fc;
  color: #0f172a;
}

.stApp {
  background: #f7f9fc;
}

.block-container {
  max-width: 1600px;
  padding-top: 0.8rem !important;
  padding-bottom: 1rem !important;
}

div[data-testid="stVerticalBlock"] > div:empty {
  display: none !important;
}

header[data-testid="stHeader"] {
  background: transparent;
}

#MainMenu, footer {
  visibility: hidden;
}

/* Scrollbar */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--yellow) #0b1320;
}
*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
*::-webkit-scrollbar-track {
  background: #0b1320;
  border-radius: 10px;
}
*::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, var(--yellow), var(--yellow-2));
  border-radius: 10px;
  border: 2px solid #0b1320;
}

.top-hero {
  background: radial-gradient(circle at 30% 0%, rgba(30,64,175,.35), transparent 38%),
              linear-gradient(90deg, #071322 0%, #082042 55%, #051425 100%);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 18px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  margin-bottom: 10px;
  box-shadow: 0 12px 30px rgba(0,0,0,.28);
}
.hero-left {
  display:flex;
  align-items:center;
  gap:12px;
}
.hero-logo {
  width:36px;
  height:36px;
  border-radius:10px;
  display:flex;
  align-items:center;
  justify-content:center;
  background: linear-gradient(180deg, #ffe16a, #facc15);
  color:#111827;
  font-size:18px;
  font-weight:900;
}
.hero-title {
  font-family:'Rajdhani', sans-serif;
  font-size:2rem;
  font-weight:700;
  letter-spacing:.3px;
}
.hero-title .yellow { color: var(--yellow); }
.hero-sub {
  color: #8ba0bb;
  font-size:.78rem;
  margin-top:2px;
}

.api-box details {
  background: #050d18;
  border: 1px solid #122846;
  border-radius: 10px;
  padding: 4px 10px;
}
.api-box summary {
  cursor: pointer;
  color: #cbd7e6;
  font-weight: 600;
}

.topbar-wrap {
  background: linear-gradient(180deg, rgba(6,14,25,.96), rgba(4,10,19,.96));
  border: 1px solid #12315c;
  border-radius: 16px;
  padding: 12px;
  margin-bottom: 12px;
  box-shadow: 0 10px 26px rgba(0,0,0,.28);
}

.section-kicker {
  font-size:.58rem;
  letter-spacing:1.6px;
  color:#6f89ad;
  text-transform:uppercase;
  margin-bottom:6px;
  font-weight:700;
}

.control-box {
  background: #081321;
  border: 1px solid #19355c;
  border-radius: 12px;
  padding: 8px 10px;
  min-height: 52px;
}

.control-box button[kind="secondary"] {
  border-color: #214273 !important;
}

.summary-inline {
  color: var(--yellow);
  font-size: .78rem;
  font-weight: 700;
  margin-top: 6px;
}

/* Inputs */
div[data-baseweb="select"] > div,
div[data-baseweb="popover"] > div,
div[data-testid="stNumberInputContainer"],
div[data-testid="stDateInput"] > div,
div[data-testid="stTextInputRootElement"] {
  background: #091321 !important;
  border-color: #1b3c6a !important;
  border-radius: 12px !important;
}

input, textarea {
  color: var(--text) !important;
}

.stMultiSelect [data-baseweb="tag"] {
  background: #ff5f5f !important;
  color: white !important;
  border-radius: 8px !important;
  border: none !important;
}

.stNumberInput button, .stDateInput button {
  background: #0e1b2d !important;
  color: white !important;
  border-color: #23426d !important;
}

.stSlider [data-baseweb="slider"] > div div {
  background: var(--yellow) !important;
}

.stCheckbox label, .stRadio label {
  color: var(--text) !important;
}

.stButton > button {
  border-radius: 12px !important;
  border: 1px solid #284a78 !important;
  background: linear-gradient(180deg, #0e1a2b, #0a1524) !important;
  color: #f4f7fb !important;
  font-weight: 700 !important;
}
.stButton > button:hover {
  border-color: var(--yellow) !important;
  box-shadow: 0 0 0 1px rgba(250,204,21,.18), 0 10px 22px rgba(250,204,21,.08);
}

.primary-cta button {
  background: linear-gradient(180deg, #ff6464, #ff5055) !important;
  border-color: #ff7377 !important;
  color: white !important;
  min-height: 52px !important;
}

.rehber-box {
  background: linear-gradient(90deg, rgba(5,22,45,.95), rgba(8,33,67,.95));
  border: 1px solid #1c4b86;
  border-radius: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  display:flex;
  flex-wrap:wrap;
  gap:22px;
  align-items:center;
}
.rehber-title {
  color:#60a5fa;
  font-size:.8rem;
  font-weight:800;
  text-transform:uppercase;
  letter-spacing:1px;
}
.rehber-item {
  color:#e8eef8;
  font-size:.9rem;
}
.rehber-item .muted {
  color:#9cb0c8;
}

.panel-title {
  font-family:'Rajdhani', sans-serif;
  font-size:2rem;
  font-weight:700;
  margin: 8px 0 2px 0;
  color:#0a1930;
}
.panel-date {
  color:#475569;
  font-size:.86rem;
}

.metrics-card {
  background: linear-gradient(180deg, #081321, #0a1424);
  border: 1px solid #143055;
  border-radius: 14px;
  padding: 14px;
  text-align:center;
}
.metrics-card .big {
  font-family:'Rajdhani',sans-serif;
  font-size:2rem;
  font-weight:700;
  color: var(--green);
}
.metrics-card .sub {
  color:#7f97b7;
  font-size:.72rem;
  text-transform:uppercase;
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
