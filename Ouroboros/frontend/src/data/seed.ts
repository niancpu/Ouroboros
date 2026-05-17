import { demoSeed } from "./demoSeed";
import type { AgentSnapshot, WebEventEnvelope } from "../types/webApi";

const agents: AgentSnapshot[] = demoSeed.snapshot.agents.map((agent) => {
  const account = demoSeed.agents.accountSnapshots.find(
    (snapshot) => snapshot.agent_id === agent.agent_id,
  );

  return {
    cash: 0,
    available_cash: 0,
    positions: {},
    available_shares: {},
    frozen_shares: {},
    market_value: agent.position_value,
    ...account,
    ...agent,
  };
});

export const seedState = {
  session: {
    ...demoSeed.session,
    symbol: demoSeed.snapshot.market.symbol,
    status: demoSeed.session.status as string,
  },
  market: demoSeed.snapshot.market,
  agents,
  events: demoSeed.eventsPage.events as WebEventEnvelope[],
  causalChains: demoSeed.audit.causalChains,
  priceSeries: [14.88, 15.02, 15.08, 15.2, 15.16, 15.28],
  agentProfiles: [
    {
      label: "公募机构",
      count: 4,
      capitalWeight: 42,
      infoSensitivity: 6,
      riskAversion: 8,
    },
    {
      label: "游资",
      count: 5,
      capitalWeight: 26,
      infoSensitivity: 9,
      riskAversion: 4,
    },
    {
      label: "散户",
      count: 15,
      capitalWeight: 32,
      infoSensitivity: 7,
      riskAversion: 3,
    },
  ],
  chronos: {
    ticks: [
      "2024-01-02T09:30:00+08:00",
      "2024-01-02T10:30:00+08:00",
      "2024-01-02T11:30:00+08:00",
      "2024-01-02T14:00:00+08:00",
      "2024-01-02T14:02:00+08:00",
      "2024-01-02T15:00:00+08:00",
    ],
    officialTrack: demoSeed.chronos.tracks[0].events.map((event, index) => ({
      id: event.event_ref,
      title: index === 0 ? "连续竞价开始" : event.source,
      ...event,
    })),
    rumorTrack: demoSeed.chronos.tracks[1].events.map((event) => ({
      id: event.event_ref,
      ...event,
    })),
  },
  dossier: {
    collapseProbability: Math.round(demoSeed.dossier.collapse_probability * 1000) / 10,
    generatedAt: demoSeed.dossier.generated_at,
    summary: demoSeed.dossier.summary,
    finding: demoSeed.dossier.headline,
  },
};
