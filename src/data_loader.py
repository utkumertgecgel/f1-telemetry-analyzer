"""
Adım 1: Veri Çekme ve Ön İşleme Modülü (data_loader.py)

NEDEN OPENF1 API KULLANIYORUZ?
Formula 1 yönetimi yakın zamanda resmi 'livetiming.formula1.com' sunucularına bulut duvarı (HTTP 401)
getirdiği için FastF1 kütüphanesi artık ücretli F1TV Pro aboneliği (F1_USERNAME / F1_PASSWORD) olmadan
telemetri verisi indirememektedir.

Bu modül, %100 ücretsiz, açık kaynaklı ve üyelik gerektirmeyen **OpenF1 API (api.openf1.org/v1)**
üzerinden 2023, 2024, 2025 ve 2026 sezonlarının tamamına erişir; doğrudan seçilen 2 pilotun en hızlı
turunun sensör (car_data) ve GPS konum (location) verilerini saniyeler içinde çeker ve yerel 'cache/'
klasörüne kaydeder.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
import pandas as pd
import requests

OPENF1_BASE_URL = "https://api.openf1.org/v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache" / "openf1"

# Takımların telifsiz, standart HEX renk kodları (Yedek / Fallback tablosu)
TEAM_COLORS_FALLBACK: Dict[str, str] = {
    "red bull": "#3671C6",
    "ferrari": "#E80020",
    "mercedes": "#27F4D2",
    "mclaren": "#FF8000",
    "aston martin": "#229971",
    "alpine": "#0093CC",
    "williams": "#64C4FF",
    "rb": "#6692FF",
    "racing bulls": "#6692FF",
    "alphatauri": "#5E8FAA",
    "kick sauber": "#52E252",
    "sauber": "#52E252",
    "audi": "#F50537",
    "cadillac": "#FFB81C",
    "alfa romeo": "#C92D4B",
    "haas": "#B6BABD",
}

# Sezonlara göre yedek pilot listesi (Canlı API bağlantısı yokken bile menünün çalışması için)
SEASON_DRIVERS: Dict[int, List[Tuple[str, str, str]]] = {
    2026: [
        ("VER", "Max Verstappen", "Red Bull Racing"),
        ("NOR", "Lando Norris", "McLaren"),
        ("LEC", "Charles Leclerc", "Ferrari"),
        ("HAM", "Lewis Hamilton", "Ferrari"),
        ("PIA", "Oscar Piastri", "McLaren"),
        ("RUS", "George Russell", "Mercedes"),
        ("ANT", "Kimi Antonelli", "Mercedes"),
        ("SAI", "Carlos Sainz", "Williams"),
        ("ALB", "Alexander Albon", "Williams"),
        ("ALO", "Fernando Alonso", "Aston Martin"),
        ("STR", "Lance Stroll", "Aston Martin"),
        ("GAS", "Pierre Gasly", "Alpine"),
        ("OCO", "Esteban Ocon", "Haas F1 Team"),
        ("BEA", "Oliver Bearman", "Haas F1 Team"),
        ("HUL", "Nico Hulkenberg", "Kick Sauber / Audi"),
        ("BOR", "Gabriel Bortoleto", "Kick Sauber / Audi"),
        ("TSU", "Yuki Tsunoda", "Racing Bulls"),
        ("LAW", "Liam Lawson", "Red Bull / Racing Bulls"),
        ("HAD", "Isack Hadjar", "Racing Bulls"),
    ],
    2025: [
        ("VER", "Max Verstappen", "Red Bull Racing"),
        ("NOR", "Lando Norris", "McLaren"),
        ("LEC", "Charles Leclerc", "Ferrari"),
        ("HAM", "Lewis Hamilton", "Ferrari"),
        ("PIA", "Oscar Piastri", "McLaren"),
        ("RUS", "George Russell", "Mercedes"),
        ("ANT", "Kimi Antonelli", "Mercedes"),
        ("SAI", "Carlos Sainz", "Williams"),
        ("ALB", "Alexander Albon", "Williams"),
        ("ALO", "Fernando Alonso", "Aston Martin"),
        ("STR", "Lance Stroll", "Aston Martin"),
        ("GAS", "Pierre Gasly", "Alpine"),
        ("DOO", "Jack Doohan", "Alpine"),
        ("COL", "Franco Colapinto", "Alpine"),
        ("OCO", "Esteban Ocon", "Haas F1 Team"),
        ("BEA", "Oliver Bearman", "Haas F1 Team"),
        ("HUL", "Nico Hulkenberg", "Kick Sauber"),
        ("BOR", "Gabriel Bortoleto", "Kick Sauber"),
        ("TSU", "Yuki Tsunoda", "Red Bull / Racing Bulls"),
        ("LAW", "Liam Lawson", "Red Bull / Racing Bulls"),
        ("HAD", "Isack Hadjar", "Racing Bulls"),
    ],
    2024: [
        ("VER", "Max Verstappen", "Red Bull Racing"),
        ("NOR", "Lando Norris", "McLaren"),
        ("LEC", "Charles Leclerc", "Ferrari"),
        ("PIA", "Oscar Piastri", "McLaren"),
        ("SAI", "Carlos Sainz", "Ferrari"),
        ("HAM", "Lewis Hamilton", "Mercedes"),
        ("RUS", "George Russell", "Mercedes"),
        ("PER", "Sergio Perez", "Red Bull Racing"),
        ("ALO", "Fernando Alonso", "Aston Martin"),
        ("GAS", "Pierre Gasly", "Alpine"),
        ("HUL", "Nico Hulkenberg", "Haas F1 Team"),
        ("TSU", "Yuki Tsunoda", "RB"),
        ("STR", "Lance Stroll", "Aston Martin"),
        ("OCO", "Esteban Ocon", "Alpine"),
        ("ALB", "Alexander Albon", "Williams"),
        ("COL", "Franco Colapinto", "Williams"),
        ("LAW", "Liam Lawson", "RB"),
        ("BEA", "Oliver Bearman", "Ferrari / Haas"),
        ("MAG", "Kevin Magnussen", "Haas F1 Team"),
        ("BOT", "Valtteri Bottas", "Kick Sauber"),
        ("ZHO", "Guanyu Zhou", "Kick Sauber"),
    ],
    2023: [
        ("VER", "Max Verstappen", "Red Bull Racing"),
        ("PER", "Sergio Perez", "Red Bull Racing"),
        ("HAM", "Lewis Hamilton", "Mercedes"),
        ("ALO", "Fernando Alonso", "Aston Martin"),
        ("LEC", "Charles Leclerc", "Ferrari"),
        ("NOR", "Lando Norris", "McLaren"),
        ("SAI", "Carlos Sainz", "Ferrari"),
        ("RUS", "George Russell", "Mercedes"),
        ("PIA", "Oscar Piastri", "McLaren"),
        ("GAS", "Pierre Gasly", "Alpine"),
    ],
}


def setup_cache(cache_dir: Optional[Path] = None) -> Path:
    """Yerel JSON önbellek klasörünü oluşturur."""
    target_dir = cache_dir or CACHE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def _cached_get_json(url: str, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    OpenF1 API isteğini yapar ve sonucu yerel diskte JSON olarak önbelleğe alır.
    Aynı yarış/pilot tekrar seçildiğinde internetten indirmeden 0.05 saniyede okur.
    """
    cache_dir = setup_cache()
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{url_hash}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list) and len(data) > 0:
        try:
            cache_file.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    return data if isinstance(data, list) else []


def get_season_events(year: int) -> List[str]:
    """
    Seçilen yıldaki (2023, 2024, 2025, 2026) Grand Prix hafta sonlarının listesini
    OpenF1 üzerinden döndürür.
    """
    try:
        sessions = _cached_get_json(f"{OPENF1_BASE_URL}/sessions?year={year}")
        seen = []
        for s in sessions:
            country = s.get("country_name", "")
            location = s.get("location", "")
            sname = s.get("session_name", "")
            if sname in ("Qualifying", "Race") and country:
                label = f"{country} ({location})" if location and location != country else country
                if label not in seen:
                    seen.append(label)
        if seen:
            return seen
    except Exception:
        pass

    return [
        "Belgium (Spa-Francorchamps)",
        "Monaco",
        "Italy (Monza)",
        "Great Britain (Silverstone)",
        "Bahrain (Sakhir)",
        "Austria (Spielberg)",
        "Netherlands (Zandvoort)",
        "Singapore (Marina Bay)",
    ]


def get_preset_drivers_for_year(
    year: int, grand_prix: Optional[str] = None, session_type: str = "Q"
) -> List[Dict[str, str]]:
    """
    Seçilen sezon ve yarış için OpenF1'den gerçek katılımcı pilot listesini (veya
    yedek sezon listesini) döndürür.
    """
    if grand_prix:
        try:
            session = load_f1_session(year, grand_prix, session_type)
            drivers_map = session.get("drivers_map", {})
            if drivers_map:
                return [
                    {"code": k, "name": v["name"], "team": v["team"]}
                    for k, v in drivers_map.items()
                ]
        except Exception:
            pass

    raw = SEASON_DRIVERS.get(year, SEASON_DRIVERS[2025])
    return [{"code": c, "name": n, "team": t} for c, n, t in raw]


def load_f1_session(year: int, grand_prix: str, session_type: str = "Q") -> Dict[str, Any]:
    """
    OpenF1 üzerinden seçilen yıl, ülke/pist ve seans ('Q' -> Qualifying, 'R' -> Race)
    için 'session_key' ve pilot listesini bulur.
    """
    target_session_name = "Qualifying" if session_type == "Q" else "Race"
    sessions = _cached_get_json(f"{OPENF1_BASE_URL}/sessions?year={year}")

    if not sessions:
        raise ValueError(f"{year} sezonu için OpenF1 sunucusundan seans bilgisi alınamadı.")

    gp_clean = grand_prix.lower().replace("grand prix", "").strip()
    country_part = gp_clean.split("(")[0].strip()
    loc_part = gp_clean.split("(")[1].replace(")", "").strip() if "(" in gp_clean else ""

    matched_session = None
    for s in sessions:
        s_name = str(s.get("session_name", ""))
        if s_name.lower() != target_session_name.lower():
            continue
        c_name = str(s.get("country_name", "")).lower()
        loc_name = str(s.get("location", "")).lower()
        short_name = str(s.get("circuit_short_name", "")).lower()

        if loc_part and (loc_part in loc_name or loc_name in loc_part):
            matched_session = s
            break
        if (
            country_part in c_name
            or c_name in gp_clean
            or loc_name in gp_clean
            or short_name in gp_clean
            or (country_part.startswith("belgi") and "belgi" in c_name)
            or (country_part.startswith("ital") and "ital" in c_name)
            or (country_part.startswith("brit") and "brit" in c_name)
        ):
            matched_session = s
            break

    if matched_session is None:
        raise ValueError(
            f"'{year} {grand_prix} ({target_session_name})' seansı OpenF1 veritabanında bulunamadı."
        )

    session_key = matched_session["session_key"]
    drivers_raw = _cached_get_json(f"{OPENF1_BASE_URL}/drivers?session_key={session_key}")

    drivers_map: Dict[str, Dict[str, Any]] = {}
    for d in drivers_raw:
        acronym = str(d.get("name_acronym", "")).upper()
        if acronym and d.get("driver_number") is not None:
            colour = str(d.get("team_colour") or "").strip("#")
            drivers_map[acronym] = {
                "driver_number": d["driver_number"],
                "code": acronym,
                "name": d.get("full_name") or acronym,
                "team": d.get("team_name") or "Unknown",
                "color": f"#{colour}" if len(colour) == 6 else None,
            }

    country_disp = matched_session.get("country_name", grand_prix)
    loc_disp = matched_session.get("location", "")
    event_title = (
        f"{country_disp} Grand Prix ({loc_disp})" if loc_disp else f"{country_disp} Grand Prix"
    )

    return {
        "session_key": session_key,
        "year": year,
        "event_name": event_title,
        "session_name": target_session_name,
        "drivers_map": drivers_map,
    }


def resolve_driver_colors(
    session: Dict[str, Any], driver1: str, team1: str, driver2: str, team2: str
) -> Tuple[str, str]:
    """
    İki pilotun grafikte kullanılacak renklerini (HEX) belirler.
    İki pilot aynı takımdansa 2. pilota yüksek kontrastlı Altın Sarısı (#FFD700) atanır.
    """
    drivers_map = session.get("drivers_map", {})

    def _get_color(drv: str, team: str) -> str:
        info = drivers_map.get(drv, {})
        if info.get("color"):
            return info["color"]
        team_lower = (team or "").lower()
        for key, hex_val in TEAM_COLORS_FALLBACK.items():
            if key in team_lower:
                return hex_val
        return "#00D2BE"

    color1 = _get_color(driver1, team1)
    color2 = _get_color(driver2, team2)

    if color1.lower() == color2.lower() or (team1 and team2 and team1 == team2):
        color2 = "#FFD700" if color1.lower() != "#ffd700" else "#00FFFF"

    return color1, color2


def format_laptime(td: pd.Timedelta) -> str:
    """Pandas Timedelta formatındaki tur süresini F1 standart formatına ('1:10.270') çevirir."""
    if pd.isna(td):
        return "N/A"
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:06.3f}"


def extract_driver_fastest_lap(session: Dict[str, Any], driver_code: str) -> Dict[str, Any]:
    """
    OpenF1 API üzerinden:
    1. Pilotun seanstaki tüm turlarını (/v1/laps) çeker ve en hızlı turunu (minimum lap_duration) bulur.
    2. Sadece o en hızlı turun başlangıç ve bitiş saniyeleri arasındaki:
       - Sensör verilerini (/v1/car_data -> Speed, Throttle, Brake, nGear, RPM)
       - Pist koordinatlarını (/v1/location -> X, Y)
       çeker, zaman ekseninde birleştirir ve 'Distance (Metre)' sütununu hesaplar.
    """
    session_key = session["session_key"]
    drivers_map = session["drivers_map"]

    if driver_code not in drivers_map:
        available = ", ".join(sorted(drivers_map.keys()))
        raise ValueError(
            f"{driver_code} pilotu bu seansta yer almıyor. Mevcut pilotlar: {available}"
        )

    drv_info = drivers_map[driver_code]
    driver_number = drv_info["driver_number"]

    # 1. Pilotun turlarını çek
    laps_url = f"{OPENF1_BASE_URL}/laps?session_key={session_key}&driver_number={driver_number}"
    laps_raw = _cached_get_json(laps_url)

    valid_laps = [
        lap
        for lap in laps_raw
        if lap.get("lap_duration") is not None
        and lap.get("date_start") is not None
        and not lap.get("is_pit_out_lap", False)
        and float(lap["lap_duration"]) > 40.0
    ]

    if not valid_laps:
        raise ValueError(
            f"{driver_code} pilotunun bu seansta kaydedilmiş geçerli bir hızlı turu bulunamadı."
        )

    # En hızlı turu seç
    fastest_lap = min(valid_laps, key=lambda x: float(x["lap_duration"]))
    lap_duration_sec = float(fastest_lap["lap_duration"])
    lap_number = int(fastest_lap.get("lap_number", 1))

    # Turun başlangıç ve bitiş zamanlarını UTC ISO formatına çevir (+00:00 olmadan, URL uyumlu)
    t_start = pd.to_datetime(fastest_lap["date_start"], utc=True)
    t_end = t_start + pd.Timedelta(seconds=lap_duration_sec + 0.6)

    start_iso = t_start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    end_iso = t_end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    # 2. Sadece bu en hızlı tura ait sensör (car_data) ve GPS (location) verilerini çek (~2 saniye sürer!)
    car_url = (
        f"{OPENF1_BASE_URL}/car_data?session_key={session_key}"
        f"&driver_number={driver_number}&date>={start_iso}&date<={end_iso}"
    )
    loc_url = (
        f"{OPENF1_BASE_URL}/location?session_key={session_key}"
        f"&driver_number={driver_number}&date>={start_iso}&date<={end_iso}"
    )

    car_raw = _cached_get_json(car_url)
    loc_raw = _cached_get_json(loc_url)

    if not car_raw:
        raise ValueError(
            f"{driver_code} pilotunun {lap_number}. turu için telemetri sensör verisi bulunamadı."
        )

    car_df = pd.DataFrame(car_raw)
    car_df["date"] = pd.to_datetime(car_df["date"], utc=True, format="ISO8601")
    car_df = car_df.sort_values("date").reset_index(drop=True)

    # Tur başlangıcından itibaren geçen saniye (Time)
    t0 = car_df["date"].iloc[0]
    car_df["TimeSec"] = (car_df["date"] - t0).dt.total_seconds()
    car_df["Time"] = pd.to_timedelta(car_df["TimeSec"], unit="s")

    # Hız (km/s -> m/s) üzerinden kümülatif Mesafe (Distance - Metre) hesabı
    dt = np.diff(car_df["TimeSec"].to_numpy(dtype=float), prepend=0.0)
    speed_ms = car_df["speed"].to_numpy(dtype=float) / 3.6
    car_df["Distance"] = np.cumsum(speed_ms * dt)

    # 3. Pist Haritası için X ve Y koordinatlarını zaman ekseninde birleştir
    if loc_raw:
        loc_df = pd.DataFrame(loc_raw)
        loc_df["date"] = pd.to_datetime(loc_df["date"], utc=True, format="ISO8601")
        loc_df = loc_df.sort_values("date").reset_index(drop=True)
        loc_sec = (loc_df["date"] - t0).dt.total_seconds().to_numpy(dtype=float)
        car_sec = car_df["TimeSec"].to_numpy(dtype=float)

        car_df["X"] = np.interp(car_sec, loc_sec, loc_df["x"].to_numpy(dtype=float))
        car_df["Y"] = np.interp(car_sec, loc_sec, loc_df["y"].to_numpy(dtype=float))
    else:
        car_df["X"] = 0.0
        car_df["Y"] = 0.0

    # Sütun isimlerini standartlaştır
    telemetry = pd.DataFrame(
        {
            "Time": car_df["Time"],
            "Distance": car_df["Distance"],
            "Speed": car_df["speed"].astype(float),
            "Throttle": car_df["throttle"].astype(float),
            "Brake": car_df["brake"].astype(float),
            "nGear": car_df["n_gear"].astype(int),
            "RPM": car_df["rpm"].astype(float),
            "X": car_df["X"].astype(float),
            "Y": car_df["Y"].astype(float),
        }
    )

    lap_td = pd.Timedelta(seconds=lap_duration_sec)

    return {
        "driver": driver_code,
        "team": drv_info["team"],
        "lap_time": lap_td,
        "lap_time_str": format_laptime(lap_td),
        "compound": f"Tur {lap_number}",
        "lap_number": lap_number,
        "telemetry": telemetry,
    }
