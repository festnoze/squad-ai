import type { TabId } from "../types";

const TABS: { id: TabId; label: string }[] = [
  { id: "data", label: "Data" },
  { id: "backtest", label: "Backtest" },
  { id: "sweep", label: "Sweep" },
  { id: "evolution", label: "Evolution" },
  { id: "optimize", label: "Optimize" },
  { id: "results", label: "Results" },
];

interface TabBarProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

export default function TabBar({ activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex border-b border-slate-700 bg-slate-800">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`px-6 py-3 text-sm font-medium transition-colors cursor-pointer ${
            activeTab === tab.id
              ? "text-purple-400 border-b-2 border-purple-500 bg-slate-900"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-700/50"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
