import { MODULE_KEYS, type ModuleKey } from "../../config/constants";
import { labelFrom, moduleLabels, sessionStatusLabels } from "../../i18n/labels";

interface TopNavProps {
  activeModule: ModuleKey;
  onSelect: (module: ModuleKey) => void;
  sessionStatus: string;
}

export function TopNav({ activeModule, onSelect, sessionStatus }: TopNavProps) {
  const statusText = sessionStatus
    ? labelFrom(sessionStatusLabels, sessionStatus) || sessionStatus
    : "未创建";
  const moduleIndex = new Map(MODULE_KEYS.map((module, index) => [module, index + 1]));

  return (
    <header className="top-nav">
      <button className="brand-button" type="button" onClick={() => onSelect("CONFIG")}>
        Ouroboros
      </button>
      <nav className="module-nav" aria-label="主模块">
        {MODULE_KEYS.map((module) => (
          <button
            className={module === activeModule ? "module-link active" : "module-link"}
            key={module}
            type="button"
            onClick={() => onSelect(module)}
          >
            <span>{String(moduleIndex.get(module) ?? 0).padStart(2, "0")}</span>
            {labelFrom(moduleLabels, module) || module}
          </button>
        ))}
      </nav>
      <div className="status-strip">
        <span>会话状态</span>
        <strong>{statusText}</strong>
      </div>
    </header>
  );
}
