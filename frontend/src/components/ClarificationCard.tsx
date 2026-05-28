import { useState } from "react";
import type { ClarificationData, ClarificationField, ClarificationOption } from "../types";

interface Props {
  data: ClarificationData;
  onSubmit: (filled: Record<string, string>) => void;
  disabled?: boolean;
}

const FIELD_ORDER: ClarificationField["field"][] = ["season", "race", "team", "driver"];

export function ClarificationCard({ data, onSubmit, disabled }: Props) {
  const orderedMissing = [...data.missing].sort(
    (a, b) =>
      (FIELD_ORDER.indexOf(a.field) === -1 ? 99 : FIELD_ORDER.indexOf(a.field)) -
      (FIELD_ORDER.indexOf(b.field) === -1 ? 99 : FIELD_ORDER.indexOf(b.field)),
  );

  const [selected, setSelected] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);

  const allFilled = orderedMissing.every((m) => selected[m.field]?.trim());

  function pick(field: string, value: string) {
    if (submitted || disabled) return;
    setSelected((prev) => ({ ...prev, [field]: value }));
  }

  function freeInput(field: string, value: string) {
    if (submitted || disabled) return;
    setSelected((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit() {
    if (!allFilled || submitted) return;
    setSubmitted(true);
    onSubmit(selected);
  }

  return (
    <div className="rounded-lg p-4 text-sm border bg-gradient-to-br from-amber-950/30 to-zinc-950 border-amber-600/40">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-base">🤔</span>
        <span className="font-bold text-amber-300">需要补充信息</span>
      </div>

      {data.message && (
        <div className="text-zinc-300 text-xs mb-3 leading-relaxed">{data.message}</div>
      )}

      {Object.keys(data.extracted || {}).filter((k) => data.extracted[k]).length > 0 && (
        <div className="text-xs mb-3 p-2 rounded bg-zinc-900/60 border border-zinc-800">
          <span className="text-zinc-500">已识别：</span>
          {Object.entries(data.extracted)
            .filter(([, v]) => v !== null && v !== undefined && v !== "")
            .map(([k, v]) => (
              <span key={k} className="ml-2 text-zinc-300">
                <span className="text-zinc-500">{labelOf(k)}:</span> {String(v)}
              </span>
            ))}
        </div>
      )}

      <div className="space-y-3">
        {orderedMissing.map((m) => (
          <FieldBlock
            key={m.field}
            field={m}
            value={selected[m.field] || ""}
            onPick={(v) => pick(m.field, v)}
            onFreeInput={(v) => freeInput(m.field, v)}
            locked={submitted || !!disabled}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!allFilled || submitted || disabled}
        className={`mt-4 w-full py-2 rounded text-sm font-medium transition-colors ${
          allFilled && !submitted && !disabled
            ? "bg-amber-600 hover:bg-amber-500 text-white"
            : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
        }`}
      >
        {submitted ? "已提交，等待响应…" : allFilled ? "提交并继续分析" : `还需选择 ${orderedMissing.length - Object.keys(selected).filter((k) => selected[k]).length} 项`}
      </button>
    </div>
  );
}

function FieldBlock({
  field,
  value,
  onPick,
  onFreeInput,
  locked,
}: {
  field: ClarificationField;
  value: string;
  onPick: (v: string) => void;
  onFreeInput: (v: string) => void;
  locked: boolean;
}) {
  const opts: ClarificationOption[] = field.options || [];
  const showFreeInput = opts.length === 0 || opts.length > 12;

  return (
    <div>
      <div className="text-zinc-400 text-xs mb-1.5 flex items-baseline gap-2">
        <span className="text-zinc-200 font-medium">{field.label}</span>
        {field.prompt_hint && <span className="text-zinc-500">— {field.prompt_hint}</span>}
      </div>

      {opts.length > 0 && opts.length <= 24 && (
        <div className="flex flex-wrap gap-1.5">
          {opts.slice(0, 24).map((o) => {
            const active = value === o.value;
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => onPick(o.value)}
                disabled={locked}
                className={`px-2.5 py-1 rounded text-xs border transition-colors ${
                  active
                    ? "bg-amber-600 border-amber-500 text-white"
                    : "bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-amber-600/60 hover:text-amber-200"
                } ${locked ? "cursor-not-allowed opacity-60" : ""}`}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      )}

      {showFreeInput && (
        <input
          type="text"
          value={value}
          onChange={(e) => onFreeInput(e.target.value)}
          disabled={locked}
          placeholder={field.prompt_hint || `请输入${field.label}`}
          className="mt-1 w-full px-2 py-1 rounded text-xs bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-amber-600/60 disabled:opacity-60"
        />
      )}
    </div>
  );
}

function labelOf(key: string): string {
  return (
    {
      season: "赛季",
      round: "轮次",
      race_name: "赛事",
      team: "车队",
      driver: "车手",
    }[key] || key
  );
}
