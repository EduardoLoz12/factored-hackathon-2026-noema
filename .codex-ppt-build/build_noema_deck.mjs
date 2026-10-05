import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "/Users/federicovargas/Documents/factored-hackathon-2026-noema";
const SKILL_DIR = "/Users/federicovargas/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations";
const TMP_DIR = path.join(workspaceDir, ".codex-ppt-build");
const FINAL_PPTX = path.join(workspaceDir, "presentations", "NOEMA_Factored_Hackathon_2026.pptx");
const RUNTIME_PYTHON = "/Users/federicovargas/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";

const { resolvePresentationFont, finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href,
);

await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const slideW = 1280;
const slideH = 720;
const navy = "#071826";
const ink = "#132433";
const teal = "#1FB6A6";
const gold = "#C9A45C";
const cream = "#F6F3EC";
const mist = "#E7EEF1";
const slate = "#5E7180";
const font = resolvePresentationFont({ fontFamily: "Aptos" });

const presentation = Presentation.create({ slideSize: { width: slideW, height: slideH } });

function addText(slide, text, x, y, w, h, opts = {}) {
  const box = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  box.text = text;
  box.text.style = {
    typeface: font,
    fontSize: opts.size ?? 24,
    bold: opts.bold ?? false,
    color: opts.color ?? ink,
    autoFit: "shrinkText",
  };
  return box;
}

function addBand(slide, x, y, w, h, fill, line = "none") {
  return slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: line === "none" ? { fill: "none", width: 0 } : line,
  });
}

function title(slide, text, subtitle) {
  addText(slide, text, 70, 42, 840, 54, { size: 34, bold: true, color: ink });
  if (subtitle) addText(slide, subtitle, 72, 96, 920, 35, { size: 17, color: slate });
  addBand(slide, 70, 134, 92, 4, teal);
}

function footer(slide, number) {
  addText(slide, "NOEMA · Factored AI & Data Hackathon 2026", 72, 672, 520, 24, { size: 12, color: slate });
  addText(slide, String(number).padStart(2, "0"), 1165, 670, 48, 24, { size: 12, color: slate, bold: true });
}

function addCard(slide, x, y, w, h, heading, body, accent = teal) {
  addBand(slide, x, y, w, h, "#FFFFFF", { fill: "#D7E2E7", width: 1 });
  addBand(slide, x, y, 6, h, accent);
  addText(slide, heading, x + 22, y + 18, w - 44, 34, { size: 19, bold: true, color: ink });
  addText(slide, body, x + 22, y + 60, w - 44, h - 74, { size: 15, color: "#314554" });
}

function addStep(slide, x, y, label, detail, color = teal) {
  addBand(slide, x, y, 168, 82, "#FFFFFF", { fill: "#D7E2E7", width: 1 });
  addBand(slide, x, y, 168, 7, color);
  addText(slide, label, x + 14, y + 17, 140, 24, { size: 15, bold: true, color: ink });
  addText(slide, detail, x + 14, y + 43, 140, 28, { size: 11.5, color: slate });
}

// Slide 1
{
  const slide = presentation.slides.add();
  slide.background.fill = navy;
  const img = await fs.readFile(path.join(workspaceDir, "assets", "noema-cover-banking-ai.png"));
  slide.images.add({
    blob: img,
    contentType: "image/png",
    alt: "Secure digital banking assistant concept",
    fit: "cover",
    position: { left: 0, top: 0, width: slideW, height: slideH },
  });
  addBand(slide, 0, 0, 590, slideH, { color: navy, transparency: 7 });
  addText(slide, "NOEMA", 74, 160, 390, 76, { size: 58, bold: true, color: "#FFFFFF" });
  addText(slide, "Credit eligibility assistant for safer banking conversations", 78, 244, 435, 86, { size: 25, color: cream });
  addBand(slide, 80, 352, 86, 5, gold);
  addText(slide, "Built for Factored AI & Data Hackathon 2026", 80, 386, 430, 28, { size: 16, color: "#D9E3E7" });
  addText(slide, "Spanish and Portuguese · verified data · deterministic credit policy · structured human handoff", 80, 420, 430, 58, { size: 15, color: "#BACAD1" });
  slide.speakerNotes.textFrame.setText("Sources: README.md sections 1, 2, 3, 4, and 10; docs/00_challenge_brief.md.");
}

// Slide 2
{
  const slide = presentation.slides.add();
  slide.background.fill = cream;
  title(slide, "The banking gap NOEMA targets", "Hackathon scoring rewards systems that act safely, not chatbots that sound confident.");
  addCard(slide, 78, 180, 336, 296, "The risk", "Credit conversations mix identity, eligibility, personal data, and product terms. A fluent answer can still expose data, invent a number, or approve something the bank cannot defend.", gold);
  addCard(slide, 472, 180, 336, 296, "The requirement", "The challenge asks for a working customer-service system with visible understand, decide, act, verify, and escalate stages.", teal);
  addCard(slide, 866, 180, 336, 296, "NOEMA's answer", "The language model explains and clarifies. Database tools provide figures. A policy engine decides eligibility. The system escalates with verified facts when evidence is missing.", "#6D8FB3");
  addText(slide, "Design principle", 82, 530, 160, 28, { size: 18, bold: true, color: ink });
  addText(slide, "No figure comes from the LLM, and the LLM does not decide eligibility.", 252, 526, 820, 38, { size: 25, bold: true, color: ink });
  footer(slide, 2);
  slide.speakerNotes.textFrame.setText("Sources: README.md sections 1, 2, and 3; docs/00_challenge_brief.md. Framing is summarized from the hackathon requirements documented in the repo.");
}

// Slide 3
{
  const slide = presentation.slides.add();
  slide.background.fill = "#FFFFFF";
  title(slide, "System architecture", "The frontend stays thin. The API owns orchestration, tools, policies, and verified reads.");
  addStep(slide, 70, 184, "Understand", "Intent, language, slots, missing facts");
  addStep(slide, 255, 184, "Access guard", "Document and birth date check");
  addStep(slide, 440, 184, "Decide", "Models plus versioned policy");
  addStep(slide, 625, 184, "Act", "Typed tools and role allowlist");
  addStep(slide, 810, 184, "Verify", "Read back every write");
  addStep(slide, 995, 184, "Escalate", "Structured case file");
  addBand(slide, 120, 338, 1040, 1, "#CAD7DD");
  addCard(slide, 78, 388, 330, 160, "Channels", "Next.js UI exposes chat, glass-box diagnostics, case console, and analytics views.", "#6D8FB3");
  addCard(slide, 474, 388, 330, 160, "Service layer", "FastAPI calls the orchestrator, verifier, policy engine, ML models, and tool registry.", teal);
  addCard(slide, 870, 388, 330, 160, "Data and models", "DuckDB and dbt curate gold tables locally. Databricks supports Delta and MLflow planning.", gold);
  footer(slide, 3);
  slide.speakerNotes.textFrame.setText("Sources: README.md sections 3 and 4; docs/18_noema_ai_final_architecture.md. The architecture summary follows the repository diagram and local deployment constraints.");
}

// Slide 4
{
  const slide = presentation.slides.add();
  slide.background.fill = cream;
  title(slide, "Controls that make the assistant defensible", "NOEMA turns safety rules into executable checks instead of relying on prompt wording.");
  const table = slide.tables.add({
    rows: 5,
    columns: 3,
    left: 80,
    top: 170,
    width: 1120,
    height: 330,
    values: [
      ["Risk area", "Control in NOEMA", "Evidence"],
      ["Identity", "Document type, document number, and date of birth before personal data leaves the system", "Three attempts, identical errors, constant-time comparison"],
      ["Numbers", "Grounding checker blocks figures that did not come from tools", "Final answer cannot carry unsupported values"],
      ["Eligibility", "YAML policy and trained models decide credit outcomes", "Policy tested without an LLM"],
      ["Actions", "Writes use typed tools, role checks, idempotency keys, and read-back verification", "Mismatch triggers escalation"],
    ],
  });
  table.styleOptions = { headerRow: true, bandedRows: true };
  for (let c = 0; c < 3; c++) {
    const cell = table.getCell(0, c);
    cell.fill = navy;
    cell.text.style = { typeface: font, fontSize: 15, bold: true, color: "#FFFFFF" };
  }
  for (let r = 1; r < 5; r++) {
    for (let c = 0; c < 3; c++) {
      table.getCell(r, c).text.style = { typeface: font, fontSize: 12.5, color: ink };
    }
  }
  table.borders.assign({ style: "solid", fill: "#CAD7DD", width: 1 });
  addText(slide, "Security posture", 82, 548, 180, 26, { size: 18, bold: true, color: ink });
  addText(slide, "The prototype treats synthetic data as real personal data: hashed traces, short retention windows, read-only business tables, and protected metrics.", 262, 542, 865, 52, { size: 18, color: "#314554" });
  footer(slide, 4);
  slide.speakerNotes.textFrame.setText("Sources: README.md section 2; docs/05_security.md sections 2 through 7; docs/03_credit_policy.md for policy behavior. Table is native and editable.");
}

// Slide 5
{
  const slide = presentation.slides.add();
  slide.background.fill = "#FFFFFF";
  title(slide, "Validation and demo readiness", "The current prototype is ready for a credible hackathon demo, with production gaps stated plainly.");
  addText(slide, "945", 88, 178, 190, 72, { size: 58, bold: true, color: teal });
  addText(slide, "backend tests passed", 94, 252, 220, 34, { size: 18, color: ink, bold: true });
  addText(slide, "23.5M", 386, 178, 220, 72, { size: 58, bold: true, color: gold });
  addText(slide, "source rows audited", 392, 252, 240, 34, { size: 18, color: ink, bold: true });
  addText(slide, "25/25", 704, 178, 220, 72, { size: 58, bold: true, color: "#6D8FB3" });
  addText(slide, "dbt models and tests passed", 710, 252, 270, 34, { size: 18, color: ink, bold: true });
  addText(slide, "5.57%", 1012, 178, 190, 72, { size: 58, bold: true, color: teal });
  addText(slide, "capacity model coverage under conservative rules", 1018, 252, 210, 52, { size: 16, color: ink, bold: true });
  addBand(slide, 78, 355, 1126, 1, "#CAD7DD");
  addCard(slide, 82, 408, 338, 146, "Demo strengths", "Runnable local flow, visible policy diagnostics, verified write patterns, and structured escalation rather than raw transcripts.", teal);
  addCard(slide, 470, 408, 338, 146, "Honest limitation", "The main chatbot endpoint should still move onto the stricter orchestrator and grounding path before production use.", gold);
  addCard(slide, 858, 408, 338, 146, "Submission fit", "The five-slide deck, repository, live URL, and short demo video map directly to the Factored deliverables.", "#6D8FB3");
  footer(slide, 5);
  slide.speakerNotes.textFrame.setText("Sources: docs/23_executive_summary_validation.md; docs/federico_model_and_data_results.txt; README.md section 10. The capacity coverage value reflects conservative abstention rules, not total credit eligibility.");
}

const candidatePath = path.join(TMP_DIR, "NOEMA_Factored_Hackathon_2026_candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);

const result = await finalizePresentation({
  explicitTotalSlideCount: 5,
  requiredNativeTableOwnerSlides: [4],
  requiredNativeChartOwnerSlides: [],
  workspaceDir,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
    "--require-native-table-slide", "4",
  ],
  fontPolicy: { basis: "design", families: [font] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(workspaceDir, ".codex-finalizer", "NOEMA_Factored_Hackathon_2026.validation.json"),
});

for (let i = 0; i < presentation.slides.length; i++) {
  const slide = presentation.slides.get(i);
  const preview = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(TMP_DIR, `slide-${i + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const montage = await presentation.export({ format: "webp", montage: true, scale: 0.6 });
await fs.writeFile(path.join(TMP_DIR, "montage.webp"), new Uint8Array(await montage.arrayBuffer()));

console.log(JSON.stringify({ finalPath: FINAL_PPTX, candidatePath, validation: result }, null, 2));
