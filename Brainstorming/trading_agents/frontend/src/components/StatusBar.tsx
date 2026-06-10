interface StatusBarProps {
  status: string;
  isLoading: boolean;
}

export default function StatusBar({ status, isLoading }: StatusBarProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-slate-800 border-t border-slate-700 text-xs text-slate-400">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            isLoading ? "bg-yellow-400 animate-pulse" : "bg-green-400"
          }`}
        />
        <span>{isLoading ? "Processing..." : "Ready"}</span>
      </div>
      <span className="text-slate-600">|</span>
      <span className="truncate">{status || "No recent activity"}</span>
    </div>
  );
}
