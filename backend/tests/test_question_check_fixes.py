"""Fixes found by the question-type check (question_cases.py): fault words, units, times, causes.

Rules these tests keep: a unit that does not belong to the kind of reading is never saved (it is asked about); the
everyday word "बार" ("times") is a unit only next to "pressure"; a part of the day that cannot hold that hour is not
turned into AM/PM; a fault word inside a stated cause is part of the cause (smoke and fire never are).
"""
import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.issues import active
from backend.app.domain.normaliser import analyse
from backend.app.domain.schemas import CandidateStatus, IssueType, SegmentSource
from backend.app.services.pipeline import Pipeline
from backend.app.storage.store import Store, make_engine
from backend.tests.helpers import review

CATALOGUE = load_catalogue()


def run(text, lang="en"):
    p = Pipeline(Store(make_engine()), CATALOGUE, lang)
    sid = p.start()
    return p, sid, p.submit_turn(sid, text, SegmentSource.FIXTURE)


def symptoms(draft):
    return {c.field_path.split(".")[1]: c.normalised_value for c in active(draft, "symptom")}


# ---------------------------------------------------------------- a unit of the wrong kind is asked about, never saved

@pytest.mark.parametrize("lang,text,kind,heard", [
    ("en", "B-02 stopped, temperature eighty PSI", "temperature", "PSI"),
    ("en", "B-02 stopped, pressure eighty celsius", "pressure", "celsius"),
    ("en", "B-02 stopped, speed sixty bar", "speed", "bar"),
    ("mr", "B-02 बंद पडला, तापमान ऐंशी PSI", "तापमान", "PSI"),
    ("hi", "B-02 बंद हो गया, प्रेशर साठ सेल्सियस", "प्रेशर", "सेल्सियस"),
])
def test_a_unit_of_the_wrong_kind_is_not_saved_and_is_asked_about(lang, text, kind, heard):
    p, sid, r = run(text, lang)
    assert r.question.issue_type == IssueType.MISSING_UNIT
    (m,) = active(r.draft, "measurement")
    assert m.unit is None  # "80 PSI" as a temperature would be a wrong value on a work order
    assert kind in r.question.text and heard in r.question.text  # the question says what was heard and why it is asked


def test_the_right_unit_then_saves_the_value():
    p, sid, r = run("B-02 stopped, temperature eighty PSI")
    r = p.answer(sid, "celsius", SegmentSource.FIXTURE)
    assert r.understood
    assert "Temperature 80 °C." in review(p, sid).readback


def test_a_pressure_unit_does_not_answer_a_temperature_question():
    p, sid, r = run("B-02 stopped, temperature eighty PSI")
    r = p.answer(sid, "bar", SegmentSource.FIXTURE)
    assert not r.understood and r.question.issue_type == IssueType.MISSING_UNIT


# ---------------------------------------------------------------- "बार" is a unit only next to "pressure"

@pytest.mark.parametrize("text", [
    "B-02 तीन बार बंद पडला", "B-02 पिछली बार भी बंद हो गया", "B-02 बार बार बंद हो रहा है", "B-02 बंद पडला, बार 60",
    "B-02 दो बार बंद हो गया",
])
def test_bar_meaning_times_is_not_a_pressure_reading(text):
    p, sid, r = run(text, "mr")
    assert active(r.draft, "measurement") == []
    assert r.question.issue_type != IssueType.MISSING_VALUE  # and "पिछली" is not mistaken for an unreadable number


@pytest.mark.parametrize("lang,text", [("mr", "B-02 बंद पडला, प्रेशर साठ बार"), ("hi", "B-02 बंद हो गया, प्रेशर साठ बार")])
def test_bar_next_to_pressure_is_the_unit(lang, text):
    p, sid, r = run(text, lang)
    (m,) = active(r.draft, "measurement")
    assert (m.normalised_value, m.unit) == (60, "bar")


# ---------------------------------------------------------------- speed in the hundreds (Marathi)

def test_marathi_fifteen_hundred_is_read():
    assert [q.number.value for q in analyse("स्पीड पंधराशे आरपीएम").quantities] == [1500]


# ---------------------------------------------------------------- a part of the day that cannot hold that hour

@pytest.mark.parametrize("text", [
    "B-02 stopped at ten thirty in the afternoon", "B-02 stopped at ten in the afternoon", "B-02 stopped at two in the evening",
])
def test_a_daypart_that_does_not_fit_the_hour_is_asked_about(text):
    p, sid, r = run(text)
    assert r.question.issue_type == IssueType.AMBIGUOUS_TIME  # never turned into a guessed AM/PM


@pytest.mark.parametrize("text,hhmm", [
    ("B-02 stopped at three in the afternoon", "15:00"), ("B-02 stopped at twelve thirty in the afternoon", "12:30"),
    ("B-02 stopped at ten in the evening", "22:00"), ("B-02 stopped at ten in the morning", "10:00"),
    ("B-02 stopped at ten at night", "22:00"), ("B-02 stopped at two at night", "02:00"),
])
def test_a_daypart_that_fits_the_hour_is_used(text, hhmm):
    p, sid, r = run(text)
    (t,) = active(r.draft, "time")
    assert t.normalised_value == hhmm


@pytest.mark.parametrize("answer,hhmm", [("पी एम", "22:30"), ("ए एम", "10:30"), ("सकाळचे", "10:30"), ("रात्रीचे", "22:30")])
def test_am_pm_said_as_letters_or_as_a_possessive_daypart_is_understood(answer, hhmm):
    p, sid, r = run("B-02 बंद पडला, साडेदहा वाजता", "mr")
    assert r.question.issue_type == IssueType.AMBIGUOUS_TIME
    assert p.answer(sid, answer, SegmentSource.FIXTURE).understood
    assert active(p.store.draft(sid), "time")[0].normalised_value == hhmm


@pytest.mark.parametrize("lang,report,answer", [
    ("en", "B-02 stopped at ten thirty", "I don't remember"), ("mr", "B-02 बंद पडला, साडेदहा वाजता", "लक्षात नाही"),
    ("hi", "B-02 बंद हो गया, साढ़े दस बजे", "याद नहीं"),
])
def test_not_remembering_the_time_is_recorded_as_unknown(lang, report, answer):
    p, sid, r = run(report, lang)
    assert p.answer(sid, answer, SegmentSource.FIXTURE).understood
    assert active(p.store.draft(sid), "time")[0].status == CandidateStatus.UNKNOWN


# ---------------------------------------------------------------- the new fault words

@pytest.mark.parametrize("lang,text,concept", [
    ("en", "B-02 is broken", "broken"), ("en", "B-02 broke down", "broken"), ("en", "B-02 is out of order", "broken"),
    ("en", "B-02 is jammed", "jammed"), ("en", "B-02 is stuck", "jammed"), ("en", "B-02 has a burning smell", "smell"),
    ("en", "B-02 there are sparks", "sparks"), ("en", "B-02 won't start", "stopped"), ("en", "B-02 stopped running", "stopped"),
    ("en", "B-02 is shaking", "vibration"), ("en", "B-02 there is a loud sound", "noise"), ("en", "B-02 is running hot", "heat"),
    ("en", "B-02 overheated", "heat"), ("en", "B-02 water is dripping", "leakage"),
    ("mr", "B-02 तुटलंय", "broken"), ("mr", "B-02 बिघडलं", "broken"), ("mr", "B-02 जाम झालंय", "jammed"),
    ("mr", "B-02 अडकलंय", "jammed"), ("mr", "B-02 जळका वास येतोय", "smell"), ("mr", "B-02 ठिणग्या उडतायत", "sparks"),
    ("mr", "B-02 सुरू होत नाही", "stopped"), ("mr", "B-02 चालू होत नाही", "stopped"), ("mr", "B-02 हादरतंय", "vibration"),
    ("mr", "B-02 पाणी गळतंय", "leakage"), ("mr", "B-02 तापलंय", "heat"),
    ("hi", "B-02 टूट गया है", "broken"), ("hi", "B-02 खराब हो गया है", "broken"), ("hi", "B-02 जाम हो गया", "jammed"),
    ("hi", "B-02 फंस गया", "jammed"), ("hi", "B-02 जलने की बदबू आ रही है", "smell"), ("hi", "B-02 चिंगारी निकल रही है", "sparks"),
    ("hi", "B-02 चालू नहीं हो रहा", "stopped"), ("hi", "B-02 काँप रहा है", "vibration"), ("hi", "B-02 पानी रिस रहा है", "leakage"),
    ("hi", "B-02 बहुत गर्म हो गया है", "heat"),
])
def test_everyday_fault_words_are_understood(lang, text, concept):
    p, sid, r = run(text, lang)
    assert symptoms(r.draft).get(concept) == "present", symptoms(r.draft)


@pytest.mark.parametrize("lang,text,concept", [
    ("en", "B-02 is not broken but noisy", "broken"), ("en", "no sparks, no smell, B-02 stopped", "sparks"),
    ("en", "B-02 no smell, it stopped", "smell"), ("mr", "B-02 तुटला नाही पण आवाज येतोय", "broken"),
    ("mr", "B-02 मधून वास येत नाही, पण गरम आहे", "smell"), ("hi", "B-02 बंद हो गया, जाम नहीं है", "jammed"),
])
def test_a_negated_fault_word_is_recorded_as_not_present(lang, text, concept):
    p, sid, r = run(text, lang)
    assert symptoms(r.draft).get(concept) == "absent"


def test_a_burning_smell_is_not_a_fire():
    p, sid, r = run("B-02 has a burning smell")
    assert symptoms(r.draft) == {"smell": "present"}  # "on fire" stays the only way to say fire
    p, sid, r = run("B-02 is burning hot")
    assert symptoms(r.draft) == {"heat": "present"}


def test_nothing_about_the_new_words_decides_urgency():
    p, sid, r = run("B-02 is broken, jammed, sparking and has a burning smell")
    assert r.question.issue_type == IssueType.MISSING_URGENCY  # the person is still asked; nothing is inferred
    assert active(r.draft, "urgency") == []


def test_the_new_symptoms_are_in_the_read_back_in_every_language():
    from backend.app.services.pipeline import Pipeline as P
    for lang, word in (("en", "broken"), ("mr", "तुटलं / बिघडलं"), ("hi", "खराब / टूटा")):
        p, sid, r = run("B-02 is broken", "en")
        review_text = review(p, sid, lang).readback
        assert word in review_text, (lang, review_text)


# ---------------------------------------------------------------- fault words inside a stated cause belong to the cause

@pytest.mark.parametrize("lang,text,cause", [
    ("en", "B-02 stopped, cause is belt broke", "belt broke"),
    ("en", "B-02 stopped, cause is bearing seized", "bearing seized"),
    ("mr", "B-02 बंद पडला, कारण बेल्ट तुटला", "बेल्ट तुटला"),
    ("hi", "B-02 बंद हो गया, कारण बेल्ट टूट गया", "बेल्ट टूट गया"),
])
def test_a_fault_word_in_the_stated_cause_is_not_also_an_observation(lang, text, cause):
    p, sid, r = run(text, lang)
    assert [c.normalised_value for c in active(r.draft, "cause")] == [cause]
    assert set(symptoms(r.draft)) == {"stopped"}  # "broken"/"jammed" describe the belt/bearing here, not the equipment


def test_smoke_in_a_stated_cause_is_still_an_observation():
    p, sid, r = run("B-02 stopped, cause is belt broke and smoke is coming")
    assert symptoms(r.draft).get("smoke") == "present"


def test_a_cause_still_ends_at_the_comma_before_another_field():
    p, sid, r = run("B-02 stopped, cause is belt broke, pressure two point five bar")
    assert [c.normalised_value for c in active(r.draft, "cause")] == ["belt broke"]
    assert [m.normalised_value for m in active(r.draft, "measurement")] == [2.5]


# ---------------------------------------------------------------- asset names as they appear on the screen

@pytest.mark.parametrize("text,asset", [
    ("the feed water pump stopped", "P-12"), ("the cooling water pump stopped", "P-21"), ("air compressor stopped", "C-04"),
    ("steam control valve stuck", "V-09"), ("drive motor stopped", "M-07"),
])
def test_the_name_shown_on_the_screen_identifies_the_asset(text, asset):
    p, sid, r = run(text)
    assert active(r.draft, "asset")[0].normalised_value == asset


# ---------------------------------------------------------------- more ways to say the urgency

@pytest.mark.parametrize("lang,report,answer,level", [
    ("hi", "B-02 बंद हो गया, धुआं", "काम रोक दो", "stop_work"), ("hi", "B-02 बंद हो गया, धुआं", "मशीन बंद करो", "stop_work"),
    ("mr", "B-02 बंद पडला, धूर", "इमरजन्सी", "emergency"), ("en", "B-02 stopped, smoke", "stop the machine", "stop_work"),
    ("en", "B-02 stopped, smoke", "no hurry", "can_wait"),
])
def test_more_natural_urgency_answers(lang, report, answer, level):
    p, sid, r = run(report, lang)
    assert p.answer(sid, answer, SegmentSource.FIXTURE).understood
    assert active(p.store.draft(sid), "urgency")[0].normalised_value == level


# ---------------------------------------------------------------- a lone hour: "at 3 pm"

@pytest.mark.parametrize("text,hhmm", [
    ("B-02 stopped at 3 pm", "15:00"), ("B-02 stopped at three PM", "15:00"), ("B-02 stopped at 9 am", "09:00"),
    ("B-02 stopped around 3 in the afternoon", "15:00"), ("B-02 stopped at 11 at night", "23:00"),
    ("B-02 stopped at 12 pm", "12:00"),
])
def test_a_lone_hour_with_am_pm_or_a_cue_and_a_part_of_the_day_is_a_time(text, hhmm):
    p, sid, r = run(text)
    assert [t.normalised_value for t in active(r.draft, "time")] == [hhmm]


@pytest.mark.parametrize("text", [
    "B-02 stopped at ten", "B-02 stopped 3 times today", "B-02 pressure 3 bar", "B-02 stopped, temperature 3 degree",
    "pump 12 is stopped", "B-02 stopped at ten PSI", "B-02 has 3 problems in the afternoon",
])
def test_a_lone_number_without_those_signs_is_not_a_time(text):
    p, sid, r = run(text)
    assert active(r.draft, "time") == []


@pytest.mark.parametrize("text", ["B-02 stopped, pressure 3 pm", "B-02 stopped at 3 bar in afternoon", "B-02 stopped, speed 3 pm"])
def test_a_number_that_is_a_reading_is_not_turned_into_a_time(text):
    p, sid, r = run(text)
    assert active(r.draft, "time") == []


# ---------------------------------------------------------------- found by the live check (Timbre voice -> Prisma, short clips)

@pytest.mark.parametrize("lang,report,answer,asset", [
    ("mr", "पंप बारा बंद पडला, धूर", "एकवीस", "P-21"), ("hi", "पंप बारह बंद हो गया, धुआं", "Pump इक्कीस।", "P-21"),
    ("en", "pump twelve stopped, smoke", "twenty one", "P-21"), ("en", "pump twelve stopped, smoke", "twelve", "P-12"),
    ("en", "pump twelve stopped, smoke", "21", "P-21"),
])
def test_a_number_that_fits_exactly_one_offered_asset_chooses_it(lang, report, answer, asset):
    p, sid, r = run(report, lang)
    assert p.answer(sid, answer, SegmentSource.FIXTURE).understood
    assert active(p.store.draft(sid), "asset")[0].normalised_value == asset


@pytest.mark.parametrize("answer", ["thirty", "four", "twelve and twenty one", "zero", "C-04", "the first"])
def test_a_number_that_fits_no_or_both_assets_is_not_guessed(answer):
    p, sid, r = run("pump twelve stopped, smoke")
    assert not p.answer(sid, answer, SegmentSource.FIXTURE).understood


def test_a_number_alone_does_not_choose_an_asset_when_no_asset_is_known():
    p, sid, r = run("smoke is coming out and it stopped")
    assert r.question.issue_type == IssueType.UNKNOWN_ASSET
    assert not p.answer(sid, "four", SegmentSource.FIXTURE).understood  # only a choice between OFFERED assets is inferred


@pytest.mark.parametrize("text,concept", [("B-02 तुटले", "broken"), ("B-02 बिघडले", "broken"), ("B-02 अडकले", "jammed")])
def test_other_marathi_forms_of_the_same_words(text, concept):
    p, sid, r = run(text, "mr")
    assert symptoms(r.draft).get(concept) == "present"
