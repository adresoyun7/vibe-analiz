```python
import io
import math
from datetime import datetime, timedelta
from html import escape

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="VIBE PRO EXPERT",
    layout="wide",
    page_icon="⚡"
)

# ==========================================================
# API KEY ACCESS SYSTEM
# ==========================================================

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
        st.markdown("## 🔑 API KEY")

        current_key = st.session_state.get("user_api_key", "")

        api_key_input = st.text_input(
            "ODDS API KEY",
            value=current_key,
            type="password",
            placeholder="API key gir...",
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Kaydet", use_container_width=True):
                st.session_state["user_api_key"] = api_key_input.strip()
                st.success("Kaydedildi ✅")
                st.rerun()

        with c2:
            if st.button("Temizle", use_container_width=True):
                st.session_state.pop("user_api_key", None)
                st.success("Temizlendi")
                st.rerun()

        if get_app_api_key():
            st.success("API aktif ✅")
        else:
            st.warning("API key gerekli")


def require_api_key():
    if not get_app_api_key():
        st.warning("Sol menüden API KEY gir.")
        st.stop()


# ==========================================================
# FUTBOL LİGLERİ + KUPALAR
# ==========================================================

FUTBOL_LIGLERI = {
    "AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league",
    },

    "TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
        "Türkiye Kupası": "soccer_turkey_cup",
    },

    "İNGİLTERE": {
        "Premier League": "soccer_epl",
        "Championship": "soccer_efl_champ",
        "League One": "soccer_england_league1",
        "League Two": "soccer_england_league2",
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
        "DFB Pokal": "soccer_germany_dfb_pokal",
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

    "VALUE LİGLER": {
        "Hollanda": "soccer_netherlands_eredivisie",
        "Belçika": "soccer_belgium_first_div",
        "Portekiz": "soccer_portugal_primeira_liga",
        "İskoçya": "soccer_spl",
        "Danimarka": "soccer_denmark_superliga",
        "İsviçre": "soccer_switzerland_superleague",
        "Avusturya": "soccer_austria_bundesliga",
        "Norveç": "soccer_norway_eliteserien",
        "İsveç": "soccer_sweden_allsvenskan",
    }
}

# ==========================================================
# API'DEN MAÇ ÇEK
# ==========================================================

@st.cache_data(ttl=1800)
def bulten_cek(api_key, kodlar, tarih):

    sonuc = []

    for lig_kodu in kodlar:

        try:
            url = f"https://api.the-odds-api.com/v4/sports/{lig_kodu}/odds/"

            r = requests.get(
                url,
                params={
                    "apiKey": api_key,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=15,
            )

            if r.status_code != 200:
                continue

            data = r.json()

            if not isinstance(data, list):
                continue

            for mac in data:

                try:
                    zaman = datetime.strptime(
                        mac["commence_time"],
                        "%Y-%m-%dT%H:%M:%SZ"
                    ) + timedelta(hours=3)

                except Exception:
                    continue

                if zaman.date() != tarih:
                    continue

                bookmakers = mac.get("bookmakers", [])

                if not bookmakers:
                    continue

                market = None

                for bk in bookmakers:
                    for mk in bk.get("markets", []):

                        if mk.get("key") == "h2h":
                            market = mk
                            break

                    if market:
                        break

                if not market:
                    continue

                outcomes = market.get("outcomes", [])

                home = mac.get("home_team", "")
                away = ""

                for team in mac.get("teams", []):
                    if team != home:
                        away = team
                        break

                h = next(
                    (
                        x["price"]
                        for x in outcomes
                        if x["name"] == home
                    ),
                    None
                )

                a = next(
                    (
                        x["price"]
                        for x in outcomes
                        if x["name"] == away
                    ),
                    None
                )

                d = next(
                    (
                        x["price"]
                        for x in outcomes
                        if str(x["name"]).lower() in [
                            "draw",
                            "tie",
                            "beraberlik"
                        ]
                    ),
                    None
                )

                if h is None or a is None or d is None:
                    continue

                sonuc.append({
                    "lig": mac.get("sport_title", lig_kodu),
                    "zaman": zaman,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "d": float(d),
                    "a": float(a),
                })

        except Exception:
            continue

    if not sonuc:
        return pd.DataFrame()

    return pd.DataFrame(sonuc).sort_values("zaman")


# ==========================================================
# UI
# ==========================================================

st.title("⚡ VIBE PRO EXPERT")

api_key_panel()
require_api_key()

st.sidebar.markdown("---")
st.sidebar.markdown("## 📅 Bülten Tarihi")

secili_tarih = st.sidebar.date_input(
    "Tarih",
    value=datetime.now().date()
)

st.sidebar.markdown("---")
st.sidebar.markdown("## 🏆 Lig / Kupa Seç")

secili_kodlar = []

for kategori, ligler in FUTBOL_LIGLERI.items():

    with st.sidebar.expander(kategori, expanded=False):

        for lig_adi, lig_kodu in ligler.items():

            secildi = st.checkbox(
                lig_adi,
                value=True,
                key=lig_kodu
            )

            if secildi:
                secili_kodlar.append(lig_kodu)

if st.button("🚀 BÜLTENİ GETİR", use_container_width=True):

    with st.spinner("Maçlar çekiliyor..."):

        df = bulten_cek(
            get_app_api_key(),
            secili_kodlar,
            secili_tarih
        )

    if df.empty:
        st.error("Maç bulunamadı.")
    else:
        st.success(f"{len(df)} maç bulundu ✅")

        for _, row in df.iterrows():

            st.markdown("---")

            col1, col2, col3 = st.columns([2, 3, 2])

            with col1:
                st.markdown(f"### ⏰ {row['zaman'].strftime('%H:%M')}")

            with col2:
                st.markdown(f"## {row['ev']} vs {row['dep']}")
                st.caption(row["lig"])

            with col3:
                st.markdown(
                    f"""
                    **MS1:** {row['h']:.2f}

                    **X:** {row['d']:.2f}

                    **MS2:** {row['a']:.2f}
                    """
                )
```
