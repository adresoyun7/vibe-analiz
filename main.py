import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

st.markdown("""
<style>
.detay-panel {
    background: #12121f;
    border: 1px solid #4a9eff;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 16px;
}
.oran-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 0.9em;
    margin: 2px;
}
.stat-kutu {
    background: #1a1a2e;
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    border: 1px solid #2a2a4a;
    margin-bottom: 6px;
}
.stat-sayi { font-size: 1.6em; font-weight: bold; color: #4a9eff; }
.stat-etiket { font-size: 0.75em; color: #888; margin-top: 2px; }
.progress-bar-bg {
    background: #2a2a4a;
    border-radius: 6px;
    height: 16px;
    width: 100%;
    overflow: hidden;
    margin: 3px 0 1px 0;
}
.skor-chip {
    display: inline-block;
    background: #2a2a4a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 3px 9px;
    font-size: 0.85em;
    margin: 2px;
    color: #ddd;
}
.skor-chip-top {
    background: #1a3a5c;
    border-color: #4a9eff;
    color: #4a9eff;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

def progress_bar(pct, renk="green"):
    renk_map = {"green": "#2ecc71", "red": "#e74c3c", "gold": "#f39c12"}
    color = renk_map.get(renk, "#2ecc71")
    return f"""
    <div class="progress-bar-bg">
      <div style="background:{color};height:100%;width:{min(pct,100):.0f}%;border-radius:6px;"></div>
    </div>
    <small style="color:#888">%{pct:.0f}</small>
    """

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color:#27ae60;color:white;'
    if val in ['Under', 'No', 'Away']: return 'background-color:#c0392b;color:white;'
    if val in ['Draw', 'Tie']:          return 'background-color:#f39c12;color:white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
spor_turu    = st.sidebar.radio("Analiz Türü", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY      = st.sidebar.text_input("The Odds API Key", type="password")
bugun        = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek    = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS     = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {
        'Şampiyonlar Ligi': 'soccer_uefa_champs_league',
        'Avrupa Ligi':      'soccer_uefa_europa_league',
        'Konferans Ligi':   'soccer_uefa_europa_conference_league',
    },
    "🇹🇷 TÜRKİYE": {
        'Süper Lig': 'soccer_turkey_super_league',
        '1. Lig':    'soccer_turkey_pTT_1_lig',
    },
    "🇪🇺 AVRUPA MAJÖR": {
        'İngiltere': 'soccer_epl',
        'İspanya':   'soccer_spain_la_liga',
        'Almanya':   'soccer_germany_bundesliga',
        'İtalya':    'soccer_italy_serie_a',
        'Fransa':    'soccer_france_ligue_one',
    },
    "🇪🇺 AVRUPA DİĞER & 🇸🇦 ARAP": {
        'Hollanda':        'soccer_netherlands_eredivisie',
        'Belçika':         'soccer_belgium_first_div',
        'Portekiz':        'soccer_portugal_primeira_liga',
        'Avusturya':       'soccer_austria_bundesliga',
        'İskoçya':         'soccer_scotland_premiership',
        'Polonya':         'soccer_poland_ekstraklasa',
        'Romanya':         'soccer_romania_liga1',
        'Suudi Arabistan': 'soccer_saudi_arabia_pro_league',
        'BAE Pro Lig':     'soccer_uae_pro_league',
    },
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {
        'Euroleague': 'basketball_euroleague',
        'NBA':        'basketball_nba',
    },
    "🇪🇺 AVRUPA LİGLERİ": {
        'Türkiye BSL': 'basketball_turkey_bsl',
        'İspanya ACB': 'basketball_spain_liga_endesa',
    },
}

lig_havuzu    = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

st.sidebar.markdown("---")
if "genel_secici" not in st.session_state:
    st.session_state["genel_secici"] = False

def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values():
            st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox(f"🚀 Bütün {spor_turu} Liglerini Seç",
                    key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"):
                secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {
        'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1',
        'I1':'IT1','F1':'FR1','N1':'NL','B1':'BE',
        'P1':'PT','SC0':'SC1','AUT':'AT',
    }
    sezonlar = ['2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url  = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df   = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG',
                        'HTHG','HTAG','FTR','HTR','B365H','B365D',
                        'B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                ms   = temp['FTHG'] + temp['FTAG']
                iy   = temp['HTHG'] + temp['HTAG']
                temp['C_1Y05'] = iy  > 0.5
                temp['C_1Y15'] = iy  > 1.5
                temp['C_MS15'] = ms  > 1.5
                temp['C_MS25'] = ms  > 2.5
                temp['C_MS35'] = ms  > 3.5
                temp['C_KG']   = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_KRN']  = temp['HC'] + temp['AC']
                temp['C_KRT']  = temp['HY'] + temp['AY']
                temp['C_FLIP'] = (
                    ((temp['HTR']=='H') & (temp['FTR']=='A')) |
                    ((temp['HTR']=='A') & (temp['FTR']=='H'))
                )
                temp['S1Y'] = (temp['HTHG'].astype(int).astype(str) + "-" +
                               temp['HTAG'].astype(int).astype(str))
                temp['SMS'] = (temp['FTHG'].astype(int).astype(str) + "-" +
                               temp['FTAG'].astype(int).astype(str))
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except:
                continue
    return pd.concat(liste).sort_values('Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t, spor):
    all_res, hata = [], []
    for k in kodlar:
        try:
            r = requests.get(
                f'https://api.the-odds-api.com/v4/sports/{k}/odds/'
                f'?apiKey={key}&regions=eu&markets=h2h',
                timeout=10
            )
            if r.status_code == 401:
                hata.append(f"❌ {k}: API key geçersiz (401)")
                continue
            if r.status_code == 422:
                hata.append(f"❌ {k}: Geçersiz lig kodu (422)")
                continue
            if r.status_code == 429:
                hata.append(f"⏸️ {k}: Kota doldu (429)")
                continue
            if r.status_code != 200:
                hata.append(f"❌ {k}: HTTP {r.status_code}")
                continue

            data = r.json()
            if not isinstance(data, list):
                hata.append(f"⚠️ {k}: Beklenmeyen yanıt")
                continue
            if not data:
                hata.append(f"ℹ️ {k}: Bülten boş")
                continue

            mac_say = 0
            for m in data:
                try:
                    tm = (datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
                          + timedelta(hours=3))
                    if tm.date() != t:
                        continue
                    mac_say += 1
                    bookies = m.get('bookmakers', [])
                    if not bookies:
                        continue
                    best = max(bookies,
                               key=lambda b: len(b['markets'][0]['outcomes'])
                               if b.get('markets') else 0)
                    o  = best['markets'][0]['outcomes']
                    h  = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a  = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    br = 0
                    if spor == "⚽ Futbol":
                        br = next((x['price'] for x in o
                                   if x['name'].lower() in ['draw','tie']), 0)
                    if h > 0 and a > 0:
                        all_res.append({'lig': m['sport_title'], 'zaman': tm,
                                        'ev': m['home_team'], 'dep': m['away_team'],
                                        'h': h, 'b': br, 'a': a})
                except:
                    continue

            if mac_say == 0 and data:
                yakin = (datetime.strptime(data[0]['commence_time'],
                         "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)).strftime('%d.%m.%Y')
                hata.append(f"📅 {k}: {t} tarihinde maç yok. Yakın: {yakin}")

        except requests.exceptions.Timeout:
            hata.append(f"⏱️ {k}: Zaman aşımı")
        except Exception as e:
            hata.append(f"💥 {k}: {e}")

    if hata:
        with st.expander(f"🔍 Bülten Günlüğü ({len(hata)} mesaj)",
                         expanded=len(all_res) == 0):
            for msg in hata:
                st.text(msg)

    return pd.DataFrame(all_res)


# ─────────────────────────────────────────────
# MAÇ DETAY PANELİ
# ─────────────────────────────────────────────
def detay_paneli(m_row, b):
    toplam = len(b)
    if toplam == 0:
        st.warning("Bu maç için geçmiş örnek bulunamadı.")
        return

    # Üst başlık
    st.markdown(f"""
    <div class="detay-panel">
      <h3 style="margin:0;color:#4a9eff">
        {m_row['ev']}
        <span style="color:#888;font-size:0.8em"> vs </span>
        {m_row['dep']}
      </h3>
      <p style="margin:4px 0;color:#888;font-size:0.85em">
        {m_row['lig']} &nbsp;|&nbsp; {m_row['zaman'].strftime('%d.%m.%Y %H:%M')}
        &nbsp;|&nbsp; Örnek: <b style="color:#fff">{toplam}</b>
      </p>
      <p style="margin:4px 0;color:#aaa;font-size:0.9em">
        Oranlar →
        <b style="color:#2ecc71"> Ev: {m_row['h']:.2f}</b> &nbsp;/&nbsp;
        <b style="color:#f39c12"> Ber: {m_row['b']:.2f}</b> &nbsp;/&nbsp;
        <b style="color:#e74c3c"> Dep: {m_row['a']:.2f}</b>
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── MS / 1Y dağılımı ────────────────────────────────────────────────────
    ms_h = (b['FTR'] == 'H').mean() * 100
    ms_d = (b['FTR'] == 'D').mean() * 100
    ms_a = (b['FTR'] == 'A').mean() * 100
    iy_h = (b['HTR'] == 'H').mean() * 100
    iy_d = (b['HTR'] == 'D').mean() * 100
    iy_a = (b['HTR'] == 'A').mean() * 100

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🏁 Maç Sonu (MS) Dağılımı**")
        st.markdown(f"Ev Galibiyeti {progress_bar(ms_h,'green')}", unsafe_allow_html=True)
        st.markdown(f"Beraberlik {progress_bar(ms_d,'gold')}", unsafe_allow_html=True)
        st.markdown(f"Deplasman Galibiyeti {progress_bar(ms_a,'red')}", unsafe_allow_html=True)
    with col2:
        st.markdown("**⏱️ İlk Yarı (1Y) Dağılımı**")
        st.markdown(f"Ev Galibiyeti {progress_bar(iy_h,'green')}", unsafe_allow_html=True)
        st.markdown(f"Beraberlik {progress_bar(iy_d,'gold')}", unsafe_allow_html=True)
        st.markdown(f"Deplasman Galibiyeti {progress_bar(iy_a,'red')}", unsafe_allow_html=True)

    st.markdown("---")

    # ── Gol / bahis yüzdeleri ───────────────────────────────────────────────
    st.markdown("**⚽ Gol & Bahis Analizi**")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    istatler = [
        (c1, "1Y 0.5 Over",  b['C_1Y05'].mean()*100),
        (c2, "1Y 1.5 Over",  b['C_1Y15'].mean()*100),
        (c3, "MS 1.5 Over",  b['C_MS15'].mean()*100),
        (c4, "MS 2.5 Over",  b['C_MS25'].mean()*100),
        (c5, "MS 3.5 Over",  b['C_MS35'].mean()*100),
        (c6, "KG Var",       b['C_KG'].mean()*100),
    ]
    for col, etiket, pct in istatler:
        with col:
            color = "#2ecc71" if pct >= 50 else "#e74c3c"
            if "KG" in etiket:
                label = "Var ✓" if pct >= 50 else "Yok ✗"
            else:
                label = "Over ✓" if pct >= 50 else "Under ✗"
            st.markdown(f"""
            <div class="stat-kutu">
              <div class="stat-sayi" style="color:{color}">{pct:.0f}%</div>
              <div style="font-size:0.8em;color:{color};margin:2px 0">{label}</div>
              <div class="stat-etiket">{etiket}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Ortalama değerler ───────────────────────────────────────────────────
    st.markdown("**📊 Ortalama Değerler**")
    ca, cb, cc, cd = st.columns(4)
    ms_gol_ort = (b['FTHG'] + b['FTAG']).mean()
    iy_gol = temp['HTHG'] + temp['HTAG'])
    for col, sayi, etiket in [
        (ca, f"{ms_gol_ort:.1f}", "MS Gol Ort."),
        (cb, f"{iy_gol_ort:.1f}", "1Y Gol Ort."),
        (cc, f"{b['C_KRN'].mean():.1f}", "Korner Ort."),
        (cd, f"{b['C_KRT'].mean():.1f}", "Kart Ort."),
    ]:
        with col:
            st.markdown(f"""
            <div class="stat-kutu">
              <div class="stat-sayi">{sayi}</div>
              <div class="stat-etiket">{etiket}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── En sık skorlar ──────────────────────────────────────────────────────
    col_iy, col_ms = st.columns(2)
    with col_iy:
        st.markdown("**🎯 En Sık 1Y Skorları**")
        iy_top = b['S1Y'].value_counts().head(8)
        html = ""
        for skor, adet in iy_top.items():
            pct = adet / toplam * 100
            cls = "skor-chip-top" if skor == iy_top.index[0] else "skor-chip"
            html += f'<span class="{cls}">{skor} ({adet}x · %{pct:.0f})</span> '
        st.markdown(html, unsafe_allow_html=True)

    with col_ms:
        st.markdown("**🎯 En Sık MS Skorları**")
        ms_top = b['SMS'].value_counts().head(8)
        html = ""
        for skor, adet in ms_top.items():
            pct = adet / toplam * 100
            cls = "skor-chip-top" if skor == ms_top.index[0] else "skor-chip"
            html += f'<span class="{cls}">{skor} ({adet}x · %{pct:.0f})</span> '
        st.markdown(html, unsafe_allow_html=True)

    # ── Flip uyarısı ────────────────────────────────────────────────────────
    flip_pct = b['C_FLIP'].mean() * 100
    if flip_pct > 5:
        st.markdown("---")
        st.warning(
            f"🔄 **Sürpriz Radarı:** Bu oran profilinde geçmişte "
            f"**%{flip_pct:.0f}** oranında 1Y → MS sonuç değişimi yaşandı."
        )

    # ── Son 10 benzer maç ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**📋 Benzer Oran Profiline Sahip Son 10 Maç**")
    son10 = b.sort_values('Date', ascending=False).head(10)[
        ['Date','HomeTeam','AwayTeam','HTR','FTR',
         'HTHG','HTAG','FTHG','FTAG','B365H','B365D','B365A']
    ].copy()
    son10['Date'] = son10['Date'].dt.strftime('%d.%m.%Y')
    son10.columns = ['Tarih','Ev','Deplasman','1Y Sn','MS Sn',
                     '1Y Ev Gol','1Y Dep Gol','MS Ev Gol','MS Dep Gol',
                     'H Oran','B Oran','A Oran']
    st.dataframe(son10, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# ANA PROGRAM
# ─────────────────────────────────────────────
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY:
        st.error("⚠️ Lütfen The Odds API key girin.")
    elif not secili_kodlar:
        st.error("⚠️ Lütfen en az bir lig seçin.")
    else:
        if "Futbol" in spor_turu:

            with st.spinner("📊 Geçmiş veriler yükleniyor..."):
                gecmis = futbol_veri_motoru()

            if gecmis.empty:
                st.error("❌ Geçmiş futbol verisi çekilemedi.")
                st.stop()

            st.info(f"✅ Geçmiş veri: {len(gecmis):,} maç yüklendi.")

            with st.spinner("📡 Bülten çekiliyor..."):
                bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "⚽ Futbol")

            if bulten.empty:
                st.error(f"❌ {secili_tarih} tarihinde bülten çekilemedi.")
                st.stop()

            st.success(f"✅ {len(bulten)} maç bulundu.")

            # Analiz
            final_list  = []
            eslesme_map = {}

            for i, m in bulten.iterrows():
                b = gecmis[
                    (gecmis['B365H'].between(m['h'] - TOLERANS, m['h'] + TOLERANS)) &
                    (gecmis['B365D'].between(m['b'] - TOLERANS, m['b'] + TOLERANS)) &
                    (gecmis['B365A'].between(m['a'] - TOLERANS, m['a'] + TOLERANS))
                ]
                if len(b) >= min_ornek:
                    eslesme_map[i] = b
                    final_list.append({
                        'SAAT':      m['zaman'].strftime('%H:%M'),
                        'LİG':       m['lig'],
                        'EV SAHİBİ': m['ev'],
                        'DEPLASMAN': m['dep'],
                        '1Y 0.5':  'Over'  if b['C_1Y05'].mean() > 0.5 else 'Under',
                        '1Y 1.5':  'Over'  if b['C_1Y15'].mean() > 0.5 else 'Under',
                        'MS 1.5':  'Over'  if b['C_MS15'].mean() > 0.5 else 'Under',
                        'MS 2.5':  'Over'  if b['C_MS25'].mean() > 0.5 else 'Under',
                        'MS 3.5':  'Over'  if b['C_MS35'].mean() > 0.5 else 'Under',
                        'KG':      'Yes'   if b['C_KG'].mean()   > 0.5 else 'No',
                        '1Y SKOR':   b['S1Y'].mode()[0],
                        'MS SKOR':   b['SMS'].mode()[0],
                        'KRN (ORT)': round(b['C_KRN'].mean(), 1),
                        'KRT (ORT)': round(b['C_KRT'].mean(), 1),
                        '1Y': ('Home' if b['HTR'].mode()[0]=='H' else
                               ('Draw' if b['HTR'].mode()[0]=='D' else 'Away')),
                        'MS': ('Home' if b['FTR'].mode()[0]=='H' else
                               ('Draw' if b['FTR'].mode()[0]=='D' else 'Away')),
                        'ÖRNEK': len(b),
                        '_idx':  i,
                    })

            if not final_list:
                st.warning(
                    f"Bülten çekildi ({len(bulten)} maç) ama oran toleransı "
                    f"({TOLERANS}) / min. örnek ({min_ornek}) kriterine uyan "
                    f"geçmiş maç bulunamadı. Toleransı artırın veya min. örneği düşürün."
                )
                st.stop()

            df = pd.DataFrame(final_list)

            # Ana tablo
            st.subheader(f"⚽ {secili_tarih} Futbol Analizleri")
            styled_cols = ['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']
            st.dataframe(
                df.drop(columns=['_idx']).style.map(style_engine, subset=styled_cols),
                use_container_width=True
            )
            st.download_button(
                "📥 Excel İndir",
                to_excel(df.drop(columns=['_idx'])),
                f"Vibe_Futbol_{secili_tarih}.xlsx"
            )

            # ── Maç detay seçici ─────────────────────────────────────────────
            st.markdown("---")
            st.subheader("🔍 Maç Detayları")
            mac_secenekler = {
                f"{r['SAAT']}  {r['EV SAHİBİ']} vs {r['DEPLASMAN']}  [{r['LİG']}]  (örnek: {r['ÖRNEK']})": r['_idx']
                for _, r in df.iterrows()
            }
            secim = st.selectbox(
                "Detayını görmek istediğin maçı seç:",
                list(mac_secenekler.keys())
            )
            secili_idx = mac_secenekler[secim]
            detay_paneli(bulten.loc[secili_idx], eslesme_map[secili_idx])

            # ── Sürpriz radarı ───────────────────────────────────────────────
            flips = []
            for _, r in df.iterrows():
                b2 = eslesme_map[r['_idx']]
                if b2['C_FLIP'].any():
                    flips.append({
                        'm': f"{r['EV SAHİBİ']}-{r['DEPLASMAN']}",
                        'p': int(b2['C_FLIP'].mean() * 100)
                    })
            if flips:
                st.markdown("---")
                st.subheader("🔄 Sürpriz Radarı")
                for f in flips:
                    st.warning(f"⚠️ {f['m']} — %{f['p']} dönüş potansiyeli")

        else:  # 🏀 Basketbol
            with st.spinner("📡 Basketbol bülteni çekiliyor..."):
                bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "🏀 Basketbol")

            if bulten.empty:
                st.error(f"❌ {secili_tarih} tarihinde basketbol bülteni çekilemedi.")
            else:
                st.success(f"✅ {len(bulten)} maç bulundu.")
                st.subheader(f"🏀 {secili_tarih} Basketbol Bülteni")
                st.dataframe(bulten, use_container_width=True)
                st.download_button(
                    "📥 Excel İndir",
                    to_excel(bulten),
                    f"Vibe_Basketbol_{secili_tarih}.xlsx"
                )

else:
    st.info("👈 Soldan lig seçin, API key girin ve analizi başlatın Ersin!")
