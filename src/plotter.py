"""
Adım 3: Pitwall Görselleştirme Motoru (plotter.py)

Bu modül Proje 1 (Telemetri Karşılaştırması) ve Proje 3 (Pist Haritası & Hız Analizi)
çıktılarını tek bir yüksek çözünürlüklü "F1 Pitwall" mühendislik panosunda birleştirir:
- Üst Sol Panel: Pist Dominasyon Haritası (Track Dominance - Hangi sektörde kim hızlı?)
- Üst Sağ Panel: Pist Hız Isı Haritası (Track Speed Heatmap - En hızlı düzlükler ve yavaş virajlar)
- Alt 4 Kanal (Mesafe Bazlı):
  1. Delta Zaman (Δt - Saniye farkı)
  2. Hız (Speed - km/s) + Viraj Numaraları (T1, T2...)
  3. Gaz Pedalı (Throttle - %)
  4. Fren (Brake - %) ve Vites (Gear - 1..8)
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.gridspec as gridspec

# Koyu Pitwall Tema Renkleri
BG_COLOR = "#0B0E14"
PANEL_COLOR = "#131722"
GRID_COLOR = "#262B3D"
TEXT_COLOR = "#ECEFF4"
SUBTEXT_COLOR = "#9AA5B1"


def _draw_track_dominance_panel(
    ax: plt.Axes,
    dom_df: pd.DataFrame,
    corners_df: Optional[pd.DataFrame],
    driver1: str,
    driver2: str,
    color1: str,
    color2: str,
    d1_pct: float,
    d2_pct: float,
):
    """Üst Sol Panel: 25 mini-sektörlü Pist Dominasyon Haritası (Proje 1 + 3)."""
    ax.set_facecolor(PANEL_COLOR)
    x = dom_df["X_rot"].to_numpy()
    y = dom_df["Y_rot"].to_numpy()
    faster = dom_df["FasterDriver"].to_numpy()

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    # Arka plan pist asfalt çerçevesi
    bg_lc = LineCollection(
        segments, colors="#2A3042", linewidths=9.0, capstyle="round", joinstyle="round"
    )
    ax.add_collection(bg_lc)

    # Pilot renklerine göre dominasyon çizgisi
    cmap = ListedColormap([color1, color2])
    norm = BoundaryNorm([0.5, 1.5, 2.5], cmap.N)
    dom_lc = LineCollection(
        segments, cmap=cmap, norm=norm, linewidths=5.2, capstyle="round", joinstyle="round"
    )
    dom_lc.set_array(faster[:-1])
    ax.add_collection(dom_lc)

    # Başlangıç/Bitiş çizgisi noktası
    ax.scatter(
        x[0],
        y[0],
        color="#FFFFFF",
        s=70,
        zorder=6,
        edgecolors="#000000",
        linewidths=1.5,
        label="Start/Finish",
    )

    # Viraj numaralarını (T1, T2...) harita üzerine yerleştir
    if corners_df is not None and not corners_df.empty:
        for _, crow in corners_df.iterrows():
            cx, cy = float(crow["X_rot"]), float(crow["Y_rot"])
            ax.scatter(
                cx, cy, color="#1E2433", s=110, zorder=5, edgecolors="#8892B0", linewidths=1.0
            )
            ax.text(
                cx,
                cy,
                str(crow["TurnLabel"]).replace("T", ""),
                color="#FFFFFF",
                fontsize=6.5,
                fontweight="bold",
                ha="center",
                va="center",
                zorder=6,
            )

    ax.set_aspect("equal", "datalim")
    ax.axis("off")

    ax.set_title(
        f"PİST DOMİNASYON HARİTASI ({driver1}: %{d1_pct} vs {driver2}: %{d2_pct})",
        color=TEXT_COLOR,
        fontsize=11,
        fontweight="bold",
        pad=10,
    )

    # Renk lejantı
    ax.plot([], [], color=color1, linewidth=5, label=f"{driver1} Daha Hızlı (%{d1_pct})")
    ax.plot([], [], color=color2, linewidth=5, label=f"{driver2} Daha Hızlı (%{d2_pct})")
    leg = ax.legend(
        loc="lower left",
        frameon=True,
        facecolor="#1A202C",
        edgecolor=GRID_COLOR,
        fontsize=8.5,
        labelcolor=TEXT_COLOR,
    )
    leg.get_frame().set_alpha(0.9)


def _draw_speed_heatmap_panel(
    ax: plt.Axes,
    fig: plt.Figure,
    dom_df: pd.DataFrame,
    corners_df: Optional[pd.DataFrame],
    driver1: str,
):
    """Üst Sağ Panel: Pist Hız Isı Haritası (Proje 3 - Hızlı Düzlükler & Yavaş Virajlar)."""
    ax.set_facecolor(PANEL_COLOR)
    x = dom_df["X_rot"].to_numpy()
    y = dom_df["Y_rot"].to_numpy()
    speed = dom_df["Speed_1"].to_numpy()

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    # Asfalt dış çizgisi
    bg_lc = LineCollection(
        segments, colors="#2A3042", linewidths=9.0, capstyle="round", joinstyle="round"
    )
    ax.add_collection(bg_lc)

    # Hız renk geçişi (Plasma: Mor=Yavaş Viraj, Sarı=Hızlı Düzlük)
    norm = plt.Normalize(float(np.min(speed)), float(np.max(speed)))
    speed_lc = LineCollection(
        segments, cmap="plasma", norm=norm, linewidths=5.2, capstyle="round", joinstyle="round"
    )
    speed_lc.set_array(speed[:-1])
    ax.add_collection(speed_lc)

    # En yüksek ve en düşük hız noktalarını işaretle
    max_idx = int(np.argmax(speed))
    min_idx = int(np.argmin(speed))
    ax.scatter(x[max_idx], y[max_idx], color="#FFE600", s=65, zorder=6, edgecolors="#000000")
    ax.annotate(
        f"Max: {speed[max_idx]:.0f} km/s",
        (x[max_idx], y[max_idx]),
        textcoords="offset points",
        xytext=(8, 8),
        color="#FFE600",
        fontsize=7.5,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", fc="#0B0E14", ec="#FFE600", alpha=0.85),
    )

    ax.scatter(x[min_idx], y[min_idx], color="#FF4B4B", s=65, zorder=6, edgecolors="#000000")
    ax.annotate(
        f"Min: {speed[min_idx]:.0f} km/s",
        (x[min_idx], y[min_idx]),
        textcoords="offset points",
        xytext=(8, -12),
        color="#FF8585",
        fontsize=7.5,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.2", fc="#0B0E14", ec="#FF4B4B", alpha=0.85),
    )

    ax.set_aspect("equal", "datalim")
    ax.axis("off")
    ax.set_title(
        f"PİST HIZ HARİTASI ({driver1} Referans Turu - km/s)",
        color=TEXT_COLOR,
        fontsize=11,
        fontweight="bold",
        pad=10,
    )

    cbar = fig.colorbar(speed_lc, ax=ax, orientation="horizontal", fraction=0.046, pad=0.02)
    cbar.set_label(
        "Hız (km/s)  [Mor: Yavaş Virajlar  →  Sarı: Hızlı Düzlükler]",
        color=SUBTEXT_COLOR,
        fontsize=8,
    )
    cbar.ax.xaxis.set_tick_params(color=SUBTEXT_COLOR, labelcolor=SUBTEXT_COLOR, labelsize=8)
    cbar.outline.set_edgecolor(GRID_COLOR)


def create_pitwall_dashboard_figure(
    event_name: str,
    year: int,
    session_name: str,
    lap1_data: Dict[str, Any],
    lap2_data: Dict[str, Any],
    aligned_df: pd.DataFrame,
    dominance_data: Dict[str, Any],
    corners_df: Optional[pd.DataFrame],
    summary_metrics: Dict[str, Any],
    color1: str,
    color2: str,
) -> plt.Figure:
    """
    Proje 1 ve Proje 3'ü tek bir profesyonel F1 Mühendislik Panosunda (Poster) çizer.
    Hem Streamlit arayüzünde doğrudan gösterilir hem de yüksek çözünürlüklü PNG olarak indirilebilir.
    """
    driver1 = lap1_data["driver"]
    driver2 = lap2_data["driver"]
    dom_df = dominance_data["df"]

    fig = plt.figure(figsize=(18, 15), dpi=150, facecolor=BG_COLOR)
    gs = gridspec.GridSpec(
        nrows=5,
        ncols=2,
        figure=fig,
        height_ratios=[2.3, 1.0, 1.5, 1.0, 1.0],
        hspace=0.22,
        wspace=0.12,
    )

    # --- ANA BAŞLIK & ÖZET BİLGİ ŞERİDİ ---
    faster_drv = summary_metrics["faster_driver"]
    gap_str = summary_metrics["abs_gap_str"]
    fig.suptitle(
        f"{year} {event_name.upper()} — {session_name.upper()} TELEMETRİ & PİST ANALİZİ",
        color=TEXT_COLOR,
        fontsize=16,
        fontweight="bold",
        y=0.975,
    )
    subtitle_text = (
        f"{driver1} ({lap1_data['team']}): {lap1_data['lap_time_str']} [{lap1_data['compound']}]   |   "
        f"{driver2} ({lap2_data['team']}): {lap2_data['lap_time_str']} [{lap2_data['compound']}]   |   "
        f"Fark: {faster_drv} -{gap_str} daha hızlı"
    )
    fig.text(
        0.5,
        0.945,
        subtitle_text,
        color=SUBTEXT_COLOR,
        fontsize=11,
        ha="center",
        fontweight="semibold",
    )

    # --- 1. SATIR: PİST DOMİNASYON HARİTASI (SOL) & PİST HIZ HARİTASI (SAĞ) ---
    ax_dom = fig.add_subplot(gs[0, 0])
    _draw_track_dominance_panel(
        ax=ax_dom,
        dom_df=dom_df,
        corners_df=corners_df,
        driver1=driver1,
        driver2=driver2,
        color1=color1,
        color2=color2,
        d1_pct=dominance_data["d1_dominance_pct"],
        d2_pct=dominance_data["d2_dominance_pct"],
    )

    ax_spd_map = fig.add_subplot(gs[0, 1])
    _draw_speed_heatmap_panel(
        ax=ax_spd_map,
        fig=fig,
        dom_df=dom_df,
        corners_df=corners_df,
        driver1=driver1,
    )

    # --- ALT SATIRLAR: MESAFE BAZLI TELEMETRİ KANALLARI ---
    dist = aligned_df["Distance"].to_numpy()
    max_dist = float(dist.max())

    ax_delta = fig.add_subplot(gs[1, :])
    ax_speed = fig.add_subplot(gs[2, :], sharex=ax_delta)
    ax_throttle = fig.add_subplot(gs[3, :], sharex=ax_delta)
    ax_brake = fig.add_subplot(gs[4, :], sharex=ax_delta)

    telemetry_axes = [ax_delta, ax_speed, ax_throttle, ax_brake]
    for ax in telemetry_axes:
        ax.set_facecolor(PANEL_COLOR)
        ax.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.6, alpha=0.7)
        ax.set_xlim(0, max_dist)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)
        ax.tick_params(colors=SUBTEXT_COLOR, labelsize=8.5)

        # Viraj kılavuz çizgileri
        if corners_df is not None and not corners_df.empty:
            for _, crow in corners_df.iterrows():
                cdist = float(crow["Distance"])
                if 0 <= cdist <= max_dist:
                    ax.axvline(cdist, color="#3B4252", linestyle=":", linewidth=0.8, alpha=0.65)

    # KANAL 1: DELTA ZAMAN (Δt)
    delta = aligned_df["DeltaTime"].to_numpy()
    ax_delta.axhline(0, color="#FFFFFF", linestyle="--", linewidth=1.0, alpha=0.8)
    ax_delta.plot(dist, delta, color="#ECEFF4", linewidth=1.8, label="Delta Zaman (sn)")
    ax_delta.fill_between(
        dist,
        0,
        delta,
        where=(delta >= 0),
        interpolate=True,
        color=color1,
        alpha=0.35,
        label=f"{driver1} Önde",
    )
    ax_delta.fill_between(
        dist,
        0,
        delta,
        where=(delta < 0),
        interpolate=True,
        color=color2,
        alpha=0.35,
        label=f"{driver2} Önde",
    )
    ax_delta.set_ylabel(
        "Δ Zaman (sn)\n[+ : " + driver1 + " Önde]",
        color=TEXT_COLOR,
        fontsize=9,
        fontweight="bold",
    )
    ax_delta.legend(
        loc="upper left",
        ncol=3,
        frameon=True,
        facecolor="#1A202C",
        edgecolor=GRID_COLOR,
        fontsize=8,
        labelcolor=TEXT_COLOR,
    )

    # KANAL 2: HIZ (SPEED km/s) + VİRAJ ETİKETLERİ
    ax_speed.plot(
        dist,
        aligned_df["Speed_1"],
        color=color1,
        linewidth=2.0,
        label=f"{driver1} ({lap1_data['lap_time_str']})",
    )
    ax_speed.plot(
        dist,
        aligned_df["Speed_2"],
        color=color2,
        linewidth=2.0,
        linestyle="-",
        alpha=0.9,
        label=f"{driver2} ({lap2_data['lap_time_str']})",
    )
    ax_speed.set_ylabel("Hız (km/s)", color=TEXT_COLOR, fontsize=9.5, fontweight="bold")
    ax_speed.legend(
        loc="lower left",
        ncol=2,
        frameon=True,
        facecolor="#1A202C",
        edgecolor=GRID_COLOR,
        fontsize=8.5,
        labelcolor=TEXT_COLOR,
    )

    # Viraj isimlerini Hız grafiğinin üst kısmına yaz
    if corners_df is not None and not corners_df.empty:
        y_top = float(max(aligned_df["Speed_1"].max(), aligned_df["Speed_2"].max())) + 14
        ax_speed.set_ylim(top=y_top + 10)
        for _, crow in corners_df.iterrows():
            cdist = float(crow["Distance"])
            if 0 <= cdist <= max_dist:
                ax_speed.text(
                    cdist,
                    y_top,
                    str(crow["TurnLabel"]),
                    color="#D8DEE9",
                    fontsize=7.5,
                    fontweight="bold",
                    ha="center",
                    va="bottom",
                    bbox=dict(boxstyle="round,pad=0.15", fc="#1E2433", ec="#4C566A", lw=0.6),
                )

    # KANAL 3: GAZ PEDALI (THROTTLE %)
    ax_throttle.plot(
        dist, aligned_df["Throttle_1"], color=color1, linewidth=1.7, label=f"{driver1} Gaz %"
    )
    ax_throttle.plot(
        dist,
        aligned_df["Throttle_2"],
        color=color2,
        linewidth=1.7,
        alpha=0.85,
        label=f"{driver2} Gaz %",
    )
    ax_throttle.set_ylim(-5, 105)
    ax_throttle.set_ylabel("Gaz (%)", color=TEXT_COLOR, fontsize=9.5, fontweight="bold")

    # KANAL 4: FREN (%) & VİTES (GEAR)
    ax_brake.plot(dist, aligned_df["Brake_1"], color=color1, linewidth=1.6, label=f"{driver1} Fren %")
    ax_brake.plot(
        dist, aligned_df["Brake_2"], color=color2, linewidth=1.6, alpha=0.85, label=f"{driver2} Fren %"
    )
    ax_brake.set_ylim(-5, 108)
    ax_brake.set_ylabel("Fren (%)", color=TEXT_COLOR, fontsize=9.5, fontweight="bold")
    ax_brake.set_xlabel(
        "Pist Mesafesi (Metre) — [0m: Başlangıç  →  Bitiş Çizgisi]",
        color=TEXT_COLOR,
        fontsize=10,
        fontweight="bold",
    )

    # Sağ Y ekseninde Vites (Gear) gösterimi
    ax_gear = ax_brake.twinx()
    ax_gear.step(
        dist, aligned_df["Gear_1"], color=color1, linestyle=":", linewidth=1.1, alpha=0.6, where="mid"
    )
    ax_gear.step(
        dist, aligned_df["Gear_2"], color=color2, linestyle=":", linewidth=1.1, alpha=0.6, where="mid"
    )
    ax_gear.set_ylim(0, 9)
    ax_gear.set_yticks([1, 2, 3, 4, 5, 6, 7, 8])
    ax_gear.set_ylabel("Vites (1-8)", color=SUBTEXT_COLOR, fontsize=8.5)
    ax_gear.tick_params(colors=SUBTEXT_COLOR, labelsize=8)
    for spine in ax_gear.spines.values():
        spine.set_visible(False)

    # Üstteki 3 telemetri grafiğinin X ekseni sayılarını gizle (en alttakinde görünüyor)
    plt.setp(ax_delta.get_xticklabels(), visible=False)
    plt.setp(ax_speed.get_xticklabels(), visible=False)
    plt.setp(ax_throttle.get_xticklabels(), visible=False)

    # Alt bilgi / Geliştirici İmza & Telif Feragatnamesi (Watermark & Disclaimer)
    fig.text(
        0.5,
        0.01,
        "Developed by Utku Mert Geçgel (github.com/utkumertgecgel)  •  Veri Kaynağı: OpenF1 API  •  Unofficial F1 Engineering Portfolio Project — Not affiliated with Formula 1 companies.",
        color="#8892B0",
        fontsize=8.5,
        fontweight="semibold",
        ha="center",
    )

    fig.subplots_adjust(top=0.91, bottom=0.05, left=0.06, right=0.95)
    return fig
