import io
import math
from datetime import datetime, timedelta
from html import escape

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import textwrap


def parse_mac_datetime(value):
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return datetime.now()

st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")


# ==========================================================
# API KEY ACCESS SYSTEM
# ==========================================================

# Kullanım:
# 1) Kullanıcı sidebar'dan kendi ODDS API KEY'ini girebilir.
# 2) İstersen Streamlit Cloud > Settings > Secrets içine ODDS_API_KEY ekleyebilirsin.
#    Sidebar'dan girilen key, secrets key'in önüne geçer.

def get_secret_value(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_app_api_key():
    user_key = str(st.session_state.get("user_api_key", "")).strip()
    if user_key:
        return user_key
    return str(get_secret_value("ODDS_API_KEY", "")).strip()


def api_key_panel():
    with st.sidebar:
        st.markdown("### 🔑 API Key Girişi")

        current_key = st.session_state.get("user_api_key", "")
        api_key_input = st.text_input(
            "ODDS API KEY",
            value=current_key,
            placeholder="API key gir...",
            type="password",
            key="api_key_input",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Kaydet", use_container_width=True, key="save_api_key_btn"):
                st.session_state["user_api_key"] = api_key_input.strip()
                st.success("API Key kaydedildi ✅")
                st.rerun()

        with c2:
            if st.button("Temizle", use_container_width=True, key="clear_api_key_btn"):
                st.session_state.pop("user_api_key", None)
                st.success("API Key temizlendi")
                st.rerun()

        if get_app_api_key():
            st.success("API key aktif ✅")
        else:
            st.warning("Maçları çekmek için API key girmen gerekiyor.")


def require_api_key():
    if not get_app_api_key():
        st.warning("Devam etmek için sol menüden ODDS API KEY girmen gerekiyor ⚠️")
        st.stop()


def limit_for_free(items, free_limit=999999):
    # Üyelik sistemi kaldırıldı. Artık sınırlama yok.
    return list(items or [])


def legal_notice_top():
    st.markdown(
        """
        <div style="background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:12px 14px;margin:8px 0;color:#7c2d12;font-size:0.86rem;">
        <b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler, geçmiş veri karşılaştırmaları ve yapay zekâ destekli tahminler sunar.
        Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir ve bağımlılık oluşturabilir.
        </div>
        """,
        unsafe_allow_html=True,
    )


def legal_sidebar_sections():
    """Sidebar içinde disclaimer ve kullanım şartları."""
    with st.sidebar:
        st.markdown("---")

        with st.expander("⚖️ Disclaimer", expanded=False):
            st.markdown("""
Bu platform yalnızca **istatistiksel analiz** ve **yapay zekâ destekli tahminler** sunar.

Sunulan içerikler kesinlik içermez ve yatırım tavsiyesi değildir.

Kullanıcılar kendi kararlarını kendileri verir. Bu platform üzerinden doğrudan bahis oynanmaz ve herhangi bir bahis hizmeti sunulmaz.

**Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.**
            """)

        with st.expander("📜 Kullanım Şartları", expanded=False):
            st.markdown("""
**1. Hizmet Tanımı**  
Bu platform, spor karşılaşmalarına ilişkin istatistiksel analizler ve yapay zekâ destekli tahminler sunar.

**2. Sorumluluk Reddi**  
Platformda yer alan hiçbir içerik kesin kazanç garantisi vermez. Kullanıcılar, elde ettikleri verileri kendi riskleri doğrultusunda değerlendirir.

**3. Bahis Hizmeti Sunulmaması**  
Bu platform bir bahis sitesi değildir. Kullanıcılara doğrudan bahis oynama imkânı sunulmaz ve herhangi bir bahis kuruluşu ile resmi bir bağlantısı bulunmaz.

**4. Kullanıcı Sorumluluğu**  
Kullanıcılar, platformu kullanırken yürürlükteki yasalara uymakla yükümlüdür.

**5. Hizmet Değişikliği**  
Platform, hizmet içeriğini önceden bildirmeksizin değiştirme hakkını saklı tutar.
            """)


def legal_footer():
    """Sayfanın en altında kısa hukuki footer."""
    st.markdown("""
    ---
    <div style="text-align:center;font-size:12px;color:#64748b;line-height:1.55;padding:10px 0 4px 0;">
        <b>Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analiz ve yapay zekâ destekli tahminler sunar.<br>
        Kesin kazanç garantisi verilmez. Kullanıcılar kararlarını kendi sorumluluğunda verir.<br>
        Bu platform üzerinden doğrudan bahis oynanmaz. Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.
    </div>
    """, unsafe_allow_html=True)



APP_SCHEMA_VERSION = 19
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--navy:#101d3b;--blue:#2f7cff;--green:#20d787;--amber:#ffb020;--red:#ff4d5f;--bg:#eef2f8;--line:#dbe3f0;--text:#14213d;--muted:#7c8aa5;}
html,body,[class*="css"]{font-family:Inter,Arial,sans-serif!important;background:var(--bg)!important;color:var(--text)!important;}
.stApp{background:linear-gradient(180deg,#f8fbff 0%,#eef2f8 100%)!important;}
.main .block-container{max-width:1180px;padding:18px 14px 36px!important;}
section[data-testid="stSidebar"]{background:#111d3a!important;border-right:1px solid rgba(255,255,255,.08)!important;}
section[data-testid="stSidebar"] *{color:#dbe7ff!important;}
section[data-testid="stSidebar"] label{font-size:.78rem!important;color:#8fa3cb!important;text-transform:uppercase;letter-spacing:.08em;}
section[data-testid="stSidebar"] .stButton>button{background:transparent!important;border:1px solid #41547c!important;border-radius:8px!important;color:#fff!important;height:34px!important;}
section[data-testid="stSidebar"] [data-baseweb="select"]>div,
section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"]{background:#14264d!important;border-color:#263b66!important;color:#fff!important;}
.stButton>button{border-radius:12px!important;border:1px solid #d8e1ef!important;background:#fff!important;color:#172443!important;font-weight:700!important;}
.stButton>button:hover{border-color:#2f7cff!important;color:#2f7cff!important;}
button[kind="primary"]{background:#111827!important;border-color:#111827!important;color:#fff!important;}
.app-top{display:flex;align-items:center;justify-content:space-between;margin:0 0 16px;gap:12px;}
.app-title{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px;color:#071331;}
.count-pill{background:#2f7cff;color:#fff;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:800;}
.live-dot{width:7px;height:7px;border-radius:50%;background:#20d787;display:inline-block;margin-right:5px;}
.sort-wrap{min-width:245px;}
.match-card{background:#fff;border:1px solid #d8e1ef;border-radius:13px;margin:10px 0;padding:13px 15px;display:grid;grid-template-columns:64px 1.45fr 85px 72px 146px 100px;align-items:center;gap:12px;box-shadow:0 1px 0 rgba(20,33,61,.03);position:relative;overflow:hidden;}
.match-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--green);}
.match-card.mid:before{background:var(--amber)}.match-card.low:before{background:var(--blue)}
.m-time{font-size:16px;font-weight:800;color:#071331;line-height:1}.m-league{font-size:10px;color:#6f80a3;margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.team-row{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:#14213d;margin:2px 0}.team-icon{width:13px;height:9px;border-radius:2px;background:#192a56;display:inline-block}.pred-pill{display:inline-flex;align-items:center;justify-content:center;padding:6px 11px;border-radius:7px;border:1px solid #bcd2ff;background:#eff5ff;color:#1d64ff;font-weight:800;font-size:13px}.pred-pill.red{background:#fff1f1;border-color:#ffc7c7;color:#e11d48}.pred-pill.amber{background:#fff8e8;border-color:#ffd676;color:#a16207}.pred-pill.cyan{background:#ecfbff;border-color:#a8eaff;color:#0077a6}.conf{font-size:17px;font-weight:900;color:#20c878;line-height:1}.conf.mid{color:#ff9f00}.conf.low{color:#2271ff}.conf small{display:block;font-size:9px;color:#6f80a3;font-weight:500;margin-top:2px}.odds{display:flex;gap:6px}.odd-box{min-width:43px;background:#f4f7fc;border:1px solid #dbe5f4;border-radius:7px;text-align:center;padding:4px 5px}.odd-box span{display:block;font-size:9px;color:#8a98b6;line-height:1}.odd-box b{font-size:12px;color:#0b1d45}.detail-shell{background:#fff;border-radius:18px;overflow:hidden;border:1px solid #bfcbe3;box-shadow:0 22px 70px rgba(17,29,58,.35)}.detail-head{background:#111d3a;color:#fff;padding:18px 20px}.detail-topline{font-size:11px;color:#9eb0d0;font-weight:800}.detail-title{font-size:25px;font-weight:900;letter-spacing:-.02em}.detail-date{font-size:12px;color:#9eb0d0;margin-top:4px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e5ebf4}.metric{padding:14px;text-align:center;border-right:1px solid #e5ebf4}.metric:last-child{border-right:0}.metric-label{font-size:10px;color:#8997b4;text-transform:uppercase;font-weight:900;letter-spacing:.08em}.metric-val{font-size:24px;font-weight:900;color:#14213d;line-height:1.1}.metric-sub{font-size:11px;color:#6f80a3}.detail-body{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:18px}.panel-title{font-size:12px;color:#8997b4;text-transform:uppercase;font-weight:900;letter-spacing:.08em;margin-bottom:9px}.stat-row{display:flex;align-items:center;justify-content:space-between;background:#f6f8fc;border:1px solid #e2e8f2;border-radius:8px;padding:10px 12px;margin-bottom:7px;font-size:13px;font-weight:800;color:#263653}.stat-mini{display:flex;gap:12px;font-size:11px;color:#51627f}.odds-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.big-odd{border:1px solid #dce5f3;border-radius:9px;background:#f7f9fd;text-align:center;padding:13px 8px}.big-odd small{display:block;color:#8997b4;font-size:10px;text-transform:uppercase;font-weight:900}.big-odd b{font-size:23px;color:#2563eb}.combo-row{display:flex;justify-content:space-between;align-items:center;background:#f0f4fa;border:1px solid #d9e2ef;border-radius:8px;padding:12px;margin-bottom:8px;font-size:13px;font-weight:800}.why-box{background:#f6f8fc;border:1px solid #e2e8f2;border-radius:10px;padding:12px;font-size:12px;color:#40516e;line-height:1.55}.history-table{width:100%;border-collapse:collapse;font-size:11px}.history-table th{color:#8997b4;text-align:left;padding:5px}.history-table td{border-top:1px solid #e5ebf4;padding:5px;color:#263653;font-weight:700}.tag{border-radius:5px;padding:2px 6px;font-size:10px;font-weight:900}.tag.green{background:#dcfce7;color:#15803d}.tag.red{background:#fee2e2;color:#dc2626}.tag.gray{background:#e5e7eb;color:#374151}.side-logo{display:flex;align-items:center;gap:9px;margin:12px 0 18px}.logo-box{width:27px;height:27px;border-radius:7px;background:#3b82f6;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900}.side-brand{font-weight:900;color:#fff}.side-section{border-top:1px solid rgba(255,255,255,.12);padding-top:14px;margin-top:14px}.side-title{font-size:10px;text-transform:uppercase;letter-spacing:.14em;color:#8295bf;font-weight:900;margin-bottom:9px}.empty{background:#fff;border:1px solid #dbe3f0;border-radius:14px;padding:34px;text-align:center;color:#64748b}.legal-box{background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:10px 12px;color:#7c2d12;font-size:.8rem;margin:8px 0 14px}.stDialog div[role="dialog"]{max-width:980px!important;padding:0!important;border-radius:20px!important;background:transparent!important} 
@media(max-width:900px){.match-card{grid-template-columns:55px 1fr 75px;}.odds,.match-card .detail-slot{display:none}.detail-body{grid-template-columns:1fr}.metric-grid{grid-template-columns:repeat(2,1fr)}}

/* === DETAIL MODAL LIGHT STYLE FIX === */
.stDialog div[role="dialog"]{max-width:980px!important;padding:0!important;border-radius:20px!important;background:transparent!important;}
.detail-shell{background:#ffffff!important;border-radius:18px!important;overflow:hidden!important;border:1px solid #bfcbe3!important;box-shadow:0 24px 80px rgba(17,29,58,.35)!important;color:#14213d!important;}
.detail-head{background:#111d3a!important;color:#fff!important;padding:18px 20px!important;}
.detail-topline{font-size:11px!important;color:#9eb0d0!important;font-weight:800!important;}
.detail-title{font-size:26px!important;font-weight:900!important;letter-spacing:-.02em!important;color:#fff!important;}
.detail-date{font-size:12px!important;color:#9eb0d0!important;margin-top:4px!important;}
.metric-grid{display:grid!important;grid-template-columns:repeat(4,1fr)!important;border-bottom:1px solid #e5ebf4!important;background:#fff!important;}
.metric{padding:14px!important;text-align:center!important;border-right:1px solid #e5ebf4!important;}
.metric:last-child{border-right:0!important;}
.metric-label{font-size:10px!important;color:#8997b4!important;text-transform:uppercase!important;font-weight:900!important;letter-spacing:.08em!important;}
.metric-val{font-size:24px!important;font-weight:900!important;color:#14213d!important;line-height:1.1!important;}
.metric-sub{font-size:11px!important;color:#6f80a3!important;}
.detail-body{display:grid!important;grid-template-columns:1fr 1fr!important;gap:18px!important;padding:18px!important;background:#fff!important;}
.panel-title{font-size:12px!important;color:#8997b4!important;text-transform:uppercase!important;font-weight:900!important;letter-spacing:.08em!important;margin:14px 0 9px!important;}
.stat-row{display:flex!important;align-items:center!important;justify-content:space-between!important;background:#f6f8fc!important;border:1px solid #e2e8f2!important;border-radius:8px!important;padding:10px 12px!important;margin-bottom:7px!important;font-size:13px!important;font-weight:800!important;color:#263653!important;}
.stat-mini{display:flex!important;gap:12px!important;font-size:11px!important;color:#51627f!important;}
.odds-grid{display:grid!important;grid-template-columns:repeat(3,1fr)!important;gap:10px!important;}
.big-odd{border:1px solid #dce5f3!important;border-radius:9px!important;background:#f7f9fd!important;text-align:center!important;padding:13px 8px!important;}
.big-odd small{display:block!important;color:#8997b4!important;font-size:10px!important;text-transform:uppercase!important;font-weight:900!important;}
.big-odd b{font-size:23px!important;color:#2563eb!important;}
.combo-row{display:flex!important;justify-content:space-between!important;align-items:center!important;background:#f0f4fa!important;border:1px solid #d9e2ef!important;border-radius:8px!important;padding:12px!important;margin-bottom:8px!important;font-size:13px!important;font-weight:800!important;color:#263653!important;}
.why-box{background:#f6f8fc!important;border:1px solid #e2e8f2!important;border-radius:10px!important;padding:12px!important;font-size:12px!important;color:#40516e!important;line-height:1.55!important;}
.hist-head,.hist-row{display:grid!important;grid-template-columns:1.2fr 1.2fr .7fr .55fr .55fr .55fr!important;gap:6px!important;align-items:center!important;}
.hist-head{color:#8997b4!important;font-size:10px!important;font-weight:900!important;letter-spacing:.05em!important;margin-bottom:4px!important;}
.hist-row{border-top:1px solid #e5ebf4!important;padding:6px 0!important;font-size:11px!important;color:#263653!important;font-weight:700!important;}
.tag{display:inline-block!important;border-radius:5px!important;padding:2px 6px!important;font-size:10px!important;font-weight:900!important;text-align:center!important;}
.tag.green{background:#dcfce7!important;color:#15803d!important;}.tag.red{background:#fee2e2!important;color:#dc2626!important;}.tag.gray{background:#e5e7eb!important;color:#374151!important;}.tag.blue{background:#dbeafe!important;color:#2563eb!important;}.tag.amber{background:#fef3c7!important;color:#b45309!important;}
@media(max-width:900px){.detail-body{grid-template-columns:1fr!important}.metric-grid{grid-template-columns:repeat(2,1fr)!important}.hist-head,.hist-row{grid-template-columns:1fr 1fr .6fr .5fr .5fr .5fr!important;font-size:10px!important}}
</style>
""", unsafe_allow_html=True)


api_key_panel()
legal_sidebar_sections()
legal_notice_top()


def format_tr_date(d):
    aylar = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    gunler = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
        4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    return f"{d.day} {aylar[d.month]} {d.year} {gunler[d.weekday()]}"


def dinamik_min_mac(tolerans: float) -> int:
    if tolerans <= 0.02:
        return 1
    elif tolerans <= 0.05:
        return 3
    elif tolerans <= 0.08:
        return 5
    elif tolerans <= 0.12:
        return 10
    return 20


def sample_factor_hesapla(sample: int, tolerans: float) -> float:
    if tolerans <= 0.02:
        hedef = 5
    elif tolerans <= 0.05:
        hedef = 10
    elif tolerans <= 0.08:
        hedef = 15
    elif tolerans <= 0.12:
        hedef = 25
    else:
        hedef = 40
    return min(0.75 + 0.25 * (sample / max(hedef, 1)), 1.0)


def tolerans_rehberi(tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if tolerans <= 0.02:
        yorum = "Çok dar filtre. Az ama çok yakın oranlı örnekler gelir."
    elif tolerans <= 0.05:
        yorum = "Dar filtre. Örnek az olabilir ama eşleşme kalitesi yüksektir."
    elif tolerans <= 0.08:
        yorum = "Dengeli filtre. Hem kalite hem örnek sayısı dengeli."
    elif tolerans <= 0.12:
        yorum = "Biraz geniş filtre. Veri artar, benzerlik biraz düşer."
    else:
        yorum = "Geniş filtre. Sonuçlar daha genel davranabilir."
    return {
        "onerilen_tolerans": "0.08 - 0.10",
        "onerilen_min_mac": min_mac,
        "yorum": yorum,
    }


def guven_metni(sample: int, tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if sample >= max(20, min_mac * 3):
        return "Çok Sağlam", "#27ae60"
    if sample >= max(10, min_mac * 2):
        return "Sağlıklı", "#2ecc71"
    if sample >= min_mac:
        return "Kullanılabilir", "#f39c12"
    return "Riskli", "#e74c3c"


def guven_renk(pct: int):
    if pct >= 70:
        return "#27ae60", "badge-yuksek", "Yüksek Güven"
    if pct >= 55:
        return "#e67e22", "badge-orta", "Orta Güven"
    return "#e74c3c", "badge-dusuk", "Düşük Güven"


def risk_seviyesi(pct: int, flip_p: float):
    if pct >= 70 and flip_p < 0.15:
        return "DÜŞÜK", "risk-dusuk"
    if pct >= 55:
        return "ORTA", "risk-orta"
    return "YÜKSEK", "risk-yuksek"


def tahmini_skor(b: pd.DataFrame, ms_mod: str):
    eg = math.floor(b["FTHG"].mean() + 0.5) if not b.empty else 1
    dg = math.floor(b["FTAG"].mean() + 0.5) if not b.empty else 1
    if ms_mod == "H" and eg <= dg:
        eg = dg + 1
    if ms_mod == "A" and dg <= eg:
        dg = eg + 1
    return eg, dg


def mac_tipi(h: float, a: float):
    if abs(h - a) <= 0.50:
        return "Dengeli"
    if h < 2.0 or a < 2.0:
        return "Favori"
    return "Sürpriz Açık"


def gol_profili(avg_goal: float):
    if avg_goal < 2.2:
        return "Düşük Gollü"
    if avg_goal < 3.0:
        return "Dengeli"
    return "Yüksek Gollü"


def fake_confidence_duzelt(conf_prob: float, sample: int, tolerans: float):
    carpan = 1.0
    if tolerans <= 0.05 and sample < 10 and conf_prob > 0.80:
        carpan *= 0.75
    elif tolerans <= 0.08 and sample < 8 and conf_prob > 0.75:
        carpan *= 0.82
    return conf_prob * carpan, carpan < 1.0


@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar:
        return pd.DataFrame()

    lig_map = [
        # TÜRKİYE
        "T1",

        # İNGİLTERE
        "E0", "E1", "E2",

        # İSPANYA
        "SP1", "SP2",

        # ALMANYA
        "D1", "D2",

        # İTALYA
        "I1", "I2",

        # FRANSA
        "F1", "F2",

        # AVRUPA ANA VALUE
        "N1", "B1", "P1", "SC0",
    ]
    liste = []

    for k in lig_map:
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = [
                    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG",
                    "FTR", "HTR", "B365H", "B365D", "B365A", "HC", "AC", "HY", "AY"
                ]
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=["B365H", "B365D", "B365A"]).copy()
                temp["Date"] = pd.to_datetime(temp["Date"], dayfirst=True, errors="coerce")
                liste.append(temp)
            except Exception:
                continue

    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def bulten_cek(key, kodlar, t):
    secret_key = get_app_api_key()
    if secret_key:
        key = secret_key
    if not key:
        st.error("ODDS_API_KEY bulunamadı. Streamlit Cloud > Settings > Secrets içine ODDS_API_KEY eklemelisin.")
        return pd.DataFrame()
    res = []

    for k in kodlar:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{k}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=12,
            )

            if r.status_code != 200:
                continue

            data = r.json()
            if not isinstance(data, list):
                continue

            for m in data:
                try:
                    tm = datetime.strptime(m["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except Exception:
                    continue

                if tm.date() != t:
                    continue

                bookies = m.get("bookmakers", [])
                if not bookies:
                    continue

                market = None
                for bk in bookies:
                    for mk in bk.get("markets", []):
                        if mk.get("key") == "h2h":
                            market = mk
                            break
                    if market:
                        break

                if not market:
                    continue

                outcomes = market.get("outcomes", [])
                home = m.get("home_team", "")
                away = m.get("away_team", "")

                if not away:
                    teams = m.get("teams", [])
                    for team in teams:
                        if team != home:
                            away = team
                            break

                h = next((x["price"] for x in outcomes if x["name"] == home), None)
                a = next((x["price"] for x in outcomes if x["name"] == away), None)
                b = next((x["price"] for x in outcomes if str(x["name"]).lower() in ["draw", "tie", "beraberlik"]), None)

                if h is None or a is None or b is None:
                    continue

                res.append({
                    "lig": m.get("sport_title", k),
                    "zaman": tm,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "b": float(b),
                    "a": float(a),
                })
        except Exception:
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    return df.sort_values("zaman").reset_index(drop=True)






def fmt_odd(odd):
    if odd is None:
        return ""
    try:
        return f"{float(odd):.2f}"
    except Exception:
        return ""


def pct100(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:
        return 0


def skoru_tahmine_uydur(eg, dg, ana_label, ms_mod):
    ana = str(ana_label)
    ms_mod = str(ms_mod)

    # Öncelik ana tahmin: Alt / Üst / KG.
    # Böylece ana tahmin 2.5 Alt iken skor 1-2 gibi çelişkili çıkmaz.
    if "2.5 Alt" in ana:
        if ms_mod == "H":
            return 1, 0
        elif ms_mod == "A":
            return 0, 1
        else:
            return 1, 1

    if "2.5 Üst" in ana:
        if ms_mod == "H":
            return 2, 1
        elif ms_mod == "A":
            return 1, 2
        else:
            return 2, 2

    if ana == "KG Yok":
        if ms_mod == "H":
            return 2, 0
        elif ms_mod == "A":
            return 0, 2
        else:
            return 0, 0

    if ana == "KG Var":
        if ms_mod == "H":
            return 2, 1
        elif ms_mod == "A":
            return 1, 2
        else:
            return 1, 1

    eg = int(eg)
    dg = int(dg)

    if ana == "MS 1" and eg <= dg:
        eg = dg + 1
    elif ana == "MS 2" and dg <= eg:
        dg = eg + 1
    elif ana == "Beraberlik":
        mx = max(eg, dg, 1)
        eg = dg = mx

    return eg, dg


def ai_kart_yorumlari(t, m):
    ana = t.get("ana_label", "")
    guven = int(t.get("ana_p", 0))
    puan = float(t.get("playable_score", guven))
    canli = t.get("canli_label", "İlk 15 dk izle")

    if t.get("belirsiz"):
        yorum = "Model bu maçta net bir yön bulamıyor; ana tahmin tek başına güçlü değil."
        risk = "Risk yüksek; maç başı tempo ve ilk 10-15 dakika izlenmeli."
        canlı = "İlk baskı ve şut hacmi oluşmadan giriş yapmak yerine beklemek daha iyi."
        return yorum, risk, canlı

    if ana in ["MS 1", "MS 2", "Beraberlik"]:
        taraf = "ev sahibi" if ana == "MS 1" else "deplasman" if ana == "MS 2" else "beraberlik"
        yorum = f"{taraf.capitalize()} tarafı oran benzerliğinde öne çıkıyor; ana senaryo {ana}."
    elif "Üst" in ana or "Alt" in ana:
        yorum = f"Gol marketinde {ana} senaryosu öne çıkıyor; skor beklentisi bu yöne göre dengelendi."
    elif "KG" in ana:
        yorum = f"Karşılıklı gol tarafında {ana} modeli daha güçlü görünüyor."
    else:
        yorum = f"Model ana senaryoda {ana} tarafını öne çıkarıyor."

    if guven >= 70 and puan >= 70:
        risk = "Güven ve puan iyi; yine de tek maç riski tamamen kaybolmaz."
    elif guven >= 60:
        risk = "Güven orta-iyi seviyede; beraberlik/tempo riski tamamen dışarıda değil."
    else:
        risk = "Güven sınırlı; kuponda düşük ağırlıkla değerlendirmek daha mantıklı."

    if "Canlı" in canli or "İzle" in canli:
        canlı = "İlk 15 dakikada baskı ve tempo oluşursa ana senaryo daha değerli olur."
    else:
        canlı = f"Canlı plan: {canli}. İlk 15 dakikadaki tempo mutlaka kontrol edilmeli."

    return yorum, risk, canlı


def pct100(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except Exception:
        return 0


def ai_yorum_uret(t):
    ana = t.get("ana_label", "")
    guven = int(t.get("ana_p", 0))
    puan = float(t.get("playable_score", guven))
    ornek = int(t.get("ornek", 0))
    mac_tipi_txt = t.get("match_type", "")
    gol_profili = t.get("goal_profile", "")
    combo = t.get("combo_label", "")
    canli = t.get("canli_label", "")

    if t.get("belirsiz"):
        return "Model bu maçta net taraf ayıramıyor. Ana tahmin yerine canlı başlangıç temposunu izlemek daha mantıklı."

    giris = f"Model ana senaryoda {ana} tarafını öne çıkarıyor."
    if guven >= 70 and puan >= 70:
        giris += " Güven ve puan birlikte güçlü olduğu için maç öncelikli izlenebilir."
    elif puan >= 65:
        giris += " Puan tarafı iyi, ancak güveni de maç temposuyla teyit etmek gerekir."
    elif guven >= 65:
        giris += " Güven iyi olsa da puan çok elit değil, kontrollü yaklaşmak daha doğru."
    else:
        giris += " Güven orta seviyede, agresif kupon için tek başına güçlü görünmüyor."

    detaylar = []
    if mac_tipi_txt:
        detaylar.append(f"maç tipi {mac_tipi_txt.lower()}")
    if gol_profili:
        detaylar.append(f"gol profili {gol_profili.lower()}")
    if combo:
        detaylar.append(f"kombo desteği: {combo}")
    if ornek < 8:
        detaylar.append("örnek sayısı düşük")
    elif ornek >= 20:
        detaylar.append("örnek sayısı sağlıklı")

    sonuc = giris
    if detaylar:
        sonuc += " " + " · ".join(detaylar).capitalize() + "."
    if canli:
        sonuc += f" Canlı plan: {canli}."
    return sonuc

def build_top3_coupon(indexed_items, mode="best_favorites"):
    candidates = []

    for idx, item in indexed_items:
        m, t = item["m"], item["t"]

        if t.get("belirsiz") or not t.get("oynanabilir"):
            continue

        ana_odd = t.get("ana_odd")
        if ana_odd is None:
            continue

        if t.get("match_type") != "Favori":
            continue

        candidates.append({
            "idx": idx,
            "m": m,
            "t": t,
            "ana_odd": ana_odd,
            "ana_label": t.get("ana_label", ""),
            "playable_score": t.get("playable_score", 0),
            "ana_p": t.get("ana_p", 0),
        })

    if mode == "best_favorites":
        # 🔥 GÜVEN ODAKLI
        candidates.sort(
            key=lambda c: (
                c["playable_score"],
                c["ana_p"],
                -c["ana_odd"]
            ),
            reverse=True
        )

        picks = []
        label_counts = {}

        for c in candidates:
            label = c["ana_label"]

            # aynı tahminden spam olmasın
            if label_counts.get(label, 0) >= 1:
                continue

            picks.append(c)
            label_counts[label] = 1

            if len(picks) == 3:
                break

        # 3'e tamamla
        if len(picks) < 3:
            used = {p["idx"] for p in picks}
            for c in candidates:
                if c["idx"] in used:
                    continue
                picks.append(c)
                if len(picks) == 3:
                    break

    else:
        # 🎯 ORAN ODAKLI
        candidates = [c for c in candidates if c["ana_odd"] >= 1.55]

        candidates.sort(
            key=lambda c: (
                c["ana_odd"],
                c["playable_score"],
                c["ana_p"]
            ),
            reverse=True
        )

        picks = candidates[:3]

    return [
        {
            "ev": c["m"]["ev"],
            "dep": c["m"]["dep"],
            "lig": c["m"]["lig"],
            "zaman_iso": c["m"]["zaman"].strftime("%Y-%m-%d %H:%M:%S"),
            "zaman_text": c["m"]["zaman"].strftime("%d.%m %H:%M"),
            "tahmin": f"{c['t']['ana_label']} ({fmt_odd(c['ana_odd'])})",
            "guven": int(c["t"].get("ana_p", 0)),
        }
        for c in picks
    ]




# ==========================================================
# SADE ANALIZ MODU
# AI günlük tarama, auto kupon builder ve 30 günlük kasa planı kaldırıldı.
# Sistem artık sadece mevcut maç bültenini tek toleransla analiz eder.
# ==========================================================

def market_label_to_odd(m_row, label):
    if not isinstance(m_row, dict):
        try:
            m_row = m_row.to_dict()
        except Exception:
            pass
    if label == "MS 1":
        return m_row.get("h")
    if label == "MS 2":
        return m_row.get("a")
    if label == "Beraberlik":
        return m_row.get("b")
    return None

def hesapla(b_df, m_row, tolerans):
    rehber = tolerans_rehberi(float(tolerans))
    onerilen_min_mac = dinamik_min_mac(float(tolerans))

    b = b_df[
        (b_df["B365H"].between(m_row["h"] - tolerans, m_row["h"] + tolerans)) &
        (b_df["B365D"].between(m_row["b"] - tolerans, m_row["b"] + tolerans)) &
        (b_df["B365A"].between(m_row["a"] - tolerans, m_row["a"] + tolerans))
    ].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")

    b = b.dropna(subset=["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A", "FTR", "HTR"])
    if b.empty:
        return None, b

    sample = len(b)
    toplam_gol = b["FTHG"] + b["FTAG"]
    ilk_yari_gol = b["HTHG"] + b["HTAG"]

    ms_vc = b["FTR"].value_counts(normalize=True)
    iy_vc = b["HTR"].value_counts(normalize=True)

    ms_mod = ms_vc.idxmax() if not ms_vc.empty else "D"
    ms_raw = float(ms_vc.get(ms_mod, 0))
    ms_side = "MS 1" if ms_mod == "H" else "MS 2" if ms_mod == "A" else "Beraberlik"

    ms1_raw = float(ms_vc.get("H", 0))
    msx_raw = float(ms_vc.get("D", 0))
    ms2_raw = float(ms_vc.get("A", 0))

    ms25_raw = float((toplam_gol >= 3).mean())
    ms35_raw = float((toplam_gol >= 4).mean())
    ms15_raw = float((toplam_gol >= 2).mean())
    kg_raw = float(((b["FTHG"] > 0) & (b["FTAG"] > 0)).mean())
    iy05_raw = float((ilk_yari_gol >= 1).mean())
    iy15_raw = float((ilk_yari_gol >= 2).mean())

    htft_s = b["HTR"].replace({"H": "1", "A": "2", "D": "X"}) + "/" + b["FTR"].replace({"H": "1", "A": "2", "D": "X"})
    htft_mod = htft_s.mode()[0] if not htft_s.empty else "-"
    htft_raw = float(htft_s.value_counts(normalize=True).get(htft_mod, 0)) if not htft_s.empty else 0.0

    oran_ev = float(m_row["h"])
    oran_ber = float(m_row["b"])
    oran_dep = float(m_row["a"])

    sample_factor = sample_factor_hesapla(sample, float(tolerans))
    if oran_ev < 1.40 or oran_dep < 1.40:
        oran_factor = 0.93
    elif oran_ev > 6.50 or oran_dep > 6.50:
        oran_factor = 0.95
    else:
        oran_factor = 1.0

    guven_carpani = sample_factor * oran_factor
    match_type = mac_tipi(oran_ev, oran_dep)

    # maç tipine göre model davranışı
    ms_bias = 1.0
    goal_bias = 1.0
    combo_bias = 1.0
    if match_type == "Favori":
        ms_bias = 1.06
        goal_bias = 0.96
        combo_bias = 0.97
    elif match_type == "Dengeli":
        ms_bias = 0.95
        goal_bias = 1.05
        combo_bias = 1.02
    elif match_type == "Sürpriz Açık":
        ms_bias = 0.92
        goal_bias = 1.03
        combo_bias = 1.08

    ms_prob = min(ms_raw * guven_carpani * ms_bias, 0.99)
    ou25_best_raw = max(ms25_raw, 1 - ms25_raw)
    ou25_prob = min(ou25_best_raw * guven_carpani * goal_bias, 0.99)
    kg_best_raw = max(kg_raw, 1 - kg_raw)
    kg_prob = min(kg_best_raw * guven_carpani * goal_bias, 0.99)

    ms_label = ms_side
    ou_label = "2.5 Üst" if ms25_raw >= 0.5 else "2.5 Alt"
    kg_label = "KG Var" if kg_raw >= 0.5 else "KG Yok"

    # belirsiz maç tespiti
    ms_sorted = sorted([ms1_raw, msx_raw, ms2_raw], reverse=True)
    belirsiz = (max(ms1_raw, msx_raw, ms2_raw) < 0.42 and (ms_sorted[0] - ms_sorted[1]) < 0.06) or (abs(ms1_raw - ms2_raw) < 0.05 and abs(ms1_raw - msx_raw) < 0.05)

    cands = [
        {"label": ms_label, "raw_prob": ms_raw, "conf_prob": ms_prob, "market": "ms"},
        {"label": ou_label, "raw_prob": ou25_best_raw, "conf_prob": ou25_prob, "market": "ou25"},
        {"label": kg_label, "raw_prob": kg_best_raw, "conf_prob": kg_prob, "market": "kg"},
    ]

    best = max(cands, key=lambda x: x["raw_prob"])
    best_conf, fake_drop = fake_confidence_duzelt(best["conf_prob"], sample, float(tolerans))

    ana_label = best["label"]
    ana_p = int(round(best_conf * 100))
    ana_raw_p = int(round(best["raw_prob"] * 100))

    others = [c for c in cands if c["label"] != ana_label]
    alt = max(others, key=lambda x: x["raw_prob"]) if others else cands[1]
    alt_conf, _ = fake_confidence_duzelt(alt["conf_prob"], sample, float(tolerans))
    alt_label = alt["label"]
    alt_p = int(round(alt_conf * 100))

    def alt_destekli_mi(ana, alt_lbl):
        if not alt_lbl:
            return False
        destek = {
            "2.5 Üst": {"KG Var"},
            "2.5 Alt": {"KG Yok"},
            "KG Var": {"2.5 Üst"},
            "KG Yok": {"2.5 Alt"},
            "MS 1": {"2.5 Üst", "KG Var", "2.5 Alt", "KG Yok"},
            "MS 2": {"2.5 Üst", "KG Var", "2.5 Alt", "KG Yok"},
            "Beraberlik": {"KG Var", "2.5 Alt"},
        }
        return alt_lbl in destek.get(ana, set())

    if not alt_destekli_mi(ana_label, alt_label):
        alt_label = ""
        alt_p = 0

    ana_odd = market_label_to_odd(m_row, ana_label)

    cond_ms1 = (b["FTR"] == "H")
    cond_msx = (b["FTR"] == "D")
    cond_ms2 = (b["FTR"] == "A")
    cond_ust25 = (toplam_gol >= 3)
    cond_alt25 = (toplam_gol <= 2)
    cond_kg_var = ((b["FTHG"] > 0) & (b["FTAG"] > 0))
    cond_kg_yok = ~cond_kg_var
    htft_series = b["HTR"].replace({"H": "1", "D": "X", "A": "2"}) + "/" + b["FTR"].replace({"H": "1", "D": "X", "A": "2"})

    combo_defs = [
        ("MS1 + KG Var", cond_ms1 & cond_kg_var, "mskg"),
        ("MS1 + KG Yok", cond_ms1 & cond_kg_yok, "mskg"),
        ("MS1 + 2.5 Üst", cond_ms1 & cond_ust25, "msou"),
        ("MS1 + 2.5 Alt", cond_ms1 & cond_alt25, "msou"),
        ("MSX + KG Var", cond_msx & cond_kg_var, "mskg"),
        ("MSX + KG Yok", cond_msx & cond_kg_yok, "mskg"),
        ("MSX + 2.5 Üst", cond_msx & cond_ust25, "msou"),
        ("MSX + 2.5 Alt", cond_msx & cond_alt25, "msou"),
        ("MS2 + KG Var", cond_ms2 & cond_kg_var, "mskg"),
        ("MS2 + KG Yok", cond_ms2 & cond_kg_yok, "mskg"),
        ("MS2 + 2.5 Üst", cond_ms2 & cond_ust25, "msou"),
        ("MS2 + 2.5 Alt", cond_ms2 & cond_alt25, "msou"),
        ("2.5 Üst + KG Var", cond_ust25 & cond_kg_var, "oukg"),
        ("2.5 Alt + KG Yok", cond_alt25 & cond_kg_yok, "oukg"),
    ]

    raw_combo_list = []
    for combo_label, combo_cond, combo_type in combo_defs:
        combo_hit = int(combo_cond.sum())
        combo_raw = float(combo_cond.mean())
        combo_conf = min(combo_raw * guven_carpani * combo_bias, 0.99)
        combo_conf, combo_fake_drop = fake_confidence_duzelt(combo_conf, sample, float(tolerans))

        if combo_type == "oukg":
            gerekli_raw = 0.30 if match_type != "Sürpriz Açık" else 0.27
            gerekli_hit = max(4, onerilen_min_mac)
        else:
            gerekli_raw = 0.26 if match_type != "Sürpriz Açık" else 0.23
            gerekli_hit = max(3, onerilen_min_mac)

        if combo_hit >= gerekli_hit and combo_raw >= gerekli_raw:
            raw_combo_list.append({
                "label": combo_label,
                "raw_prob": combo_raw,
                "conf_prob": combo_conf,
                "hit": combo_hit,
                "fake_drop": combo_fake_drop,
                "type": combo_type,
            })

    htft_counts = htft_series.value_counts(normalize=True)
    for htft_label, htft_raw_prob in htft_counts.items():
        htft_hit = int((htft_series == htft_label).sum())
        htft_conf = min(float(htft_raw_prob) * guven_carpani * combo_bias, 0.99)
        htft_conf, htft_fake_drop = fake_confidence_duzelt(htft_conf, sample, float(tolerans))
        gerekli_raw = 0.22 if match_type != "Sürpriz Açık" else 0.20
        gerekli_hit = max(3, onerilen_min_mac)
        if htft_hit >= gerekli_hit and float(htft_raw_prob) >= gerekli_raw:
            raw_combo_list.append({
                "label": f"HT/FT {htft_label}",
                "raw_prob": float(htft_raw_prob),
                "conf_prob": htft_conf,
                "hit": htft_hit,
                "fake_drop": htft_fake_drop,
                "type": "htft",
            })

    def uyum_kontrol(label, ana):
        if ana == "2.5 Alt":
            return ("2.5 Alt" in label) or ("KG Yok" in label) or ("HT/FT X/X" in label) or ("HT/FT 1/X" in label) or ("HT/FT X/1" in label) or ("HT/FT 2/X" in label) or ("HT/FT X/2" in label)
        if ana == "2.5 Üst":
            return ("2.5 Üst" in label) or ("KG Var" in label) or ("HT/FT 1/1" in label) or ("HT/FT 2/2" in label) or ("HT/FT 1/2" in label) or ("HT/FT 2/1" in label)
        if ana == "KG Var":
            return ("KG Var" in label) or ("2.5 Üst + KG Var" in label) or ("HT/FT 1/1" in label) or ("HT/FT 2/2" in label)
        if ana == "KG Yok":
            return ("KG Yok" in label) or ("2.5 Alt + KG Yok" in label)
        if ana == "MS 1":
            return ("MS1" in label) or ("HT/FT 1/" in label) or ("HT/FT X/1" in label)
        if ana == "MS 2":
            return ("MS2" in label) or ("HT/FT 2/" in label) or ("HT/FT X/2" in label)
        if ana == "Beraberlik":
            return ("MSX" in label) or ("HT/FT X/X" in label)
        return True

    combo_list = [c for c in raw_combo_list if uyum_kontrol(c["label"], ana_label)]
    combo_list = sorted(combo_list, key=lambda x: (x["conf_prob"], x["raw_prob"], x["hit"]), reverse=True)

    if combo_list and combo_list[0]["conf_prob"] >= 0.33 and not belirsiz:
        best_combo = combo_list[0]
        combo_label = best_combo["label"]
        combo_p = int(round(best_combo["conf_prob"] * 100))
        combo_raw_p = int(round(best_combo["raw_prob"] * 100))
        combo_hit = int(best_combo["hit"])
        combo_var = True
    else:
        combo_label = ""
        combo_p = 0
        combo_raw_p = 0
        combo_hit = 0
        combo_var = False

    # kombo seviye
    combo_level = ""
    if combo_var:
        if combo_p >= 60:
            combo_level = "Premium"
        elif combo_p >= 45:
            combo_level = "Güçlü"
        else:
            combo_level = "Deneysel"

    if belirsiz:
        ana_p = min(ana_p, 50)
        combo_label = ""
        combo_var = False
        combo_level = ""

    if ana_p < 35 and not belirsiz:
        ana_label = "Tahmin Zayıf"

    # en uyumlu senaryo
    if belirsiz:
        scenario_label = "Net senaryo oluşmadı"
    else:
        senaryo_parts = []
        if ana_label not in ["Belirsiz Maç", "Tahmin Zayıf"]:
            senaryo_parts.append(ana_label)
        if combo_var and combo_label and combo_label != ana_label:
            combo_core = combo_label.replace("MS1 + ", "").replace("MS2 + ", "").replace("MSX + ", "")
            if combo_core not in senaryo_parts and combo_label not in senaryo_parts:
                if combo_label.startswith("HT/FT"):
                    senaryo_parts.append(combo_label)
                else:
                    senaryo_parts.append(combo_core)
        scenario_label = " + ".join(senaryo_parts[:3]) if senaryo_parts else ana_label

    # canlı strateji
    if belirsiz:
        canli_label, canli_p = "İlk 15 dk izle", 48
        canli_strateji = "İlk 15 dakikada yön netleşmezse bu maçı pas geç. Erken baskı oluşursa ancak o zaman markete gir."
    elif iy05_raw * guven_carpani >= 0.68:
        canli_label = "İY 0.5 Üst" + (
            " · 3.5 Üst" if ms35_raw * guven_carpani >= 0.60 else
            " · 2.5 Üst" if ms25_raw * guven_carpani >= 0.60 else
            ""
        )
        canli_p = int(round(iy05_raw * guven_carpani * 100))
        canli_strateji = "İlk 15 dakikada yüksek tempo ve şut hacmi varsa canlı üst tarafı güçlenir. Erken gol gelirse üst senaryosu desteklenir."
    elif iy15_raw * guven_carpani >= 0.55:
        canli_label = "İY 1.5 Üst"
        canli_p = int(round(iy15_raw * guven_carpani * 100))
        canli_strateji = "Maç hızlı başlarsa ilk yarı golleri değerlendir. 20. dakikaya kadar tempo yoksa bu senaryoyu zayıflat."
    elif ana_label == "2.5 Alt" or combo_label == "2.5 Alt + KG Yok":
        canli_label, canli_p = "Alt Senaryosu", max(50, int(round((1 - ms25_raw) * guven_carpani * 100)))
        canli_strateji = "İlk 15-20 dakikada tempo düşük ve ceza sahası aksiyonu azsa alt taraf güçlenir. Erken gol gelirse yeniden değerlendir."
    elif ana_label == "KG Yok":
        canli_label, canli_p = "Tek Taraf Gol", max(50, int(round((1 - kg_raw) * guven_carpani * 100)))
        canli_strateji = "Zayıf taraf üretim yapmıyorsa KG Yok korunur. İki takım da net pozisyona girerse bu görüşü düşür."
    else:
        canli_label, canli_p = "Canlı İzle", 50
        canli_strateji = "İlk 10-15 dakikada baskı, şut ve korner üstünlüğü hangi taraftaysa sadece o yönde canlı giriş düşün."

    flip_p = float((((b["HTR"] == "H") & (b["FTR"] == "A")) | ((b["HTR"] == "A") & (b["FTR"] == "H"))).mean())

    risk_l, risk_cls = risk_seviyesi(ana_p, flip_p)
    eg, dg = tahmini_skor(b, ms_mod)
    eg, dg = skoru_tahmine_uydur(eg, dg, ana_label, ms_mod)
    gc, gb_cls, gb_lbl = guven_renk(ana_p)
    ornek_durum, ornek_renk = guven_metni(sample, float(tolerans))

    if sample < onerilen_min_mac:
        tavsiye = "Örnek az ama kullanılabilir"
    elif sample < max(10, onerilen_min_mac * 2):
        tavsiye = "Dengeli"
    elif sample > max(25, onerilen_min_mac * 3) and tolerans > 0.10:
        tavsiye = "Biraz düşürülebilir"
    else:
        tavsiye = "Uygun"

    avg_goal = float(toplam_gol.mean())
    goal_profile = gol_profili(avg_goal)

    nedenler = [
        f"Bu oran aralığında {sample} benzer maç bulundu.",
        f"Ham ana olasılık %{ana_raw_p} seviyesinde.",
        f"Ortalama toplam gol {avg_goal:.2f} ({goal_profile}).",
        f"Maç tipi: {match_type}.",
    ]
    if belirsiz:
        nedenler.append("1/X/2 dağılımı birbirine çok yakın olduğu için maç belirsiz işaretlendi.")
    if combo_var:
        nedenler.append(f"Güçlü kombo bulundu: {combo_label} (%{combo_raw_p}, {combo_hit} maç).")
    if fake_drop:
        nedenler.append("Düşük örnek + yüksek güven görüldüğü için fake confidence freni uygulandı.")
    if flip_p >= 0.12:
        nedenler.append(f"HT/FT sürpriz riski %{int(round(flip_p * 100))}.")

    playable_score = ana_p
    if combo_var:
        playable_score += min(combo_p, 20) * 0.35
    playable_score += min(sample, 40) * 0.25
    if match_type == "Favori":
        playable_score += 4
    elif match_type == "Dengeli":
        playable_score += 2
    if belirsiz:
        playable_score -= 12
    if fake_drop:
        playable_score -= 6
    if flip_p >= 0.12:
        playable_score -= 4
    playable_score = round(playable_score, 1)

    oynanabilir = (ana_p >= 58 and sample >= onerilen_min_mac and not belirsiz)

    score = ana_p * 0.65
    if sample < onerilen_min_mac:
        score -= 18
    elif sample < max(onerilen_min_mac * 2, 10):
        score += 4
    elif sample < max(onerilen_min_mac * 3, 18):
        score += 8
    else:
        score += 10
    if combo_var:
        score += min(8, combo_p * 0.12)
    if belirsiz:
        score -= 20
    if fake_drop:
        score -= 6
    if oynanabilir:
        score += 6
    score = round(score, 1)

    return {
        "ana_label": ana_label,
        "ana_p": ana_p,
        "playable_score": playable_score,
        "ana_raw_p": ana_raw_p,
        "ana_odd": ana_odd,
        "alt_label": alt_label,
        "alt_p": alt_p,
        "kg_label": kg_label,
        "kg_p": int(round(kg_raw * guven_carpani * 100)),
        "combo_label": combo_label,
        "combo_p": combo_p,
        "combo_raw_p": combo_raw_p,
        "combo_hit": combo_hit,
        "combo_var": combo_var,
        "combo_level": combo_level,
        "scenario_label": scenario_label,
        "canli_label": canli_label,
        "canli_p": canli_p,
        "canli_strateji": canli_strateji,
        "belirsiz": belirsiz,
        "ms_side": ms_side,
        "ms_p": int(round(ms_raw * guven_carpani * ms_bias * 100)),
        "ms_mod": ms_mod,
        "ms1_p": int(round(ms1_raw * guven_carpani * ms_bias * 100)),
        "msx_p": int(round(msx_raw * guven_carpani * ms_bias * 100)),
        "ms2_p": int(round(ms2_raw * guven_carpani * ms_bias * 100)),
        "ms25_p": int(round(ms25_raw * guven_carpani * goal_bias * 100)),
        "ms25a_p": int(round((1 - ms25_raw) * guven_carpani * goal_bias * 100)),
        "ms15_p": int(round(ms15_raw * guven_carpani * goal_bias * 100)),
        "ms35_p": int(round(ms35_raw * guven_carpani * goal_bias * 100)),
        "kg_var_p": int(round(kg_raw * guven_carpani * goal_bias * 100)),
        "kg_yok_p": int(round((1 - kg_raw) * guven_carpani * goal_bias * 100)),
        "iy05_p": int(round(iy05_raw * guven_carpani * goal_bias * 100)),
        "iy05a_p": int(round((1 - iy05_raw) * guven_carpani * goal_bias * 100)),
        "iy15_p": int(round(iy15_raw * guven_carpani * goal_bias * 100)),
        "iy1_p": int(round(float(iy_vc.get("H", 0)) * guven_carpani * 100)),
        "iyx_p": int(round(float(iy_vc.get("D", 0)) * guven_carpani * 100)),
        "iy2_p": int(round(float(iy_vc.get("A", 0)) * guven_carpani * 100)),
        "htft_mod": htft_mod,
        "htft_p": int(round(htft_raw * guven_carpani * combo_bias * 100)),
        "flip_p": flip_p,
        "risk_label": risk_l,
        "risk_cls": risk_cls,
        "eg": eg,
        "dg": dg,
        "guven_renk": gc,
        "guven_badge_cls": gb_cls,
        "guven_badge_lbl": gb_lbl,
        "ornek": sample,
        "ornek_durum": ornek_durum,
        "ornek_renk": ornek_renk,
        "onerilen_tolerans": rehber["onerilen_tolerans"],
        "onerilen_min_mac": onerilen_min_mac,
        "tolerans_yorumu": rehber["yorum"],
        "tolerans_tavsiyesi": tavsiye,
        "kullanilan_tolerans": round(float(tolerans), 2),
        "guven_carpani": round(guven_carpani, 3),
        "goal_profile": goal_profile,
        "match_type": match_type,
        "nedenler": nedenler,
        "oynanabilir": oynanabilir,
        "oynanabilir_esik_ok": (ana_p >= 55),
        "fake_drop": fake_drop,
        "score": score,
        "stability_tols": [],
        "stability_count": 0,
        "stability_text": "",
        "stability_early_tols": [],
        "stability_late_tols": [],
        "stability_early_text": "",
        "stability_late_text": "",
    }, b.sort_values("Date", ascending=False)





def kombo_tahmini_oran(label, ana_odd=None):
    """Kombo market için güvenli tahmini oran üretir.
    Gerçek oran API'den gelmediğinde top10/kupon sisteminin çökmesini engeller.
    """
    if not label:
        return None

    try:
        base = float(ana_odd) * 1.65 if ana_odd is not None else 2.20
    except Exception:
        base = 2.20

    text = str(label)
    if "KG Var" in text:
        base += 0.35
    if "KG Yok" in text:
        base += 0.25
    if "2.5 Üst" in text:
        base += 0.35
    if "2.5 Alt" in text:
        base += 0.25
    if "HT/FT" in text:
        base += 1.20

    return round(max(1.40, min(base, 8.50)), 2)


def top10_market_adaylari(t):
    """
    Top 10 için gerçek multi-market aday havuzu.
    Sadece MS'e kilitlenmez; MS / Alt-Üst / KG / İlk Yarı / Kombo marketlerini aynı havuza alır.
    Non-MS marketlere bilinçli bonus verir ki Top 10 sadece MS1-MS2 dolmasın.
    """
    adaylar = []

    def safe_int(v, default=0):
        try:
            return int(round(float(v or 0)))
        except Exception:
            return default

    def infer_tip(label):
        label = str(label or "")
        if label.startswith("MS") or label == "Beraberlik":
            return "MS"
        if "KG" in label:
            return "KG"
        if "Üst" in label or "Alt" in label or "2.5" in label or "1.5" in label or "3.5" in label:
            return "Alt/Üst"
        if "İY" in label:
            return "İlk Yarı"
        if "HT/FT" in label:
            return "HT/FT"
        if "+" in label:
            return "Kombo"
        return "Market"

    def add(label, guven, tip=None, oran=None, bonus=0, min_guven=50):
        label = str(label or "").strip()
        guven = safe_int(guven)
        if not label or label in ["Belirsiz Maç", "Tahmin Zayıf", "None", "-"]:
            return
        if guven < min_guven:
            return
        tip = tip or infer_tip(label)

        # Aynı label tekrar eklenirse en yüksek güvenli olanı tut.
        for a in adaylar:
            if a["label"] == label and a["tip"] == tip:
                if guven + bonus > a["guven"] + a["bonus"]:
                    a.update({"guven": guven, "oran": oran, "bonus": bonus})
                return

        adaylar.append({
            "label": label,
            "guven": guven,
            "tip": tip,
            "oran": oran,
            "bonus": bonus,
        })

    # Ana tahmin hangi market olursa olsun havuza girsin.
    ana_label = t.get("ana_label")
    ana_tip = infer_tip(ana_label)
    ana_bonus = {"MS": -4, "Alt/Üst": 16, "KG": 14, "İlk Yarı": 7, "Kombo": 10, "HT/FT": 8}.get(ana_tip, 0)
    add(ana_label, t.get("ana_p", 0), ana_tip, t.get("ana_odd"), bonus=ana_bonus, min_guven=50)

    # Alternatif/uyumlu tahmin havuza girsin.
    alt_label = t.get("alt_label")
    alt_tip = infer_tip(alt_label)
    alt_bonus = {"Alt/Üst": 15, "KG": 13, "MS": -2}.get(alt_tip, 5)
    add(alt_label, t.get("alt_p", 0), alt_tip, None, bonus=alt_bonus, min_guven=50)

    # MS marketleri: tek başına çok basmasın diye bonus düşük/negatif.
    add("MS 1", t.get("ms1_p", 0), "MS", None, bonus=-6, min_guven=52)
    add("Beraberlik", t.get("msx_p", 0), "MS", None, bonus=-4, min_guven=52)
    add("MS 2", t.get("ms2_p", 0), "MS", None, bonus=-6, min_guven=52)

    # Alt / Üst marketleri.
    add("2.5 Üst", t.get("ms25_p", 0), "Alt/Üst", None, bonus=18, min_guven=50)
    add("2.5 Alt", t.get("ms25a_p", 0), "Alt/Üst", None, bonus=18, min_guven=50)
    add("1.5 Üst", t.get("ms15_p", 0), "Alt/Üst", None, bonus=10, min_guven=58)
    add("3.5 Üst", t.get("ms35_p", 0), "Alt/Üst", None, bonus=9, min_guven=54)

    # KG marketleri.
    add("KG Var", t.get("kg_var_p", t.get("kg_p", 0)), "KG", None, bonus=16, min_guven=50)
    add("KG Yok", t.get("kg_yok_p", 0), "KG", None, bonus=16, min_guven=50)

    # İlk yarı marketleri.
    add("İY 0.5 Üst", t.get("iy05_p", 0), "İlk Yarı", None, bonus=7, min_guven=56)
    add("İY 0.5 Alt", t.get("iy05a_p", 0), "İlk Yarı", None, bonus=6, min_guven=56)
    add("İY 1.5 Üst", t.get("iy15_p", 0), "İlk Yarı", None, bonus=5, min_guven=52)

    # Kombo / HT-FT.
    if t.get("combo_var") and t.get("combo_label"):
        add(
            t.get("combo_label"),
            t.get("combo_p", 0),
            "Kombo",
            kombo_tahmini_oran(t.get("combo_label"), t.get("ana_odd")),
            bonus=12,
            min_guven=42,
        )

    if t.get("htft_mod") and str(t.get("htft_mod")) not in ["", "-"]:
        add(f"HT/FT {t.get('htft_mod')}", t.get("htft_p", 0), "HT/FT", None, bonus=8, min_guven=42)

    return adaylar


def gunun_en_iyi_10_uret(gecmis_df, bulten_df, min_ornek=1, limit=10):
    """
    Günün Top 10 listesini seçili hassasiyete bağlamaz.
    Her maç için 0.00 - 0.10 arası toleransları dener.
    MS / Alt-Üst / KG / İlk Yarı / Kombo adayları arasından maçın en iyi marketini seçer.
    API kullanmaz; sadece mevcut bülten + geçmiş veri üzerinden hesaplama yapar.
    """
    top_toleranslar = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10]
    adaylar = []

    if gecmis_df is None or bulten_df is None:
        return []
    if getattr(gecmis_df, "empty", True) or getattr(bulten_df, "empty", True):
        return []

    for _, m in bulten_df.iterrows():
        en_iyi = None

        for tol in top_toleranslar:
            try:
                t, b_det = hesapla(gecmis_df, m, tol)
            except Exception:
                continue

            if t is None or t.get("belirsiz"):
                continue

            ornek = int(t.get("ornek", 0) or 0)
            if ornek < max(1, int(min_ornek or 1)):
                continue

            marketler = top10_market_adaylari(t)
            if not marketler:
                continue

            tol_ceza = round(float(tol) * 100, 1)
            dusuk_tol_bonus = 8 if tol <= 0.02 else 5 if tol <= 0.04 else 2 if tol <= 0.06 else 0
            risk_ceza = 8 if t.get("risk_label") == "YÜKSEK" else 3 if t.get("risk_label") == "ORTA" else 0
            fake_ceza = 5 if t.get("fake_drop") else 0
            sample_bonus = min(ornek, 25) * 0.25
            playable = float(t.get("playable_score", 0) or 0)

            for mk in marketler:
                guven = int(mk.get("guven", 0) or 0)
                top10_skor = (
                    guven * 1.00
                    + playable * 0.22
                    + sample_bonus
                    + mk.get("bonus", 0)
                    + dusuk_tol_bonus
                    - tol_ceza
                    - risk_ceza
                    - fake_ceza
                )

                t_secili = t.copy()
                t_secili["top10_market_label"] = mk.get("label")
                t_secili["top10_market_tip"] = mk.get("tip")
                t_secili["top10_market_guven"] = guven
                t_secili["top10_market_oran"] = mk.get("oran")
                # Detay ekranı ve kartlar seçilen marketi ana tahmin gibi gösterebilsin.
                t_secili["ana_label"] = mk.get("label")
                t_secili["ana_p"] = guven
                if mk.get("oran") is not None:
                    t_secili["ana_odd"] = mk.get("oran")

                aday = {
                    "m": m.to_dict(),
                    "t": t_secili,
                    "b": b_det,
                    "top10_tol": round(float(tol), 2),
                    "top10_skor": round(top10_skor, 1),
                    "top10_market": mk,
                }
                aday["m"]["durum"] = mac_canli_durumu(aday["m"].get("zaman"))

                if en_iyi is None or aday["top10_skor"] > en_iyi["top10_skor"]:
                    en_iyi = aday

        if en_iyi:
            adaylar.append(en_iyi)

    adaylar.sort(
        key=lambda x: (
            x.get("top10_skor", 0),
            x.get("t", {}).get("top10_market_guven", 0),
            x.get("t", {}).get("ornek", 0),
        ),
        reverse=True,
    )

    # Top 10 sadece MS1/MS2 dolmasın diye küçük çeşitlilik kuralı.
    # Uygun non-MS aday varsa MS marketleri maksimum 4 adetle sınırlarız.
    secilen = []
    ms_sayisi = 0
    max_ms = 4

    for item in adaylar:
        tip = str(item.get("t", {}).get("top10_market_tip", ""))
        if tip == "MS" and ms_sayisi >= max_ms:
            continue
        secilen.append(item)
        if tip == "MS":
            ms_sayisi += 1
        if len(secilen) >= limit:
            break

    # Eğer yeterli aday dolmadıysa kalanları sıralamadan tamamla.
    if len(secilen) < limit:
        used = {mac_key(x.get("m", {})) + str(x.get("t", {}).get("top10_market_label", "")) for x in secilen}
        for item in adaylar:
            k = mac_key(item.get("m", {})) + str(item.get("t", {}).get("top10_market_label", ""))
            if k in used:
                continue
            secilen.append(item)
            if len(secilen) >= limit:
                break

    return secilen[:limit]



for key, default in [
    ("final_list", []),
    ("detay_idx", None),
    ("detay_item", None),
    ("top10_list", []),
    ("filtre", "tumu"),
    ("kupona", []),
    ("coupon_popup_open", False),
    ("last_gecmis_df", None),
    ("last_bulten_df", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

FUTBOL_LIGLERI = {
    "AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league",
    },
    "TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
    },
    "İNGİLTERE": {
        "Premier League": "soccer_epl",
        "Championship": "soccer_efl_champ",
        "League 1": "soccer_england_league1",
        "League 2": "soccer_england_league2",
        "FA Cup": "soccer_fa_cup",
        "EFL Cup": "soccer_england_efl_cup",
    },
    "İSPANYA": {
        "La Liga": "soccer_spain_la_liga",
        "La Liga 2": "soccer_spain_segunda_division",
        "Copa del Rey": "soccer_spain_copa_del_rey",
    },
    "ALMANYA": {
        "Bundesliga": "soccer_germany_bundesliga",
        "Bundesliga 2": "soccer_germany_bundesliga2",
        "DFB-Pokal": "soccer_germany_dfb_pokal",
    },
    "İTALYA": {
        "Serie A": "soccer_italy_serie_a",
        "Serie B": "soccer_italy_serie_b",
        "Coppa Italia": "soccer_italy_coppa_italia",
    },
    "FRANSA": {
        "Ligue 1": "soccer_france_ligue_one",
        "Ligue 2": "soccer_france_ligue_two",
        "Coupe de France": "soccer_france_coupe_de_france",
    },
    "AVRUPA VALUE": {
        "Hollanda": "soccer_netherlands_eredivisie",
        "Belçika": "soccer_belgium_first_div",
        "Portekiz": "soccer_portugal_primeira_liga",
        "İskoçya": "soccer_spl",
        "Danimarka": "soccer_denmark_superliga",
        "Avusturya": "soccer_austria_bundesliga",
        "İsviçre": "soccer_switzerland_superleague",
        "İsveç": "soccer_sweden_allsvenskan",
        "Norveç": "soccer_norway_eliteserien",
        "Polonya": "soccer_poland_ekstraklasa",
        "Finlandiya": "soccer_finland_veikkausliiga",
        "İrlanda": "soccer_league_of_ireland",
        "Yunanistan": "soccer_greece_super_league",
    },
    "DÜNYA VALUE": {
        "MLS": "soccer_usa_mls",
        "Brezilya Serie A": "soccer_brazil_campeonato",
        "Arjantin Primera": "soccer_argentina_primera_division",
        "Japonya J League": "soccer_japan_j_league",
        "Meksika Liga MX": "soccer_mexico_ligamx",
        "Güney Kore K League 1": "soccer_korea_kleague1",
        "Şili Primera": "soccer_chile_campeonato",
    },
}


LEAGUE_EMOJIS = {
    "Şampiyonlar Ligi": "🏆",
    "Avrupa Ligi": "🟠",
    "Konferans Ligi": "🟢",
    "Süper Lig": "🇹🇷",
    "Premier League": "🏴",
    "Championship": "🏴",
    "League 1": "🏴",
    "League 2": "🏴",
    "FA Cup": "🏴",
    "EFL Cup": "🏴",
    "La Liga": "🇪🇸",
    "La Liga 2": "🇪🇸",
    "Copa del Rey": "🇪🇸",
    "Bundesliga": "🇩🇪",
    "Bundesliga 2": "🇩🇪",
    "DFB-Pokal": "🇩🇪",
    "Serie A": "🇮🇹",
    "Serie B": "🇮🇹",
    "Coppa Italia": "🇮🇹",
    "Ligue 1": "🇫🇷",
    "Ligue 2": "🇫🇷",
    "Coupe de France": "🇫🇷",
    "Hollanda": "🇳🇱",
    "Belçika": "🇧🇪",
    "Portekiz": "🇵🇹",
    "İskoçya": "🏴",
    "Danimarka": "🇩🇰",
    "Avusturya": "🇦🇹",
    "İsviçre": "🇨🇭",
    "İsveç": "🇸🇪",
    "Norveç": "🇳🇴",
    "Polonya": "🇵🇱",
    "Finlandiya": "🇫🇮",
    "İrlanda": "🇮🇪",
    "Yunanistan": "🇬🇷",
    "MLS": "🇺🇸",
    "Brezilya Serie A": "🇧🇷",
    "Arjantin Primera": "🇦🇷",
    "Japonya J League": "🇯🇵",
    "Meksika Liga MX": "🇲🇽",
    "Güney Kore K League 1": "🇰🇷",
    "Şili Primera": "🇨🇱",
}


def lig_etiketi(isim: str) -> str:
    emoji = LEAGUE_EMOJIS.get(isim, "⚽")
    return f"{emoji} {isim}"


def tum_lig_listesi():
    rows = []
    for kat, ligler in FUTBOL_LIGLERI.items():
        for isim, kod in ligler.items():
            rows.append({
                "kategori": kat,
                "isim": isim,
                "kod": kod,
                "label": lig_etiketi(isim),
            })
    return rows


def filtrelenmis_lig_listesi(arama_text: str):
    ligler = tum_lig_listesi()
    if not arama_text:
        return ligler

    q = arama_text.strip().lower()
    return [
        x for x in ligler
        if q in x["isim"].lower() or q in x["kategori"].lower()
    ]


KARLI_LIG_PRESETLERI = {
    # Popup içindeki tek hızlı filtre: Kararlı çekirdek + kârlı/value ligler birlikte seçilir.
    "cekirdek_value": [
        # Kararlı çekirdek
        "soccer_epl",
        "soccer_efl_champ",
        "soccer_spain_la_liga",
        "soccer_spain_segunda_division",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_germany_bundesliga2",
        "soccer_france_ligue_one",
        "soccer_turkey_super_league",
        "soccer_netherlands_eredivisie",
        "soccer_norway_eliteserien",
        "soccer_usa_mls",
        "soccer_switzerland_superleague",
        "soccer_uefa_champs_league",
        "soccer_uefa_europa_league",
        "soccer_uefa_europa_conference_league",
        # Kârlı / value ek ligler
        "soccer_portugal_primeira_liga",
        "soccer_belgium_first_div",
        "soccer_austria_bundesliga",
        "soccer_denmark_superliga",
        "soccer_sweden_allsvenskan",
        "soccer_finland_veikkausliiga",
    ],
}


def tum_lig_kodlari():
    return [kod for ligler in FUTBOL_LIGLERI.values() for kod in ligler.values()]


def init_league_states():
    for _, ligler in FUTBOL_LIGLERI.items():
        for _, kod in ligler.items():
            item_key = f"cb_{kod}"
            if item_key not in st.session_state:
                st.session_state[item_key] = False



def set_leagues(selected_codes):
    secili = set(selected_codes)
    for kod in tum_lig_kodlari():
        st.session_state[f"cb_{kod}"] = kod in secili



def clear_leagues():
    set_leagues([])


def toggle_leagues(selected_codes):
    secili = set(selected_codes)
    tumu_aktif = all(st.session_state.get(f"cb_{kod}", False) for kod in secili) if secili else False
    if tumu_aktif:
        for kod in secili:
            st.session_state[f"cb_{kod}"] = False
    else:
        set_leagues(selected_codes)

def sonraki_hafta_gunu(baslangic_tarihi, hedef_weekday: int):
    gun_farki = (hedef_weekday - baslangic_tarihi.weekday()) % 7
    return baslangic_tarihi + timedelta(days=gun_farki)


def tarih_secimine_gore_date(secim: str, bugun_tarih, ozel_tarih):
    if secim == "Bugün":
        return bugun_tarih
    if secim == "Yarın":
        return bugun_tarih + timedelta(days=1)
    if secim == "2 gün sonra":
        return bugun_tarih + timedelta(days=2)
    if secim == "3 gün sonra":
        return bugun_tarih + timedelta(days=3)
    return ozel_tarih


def mac_canli_durumu(mac_zamani):
    now = datetime.now()
    if now < mac_zamani:
        return "Başlamamış"
    if now <= mac_zamani + timedelta(hours=2, minutes=15):
        return "Canlı"
    return "Bitti"


def mac_durum_badge(mac_zamani):
    durum = mac_canli_durumu(mac_zamani)
    if durum == "Canlı":
        return "#16a34a", "CANLI"
    if durum == "Başlamamış":
        return "#2563eb", "YAKINDA"
    return "#64748b", "BİTTİ"


init_league_states()

# =========================
# YENİ UI — SOL FİLTRE + KART LİSTE + MODAL DETAY
# =========================

def selected_league_codes():
    return [lig["kod"] for lig in tum_lig_listesi() if st.session_state.get(f"cb_{lig['kod']}", False)]


def pred_class(label):
    s = str(label)
    if "MS 2" in s:
        return "red"
    if "2.5" in s or "Alt" in s or "Üst" in s:
        return "amber"
    if "KG" in s:
        return "cyan"
    return ""


def conf_class(p):
    p = int(p or 0)
    if p >= 70:
        return "", "Yüksek"
    if p >= 55:
        return "mid", "Orta"
    return "low", "Düşük"


def safe(v, default="-"):
    return default if v is None or v == "" else v


def render_history_table(b_det, max_rows=10):
    """HTML table yerine div-grid kullanır; Streamlit'te <tr>/<td> kod olarak görünme sorununu engeller."""
    if b_det is None or getattr(b_det, "empty", True):
        return "<div class='why-box'>Benzer maç verisi bulunamadı.</div>"

    cols_needed = ["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
    for c in cols_needed:
        if c not in b_det.columns:
            return "<div class='why-box'>Geçmiş maç tablosu için gerekli kolonlar yok.</div>"

    # b_det Date descending sıralı geldiği için en güncel/son 10 maç için head() kullanılır.
    temp = b_det.head(max_rows).copy()
    rows = []
    for _, r in temp.iterrows():
        try:
            hg = int(r.get("FTHG", 0) or 0)
            ag = int(r.get("FTAG", 0) or 0)
        except Exception:
            hg, ag = 0, 0
        total_goals = hg + ag
        ust = "Üst" if total_goals >= 3 else "Alt"
        kg = "Var" if hg > 0 and ag > 0 else "Yok"
        ms = {"H": "1", "D": "X", "A": "2"}.get(str(r.get("FTR", "")), "-")
        ust_cls = "green" if ust == "Üst" else "gray"
        kg_cls = "green" if kg == "Var" else "red"
        ms_cls = "green" if ms == "1" else "red" if ms == "2" else "gray"
        rows.append(f"""
        <div class='hist-row'>
          <div>{escape(str(r.get('HomeTeam',''))[:16])}</div>
          <div>{escape(str(r.get('AwayTeam',''))[:16])}</div>
          <div>{hg}-{ag}</div>
          <div><span class='tag {ust_cls}'>{ust}</span></div>
          <div><span class='tag {kg_cls}'>{kg}</span></div>
          <div><span class='tag {ms_cls}'>{ms}</span></div>
        </div>
        """)

    return f"""
    <div class='hist-head'>
      <div>EV</div><div>DEP</div><div>SKOR</div><div>2.5</div><div>KG</div><div>MS</div>
    </div>
    {''.join(rows)}
    """


def render_detail_html(item):
    m, t, b_det = item["m"], item["t"], item.get("b")
    ana = escape(str(safe(t.get("ana_label"))))
    p = int(t.get("ana_p", 0) or 0)
    eg, dg = int(t.get("eg", 0) or 0), int(t.get("dg", 0) or 0)
    conf_cls, conf_text = conf_class(p)
    nedenler = t.get("nedenler", []) or []
    why = "".join([f"<div class='why-line'>• {escape(str(x))}</div>" for x in nedenler[:7]]) or "<div class='why-line'>• Model bu maçı mevcut oran ve geçmiş benzerlik üzerinden analiz etti.</div>"

    combo = escape(str(t.get("combo_label") or "Kombo önerisi zayıf"))
    combo_p = int(t.get("combo_p", 0) or 0)
    combo_level = escape(str(t.get("combo_level") or ("Güçlü" if combo_p >= 45 else "Deneysel")))
    combo_odd = kombo_tahmini_oran(t.get("combo_label"), t.get("ana_odd")) if t.get("combo_label") else None

    canli_label = escape(str(safe(t.get("canli_label"), "Canlı İzle")))
    canli_p = int(t.get("canli_p", 0) or 0)
    canli_strateji = escape(str(safe(t.get('canli_strateji'), 'İlk 10-15 dakikadaki tempo, şut ve baskı kontrol edilmeli.')))

    history = render_history_table(b_det)
    tarih = m["zaman"].strftime("%d %B %Y · %H:%M") if hasattr(m.get("zaman"), "strftime") else str(m.get("zaman", ""))
    tarih = escape(tarih)
    lig = escape(str(safe(m.get('lig'))))
    ev = escape(str(safe(m.get('ev'))))
    dep = escape(str(safe(m.get('dep'))))

    avg_goal_txt = escape(str(t.get("goal_profile", "Dengeli")))
    home_power = "-"
    away_power = "-"
    try:
        home_power = f"{1 / float(m.get('h')) * 2:.2f}"
        away_power = f"{1 / float(m.get('a')) * 2:.2f}"
    except Exception:
        pass

    combo_odd_html = f"<b>@{fmt_odd(combo_odd)}</b>" if combo_odd else "<b>-</b>"

    detail_css = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
      *{box-sizing:border-box} html,body{margin:0;padding:0;background:transparent;font-family:Inter,Arial,sans-serif;color:#102040;}
      body{overflow-x:hidden;}
      .detail-shell{width:100%;background:#fff;border:1px solid #c9d5ea;border-radius:18px;overflow:hidden;box-shadow:0 24px 80px rgba(17,29,58,.30);}
      .detail-head{background:linear-gradient(135deg,#111d3a 0%,#091a43 100%);color:#fff;padding:22px 28px 24px;}
      .detail-topline{font-size:12px;color:#b6c4df;font-weight:900;margin-bottom:6px;}
      .detail-title{font-size:32px;line-height:1.1;font-weight:900;letter-spacing:-.03em;color:#fff;}
      .detail-date{font-size:13px;color:#b6c4df;margin-top:8px;font-weight:700;}
      .metric-grid{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e4ebf6;background:#fff;}
      .metric{padding:19px 12px;text-align:center;border-right:1px solid #e4ebf6;min-height:104px;display:flex;flex-direction:column;align-items:center;justify-content:center;}
      .metric:last-child{border-right:0;}
      .metric-label{font-size:11px;color:#7f90b0;text-transform:uppercase;font-weight:900;letter-spacing:.07em;}
      .metric-val{font-size:28px;font-weight:900;color:#102040;line-height:1.12;margin-top:7px;}
      .metric-val.blue{color:#1f74ff}.metric-val.green{color:#16c978}.metric-val.dark{color:#0f1d3d;}
      .metric-sub{font-size:12px;color:#60708e;margin-top:5px;font-weight:700;}
      .detail-body{display:grid;grid-template-columns:1fr 1fr;gap:30px;padding:26px 28px 20px;background:#fff;}
      .panel-title{font-size:13px;color:#65799d;text-transform:uppercase;font-weight:900;letter-spacing:.075em;margin:0 0 13px;}
      .panel-title.mt{margin-top:22px;}
      .stat-row{display:flex;align-items:center;justify-content:space-between;background:#f8faff;border:1px solid #dce5f3;border-radius:10px;padding:14px 16px;margin-bottom:9px;font-size:15px;font-weight:900;color:#14264b;min-height:54px;}
      .stat-mini{display:flex;gap:17px;align-items:center;font-size:12px;color:#53668a;text-align:center;}
      .stat-mini b{display:block;color:#0f1d3d;font-size:13px;white-space:nowrap;}
      .odds-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:18px;}
      .big-odd{border:1px solid #dce5f3;border-radius:11px;background:#f9fbff;text-align:center;padding:18px 8px;min-height:94px;display:flex;flex-direction:column;justify-content:center;}
      .big-odd small{display:block;color:#65799d;font-size:11px;text-transform:uppercase;font-weight:900;margin-bottom:8px;}
      .big-odd b{font-size:30px;line-height:1;color:#1f74ff;font-weight:900;}
      .market-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:4px 0 22px;}
      .market-card{border-radius:11px;text-align:center;padding:14px 8px;border:1px solid #dce5f3;background:#f9fbff;}
      .market-card.green{background:#eafaf3;border-color:#aeeacc;color:#087948}.market-card.amber{background:#fff8e8;border-color:#ffd676;color:#9a4b00}.market-card.cyan{background:#ecfbff;border-color:#a8eaff;color:#075985}
      .market-card small{display:block;font-size:11px;font-weight:900;text-transform:uppercase;margin-bottom:5px}.market-card b{font-size:22px;font-weight:900;}
      .combo-row{display:flex;justify-content:space-between;align-items:center;background:#f8faff;border:1px solid #dce5f3;border-radius:10px;padding:15px 16px;margin-bottom:10px;font-size:16px;font-weight:900;color:#14264b;}
      .combo-left{display:flex;align-items:center;gap:12px}.tag{display:inline-flex;align-items:center;justify-content:center;border-radius:7px;padding:4px 8px;font-size:11px;font-weight:900;line-height:1}.tag.green{background:#dcfce7;color:#15803d}.tag.red{background:#fee2e2;color:#dc2626}.tag.gray{background:#eef1f6;color:#475569}.tag.blue{background:#dbeafe;color:#2563eb}.tag.amber{background:#fef3c7;color:#b45309}
      .combo-row b{color:#1f74ff;font-size:20px;}
      .why-box{background:#f8faff;border:1px solid #dce5f3;border-radius:10px;padding:14px 16px;font-size:13px;color:#344664;line-height:1.7;font-weight:700;}
      .why-line{margin-bottom:2px;color:#344664}.why-line::first-letter{color:#1f74ff;}
      .hist-head,.hist-row{display:grid;grid-template-columns:1.2fr 1.2fr .7fr .55fr .55fr .55fr;gap:8px;align-items:center;}
      .hist-head{color:#65799d;font-size:11px;font-weight:900;letter-spacing:.05em;margin:4px 0 8px;text-transform:uppercase;}
      .hist-row{border-top:1px solid #e5ebf4;padding:9px 0;font-size:13px;color:#14264b;font-weight:800;}
      .footer-metrics{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #e3eaf5;margin:2px 28px 0;padding:20px 0 24px;}
      .footer-metric{text-align:center;border-right:1px solid #e3eaf5;}.footer-metric:last-child{border-right:0}.footer-metric small{display:block;text-transform:uppercase;color:#102040;font-weight:900;font-size:12px;margin-bottom:8px}.footer-metric b{font-size:24px;color:#1f74ff;font-weight:900}.footer-metric b.green{color:#16c978}.footer-metric b.red{color:#dc2626}.footer-metric b.purple{color:#6d28d9}
      .legal-box{margin:0 28px 18px;background:#fff7ed;border:1px solid #fdba74;border-radius:12px;padding:13px 16px;color:#b45309;font-size:13px;line-height:1.55;font-weight:700;}
      @media(max-width:850px){.detail-title{font-size:24px}.metric-grid{grid-template-columns:repeat(2,1fr)}.detail-body{grid-template-columns:1fr;padding:18px}.odds-grid,.market-grid{gap:10px}.footer-metrics{grid-template-columns:repeat(2,1fr);margin:0 18px}.hist-head,.hist-row{grid-template-columns:1fr 1fr .6fr .5fr .5fr .5fr;font-size:11px}.legal-box{margin:0 18px 18px}}
    </style>
    """

    return f"""
    <!doctype html>
    <html>
    <head>{detail_css}</head>
    <body>
    <div class='detail-shell'>
      <div class='detail-head'>
        <div class='detail-topline'>{lig}</div>
        <div class='detail-title'>{ev} – {dep}</div>
        <div class='detail-date'>{tarih}</div>
      </div>

      <div class='metric-grid'>
        <div class='metric'><div class='metric-label'>Ana Tahmin</div><div class='metric-val blue'>{ana}</div><div class='metric-sub'>Model seçimi</div></div>
        <div class='metric'><div class='metric-label'>Güven Skoru</div><div class='metric-val green'>{p}%</div><div class='metric-sub'>{conf_text} Güven</div></div>
        <div class='metric'><div class='metric-label'>Tahmini Skor</div><div class='metric-val dark'>{eg} – {dg}</div><div class='metric-sub'>En olası skor</div></div>
        <div class='metric'><div class='metric-label'>Benzer Maç</div><div class='metric-val dark'>{int(t.get('ornek',0) or 0)}</div><div class='metric-sub'>Analiz edildi</div></div>
      </div>

      <div class='detail-body'>
        <div>
          <div class='panel-title'>Maç Tahminleri</div>
          <div class='stat-row'><span>Maç Sonucu</span><div class='stat-mini'><b>1<br>%{int(t.get('ms1_p',0) or 0)}</b><b>X<br>%{int(t.get('msx_p',0) or 0)}</b><b>2<br>%{int(t.get('ms2_p',0) or 0)}</b></div></div>
          <div class='stat-row'><span>2.5 Üst/Alt</span><div class='stat-mini'><b>Üst<br>%{int(t.get('ms25_p',0) or 0)}</b><b>Alt<br>%{int(t.get('ms25a_p',0) or 0)}</b></div></div>
          <div class='stat-row'><span>Karşılıklı Gol</span><div class='stat-mini'><b>Var<br>%{int(t.get('kg_var_p', t.get('kg_p',0)) or 0)}</b><b>Yok<br>%{int(t.get('kg_yok_p', 100-int(t.get('kg_p',0) or 0)) or 0)}</b></div></div>
          <div class='stat-row'><span>İlk Yarı Sonucu</span><div class='stat-mini'><b>1<br>%{int(t.get('iy1_p',0) or 0)}</b><b>X<br>%{int(t.get('iyx_p',0) or 0)}</b><b>2<br>%{int(t.get('iy2_p',0) or 0)}</b></div></div>
          <div class='stat-row'><span>İlk Yarı 0.5 Gol</span><div class='stat-mini'><b>Üst<br>%{int(t.get('iy05_p',0) or 0)}</b><b>Alt<br>%{int(t.get('iy05a_p',0) or 0)}</b></div></div>

          <div class='panel-title mt'>Kombo Önerileri</div>
          <div class='combo-row'><div class='combo-left'><span>{combo}</span><span class='tag green'>{combo_level}</span></div>{combo_odd_html}</div>
          <div class='combo-row'><div class='combo-left'><span>{canli_label}</span><span class='tag blue'>Canlı</span></div><b>%{canli_p}</b></div>

          <div class='panel-title mt'>Neden Bu Tahmin?</div>
          <div class='why-box'>{why}</div>
        </div>

        <div>
          <div class='panel-title'>Oranlar</div>
          <div class='odds-grid'>
            <div class='big-odd'><small>Ev Sahibi</small><b>{fmt_odd(m.get('h'))}</b></div>
            <div class='big-odd'><small>Beraberlik</small><b style='color:#6d28d9'>{fmt_odd(m.get('b'))}</b></div>
            <div class='big-odd'><small>Deplasman</small><b style='color:#dc2626'>{fmt_odd(m.get('a'))}</b></div>
          </div>

          <div class='market-grid'>
            <div class='market-card green'><small>2.5 Üst</small><b>%{int(t.get('ms25_p',0) or 0)}</b></div>
            <div class='market-card amber'><small>2.5 Alt</small><b>%{int(t.get('ms25a_p',0) or 0)}</b></div>
            <div class='market-card cyan'><small>KG Var</small><b>%{int(t.get('kg_var_p', t.get('kg_p',0)) or 0)}</b></div>
          </div>

          <div class='panel-title'>Benzer Oranlı Geçmiş Maçlar (Son 10)</div>
          {history}
        </div>
      </div>

      <div class='footer-metrics'>
        <div class='footer-metric'><small>Ev Sahibi Gücü</small><b>{home_power}</b></div>
        <div class='footer-metric'><small>Beraberlik İhtimali</small><b class='purple'>%{int(t.get('msx_p',0) or 0)}</b></div>
        <div class='footer-metric'><small>Deplasman Gücü</small><b class='red'>{away_power}</b></div>
        <div class='footer-metric'><small>Maç Temposu</small><b class='green'>{avg_goal_txt}</b></div>
      </div>

      <div class='legal-box'>⚠️ Bu tahminler istatistiksel analiz ve yapay zekâ destekli tahminler sunar. Kesin kazanç garantisi verilmez.<br>Bahis oynamak risk içerir ve bağımlılık oluşturabilir.</div>
    </div>
    </body>
    </html>
    """


try:
    dialog_decorator = st.dialog
except AttributeError:
    dialog_decorator = st.experimental_dialog

@dialog_decorator(" ", width="large")
def mac_detay_modal():
    item = st.session_state.get("detay_item")
    if not item and st.session_state.get("detay_idx") is not None:
        try:
            item = st.session_state.final_list[st.session_state.detay_idx]
        except Exception:
            item = None
    if not item:
        st.warning("Detay bulunamadı.")
        if st.button("Kapat"):
            st.session_state.detay_item = None
            st.session_state.detay_idx = None
            st.rerun()
        return
    c1, c2 = st.columns([10,1])
    with c2:
        if st.button("×", key="close_detail_modal", use_container_width=True):
            st.session_state.detay_item = None
            st.session_state.detay_idx = None
            st.rerun()
    components.html(
    textwrap.dedent(render_detail_html(item)),
    height=1120,
    scrolling=True
)


def clear_detail_state():
    """Filtre/sıralama değişince eski detay modalının kendiliğinden açılmasını engeller."""
    st.session_state.detay_item = None
    st.session_state.detay_idx = None

# Sidebar filtreleri
bugun = datetime.now().date()
with st.sidebar:
    st.markdown("<div class='side-logo'><div class='logo-box'>OA</div><div class='side-brand'>OddsAnaliz</div></div>", unsafe_allow_html=True)
    if st.button("⇆", use_container_width=True, key="sidebar_fake_toggle"):
        st.toast("Streamlit sidebar ok tuşuyla kapanır/açılır.")

    st.markdown("<div class='side-section'><div class='side-title'>API</div></div>", unsafe_allow_html=True)
    API_KEY = get_app_api_key()
    if API_KEY:
        st.success("API key aktif ✅")
    else:
        st.warning("API key gerekli")

    st.markdown("<div class='side-section'><div class='side-title'>Tarih</div></div>", unsafe_allow_html=True)
    if "date_mode" not in st.session_state:
        st.session_state.date_mode = "Bugün"
    if "special_date" not in st.session_state:
        st.session_state.special_date = bugun
    date_mode = st.radio("Tarih", ["Bugün", "Yarın", "2 gün sonra", "3 gün sonra", "Özel Tarih"], key="date_mode", label_visibility="collapsed", on_change=clear_detail_state)
    if date_mode == "Özel Tarih":
        st.date_input("Özel tarih", value=st.session_state.special_date, key="special_date", on_change=clear_detail_state)
    secili_tarih = tarih_secimine_gore_date(date_mode, bugun, st.session_state.special_date)

    st.markdown("<div class='side-section'><div class='side-title'>Ligler</div></div>", unsafe_allow_html=True)
    lig_arama = st.text_input("Lig ara", placeholder="Bundesliga, MLS...", label_visibility="collapsed", on_change=clear_detail_state)
    lc1, lc2 = st.columns(2)
    with lc1:
        if st.button("Tümü", use_container_width=True):
            clear_detail_state(); set_leagues(tum_lig_kodlari()); st.rerun()
    with lc2:
        if st.button("Temizle", use_container_width=True):
            clear_detail_state(); clear_leagues(); st.rerun()
    if st.button("Çekirdek + Value", use_container_width=True):
        clear_detail_state(); toggle_leagues(KARLI_LIG_PRESETLERI.get("cekirdek_value", tum_lig_kodlari())); st.rerun()
    lig_box = st.container(height=250, border=False)
    with lig_box:
        for lig in filtrelenmis_lig_listesi(lig_arama):
            st.checkbox(lig["label"], key=f"cb_{lig['kod']}", on_change=clear_detail_state)

    st.markdown("<div class='side-section'><div class='side-title'>Güven Skoru</div></div>", unsafe_allow_html=True)
    guven_filtreleri = st.multiselect("Güven", ["Yüksek (70%+)", "Orta (50–70%)", "Düşük (<50%)"], default=["Yüksek (70%+)", "Orta (50–70%)"], label_visibility="collapsed", on_change=clear_detail_state)

    st.markdown("<div class='side-section'><div class='side-title'>Tahmin Tipi</div></div>", unsafe_allow_html=True)
    tip_ms = st.checkbox("MS1 / MS2 / X", value=True, on_change=clear_detail_state)
    tip_ou = st.checkbox("2.5 Üst/Alt", value=True, on_change=clear_detail_state)
    tip_kg = st.checkbox("KG Var/Yok", value=True, on_change=clear_detail_state)

    st.markdown("<div class='side-section'><div class='side-title'>Analiz Ayarları</div></div>", unsafe_allow_html=True)
    yillar = st.multiselect("Sezonlar", ['2122','2223','2324','2425','2526'], default=['2122','2223','2324','2425','2526'], on_change=clear_detail_state)
    min_ornek = st.number_input("Min. örnek", min_value=1, value=1, on_change=clear_detail_state)
    TOLERANS = st.slider("Oran hassasiyeti", 0.00, 0.30, 0.08, step=0.01, on_change=clear_detail_state)
    canli_filtre = st.selectbox("Canlı", ["Tümü", "Canlı", "Başlamamış", "Bitti"], on_change=clear_detail_state)
    analiz_btn = st.button("▶ ANALİZİ BAŞLAT", use_container_width=True, type="primary")

secili_kodlar = selected_league_codes()

# Analiz çalıştır
if analiz_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("📊 Veriler çekiliyor ve analiz ediliyor..."):
            gecmis = futbol_veri_motoru(tuple(yillar))
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            st.session_state.last_gecmis_df = gecmis
            st.session_state.last_bulten_df = bulten
            final = []
            stability_tols = [0.00, 0.03, 0.05, 0.08, 0.10]
            if not bulten.empty and not gecmis.empty:
                for _, m in bulten.iterrows():
                    t, b_det = hesapla(gecmis, m, TOLERANS)
                    if t is None or len(b_det) < min_ornek:
                        continue
                    stable_hits = []
                    for stab_tol in stability_tols:
                        stab_t, stab_b = hesapla(gecmis, m, stab_tol)
                        if stab_t and stab_t.get("ana_label") == t.get("ana_label") and stab_t.get("ornek",0) >= max(min_ornek, stab_t.get("onerilen_min_mac",1)):
                            stable_hits.append(f"{stab_tol:.2f}")
                    t["stability_tols"] = stable_hits
                    t["stability_count"] = len(stable_hits)
                    t["playable_score"] = round(t.get("playable_score", t.get("ana_p",0)) + min(5, len(stable_hits)), 1)
                    m_dict = m.to_dict()
                    m_dict["durum"] = mac_canli_durumu(m_dict["zaman"])
                    if canli_filtre != "Tümü" and m_dict["durum"] != canli_filtre:
                        continue
                    final.append({"m": m_dict, "t": t, "b": b_det})
            final = sorted(final, key=lambda x: (x["t"].get("playable_score",0), x["t"].get("ana_p",0), x["t"].get("ornek",0)), reverse=True)
            st.session_state.final_list = final
            st.session_state.top10_list = gunun_en_iyi_10_uret(gecmis, bulten, min_ornek=min_ornek, limit=10) if not bulten.empty and not gecmis.empty else []
            st.session_state.son_analiz = datetime.now().strftime("%d/%m/%Y %H:%M")
            st.session_state.toplam_mac = len(final)
            st.session_state.detay_item = None
            st.session_state.detay_idx = None
        st.rerun()

# Ana liste filtre/sıralama
fl = st.session_state.get("final_list", [])
filtered = []
for item in fl:
    t = item["t"]
    p = int(t.get("ana_p",0) or 0)
    label = str(t.get("ana_label", ""))
    ok_guven = ((p >= 70 and "Yüksek (70%+)" in guven_filtreleri) or (50 <= p < 70 and "Orta (50–70%)" in guven_filtreleri) or (p < 50 and "Düşük (<50%)" in guven_filtreleri))
    ok_tip = ((label.startswith("MS") or "Beraberlik" in label) and tip_ms) or (("2.5" in label or "Alt" in label or "Üst" in label) and tip_ou) or ("KG" in label and tip_kg)
    if ok_guven and ok_tip:
        filtered.append(item)

st.markdown("<div class='app-top'><div class='app-title'>Anlık Maç Tahminleri <span class='count-pill'>%d Maç</span> <span style='font-size:12px;color:#20b970'><span class='live-dot'></span>Canlı</span></div><div class='sort-wrap'></div></div>" % len(filtered), unsafe_allow_html=True)
sort_col1, sort_col2 = st.columns([3,1])
with sort_col2:
    siralama = st.selectbox("Sıralama", ["Güven: Yüksek → Düşük", "Saat: Yakın → Uzak", "Oran: Yüksek → Düşük"], label_visibility="collapsed", on_change=clear_detail_state)
if siralama.startswith("Güven"):
    filtered.sort(key=lambda x: x["t"].get("ana_p",0), reverse=True)
elif siralama.startswith("Saat"):
    filtered.sort(key=lambda x: x["m"].get("zaman"))
else:
    filtered.sort(key=lambda x: float(x["t"].get("ana_odd") or max(x["m"].get("h",0), x["m"].get("b",0), x["m"].get("a",0))), reverse=True)

if not fl:
    st.markdown("<div class='empty'><b>Analizi Başlatın</b><br>Sol bardan API, tarih ve ligleri seçip analizi başlat.</div>", unsafe_allow_html=True)
elif not filtered:
    st.markdown("<div class='empty'><b>Filtreye uygun maç yok.</b><br>Sol bardaki güven/tahmin tipi filtrelerini genişlet.</div>", unsafe_allow_html=True)

for i, item in enumerate(filtered):
    m, t = item["m"], item["t"]
    p = int(t.get("ana_p",0) or 0)
    conf_cls, _ = conf_class(p)
    card_cls = "mid" if 55 <= p < 70 else "low" if p < 55 else ""
    pred_cls = pred_class(t.get("ana_label", ""))
    st.markdown(f"""
    <div class='match-card {card_cls}'>
      <div><div class='m-time'>{m['zaman'].strftime('%H:%M') if hasattr(m.get('zaman'),'strftime') else ''}</div><div class='m-league'>{str(m.get('lig',''))[:12]}</div></div>
      <div><div class='team-row'><span class='team-icon'></span>{safe(m.get('ev'))}</div><div class='team-row'><span class='team-icon' style='opacity:.75'></span>{safe(m.get('dep'))}</div></div>
      <div><span class='pred-pill {pred_cls}'>{safe(t.get('ana_label'))}</span></div>
      <div><div class='conf {conf_cls}'>{p}%<small>Güven</small></div></div>
      <div class='odds'><div class='odd-box'><span>1</span><b>{fmt_odd(m.get('h'))}</b></div><div class='odd-box'><span>X</span><b>{fmt_odd(m.get('b'))}</b></div><div class='odd-box'><span>2</span><b>{fmt_odd(m.get('a'))}</b></div></div>
      <div class='detail-slot'></div>
    </div>
    """, unsafe_allow_html=True)
    # Butonu kartın hemen altına koyuyoruz; Streamlit native buton olduğu için sorunsuz çalışır.
    _, bcol = st.columns([6,1])
    with bcol:
        if st.button("Detay →", key=f"new_detail_{i}_{abs(hash(str(m.get('ev'))+str(m.get('dep'))+str(m.get('zaman'))))}", use_container_width=True):
            st.session_state.detay_item = item
            st.session_state.detay_idx = None
            st.rerun()

if st.session_state.get("detay_item") is not None or st.session_state.get("detay_idx") is not None:
    mac_detay_modal()

legal_footer()
