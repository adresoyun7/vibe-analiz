import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Pro Expert v4.0", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi v4.0")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Veri Havuzu")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
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
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik']), 0)
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

# --- ANA MOTOR ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key ve Lig seçin.")
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
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean(); ms25 = (b['FTHG']+b['FTAG']>=3).mean(); kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    ms_mod = b['FTR'].mode()[0]; iy_mod = b['HTR'].mode()[0]
                    
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y_05': f"Over ({int(iy05*100)}%)",
                        'İY_15': f"Over ({int((b['HTHG']+b['HTAG']>=2).mean()*100)}%)",
                        'MS_15': f"Over ({int((b['FTHG']+b['FTAG']>=2).mean()*100)}%)",
                        'MS_25': f"Over ({int(ms25*100)}%)",
                        'MS_35': f"Over ({int((b['FTHG']+b['FTAG']>=4).mean()*100)}%)",
                        'KG_V': f"Yes ({int(kg*100)}%)",
                        '1Y_SKOR': (b['HTHG'].astype(int).astype(str)+"-"+b['HTAG'].astype(int).astype(str)).mode()[0],
                        'MS_SKOR': (b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)).mode()[0],
                        '1Y_V': f"{iy_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber')} ({int(b['HTR'].value_counts(normalize=True).get(iy_mod,0)*100)}%)",
                        'MS_V': f"{ms_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber')} ({int(b['FTR'].value_counts(normalize=True).get(ms_mod,0)*100)}%)",
                        'ÖRNEK': len(b), 'idx': i, 'iy05_r': iy05, 'ms25_r': ms25, 'kg_r': kg, 'ms_m_r': ms_mod, 'iy_m_r': iy_mod,
                        'h_o': m['h'], 'b_o': m['b'], 'a_o': m['a']
                    })

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe Analizi")
                st.dataframe(df_ana.drop(columns=['idx','iy05_r','ms25_r','kg_r','ms_m_r','iy_m_r','h_o','b_o','a_o']).style.map(style_engine), use_container_width=True)
                
                st.markdown("---")
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        # --- EXPERT TAHMİN MANTIĞI ---
                        b_det_data = gecmis[(gecmis['B365H'].between(bulten.loc[row['idx']]['h']-TOLERANS, bulten.loc[row['idx']]['h']+TOLERANS)) & (gecmis['B365D'].between(bulten.loc[row['idx']]['b']-TOLERANS, bulten.loc[row['idx']]['b']+TOLERANS)) & (gecmis['B365A'].between(bulten.loc[row['idx']]['a']-TOLERANS, bulten.loc[row['idx']]['a']+TOLERANS))].copy()
                        
                        htft = (b_det_data['HTR'] + "/" + b_det_data['FTR']).mode()[0].replace('H','1').replace('A','2').replace('D','X')
                        kg_durum = "KG VAR" if row['kg_r'] > 0.55 else "KG YOK"
                        ms_kg = f"MS {row['ms_m_r'].replace('H','1').replace('A','2').replace('D','X')} & {kg_durum}"
                        
                        w_text, w_color = "", "#27ae60"
                        if row['ms25_r'] >= 0.65 and row['kg_r'] < 0.50:
                            w_text = "⚠️ 3-0 RİSKİ: Üst beklentisi tek taraflı olabilir!"; w_color = "#f39c12"

                        st.markdown(f"""
                        <div style="background-color: #1e272e; padding: 15px; border-radius: 10px; border-left: 8px solid {w_color}; margin-bottom: 20px;">
                            <h4 style="color: white; margin-top: 0;">🎯 VİBE EXPERT RAPORU</h4>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                <p style="color: white;">🎯 <b>ANA TERCİH :</b> <span style="color: #27ae60;">{ms_kg}</span></p>
                                <p style="color: white;">🥈 <b>HT/FT VİBE :</b> <span style="color: #f39c12;">{htft}</span></p>
                                <p style="color: white;">🔥 <b>KOMBİNE :</b> <span style="color: #3498db;">{row['ms_m_r'].replace('H','1').replace('A','2').replace('D','X')} & 2.5 ÜST</span></p>
                                {f"<p style='color: #e74c3c;'>📍 <b>CANLI :</b> İY 0.5 ÜST</p>" if row['iy05_r'] > 0.75 else ""}
                            </div>
                            {f'<p style="color: #f39c12; font-weight: bold;">{w_text}</p>' if w_text else ""}
                        </div>
                        """, unsafe_allow_html=True)

                        # --- DETAYLI TABLO (TAM SÜTUNLAR) ---
                        dt = pd.DataFrame()
                        dt['Tarih'] = b_det_data['Date'].dt.strftime('%d.%m.%Y')
                        dt['Maç'] = b_det_data['HomeTeam'] + "-" + b_det_data['AwayTeam']
                        dt['İY'] = b_det_data['HTHG'].astype(int).astype(str)+"-"+b_det_data['HTAG'].astype(int).astype(str)
                        dt['MS'] = b_det_data['FTHG'].astype(int).astype(str)+"-"+b_det_data['FTAG'].astype(int).astype(str)
                        dt['1Y_05'] = (b_det_data['HTHG']+b_det_data['HTAG']>=1).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b_det_data['FTHG']+b_det_data['FTAG']>=3).map({True:'Over', False:'Under'})
                        dt['KG'] = ((b_det_data['FTHG']>0)&(b_det_data['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['Krn'] = (b_det_data.get('HC',0)+b_det_data.get('AC',0)).astype(int)
                        dt['HT/FT'] = b_det_data['HTR'].replace({'H':'1','A':'2','D':'X'}) + "/" + b_det_data['FTR'].replace({'H':'1','A':'2','D':'X'})
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05','MS_25','KG']), use_container_width=True, hide_index=True)

                        # --- SÜRPRİZ RADARI (1/2 - 2/1) ---
                        flip_p = ((b_det_data['HTR']=='H')&(b_det_data['FTR']=='A')|(b_det_data['HTR']=='A')&(b_det_data['FTR']=='H')).mean()
                        if flip_p >= 0.10:
                            st.warning(f"🔥 SÜRPRİZ RADARI: Bu maçta %{int(flip_p*100)} ihtimalle HT/FT Sürprizi (1/2 veya 2/1) görüldü!")
