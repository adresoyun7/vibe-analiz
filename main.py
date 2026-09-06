
import io
import json
import math
import re
import time
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components



def kart_takim_adi(ad):
    """Kartlarda baştaki yaygın kulüp eklerini gizler; veri eşleştirmesini etkilemez."""
    s = str(ad or "").strip()
    s = re.sub(r"^(?:FC|CF|AFC|SC|AC)\s+", "", s, flags=re.IGNORECASE)
    return s.strip() or str(ad or "")

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
    st.markdown("""
    ---
    <div style="text-align:center;font-size:12px;color:#64748b;line-height:1.55;padding:10px 0 4px 0;">
        <b>Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analiz ve yapay zekâ destekli tahminler sunar.<br>
        Kesin kazanç garantisi verilmez. Kullanıcılar kararlarını kendi sorumluluğunda verir.<br>
        Bu platform üzerinden doğrudan bahis oynanmaz. Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.
    </div>
    """, unsafe_allow_html=True)



APP_SCHEMA_VERSION = 78
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
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
                    "FTR", "HTR",
                    # Football-Data: ilk/pre-closing set
                    "B365H", "B365D", "B365A",
                    # Football-Data: kapanış seti (C = closing), mevcut sezonlarda varsa
                    "B365CH", "B365CD", "B365CA",
                    "HC", "AC", "HY", "AY"
                ]
                df = df[df.columns.intersection(cols)].copy()

                # Eksik sütunları güvenli biçimde oluştur. Eski sezonlarda C sütunları olmayabilir.
                for c in ["B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA"]:
                    if c not in df.columns:
                        df[c] = pd.NA
                    df[c] = pd.to_numeric(df[c], errors="coerce")

                # Ana karşılaştırma için mümkünse kapanış oranını, yoksa eski/pre-closing oranını kullan.
                df["REF_H"] = df["B365CH"].combine_first(df["B365H"])
                df["REF_D"] = df["B365CD"].combine_first(df["B365D"])
                df["REF_A"] = df["B365CA"].combine_first(df["B365A"])

                temp = df.dropna(subset=["REF_H", "REF_D", "REF_A"]).copy()
                temp["Date"] = pd.to_datetime(temp["Date"], dayfirst=True, errors="coerce")
                temp["league_code"] = k
                temp["season_code"] = s
                liste.append(temp)
            except Exception:
                continue

    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner=False)
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
        st.error("Maç bültenini çekmek için ODDS API key gerekli.")
        return pd.DataFrame()
    res = []

    for secili_kod in kodlar:
        k = odds_lig_kodu_coz(key, secili_kod)
        if not k:
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
                    if bk_key.lower() == "bet365":
                        return (0, bk_key)
                    return (1, bk_key)

                market = None
                totals_market = None
                secilen_bk_key = ""
                totals_bk_key = ""
                sirali_bk = sorted(bookies, key=bk_priority)

                # 1X2 için tercih edilen bookmaker'ı seç.
                for bk in sirali_bk:
                    markets_by_key = {str(mk.get("key", "")): mk for mk in bk.get("markets", [])}
                    h2h_mk = markets_by_key.get("h2h")
                    if h2h_mk is None:
                        continue
                    market = h2h_mk
                    secilen_bk_key = str(bk.get("key", ""))
                    break

                if not market:
                    continue

                # 2.5 Alt/Üst bağımsız aranır. H2H aldığımız bookmaker totals
                # sunmuyorsa diğer bookmaker'larda gerçek 2.5 çizgisini ara.
                for bk in sirali_bk:
                    markets_by_key = {str(mk.get("key", "")): mk for mk in bk.get("markets", [])}
                    tmkt = markets_by_key.get("totals")
                    if not tmkt:
                        continue
                    has_25 = False
                    for ox in tmkt.get("outcomes", []) or []:
                        try:
                            if abs(float(ox.get("point")) - 2.5) <= 1e-9:
                                has_25 = True
                                break
                        except Exception:
                            continue
                    if has_25:
                        totals_market = tmkt
                        totals_bk_key = str(bk.get("key", ""))
                        break

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
                    "totals_bookmaker_key": totals_bk_key,
                    "o25_over": o25_over,
                    "o25_under": o25_under,
                })
        except Exception as exc:
            st.session_state["odds_api_last_error"] = f"{k}: {type(exc).__name__}: {exc}"
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    df = df.sort_values("zaman").reset_index(drop=True)
    return df



ODDS_BULTEN_CACHE_TTL = 15 * 60  # 15 dakika


def bulten_guncel_al(key, kodlar, t, zorla_yenile=False):
    """
    Lig bazlı session cache kullanır.

    - Aynı tarih + lig 15 dakika içinde tekrar API'ye gitmez.
    - Yeni bir lig eklenirse yalnızca o lig çekilir.
    - Hassasiyet / minimum örnek / güven eşiği değişiklikleri API tüketmez.
    - zorla_yenile=True yalnızca seçili ligleri yeniden çeker.
    """
    cache = st.session_state.setdefault("odds_league_cache", {})
    simdi_ts = time.time()
    parcalar = []

    for secili_kod in list(dict.fromkeys(kodlar or [])):
        cache_key = f"{secili_kod}|{t.isoformat()}"
        kayit = cache.get(cache_key)
        gecerli = (
            isinstance(kayit, dict)
            and (simdi_ts - float(kayit.get("ts", 0) or 0)) < ODDS_BULTEN_CACHE_TTL
        )

        if gecerli and not zorla_yenile:
            lig_df = kayit.get("df")
            # Boş cache'i geçerli sayma. Geçici API sorunu sonrası 15 dakika
            # boyunca "maç yok" görünmesine sebep olmasın.
            if isinstance(lig_df, pd.DataFrame) and not lig_df.empty:
                parcalar.append(lig_df.copy())
                continue

        # Cache yoksa/süresi dolduysa yalnızca bu ligi sorgula.
        lig_df = bulten_cek(key, [secili_kod], t)
        if not isinstance(lig_df, pd.DataFrame):
            lig_df = pd.DataFrame()
        if not lig_df.empty:
            cache[cache_key] = {"ts": simdi_ts, "df": lig_df.copy()}
        else:
            cache.pop(cache_key, None)
        parcalar.append(lig_df)

    # Süresi dolmuş eski kayıtları ara sıra temizle.
    eski_sinir = simdi_ts - (ODDS_BULTEN_CACHE_TTL * 4)
    for ck in list(cache.keys()):
        try:
            if float(cache[ck].get("ts", 0) or 0) < eski_sinir:
                cache.pop(ck, None)
        except Exception:
            cache.pop(ck, None)

    if not parcalar:
        return pd.DataFrame()
    dolu = [x for x in parcalar if isinstance(x, pd.DataFrame) and not x.empty]
    if not dolu:
        return pd.DataFrame()
    df = pd.concat(dolu, ignore_index=True)
    if all(c in df.columns for c in ["ev", "dep", "zaman"]):
        df = df.drop_duplicates(subset=["ev", "dep", "zaman"]).sort_values("zaman").reset_index(drop=True)
    return df


def bulten_saglam_al(key, kodlar, t, zorla_yenile=False):
    """Boş/stale cache'in Maç Analizi ve Geçmiş Örnekleri'ni kilitlemesini önler."""
    df = bulten_guncel_al(key, kodlar, t, zorla_yenile=zorla_yenile)
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df
    # HTTP/bağlantı hatası olduysa bir kez zorla yenile; gerçek fikstür yoksa ikinci kez tüketme.
    if st.session_state.get("odds_api_last_error") and not zorla_yenile:
        st.session_state["odds_api_last_error"] = None
        df = bulten_guncel_al(key, kodlar, t, zorla_yenile=True)
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def odds_cache_bilgi(kodlar, t):
    """Seçili liglerin cache durumunu (geçerli/toplam) döndürür."""
    cache = st.session_state.get("odds_league_cache", {})
    simdi_ts = time.time()
    toplam = len(list(dict.fromkeys(kodlar or [])))
    gecerli = 0
    for kod in list(dict.fromkeys(kodlar or [])):
        kayit = cache.get(f"{kod}|{t.isoformat()}")
        try:
            if isinstance(kayit, dict) and (simdi_ts - float(kayit.get("ts", 0) or 0)) < ODDS_BULTEN_CACHE_TTL:
                gecerli += 1
        except Exception:
            pass
    return gecerli, toplam





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
    simdi = datetime.now()
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
        tolerans = float(t.get("kullanilan_tolerans", 0.08) or 0.08)
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
            "hassasiyet": float(t.get("kullanilan_tolerans", 0.08) or 0.08),
            "hassasiyetler": list(aday.get("hassasiyetler") or t.get("top10_hassasiyetler") or t.get("stability_tols") or []),
            "hassasiyet_sayisi": int(aday.get("hassasiyet_sayisi") or len(aday.get("hassasiyetler") or []) or 0),
            "otomatik": True,
            "profil": profil,
            # Kupon geçmişinden maç detayını yeniden oluşturabilmek için
            # Son bültendeki temel maç/oran bilgilerini de sakla.
            "sport_key": m.get("sport_key", ""),
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
    Aynı maçtan yalnızca bir seçim alınır. 2-6 seçim üretilebilir.
    Güven kadar 0.00-0.10 taramasındaki kararlılık da dikkate alınır.
    """
    simdi = datetime.now()
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
        tolerans = float(t.get("kullanilan_tolerans", 0.08) or 0.08)
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
            "hassasiyet": float(t.get("kullanilan_tolerans", 0.08) or 0.08),
            "hassasiyetler": list(t.get("top10_hassasiyetler", t.get("stability_tols", [])) or []),
            "hassasiyet_sayisi": int(aday["stabil"]),
            "gunun_puani": round(float(aday["gunun_puani"]), 1),
            "baglam_ayari": round(float(aday["baglam_ayari"]), 2),
            "baglam": aday.get("baglam", {}),
            "kontrollu_gevsetme": bool(aday.get("kontrollu_gevsetme", False)),
            "otomatik": True,
            "profil": "Günün Kuponu",
            "sport_key": m.get("sport_key", ""),
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

    # Tek maç "kupon" üretmeyelim. Yeterli kalite yoksa kullanıcıya açıkça
    # kupon bulunamadığını söylemek, zayıf seçim eklemekten daha doğrudur.
    return secimler if len(secimler) >= 2 else []


KUPON_GECMISI_PATH = Path(__file__).with_name("vibe_kupon_gecmisi.json")


def kupon_gecmisini_oku():
    try:
        if KUPON_GECMISI_PATH.exists():
            veri = json.loads(KUPON_GECMISI_PATH.read_text(encoding="utf-8"))
            return veri if isinstance(veri, list) else []
    except Exception:
        pass
    return []


def kupon_gecmisini_yaz(kayitlar):
    try:
        gecici = KUPON_GECMISI_PATH.with_suffix(".tmp")
        gecici.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=2), encoding="utf-8")
        gecici.replace(KUPON_GECMISI_PATH)
        return True
    except Exception:
        return False


def kupon_gecmisine_ekle(secimler, profil, hassasiyet):
    kayitlar = kupon_gecmisini_oku()
    simdi = datetime.now()
    kayit = {
        "kupon_id": simdi.strftime("%Y%m%d%H%M%S%f"),
        "profil": str(profil),
        "hassasiyet": (
            round(float(hassasiyet), 2)
            if isinstance(hassasiyet, (int, float))
            else str(hassasiyet)
        ),
        "olusturma_zamani": simdi.isoformat(timespec="seconds"),
        "secimler": secimler,
    }
    kayitlar.insert(0, kayit)
    kupon_gecmisini_yaz(kayitlar[:200])
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
        "sport_key": m.get("sport_key", ""),
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


TAKIM_ADI_ALIASLARI = {
    # Türkiye
    "istanbulbasaksehir": "basaksehir",
    "istanbulbuyuksehirbelediyesi": "basaksehir",
    "istanbulbb": "basaksehir",
    "buyuksehyr": "basaksehir",       # football-data'nın eski kısa adı
    "gencbirligi": "genclerbirligi",
    "genclerbirligi": "genclerbirligi",
    "kasimpasa": "kasimpasa",
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
    tarih = m_row.get("zaman", m_row.get("Date", datetime.now()))
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

def hesapla(b_df, m_row, tolerans, sadece_ayni_lig=False, form_aktif=False, kalibrasyon_aktif=False, form_profili_override=None):
    # Form, oran eşleşmesi yapılmadan önceki tarihsel takım maçlarından hesaplanır.
    form_kaynagi = ayni_lig_gecmisi(b_df, m_row, sadece_ayni_lig)
    b_df = form_kaynagi
    if b_df.empty:
        return None, b_df
    rehber = tolerans_rehberi(float(tolerans))
    onerilen_min_mac = dinamik_min_mac(float(tolerans))

    # Güncel oranı geçmişte mümkünse gerçek kapanış (C) oranlarıyla karşılaştır.
    # Eski sezonlarda closing sütunu yoksa futbol_veri_motoru REF_* için pre-closing oranına düşer.
    ref_h = "REF_H" if "REF_H" in b_df.columns else "B365H"
    ref_d = "REF_D" if "REF_D" in b_df.columns else "B365D"
    ref_a = "REF_A" if "REF_A" in b_df.columns else "B365A"
    b = b_df[
        (b_df[ref_h].between(m_row["h"] - tolerans, m_row["h"] + tolerans)) &
        (b_df[ref_d].between(m_row["b"] - tolerans, m_row["b"] + tolerans)) &
        (b_df[ref_a].between(m_row["a"] - tolerans, m_row["a"] + tolerans))
    ].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A",
              "REF_H", "REF_D", "REF_A"]:
        if c in b.columns:
            b[c] = pd.to_numeric(b[c], errors="coerce")

    required_odds = [c for c in [ref_h, ref_d, ref_a] if c in b.columns]
    b = b.dropna(subset=["FTHG", "FTAG", "HTHG", "HTAG", *required_odds, "FTR", "HTR"])
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

    # Karşıt marketler önce kendi aileleri içinde yarıştırılır. Böylece örneğin
    # KG Yok %72 iken KG Var %63 resmî ana tahmin olarak kalamaz.
    def _adj(raw, bias, label):
        return min(float(raw) * guven_carpani * bias * form_market_carpani(label, form_profili), 0.99)

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
    belirsiz = (max(ms1_raw, msx_raw, ms2_raw) < 0.42 and (ms_sorted[0] - ms_sorted[1]) < 0.06) or (abs(ms1_raw - ms2_raw) < 0.05 and abs(ms1_raw - msx_raw) < 0.05)

    cands = [ms_best, ou_best, kg_best]
    net_cands = [c for c in cands if not c.get("aile_belirsiz")]
    # Mümkünse karşıt tarafları birbirine çok yakın olan market ailesini ana tahmin yapma.
    secim_havuzu = net_cands or cands
    best = max(secim_havuzu, key=lambda x: (x["conf_prob"], x["raw_prob"]))
    best_conf, fake_drop = fake_confidence_duzelt(best["conf_prob"], sample, float(tolerans))

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
        alt_conf, _ = fake_confidence_duzelt(alt["conf_prob"], sample, float(tolerans))
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
        combo_conf = min(combo_raw * guven_carpani * combo_bias * form_market_carpani(combo_label, form_profili), 0.99)
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
        htft_conf = min(float(htft_raw_prob) * guven_carpani * combo_bias * form_market_carpani(f"HT/FT {htft_label}", form_profili), 0.99)
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
        "playable_score": playable_score,
        "ana_raw_p": ana_raw_p,
        "ana_odd": ana_odd,
        "odds_h": round(oran_ev, 3),
        "odds_d": round(oran_ber, 3),
        "odds_a": round(oran_dep, 3),
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
        "ms_p": int(round(ms_raw * guven_carpani * ms_bias * form_market_carpani(ms_side, form_profili) * 100)),
        "ms_mod": ms_mod,
        "ms1_p": int(round(ms1_raw * guven_carpani * ms_bias * form_market_carpani("MS 1", form_profili) * 100)),
        "msx_p": int(round(msx_raw * guven_carpani * ms_bias * form_market_carpani("Beraberlik", form_profili) * 100)),
        "ms2_p": int(round(ms2_raw * guven_carpani * ms_bias * form_market_carpani("MS 2", form_profili) * 100)),
        "ms25_p": int(round(ms25_raw * guven_carpani * goal_bias * form_market_carpani("2.5 Üst", form_profili) * 100)),
        "ms25a_p": int(round((1 - ms25_raw) * guven_carpani * goal_bias * form_market_carpani("2.5 Alt", form_profili) * 100)),
        "ms15_p": int(round(ms15_raw * guven_carpani * goal_bias * 100)),
        "ms35_p": int(round(ms35_raw * guven_carpani * goal_bias * form_market_carpani("3.5 Üst", form_profili) * 100)),
        "kg_var_p": int(round(kg_raw * guven_carpani * goal_bias * form_market_carpani("KG Var", form_profili) * 100)),
        "kg_yok_p": int(round((1 - kg_raw) * guven_carpani * goal_bias * form_market_carpani("KG Yok", form_profili) * 100)),
        "iy05_p": int(round(iy05_raw * guven_carpani * goal_bias * form_market_carpani("İY 0.5 Üst", form_profili) * 100)),
        "iy05a_p": int(round((1 - iy05_raw) * guven_carpani * goal_bias * 100)),
        "iy15_p": int(round(iy15_raw * guven_carpani * goal_bias * form_market_carpani("İY 1.5 Üst", form_profili) * 100)),
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
        "form_aktif": bool(form_profili.get("aktif")),
        "form_status": form_profili.get("durum", ""),
        "form_text": form_ozet_yazi(form_profili),
        "form_factor": round(form_market_carpani(ana_label, form_profili), 3),
        "form_ev_puan_orani": round(float(form_profili.get("ev", {}).get("puan_orani", 0.5)) * 100, 1) if form_profili.get("ev") else None,
        "form_dep_puan_orani": round(float(form_profili.get("dep", {}).get("puan_orani", 0.5)) * 100, 1) if form_profili.get("dep") else None,
        "form_farki": round(float(form_profili.get("form_farki", 0.0)), 3),
        "odds_basis": "Güncel/son API oranı",
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
    }

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
        bt = st.session_state.get("backtest_df")
        if isinstance(bt, pd.DataFrame) and not bt.empty:
            try:
                kayitlar = bt[["Tahmin", "Tuttu"]].to_dict("records")
            except Exception:
                kayitlar = []
        else:
            kayitlar = []

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


def hassasiyet_birlesik_hesapla(
    b_df, m_row, min_ornek, sadece_ayni_lig=False, market_gecmis_kayitlari=None
):
    """
    0.00–0.10 sonuçlarını yeni sıralama mantığıyla birleştirir.

    Ana puan:
      - Güven: %80
      - Kararlılık: %20
      - Örnek sayısı: puan vermez; yalnızca yeterlilik şartıdır.
      - Çok az medyan örnekte ayrıca ceza uygulanır.
      - Marketin geçmiş backtest başarısı güvene küçük bir düzeltme yapar.
    """
    market_alanlari = {
        "MS 1": "ms1_p", "Beraberlik": "msx_p", "MS 2": "ms2_p",
        "2.5 Üst": "ms25_p", "2.5 Alt": "ms25a_p",
        "KG Var": "kg_var_p", "KG Yok": "kg_yok_p",
    }

    marketler = {}
    for tol in [round(i / 100, 2) for i in range(11)]:
        tol_t, tol_b = hesapla(
            b_df, m_row, tol, sadece_ayni_lig=sadece_ayni_lig,
            form_aktif=False, kalibrasyon_aktif=False,
        )
        if tol_t is None:
            continue

        ornek = int(tol_t.get("ornek", len(tol_b)) or 0)
        gerekli = max(
            int(min_ornek),
            int(tol_t.get("onerilen_min_mac", dinamik_min_mac(tol)) or 0),
        )

        # Örnek artık puan üretmiyor; yalnızca yeterlilik kapısı.
        if ornek < gerekli:
            continue

        for etiket, alan in market_alanlari.items():
            guven = int(tol_t.get(alan, 0) or 0)
            if guven > 60:
                marketler.setdefault(etiket, []).append({
                    "guven": guven,
                    "ornek": ornek,
                    "gerekli": gerekli,
                    "tol": tol,
                    "t": tol_t,
                    "b": tol_b,
                })

    sirali = []
    for etiket, kayitlar in marketler.items():
        # En az 3 hassasiyette destek görmeyen market birleşik aday olmasın.
        if len(kayitlar) < 3:
            continue

        # Güven ortalaması artık örnek sayısıyla ağırlıklandırılmıyor.
        # Böylece yüksek örnek sayısı dolaylı olarak da puan kazandırmıyor.
        ort_guven = sum(x["guven"] for x in kayitlar) / len(kayitlar)

        ornekler = sorted(x["ornek"] for x in kayitlar)
        orta = len(ornekler) // 2
        medyan_ornek = (
            ornekler[orta]
            if len(ornekler) % 2
            else (ornekler[orta - 1] + ornekler[orta]) / 2
        )

        kararlilik = len(kayitlar) / 11.0 * 100.0

        # Marketin geçmiş başarısı yalnızca küçük bir güven düzeltmesidir.
        duzeltilmis_guven, market_basari, market_adet, market_delta = (
            market_gecmis_guven_duzeltmesi(
                etiket, ort_guven, market_gecmis_kayitlari
            )
        )

        # Birleşik puanda da yalnızca gerçekten tek örnekli yapı cezalandırılır.
        # 2+ örneğe artık düşük örnek cezası uygulanmaz. 0.00 hassasiyetin tek
        # örnek durumu sample_factor_hesapla içinde özellikle muaf tutulur.
        az_ornek_cezasi = 8.0 if medyan_ornek <= 1 else 0.0

        birlesik_puan = (
            duzeltilmis_guven * 0.80
            + kararlilik * 0.20
            - az_ornek_cezasi
        )

        temsilci = max(
            kayitlar,
            key=lambda x: (x["guven"], -x["tol"]),
        )

        sirali.append({
            "label": etiket,
            "guven": int(round(duzeltilmis_guven)),
            "ham_guven": round(ort_guven, 1),
            "puan": round(birlesik_puan, 1),
            "ornek": int(round(medyan_ornek)),
            "kararlilik": len(kayitlar),
            "kararlilik_pct": round(kararlilik, 1),
            "az_ornek_cezasi": az_ornek_cezasi,
            "market_gecmis_basari": round(market_basari, 1) if market_basari is not None else None,
            "market_gecmis_adet": int(market_adet),
            "market_guven_delta": round(market_delta, 2),
            "toleranslar": [f'{x["tol"]:.2f}' for x in kayitlar],
            "temsilci": temsilci,
        })

    sirali.sort(
        key=lambda x: (x["puan"], x["guven"], x["kararlilik"]),
        reverse=True,
    )
    if not sirali:
        return None, pd.DataFrame()

    ana, alt = sirali[0], (sirali[1] if len(sirali) > 1 else None)
    t = dict(ana["temsilci"]["t"])
    b = ana["temsilci"]["b"]

    t.update({
        "ana_label": ana["label"],
        "ana_p": ana["guven"],
        "ana_ham_guven": ana["ham_guven"],
        "ana_odd": market_label_to_odd(m_row, ana["label"]),
        "score": ana["puan"],
        "playable_score": ana["puan"],
        "ornek": int(len(b)),
        "birlesik_ornek_medyan": ana["ornek"],
        "kullanilan_tolerans": float(ana["temsilci"]["tol"]),
        "stability_tols": ana["toleranslar"],
        "stability_count": ana["kararlilik"],
        "stability_pct": ana["kararlilik_pct"],
        "stability_text": " · ".join(ana["toleranslar"]),
        "birlesik_model": True,
        "birlesik_puan": ana["puan"],
        "az_ornek_cezasi": ana["az_ornek_cezasi"],
        "market_gecmis_basari": ana["market_gecmis_basari"],
        "market_gecmis_adet": ana["market_gecmis_adet"],
        "market_guven_delta": ana["market_guven_delta"],
        "puan_formulu": "Güven %80 + Kararlılık %20",
    })

    t["stability_early_tols"] = [
        x for x in ana["toleranslar"] if float(x) <= 0.05
    ]
    t["stability_late_tols"] = [
        x for x in ana["toleranslar"] if float(x) > 0.05
    ]
    t["stability_early_text"] = " · ".join(t["stability_early_tols"])
    t["stability_late_text"] = " · ".join(t["stability_late_tols"])

    renk, badge_cls, badge_lbl = guven_renk(t["ana_p"])
    t["guven_renk"], t["guven_badge_cls"], t["guven_badge_lbl"] = (
        renk, badge_cls, badge_lbl
    )

    if alt:
        t.update({
            "alt_label": alt["label"],
            "alt_p": alt["guven"],
            "alt_ornek": alt["ornek"],
            "alt_puan": alt["puan"],
            "alt_kararlilik": alt["kararlilik"],
            "alt_hassasiyetler": alt["toleranslar"],
            "alt_hassasiyet": float(alt["temsilci"]["tol"]),
            "alt_market_gecmis_basari": alt["market_gecmis_basari"],
            "alt_market_gecmis_adet": alt["market_gecmis_adet"],
        })
    else:
        t.update({
            "alt_label": "",
            "alt_p": 0,
            "alt_ornek": 0,
            "alt_puan": 0,
            "alt_kararlilik": 0,
            "alt_hassasiyetler": [],
            "alt_hassasiyet": None,
            "alt_market_gecmis_basari": None,
            "alt_market_gecmis_adet": 0,
        })

    return t, b.sort_values("Date", ascending=False)

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


def top10_market_adaylari(t):
    """
    Top 10 için gerçek multi-market aday havuzu.
    Sadece MS'e kilitlenmez; MS / Alt-Üst / KG / İlk Yarı / Kombo marketlerini aynı havuza alır.
    Market türüne göre keyfi bonus vermez; Value/Edge yalnızca gerçek MS oranı varsa hafif sinyal olur.
    """
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
        guven = safe_int(guven)
        if not label or label in ["Belirsiz Maç", "Tahmin Zayıf", "None", "-"]:
            return
        if guven < min_guven:
            return
        tip = tip or infer_tip(label)

        # Top 10 Market sayfasındaki market aç/kapat filtreleri.
        # Ana maç analizi tarafını etkilemez; sadece Top 10 aday havuzunu filtreler.
        if not st.session_state.get("top10_filter_ms", True) and tip == "MS":
            return
        if not st.session_state.get("top10_filter_25", True) and (tip == "Alt/Üst" or "2.5" in label):
            return
        if not st.session_state.get("top10_filter_kg", True) and tip == "KG":
            return
        if not st.session_state.get("top10_filter_iy05", True) and label == "İY 0.5 Üst":
            return
        if not st.session_state.get("top10_filter_iy15", True) and label == "İY 1.5 Üst":
            return
        if not st.session_state.get("top10_filter_combo", True) and tip in ["Kombo", "HT/FT"]:
            return

        # İlk yarı marketleri daha volatil olduğu için Top 10/Top 50'ye kontrollü girsin.
        if label == "İY 0.5 Üst":
            if guven < 70:
                return
            if safe_int(t.get("ornek", 0)) < 5:
                return
            if str(t.get("goal_profile", "")) == "Düşük Gollü":
                return

        if label == "İY 1.5 Üst":
            if guven < 55:
                return
            if safe_int(t.get("ornek", 0)) < 5:
                return
            if str(t.get("goal_profile", "")) == "Düşük Gollü":
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


TAHMIN_LOG_PATH = Path(__file__).with_name("vibe_tahmin_sonuclari.json")


def _json_guvenli_deger(value):
    if isinstance(value, dict):
        return {str(k): _json_guvenli_deger(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_guvenli_deger(v) for v in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
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
            tuttu = skor_tahmini_tuttu_mu(secilen.get("tahmin"), ev_gol, dep_gol)
            alternatif_tuttu = skor_tahmini_tuttu_mu(
                secilen.get("alternatif_tahmin"), ev_gol, dep_gol
            )
            secilen.update({
                "durum": "Tamamlandı", "ev_gol": ev_gol, "dep_gol": dep_gol,
                "tuttu": bool(tuttu) if tuttu is not None else None,
                "alternatif_tuttu": bool(alternatif_tuttu) if alternatif_tuttu is not None else None,
                "sonuc_guncelleme": tamamlanan.get("sonuc_guncelleme"),
            })
        secilen["kayit_id"] = anahtar
        sonuc.append(secilen)
    return sonuc


def tahmin_logunu_oku():
    try:
        if TAHMIN_LOG_PATH.exists():
            veri = json.loads(TAHMIN_LOG_PATH.read_text(encoding="utf-8"))
            return tahmin_kayitlarini_tekillestir(veri) if isinstance(veri, list) else []
    except Exception:
        pass
    return []


def tahmin_logunu_yaz(kayitlar):
    try:
        gecici = TAHMIN_LOG_PATH.with_suffix(".tmp")
        gecici.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=2), encoding="utf-8")
        gecici.replace(TAHMIN_LOG_PATH)
        return True
    except Exception:
        return False


def sonuc_takibini_sifirla():
    """Yalnızca Sonuç Takibi kayıtlarını temizler; API anahtarları ve kupon geçmişi korunur."""
    return tahmin_logunu_yaz([])


def tahmin_loguna_baglam_yaz(m, label, baglam):
    """Hesaplanan bağlamı, aynı maç+tahmin kaydına sonuç analizi için snapshot olarak ekler."""
    try:
        kayitlar = tahmin_logunu_oku()
        if not kayitlar or not isinstance(baglam, dict):
            return False
        hedef = str(m.get("match_id") or mac_key(m))
        degisti = False
        for k in kayitlar:
            kid = str(k.get("match_id") or k.get("kayit_id") or "")
            ayni = kid == hedef or (
                takim_adi_norm(k.get("ev")) == takim_adi_norm(m.get("ev"))
                and takim_adi_norm(k.get("dep")) == takim_adi_norm(m.get("dep"))
                and str(k.get("zaman", ""))[:10] == str(m.get("zaman", ""))[:10]
            )
            if not ayni or str(k.get("tahmin", "")).strip() != str(label or "").strip():
                continue
            k["baglam_ayari"] = float(baglam.get("toplam", 0.0) or 0.0)
            k["baglam_kaynak"] = str(baglam.get("kaynak", ""))
            k["baglam_snapshot"] = baglam
            k["baglam_kaydedildi"] = datetime.now().isoformat(timespec="seconds")
            degisti = True
        return tahmin_logunu_yaz(kayitlar) if degisti else False
    except Exception:
        return False


def analiz_tahminlerini_kaydet(final):
    """Aynı maç için maç başlamadan önceki en yüksek güvenli tek tahmini saklar."""
    kayitlar = tahmin_logunu_oku()
    mevcut = {tahmin_kaydi_mac_anahtari(x): x for x in kayitlar}
    for item in final:
        m, t = item.get("m", {}), item.get("t", {})
        label = str(t.get("ana_label", ""))
        if not label or label in ["Belirsiz Maç", "Tahmin Zayıf"]:
            continue
        zaman = m.get("zaman")
        zaman_iso = zaman.isoformat() if hasattr(zaman, "isoformat") else str(zaman)
        mac_anahtari = str(m.get("match_id") or mac_key(m))
        eski = mevcut.get(mac_anahtari, {})
        aday = {
            "kayit_id": mac_anahtari,
            "match_id": str(m.get("match_id", "")),
            "sport_key": str(m.get("sport_key", "")),
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
            "kaydedildi": eski.get("kaydedildi", datetime.now().isoformat(timespec="seconds")),
            "durum": eski.get("durum", "Bekliyor"),
            "ev_gol": eski.get("ev_gol"),
            "dep_gol": eski.get("dep_gol"),
            "tuttu": eski.get("tuttu"),
            "alternatif_tuttu": eski.get("alternatif_tuttu"),
            "sonuc_guncelleme": eski.get("sonuc_guncelleme"),
            "detay_snapshot": detay_snapshot_olustur(m, t, item.get("b")),
        }
        # Sonuçlanmış ana tahmin dondurulur; yeni tarama yalnızca eksik/daha
        # güçlü alternatif bilgisini tamamlayabilir.
        if eski.get("durum") == "Tamamlandı":
            secilen = dict(eski)
            if aday.get("detay_snapshot", {}).get("b"):
                secilen["detay_snapshot"] = aday["detay_snapshot"]
            alt_etiket, alt_guven, alt_oran = _en_iyi_alternatif(
                secilen.get("tahmin"), [eski, aday]
            )
            secilen["alternatif_tahmin"] = alt_etiket
            secilen["alternatif_guven"] = alt_guven
            secilen["alternatif_oran"] = alt_oran
            if secilen.get("ev_gol") is not None and secilen.get("dep_gol") is not None:
                alt_tuttu = skor_tahmini_tuttu_mu(
                    alt_etiket, int(secilen["ev_gol"]), int(secilen["dep_gol"])
                )
                secilen["alternatif_tuttu"] = bool(alt_tuttu) if alt_tuttu is not None else None
            mevcut[mac_anahtari] = secilen
            continue
        if not eski or _tahmin_kaydi_sirasi(aday) > _tahmin_kaydi_sirasi(eski):
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
    return tahmin_logunu_yaz(tahmin_kayitlarini_tekillestir(list(mevcut.values())))


def skor_tahmini_tuttu_mu(label, ev_gol, dep_gol):
    toplam = ev_gol + dep_gol
    return {
        "MS 1": ev_gol > dep_gol,
        "Beraberlik": ev_gol == dep_gol,
        "MS 2": dep_gol > ev_gol,
        "2.5 Üst": toplam >= 3,
        "2.5 Alt": toplam <= 2,
        "KG Var": ev_gol > 0 and dep_gol > 0,
        "KG Yok": ev_gol == 0 or dep_gol == 0,
    }.get(str(label))


def takim_anahtari(ad):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(ad)).encode("ascii", "ignore").decode().lower())


def tahmin_sonuclarini_guncelle(api_key):
    """Odds API skorlarından son üç gündeki tamamlanan takip kayıtlarını günceller."""
    kayitlar = tahmin_logunu_oku()
    bekleyen = [x for x in kayitlar if x.get("durum") != "Tamamlandı"]
    ligler = sorted({x.get("sport_key") for x in bekleyen if x.get("sport_key")})
    skorlar = []
    hata = None
    for lig in ligler:
        try:
            skor_url = f"https://api.the-odds-api.com/v4/sports/{lig}/scores/"
            skor_param = {"apiKey": api_key, "daysFrom": 3, "dateFormat": "iso"}
            r = requests.get(skor_url, params=skor_param, timeout=15)
            # Oturumda kalmış anahtar geçersizse ve uygulamada farklı bir secret
            # anahtar varsa sonuç takibini onunla bir kez daha dene.
            if r.status_code == 401:
                yedek_key = str(get_secret_value("ODDS_API_KEY", "") or "").strip()
                if yedek_key and yedek_key != str(api_key).strip():
                    skor_param["apiKey"] = yedek_key
                    r = requests.get(skor_url, params=skor_param, timeout=15)
            if r.status_code == 200 and isinstance(r.json(), list):
                skorlar.extend(r.json())
            elif r.status_code == 401:
                hata = "Odds API anahtarı geçersiz, süresi dolmuş veya aktif değil. Sol menüden anahtarı yeniden gir."
            else:
                hata = f"Skor servisi HTTP {r.status_code} yanıtı verdi."
        except Exception as exc:
            hata = f"Skorlar alınamadı: {exc}"

    id_map = {str(x.get("id", "")): x for x in skorlar if x.get("id")}
    ad_map = {
        (takim_anahtari(x.get("home_team")), takim_anahtari(x.get("away_team"))): x
        for x in skorlar
    }
    guncellenen = 0
    for kayit in kayitlar:
        if kayit.get("durum") == "Tamamlandı":
            continue
        mac = id_map.get(str(kayit.get("match_id", "")))
        if mac is None:
            mac = ad_map.get((takim_anahtari(kayit.get("ev")), takim_anahtari(kayit.get("dep"))))
        if not mac or not mac.get("completed") or not mac.get("scores"):
            continue
        puanlar = {takim_anahtari(x.get("name")): x.get("score") for x in mac.get("scores", [])}
        try:
            ev_gol = int(puanlar[takim_anahtari(kayit.get("ev"))])
            dep_gol = int(puanlar[takim_anahtari(kayit.get("dep"))])
        except (KeyError, TypeError, ValueError):
            continue
        tuttu = skor_tahmini_tuttu_mu(kayit.get("tahmin"), ev_gol, dep_gol)
        if tuttu is None:
            continue
        kayit.update({
            "durum": "Tamamlandı", "ev_gol": ev_gol, "dep_gol": dep_gol,
            "tuttu": bool(tuttu), "sonuc_guncelleme": datetime.now().isoformat(timespec="seconds"),
            "alternatif_tuttu": (
                bool(skor_tahmini_tuttu_mu(kayit.get("alternatif_tahmin"), ev_gol, dep_gol))
                if skor_tahmini_tuttu_mu(kayit.get("alternatif_tahmin"), ev_gol, dep_gol) is not None
                else None
            ),
        })
        guncellenen += 1
    tahmin_logunu_yaz(kayitlar)
    return guncellenen, hata


def tahmini_mac_dakikasi(baslangic, simdi=None):
    """Başlangıç saatinden yaklaşık futbol dakikası üretir; API gerçek dakika sağlamaz."""
    simdi = simdi or (datetime.utcnow() + timedelta(hours=3))
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

    simdi = datetime.utcnow() + timedelta(hours=3)
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
        if simdi < baslangic or simdi > baslangic + timedelta(hours=3):
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
                         kupon_profili=None, tum_marketler=False):
    """
    Top10 / Top50 özel liste üretici.

    ÖNEMLİ:
    Bu fonksiyon sidebar'daki hassasiyet slider'ına bağlı çalışmaz.
    Her maç için 0.00 - 0.10 aralığını 0.01 adımlarla tarar ve aynı maç + aynı market
    kaç farklı hassasiyette çıkıyorsa bunu stabilite skoru olarak kullanır.

    Böylece slider 0.05 / 0.08 / 0.10 değişince Top10/Top50 listesi zıplamaz.
    """
    top_toleranslar = [round(i / 100, 2) for i in range(11)]
    adaylar = []

    if gecmis_df is None or bulten_df is None:
        return []
    if getattr(gecmis_df, "empty", True) or getattr(bulten_df, "empty", True):
        return []

    min_ornek_val = max(1, int(min_ornek or 1))

    for _, m in bulten_df.iterrows():
        # Aynı maç içinde market bazlı gruplama:
        # Örnek: Arsenal - Chelsea / 2.5 Üst
        # 0.01, 0.02, 0.03 ... 0.10 noktalarında çıkıyorsa stabil sayılır.
        market_gruplari = {}

        for tol in top_toleranslar:
            try:
                t, b_det = hesapla(gecmis_df, m, tol, sadece_ayni_lig=sadece_ayni_lig)
            except Exception:
                continue

            if t is None or t.get("belirsiz"):
                continue

            ornek = int(t.get("ornek", 0) or 0)
            if ornek < min_ornek_val:
                continue

            marketler = top10_market_adaylari(t)
            if not marketler:
                continue

            tol_ceza = round(float(tol) * 100, 1)
            dusuk_tol_bonus = 8 if tol <= 0.02 else 5 if tol <= 0.04 else 2 if tol <= 0.06 else 0
            risk_ceza = 8 if t.get("risk_label") == "YÜKSEK" else 3 if t.get("risk_label") == "ORTA" else 0
            fake_ceza = 5 if t.get("fake_drop") else 0
            sample_bonus = min(ornek, 25) * 0.25
            playable = float(t.get("playable_score", 0) or 0)

            for mk in marketler:
                label = str(mk.get("label", "")).strip()
                tip = str(mk.get("tip", "")).strip()
                if not label:
                    continue
                if kupon_modu and not kupon_marketi_uygun(label):
                    continue

                guven = int(mk.get("guven", 0) or 0)

                # Tek toleranstaki ham skor.
                # Kalibre Value/Edge bu aşamada yalnızca ölçülür; Top 50 skorunu etkilemez.
                tekil_skor = (
                    guven * 1.00
                    + playable * 0.22
                    + sample_bonus
                    + float(mk.get("bonus", 0) or 0)
                    + dusuk_tol_bonus
                    - tol_ceza
                    - risk_ceza
                    - fake_ceza
                )

                grup_key = f"{label}|{tip}"
                if grup_key not in market_gruplari:
                    market_gruplari[grup_key] = {
                        "label": label,
                        "tip": tip,
                        "kayitlar": [],
                    }

                t_secili = t.copy()
                t_secili["top10_market_label"] = label
                t_secili["top10_market_tip"] = tip
                t_secili["top10_market_guven"] = guven
                t_secili["top10_market_oran"] = mk.get("oran")
                t_secili["top10_market_oran_tahmini"] = bool("+" in label and mk.get("oran") is not None)

                # Detay ekranı ve kartlar seçilen marketi ana tahmin gibi gösterebilsin.
                t_secili["ana_label"] = label
                t_secili["ana_p"] = guven
                # Seçilen marketin gerçek oranı yoksa önceki ana marketin
                # 1/X/2 oranını yanlışlıkla kombinasyon oranı gibi taşıma.
                t_secili["ana_odd"] = mk.get("oran")

                market_gruplari[grup_key]["kayitlar"].append({
                    "tol": round(float(tol), 2),
                    "skor": round(float(tekil_skor), 2),
                    "guven": guven,
                    "ornek": ornek,
                    "t": t_secili,
                    "b": b_det,
                    "mk": mk,
                })

        if not market_gruplari:
            continue

        en_iyi = None
        mac_adaylari = []

        for _, grup in market_gruplari.items():
            kayitlar = grup["kayitlar"]
            if not kayitlar:
                continue

            hassasiyetler = sorted({k["tol"] for k in kayitlar})
            stabilite_sayisi = len(hassasiyetler)

            # Aynı market birden fazla hassasiyette çıkıyorsa ciddi bonus.
            # 11/11 çıkan market Top10/Top50'de en stabil kabul edilir.
            stabilite_orani = stabilite_sayisi / max(len(top_toleranslar), 1)
            stabilite_bonus = stabilite_sayisi * (45.0 / 11.0)

            max_skor = max(float(k["skor"]) for k in kayitlar)
            ort_skor = sum(float(k["skor"]) for k in kayitlar) / len(kayitlar)
            max_guven = max(int(k["guven"]) for k in kayitlar)
            ort_guven = sum(int(k["guven"]) for k in kayitlar) / len(kayitlar)
            max_ornek = max(int(k["ornek"]) for k in kayitlar)

            # Stabilite odaklı final skor:
            # - Sadece tek toleransta patlayan adaylar geriye düşer.
            # - Birkaç hassasiyette sürekli çıkan adaylar öne gelir.
            stabilite_skoru = (
                max_skor * 0.55
                + ort_skor * 0.30
                + ort_guven * 0.10
                + min(max_ornek, 30) * 0.15
                + stabilite_bonus
            )

            # Kupon modunda herhangi bir toleransta yüksek güven bulan marketi
            # sırf diğer toleranslarda tekrarlanmadı diye kaybetme. Bu bonus
            # 0.00 dahil taranan bütün hassasiyetlere eşit uygulanır.
            tekil_yuksek_guven = kupon_modu and max_guven >= 70
            if tekil_yuksek_guven:
                stabilite_skoru += 30 + (max_guven - 70) * 3

            # Her profil aynı kuponu üretmesin: Temkinli güven/kararlılığı,
            # Dengeli market çeşitliliğini, Yüksek Oran ise kombinasyonları
            # ve oran potansiyelini farklı ağırlıklarla değerlendirir.
            if kupon_modu:
                etiket = str(grup.get("label", ""))
                kombinasyon = "+" in etiket
                if kupon_profili == "Temkinli":
                    stabilite_skoru += max_guven * 0.18 + stabilite_sayisi * (15.0 / 11.0)
                    if kombinasyon:
                        stabilite_skoru -= 9
                    elif etiket in {"MS 1", "MS1", "Beraberlik", "MS X", "MSX", "MS 2", "MS2"}:
                        stabilite_skoru += 12
                elif kupon_profili == "Dengeli":
                    if "KG" in etiket or "2.5" in etiket:
                        stabilite_skoru += 10
                    if kombinasyon:
                        stabilite_skoru += 7
                elif kupon_profili == "Yüksek Oran":
                    if kombinasyon:
                        stabilite_skoru += 42
                    elif "KG" in etiket or "2.5" in etiket:
                        stabilite_skoru += 14

            # Tek hassasiyette çıkan ama skoru çok yüksek olanları biraz törpüle.
            if stabilite_sayisi <= 2 and not tekil_yuksek_guven:
                stabilite_skoru -= 14
            elif stabilite_sayisi <= 4:
                stabilite_skoru -= 5

            # Temsilci kayıt: finalde detay ekranı için en iyi tekil skorun datasını kullan.
            temsilci = max(
                kayitlar,
                key=lambda k: (
                    k["skor"],
                    k["guven"],
                    k["ornek"],
                    -k["tol"],
                )
            )

            t_final = temsilci["t"].copy()
            t_final["top10_hassasiyetler"] = hassasiyetler
            t_final["top10_hassasiyet_sayisi"] = stabilite_sayisi
            t_final["top10_stabilite_skoru"] = round(stabilite_skoru, 1)
            t_final["top10_stabilite_orani"] = round(stabilite_orani * 100, 0)
            t_final["stability_tols"] = [f"{x:.2f}" for x in hassasiyetler]
            t_final["stability_count"] = stabilite_sayisi
            t_final["stability_early_tols"] = [f"{x:.2f}" for x in hassasiyetler if x <= 0.05]
            t_final["stability_late_tols"] = [f"{x:.2f}" for x in hassasiyetler if x > 0.05]
            t_final["hassasiyet_taramali"] = True

            aday = {
                "m": m.to_dict(),
                "t": t_final,
                "b": temsilci["b"],
                "top10_tol": round(float(temsilci["tol"]), 2),
                "top10_skor": round(stabilite_skoru, 1),
                "top10_market": temsilci["mk"],
                "top10_hassasiyetler": hassasiyetler,
                "top10_hassasiyet_sayisi": stabilite_sayisi,
                "top10_stabilite_skoru": round(stabilite_skoru, 1),
                "top10_stabilite_orani": round(stabilite_orani * 100, 0),
            }
            aday["m"]["durum"] = mac_canli_durumu(aday["m"].get("zaman"))

            if tum_marketler:
                # "Tüm aday listeleri" görünümünde maçın yalnızca tek marketini
                # seçme; profil koşullarını geçebilecek bütün güçlü marketleri taşı.
                mac_adaylari.append(aday)
            elif en_iyi is None or aday["top10_skor"] > en_iyi["top10_skor"]:
                en_iyi = aday

        if tum_marketler:
            adaylar.extend(mac_adaylari)
        elif en_iyi:
            adaylar.append(en_iyi)

    adaylar.sort(
        key=lambda x: (
            x.get("top10_stabilite_skoru", x.get("top10_skor", 0)),
            x.get("top10_hassasiyet_sayisi", 0),
            x.get("t", {}).get("top10_market_guven", 0),
            x.get("t", {}).get("ornek", 0),
        ),
        reverse=True,
    )

    # Tüm profil adayları görünümünde çeşitlilik kotası uygulama.
    # Amaç maçın profil kriterini karşılayan bütün marketlerini kullanıcıya göstermek.
    if tum_marketler:
        if limit is None or int(limit or 0) <= 0:
            return adaylar
        return adaylar[:int(limit)]

    # Top 10 sadece MS1/MS2 dolmasın diye küçük çeşitlilik kuralı.
    # Top50 için limit yüksek olduğundan aynı kural listeyi boğmaz.
    secilen = []
    ms_sayisi = 0
    max_ms = 4 if int(limit or 10) <= 10 else 18

    for item in adaylar:
        tip = str(item.get("t", {}).get("top10_market_tip", ""))
        if tip == "MS" and ms_sayisi >= max_ms:
            continue
        secilen.append(item)
        if tip == "MS":
            ms_sayisi += 1
        if len(secilen) >= limit:
            break

    # Eğer yeterli aday dolmadıysa kalanları sıralamadan tamamla.
    if len(secilen) < limit:
        used = {mac_key(x.get("m", {})) + str(x.get("t", {}).get("top10_market_label", "")) for x in secilen}
        for item in adaylar:
            k = mac_key(item.get("m", {})) + str(item.get("t", {}).get("top10_market_label", ""))
            if k in used:
                continue
            secilen.append(item)
            if len(secilen) >= limit:
                break

    return secilen[:limit]


def tahmin_tuttu_mu(label, row):
    toplam_gol = float(row["FTHG"]) + float(row["FTAG"])
    kg_var = float(row["FTHG"]) > 0 and float(row["FTAG"]) > 0
    return {
        "MS 1": row["FTR"] == "H",
        "Beraberlik": row["FTR"] == "D",
        "MS 2": row["FTR"] == "A",
        "2.5 Üst": toplam_gol >= 3,
        "2.5 Alt": toplam_gol <= 2,
        "KG Var": kg_var,
        "KG Yok": not kg_var,
    }.get(str(label))


def backtest_calistir(gecmis_df, test_sezonu, tolerans, min_ornek,
                      sadece_ayni_lig=False, lig_kodlari=None, max_test=500,
                      birlesik_hassasiyet=False):
    """Her maçı yalnızca daha eski maçlarla analiz eden tarih sıralı backtest."""
    if gecmis_df is None or gecmis_df.empty:
        return pd.DataFrame()

    veri = gecmis_df.copy()
    veri["Date"] = pd.to_datetime(veri["Date"], errors="coerce")
    veri = veri.dropna(subset=["Date", "FTHG", "FTAG", "FTR"])
    # Aynı karşılaşma veri birleşiminde birden fazla kez geldiyse tek maç say.
    veri = veri.sort_values("Date").drop_duplicates(
        subset=["Date", "league_code", "HomeTeam", "AwayTeam"], keep="last"
    )
    test = veri[veri["season_code"].astype(str) == str(test_sezonu)].copy()
    if lig_kodlari:
        test = test[test["league_code"].isin(set(lig_kodlari))]
    test = test.sort_values("Date").tail(int(max_test))

    sonuclar = []
    for _, row in test.iterrows():
        train = veri[veri["Date"] < row["Date"]]
        if sadece_ayni_lig:
            train = train[train["league_code"] == row["league_code"]]
        if train.empty:
            continue

        hedef = {
            "h": row["B365H"], "b": row["B365D"], "a": row["B365A"],
            "ev": row.get("HomeTeam", ""), "dep": row.get("AwayTeam", ""),
            "zaman": row["Date"],
        }
        # Aynı maç için hem güncel-formlu hem formsuz model çalıştırılır.
        # İkisi de yalnızca row["Date"] öncesindeki train verisini görür.
        if birlesik_hassasiyet:
            t, benzerler = hassasiyet_birlesik_hesapla(
                train, hedef, min_ornek, sadece_ayni_lig=False,
                market_gecmis_kayitlari=sonuclar,
            )
        else:
            t, benzerler = hesapla(train, hedef, tolerans, form_aktif=False, kalibrasyon_aktif=False)
        if t is None or len(benzerler) < int(min_ornek):
            continue

        # Backtest yalnızca %60'ın ÜSTÜNDE güvene sahip tahminleri değerlendirir.
        # %60 tam değer dahil değildir; %61 ve üzeri kabul edilir.
        if int(t.get("ana_p", 0) or 0) <= 60:
            continue

        label = t.get("ana_label", "")
        tuttu = tahmin_tuttu_mu(label, row)
        if tuttu is None:
            continue

        oran = market_label_to_odd(hedef, label)
        alternatif_label = str(t.get("alt_label", "") or "")
        alternatif_guven = int(t.get("alt_p", 0) or 0)
        alternatif_tuttu = (
            tahmin_tuttu_mu(alternatif_label, row)
            if alternatif_label and alternatif_guven > 60
            else None
        )
        kar = None
        if oran is not None:
            kar = round((float(oran) - 1) * 100 if tuttu else -100, 2)

        sonuc_kaydi = {
            "Tarih": row["Date"].date(),
            "Lig": row.get("league_code", "-"),
            "Maç": f"{row.get('HomeTeam', '')} - {row.get('AwayTeam', '')}",
            "Tahmin": label,
            "Güven": int(t.get("ana_p", 0)),
            "Ana Puan": float(t.get("birlesik_puan", t.get("score", 0)) or 0),
            "Ana Medyan Örnek": int(t.get("birlesik_ornek_medyan", t.get("ornek", 0)) or 0),
            "Ana Kararlılık": int(t.get("stability_count", 0) or 0),
            "Ana Hassasiyetler": " · ".join(t.get("stability_tols", []) or []),
            "Alternatif Tahmin": alternatif_label if alternatif_guven > 60 else "",
            "Alt. Güven": alternatif_guven if alternatif_guven > 60 else None,
            "Alt. Örnek": int(t.get("alt_ornek", 0) or 0) if alternatif_guven > 60 else None,
            "Alt. Puan": float(t.get("alt_puan", 0) or 0) if alternatif_guven > 60 else None,
            "Alt. Kararlılık": int(t.get("alt_kararlilik", 0) or 0) if alternatif_guven > 60 else None,
            "Alt. Hassasiyetler": " · ".join(t.get("alt_hassasiyetler", []) or []) if alternatif_guven > 60 else "",
            "Alt. Tuttu": bool(alternatif_tuttu) if alternatif_tuttu is not None else None,
            "Örnek": int(t.get("ornek", 0)),
            "Sonuç": f"{int(row['FTHG'])}-{int(row['FTAG'])}",
            "Tuttu": bool(tuttu),
            "Oran": round(float(oran), 2) if oran is not None else None,
            "Kâr (100 TL)": kar,
        }
        sonuclar.append(sonuc_kaydi)
    sonuc_df = pd.DataFrame(sonuclar)
    if sonuc_df.empty:
        return sonuc_df
    # Güven eşitse daha çok örneği olan tahmin resmî kayıt olur.
    sonuc_df = sonuc_df.sort_values(["Güven", "Örnek"], ascending=[False, False])
    return sonuc_df.drop_duplicates(subset=["Tarih", "Lig", "Maç"], keep="first").sort_values("Tarih")



def backtest_11_hassasiyet_calistir(gecmis_df, test_sezonu, secili_tolerans, min_ornek,
                                    sadece_ayni_lig=False, lig_kodlari=None, max_test=500):
    """0.00–0.10 arasındaki 11 toleransı tek kronolojik geçişte test eder.
    Form ve Value/Edge kullanılmaz.
    """
    toleranslar = [round(i / 100.0, 2) for i in range(11)]
    # Her toleransı aynı tarih sıralı backtest mantığıyla çalıştır.
    # Özet sade tutulur; hiçbir hassasiyet otomatik sabitlenmez.
    satirlar = []
    secili_df = None
    for tol in toleranslar:
        bt = backtest_calistir(
            gecmis_df, test_sezonu, tol, min_ornek,
            sadece_ayni_lig=sadece_ayni_lig,
            lig_kodlari=lig_kodlari,
            max_test=max_test,
        )
        if bt is None or bt.empty:
            satirlar.append({
                "Hassasiyet": f"{tol:.2f}", "Tahmin": 0,
                "Başarı %": None, "MS Tahmin": 0, "MS ROI %": None,
            })
            continue
        toplam = len(bt)
        basari = float(bt["Tuttu"].astype(bool).mean() * 100.0)
        ms = bt[bt["Kâr (100 TL)"].notna()].copy()
        ms_roi = float(ms["Kâr (100 TL)"].sum()) / (len(ms) * 100.0) * 100.0 if len(ms) else None
        satirlar.append({
            "Hassasiyet": f"{tol:.2f}",
            "Tahmin": int(toplam),
            "Başarı %": round(basari, 1),
            "MS Tahmin": int(len(ms)),
            "MS ROI %": round(ms_roi, 1) if ms_roi is not None else None,
        })
    # Ana backtest, canlı analizde kullanılan birleşik 0.00–0.10 modelidir.
    # Üstteki 11 satır tekil hassasiyetleri yalnızca karşılaştırma için gösterir.
    secili_df = backtest_calistir(
        gecmis_df, test_sezonu, secili_tolerans, min_ornek,
        sadece_ayni_lig=sadece_ayni_lig,
        lig_kodlari=lig_kodlari, max_test=max_test,
        birlesik_hassasiyet=True,
    )
    return pd.DataFrame(satirlar), secili_df


def gecmis_ornekleri_bul(gecmis_df, m_row, tolerans, sadece_ayni_lig=False,
                         filtre_12=False, filtre_21=False, filtre_cift_yari_kg=False,
                         limit=25):
    """Bir güncel maç için benzer oranlı geçmiş maçları ve özel senaryoları getirir."""
    kaynak = ayni_lig_gecmisi(gecmis_df, m_row, sadece_ayni_lig)
    if kaynak.empty:
        return pd.DataFrame()

    b = kaynak[
        kaynak[("REF_H" if "REF_H" in kaynak.columns else "B365H")].between(float(m_row["h"]) - tolerans, float(m_row["h"]) + tolerans)
        & kaynak[("REF_D" if "REF_D" in kaynak.columns else "B365D")].between(float(m_row["b"]) - tolerans, float(m_row["b"]) + tolerans)
        & kaynak[("REF_A" if "REF_A" in kaynak.columns else "B365A")].between(float(m_row["a"]) - tolerans, float(m_row["a"]) + tolerans)
    ].copy()
    gerekli = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG", "FTR", "HTR"]
    if b.empty or any(c not in b.columns for c in gerekli):
        return pd.DataFrame()
    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")
    b = b.dropna(subset=gerekli + ["B365H", "B365D", "B365A"])

    b["olay_12"] = (b["HTR"] == "H") & (b["FTR"] == "A")
    b["olay_21"] = (b["HTR"] == "A") & (b["FTR"] == "H")
    ev_ikinci_yari = b["FTHG"] - b["HTHG"]
    dep_ikinci_yari = b["FTAG"] - b["HTAG"]
    b["olay_cift_yari_kg"] = (
        (b["HTHG"] > 0) & (b["HTAG"] > 0)
        & (ev_ikinci_yari > 0) & (dep_ikinci_yari > 0)
    )

    secili_maskeler = []
    if filtre_12:
        secili_maskeler.append(b["olay_12"])
    if filtre_21:
        secili_maskeler.append(b["olay_21"])
    if filtre_cift_yari_kg:
        secili_maskeler.append(b["olay_cift_yari_kg"])
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
        aktif_hassasiyet = float(TOLERANS or 0.0)
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

    def olay_renk(value):
        metin = str(value)
        if "İki yarıda da KG" in metin:
            return "background-color:#6b21a8;color:#faf5ff;font-weight:900"
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
    olay_kolonlari = [c for c in ["Özel olay", "Yüksek oran olayı"] if c in tablo.columns]
    if olay_kolonlari:
        stil = stil.map(olay_renk, subset=olay_kolonlari)
    return stil


def yuksek_oran_istatistikleri(tum_ornekler, filtre_12=True, filtre_21=True,
                               filtre_cift_yari_kg=True):
    """Nadir senaryoları örnek büyüklüğünü de dikkate alarak sıralar."""
    toplam = len(tum_ornekler)
    tanimlar = [
        ("1/2", "olay_12", filtre_12),
        ("2/1", "olay_21", filtre_21),
        ("İki yarıda da KG", "olay_cift_yari_kg", filtre_cift_yari_kg),
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
    ("gecmis_inceleme_list", None),
    ("gecmis_tam_ekran_sira", None),
    ("yuksek_oran_list", None),
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
# Uygulama sunucusu UTC'de çalışsa bile tarih seçimi Türkiye gününe göre yapılır.
try:
    from zoneinfo import ZoneInfo
    sistem_simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
except Exception:
    sistem_simdi = datetime.utcnow() + timedelta(hours=3)
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
    yeni_bugun = (datetime.utcnow() + timedelta(hours=3)).date()
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
        TOLERANS = st.slider(
            "Oran Hassasiyeti",
            0.00, 0.30, 0.08,
            step=0.01,
            key="top_tol",
            on_change=clear_detail_on_filter_change,
            help="Düşük değerler oranı daha yakın maçları; yüksek değerler daha fazla geçmiş örneği kapsar.",
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
                on_change=clear_detail_on_filter_change,
            )

        preset1, preset2, preset3 = st.columns(3, gap="small")
        with preset1:
            if st.button("Hepsini Aç", use_container_width=True, key="preset_all_top"):
                set_leagues(tum_lig_kodlari())
                st.rerun()
        with preset2:
            if st.button("Temizle", use_container_width=True, key="preset_clear_top"):
                clear_leagues()
                st.rerun()
        with preset3:
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
    """Uygulamanın tüm ana Streamlit bileşenlerini seçilen temaya uyarlar."""
    if not koyu_mod:
        return

    st.markdown(
        """
        <style>
        /* === YAPAIKUPON DARK MODE === */
        :root {
            color-scheme: dark;
            --yk-bg:#07111f;
            --yk-bg2:#0a1830;
            --yk-surface:#0b1628;
            --yk-surface2:#0f1b31;
            --yk-card:#111827;
            --yk-border:#284977;
            --yk-border-soft:#1f2a44;
            --yk-text:#f8fafc;
            --yk-muted:#9db2d1;
            --yk-muted2:#cbd5e1;
            --yk-accent:#facc15;
            --yk-blue:#77b4ff;
        }

        html, body, [class*="css"], .stApp,
        [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background:#07111f !important;
            color:#f8fafc !important;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background:linear-gradient(180deg,#07111f 0%,#081426 48%,#0a1830 100%) !important;
        }
        [data-testid="stHeader"] {
            background:rgba(7,17,31,.94) !important;
        }
        .main .block-container, [data-testid="stMainBlockContainer"] {
            background:transparent !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div {
            background:#091526 !important;
            border-color:#223c63 !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] label *,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span:not([data-baseweb="tag"] span),
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {
            color:#9db2d1 !important;
            -webkit-text-fill-color:#9db2d1 !important;
        }

        /* Tema anahtarı */
        .st-key-koyu_mod_toggle {
            background:#0b1628 !important;
            border:1px solid #284977 !important;
            border-radius:12px !important;
            padding:7px 10px 4px 10px !important;
            margin:2px 0 8px 0 !important;
        }
        .st-key-koyu_mod_toggle label,
        .st-key-koyu_mod_toggle label * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            font-weight:800 !important;
        }

        /* Saat kutusu */
        .st-key-sidebar_system_clock {
            background:#0b1628 !important;
            border:1px solid #284977 !important;
            box-shadow:0 4px 14px rgba(0,0,0,.28) !important;
        }
        .st-key-sidebar_system_clock .system-clock-label,
        .st-key-sidebar_system_clock .system-clock-label *,
        .st-key-sidebar_system_clock .system-clock-time {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }

        /* Başlıklar ve açık sayfa metinleri */
        .top-header h2, .list-heading, .panel-title,
        .topbar-wrap h1, .topbar-wrap h2, .topbar-wrap h3,
        [data-testid="stMain"] h1, [data-testid="stMain"] h2,
        [data-testid="stMain"] h3, [data-testid="stMain"] h4,
        [data-testid="stMain"] p, [data-testid="stMain"] label {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        .top-header .sub, .panel-date, .summary-note, .list-subheading,
        .control-label, .section-kicker, .league-chip-note {
            color:#9db2d1 !important;
            -webkit-text-fill-color:#9db2d1 !important;
        }

        /* Üst filtre/kontrol yüzeyleri */
        .top-shell, .topbar-wrap, .control-card, .metrics-card,
        .helper-bar, .rehber-box, .top-hero {
            background:linear-gradient(180deg,#0b1628 0%,#0a1830 100%) !important;
            border-color:#284977 !important;
            color:#f8fafc !important;
            box-shadow:0 10px 30px rgba(0,0,0,.20) !important;
        }

        /* Inputs / select / multiselect / date / number */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-testid="stNumberInput"] div[data-baseweb="input"] > div,
        div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
        div[data-testid="stDateInput"] div[data-baseweb="input"] > div,
        div[data-testid="stNumberInputContainer"],
        div[data-testid="stTextInputRootElement"],
        textarea, input {
            background:#0f1b31 !important;
            border-color:#284977 !important;
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        div[data-baseweb="select"] *,
        [data-baseweb="popover"] *,
        [role="listbox"] *, [role="option"] * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        [data-baseweb="popover"], [role="listbox"] {
            background:#0b1628 !important;
            border-color:#284977 !important;
        }
        [role="option"]:hover, [aria-selected="true"][role="option"] {
            background:#17304d !important;
        }

        /* Butonlar */
        .stButton > button,
        div[data-testid="stPopover"] button,
        div[data-testid="stPopoverButton"] > button,
        [data-testid="baseButton-secondary"] {
            background:linear-gradient(180deg,#0f1b31 0%,#0b1628 100%) !important;
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            border-color:#315487 !important;
        }
        .stButton > button:hover,
        div[data-testid="stPopoverButton"] > button:hover {
            border-color:#facc15 !important;
            color:#ffffff !important;
        }
        button[kind="primary"], [data-testid="baseButton-primary"] {
            color:#ffffff !important;
            -webkit-text-fill-color:#ffffff !important;
        }

        /* Expanders / radio / checkbox / toggle / tabs */
        div[data-testid="stExpander"],
        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] summary,
        .streamlit-expanderHeader {
            background:linear-gradient(90deg,#0b1628 0%,#0a1830 100%) !important;
            border-color:#284977 !important;
            color:#f8fafc !important;
        }
        div[data-testid="stExpander"] *,
        .stCheckbox label *, .stRadio label *,
        div[data-testid="stToggle"] label * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] button * {
            color:#cbd5e1 !important;
            -webkit-text-fill-color:#cbd5e1 !important;
        }

        /* Metric / info / warning / success alanları */
        [data-testid="stMetric"], [data-testid="metric-container"] {
            background:#0b1628 !important;
            border:1px solid #223c63 !important;
            border-radius:12px !important;
            padding:10px !important;
        }
        [data-testid="stMetric"] *, [data-testid="metric-container"] * {
            color:#f8fafc !important;
        }
        div[data-testid="stAlert"] {
            background:#0b1628 !important;
            border-color:#284977 !important;
            color:#f8fafc !important;
        }
        div[data-testid="stAlert"] * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }

        /* Dataframe / tablo çevresi */
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            background:#0b1628 !important;
            border-radius:12px !important;
            border:1px solid #223c63 !important;
            overflow:hidden !important;
        }
        [data-testid="stDataFrame"] iframe {
            background:#0b1628 !important;
        }
        table, thead, tbody, tr, th, td {
            border-color:#223c63 !important;
        }
        [data-testid="stTable"] table,
        [data-testid="stTable"] th,
        [data-testid="stTable"] td {
            background:#0b1628 !important;
            color:#f8fafc !important;
        }

        /* Uygulamanın kendi kartları */
        .mac-kart, .tahmin-kart, .diger-kart, .neden-kart, .kupon-kart,
        .combo-kart, .canli-kart, .strateji-kart, .oranlar-kart,
        .history-card, .ai-comment, .ai-inline, .coupon-item,
        .recent-match-row, .detail-form-sidebar-title {
            background:linear-gradient(135deg,#0b1628,#111827) !important;
            border-color:#223c63 !important;
            color:#f8fafc !important;
        }
        .mac-kart *, .tahmin-kart *, .diger-kart *, .neden-kart *,
        .kupon-kart *, .combo-kart *, .canli-kart *, .strateji-kart *,
        .oranlar-kart *, .history-card *, .ai-comment *, .ai-inline * {
            color:#f8fafc;
        }
        .history-sub, .mk-mini, .tk-key, .diger-sub, .hb-sub, .hb-label,
        .mk-label, .recent-top {
            color:#9db2d1 !important;
            -webkit-text-fill-color:#9db2d1 !important;
        }

        /* Detay modal */
        div[data-testid="stDialog"] div[role="dialog"] {
            background:linear-gradient(180deg,#07111f 0%,#0a1830 100%) !important;
            border-color:#284977 !important;
        }
        div[data-testid="stDialog"] div[role="dialog"] p,
        div[data-testid="stDialog"] div[role="dialog"] label,
        div[data-testid="stDialog"] div[role="dialog"] h1,
        div[data-testid="stDialog"] div[role="dialog"] h2,
        div[data-testid="stDialog"] div[role="dialog"] h3 {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }

        /* Sidebar özel açık kutular */
        .sidebar-high-market-title {
            background:#102340 !important;
            border-color:#315487 !important;
        }
        .sidebar-high-market-title b {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }
        .sidebar-high-market-title span {
            color:#cbd5e1 !important;
            -webkit-text-fill-color:#cbd5e1 !important;
        }

        /* Linkler / ayraçlar / spinner */
        a { color:#77b4ff !important; }
        hr { border-color:#223c63 !important; }
        div[data-testid="stSpinner"], div[data-testid="stSpinner"] *,
        div[data-testid="stStatusWidget"], div[data-testid="stStatusWidget"] * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }

        /* === DARK MODE OKUNABİLİRLİK FIX: Ana Analiz Ayarları + Görünüm === */
        .st-key-sticky_analysis_controls {
            background:linear-gradient(180deg,#0b1628 0%,#0a1830 100%) !important;
            border-color:#315487 !important;
            box-shadow:0 8px 24px rgba(0,0,0,.30) !important;
        }
        /* Ana analiz panelinde Streamlit'in beyaz iç katmanlarını da kapat */
        .st-key-sticky_analysis_controls > div,
        .st-key-sticky_analysis_controls [data-testid="stVerticalBlock"],
        .st-key-sticky_analysis_controls [data-testid="stHorizontalBlock"],
        .st-key-sticky_analysis_controls [data-testid="column"],
        .st-key-sticky_analysis_controls div[data-testid="stElementContainer"] {
            background:transparent !important;
        }
        .st-key-sticky_analysis_controls {
            background-color:#0b1628 !important;
        }
        .st-key-sticky_analysis_controls .top-analysis-controls b,
        .st-key-sticky_analysis_controls label,
        .st-key-sticky_analysis_controls label *,
        .st-key-sticky_analysis_controls p,
        .st-key-sticky_analysis_controls span,
        .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"],
        .st-key-sticky_analysis_controls [data-testid="stWidgetLabel"] * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            opacity:1 !important;
        }
        .st-key-sticky_analysis_controls [data-testid="stSlider"] label,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] label *,
        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] label,
        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] label *,
        .st-key-sticky_analysis_controls [data-testid="stSelectbox"] label,
        .st-key-sticky_analysis_controls [data-testid="stSelectbox"] label * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            font-weight:800 !important;
        }
        .st-key-sticky_analysis_controls [data-baseweb="select"] > div,
        .st-key-sticky_analysis_controls [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
            background:#0f1b31 !important;
            border-color:#315487 !important;
        }
        .st-key-sticky_analysis_controls [data-baseweb="select"] *,
        .st-key-sticky_analysis_controls input {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
        }

        /* Sidebar Görünüm başlığı ve tüm radio seçenekleri */
        .st-key-sayfa_modu,
        .st-key-sayfa_modu [data-testid="stRadio"] {
            color:#f8fafc !important;
        }
        .st-key-sayfa_modu label,
        .st-key-sayfa_modu label *,
        .st-key-sayfa_modu p,
        .st-key-sayfa_modu span,
        .st-key-sayfa_modu [data-testid="stWidgetLabel"],
        .st-key-sayfa_modu [data-testid="stWidgetLabel"] * {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            opacity:1 !important;
        }
        .st-key-sayfa_modu [role="radiogroup"] label,
        .st-key-sayfa_modu [role="radiogroup"] label *,
        section[data-testid="stSidebar"] .st-key-sayfa_modu [role="radiogroup"] p {
            color:#f8fafc !important;
            -webkit-text-fill-color:#f8fafc !important;
            font-weight:700 !important;
        }

        /* === SLIDER / ANA ANALİZ AYARLARI KOYU MOD NETLİK FIX === */
        .st-key-sticky_analysis_controls .top-analysis-controls,
        .st-key-sticky_analysis_controls .top-analysis-controls *,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] label,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] label *,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stWidgetLabel"],
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stWidgetLabel"] *,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBar"],
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBar"] *,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBarMin"],
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [data-testid="stTickBarMax"],
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"],
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"] * {
            color:#ffffff !important;
            -webkit-text-fill-color:#ffffff !important;
            opacity:1 !important;
        }
        .st-key-sticky_analysis_controls .top-analysis-controls b {
            color:#ffffff !important;
            -webkit-text-fill-color:#ffffff !important;
            text-shadow:0 1px 1px rgba(0,0,0,.35) !important;
        }
        .st-key-sticky_analysis_controls [data-testid="stSlider"] svg,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] button svg,
        .st-key-sticky_analysis_controls [data-testid="stTooltipIcon"] svg {
            color:#f8fafc !important;
            fill:#f8fafc !important;
            stroke:#f8fafc !important;
            opacity:1 !important;
        }
        /* Slider uç değerleri (örn. 0.00 / 0.30) ve aktif değer (örn. 0.02) */
        .st-key-sticky_analysis_controls [data-testid="stSlider"] div,
        .st-key-sticky_analysis_controls [data-testid="stSlider"] span {
            -webkit-text-fill-color:#f8fafc !important;
        }
        .st-key-sticky_analysis_controls [data-testid="stSlider"] [role="slider"] {
            background:#facc15 !important;
            border-color:#ffe27a !important;
        }

        /* Footer */
        [data-testid="stMain"] div[style*="text-align:center"][style*="font-size:12px"] {
            color:#9db2d1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# FİLTRELER ARTIK SOL SIDEBAR İÇİNDE
with st.sidebar:
    with st.container(key="koyu_mod_toggle"):
        koyu_mod = st.toggle("🌙 Koyu Mod", value=bool(st.session_state.get("koyu_mod", True)), key="koyu_mod")
    uygula_tema_css(koyu_mod)
    with st.container(key="sidebar_system_clock"):
        st.markdown(
            """
            <style>
            .st-key-sidebar_system_clock {
                background:#ffffff !important;
                border:1px solid #cbd5e1 !important;
                border-radius:12px !important;
                padding:8px 9px 6px 9px !important;
                margin:2px 0 9px 0 !important;
                box-shadow:0 4px 12px rgba(15,23,42,.08) !important;
            }
            .st-key-sidebar_system_clock .system-clock-label,
            .st-key-sidebar_system_clock .system-clock-label * {
                color:#0f172a !important;
                -webkit-text-fill-color:#0f172a !important;
                opacity:1 !important;
            }
            .st-key-sidebar_system_clock .system-clock-label {
                font-size:.72rem;
                line-height:1.3;
                font-weight:700;
                padding-top:2px;
            }
            .st-key-sidebar_system_clock .system-clock-time {
                display:block;
                margin-top:2px;
                color:#0f172a !important;
                -webkit-text-fill-color:#0f172a !important;
                font-size:.82rem;
                font-weight:900;
            }
            .st-key-sidebar_system_clock button {
                min-height:38px !important;
                color:#ffffff !important;
                -webkit-text-fill-color:#ffffff !important;
                font-weight:800 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
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
    st.caption(f"🧠 Bülten cache: {cache_hazir}/{cache_toplam} lig · 15 dk · {kota_yazi}")
    if st.button(
        "🔄 Oranları Yenile",
        use_container_width=True,
        key="oranlari_zorla_yenile_btn",
        help="Yalnızca seçili liglerin oranlarını yeniden API'den çeker. Normal analizlerde 15 dakikalık cache kullanılır.",
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
        ["Maç Analizi", "Top 50 Market", "Geçmiş Örnekleri", "Yüksek Oran Filtresi", "Canlı Takip", "Sonuç Takibi", "Backtest"],
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

        # Alt satır: 3 filtre
        c_iy05, c_iy15, c_combo = st.columns([1, 1, 1], gap="small")
        with c_iy05:
            st.checkbox("İY 0.5", value=True, key="top10_filter_iy05", on_change=clear_detail_and_rebuild_top_markets)
        with c_iy15:
            st.checkbox("İY 1.5", value=True, key="top10_filter_iy15", on_change=clear_detail_and_rebuild_top_markets)
        with c_combo:
            st.checkbox("Kombo", value=True, key="top10_filter_combo", on_change=clear_detail_and_rebuild_top_markets)

    # Tarih, lig ve sezon ayarları üstteki yapışkan kontrol alanına taşındı.
    analiz_btn = False
    backtest_btn = False
    gecmis_btn = False
    yuksek_oran_btn = False
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
    elif st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
        st.markdown(
            """
            <div class="sidebar-high-market-title">
              <b>💎 Yüksek Oran Marketleri</b>
              <span>Birden fazla seçim açılırsa koşullardan herhangi birini sağlayan geçmiş örnekler gösterilir.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        yf1, yf2 = st.columns(2)
        with yf1:
            yuksek_filtre_12 = st.checkbox('1/2', value=True, key='yuksek_filtre_12')
        with yf2:
            yuksek_filtre_21 = st.checkbox('2/1', value=True, key='yuksek_filtre_21')
        yuksek_filtre_cift_yari_kg = st.checkbox(
            'İki yarıda da karşılıklı gol', value=True, key='yuksek_filtre_cift_yari_kg'
        )
        yuksek_limit = st.selectbox('Maç başına geçmiş örnek', [10, 25, 50, 100], index=1, key='yuksek_limit')
        yuksek_oran_btn = False
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
elif st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        yuksek_oran_btn = st.button(
            '💎 ORANLILARI BUL',
            use_container_width=True,
            type='primary',
            key='yuksek_oran_btn',
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
elif st.session_state.get('sayfa_modu') == 'Canlı Takip':
    with ust_analiz_buton_alani.container():
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        canli_yenile_btn = st.button(
            '🔄 CANLIYI YENİLE',
            use_container_width=True,
            type='primary',
            key='canliyi_yenile_btn',
        )


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
    st.markdown(
        """
        <div class="history-page-header" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:14px;padding:15px 18px;margin-bottom:14px;">
          <div style="font-size:1.55rem;font-weight:900;line-height:1.2;">🔎 Geçmiş Örnekleri İncele</div>
          <div style="font-size:.90rem;margin-top:7px;line-height:1.5;">
            Seçilen liglerde o gün oynanacak tüm maçları ve benzer 1-X-2 oranlarına sahip geçmiş karşılaşmaları gösterir; tahmin üretmez.
          </div>
        </div>
        <style>
        .history-page-header, .history-page-header * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        .history-page-header > div:last-child {
            color:#334155 !important;
            -webkit-text-fill-color:#334155 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
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
        # Sağ üstte, koyu mod anahtarı gibi açılıp kapanırlar.
        mevcut_ayni_lig = bool(st.session_state.get("sadece_ayni_lig", False))
        if "gecmis_sadece_ayni_lig_toggle" not in st.session_state:
            st.session_state["gecmis_sadece_ayni_lig_toggle"] = mevcut_ayni_lig
        # Bu değer, Geçmiş Örnekleri listesinin en son hangi "aynı lig" durumuyla
        # hesaplandığını tutar. Böylece anahtar AÇIK -> KAPALI yapıldığında da liste
        # yeniden tüm ligleri kapsayacak şekilde hesaplanır.
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
            ozetler = [
                ("İY", iy_sonuc, float(iy_pct)),
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
                            overflow:hidden !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpander"] {{
                            width:100% !important;
                            max-width:none !important;
                            height:calc(100vh - 16px) !important;
                            overflow:hidden !important;
                        }}
                        .st-key-gecmis_mac_baslik_{sira} [data-testid="stExpanderDetails"] {{
                            height:calc(100vh - 62px) !important;
                            overflow:hidden !important;
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


if yuksek_oran_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    elif not (yuksek_filtre_12 or yuksek_filtre_21 or yuksek_filtre_cift_yari_kg):
        st.error("⚠️ En az bir yüksek oran marketi seçin.")
    else:
        with st.spinner("💎 1/2, 2/1 ve iki yarıda da KG örnekleri taranıyor..."):
            yo_gecmis = futbol_veri_motoru(tuple(yillar))
            yo_bulten = bulten_saglam_al(API_KEY, secili_kodlar, secili_tarih)
            yuksek_liste = []
            for _, yo_mac in yo_bulten.iterrows():
                tum_ornekler = gecmis_ornekleri_bul(
                    yo_gecmis,
                    yo_mac,
                    TOLERANS,
                    sadece_ayni_lig=sadece_ayni_lig,
                    limit=100000,
                )
                ornekler = gecmis_ornekleri_bul(
                    yo_gecmis,
                    yo_mac,
                    TOLERANS,
                    sadece_ayni_lig=sadece_ayni_lig,
                    filtre_12=yuksek_filtre_12,
                    filtre_21=yuksek_filtre_21,
                    filtre_cift_yari_kg=yuksek_filtre_cift_yari_kg,
                    limit=yuksek_limit,
                )
                if not ornekler.empty:
                    istatistikler, en_iyi, oneri = yuksek_oran_istatistikleri(
                        tum_ornekler,
                        filtre_12=yuksek_filtre_12,
                        filtre_21=yuksek_filtre_21,
                        filtre_cift_yari_kg=yuksek_filtre_cift_yari_kg,
                    )
                    yuksek_liste.append({
                        "m": yo_mac.to_dict(),
                        "ornekler": ornekler,
                        "istatistikler": istatistikler,
                        "en_iyi": en_iyi,
                        "oneri": oneri,
                        "toplam_benzer": len(tum_ornekler),
                    })
            yuksek_liste.sort(
                key=lambda x: (x.get("en_iyi", {}).get("puan", 0), x.get("toplam_benzer", 0)),
                reverse=True,
            )
            st.session_state.yuksek_oran_list = yuksek_liste
            st.rerun()

if st.session_state.get('sayfa_modu') == 'Yüksek Oran Filtresi':
    st.markdown(
        """
        <div class="high-filter-header-fix" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:14px;padding:15px 18px;margin-bottom:14px;">
          <div style="font-size:1.55rem;font-weight:900;line-height:1.2;">💎 Yüksek Oran Filtresi</div>
          <div style="font-size:.90rem;margin-top:7px;line-height:1.5;">
            Tahmin üretmez; yalnızca benzer geçmiş maçlarda seçilen yüksek oran senaryoları gerçekleşmiş güncel karşılaşmaları listeler.
          </div>
        </div>
        <style>
        .high-filter-header-fix, .high-filter-header-fix * {
            color:#0f172a !important;
            -webkit-text-fill-color:#0f172a !important;
            opacity:1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    yuksek_liste = st.session_state.get("yuksek_oran_list")
    if yuksek_liste is None:
        st.info("Lig, tarih ve marketleri seçip YÜKSEK ORANLILARI BUL butonuna bas.")
    elif not yuksek_liste:
        st.warning("Seçilen koşullarda 1/2, 2/1 veya iki yarıda da KG geçmiş örneği bulunan güncel maç yok.")
    else:
        st.success(f"{len(yuksek_liste)} güncel maç filtreye takıldı.")
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
                        Denenebilirlik puanı: <b>{float(en_iyi.get('puan', 0)):.1f}</b> ·
                        Toplam benzer maç: <b>{toplam_benzer}</b>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                metrik_kolonlari = st.columns(3)
                for metrik_col, label in zip(metrik_kolonlari, ["1/2", "2/1", "İki yarıda da KG"]):
                    bilgi = istatistik_map.get(label, {"hit": 0, "toplam": toplam_benzer, "oran": 0.0})
                    with metrik_col:
                        st.metric(
                            label,
                            f"{int(bilgi.get('hit', 0))} adet",
                            f"%{float(bilgi.get('oran', 0)):.1f} / {int(bilgi.get('toplam', toplam_benzer))} maç",
                            delta_color="off",
                        )
                st.markdown(
                    f"**Güncel oran:** `{m.get('h', 0):.2f} / {m.get('b', 0):.2f} / {m.get('a', 0):.2f}`"
                )
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
                    "Yüksek oran olayı": ornekler["Olay"],
                })
                st.dataframe(gecmis_tablo_stili(tablo), use_container_width=True, hide_index=True)
    legal_footer()
    st.stop()


if st.session_state.get('sayfa_modu') == 'Canlı Takip':
    st.markdown(
        """
        <div style="background:#ffffff;border:1px solid #cbd5e1;border-radius:14px;padding:15px 18px;margin-bottom:14px;color:#0f172a">
          <div style="font-size:1.55rem;font-weight:900;color:#0f172a">📡 Canlı Tahmin Takibi</div>
          <div style="font-size:.90rem;margin-top:7px;color:#334155">
            Kaydedilmiş maç önü tahminlerini canlı skor ve başlangıç saatinden hesaplanan tahmini dakikayla karşılaştırır.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    simdi_canli = datetime.utcnow() + timedelta(hours=3)
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
        baslangic = pd.Timestamp((datetime.utcnow() + timedelta(hours=3)).date())
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
                        .agg(Tahmin=("tuttu", "size"), Kazanan=("tuttu", "sum"), Ortalama_Bağlam=("Bağlam Puanı", "mean"))
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
                ozet = biten.groupby(alan, dropna=False).agg(Tahmin=("tuttu", "size"), Kazanan=("tuttu", "sum")).reset_index()
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
                        .agg(Tahmin=("alternatif_tuttu", "size"), Kazanan=("alternatif_tuttu", "sum"))
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


if backtest_btn:
    with st.spinner("🧪 11 hassasiyet test ediliyor (0.00–0.10)..."):
        bt_sezonlar = list(dict.fromkeys(list(yillar) + [backtest_sezonu]))
        bt_gecmis = futbol_veri_motoru(tuple(bt_sezonlar))
        secili_history_codes = [ODDS_TO_HISTORY[k] for k in secili_kodlar if k in ODDS_TO_HISTORY]
        bt11, bt_secili = backtest_11_hassasiyet_calistir(
            bt_gecmis,
            backtest_sezonu,
            TOLERANS,
            min_ornek,
            sadece_ayni_lig=sadece_ayni_lig,
            lig_kodlari=secili_history_codes or None,
            max_test=backtest_limit,
        )
        st.session_state.backtest_11_df = bt11
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
    bt = st.session_state.get("backtest_df")
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
            .agg(Tahmin_Sayısı=("Tuttu", "size"), Kazanan=("Tuttu", "sum"), Ortalama_Güven=("Güven", "mean"))
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
                        Kazanan=("Tuttu", "sum"),
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
                        .agg(Tahmin_Sayısı=("Alt. Tuttu", "size"), Kazanan=("Alt. Tuttu", "sum"), Ortalama_Güven=("Alt. Güven", "mean"))
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
            st.session_state.last_gecmis_df = gecmis
            st.session_state.last_bulten_df = bulten
            st.session_state["son_bulten_mac_sayisi"] = 0 if getattr(bulten, "empty", True) else len(bulten)
            st.session_state["son_api_hatasi"] = st.session_state.get("odds_api_last_error")
            st.session_state["son_analiz_tarihi_secili"] = str(secili_tarih)

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

        if not bulten.empty and not gecmis.empty:
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

                # Minimum Örnek Sayısı ana maç analizinde de kesin olarak uygulanır.
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
                m_dict = m.to_dict()
                m_dict["durum"] = mac_canli_durumu(m_dict["zaman"])
                final.append({"m": m_dict, "t": t, "b": b_det})
                _sayac_gecen += 1

        final = sorted(
            final,
            key=lambda x: (
                x["t"].get("score", 0),
                x["t"].get("ana_p", 0),
                x["t"].get("stability_count", 0),
            ),
            reverse=True,
        )
        final = sorted(
            final,
            key=lambda x: (
                x["t"].get("playable_score", 0),
                x["t"].get("ana_p", 0),
                x["t"].get("score", 0),
                x["t"].get("stability_count", 0),
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
        if st.session_state.get("sayfa_modu") == "Top 50 Market":
            st.session_state.top50_list = gunun_en_iyi_10_uret(
                gecmis, bulten, min_ornek=min_ornek, limit=50,
                sadece_ayni_lig=sadece_ayni_lig,
            )
        else:
            st.session_state.top50_list = []
        st.session_state.detay_idx = None
        st.session_state.detay_item = None
        st.session_state.son_analiz = datetime.now().strftime("%d/%m/%Y %H:%M")
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
    bulten = st.session_state.get("last_bulten_df")
    if bulten is not None and not getattr(bulten, "empty", True):
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

    try:
        tolerans = float(secim.get("hassasiyet", 0.08) or 0.08)
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
        return {"m": m, "t": t, "b": b_det, "kupon_secim": secim}
    except Exception:
        return None


def ana_tahmin_gecmis_detayi(m, t, b_det):
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
        st.warning(
            f"🔎 Son analiz teşhisi · API: {_bc} · hesapla() sonuç yok: {_fs.get('t_none',0)} · "
            f"minimum örnekten elenen: {_fs.get('ornek',0)} · güven eşiğinden elenen: {_fs.get('guven',0)} · "
            f"geçen: {_fs.get('gecen',0)} · tolerans: {_fs.get('tolerans','?')} · "
            f"min örnek: {_fs.get('min_ornek','?')} · güven eşiği: {_fs.get('oynanabilir_esik','?')}"
        )
    else:
        st.success(
            f"🔎 Son analiz teşhisi · API: {_bc} · hesapla() sonuç yok: {_fs.get('t_none',0)} · "
            f"örnekten elenen: {_fs.get('ornek',0)} · güvenden elenen: {_fs.get('guven',0)} · "
            f"gösterilen: {_fc}"
        )

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
        goster = sorted(yuksek, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    elif filtre == "orta":
        goster = sorted(orta, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    elif filtre == "kombo":
        goster = sorted(kombolu, key=lambda x: x[1]["t"].get("playable_score", x[1]["t"].get("ana_p", 0)), reverse=True)
    else:
        goster = indexed_fl

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
            if gunun_secimleri:
                kupon_gecmisine_ekle(gunun_secimleri, "Günün Kuponu", "0.00–0.10 tarama")
                st.session_state.coupon_popup_open = True
                st.session_state.scroll_to_coupon = True
                kupon_mesaji = (
                    "success",
                    f"⭐ Günün Kuponu oluşturuldu: kalite eşiğini geçen {len(gunun_secimleri)} güçlü seçim tek kupona eklendi."
                )
            else:
                kupon_mesaji = (
                    "warning",
                    "Günün Kuponu için en az iki yeterince güvenilir ve kararlı seçim bulunamadı."
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

                        for secim_no, secim in enumerate(kayit.get("secimler", [])):
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
