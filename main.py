import streamlit as st
import pandas as pd
import requests
import io
import google.generativeai as genai
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Kesin Çözüm", layout="wide")

# GEMINI AYARI
GEMINI_KEY = "AIzaSyBhy1PQMaY5PtZVr59OCas2T_Zqg7lLwWE"
genai.configure(api_key=GEMINI_KEY)

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

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
min_ornek = st.sidebar.number_input("Min. Örnek", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Hassasiyet", 0.05, 0.45, 0.15)

# --- LİG HAVUZU ---
FUTBOL_LIGLERI = {
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "🇪🇺 AVRUPA DİĞER": {'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'Portekiz': 'soccer_portugal_primeira_liga', 'Belçika': 'soccer_belgium_first_division'},
    "🌎 GLOBAL": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else {}
secili_kodlar = []
for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.sidebar.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
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

def bulten_cek(key, kodlar, hedef_tarih):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h').json()
            for m in r:
                t = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                if t.date() == hedef_tarih:
                    o = m['bookmakers'][0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name']==m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name']==m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() == 'draw'), 0)
                    res.append({'lig': m['sport_title'], 'zaman': t, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

# --- ANALİZ ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if API_KEY and secili_kodlar:
        gecmis = futbol_veri_motoru()
        bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
        if not bulten.empty:
            final_list, flips = [], []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                if len(b) >= min_ornek:
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                        '1Y 0.5': 'Üst' if b['C_1Y05'].mean() > 0.5 else 'Alt', 'MS 2.5': 'Üst' if b['C_MS25'].mean() > 0.5 else 'Alt',
                        'KG': 'Var' if b['C_KG'].mean() > 0.5 else 'Yok', '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                        '1Y': b['HTR'].mode()[0], 'MS': b['FTR'].mode()[0], 'ÖRNEK': len(b)
                    })
                    if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']}-{m['dep']}", 'p': int(b['C_FLIP'].mean()*100)})
            
            if final_list:
                df = pd.DataFrame(final_list)
                st.table(df)
                
                # AI RAPORU
                st.markdown("### 🤖 AI Analizi")
                try:
                    # Alternatif çağırma yöntemi
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = f"Bu maçları yorumla, en güvenilir 3 tanesini seç: {df.to_string()}"
                    response = model.generate_content(prompt)
                    st.info(response.text)
                except:
                    st.warning("AI şu an bülteni okuyamadı ama tablo yukarıda!")

                if flips:
                    st.subheader("🔥 Sürpriz Radarı (1/2 - 2/1)")
                    for f in flips: st.warning(f"{f['m']}: %{f['p']} Sürpriz İhtimali!")
        else: st.error("Maç bulunamadı.")
    else: st.info("Seçim yapın.")
