"""Synthetic asset catalogue and conservative alias resolution.

Resolution never guesses: zero matches -> UNKNOWN, more than one -> AMBIGUOUS.
Number-word handling ("बारा" -> 12) belongs to the normaliser, not here;
aliases in the catalogue cover the spoken forms we expect.
"""
import json
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.domain.lexicon import norm
from backend.app.domain.schemas import Asset

DEFAULT_CATALOGUE = Path(__file__).resolve().parents[3] / "fixtures" / "assets.json"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class AssetResolution(BaseModel):
    status: ResolutionStatus
    mention: str
    candidates: list[Asset] = Field(default_factory=list)

    @property
    def asset(self) -> Asset | None:
        return self.candidates[0] if self.status == ResolutionStatus.RESOLVED else None


def _key(text: str) -> str:
    """Case/spacing/nukta-insensitive key (same folding as the lexicon); keeps Devanagari intact."""
    return re.sub(r"[\s\-_./]+", "", norm(text).strip())


def alias_index(catalogue: list[Asset]) -> dict[str, set[str]]:
    """key -> asset ids that answer to it (more than one id means the alias is ambiguous)."""
    index: dict[str, set[str]] = {}
    for asset in catalogue:
        for name in [asset.id, *asset.aliases]:
            index.setdefault(_key(name), set()).add(asset.id)
    return index


def load_catalogue(path: Path = DEFAULT_CATALOGUE) -> list[Asset]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Asset(**a) for a in data["assets"]]


def resolve_asset(mention: str, catalogue: list[Asset]) -> AssetResolution:
    target = _key(mention)
    if not target:
        return AssetResolution(status=ResolutionStatus.UNKNOWN, mention=mention)

    matches = [
        asset
        for asset in catalogue
        if target == _key(asset.id) or target in {_key(a) for a in asset.aliases}
    ]
    if len(matches) == 1:
        status = ResolutionStatus.RESOLVED
    elif matches:
        status = ResolutionStatus.AMBIGUOUS
    else:
        status = ResolutionStatus.UNKNOWN
    return AssetResolution(status=status, mention=mention, candidates=matches)
