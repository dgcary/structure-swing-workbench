import { useState } from "react";
import { LocalPlanDrafts as DraftEditor } from "./LocalPlanDraftsBase";
import { LocalDraftImport } from "./LocalDraftImport";
import { DRAFT_KEY } from "./planDraftStore";

/** Keep the existing editor isolated from the optional history restore flow. */
export function LocalPlanDrafts({ history = false }: { history?: boolean }) {
  const [revision, setRevision] = useState(0);
  let canRestore = false;
  if (history) {
    try { canRestore = localStorage.getItem(DRAFT_KEY) === null; }
    catch { canRestore = false; }
  }
  return <>
    <DraftEditor key={revision} history={history} />
    {history && <section className="panel">
      <h2>恢复历史草稿备份</h2>
      <LocalDraftImport disabled={!canRestore}
        onImported={() => setRevision((value) => value + 1)} />
    </section>}
  </>;
}
