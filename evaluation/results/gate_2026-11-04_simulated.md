# Gate test 2026-11-04

Clips through Prisma (files with _sim- are synthetic-noise variants of the human recordings). 'sim' = rough text similarity to what was said (1.00 = identical), not WER.

## HE1_sim-fan10.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: C-04 compressor trip हो गया, दस बजकर तीस मिनट पर. Pressure पंद्रह... नहीं, पचास PSI था.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | hi-IN | 1.00 | C-04 compressor trip हो गया। दस बजकर तीस मिनट पर pressure पंद्रह नहीं, पचास PSI था। | PASS correction (got [(15, 50)]); PASS correction unit (got PSI); PASS time (got (10, 30, 'needs_clarification')) |

## HE1_sim-fan5.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: C-04 compressor trip हो गया, दस बजकर तीस मिनट पर. Pressure पंद्रह... नहीं, पचास PSI था.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | hi-IN | 1.00 | C-04 compressor trip हो गया। दस बजकर तीस मिनट पर pressure पंद्रह नहीं, पचास PSI था। | PASS correction (got [(15, 50)]); PASS correction unit (got PSI); PASS time (got (10, 30, 'needs_clarification')) |

## HE1_sim-phone.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: C-04 compressor trip हो गया, दस बजकर तीस मिनट पर. Pressure पंद्रह... नहीं, पचास PSI था.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | None | 0.00 |  | FAIL correction (got []); FAIL time (got None) |

## HE3_sim-fan10.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 का temperature अस्सी है, और थोड़ी आवाज़ आ रही है.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | hi-IN | 1.00 | P-12 का temperature अस्सी है और थोड़ी आवाज आ रही है। | PASS quantity (got [(80, None)]) |

## HE3_sim-fan5.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 का temperature अस्सी है, और थोड़ी आवाज़ आ रही है.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | hi-IN | 0.91 | fuel का temperature अस्सी है और थोड़ी आवाज आ रही है। | PASS quantity (got [(80, None)]) |

## HE3_sim-phone.wav  (hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 का temperature अस्सी है, और थोड़ी आवाज़ आ रही है.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | hi-IN | 0.91 | fuel का temperature अस्सी है और थोड़ी आवाज आ रही है। | PASS quantity (got [(80, None)]) |

## ME1_sim-fan10.wav  (mr-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 pump बंद पडला आहे, सकाळी साडेदहा वाजता. Vibration खूप होतं. Pressure पंधरा... नाही, पन्नास होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 1.00 | P-12 pump बंद पडला आहे. सकाळी साडेदहा वाजता vibration खूप होतो. pressure पंधरा नाही, पन्नास होतं. | PASS correction (got [(15, 50)]); PASS correction unit (got None); PASS time (got (10, 30, 'resolved')) |

## ME1_sim-fan5.wav  (mr-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 pump बंद पडला आहे, सकाळी साडेदहा वाजता. Vibration खूप होतं. Pressure पंधरा... नाही, पन्नास होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 1.00 | P-12 pump बंद पडला आहे. सकाळी साडेदहा वाजता vibration खूप होतं. pressure पंधरा नाही, पन्नास होतं. | PASS correction (got [(15, 50)]); PASS correction unit (got None); PASS time (got (10, 30, 'resolved')) |

## ME1_sim-phone.wav  (mr-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 pump बंद पडला आहे, सकाळी साडेदहा वाजता. Vibration खूप होतं. Pressure पंधरा... नाही, पन्नास होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.98 | P-12 pump बंद पडला आहे. सकाळी साडेदहा वाजता vibration होत होतं. pressure पंधरा नाही, पन्नास होतं. | PASS correction (got [(15, 50)]); PASS correction unit (got None); PASS time (got (10, 30, 'resolved')) |

## MHE1_sim-fan10.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 बंद पडला, pressure पंधरा... नहीं, पन्नास PSI. खाली पाणी निकल रहा है, पण कहाँ से ते माहीत नाही.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.93 | twelve बंद पडला, pressure पंधरा नाही, पन्नास PSI खाली पाणी निकल रहा आहे, पण कहा सेतू माहीत नाही. | PASS correction (got [(15, 50)]); PASS correction unit (got PSI) |

## MHE1_sim-fan5.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 बंद पडला, pressure पंधरा... नहीं, पन्नास PSI. खाली पाणी निकल रहा है, पण कहाँ से ते माहीत नाही.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.89 | valve बंद पडला, pressure बनला नाही. पन्नास PSI खाली पाणी निकल रहा आहे, पण कहा सेतू माहीत नाही. | FAIL correction (got []) |

## MHE1_sim-phone.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: P-12 बंद पडला, pressure पंधरा... नहीं, पन्नास PSI. खाली पाणी निकल रहा है, पण कहाँ से ते माहीत नाही.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | None | 0.00 |  | FAIL correction (got []) |

## MHE2_sim-fan10.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: M-07 motor ला heat येत होती, मग मी बंद किया. Temperature साठ डिग्री होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.88 | M-07 meterला heat येत होती, मग मी बंद किया. temperature साठ degree होतं. | PASS quantity (got [(60, 'degree')]) |

## MHE2_sim-fan5.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: M-07 motor ला heat येत होती, मग मी बंद किया. Temperature साठ डिग्री होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.81 | seven meterला heat येत होती, मग मी बंद किया. temperature साठ degree होतं. | PASS quantity (got [(7, None), (60, 'degree')]) |

## MHE2_sim-phone.wav  (mr-hi-en)  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**
said: M-07 motor ला heat येत होती, मग मी बंद किया. Temperature साठ डिग्री होतं.

| setting | detected | sim | transcript | checks |
|---|---|---|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | mr-IN | 0.81 | seven meterला heat येत होती, मग मी बंद किया. temperature साठ degree होतं. | PASS quantity (got [(7, None), (60, 'degree')]) |

## Normaliser checks passed per setting

| config | passed / checked |
|---|---|
| codemix+keyterms / mr-IN,hi-IN,en-IN | 23 / 27 |

Clips: 15. Model: prisma-v3.0. Variants: codemix+keyterms. Small sample; read transcripts yourself before deciding.