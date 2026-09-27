"""Keep AgentRoute-generated .blend files and open them locally.

The browser never receives a filesystem path. A scene id refers only to a file
this process copied out of a BLENDER_TOOL work directory.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_ID = re.compile(r"\A[0-9a-f]{32}\Z")
_MARKER = "Blender tool result:"
_BLEND_MAGIC = b"BLENDER"
_GZIP_MAGIC = b"\x1f\x8b"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class SceneNotFound(Exception):
    """No generated scene is stored under this id."""


class BlenderLaunchError(Exception):
    """The installed Blender application could not be started."""


def _tool_fields(response: str) -> dict | None:
    index = response.rfind(_MARKER)
    if index < 0:
        return None
    fields: dict[str, str] = {}
    for line in response[index + len(_MARKER):].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            break
        key, sep, value = stripped[2:].partition(":")
        if not sep:
            break
        fields[key.strip()] = value.strip()
    return fields


def _zstd():
    """Zstandard codec. Python 3.14 has it in the standard library."""
    if sys.version_info >= (3, 14):
        from compression import zstd
    else:
        from backports import zstd
    return zstd


def _looks_like_blend(path: Path) -> bool:
    """True for a classic .blend or a gzip/zstd file whose payload is one.

    Blender 5 writes zstd-compressed scenes, so the file does not start with
    the plain ``BLENDER`` header.
    """
    try:
        payload = path.read_bytes()
    except OSError:
        return False
    if payload.startswith(_BLEND_MAGIC):
        return True
    try:
        if payload.startswith(_GZIP_MAGIC):
            import gzip

            return gzip.decompress(payload).startswith(_BLEND_MAGIC)
        if payload.startswith(_ZSTD_MAGIC):
            return _zstd().decompress(payload).startswith(_BLEND_MAGIC)
    except Exception:
        return False
    return False


def _generated_scene(response: str) -> Path | None:
    """The scene.blend BLENDER_TOOL just wrote, when execution succeeded."""
    fields = _tool_fields(response)
    if not fields:
        return None
    if fields.get("tool") != "BLENDER_TOOL":
        return None
    if fields.get("invoked") != "yes" or fields.get("executed") != "yes":
        return None
    if fields.get("success") != "yes":
        return None
    raw = fields.get("output") or ""
    if not raw or not os.path.isabs(raw):
        return None
    try:
        path = Path(raw).resolve(strict=True)
    except OSError:
        return None
    if path.name != "scene.blend" or not path.is_file():
        return None
    parent = path.parent
    temp_root = Path(tempfile.gettempdir()).resolve()
    if not parent.name.startswith("agentroute_blender_"):
        return None
    if os.path.normcase(str(parent.parent)) != os.path.normcase(str(temp_root)):
        return None
    if not _looks_like_blend(path):
        return None
    return path


class SceneStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else Path(tempfile.gettempdir()) / "agentroute_scenes"

    def path_for(self, scene_id: str) -> Path | None:
        if not isinstance(scene_id, str) or not _ID.fullmatch(scene_id):
            return None
        root = self.root.resolve()
        candidate = (root / scene_id / "scene.blend").resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        if candidate.is_file():
            return candidate
        return None

    def adopt(self, source: Path) -> str | None:
        scene_id = uuid.uuid4().hex
        destination = self.root / scene_id / "scene.blend"
        try:
            destination.parent.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(source, destination)
        except OSError:
            shutil.rmtree(destination.parent, ignore_errors=True)
            return None
        if self.path_for(scene_id) is None:
            shutil.rmtree(destination.parent, ignore_errors=True)
            return None
        return scene_id

    def publish(self, result: dict) -> dict | None:
        """Copy a successful tool scene and return the client descriptor.

        Omitted unless BLENDER_TOOL ran, succeeded, and the .blend is still a
        real generated file. Fallback turns are omitted too.
        """
        if not isinstance(result, dict) or result.get("fallback_used"):
            return None
        if result.get("response_success") is False:
            return None
        existing = result.get("blender_scene_id")
        if isinstance(existing, str) and self.path_for(existing) is not None:
            return {"scene_id": existing}
        response = result.get("response")
        if not isinstance(response, str):
            return None
        source = _generated_scene(response)
        if source is None:
            return None
        scene_id = self.adopt(source)
        if scene_id is None:
            return None
        result["blender_scene_id"] = scene_id
        return {"scene_id": scene_id}

    def launch(self, scene_id: str) -> None:
        """Open the stored .blend in the installed Blender application."""
        path = self.path_for(scene_id)
        if path is None:
            raise SceneNotFound()
        from tools.blender_tool import BlenderTool

        binary = BlenderTool().find_binary()
        if not binary or not os.path.isfile(binary):
            raise BlenderLaunchError("Blender could not be launched. Open the .blend file with Blender.")
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen([binary, str(path)], **kwargs)
        except OSError as exc:
            raise BlenderLaunchError(
                "Blender could not be launched. Open the .blend file with Blender."
            ) from exc


STORE = SceneStore()


def attach_blender_scene(body: dict, result: dict) -> dict:
    if body is None:
        return body
    scene = STORE.publish(result)
    if scene is not None:
        body["blender_scene"] = scene
    return body
