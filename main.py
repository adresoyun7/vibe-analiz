                                }}
                                .st-key-{kart_key} .stButton > button {{
                                    min-height: 42px;
                                    margin: 0;
                                }}
                                </style>
                                """,
                                unsafe_allow_html=True,
                            )

                            with st.container(key=kart_key, border=False):
                                bilgi_col, detay_col, ekle_col = st.columns([6.4, 2.3, 1.3], gap="small")

                                with bilgi_col:
                                    st.markdown(
                                        f"""
                                        <div style="color:#f8fafc;padding:2px 0">
                                          <b style="font-size:.94rem">
                                            {escape(str(secim.get('ev', '')))} – {escape(str(secim.get('dep', '')))}
                                          </b>
                                          <div style="font-size:.80rem;color:#dbeafe;margin-top:5px">
                                            {escape(str(secim.get('tahmin', '-')))} · Güven %{int(secim.get('guven', 0))}
                                          </div>
                                          {_kupon_market_html}
                                          {hassasiyet_alt}
                                          {baglam_alt}
                                        </div>
                                        """,
                                        unsafe_allow_html=True,
                                    )

                                with detay_col:
                                    if st.button(
                                        "Detay",
                                        key=f"auto_coupon_detail_{kayit.get('kupon_id')}_{secim_no}",
                                        use_container_width=True,
                                    ):
                                        detay_item = kupon_seciminden_detay_itemi(
                                            secim, sadece_ayni_lig=sadece_ayni_lig
                                        )
                                        if detay_item is None:
                                            st.warning("Bu kupon kaydı için detay verisi yeniden oluşturulamadı.")
                                        else:
                                            st.session_state.detay_item = detay_item
                                            st.session_state.detay_idx = None
                                            st.rerun()

                                with ekle_col:
                                    if st.button(
                                        "＋",
                                        key=f"auto_to_manual_{kayit.get('kupon_id')}_{secim_no}",
                                        use_container_width=True,
                                        help="Kendi Kuponuma ekle",
                                    ):
                                        secim_m = {
                                            "ev": secim.get("ev", ""),
                                            "dep": secim.get("dep", ""),
                                            "lig": secim.get("lig", ""),
                                            "sport_key": secim.get("sport_key", ""),
                                            "h": secim.get("h"),
                                            "b": secim.get("b"),
                                            "a": secim.get("a"),
                                            "zaman": parse_mac_datetime(secim.get("zaman_iso", "")),
                                        }
                                        manuel_kupona_ekle(
                                            secim_m, {}, secim.get("tahmin", "-"), secim.get("guven", 0),
                                            oran=secim.get("oran"),
                                            oran_tahmini=bool(secim.get("oran_tahmini", False)),
                                        )
                                        st.rerun()

                        kart_col, sil_col = st.columns([8, 2])
                        with kart_col:
                            st.markdown("<div style='height:1px'></div>", unsafe_allow_html=True)
                        with sil_col:
                            if st.button("🗑️", key=f"auto_coupon_delete_{kayit.get('kupon_id')}", use_container_width=True):
                                yeni_gecmis = [x for x in kupon_gecmisi if x.get("kupon_id") != kayit.get("kupon_id")]
                                kupon_gecmisini_yaz(yeni_gecmis)
                                st.rerun()

            with profil_sutunlari[4]:
                st.markdown(
                    """
                    <div style="background:#312e81;border:1px solid #a78bfa;border-radius:12px;
                                padding:10px 12px;margin-bottom:10px;text-align:center;
                                color:#f8fafc;-webkit-text-fill-color:#f8fafc;font-size:1rem;
                                font-weight:900;opacity:1">
                        🟣 Kendi Kuponum
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if not st.session_state.kupona:
                    st.info("Henüz manuel seçim eklenmedi.")
                for del_i, item in enumerate(list(st.session_state.kupona)):
                    mac_dt = parse_mac_datetime(item.get("zaman_iso", ""))
                    durum = mac_canli_durumu(mac_dt) if item.get("zaman_iso") else "Takipte"
                    mac_ad = f"{item.get('ev', '')} – {item.get('dep', '')}".strip(" –")
                    kart_col, sil_col = st.columns([8, 2])
                    with kart_col:
                        st.markdown(
                            f"""
                            <div style="background:#1e1b4b;border:1px solid #7c3aed;border-radius:13px;
                                        padding:11px 12px;margin-bottom:8px;color:#f8fafc">
                              <b style="color:#c4b5fd">{escape(mac_ad)}</b>
                              <div style="font-size:.79rem;color:#e2e8f0;margin-top:5px">
                                {escape(str(item.get('tahmin','-')))} · Güven %{int(item.get('guven',0))}<br>
                                {escape(durum)}
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with sil_col:
                        if st.button("🗑️", key=f"coupon_delete_{del_i}", use_container_width=True):
                            st.session_state.kupona.pop(del_i)
                            st.rerun()
                if st.session_state.kupona and st.button(
                    "Kendi kuponumu temizle", key="coupon_clear_inside_panel", use_container_width=True
                ):
                    st.session_state.kupona = []
                    st.rerun()

        if not st.session_state.kupona and not kupon_gecmisi:
            st.info("Henüz kupon kaydı yok. Maç kartlarından seçim ekleyebilir veya Günün Kuponunu Oluştur bölümünü kullanabilirsin.")

        if st.button("Kapat", key="coupon_close_inside_panel", use_container_width=True):
            st.session_state.coupon_popup_open = False
            st.rerun()

legal_footer()
