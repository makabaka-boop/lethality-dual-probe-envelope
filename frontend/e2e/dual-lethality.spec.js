import { expect, test } from '@playwright/test';

// 双探头复核真实联调：页面经 nginx 代理访问 FastAPI，无任何 mock。
test.describe('双探头复核联调', () => {
  test('默认重合样例：保守 F₀=3.00 放行，段来源为两探头一致', async ({
    page,
  }) => {
    await page.goto('/');
    await page.getByRole('button', { name: '双探头复核计算' }).click();

    const conclusion = page.getByTestId('dual-conclusion');
    await expect(conclusion).toContainText('放行');
    await expect(conclusion).toContainText('3.00');
    await expect(page.getByTestId('dual-conservative-total')).toHaveText(
      '3.000000',
    );
    await expect(page.locator('.dual-segments tbody tr')).toHaveCount(3);
    await expect(
      page.locator('.dual-segments tbody').getByText('两探头一致'),
    ).toHaveCount(3);
    // 曲线图与表格来自同一响应：两条探头曲线 + 保守下包络
    // （恒温样例折线水平、包围盒高度为 0，故断言存在于 DOM 而非可见性）
    await expect(page.getByTestId('curve-probe-a')).toBeAttached();
    await expect(page.getByTestId('curve-probe-b')).toBeAttached();
    await expect(page.getByTestId('curve-envelope')).toBeAttached();
  });

  test('换源样例：速率线在 90 秒相交，交点拆段且来源探头切换', async ({
    page,
  }) => {
    await page.goto('/');
    // 探头A 前低后高：115,115,127,127
    await page.getByLabel('探头A 第1行 温度').fill('115');
    await page.getByLabel('探头A 第2行 温度').fill('115');
    await page.getByLabel('探头A 第3行 温度').fill('127');
    await page.getByLabel('探头A 第4行 温度').fill('127');
    // 探头B 前高后低：127,127,115,115
    await page.getByLabel('探头B 第1行 温度').fill('127');
    await page.getByLabel('探头B 第2行 温度').fill('127');
    await page.getByLabel('探头B 第3行 温度').fill('115');
    await page.getByLabel('探头B 第4行 温度').fill('115');
    await page.getByRole('button', { name: '双探头复核计算' }).click();

    const conclusion = page.getByTestId('dual-conclusion');
    await expect(conclusion).toContainText('不放行');
    // 保守总量 1.647658 min，远低于各自总量 6.203884 min：
    // 不能取两份总量的较小值代替逐时刻取低
    await expect(page.getByTestId('dual-conservative-total')).toHaveText(
      '1.647658',
    );
    await expect(page.getByTestId('dual-probe-a-total')).toHaveText(
      '6.203884',
    );

    const rows = page.locator('.dual-segments tbody tr');
    await expect(rows).toHaveCount(4);
    // 交点 90 秒拆段：[0,60]A [60,90]A [90,120]B [120,180]B
    await expect(rows.nth(1)).toContainText('60 → 90');
    await expect(rows.nth(2)).toContainText('90 → 120');
    const sources = await rows.locator('td:nth-child(3)').allTextContents();
    expect(sources).toEqual(['探头A', '探头A', '探头B', '探头B']);
  });

  test('结束时刻不一致被服务端拒绝，且不影响已显示的单探头结论', async ({
    page,
  }) => {
    await page.goto('/');
    // 先得到单探头放行结论
    await page.getByRole('button', { name: '计算致死量' }).click();
    await expect(page.getByTestId('conclusion')).toContainText('放行');

    // 探头B 结束于 150 秒，与探头A 的 180 秒不一致
    await page.getByLabel('探头B 第4行 时间').fill('150');
    await page.getByRole('button', { name: '双探头复核计算' }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('结束于同一秒');
    // 双探头比较被清除，单探头结论保留
    await expect(page.getByTestId('dual-conclusion')).toHaveCount(0);
    await expect(page.getByTestId('conclusion')).toContainText('放行');
  });

  test('探头B 非法行定位到对应表格，双探头结果区清空', async ({ page }) => {
    await page.goto('/');
    // 先算一次默认重合样例，让双探头结论显示出来
    await page.getByRole('button', { name: '双探头复核计算' }).click();
    await expect(page.getByTestId('dual-conclusion')).toBeVisible();

    await page.getByLabel('探头B 第2行 温度').fill('99');
    await page.getByRole('button', { name: '双探头复核计算' }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('探头B');
    await expect(alert).toContainText('第 2 行');
    await expect(alert).toContainText('温度');
    await expect(page.getByTestId('dual-conclusion')).toHaveCount(0);
    // 非法行在探头B 表格中高亮
    await expect(
      page.getByLabel('探头B 第2行 温度').locator('xpath=ancestor::tr[1]'),
    ).toHaveClass(/row-error/);
  });
});
