"""BLENDER_TOOL — validate and (optionally) execute Blender Python scripts.

This is a TOOL, not an agent. It is registered only in the tool registry and is
invoked by THREE_D_AGENT. The router must never see or call it.

Execution is gated behind BLENDER_EXECUTION_ENABLED (default: false). Running
model-generated code is security-sensitive, so it stays opt-in.
"""

import os
import shutil
import subprocess
import tempfile

from config import optional_env

from .base_tool import BaseTool, ToolResult

ARTIFACT_EXTENSIONS = (".glb", ".blend", ".gltf", ".obj", ".fbx")
EXECUTION_TIMEOUT_SECONDS = 120


def execution_enabled() -> bool:
    return (optional_env("BLENDER_EXECUTION_ENABLED", "false") or "").lower() == "true"


def _objects_from_stdout(stdout: str) -> list:
    for line in stdout.splitlines():
        if line.startswith("AGENTROUTE_OBJECTS="):
            return [name for name in line.split("=", 1)[1].split("|") if name]
    return []


class BlenderTool(BaseTool):
    name = "BLENDER_TOOL"
    description = "Validate and optionally execute Blender Python (bpy) scripts."

    # --- installation -------------------------------------------------------
    def find_binary(self):
        return optional_env("BLENDER_PATH") or shutil.which("blender")

    def is_available(self) -> bool:
        return bool(self.find_binary())

    def check_installation(self) -> dict:
        binary = self.find_binary()
        if not binary:
            return {"installed": False, "path": None, "version": None}
        try:
            proc = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=30
            )
            version = (proc.stdout or "").strip().splitlines()
            return {
                "installed": True,
                "path": binary,
                "version": version[0] if version else None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"installed": True, "path": binary, "version": None,
                    "error": type(exc).__name__}

    # --- execution ----------------------------------------------------------
    def run(self, script: str, output_dir: str | None = None) -> ToolResult:
        """Accept a bpy script; execute it only if explicitly enabled."""
        if not isinstance(script, str) or not script.strip():
            return ToolResult(
                tool=self.name,
                success=False,
                error="No Blender script provided.",
                metadata={"executed": False},
            )

        if not execution_enabled():
            return ToolResult(
                tool=self.name,
                success=True,
                output=(
                    "Script received and validated. Execution is disabled "
                    "(BLENDER_EXECUTION_ENABLED=false), so Blender was not invoked."
                ),
                metadata={
                    "executed": False,
                    "execution_enabled": False,
                    "script_chars": len(script),
                    "blender_installed": self.is_available(),
                },
            )

        binary = self.find_binary()
        if not binary:
            return ToolResult(
                tool=self.name,
                success=False,
                error=(
                    "Blender executable not found. Install Blender (see setup.md) "
                    "and ensure it is on PATH or set BLENDER_PATH."
                ),
                metadata={"executed": False, "execution_enabled": True},
            )

        workdir = output_dir or tempfile.mkdtemp(prefix="agentroute_blender_")
        script_path = os.path.join(workdir, "agentroute_scene.py")
        try:
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            proc = subprocess.run(
                [binary, "--background", "--python", script_path],
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT_SECONDS,
                cwd=workdir,
            )
            artifacts = [
                os.path.join(workdir, f)
                for f in sorted(os.listdir(workdir))
                if f.lower().endswith(ARTIFACT_EXTENSIONS)
            ]
            return ToolResult(
                tool=self.name,
                success=proc.returncode == 0,
                output=proc.stdout or "",
                error=(proc.stderr or None) if proc.returncode != 0 else None,
                artifacts=artifacts,
                metadata={
                    "executed": True,
                    "execution_enabled": True,
                    "returncode": proc.returncode,
                    "workdir": workdir,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Blender timed out after {EXECUTION_TIMEOUT_SECONDS}s.",
                metadata={"executed": True, "workdir": workdir},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Blender execution failed: {type(exc).__name__}",
                metadata={"executed": True, "workdir": workdir},
            )

    def execute(self, script: str, output_dir: str | None = None) -> ToolResult:
        """Run a bpy script in Blender and save the scene it produces.

        This is the path THREE_D_AGENT uses. It does not report success unless
        Blender actually exits cleanly and writes a .blend file. The older
        ``run`` method stays gated by BLENDER_EXECUTION_ENABLED for validation.
        """
        if not isinstance(script, str) or not script.strip():
            return ToolResult(
                tool=self.name,
                success=False,
                error="No Blender script provided.",
                metadata={"invoked": True, "executed": False},
            )
        if not execution_enabled():
            return ToolResult(
                tool=self.name,
                success=False,
                error=(
                    "Blender was not invoked because BLENDER_EXECUTION_ENABLED "
                    "is not true. No scene was created."
                ),
                metadata={
                    "invoked": True,
                    "executed": False,
                    "execution_enabled": False,
                    "blender_installed": self.is_available(),
                },
            )

        binary = self.find_binary()
        if not binary:
            return ToolResult(
                tool=self.name,
                success=False,
                error=(
                    "Blender executable not found. Install Blender (see setup.md) "
                    "and ensure it is on PATH or set BLENDER_PATH. "
                    "No scene was created."
                ),
                metadata={
                    "invoked": True,
                    "executed": False,
                    "execution_enabled": True,
                    "blender_installed": False,
                },
            )

        workdir = output_dir or tempfile.mkdtemp(prefix="agentroute_blender_")
        script_path = os.path.join(workdir, "agentroute_scene.py")
        harness_path = os.path.join(workdir, "agentroute_harness.py")
        blend_path = os.path.join(workdir, "scene.blend")
        harness = (
            "import runpy\n"
            "import bpy\n"
            f"runpy.run_path({script_path!r}, run_name='__main__')\n"
            "names = [obj.name for obj in bpy.data.objects]\n"
            "print('AGENTROUTE_OBJECTS=' + '|'.join(names))\n"
            f"bpy.ops.wm.save_as_mainfile(filepath={blend_path!r})\n"
        )
        try:
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            with open(harness_path, "w", encoding="utf-8") as fh:
                fh.write(harness)
            proc = subprocess.run(
                [binary, "--background", "--factory-startup", "--python", harness_path],
                capture_output=True,
                text=True,
                timeout=EXECUTION_TIMEOUT_SECONDS,
                cwd=workdir,
            )
            objects = _objects_from_stdout(proc.stdout or "")
            wrote_scene = os.path.isfile(blend_path)
            ok = proc.returncode == 0 and wrote_scene
            artifacts = [blend_path] if wrote_scene else []
            error = None
            if not ok:
                detail = (proc.stderr or proc.stdout or "").strip()
                if len(detail) > 2500:
                    detail = detail[-2500:]
                if not wrote_scene and proc.returncode == 0:
                    error = "Blender exited without writing a scene file. No scene was created."
                    if detail:
                        error = f"{error}\n{detail}"
                else:
                    error = detail or "Blender did not write a scene file."
            return ToolResult(
                tool=self.name,
                success=ok,
                output=proc.stdout or "",
                error=error,
                artifacts=artifacts,
                metadata={
                    "invoked": True,
                    "executed": True,
                    "execution_enabled": True,
                    "returncode": proc.returncode,
                    "workdir": workdir,
                    "objects": objects,
                    "scene_written": wrote_scene,
                },
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Blender timed out after {EXECUTION_TIMEOUT_SECONDS}s. No scene was created.",
                metadata={"invoked": True, "executed": True, "workdir": workdir},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"Blender execution failed: {type(exc).__name__}. No scene was created.",
                metadata={"invoked": True, "executed": True, "workdir": workdir},
            )
