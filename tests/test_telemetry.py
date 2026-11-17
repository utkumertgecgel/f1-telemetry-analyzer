"""
Otomatik Mühendislik Birim Testleri (tests/test_telemetry.py)

Çalıştırmak için terminalde:
    pytest -v
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.data_loader import format_laptime, resolve_driver_colors
from src.telemetry_analyzer import (
    rotate_coordinates,
    align_telemetry_by_distance,
    compute_track_dominance,
    analyze_corners,
    compute_summary_metrics,
)
from src.plotter import create_pitwall_dashboard_figure


def _create_mock_lap_data(driver: str, team: str, lap_sec: float, speed_offset: float = 0.0):
    """Testler için deterministik F1 tur ve sensör verisi üretir."""
    n = 600
    dist = np.linspace(0.0, 5000.0, n)
    theta = np.linspace(0.0, 2.0 * np.pi, n)
    x = 1000.0 * np.cos(theta)
    y = 800.0 * np.sin(theta)

    # 3 belirgin viraj (1000m, 2500m, 4000m) içeren hız profili
    speed = np.full(n, 300.0 + speed_offset)
    for c_dist in (1000.0, 2500.0, 4000.0):
        speed -= 160.0 * np.exp(-0.5 * ((dist - c_dist) / 70.0) ** 2)
    speed = np.clip(speed, 80.0, 340.0)

    t_arr = np.linspace(0.0, lap_sec, n)
    throttle = np.where(speed > 220.0, 100.0, 45.0)
    brake = np.where(np.gradient(speed) < -0.2, 100.0, 0.0)
    gear = np.clip((speed // 42).astype(int) + 1, 1, 8)

    tel = pd.DataFrame(
        {
            "Time": pd.to_timedelta(t_arr, unit="s"),
            "Distance": dist,
            "Speed": speed,
            "Throttle": throttle,
            "Brake": brake,
            "nGear": gear,
            "RPM": speed * 35.0,
            "X": x,
            "Y": y,
        }
    )

    lap_td = pd.Timedelta(seconds=lap_sec)
    return {
        "driver": driver,
        "team": team,
        "lap_time": lap_td,
        "lap_time_str": format_laptime(lap_td),
        "compound": "Tur 12",
        "lap_number": 12,
        "telemetry": tel,
    }


def test_rotate_coordinates_math():
    """2 boyutlu rotasyon matrisinin 0 ve 90 derece dönüşlerini doğrular."""
    x = np.array([10.0, 0.0])
    y = np.array([0.0, 10.0])

    x0, y0 = rotate_coordinates(x, y, 0.0)
    np.testing.assert_allclose(x0, x, atol=1e-6)
    np.testing.assert_allclose(y0, y, atol=1e-6)

    x90, y90 = rotate_coordinates(x, y, 90.0)
    np.testing.assert_allclose(x90, np.array([0.0, -10.0]), atol=1e-6)
    np.testing.assert_allclose(y90, np.array([10.0, 0.0]), atol=1e-6)


def test_format_laptime_precision():
    """Tur süresi formatlayıcısının dakika:saniye.milisaniye çıktısını doğrular."""
    td = pd.Timedelta(seconds=70.270)
    assert format_laptime(td) == "1:10.270"
    assert format_laptime(pd.NaT) == "N/A"


def test_resolve_driver_colors_teammate_contrast():
    """Aynı takımdan iki pilot seçildiğinde renk çakışmasının önlendiğini doğrular."""
    mock_session = {
        "drivers_map": {
            "LEC": {"color": "#E80020"},
            "HAM": {"color": "#E80020"},
            "VER": {"color": "#3671C6"},
        }
    }
    # Farklı takımlar kendi renklerini korumalı
    c1, c2 = resolve_driver_colors(mock_session, "LEC", "Ferrari", "VER", "Red Bull Racing")
    assert c1 == "#E80020"
    assert c2 == "#3671C6"

    # Takım arkadaşları (LEC vs HAM) farklı kontrast renkler almalı
    tc1, tc2 = resolve_driver_colors(mock_session, "LEC", "Ferrari", "HAM", "Ferrari")
    assert tc1 == "#E80020"
    assert tc2 == "#FFD700"
    assert tc1 != tc2


def test_align_telemetry_by_distance_and_delta_calibration():
    """
    Mesafe bazlı lineer interpolasyonun 1500 ortak nokta ürettiğini ve
    bitiş çizgisindeki DeltaTime değerinin resmi tur farkıyla birebir örtüştüğünü doğrular.
    """
    lap1 = _create_mock_lap_data("VER", "Red Bull Racing", lap_sec=75.100, speed_offset=3.0)
    lap2 = _create_mock_lap_data("LEC", "Ferrari", lap_sec=75.450, speed_offset=0.0)

    aligned = align_telemetry_by_distance(lap1, lap2, num_points=1500)

    assert len(aligned) == 1500
    assert aligned["Distance"].iloc[0] == 0.0
    assert np.isclose(aligned["Distance"].iloc[-1], 5000.0)

    # Bitiş çizgisindeki kümülatif DeltaTime resmi farka (75.450 - 75.100 = +0.350 sn) eşit olmalı
    expected_gap = 75.450 - 75.100
    assert np.isclose(aligned["DeltaTime"].iloc[-1], expected_gap, atol=1e-4)


def test_compute_track_dominance_sectors():
    """Pist dominasyon yüzdelerinin toplamının %100 olduğunu ve hızlı pilotu doğru bulduğunu doğrular."""
    lap1 = _create_mock_lap_data("VER", "Red Bull Racing", lap_sec=74.800, speed_offset=5.0)
    lap2 = _create_mock_lap_data("NOR", "McLaren", lap_sec=75.200, speed_offset=0.0)

    aligned = align_telemetry_by_distance(lap1, lap2)
    dom = compute_track_dominance(aligned, num_minisectors=25, rotation_deg=15.0)

    assert dom["num_minisectors"] == 25
    assert dom["d1_sectors"] + dom["d2_sectors"] == 25
    assert np.isclose(dom["d1_dominance_pct"] + dom["d2_dominance_pct"], 100.0)
    assert dom["d1_dominance_pct"] == 100.0


def test_analyze_corners_apex_detection():
    """Sinyal işleme (find_peaks) algoritmasının pistteki 3 virajı doğru tespit ettiğini doğrular."""
    lap1 = _create_mock_lap_data("VER", "Red Bull Racing", lap_sec=75.0, speed_offset=4.0)
    lap2 = _create_mock_lap_data("LEC", "Ferrari", lap_sec=75.3, speed_offset=0.0)

    aligned = align_telemetry_by_distance(lap1, lap2)
    corner_table, corners_df = analyze_corners({}, aligned, "VER", "LEC")

    assert corners_df is not None
    assert len(corners_df) == 3
    assert list(corner_table["Viraj"]) == ["T1", "T2", "T3"]
    assert all(corner_table["Virajda Hızlı Pilot"] == "VER")


def test_pitwall_dashboard_figure_creation():
    """6 panelli Matplotlib Pitwall figürünün hatasız oluşturulduğunu doğrular."""
    lap1 = _create_mock_lap_data("VER", "Red Bull Racing", lap_sec=75.0, speed_offset=2.0)
    lap2 = _create_mock_lap_data("LEC", "Ferrari", lap_sec=75.2, speed_offset=0.0)

    aligned = align_telemetry_by_distance(lap1, lap2)
    dom = compute_track_dominance(aligned, num_minisectors=25)
    _, corners_df = analyze_corners({}, aligned, "VER", "LEC")
    summary = compute_summary_metrics(lap1, lap2, aligned, dom)

    fig = create_pitwall_dashboard_figure(
        event_name="Belgium Grand Prix (Spa-Francorchamps)",
        year=2024,
        session_name="Qualifying",
        lap1_data=lap1,
        lap2_data=lap2,
        aligned_df=aligned,
        dominance_data=dom,
        corners_df=corners_df,
        summary_metrics=summary,
        color1="#3671C6",
        color2="#E80020",
    )

    assert fig is not None
    assert len(fig.axes) >= 6
    plt.close(fig)
