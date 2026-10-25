"""
Runs Python in a running Unreal Editor through the Python plugin's remote execution
(the engine's own remote_execution.py client). Dev-only: it lets a terminal, or Claude
Code, drive the open UE 5.5 editor without restarting it, for example to rerun a
material builder and read its [TEST] lines.

The editor must have remote execution on. This project turns it on per user, in
Config/UserEngine.ini (ignored by git, read by the editor at startup):

  [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
  bRemoteExecution=True

The editor only listens on the local host (the plugin's defaults: bind 127.0.0.1, TTL 0).

Usage (any Python 3):
  python Tools/ue_exec.py --list
  python Tools/ue_exec.py Plugins/DevMaterialTools/Tools/build_m_loadingarc.py
  python Tools/ue_exec.py -c "import unreal; unreal.log('hello')"
  python Tools/ue_exec.py -e "unreal.SystemLibrary.get_engine_version()"
  python Tools/ue_exec.py -c - < script.py
  python Tools/ue_exec.py --wait 300 -e "1"     (right after launching the editor)

It talks to the editor that has this checkout open (matched by project root);
--project-root picks another one. Exit codes: 0 success, 1 the command failed,
2 no editor found or the connection failed.
"""
import argparse
import json
import os
import re
import socket
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the Epic Games Launcher records the engines it installed.
LAUNCHER_INSTALLED = os.path.join(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Epic", "UnrealEngineLauncher", "LauncherInstalled.dat")


def find_engine_root(explicit):
    """The engine of this project's EngineAssociation: a launcher install ("5.5") or a registered source build."""
    if explicit:
        return explicit
    if os.environ.get("UE_ENGINE_ROOT"):
        return os.environ["UE_ENGINE_ROOT"]
    uproject = next(name for name in os.listdir(REPO_ROOT) if name.endswith(".uproject"))
    with open(os.path.join(REPO_ROOT, uproject), encoding="utf-8") as f:
        association = json.load(f)["EngineAssociation"]
    try:
        with open(LAUNCHER_INSTALLED, encoding="utf-8") as f:
            for install in json.load(f)["InstallationList"]:
                if install.get("AppName") == f"UE_{association}":
                    return install["InstallLocation"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Epic Games\Unreal Engine\Builds") as key:
            return winreg.QueryValueEx(key, association)[0]
    except (ImportError, OSError):
        pass
    fail(f"cannot find the engine for EngineAssociation '{association}'; pass --engine-root or set UE_ENGINE_ROOT")


def fail(message, code=2):
    print(f"ue_exec: {message}", file=sys.stderr)
    sys.exit(code)


def load_remote_execution(engine_root):
    python_dir = os.path.join(engine_root, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python")
    if not os.path.isfile(os.path.join(python_dir, "remote_execution.py")):
        fail(f"remote_execution.py not found under {python_dir}")
    sys.path.insert(0, python_dir)
    import remote_execution

    def receive_message(self, expected_type):
        # The engine's version stops at the first recv() shorter than its buffer, which
        # cuts a long result (a builder's log) short. Read until the bytes form one message.
        # The command may run for minutes before the first byte, but the editor sends the
        # result in one go, so a stall after that means it was cut off.
        sock = self._command_channel_socket
        data = b""
        try:
            while True:
                part = sock.recv(65536)
                if not part:
                    break
                data += part
                sock.settimeout(10)
                if data.rstrip().endswith(b"}"):
                    try:
                        json.loads(data.decode("utf-8"))
                        break
                    except ValueError:
                        pass
        except socket.timeout:
            raise RuntimeError(f"the result stopped after {len(data)} bytes (larger than the editor's send buffer?)")
        finally:
            sock.settimeout(None)
        message = remote_execution._RemoteExecutionMessage(None, None)
        if data and message.from_json_bytes(data) and message.passes_receive_filter(self._node_id) \
                and message.type_ == expected_type:
            return message
        raise RuntimeError("Remote party failed to send a valid response!")

    remote_execution._RemoteExecutionCommandConnection._receive_message = receive_message
    return remote_execution


def free_local_port():
    # The editor connects back to the client's command port, so concurrent runs each need their own.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def same_path(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def quote(arg):
    return f'"{arg}"' if not arg or any(c.isspace() for c in arg) else arg


def main():
    parser = argparse.ArgumentParser(description="Run Python in a running Unreal Editor (remote execution).")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("-c", dest="code", help="literal Python code to run ('-' reads it from stdin)")
    source.add_argument("-e", dest="expr", help="a single expression to evaluate; its value is printed")
    source.add_argument("--list", action="store_true", help="list the editors that answer and exit")
    parser.add_argument("script", nargs="?", help="a .py file to run in the editor")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the script (sys.argv)")
    parser.add_argument("--project-root", default=REPO_ROOT, help="pick the editor with this project open (default: this checkout)")
    parser.add_argument("--wait", type=float, default=5, help="seconds to wait for the editor to answer (default 5)")
    parser.add_argument("--attended", action="store_true", help="allow dialogs (the default runs unattended)")
    parser.add_argument("--engine-root", help="engine whose remote_execution.py to use (default: the project's engine)")
    args = parser.parse_args()

    if sum(x is not None for x in (args.code, args.expr, args.script)) + args.list != 1:
        parser.error("give exactly one of: a script, -c, -e or --list")
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    remote_execution = load_remote_execution(find_engine_root(args.engine_root))
    config = remote_execution.RemoteExecutionConfig()
    config.command_endpoint = ("127.0.0.1", free_local_port())
    remote = remote_execution.RemoteExecution(config)
    remote.start()
    try:
        # Nodes answer the client's pings (one per second); --list collects for a moment.
        deadline = time.monotonic() + (min(args.wait, 2.5) if args.list else args.wait)
        while True:
            nodes = remote.remote_nodes
            matches = [n for n in nodes if same_path(n.get("project_root", ""), args.project_root)]
            if (matches and not args.list) or time.monotonic() >= deadline:
                break
            time.sleep(0.1)

        if args.list:
            for n in nodes:
                print(f"{n.get('engine_version', '?')}  {n.get('project_name', '-')}  {n.get('project_root', '-')}  [{n['node_id']}]")
            if not nodes:
                print("ue_exec: no editor answered (is remote execution on, and the editor fully started?)", file=sys.stderr)
            return 0 if nodes else 2
        if not matches:
            others = ", ".join(f"{n.get('project_name', '?')} ({n.get('engine_version', '?')})" for n in nodes) or "none"
            fail(f"no editor with {args.project_root} open answered within {args.wait:g} s (others: {others})")

        if args.script:
            script = os.path.abspath(args.script).replace("\\", "/")
            if not os.path.isfile(script):
                fail(f"no such script: {args.script}")
            command, mode = " ".join(quote(a) for a in [script] + args.args), remote_execution.MODE_EXEC_FILE
        elif args.expr is not None:
            command, mode = args.expr, remote_execution.MODE_EVAL_STATEMENT
        else:
            command = sys.stdin.read() if args.code == "-" else args.code
            mode = remote_execution.MODE_EXEC_FILE

        try:
            remote.open_command_connection(matches[0]["node_id"])
            result = remote.run_command(command, unattended=not args.attended, exec_mode=mode)
        except (OSError, RuntimeError) as e:
            fail(f"connection failed: {e}")
    finally:
        remote.stop()

    # Everything goes to stdout so warnings stay in order with the lines around them.
    for entry in result.get("output", []):
        kind, text = entry.get("type", "Info"), entry.get("output", "").replace("\r\n", "\n").rstrip("\n")
        print(text if kind == "Info" else f"[{kind}] {text}")
    if mode == remote_execution.MODE_EVAL_STATEMENT or not result["success"]:
        text = result.get("result", "").replace("\r\n", "\n").rstrip("\n")
        # The editor joins traceback lines that already end in a newline with another one.
        print(text if result["success"] else re.sub(r"\n{2,}", "\n", text))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
