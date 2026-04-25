import math
from datetime import datetime, timedelta, date
from html import escape

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="OddsAnaliz", page_icon="OA", layout="wide", initial_sidebar_state="expanded")

APP_VERSION = 42
if st.session_state.get("app_version") != APP_VERSION:
    st.session_state.clear()
    st.session_state["app_version"] = APP_VERSION

LEAGUES = {
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one",
    "MLS": "soccer_usa_mls",
    "Premier League": "soccer_epl",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Belgium": "soccer_belgium_first_div",
    "Denmark": "soccer_denmark_superliga",
    "Norway": "soccer_norway_eliteserien",
    "Portugal": "soccer_portugal_primeira_liga",
    "Turkey": "soccer_turkey_super_league",
}

HIST_CODES = ["E0", "E1", "SP1", "D1", "I1", "F1", "N1", "B1", "P1", "SC0", "T1"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800&display=swap');
:root{--navy:#101d3d;--navy2:#142754;--blue:#2f7df6;--green:#19c77b;--yellow:#f6b325;--red:#ee3d3d;--line:#dbe5f3;--soft:#f4f7fc;--text:#071735;--muted:#8290ae}
html,body,.stApp,[class*=css]{font-family:Inter,system-ui,sans-serif;background:#eef3fb!important;color:var(--text)!important}.main .block-container{max-width:1220px;padding:0 1rem 1rem 1rem}.stApp>header{display:none}
section[data-testid="stSidebar"]{background:#102044!important;border-right:1px solid #263b70!important;width:255px!important}section[data-testid="stSidebar"] *{color:#dbe7ff!important}section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] p{font-size:.78rem!important}.stTextInput input{background:#162a58!important;border:1px solid #39558f!important;color:#fff!important}.stCheckbox label span{color:#dbe7ff!important}.stButton>button{border-radius:10px!important;border:1px solid #dce5f2!important;background:#fff!important;color:#173057!important;font-weight:800!important}.stButton>button:hover{border-color:#2f7df6!important;color:#2f7df6!important}
.logo{display:flex;align-items:center;gap:10px;margin:10px 0 18px}.logo-b{background:#3182ff;color:white;border-radius:8px;padding:7px 6px;font-weight:900}.logo-t{font-weight:900;font-size:1.05rem;color:#fff}.side-title{font-size:.68rem;letter-spacing:1.6px;color:#7f90bb!important;margin:14px 0 8px}.side-pill{background:#172f66;border-radius:10px;padding:8px 10px;margin:5px 0;font-weight:800;font-size:.82rem}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px}.g{background:#20d47e}.y{background:#ffc13b}.b{background:#2f7df6}.r{background:#ff5757}
.top{height:58px;background:white;border-bottom:1px solid #dde6f2;display:flex;align-items:center;justify-content:space-between;padding:0 16px;margin:0 -1rem 14px}.title{font-size:1.05rem;font-weight:900}.badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;background:#317ef8;color:#fff;font-size:.68rem;font-weight:900;padding:4px 8px;margin-left:8px}.live{font-size:.72rem;color:#14b76b;font-weight:800;margin-left:14px}.sort{background:#202020;color:#fff;border-radius:7px;padding:10px 18px;font-weight:800;box-shadow:0 1px 2px rgba(0,0,0,.18)}
.match-card{background:white;border:1px solid #dbe5f3;border-left:3px solid var(--green);border-radius:12px;margin:10px 0;padding:12px 14px;display:grid;grid-template-columns:62px 1.5fr 90px 62px 134px 92px;align-items:center;gap:12px}.match-card.mid{border-left-color:var(--yellow)}.match-card.low{border-left-color:#3e82ff}.time{font-weight:900;font-size:.93rem}.league{font-size:.58rem;color:#7f8dad;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.teams{font-size:.79rem;font-weight:800;line-height:1.55}.team-dot{display:inline-block;width:13px;height:8px;border-radius:2px;background:#26365e;margin-right:7px}.pred{display:inline-block;border:1px solid #bcd1ff;background:#eef4ff;color:#1d5eff;border-radius:7px;padding:5px 12px;font-weight:900;font-size:.8rem}.pred.alt{border-color:#ffd87d;background:#fff7dc;color:#ad6500}.pred.red{border-color:#ffc6c6;background:#fff0f0;color:#e21f1f}.pred.kg{border-color:#aee0ff;background:#eafdff;color:#006aa4}.conf{font-size:1rem;font-weight:900}.conf small{display:block;font-size:.55rem;font-weight:600;color:#8290ae}.odds{display:flex;gap:6px}.odd{background:#f5f7fc;border:1px solid #d8e2f2;border-radius:6px;text-align:center;min-width:38px;padding:4px 3px}.odd small{display:block;color:#8a98b6;font-size:.53rem}.odd b{font-size:.75rem}.detail-btn{border:1px solid #e7edf7;border-radius:8px;text-align:center;color:#c6cedb;font-weight:900;padding:10px 0;background:white}
.detail{background:white;border-radius:13px;border:1px solid #dce6f3;overflow:hidden;margin-top:12px}.dh{background:#111f44;color:white;padding:12px 18px;position:relative}.dh .lg{font-size:.7rem;color:#8ea0cc;font-weight:800}.dh .teams-title{font-size:1.55rem;font-weight:900;line-height:1.05}.dh .dt{color:#8ea0cc;font-size:.75rem;margin-top:6px}.close{position:absolute;right:13px;top:9px;border:1px solid #5770a5;border-radius:7px;color:#fff;padding:4px 9px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e3eaf4}.metric{text-align:center;padding:14px 8px;border-right:1px solid #e3eaf4}.metric:last-child{border-right:0}.ml{font-size:.68rem;color:#8b9ab8;font-weight:900}.mv{font-size:1.55rem;color:#2169ef;font-weight:900}.msub{font-size:.68rem;color:#8090ad}.detail-body{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px}.sect-title{color:#8998b8;font-size:.72rem;font-weight:900;letter-spacing:.8px;margin:3px 0 9px}.row{background:#f6f8fd;border:1px solid #dfe7f4;border-radius:8px;margin:6px 0;padding:10px;display:flex;justify-content:space-between;align-items:center;font-size:.8rem;font-weight:800}.mini-pcts{font-size:.62rem;color:#697999}.odd-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.big-odd{background:#f7f9fe;border:1px solid #dfe7f4;border-radius:9px;text-align:center;padding:14px 6px}.big-odd .lab{font-size:.62rem;color:#8998b8;font-weight:900}.big-odd .val{font-size:1.35rem;font-weight:900;color:#2a6cec}.big-odd.green{background:#eafff5;border-color:#b9ecd7}.big-odd.green .val{color:#008b58}.big-odd.gold{background:#fff8e4;border-color:#ffd978}.big-odd.gold .val{color:#b36d00}.big-odd.blue{background:#edf8ff;border-color:#bde5ff}.big-odd.blue .val{color:#006da8}.combo{background:#f1f5fb;border:1px solid #dbe5f3;border-radius:8px;padding:10px 12px;margin:8px 0;display:flex;justify-content:space-between;font-weight:900}.tag{font-size:.6rem;padding:3px 7px;border-radius:999px;background:#dcfce7;color:#067a43;margin-left:6px}.why{background:#f6f8fd;border:1px solid #dfe7f4;border-radius:10px;padding:12px;margin-top:10px;color:#40506e;font-size:.78rem;line-height:1.7}.hist{width:100%;border-collapse:collapse;font-size:.72rem}.hist th{color:#8898b8;text-align:left;padding:5px}.hist td{border-top:1px solid #e6edf7;padding:6px;color:#30405f;font-weight:700}.pill-ok{background:#dcfce7;color:#078044;border-radius:5px;padding:2px 6px}.pill-no{background:#ffe5e5;color:#e02525;border-radius:5px;padding:2px 6px}
.warn{background:#fff7ed;border:1px solid #fdba74;border-radius:10px;padding:10px 12px;color:#7c2d12;font-size:.78rem;margin-top:14px}
@media(max-width:900px){.match-card{grid-template-columns:55px 1fr 70px;}.odds,.detail-btn{display:none}.detail-body,.metrics{grid-template-columns:1fr}.metric{border-right:0;border-bottom:1px solid #e3eaf4}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def esc(x): return escape(str(x or ""))
def fmt_odd(x):
    try: return f"{float(x):.2f}"
    except Exception: return "-"

def api_key():
    user_key = st.session_state.get("api_key", "").strip()
    if user_key: return user_key
    try: return st.secrets.get("ODDS_API_KEY", "").strip()
    except Exception: return ""


def tr_date(d):
    ay = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
    return f"{d.day} {ay[d.month-1]} {d.year}"


def confidence_class(p):
    if p >= 70: return "high", "#16c778", "Yüksek"
    if p >= 60: return "mid", "#ffae00", "Orta"
    return "low", "#347cff", "Düşük"


def pred_class(label):
    s = str(label)
    if "Alt" in s: return "alt"
    if "MS2" in s or s == "MS 2": return "red"
    if "KG" in s: return "kg"
    return ""


@st.cache_data(ttl=86400, show_spinner=False)
def history_data(seasons):
    frames = []
    for season in seasons:
        for code in HIST_CODES:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
                df = pd.read_csv(url)
                need = ["Date","HomeTeam","AwayTeam","FTHG","FTAG","HTHG","HTAG","FTR","HTR","B365H","B365D","B365A"]
                df = df[df.columns.intersection(need)].dropna(subset=["B365H","B365D","B365A","FTR"])
                for col in ["FTHG","FTAG","HTHG","HTAG","B365H","B365D","B365A"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna()
                frames.append(df)
            except Exception:
                pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@st.cache_data(ttl=1200, show_spinner=False)
def fetch_odds(key, sports, target_day):
    rows = []
    if not key: return pd.DataFrame()
    for code in sports:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{code}/odds/",
                params={"apiKey": key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}, timeout=12)
            if r.status_code != 200: continue
            for m in r.json():
                try: t = datetime.strptime(m["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except Exception: continue
                if t.date() != target_day: continue
                home, away = m.get("home_team",""), m.get("away_team","")
                if not away:
                    away = next((x for x in m.get("teams", []) if x != home), "")
                market = None
                for bk in m.get("bookmakers", []):
                    market = next((x for x in bk.get("markets", []) if x.get("key") == "h2h"), None)
                    if market: break
                if not market: continue
                outs = market.get("outcomes", [])
                h = next((x.get("price") for x in outs if x.get("name") == home), None)
                a = next((x.get("price") for x in outs if x.get("name") == away), None)
                d = next((x.get("price") for x in outs if str(x.get("name","")).lower() in ["draw","tie"]), None)
                if h and d and a:
                    rows.append({"lig": m.get("sport_title", code), "code": code, "zaman": t, "ev": home, "dep": away, "h": float(h), "b": float(d), "a": float(a)})
        except Exception:
            pass
    return pd.DataFrame(rows).drop_duplicates(subset=["ev","dep","zaman"]).sort_values("zaman") if rows else pd.DataFrame()


def similar_matches(hist, m, tol):
    if hist.empty: return hist
    return hist[
        hist.B365H.between(m["h"]-tol, m["h"]+tol) &
        hist.B365D.between(m["b"]-tol, m["b"]+tol) &
        hist.B365A.between(m["a"]-tol, m["a"]+tol)
    ].copy()


def analyze(hist, m, tol=0.08):
    b = similar_matches(hist, m, tol)
    if b.empty:
        return None, b
    goals = b.FTHG + b.FTAG
    ms = b.FTR.value_counts(normalize=True)
    p1, px, p2 = float(ms.get("H",0)), float(ms.get("D",0)), float(ms.get("A",0))
    over25 = float((goals >= 3).mean()); under25 = 1 - over25
    kg = float(((b.FTHG > 0) & (b.FTAG > 0)).mean()); kg_yok = 1 - kg
    sample = len(b)
    factor = min(.74 + sample / 80, 1.0)
    cands = [("MS1", p1, m["h"]), ("X", px, m["b"]), ("MS2", p2, m["a"]), ("2.5 Üst", over25, None), ("2.5 Alt", under25, None), ("KG Var", kg, None), ("KG Yok", kg_yok, None)]
    label, raw, odd = max(cands, key=lambda x: x[1])
    conf = max(35, min(92, int(round(raw * factor * 100))))
    avg_h, avg_a = b.FTHG.mean(), b.FTAG.mean()
    eh, ea = int(math.floor(avg_h + .5)), int(math.floor(avg_a + .5))
    if label == "2.5 Alt": eh, ea = (1, 1) if abs(m["h"]-m["a"]) < .7 else ((1,0) if m["h"] < m["a"] else (0,1))
    if label == "2.5 Üst": eh, ea = (2,1) if m["h"] < m["a"] else (1,2)
    if label == "MS1" and eh <= ea: eh = ea + 1
    if label == "MS2" and ea <= eh: ea = eh + 1
    if label == "X": eh = ea = max(1, min(2, eh))
    combo1 = f"{'MS1' if p1>=p2 else 'MS2'} + {'KG Var' if kg>=.5 else 'KG Yok'}"
    combo2 = f"{'MS1' if p1>=p2 else 'MS2'} + {'2.5 Üst' if over25>=.5 else '2.5 Alt'}"
    return {
        "label": label, "conf": conf, "sample": sample, "score": f"{eh} - {ea}",
        "p1": int(p1*100), "px": int(px*100), "p2": int(p2*100),
        "over": int(over25*100), "under": int(under25*100), "kg": int(kg*100), "nkg": int(kg_yok*100),
        "combo1": combo1, "combo2": combo2, "odd": odd,
        "why": [f"{sample} benzer maç analiz edildi, oran aralığı ±{tol:.2f}.", f"Ham ana oran %{int(raw*100)} seviyesinde güçlü sinyal veriyor.", f"Ortalama toplam gol {goals.mean():.2f} seviyesinde."],
    }, b


def sidebar():
    st.sidebar.markdown('<div class="logo"><span class="logo-b">OA</span><span class="logo-t">OddsAnaliz</span></div>', unsafe_allow_html=True)
    key = st.sidebar.text_input("ODDS API KEY", value=st.session_state.get("api_key", ""), type="password", placeholder="API key gir...")
    if key != st.session_state.get("api_key", ""):
        st.session_state["api_key"] = key.strip()
    st.sidebar.markdown('<div class="side-title">LİGLER</div>', unsafe_allow_html=True)
    selected = []
    for name, code in LEAGUES.items():
        default = name in ["Bundesliga", "Ligue 1", "MLS"]
        if st.sidebar.checkbox(name, value=st.session_state.get(f"lg_{name}", default), key=f"lg_{name}"):
            selected.append(code)
    st.sidebar.markdown('<div class="side-title">GÜVEN SKORU</div><div class="side-pill"><span class="dot g"></span>Yüksek (70%+)</div><div class="side-pill"><span class="dot y"></span>Orta (50–70%)</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="side-title">TAHMİN TİPİ</div>', unsafe_allow_html=True)
    st.sidebar.checkbox("MS1/MS2/X", True, key="type_ms")
    st.sidebar.checkbox("2.5 Üst/Alt", True, key="type_ou")
    st.sidebar.checkbox("KG Var/Yok", False, key="type_kg")
    tol = st.sidebar.slider("Oran hassasiyeti", 0.02, 0.15, 0.08, 0.01)
    return selected, tol


def render_card(i, m, t):
    cls, color, _ = confidence_class(t["conf"])
    pc = pred_class(t["label"])
    html = f"""
    <div class="match-card {'mid' if t['conf']<70 else ''} {'low' if t['conf']<60 else ''}">
      <div><div class="time">{m['zaman'].strftime('%H:%M')}</div><div class="league">{esc(m['lig'])}</div></div>
      <div class="teams"><div><span class="team-dot"></span>{esc(m['ev'])}</div><div><span class="team-dot" style="opacity:.75"></span>{esc(m['dep'])}</div></div>
      <div><span class="pred {pc}">{esc(t['label'])}</span></div>
      <div class="conf" style="color:{color}">{t['conf']}%<small>Güven</small></div>
      <div class="odds"><div class="odd"><small>1</small><b>{fmt_odd(m['h'])}</b></div><div class="odd"><small>X</small><b>{fmt_odd(m['b'])}</b></div><div class="odd"><small>2</small><b>{fmt_odd(m['a'])}</b></div></div>
      <div class="detail-btn">Detay →</div>
    </div>"""
    c1, c2 = st.columns([9, 1])
    with c1: st.markdown(html, unsafe_allow_html=True)
    with c2:
        st.write("")
        if st.button("Aç", key=f"open_{i}", use_container_width=True):
            st.session_state["selected"] = i
            st.rerun()


def render_detail(i, m, t, b):
    if st.button("× Kapat", key="close_detail"):
        st.session_state.pop("selected", None); st.rerun()
    cls, color, glabel = confidence_class(t["conf"])
    rows = b.tail(10).copy() if not b.empty else pd.DataFrame()
    hist_rows = ""
    for _, r in rows.iterrows():
        total = int(r.FTHG + r.FTAG)
        kg = r.FTHG > 0 and r.FTAG > 0
        ms = "1" if r.FTR == "H" else "2" if r.FTR == "A" else "X"
        hist_rows += f"<tr><td>{esc(r.HomeTeam)}</td><td>{esc(r.AwayTeam)}</td><td>{int(r.FTHG)}-{int(r.FTAG)}</td><td><span class='pill-ok'>{'Üst' if total>=3 else 'Alt'}</span></td><td><span class='{'pill-ok' if kg else 'pill-no'}'>{'Var' if kg else 'Yok'}</span></td><td>{ms}</td></tr>"
    html = f"""
    <div class="detail">
      <div class="dh"><div class="lg">{esc(m['lig'])}</div><div class="teams-title">{esc(m['ev'])} – {esc(m['dep'])}</div><div class="dt">{tr_date(m['zaman'].date())} · Pazar · {m['zaman'].strftime('%H:%M')}</div></div>
      <div class="metrics"><div class="metric"><div class="ml">ANA TAHMİN</div><div class="mv">{esc(t['label'])}</div><div class="msub">{esc(t['label'])}</div></div><div class="metric"><div class="ml">GÜVEN SKORU</div><div class="mv" style="color:{color}">{t['conf']}%</div><div class="msub">{glabel} Güven</div></div><div class="metric"><div class="ml">TAHMİNİ SKOR</div><div class="mv" style="color:#17234a">{t['score']}</div><div class="msub">En olası skor</div></div><div class="metric"><div class="ml">BENZER MAÇ</div><div class="mv" style="color:#17234a">{t['sample']}</div><div class="msub">Analiz edildi</div></div></div>
      <div class="detail-body"><div>
        <div class="sect-title">MAÇ TAHMİNLERİ</div>
        <div class="row"><span>Maç Sonucu</span><span class="mini-pcts">1 %{t['p1']} &nbsp; X %{t['px']} &nbsp; 2 %{t['p2']}</span></div>
        <div class="row"><span>2.5 Üst/Alt</span><span class="mini-pcts">Üst %{t['over']} &nbsp; Alt %{t['under']}</span></div>
        <div class="row"><span>Karşılıklı Gol</span><span class="mini-pcts">Var %{t['kg']} &nbsp; Yok %{t['nkg']}</span></div>
        <div class="sect-title" style="margin-top:14px">KOMBO ÖNERİLERİ</div>
        <div class="combo"><span>{esc(t['combo1'])}<span class="tag">Güçlü</span></span><span>@2.85</span></div>
        <div class="combo"><span>{esc(t['combo2'])}<span class="tag" style="background:#fff2c6;color:#9c6500">Deneysel</span></span><span>@3.10</span></div>
        <div class="sect-title" style="margin-top:14px">NEDEN BU TAHMİN?</div><div class="why">• {'<br>• '.join(esc(x) for x in t['why'])}</div>
      </div><div>
        <div class="sect-title">ORANLAR</div><div class="odd-grid"><div class="big-odd"><div class="lab">EV SAHİBİ</div><div class="val">{fmt_odd(m['h'])}</div></div><div class="big-odd"><div class="lab">BERABERLİK</div><div class="val" style="color:#6d4bd4">{fmt_odd(m['b'])}</div></div><div class="big-odd"><div class="lab">DEPLASMAN</div><div class="val" style="color:#e21f1f">{fmt_odd(m['a'])}</div></div></div>
        <div class="odd-grid" style="margin-top:9px"><div class="big-odd green"><div class="lab">2.5 ÜST</div><div class="val">1.87</div></div><div class="big-odd gold"><div class="lab">2.5 ALT</div><div class="val">1.95</div></div><div class="big-odd blue"><div class="lab">KG VAR</div><div class="val">1.72</div></div></div>
        <div class="sect-title" style="margin-top:14px">BENZER ORANLI GEÇMİŞ MAÇLAR (SON 10)</div><table class="hist"><tr><th>EV</th><th>DEP</th><th>SKOR</th><th>2.5</th><th>KG</th><th>MS</th></tr>{hist_rows}</table>
      </div></div>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)

selected_leagues, tolerance = sidebar()

today = datetime.now().date()
with st.container():
    st.markdown('<div class="top"><div class="title">Anlık Maç Tahminleri <span class="badge">0 Maç</span><span class="live">● Canlı</span></div><div class="sort">Güven: Yüksek → Düşük</div></div>', unsafe_allow_html=True)

key = api_key()
if not key:
    st.warning("Sol menüden ODDS API KEY girmen gerekiyor.")
    st.stop()

cdate = st.date_input("Tarih", value=today, label_visibility="collapsed")
seasons = ["2526", "2425", "2324", "2223"]
with st.spinner("Maçlar ve geçmiş oranlar analiz ediliyor..."):
    hist = history_data(seasons)
    odds = fetch_odds(key, selected_leagues, cdate)

if odds.empty:
    st.info("Bu tarih/lig seçimi için maç bulunamadı veya API limitin dolmuş olabilir.")
    st.stop()

items = []
for idx, m in odds.reset_index(drop=True).iterrows():
    t, b = analyze(hist, m, tolerance)
    if t:
        items.append((idx, m, t, b))
items.sort(key=lambda x: x[2]["conf"], reverse=True)

st.markdown(f"""<script>document.querySelector('.badge').innerText='{len(items)} Maç';</script>""", unsafe_allow_html=True)
if not items:
    st.warning("Benzer oranlı geçmiş maç bulunamadı. Hassasiyeti biraz artırmayı dene.")
    st.stop()

for idx, m, t, b in items:
    render_card(idx, m, t)

sel = st.session_state.get("selected")
if sel is not None:
    found = next((x for x in items if x[0] == sel), None)
    if found:
        render_detail(*found)

st.markdown('<div class="warn"><b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler ve yapay zekâ destekli tahminler sunar. Kesin kazanç garantisi verilmez.</div>', unsafe_allow_html=True)
