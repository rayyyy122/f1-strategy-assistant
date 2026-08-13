# RL 强化学习 — 进度与训练细节

最后更新：2026-08-03

> 数据文件（`data/traces/`、`data/rl_dataset.jsonl`、`data/rl_policy.npz`）被 gitignore 不入库，
> 本文档记录截至上述日期的数据快照与管道细节，便于复现。

---

## 1. 管道总览（已端到端闭环）

```
赛前分析 ──自动存轨迹──▶ data/traces/*.jsonl
                              │  state + agent_outputs + final_prediction
                              ▼
赛后回填（真实结果）── _compute_reward ──▶ trace.reward
                              ▼
特征提取 ── state_extractor (19维) / action_extractor (11维)
                              ▼
数据集构建 ── dataset_builder ──▶ data/rl_dataset.jsonl
                              ▼
训练 ── train.py（奖励加权岭回归）──▶ data/rl_policy.npz
```

| 环节 | 文件 | 说明 |
|------|------|------|
| 轨迹采集 | `backend/harness/orchestrator.py` `_run_pre_race` | 4-Agent 分析完成后自动保存 |
| 批量生成 | `backend/scripts/generate_traces.py` | 历史比赛批量跑分析 + 自动回填 + 审计表 |
| 回填 | `backend/scripts/backfill_traces.py` | `--force` 可复用已存结果重算 reward |
| 数据校验 | `backend/scripts/validate_traces.py` | 结构完整性 + 奖励分布 |
| 状态提取 | `backend/rl/state_extractor.py` | 轨迹 → 19 维状态向量 |
| 动作提取 | `backend/rl/action_extractor.py` | Agent 输出 → 11 维动作向量 |
| 数据集 | `backend/rl/dataset_builder.py` | 轨迹 → (s, a, r) 样本 |
| 训练 | `backend/rl/train.py` | 奖励加权 BC + LOO 评估 |

---

## 2. 数据格式

### 轨迹（`data/traces/{season}_R{round}_{ts}_{hash}.jsonl`）

```json
{
  "trace_id": "...", "mode": "pre_race", "season": 2024, "round": 8,
  "prompt": "...", "state": {"race_data": {...}, "driver": "...", "team": "..."},
  "agent_outputs": {"race_context": {...}, "tire_strategist": {...}, ...},
  "final_prediction": {"recommended_strategy": "...", "pit_window": "...", "predicted_position": "P2", ...},
  "actual_outcome": {"results": [...], "strategies": {...}},
  "reward": 0.5, "backfilled_at": "..."
}
```

### 状态向量（19 维，`state_to_vector`）

| 组 | 维度 | 内容 |
|----|------|------|
| 赛道 | 7 | 长度/10、弯道数/20、DRS 区数/4、超车难度评分、类型 one-hot(3: street/high_speed/technical，balanced=[.5,.5,.5]) |
| 天气 | 5 | 气温、赛道温度（归一化）、湿度/100、降雨 0/1、风速/20 |
| 排位 | 3 | 目标车手发车位 (pos-1)/19、杆位差距/2、前两排车队多样性 |
| 长距离 | 4 | SOFT/MEDIUM/HARD 平均退化率（截断归一）、平均 stint 长度/30 |

### 动作向量（11 维，`StrategyAction.to_vector`）

起步配方 one-hot(3) + 进站窗口 start/end（/70 归一）+ 停站次数 one-hot(3) + 3 个辅助参数（安全车敏感度 / undercut 激进度 / 位置优先度，各 0-1）。

---

## 3. Reward 规则（2026-08-03 修正版）

对比对象为**轨迹的目标车手**（`state.driver`），不再是冠军：

| 维度 | 规则 |
|------|------|
| 冠军预测 | 预测目标车手 P1 且其确实夺冠 → +1.0 |
| 策略类型 | 预测停站次数与目标车手实际一致 → +0.5 |
| 进站窗口 | 实际进站命中预测窗口 → +0.3，每多命中一次 +0.1，上限 +0.5 |
| 名次偏差 | -0.2 × \|预测名次 - 实际名次\|，下限 -1.0 |

- 目标车手在实际结果中匹配不到时（如中文名），回退为与冠军对比
- `predicted_position` 支持 `"P2（最佳P1，最差P4）"` 等富文本（取首个 `P\d+`）
- `pit_window` 支持 dict 多停格式（`{"pitstop_1": ..., "pitstop_2": ...}`）

**修正历史**：旧版 `_compute_reward` 始终与冠军对比，预测任何人 P1 都白得 +1.0、名次偏差恒与 P1 比。
由审计表发现（2024 R3 维斯塔潘预测 P1 实际退赛 P19，旧 reward +1.50 → 修正后 -1.00），
全量 18 条轨迹用 `--force` 重算。教训：**reward 变更后必须全量重回填**。

---

## 4. 批量生成（`generate_traces.py`）

```bash
PYTHONPATH=$PWD python -m backend.scripts.generate_traces \
  --season 2024 --rounds 1-7,9-18 --drivers-per-race 2 --delay 3
```

- 从 Jolpica 拉赛程 + 排位结果，每场选代表性车手：P1 / P10 / P17（`--drivers-per-race` 1-3）
- prompt 模板含 season/round/team/driver 四要素（intake gate 硬性要求）
- 已有 (场次, 车手) 组合自动跳过 → **可断点续跑**
- 单次分析超时 600s；回填单条超时 600s
- 成本实测：单次分析约 8-16 万 input tokens（DeepSeek，含 prompt cache），耗时 70-180s
- 结尾打印审计表（预测名次 vs 实际名次 vs reward）供抽查

**已知失败模式**（约 20% 场次需重跑）：DeepSeek 连接重置、intake 路由 LLM 偶发提不全字段（clarification 退出）。重跑同命令即可补齐。

---

## 5. 当前数据快照（2026-08-03）

- **52 条轨迹**，47 条为 2024 赛季（R1-R18 全覆盖；R8 摩纳哥 11 条为早期手工数据），
  另含 2025_R16、2026_R2×2、2026_R5、2026_R10
- 奖励分布：min -1.00 / max 1.90 / 均值 0.22
- 动作分布：起步配方 MEDIUM 49 / HARD 2 / SOFT 1；策略 一停 44 / 二停 8
  （偏斜符合 F1 真实策略分布，但不利于学习）

### 已知数据瑕疵

1. R5 周冠宇：FastF1 英文名 "Guanyu Zhou" 与轨迹 "Zhou Guanyu" 顺序相反，实际名次匹配失败，reward 可疑（1 条）
2. 早期 R8 摩纳哥 11 条轨迹 prompt 未指定车手，reward 为冠军回退语义，与新数据不同源
3. R7 霍肯伯格有 1 条重复

---

## 6. 训练（`train.py`）

**方法**：奖励加权行为克隆（Reward-Weighted BC）

- 样本权重 `softmax(reward / T)`，T=0.5（高奖励动作占比更大）
- 模型：加权岭回归 state(19) → action(11)，λ=1.0，纯 numpy，无新依赖
- 评估：留一法交叉验证（LOO），基线 = 训练集动作均值（≈ 总猜多数类）
- 产物：`data/rl_policy.npz`（W, b）

### 结果

| 指标 | 18 样本（旧 reward） | 52 样本 | 基线（52 样本） |
|------|---------------------|---------|----------------|
| 起跑轮胎准确率 | 0.89 | 0.94 | 0.94 |
| 策略类型准确率 | 0.89 | 0.85 | 0.85 |
| 进站窗口 MAE | 4.94 | 4.10 | 3.72 |

**结论：模型尚未超越多数类基线。** 原因：

1. 动作分布偏斜（94% MEDIUM 起步），可学的方差小
2. 线性模型容量有限，state→action 关系大概率非线性
3. **固有局限**：DeepSeek 训练语料大概率包含 2024/2025 赛果，轨迹的"预测"部分是记忆而非推理，
   reward 衡量的准确性有泄漏成分——当前实质是"结果加权的模仿学习"，管道验证价值 > 策略价值

---

## 7. 过程中的关键修复

| 问题 | 修复 | 提交 |
|------|------|------|
| FastF1 同步下载阻塞事件循环，单点卡死全员冻结（首批批量生成 3 小时 0 产出） | 三处 `asyncio.to_thread`（race 数据加载 / 工具执行 / 结果加载） | `617d5db` |
| reward 与冠军而非目标车手对比 | `_compute_reward` 重写 + 全量重回填 | `abdd258` |
| synthesis `pit_window` dict 新格式导致提取器崩溃 | isinstance 防御 + 取第一停 | `91edf0e` |
| 回填阶段无超时，下载卡死阻塞批量任务 | 单条 600s `asyncio.wait_for` | `cf7e981` |

---

## 8. 复现命令

```bash
# 1. 批量生成轨迹（可断点续跑）
PYTHONPATH=$PWD python -m backend.scripts.generate_traces --season 2024 --rounds all --drivers-per-race 2

# 2. 回填 / 校验
PYTHONPATH=$PWD python backend/scripts/backfill_traces.py            # 补缺
PYTHONPATH=$PWD python backend/scripts/backfill_traces.py --force    # reward 规则变更后全量重算
PYTHONPATH=$PWD python backend/scripts/validate_traces.py

# 3. 数据集 + 训练
PYTHONPATH=$PWD python -m backend.rl.dataset_builder
PYTHONPATH=$PWD python -m backend.rl.train
```

---

## 9. 下一步候选

- [ ] 扩 2025 赛季数据（`--season 2025`，约半小时）
- [ ] 修姓名匹配（处理 "Zhou Guanyu" / "Guanyu Zhou" 顺序）+ 去重 R7 重复条
- [ ] 数据量上来后换非线性模型（MLP），需要引入 torch 或 sklearn
- [ ] 回接设计：训练出的策略如何注入 Agent 决策（如作为 synthesis 的参考先验写进 prompt）
- [ ] 评估改进：按比赛 leave-one-race-out 划分，比逐条 LOO 更能测泛化
