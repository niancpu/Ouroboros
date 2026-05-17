import { TopNav } from "./components/shell/TopNav";
import { ChronosPage } from "./pages/ChronosPage";
import ConfigurationPage from "./pages/ConfigurationPage";
import { DossierPage } from "./pages/DossierPage";
import { EntityPage } from "./pages/EntityPage";
import { LivePage } from "./pages/LivePage";
import { useSession, useUI } from "./state";
import { type ModuleKey } from "./config/constants";
import { type ReactNode } from "react";

const MODULE_PAGES: ReadonlyArray<{
  key: ModuleKey;
  label: string;
  render: () => ReactNode;
}> = [
  { key: "CONFIG", label: "新建推演", render: () => <ConfigurationPage /> },
  { key: "LIVE", label: "实时推演", render: () => <LivePage /> },
  { key: "ENTITY", label: "智能体解剖室", render: () => <EntityPage /> },
  { key: "CHRONOS", label: "时间轴剧本管理", render: () => <ChronosPage /> },
  { key: "DOSSIER", label: "崩塌报告", render: () => <DossierPage /> },
];

export function App() {
  const ui = useUI();
  const session = useSession();
  const sessionStatus =
    session.phase.kind === "active" || session.phase.kind === "terminal"
      ? session.phase.session.status
      : "";

  return (
    <div className="app-shell">
      <TopNav
        activeModule={ui.activeModule}
        onSelect={ui.setActiveModule}
        sessionStatus={sessionStatus}
      />
      <main className="workspace">
        {MODULE_PAGES.map((page) => {
          const isActive = ui.activeModule === page.key;
          return (
            <div
              aria-label={page.label}
              aria-hidden={!isActive}
              className="workspace-pane"
              data-module={page.key}
              key={page.key}
            >
              {page.render()}
            </div>
          );
        })}
      </main>
    </div>
  );
}
