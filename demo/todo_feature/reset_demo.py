from pathlib import Path
import shutil
import subprocess


root = Path(__file__).parent
workspace = root / "workspace"
starter = root / "starter"
runtime_state = workspace / ".proofcode"
git_state = workspace / ".git"
data_file = workspace / "demo_todos.json"

if runtime_state.exists():
    shutil.rmtree(runtime_state)
if (workspace / "todo_app").exists():
    shutil.rmtree(workspace / "todo_app")
if (workspace / "scripts").exists():
    shutil.rmtree(workspace / "scripts")
(workspace / "todo_app").mkdir()
(workspace / "scripts").mkdir()
for source in sorted(starter.glob("*.py")):
    shutil.copy2(source, workspace / "todo_app" / source.name)
for source in sorted((starter / "scripts").glob("*.py")):
    shutil.copy2(source, workspace / "scripts" / source.name)
data_file.write_text(
    '[\n  {"id": 1, "title": "整理申请材料", "completed": false},\n'
    '  {"id": 2, "title": "录制演示视频", "completed": true}\n]\n',
    encoding="utf-8",
)
if not git_state.exists():
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
subprocess.run(["git", "config", "user.name", "ProofCode Demo"], cwd=workspace, check=True)
subprocess.run(
    ["git", "config", "user.email", "demo@proofcode.local"],
    cwd=workspace,
    check=True,
)
subprocess.run(["git", "add", "."], cwd=workspace, check=True)
has_head = subprocess.run(
    ["git", "rev-parse", "--verify", "HEAD"],
    cwd=workspace,
    capture_output=True,
).returncode == 0
commit_command = (
    ["git", "commit", "-q", "--amend", "--no-edit"]
    if has_head
    else ["git", "commit", "-q", "-m", "Todo CLI baseline"]
)
subprocess.run(commit_command, cwd=workspace, check=True)
print(
    "Todo feature demo reset: starter code and legacy data restored; "
    "isolated Git baseline created; ProofCode memory cleared."
)
