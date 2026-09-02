from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


root = Path(__file__).parent
workspace = root / "workspace"
starter = root / "starter"

for relative in ("inventory", "scripts", "static"):
    target = workspace / relative
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(starter / relative, target)
shutil.copy2(starter / "server.py", workspace / "server.py")

for generated in (workspace / ".smoke_test.py",):
    if generated.exists():
        generated.unlink()

runtime = workspace / ".proofcode"
if runtime.exists():
    shutil.rmtree(runtime)
demo_data = workspace / "data" / "demo_inventory.json"
shutil.copy2(workspace / "data" / "inventory.json", demo_data)

git_dir = workspace / ".git"
if not git_dir.exists():
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
subprocess.run(["git", "config", "user.name", "ProofCode Demo"], cwd=workspace, check=True)
subprocess.run(["git", "config", "user.email", "demo@proofcode.local"], cwd=workspace, check=True)
subprocess.run(["git", "add", "."], cwd=workspace, check=True)
has_head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=workspace, capture_output=True).returncode == 0
command = ["git", "commit", "-q", "--amend", "--no-edit"] if has_head else ["git", "commit", "-q", "-m", "Stockroom baseline"]
subprocess.run(command, cwd=workspace, check=True)
print("Inventory demo reset: starter website restored, data copied, Git baseline ready, ProofCode memory cleared.")
