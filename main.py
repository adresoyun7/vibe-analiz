import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Pro Master", layout="wide")

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
TOLERANS = st.sidebar.slider("Hassasiyet (Tolerans)", 0.00, 0.30, 0.12, step=0.01)

# --- VERİ MOTORLARI ---
@st.cache_data(ttl=86400)
def futbol_arsiv_yukle(sezonlar):
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

def bulten_cek_master(key, t):
    # API'den tüm futbol bültenini çek (Sadece bugün değil, genel listeyi çeker)
    url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={key}&regions=eu&markets=h2h'
    try:
        r = requests.get(url, timeout=25)
        if r.status_code != 200:
            st.error(f"API Hatası ({r.status_code}): {r.text}")
            return pd.DataFrame()
        data = r.json()
        res = []
        for m in data:
            # Türkiye saatine göre ayarla (+3)
            tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
            # Seçili tarihi ve o tarihten bir sonraki günü de kontrol eder (Gece maçları için)
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
        return pd.DataFrame(res).sort_values('Saat') if res else pd.DataFrame()
    except Exception as e:
        st.error(f"Sistem Hatası: {e}")
        return pd.DataFrame()

# --- ANA EKRAN ---
st.title("⚽ Vibe Pro Master Analiz")

if not API_KEY:
    st.info("👋 Başlamak için yan menüye geçerli bir API Key girin.")
else:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🚀 BÜLTENİ TARA (GÜNCELLE)"):
            with st.spinner("API'den güncel bülten verileri alınıyor..."):
                b_df = bulten_cek_master(API_KEY, secili_tarih)
                if not b_df.empty:
                    st.session_state['master_bulten'] = b_df
                    st.success(f"{len(b_df)} maç bulundu!")
                else:
                    st.session_state['master_bulten'] = pd.DataFrame()
                    st.warning("Seçilen tarihte bülten boş veya veri gelmedi.")
    with c2:
        if st.button("📚 ARŞİVİ YÜKLE / YENİLE"):
            with st.spinner("5 Yıllık veri havuzu yükleniyor..."):
                st.session_state['master_arsiv'] = futbol_arsiv_yukle(yillar)
                st.success("Arşiv verileri başarıyla yüklendi!")

    if 'master_bulten' in st.session_state and not st.session_state['master_bulten'].empty:
        df_b = st.session_state['master_bulten']
        st.markdown("---")
        
        # MAÇ SEÇİMİ
        mac_secimi = st.selectbox("🎯 Analiz edilecek maçı seçin:", ["--- MAÇ LİSTESİ ---"] + df_b['ID'].tolist())
        
        if mac_secimi != "--- MAÇ LİSTESİ ---":
            m_data = df_b[df_b['ID'] == mac_secimi].iloc[0]
            
            # ANALİZ BAŞLAT
            if 'master_arsiv' not in st.session_state:
                st.error("❌ Lütfen önce sağdaki 'ARŞİVİ YÜKLE' butonuna basın.")
            else:
                arsiv = st.session_state['master_arsiv']
                # ORANLARI KIYASLA
                b = arsiv[
                    (arsiv['B365H'].between(m_data['h_raw']-TOLERANS, m_data['h_raw']+TOLERANS)) & 
                    (arsiv['B365D'].between(m_data['b_raw']-TOLERANS, m_data['b_raw']+TOLERANS)) & 
                    (arsiv['B365A'].between(m_data['a_raw']-TOLERANS, m_data['a_raw']+TOLERANS))
                ].copy()
                
                if b.empty:
                    st.warning(f"⚠️ Bu oranlarla ({m_data['h_raw']}-{m_data['b_raw']}-{m_data['a_raw']}) geçmişte eşleşen maç bulunamadı. Toleransı biraz artırmayı deneyin.")
                else:
                    st.success(f"✅ {len(b)} adet geçmiş maç örneği bulundu!")
                    
                    # HESAPLAMALAR
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean()
                    ms25 = (b['FTHG']+b['FTAG']>=3).mean()
                    kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    
                    # TABLO
                    res_df = pd.DataFrame([{
                        '1Y 0.5 ÜST': f"%{int(iy05*100)}",
                        'MS 2.5 ÜST': f"%{int(ms25*100)}",
                        'KG VAR': f"%{int(kg*100)}",
                        '1Y VİBE': b['HTR'].mode()[0].replace('H','Ev').replace('A','Dep').replace('D','Ber'),
                        'MS VİBE': b['FTR'].mode()[0].replace('H','Ev').replace('A','Dep').replace('D','Ber')
                    }])
                    st.table(res_df)
                    
                    # GEÇMİŞ LİSTESİ
                    with st.expander("📚 Benzer Maçların Listesi"):
                        st.dataframe(b[['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTR','FTR']], use_container_width=True)
