// Private local recording. It calls the actual API; no response interception or fixture replay.
import { chromium } from "@playwright/test";
import { mkdir, rename, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const baseURL = process.argv[2] ?? "http://127.0.0.1:8004";
const output = resolve("../output/demo-v2");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: output, size: { width: 1440, height: 1000 } },
});
const page = await context.newPage();
const started = Date.now();
const summary = {
  baseURL,
  scope: "Local live walkthrough; unreviewed integration evidence",
  steps: [],
};

async function caption(text) {
  await page.evaluate((message) => {
    let label = document.getElementById("recording-caption");
    if (!label) {
      label = document.createElement("div");
      label.id = "recording-caption";
      label.style.cssText =
        "position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:10000;background:#102b30;color:#fff;padding:14px 24px;border:1px solid #46c6a7;border-radius:12px;font:600 17px system-ui;max-width:85%;text-align:center;pointer-events:none";
      document.body.appendChild(label);
    }
    label.textContent = message;
  }, text);
  summary.steps.push({ seconds: (Date.now() - started) / 1000, caption: text });
  console.log(text);
}

async function holdUntil(seconds) {
  const remaining = seconds * 1000 - (Date.now() - started);
  if (remaining > 0) await page.waitForTimeout(remaining);
}

try {
  await page.goto(baseURL);
  await page
    .getByRole("combobox", { name: "Select match", exact: true })
    .selectOption("19717");
  await caption(
    "TactiGraph AI · Analyse locale · Les chiffres renvoient aux événements du match",
  );
  await holdUntil(20);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Evidence Analyst", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Question libre / Free question" })
    .click();
  await page
    .getByRole("combobox", { name: "Query language" })
    .selectOption("fr");
  await page.getByRole("combobox", { name: "Query team" }).selectOption("968");
  const question = page.getByRole("textbox", { name: "Analyst question" });
  await question.fill(
    "Compare la création d’occasions entre les minutes 45–60 et 60–75, et explique le xG.",
  );
  await caption(
    "1 · Une question en français, avec le match et l’équipe sélectionnés",
  );
  await holdUntil(35);
  await page
    .getByRole("button", { name: "Analyser la question", exact: true })
    .click();
  const result = page.getByRole("article", { name: "Query result" });
  await result.waitFor({ timeout: 35000 });
  if ((await result.getAttribute("data-status")) !== "answered")
    throw new Error("French query did not answer");
  await result.scrollIntoViewIfNeeded();
  await caption(
    "Les nombres sont calculés en Python. Le xG est expliqué par un extrait cité.",
  );
  await page.screenshot({
    path: resolve(output, "query-fr.png"),
    fullPage: true,
  });
  await holdUntil(65);
  await result.getByRole("button", { name: "Preuve avant" }).first().click();
  const evidence = page.getByRole("complementary", { name: "Query evidence" });
  await evidence.waitFor();
  await evidence.scrollIntoViewIfNeeded();
  await caption(
    "2 · Ouvrir une preuve : définition, événements justificatifs et source du match",
  );
  await page.screenshot({
    path: resolve(output, "evidence-fr.png"),
    fullPage: true,
  });
  await holdUntil(95);
  await page
    .getByRole("combobox", { name: "Query language" })
    .selectOption("en");
  await question.fill(
    "Compare chance creation between minutes 45–60 and 60–75, and explain xG.",
  );
  await caption(
    "3 · The same analysis in English, with verified measurements and definitions",
  );
  await page
    .getByRole("button", { name: "Analyze question", exact: true })
    .click();
  await result.waitFor({ timeout: 35000 });
  if ((await result.getAttribute("data-status")) !== "answered")
    throw new Error("English query did not answer");
  await result.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: resolve(output, "query-en.png"),
    fullPage: true,
  });
  await holdUntil(130);
  await question.fill("How did chance creation change after minute 60?");
  await caption("4 · An incomplete time window asks for clarification");
  await page
    .getByRole("button", { name: "Analyze question", exact: true })
    .click();
  await result.waitFor();
  if ((await result.getAttribute("data-status")) !== "clarification_required")
    throw new Error("Clarification missing");
  await result.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: resolve(output, "clarification.png"),
    fullPage: true,
  });
  await holdUntil(160);
  await caption(
    "Local feature delivered · Independent quality review pending · Public access requires a separate decision",
  );
  await holdUntil(180);
  summary.duration_seconds = (Date.now() - started) / 1000;
  await writeFile(
    resolve(output, "recording.json"),
    JSON.stringify(summary, null, 2),
  );
  const video = page.video();
  await context.close();
  await rename(await video.path(), resolve(output, "tactigraph-query-v2.webm"));
  console.log("Saved output/demo-v2/tactigraph-query-v2.webm");
} finally {
  await browser.close();
}
