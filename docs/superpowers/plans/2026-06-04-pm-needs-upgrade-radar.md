# PMAgent 治标→治本升级雷达 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 PMAgent 的 `SYSTEM_PROMPT` 澄清对话阶段植入一组"治标→治本"升级模式参照 + 强克制规则，让 PMAgent 主动温和地把用户的表层方案需求升级为更治本的方案、由用户拍板。

**Architecture:** 纯 prompt 改动，只编辑 `backend/app/agents/prompts/pm_prompts.py` 的 `SYSTEM_PROMPT` 字符串常量，在现有原则 3（挖根因）末尾追加升级雷达小节。不动代码逻辑、不动意图路由、不动 `modify_prd`/MODIFY 路径。配一个不依赖第三方库的轻量回归测试防 prompt 锚点丢失；效果验证靠真机对话清单。

**Tech Stack:** Python、FastAPI、launchd（Mac mini backend 守护）。设计依据见 `docs/superpowers/specs/2026-06-04-pm-needs-upgrade-radar-design.md`。

---

## File Structure

- Modify: `backend/app/agents/prompts/pm_prompts.py` — 在 `SYSTEM_PROMPT` 原则 3 末尾插入升级雷达小节（唯一逻辑改动）
- Create: `backend/tests/test_pm_prompt_radar.py` — 纯文件读取式回归测试，断言升级雷达锚点存在（本地可跑、不依赖 anthropic）

---

### Task 1: 给 SYSTEM_PROMPT 加升级雷达小节

**Files:**
- Modify: `backend/app/agents/prompts/pm_prompts.py`（`SYSTEM_PROMPT`，原则 3 与原则 4 之间）
- Test: `backend/tests/test_pm_prompt_radar.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_pm_prompt_radar.py`：

```python
"""回归保护：SYSTEM_PROMPT 必须包含'治标→治本'升级雷达的关键锚点。
纯文件读取，不 import app(避免触发 anthropic 依赖),本地/CI 均可跑。
效果(模型是否真的升级需求)靠真机对话评估,不在此断言。
"""
from pathlib import Path

PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "app" / "agents" / "prompts" / "pm_prompts.py"
)


def test_system_prompt_contains_upgrade_radar():
    src = PROMPT_FILE.read_text(encoding="utf-8")
    # 雷达存在性锚点
    assert "治标" in src and "治本" in src, "缺少治标→治本升级雷达小节"
    assert "可配置" in src, "缺少'可配置'升级方向(下拉框写死场景)"
    # 克制规则锚点(防止整段被删后只剩清单、丢了克制)
    assert "最多提一次" in src, "缺少'最多提一次'克制规则"
    assert "别硬塞" in src, "缺少'简单需求别硬塞'克制规则"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_pm_prompt_radar.py -v`
Expected: FAIL（`AssertionError: 缺少治标→治本升级雷达小节`，因为 prompt 还没改）

> 若本机无 pytest：`cd backend && python3 tests/test_pm_prompt_radar.py` 改不了断言运行，可临时用 `python3 -c "from tests.test_pm_prompt_radar import test_system_prompt_contains_upgrade_radar as t; t()"`，预期抛 AssertionError。

- [ ] **Step 3: 编辑 SYSTEM_PROMPT 插入升级雷达**

打开 `backend/app/agents/prompts/pm_prompts.py`。原则 3 当前以这两行结尾（约第 24 行）：

```python
   **追问要轻盈、自然**，像同事问候一样，不要变成审讯。每次只追一个最关键的点。
```

在该行之后、空行与 `4. **方案不合理时委婉提出来重新讨论。**`（原则 4）之前，插入以下整段（注意保持三空格缩进、与现有原则风格一致）：

```python

   **常见的"治标→治本"信号（识别到就按下面第 5 条温和提一次，给推荐 + 一句理由）：**

   | 他怎么说 | 多半真正要的 | 可以提的方向 |
   |---|---|---|
   | "加个选项 5 6""再加一项"（选项写死） | 选项以后还会变 | 做成他自己能加减的（可配置） |
   | "导出 Excel 我自己看""每周导一次" | 就想看某个结果 | 直接做页面自动算给他看 |
   | "这条帮我改成 X""这几个都改"（一条条手动） | 量大、重复 | 一次选多条批量改 |
   | "A 改了我再去改 B" | 两处该联动 | A 变 B 自动跟着变 |
   | "列表太长找不到""老翻页" | 找不到东西 | 加搜索或筛选 |
   | "给他也开个权限"（一个个开） | 按岗位分 | 按角色分权限 |

   这表是**参照不是清单**——碰到同类"他在描述操作步骤、而不是要解决的事"，就照这个思路想想有没有更省事的做法。

   **克制（重要，别变成话痨、也别什么都劝人做大）：**
   - 信号明确才提，**一整轮最多提一次**，别反复念叨；提就一句方向 + 一句"帮你省什么事"。
   - 他说"就按我说的做"——立刻回到他的原方案，不再劝。
   - **反过来也要拦**：如果他要的简单做法其实够用、而"升级版"明显更费事，就别升级，甚至帮他砍掉多余的。升级是为省他的事，不是把功能做大。
   - 真·简单又一次性的需求（明显不会变、不会重复），**别硬塞**升级。
```

- [ ] **Step 4: 运行测试 + 语法检查，确认通过**

Run: `cd backend && python3 -m pytest tests/test_pm_prompt_radar.py -v && python3 -m py_compile app/agents/prompts/pm_prompts.py`
Expected: PASS（测试通过）+ 无语法错误输出

- [ ] **Step 5: 提交**

```bash
git add backend/app/agents/prompts/pm_prompts.py backend/tests/test_pm_prompt_radar.py
git commit -m "feat(pm): SYSTEM_PROMPT 加治标→治本升级雷达

澄清对话阶段内置一组常见'治标'信号(选项写死/导出/逐条手动/
手动联动/翻页/逐人授权)及其治本升级方向,配强克制规则(最多提
一次/被拒即停/简单需求不硬塞/过度升级反向劝简)。纯 prompt 改动。
回归测试 test_pm_prompt_radar.py 守住关键锚点。"
```

---

### Task 2: 部署并真机验证

**Files:** 无（运维操作；backend 由 launchd 守护，重启即加载新 prompt）

- [ ] **Step 1: 重启 Mac mini backend 加载新 prompt**

```bash
U=$(id -u)
launchctl kickstart -k gui/$U/com.superuserai.backend
for i in $(seq 1 30); do
  curl -s --max-time 3 localhost:8000/healthz | grep -q '"status": "ok"' && { echo "就绪(${i}s)"; break; }
  sleep 1
done
```
Expected: 30s 内打印"就绪"，`/healthz` 返回 ok

- [ ] **Step 2: 真机对话验证（企微群，记得 @机器人）**

逐条发，对照期望表现（判据：该提的只提一次；不该提的不打扰）：

| 输入 | 期望表现 |
|---|---|
| "我要个下拉框选 1234" | 温和提议"选项以后会变吗？要不可配置" |
| "帮我把这条记录改成 X"（单条一次性） | **正常照做、不硬升级** |
| "导出 Excel" | 反问"主要看哪个数"，提议仪表盘 |
| "给小王也开个权限" | 提议按岗位分权限 |

- [ ] **Step 3: 不达预期时的回退/迭代**

- prompt 未生效/表现不稳：先确认 backend 已重启（`launchctl print gui/$U/com.superuserai.backend | grep pid`，pid 应为新值）。
- 模型遵循度差（`gpt-4.1-mini`）：在 spec「风险」记录实际表现，再评估升级模型或转 spec 的方案二/三。
- 升级提议过度打扰：回到 Task 1 收紧克制规则（强调"最多提一次""简单需求不提"），重启复验。

---

## Self-Review

**Spec coverage:**
- 升级雷达清单（6 模式）→ Task 1 Step 3 表格，逐条对应 spec §3.2 ✓
- 克制规则（最多一次/被拒即停/双向判断/简单不硬塞）→ Task 1 Step 3 克制段，对应 spec §3.3 ✓
- 只改 SYSTEM_PROMPT、不动 MODIFY/代码 → Task 1 仅编辑 pm_prompts.py ✓
- 真机验证 4 用例 → Task 2 Step 2，对应 spec §4 ✓
- 模型遵循度风险 → Task 2 Step 3，对应 spec §5 ✓

**Placeholder scan:** 无 TBD/TODO；插入文本、测试代码、命令均完整给出 ✓

**Type consistency:** 测试锚点（"治标""治本""可配置""最多提一次""别硬塞"）与 Task 1 Step 3 插入文本逐一对应、字面一致 ✓
