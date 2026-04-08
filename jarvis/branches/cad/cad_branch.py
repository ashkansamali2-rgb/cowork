import subprocess, os, sys, tempfile
sys.path.insert(0, os.path.expanduser("~/jarvis"))
from config import JARVIS_ROOT
from core.orchestrator import execute
from core.search import search

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
CAD_DIR = os.path.join(JARVIS_ROOT, "projects", "cad")
os.makedirs(CAD_DIR, exist_ok=True)

def handle(instruction: str, context: dict = {}) -> str:
    output_file = os.path.join(CAD_DIR, "output.blend")

    print("[CAD] Searching for Blender reference...")
    ref = search(f"Blender Python bpy {instruction}")

    prompt = (
        f"I need ONE line of Blender Python bpy code that creates this object: {instruction}\n"
        f"Reference: {ref[:500]}\n\n"
        "Reply with ONLY the single bpy line that adds the object. Example: bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))"
    )

    raw = execute(prompt, "cad")

    # extract just the bpy line
    bpy_line = ""
    for line in raw.split("\n"):
        l = line.strip()
        if l.startswith("bpy."):
            bpy_line = l
            break

    if not bpy_line:
        bpy_line = "bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))"

    print(f"[CAD] Object line: {bpy_line}")

    script = f"""import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
{bpy_line}
bpy.ops.wm.save_as_mainfile(filepath="{output_file}")
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    print(f"[CAD] Running Blender...")
    result = subprocess.run(
        [BLENDER, "--background", "--python", script_path],
        capture_output=True, text=True, timeout=60
    )
    os.unlink(script_path)

    if result.returncode == 0:
        return f"3D model saved to {output_file}"
    else:
        return f"Blender error:\n{result.stderr[-400:]}"
