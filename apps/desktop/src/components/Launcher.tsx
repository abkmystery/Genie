interface LauncherProps {
  open: boolean;
  onToggle(): void;
}

export function Launcher({ open, onToggle }: LauncherProps) {
  return (
    <div className="launcher">
      <div className="launcher-handle" aria-hidden="true" />
      <button className="launcher-button" onClick={onToggle} type="button" aria-label="Open Genie">
        <span className="launcher-mark" aria-hidden="true">
          <span className="launcher-orbit launcher-orbit-outer" />
          <span className="launcher-orbit launcher-orbit-inner" />
          <span className="launcher-core">G</span>
          <span className="launcher-spark" />
        </span>
        <span className="launcher-label">{open ? "Close" : "Genie"}</span>
      </button>
    </div>
  );
}
