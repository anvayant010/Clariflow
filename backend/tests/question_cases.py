"""Every question type x language x way of answering: the data for test_question_types.py.

Each case is (name, language, first report, the question that must be asked, [(answer, expected)]). `expected` is a
(field, value) pair that must appear in the draft afterwards, or None: an answer that must NOT be accepted (the same
question is asked again instead of guessing). Transcripts are Claude-written phrasings (not Prisma output); the Marathi
and Hindi wording is a draft that still needs native-speaker review.
"""
CASES: list[tuple] = []


def case(name, lang, report, expect_q, answers):
    CASES.append((name, lang, report, expect_q, answers))


# ---------------- unknown asset
A = "asset"
for lang, rep, ans in [
    ("en", "smoke is coming out and it stopped", [
        ("it is the conveyor belt two", (A, "B-02")), ("B-02", (A, "B-02")), ("belt two", (A, "B-02")),
        ("the cooling tower", (A, "T-08")), ("exhaust fan", (A, "F-03")), ("compressor four", (A, "C-04")),
        ("hydraulic press", (A, "H-11")), ("steam valve", (A, "V-09")),
        ("I don't know", None), ("the big one", None), ("pump", None), ("belt two and fan three", None)]),
    ("mr", "धूर येतोय आणि बंद पडलं", [
        ("बेल्ट दोन", (A, "B-02")), ("बी टू", (A, "B-02")), ("कंप्रेसर चार", (A, "C-04")), ("फॅन तीन", (A, "F-03")),
        ("पंखा तीन", (A, "F-03")), ("एम सेव्हन", (A, "M-07")), ("गिअरबॉक्स सहा", (A, "G-06")), ("वाल्व नऊ", (A, "V-09")),
        ("टॉवर आठ", (A, "T-08")), ("प्रेस अकरा", (A, "H-11")), ("माहीत नाही", None), ("तो मोठा", None)]),
    ("hi", "धुआं आ रहा है और बंद हो गया", [
        ("बेल्ट दो", (A, "B-02")), ("पंखा तीन", (A, "F-03")), ("फैन तीन", (A, "F-03")), ("वाल्व नौ", (A, "V-09")),
        ("गियरबॉक्स छह", (A, "G-06")), ("प्रेस ग्यारह", (A, "H-11")), ("टावर आठ", (A, "T-08")), ("पता नहीं", None),
        ("वो बड़ा वाला", None)]),
]:
    case("unknown_asset", lang, rep, "unknown_asset", ans)

# ---------------- ambiguous asset
for lang, rep, ans in [
    ("en", "pump twelve stopped, smoke", [
        ("P-12", (A, "P-12")), ("feed water pump", (A, "P-12")), ("feed pump", (A, "P-12")), ("the cooling pump", (A, "P-21")),
        ("P-21", (A, "P-21")), ("pump twenty one", (A, "P-21")), ("cooling water pump twenty one", (A, "P-21")),
        ("the first one", None), ("both", None), ("C-04", None), ("I don't know", None)]),
    ("mr", "पंप बारा बंद पडला, धूर", [
        ("पी ट्वेल्व", (A, "P-12")), ("पी बारा", (A, "P-12")), ("पी एकवीस", (A, "P-21")), ("पी ट्वेंटी वन", (A, "P-21")),
        ("पंप एकवीस", (A, "P-21")), ("P-21", (A, "P-21")), ("पहिला", None), ("दोन्ही", None), ("माहीत नाही", None)]),
    ("hi", "पंप बारह बंद हो गया, धुआं", [
        ("पी ट्वेल्व", (A, "P-12")), ("पंप इक्कीस", (A, "P-21")), ("पी २१", (A, "P-21")), ("पहला वाला", None),
        ("दोनों", None), ("पता नहीं", None)]),
]:
    case("ambiguous_asset", lang, rep, "ambiguous_asset", ans)

# ---------------- conflict: leakage vs water
L = "symptom.leakage"
for lang, rep, ans in [
    ("en", "B-02 no leakage but water is underneath", [
        ("yes there is a leak", (L, "present")), ("leak confirmed", (L, "present")), ("leakage is there", (L, "present")),
        ("it is leaking", (L, "present")), ("source unknown", ("symptom.water", "present")), ("I don't know where the water is from", ("symptom.water", "present")),
        ("not sure", ("symptom.water", "present")), ("maybe", None), ("blue", None)]),
    ("mr", "B-02 लिकेज नाही पण खाली पाणी आहे", [
        ("गळती आहे", (L, "present")), ("लिकेज आहे", (L, "present")), ("हो गळती निश्चित आहे", (L, "present")), ("गळतंय", (L, "present")),
        ("पाण्याचा स्रोत माहीत नाही", ("symptom.water", "present")), ("माहीत नाही", ("symptom.water", "present")),
        ("कदाचित", None)]),
    ("hi", "B-02 लीकेज नहीं है लेकिन नीचे पानी है", [
        ("लीकेज है", (L, "present")), ("लीक हो रहा है", (L, "present")), ("रिसाव है", (L, "present")), ("हाँ लीकेज पक्का है", (L, "present")),
        ("पानी का स्रोत पता नहीं", ("symptom.water", "present")), ("पता नहीं", ("symptom.water", "present")), ("शायद", None)]),
]:
    case("conflict_leak", lang, rep, "conflicting_observation", ans)

# ---------------- conflict: running vs stopped
for lang, rep, ans in [
    ("en", "B-02 is running and also stopped", [
        ("it is stopped", ("symptom.stopped", "present")), ("stopped", ("symptom.stopped", "present")), ("it is running", ("symptom.running", "present")),
        ("running", ("symptom.running", "present")), ("not sure", None), ("both", None)]),
    ("mr", "B-02 चालू आहे आणि बंद पडलं", [
        ("बंद पडलं", ("symptom.stopped", "present")), ("बंद आहे", ("symptom.stopped", "present")), ("चालू आहे", ("symptom.running", "present")),
        ("चालू", ("symptom.running", "present")), ("माहीत नाही", None)]),
    ("hi", "B-02 चल रहा है और बंद हो गया", [
        ("बंद हो गया", ("symptom.stopped", "present")), ("बंद है", ("symptom.stopped", "present")), ("चल रहा है", ("symptom.running", "present")),
        ("चालू है", ("symptom.running", "present")), ("पता नहीं", None)]),
]:
    case("conflict_run", lang, rep, "conflicting_observation", ans)

# ---------------- missing unit (pressure)
for lang, rep, ans in [
    ("en", "B-02 stopped, pressure sixty", [
        ("bar", ("measurement.pressure", "60 bar")), ("PSI", ("measurement.pressure", "60 PSI")), ("it is in bar", ("measurement.pressure", "60 bar")),
        ("sixty PSI", ("measurement.pressure", "60 PSI")), ("kilopascal", ("measurement.pressure", "60 kPa")), ("megapascal", ("measurement.pressure", "60 MPa")),
        ("I don't know", ("measurement.pressure", "60 unit-unknown")), ("celsius", None), ("RPM", None), ("sixty", None), ("high", None)]),
    ("mr", "B-02 बंद पडला, प्रेशर साठ", [
        ("बार", ("measurement.pressure", "60 bar")), ("पीएसआय", ("measurement.pressure", "60 PSI")), ("पी एस आय", ("measurement.pressure", "60 PSI")),
        ("साठ बार", ("measurement.pressure", "60 bar")), ("किलोपास्कल", ("measurement.pressure", "60 kPa")), ("माहीत नाही", ("measurement.pressure", "60 unit-unknown")),
        ("सेल्सिअस", None), ("जास्त", None)]),
    ("hi", "B-02 बंद हो गया, प्रेशर साठ", [
        ("बार", ("measurement.pressure", "60 bar")), ("पीएसआई", ("measurement.pressure", "60 PSI")), ("साठ बार", ("measurement.pressure", "60 bar")),
        ("पता नहीं", ("measurement.pressure", "60 unit-unknown")), ("सेल्सियस", None), ("ज़्यादा", None)]),
]:
    case("missing_unit_pressure", lang, rep, "missing_unit", ans)

# ---------------- missing unit (speed)  + temperature ambiguous
for lang, rep, ans in [
    ("en", "B-02 stopped, speed fifteen hundred", [("RPM", ("measurement.speed", "1500 RPM")), ("revolutions per minute", ("measurement.speed", "1500 RPM")),
                                                    ("rpm", ("measurement.speed", "1500 RPM")), ("bar", None)]),
    ("mr", "B-02 बंद पडला, स्पीड पंधराशे", [("आरपीएम", ("measurement.speed", "1500 RPM")), ("आर पी एम", ("measurement.speed", "1500 RPM")), ("बार", None)]),
]:
    case("missing_unit_speed", lang, rep, "missing_unit", ans)

for lang, rep, ans in [
    ("en", "B-02 stopped, temperature eighty degree", [
        ("celsius", ("measurement.temperature", "80 °C")), ("Celsius", ("measurement.temperature", "80 °C")), ("centigrade", ("measurement.temperature", "80 °C")),
        ("fahrenheit", ("measurement.temperature", "80 °F")), ("degree C", ("measurement.temperature", "80 °C")), ("I don't know", ("measurement.temperature", "80 unit-unknown")),
        ("bar", None), ("hot", None)]),
    ("mr", "B-02 बंद पडला, तापमान ऐंशी डिग्री", [
        ("सेल्सिअस", ("measurement.temperature", "80 °C")), ("सेल्सियस", ("measurement.temperature", "80 °C")), ("फॅरेनहाइट", ("measurement.temperature", "80 °F")),
        ("फारेनहाइट", ("measurement.temperature", "80 °F")), ("माहीत नाही", ("measurement.temperature", "80 unit-unknown")), ("बार", None)]),
    ("hi", "B-02 बंद हो गया, तापमान अस्सी डिग्री", [
        ("सेल्सियस", ("measurement.temperature", "80 °C")), ("फारेनहाइट", ("measurement.temperature", "80 °F")), ("पता नहीं", ("measurement.temperature", "80 unit-unknown")),
        ("बार", None)]),
]:
    case("ambiguous_unit_temp", lang, rep, "ambiguous_unit", ans)

# ---------------- missing value
M = "measurement.temperature"
for lang, rep, ans in [
    ("en", "M-07 is hot, temperature फलाणा degree.", [("eighty five", (M, "85")), ("it was 85", (M, "85")), ("two point five", (M, "2.5")),
                                                       ("I don't know", (M, "unknown")), ("high", None), ("degree", None)]),
    ("mr", "M-07 गरम आहे, तापमान फलाणा डिग्री.", [("ऐंशी", (M, "80")), ("पंचाऐंशी", (M, "85")), ("अडीच", (M, "2.5")), ("माहीत नाही", (M, "unknown")), ("जास्त", None)]),
    ("hi", "M-07 गरम है, तापमान फलाणा डिग्री.", [("अस्सी", (M, "80")), ("पचासी", (M, "85")), ("ढाई", (M, "2.5")), ("पता नहीं", (M, "unknown")), ("ज़्यादा", None)]),
]:
    case("missing_value", lang, rep, "missing_value", ans)

# ---------------- ambiguous time
T = "time"
for lang, rep, ans in [
    ("en", "B-02 stopped at ten thirty", [
        ("morning", (T, "10:30")), ("AM", (T, "10:30")), ("in the morning", (T, "10:30")), ("a m", (T, "10:30")), ("night", (T, "22:30")),
        ("PM", (T, "22:30")), ("evening", (T, "22:30")), ("at night", (T, "22:30")), ("I don't remember", (T, "unknown")), ("don't know", (T, "unknown")),
        ("afternoon", None), ("yesterday", None), ("ten", None)]),
    ("mr", "B-02 बंद पडला, साडेदहा वाजता", [
        ("सकाळी", (T, "10:30")), ("सकाळचे", (T, "10:30")), ("रात्री", (T, "22:30")), ("रात्रीचे", (T, "22:30")), ("संध्याकाळी", (T, "22:30")), ("AM", (T, "10:30")),
        ("पी एम", (T, "22:30")), ("ए एम", (T, "10:30")), ("माहीत नाही", (T, "unknown")), ("लक्षात नाही", (T, "unknown")), ("काल", None)]),
    ("hi", "B-02 बंद हो गया, साढ़े दस बजे", [
        ("सुबह", (T, "10:30")), ("रात", (T, "22:30")), ("रात को", (T, "22:30")), ("शाम", (T, "22:30")), ("सुबह के", (T, "10:30")), ("पता नहीं", (T, "unknown")),
        ("याद नहीं", (T, "unknown")), ("कल", None)]),
]:
    case("ambiguous_time", lang, rep, "ambiguous_time", ans)

# ---------------- missing symptom (answered by describing)
S = "symptom"
for lang, rep, ans in [
    ("en", "B-02", [
        ("it is making noise", ("symptom.noise", "present")), ("there is vibration", ("symptom.vibration", "present")), ("smoke", ("symptom.smoke", "present")),
        ("it is leaking", ("symptom.leakage", "present")), ("it is very hot", ("symptom.heat", "present")), ("it stopped", ("symptom.stopped", "present")),
        ("it tripped", ("symptom.stopped", "present")), ("not working", ("symptom.stopped", "present")), ("it is not running", ("symptom.stopped", "present")),
        ("it is overheating", ("symptom.heat", "present")), ("it overheated", ("symptom.heat", "present")), ("it is broken", ("symptom.broken", "present")),
        ("it broke down", ("symptom.broken", "present")), ("belt is jammed", ("symptom.jammed", "present")), ("there is a burning smell", ("symptom.smell", "present")),
        ("sparks are coming", ("symptom.sparks", "present")), ("it won't start", ("symptom.stopped", "present")), ("making a loud sound", ("symptom.noise", "present")),
        ("water is dripping", ("symptom.leakage", "present")), ("it is shaking", ("symptom.vibration", "present")), ("it is running hot", ("symptom.heat", "present")),
        ("I don't know", None), ("it is fine", None), ("nothing", None)]),
    ("mr", "B-02", [
        ("आवाज येतोय", ("symptom.noise", "present")), ("व्हायब्रेशन आहे", ("symptom.vibration", "present")), ("धूर येतोय", ("symptom.smoke", "present")),
        ("गळतंय", ("symptom.leakage", "present")), ("पाणी गळतंय", ("symptom.leakage", "present")), ("पाणी गळत आहे", ("symptom.leakage", "present")),
        ("खूप गरम झालंय", ("symptom.heat", "present")), ("गरम होतंय", ("symptom.heat", "present")), ("बंद पडलंय", ("symptom.stopped", "present")),
        ("बंद पडलं", ("symptom.stopped", "present")), ("सुरू होत नाही", ("symptom.stopped", "present")), ("चालू होत नाही", ("symptom.stopped", "present")),
        ("तुटलंय", ("symptom.broken", "present")), ("तुटला आहे", ("symptom.broken", "present")), ("जाम झालंय", ("symptom.jammed", "present")),
        ("जळका वास येतोय", ("symptom.smell", "present")), ("ठिणग्या उडतायत", ("symptom.sparks", "present")), ("हादरतंय", ("symptom.vibration", "present")),
        ("माहीत नाही", None), ("ठीक आहे", None)]),
    ("hi", "B-02", [
        ("आवाज़ आ रही है", ("symptom.noise", "present")), ("शोर हो रहा है", ("symptom.noise", "present")), ("कंपन हो रहा है", ("symptom.vibration", "present")),
        ("धुआं निकल रहा है", ("symptom.smoke", "present")), ("लीक हो रहा है", ("symptom.leakage", "present")), ("पानी रिस रहा है", ("symptom.leakage", "present")),
        ("बहुत गरम हो गया है", ("symptom.heat", "present")), ("गरम हो रहा है", ("symptom.heat", "present")), ("बंद हो गया", ("symptom.stopped", "present")),
        ("चालू नहीं हो रहा", ("symptom.stopped", "present")), ("टूट गया है", ("symptom.broken", "present")), ("खराब हो गया है", ("symptom.broken", "present")),
        ("जाम हो गया", ("symptom.jammed", "present")), ("जलने की बदबू आ रही है", ("symptom.smell", "present")), ("चिंगारी निकल रही है", ("symptom.sparks", "present")),
        ("पता नहीं", None), ("सब ठीक है", None)]),
]:
    case("missing_symptom", lang, rep, "missing_symptom", ans)

# ---------------- urgency (answered last)
U = "urgency"
for lang, rep, ans in [
    ("en", "B-02 stopped, smoke", [("it can wait", (U, "can_wait")), ("today", (U, "today")), ("needs attention today", (U, "today")),
                                    ("stop the line", (U, "stop_work")), ("stop work now", (U, "stop_work")), ("emergency", (U, "emergency")),
                                    ("not sure", (U, "unknown")), ("not urgent", (U, "can_wait")), ("very urgent", None), ("hmm", None)]),
    ("mr", "B-02 बंद पडला, धूर", [("थांबू शकतं", (U, "can_wait")), ("आज लक्ष द्यावं लागेल", (U, "today")), ("काम बंद करा", (U, "stop_work")),
                                   ("आणीबाणी", (U, "emergency")), ("माहीत नाही", (U, "unknown")), ("अर्जंट आहे", None)]),
    ("hi", "B-02 बंद हो गया, धुआं", [("रुक सकता है", (U, "can_wait")), ("आज ध्यान देना होगा", (U, "today")), ("काम रोक दो", (U, "stop_work")),
                                      ("इमरजेंसी", (U, "emergency")), ("पता नहीं", (U, "unknown")), ("बहुत ज़रूरी है", None)]),
]:
    # urgency is last: the report first needs no other blocker
    case("missing_urgency", lang, rep, "missing_urgency", ans)

# ---------------- wrong-KIND unit stated in the report itself (must be asked, not silently accepted)
for lang, rep, want_q in [
    ("en", "B-02 stopped, temperature eighty PSI", "missing_unit"), ("en", "B-02 stopped, pressure eighty celsius", "missing_unit"),
    ("en", "B-02 stopped, speed sixty bar", "missing_unit"), ("mr", "B-02 बंद पडला, तापमान ऐंशी PSI", "missing_unit"),
    ("mr", "B-02 बंद पडला, प्रेशर साठ सेल्सिअस", "missing_unit"), ("hi", "B-02 बंद हो गया, तापमान अस्सी बार", "missing_unit"),
]:
    case("wrong_kind_unit", lang, rep, want_q, [])
