"""
Adım 4: İnteraktif F1 Pitwall Web Uygulaması (app.py - Streamlit)

Çalıştırmak için terminalde:
    streamlit run app.py
"""

import io
from pathlib import Path
import streamlit as st

from src.data_loader import (
    get_season_events,
    get_preset_drivers_for_year,
    load_f1_session,
    extract_driver_fastest_lap,
    resolve_driver_colors,
)
from src.telemetry_analyzer import (
    align_telemetry_by_distance,
    compute_track_dominance,
    analyze_corners,
    compute_summary_metrics,
)
from src.plotter import create_pitwall_dashboard_figure

# Sayfa yapılandırması
st.set_page_config(
    page_title="F1 Pitwall | Telemetri & Pist Dominasyon Analizi",
    page_icon="🏎️",
    layout="wide",
)

# Özel Koyu Tema CSS İyileştirmeleri
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    div[data-testid="stMetric"] {
        background-color: #131722;
        border: 1px solid #262B3D;
        padding: 12px 16px;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_season_events(year: int):
    return get_season_events(year)


@st.cache_data(show_spinner=False)
def cached_load_session(year: int, gp: str, session_type: str):
    return load_f1_session(year, gp, session_type)


def main():
    st.title("🏎️ F1 Pitwall: Telemetri, Sürüş ve Pist Dominasyon Analizi")
    st.caption(
        "İki F1 pilotunun en hızlı turlarını **OpenF1 API** üzerinden çekip **Mesafe (Metre)** ekseninde hizalayarak "
        "Hız, Gaz, Fren, Vites, Delta Zaman (Δt) ve Pist Dominasyon Haritası üzerinden karşılaştırır."
    )

    # --- SOL MENÜ (SIDEBAR): SEANS VE PİLOT SEÇİMİ ---
    with st.sidebar:
        st.header("⚙️ Seans & Pilot Seçimi")

        year = st.selectbox("Sezon Yılı", options=[2026, 2025, 2024, 2023], index=1)

        events = cached_season_events(year)

        default_gp_idx = 0
        for idx, name in enumerate(events):
            if "Belgium" in name or "Monaco" in name:
                default_gp_idx = idx
                break

        grand_prix = st.selectbox("Grand Prix (Pist)", options=events, index=default_gp_idx)

        session_map = {
            "Sıralama Turları (Qualifying - Q)": "Q",
            "Yarış (Race - R)": "R",
        }
        session_label = st.selectbox("Seans Tipi", options=list(session_map.keys()), index=0)
        session_type = session_map[session_label]

        drivers_list = get_preset_drivers_for_year(year, grand_prix, session_type)
        driver_codes = [d["code"] for d in drivers_list]
        driver_labels = {
            d["code"]: f"{d['code']} — {d['name']} ({d['team']})" for d in drivers_list
        }

        driver1 = st.selectbox(
            "1. Pilot (Referans)",
            options=driver_codes,
            index=0,
            format_func=lambda x: driver_labels.get(x, x),
        )
        driver2 = st.selectbox(
            "2. Pilot (Karşılaştırılan)",
            options=driver_codes,
            index=2 if len(driver_codes) > 2 else 1,
            format_func=lambda x: driver_labels.get(x, x),
        )

        num_sectors = st.slider(
            "Pist Dominasyon Mini-Sektör Sayısı",
            min_value=15,
            max_value=40,
            value=25,
            step=5,
            help="Pisti kaç eşit parçaya bölerek hız üstünlüğünü hesaplayacağını belirler.",
        )

        run_btn = st.button(
            "🚀 Telemetri Analizini Başlat",
            type="primary",
            use_container_width=True,
        )

        st.markdown("---")
        st.caption(
            "⚡ **OpenF1 Motoru Aktif:** Sadece seçtiğiniz 2 pilotun en hızlı turunu indirdiği için "
            "**Sıralama (Q) da seçseniz Yarış (R) da seçseniz ~3-5 saniye içinde** ekrana gelir!"
        )
        st.markdown(
            "👨‍💻 **Geliştirici:** [Utku Mert Geçgel](https://github.com/utkumertgecgel)"
        )

    if driver1 == driver2:
        st.warning("Lütfen karşılaştırma yapmak için iki farklı pilot seçin.")
        return

    if "last_analysis" not in st.session_state:
        st.session_state["last_analysis"] = None

    # Butona basıldığında veriyi indir ve analizi çalıştır
    if run_btn:
        with st.spinner(
            f"📡 {year} {grand_prix} ({session_type}) — {driver1} vs {driver2} en hızlı tur telemetrisi "
            f"OpenF1 sunucularından çekiliyor (~3-5 sn)..."
        ):
            try:
                session = cached_load_session(year, grand_prix, session_type)
                lap1_data = extract_driver_fastest_lap(session, driver1)
                lap2_data = extract_driver_fastest_lap(session, driver2)
                color1, color2 = resolve_driver_colors(
                    session, driver1, lap1_data["team"], driver2, lap2_data["team"]
                )

                aligned_df = align_telemetry_by_distance(lap1_data, lap2_data)
                dominance_data = compute_track_dominance(
                    aligned_df, num_minisectors=num_sectors, rotation_deg=0.0
                )
                corner_table, corners_df = analyze_corners(
                    session, aligned_df, driver1, driver2, rotation_deg=0.0
                )
                summary = compute_summary_metrics(
                    lap1_data, lap2_data, aligned_df, dominance_data
                )

                fig = create_pitwall_dashboard_figure(
                    event_name=session["event_name"],
                    year=year,
                    session_name=session["session_name"],
                    lap1_data=lap1_data,
                    lap2_data=lap2_data,
                    aligned_df=aligned_df,
                    dominance_data=dominance_data,
                    corners_df=corners_df,
                    summary_metrics=summary,
                    color1=color1,
                    color2=color2,
                )

                buf = io.BytesIO()
                fig.savefig(
                    buf, format="png", dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor()
                )
                buf.seek(0)

                st.session_state["last_analysis"] = {
                    "year": year,
                    "grand_prix": grand_prix,
                    "event_name": session["event_name"],
                    "driver1": driver1,
                    "driver2": driver2,
                    "lap1_data": lap1_data,
                    "lap2_data": lap2_data,
                    "summary": summary,
                    "num_sectors": num_sectors,
                    "corner_table": corner_table,
                    "png_bytes": buf.getvalue(),
                }
            except Exception as e:
                st.error(f"Telemetri analizi sırasında bir hata oluştu: {e}")
                return

    # Eğer henüz butona basılmadıysa hazır örnek posteri göster
    if st.session_state["last_analysis"] is None:
        st.info(
            "👈 Sol menüden **Yıl, Pist, Seans ve 2 Pilot** seçip **'🚀 Telemetri Analizini Başlat'** "
            "butonuna basın. Aşağıda örnek Pitwall çıktısını görebilirsiniz:"
        )
        sample_img = Path(__file__).resolve().parent / "assets" / "sample_telemetry_poster.png"
        if sample_img.exists():
            st.image(str(sample_img), use_container_width=True)
        return

    res = st.session_state["last_analysis"]
    lap1_data = res["lap1_data"]
    lap2_data = res["lap2_data"]
    summary = res["summary"]
    d1 = res["driver1"]
    d2 = res["driver2"]

    # --- ÜST ÖZET KARTLARI (KPI METRICS) ---
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(
            label=f"🥇 {d1} ({lap1_data['team']})",
            value=lap1_data["lap_time_str"],
            delta=f"Max: {summary['top_speed_1']} km/s | {lap1_data['compound']}",
        )
    with col2:
        st.metric(
            label=f"🏁 {d2} ({lap2_data['team']})",
            value=lap2_data["lap_time_str"],
            delta=f"Max: {summary['top_speed_2']} km/s | {lap2_data['compound']}",
        )
    with col3:
        st.metric(
            label="⏱️ Tur Zamanı Farkı (Δt)",
            value=summary["abs_gap_str"],
            delta=f"{summary['faster_driver']} Daha Hızlı",
        )
    with col4:
        st.metric(
            label="🗺️ Pist Dominasyonu",
            value=f"{d1} %{summary['d1_dominance_pct']}",
            delta=f"{d2}: %{summary['d2_dominance_pct']} ({res['num_sectors']} Sektör)",
        )
    with col5:
        st.metric(
            label="🚀 Tam Gaz Oranı (% Tur)",
            value=f"%{summary['full_throttle_pct_1']} vs %{summary['full_throttle_pct_2']}",
            delta=f"Fren: %{summary['braking_pct_1']} vs %{summary['braking_pct_2']}",
        )

    # --- SEKMELER (TABS) ---
    tab_dashboard, tab_corners, tab_guide = st.tabs(
        [
            "📊 Pitwall Telemetri & Pist Haritası Panosu",
            "🏁 Viraj Bazlı Hız Analizi (T1-Tn)",
            "📘 Mühendislik Rehberi (Nasıl Okunur?)",
        ]
    )

    with tab_dashboard:
        dl_col1, dl_col2 = st.columns([3, 1])
        with dl_col1:
            st.subheader(
                f"{res['year']} {res['event_name']} — {d1} vs {d2} Mühendislik Panosu"
            )
        with dl_col2:
            st.download_button(
                label="📥 Yüksek Çözünürlüklü Poster İndir (.PNG)",
                data=res["png_bytes"],
                file_name=f"F1_{res['year']}_{res['grand_prix'].replace(' ', '_')}_{d1}_vs_{d2}.png",
                mime="image/png",
                use_container_width=True,
            )

        st.image(res["png_bytes"], use_container_width=True)

    with tab_corners:
        st.subheader("Viraj Bazlı Minimum Geçiş Hızı (Apex Speed) ve Delta Zaman Tablosu")
        st.markdown(
            "Pistin her virajının merkezinde (**±35m** penceresinde) hangi pilotun viraj içine daha fazla "
            "hız taşıdığını ve o viraj itibarıyla toplam saniye farkını gösterir."
        )
        if not res["corner_table"].empty:
            st.dataframe(res["corner_table"], use_container_width=True, hide_index=True)
        else:
            st.info("Bu pist için viraj verisi bulunamadı.")

    with tab_guide:
        st.markdown(
            """
            ### 🧠 Bu Telemetri Panosu Nasıl Okunur?
            1. **Pist Dominasyon Haritası (Üst Sol - Proje 3):**
               * Pist 25 eşit mini-sektöre bölünür. Her parçada ortalama hızı daha yüksek olan pilotun takım rengi boyanır.
               * Bir pilotun düzlüklerde mi yoksa yavaş/teknik virajlarda mı üstün olduğunu tek bakışta gösterir.
            2. **Pist Hız Haritası (Üst Sağ - Proje 3):**
               * Tur boyunca aracın ulaştığı en yüksek hız noktalarını (sarı) ve en sert frenleme/yavaş viraj bölgelerini (mor/kırmızı) gösterir.
            3. **Delta Zaman `Δt` (1. Grafik - Proje 1):**
               * `0.00` kesikli çizgisinin üstü **1. Pilotun**, altı ise **2. Pilotun** önde olduğu bölgeleri gösterir.
               * Çizginin dikleştiği yerler, bir pilotun diğerine göre **en çok zaman kazandığı viraj veya düzlüktür**.
            4. **Hız, Gaz (%) ve Fren (%) Kanalları (2, 3 ve 4. Grafikler - Proje 1):**
               * **Geç Frenleme (Late Braking):** Fren grafiğinde çizgisi daha sağda (daha ileri metrede) yükselen pilot viraja daha geç fren yaparak girmiştir.
               * **Erken Gaz (Early Traction):** Viraj çıkışında Gaz (%) çizgisi `%100`'e daha erken ulaşan pilot virajdan daha iyi çekişle çıkmıştır.
            """
        )


if __name__ == "__main__":
    main()
