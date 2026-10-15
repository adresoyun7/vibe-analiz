    for grup in parcalar:
        hedef = min(range(adet), key=lambda j: (len(sonuc[j]), j))
        sonuc[hedef].extend(grup)
    return [[secim for _, secim in sorted(grup, key=lambda item: item[0])] for grup in sonuc]


def fix45_oran_hesapla(secimler):
    toplam = 1.0
    for secim in secimler:
        try:
            oran = float(secim.get('oran'))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(oran) or oran <= 1:
            return None
        toplam *= oran
    return toplam


# FIX44 — Her sekmede görünen sağ-alt sabit, açılır/kapanır kupon çekmecesi.
# st.popover, Streamlit widget'larını ana uygulama oturumuyla paylaşır.
def sabit_kupon_cekmecesi():
    st.markdown("""
    <style>
    .st-key-fix44_floating_coupon {
        position: fixed !important;
        right: 18px !important;
        bottom: 18px !important;
        z-index: 999990 !important;
        width: min(245px, calc(100vw - 28px)) !important;
        background: #303b42 !important;
        border: 1px solid #52616b !important;
        border-radius: 10px !important;
        padding: 6px !important;
        box-shadow: 0 8px 30px rgba(0,0,0,.38) !important;
    }
    .st-key-fix44_floating_coupon [data-testid="stPopover"] > button {
        width: 100% !important;
        background: #303b42 !important;
        color: #fff !important;
        border: 0 !important;
        font-weight: 700 !important;
        justify-content: space-between !important;
    }
    @media(max-width: 640px) {
        .st-key-fix44_floating_coupon { right: 9px !important; bottom: 9px !important; }
    }
    </style>
    """, unsafe_allow_html=True)
    with st.container(key="fix44_floating_coupon"):
        secimler = [x for x in st.session_state.get("kupona", []) if isinstance(x, dict)]
        toplam = 1.0
        eksik = 0
        for secim in secimler:
            try:
                oran = float(secim.get("oran"))
                if math.isfinite(oran) and oran > 1:
                    toplam *= oran
                else:
                    eksik += 1
            except (ValueError, TypeError):
                eksik += 1
        oran_text = f"{toplam:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if secimler and not eksik else "—"
        with st.popover(f"🎫 Kuponum · {len(secimler)} maç · {oran_text}", use_container_width=True):
            st.markdown("**Kuponum**")
            st.caption(f"{len(secimler)} maç · Toplam oran: {oran_text}" + (" · Eksik oran var" if eksik else ""))
            if not secimler:
                st.info("Henüz kupona maç eklenmedi.")
            for index, secim in enumerate(list(secimler)):
                a, b = st.columns([5, 1], gap="small")
                with a:
                    st.markdown(f"**{escape(str(secim.get('ev','')))} – {escape(str(secim.get('dep','')))}**")
                    st.caption(f"{escape(str(secim.get('tahmin','-')))} · {escape(str(secim.get('zaman_text','')))} · {secim.get('oran') or 'Oran yok'}")
                with b:
                    if st.button("✕", key=f"fix44_remove_{index}", help="Kupondan çıkar"):
                        # Liste başka bir bölümce değiştirilmiş olsa bile aynı kaydı hedefle.
                        current = st.session_state.get("kupona", [])
                        if secim in current:
                            current.remove(secim)
                        st.rerun()
            if len(secimler) >= 2:
                st.divider()
                st.markdown("**✂️ Kuponu Böl**")
                st.caption("Maçları ayrı kuponlara dağıtır; aynı maç farklı kuponlara kopyalanmaz. Oranlar yalnızca mevcut oranlardan hesaplanır.")
                bolum_adedi = st.selectbox(
                    "Kaç kupon oluşturulsun?", options=list(range(2, min(4, len(secimler)) + 1)),
                    index=0, key="fix45_split_count"
                )
                if st.button("Kuponları oluştur", key="fix45_split_button", use_container_width=True):
                    bolunmus = fix45_kuponlari_bol(secimler, bolum_adedi)
                    if bolunmus is None:
                        st.warning("Aynı maça ait seçimler birlikte tutulduğundan bu sayıda kupon oluşturulamıyor.")
                    else:
                        st.session_state["fix45_split_result"] = bolunmus
                        st.session_state["fix45_split_signature"] = repr(secimler)
                        st.rerun()
                bolunmus = st.session_state.get("fix45_split_result")
                if bolunmus and st.session_state.get("fix45_split_signature") == repr(secimler):
                    st.caption("Önizleme: Ana kupon değiştirilmedi. Bunlar ayrı kuponlardır, tek bir kombine kupon değildir.")
                    for no, grup in enumerate(bolunmus, 1):
                        oran = fix45_oran_hesapla(grup)
                        oran_yazi = f"{oran:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") if oran is not None else "Eksik oran"
                        with st.expander(f"Kupon {no} · {len(grup)} maç · {oran_yazi}", expanded=False):
                            for secim in grup:
                                st.markdown(f"• {escape(str(secim.get('ev','')))} – {escape(str(secim.get('dep','')))}: {escape(str(secim.get('tahmin','-')))}")
                elif bolunmus:
                    st.session_state.pop("fix45_split_result", None)
                    st.session_state.pop("fix45_split_signature", None)
            if secimler and st.button("Kuponu temizle", key="fix44_clear", use_container_width=True):
                st.session_state.kupona = []
                st.rerun()


sabit_kupon_cekmecesi()

legal_footer()
