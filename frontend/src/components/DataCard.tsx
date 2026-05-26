import type { TrackCardData } from "../types";
import { TeamColorStripe } from "./F1Badges";

export function DataCard({ cardType, data }: { cardType: string; data: unknown }) {
  switch (cardType) {
    case "track":
      return <TrackCard data={data as TrackCardData} />;
    case "weather":
      return <WeatherCard data={data as { air_temp_c: number; track_temp_c: number; humidity_pct: number; rainfall: boolean; wind_speed_kmh: number; sessions: string[] }} />;
    case "qualifying":
      return <QualifyingCard data={data as { results: { position: number; driver: string; team: string; q3_time: string }[] }} />;
    case "practice":
      return <PracticeCard data={data as { session: string; drivers_analyzed: number; summary: string }} />;
    default:
      return null;
  }
}

function TrackCard({ data }: { data: TrackCardData }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-red-500 font-semibold mb-1 text-xs uppercase tracking-wider">🏁 赛道</div>
      <div className="text-white font-medium">{data.name}</div>
      <div className="text-zinc-400 text-xs">{data.locality}, {data.country}</div>
    </div>
  );
}

function WeatherCard({ data }: { data: { air_temp_c: number; track_temp_c: number; humidity_pct: number; rainfall: boolean; wind_speed_kmh: number; sessions: string[] } }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-sky-400 font-semibold mb-1 text-xs uppercase tracking-wider">☁️ 天气</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <span className="text-white">🌡️ 气温 <span className="text-zinc-300">{data.air_temp_c}°C</span></span>
        <span className="text-white">🏁 赛道 <span className="text-zinc-300">{data.track_temp_c}°C</span></span>
        <span className={data.rainfall ? "text-green-400" : "text-zinc-500"}>
          🌧️ {data.rainfall ? "降雨" : "无雨"}
        </span>
        <span className="text-zinc-400">💨 {data.wind_speed_kmh} km/h</span>
      </div>
      <div className="text-zinc-500 text-xs mt-0.5">来源: {data.sessions?.join(", ")}</div>
    </div>
  );
}

function QualifyingCard({ data }: { data: { results: { position: number; driver: string; team: string; q3_time: string }[] } }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-purple-400 font-semibold mb-2 text-xs uppercase tracking-wider">📋 排位赛</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1 w-7">P</th>
            <th className="text-left py-1">车手 / 车队</th>
            <th className="text-right py-1">圈速</th>
          </tr>
        </thead>
        <tbody>
          {data.results.slice(0, 5).map((r) => (
            <tr key={r.position} className="border-b border-zinc-800/50">
              <td className="py-1.5 text-red-500 font-mono font-bold">{r.position}</td>
              <td className="py-1.5">
                <div className="flex items-center">
                  <TeamColorStripe team={r.team} />
                  <span className="text-white">{r.driver}</span>
                </div>
                <div className="text-zinc-500 text-[10px] pl-2.5 mt-0.5">{r.team}</div>
              </td>
              <td className="py-1.5 text-right text-zinc-300 font-mono align-top">{r.q3_time}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PracticeCard({ data }: { data: { session: string; drivers_analyzed: number; summary: string } }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-emerald-400 font-semibold mb-1 text-xs uppercase tracking-wider">🏎️ 练习赛</div>
      <div className="text-white text-xs">{data.summary}</div>
      <div className="text-zinc-500 text-xs mt-0.5">来源: {data.session}</div>
    </div>
  );
}