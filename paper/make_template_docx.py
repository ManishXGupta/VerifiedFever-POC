"""Build the VerifiedFever paper inside an existing IEEE conference Word template.

The template's own styles, page setup, author block layout, numbered Heading 1 sections,
small-caps table captions, table borders and reference formatting are reused; only the
content is replaced. All numbers are read from experiments/results/*.json and
paper/generated/numbers.tex (rerun the experiments first).

Usage:  python paper/make_template_docx.py TEMPLATE.docx OUTPUT.docx
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
FIG = ROOT / "docs" / "figures"

N = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", (ROOT / "paper/generated/numbers.tex").read_text()))
N = {k: v.replace("--", "\u2013") for k, v in N.items()}
syn = json.loads((RES / "synthetic_results.json").read_text())
ob = json.loads((RES / "outbreak_results.json").read_text())
cost = json.loads((RES / "cost_results.json").read_text())
tam = json.loads((RES / "tamper_results.json").read_text())

COL_PT = 243.0  # column width of the template's two-column body
RF = '<w:rFonts w:eastAsia="Times New Roman"/>'


# ---------------------------------------------------------------- runs with mini markup
def runs(text: str, size: int | None = None, bold=False, italic=False) -> str:
    """{Macro} numbers, *italic*, _{sub}, ^{sup}, [[red placeholder]]."""
    text = re.sub(r"\{(\w+)\}", lambda m: N.get(m.group(1), m.group(0)), text)
    out = []
    for part in re.split(r"(\*[^*]+\*|_\{[^}]+\}|\^\{[^}]+\}|\[\[[^\]]+\]\])", text):
        if not part:
            continue
        rpr, t = [RF], part
        if bold:
            rpr.append("<w:b/><w:bCs/>")
        if italic:
            rpr.append("<w:i/><w:iCs/>")
        if part.startswith("*") and part.endswith("*") and len(part) > 2:
            rpr.append("<w:i/><w:iCs/>"); t = part[1:-1]
        elif part.startswith("_{"):
            rpr.append('<w:vertAlign w:val="subscript"/>'); t = part[2:-1]
        elif part.startswith("^{"):
            rpr.append('<w:vertAlign w:val="superscript"/>'); t = part[2:-1]
        elif part.startswith("[["):
            rpr.append('<w:color w:val="C00000"/>'); t = part[2:-2]
        if size:
            rpr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
        out.append(f'<w:r><w:rPr>{"".join(rpr)}</w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r>')
    return "".join(out)


def body(text):
    return ('<w:p><w:pPr><w:spacing w:line="11.40pt" w:lineRule="auto"/><w:ind w:firstLine="10.10pt"/>'
            f'<w:jc w:val="both"/></w:pPr>{runs(text)}</w:p>')


def center(text):
    return f'<w:p><w:pPr><w:spacing w:before="3pt" w:after="3pt"/><w:jc w:val="center"/></w:pPr>{runs(text)}</w:p>'


def h1(text):
    return ('<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="4"/></w:numPr>'
            '<w:tabs><w:tab w:val="clear" w:pos="28.80pt"/></w:tabs><w:ind w:start="25.05pt" w:hanging="18pt"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve"> {escape(text)}</w:t></w:r></w:p>')


def h2(text):
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="5pt" w:after="2pt"/><w:jc w:val="start"/></w:pPr>'
            f'<w:r><w:rPr>{RF}<w:i/><w:iCs/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')


def caption_table(num, title):
    a = ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="6pt"/><w:jc w:val="center"/></w:pPr>'
         f'<w:r><w:rPr>{RF}<w:smallCaps/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t>Table {num}</w:t></w:r></w:p>')
    b = ('<w:p><w:pPr><w:keepNext/><w:spacing w:after="3pt"/><w:jc w:val="center"/></w:pPr>'
         f'<w:r><w:rPr>{RF}<w:smallCaps/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t>{escape(title)}</w:t></w:r></w:p>')
    return a + b


def note(text):
    return f'<w:p><w:pPr><w:spacing w:before="2pt" w:after="6pt"/></w:pPr>{runs(text, size=14)}</w:p>'


def table(header, rows, widths_pt):
    total = sum(widths_pt)
    grid = "".join(f'<w:gridCol w:w="{round(w * 20)}"/>' for w in widths_pt)
    nrows = len(rows) + 1

    def cell(text, i, r):
        top = "single" if r == 0 else "none"
        bot = "single" if r in (0, nrows - 1) else "none"
        b = text.startswith("!")
        text = text[1:] if b else text
        jc = "start" if i == 0 else "center"
        bd = (f'<w:top w:val="{top}" w:sz="{4 if top == "single" else 0}" w:space="0" w:color="{"000000" if top == "single" else "FFFFFF"}"/>'
              '<w:start w:val="none" w:sz="0" w:space="0" w:color="FFFFFF"/>'
              f'<w:bottom w:val="{bot}" w:sz="{4 if bot == "single" else 0}" w:space="0" w:color="{"000000" if bot == "single" else "FFFFFF"}"/>'
              '<w:end w:val="none" w:sz="0" w:space="0" w:color="FFFFFF"/>')
        return (f'<w:tc><w:tcPr><w:tcW w:w="{widths_pt[i]}pt" w:type="dxa"/><w:tcBorders>{bd}</w:tcBorders>'
                '<w:tcMar><w:top w:w="1pt" w:type="dxa"/><w:start w:w="2.50pt" w:type="dxa"/><w:bottom w:w="1pt" w:type="dxa"/>'
                '<w:end w:w="2.50pt" w:type="dxa"/></w:tcMar><w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:jc w:val="{jc}"/></w:pPr>{runs(text, size=14, bold=(r == 0 or b))}</w:p></w:tc>')

    trs = "".join('<w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/></w:trPr>'
                  + "".join(cell(c, i, r) for i, c in enumerate(row)) + "</w:tr>"
                  for r, row in enumerate([header] + rows))
    return ('<w:tbl><w:tblPr>' f'<w:tblW w:w="{total}pt" w:type="dxa"/><w:jc w:val="center"/>'
            '<w:tblCellMar><w:start w:w="0.50pt" w:type="dxa"/><w:end w:w="0.50pt" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
            f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{trs}</w:tbl>')


FIGS: list[tuple[str, str]] = []  # (rId, file)


def figure(file, caption, width_pt=COL_PT):
    from PIL import Image
    w, h = Image.open(FIG / file).size
    cx = int(width_pt * 12700); cy = int(cx * h / w)
    rid = f"rIdVF{len(FIGS) + 1}"
    FIGS.append((rid, file))
    n = len(FIGS)
    drawing = (f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
               f'<wp:docPr id="{100 + n}" name="Figure {n}" descr="{escape(caption)}"/>'
               '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://purl.oclc.org/ooxml/drawingml/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
               '<a:graphic xmlns:a="http://purl.oclc.org/ooxml/drawingml/main"><a:graphicData uri="http://purl.oclc.org/ooxml/drawingml/picture">'
               '<pic:pic xmlns:pic="http://purl.oclc.org/ooxml/drawingml/picture"><pic:nvPicPr>'
               f'<pic:cNvPr id="{n}" name="{escape(file)}"/><pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>'
               f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
               f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
               '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>')
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="6pt"/><w:jc w:val="center"/></w:pPr>'
            f'<w:r><w:rPr><w:noProof/></w:rPr>{drawing}</w:r></w:p>'
            f'<w:p><w:pPr><w:spacing w:after="6pt"/><w:jc w:val="both"/></w:pPr>{runs(f"Fig. {n}. " + caption, size=16)}</w:p>')


def ref(i, text):
    return ('<w:p><w:pPr><w:tabs><w:tab w:val="start" w:pos="18pt"/></w:tabs><w:spacing w:after="1pt"/>'
            '<w:ind w:start="18pt" w:hanging="18pt"/><w:jc w:val="both"/></w:pPr>'
            f'<w:r><w:rPr>{RF}<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t>[{i}]</w:t></w:r>'
            f'<w:r><w:rPr>{RF}<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:tab/></w:r>{runs(text, size=16)}</w:p>')


# ---------------------------------------------------------------- content
TITLE = ("Verified Fever, No Appointment: An IoT Portable Thermometer for Automated Digital Absence "
         "Certification and Early Outbreak Alerts in Schools")
ABSTRACT = ("Many schools require a doctor\u2019s note after a few illness absences, so families visit a clinic for a mild "
            "fever only to obtain paperwork. We present a sensor-to-certificate system in which a registered portable "
            "thermometer signs each daily reading, a verifier rejects altered, replayed, delayed or foreign readings, and "
            "a rule engine compares each reading with the student\u2019s own baseline and the school\u2019s cutoff. A nurse "
            "or physician validates the resulting certificate in one click; the parent shares it directly with the school "
            "by code, QR or signed file, and the school verifies it offline and sees only dates and status. The same "
            "verified daily readings feed class- and school-level outbreak alerts. In simulation, the personal-baseline "
            "rule raised fever-day sensitivity for students with low normal temperatures from {SensFixedLow} to "
            "{SensPersLow} at {FCPers} false certificates per 1000 student-days. In 480-student school terms, "
            "verified-fever surveillance detected {ObDetPers}% of influenza outbreaks within 21 days, a median "
            "{ObLeadAbs} days before absenteeism and {ObLeadConf} days before confirmed-case reports. All {NAttacks} "
            "scripted attacks were detected. Each avoided note-only visit saves about ${CostVisitBase} at 2026 prices "
            "and wages.")
KEYWORDS = ("Internet of Things, body temperature sensing, digital signatures, verifiable credentials, school health, "
            "syndromic surveillance, outbreak detection")

S = syn["summary"]
f3 = lambda x: f"{x:.3f}"  # noqa: E731


def content() -> str:
    x = []
    x.append(h1("Introduction"))
    x.append(body("The 2025\u201326 influenza season hit children hard: in January 2026, children under 18 had the highest peak weekly influenza hospitalization rate observed since 2010\u201311 [1], and their cumulative rate was the second highest since then by March [2]. Schools sit at the center of this burden, yet their attendance rules push families toward clinics for mild illness. Mississippi, for example, now requires medical documentation after a student\u2019s third illness-related absence [3]. A note-only visit costs the visit itself (an average of $220 at urgent care and $224 in primary care [4]), plus a parent\u2019s time, travel and possibly lost pay; about half of lower-income working parents would be highly worried about losing pay to care for a sick child [5]. Time spent seeking care is a recognized economic burden [6], and virtual pediatric care has shown large savings when travel is avoided [7]."))
    x.append(body("Two gaps keep home thermometers out of this loop. First, a consumer reading is not evidence: a typed or edited value looks like a measured one, which is why authenticated sensor provenance is an active topic in medical IoT [8]. Second, fever is usually judged with one fixed cutoff, although normal temperature varies from person to person [9], and wearable temperature studies already use statistical outlier detection alongside fixed thresholds [10]. Meanwhile, school-based influenza surveillance still relies largely on absenteeism data [11], which mixes illness with every other reason a child stays home."))
    x.append(body("This paper makes four contributions: 1) a registered-thermometer evidence format and verifier; 2) a personal-baseline fever rule that keeps the school\u2019s cutoff; 3) a clinician-validated certificate that the family shares directly with the school, in the spirit of verifiable credentials [12], with minimum disclosure; and 4) cohort surveillance on the same verified daily readings, evaluated against absenteeism and confirmed-case reporting. We also quantify cost and time savings and release an open-source proof of concept."))
    x.append(figure("graphical_abstract_column.png", "Overview. A signed home reading becomes a nurse-validated absence certificate that the parent shares directly with the school, and an input to early outbreak alerts. Headline numbers are from Section IV."))

    x.append(h1("System Design"))
    x.append(body("Fig. 2 shows the architecture and Fig. 3 the user interface of the proof of concept."))
    x.append(h2("A. Registered Thermometer, Verifier and Rule"))
    x.append(body("At enrollment, with parental consent, the school registers a device ID and the device\u2019s Ed25519 public key against one student; the device never sees the student\u2019s identity. Each reading {*device_id*, *seq*, *ts*, *T*, *site*, *nonce*} is canonical JSON, signed ({ReadingBytes} bytes). A reading is accepted only if the device is enrolled and active, any claimed student matches, the signature verifies, *seq* increases (anti-replay), *ts* is fresh (at most 6 h old, 5 min skew) and 34 \u2264 *T* \u2264 43 \u00b0C. The baseline *B* is the median of the last 14 accepted readings below 37.5 \u00b0C (default 36.8 \u00b0C until five exist). A reading is febrile if"))
    x.append(center("*T* \u2265 *T*_{fix}  \u2228  (*T* \u2265 *T*_{floor}  \u2227  *T* \u2212 *B* \u2265 \u0394)        (1)"))
    x.append(body("with the school cutoff *T*_{fix} = 38.0 \u00b0C always honoured, *T*_{floor} = 37.5 \u00b0C and \u0394 = 1.0 \u00b0C. Fever at or above 39.5 \u00b0C, or on a third consecutive day, goes to clinical review instead of certification."))
    x.append(figure("architecture_column.png", "Architecture. Green arrows: the approved certificate returns to the parent\u2019s wallet and is shared directly with the school. Dashed: daily flags feed cohort surveillance.", width_pt=215))
    x.append(h2("B. Certificate, Validation and Direct Sharing"))
    x.append(body("A febrile reading creates or extends a certificate (fever day plus a 24 h fever-free period) holding the student ID, dates, status, validator and a SHA-256 digest of the signed evidence; the service signs it and re-signs it on every change. After one-click validation by a nurse or physician, the certificate appears in the parent\u2019s wallet. The parent shares it with a short code or QR, or as a signed file. The school portal accepts it only if the issuer signature verifies, the status is approved, the record still matches the issuer (not revoked or superseded), the code is unexpired and the student is enrolled; a duplicate is recognized. The school sees the reason (fever-related absence), dates and status, never temperatures."))
    x.append(figure("ui_column.png", "Proof-of-concept screens: (a) a signed reading of 37.6 \u00b0C is +1.3 \u00b0C above this student\u2019s baseline, so a certificate is created although a 38.0 \u00b0C rule would not flag it; (b) the parent shares the approved certificate by code or QR; (c) nurse validation; (d) the school verifies and accepts it."))
    x.append(h2("C. Cohort Surveillance"))
    x.append(body("Each morning, the count of verified febrile students per class and per school is monitored with a one-sided CUSUM against a trailing 28-day baseline (3-day guard band) and a class-level count threshold; an alert goes to the school nurse and public health, without disclosing individual temperatures."))

    x.append(h1("Evaluation"))
    x.append(body("All experiments were rerun for this version from the open-source code; every value in Tables I\u2013IV is generated from the saved results."))
    x.append(h2("A. Individual Fever Detection"))
    x.append(body("We simulated 500 students for 90 days: normal temperature N(36.7, 0.25^{2}) \u00b0C clipped to [36.0, 37.4], day-to-day noise 0.15 \u00b0C, measurement noise 0.10 \u00b0C, 0.1 \u00b0C display rounding, fever episodes of 1\u20133 days raising temperature 1.0\u20132.5 \u00b0C above a student\u2019s own normal, and 0.3\u20130.8 \u00b0C transient rises on 3% of other days. The baseline was computed causally ({NSeeds} seeds)."))
    rows = []
    for k, label in (("fixed38", "Fixed 38.0 \u00b0C"), ("fixed37.5", "Fixed 37.5 \u00b0C"), ("personal", "!Personal (ours)")):
        v = S["overall"][k]
        rows.append([label, f3(v["sensitivity"][0]), f3(S["by_baseline"][k]["low"]["sensitivity"][0]),
                     f"{v['specificity'][0]:.4f}", f3(v["ppv"][0]), f3(v["f1"][0]), f"{v['false_cert_per_1000'][0]:.1f}"])
    x.append(caption_table("I", f"Fever-Day Detection (Mean of {syn['n_seeds']} Seeds)"))
    x.append(table(["Rule", "Sens.", "Sens. low", "Spec.", "PPV", "F1", "FC"], rows, [62, 28, 32, 34, 28, 28, 24]))
    x.append(note(f"{S['days_eval']:,} student-days per seed after warm-up. Sens. low: lowest tertile of normal temperature. FC: false certificates per 1000 student-days."))
    x.append(body("The fixed 38.0 \u00b0C rule missed many fever days in students with low normal temperatures (Table I, Fig. 4). The personal rule recovered most of them, raising episode detection from {EpiFixed}% to {EpiPers}% while adding less than one false certificate per 1000 student-days; a 37.5 \u00b0C cutoff reached similar sensitivity at {FCLow} false certificates. Across nine settings of inter-individual spread (0.15\u20130.35 \u00b0C) and noise (0.05\u20130.20 \u00b0C), personal-rule sensitivity stayed at {SensRangePers} (fixed 38.0 \u00b0C: {SensRangeFixed})."))
    x.append(figure("results.png", "Individual detection. (a) Fever-day sensitivity by tertile of normal temperature. (b) False certificates per 1000 student-days."))

    x.append(h2("B. Early Outbreak Detection"))
    x.append(body("Each simulated term had 480 students in 20 classes over 120 school days, with background non-influenza fevers, ordinary absences (4.5% with school-wide day effects) and readings on 85% of mornings. In outbreak terms one student was infected between days 30 and 90, and influenza spread within classes and across the school by attendance; 75% of cases were febrile, and 85% of febrile children stayed home. Of 400 outbreak terms, {ObFizzled} fizzled (fewer than five symptomatic cases) and were excluded; the remaining {ObTerms} had a median of {ObSize} symptomatic cases (IQR {ObSizeQone}\u2013{ObSizeQthree}). Confirmed cases required care seeking (40%), testing (50%) and a 3\u20136 day reporting delay. Each signal\u2019s detector was tuned on separate calibration terms so that at most 10% of outbreak-free terms raised a false alert."))
    names = {"VF-personal": "!Verified fever, personal", "VF-fixed": "Verified fever, 38.0 \u00b0C",
             "Confirmed": "Confirmed-case reports", "Absence": "All-cause absence"}
    orows = []
    for k, label in names.items():
        v = ob["summary"][k]
        orows.append([label, f"{100 * v['detection_rate']:.0f}%", f"{v['delay_median']:.0f} ({v['delay_q1']:.0f}\u2013{v['delay_q3']:.0f})",
                      f"{v['cases_at_alert_median']:.0f}", f"{100 * v['false_alarm_terms']:.0f}%"])
    x.append(caption_table("II", "School Influenza Outbreak Detection"))
    x.append(table(["Signal", "Detected", "Delay, d", "Cases", "False alarm"], orows, [80, 36, 44, 28, 40]))
    x.append(note(f"{ob['n_eval_outbreak_terms']} outbreak and {ob['n_eval_null_terms']} outbreak-free terms. Detected: within {ob['detect_window_days']} days of the first symptomatic case. Delay: median (IQR) days from that case. Cases: median symptomatic cases by the alert day. False alarm: share of outbreak-free terms with any alert."))
    x.append(body("Verified-fever surveillance detected the most outbreaks and the earliest (Table II, Fig. 5): a median {ObDelayPers} days after the first symptomatic case, when about {ObCasesPers} children had fallen ill, versus {ObDelayConf} days and {ObCasesConf} cases for confirmed reports. Absenteeism detected only {ObDetAbs}%, because ordinary absences mask the outbreak signal. Among outbreaks detected by both, verified fever alerted a median {ObLeadAbs} days before absenteeism (n = {ObPairsAbs}) and {ObLeadConf} days before confirmed reports (n = {ObPairsConf}). Using the personal rule rather than a fixed 38.0 \u00b0C cutoff raised detection from {ObDetFixed}% to {ObDetPers}%."))
    x.append(figure("outbreak.png", "Cumulative share of school influenza outbreaks detected by days after the first symptomatic case, at matched false-alarm rates."))

    x.append(h2("C. Cost and Time Savings"))
    x.append(body("Table III combines the average urgent care price [4], the May 2026 average hourly wage of $37.53 [13] and the 2026 vehicle rate of $0.76 per mile [14] with stated time and distance assumptions. Each avoided note-only visit saves about ${CostVisitLow}\u2013${CostVisitHigh} (base ${CostVisitBase}); for a 500-student school where 20% of students would otherwise make one such visit a year, that is about ${CostSchoolBase} and {HoursSchoolBase} parent hours a year, and the thermometers pay back in {PaybackBase} years."))
    m = lambda v: f"${round(v):,}"  # noqa: E731
    C = lambda k: cost[k]  # noqa: E731
    ks = ("low", "base", "high")
    crow = [["Visit price"] + [m(C(k)["per_visit"]["visit_price"]) for k in ks],
            ["Parent time (h)"] + [f"{C(k)['per_visit']['parent_hours_saved']:.1f}" for k in ks],
            ["Parent time value"] + [m(C(k)["per_visit"]["parent_time_cost"]) for k in ks],
            ["Travel"] + [m(C(k)["per_visit"]["travel"]) for k in ks],
            ["!Net saving per visit"] + ["!" + m(C(k)["per_visit"]["net_saving"]) for k in ks],
            ["Visits avoided\u2020"] + [f"{C(k)['per_school_year']['visits_avoided']:.0f}" for k in ks],
            ["!Annual saving\u2020"] + ["!" + m(C(k)["per_school_year"]["annual_net_saving"]) for k in ks],
            ["Parent hours saved\u2020"] + [f"{C(k)['per_school_year']['parent_hours_saved']:.0f}" for k in ks],
            ["Thermometer payback (yr)"] + [f"{C(k)['per_school_year']['payback_years']:.1f}" for k in ks]]
    x.append(caption_table("III", "Savings When a Verified Certificate Replaces a Note-Only Visit"))
    x.append(table(["", "Low", "Base", "High"], crow, [100, 40, 40, 40]))
    x.append(note("\u2020Per 500-student school per year, with 10/20/30% of students otherwise making one note-only visit. Net of 3 min nurse review; $30 thermometer per student. Wage $37.53/h, vehicle $0.76/mile."))

    x.append(h2("D. Tamper Evidence and Timing"))
    trows = [[name, v["expected_check"], f"{v['detected']}/{v['trials']}"] for name, v in tam["attacks"].items()]
    g = tam["genuine"]
    trows.append(["!Genuine readings (accepted)", "\u2013", f"!{g['accepted']}/{g['submitted']}"])
    x.append(body(f"We enrolled 50 virtual thermometers, submitted {g['submitted']} genuine readings and ran 200 trials of each attack in Table IV. Every attack was rejected by the intended check and every genuine reading was accepted; altered shared files were also refused by the school. Median times on a commodity x86-64 machine were {{SignMs}} ms to sign a reading, {{VerifyMs}} ms to verify a signature and {{EtoEMs}} ms (95th percentile {{EtoEPms}} ms) from receiving a reading to issuing a certificate."))
    x.append(caption_table("IV", "Tamper-Evidence Tests"))
    x.append(table(["Attack", "Caught by", "Detected"], trows, [130, 70, 40]))
    x.append(note("Fifty enrolled virtual thermometers; 200 trials per attack."))

    x.append(h1("Limitations and Conclusion"))
    x.append(body("Detection and outbreak results come from simulation and depend on stated assumptions; savings depend on local prices and policies. Signatures prove a reading came unaltered from an enrolled device, not that the probe was used correctly or not warmed; fever-reducing medicine can mask fever; the proof-of-concept key must move into a secure element; and the system documents fever and does not diagnose it."))
    x.append(body("Within these limits, a registered thermometer turns a routine home measurement into a verifiable certificate that families share directly with schools, saves a clinic visit, and provides an outbreak signal days earlier than existing school data. Next steps are the bench test, Bluetooth firmware signing on a commercial thermometer and a pilot with school nurses. Code, data and the demo are available at https://github.com/ManishXGupta/VerifiedFever-POC."))
    x.append('<w:p><w:pPr><w:keepNext/><w:spacing w:before="8pt" w:after="4pt"/><w:jc w:val="center"/></w:pPr>'
             f'<w:r><w:rPr>{RF}<w:smallCaps/></w:rPr><w:t>References</w:t></w:r></w:p>')
    refs = [
        "Centers for Disease Control and Prevention, \u201cWeekly US influenza surveillance report: Key updates for week 2, ending January 17, 2026,\u201d FluView, Jan. 2026.",
        "Centers for Disease Control and Prevention, \u201cWeekly US influenza surveillance report: Key updates for week 10, ending March 14, 2026,\u201d FluView, Mar. 2026.",
        "WLOX News, \u201cMississippi attendance law brings new rules for student absences,\u201d Sep. 16, 2026 (Mississippi Senate Bill 2103).",
        "Health Care Cost Institute, \u201cUrgent care spending increased by 50% over 5 years driven by higher use,\u201d Jan. 28, 2026.",
        "R. Minkin, L. Lin, D. Braga, and K. Hurst, \u201cFor working parents, the boundary between work and family is often blurred,\u201d Pew Research Center, Jun. 16, 2026.",
        "Sollis Health, \u201cThe real cost of healthcare for Americans: 2026 health trend report,\u201d industry report, Sep. 2026.",
        "E. Lim, J. Strychowsky, A. C. Gunz, and S. Belisle, \u201cSustainability in quality improvement: Outcomes of a novel pediatric virtual urgent care in Ontario, Canada,\u201d *West. J. Emerg. Med.*, vol. 27, no. 5, 2026, doi: 10.5811/westjem.54076.",
        "V. Shukla, V. Shukla, Atul, D. Mishra, and M. K. Das, \u201cASCON-based lightweight cryptographic provenance for distinguishing physiological events, sensor faults, and cyberattacks in IoMT,\u201d Cryptology ePrint Archive, Paper 2026/1929, Sep. 2026.",
        "D. M. Consolini, \u201cFever in infants and children,\u201d *Merck Manual Consumer Version*, last updated May 2026.",
        "Y. Liu, Q. Zhao, K. Li, and D. Dowding, \u201cContinuous temperature monitoring via wearable devices for fever or infection management in acute care hospitals: Scoping review of clinical implementation and data analytics,\u201d *JMIR mHealth uHealth*, vol. 14, art. e89773, 2026, doi: 10.2196/89773.",
        "V. Joshy, Z. Feng, L. Deeth, K. Vanderkruk, and J. Slater, \u201cDESA: An R package for detecting epidemics using a school-absenteeism surveillance framework,\u201d *J. Open Res. Softw.*, vol. 14, art. 11, Feb. 2026, doi: 10.5334/jors.634.",
        "W3C Verifiable Credentials Working Group, \u201cVerifiable credentials overview,\u201d W3C Group Note, Jun. 17, 2026.",
        "U.S. Bureau of Labor Statistics, \u201cThe employment situation: May 2026,\u201d USDL-26-0786, Jun. 5, 2026.",
        "Internal Revenue Service, \u201cOptional standard mileage rates,\u201d Announcement 2026-11, Jul. 2026.",
    ]
    x += [ref(i + 1, r) for i, r in enumerate(refs)]
    return "".join(x)


# ---------------------------------------------------------------- assemble
def main(template: str, output: str):
    tmp = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(template) as z:
        z.extractall(tmp)
    docp = tmp / "word" / "document.xml"
    x = docp.read_text(encoding="utf8")
    head, rest = x.split("<w:body>", 1)
    items = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", rest, re.S)
    final_sect = re.search(r"<w:sectPr(?:(?!<w:sectPr).)*?</w:sectPr>\s*</w:body>", rest, re.S).group(0)
    final_sect = final_sect.replace("</w:body>", "")
    texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in items]
    i_intro = next(i for i, t in enumerate(texts) if "Introduction" in t and "Heading1" in items[i])
    front = items[:i_intro]

    # title (paragraph 0): replace text, keep formatting
    front[0] = re.sub(r"(<w:t[^>]*>)[^<]*(</w:t>)", lambda m: m.group(1) + escape(TITLE) + m.group(2), front[0], count=1)
    # abstract and keywords: rebuild runs, keep paragraph properties
    for k, p in enumerate(front):
        if 'w:val="Abstract"' in p:
            ppr = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S).group(0)
            front[k] = (f"<w:p>{ppr}<w:r><w:rPr><w:i/><w:iCs/></w:rPr><w:t>Abstract</w:t></w:r><w:r><w:t>\u2014</w:t></w:r>"
                        f"{runs(ABSTRACT)}</w:p>").replace(RF, "")
        if 'w:val="Keywords"' in p:
            ppr = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S).group(0)
            front[k] = f"<w:p>{ppr}<w:r><w:t>Keywords\u2014</w:t></w:r>{runs(KEYWORDS)}</w:p>".replace(RF, "")

    new_body = "".join(front) + content() + final_sect
    docp.write_text(head + "<w:body>" + new_body + "</w:body></w:document>", encoding="utf8")

    # media + relationships
    media = tmp / "word" / "media"
    for old in media.glob("*"):
        old.unlink()
    rels = tmp / "word" / "_rels" / "document.xml.rels"
    r = rels.read_text(encoding="utf8")
    r = re.sub(r'<Relationship Id="[^"]+" Type="[^"]+/image" Target="media/[^"]+"/>', "", r)
    add = ""
    for rid, f in FIGS:
        shutil.copy(FIG / f, media / f)
        add += f'<Relationship Id="{rid}" Type="http://purl.oclc.org/ooxml/officeDocument/relationships/image" Target="media/{f}"/>'
    rels.write_text(r.replace("</Relationships>", add + "</Relationships>"), encoding="utf8")

    out = Path(output)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        ct = tmp / "[Content_Types].xml"
        z.write(ct, "[Content_Types].xml")
        for f in sorted(tmp.rglob("*")):
            if f.is_file() and f != ct:
                z.write(f, f.relative_to(tmp).as_posix())
    print("wrote", out, "with", len(FIGS), "figures")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
