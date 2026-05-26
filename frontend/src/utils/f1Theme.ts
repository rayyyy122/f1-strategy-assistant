/** F1 车队配色（2024-2025 赛季）。 */
export const TEAM_COLORS: Record<string, string> = {
  "Ferrari": "#DC0000",
  "McLaren": "#FF8000",
  "Mercedes": "#00D7B6",
  "Red Bull": "#1E5BC6",
  "Red Bull Racing": "#1E5BC6",
  "Aston Martin": "#006F62",
  "Alpine F1 Team": "#0090FF",
  "Alpine": "#0090FF",
  "Williams": "#005AFF",
  "RB F1 Team": "#6692FF",
  "RB": "#6692FF",
  "Kick Sauber": "#52E252",
  "Sauber": "#52E252",
  "Haas F1 Team": "#B6BABD",
  "Haas": "#B6BABD",
};

export function getTeamColor(team: string): string {
  // 模糊匹配
  for (const [name, color] of Object.entries(TEAM_COLORS)) {
    if (team.toLowerCase().includes(name.toLowerCase())) return color;
  }
  return "#71717a"; // zinc-500 fallback
}

/** 轮胎配方对应颜色和缩写。 */
export const TIRE_COMPOUND_INFO: Record<string, { color: string; ring: string; label: string }> = {
  SOFT:         { color: "#FF3B3B", ring: "#FF6363", label: "S" },
  MEDIUM:       { color: "#F5C518", ring: "#FFD544", label: "M" },
  HARD:         { color: "#F5F5F5", ring: "#D4D4D8", label: "H" },
  INTERMEDIATE: { color: "#34D399", ring: "#6EE7B7", label: "I" },
  WET:          { color: "#3B82F6", ring: "#60A5FA", label: "W" },
};