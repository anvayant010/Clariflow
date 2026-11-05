from backend.app.domain.assets import ResolutionStatus, load_catalogue, resolve_asset
from backend.app.domain.schemas import Draft, EvidenceRef, Issue, IssueType, TranscriptSegment, SegmentSource

import pytest
from pydantic import ValidationError


@pytest.fixture(scope="module")
def catalogue():
    return load_catalogue()


def test_catalogue_has_ten_unique_assets(catalogue):
    ids = [a.id for a in catalogue]
    assert len(ids) == 10
    assert len(set(ids)) == 10


def test_exact_id_resolves(catalogue):
    r = resolve_asset("P-12", catalogue)
    assert r.status == ResolutionStatus.RESOLVED
    assert r.asset.id == "P-12"


def test_spacing_and_case_insensitive(catalogue):
    assert resolve_asset("p 12", catalogue).asset.id == "P-12"
    assert resolve_asset("c4", catalogue).asset.id == "C-04"


def test_marathi_alias_resolves(catalogue):
    assert resolve_asset("मोटर सात", catalogue).asset.id == "M-07"


def test_deliberate_ambiguity_is_never_guessed(catalogue):
    for mention in ("pump twelve", "पंप बारा"):
        r = resolve_asset(mention, catalogue)
        assert r.status == ResolutionStatus.AMBIGUOUS
        assert r.asset is None
        assert {a.id for a in r.candidates} == {"P-12", "P-21"}


def test_unknown_asset(catalogue):
    assert resolve_asset("Z-99", catalogue).status == ResolutionStatus.UNKNOWN
    assert resolve_asset("   ", catalogue).status == ResolutionStatus.UNKNOWN


def test_transcript_segment_is_immutable():
    seg = TranscriptSegment(
        session_id="s1", turn_index=0, text="P-12 बंद पडला", source=SegmentSource.FIXTURE
    )
    with pytest.raises(ValidationError):
        seg.text = "changed"


def test_open_blockers_only_counts_blocking_open_issues():
    blocking = Issue(type=IssueType.MISSING_UNIT, evidence=[EvidenceRef(segment_id="a", quote="q")])
    optional = Issue(type=IssueType.OPTIONAL_DETAIL, blocking=False)
    draft = Draft(session_id="s1", issues=[blocking, optional])
    assert draft.open_blockers() == [blocking]


@pytest.mark.parametrize("mention,asset_id", [
    ("सी फोर", "C-04"), ("एम सेव्हन", "M-07"), ("पी ट्वेल्व", "P-12"), ("एफ थ्री", "F-03"),
])
def test_devanagari_spoken_ids_resolve(catalogue, mention, asset_id):
    assert resolve_asset(mention, catalogue).asset.id == asset_id


@pytest.mark.parametrize("mention", ["पीकवेल", "एसटी", "पिक्चर"])
def test_real_stt_mishearings_do_not_resolve(catalogue, mention):
    # Seen in the gate test; must be asked about, never guessed
    assert resolve_asset(mention, catalogue).status == ResolutionStatus.UNKNOWN
