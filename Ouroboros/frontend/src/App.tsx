import { TopNav } from "./components/shell/TopNav";
import { ChronosPage } from "./pages/ChronosPage";
import { ConfigurationPage } from "./pages/ConfigurationPage";
import { DossierPage } from "./pages/DossierPage";
import { EntityPage } from "./pages/EntityPage";
import { LivePage } from "./pages/LivePage";
import { useSession, useUI } from "./state";

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
        {ui.activeModule === "CONFIG" && <ConfigurationPage />}
        {ui.activeModule === "LIVE" && <LivePage />}
        {ui.activeModule === "ENTITY" && <EntityPage />}
        {ui.activeModule === "CHRONOS" && <ChronosPage />}
        {ui.activeModule === "DOSSIER" && <DossierPage />}
      </main>
    </div>
  );
}
