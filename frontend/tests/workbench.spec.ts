import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("fictional preview shows traceable source times and disables approval", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "包裹运输进度", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("当前使用虚构数据。", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("源更新：2026-09-20 05:30:00 UTC")).toBeVisible();
  await expect(page.getByRole("button", { name: "批准草稿" })).toBeDisabled();
  await expect(page.getByText("尚未执行校验")).toBeVisible();
});

test("multi-parcel view preserves distinct business statuses", async ({
  page,
}) => {
  await page.getByRole("button", { name: /拆单后的包裹进度/ }).click();
  await expect(
    page.getByRole("heading", { name: "包裹 1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "包裹 2", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("NOT_COLLECTED", { exact: true })).toBeVisible();
  await expect(
    page.getByText("IN_TRANSIT", { exact: true }).first(),
  ).toBeVisible();
});

test("older source time remains old despite a new fetch", async ({ page }) => {
  await page.getByRole("button", { name: /物流记录很久没更新/ }).click();
  await expect(
    page.getByText("2026-09-17 06:00:00 UTC", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("这份物流记录较旧，不能代表实时位置。"),
  ).toBeVisible();
});

test("partial timeout keeps the successful parcel without inventing an exception", async ({
  page,
}) => {
  await page.getByRole("button", { name: /部分包裹暂时无法查询/ }).click();
  await expect(page.getByText("查询超时", { exact: true })).toBeVisible();
  await expect(
    page.getByText("IN_TRANSIT", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("查询失败无事实抓取时间")).toBeVisible();
  await expect(page.getByText("EXCEPTION", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "来源查询", exact: true }).click();
  await expect(page.getByText("查询超时", { exact: true })).toBeVisible();
});

test("unknown source time is visible rather than promoted to live information", async ({
  page,
}) => {
  await page.getByRole("button", { name: /来源更新时间未知/ }).click();
  await expect(page.getByText("源更新：更新时间未知")).toBeVisible();
  await expect(
    page.getByText("更新时间未知", { exact: true }).first(),
  ).toBeVisible();
});

test("conflict view preserves both warehouse text and logistics status", async ({
  page,
}) => {
  await page.getByRole("button", { name: /仓库与物流信息不一致/ }).click();
  await expect(
    page.getByText("同日仓库备注与物流状态可能冲突，需人工核实。"),
  ).toBeVisible();
  await expect(
    page
      .getByText("Parcel has not been handed to carrier today.", {
        exact: true,
      })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText("PICKED_UP", { exact: true }).first(),
  ).toBeVisible();
});

for (const [state, heading] of [
  ["loading", "正在加载咨询资料"],
  ["empty", "暂无待处理咨询"],
  ["error", "暂时无法读取咨询资料"],
]) {
  test(`preview ${state} state stays distinct from business facts`, async ({
    page,
  }) => {
    await page.getByRole("combobox", { name: "预览状态" }).selectOption(state);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "订单资料与证据" }),
    ).toHaveCount(0);
    if (state !== "loading") {
      await page.getByRole("button", { name: "返回演示咨询" }).click();
      await expect(
        page.getByRole("heading", { name: "订单资料与证据" }),
      ).toBeVisible();
    }
  });
}

test("local edits never gain approval and reset restores the original sample", async ({
  page,
}) => {
  const editor = page.getByRole("textbox", { name: "回复内容" });
  const original = await editor.inputValue();
  await editor.fill("这是修改后的本地预览。");
  await expect(page.getByText("已修改预览", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "批准草稿" })).toBeDisabled();
  await expect(page.getByText("尚未执行校验")).toBeVisible();
  await page.getByRole("button", { name: "恢复示例" }).click();
  await expect(editor).toHaveValue(original);
});

test("static workbench makes no business or external requests", async ({
  page,
}) => {
  const calls: string[] = [];
  page.on("request", (request) => {
    if (
      ["fetch", "xhr"].includes(request.resourceType()) ||
      /\/api\//.test(request.url())
    )
      calls.push(request.url());
  });
  // Capture initial application requests as well as later preview interactions.
  await page.reload();
  await page.getByRole("button", { name: /部分包裹暂时无法查询/ }).click();
  await page.getByRole("textbox", { name: "回复内容" }).fill("本地编辑。");
  await page.getByRole("button", { name: "来源查询", exact: true }).click();
  expect(calls).toEqual([]);
});

test("mobile preview has no viewport overflow and retains disabled approval", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /拆单后的包裹进度/ }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(page.getByRole("button", { name: "批准草稿" })).toBeDisabled();
});
