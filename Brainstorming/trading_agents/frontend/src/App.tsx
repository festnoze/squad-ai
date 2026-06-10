import { useState } from "react";
import type { TabId } from "./types";
import type { GlobalParamsData } from "./components/GlobalParams";
import { usePersistedSymbols } from "./hooks/usePersistedSymbols";
import TabBar from "./components/TabBar";
import StatusBar from "./components/StatusBar";
import DataTab from "./tabs/DataTab";
import BacktestTab from "./tabs/BacktestTab";
import SweepTab from "./tabs/SweepTab";
import EvolutionTab from "./tabs/EvolutionTab";
import OptimizeTab from "./tabs/OptimizeTab";
import ResultsTab from "./tabs/ResultsTab";

function defaultDates(): { start: string; end: string } {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const twoYearsAgo = new Date(now);
  twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);
  const start = twoYearsAgo.toISOString().slice(0, 10);
  return { start, end };
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("data");
  const [status, setStatus] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const { symbols, addSymbol } = usePersistedSymbols();

  const { start: defaultStart, end: defaultEnd } = defaultDates();
  const [globalParams, setGlobalParams] = useState<GlobalParamsData>({
    symbol: symbols[0] ?? "BTC-USD",
    interval: "1d",
    start: defaultStart,
    end: defaultEnd,
  });

  const tabProps = {
    globalParams,
    onGlobalParamsChange: setGlobalParams,
    symbols,
    onAddSymbol: addSymbol,
    onStatus: setStatus,
    setLoading: setIsLoading,
  };

  const renderTab = () => {
    switch (activeTab) {
      case "data":
        return <DataTab {...tabProps} />;
      case "backtest":
        return <BacktestTab {...tabProps} />;
      case "sweep":
        return <SweepTab {...tabProps} />;
      case "evolution":
        return <EvolutionTab {...tabProps} />;
      case "optimize":
        return <OptimizeTab {...tabProps} />;
      case "results":
        return <ResultsTab {...tabProps} />;
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-200">
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="flex flex-1 overflow-hidden">{renderTab()}</div>
      <StatusBar status={status} isLoading={isLoading} />
    </div>
  );
}

export default App;
