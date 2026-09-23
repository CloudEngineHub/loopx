import { resolve } from "node:path";

import { outputDir } from "./fixture.mjs";
import { openWorkspacePage } from "./scenario-context.mjs";

export const stewardModelSettingsScenario = {
  id: "steward-model-settings",
  async run({ browser, collectCoverage, url }) {
    const context = await openWorkspacePage(browser, url, { collectCoverage });
    const { api, page } = context;
    try {
      await page.getByRole("button", { name: "设置", exact: true }).click();
      const detail = page.locator(".personal-capability-detail");
      await detail.getByText("管家模型与思考深度").waitFor();
      await page.screenshot({ path: resolve(outputDir, "steward-model-settings.png"), fullPage: false, animations: "disabled" });
      await detail.getByLabel("模型").fill("gpt-6-sol");
      await detail.getByLabel("推理档位").selectOption("xhigh");
      await detail.getByRole("button", { name: "预览变更" }).click();
      await detail.getByRole("button", { name: "应用已审阅预览" }).click();
      const applied = api.machineConfigurationRequests.find((item) => item.phase === "apply");
      if (applied?.namespace !== "steward_executor"
          || applied?.namespace_configuration?.executor_model !== "gpt-6-sol"
          || applied?.namespace_configuration?.executor_reasoning_effort !== "xhigh") {
        throw new Error("Steward settings did not apply the selected model and effort");
      }
      await detail.getByLabel("模型").waitFor();
      if (await detail.getByLabel("模型").inputValue() !== "gpt-6-sol"
          || await detail.getByLabel("推理档位").inputValue() !== "xhigh") {
        throw new Error("Steward model and effort were not read back after apply");
      }
      if (context.errors.length) throw new Error(context.errors.join(" | "));
      return { coverageEntries: await context.close(), note: "Manager settings directly select and read back Sol xhigh" };
    } catch (error) {
      await context.close();
      throw error;
    }
  },
};
