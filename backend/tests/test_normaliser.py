import pytest

from backend.app.domain.lexicon import load_lexicon, norm
from backend.app.domain.normaliser import analyse, parse_number


# ---------- lexicon ----------

def test_lexicon_loads_without_conflicts():
    lex = load_lexicon()
    assert lex.numbers[norm("पन्नास")] == 50
    assert lex.numbers[norm("पचास")] == 50


def test_nukta_and_chandrabindu_variants_match():
    assert norm("पाँच") == norm("पांच")
    assert norm("अड़तीस") == norm("अडतीस")


# ---------- numbers ----------

@pytest.mark.parametrize("text,value", [
    ("पंधरा", 15), ("पंद्रह", 15), ("पन्नास", 50), ("पचास", 50), ("साठ", 60), ("अस्सी", 80), ("ऐंशी", 80),
    ("fifteen", 15), ("fifty", 50), ("twenty five", 25), ("twenty-five", 25), ("ninety nine", 99),
    ("दो सौ पचास", 250), ("दोनशे पन्नास", 250), ("one hundred twenty five", 125),
    ("एक हजार दो सौ", 1200), ("दोन हजार", 2000), ("hundred", 100), ("शंभर", 100),
    ("१५", 15), ("50", 50), ("1,200", 1200), ("12.5", 12.5), ("शून्य", 0),
])
def test_parse_number(text, value):
    assert parse_number(text) == value


def test_adjacent_numbers_are_not_summed():
    a = analyse("fifteen fifty")
    assert [q.number.value for q in a.quantities] == [15, 50]
    a = analyse("दस तीस")
    assert [q.number.value for q in a.quantities] == [10, 30]


def test_asset_ids_are_not_numbers():
    a = analyse("P-12 और C-04 और M-07 बंद")
    assert a.quantities == []


def test_raw_text_and_offsets_preserved():
    text = "pressure पंधरा PSI"
    q = analyse(text).quantities[0]
    assert text[q.number.start:q.number.end] == q.number.raw == "पंधरा"
    assert q.number.value == 15 and q.unit.canonical == "PSI"


# ---------- units ----------

def test_missing_unit_is_not_inferred():
    q = analyse("P-12 का temperature अस्सी है").quantities[0]
    assert q.number.value == 80 and q.unit is None


def test_degree_stays_ambiguous():
    q = analyse("Temperature साठ डिग्री होतं").quantities[0]
    assert q.number.value == 60 and q.unit.canonical == "degree" and q.unit.ambiguous


def test_celsius_is_not_ambiguous():
    for text in ("60 celsius", "sixty degrees celsius", "साठ डिग्री सेल्सियस"):
        q = analyse(text).quantities[0]
        assert q.unit.canonical == "°C" and not q.unit.ambiguous, text
    q = analyse("sixty degrees celsius").quantities[0]
    assert q.unit.raw == "degrees celsius"


def test_symbol_units():
    assert analyse("50°C").quantities[0].unit.canonical == "°C"
    assert analyse("40%").quantities[0].unit.canonical == "%"


# ---------- corrections (from docs/TEST_SCRIPTS.md) ----------

def test_ME1_marathi_correction_without_unit():
    a = analyse("P-12 pump बंद पडला आहे, सकाळी साडेदहा वाजता. Vibration खूप होतं. Pressure पंधरा... नाही, पन्नास होतं.")
    assert len(a.corrections) == 1
    c = a.corrections[0]
    assert (c.old.number.value, c.new.number.value) == (15, 50)
    assert c.old.unit is None and c.new.unit is None


def test_HE1_hindi_correction_unit_on_new_value_only():
    a = analyse("C-04 compressor trip हो गया, दस बजकर तीस मिनट पर. Pressure पंद्रह... नहीं, पचास PSI था.")
    assert len(a.corrections) == 1
    c = a.corrections[0]
    assert (c.old.number.value, c.new.number.value) == (15, 50)
    assert c.old.unit is None and c.new.unit.canonical == "PSI"


def test_MHE1_trilingual_correction():
    a = analyse("P-12 बंद पडला, pressure पंधरा... नहीं, पन्नास PSI. खाली पाणी निकल रहा है")
    assert [(c.old.number.value, c.new.number.value) for c in a.corrections] == [(15, 50)]


def test_english_correction_hero_scenario():
    a = analyse("Pressure is fifteen... sorry, fifty PSI.")
    assert [(c.old.number.value, c.new.number.value) for c in a.corrections] == [(15, 50)]
    assert a.corrections[0].new.unit.canonical == "PSI"


def test_digits_correction():
    a = analyse("pressure 15, sorry, 50 PSI")
    assert len(a.corrections) == 1


def test_plain_negation_is_not_a_correction():
    assert analyse("Leakage नाही. पन्नास PSI").corrections == []
    assert analyse("no leakage, fifty PSI").corrections == []
    assert analyse("fifteen PSI, no leakage").corrections == []


# ---------- times ----------

def test_marathi_sakali_sade_dahaa_is_10_30_am():
    t = analyse("सकाळी साडेदहा वाजता").times[0]
    assert (t.hour_spoken, t.minute, t.am_pm, t.am_pm_source) == (10, 30, "am", "daypart")
    assert t.hhmm == "10:30" and t.status == "resolved"


def test_marathi_attached_and_split_forms_agree():
    a = analyse("साडेदहा वाजता").times[0]
    b = analyse("साडे दहा वाजता").times[0]
    assert (a.hour_spoken, a.minute) == (b.hour_spoken, b.minute) == (10, 30)


def test_hindi_bajkar_minutes_is_ambiguous_without_daypart():
    t = analyse("दस बजकर तीस मिनट पर").times[0]
    assert (t.hour_spoken, t.minute) == (10, 30)
    assert t.hour24 is None and t.status == "needs_clarification"


def test_english_ten_thirty_with_cue_is_ambiguous():
    t = analyse("Pump P-12 stopped at ten thirty.").times[0]
    assert (t.hour_spoken, t.minute, t.hhmm) == (10, 30, None)
    assert t.status == "needs_clarification"


def test_explicit_pm_resolves():
    t = analyse("stopped at ten thirty pm").times[0]
    assert t.hhmm == "22:30" and t.am_pm_source == "explicit"


def test_clock_digits():
    assert analyse("at 10:30").times[0].status == "needs_clarification"
    assert analyse("at 14:05").times[0].hhmm == "14:05"
    assert analyse("शाम 6:15").times[0].hhmm == "18:15"


@pytest.mark.parametrize("text,h,m", [
    ("सव्वा दहा वाजता", 10, 15), ("पावणे दहा वाजता", 9, 45), ("पौने दस बजे", 9, 45),
    ("साढ़े तीन बजे", 3, 30), ("सवा पांच बजे", 5, 15), ("दीड वाजता", 1, 30), ("डेढ़ बजे", 1, 30),
    ("अडीच वाजता", 2, 30), ("ढाई बजे", 2, 30), ("half past ten", 10, 30), ("quarter to eleven", 10, 45),
    ("quarter past two", 2, 15), ("पौने एक बजे", 12, 45),
])
def test_fractional_times(text, h, m):
    t = analyse(text).times[0]
    assert (t.hour_spoken, t.minute) == (h, m)


def test_night_daypart_rules():
    assert analyse("रात्री नऊ वाजता").times[0].hhmm == "21:00"
    assert analyse("रात्री दोन वाजता").times[0].hhmm == "02:00"
    assert analyse("दुपारी तीन वाजता").times[0].hhmm == "15:00"
    assert analyse("संध्याकाळी सहा वाजता").times[0].hhmm == "18:00"


def test_daypart_in_previous_sentence_is_not_used():
    t = analyse("Pressure was normal at night. Stopped at ten thirty.").times[0]
    assert t.am_pm is None and t.status == "needs_clarification"


def test_daypart_belongs_to_nearest_time():
    a = analyse("सकाळी दहा वाजता चालू, रात्री अकरा वाजता बंद")
    assert [t.hhmm for t in a.times] == ["10:00", "23:00"]


def test_time_numbers_are_not_reported_as_quantities():
    a = analyse("दस बजकर तीस मिनट पर pressure पचास PSI")
    assert [q.number.value for q in a.quantities] == [50]


def test_bare_number_pair_without_cue_is_not_a_time():
    a = analyse("pressure fifteen fifty")
    assert a.times == []


def test_fraction_word_without_clock_marker_is_not_a_time():
    assert analyse("साढ़े तीन किलो").times == []


def test_24h_time_ignores_conflicting_am_pm():
    t = analyse("at 15:30 am").times[0]
    assert t.hhmm == "15:30" and t.note


def test_empty_text_produces_nothing():
    a = analyse("")
    assert a.times == a.quantities == a.corrections == []


# ---------- found in the 2026-11-04 gate test (real Prisma output, English words in Devanagari) ----------

def test_spaced_devanagari_unit_is_matched():
    q = analyse("प्रेशर पंधरा नाही, पन्नास पी एस आय खाली पाणी").corrections[0].new
    assert q.number.value == 50 and q.unit.canonical == "PSI"
    assert q.unit.raw == "पी एस आय"


def test_devanagari_english_number_words():
    for text, value in [("ट्वेल्व", 12), ("फिफ्टी फाइव", 55), ("सेव्हन", 7), ("थर्टी", 30)]:
        assert parse_number(text) == value, text


def test_dropped_first_value_is_not_invented():
    # Prisma sometimes returns "प्रेशर नाही, पन्नास" with the corrected-away value missing
    a = analyse("प्रेशर नहीं, पचास पीएसआई था।")
    assert a.corrections == []
    assert [q.number.value for q in a.quantities] == [50]


def test_real_prisma_time_with_split_sade():
    t = analyse("सकाळी साडे दहा वाजता व्हायब्रेशन खूप होतं").times[0]
    assert t.hhmm == "10:30"
