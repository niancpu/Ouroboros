import { useMemo, useState, type FormEvent } from "react";
import type { CreateSessionRequest } from "../types/api";
import { ErrorBar } from "../components/shell/ErrorBar";
import { Radar } from "../components/common/Radar";
import { Stepper } from "../components/common/Stepper";
import { useSession, useUI } from "../state";

interface ProfileDraft {
  label: string;
  count: number;
  capitalWeight: number;
  infoSensitivity: number;
  riskAversion: number;
}

const DEFAULT_PROFILES: ProfileDraft[] = [
  { label: "游资大佬", count: 2, capitalWeight: 22, infoSensitivity: 9, riskAversion: 4 },
  { label: "公募机构", count: 2, capitalWeight: 30, infoSensitivity: 6, riskAversion: 8 },
  { label: "量化游资", count: 2, capitalWeight: 18, infoSensitivity: 8, riskAversion: 5 },
  { label: "国家队", count: 2, capitalWeight: 20, infoSensitivity: 5, riskAversion: 7 },
  { label: "散户群体", count: 16, capitalWeight: 10, infoSensitivity: 7, riskAversion: 3 },
];

const DEFAULT_FORM = {
  symbol: "demo_stock",
  scenarioId: "demo_a_share",
  chronosAnchor: "2024-01-02T09:30:00+08:00",
  startTick: "2024-01-02T09:30:00+08:00",
  endTick: "2024-01-02T15:00:00+08:00",
  tickInterval: "5m",
  profileSet: "default_24",
};

const FORM_FIELDS: ReadonlyArray<readonly [string, keyof typeof DEFAULT_FORM]> = [
  ["标的代码", "symbol"],
  ["场景编号", "scenarioId"],
  ["时间锚点", "chronosAnchor"],
  ["起始节拍", "startTick"],
  ["结束节拍", "endTick"],
  ["节拍间隔", "tickInterval"],
];

export default function ConfigurationPage() {
  const session = useSession();
  const ui = useUI();
  const [form, setForm] = useState(DEFAULT_FORM);
  const [profiles, setProfiles] = useState<ProfileDraft[]>(DEFAULT_PROFILES);

  const hasLocalProfileDraft = useMemo(
    () => JSON.stringify(profiles) !== JSON.stringify(DEFAULT_PROFILES),
    [profiles],
  );

  const isCreating = session.phase.kind === "creating";
  const lastError = session.phase.kind === "none" ? session.phase.lastError : null;

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function adjustProfile(index: number, field: keyof ProfileDraft, delta: number) {
    setProfiles((current) =>
      current.map((profile, profileIndex) => {
        if (profileIndex !== index || field === "label") return profile;
        const currentValue = Number(profile[field]);
        return { ...profile, [field]: Math.max(0, currentValue + delta) };
      }),
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isCreating) return;
    const request: CreateSessionRequest = {
      scenario_id: form.scenarioId,
      symbol: form.symbol,
      agent_profile_set: form.profileSet,
      start_tick_id: form.startTick,
      end_tick_id: form.endTick,
      tick_interval: form.tickInterval,
    };
    try {
      await session.createSession(request);
      ui.setActiveModule("LIVE");
    } catch {
      /* error already recorded in session.phase.lastError */
    }
  }

  const totalAgents = profiles.reduce((sum, profile) => sum + profile.count, 0);
  const totalCapitalWeight = profiles.reduce((sum, profile) => sum + profile.capitalWeight, 0);

  return (
    <form className="page-grid configuration-page" onSubmit={handleSubmit}>
      <header className="masthead">
        <div className="masthead-title">
          <p className="eyebrow">SYS_CTRL / SANDBOX_INIT</p>
          <h1>Ouroboros · 新建推演</h1>
        </div>
      </header>

      <section className="config-columns">
        <div className="panel form-panel">
          <h2><span>01</span> 标的与环境</h2>
          {FORM_FIELDS.map(([label, field]) => (
            <label className="field-row" key={field}>
              <span>{label}</span>
              <input
                disabled={isCreating}
                value={form[field]}
                onChange={(event) => updateField(field, event.target.value)}
              />
            </label>
          ))}
          <label className="field-row" key="profileSet">
            <span>智能体预设</span>
            <input
              disabled={isCreating}
              value={form.profileSet}
              onChange={(event) => updateField("profileSet", event.target.value)}
            />
          </label>
          <div className="config-meta">
            <span>CFG_ID</span>
            <strong>CFG-20240102-001</strong>
            <span>ENGINE</span>
            <strong>OUROBOROS_CORE</strong>
            <span>MODE</span>
            <strong>SANDBOX</strong>
            <span>VERSION</span>
            <strong>v2.4.1</strong>
          </div>
        </div>

        <div className="panel agent-balance">
          <h2><span>02</span> 智能体配置</h2>
          <div className="profile-grid">
            {profiles.map((profile, index) => (
              <article className="profile-cell" key={profile.label}>
                <h3>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {profile.label}
                  <small>[AGT-{String(index + 1).padStart(2, "0")}]</small>
                </h3>
                <Radar
                  values={[
                    profile.count,
                    profile.capitalWeight,
                    profile.infoSensitivity,
                    profile.riskAversion,
                  ]}
                />
                {(
                  [
                    ["智能体数量", "count"],
                    ["资金权重", "capitalWeight"],
                    ["信息敏感度", "infoSensitivity"],
                    ["风险厌恶度", "riskAversion"],
                  ] as ReadonlyArray<readonly [string, keyof ProfileDraft]>
                ).map(([label, field]) => (
                  <Stepper
                    key={field}
                    label={label}
                    value={Number(profile[field])}
                    onMinus={() => adjustProfile(index, field, -1)}
                    onPlus={() => adjustProfile(index, field, 1)}
                  />
                ))}
              </article>
            ))}
          </div>
          <div className="profile-summary">
            <span>TOTAL_AGENTS</span>
            <strong>{totalAgents}</strong>
            <span>TOTAL_CAP_WEIGHT</span>
            <strong>{totalCapitalWeight}</strong>
            <span>PROFILE_SET</span>
            <strong>{form.profileSet}</strong>
            <span>SEED</span>
            <strong>20240102</strong>
          </div>
        </div>
      </section>

      {hasLocalProfileDraft && (
        <div className="local-profile-warning" role="status">
          本地预览仅供参考，提交时使用 agent_profile_set={form.profileSet}
        </div>
      )}

      {lastError && (
        <ErrorBar code={lastError.code} message={lastError.message ?? "创建会话失败"} />
      )}

      <button
        className="primary-command"
        type="submit"
        disabled={isCreating}
      >
        <span>▷</span>
        {isCreating ? "创建会话中" : "启动推演序列"}
        <small>[ RUN_SIM ]</small>
      </button>
    </form>
  );
}
