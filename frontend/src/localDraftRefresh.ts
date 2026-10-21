/** One consistent snapshot of browser-local manual drafts for cross-tab refresh. */
import { DRAFT_KEY, readDrafts, type PlanDraft } from "./planDraftStore.ts";
import { summarizeLocalDrafts, type LocalDraftSummary } from "./localDraftSummary.ts";

export type DraftRefresh = {
  drafts: PlanDraft[];
  summary: LocalDraftSummary;
  editingStale: boolean;
};

export function refreshLocalDrafts(
  storage: Pick<Storage, "getItem">,
  editingId: string | null,
  editingVersion: number | null,
): DraftRefresh {
  const snapshot = storage.getItem(DRAFT_KEY);
  const frozen = { getItem: (key: string) => key === DRAFT_KEY ? snapshot : null };
  const drafts = readDrafts(frozen);
  const summary = summarizeLocalDrafts(frozen);
  const latest = editingId === null ? null :
    summary.latest.find((item) => item.id === editingId)?.version ?? null;
  return {
    drafts,
    summary,
    editingStale: editingId !== null && editingVersion !== latest,
  };
}
