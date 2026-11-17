"""
Adım 2: Telemetri Hizalama, Delta Zaman (Δt), Pist Dominasyonu ve Viraj Analizi (telemetry_analyzer.py)

Bu modül projenin matematiksel ve mühendislik çekirdeğidir:
1. İki pilotun farklı zamanlarda kaydettiği sensör verilerini "Mesafe (Metre)" ekseninde
   lineer interpolasyon (np.interp) ile milimetrik olarak hizalar.
2. Her metredeki kümülatif zaman farkını (Delta Time - Δt) hesaplar.
3. Pisti 25 mini-sektöre bölerek hangi sektörde hangi pilotun daha hızlı olduğunu (Track Dominance)
   ve pist üzerindeki hız dağılımını (Speed Map) çıkarır.
4. Sinyal işleme (scipy.signal.find_peaks) ile pistteki viraj merkezlerini (Apex - T1, T2...)
   otomatik tespit ederek her virajdaki minimum hızları karşılaştırır.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def rotate_coordinates(
    x: np.ndarray, y: np.ndarray, angle_deg: float
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Pist haritasının (X, Y) koordinatlarını döndürür (2 Boyutlu Rotasyon Matrisi).
    """
    angle_rad = np.deg2rad(angle_deg)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    x_rot = x * cos_a - y * sin_a
    y_rot = x * sin_a + y * cos_a
    return x_rot, y_rot


def align_telemetry_by_distance(
    lap1_data: Dict[str, Any],
    lap2_data: Dict[str, Any],
    num_points: int = 1500,
) -> pd.DataFrame:
    """
    İki pilotun telemetri verilerini ortak bir mesafe (Distance) ızgarasında hizalar.
    """
    tel1 = lap1_data["telemetry"].copy()
    tel2 = lap2_data["telemetry"].copy()

    max_dist1 = float(tel1["Distance"].max())
    max_dist2 = float(tel2["Distance"].max())
    track_length = max(max_dist1, 100.0)

    dist1 = tel1["Distance"].to_numpy(dtype=float)
    dist2 = tel2["Distance"].to_numpy(dtype=float) * (max_dist1 / max(max_dist2, 1.0))

    common_dist = np.linspace(0.0, track_length, num_points)

    t1_sec = tel1["Time"].dt.total_seconds().to_numpy(dtype=float)
    t2_sec = tel2["Time"].dt.total_seconds().to_numpy(dtype=float)

    t1_interp = np.interp(common_dist, dist1, t1_sec)
    t2_interp = np.interp(common_dist, dist2, t2_sec)

    # Delta Time (Δt): Pozitif (+) ise 1. pilot önde, Negatif (-) ise 2. pilot önde
    raw_delta = t2_interp - t1_interp
    official_gap = (lap2_data["lap_time"] - lap1_data["lap_time"]).total_seconds()
    end_drift = official_gap - raw_delta[-1]
    delta_time = raw_delta + (common_dist / track_length) * end_drift

    speed1 = np.interp(common_dist, dist1, tel1["Speed"].to_numpy(dtype=float))
    speed2 = np.interp(common_dist, dist2, tel2["Speed"].to_numpy(dtype=float))

    throttle1 = np.interp(common_dist, dist1, tel1["Throttle"].to_numpy(dtype=float))
    throttle2 = np.interp(common_dist, dist2, tel2["Throttle"].to_numpy(dtype=float))

    b1_raw = tel1["Brake"].astype(float).to_numpy()
    b2_raw = tel2["Brake"].astype(float).to_numpy()
    if b1_raw.max() <= 1.0:
        b1_raw = b1_raw * 100.0
    if b2_raw.max() <= 1.0:
        b2_raw = b2_raw * 100.0
    brake1 = np.interp(common_dist, dist1, b1_raw)
    brake2 = np.interp(common_dist, dist2, b2_raw)

    gear1 = np.round(np.interp(common_dist, dist1, tel1["nGear"].to_numpy(dtype=float))).astype(int)
    gear2 = np.round(np.interp(common_dist, dist2, tel2["nGear"].to_numpy(dtype=float))).astype(int)

    rpm1 = np.interp(common_dist, dist1, tel1["RPM"].to_numpy(dtype=float))
    rpm2 = np.interp(common_dist, dist2, tel2["RPM"].to_numpy(dtype=float))

    # Pist Haritası için X ve Y koordinatları:
    # 1. Pilotun GPS verisi varsa onu kullan; yoksa 2. Pilotun GPS verisini kullan;
    # Eğer her ikisinde de OpenF1 GPS kaydı yoksa hız profilinden kapalı pist geometrisi üret.
    x1_raw = tel1["X"].to_numpy(dtype=float)
    y1_raw = tel1["Y"].to_numpy(dtype=float)
    x2_raw = tel2["X"].to_numpy(dtype=float)
    y2_raw = tel2["Y"].to_numpy(dtype=float)

    if np.ptp(x1_raw) > 10.0 and np.ptp(y1_raw) > 10.0:
        x_coord = np.interp(common_dist, dist1, x1_raw)
        y_coord = np.interp(common_dist, dist1, y1_raw)
    elif np.ptp(x2_raw) > 10.0 and np.ptp(y2_raw) > 10.0:
        x_coord = np.interp(common_dist, dist2, x2_raw)
        y_coord = np.interp(common_dist, dist2, y2_raw)
    else:
        theta = np.linspace(0.0, 2.0 * np.pi, num_points)
        norm_spd = (speed1 - np.min(speed1)) / max(float(np.ptp(speed1)), 1.0)
        radius = 1000.0 + 320.0 * norm_spd + 180.0 * np.sin(3.0 * theta)
        x_coord = radius * np.cos(theta) * 1.35
        y_coord = radius * np.sin(theta) * 0.90

    aligned_df = pd.DataFrame(
        {
            "Distance": common_dist,
            "DeltaTime": delta_time,
            "Speed_1": speed1,
            "Speed_2": speed2,
            "SpeedDiff": speed1 - speed2,
            "Throttle_1": np.clip(throttle1, 0, 100),
            "Throttle_2": np.clip(throttle2, 0, 100),
            "Brake_1": np.clip(brake1, 0, 100),
            "Brake_2": np.clip(brake2, 0, 100),
            "Gear_1": gear1,
            "Gear_2": gear2,
            "RPM_1": rpm1,
            "RPM_2": rpm2,
            "X": x_coord,
            "Y": y_coord,
        }
    )
    return aligned_df


def compute_track_dominance(
    aligned_df: pd.DataFrame,
    num_minisectors: int = 25,
    rotation_deg: float = 0.0,
) -> Dict[str, Any]:
    """
    Pisti 'num_minisectors' (varsayılan 25) adet mini-sektöre böler ve her parçada
    hangi pilotun ortalama hızının daha yüksek olduğunu hesaplar.
    """
    df = aligned_df.copy()
    x_rot, y_rot = rotate_coordinates(df["X"].to_numpy(), df["Y"].to_numpy(), rotation_deg)
    df["X_rot"] = x_rot
    df["Y_rot"] = y_rot

    total_dist = df["Distance"].max()
    bins = np.linspace(0.0, total_dist, num_minisectors + 1)
    df["MiniSector"] = np.digitize(df["Distance"], bins) - 1
    df["MiniSector"] = df["MiniSector"].clip(0, num_minisectors - 1)

    sector_speeds = df.groupby("MiniSector")[["Speed_1", "Speed_2"]].mean()
    faster_map = (
        (sector_speeds["Speed_1"] >= sector_speeds["Speed_2"])
        .map(lambda is_d1: 1 if is_d1 else 2)
        .to_dict()
    )

    df["FasterDriver"] = df["MiniSector"].map(faster_map)

    d1_sectors = sum(1 for v in faster_map.values() if v == 1)
    d2_sectors = num_minisectors - d1_sectors
    d1_pct = round((d1_sectors / num_minisectors) * 100, 1)
    d2_pct = round(100.0 - d1_pct, 1)

    return {
        "df": df,
        "d1_sectors": d1_sectors,
        "d2_sectors": d2_sectors,
        "d1_dominance_pct": d1_pct,
        "d2_dominance_pct": d2_pct,
        "num_minisectors": num_minisectors,
    }


def analyze_corners(
    session: Any,
    aligned_df: pd.DataFrame,
    driver1: str,
    driver2: str,
    rotation_deg: float = 0.0,
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Hız profilindeki lokal minimum noktalarını (scipy.signal.find_peaks) kullanarak
    pistteki viraj merkezlerini (Apex - T1, T2...) otomatik tespit eder ve her virajda
    hangi pilotun daha yüksek hız taşıdığını tablo olarak çıkarır.
    """
    speed_arr = aligned_df["Speed_1"].to_numpy(dtype=float)
    dist_arr = aligned_df["Distance"].to_numpy(dtype=float)
    x_arr = aligned_df["X"].to_numpy(dtype=float)
    y_arr = aligned_df["Y"].to_numpy(dtype=float)
    x_rot, y_rot = rotate_coordinates(x_arr, y_arr, rotation_deg)

    # Hızın en az 20 km/s düştüğü viraj merkezlerini (Apex) tespit et
    peaks, _ = find_peaks(-speed_arr, distance=55, prominence=20.0)

    if len(peaks) == 0:
        return pd.DataFrame(), None

    corner_markers = []
    corner_rows = []

    for idx_num, p_idx in enumerate(peaks, start=1):
        c_dist = float(dist_arr[p_idx])
        label = f"T{idx_num}"

        corner_markers.append(
            {
                "TurnLabel": label,
                "Distance": c_dist,
                "X_rot": float(x_rot[p_idx]),
                "Y_rot": float(y_rot[p_idx]),
            }
        )

        window = aligned_df[
            (aligned_df["Distance"] >= c_dist - 35.0)
            & (aligned_df["Distance"] <= c_dist + 35.0)
        ]
        if window.empty:
            continue

        min_s1 = float(window["Speed_1"].min())
        min_s2 = float(window["Speed_2"].min())
        diff = min_s1 - min_s2
        faster = driver1 if diff >= 0 else driver2
        delta_at_corner = float(aligned_df.loc[p_idx, "DeltaTime"])

        corner_rows.append(
            {
                "Viraj": label,
                "Mesafe (m)": int(round(c_dist)),
                f"{driver1} Min Hız (km/s)": round(min_s1, 1),
                f"{driver2} Min Hız (km/s)": round(min_s2, 1),
                "Hız Farkı (km/s)": round(abs(diff), 1),
                "Virajda Hızlı Pilot": faster,
                "Kümülatif Delta (sn)": round(delta_at_corner, 3),
            }
        )

    corners_df = pd.DataFrame(corner_markers)
    corner_analysis_df = pd.DataFrame(corner_rows)
    return corner_analysis_df, corners_df


def compute_summary_metrics(
    lap1_data: Dict[str, Any],
    lap2_data: Dict[str, Any],
    aligned_df: pd.DataFrame,
    dominance_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Arayüzde ve posterde gösterilecek özet mühendislik istatistiklerini hesaplar."""
    gap_sec = (lap2_data["lap_time"] - lap1_data["lap_time"]).total_seconds()

    full_throttle_1 = float((aligned_df["Throttle_1"] >= 98.0).mean() * 100.0)
    full_throttle_2 = float((aligned_df["Throttle_2"] >= 98.0).mean() * 100.0)

    braking_pct_1 = float((aligned_df["Brake_1"] >= 10.0).mean() * 100.0)
    braking_pct_2 = float((aligned_df["Brake_2"] >= 10.0).mean() * 100.0)

    return {
        "gap_seconds": gap_sec,
        "faster_driver": lap1_data["driver"] if gap_sec >= 0 else lap2_data["driver"],
        "abs_gap_str": f"{abs(gap_sec):.3f}s",
        "top_speed_1": round(float(aligned_df["Speed_1"].max()), 1),
        "top_speed_2": round(float(aligned_df["Speed_2"].max()), 1),
        "avg_speed_1": round(float(aligned_df["Speed_1"].mean()), 1),
        "avg_speed_2": round(float(aligned_df["Speed_2"].mean()), 1),
        "full_throttle_pct_1": round(full_throttle_1, 1),
        "full_throttle_pct_2": round(full_throttle_2, 1),
        "braking_pct_1": round(braking_pct_1, 1),
        "braking_pct_2": round(braking_pct_2, 1),
        "d1_dominance_pct": dominance_data["d1_dominance_pct"],
        "d2_dominance_pct": dominance_data["d2_dominance_pct"],
    }
