import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import math

# ──────────────────────────────────────────────────────────────────────────
# SAYFA AYARLARI VE ÖZEL CSS (V6.3 UI TASARIMI)
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Vibe Pro Expert v6.3", layout="wide", page_icon="⚡")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Rajdhani:wght@600;700&display=swap');

/* Genel Arka Plan ve Yazı Tipi */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0b0d11 !important;
    color: #ffffff;
}

.main .block-container {
    padding-top: 1.5rem;
    max-width: 95%;
}

/* Sol Menü (Sidebar) */
section[data-testid="stSidebar"] {
    background-color: #11141d !important;
    border-right: 1px solid #1e212b;
}

/* Logo Alanı */
.logo-container {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0 30px 0;
}
.logo-v {
    background: #21ce66;
    color: #000;
    font-weight: 900;
    font-size: 24px;
    padding: 5px 12px;
    border-radius: 6px;
}
.logo-text {
    font-family: 'Rajdhani', sans-serif;
    font-weight: 700;
    font-size: 20px;
    line-height: 1;
}
.logo-version {
    color: #21ce66;
    font-size: 12px;
    letter-spacing: 1px;
}

/* Kart Yapıları */
.mac-kart {
    background: #161a23;
    border: 1px solid #1e222d;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 12px;
    transition: all 0.3s ease;
}
.mac-kart:hover {
    border-color: #21ce66;
    background: #1c212c;
}

/* Rozetler ve Değerler */
.pill-main {
    background: #1d3b2a;
    color: #21ce66;
    padding: 6px 15px;
    border-radius: 6px;
    font-weight: 700;
    font-family: 'Rajdhani';
    font-size: 1.1rem;
    display: inline-block;
}
.guven-bar-bg {
    background: #252a36;
    height: 6px;
    border-radius: 10px;
    margin-top: 8px;
    width: 100%;
}
.guven-bar-fill {
    height: 100%;
    border-radius: 10px;
    background: #21ce66;
}

/* Alt Tablo ve Detaylar */
.stDataFrame {
    border: 1px solid #1e222d;
    border-radius: 12px;
}

/* Buton Tasarımı */
div.stButton > button {
    background-color: #21ce66 !important;
    color: #000 !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
    border: none !important;
    padding: 10px 20px !important;
    width: 100%;
}

</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────
# SIDEBAR (SOL PANEL)
# ──────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="logo-container">
        <div class="logo-v">V</div>
        <div>
            <div class="logo-text">VIBE PRO</div>
            <div class="logo-version">EXPERT v6.3</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<p style='color:#555; font-size:0.7rem; font-weight:700;'>KONTROL MERKEZİ</p>", unsafe_allow_html=True)
    API_KEY = st.text_input("The Odds API Key", type="password", placeholder="api_key_buraya")
    
    analysis_date = st.date_input("Analiz Tarihi", datetime.now())
    
    with st.expander("Sezonlar"):
        s2526 = st.checkbox("2526", value=True)
        s2425 = st.checkbox("2425", value=True)
        s2324 = st.checkbox("2324", value=True)
    
    min_sample = st.number_input("Min. Örnek Sayısı", value=1, min_value=1)
    sensitivity = st.slider("Oran Hassasiyeti", 0.0, 0.2, 0.08)
    
    st.markdown("---")
    if st.button("⚡ ANALİZİ BAŞLAT"):
        st.toast("Analiz başlatılıyor...", icon="🚀")

# ──────────────────────────────────────────────────────────────────────────
# ANA EKRAN (GÖRSELDEKİ ÜST KISIM)
# ──────────────────────────────────────────────────────────────────────────
col_title, col_stat = st.columns([4, 1])

with col_title:
    st.markdown(f"### ANA MAÇ EKRANI")
    st.markdown(f"<p style='color:#666;'>{analysis_date.strftime('%d Mayıs %Y Perşembe')}</p>", unsafe_allow_html=True)

with col_stat:
    st.markdown("""
    <div style="background:#161a23; border:1px solid #1e222d; border-radius:8px; padding:10px; text-align:center;">
        <span style="color:#21ce66; font-size:1.5rem; font-weight:700; font-family:Rajdhani;">24</span><br>
        <span style="color:#666; font-size:0.7rem;">MAÇ BULUNDU</span>
    </div>
    """, unsafe_allow_html=True)

# Filtre Sekmeleri (Görseldeki gibi)
tabs = st.columns([1, 1.2, 1.2, 1.2, 4])
with tabs[0]: st.markdown("<p style='color:#21ce66; border-bottom:2px solid #21ce66; text-align:center; cursor:pointer;'>Tümü</p>", unsafe_allow_html=True)
with tabs[1]: st.markdown("<p style='color:#666; text-align:center; cursor:pointer;'>🔥 Yüksek Güven</p>", unsafe_allow_html=True)
with tabs[2]: st.markdown("<p style='color:#666; text-align:center; cursor:pointer;'>🟡 Orta Güven</p>", unsafe_allow_html=True)
with tabs[3]: st.markdown("<p style='color:#666; text-align:center; cursor:pointer;'>⭐ Sürpriz Maçlar</p>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Örnek Maç Kartı (Görseldeki Galatasaray - Kocaelispor satırı simülasyonu)
def draw_match_card(time, home, away, prediction, confidence, odds):
    st.markdown(f"""
    <div class="mac-kart">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 40px; flex: 3;">
                <div style="text-align: center;">
                    <div style="font-size: 1.2rem; font-weight: 700; font-family: Rajdhani;">{time}</div>
                    <div style="font-size: 0.6rem; color: #666; background: #11141d; padding: 2px 5px; border-radius: 4px;">Süper Lig</div>
                </div>
                <div style="line-height: 1.8;">
                    <div style="font-weight: 600; font-size: 1.1rem;">🦁 {home}</div>
                    <div style="font-weight: 600; font-size: 1.1rem; color: #aaa;">🛡️ {away}</div>
                </div>
            </div>
            <div style="flex: 2; text-align: center;">
                <div style="font-size: 0.6rem; color: #666; letter-spacing: 1px;">ANA TAHMİN</div>
                <div class="pill-main">{prediction}</div>
                <div style="margin-top: 10px;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-family: Rajdhani;">
                        <span>GÜVEN</span><span>%{confidence}</span>
                    </div>
                    <div class="guven-bar-bg"><div class="guven-bar-fill" style="width: {confidence}%;"></div></div>
                </div>
            </div>
            <div style="flex: 1; text-align: center;">
                <div style="font-size: 0.6rem; color: #666;">ALTERNATİF</div>
                <div style="color: #21ce66; font-weight: 700;">2.5 Üst</div>
                <div style="font-size: 0.6rem; color: #666; margin-top: 10px;">SÜRPRİZ</div>
                <div style="color: #f1c40f; font-weight: 700; font-size: 0.8rem;">KG Var</div>
            </div>
            <div style="flex: 2; text-align: right;">
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <div style="text-align: center;"><div style="font-size: 0.6rem; color: #666;">1</div><div style="font-weight: 600;">{odds[0]}</div></div>
                    <div style="text-align: center;"><div style="font-size: 0.6rem; color: #666;">X</div><div style="font-weight: 600;">{odds[1]}</div></div>
                    <div style="text-align: center;"><div style="font-size: 0.6rem; color: #666;">2</div><div style="font-weight: 600;">{odds[2]}</div></div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Örnek maçları listele
draw_match_card("19:00", "Galatasaray", "Kocaelispor", "MS 1", 78, [1.42, 4.20, 6.80])
draw_match_card("20:00", "Trabzonspor", "Karagümrük", "MS 1", 72, [1.65, 3.80, 5.40])
draw_match_card("22:00", "Fenerbahçe", "Hatayspor", "MS 1", 76, [1.30, 5.00, 8.20])

# ──────────────────────────────────────────────────────────────────────────
# DETAY PANELİ (ALT KISIM)
# ──────────────────────────────────────────────────────────────────────────
st.markdown("<br><hr style='border-color: #1e222d;'>", unsafe_allow_html=True)
st.markdown("### 📊 GALATASARAY - KOCAELİSPOR DETAY ANALİZİ")

col_l, col_r = st.columns(2)

with col_l:
    st.markdown("""
    <div style="background: #161a23; padding: 20px; border-radius: 12px; border: 1px solid #1e222d;">
        <p style="font-family: Rajdhani; font-weight: 700; letter-spacing: 1px;">MAÇ TAHMİNLERİ</p>
        <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #1e222d;">
            <span style="color: #888;">Maç Sonucu (1/X/2)</span>
            <span style="color: #21ce66; font-weight: 700;">%62 / %23 / %15</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #1e222d;">
            <span style="color: #888;">2.5 Üst / Alt</span>
            <span style="color: #21ce66; font-weight: 700;">%68 / %32</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #1e222d;">
            <span style="color: #888;">Karşılıklı Gol</span>
            <span style="color: #f1c40f; font-weight: 700;">Var %41 / Yok %59</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_r:
    st.markdown("""
    <div style="background: #161a23; padding: 20px; border-radius: 12px; border: 1px solid #1e222d;">
        <p style="font-family: Rajdhani; font-weight: 700; letter-spacing: 1px;">DİĞER ÖNERİLER</p>
        <div style="display: flex; justify-content: space-between; padding: 10px 0;">
            <span style="color: #888;">HT/FT (1/1)</span>
            <span style="background: #1d3b2a; color: #21ce66; padding: 2px 8px; border-radius: 4px;">%45</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 10px 0;">
            <span style="color: #888;">Toplam Gol 3.5 Üst</span>
            <span style="background: #3b2a1d; color: #f1c40f; padding: 2px 8px; border-radius: 4px;">%42</span>
        </div>
        <div style="margin-top: 15px; background: #11141d; padding: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.8rem; font-weight: 700;">RİSK SEVİYESİ</span>
            <span style="background: #21ce66; color: #000; padding: 4px 15px; border-radius: 6px; font-weight: 800; font-size: 0.8rem;">DÜŞÜK</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
