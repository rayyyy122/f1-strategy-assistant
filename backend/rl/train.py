"""训练脚本 — 奖励加权的行为克隆（Reward-Weighted BC）。

思路：把每条轨迹当作 (state, action, reward) 样本，用 softmax(reward/T) 作为样本权重，
训练一个加权岭回归 state→action。高奖励的动作在拟合中占更大比重，
使策略向历史高奖励决策靠拢。

评估：留一法交叉验证（LOO），对比多数类基线（永远预测 MEDIUM 一停）。

用法:
    PYTHONPATH=$PWD python -m backend.rl.train
"""

import json
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = BASE_DIR / "data" / "rl_dataset.jsonl"

TEMPERATURE = 0.5   # 奖励温度：越小高奖励样本权重越大
RIDGE_LAMBDA = 1.0  # 岭回归正则强度

COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]
STRATEGY_TYPES = ["一停", "二停", "三停"]


def load_dataset(path: Path = DATASET_PATH) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """加载数据集，返回 (states, actions, rewards, samples)。"""
    samples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    states = np.array([s["state_vector"] for s in samples], dtype=float)
    actions = np.array([s["action_vector"] for s in samples], dtype=float)
    rewards = np.array([s["reward"] for s in samples], dtype=float)
    return states, actions, rewards, samples


def reward_weights(rewards: np.ndarray, temperature: float = TEMPERATURE) -> np.ndarray:
    """softmax(reward/T) 归一化权重。"""
    z = rewards / temperature
    z = z - z.max()  # 数值稳定
    w = np.exp(z)
    return w / w.sum()


def fit_ridge(X: np.ndarray, Y: np.ndarray, weights: np.ndarray, lam: float = RIDGE_LAMBDA) -> tuple[np.ndarray, np.ndarray]:
    """加权岭回归，返回 (W, b)。X: (n, d), Y: (n, k), weights: (n,)"""
    X_aug = np.hstack([X, np.ones((X.shape[0], 1))])
    W_sqrt = np.sqrt(weights)[:, None]
    A = X_aug * W_sqrt
    B = Y * W_sqrt
    reg = lam * np.eye(X_aug.shape[1])
    reg[-1, -1] = 0.0  # 不正则化偏置
    theta = np.linalg.solve(A.T @ A + reg, A.T @ B)
    return theta[:-1], theta[-1]


def predict(X: np.ndarray, W: np.ndarray, b: np.ndarray) -> np.ndarray:
    return X @ W + b


def decode_action(vec: np.ndarray) -> dict:
    """把 11 维动作向量解码为可读策略。"""
    compound = COMPOUNDS[int(np.argmax(vec[0:3]))]
    window_start = int(round(float(vec[3]) * 70))
    window_end = int(round(float(vec[4]) * 70))
    strategy = STRATEGY_TYPES[int(np.argmax(vec[5:8]))]
    return {
        "starting_compound": compound,
        "pit_window_start": max(1, window_start),
        "pit_window_end": max(1, window_end),
        "strategy_type": strategy,
    }


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """计算预测与真实动作的匹配指标。"""
    true_decoded = [decode_action(v) for v in y_true]
    pred_decoded = [decode_action(v) for v in y_pred]

    compound_acc = np.mean([t["starting_compound"] == p["starting_compound"] for t, p in zip(true_decoded, pred_decoded)])
    strategy_acc = np.mean([t["strategy_type"] == p["strategy_type"] for t, p in zip(true_decoded, pred_decoded)])
    window_mae = np.mean([
        abs(t["pit_window_start"] - p["pit_window_start"]) + abs(t["pit_window_end"] - p["pit_window_end"])
        for t, p in zip(true_decoded, pred_decoded)
    ]) / 2.0

    return {"compound_acc": compound_acc, "strategy_acc": strategy_acc, "window_mae": window_mae}


def main() -> None:
    states, actions, rewards, samples = load_dataset()
    n = len(samples)
    print(f"样本数: {n}, 状态维度: {states.shape[1]}, 动作维度: {actions.shape[1]}")

    # ---- 留一法交叉验证 ----
    model_preds = np.zeros_like(actions)
    baseline_preds = np.zeros_like(actions)

    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        X_tr, Y_tr, r_tr = states[mask], actions[mask], rewards[mask]

        # 模型：奖励加权岭回归
        w = reward_weights(r_tr)
        W, b = fit_ridge(X_tr, Y_tr, w)
        model_preds[i] = predict(states[i:i+1], W, b)[0]

        # 基线：训练集动作的均值（≈ 总是预测多数类策略）
        baseline_preds[i] = Y_tr.mean(axis=0)

    model_metrics = evaluate(actions, model_preds)
    baseline_metrics = evaluate(actions, baseline_preds)

    print("\n==== LOO 评估结果 ====")
    print(f"{'指标':<16}{'模型':>10}{'基线':>10}")
    print(f"{'起跑轮胎准确率':<16}{model_metrics['compound_acc']:>10.2f}{baseline_metrics['compound_acc']:>10.2f}")
    print(f"{'策略类型准确率':<16}{model_metrics['strategy_acc']:>10.2f}{baseline_metrics['strategy_acc']:>10.2f}")
    print(f"{'进站窗口 MAE(圈)':<16}{model_metrics['window_mae']:>10.2f}{baseline_metrics['window_mae']:>10.2f}")

    # ---- 用全部数据训练最终模型并保存 ----
    w = reward_weights(rewards)
    W, b = fit_ridge(states, actions, w)
    model_path = BASE_DIR / "data" / "rl_policy.npz"
    np.savez(model_path, W=W, b=b)
    print(f"\n最终模型（全量数据训练）已保存: {model_path}")

    # 奖励最高的样本，看模型学到了什么
    best = samples[int(np.argmax(rewards))]
    print(f"\n奖励最高的样本: {best['trace_id']} (reward={best['reward']:.2f})")
    print(f"  实际策略: {best['action']}")
    print(f"  模型对该状态预测: {decode_action(predict(np.array([best['state_vector']]), W, b)[0])}")


if __name__ == "__main__":
    main()
