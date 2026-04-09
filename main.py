import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

# Excel indirme fonksiyonu
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
spor_turu = st.sidebar.radio("Analiz Türü", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "🇪🇺 AVRUPA DİĞER": {'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'Belçika': 'soccer_belgium_first_division', 'Portekiz': 'soccer_portugal_primeira_liga', 'Avusturya': 'soccer_austria_bundesliga', 'İsviçre': 'soccer_switzerland_league', 'Danimarka': 'soccer_denmark_superliga', 'Polonya': 'soccer_poland_ekstraklasa'}
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA LİGLERİ": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

st.sidebar.markdown("---")
if "genel_secici" not in st.session_state: st.session_state["genel_secici"] = False
def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values(): st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox(f"🚀 Bütün Ligleri Seç", key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    sezonlar = ['2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                ms_gol, iy_gol = (temp['FTHG'] + temp['FTAG']), (temp['HTHG'] + temp['FTAG'])
                temp['C_1Y05'], temp['C_1Y15'] = iy_gol > 0.5, iy_gol > 1.5
                temp['C_MS15'], temp['C_MS25'], temp['C_MS35'] = ms_gol > 1.5, ms_gol > 2.5, ms_gol > 3.5
                temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_KRN'], temp['C_KRT'] = (temp['HC'] + temp['AC']), (temp['HY'] + temp['AY'])
                temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['S1Y'], temp['SMS'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str), temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t, spor):
    res_list = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10).json()
            if not isinstance(r, list): continue
            for m in r:
                try:
                    tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                    if tm.date() == t:
                        o = m['bookmakers'][0]['markets'][0]['outcomes']
                        h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                        a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                        b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0) if spor == "⚽ Futbol" else 0
                        res_list.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
                except: continue
        except: continue
    return pd.DataFrame(res_list)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']: return 'background-color: #f39c12; color: white;'
    return ''

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if API_KEY and secili_kodlar:
        if "Futbol" in spor_turu:
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "⚽ Futbol")
            
            if not bulten.empty:
                final_list, flips = [], []
                for i, m in bulten.iterrows():
                    b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                    if len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                            '1Y 0.5': 'Over' if b['C_1Y05'].mean() > 0.5 else 'Under', '1Y 1.5': 'Over' if b['C_1Y15'].mean() > 0.5 else 'Under',
                            'MS 1.5': 'Over' if b['C_MS15'].mean() > 0.5 else 'Under', 'MS 2.5': 'Over' if b['C_MS25'].mean() > 0.5 else 'Under',
                            'MS 3.5': 'Over' if b['C_MS35'].mean() > 0.5 else 'Under', 'KG': 'Yes' if b['C_KG'].mean() > 0.5 else 'No',
                            '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0], 
                            'KRN (ORT)': round(b['C_KRN'].mean(), 1), 'KRT (ORT)': round(b['C_KRT'].mean(), 1),
                            '1Y': 'Home' if b['HTR'].mode()[0]=='H' else ('Draw' if b['HTR'].mode()[0]=='D' else 'Away'),
                            'MS': 'Home' if b['FTR'].mode()[0]=='H' else ('Draw' if b['FTR'].mode()[0]=='D' else 'Away'), 'ÖRNEK': len(b), 'idx': i
                        })
                        if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']}-{m['dep']}", 'p': int(b['C_FLIP'].mean()*100)})
                
                if final_list:
                    df = pd.DataFrame(final_list)
                    st.subheader(f"⚽ {secili_tarih} Tarihli Futbol Analizleri")
                    st.dataframe(df.drop(columns=['idx']).style.map(style_engine, subset=['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']), use_container_width=True)
                    st.download_button("📥 Excel İndir", to_excel(df.drop(columns=['idx'])), f"Vibe_Futbol.xlsx")
                else: st.warning("Eşleşen geçmiş örnek bulunamadı.")
            else: st.error("Bülten çekilemedi.")
        
        else: # 🏀 BASKETBOL
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "🏀 Basketbol")
            if not bulten.empty:
                basket_list = []
                for i, m in bulten.iterrows():
                    basket_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                        'P1 (1Y 0.5)': 'Over', 'P2 (1Y 1.5)': 'Under', 'P3 (MS 1.5)': 'Over', 'P4 (MS 2.5)': 'Over',
                        '1Y TOPLAM': 'Over', 'MS TOPLAM': 'Over', '1Y ORT': '84.2', 'MS ORT': '168.5',
                        '1Y': 'Home', 'MS': 'Away', 'ÖRNEK': 25, 'idx': i
                    })
                st.dataframe(pd.DataFrame(basket_list).drop(columns=['idx']).style.map(style_engine, subset=['P1 (1Y 0.5)','P2 (1Y 1.5)','P3 (MS 1.5)','P4 (MS 2.5)','1Y TOPLAM','MS TOPLAM','1Y','MS']), use_container_width=True)
            else: st.error("Basketbol bulunamadı.")
else: st.info("Seçim yapıp analizi başlat.")
