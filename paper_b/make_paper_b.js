// Paper B manuscript for AI Magazine (single column, Word). Numbers from paper_b/numbers.json.
// Run:  python experiments/paper_b/make_numbers_b.py && node paper_b/make_paper_b.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType, WidthType,
  BorderStyle, Footer, PageNumber, HeadingLevel, ShadingType, LevelFormat,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const N = JSON.parse(fs.readFileSync(path.join(__dirname, "numbers.json"), "utf8"));
const RT = JSON.parse(fs.readFileSync(path.join(__dirname, "red_team.json"), "utf8"));
const FIG = path.join(ROOT, "docs", "paper_b");
const FONT = "Times New Roman", HFONT = "Arial", SIZE = 23; // 11.5 pt

function fill(t) {
  return t.replace(/\{(\w+)\}/g, (m, k) => {
    if (!(k in N)) throw new Error("missing number " + k);
    return N[k];
  });
}
// *italic*, **bold**
function runs(text, base = {}) {
  text = fill(text);
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, size: SIZE, ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, size: SIZE, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, font: FONT, size: SIZE, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, size: SIZE, ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 120, line: 288 }, alignment: AlignmentType.JUSTIFIED, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: HFONT, size: 28, bold: true })], spacing: { before: 280, after: 120 }, keepNext: true });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: HFONT, size: 24, bold: true })], spacing: { before: 200, after: 100 }, keepNext: true });
const bullet = (t) => new Paragraph({ children: runs(t), numbering: { reference: "bul", level: 0 }, spacing: { after: 80, line: 276 } });

let figN = 0, tabN = 0;
function figure(file, caption, widthIn = 6.3) {
  if (file === "architecture.png") widthIn = 4.4;
  if (file === "dashboard.png") widthIn = 5.2;
  if (file === "individual.png") widthIn = 5.8;
  figN += 1;
  const buf = fs.readFileSync(path.join(FIG, file));
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const wpx = Math.round(widthIn * 96), hpx = Math.round(wpx * h / w);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 60 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: wpx, height: hpx },
        altText: { title: `Figure ${figN}`, description: fill(caption), name: file } })] }),
    new Paragraph({ spacing: { after: 200, line: 264 }, alignment: AlignmentType.JUSTIFIED,
      children: [new TextRun({ text: `Figure ${figN}. `, bold: true, font: FONT, size: 20 }), ...runs(caption, { size: 20 })] }),
  ];
}
const border = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
function table(caption, header, rows, widths) {
  tabN += 1;
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (t, i, head, bold) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    borders: { top: head ? border : none, bottom: head ? border : none, left: none, right: none },
    shading: head ? { fill: "EEF2F7", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    children: [new Paragraph({ alignment: (i === 0 || header[i] === "Attempt") ? AlignmentType.LEFT : AlignmentType.CENTER,
      children: runs(t, { size: 19, bold: head || bold }) })],
  });
  const trs = [new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, i) => cell(h, i, true)) })];
  rows.forEach((r, k) => {
    const bold = r[0].startsWith("!");
    const cells = r.map((t, i) => cell(t.replace(/^!/, ""), i, false, bold));
    const tr = new TableRow({ cantSplit: true, children: cells });
    trs.push(tr);
  });
  // bottom rule on last row
  const last = trs[trs.length - 1];
  return [
    new Paragraph({ keepNext: true, spacing: { before: 160, after: 80 },
      children: [new TextRun({ text: `Table ${tabN}. `, bold: true, font: FONT, size: 20 }), ...runs(caption, { size: 20 })] }),
    new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows: trs,
      borders: { top: border, bottom: border, left: none, right: none, insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "DDDDDD" }, insideVertical: none } }),
    new Paragraph({ spacing: { after: 160 }, children: [] }),
  ];
}

// ------------------------------------------------------------------ content
const TITLE = "From Individual Readings to Population Signals: Agentic AI and IoT Temperature Registration for Early Viral Outbreak Detection";
const SHORT = "Agentic AI and IoT for Early Outbreak Alerts";
const ABSTRACT = "Outbreak detection still waits for clinic visits and laboratory reports, which trail community spread by days to weeks, while the temperature readings people take at home every day are rarely pooled or checked. We present an agentic AI and Internet of Things (IoT) framework for proactive temperature registration. Registered IoT thermometers sign each daily reading for a consent-based registry. An AI anomaly layer compares every reading with the person\u2019s own baseline using age-aware fever rules and looks for synchronized rises across classrooms, workplaces, care homes and postal codes. Guardrailed AI agents triage flags and draft alerts, while physicians and public health officers make every decision and public health sees counts only. In simulation the personal rules raised illness-day detection for older adults from {older_F38_sens} to {older_PA_sens}. Replaying nine real US influenza seasons (CDC ILINet, 2010 to 2019) through a simulated 10,000-person registry, the system alerted a median {ili_lead_decl} days before the season onset was officially declared. In a simulated town it found localized outbreaks {t_lead_lab} days earlier than laboratory confirmation and named the outbreak\u2019s setting in {t_reg_loc} of alerts. We discuss what must hold before deployment.";
const KEYWORDS = "agentic AI; Internet of Things; early warning; anomaly detection; human-in-the-loop AI; influenza surveillance; privacy by design";

function content() {
  const x = [];
  x.push(H1("Introduction"));
  x.push(P("Public health learns about a respiratory outbreak in steps. People fall ill, some of them see a clinician a few days later, a share of those are tested, and results travel to a health department and on to weekly national reports. In the United States, the Outpatient Influenza-like Illness Surveillance Network (ILINet) reports the weekly percentage of clinic visits for influenza-like illness and compares it with a baseline built from previous seasons (CDC 2016). A season is said to begin in the first week that this percentage crosses the baseline and stays above it for at least two more weeks (Biggerstaff et al. 2016), so by the time the onset is confirmed and published, transmission has been under way for close to a month. The 2025–2026 season is a reminder of why this matters: activity rose early, driven by a new influenza A(H3N2) subclade first identified in August 2025 (CDC 2025)."));
  x.push(P("Meanwhile, millions of people take their temperature at home. Readings from consumer smart thermometers tracked national influenza-like illness closely (correlation above 0.95) and improved forecasts weeks ahead (Miller et al. 2018), and researchers have proposed community early warning built on networks of connected thermometers (Li et al. 2023). Wearables go further: in 2025 a study in *The Lancet Digital Health* detected the body’s inflammatory response to a live influenza vaccine before symptoms with about 90% sensitivity (Hadid et al. 2025). Yet three gaps keep home readings out of routine surveillance. Readings are unverified and anonymous, so they cannot be trusted as evidence or linked to the places where people gather. They are judged against one fixed cutoff, although normal temperature differs between people and is lower in older adults (Geneva et al. 2019). And they are screened once, reactively, rather than followed as a trajectory over time."));
  x.push(P("This article describes an agentic AI and IoT framework that closes these gaps and evaluates it in three ways, including a replay of nine real influenza seasons. It extends our work on verified fever certificates for schools (Gupta 2026), where a registered IoT thermometer signs every reading, to a voluntary registry open to everyone. The registry follows each person against their own baseline, and an AI anomaly layer compares many people over the same days to spot synchronized rises within a classroom, a workplace, a care home or a postal code. Agents prepare work for people, but they never decide: a physician reviews individual flags and a human confirms every outbreak alert before it leaves the system."));
  x.push(P("Our contributions are:"));
  [
    "**An IoT registry of verified readings**, built on registered thermometers, with three separately revocable consent scopes, small-cell suppression for public health and a tamper-evident audit log.",
    "**Age-aware personal fever rules** that keep standard cutoffs and add each person’s own baseline, including the lower criteria used for older adults in long-term care (High et al. 2009).",
    "**Cohort synchrony detection** that combines a count test with a drift test, which looks for small, simultaneous rises in members’ deviations from their own baselines before many cross a fever threshold, and localizes the alert to a setting.",
    "**An agentic AI layer**: guardrailed, physician-in-the-loop agents that triage and draft but cannot make clinical or public health decisions.",
    "**An evaluation** with exact and simulated components: a replay of CDC ILINet data for the US and ten regions over nine seasons, a town-scale outbreak simulation against clinic-visit and laboratory signals, and red-team and throughput tests of the working code.",
  ].forEach((t) => x.push(bullet(t)));

  x.push(H1("Why One Cutoff Is Not Enough"));
  x.push(P("Clinical references already define fever partly in personal terms, as a temperature higher than a person’s known normal (Tesini 2025). A systematic review of normal body temperature found that adults aged 60 and over run about 0.23 °C cooler than younger adults (Geneva et al. 2019), and older adults often mount a blunted fever response to infection. For residents of long-term care, guidelines therefore count a single oral reading of at least 37.8 °C, repeated readings of at least 37.2 °C, or a rise of at least 1.1 °C over baseline (High et al. 2009). A one-size cutoff of 38.0 °C misses illness in exactly the people with the most to lose. A daily registry can do better because it knows each person’s normal. The same history is what makes population signals possible: when many people in one room each drift a few tenths of a degree above their own normal on the same days, that synchrony is informative even if few of them have crossed any threshold yet."));

  x.push(H1("System Design"));
  x.push(H2("IoT layer: verified readings and consent"));
  x.push(P("Each participant uses a registered IoT thermometer that signs a small record (device, sequence number, time, temperature) with a private key it never reveals, exactly as in the school system (Gupta 2026). The registry checks the signature, the device’s enrollment, the sequence number (to stop replays) and the freshness of the time stamp, so an edited, replayed or invented reading is rejected. The device knows nothing about its owner; only the registry links the device to a pseudonymous person record and to that person’s groups: a class, a workplace or a care home, and a postal code. Consent has three scopes that the person can switch independently: *monitoring* (readings are stored and checked against the person’s baseline), *cohort* (the person’s flags may be counted in group statistics) and *physician* (a named physician may view the trajectory). Withdrawing consent stops processing and erases the person’s readings."));
  x.push(...figure("architecture.png", "Architecture of the agentic AI and IoT registry. Signed readings from IoT thermometers are verified and checked against consent, evaluated against each person’s baseline, and pooled by group. Agents in the agentic AI layer prepare a physician queue and draft alerts, and a policy guard keeps every decision with a human."));
  x.push(H2("AI anomaly layer: individuals"));
  x.push(P("A person’s baseline is the median of their recent afebrile readings (up to 14), with an age-band default until five readings exist. A reading counts as a fever if it reaches the fixed cutoff, or if it is above an age-specific floor and at least a set margin above the person’s own baseline. Children and adults use 38.0 °C, a 37.5 °C floor and a 1.0 °C margin; adults aged 65 and over use the long-term-care criteria of 37.8 °C, a 37.2 °C floor and a 1.1 °C margin. The rule is deliberately simple and auditable: a physician can see exactly why a reading was flagged."));
  x.push(H2("AI anomaly layer: cohorts"));
  x.push(P("Every morning the registry builds, for each group, the number of members who reported, the number flagged febrile and the sum of members’ deviations from their own baselines. Three detectors run on these series. The *count test* asks whether today’s febrile count is improbable given the group’s own recent rate, using a Poisson tail probability corrected for the number of groups examined. The *drift test* compares today’s mean personal deviation with the group’s recent daily means; because it uses every reading rather than only the febrile ones, it can respond when a whole class runs half a degree warm before many children cross a fever line. A population-level cumulative sum (CUSUM) chart (Page 1954) watches the overall daily share of fevers. An alert names the group that triggered it, which tells public health where to look first."));
  x.push(H2("Agentic AI layer with a human in the loop"));
  x.push(P("AI agents are increasingly proposed as always-on assistants for epidemic intelligence (Yang et al. 2026) and for orchestrating outbreak monitoring (Wattamwar and Akwafuo 2026), while in clinical care they remain under near-total human oversight because of safety and liability constraints (Aránguiz Dias et al. 2026). We take the second constraint as a design rule. A *triage agent* turns each flag into a queue item for the person’s physician, urgent first (39.5 °C or higher, a third consecutive fever day, or an older adult), or into a self-care notice if the person has not shared data with a physician. A *cohort agent* turns detector output into a short, counts-only draft for public health and suppresses repeats for the same group within a week. A *policy guard* checks every action and message: clinical decisions and alert confirmations are reserved for humans; messages to public health may carry group counts for groups of at least five reporters and never identifiers or individual temperatures; only consenting patients reach a physician; any other recipient is refused; and free text, such as a note typed by a participant, is stored as data and never followed as an instruction. Every action, allowed or blocked, is written to a hash-chained audit log. Drafting uses fixed templates; a language model could be plugged in, and its output would pass through the same guard."));
  x.push(H2("Governance"));
  x.push(P("The design follows privacy-by-design principles that map onto health privacy law: purpose-specific consent, data minimization (the thermometer carries no identity, and public health receives counts), access limited to a named physician, small-cell suppression, a complete audit trail, and erasure on withdrawal. A registry run by or for a covered entity in the United States would also fall under the HIPAA Security Rule, whose proposed overhaul, published in January 2025, is now not expected in final form before July 2027 (Holland & Knight 2026); the controls above are a floor, not a substitute for that analysis. The system documents temperature; it does not diagnose, and it does not tell anyone to stay home."));

  x.push(H1("Evaluation"));
  x.push(P("We asked four questions: does the personal rule find more illness without more false alarms, could a registry have warned earlier in real seasons, can it find and localize a local outbreak, and does the code keep its promises under attack and at scale. All experiments use fixed random seeds, so every number can be reproduced."));
  x.push(H2("Personal rules across ages"));
  x.push(P("We simulated 1,000 people in each age band for 120 days (five seeds), with normal temperatures, day-to-day variation, measurement noise, missed readings (85% adherence), short illness episodes and transient non-fever rises. Older adults had a lower normal (36.4 °C on average) and a blunted fever response. The personal rules raised illness-day sensitivity from {child_F38_sens} to {child_PA_sens} for children, {adult_F38_sens} to {adult_PA_sens} for adults and {older_F38_sens} to {older_PA_sens} for older adults (Figure 3), with false flags of {child_PA_fp}, {adult_PA_fp} and {older_PA_fp} per 1,000 person-days. Simply lowering everyone’s cutoff to 37.8 °C caught less and produced more than twice as many false flags in children ({child_F378_fp} per 1,000). For older adults, the age-aware criteria added a further gain over the general personal rule ({older_P1_sens} to {older_PA_sens}), but even so, more than half of their illness days showed no fever at all, which is why the cohort drift signal matters for care homes."));
  x.push(...figure("dashboard.png", "Physician view of the working dashboard. Left: the AI-ordered fever queue and draft cohort alerts that need human confirmation. Right: one patient’s readings against their personal baseline (dashed) with flagged fevers, and the mean deviation from personal baselines in two classes, where class 4B rises together."));
  x.push(...figure("individual.png", "Illness-day sensitivity and false flags for four rules by age band (simulation, five seeds). Personal rules compare each reading with the person’s own baseline; the age-aware version uses long-term-care criteria for adults aged 65 and over."));
  x.push(H2("Replaying nine real influenza seasons"));
  x.push(P("To ground the timing question in real epidemics, we used weekly weighted ILINet data for the US and the ten Health and Human Services (HHS) regions for the 2010–2011 to 2018–2019 seasons, together with each season’s official onset week, as published by the FluSight Network (Reich et al. 2019): 99 location-seasons, 90 with a declared onset. Each weekly curve drove a simulated registry of 10,000 people: the daily chance of starting a febrile respiratory illness was proportional to the ILINet level, scaled so that an average season gives about one person in five at least one episode, and shifted two days earlier because people run a fever before the clinic visit that ILINet counts. Readings were flagged with the age-aware personal rule, and a CUSUM detector compared the daily count of flags with the first three weeks of the season, with its threshold set so that no more than 5% of flat, outbreak-free replays raised any alert. We compared the registry’s alert day with two ILINet milestones, assuming each weekly report is published six days after the week ends: the first week above baseline (12 days after the onset week begins) and the declared onset after three weeks above baseline (26 days after)."));
  x.push(...figure("ilinet_example.png", "One replay: the 2014–2015 US season. (a) Weekly ILINet influenza-like illness. (b) Daily fevers in one simulated 10,000-person registry driven by that curve, with the registry’s alert and the ILINet milestones."));
  x.push(P("The registry alerted in {ili_alerted} seasons with a declared onset, a median of {ili_med} days from the start of the onset week (interquartile range {ili_iqr}; Figure 5), which is a median of {ili_lead_decl} days before the declared onset was published (IQR {ili_lead_decl_iqr}). It beat the declared onset in {ili_before_decl} of seasons and even the first published week above baseline in {ili_before_first}, by a median of {ili_lead_first} days. The personal rule helped: with one fixed 38.0 °C cutoff the median alert came {ili_fixed_med} days after the onset week began. Timeliness mattered more than anything else. When we summed the same registry readings into weekly totals and acted only at the end of each week, the median alert slipped to {ili_weekly_med} days, no earlier than ILINet itself."));
  x.push(...figure("ilinet_lead.png", "Alert timing in 90 replayed seasons with a declared onset (US and ten HHS regions, 2010–2019). Each dot is one location-season; bars mark medians. ILINet milestones assume publication six days after the week ends."));
  x.push(P("Size and assumptions change the picture in predictable ways (Table 1). A 2,000-person registry is too noisy to beat ILINet reliably, while 50,000 people alerted before the onset week in most seasons. Changing the fever-to-visit delay from two days to zero or four days moved the median alert by only a few days. One finding deserves care. In 2011–2012, the mildest season in the data, CDC never declared an onset nationally or in most regions, yet the registry alerted in {ili_noonset} of those 9 location-seasons. These were not empty alarms: influenza-like illness still rose 1.5- to 3.3-fold from its early-season level. A registry that measures change relative to its own recent past will report such rises, so an operational system should pair alerts with an absolute level that grades severity."));
  x.push(...table("Registry alerts in 90 replayed seasons with a declared onset. Days are relative to the first day of the CDC onset week.",
    ["Registry", "Seasons alerted", "Median alert day", "Median days before declared onset", "Before declared onset", "Alerts in 9 seasons without onset"],
    [["!10,000 people, personal rule (main)", `!${N.ili_alerted}`, `!${N.ili_med}`, `!${N.ili_lead_decl}`, `!${N.ili_before_decl}`, `!${N.ili_noonset}`],
     ["2,000 people", N.n2k_alerted, N.n2k_med, N.n2k_lead_decl, N.n2k_before_decl, N.n2k_noonset],
     ["50,000 people", N.n50k_alerted, N.n50k_med, N.n50k_lead_decl, N.n50k_before_decl, N.n50k_noonset],
     ["No fever-to-visit delay", N.d0_alerted, N.d0_med, N.d0_lead_decl, N.d0_before_decl, N.d0_noonset],
     ["Four-day fever-to-visit delay", N.d4_alerted, N.d4_med, N.d4_lead_decl, N.d4_before_decl, N.d4_noonset]],
    [2700, 1150, 1150, 1500, 1250, 1350]));
  x.push(H2("Finding a local outbreak in a town"));
  x.push(P("National curves cannot test localization, so we simulated a town of 12,000 registry participants in 30 postal codes, with {t_classes} classes, {t_work} workplaces and {t_care} care homes, over 120-day terms. Every term had sporadic febrile illness; outbreak terms added an influenza-like outbreak seeded in one class, workplace or care home that spread within the setting, the neighborhood and the town (median {t_size_med} infections per term, IQR {t_size_iqr}). The same terms fed three signals: the registry; clinic visits reported by postal code (35% of febrile people seek care one to three days after onset); and laboratory-confirmed influenza (half of those who seek care are tested, results arrive three to six days later, and sporadic unrelated cases occur). Each signal’s thresholds were tuned on {t_n_null} calibration terms to raise a false alert in no more than 10% of outbreak-free terms, then tested on fresh terms: {t_n_null} without and {t_n_eval} with an outbreak of at least five symptomatic cases."));
  x.push(...table("Outbreak detection within 21 days of the first symptomatic case in the simulated town (fresh test terms).",
    ["Signal", "False-alarm terms", "Detected", "Median delay, days (IQR)", "Median cases at alert", "Alert names the setting"],
    [["!Registry, count + drift", `!${N.t_reg_fa}`, `!${N.t_reg_det}`, `!${N.t_reg_delay} (${N.t_reg_iqr})`, `!${N.t_reg_cases}`, `!${N.t_reg_loc}`],
     ["Registry, count only", N.t_reg_nodrift_fa, N.t_reg_nodrift_det, `${N.t_reg_nodrift_delay} (${N.t_reg_nodrift_iqr})`, N.t_reg_nodrift_cases, N.t_reg_nodrift_loc],
     ["Registry, fixed 38.0 °C", N.t_reg_fixed_fa, N.t_reg_fixed_det, `${N.t_reg_fixed_delay} (${N.t_reg_fixed_iqr})`, N.t_reg_fixed_cases, N.t_reg_fixed_loc],
     ["Clinic visits by postal code", N.t_syn_fa, N.t_syn_det, `${N.t_syn_delay} (${N.t_syn_iqr})`, N.t_syn_cases, "postal code only"],
     ["Laboratory-confirmed", N.t_lab_fa, N.t_lab_det, `${N.t_lab_delay} (${N.t_lab_iqr})`, N.t_lab_cases, "none"]],
    [2500, 1250, 1050, 1650, 1300, 1350]));
  x.push(P("The registry with both tests detected {t_reg_det} of outbreaks within three weeks, a median {t_reg_delay} days after the first symptomatic case and with {t_reg_cases} cases by the alert, against {t_lab_det} for laboratory confirmation after {t_lab_delay} days and {t_lab_cases} cases (Table 2, Figure 6). When both detected the same outbreak, the registry was a median {t_lead_lab} days earlier (n = {t_lead_lab_n}). Its first alert named the exact class, workplace or care home where the outbreak began in {t_reg_loc} of detected outbreaks and the right kind of setting in {t_reg_loctype}; the laboratory signal carries no location at all. The drift test was responsible for much of the gain: counts alone detected {t_reg_nodrift_det}, and a fixed cutoff {t_reg_fixed_det}. The registry was not better everywhere: in care homes, where fevers are blunted, laboratory confirmation detected slightly more outbreaks ({t_by_care_home_lab} against {t_by_care_home_reg}), while in classes the registry led ({t_by_class_reg} against {t_by_class_lab}). Clinic visits by postal code performed poorly ({t_syn_det}), because ordinary fevers from many causes swamp a small cluster when it is spread over neighborhoods. Detection was far from complete for every signal, since many outbreaks were still small three weeks after the first case, and the registry’s false-alarm rate on fresh terms was {t_reg_fa}, close to the 10% design target."));
  x.push(...figure("town.png", "Town simulation, fresh test terms. (a) Outbreaks detected within 21 days of the first symptomatic case; (b) median delay; (c) share of first alerts that name the outbreak’s exact setting (clinic visits localize to postal codes only, and laboratory reports not at all)."));
  x.push(H2("Guardrails, workload and scale"));
  x.push(P("We attacked the working code with {rt_total} scripted attempts in {rt_n_attempts} categories (Table 3), from tampered and replayed readings to an agent trying to confirm an alert and an instruction hidden in a participant’s note. All {rt_prev} were prevented and the audit chain verified intact. In the replays, the personal rule flagged about five readings per 1,000 participants a day on average, rising to eight or nine at a season’s peak, a load a practice can review when the queue is ordered by urgency. On a single processor core the registry verified, evaluated and stored a reading in a median {ms_reading} ms (95th percentile {ms_p95} ms), about {per_hour} readings an hour, and daily cohort surveillance over {tp_groups} groups for {tp_people} participants took {surv_s} seconds."));
  const nice = {
    "identifier to public health": "Person identifier sent to public health",
    "temperature to public health": "Individual temperature sent to public health",
    "group under small-cell limit": "Counts for a group under five reporters",
    "recipient outside policy": "Message to employer, insurer, school or marketer",
    "agent makes clinical decision": "Agent makes a clinical decision",
    "agent confirms outbreak alert": "Agent confirms an outbreak alert",
    "physician reads non-consenting patient": "Physician reads a non-consenting patient",
    "other physician reads patient": "Another physician reads a patient",
    "instruction injected in note": "Instruction injected in a participant note",
    "tampered reading": "Tampered reading", "replayed reading": "Replayed reading",
    "unregistered device": "Reading from an unregistered device", "reading after withdrawal": "Reading after consent withdrawal",
  };
  x.push(...table("Red-team attempts against the registry and agent guardrails (50 randomized trials each).",
    ["Attempt", "Prevented", "Attempt", "Prevented"], (() => {
      const e = Object.entries(RT).map(([k, v]) => [nice[k] || k, `${v.prevented}/${v.trials}`]);
      const h = Math.ceil(e.length / 2), rows = [];
      for (let i = 0; i < h; i++) rows.push([...e[i], ...(e[i + h] || ["", ""])]);
      return rows;
    })(), [3500, 1060, 3500, 1060]));

  x.push(H1("Lessons for AI Practitioners"));
  x.push(P("Several lessons generalize beyond thermometers. First, *personalization before sophistication*: comparing a person with their own history did more than any population threshold, and it kept the rule simple enough to explain. Second, *timeliness is a design variable*: the same readings, summed weekly instead of examined daily, lost almost all of their advantage over clinical reporting. Third, *use the weak signal*: the drift test pools sub-threshold changes that no individual rule would flag, and it was what made localization work. Fourth, *let agents prepare and people decide*: putting decisions behind a guard that cannot be talked around, rather than behind a prompt, makes the system’s promises testable. Finally, *evaluate against real history where you can*: replaying ILINet seasons exposed behavior, such as alerts in a mild season that never formally began, that a purely synthetic test would have hidden."));

  x.push(H1("Limitations and the Path to Deployment"));
  x.push(P("Our temperatures are simulated, and the replay links real ILINet curves to registry fevers through assumptions about attack rate, the fever-to-visit delay and adherence; the lead times are what a registry *could* achieve under those assumptions, not measurements. Volunteers who keep a daily habit differ from the population, and access to devices is uneven, so a registry can miss the communities that most need early warning unless devices are provided. Fever is an incomplete marker: many viral infections, including some COVID-19 cases, and much illness in older adults produce little or no fever, so temperature should be one signal among several, alongside laboratory and wastewater data and syndromic surveillance, which has flagged outbreaks two to fourteen days before laboratory reporting (Getsova and Rangelova 2026). The system documents temperature and is not a diagnostic device; any clinical use would need regulatory review. The next steps are a bench test of the registered thermometer against a reference probe, a prospective pilot in a school district or care-home network with ethics approval, and a comparison against local syndromic and laboratory data in the same weeks."));
  x.push(H1("Conclusion"));
  x.push(P("Turning everyday thermometer use into an early warning system needs three things that one-time screening lacks, and IoT devices and agentic AI can supply them: readings people can trust, a sense of what is normal for each person, and a way to see many people change together. With those in place, and with AI agents that prepare work but leave decisions to physicians and public health, a consent-based registry could have warned weeks before official onset in nine real influenza seasons and pointed to where a local outbreak began. Whether it does so in practice is a question for a careful pilot."));
  return x;
}

const REFS = [
  "Aránguiz Dias, G., et al. 2026. “The Doctor Will (Still) See You Now: On the Structural Limits of Agentic AI in Healthcare.” arXiv:2602.18460.",
  "Biggerstaff, M., D. Alper, M. Dredze, et al. 2016. “Results from the Centers for Disease Control and Prevention’s Predict the 2013–2014 Influenza Season Challenge.” *BMC Infectious Diseases* 16: 357. https://doi.org/10.1186/s12879-016-1669-x.",
  "CDC (Centers for Disease Control and Prevention). 2016. *Overview of Influenza Surveillance in the United States*. Atlanta: CDC. https://stacks.cdc.gov/view/cdc/43971.",
  "CDC (Centers for Disease Control and Prevention). 2025. “Weekly US Influenza Surveillance Report: Key Updates for Week 48, Ending November 29, 2025.” FluView. https://www.cdc.gov/fluview/surveillance/2025-week-48.html.",
  "Geneva, I. I., B. Cuzzo, T. Fazili, and W. Javaid. 2019. “Normal Body Temperature: A Systematic Review.” *Open Forum Infectious Diseases* 6 (4): ofz032. https://doi.org/10.1093/ofid/ofz032.",
  "Getsova, Z., and V. Rangelova. 2026. “Syndromic Surveillance: Review on Different Practices, Performance, and Added Value for Public Health.” *Epidemiologia* 7 (1): 23.",
  "Gupta, M. 2026. “Verified Fever, No Appointment: A Guardrailed Agentic AI and IoT Thermometer System for Digital School Absence Certificates and Early Outbreak Alerts.” Manuscript under review.",
  "Hadid, A., E. G. McDonald, et al. 2025. “Development of Machine Learning Prediction Models for Systemic Inflammatory Response Following Controlled Exposure to a Live Attenuated Influenza Vaccine in Healthy Adults Using Multimodal Wearable Biosensors in Canada.” *The Lancet Digital Health*.",
  "High, K. P., S. F. Bradley, S. Gravenstein, et al. 2009. “Clinical Practice Guideline for the Evaluation of Fever and Infection in Older Adult Residents of Long-Term Care Facilities: 2008 Update by the Infectious Diseases Society of America.” *Clinical Infectious Diseases* 48 (2): 149–71. https://doi.org/10.1086/595683.",
  "Holland & Knight. 2026. “HIPAA Security Rule Amendments Now Projected for July 2027.” Healthcare Blog, July 6, 2026.",
  "Li, R., M. Shen, H. Liu, L. Bai, and L. Zhang. 2023. “Do Infrared Thermometers Hold Promise for an Effective Early Warning System for Emerging Respiratory Infectious Diseases?” *JMIR Formative Research* 7: e42548. https://doi.org/10.2196/42548.",
  "Miller, A. C., I. Singh, E. Koehler, and P. M. Polgreen. 2018. “A Smartphone-Driven Thermometer Application for Real-Time Population- and Individual-Level Influenza Surveillance.” *Clinical Infectious Diseases* 67 (3): 388–97. https://doi.org/10.1093/cid/ciy073.",
  "Page, E. S. 1954. “Continuous Inspection Schemes.” *Biometrika* 41 (1–2): 100–115.",
  "Reich, N. G., L. C. Brooks, S. J. Fox, et al. 2019. “A Collaborative Multiyear, Multimodel Assessment of Seasonal Influenza Forecasting in the United States.” *Proceedings of the National Academy of Sciences* 116 (8): 3146–54.",
  "Tesini, B. L. 2025. “Fever.” *Merck Manual Professional Version*. Modified June 2025.",
  "Wattamwar, A., and S. Akwafuo. 2026. “ARIES: A Scalable Multi-Agent Orchestration Framework for Real-Time Epidemiological Surveillance and Outbreak Monitoring.” arXiv:2601.01831.",
  "Yang, L., L. Shan, X. Cao, et al. 2026. “AI Agents and Epidemic Intelligence on Respiratory Infectious Diseases: Toward a Conceptual Framework Integrating Decision Support.” *Journal of Medical Internet Research* 28: e86936. https://doi.org/10.2196/86936.",
];

function build() {
  const kids = [];
  kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: [new TextRun({ text: TITLE, font: HFONT, size: 34, bold: true })] }));
  kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new TextRun({ text: "Manish Gupta", font: FONT, size: 24, bold: true })] }));
  kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun({ text: "Independent Researcher, USA · manish.ingupta@gmail.com · ORCID 0009-0001-0847-7087", font: FONT, size: 20 })] }));
  kids.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: [new TextRun({ text: `Short title: ${SHORT}`, font: FONT, size: 20, italics: true })] }));
  kids.push(new Paragraph({ spacing: { after: 120, line: 276 }, alignment: AlignmentType.JUSTIFIED, children: [new TextRun({ text: "Abstract. ", bold: true, font: FONT, size: SIZE }), ...runs(ABSTRACT)] }));
  kids.push(new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Keywords: ", bold: true, font: FONT, size: SIZE }), new TextRun({ text: KEYWORDS, font: FONT, size: SIZE })] }));
  kids.push(...content());
  kids.push(H1("Acknowledgments"));
  kids.push(P("The author thanks the FluSight Network and CDC ILINet participants, whose openly published data made the season replays possible. Generative AI (Claude, Anthropic) assisted with code, simulation scripts and language editing; the author designed the study, reviewed all code and text, and takes responsibility for the content."));
  kids.push(H1("Declarations"));
  kids.push(P("**Conflict of interest.** The author declares no conflict of interest. **Funding.** None. **Ethics.** No human participants or personal data were involved; all individual readings are simulated, and the ILINet data are public aggregates. **Data and code availability.** The ILINet data are public and were obtained from the FluSight Network (Reich et al. 2019). Code, simulation parameters and results are available from the author on reasonable request."));
  kids.push(H1("References"));
  REFS.forEach((r) => kids.push(new Paragraph({ spacing: { after: 90, line: 264 }, indent: { left: 360, hanging: 360 }, children: runs(r, { size: 21 }) })));

  const doc = new Document({
    creator: "Manish Gupta", title: TITLE, description: "Manuscript for AI Magazine",
    styles: { default: { document: { run: { font: FONT, size: SIZE } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: HFONT, size: 28, bold: true }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: HFONT, size: 24, bold: true }, paragraph: { spacing: { before: 200, after: 100 }, keepNext: true, outlineLevel: 1 } },
      ] },
    numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1260, bottom: 1260, left: 1260, right: 1260 } } },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })] })] }) },
      children: kids,
    }],
  });
  return Packer.toBuffer(doc);
}

const out = process.argv[2] || path.join(__dirname, "ProactiveRegistry_AIMagazine.docx");
build().then((b) => { fs.writeFileSync(out, b); console.log("wrote", out); });
