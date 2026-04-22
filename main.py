import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import math

# ─────────────────────────────────────────
st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")
# ─────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #0d0f14;
    color: #fff;
}

section[data-testid="stSidebar"] {
    background: #111318 !important;
    border-right: 1px solid #1e2130;
}
section[data-testid="stSidebar"] label {
    font-size: 0.82rem !important;
    color: #aaa !important;
}
.main .block-container {
    background: #0d0f14;
    padding-top: 1.2rem;
    max-width: 1500px;
}

/* UI Bileşenleri */
.mac-kart {
    background:#13151e;
    border:1px solid #1e2130;
    border-radius:16px;
    padding:16px 18px;
    margin-bottom:12px;
    display:grid;
    grid-template-columns:90px 1.4fr 180px 160px 160px;
    gap:14px;
    align-items:center;
    transition:.2s ease;
}
.mac-kart:hover {
    border-color:#27ae60;
}
.ana-pill {
    background:#27ae60;
    color:#fff;
    font-family:'Rajdhani',sans-serif;
    font-size:1.08rem;
    font-weight:700;
    padding:5px 15px;
    border-radius:7px;
    display:inline-block;
}
.ana-pill.kirmizi { background:#c0392b; }
.ana-pill.sari { background:#c9a227; color:#111; }

/* Progress Bar */
.guven-bar {
    height:6px;
    border-radius:6px;
    background:#1e2130;
    margin-top:5px;
    overflow:hidden;
}
.guven-fill { height:100%; border-radius:6px; }

/* Detay Sayfası */
.hero-boxes {
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    gap:14px;
    margin-bottom:14px;
}
.hbox { border-radius:16px; padding:20px 24px; text-align:center; border:1px solid #1e2130; }
.hbox.green { background:linear-gradient(135deg,#153b25,#1b5636); border-color:#27ae60; }
.hbox.blue { background:linear-gradient(135deg,#102340,#173764); border-color:#2c7be5; }
.hbox.dark { background:linear-gradient(135deg,#1a1d28,#232845); }

.tk-row {
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:10px 0;
    border-bottom:1px solid #1a1d26;
}
</style>
""", unsafe_allow_html=True)

# ─── YARDIMCI FONKSİYONLAR ───
def format_tr_date(d):
    aylar = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}
    gunler = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}
    return f"{d.day} {aylar[d.month]} {d.year} {gunler[d.weekday()]}"

def guven_renk(pct):
    if pct >= 70: return "#27ae60", "badge-yuksek", "Yüksek Güven"
    if pct >= 55: return "#e67e22", "badge-orta", "Orta Güven"
    return "#e74c3c", "badge-dusuk", "Düşük Güven"

def risk_seviyesi(pct, flip_p):
    if pct >= 70 and flip_p < 0.15: return "DÜŞÜK", "risk-dusuk"
    if pct >= 55: return "ORTA", "risk-orta"
    return "YÜKSEK", "risk-yuksek"

def tahmini_skor(b, ms_mod):
    eg = math.floor(b['FTHG'].mean() + 0.5) if not b.empty else 1
    dg = math.floor(b['FTAG'].mean() + 0.5) if not b.empty else 1
    if ms_mod == 'H' and eg <= dg: eg = dg + 1
    if ms_mod == 'A' and dg <= eg: dg = eg + 1
    return eg, dg

# ─── VERİ MOTORU ───
@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar: return pd.DataFrame()
    lig_map = ['T1','E0','SP1','D1','I1','F1','N1','B1','P1','SC0']
    liste = []
    for k in lig_map:
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A']
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
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/', 
                             params={"apiKey": key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=12)
            if r.status_code != 200: continue
            data = r.json()
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() != t: continue
                bookies = m.get('bookmakers', [])
                if not bookies: continue
                outcomes = bookies[0]['markets'][0]['outcomes']
                h = next((x['price'] for x in outcomes if x['name'] == m['home_team']), None)
                a = next((x['price'] for x in outcomes if x['name'] == m['away_team']), None)
                b = next((x['price'] for x in outcomes if str(x['name']).lower() in ['draw', 'tie', 'beraberlik']), None)
                if h and a and b:
                    res.append({'lig': m.get('sport_title', k), 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': float(h), 'b': float(b), 'a': float(a)})
        except: continue
    return pd.DataFrame(res)

def hesapla(b_df, m_row, tolerans):
    b = b_df[
        (b_df['B365H'].between(m_row['h'] - tolerans, m_row['h'] + tolerans)) &
        (b_df['B365D'].between(m_row['b'] - tolerans, m_row['b'] + tolerans)) &
        (b_df['B365A'].between(m_row['a'] - tolerans, m_row['a'] + tolerans))
    ].copy()
    
    if b.empty: return None, b

    # Olasılıklar
    ms25_p = (b['FTHG'] + b['FTAG'] >= 3).mean()
    ms35_p = (b['FTHG'] + b['FTAG'] >= 4).mean()
    kg_p   = ((b['FTHG'] > 0) & (b['FTAG'] > 0)).mean()
    iy05_p = (b['HTHG'] + b['HTAG'] >= 1).mean()
    iy15_p = (b['HTHG'] + b['HTAG'] >= 2).mean()

    ms_vc = b['FTR'].value_counts(normalize=True)
    ms_mod = ms_vc.idxmax()
    ms_p = ms_vc.get(ms_mod, 0)
    
    # Ana Tahmin Belirleme
    cands = [
        (ms_p, "MS 1" if ms_mod=='H' else "MS 2" if ms_mod=='A' else "Beraberlik", int(ms_p*100), m_row['h'] if ms_mod=='H' else m_row['a'] if ms_mod=='A' else m_row['b']),
        (ms25_p if ms25_p >= 0.5 else 1-ms25_p, "2.5 Üst" if ms25_p>=0.5 else "2.5 Alt", int(max(ms25_p, 1-ms25_p)*100), "-"),
        (kg_p if kg_p >= 0.5 else 1-kg_p, "KG Var" if kg_p>=0.5 else "KG Yok", int(max(kg_p, 1-kg_p)*100), "-")
    ]
    
    best = max(cands, key=lambda x: x[0])
    ana_label, ana_p, ana_oran = best[1], best[2], best[3]
    
    others = [c for c in cands if c[1] != ana_label]
    alt = max(others, key=lambda x: x[0])
    
    # Canlı Önerisi
    canli_label = "İY 0.5 Üst" if iy05_p >= 0.65 else "Canlı İzle"
    
    flip_p = (((b['HTR'] == 'H') & (b['FTR'] == 'A')) | ((b['HTR'] == 'A') & (b['FTR'] == 'H'))).mean()
    risk_l, risk_cls = risk_seviyesi(ana_p, flip_p)
    eg, dg = tahmini_skor(b, ms_mod)
    gc, gb_cls, gb_lbl = guven_renk(ana_p)

    return {
        'ana_label': ana_label, 'ana_p': ana_p, 'ana_oran': ana_oran,
        'alt_label': alt[1], 'alt_p': alt[2],
        'kg_label': "KG Var" if kg_p >= 0.5 else "KG Yok",
        'canli_label': canli_label, 'canli_p': int(iy05_p*100),
        'ms1_p': int(ms_vc.get('H', 0)*100), 'msx_p': int(ms_vc.get('D', 0)*100), 'ms2_p': int(ms_vc.get('A', 0)*100),
        'ms25_p': int(ms25_p*100), 'ms25a_p': int((1-ms25_p)*100),
        'kg_var_p': int(kg_p*100), 'kg_yok_p': int((1-kg_p)*100),
        'iy05_p': int(iy05_p*100), 'iy05a_p': int((1-iy05_p)*100),
        'ms35_p': int(ms35_p*100), 'flip_p': flip_p, 'htft_mod': "-", 'htft_p': 0,
        'risk_label': risk_l, 'risk_cls': risk_cls, 'eg': eg, 'dg': dg,
        'guven_renk': gc, 'guven_badge_cls': gb_cls, 'guven_badge_lbl': gb_lbl, 'ornek': len(b),
        'ms_mod': ms_mod
    }, b.sort_values('Date', ascending=False)

# ─── SESSİON VE SİDEBAR ───
for key, default in [('final_list',[]),('detay_idx',None),('filtre','tumu'),('kupona',[])]:
    if key not in st.session_state: st.session_state[key] = default

with st.sidebar:
    st.markdown('<h2 style="font-family:Rajdhani; color:#27ae60;">VIBE PRO v6.3</h2>', unsafe_allow_html=True)
    API_KEY = st.text_input("API Key", type="password")
    secili_tarih = st.date_input("Analiz Tarihi", datetime.now())
    yillar = st.multiselect("Sezonlar", ['2324','2425','2526'], default=['2425','2526'])
    TOLERANS = st.slider("Hassasiyet", 0.01, 0.20, 0.08)
    analiz_btn = st.button("🚀 ANALİZİ BAŞLAT", use_container_width=True, type="primary")

# ─── ANALİZ TETİKLEME ───
if analiz_btn:
    if not API_KEY: st.error("API Key Gerekli")
    else:
        with st.spinner("Analiz ediliyor..."):
            gecmis = futbol_veri_motoru(yillar)
            bulten = bulten_cek(API_KEY, ['soccer_turkey_super_league','soccer_epl'], secili_tarih)
            final = []
            for _, m in bulten.iterrows():
                res, b_det = hesapla(gecmis, m, TOLERANS)
                if res: final.append({'m': m.to_dict(), 't': res, 'b': b_det})
            st.session_state.final_list = final
            st.rerun()

# ─── EKRAN YÖNETİMİ ───
if st.session_state.detay_idx is not None:
    # Detay Sayfası Tasarımı (Kısaltılmış)
    idx = st.session_state.detay_idx
    item = st.session_state.final_list[idx]
    if st.button("← Geri"): 
        st.session_state.detay_idx = None
        st.rerun()
    st.title(f"{item['m']['ev']} vs {item['m']['dep']}")
    st.json(item['t']) # Verileri kontrol etmek için
else:
    # Ana Liste Ekranı
    st.header("ANA MAÇ EKRANI")
    for i, item in enumerate(st.session_state.final_list):
        m, t = item['m'], item['t']
        st.markdown(f"""
        <div class="mac-kart">
            <div style="text-align:center"><b>{m['zaman'].strftime('%H:%M')}</b><br><small>{m['lig']}</small></div>
            <div><b>{m['ev']}</b><br>{m['dep']}</div>
            <div><span class="ana-pill">{t['ana_label']}</span><br><small>Güven: %{t['ana_p']}</small></div>
            <div><small>Alt: {t['alt_label']}</small><br><small>Sürpriz: {t['kg_label']}</small></div>
            <div>{m['h']} - {m['b']} - {m['a']}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"Detay Gör #{i}", key=f"btn_{i}"):
            st.session_state.detay_idx = i
            st.rerun()
