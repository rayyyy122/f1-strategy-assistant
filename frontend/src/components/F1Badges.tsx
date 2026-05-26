import { TIRE_COMPOUND_INFO, getTeamColor } from "../utils/f1Theme";

/** 轮胎配方徽章。 */
export function TireBadge({ compound, size = "md" }: { compound: string; size?: "sm" | "md" | "lg" }) {
  const upper = compound.toUpperCase();
  const info = TIRE_COMPOUND_INFO[upper] || { color: "#71717a", ring: "#a1a1aa", label: "?" };
  const sizeClass = {
    sm: "w-4 h-4 text-[8px]",
    md: "w-5 h-5 text-[10px]",
    lg: "w-7 h-7 text-xs",
  }[size];

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-bold border-2 ${sizeClass}`}
      style={{
        backgroundColor: info.color,
        borderColor: info.ring,
        color: upper === "HARD" ? "#000" : "#000",
      }}
      title={`${upper} 轮胎`}
    >
      {info.label}
    </span>
  );
}

/** 车队配色条。 */
export function TeamColorStripe({ team }: { team: string }) {
  const color = getTeamColor(team);
  return (
    <span
      className="inline-block w-1 h-3.5 rounded-sm mr-1.5 align-middle"
      style={{ backgroundColor: color }}
      title={team}
    />
  );
}