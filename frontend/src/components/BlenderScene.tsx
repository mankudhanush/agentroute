import { useRef, useState, type MouseEvent } from "react";
import { blenderSceneUrl, openBlenderScene } from "../api/agentroute";

const SCENE_ID = /^[a-f0-9]{32}$/;

type BlenderSceneProps = {
  sceneId: string | undefined;
};

export function BlenderScene({ sceneId }: BlenderSceneProps) {
  const [phase, setPhase] = useState<"idle" | "opening" | "opened" | "failed">("idle");
  const busy = useRef(false);
  if (!sceneId || !SCENE_ID.test(sceneId)) return null;
  const id = sceneId;

  async function view(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (busy.current) return;
    busy.current = true;
    setPhase("opening");
    try {
      await openBlenderScene(id);
      setPhase("opened");
    } catch {
      setPhase("failed");
    } finally {
      busy.current = false;
    }
  }

  return (
    <div className="scene-bar">
      <p className="scene-status">✓ Blender scene generated</p>
      <button
        type="button"
        className="scene-btn"
        data-scene-id={id}
        onClick={view}
        disabled={phase === "opening"}
      >
        {phase === "opening" ? "Opening in Blender…" : "View in Blender"}
      </button>
      {phase === "opened" && (
        <p className="scene-note">Opened in Blender on this computer.</p>
      )}
      {phase === "failed" && (
        <>
          <p className="scene-note">Blender could not be launched from this page.</p>
          <a className="scene-btn" href={blenderSceneUrl(sceneId)} download="scene.blend">
            Open .blend
          </a>
          <p className="scene-note">Open this file with Blender.</p>
        </>
      )}
    </div>
  );
}
