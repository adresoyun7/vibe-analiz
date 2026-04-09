import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Interactive", layout="wide")

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
secili_tarih = st.sidebar.date_input("Bülten Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Analiz Ayarları")
yillar = st.sidebar.multiselect("Arşiv Sezonları", options=['2122','2223','2324','2425','2526'], default=['2223','2324','2425','2526'])
TOLERANS = st.sidebar.slider("Hassasiyet (Tolerans)", 0.00, 0.30, 0.08, step=0.01)

# --- VERİ MOTORLARI ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k, v in lig_map.items():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url, on_bad_lines='skip')
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def bulteni_getir(key, t):
    url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={key}&regions=eu&markets=h2h'
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200: return pd.DataFrame()
        data = r.json()
        res = []
        for m in data:
            tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
            if tm.date() == t:
                bookies = m.get('bookmakers', [])
                if not bookies: continue
                markets = bookies[0].get('markets', [])
                if not markets: continue
                o = markets[0]['outcomes']
                try:
                    h = next(x['price'] for x in o if x['name'] == m['home_team'])
                    a = next(x['price'] for x in o if x['name'] == m['away_team'])
                    b = next(x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik'])
                    res.append({
                        'Maç': f"{tm.strftime('%H:%M')} | {m['home_team']} - {m['away_team']}",
                        'Lig': m['sport_title'], 'Ev': h, 'Beraberlik': b, 'Deplasman': a,
                        'h_raw': h, 'b_raw': b, 'a_raw': a, 'ev_ad': m['home_team'], 'dep_ad': m['away_team']
                    })
                except: continue
        return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- ANA EKRAN ---
st.title("⚽ Vibe Bülten Analizörü")

if not API_KEY:
    st.info("👋 Devam etmek için yan menüye API Key girin.")
else:
    if st.button("📅 GÜNLÜK BÜLTENİ ÇEK"):
        st.session_state['bulten_df'] = bulteni_getir(API_KEY, secili_tarih)
        st.session_state['arsiv_df'] = futbol_veri_motoru(yillar)

    if 'bulten_df' in st.session_state and not st.session_state['bulten_df'].empty:
        df_bulten = st.session_state['bulten_df']
        
        st.markdown("---")
        mac_listesi = df_bulten['Maç'].tolist()
        secili_mac_adi = st.selectbox("🎯 Analiz Etmek İstediğiniz Maçı Seçin:", ["Seçiniz..."] + mac_listesi)
        
        if secili_mac_adi != "Seçiniz...":
            mac_data = df_bulten[df_bulten['Maç'] == secili_mac_adi].iloc[0]
            
            with st.spinner("🔍 Arşiv taranıyor..."):
                gecmis = st.session_state['arsiv_df']
                # ORAN EŞLEŞTİRME
                b = gecmis[
                    (gecmis['B365H'].between(mac_data['h_raw']-TOLERANS, mac_data['h_raw']+TOLERANS)) & 
                    (gecmis['B365D'].between(mac_data['b_raw']-TOLERANS, mac_data['b_raw']+TOLERANS)) & 
                    (gecmis['B365A'].between(mac_data['a_raw']-TOLERANS, mac_data['a_raw']+TOLERANS))
                ].copy()
                
                if b.empty:
                    st.error(f"❌ Maalesef bu oranlarla ({mac_data['h_raw']} - {mac_data['b_raw']} - {mac_data['a_raw']}) geçmişte eşleşen maç bulunamadı. Hassasiyeti artırmayı deneyin.")
                else:
                    # ANALİZ HESAPLAMALARI
                    st.success(f"✅ {len(b)} adet benzer geçmiş maç bulundu!")
                    
                    # Kolonları temizle
                    for col in ['FTHG','FTAG','HTHG','HTAG']: b[col] = b[col].fillna(0)
                    
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean(); iy15 = (b['HTHG']+b['HTAG']>=2).mean()
                    ms15 = (b['FTHG']+b['FTAG']>=2).mean(); ms25 = (b['FTHG']+b['FTAG']>=3).mean(); ms35 = (b['FTHG']+b['FTAG']>=4).mean()
                    kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    iy_mod = b['HTR'].mode()[0]; ms_mod = b['FTR'].mode()[0]
                    
                    # ÖZET TABLO
                    res_df = pd.DataFrame([{
                        '1Y 0.5': f"{int(iy05*100)}% {'Over' if iy05>=0.5 else 'Under'}",
                        '1Y 1.5': f"{int(iy15*100)}% {'Over' if iy15>=0.5 else 'Under'}",
                        'MS 1.5': f"{int(ms15*100)}% {'Over' if ms15>=0.5 else 'Under'}",
                        'MS 2.5': f"{int(ms25*100)}% {'Over' if ms25>=0.5 else 'Under'}",
                        'MS 3.5': f"{int(ms35*100)}% {'Over' if ms35>=0.5 else 'Under'}",
                        'KG VAR': f"{int(kg*100)}% {'Yes' if kg>=0.5 else 'No'}",
                        '1Y VİBE': iy_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber'),
                        'MS VİBE': ms_mod.replace('H','Ev').replace('A','Dep').replace('D','Ber')
                    }])
                    
                    st.subheader("📊 Analiz Sonuçları")
                    st.dataframe(res_df.style.map(style_engine), use_container_width=True)
                    
                    # DETAYLI GEÇMİŞ TABLOSU
                    st.subheader("📚 Benzer Oranlı Geçmiş Maçlar")
                    dt = pd.DataFrame()
                    dt['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                    dt['Ev'] = b['HomeTeam']; dt['Dep'] = b['AwayTeam']
                    dt['1Y'] = b['HTHG'].astype(int).astype(str)+"-"+b['HTAG'].astype(int).astype(str)
                    dt['MS'] = b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)
                    dt['Krn'] = (b.get('HC', 0).fillna(0) + b.get('AC', 0).fillna(0)).astype(int)
                    dt['1Y_V'] = b['HTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                    dt['MS_V'] = b['FTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                    
                    st.dataframe(dt.style.map(style_engine, subset=['1Y_V','MS_V']), use_container_width=True, hide_index=True)
    elif 'bulten_df' in st.session_state:
        st.warning("Seçilen tarihte bülten boş görünüyor.")
