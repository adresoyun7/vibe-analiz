import os
import math
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date

# =========================
# CONFIG
# =========================

st.set_page_config(
    page_title="Vibe Analiz AI",
    page_icon="⚽",
    layout="wide"
)

API_BASE = "https://api.the-odds-api.com/v4"

DEFAULT_LEAGUES = {
    "Premier League": "soccer_epl",
    "La Liga": "soccer_spain_la_liga",
    "Bundesliga": "soccer_germany_bundesliga",
    "Serie A": "soccer_italy_serie_a",
    "Ligue 1": "soccer_france_ligue_one",
    "Süper Lig": "soccer_turkey_super_league",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Championship": "soccer_efl_champ",
    "MLS": "soccer_usa_mls",
    "Denmark Superliga": "soccer_denmark_superliga",
    "Saudi Pro League": "soccer_saudi_arabia_pro_league",
    "UCL": "soccer_uefa_champs_league",
    "UEL": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
}

# =========================
# STYLE
# =========================

st.markdown("""
<style>
body, .stApp {
    background: #07111f;
    color: #eaf1ff;
}

.main-card {
    background: linear-gradient(145deg, #0d1b2f, #081424);
    border: 1px solid rgba(255, 204, 64, .25);
    border-radius: 20px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 12px 32px rgba(0,0,0,.25);
}

.metric-pill {
    display:inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    margin-right: 6px;
    font-size: 13px;
    background: rgba(255,255,255,.08);
    border: 1px solid rgba(255,255,255,.12);
}

.good {
    background: rgba(46, 204, 113, .15);
    color: #5ff39a;
    border: 1px solid rgba(46,204,113,.35);
}

.value {
    background: rgba(255, 204, 64, .15);
    color: #ffd86b;
    border: 1px solid rgba(255,204,64,.35);
}

.risk {
    background: rgba(255, 92, 92, .13);
    color: #ff9a9a;
    border: 1px solid rgba(255,92,92,.35);
}

.gray {
    color: #aab6cc;
}

.big-title {
    font-size: 34px;
    font-weight: 800;
    color: #ffd86b;
    margin-bottom: 0;
}

.sub-title {
    color: #aab6cc;
    margin-top: 2px;
}

hr {
    border-color: rgba(255,255,255,.08);
}
</style>
""", unsafe_allow_html=True)

# =========================
# HELPERS
# =========================

def safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def mac_key(m):
    home = m.get("home") or m.get("home_team") or m.get("ev") or m.get("takim1") or ""
    away = m.get("away") or m.get("away_team") or m.get("dep") or m.get("takim2") or ""
    dt = m.get("date") or m.get("commence_time") or m.get("tarih") or ""
    return f"{str(home).strip().lower()}_{str(away).strip().lower()}_{str(dt).strip()}"


def implied_prob(odd):
    odd = safe_float(odd)
    if not odd or odd <= 1:
        return 0
    return 1 / odd


def normalize_probs(raw):
    total = sum(raw.values())
    if total <= 0:
        return raw
    return {k: v / total for k, v in raw.items()}


def clamp(x, a, b):
    return max(a, min(b, x))


def fmt_pct(x):
    try:
        return f"%{round(float(x) * 100)}"
    except Exception:
        return "-"


def fmt_odd(x):
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "-"


def date_option_to_range(opt, custom_day=None):
    today = date.today()

    if opt == "Bugün":
        d = today
    elif opt == "Yarın":
        d = today + timedelta(days=1)
    elif opt == "2 Gün Sonra":
        d = today + timedelta(days=2)
    elif opt == "3 Gün Sonra":
        d = today + timedelta(days=3)
    else:
        d = custom_day or today

    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


def parse_match_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return "-"


def get_bookmaker_markets(event):
    """
    The Odds API event içinden h2h, totals, btts oranlarını normalize eder.
    """
    result = {
        "h": None,
        "d": None,
        "a": None,
        "over25": None,
        "under25": None,
        "btts_yes": None,
        "btts_no": None,
    }

    bookmakers = event.get("bookmakers", [])
    if not bookmakers:
        return result

    # İlk dolu bookmaker üzerinden alıyoruz
    for bm in bookmakers:
        for market in bm.get("markets", []):
            key = market.get("key")

            if key == "h2h":
                outcomes = market.get("outcomes", [])
                home = event.get("home_team")
                away = event.get("away_team")

                for o in outcomes:
                    name = o.get("name")
                    price = safe_float(o.get("price"))
                    if name == home:
                        result["h"] = price
                    elif name == away:
                        result["a"] = price
                    elif name and name.lower() in ["draw", "tie", "x"]:
                        result["d"] = price

            elif key == "totals":
                for o in market.get("outcomes", []):
                    point = safe_float(o.get("point"))
                    name = str(o.get("name", "")).lower()
                    price = safe_float(o.get("price"))

                    if point == 2.5:
                        if "over" in name:
                            result["over25"] = price
                        elif "under" in name:
                            result["under25"] = price

            elif key == "btts":
                for o in market.get("outcomes", []):
                    name = str(o.get("name", "")).lower()
                    price = safe_float(o.get("price"))

                    if name in ["yes", "evet"]:
                        result["btts_yes"] = price
                    elif name in ["no", "hayır", "hayir"]:
                        result["btts_no"] = price

        if any(result.values()):
            break

    return result


# =========================
# AI ENGINE
# =========================

def estimate_goal_profile(h, d, a, over25=None, under25=None, btts_yes=None, btts_no=None):
    """
    Basit ama tutarlı AI skor profili.
    Oranlardan favori gücü + gol eğilimi çıkarır.
    """
    h = safe_float(h)
    d = safe_float(d)
    a = safe_float(a)

    raw = {
        "MS 1": implied_prob(h),
        "X": implied_prob(d),
        "MS 2": implied_prob(a),
    }
    probs = normalize_probs(raw)

    p1 = probs.get("MS 1", 0)
    px = probs.get("X", 0)
    p2 = probs.get("MS 2", 0)

    fav_side = "home" if p1 >= p2 else "away"
    fav_power = abs(p1 - p2)

    over_p = implied_prob(over25)
    under_p = implied_prob(under25)

    if over_p and under_p:
        ou = normalize_probs({"over": over_p, "under": under_p})
        goal_temp = ou["over"]
    else:
        goal_temp = 0.52

    btts_p = implied_prob(btts_yes)
    nobtts_p = implied_prob(btts_no)

    if btts_p and nobtts_p:
        kg = normalize_probs({"yes": btts_p, "no": nobtts_p})
        btts_temp = kg["yes"]
    else:
        btts_temp = 0.50

    base_goals = 2.15 + (goal_temp - 0.5) * 1.6
    base_goals = clamp(base_goals, 1.4, 3.8)

    if fav_power > 0.22:
        if fav_side == "home":
            hg = 1.55 + fav_power * 2.4
            ag = max(0.45, base_goals - hg)
        else:
            ag = 1.45 + fav_power * 2.4
            hg = max(0.45, base_goals - ag)
    else:
        hg = base_goals / 2
        ag = base_goals / 2

    if btts_temp > 0.56:
        hg = max(hg, 1.05)
        ag = max(ag, 1.05)

    return {
        "home_xg": round(hg, 2),
        "away_xg": round(ag, 2),
        "goal_temp": round(goal_temp, 3),
        "btts_temp": round(btts_temp, 3),
        "fav_power": round(fav_power, 3),
    }


def predicted_score(profile):
    hg = profile["home_xg"]
    ag = profile["away_xg"]

    h_score = int(round(hg))
    a_score = int(round(ag))

    h_score = clamp(h_score, 0, 5)
    a_score = clamp(a_score, 0, 5)

    return f"{h_score}-{a_score}", h_score, a_score


def ai_analyze_match(m):
    h = m.get("h")
    d = m.get("d")
    a = m.get("a")
    over25 = m.get("over25")
    under25 = m.get("under25")
    btts_yes = m.get("btts_yes")
    btts_no = m.get("btts_no")

    raw_ms = {
        "MS 1": implied_prob(h),
        "X": implied_prob(d),
        "MS 2": implied_prob(a),
    }
    ms_probs = normalize_probs(raw_ms)

    profile = estimate_goal_profile(h, d, a, over25, under25, btts_yes, btts_no)
    score_text, hs, aw = predicted_score(profile)

    total_goals = hs + aw
    btts_hit = hs > 0 and aw > 0

    ana_label = max(ms_probs, key=ms_probs.get)
    ana_p = ms_probs[ana_label]
    ana_odd = h if ana_label == "MS 1" else d if ana_label == "X" else a

    markets = []

    # MS
    for label, odd in [("MS 1", h), ("X", d), ("MS 2", a)]:
        p = ms_probs.get(label, 0)
        if odd:
            fair_odd = 1 / p if p > 0 else None
            value_score = ((odd / fair_odd) - 1) if fair_odd else 0
            markets.append({
                "label": label,
                "p": p,
                "odd": odd,
                "type": "MS",
                "value": value_score,
            })

    # 2.5
    goal_temp = profile["goal_temp"]
    over_p = clamp(goal_temp, 0.35, 0.72)
    under_p = 1 - over_p

    if over25:
        markets.append({
            "label": "2.5 Üst",
            "p": over_p,
            "odd": over25,
            "type": "Gol",
            "value": over25 * over_p - 1,
        })

    if under25:
        markets.append({
            "label": "2.5 Alt",
            "p": under_p,
            "odd": under25,
            "type": "Gol",
            "value": under25 * under_p - 1,
        })

    # KG
    btts_temp = profile["btts_temp"]
    yes_p = clamp(btts_temp, 0.35, 0.72)
    no_p = 1 - yes_p

    if btts_yes:
        markets.append({
            "label": "KG Var",
            "p": yes_p,
            "odd": btts_yes,
            "type": "KG",
            "value": btts_yes * yes_p - 1,
        })

    if btts_no:
        markets.append({
            "label": "KG Yok",
            "p": no_p,
            "odd": btts_no,
            "type": "KG",
            "value": btts_no * no_p - 1,
        })

    # Çelişki düzeltme
    for mk in markets:
        if mk["label"] == "2.5 Alt" and total_goals >= 3:
            mk["p"] *= 0.78
        if mk["label"] == "2.5 Üst" and total_goals <= 2:
            mk["p"] *= 0.82
        if mk["label"] == "KG Var" and not btts_hit:
            mk["p"] *= 0.82
        if mk["label"] == "KG Yok" and btts_hit:
            mk["p"] *= 0.82

        mk["p"] = clamp(mk["p"], 0.05, 0.88)
        mk["score"] = mk["p"] * 100 + max(0, mk.get("value", 0)) * 30

    best_market = max(markets, key=lambda x: x["score"]) if markets else None

    stable_markets = [
        x for x in markets
        if x["p"] >= 0.62 and x["odd"] and x["odd"] <= 1.85
    ]

    value_markets = [
        x for x in markets
        if x["p"] >= 0.50 and x["value"] >= 0.03 and x["odd"] and x["odd"] <= 2.40
    ]

    aggressive_markets = [
        x for x in markets
        if x["p"] >= 0.43 and x["odd"] and x["odd"] >= 1.70
    ]

    confidence = best_market["p"] if best_market else ana_p

    if confidence >= 0.68:
        risk = "Düşük"
        risk_cls = "good"
    elif confidence >= 0.57:
        risk = "Orta"
        risk_cls = "value"
    else:
        risk = "Yüksek"
        risk_cls = "risk"

    comment = generate_comment(m, best_market, profile, score_text, risk)

    return {
        "ana_label": ana_label,
        "ana_p": ana_p,
        "ana_odd": ana_odd,
        "score_text": score_text,
        "home_xg": profile["home_xg"],
        "away_xg": profile["away_xg"],
        "best_market": best_market,
        "markets": markets,
        "stable_markets": stable_markets,
        "value_markets": value_markets,
        "aggressive_markets": aggressive_markets,
        "risk": risk,
        "risk_cls": risk_cls,
        "confidence": confidence,
        "comment": comment,
        "profile": profile,
    }


def generate_comment(m, best_market, profile, score_text, risk):
    home = m.get("home_team")
    away = m.get("away_team")

    if not best_market:
        return "Bu maçta yeterince güçlü sinyal bulunamadı."

    label = best_market["label"]
    p = best_market["p"]

    if label in ["MS 1", "MS 2", "X"]:
        yön = home if label == "MS 1" else away if label == "MS 2" else "beraberlik"
        base = f"{yön} tarafı oran modelinde öne çıkıyor."
    elif "Üst" in label:
        base = "Gol temposu üst senaryoya yakın görünüyor."
    elif "Alt" in label:
        base = "Maç profili kontrollü ve düşük skorlu senaryoya daha yakın."
    elif "KG Var" in label:
        base = "İki takımın da skor üretme ihtimali modelde öne çıkıyor."
    else:
        base = "Takımlardan birinin skor bulamama ihtimali daha güçlü görünüyor."

    return (
        f"{base} Ana AI senaryo: {label}. "
        f"Tahmini skor: {score_text}. "
        f"Güven: %{round(p*100)}. Risk: {risk}. "
        f"Canlıda ilk 15 dakikada tempo bu senaryoyu destekliyorsa değer artabilir."
    )


# =========================
# ODDS API
# =========================

@st.cache_data(ttl=300)
def fetch_odds(api_key, sport_key):
    url = f"{API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h,totals,btts",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }

    r = requests.get(url, params=params, timeout=20)

    if r.status_code != 200:
        raise Exception(f"{sport_key}: {r.status_code} - {r.text}")

    return r.json()


def load_matches(api_key, selected_leagues, start_dt, end_dt):
    all_matches = []
    errors = []

    for league_name in selected_leagues:
        sport_key = DEFAULT_LEAGUES.get(league_name)
        if not sport_key:
            continue

        try:
            events = fetch_odds(api_key, sport_key)
        except Exception as e:
            errors.append(str(e))
            continue

        for ev in events:
            commence = ev.get("commence_time")
            try:
                ev_dt = datetime.fromisoformat(commence.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue

            if not (start_dt <= ev_dt < end_dt):
                continue

            odds = get_bookmaker_markets(ev)

            if not odds.get("h") or not odds.get("a"):
                continue

            all_matches.append({
                "id": ev.get("id"),
                "league": league_name,
                "home_team": ev.get("home_team"),
                "away_team": ev.get("away_team"),
                "commence_time": commence,
                "time_text": parse_match_time(commence),
                **odds
            })

    return all_matches, errors


# =========================
# TOP 10 AI
# =========================

def top10_market_adaylari(t):
    adaylar = []

    for mk in t.get("markets", []):
        if not mk:
            continue

        label = mk.get("label")
        p = mk.get("p", 0)
        odd = mk.get("odd")
        val = mk.get("value", 0)

        if not label or not odd:
            continue

        # Kararlı çekirdek
        if p >= 0.62 and odd <= 1.85:
            cls = "Kararlı Çekirdek"
            score = p * 100 + 8

        # Karlı value
        elif p >= 0.50 and val >= 0.03 and odd <= 2.40:
            cls = "Karlı Value"
            score = p * 100 + val * 45

        # Oynanabilir
        elif p >= 0.55 and odd <= 2.10:
            cls = "Oynanabilir"
            score = p * 100

        else:
            continue

        adaylar.append({
            "label": label,
            "p": p,
            "odd": odd,
            "value": val,
            "class": cls,
            "score": score,
        })

    return sorted(adaylar, key=lambda x: x["score"], reverse=True)


def gunun_en_iyi_10_uret(matches, limit=10):
    havuz = []

    for m in matches:
        try:
            t = ai_analyze_match(m)
        except Exception:
            continue

        adaylar = top10_market_adaylari(t)

        for ad in adaylar:
            havuz.append({
                "m": m,
                "t": t,
                "market": ad,
                "rank_score": ad["score"] + t["confidence"] * 10,
            })

    havuz = sorted(havuz, key=lambda x: x["rank_score"], reverse=True)

    secilen = []
    used = set()
    market_count = {}

    for item in havuz:
        m = item["m"]
        market = item["market"]

        key = mac_key(m) + "_" + market["label"]
        match_only = mac_key(m)

        if key in used:
            continue

        # Aynı maçtan en fazla 1 market
        if any(mac_key(x["m"]) == match_only for x in secilen):
            continue

        # Market çeşitliliği
        label_type = market["label"]
        market_count[label_type] = market_count.get(label_type, 0)

        if market_count[label_type] >= 4:
            continue

        secilen.append(item)
        used.add(key)
        market_count[label_type] += 1

        if len(secilen) >= limit:
            break

    return secilen


# =========================
# COUPON ENGINE
# =========================

def build_coupon(matches, mode="safe"):
    pool = []

    for m in matches:
        try:
            t = ai_analyze_match(m)
        except Exception:
            continue

        if mode == "safe":
            candidates = t["stable_markets"]
            max_odd = 1.75
            min_p = 0.62
            target_total = 3.0
        elif mode == "value":
            candidates = t["value_markets"]
            max_odd = 2.10
            min_p = 0.52
            target_total = 5.8
        else:
            candidates = t["aggressive_markets"]
            max_odd = 2.80
            min_p = 0.45
            target_total = 9.0

        for c in candidates:
            if c["odd"] and c["odd"] <= max_odd and c["p"] >= min_p:
                pool.append({
                    "m": m,
                    "t": t,
                    "market": c,
                    "score": c["p"] * 100 + max(0, c.get("value", 0)) * 35,
                })

    pool = sorted(pool, key=lambda x: x["score"], reverse=True)

    coupon = []
    total_odd = 1.0
    used_matches = set()

    for item in pool:
        mkey = mac_key(item["m"])
        if mkey in used_matches:
            continue

        odd = item["market"]["odd"]
        if not odd:
            continue

        if total_odd * odd > target_total and len(coupon) >= 2:
            continue

        coupon.append(item)
        used_matches.add(mkey)
        total_odd *= odd

        if mode == "safe" and len(coupon) >= 3:
            break
        if mode == "value" and len(coupon) >= 4:
            break
        if mode == "aggressive" and len(coupon) >= 5:
            break

    return coupon, total_odd


# =========================
# UI
# =========================

st.markdown('<p class="big-title">Vibe Analiz AI</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Kararlı çekirdek + karlı value + otomatik AI kupon sistemi</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 API Ayarları")

    api_key = st.text_input(
        "The Odds API Key",
        value=os.getenv("ODDS_API_KEY", ""),
        type="password"
    )

    st.divider()

    st.header("📅 Tarih")
    date_opt = st.selectbox(
        "Maç günü",
        ["Bugün", "Yarın", "2 Gün Sonra", "3 Gün Sonra", "Özel Tarih"]
    )

    custom_day = None
    if date_opt == "Özel Tarih":
        custom_day = st.date_input("Tarih seç", value=date.today())

    start_dt, end_dt = date_option_to_range(date_opt, custom_day)

    st.divider()

    st.header("🏆 Ligler")
    selected_leagues = st.multiselect(
        "Lig seç",
        list(DEFAULT_LEAGUES.keys()),
        default=[
            "Premier League",
            "La Liga",
            "Bundesliga",
            "Serie A",
            "Ligue 1",
            "Süper Lig"
        ]
    )

    st.divider()

    load_btn = st.button("🚀 Maçları Yükle", use_container_width=True)

st.markdown("""
<div class="main-card">
<b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler, geçmiş veri karşılaştırmaları ve yapay zekâ destekli tahminler sunar. 
Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir ve maddi kayıplara yol açabilir.
</div>
""", unsafe_allow_html=True)

if "matches" not in st.session_state:
    st.session_state.matches = []

if load_btn:
    if not api_key:
        st.error("API key girmelisin.")
    elif not selected_leagues:
        st.error("En az 1 lig seçmelisin.")
    else:
        with st.spinner("Maçlar yükleniyor..."):
            matches, errors = load_matches(api_key, selected_leagues, start_dt, end_dt)
            st.session_state.matches = matches

        if errors:
            with st.expander("API uyarıları"):
                for e in errors:
                    st.warning(e)

        if matches:
            st.success(f"{len(matches)} maç bulundu.")
        else:
            st.warning("Seçili tarih ve liglerde maç bulunamadı.")

matches = st.session_state.matches

if not matches:
    st.info("Sol menüden API key girip maçları yükle.")
    st.stop()

# =========================
# TABS
# =========================

tab1, tab2, tab3 = st.tabs([
    "🔥 AI Top 10",
    "📋 Tüm Maçlar",
    "🎟️ AI Kuponlar"
])

# =========================
# TAB 1
# =========================

with tab1:
    st.subheader("🔥 Günün En İyi 10 Oynanabilir Seçimi")

    top10 = gunun_en_iyi_10_uret(matches, limit=10)

    if not top10:
        st.warning("Top 10 için yeterli güçlü sinyal bulunamadı.")
    else:
        for i, item in enumerate(top10, 1):
            m = item["m"]
            t = item["t"]
            mk = item["market"]

            cls = "good" if mk["class"] == "Kararlı Çekirdek" else "value"

            st.markdown(f"""
            <div class="main-card">
                <h3>#{i} {m['home_team']} - {m['away_team']}</h3>
                <p class="gray">{m['league']} • {m['time_text']}</p>
                <span class="metric-pill {cls}">{mk['class']}</span>
                <span class="metric-pill">Tahmin: <b>{mk['label']}</b></span>
                <span class="metric-pill">Oran: <b>{fmt_odd(mk['odd'])}</b></span>
                <span class="metric-pill">Güven: <b>{fmt_pct(mk['p'])}</b></span>
                <span class="metric-pill">Skor: <b>{t['score_text']}</b></span>
                <hr>
                <p>{t['comment']}</p>
            </div>
            """, unsafe_allow_html=True)

# =========================
# TAB 2
# =========================

with tab2:
    st.subheader("📋 Anlık Maç Tahminleri")

    analyzed = []

    for m in matches:
        try:
            t = ai_analyze_match(m)
            analyzed.append((m, t))
        except Exception:
            continue

    analyzed = sorted(analyzed, key=lambda x: x[1]["confidence"], reverse=True)

    for m, t in analyzed:
        best = t["best_market"]

        best_label = best["label"] if best else "-"
        best_odd = best["odd"] if best else None
        best_p = best["p"] if best else 0

        st.markdown(f"""
        <div class="main-card">
            <h3>{m['home_team']} - {m['away_team']}</h3>
            <p class="gray">{m['league']} • {m['time_text']}</p>

            <span class="metric-pill">Ana Tahmin: <b>{best_label}</b></span>
            <span class="metric-pill">Oran: <b>{fmt_odd(best_odd)}</b></span>
            <span class="metric-pill">Güven: <b>{fmt_pct(best_p)}</b></span>
            <span class="metric-pill {t['risk_cls']}">Risk: <b>{t['risk']}</b></span>
            <span class="metric-pill">Tahmini Skor: <b>{t['score_text']}</b></span>

            <hr>
            <p><b>Yorum:</b> {t['comment']}</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Detaylı market analizi"):
            rows = []

            for mk in sorted(t["markets"], key=lambda x: x["score"], reverse=True):
                rows.append({
                    "Market": mk["label"],
                    "Oran": fmt_odd(mk["odd"]),
                    "AI Güven": fmt_pct(mk["p"]),
                    "Value": round(mk.get("value", 0), 3),
                    "Tip": mk.get("type", "-"),
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True)

# =========================
# TAB 3
# =========================

with tab3:
    st.subheader("🎟️ Otomatik AI Kuponlar")

    c1, c2, c3 = st.columns(3)

    modes = [
        ("safe", "🛡️ Güvenli Yol"),
        ("value", "💰 Oynanabilir Value Yol"),
        ("aggressive", "🔥 Agresif Yol"),
    ]

    for col, (mode, title) in zip([c1, c2, c3], modes):
        with col:
            coupon, total_odd = build_coupon(matches, mode=mode)

            st.markdown(f"""
            <div class="main-card">
                <h3>{title}</h3>
                <span class="metric-pill">Toplam Oran: <b>{fmt_odd(total_odd)}</b></span>
            </div>
            """, unsafe_allow_html=True)

            if not coupon:
                st.warning("Uygun kupon bulunamadı.")
                continue

            for item in coupon:
                m = item["m"]
                mk = item["market"]
                t = item["t"]

                st.markdown(f"""
                <div class="main-card">
                    <b>{m['home_team']} - {m['away_team']}</b><br>
                    <span class="gray">{m['league']} • {m['time_text']}</span><br><br>
                    <span class="metric-pill">Tahmin: <b>{mk['label']}</b></span>
                    <span class="metric-pill">Oran: <b>{fmt_odd(mk['odd'])}</b></span>
                    <span class="metric-pill">Güven: <b>{fmt_pct(mk['p'])}</b></span>
                    <span class="metric-pill">Skor: <b>{t['score_text']}</b></span>
                </div>
                """, unsafe_allow_html=True)
