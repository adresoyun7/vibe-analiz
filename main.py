import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def poisson_skor_tahmin(ev_lambda, dep_lambda):
    # 0-5 gol arası olasılık matrisi oluşturur
    max_goals = 6
    ev_prob = [poisson.pmf(i, ev_lambda) for i in range(max_goals)]
    dep_prob = [poisson.pmf(i, dep_lambda) for i in range(max_goals)]
    
    # En yüksek olasılıklı skoru bul
    m = np.outer(ev_prob, dep_prob)
    ev_skor, dep_skor = np.unravel_index(m.argmax(), m.shape)
    return f"{ev_skor}-{dep_skor}"

# Excel indirme
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
TOLERANS = st.sidebar.slider("Oran Hassasiyeti (Tolerans)", 0.05, 0.30, 0.10)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇸🇦 ARAP LİGLERİ": {'Suudi Arabistan Pro Lig': 'soccer_saudi_arabia_pro_league', 'BAE Pro Lig': 'soccer_uae_pro_league'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else {}
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
                temp['C_1Y05'] = iy_gol > 0.5
                temp['C_MS25'] = ms_gol > 2.5
                temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_KRN'], temp['C_KRT'] = (temp['HC'] + temp['AC']), (temp['HY'] + temp['AY'])
                temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t):
    all_res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10)
            if r.status_code != 200: continue
            data = r.json()
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() == t:
                    bookies = m.get('bookmakers', [])
                    if not bookies: continue
                    o = bookies[0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                    all_res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(all_res)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']: return 'background-color: #f39c12; color: white;'
    return ''

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key girin ve lig seçin.")
    else:
        gecmis = futbol_veri_motoru()
        bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
        if not bulten.empty:
            final_list, flips = [], []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                if len(b) >= min_ornek:
                    # POISSON HESABI
                    avg_ev = b['FTHG'].mean()
                    avg_dep = b['FTAG'].mean()
                    iy_ev_avg = b['HTHG'].mean()
                    iy_dep_avg = b['HTAG'].mean()
                    
                    ms_skor = poisson_skor_tahmin(avg_ev, avg_dep)
                    iy_skor = poisson_skor_tahmin(iy_ev_avg, iy_dep_avg)
                    
                    ms_ev, ms_dep = map(int, ms_skor.split('-'))
                    iy_ev, iy_dep = map(int, iy_skor.split('-'))
                    
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y 0.5': 'Over' if (iy_ev + iy_dep) >= 1 else 'Under',
                        'MS 2.5': 'Over' if (ms_ev + ms_dep) >= 3 else 'Under',
                        'KG': 'Yes' if (ms_ev > 0 and ms_dep > 0) else 'No',
                        '1Y SKOR (Poisson)': iy_skor, 'MS SKOR (Poisson)': ms_skor, 
                        'KRN (ORT)': round(b['C_KRN'].mean(), 1), 'KRT (ORT)': round(b['C_KRT'].mean(), 1),
                        '1Y': 'Home' if iy_ev > iy_dep else ('Draw' if iy_ev == iy_dep else 'Away'),
                        'MS': 'Home' if ms_ev > ms_dep else ('Draw' if ms_ev == ms_dep else 'Away'),
                        'ÖRNEK': len(b), 'idx': i
                    })
                    if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']} - {m['dep']}", 'p': int(b['C_FLIP'].mean()*100)})
            
            if final_list:
                df = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Tarihli Poisson Destekli Analizler")
                st.dataframe(df.drop(columns=['idx']).style.map(style_engine, subset=['1Y 0.5','MS 2.5','KG','1Y','MS']), use_container_width=True)
                
                if flips:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT Sürpriz Radarı")
                    for f in flips: st.warning(f"⚠️ **{f['m']}**: %{f['p']} sürpriz potansiyeli!")
            else: st.warning("Eşleşen örnek bulunamadı.")
        else: st.error("Bülten boş.")
