import os, sys, json
sys.path.insert(0, r"D:\Hermes-Lab\hermes-agent")
base = r"D:\Temp\claude\e76210c2bd5515e6\38af4e07-2e25-47f8-b170-de349f30130b\scratchpad\permtest"
inside, outside = os.path.join(base, "inside", "a.md"), os.path.join(base, "outside", "b.md")
from agent import file_safety as fs
out = {"HERMES_WRITE_SAFE_ROOT": os.environ.get("HERMES_WRITE_SAFE_ROOT")}
for label, p in (("inside", inside), ("outside", outside),
                 ("hermes_state_db", os.path.join(os.environ["HERMES_HOME"], "state.db")),
                 ("ssh_key", os.path.expanduser(r"~\.ssh\id_ed25519"))):
    out[label] = fs.get_write_denied_error(p)
from tools.file_tools import write_file_tool
for label, p in (("tool_inside", inside), ("tool_outside", outside)):
    r = write_file_tool(p, "probe\n", task_id="permtest")
    out[label] = json.loads(r) if isinstance(r, str) else r
    out[label + "_exists"] = os.path.exists(p)
print(json.dumps(out, indent=1, default=str)[:3000])
