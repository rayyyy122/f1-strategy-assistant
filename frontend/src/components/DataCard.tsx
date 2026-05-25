import type { TrackCardData } from "../types";

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
      <div className="text-amber-400 font-semibold mb-1 text-xs uppercase tracking-wider">赛道信息</div>
      <div className="text-white font-medium">{data.name}</div>
      <div className="text-zinc-400 text-xs">{data.locality}, {data.country}</div>
    </div>
  );
}

function WeatherCard({ data }: { data: { air_temp_c: number; track_temp_c: number; humidity_pct: number; rainfall: boolean; wind_speed_kmh: number; sessions: string[] } }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-sky-400 font-semibold mb-1 text-xs uppercase tracking-wider">天气数据</div>
      <div className="flex gap-4 text-xs">
        <span className="text-white">🌡️ 气温 <span className="text-zinc-300">{data.air_temp_c}°C</span></span>
        <span className="text-white">🏁 赛道 <span className="text-zinc-300">{data.track_temp_c}°C</span></span>
        <span className={data.rainfall ? "text-green-400" : "text-zinc-500"}>
          🌧️ {data.rainfall ? "降雨" : "无雨"}
        </span>
      </div>
      <div className="text-zinc-500 text-xs mt-0.5">来源: {data.sessions?.join(", ")}</div>
    </div>
  );
}

function QualifyingCard({ data }: { data: { results: { position: number; driver: string; team: string; q3_time: string }[] } }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-lg p-3 text-sm">
      <div className="text-purple-400 font-semibold mb-2 text-xs uppercase tracking-wider">排位赛结果</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1">P</th>
            <th className="text-left py-1">车手</th>
            <th className="text-left py-1">车队</th>
            <th className="text-right py-1">圈速</th>
          </tr>
        </thead>
        <tbody>
          {data.results.slice(0, 5).map((r) => (
            <tr key={r.position} className="border-b border-zinc-800/50">
              <td className="py-1 text-amber-400 font-mono">{r.position}</td>
              <td className="py-1 text-white">{r.driver}</td>
              <td className="py-1 text-zinc-400">{r.team}</td>
              <td className="py-1 text-right text-zinc-300 font-mono">{r.q3_time}</td>
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
      <div className="text-emerald-400 font-semibold mb-1 text-xs uppercase tracking-wider">练习赛数据</div>
      <div className="text-white text-xs">{data.summary}</div>
      <div className="text-zinc-500 text-xs mt-0.5">来源: {data.session}</div>
    </div>
  );
}