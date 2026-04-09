import streamlit as st
import pandas as pd
import requests
import io
import google.generativeai as genai
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Basketbol Fix", layout="wide")

# GEMINI AYARI (Kalıcı Key)
try:
    GEMINI_KEY = "AIzaSyBhy1PQMaY5PtZVr59OCas2T_Zqg7lLwWE"
    genai.configure(api_key=GEMINI_KEY)
except:
    pass

def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol")
spor_turu = st.sidebar.radio("Tür", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Tarih", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek (Futbol İçin)", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Hassasiyet", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "🌎 GLOBAL": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a'}
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa', 'İtalya Lega A': 'basketball_italy_lega_a', 'Almanya BBL': 'basketball_germany_bbl', 'Yunanistan GBL': 'basketball_greece_basket_league'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

st.sidebar.markdown("---")
if "genel_secici" not in st.session_state: st.session_state["genel_secici"] = False
def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values(): st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox("🚀 Bütün Ligleri Seç", key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU (FUTBOL) ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE'}
    liste = []
    for k in lig_map.keys():
        try:
            url = f"https://www.football-data.co.uk/mmz4281/2425/{k}.csv"
            df = pd.read_csv(url)
            cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC']
            temp = df[cols].dropna().copy()
            ms_gol, iy_gol = (temp['FTHG'] + temp['FTAG']), (temp['HTHG'] + temp['HTAG'])
            temp['C_1Y05'], temp['C_MS25'] = iy_gol > 0.5, ms_gol > 2.5
            temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
            temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
            temp['S1Y'], temp['SMS'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str), temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
            temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
            liste.append(temp)
        except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t):
    res = []
    for k in kodlar:
        try:
            # Basketbol için 'h2h' pazarını çekerken hata riskine karşı kontrol
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h').json()
            if isinstance(r, list):
                for m in r:
                    tm = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                    if tm.date() == t:
                        try:
                            o = m['bookmakers'][0]['markets'][0]['outcomes']
                            h = next((x['price'] for x in o if x['name']==m['home_team']), 0)
                            a = next((x['price'] for x in o if x['name']==m['away_team']), 0)
                            res.append({'LİG': m['sport_title'], 'SAAT': tm.strftime('%H:%M'), 'EV': m['home_team'], 'DEP': m['away_team'], 'EV ORAN': h, 'DEP ORAN': a})
                        except: continue
        except: continue
    return pd.DataFrame(res)

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if API_KEY and secili_kodlar:
        if "Futbol" in spor_turu:
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten.empty:
                final_list, flips = [], []
                for i, m in bulten.iterrows():
                    b = gecmis[(gecmis['B365H'].between(m['EV ORAN']-TOLERANS, m['EV ORAN']+TOLERANS)) & (gecmis['B365A'].between(m['DEP ORAN']-TOLERANS, m['DEP ORAN']+TOLERANS))]
                    if len(b) >= min_ornek:
                        final_list.append({'SAAT': m['SAAT'], 'LİG': m['LİG'], 'EV': m['EV'], 'DEP': m['DEP'], '1Y 0.5': 'Üst' if b['C_1Y05'].mean() > 0.5 else 'Alt', 'MS 2.5': 'Üst' if b['C_MS25'].mean() > 0.5 else 'Alt', 'KG': 'Var' if b['C_KG'].mean() > 0.5 else 'Yok', '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0], 'ÖRNEK': len(b)})
                        if b['C_FLIP'].any(): flips.append({'m': f"{m['EV']}-{m['DEP']}", 'p': int(b['C_FLIP'].mean()*100)})
                
                if final_list:
                    df = pd.DataFrame(final_list)
                    st.dataframe(df, use_container_width=True)
                    st.download_button("📥 Excel İndir", to_excel(df), f"Vibe_Futbol_{secili_tarih}.xlsx")
                    
                    st.markdown("### 🤖 Gemini AI Analizi")
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(f"Futbol uzmanı gibi bu tabloyu yorumla: {df.to_string()}")
                        st.info(response.text)
                    except: st.warning("AI şu an meşgul.")

                    if flips:
                        st.subheader("🔥 Sürpriz Radarı")
                        for f in flips: st.warning(f"{f['m']}: %{f['p']} Sürpriz!")
            else: st.warning("Seçili tarihte futbol maçı bulunamadı.")
        
        else: # BASKETBOL ANALİZİ
            bulten_bsk = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten_bsk.empty:
                st.subheader(f"🏀 {secili_tarih} Basketbol Bülteni")
                st.dataframe(bulten_bsk, use_container_width=True)
                st.download_button("📥 Excel İndir", to_excel(bulten_bsk), f"Vibe_Basket_{secili_tarih}.xlsx")
                
                st.markdown("### 🤖 Gemini AI Basketbol Yorumu")
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(f"Basketbol uzmanı gibi bu maçları yorumla, oranlara göre öne çıkanları söyle: {bulten_bsk.to_string()}")
                    st.info(response.text)
                except: st.warning("AI şu an meşgul.")
            else:
                st.error("Basketbol maçı bulunamadı. Lütfen ligleri ve tarihi kontrol et.")
else: st.info("Ligleri seç ve analizi başlat.")
