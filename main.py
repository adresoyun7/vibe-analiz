import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

# Senin sevdiğin o renk motoru
def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if any(x in val_str for x in ['Over', 'Yes', 'Home', '1/1', '2/2', '1/2', '2/1']): 
        return 'background-color: #27ae60; color: white;'
    if any(x in val_str for x in ['Under', 'No', 'Away']): 
        return 'background-color: #c0392b; color: white;'
    if any(x in val_str for x in ['Draw', 'Tie', 'Beraberlik', 'X/']): 
        return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi v4.7")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.00, 0.30, 0.08, step=0.01)

FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "⚽ AVRUPA DİĞER": {'Hollanda': 'soccer_netherlands_eredivisie', 'Belçika': 'soccer_belgium_first_division', 'Portekiz': 'soccer_portugal_primeira_liga', 'İskoçya': 'soccer_scotland_premiership'}
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        select_all = st.checkbox(f"{kat} - Tümünü Seç", key=f"all_{kat}")
        for isim, kod in ligler.items():
            is_checked = st.checkbox(isim, value=select_all, key=f"cb_{kod}")
            if is_checked: secili_kodlar.append(kod)

@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar: return pd.DataFrame()
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

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
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik']), 0)
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key ve Lig seçimi yapın.")
    else:
        with st.spinner("📊 Vibe Hesaplanıyor..."):
            gecmis = futbol_veri_motoru(yillar)
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        if not bulten.empty:
            final_list = []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                
                if len(b) >= 1:
                    for col in ['FTHG','FTAG','HTHG','HTAG']: b[col] = b[col].fillna(0)
                    iy05 = (b['HTHG'] + b['HTAG'] >= 1).mean()
                    ms25 = (b['FTHG'] + b['FTAG'] >= 3).mean()
                    kg = ((b['FTHG'] > 0) & (b['FTAG'] > 0)).mean()
                    ms_mod = b['FTR'].mode()[0]; iy_mod = b['HTR'].mode()[0]
                    ms_p = b['FTR'].value_counts(normalize=True).get(ms_mod, 0)
                    iy_p = b['HTR'].value_counts(normalize=True).get(iy_mod, 0)
                    
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y_05': f"Over ({int(iy05*100)}%)",
                        'İY_15': f"Over ({int((b['HTHG']+b['HTAG']>=2).mean()*100)}%)",
                        'MS_15': f"Over ({int((b['FTHG']+b['FTAG']>=2).mean()*100)}%)",
                        'MS_25': f"Over ({int(ms25*100)}%)",
                        'MS_35': f"Over ({int((b['FTHG']+b['FTAG']>=4).mean()*100)}%)",
                        'KG_V': f"Yes ({int(kg*100)}%)",
                        '1Y_V': f"{iy_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber')} ({int(iy_p*100)}%)",
                        'MS_V': f"{ms_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber')} ({int(ms_p*100)}%)",
                        'ÖRNEK': len(b), 'idx': i, 'iy05_r': iy05, 'ms25_r': ms25, 'kg_r': kg, 'ms_m_r': ms_mod
                    })

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe Ana Bülten")
                st.dataframe(df_ana.drop(columns=['idx','iy05_r','ms25_r','kg_r','ms_m_r']).style.map(style_engine), use_container_width=True)
                
                st.markdown("---")
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        # --- ANALİZ ÖZETİ ---
                        st.info(f"🎯 **ANA TERCİH:** {'2.5 ÜST' if row['ms25_r'] > 0.65 else 'KG VAR' if row['kg_r'] > 0.6 else row['MS_V'].split(' ')[0]} | "
                                f"🥈 **KOMBO:** {row['MS_V'].split(' ')[0]} & {'KG VAR' if row['kg_r'] > 0.55 else 'KG YOK'}")
                        
                        # --- GENİŞ VE RENKLİ DETAYLI TABLO ---
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))].copy().sort_values('Date', ascending=False)
                        
                        dt = pd.DataFrame()
                        dt['Tarih'] = b_det['Date'].dt.strftime('%d.%m.%Y')
                        dt['Maç'] = b_det['HomeTeam'] + "-" + b_det['AwayTeam']
                        dt['İY'] = b_det['HTHG'].astype(int).astype(str)+"-"+b_det['HTAG'].astype(int).astype(str)
                        dt['MS'] = b_det['FTHG'].astype(int).astype(str)+"-"+b_det['FTAG'].astype(int).astype(str)
                        dt['1Y_05'] = (b_det['HTHG']+b_det['HTAG']>=1).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b_det['FTHG']+b_det['FTAG']>=3).map({True:'Over', False:'Under'})
                        dt['KG'] = ((b_det['FTHG']>0)&(b_det['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['HT/FT'] = b_det['HTR'].replace({'H':'1','A':'2','D':'X'}) + "/" + b_det['FTR'].replace({'H':'1','A':'2','D':'X'})
                        dt['Krn'] = (b_det.get('HC',0)+b_det.get('AC',0)).astype(int)
                        
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05','MS_25','KG','HT/FT']), use_container_width=True, hide_index=True)

                        # --- SÜRPRİZ RADARI ---
                        flip_p = ((b_det['HTR']=='H')&(b_det['FTR']=='A')|(b_det['HTR']=='A')&(b_det['FTR']=='H')).mean()
                        if flip_p >= 0.10:
                            st.error(f"🔥 SÜRPRİZ RADARI: Bu maçta %{int(flip_p*100)} oranında HT/FT sürprizi (1/2-2/1) saptandı!")
