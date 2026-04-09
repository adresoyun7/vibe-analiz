import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Veri Havuzu Ayarları")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.00, 0.30, 0.08, step=0.01)

FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "⚽ AVRUPA DİĞER": {'Hollanda Eredivisie': 'soccer_netherlands_eredivisie', 'Belçika Pro League': 'soccer_belgium_first_division', 'Portekiz Primeiralga': 'soccer_portugal_primeira_liga', 'İskoçya Premiership': 'soccer_scotland_premiership', 'Avusturya Bundesliga': 'soccer_austria_bundesliga'}
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

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
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
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
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Eksik giriş yapıldı.")
    else:
        with st.spinner("📊 Vibe Hesaplanıyor..."):
            gecmis = futbol_veri_motoru(yillar)
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        if not bulten.empty:
            final_list = []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                
                if len(b) >= min_ornek:
                    for col in ['FTHG','FTAG','HTHG','HTAG']: b[col] = b[col].fillna(0)
                    iy05_p = (b['HTHG'] + b['HTAG'] >= 1).mean()
                    ms15_p = (b['FTHG'] + b['FTAG'] >= 2).mean()
                    ms25_p = (b['FTHG'] + b['FTAG'] >= 3).mean()
                    kg_p = ((b['FTHG'] > 0) & (b['FTAG'] > 0)).mean()
                    ms_mod = b['FTR'].mode()[0]
                    
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y_05': f"Over ({int(iy05_p*100)}%) {'🔥' if iy05_p >= 0.8 else ''}",
                        'İY_15': f"{'Over' if (b['HTHG']+b['HTAG']>=2).mean() >= 0.5 else 'Under'} ({int((b['HTHG']+b['HTAG']>=2).mean()*100)}%)",
                        'MS_15': f"Over ({int(ms15_p*100)}%) {'🔥' if ms15_p >= 0.8 else ''}",
                        'MS_25': f"{'Over' if ms25_p >= 0.5 else 'Under'} ({int(ms25_p*100)}%) {'🔥' if ms25_p >= 0.8 else ''}",
                        'MS_35': f"{'Over' if (b['FTHG']+b['FTAG']>=4).mean() >= 0.5 else 'Under'} ({int((b['FTHG']+b['FTAG']>=4).mean()*100)}%)",
                        'KG_V': f"{'Yes' if kg_p >= 0.5 else 'No'} ({int(kg_p*100)}%) {'🔥' if kg_p >= 0.8 else ''}",
                        '1Y_SKOR': (b['HTHG'].astype(int).astype(str) + "-" + b['HTAG'].astype(int).astype(str)).mode()[0],
                        'MS_SKOR': (b['FTHG'].astype(int).astype(str) + "-" + b['FTAG'].astype(int).astype(str)).mode()[0],
                        '1Y_V': f"{b['HTR'].mode()[0].replace('H','Home').replace('A','Away').replace('D','Draw')} ({int(b['HTR'].value_counts(normalize=True).get(b['HTR'].mode()[0],0)*100)}%)",
                        'MS_V': f"{ms_mod.replace('H','Home').replace('A','Away').replace('D','Draw')} ({int(b['FTR'].value_counts(normalize=True).get(ms_mod,0)*100)}%)",
                        'ÖRNEK': len(b), 'idx': i,
                        'iy05_raw': iy05_p, 'ms15_raw': ms15_p, 'ms25_raw': ms25_p, 'kg_raw': kg_p, 'ms_vibe_raw': ms_mod
                    })

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe & Mod Skor Analizi")
                style_cols = ['1Y_05','İY_15','MS_15','MS_25','MS_35','KG_V','1Y_V','MS_V']
                st.dataframe(df_ana.drop(columns=['idx','iy05_raw','ms15_raw','ms25_raw','kg_raw','ms_vibe_raw']).style.map(style_engine, subset=style_cols), use_container_width=True)
                
                st.markdown("---")
                st.subheader("📚 Detaylı Analiz & Tahmin Raporu")
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        # --- TAHMİN RAPORU ---
                        ana_t = "Bilinmiyor"
                        if row['ms_vibe_raw'] == 'H' and row['ms25_raw'] < 0.6: ana_t = "MS 1"
                        elif row['ms_vibe_raw'] == 'A' and row['ms25_raw'] < 0.6: ana_t = "MS 2"
                        elif row['ms25_raw'] >= 0.65: ana_t = "2.5 ÜST"
                        else: ana_t = "KG VAR" if row['kg_raw'] > 0.6 else "1.5 ÜST"

                        alt_t = "KG VAR" if ana_t == "2.5 ÜST" and row['kg_raw'] > 0.65 else "EV 1.5 ÜST" if row['ms_vibe_raw'] == 'H' else "DEP 1.5 ÜST"

                        st.markdown(f"""
                        <div style="background-color: #1e272e; padding: 15px; border-radius: 10px; border-left: 5px solid #27ae60; margin-bottom: 20px;">
                            <h4 style="color: white; margin-top: 0;">🎯 VİBE TAHMİN RAPORU</h4>
                            <p style="font-size: 16px; margin: 5px 0;">🎯 <b>ANA TERCİH :</b> <span style="color: #27ae60;">{ana_t}</span></p>
                            <p style="font-size: 16px; margin: 5px 0;">🥈 <b>ALTERNATİF :</b> <span style="color: #f39c12;">{alt_t}</span></p>
                            {"<p style='font-size: 16px; margin: 5px 0;'>📍 <b>CANLI TERCİH :</b> <span style='color: #e74c3c;'>İY 0.5 ÜST</span></p>" if row['iy05_raw'] >= 0.75 else ""}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # --- DETAYLI TABLO (BOZULAN KISIM ONARILDI) ---
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))].copy().sort_values('Date', ascending=False)
                        
                        dt = pd.DataFrame()
                        dt['Tarih'] = b_det['Date'].dt.strftime('%d.%m.%Y')
                        dt['Ev'] = b_det['HomeTeam']; dt['Dep'] = b_det['AwayTeam']
                        dt['1Y_05'] = (b_det['HTHG'] + b_det['HTAG'] >= 1).map({True:'Over', False:'Under'})
                        dt['İY_15'] = (b_det['HTHG'] + b_det['HTAG'] >= 2).map({True:'Over', False:'Under'})
                        dt['MS_15'] = (b_det['FTHG'] + b_det['FTAG'] >= 2).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b_det['FTHG'] + b_det['FTAG'] >= 3).map({True:'Over', False:'Under'})
                        dt['KG_V'] = ((b_det['FTHG']>0) & (b_det['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['1Y_SKOR'] = b_det['HTHG'].fillna(0).astype(int).astype(str) + "-" + b_det['HTAG'].fillna(0).astype(int).astype(str)
                        dt['MS_SKOR'] = b_det['FTHG'].fillna(0).astype(int).astype(str) + "-" + b_det['FTAG'].fillna(0).astype(int).astype(str)
                        dt['1Y_V'] = b_det['HTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        dt['MS_V'] = b_det['FTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05','İY_15','MS_15','MS_25','KG_V','1Y_V','MS_V']), use_container_width=True, hide_index=True)
