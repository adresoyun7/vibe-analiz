import streamlit as st
import pandas as pd
import requests
import io
import google.generativeai as genai
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Stabil Pro", layout="wide")

# GEMINI AYARI (Senin Key'in)
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

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "🇪🇺 AVRUPA DİĞER": {'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'Portekiz': 'soccer_portugal_primeira_liga', 'Belçika': 'soccer_belgium_first_division', 'İskoçya': 'soccer_scotland_premier_league', 'Avusturya': 'soccer_austria_bundesliga', 'İsviçre': 'soccer_switzerland_league', 'Danimarka': 'soccer_denmark_superliga', 'Yunanistan': 'soccer_greece_super_league', 'Polonya': 'soccer_poland_ekstraklasa'},
    "🌎 GLOBAL": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a', 'Meksika': 'soccer_mexico_ligamx', 'Japonya': 'soccer_japan_j_league'}
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA LİGLERİ": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa', 'İtalya Lega A': 'basketball_italy_lega_a', 'Almanya BBL': 'basketball_germany_bbl', 'Fransa LNB': 'basketball_france_lnb', 'Yunanistan GBL': 'basketball_greece_basket_league'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

# --- SEÇİM MANTIĞI ---
st.sidebar.markdown("---")
def toggler_all():
    state = st.session_state["genel_secici"]
    for kat in lig_havuzu.values():
        for kod in kat.values(): st.session_state[f"cb_{kod}"] = state

st.sidebar.checkbox(f"🚀 Bütün Ligleri Seç", value=False, key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        def toggler_kat(k=kat_isim, l=ligler):
            state = st.session_state[f"kat_sec_{k}"]
            for kod in l.values(): st.session_state[f"cb_{kod}"] = state
        st.checkbox(f"Hepsini Seç ({kat_isim})", key=f"kat_sec_{kat_isim}", on_change=toggler_kat)
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT','GRE':'GR','SWZ':'CH','DNK':'DK','POL':'PL','BRA':'BR'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                ms_gol, iy_gol = (temp['FTHG'] + temp['FTAG']), (temp['HTHG'] + temp['HTAG'])
                temp['C_1Y05'], temp['C_MS25'] = iy_gol > 0.5, ms_gol > 2.5
                temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['C_KRN'], temp['C_KRT'] = (temp['HC'] + temp['AC']), (temp['HY'] + temp['AY'])
                temp['S1Y'], temp['SMS'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str), temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

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

# --- ANA PROGRAM ---
st.title(f"{spor_turu} Pro Analiz İstasyonu")

if API_KEY and secili_kodlar:
    if st.button("🚀 ANALİZİ BAŞLAT"):
        if "Futbol" in spor_turu:
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten.empty:
                final_list, flips = [], []
                for i, m in bulten.sort_values(by='zaman').iterrows():
                    b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                    if len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                            '1Y 0.5': 'Üst' if b['C_1Y05'].mean() > 0.5 else 'Alt', 'MS 2.5': 'Üst' if b['C_MS25'].mean() > 0.5 else 'Alt',
                            'KG': 'Var' if b['C_KG'].mean() > 0.5 else 'Yok', '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                            '1Y': b['HTR'].mode()[0], 'MS': b['FTR'].mode()[0], 'ÖRNEK': len(b), 'idx': i
                        })
                        if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']}-{m['dep']}", 'p': int(b['C_FLIP'].mean()*100)})
                
                if final_list:
                    df = pd.DataFrame(final_list)
                    st.dataframe(df.drop(columns=['idx']), use_container_width=True)
                    st.download_button("📥 Excel İndir", to_excel(df.drop(columns=['idx'])), f"Vibe_{secili_tarih}.xlsx")

                    # AI RAPORU
                    st.markdown("### 🤖 Gemini AI Analizi")
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        resp = model.generate_content(f"Futbol analisti olarak yorumla: {df.to_string()}")
                        st.info(resp.text)
                    except: st.warning("AI şu an meşgul.")

                    if flips:
                        st.subheader("🔥 Sürpriz Radarı")
                        for f in flips: st.warning(f"{f['m']}: %{f['p']} Sürpriz!")
            else: st.error("Maç yok.")
        else:
            bulten_bsk = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten_bsk.empty: st.dataframe(bulten_bsk)
else: st.info("Seçim yapın.")
