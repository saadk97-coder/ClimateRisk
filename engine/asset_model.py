from dataclasses import dataclass, field, asdict
from typing import Iterable, MutableMapping, Optional
import json
import os


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0", ""}:
        return False
    raise ValueError(f"basement must be boolean-like, got {value}")


@dataclass
class Asset:
    id: str
    name: str
    lat: float
    lon: float
    asset_type: str                  # e.g. "residential_masonry", "commercial_steel"
    replacement_value: float
    construction_material: str       # wood_frame | masonry | steel | concrete | mixed
    year_built: int
    stories: int
    basement: bool
    roof_type: str                   # flat | gable | hip
    first_floor_height_m: float       # first-floor height above local ground (freeboard, NOT ASL)
    terrain_elevation_asl_m: float   # terrain elevation above sea level (auto-detected or manual)
    floor_area_m2: float
    region: str                      # iso3 country code
    # ---- Transition risk inputs (Session 8) ----
    # Sector key from data/transition/sector_taxonomy.json — drives pass-through,
    # learning-curve mapping, IO position. Empty string disables transition layer for this asset.
    sector: str = ""
    scope1_emissions_tco2: float = 0.0   # Direct emissions, t CO2/yr
    scope2_emissions_tco2: float = 0.0   # Purchased electricity emissions, t CO2/yr
    scope3_emissions_tco2: float = 0.0   # Value-chain emissions (optional), t CO2/yr
    annual_revenue: float = 0.0          # Asset-attributable revenue (for pass-through cap & financing premium)

    def to_dict(self) -> dict:
        return asdict(self)

    def __post_init__(self):
        self.id = str(self.id).strip()
        self.name = str(self.name).strip()
        self.region = str(self.region).strip().upper()
        self.sector = str(self.sector).strip().lower()
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"lat must be in [-90, 90], got {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"lon must be in [-180, 180], got {self.lon}")
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.replacement_value < 0:
            raise ValueError(f"replacement_value must be >= 0, got {self.replacement_value}")
        if not (1800 <= self.year_built <= 2025):
            raise ValueError(f"year_built must be in [1800, 2025], got {self.year_built}")
        if self.stories < 1:
            raise ValueError(f"stories must be >= 1, got {self.stories}")
        if self.floor_area_m2 < 0:
            raise ValueError(f"floor_area_m2 must be >= 0, got {self.floor_area_m2}")
        if len(self.region) != 3:
            raise ValueError(f"region must be an ISO3 code, got {self.region}")
        # Negative freeboard would increase flood intensity — clamp to 0
        if self.first_floor_height_m < 0:
            self.first_floor_height_m = 0.0
        # Emissions and revenue must be non-negative
        for fname in ("scope1_emissions_tco2", "scope2_emissions_tco2",
                      "scope3_emissions_tco2", "annual_revenue"):
            v = getattr(self, fname)
            if v < 0:
                setattr(self, fname, 0.0)

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        return cls(
            id=str(d["id"]),
            name=str(d["name"]),
            lat=float(d["lat"]),
            lon=float(d["lon"]),
            asset_type=str(d["asset_type"]),
            replacement_value=float(d["replacement_value"]),
            construction_material=str(d.get("construction_material", "masonry")),
            year_built=int(d.get("year_built", 2000)),
            stories=int(d.get("stories", 1)),
            basement=_coerce_bool(d.get("basement", False)),
            roof_type=str(d.get("roof_type", "gable")),
            first_floor_height_m=float(d.get("first_floor_height_m", 0.0)),
            terrain_elevation_asl_m=float(d.get("terrain_elevation_asl_m", d.get("elevation_m", 0.0))),
            floor_area_m2=float(d.get("floor_area_m2", 200.0)),
            region=str(d.get("region", "GBR")).upper(),
            sector=str(d.get("sector", "")),
            scope1_emissions_tco2=float(d.get("scope1_emissions_tco2", 0.0)),
            scope2_emissions_tco2=float(d.get("scope2_emissions_tco2", 0.0)),
            scope3_emissions_tco2=float(d.get("scope3_emissions_tco2", 0.0)),
            annual_revenue=float(d.get("annual_revenue", 0.0)),
        )


def load_asset_types() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "asset_types.json")
    with open(os.path.normpath(path)) as f:
        return json.load(f)


def get_default_asset_params(asset_type: str) -> dict:
    catalog = load_asset_types()
    return catalog.get(asset_type, catalog.get("residential_masonry", {}))


def normalize_assets(raw_assets: Iterable) -> list[Asset]:
    """Normalize mixed session-state assets into Asset dataclasses."""
    normalized: list[Asset] = []
    for asset in raw_assets or []:
        normalized.append(Asset.from_dict(asset) if isinstance(asset, dict) else asset)
    return normalized


def normalize_asset_state(state: MutableMapping, key: str = "assets") -> list[Asset]:
    assets = normalize_assets(state.get(key, []))
    state[key] = assets
    return assets
