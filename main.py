import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Master", layout="wide")

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
yillar = st.sidebar.multiselect("Arşiv Sezonları", options=['2122','2223','2324','2425','2526'], default=['2324','2425','2526'])
TOLERANS = st.sidebar.slider("Hassasiyet (Tolerans)", 0.00, 0.30, 0.10, step=0.01)

# --- VERİ MOTORLARI ---
@st.cache_data(ttl=86400)
def futbol_arsiv_yukle(sezonlar):
    # Bu liste Football-Data sitesindeki TÜM ücretsiz ligleri kapsar
    ligler = {
        'E0':'İngiltere 1','E1':'İngiltere 2','SP1':'İspanya 1','SP2':'İspanya 2',
        'D1':'Almanya 1','D2':'Almanya 2','I1':'İtalya 1','I2':'İtalya 2',
        'F1':'Fransa 1','F2':'Fransa 2','T1':'Türkiye 1','N1':'Hollanda 1',
        'B1':'Belçika 1','P1':'Portekiz 1','SC0':'İskoçya 1','AUT':'Avusturya 1'
    }
    liste = []
    for k in ligler.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url, on_bad_lines='skip')
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def bulten_cek_full(key, t):
    # Tüm dünyadaki futbol bültenini kota dostu tek istekte çek
    url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={key}&regions=eu&markets=h2h'
    try:
        r = requests.get(url, timeout=20)
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
                        'ID': f"{tm.strftime('%H:%M')} | {m['home_team']} - {m['away_team']}",
                        'Lig': m['sport_title'], 'Saat': tm.strftime('%H:%M'),
                        'Ev': m['home_team'], 'Dep': m['away_team'],
                        'h_raw': h, 'b_raw': b, 'a_raw': a
                    })
                except: continue
        return pd.DataFrame(res).sort_values('Saat')
    except: return pd.DataFrame()

# --- ANA EKRAN ---
st.title("⚽ Vibe Pro Master Analiz")

if not API_KEY:
    st.warning("⚠️ Lütfen sol tarafa API Key girerek başlayın.")
else:
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🚀 BUGÜNKÜ TÜM BÜLTENİ ÇEK"):
            with st.spinner("API'den bülten alınıyor..."):
                st.session_state['full_bulten'] = bulten_cek_full(API_KEY, secili_tarih)
    with col2:
        if st.button("📚 ARŞİV VERİLERİNİ YÜKLE"):
            with st.spinner("5 Yıllık arşiv hafızaya alınıyor..."):
                st.session_state['full_arsiv'] = futbol_arsiv_yukle(yillar)
                st.success("Arşiv hazır!")

    if 'full_bulten' in st.session_state and not st.session_state['full_bulten'].empty:
        df_b = st.session_state['full_bulten']
        
        st.markdown("---")
        # MAÇ SEÇİMİ
        maclar = df_b['ID'].tolist()
        secim = st.selectbox("🎯 Analiz etmek istediğiniz maçı listeden seçin:", ["--- MAÇ SEÇİNİZ ---"] + maclar)
        
        if secim != "--- MAÇ SEÇİNİZ ---":
            m = df_b[df_b['ID'] == secim].iloc[0]
            st.info(f"📊 Oranlar: Ev: {m['h_raw']} | Ber: {m['b_raw']} | Dep: {m['a_raw']}")
            
            if 'full_arsiv' not in st.session_state:
                st.error("❌ Lütfen önce 'ARŞİV VERİLERİNİ YÜKLE' butonuna basın.")
            else:
                arsiv = st.session_state['full_arsiv']
                # FİLTRELEME
                b = arsiv[
                    (arsiv['B365H'].between(m['h_raw']-TOLERANS, m['h_raw']+TOLERANS)) & 
                    (arsiv['B365D'].between(m['b_raw']-TOLERANS, m['b_raw']+TOLERANS)) & 
                    (arsiv['B365A'].between(m['a_raw']-TOLERANS, m['a_raw']+TOLERANS))
                ].copy()
                
                if b.empty:
                    st.warning("⚠️ Bu oranlarla geçmişte bir eşleşme bulunamadı. Toleransı (Hassasiyet) artırmayı deneyin.")
                else:
                    st.success(f"✅ Arşivde {len(b)} adet benzer maç bulundu!")
                    
                    # Analiz Kısmı
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean()
                    ms25 = (b['FTHG']+b['FTAG']>=3).mean()
                    kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    iy_res = b['HTR'].value_counts(normalize=True).idxmax()
                    ms_res = b['FTR'].value_counts(normalize=True).idxmax()
                    
                    # TABLO TASARIMI
                    res_data = {
                        'İY 0.5 ÜST': f"%{int(iy05*100)}",
                        'MS 2.5 ÜST': f"%{int(ms25*100)}",
                        'KG VAR': f"%{int(kg*100)}",
                        'İY VİBE': iy_res.replace('H','Ev').replace('A','Dep').replace('D','Ber'),
                        'MS VİBE': ms_res.replace('H','Ev').replace('A','Dep').replace('D','Ber')
                    }
                    st.table(pd.DataFrame([res_data]))
                    
                    # GEÇMİŞ MAÇLAR
                    with st.expander("📚 Geçmiş Maçların Detayları"):
                        dt = pd.DataFrame()
                        dt['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                        dt['Maç'] = b['HomeTeam'] + " " + b['FTHG'].astype(int).astype(str) + "-" + b['FTAG'].astype(int).astype(str) + " " + b['AwayTeam']
                        dt['İY'] = b['HTHG'].astype(int).astype(str) + "-" + b['HTAG'].astype(int).astype(str)
                        st.dataframe(dt, use_container_width=True, hide_index=True)

    elif 'full_bulten' in st.session_state:
        st.info("Bu tarih için bülten boş veya çekilemedi.")
