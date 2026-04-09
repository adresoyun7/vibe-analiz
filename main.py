import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

# POISSON ANALİZ MOTORU
def poisson_analiz(ev_avg, dep_avg):
    if ev_avg <= 0 and dep_avg <= 0: return "0-0", 0.0, 0.0
    ev_avg, dep_avg = max(ev_avg, 0.05), max(dep_avg, 0.05)
    max_g = 6
    ev_probs = [poisson.pmf(i, ev_avg) for i in range(max_g)]
    dep_probs = [poisson.pmf(i, dep_avg) for i in range(max_g)]
    m = np.outer(ev_probs, dep_probs)
    ev_s, dep_s = np.unravel_index(m.argmax(), m.shape)
    ust_prob = (1 - (m[0,0] + m[0,1] + m[0,2] + m[1,0] + m[1,1] + m[2,0])) * 100
    kg_prob = (1 - (sum(m[0,:]) + sum(m[:,0]) - m[0,0])) * 100
    return f"{ev_s}-{dep_s}", round(ust_prob, 1), round(kg_prob, 1)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.30, 0.10)

FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇸🇦 ARAP LİGLERİ": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'}
}

secili_kodlar = []
for kat_isim, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    sezonlar = ['2324', '2425', '2526']
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10)
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
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

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
                    iy_skor_mod = (b['HTHG'].astype(int).astype(str) + "-" + b['HTAG'].astype(int).astype(str)).mode()[0]
                    ms_skor_mod = (b['FTHG'].astype(int).astype(str) + "-" + b['FTAG'].astype(int).astype(str)).mode()[0]
                    iy_e, iy_d = map(int, iy_skor_mod.split('-'))
                    ms_e, ms_d = map(int, ms_skor_mod.split('-'))
                    
                    c_flip = ((b['HTR'] == 'H') & (b['FTR'] == 'A')) | ((b['HTR'] == 'A') & (b['FTR'] == 'H'))
                    if c_flip.any(): flips.append({'m': f"{m['ev']} - {m['dep']}", 'p': int(c_flip.mean()*100)})

                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y_05': 'Over' if (iy_e+iy_d) >= 1 else 'Under',
                        'MS_15': 'Over' if (ms_e+ms_d) >= 2 else 'Under',
                        'MS_25': 'Over' if (ms_e+ms_d) >= 3 else 'Under',
                        'KG_V': 'Yes' if (ms_e > 0 and ms_d > 0) else 'No',
                        '1Y_SKOR': iy_skor_mod, 'MS_SKOR': ms_skor_mod,
                        '1Y_V': 'Home' if iy_e > iy_d else ('Draw' if iy_e == iy_d else 'Away'),
                        'MS_V': 'Home' if ms_e > ms_d else ('Draw' if ms_e == ms_d else 'Away'),
                        'ÖRNEK': len(b), 'idx': i, 'avg_ev': b['FTHG'].mean(), 'avg_dep': b['FTAG'].mean()
                    })

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe Analizleri")
                
                # ANA TABLO RENKLENDİRME (KİLİTLİ İSİMLER)
                st.dataframe(df_ana.drop(columns=['idx','avg_ev','avg_dep']).style.map(style_engine, subset=['1Y_05','MS_15','MS_25','KG_V','1Y_V','MS_V']), use_container_width=True)
                
                st.markdown("---")
                st.subheader("📚 Maç Detayları & Poisson")
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        p_skor, p_ust, p_kg = poisson_analiz(row['avg_ev'], row['avg_dep'])
                        st.info(f"📊 **Poisson Tahmini:** Beklenen Skor: **{p_skor}** | Üst Olasılığı: **%{p_ust}** | KG Olasılığı: **%{p_kg}**")
                        
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))].copy()
                        
                        dt = pd.DataFrame()
                        dt['Tarih'] = b_det['Date'].dt.strftime('%d.%m.%Y')
                        dt['Ev'] = b_det['HomeTeam']
                        dt['Dep'] = b_det['AwayTeam']
                        dt['1Y_05'] = (b_det['HTHG'] + b_det['HTAG'] >= 1).map({True:'Over', False:'Under'})
                        dt['MS_15'] = (b_det['FTHG'] + b_det['FTAG'] >= 2).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b_det['FTHG'] + b_det['FTAG'] >= 3).map({True:'Over', False:'Under'})
                        dt['KG_V'] = ((b_det['FTHG']>0) & (b_det['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['1Y_SKOR'] = b_det['HTHG'].astype(int).astype(str) + "-" + b_det['HTAG'].astype(int).astype(str)
                        dt['MS_SKOR'] = b_det['FTHG'].astype(int).astype(str) + "-" + b_det['FTAG'].astype(int).astype(str)
                        dt['Krn'] = (b_det['HC'] + b_det['AC']).astype(int)
                        dt['Krt'] = (b_det['HY'] + b_det['AY']).astype(int)
                        dt['1Y_V'] = b_det['HTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        dt['MS_V'] = b_det['FTR'].replace({'H':'Home','A':'Away','D':'Draw'})

                        # DETAY TABLO RENKLENDİRME (KİLİTLİ İSİMLER)
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05','MS_15','MS_25','KG_V','1Y_V','MS_V']), use_container_width=True)
                
                if flips:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT Sürpriz Radarı (1/2 - 2/1)")
                    for f in flips: st.warning(f"⚠️ **{f['m']}**: Geçmişte bu oranlarla %{f['p']} sürpriz HT/FT dönüşü olmuş!")
            else: st.warning("Eşleşen maç bulunamadı.")
