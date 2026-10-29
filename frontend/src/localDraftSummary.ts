/** Browser-only draft summary for the dashboard; never an effective plan. */
import { readDrafts, type PlanDraft } from "./planDraftStore.ts";

export type LocalDraftSummary = { versionCount: number; latest: PlanDraft[] };

export function summarizeLocalDrafts(storage: Pick<Storage, "getItem">): LocalDraftSummary {
  const drafts = readDrafts(storage);
  const latestById = new Map<string, PlanDraft>();
  for (const draft of drafts) {
    const previous = latestById.get(draft.id);
    if (!previous || draft.version > previous.version) latestById.set(draft.id, draft);
  }
  const latest = [...latestById.values()].sort((a, b) =>
    Date.parse(b.savedAt) - Date.parse(a.savedAt) ||
    a.symbol.localeCompare(b.symbol) || a.id.localeCompare(b.id));
  return { versionCount: drafts.length, latest };
}
