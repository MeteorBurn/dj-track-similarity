import { useState } from "react";
import { resolvePanelCollapsed, storePanelCollapsed, type CollapsiblePanel } from "./libraryView";

type WorkspaceView = "discover" | "analyze" | "library" | "search" | "export";

export function useWorkspacePanels() {
  const [setupCollapsed, setSetupCollapsed] = useState(() => resolvePanelCollapsed("setup"));
  const [libraryCollapsed, setLibraryCollapsed] = useState(() => resolvePanelCollapsed("library"));
  const [searchCollapsed, setSearchCollapsed] = useState(() => resolvePanelCollapsed("search"));
  const [exportVisible, setExportVisible] = useState(false);

  function togglePanel(panel: CollapsiblePanel) {
    const setters = { setup: setSetupCollapsed, library: setLibraryCollapsed, search: setSearchCollapsed };
    const collapsed = { setup: setupCollapsed, library: libraryCollapsed, search: searchCollapsed }[panel];
    storePanelCollapsed(panel, !collapsed);
    setters[panel](!collapsed);
  }

  function selectWorkspace(view: WorkspaceView) {
    setExportVisible(view === "export");
    if (view === "export") return;
    setSetupCollapsed(view !== "discover" && view !== "analyze");
    setLibraryCollapsed(view !== "discover" && view !== "library");
    setSearchCollapsed(view !== "discover" && view !== "search");
  }

  return { setupCollapsed, libraryCollapsed, searchCollapsed, exportVisible, togglePanel, selectWorkspace };
}
