#!/home/limar01/.local/share/mise/installs/python/latest/bin/python3
import os, sys, json
lane = sys.argv[1] if len(sys.argv) > 1 else "pc"
cmd = sys.argv[2] if len(sys.argv) > 2 else "uptime && whoami && hostname && date 2>&1"
os.environ["ZILLION_LANE"] = lane
sys.path.insert(0, os.path.expanduser("~/Projects/workspace/project/zillioncli/bridge"))
import mq_pc
r = mq_pc.exec_remote(cmd, timeout=15)
sys.stdout.write(json.dumps(r))
