const REPO = "https://github.com/mankudhanush/agentroute";

function Note({ hidden = false }: { hidden?: boolean }) {
  return (
    <p aria-hidden={hidden || undefined}>
      Download the backend from the GitHub repo and run it on your machine.{" "}
      <a href={REPO} target="_blank" rel="noreferrer">
        github.com/mankudhanush/agentroute
      </a>
      <span aria-hidden="true"> · </span>
    </p>
  );
}

export function BackendNote() {
  return (
    <div className="backend-note" role="region" aria-label="Download the backend">
      <div className="backend-note-track">
        <Note />
        <Note hidden />
      </div>
    </div>
  );
}
