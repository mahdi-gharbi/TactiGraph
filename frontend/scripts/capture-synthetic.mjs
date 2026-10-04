// README assets use invented data, without publishing an unreviewed real-data report.
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const output = resolve("../docs/assets");
const baseURL = process.argv[2] ?? "http://127.0.0.1:8011";
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [name, viewport] of [
    ["query-analyst-v2", { width: 1440, height: 1000 }],
    ["query-analyst-v2-mobile", { width: 390, height: 844 }],
  ]) {
    const page = await browser.newPage({ viewport });
    await page.goto(baseURL);
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Evidence Analyst", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Question libre / Free question" })
      .click();
    await page
      .getByRole("textbox", { name: "Analyst question" })
      .fill("Compare les tirs dans les fenêtres sélectionnées");
    await page
      .getByRole("button", { name: "Analyser la question", exact: true })
      .click();
    const result = page.getByRole("article", { name: "Query result" });
    await result.waitFor();
    if ((await result.getAttribute("data-status")) !== "answered")
      throw new Error("Fixture failed");
    const panel = page.getByRole("region", {
      name: "Posez une question. Vérifiez les preuves.",
    });
    await panel.evaluate((element) => {
      // Crop the analyst panel without fixed navigation covering its caption.
      for (const overlay of document.querySelectorAll(".sidebar, .topbar")) {
        if (!element.contains(overlay)) overlay.style.visibility = "hidden";
      }
      const note = document.createElement("p");
      note.textContent =
        "DEMONSTRATION CI · Match inventé · Interprétation simulée · Aucun score de qualité humaine";
      note.style.cssText =
        "padding:14px;background:#123c36;color:#c5ffe8;border:1px solid #47d8aa;border-radius:12px;font-weight:700";
      element.prepend(note);
    });
    await panel.screenshot({ path: resolve(output, `${name}.png`) });
    await page.close();
  }
} finally {
  await browser.close();
}
console.log("Saved invented-data desktop/mobile screenshots in docs/assets");
