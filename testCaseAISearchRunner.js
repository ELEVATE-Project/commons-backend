#!/usr/bin/env node

/**
 * AI Search Filter Test Runner
 *
 * Replays every row of the test-case CSV through the live /api/v2/media/
 * endpoint and scores the filters the view resolved against the expectations
 * recorded in the CSV.
 *
 * Requirements:
 *   - Node.js 18+ (uses built-in fetch)
 *   - No npm packages required
 *
 * Usage:
 *   node testCaseAISearchRunner.js
 *
 * This script is self-contained: everything it needs is in the CONFIGURATION
 * block below. It reads no environment variables and no command-line
 * arguments, so a run is reproducible from the file alone. To switch
 * environment, comment out the active block and uncomment the other.
 *
 * Output:
 *   <input-name>_results_<ENV_NAME>.csv
 *
 * What is compared
 * ----------------
 * The view reports filters twice in search_metadata, and only one of them is
 * the right yardstick:
 *
 *   filter_resolution - how the filters were *decided*. Carries semantic_query
 *                       and the un-widened media types. This is what the CSV
 *                       expectations were written against.
 *   applied_filters   - what was actually sent to Qdrant, *after* alias
 *                       expansion, so ["application/pdf"] arrives as
 *                       ["application/pdf","PDF","pdf",".pdf","PDFs","pdfs"].
 *                       It also carries no semantic_query at all.
 *
 * Scoring therefore reads filter_resolution, matching
 * chatbot/scripts/ai_search/run_filter_test_cases.py so the two harnesses can
 * never disagree. applied_filters is still recorded, as evidence of what the
 * expansion produced.
 */

const fs = require("fs");
const path = require("path");

// ======================= CONFIGURATION =======================
// Exactly one environment block may be active at a time.

// ---- LOCAL (active) -----------------------------------------
const ENV_NAME = "LOCAL";
const BASE_URL = "http://localhost:9000";
const COOKIE = ""; // Not required: MediaSearchV2View resolves to AllowAny.

// This script never picks the model itself — it hits whatever AI_SERVICE_MODEL
// the backend is currently configured with (see .env). Set this to match, by
// hand, before each run, so the two models' result CSVs don't overwrite each
// other. Kept as a plain label rather than plumbed through the request path
// because switching models here is a manual .env edit + backend restart, not a
// per-request choice.
// const MODEL_LABEL = "gemini-3.1-flash-lite";
const MODEL_LABEL = "gpt-4.1-mini";

// ---- QA (commented out while testing LOCAL) -----------------
// const ENV_NAME = "QA";
// const BASE_URL = "https://qa.elevate-commons.shikshalokam.org";
// const COOKIE = "";

const INPUT_FILE =
  "/Users/priyankapradeep/Desktop/SG_COMMON/commons-backend/testCasesAISearch.csv";

// A vector query takes seconds; a hung one must not stall the whole run.
const REQUEST_TIMEOUT_MS = 60000;
const REQUEST_DELAY_MS = 0;

// Case ids to run, e.g. ["TC117", "TC198"]. Empty means every row.
const ONLY_CASES = [];
// Representative subset spanning every scenario bucket, used for the first
// pass per model before committing to the full 218-case run. Blank this array
// for the full run.
// ["TC017", "TC018", "TC019", "TC020", "TC021", "TC022", "TC023", "TC024", "TC025", "TC026"];
// ["TC001", "TC002", "TC003", "TC004", "TC005", "TC006", "TC007", "TC008", "TC009", "TC010"];
// =============================================================

if (!fs.existsSync(INPUT_FILE)) {
  console.error(`Input CSV not found: ${INPUT_FILE}`);
  process.exit(1);
}

const parsedInput = path.parse(INPUT_FILE);
const OUTPUT_FILE = path.join(
  parsedInput.dir,
  `${parsedInput.name}_results_${ENV_NAME}_${MODEL_LABEL}.csv`
);

// Reused verbatim from run_filter_test_cases.py so a diff across the two
// harnesses shows behaviour changes rather than rewording.
const PATH_POSTGRES =
  "LLM call → filters only, no residual query → " +
  "PostgreSQL only (no Vector Service call)";
const PATH_VECTOR =
  "LLM call → residual query or any_of present → Vector Service call";
const PATH_NO_LLM = "No LLM call (empty/whitespace query) → PostgreSQL only";

function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

function escapeCSV(value) {
  if (value === null || value === undefined) return "";

  let text = typeof value === "string" ? value : JSON.stringify(value);

  if (
    text.includes(",") ||
    text.includes('"') ||
    text.includes("\n") ||
    text.includes("\r")
  ) {
    text = `"${text.replace(/"/g, '""')}"`;
  }

  return text;
}

function writeCSV(headers, records, outputFile) {
  const lines = [headers.map(escapeCSV).join(",")];

  for (const record of records) {
    lines.push(
      headers.map((header) => escapeCSV(record[header] ?? "")).join(",")
    );
  }

  fs.writeFileSync(outputFile, `${lines.join("\n")}\n`, "utf8");
}

function rowsToObjects(rows) {
  if (!rows.length) return { headers: [], records: [] };

  // The input carries a trailing empty header; keeping it would collide every
  // unnamed column onto a single "" key and emit a stray column on the way out.
  const headers = rows[0].map((h) => h.trim()).filter((h) => h !== "");

  const records = rows
    .slice(1)
    .filter((row) => row.some((value) => String(value).trim() !== ""))
    .map((row) => {
      const obj = {};
      headers.forEach((header, index) => {
        obj[header] = row[index] ?? "";
      });
      return obj;
    });

  return { headers, records };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Canonicalize JSON before comparison.
 *
 * - Object key order does not matter.
 * - Array order does not matter: filter arrays are sets, and any_of branches
 *   are OR'ed, so neither carries meaning in its ordering.
 */
function canonicalize(value) {
  if (Array.isArray(value)) {
    const normalized = value.map(canonicalize);

    return normalized.sort((a, b) =>
      JSON.stringify(a).localeCompare(JSON.stringify(b))
    );
  }

  if (value && typeof value === "object") {
    const output = {};

    for (const key of Object.keys(value).sort()) {
      output[key] = canonicalize(value[key]);
    }

    return output;
  }

  return value;
}

/**
 * An any_of branch reduced to something order-insensitively comparable.
 *
 * Empty-valued keys are dropped so a block that omits a field and one that
 * sets it to [] compare equal.
 */
function normalizedAnyOf(blocks) {
  return (blocks || []).map((block) => {
    const kept = {};

    for (const [key, values] of Object.entries(block || {})) {
      if (Array.isArray(values) ? values.length : values) {
        kept[key] = values;
      }
    }

    return kept;
  });
}

/**
 * The whole payload, canonicalized as one comparable unit.
 *
 * semantic_query is excluded: it is scored separately against
 * expected_semantic_query, not as part of this object.
 */
function normalizedPayload(source) {
  const { semantic_query, any_of, ...rest } = source || {};

  return canonicalize({ ...rest, any_of: normalizedAnyOf(any_of) });
}

/**
 * The search_metadata block for one response.
 *
 * The view nests it under the top-level key, but older builds wrapped the
 * response differently, so fall back to a breadth-first hunt for a block that
 * carries filter_resolution rather than failing outright.
 */
function extractSearchMetadata(response) {
  if (!response || typeof response !== "object") {
    return null;
  }

  if (
    response.search_metadata &&
    typeof response.search_metadata === "object"
  ) {
    return response.search_metadata;
  }

  const queue = [response];
  const visited = new Set();

  while (queue.length) {
    const current = queue.shift();

    if (!current || typeof current !== "object" || visited.has(current)) {
      continue;
    }

    visited.add(current);

    if (
      current.search_metadata &&
      typeof current.search_metadata === "object"
    ) {
      return current.search_metadata;
    }

    if (
      current.filter_resolution &&
      typeof current.filter_resolution === "object"
    ) {
      return current;
    }

    for (const value of Object.values(current)) {
      if (value && typeof value === "object") {
        queue.push(value);
      }
    }
  }

  return null;
}

/**
 * The six axes the CSV scores, read from how the filters were *decided*.
 *
 * semantic_query falls back to search_metadata.query: the vector branch echoes
 * the residual query there, and a response that resolved nothing has neither.
 */
function payloadFromMetadata(metadata) {
  const resolution = metadata.filter_resolution || {};

  return {
    organizations: resolution.organizations || [],
    file_type: resolution.media_types || [],
    exclude_organizations: resolution.exclude_organizations || [],
    exclude_file_type: resolution.exclude_media_types || [],
    any_of: resolution.any_of || [],
    semantic_query:
      resolution.semantic_query ?? (metadata.query || ""),
  };
}

/**
 * Which path served a response.
 *
 * top_k only exists on the vector branch's metadata; an empty resolution means
 * the view never reached the LLM at all.
 */
function executionPath(metadata) {
  const resolution = metadata.filter_resolution || {};

  if (!Object.keys(resolution).length) return PATH_NO_LLM;

  return "top_k" in metadata ? PATH_VECTOR : PATH_POSTGRES;
}

/**
 * Score one payload against the row's expectations.
 *
 * expected_payload is scored as one whole object -- not decomposed into
 * per-field organizations/file_type/exclude_organizations/exclude_file_type/
 * any_of checks -- so a mismatch anywhere in it surfaces as a single `payload`
 * failure. semantic_query is the one exception: it is verified against the
 * dedicated expected_semantic_query column instead of expected_payload's own
 * semantic_query field, since the two disagree on a handful of rows and the
 * standalone column is the more carefully curated source.
 */
function compareAgainstExpectations(row, payload) {
  const failures = [];

  let wantPayload = null;

  try {
    const raw = (row.expected_payload || "").trim();
    wantPayload = JSON.parse(raw || "{}");
  } catch (error) {
    failures.push(`expected_payload: unparseable expectation (${error.message})`);
  }

  if (wantPayload) {
    const want = normalizedPayload(wantPayload);
    const got = normalizedPayload(payload);

    if (JSON.stringify(want) !== JSON.stringify(got)) {
      failures.push(
        `payload: expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`
      );
    }
  }

  const wantQuery = (row.expected_semantic_query || "").trim();
  const gotQuery = (payload.semantic_query || "").trim();

  if (wantQuery !== gotQuery) {
    failures.push(
      `semantic_query: expected ${JSON.stringify(wantQuery)}, ` +
        `got ${JSON.stringify(gotQuery)}`
    );
  }

  return failures;
}

async function executeQuery(query) {
  const url = new URL("/api/v2/media/", BASE_URL);

  url.searchParams.set("q", query);
  url.searchParams.set("limit", "48");
  url.searchParams.set("offset", "0");
  url.searchParams.set("ordering", "-created_at");

  const headers = {
    Accept: "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    Referer: `${BASE_URL}/sg-commons/resources`,
    "User-Agent":
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
  };

  if (COOKIE) {
    headers.Cookie = COOKIE;
  }

  const response = await fetch(url, {
    method: "GET",
    headers,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  const rawText = await response.text();

  let body;
  try {
    body = rawText ? JSON.parse(rawText) : {};
  } catch {
    throw new Error(
      `HTTP ${response.status}: Response is not valid JSON: ${rawText.slice(
        0,
        500
      )}`
    );
  }

  if (!response.ok) {
    throw new Error(
      `HTTP ${response.status}: ${JSON.stringify(body).slice(0, 1000)}`
    );
  }

  return body;
}

async function main() {
  const csvText = fs.readFileSync(INPUT_FILE, "utf8");
  const { headers: inputHeaders, records } = rowsToObjects(parseCSV(csvText));

  if (!records.length) {
    throw new Error("CSV does not contain any test cases.");
  }

  const requiredColumns = [
    "id",
    "query",
    "expected_organizations",
    "expected_file_types",
    "expected_exclude_organizations",
    "expected_exclude_file_types",
    "expected_any_of",
    "expected_semantic_query",
    "expected_payload",
  ];

  for (const column of requiredColumns) {
    if (!(column in records[0])) {
      throw new Error(`Required CSV column is missing: ${column}`);
    }
  }

  const outputHeaders = [...inputHeaders];

  for (const column of [
    "actual_payload",
    "api_filter_resolution",
    "api_applied_filters",
    "execution_path",
    "final_status",
    "failure_reason",
  ]) {
    if (!outputHeaders.includes(column)) {
      outputHeaders.push(column);
    }
  }

  const wanted = new Set(ONLY_CASES);
  const targets = wanted.size
    ? records.filter((row) => wanted.has(row.id))
    : records;

  if (!targets.length) {
    throw new Error(`ONLY_CASES matched no rows: ${ONLY_CASES.join(",")}`);
  }

  // Clear every outcome column before starting. The input CSV ships with an
  // actual_payload from a previous run; without this, rows that ONLY_CASES
  // skipped -- or that an interrupted run never reached -- would sit in the
  // results sheet carrying that stale payload, indistinguishable from a fresh
  // result. NOT_RUN says so explicitly. The input CSV keeps the old values.
  for (const record of records) {
    record.actual_payload = "";
    record.api_filter_resolution = "";
    record.api_applied_filters = "";
    record.execution_path = "";
    record.failure_reason = "";
    record.final_status = "NOT_RUN";
  }

  console.log(`Environment: ${ENV_NAME} (${BASE_URL}) — model label: ${MODEL_LABEL}`);
  console.log(`Input      : ${INPUT_FILE}`);
  console.log(`Running ${targets.length} of ${records.length} test cases...`);

  let passed = 0;
  let failed = 0;

  for (let index = 0; index < targets.length; index++) {
    const row = targets[index];
    const testId = row.id || `ROW_${index + 2}`;
    const query = row.query || "";

    process.stdout.write(
      `[${index + 1}/${targets.length}] ${testId}: ${query} ... `
    );

    try {
      const apiResponse = await executeQuery(query);
      const metadata = extractSearchMetadata(apiResponse);

      if (!metadata) {
        row.execution_path = "";
        row.api_applied_filters = "";
        row.final_status = "FAILED";
        row.failure_reason =
          "API response does not contain search_metadata.";
        failed++;

        console.log("FAILED - search_metadata missing");
      } else {
        const payload = payloadFromMetadata(metadata);

        row.actual_payload = JSON.stringify(payload);
        // The full diagnostics trail, not just the six scored axes: it also
        // carries llm_decision, the per-field *_source flags, llm_error and
        // llm_cooldown, which are what separate "the LLM was skipped" from
        // "the LLM ran and found nothing" when a row fails.
        row.api_filter_resolution = JSON.stringify(
          metadata.filter_resolution || {}
        );
        row.api_applied_filters = JSON.stringify(
          metadata.applied_filters || {}
        );
        row.execution_path = executionPath(metadata);

        const failures = compareAgainstExpectations(row, payload);

        if (!failures.length) {
          row.final_status = "PASSED";
          row.failure_reason = "";
          passed++;
          console.log("PASSED");
        } else {
          row.final_status = "FAILED";
          row.failure_reason = failures.join(" | ");
          failed++;
          console.log("FAILED");
        }
      }
    } catch (error) {
      row.execution_path = "";
      row.api_applied_filters = "";
      row.final_status = "FAILED";
      row.failure_reason = `API_ERROR: ${error.message}`;
      failed++;
      console.log("FAILED - API error");
    }

    // Save after every test case so progress is not lost. Every record is
    // written, so rows outside ONLY_CASES keep whatever the CSV already held.
    writeCSV(outputHeaders, records, OUTPUT_FILE);

    if (REQUEST_DELAY_MS > 0 && index < targets.length - 1) {
      await sleep(REQUEST_DELAY_MS);
    }
  }

  const notRun = records.length - targets.length;

  console.log("\n==============================");
  console.log(`Execution completed (${ENV_NAME})`);
  console.log(`Total  : ${targets.length}`);
  console.log(`Passed : ${passed}`);
  console.log(`Failed : ${failed}`);
  if (notRun > 0) {
    console.log(`Not run: ${notRun} (marked NOT_RUN, outcome columns blank)`);
  }
  console.log(`Output : ${OUTPUT_FILE}`);
  console.log("==============================");

  if (failed > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(`Fatal error: ${error.stack || error.message}`);
  process.exit(1);
});
