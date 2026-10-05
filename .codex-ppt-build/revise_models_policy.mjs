import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { FileBlob, PresentationFile } from '@oai/artifact-tool';
import { finalizePresentation } from '/Users/federicovargas/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations/container_tools/artifact_tool_utils.mjs';

const root = '/Users/federicovargas/Documents/factored-hackathon-2026-noema';
const skill = '/Users/federicovargas/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations';
const source = path.join(root, 'presentations/NOEMA_Factored_Hackathon_2026.pptx');
const build = path.join(root, '.codex-ppt-build/revision');
await fs.mkdir(build, { recursive: true });
const p = await PresentationFile.importPptx(await FileBlob.load(source));
const read = async f => JSON.parse(await fs.readFile(path.join(root, f), 'utf8'));
const interest = await read('ml/model_cards/product_interest.json');
const deep = await read('ml/model_cards/deep_interest.json');
const depth = await read('ml/model_cards/depth_experiment.json');
const capacity = await read('data/models/capacity.json');
const support = await read('ml/model_cards/support_escalation.json');
const churn = await read('ml/model_cards/churn_prediction.json');
const C = { ink: '#132433', navy: '#071826', teal: '#1FB6A6', gold: '#C9A45C', cream: '#F6F3EC', slate: '#5E7180' };
const font = 'Aptos';
const pct = (v, d = 2) => `${(v * 100).toFixed(d)}%`;
const num = v => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f4 = v => v.toFixed(4);

// Retain the imported cover and architecture, including their image and theme.
p.slides.remove(4);
p.slides.remove(3);
p.slides.remove(1);
p.resolve('sh/21szqxcb').text = '02';
p.resolve('sh/a5c3ql8z').text = 'Versioned policy with capacity cap';
p.resolve('sh/cza94vmx').text = 'Credit conversations require evidence, a policy decision, and confirmation of every recorded action.';
p.resolve('sh/4nuhs7uh').text = '23.5M source rows audited. DuckDB and dbt curate local data. Model cards record comparisons and limitations.';
p.slides.items[1].speakerNotes.textFrame.setText('NOEMA separates language understanding, identity checks, deterministic eligibility, tool execution, read-back verification, and structured escalation. Models support specific tasks: product-interest ranking and a bounded cash-flow estimate. They do not learn a defensible credit approval label from this dataset. The visible architecture is the repository design, not certification that every deployed endpoint enforces every control. Sources: README.md; agent/policies/engine.py; agent/core/orchestrator.py; agent/core/verifier.py; docs/23_executive_summary_validation.md. Audit total: 23,495,188 rows, from docs/federico_model_and_data_results.txt.');

function text(s, value, x, y, w, h, size = 22, bold = false, color = C.ink) {
  const a = s.shapes.add({ geometry: 'textbox', position: { left: x, top: y, width: w, height: h }, fill: 'none', line: { fill: 'none', width: 0 } });
  a.text = value;
  a.text.style = { typeface: font, fontSize: size, bold, color, autoFit: 'none' };
  return a;
}
function slide(title, subtitle, notes) {
  const s = p.slides.add();
  s.background.fill = p.slides.items.length % 2 ? '#FFFFFF' : C.cream;
  text(s, title, 70, 42, 1140, 55, 34, true);
  text(s, subtitle, 72, 102, 1136, 42, 18, false, C.slate);
  s.shapes.add({ geometry: 'rect', position: { left: 70, top: 148, width: 92, height: 4 }, fill: C.teal, line: { fill: 'none', width: 0 } });
  text(s, 'NOEMA  /  Factored AI & Data Hackathon 2026', 72, 672, 750, 25, 12, false, C.slate);
  text(s, String(p.slides.items.length).padStart(2, '0'), 1165, 672, 48, 25, 12, true, C.slate);
  s.speakerNotes.textFrame.setText(notes.replace('36.4974%', '36.4969%').replace('22.0586%', '22.0591%').replace('509.42 at24months,304.79 at48months,240.14 at72months', '509.45 at24months,304.84 at48months,240.11 at72months'));
  return s;
}
function table(s, values, widths, y = 178, height = 285, size = 20) {
  const t = s.tables.add({ rows: values.length, columns: values[0].length, left: 72, top: y, width: 1136, height, columnWidths: widths, values });
  t.styleOptions = { headerRow: true, bandedRows: false };
  for (let r = 0; r < values.length; r++) for (let c = 0; c < values[0].length; c++) {
    const cell = t.getCell(r, c);
    cell.fill = r === 0 ? C.navy : r % 2 ? '#FFFFFF' : '#EDF3F4';
    cell.text.style = { typeface: font, fontSize: size, bold: r === 0 || c === 0, color: r === 0 ? '#FFFFFF' : C.ink, autoFit: 'none' };
  }
  t.borders.assign({ style: 'solid', fill: '#CCD8DE', width: 0.6 });
  return t;
}
function block(s, heading, body, x, y, w = 540, h = 90) {
  text(s, heading, x, y, w, 30, 23, true);
  text(s, body, x, y + 38, w, h, 20);
}
function foot(s, value, y = 604) { text(s, value, 74, y, 1130, 54, 17, false, C.slate); }

{
  const m = interest.splits.test.model, b = interest.splits.test.baseline, n = deep.splits.test.deep_mlp;
  const gain = (b.log_loss - m.log_loss) / b.log_loss;
  const s = slide('Trained models versus baseline', 'Product interest: observed campaign conversion within 30 days. Test set: 248,875 exposures.',
    `Sources: ml/model_cards/product_interest.json and deep_interest.json; ml/training/product_interest.py. Test period: May-November 2025, 1,216 positive cases, prevalence ${pct(m.prevalence, 3)}. Baseline predicts the training conversion prior for every exposure. Logistic regression uses product, channel, prior sends and send month. Deep MLP uses the same inputs. Logistic test log loss improves by ${pct(gain)} relative to the prior, AP by ${pct((m.average_precision / b.average_precision) - 1)}, and top-decile lift is ${m.lift_top_10pct.toFixed(2)}x. These are retrospective ranking results, not causal uplift or credit approval accuracy. Selection uses validation, not the displayed test. Models remain marked production_ready=false. AP means average precision, ROC-AUC measures ranking, log loss evaluates probabilities, and lift compares top-decile conversion with the full test prevalence. The small absolute AP reflects the rare outcome.`);
  table(s, [
    ['Model', 'ROC-AUC', 'AP', 'Log loss', 'Top 10% lift'],
    ['Prior baseline', f4(b.roc_auc), f4(b.average_precision), b.log_loss.toFixed(5), '1.00x'],
    ['Logistic regression', f4(m.roc_auc), f4(m.average_precision), m.log_loss.toFixed(5), `${m.lift_top_10pct.toFixed(2)}x`],
    ['MLP: 32 / 16 / 8', f4(n.roc_auc), f4(n.average_precision), n.log_loss.toFixed(5), `${n.lift_top_10pct.toFixed(2)}x`],
  ], [330, 185, 180, 205, 236], 181, 264, 21);
  block(s, 'Selected: logistic regression', '5.48% lower test log loss than the prior.\nValidation favored logistic over the MLP.', 76, 480, 530, 78);
  block(s, 'Scope of the result', 'Test conversion prevalence: 0.489%.\nProduct interest never authorizes credit.', 668, 480, 535, 78);
  foot(s, 'Higher is better for ROC-AUC, AP and lift. Lower is better for log loss. Both candidates remain experimental.');
}
{
  const s = slide('Training adjustments and measured outcomes', 'Model selection follows validation evidence. Greater depth did not produce a reliable improvement.',
    'Sources: ml/training/product_interest.py; ml/model_cards/deep_interest.json; ml/model_cards/depth_experiment.json; ml/training/depth_experiment.py. Product-interest preparation one-hot encodes categories, imputes numeric values using training medians with missingness indicators, and scales numerics. Logistic C=1.0, max_iter=1000, seed=42. MLP uses ReLU hidden layers, sigmoid output, Adam, alpha=0.01, learning rate=0.001, batch=1024, patience=4. The initial MLP run used at most 20 epochs and selected epoch 14. Follow-up depth study uses 30 epochs and seeds 42,43,44, with separate stopping and selection periods. Three-layer selection mean log loss=0.0325569, six-layer=0.0325812, logistic=0.0323455. Three-layer mean AP is higher, but logistic has better log loss and Brier. The recommendation remains logistic. Cleaning and validation controls improve evidence quality; no isolated ablation proves the metric contribution of each preprocessing step. No new training is claimed by this presentation.');
  table(s, [
    ['Adjustment', 'Implementation', 'Evidence / outcome'],
    ['Leakage control', '30-day label maturity and temporal gaps.\nOnly information available before each send.', '557,603 train / 99,158 validation.\n248,875 test exposures.'],
    ['Preprocessing', 'One-hot categories, numeric imputation,\nstandardization. Logistic C = 1.0.', 'Logistic test AUC 0.6767\nversus prior 0.5000.'],
    ['Neural regularization', 'Adam, L2 = 0.01, learning rate 0.001.\nEarly stopping with patience 4.', 'Initial MLP selected epoch 14.\nValidation log loss still favors logistic.'],
    ['Depth experiment', '3 versus 6 hidden layers, 3 seeds,\n30-epoch limit, separate selection set.', 'Selection mean log loss: 0.03256\nvs 0.03258. Logistic: 0.03235.'],
  ], [256, 466, 414], 180, 368, 18);
  foot(s, 'Measured gains belong to the complete pipelines. Per-adjustment gains were not isolated in ablation studies.', 579);
}
{
  const s = slide('Repayment capacity: conservative cash-flow proxy', '150,000 training examples. 14,820 temporal validation examples from October-November 2025.',
    'Sources: data/models/capacity.json; ml/training/capacity.py. Target=min(max(monthly deposits-monthly outflows,0),0.30*monthly deposits). Baseline=min(previous-three-month minimum surplus,0.30*previous-three-month mean deposits). LinearRegression(positive=True) predicts the future target from mean deposits, mean outflows, minimum surplus and active months. Prediction is clipped to [0, baseline], so the learned model can only lower this ceiling. Last two complete months form validation. Training is capped at 150,000 rows with seed 42 after deterministic customer sampling hash(customer_id)%20=0. Metrics describe all 14,820 validation rows, not only the 825 rows meeting serving evidence requirements. Eligibility for serving requires three active months and no ambiguous transfers/adjustments. Aggregate MAE 92,731.04 baseline vs 92,369.45 model gives 0.39% reduction, but mixes currencies and must not support cross-country claims. No observed solvency/default label and no external validation.');
  const rows = [['Currency', 'Baseline MAE', 'Model MAE', 'Reduction']];
  for (const [currency, m] of Object.entries(capacity.metrics.by_currency)) rows.push([currency, num(m.baseline_mae), num(m.model_mae), pct(1 - m.model_mae / m.baseline_mae)]);
  table(s, rows, [230, 310, 310, 286], 181, 248, 21);
  block(s, 'Bounded estimate', 'Positive linear regression, capped by the\nthree-month cash-flow baseline.', 76, 461, 540, 70);
  block(s, 'Evidence coverage: 5.57%', '825 / 14,820 rows meet the history rules.\nMissing or ambiguous history causes abstention.', 668, 461, 536, 80);
  foot(s, 'MAE is in each currency\'s native units. Coverage describes usable evidence, not an approval rate. Gains are modest.');
}
{
  const s = slide('Eligibility and financial offer policy', 'Policy version 3 applies explicit prototype business assumptions to verified customer facts.',
    'Sources: agent/policies/eligibility_v1.yaml (version:3, effective 2026-10-02, data cutoff 2025-12-31); agent/policies/engine.py; agent/tools/credit.py; agent/core/verifier.py. Rules are prototype business choices, not regulatory thresholds. Missing positive income or missing credit limit/rate causes abstention. Additional product requires 6 months tenure; at 4 existing credit products no new offer; current DTI>=60% blocks; current granted exposure>3*annual income blocks. DTI budget is normally 40%, or 45% when reserves cover >=6 months of positive current obligations. Policy margin=max(0,DTI budget*income-current obligations). Available capacity caps this margin; absent capacity multiplies it by 0.80 and excludes mortgages. Per-product checks include segment, minimum, maximum, term and reserves. Tools record a quote and read it back before success. A quote is not a disbursement. The strict path has these controls, while end-to-end deployment enforcement requires validation.');
  block(s, '1. Check evidence and current debt', 'Positive income and complete obligation terms.\n6-month tenure for an additional product.\nFewer than 4 existing credit products.', 76, 184, 540, 103);
  block(s, '2. Calculate the payment budget', 'Debt-to-income (DTI) budget: 40%. Hard stop: 60%.\n45% if reserves cover 6 current-payment months.\nExisting exposure capped at 3x annual income.', 668, 184, 536, 103);
  block(s, '3. Apply the capacity restriction', 'Use the lower of policy margin and ML capacity.\nWithout a capacity estimate: 20% margin cut\nand no mortgage offer.', 76, 384, 540, 103);
  block(s, '4. Validate and record the offer', 'Check segment, amount, term and reserves.\nPublish payment, effective rate and total interest.\nRecord quote, read it back, or escalate.', 668, 384, 536, 103);
  foot(s, 'The policy determines eligibility. Commercial scores cannot override it. Recorded quotes do not constitute disbursement.');
}

async function save(name) {
  name += '_v2';
  const candidatePath = path.join(build, `${name}-candidate.pptx`);
  await (await PresentationFile.exportPptx(p)).save(candidatePath);
  const owners = p.slides.items.flatMap((s, i) => s.tables.items.length ? [i + 1] : []);
  const result = await finalizePresentation({
    explicitTotalSlideCount: p.slides.items.length,
    requiredNativeTableOwnerSlides: owners,
    requiredNativeChartOwnerSlides: [],
    workspaceDir: root, candidatePath,
    finalPath: path.join(root, 'presentations', `${name}.pptx`),
    pythonExecutable: '/Users/federicovargas/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
    integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
    layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit', ...owners.flatMap(n => ['--require-native-table-slide', String(n)])],
    fontPolicy: { basis: 'reference', families: [font], referencePath: source, referenceSha256: crypto.createHash('sha256').update(await fs.readFile(source)).digest('hex') },
    verifyArtifactToolImport: true,
    receiptPath: path.join(root, '.codex-finalizer', `${name}.validation.json`),
  });
  console.log(JSON.stringify({ name, slides: p.slides.items.length, result }));
}
await save('NOEMA_Factored_2026_Updated');

{
  const s = slide('Product-interest model: data and validation', 'Target: conversion within 30 days of a campaign send. The model ranks observed campaign opportunities.',
    'Sources: ml/training/product_interest.py and ml/model_cards/product_interest.json. The source audit counts 1,746,801 exposures and 979,681 eligible rows before temporal split/embargo. Audit exclusion categories can overlap and should not be summed as a waterfall. Same customers may recur across time. Customer-cluster bootstrap with 100 repetitions gives test ROC-AUC interval [0.66750,0.68891] and AP interval [0.00744,0.00922]. Those intervals are conditional on the test period. Training uses exposures July 2023-November 2024, validation January-March 2025 and test May-November 2025. December and April create gaps for label maturation. Process-date availability is enforced at split boundaries. Inputs exclude target-campaign opens and clicks and any post-send outcome. Product/channel metadata are assumed stable and lack a versioned availability history.');
  table(s, [
    ['Split', 'Period', 'Exposures', 'Conversions'],
    ['Training', 'Jul 2023-Nov 2024', '557,603', '3,183'],
    ['Validation', 'Jan-Mar 2025', '99,158', '431'],
    ['Test', 'May-Nov 2025', '248,875', '1,216'],
  ], [240, 416, 240, 240], 180, 252, 21);
  block(s, 'Inputs known before the send', 'Promoted product, channel, prior send count\nand send month. Target opens/clicks excluded.', 76, 468, 540, 80);
  block(s, 'Uncertainty and generalization', 'Test ROC-AUC 95% interval: 0.6675-0.6889.\nRepeated customers limit new-customer claims.', 668, 468, 536, 80);
  foot(s, 'Validation uses a 30-day maturation gap. Bootstrap intervals reflect customer clustering within the test period.');
}
{
  const s = slide('Neural depth experiment and selection', 'Separate stopping and selection windows. Three seeds: 42, 43 and 44. Maximum 30 epochs.',
    'Sources: ml/model_cards/depth_experiment.json; ml/training/depth_experiment.py. Three hidden layers=[32,16,8], 1,153 parameters. Six hidden layers=[32,32,16,16,8,8], 2,553 parameters. Training through November 2024, stopping in January 2025, selection from March 3, test from May. Selection set contains 34,142 exposures and 187 positives. ReLU, Adam, alpha 0.01, learning rate 0.001, batch 1024, patience 4. Selection summary reports means over 3 seeds for neural families; logistic is a single deterministic baseline run. Preferred neural family is three_hidden, recommended model logistic. Test fixed seed 42 yields six-layer AUC 0.67758, logistic 0.67672; this small test difference does not justify changing the validation choice. The test was reused from previous experiments and is not fresh external validation. Standard deviation over seeds is not a confidence interval.');
  table(s, [
    ['Candidate', 'Parameters', 'Selection AUC', 'Selection AP', 'Selection loss'],
    ['Logistic', 'Linear model', '0.6572', '0.00805', '0.03235'],
    ['3 hidden layers', '1,153', f4(depth.summary.three_hidden.roc_auc.mean), depth.summary.three_hidden.average_precision.mean.toFixed(5), depth.summary.three_hidden.log_loss.mean.toFixed(5)],
    ['6 hidden layers', '2,553', f4(depth.summary.six_hidden.roc_auc.mean), depth.summary.six_hidden.average_precision.mean.toFixed(5), depth.summary.six_hidden.log_loss.mean.toFixed(5)],
  ], [268, 200, 226, 216, 226], 182, 258, 19);
  block(s, 'What changed', 'Depth more than doubled the parameter count.\nEarly stopping and L2 constrained overfitting.', 76, 474, 540, 76);
  block(s, 'What the comparison supports', 'The shallower network had better mean results.\nLogistic retained the best selection log loss.', 668, 474, 536, 76);
  foot(s, 'Neural rows report means across seeds. The reused test is not an independent confirmation of model improvements.');
}
{
  const sm = support.splits.test;
  const s = slide('Other model experiments and evidence limits', 'A trained artifact alone does not establish useful predictive performance.',
    'Sources: ml/model_cards/support_escalation.json; ml/model_cards/churn_prediction.json; ml/training/churn_prediction.py; ml/training/customer_segmentation.py. Support escalation: trained logistic on channel, interaction type, reason category with temporal train/validation/test, 88,976 test rows. Logistic AUC=0.497402 versus prior 0.5; AP=0.097986 versus 0.099251; signal_gate_passed=false. User-requested human escalation must remain available regardless of scores. Churn V2: 100-tree random forest, class_weight=balanced, one-hot encoding, StandardScaler, train_test_split test_size=0.2 random_state=42. Training code fills product_count and total_balance_usd structural nulls and drops remaining incomplete rows. Card reports accuracy 0.841953, precision 0.151659, recall 0.014506, F1 0.026479. No baseline benchmark or forward temporal evaluation is reported, so no improvement claim is supported. Customer segmentation script fits 50-tree random forest and scores on the training data, explicitly a mock. Its production_ready flag cannot substitute for held-out evidence.');
  table(s, [
    ['Experiment', 'Recorded result', 'Decision / limitation'],
    ['Support escalation\nLogistic regression', `Test AUC ${f4(sm.logistic.roc_auc)} vs 0.5000.\nAP ${f4(sm.logistic.average_precision)} vs ${f4(sm.prior.average_precision)}.`, 'Failed signal gate.\nKeep rule-based escalation.'],
    ['Churn V2\nBalanced random forest', `Accuracy ${pct(churn.metrics.Accuracy)}.\nRecall ${pct(churn.metrics.Recall)}, F1 ${churn.metrics['F1-Score'].toFixed(4)}.`, 'Low recall. No baseline reported.\nCannot claim a verified uplift.'],
    ['Customer segmentation\nRandom forest prototype', 'Training-set evaluation only\nin the available script.', 'No held-out evidence.\nExclude from performance claims.'],
  ], [315, 398, 423], 181, 330, 20);
  foot(s, 'These experiments are separate from the deterministic eligibility policy and cannot override its decision.', 554);
}
{
  const s = slide('Capacity model: target, ceiling and abstention', 'The learned output estimates a monthly cash-flow proxy. It can only restrict the policy budget.',
    'Sources: ml/training/capacity.py; data/models/capacity.json. Approved transactions only, with operation and process dates before the cutoff. Calendar months are completed and missing activity months are represented as zero activity. Per customer/currency, three lagged months form features. Deposits are Deposit/Deposito; outflows Payment/Purchase/Withdrawal and translated equivalents. Transfers and adjustments count as ambiguous. Target and baseline are distinct: target is the next monthly proxy, baseline uses prior-three-month history. Nonnegative coefficients constrain the learned regression, not all economic relationships. Intercept and coefficients come from pooled native-currency data, limiting comparability. Output is clipped to [0,ceiling]. Serving needs 3 active months, no ambiguity and the requested currency. Aggregate selection favors model by 0.39% MAE but this is modest and currency-scale sensitive. Metrics were computed across all validation rows, not solely the serving-eligible subset.');
  block(s, 'Training target', 'Monthly surplus = max(deposits - outflows, 0).\nProxy = min(surplus, 30% of deposits).', 76, 183, 540, 76);
  block(s, 'Historical baseline', 'Ceiling = min(lowest prior 3-month surplus,\n30% of prior 3-month mean deposits).', 668, 183, 536, 76);
  block(s, 'Learned estimator', 'Nonnegative linear regression on mean deposits,\nmean outflows, minimum surplus, active months.\nFinal estimate stays between zero and ceiling.', 76, 370, 540, 114);
  block(s, 'Abstention gate', 'Require 3 active months in the requested currency.\nTransfers or adjustments make history ambiguous.\nNo usable history means no capacity estimate.', 668, 370, 536, 114);
  foot(s, 'All-validation MAE and serving coverage use different populations. The proxy does not establish observed solvency.');
}
{
  const s = slide('Eligibility rules and decision order', 'Incomplete evidence causes abstention. The first failed customer rule determines the rejection reason.',
    'Sources: agent/policies/engine.py evaluar and agent/policies/eligibility_v1.yaml version 3. Income must be positive. Missing limit or annual rate on an existing credit obligation causes abstention before DTI computation. Rules proceed through tenure, product count, hard DTI, current granted exposure, and remaining margin. Existing-product count at 4 blocks another. Exposure check is on existing granted credit and does not itself prove a post-offer combined exposure ceiling. Qualifying reserves may raise DTI budget to 45%, but the separate current DTI hard cutoff remains 60%. Net worth is published as a fact and is not a decision threshold. Delinquency cannot be reliably determined. Policy comments retaining an older remaining-term formula are superseded by executable _carga: fixed-loan payment uses original total term.');
  table(s, [
    ['Check', 'Rule in policy version 3', 'Outcome on failure'],
    ['Evidence', 'Positive income. Complete existing limits and rates.', 'Abstain and refer'],
    ['Relationship', 'At least 6 months if credit already exists.', 'Reject additional product'],
    ['Product count', 'Fewer than 4 existing credit products.', 'Reject'],
    ['Current DTI', 'Current monthly obligations / income < 60%.', 'Reject'],
    ['Existing exposure', 'Granted credit <= 3 x annual income.', 'Reject'],
    ['Available margin', 'Positive margin after policy and capacity limits.', 'Reject if no budget'],
  ], [255, 601, 280], 177, 385, 18);
  foot(s, 'Prototype assumptions, not legal requirements. Net worth and payment counts are descriptive facts, not approval rules.');
}
{
  const effective = nominal => ((1 + nominal / 1200) ** 12 - 1) * 100;
  const s = slide('Product catalog and offer constraints', 'All catalog limits are in USD. Rates and terms come from the versioned prototype policy.',
    'Sources: agent/policies/eligibility_v1.yaml; agent/policies/engine.py; agent/tools/credit.py. Credit card: nominal 31.52%, effective 36.4974%, minimum 500, maximum 100000, all Basic/Plus/Premium/Student segments, revolving minimum-payment assumption 5%, no reserve requirement. Config contains a 48-month value, but this is not an amortization schedule. Personal loan: nominal 20.10%, effective 22.0586%, USD1000-150000, terms24/48/72 months, Basic/Plus/Premium, reserves cover1 proposed payment. Mortgage nominal8.98%, effective9.3590%, USD20000-500000, terms120/180/240 months, Plus/Premium, reserves cover3 proposed payments, requires available cash-flow estimate. Effective rate=(1+nominal/12)^12-1 with nominal expressed as fraction. Fees and jurisdiction-specific disclosures are not established by these calculations. Annual rates are policy values based on source medians, not current market quotes. The authoritative catalog is YAML, not placeholder gold.product_policy rows.');
  table(s, [
    ['Product', 'USD range', 'Nominal / effective', 'Terms (months)', 'Reserves'],
    ['Credit card', '500-100,000', `31.52% / ${effective(31.52).toFixed(2)}%`, 'Revolving', 'None'],
    ['Personal loan', '1,000-150,000', `20.10% / ${effective(20.10).toFixed(2)}%`, '24 / 48 / 72', '1 payment'],
    ['Mortgage', '20,000-500,000', `8.98% / ${effective(8.98).toFixed(2)}%`, '120 / 180 / 240', '3 payments'],
  ], [230, 235, 266, 245, 160], 180, 258, 19);
  block(s, 'Segment restrictions', 'Card: all four segments. Personal: Basic, Plus,\nPremium. Mortgage: Plus and Premium.', 76, 469, 550, 83);
  block(s, 'Quote-level checks', 'Cap the amount by budget and catalog maximum.\nValidate the minimum and reserves at each term.', 674, 469, 530, 83);
  foot(s, 'Longer fixed-loan terms lower the payment but increase total interest. A revolving line has no fixed total interest.');
}
{
  const payment = (principal, months) => { const i = .201 / 12; return principal * i / (1 - (1 + i) ** -months); };
  const s = slide('Worked example: a USD 10,000 personal loan', 'Illustrative scenario using policy version 3. These are assumed inputs, not a recorded customer outcome.',
    'Sources: agent/policies/engine.py cuota_francesa and evaluar; agent/policies/eligibility_v1.yaml. Example assumptions: Basic segment, established relationship, monthly income USD3000, current obligations USD600, current granted exposure USD10000, one existing credit product, liquid reserves USD1500, available capacity estimate USD450/month. Reserves cover2.5 months of current obligations, below6, so DTI cap stays40%. Base margin=0.4*3000-600=600. Capacity caps it at450. Current DTI20% passes hard60%; existing exposure10000 is under108000; other customer rules pass. At nominal20.10% the requested10000 costs approximately509.42 at24months,304.79 at48months,240.14 at72months. 24months cannot fund the full requested principal within450 but may produce a lower counteroffer. 48/72 pass one-payment reserve requirement. Calculations use full precision before display rounding. Total interest=payment*months-principal. Quote recording and verification remain separate subsequent actions.');
  text(s, 'Income $3,000   Current payments $600   Reserves $1,500   ML capacity $450 / month', 76, 177, 1126, 43, 21, true);
  text(s, 'Policy margin: 40% x $3,000 - $600 = $600. Final payment budget: min($600, $450) = $450.', 76, 230, 1126, 57, 22);
  table(s, [
    ['Term', 'Monthly payment', 'Total interest', 'Full $10,000 request'],
    ...[24, 48, 72].map(n => [String(n), `$${num(payment(10000, n))}`, `$${num(payment(10000, n) * n - 10000)}`, n === 24 ? 'Over budget: lower counteroffer' : 'Fits budget and reserves']),
  ], [140, 265, 265, 466], 321, 236, 20);
  foot(s, 'The customer can compare lower monthly payments against higher total interest. The effective annual rate is unchanged.');
}
{
  const s = slide('Policy refinements and offer verification', 'The implemented changes address missing evidence, repayment arithmetic and traceable product terms.',
    'Sources: agent/policies/engine.py _carga and evaluar; agent/policies/eligibility_v1.yaml; agent/tools/credit.py record_offer_quote; agent/core/verifier.py; tests/policies; tests/tools/test_escrituras_y_relectura.py. Existing card load is max(5% drawn balance,USD25) when drawn balance>0, plus5%*10% of unused line. Unknown drawn balance assumes full line. Existing fixed-loan payment uses original total term rather than remaining term. Reserves count eligible liquid accounts at100% and investments at70%; >=6 current-payment months permits45% DTI. Missing capacity now cuts policy margin by20% and excludes mortgages. Multiple terms evaluate minimum, ceiling and reserves separately and publish total interest. Removed unsupported payment-compliance rule never executed, so removing it alone did not change decisions. Record_offer_quote validates selected product and term against eligible offers; tools enforce roles and idempotency, then verifier reads persisted fields. Grounding checks compare response values with tool evidence. Validation tests exist in repository, but no new suite run or production enforcement claim is made here.');
  table(s, [
    ['Refinement', 'Implemented behavior'],
    ['Missing debt or capacity', 'Missing limit/rate triggers abstention. Missing cash flow cuts margin 20% and excludes mortgages.'],
    ['Correct repayment arithmetic', 'Existing loans use total term. Cards use drawn balance plus an unused-line stress allowance.'],
    ['Term and reserve checks', 'Evaluate each term, price the actual requested amount, and disclose any lower counteroffer.'],
    ['Verified quote workflow', 'Match product and term to eligible offers. Record idempotently, read back, and verify fields.'],
  ], [323, 813], 180, 353, 20);
  foot(s, 'Every decision carries policy version, facts, reasons and warnings. Missing evidence or failed verification can trigger a case.');
}
{
  const s = slide('Repayment obligations and reserve rules', 'Policy version 3 distinguishes existing debt, liquid reserves and the budget available for a new offer.',
    'Sources: agent/policies/engine.py _carga, _reservas and evaluar; agent/policies/eligibility_v1.yaml. Existing fixed-loan installments use granted principal and original total term, not remaining term. The policy discloses assumed terms when contractual terms are unavailable. Existing revolvers use max(5% drawn balance,25 USD) when drawn balance is positive plus0.5% unused line (5% minimum times10% stress factor). Missing drawn balance assumes full credit limit. Liquid eligible accounts count100%, investments70%, reserve compensation uses reserves divided by positive CURRENT monthly debt service. At least6 months raises DTI budget from40% to45%. Required reserves on a proposed loan are measured against its PROPOSED installment: personal1, mortgage3, card0. New revolving quote payment uses5% of offered line. Fixed-loan formula uses i=nominal annual fraction/12 and n=months. These are prototype underwriting assumptions and not universal banking or regulatory rules.');
  block(s, 'Existing fixed-payment loans', 'Monthly payment = P x i / [1 - (1 + i)^(-n)].\nUse the original total term, not remaining term.\nDeclare any assumed term.', 76, 183, 540, 108);
  block(s, 'Existing revolving cards', '5% of drawn balance, with a $25 payment floor.\nAdd 0.5% of the unused line as stress.\nUnknown balance: assume the full line is drawn.', 668, 183, 536, 108);
  block(s, 'Recognized reserves', 'Eligible liquid account balances count at 100%.\nInvestment balances count at 70%.\n6 months of current payments permits 45% DTI.', 76, 383, 540, 108);
  block(s, 'Reserves for the proposed product', 'Personal loan: cover 1 proposed payment.\nMortgage: cover 3 proposed payments.\nCard: no minimum reserve requirement.', 668, 383, 536, 108);
  foot(s, 'P = principal, i = monthly rate, n = months. Payment floor applies to a positive drawn balance. All are prototype rules.');
}
await save('NOEMA_Factored_2026_Technical_Expanded');
await fs.writeFile(path.join(build, 'contents.ndjson'), (await p.inspect({ kind: 'slide,textbox,table,notes', maxChars: 100000 })).ndjson);
console.log('Both revised decks exported.');
