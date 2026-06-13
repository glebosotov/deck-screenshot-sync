import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ProgressBarWithInfo,
  TextField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { FaPhotoVideo } from "react-icons/fa";

type Settings = {
  serverUrl: string;
  hasApiKey: boolean;
  exiftoolPath: string;
};

type SaveSettings = {
  serverUrl: string;
  exiftoolPath: string;
  apiKey?: string;
  clearApiKey?: boolean;
};

type ScanBucket = {
  total: number;
  new: number;
  lastUploadTime: number;
};

type ScanResult = {
  screenshots: ScanBucket;
  clips: ScanBucket;
  dependencies: DependencyStatus;
};

type DependencyStatus = {
  ffmpeg: boolean;
  exiftool: boolean;
};

type SyncSummary = {
  kind: "screenshots" | "clips";
  status: string;
  total: number;
  new: number;
  ok: number;
  duplicates: number;
  failed: number;
  message: string;
};

type SyncResult = {
  mode: SyncMode;
  summaries: SyncSummary[];
  scan: ScanResult;
};

type RunState = {
  running: boolean;
  mode: string;
  phase: string;
  progress: number;
  current: number;
  total: number;
  filename: string;
  lastResult: SyncResult | null;
  lastError: string;
  startedAt: string;
  finishedAt: string;
};

type SyncMode = "screenshots" | "clips" | "all";

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[payload: SaveSettings], Settings>("save_settings");
const scanMedia = callable<[], ScanResult>("scan");
const startSync = callable<[mode: SyncMode], RunState>("start_sync");
const getRunState = callable<[], RunState>("get_run_state");
const getDependencyStatus = callable<[], DependencyStatus>("get_dependency_status");

const emptyRunState: RunState = {
  running: false,
  mode: "",
  phase: "idle",
  progress: 0,
  current: 0,
  total: 0,
  filename: "",
  lastResult: null,
  lastError: "",
  startedAt: "",
  finishedAt: "",
};

function Content() {
  const [settings, setSettings] = useState<Settings>({
    serverUrl: "",
    hasApiKey: false,
    exiftoolPath: "",
  });
  const [serverUrl, setServerUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [exiftoolPath, setExiftoolPath] = useState("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [dependencies, setDependencies] = useState<DependencyStatus | null>(null);
  const [runState, setRunState] = useState<RunState>(emptyRunState);
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState("");

  const canSync = useMemo(
    () => Boolean(settings.serverUrl && settings.hasApiKey && !runState.running),
    [settings, runState.running],
  );

  const refresh = async () => {
    const [nextSettings, nextScan, nextDeps, nextRunState] = await Promise.all([
      getSettings(),
      scanMedia(),
      getDependencyStatus(),
      getRunState(),
    ]);
    setSettings(nextSettings);
    setServerUrl(nextSettings.serverUrl);
    setExiftoolPath(nextSettings.exiftoolPath);
    setScan(nextScan);
    setDependencies(nextDeps);
    setRunState(nextRunState);
  };

  useEffect(() => {
    refresh().catch((error) => {
      setStatusText(error?.toString?.() ?? "Failed to load plugin state");
    });
  }, []);

  useEffect(() => {
    if (!runState.running) {
      return;
    }
    const id = window.setInterval(() => {
      getRunState()
        .then((nextRunState) => {
          setRunState(nextRunState);
          if (!nextRunState.running) {
            scanMedia().then(setScan).catch(() => undefined);
          }
        })
        .catch((error) => {
          setStatusText(error?.toString?.() ?? "Failed to update progress");
        });
    }, 1000);
    return () => window.clearInterval(id);
  }, [runState.running]);

  const save = async () => {
    setBusy(true);
    setStatusText("");
    try {
      const payload: SaveSettings = { serverUrl, exiftoolPath };
      if (apiKey.trim()) {
        payload.apiKey = apiKey.trim();
      }
      const nextSettings = await saveSettings(payload);
      setSettings(nextSettings);
      setExiftoolPath(nextSettings.exiftoolPath);
      setApiKey("");
      setStatusText("Settings saved");
      toaster.toast({ title: "Game Media Sync", body: "Settings saved" });
    } catch (error) {
      setStatusText(error?.toString?.() ?? "Failed to save settings");
    } finally {
      setBusy(false);
    }
  };

  const run = async (mode: SyncMode) => {
    setBusy(true);
    setStatusText("");
    try {
      const nextRunState = await startSync(mode);
      setRunState(nextRunState);
    } catch (error) {
      setStatusText(error?.toString?.() ?? "Failed to start sync");
    } finally {
      setBusy(false);
    }
  };

  const refreshScan = async () => {
    setBusy(true);
    setStatusText("");
    try {
      const [nextScan, nextDeps] = await Promise.all([
        scanMedia(),
        getDependencyStatus(),
      ]);
      setScan(nextScan);
      setDependencies(nextDeps);
    } catch (error) {
      setStatusText(error?.toString?.() ?? "Failed to scan media");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSection title="Immich">
        <PanelSectionRow>
          <TextField
            label="Server URL"
            value={serverUrl}
            mustBeURL
            disabled={busy || runState.running}
            onChange={(event) => setServerUrl(event.currentTarget.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label={settings.hasApiKey ? "API key saved" : "API key"}
            value={apiKey}
            bIsPassword
            disabled={busy || runState.running}
            onChange={(event) => setApiKey(event.currentTarget.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton disabled={busy || runState.running} onClick={save}>
            Save Settings
          </ActionButton>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Tools">
        <PanelSectionRow>
          <TextField
            label="ExifTool path"
            value={exiftoolPath}
            disabled={busy || runState.running}
            onChange={(event) => setExiftoolPath(event.currentTarget.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "12px", lineHeight: 1.35, opacity: 0.75 }}>
            {exiftoolPath
              ? "Using custom ExifTool location"
              : "Blank uses exiftool from PATH"}
          </div>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Steam Media">
        <PanelSectionRow>
          <StatusRows scan={scan} dependencies={dependencies} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton disabled={busy || runState.running} onClick={refreshScan}>
            Refresh Scan
          </ActionButton>
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton disabled={!canSync || busy} onClick={() => run("screenshots")}>
            Sync Screenshots
          </ActionButton>
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton
            disabled={!canSync || busy || dependencies?.ffmpeg === false}
            onClick={() => run("clips")}
          >
            Sync Clips
          </ActionButton>
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton disabled={!canSync || busy} onClick={() => run("all")}>
            Sync All
          </ActionButton>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Status">
        {runState.running && (
          <PanelSectionRow>
            <ProgressBarWithInfo
              nProgress={Math.max(0, Math.min(1, runState.progress || 0))}
              sOperationText={progressText(runState)}
            />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ResultText runState={runState} statusText={statusText} />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

function ActionButton({
  children,
  disabled,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <div style={{ width: "100%" }}>
      <ButtonItem layout="below" disabled={disabled} onClick={onClick}>
        <span
          style={{
            display: "block",
            width: "100%",
            minWidth: "220px",
            textAlign: "center",
          }}
        >
          {children}
        </span>
      </ButtonItem>
    </div>
  );
}

function StatusRows({
  scan,
  dependencies,
}: {
  scan: ScanResult | null;
  dependencies: DependencyStatus | null;
}) {
  return (
    <div style={{ display: "grid", gap: "6px", fontSize: "13px" }}>
      <div>{bucketText("Screenshots", scan?.screenshots)}</div>
      <div>{bucketText("Clips", scan?.clips)}</div>
      <div>{dependencyText(dependencies)}</div>
    </div>
  );
}

function ResultText({
  runState,
  statusText,
}: {
  runState: RunState;
  statusText: string;
}) {
  const summaries = runState.lastResult?.summaries ?? [];
  const text = runState.lastError
    ? runState.lastError
    : statusText || summaries.map((summary) => summary.message).join(" | ") || "Idle";

  return (
    <div style={{ fontSize: "13px", lineHeight: 1.35, overflowWrap: "anywhere" }}>
      {text}
    </div>
  );
}

function bucketText(label: string, bucket?: ScanBucket) {
  if (!bucket) {
    return `${label}: scanning`;
  }
  return `${label}: ${bucket.new} new / ${bucket.total} total`;
}

function dependencyText(dependencies: DependencyStatus | null) {
  if (!dependencies) {
    return "Tools: checking";
  }
  const clipStatus = dependencies.ffmpeg ? "clips ready" : "ffmpeg missing";
  const metadataStatus = dependencies.exiftool ? "metadata ready" : "exiftool missing";
  return `Tools: ${clipStatus}, ${metadataStatus}`;
}

function progressText(runState: RunState) {
  const file = runState.filename ? ` - ${runState.filename}` : "";
  if (!runState.total) {
    return `${runState.phase}${file}`;
  }
  return `${runState.phase} ${runState.current}/${runState.total}${file}`;
}

export default definePlugin(() => ({
  name: "Game Media Sync",
  titleView: <div className={staticClasses.Title}>Game Media Sync</div>,
  content: <Content />,
  icon: <FaPhotoVideo />,
}));
