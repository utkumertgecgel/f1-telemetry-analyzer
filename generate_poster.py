"""
Komut Satırından (CLI) Yüksek Çözünürlüklü F1 Pitwall Poster Üretici (generate_poster.py)

Kullanım Örneği:
    python generate_poster.py --year 2024 --gp "Belgium" --session Q --d1 VER --d2 LEC
"""

import argparse
from pathlib import Path
from src.data_loader import (
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


def generate_analysis_poster(
    year: int = 2024,
    grand_prix: str = "Belgium",
    session_type: str = "Q",
    driver1: str = "VER",
    driver2: str = "LEC",
    output_path: str = "assets/sample_telemetry_poster.png",
) -> Path:
    print(f"[1/4] {year} {grand_prix} ({session_type}) seans bilgisi OpenF1'den yükleniyor...")
    session = load_f1_session(year, grand_prix, session_type)

    print(f"[2/4] {driver1} ve {driver2} en hızlı turları ve sensör verileri çekiliyor...")
    lap1_data = extract_driver_fastest_lap(session, driver1)
    lap2_data = extract_driver_fastest_lap(session, driver2)

    color1, color2 = resolve_driver_colors(
        session, driver1, lap1_data["team"], driver2, lap2_data["team"]
    )

    print("[3/4] Mesafe bazlı interpolasyon, Delta Zaman (Δt) ve Pist Dominasyonu hesaplanıyor...")
    aligned_df = align_telemetry_by_distance(lap1_data, lap2_data)
    dominance_data = compute_track_dominance(
        aligned_df, num_minisectors=25, rotation_deg=0.0
    )
    corner_table, corners_df = analyze_corners(
        session, aligned_df, driver1, driver2, rotation_deg=0.0
    )
    summary_metrics = compute_summary_metrics(lap1_data, lap2_data, aligned_df, dominance_data)

    print("[4/4] Pitwall Mühendislik Panosu çiziliyor ve kaydediliyor...")
    fig = create_pitwall_dashboard_figure(
        event_name=session["event_name"],
        year=year,
        session_name=session["session_name"],
        lap1_data=lap1_data,
        lap2_data=lap2_data,
        aligned_df=aligned_df,
        dominance_data=dominance_data,
        corners_df=corners_df,
        summary_metrics=summary_metrics,
        color1=color1,
        color2=color2,
    )

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Başarıyla kaydedildi: {out_file.resolve()}")
    return out_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 Telemetri ve Pist Dominasyon Poster Üretici")
    parser.add_argument("--year", type=int, default=2024, help="Sezon yılı (Örn: 2024)")
    parser.add_argument(
        "--gp", type=str, default="Belgium", help="Grand Prix adı (Örn: Belgium, Monaco, Italy)"
    )
    parser.add_argument(
        "--session", type=str, default="Q", help="Seans tipi: Q (Sıralama) veya R (Yarış)"
    )
    parser.add_argument("--d1", type=str, default="VER", help="1. Pilot Kodu (Örn: VER)")
    parser.add_argument("--d2", type=str, default="LEC", help="2. Pilot Kodu (Örn: LEC)")
    parser.add_argument(
        "--out",
        type=str,
        default="assets/sample_telemetry_poster.png",
        help="Çıktı dosya yolu",
    )
    args = parser.parse_args()

    generate_analysis_poster(
        year=args.year,
        grand_prix=args.gp,
        session_type=args.session,
        driver1=args.d1,
        driver2=args.d2,
        output_path=args.out,
    )
