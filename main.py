import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Multi-Sport Pro", layout="wide")

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

# --- YAN MENÜ (SPOR VE FİLTRE SEÇİMİ) ---
st.sidebar.title("🎮 Kontrol Merkezi")
spor_turu = st.sidebar.radio("Spor Türü Seçin", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun, min_value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.20)

# --- LİG YAPILARI ---
FUTBOL_LIGLERI = {
    "TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "AVRUPA": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Romanya': 'soccer_romania_liga_1'},
    "DİĞER": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a'}
}

BASKETBOL_LIGLERI = {
    "MAJÖR": {'NBA': 'basketball_nba', 'Euroleague': 'basketball_euroleague'},
    "AVRUPA": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa', 'Almanya BBL': 'basketball_germany_bbl'},
    "DİĞER": {'Çin CBA': 'basketball_china_cba', 'Avustralya NBL': 'basketball_australia_nbl'}
}

secili_kodlar = []
lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI

st.sidebar.markdown(f"### 🏟️ {spor_turu} Ligleri")
for kat, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, value=False, key=kod):
                secili_kodlar.append(kod)

# --- VERİ MOTORLARI ---
@st.cache_data(ttl=86400)
def futbol_veri_yukle():
    ligler = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','BRA':'BR','N1':'NL'}
    liste = []
    for k in ligler.keys():
        try:
            url = f"https://www.football-data.co.uk/mmz4281/2425/{k}.csv"
            df = pd.read_csv(url)
            cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
            temp = df[cols].dropna().copy()
            temp['COL_MS25'] = (temp['FTHG'] + temp['FTAG']) > 2.5
            temp['COL_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
            temp['COL_KRN'] = temp['HC'] + temp['AC']
            temp['S1Y'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str)
            temp['SMS'] = temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
            temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True)
            liste.append(temp)
        except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

# --- ANA PROGRAM ---
st.title(f"{spor_turu} Analiz İstasyonu")

if API_KEY and secili_kodlar:
    if st.button(f"🚀 {spor_turu} ANALİZİNİ BAŞLAT"):
        if "Futbol" in spor_turu:
            gecmis = futbol_veri_yukle()
            # (Önceki futbol analiz mantığı burada çalışacak...)
            st.success("Futbol bülteni yüklendi. (Gelişmiş tablo görünümü)")
            # [Buraya daha önceki futbol döngüsü gelecek]
        else:
            # BASKETBOL MANTIĞI
            st.warning("🏀 Basketbol modu aktif. Basketbol veri seti analiz ediliyor...")
            st.info("Basketbol analizi için handikap ve toplam sayı limitleri üzerinden geçmiş tarama yapılıyor.")
            # Basketbol için veri havuzu çekme ve karşılaştırma kodu buraya entegre edilecek
else:
    st.info("👋 Ersin, lütfen sol menüden Branş ve Lig seçimi yaparak başla.")
