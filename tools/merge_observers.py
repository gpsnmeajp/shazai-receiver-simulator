#!/usr/bin/env python3
"""観察者の集団の生の出力（eval/observers/raw/<変種>/*.jsonl）を確かめて、観察JSONにまとめる。

- 各行の group が、対応するバッチ（batches/<名前>.json）の group か、回答IDがその group の回答と一致するかを確かめる
- 同じ group が二度あれば後の行を採る（再開時の重複）
- 変種ごとに obs-<変種>.json、ベンチマークの全変種から obs-ensemble.json（sim.py ensemble）を書く

  python3 tools/merge_observers.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sim  # noqa: E402

BASE = ROOT / "eval" / "observers"
MODEL = {"opus": "claude-top", "sonnet": "claude-mid"}


def main():
    batches = {p.stem: {g["group"]: g for g in sim.load(p)["groups"]} for p in sorted((BASE / "batches").glob("*.json"))}
    bench = []
    report = []
    for vdir in sorted((BASE / "raw").iterdir()):
        if not vdir.is_dir():
            continue
        name = vdir.name
        obs = {"scenarios": {}, "answers": {}}
        problems, n_lines = [], 0
        for f in sorted(vdir.glob("*.jsonl")):
            groups = batches.get(f.stem)
            if groups is None:
                problems.append(f"{f.name}: 対応するバッチがない")
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                n_lines += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    problems.append(f"{f.name}:{i + 1}: JSON を読めない（{e}）")
                    continue
                g = groups.get(row.get("group"))
                if g is None:
                    problems.append(f"{f.name}:{i + 1}: バッチにない group {row.get('group')}")
                    continue
                want = {a["id"] for a in g["answers"]}
                got = set(row.get("answers", {}))
                if want != got:
                    problems.append(f"{f.name}:{i + 1}: 回答IDが一致しない（不足 {len(want - got)}、余分 {len(got - want)}）")
                obs["scenarios"][row["group"]] = row.get("scenario", {})
                for aid in want & got:
                    obs["answers"][aid] = row["answers"][aid]
        expected = sum(len(batches[f.stem]) for f in vdir.glob("*.jsonl") if f.stem in batches)
        model, _, policy = name.partition("-")
        obs["source"] = f"llm:{MODEL.get(model, model)}:{policy}" if not name.startswith("scenes") else f"llm:{name}"
        obs["variant"] = {"policy": policy, "model": MODEL.get(model, model)}
        out = BASE / f"obs-{name}.json"
        sim.save(out, obs)
        report.append(f"{name}: 行 {n_lines}、場面 {len(obs['scenarios'])}/{expected}、回答 {len(obs['answers'])}、問題 {len(problems)}")
        for p in problems[:10]:
            report.append(f"    {p}")
        if not name.startswith("scenes") and len(obs["scenarios"]) == 64:
            bench.append(obs)
    if len(bench) >= 2:
        ens = sim.ensemble(bench)
        sim.save(BASE / "obs-ensemble.json", ens)
        report.append(f"集団: {len(bench)} 変種 → obs-ensemble.json（ばらつきの大きい項目 {sum(len(v) for v in ens['unsure'].values())}）")
    print("\n".join(report))


if __name__ == "__main__":
    main()
