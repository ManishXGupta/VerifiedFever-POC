// Build an editable Word version of the IEEE Sensors Letters draft.
// Numbers come from paper/generated/numbers.tex and experiments/results/*.json,
// figures from docs/figures/. Run:  node paper/make_docx.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType,
  WidthType, BorderStyle, SectionType, Footer, PageNumber, ExternalHyperlink, TabStopType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const json = (p) => JSON.parse(read(p));

// ---------- numbers ----------
const N = {};
for (const m of read("paper/generated/numbers.tex").matchAll(/\\newcommand\{\\(\w+)\}\{([^}]*)\}/g)) {
  N[m[1]] = m[2].replace(/--/g, "–");
}
const syn = json("experiments/results/synthetic_results.json");
const ob = json("experiments/results/outbreak_results.json");
const cost = json("experiments/results/cost_results.json");

// ---------- text helpers ----------
const FONT = "Times New Roman";
const BODY = 20; // 10 pt
const RED = "C00000";

// Mini markup: {Macro}, *italic*, _{sub}, ^{sup}, [[red]]
function runs(text, base = {}) {
  text = text.replace(/\{(\w+)\}/g, (m, k) => (k in N ? N[k] : m));
  const out = [];
  const re = /(\*[^*]+\*|_\{[^}]+\}|\^\{[^}]+\}|\[\[[^\]]+\]\])/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, size: BODY, ...base }));
    const t = m[0];
    if (t.startsWith("*")) out.push(new TextRun({ text: t.slice(1, -1), italics: true, font: FONT, size: BODY, ...base }));
    else if (t.startsWith("_{")) out.push(new TextRun({ text: t.slice(2, -1), subScript: true, font: FONT, size: BODY, ...base }));
    else if (t.startsWith("^{")) out.push(new TextRun({ text: t.slice(2, -1), superScript: true, font: FONT, size: BODY, ...base }));
    else out.push(new TextRun({ text: t.slice(2, -2), color: RED, font: FONT, size: BODY, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, size: BODY, ...base }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({
  children: runs(text, opts.run || {}), alignment: opts.align || AlignmentType.JUSTIFIED,
  indent: opts.noIndent ? undefined : { firstLine: 202 }, spacing: { after: 0, line: 222 }, ...(opts.para || {}),
});
const H1 = (num, text) => new Paragraph({
  children: [new TextRun({ text: `${num}. ${text.toUpperCase()}`, font: FONT, size: BODY, smallCaps: false })],
  alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80 }, keepNext: true,
});
const H2 = (letter, text) => new Paragraph({
  children: [new TextRun({ text: `${letter}. ${text}`, font: FONT, size: BODY, italics: true })],
  spacing: { before: 120, after: 60 }, keepNext: true,
});

// ---------- figures ----------
function pngSize(file) {
  const b = fs.readFileSync(file);
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}
function figure(file, widthIn, caption) {
  const f = path.join(ROOT, "docs/figures", file);
  const [w, h] = pngSize(f);
  const W = Math.round(widthIn * 96), H = Math.round(W * h / w);
  return [
    new Paragraph({ children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: W, height: H },
      altText: { title: caption.slice(0, 40), description: caption, name: file } })],
      alignment: AlignmentType.CENTER, spacing: { before: 80, after: 40 }, keepNext: true }),
    new Paragraph({ children: runs(caption, { size: 16 }), alignment: AlignmentType.JUSTIFIED, spacing: { after: 100 } }),
  ];
}

// ---------- tables (IEEE style: top, header and bottom rules only) ----------
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const LINE = { style: BorderStyle.SINGLE, size: 6, color: "000000" };
function table(caption, header, rows, colW, note) {
  const total = colW.reduce((a, b) => a + b, 0);
  const cell = (t, i, r, nRows, bold) => new TableCell({
    width: { size: colW[i], type: WidthType.DXA },
    margins: { top: 20, bottom: 20, left: 50, right: 50 },
    borders: { left: NONE, right: NONE, top: r === 0 ? LINE : NONE, bottom: (r === 0 || r === nRows - 1) ? LINE : NONE },
    children: [new Paragraph({ children: runs(t, { size: 15, bold }), alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER })],
  });
  const all = [header, ...rows];
  const t = new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: colW, alignment: AlignmentType.CENTER,
    borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
    rows: all.map((r, ri) => new TableRow({ children: r.map((c, ci) => { const b = c.startsWith("!"); return cell(b ? c.slice(1) : c, ci, ri, all.length, b); }) })),
  });
  return [
    new Paragraph({ children: runs(caption, { size: 16 }), alignment: AlignmentType.CENTER, spacing: { before: 160, after: 60 }, keepNext: true }),
    t,
    new Paragraph({ children: runs(note, { size: 14 }), alignment: AlignmentType.LEFT, spacing: { before: 40, after: 160 } }),
  ];
}
const f3 = (x) => x.toFixed(3), f4 = (x) => x.toFixed(4), f1 = (x) => x.toFixed(1);

const S = syn.summary;
const detRows = [["fixed38", "Fixed 38.0 °C"], ["fixed37.5", "Fixed 37.5 °C"], ["personal", "Personal (ours)"]].map(([k, l]) => {
  const v = S.overall[k];
  return [l, f3(v.sensitivity[0]), f3(S.by_baseline[k].low.sensitivity[0]), f4(v.specificity[0]), f3(v.ppv[0]), f3(v.f1[0]), f1(v.false_cert_per_1000[0])];
});
const obNames = { "VF-personal": "Verified fever, personal", "VF-fixed": "Verified fever, fixed 38.0 °C",
  "Confirmed": "Confirmed-case reports", "Absence": "All-cause absence" };
const obRows = Object.entries(obNames).map(([k, l]) => {
  const v = ob.summary[k];
  return [l, `${Math.round(100 * v.detection_rate)}%`, `${v.delay_median.toFixed(0)} (${v.delay_q1.toFixed(0)}–${v.delay_q3.toFixed(0)})`,
    v.cases_at_alert_median.toFixed(0), `${Math.round(100 * v.false_alarm_terms)}%`];
});
const C = (k) => cost[k];
const money = (x) => "$" + Math.round(x).toLocaleString("en-US");
const costRows = [
  ["Visit price", ...["low", "base", "high"].map((k) => money(C(k).per_visit.visit_price))],
  ["Parent time (h)", ...["low", "base", "high"].map((k) => C(k).per_visit.parent_hours_saved.toFixed(1))],
  ["Parent time value", ...["low", "base", "high"].map((k) => money(C(k).per_visit.parent_time_cost))],
  ["Travel", ...["low", "base", "high"].map((k) => money(C(k).per_visit.travel))],
  ["!Net saving per visit", ...["low", "base", "high"].map((k) => "!" + money(C(k).per_visit.net_saving))],
  ["Note-only visits avoided†", ...["low", "base", "high"].map((k) => C(k).per_school_year.visits_avoided.toFixed(0))],
  ["!Annual saving†", ...["low", "base", "high"].map((k) => "!" + money(C(k).per_school_year.annual_net_saving))],
  ["Parent hours saved†", ...["low", "base", "high"].map((k) => C(k).per_school_year.parent_hours_saved.toFixed(0))],
  ["Thermometer payback (yr)", ...["low", "base", "high"].map((k) => C(k).per_school_year.payback_years.toFixed(1))],
];

// ---------- content ----------
const title = "Verified Fever, No Appointment: An IoT Portable Thermometer for Automated Digital Absence Certification and Early Outbreak Alerts in Schools";
const abstract = `Many schools require a doctor’s note after a few illness absences, so families visit a clinic for a mild fever only to obtain paperwork. We present a sensor-to-certificate system in which a registered portable thermometer signs each daily reading, a verifier rejects altered, replayed, delayed or foreign readings, and a rule engine compares each reading with the student’s own baseline and the school’s cutoff. A nurse or physician validates the resulting certificate in one click; the parent shares it directly with the school by code, QR or signed file, and the school verifies it offline and sees only dates and status. The same verified daily readings feed class- and school-level outbreak alerts. In simulation, the personal-baseline rule raised fever-day sensitivity for students with low normal temperatures from {SensFixedLow} to {SensPersLow} at {FCPers} false certificates per 1000 student-days. In 480-student school terms, verified-fever surveillance detected {ObDetPers}% of influenza outbreaks within 21 days, a median {ObLeadAbs} days before absenteeism and {ObLeadConf} days before confirmed-case reports. All {NAttacks} scripted attacks were detected. Each avoided note-only visit saves about \${CostVisitBase} (2026 prices and wages).`;

const front = [
  new Paragraph({ children: [new TextRun({ text: "IEEE SENSORS LETTERS (DRAFT)", font: FONT, size: 14 })], spacing: { after: 200 } }),
  new Paragraph({ children: [new TextRun({ text: title, font: FONT, size: 32 })], alignment: AlignmentType.CENTER, spacing: { after: 120 } }),
  new Paragraph({ children: [new TextRun({ text: "Manish Gupta, ", font: FONT, size: 22 }), new TextRun({ text: "Senior Member, IEEE", font: FONT, size: 22, italics: true })],
    alignment: AlignmentType.CENTER, spacing: { after: 80 } }),
  new Paragraph({ children: [new TextRun({ text: "Design Laboratory Inc., Bellevue, WA, USA · e-mail: ", font: FONT, size: 16 }),
    new TextRun({ text: "[email]", font: FONT, size: 16, color: RED }), new TextRun({ text: " · ORCID: 0009-0001-0847-7087", font: FONT, size: 16 })],
    alignment: AlignmentType.CENTER }),
  new Paragraph({ children: [new TextRun({ text: "Code, data and demo: ", font: FONT, size: 16 }),
    new ExternalHyperlink({ link: "https://github.com/ManishXGupta/VerifiedFever-POC",
      children: [new TextRun({ text: "https://github.com/ManishXGupta/VerifiedFever-POC", font: FONT, size: 16, style: "Hyperlink" })] })],
    alignment: AlignmentType.CENTER, spacing: { after: 200 } }),
  new Paragraph({ children: [new TextRun({ text: "Abstract—", font: FONT, size: 18, bold: true, italics: true }), ...runs(abstract, { size: 18, bold: true })],
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 100 } }),
  new Paragraph({ children: [new TextRun({ text: "Index Terms—", font: FONT, size: 18, bold: true, italics: true }),
    ...runs("Sensor applications, body temperature, digital signatures, Internet of Things, school health, syndromic surveillance.", { size: 18, bold: true })],
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 120 } }),
  ...figure("graphical_abstract_column.png", 3.3, "Fig. 1.  Overview. A signed home reading becomes a nurse-validated absence certificate that the parent shares directly with the school, and an input to early outbreak alerts. Headline numbers are from Section IV."),
];

const body1 = [
  H1("I", "Introduction"),
  P("The 2025–26 influenza season hit children hard: in January 2026, children under 18 had the highest peak weekly influenza hospitalization rate observed since 2010–11 [1], and their cumulative rate was the second highest since then by March [2]. Schools sit at the center of this burden, yet their attendance rules push families toward clinics for mild illness. Mississippi, for example, now requires medical documentation after a student’s third illness-related absence [3]. A note-only visit costs the visit itself (an average of $220 at urgent care and $224 in primary care [4]), plus a parent’s time, travel and possibly lost pay; about half of lower-income working parents would be highly worried about losing pay to care for a sick child [5]. Time spent seeking care is a recognized economic burden [6], and virtual pediatric care has shown large savings when travel is avoided [7]."),
  P("Two gaps keep home thermometers out of this loop. First, a consumer reading is not evidence: a typed or edited value looks like a measured one, which is why authenticated sensor provenance is an active topic in medical IoT [8]. Second, fever is usually judged with one fixed cutoff, although normal temperature varies from person to person [9], and wearable temperature studies already use statistical outlier detection alongside fixed thresholds [10]. Meanwhile, school-based influenza surveillance still relies largely on absenteeism data [11], which mixes illness with every other reason a child stays home."),
  P("This letter makes four contributions: 1) a registered-thermometer evidence format and verifier; 2) a personal-baseline fever rule that keeps the school’s cutoff; 3) a clinician-validated certificate that the family shares directly with the school, in the spirit of verifiable credentials [12], with minimum disclosure; and 4) cohort surveillance on the same verified daily readings, evaluated against absenteeism and confirmed-case reporting. We also quantify cost and time savings and release an open-source proof of concept."),
];
const body1b = [
  H1("II", "System Design"),
  P("Fig. 2 shows the architecture and Fig. 3 the user interface."),
  H2("A", "Registered Thermometer, Verifier and Rule"),
  P("At enrollment, with parental consent, the school registers a device ID and the device’s Ed25519 public key against one student; the device never sees the student’s identity. Each reading {*device_id*, *seq*, *ts*, *T*, *site*, *nonce*} is canonical JSON, signed ({ReadingBytes} bytes). A reading is accepted only if the device is enrolled and active, any claimed student matches, the signature verifies, *seq* increases (anti-replay), *ts* is fresh (at most 6 h old, 5 min skew) and 34 ≤ *T* ≤ 43 °C. The baseline *B* is the median of the last 14 accepted readings below 37.5 °C (default 36.8 °C until five exist). A reading is febrile if"),
  new Paragraph({ children: runs("*T* ≥ *T*_{fix}  ∨  (*T* ≥ *T*_{floor}  ∧  *T* − *B* ≥ Δ),"),
    alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 },
    tabStops: [{ type: TabStopType.RIGHT, position: 4900 }] }),
  P("with the school cutoff *T*_{fix} = 38.0 °C always honoured, *T*_{floor} = 37.5 °C and Δ = 1.0 °C. Fever at or above 39.5 °C, or on a third consecutive day, goes to clinical review instead of certification.", { noIndent: true }),
  H2("B", "Certificate, Validation and Direct Sharing"),
  P("A febrile reading creates or extends a certificate (fever day plus a 24 h fever-free period) holding the student ID, dates, status, validator and a SHA-256 digest of the signed evidence; the service signs it and re-signs it on every change. After one-click validation by a nurse or physician, the certificate appears in the parent’s wallet. The parent shares it with a short code or QR, or as a signed file. The school portal accepts it only if the issuer signature verifies, the status is approved, the record still matches the issuer (not revoked or superseded), the code is unexpired and the student is enrolled; a duplicate is recognized. The school sees the reason (fever-related absence), dates and status, never temperatures."),
  H2("C", "Cohort Surveillance"),
  P("Each morning, the count of verified febrile students per class and per school is monitored with a one-sided CUSUM against a trailing 28-day baseline (3-day guard band) and a class-level count threshold; an alert goes to the school nurse and public health, without disclosing individual temperatures."),
];

const wideFigs = [
  ...figure("architecture_column.png", 3.0, "Fig. 2.  Architecture. Green arrows: the approved certificate returns to the parent’s wallet and is shared directly with the school. Dashed: daily flags feed cohort surveillance."),
  ...figure("ui_column.png", 3.3, "Fig. 3.  Proof-of-concept screens: (a) a signed reading of 37.6 °C is +1.3 °C above this student’s baseline, so a certificate is created although a 38.0 °C rule would not flag it; (b) the parent shares the approved certificate by code or QR; (c) nurse validation; (d) the school verifies and accepts it."),
];

const body2 = [
  H1("III", "Evaluation"),
  H2("A", "Individual Fever Detection"),
  P(`We simulated 500 students for 90 days: normal temperature N(36.7, 0.25^{2}) °C clipped to [36.0, 37.4], day-to-day noise 0.15 °C, measurement noise 0.10 °C, 0.1 °C display rounding, fever episodes of 1–3 days raising temperature 1.0–2.5 °C above a student’s own normal, and 0.3–0.8 °C transient rises on 3% of other days. The baseline was computed causally ({NSeeds} seeds).`),
  ...table(`TABLE I\nFEVER-DAY DETECTION ON THE SYNTHETIC COHORT (MEAN OF ${syn.n_seeds} SEEDS; ${S.days_eval.toLocaleString("en-US")} STUDENT-DAYS PER SEED)`.replace("\n", "  ·  "),
    ["Rule", "Sens.", "Sens. low", "Spec.", "PPV", "F1", "FC"], detRows, [1300, 520, 620, 640, 520, 520, 440],
    "Sens. low: students in the lowest tertile of normal temperature. FC: false certificates per 1000 student-days."),
  P("The fixed 38.0 °C rule missed many fever days in students with low normal temperatures (Table I, Fig. 4). The personal rule recovered most of them, raising episode detection from {EpiFixed}% to {EpiPers}% while adding less than one false certificate per 1000 student-days; a 37.5 °C cutoff reached similar sensitivity at {FCLow} false certificates. Across nine settings of inter-individual spread (0.15–0.35 °C) and noise (0.05–0.20 °C), personal-rule sensitivity stayed at {SensRangePers} (fixed 38.0 °C: {SensRangeFixed})."),
  ...figure("results.png", 3.3, "Fig. 4.  Individual detection. (a) Fever-day sensitivity by tertile of normal temperature. (b) False certificates per 1000 student-days."),
  H2("B", "Early Outbreak Detection"),
  P("Each simulated term had 480 students in 20 classes over 120 school days, with background non-influenza fevers, ordinary absences (4.5% with school-wide day effects) and readings on 85% of mornings. In outbreak terms one student was infected between days 30 and 90, and influenza spread within classes and across the school by attendance; 75% of cases were febrile, and 85% of febrile children stayed home. Of 400 outbreak terms, {ObFizzled} fizzled (fewer than five symptomatic cases) and were excluded; the remaining {ObTerms} had a median of {ObSize} symptomatic cases (IQR {ObSizeQone}–{ObSizeQthree}). Confirmed cases required care seeking (40%), testing (50%) and a 3–6 day reporting delay. Each signal’s detector was tuned on separate calibration terms so that at most 10% of outbreak-free terms raised a false alert."),
  ...table(`TABLE II  ·  SCHOOL INFLUENZA OUTBREAK DETECTION (${ob.n_eval_outbreak_terms} OUTBREAK TERMS, ${ob.n_eval_null_terms} OUTBREAK-FREE TERMS)`,
    ["Signal", "Detected", "Delay, d", "Cases", "False alarm"], obRows, [1700, 640, 820, 500, 760],
    `Detected: within ${ob.detect_window_days} days of the first symptomatic case. Delay: median (IQR) days from that case. Cases: median symptomatic cases by the alert day. False alarm: share of outbreak-free terms with any alert.`),
  P("Verified-fever surveillance detected the most outbreaks and the earliest (Table II, Fig. 5): a median {ObDelayPers} days after the first symptomatic case, when about {ObCasesPers} children had fallen ill, versus {ObDelayConf} days and {ObCasesConf} cases for confirmed reports. Absenteeism detected only {ObDetAbs}%, because ordinary absences mask the outbreak signal. Among outbreaks detected by both, verified fever alerted a median {ObLeadAbs} days before absenteeism (n = {ObPairsAbs}) and {ObLeadConf} days before confirmed reports (n = {ObPairsConf}). Using the personal rule rather than a fixed 38.0 °C cutoff raised detection from {ObDetFixed}% to {ObDetPers}%."),
  ...figure("outbreak.png", 3.3, "Fig. 5.  Cumulative share of school influenza outbreaks detected by days after the first symptomatic case, at matched false-alarm rates."),
  H2("C", "Cost and Time Savings"),
  P("Table III combines the average urgent care price [4], the May 2026 average hourly wage of $37.53 [13] and the 2026 vehicle rate of $0.76 per mile [14] with stated time and distance assumptions. Each avoided note-only visit saves about ${CostVisitLow}–${CostVisitHigh} (base ${CostVisitBase}); for a 500-student school where 20% of students would otherwise make one such visit a year, that is about ${CostSchoolBase} and {HoursSchoolBase} parent hours a year, and the thermometers pay back in {PaybackBase} years."),
  ...table("TABLE III  ·  ESTIMATED SAVINGS WHEN A VERIFIED CERTIFICATE REPLACES A NOTE-ONLY VISIT",
    ["", "Low", "Base", "High"], costRows, [2100, 750, 750, 750],
    "†Per 500-student school per year, with 10/20/30% of students otherwise making one note-only visit. Net of 3 min nurse review; $30 thermometer per student. Wage $37.53/h, vehicle $0.76/mile."),
  H2("D", "Tamper Evidence, Timing and Bench Agreement"),
  P("With 50 enrolled virtual thermometers, all 200 trials of each of seven reading attacks (edited value, back-dated timestamp, replay, non-enrolled key, another student’s device, delayed reading, unregistered device) and of certificate alteration were rejected, and all 1000 genuine readings were accepted. Altered shared files were refused by the school. Median times on a commodity x86-64 machine were {VerifyMs} ms to verify a signature and {EtoEMs} ms from reading to certificate. Sensor agreement is tested on a bench, with the thermometer and a calibrated reference in a stirred water bath at six set points from 36.0 to 40.0 °C, reporting bias, limits of agreement and classification at 38.0 °C (Table IV). [[Fill in Table IV after the bench test (run experiments/bench_analysis.py).]]"),
  ...table("TABLE IV  ·  BENCH AGREEMENT: PORTABLE THERMOMETER VS CALIBRATED REFERENCE (WATER BATH)",
    ["Set point", "Pairs", "Reference, °C", "Device, °C", "Bias, °C"],
    [...["36.0", "37.0", "37.5", "38.0", "39.0", "40.0"].map((t) => [t + " °C", "[[__]]", "[[__.__]]", "[[__.__]]", "[[±_.__]]"]),
     ["Overall bias (SD)", "[[__]]", "", "", "[[_.__ (_.__)]]"],
     ["95% limits of agreement", "", "", "", "[[_.__ to _.__]]"],
     ["Within ±0.2 °C / ±0.3 °C", "", "", "", "[[__% / __%]]"],
     ["Agreement at 38.0 °C cutoff", "", "", "", "[[__%]]"]],
    [1500, 520, 820, 760, 860],
    "Thermometer: [[device model]]; reference: [[reference model and accuracy]]. At least five paired readings per set point after 2 min stabilization. Bias = device − reference; limits of agreement = bias ± 1.96 SD (Bland–Altman)."),
  H1("IV", "Limitations and Conclusion"),
  P("Detection and outbreak results come from simulation and depend on stated assumptions; savings depend on local prices and policies. Signatures prove a reading came unaltered from an enrolled device, not that the probe was used correctly or not warmed; fever-reducing medicine can mask fever; the POC key must move into a secure element; the system documents fever and does not diagnose. Within these limits, a registered thermometer turns a routine home measurement into a verifiable certificate that families share directly with schools, saves a clinic visit, and provides an outbreak signal days earlier than existing school data. Next steps are the bench test, BLE firmware signing and a pilot with school nurses."),
  new Paragraph({ children: [new TextRun({ text: "REFERENCES", font: FONT, size: BODY })], alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80 } }),
];

const refs = [
  "Centers for Disease Control and Prevention, “Weekly US influenza surveillance report: Key updates for week 2, ending January 17, 2026,” FluView, Jan. 2026.",
  "Centers for Disease Control and Prevention, “Weekly US influenza surveillance report: Key updates for week 10, ending March 14, 2026,” FluView, Mar. 2026.",
  "WLOX News, “Mississippi attendance law brings new rules for student absences,” Sep. 16, 2026 (Mississippi Senate Bill 2103).",
  "Health Care Cost Institute, “Urgent care spending increased by 50% over 5 years driven by higher use,” Jan. 28, 2026.",
  "R. Minkin, L. Lin, D. Braga, and K. Hurst, “For working parents, the boundary between work and family is often blurred,” Pew Research Center, Jun. 16, 2026.",
  "Sollis Health, “The real cost of healthcare for Americans: 2026 health trend report,” industry report, Sep. 2026.",
  "E. Lim, J. Strychowsky, A. C. Gunz, and S. Belisle, “Sustainability in quality improvement: Outcomes of a novel pediatric virtual urgent care in Ontario, Canada,” *West. J. Emerg. Med.*, vol. 27, no. 5, 2026, doi: 10.5811/westjem.54076.",
  "V. Shukla, V. Shukla, Atul, D. Mishra, and M. K. Das, “ASCON-based lightweight cryptographic provenance for distinguishing physiological events, sensor faults, and cyberattacks in IoMT,” Cryptology ePrint Archive, Paper 2026/1929, Sep. 2026.",
  "D. M. Consolini, “Fever in infants and children,” *Merck Manual Consumer Version*, last updated May 2026.",
  "Y. Liu, Q. Zhao, K. Li, and D. Dowding, “Continuous temperature monitoring via wearable devices for fever or infection management in acute care hospitals: Scoping review of clinical implementation and data analytics,” *JMIR mHealth uHealth*, vol. 14, art. e89773, 2026, doi: 10.2196/89773.",
  "V. Joshy, Z. Feng, L. Deeth, K. Vanderkruk, and J. Slater, “DESA: An R package for detecting epidemics using a school-absenteeism surveillance framework,” *J. Open Res. Softw.*, vol. 14, art. 11, Feb. 2026, doi: 10.5334/jors.634.",
  "W3C Verifiable Credentials Working Group, “Verifiable credentials overview,” W3C Group Note, Jun. 17, 2026.",
  "U.S. Bureau of Labor Statistics, “The employment situation: May 2026,” USDL-26-0786, Jun. 5, 2026.",
  "Internal Revenue Service, “Optional standard mileage rates,” Announcement 2026-11, Jul. 2026.",
].map((r, i) => new Paragraph({ children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 16 }), ...runs(r, { size: 15 })],
  indent: { left: 360, hanging: 360 }, tabStops: [{ type: TabStopType.LEFT, position: 360 }], spacing: { after: 20 }, alignment: AlignmentType.LEFT }));

// ---------- document ----------
const page = { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 900, right: 900 } };
const footer = { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
  children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16 })] })] }) };
const twoCol = { count: 2, space: 360, equalWidth: true };

const doc = new Document({
  creator: "Manish Gupta", title,
  styles: { default: { document: { run: { font: FONT, size: BODY } } } },
  sections: [
    { properties: { page, column: twoCol }, footers: footer, children: [...front, ...body1, ...body1b, ...wideFigs, ...body2, ...refs] },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(ROOT, "paper", "VerifiedFever_IEEE_Sensors_Letters.docx");
  fs.writeFileSync(out, buf);
  console.log("wrote", out);
});
