interface TabDefinition {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: TabDefinition[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

function Tabs({ tabs, activeTab, onChange }: TabsProps) {
  return (
    <div className="flex border-b border-gray-200">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        const baseClasses =
          'px-4 py-2 text-sm font-medium focus:outline-none transition-colors';
        const activeClasses =
          'border-b-2 border-blue-600 text-blue-600';
        const inactiveClasses =
          'border-b-2 border-transparent text-gray-500 hover:text-gray-700';
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`${baseClasses} ${isActive ? activeClasses : inactiveClasses}`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
