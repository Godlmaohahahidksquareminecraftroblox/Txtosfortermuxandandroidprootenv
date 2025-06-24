#!/usr/bin/env python3
import os, sys, shlex, subprocess, threading, time, tempfile, shutil, zipfile
from collections import defaultdict

REAL_TMP = tempfile.mkdtemp(prefix="txtosvfs_")
ZIP_PATH = "vfs_save.zip"

if os.path.exists(ZIP_PATH):
    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(REAL_TMP)

os.chdir(REAL_TMP)

CWD = ["/"]
NEXT_PID = [2]
PROCESSES = {}
PERMISSIONS = defaultdict(lambda: "rwx")

HOST_TMP = "/data/data/com.termux/files/usr/tmp" if "com.termux" in sys.executable else "/tmp"

os.makedirs("proc", exist_ok=True)
os.makedirs("dev", exist_ok=True)

def join_path(parts):
    return os.path.abspath(os.path.join(*([REAL_TMP] + parts[1:] if parts[0] == "/" else parts)))

def resolve(path):
    if path.startswith("/"):
        return os.path.abspath(os.path.join(REAL_TMP, path[1:]))
    return os.path.abspath(os.path.join(REAL_TMP, *CWD[1:], path))

def list_dir(path):
    try:
        return os.listdir(path)
    except FileNotFoundError:
        return []

def chmod(path, perms):
    PERMISSIONS[resolve(path)] = perms

def has_permission(path, perm):
    return perm in PERMISSIONS[resolve(path)]

def shell_exec(cmd, stdin=None, stdout=None, stderr=None, background=False):
    pid = NEXT_PID[0]
    NEXT_PID[0] += 1
    tty = "tty0"
    PROCESSES[pid] = {"pid": pid, "cmd": cmd, "tty": tty, "status": "Running"}
    proc_dir = os.path.join(REAL_TMP, "proc", str(pid))
    os.makedirs(proc_dir, exist_ok=True)
    with open(os.path.join(proc_dir, "cmdline"), "w") as f: f.write(cmd)
    with open(os.path.join(proc_dir, "tty"), "w") as f: f.write(tty)
    with open(os.path.join(proc_dir, "status"), "w") as f: f.write("Running")

    def run():
        try:
            args = shlex.split(cmd)
            full_path = which(args[0])
            if full_path:
                cwd_env = os.path.join(REAL_TMP, *CWD[1:])
                subprocess.run([full_path] + args[1:], cwd=cwd_env)
            else:
                print(f"{args[0]}: command not found")
        except Exception as e:
            print("error:", e)
        PROCESSES.pop(pid, None)
        shutil.rmtree(proc_dir, ignore_errors=True)

    if background:
        threading.Thread(target=run).start()
        return pid
    else:
        run()
        return 0

def which(cmd):
    paths = os.environ.get("PATH", "/bin:/usr/bin:/data/data/com.termux/files/usr/bin").split(":")
    for p in paths:
        full = os.path.join(p, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None

def builtin_cd(args):
    if len(args) < 2:
        return
    target = args[1]
    if target == "..":
        if len(CWD) > 1:
            CWD.pop()
    elif target == "/":
        CWD.clear(); CWD.append("/")
    else:
        maybe = resolve(target)
        if os.path.isdir(maybe):
            if target != ".":
                CWD.append(target)

def builtin_ls(args):
    detailed = "-l" in args
    show_all = "-a" in args
    target = args[-1] if len(args) > 1 and not args[-1].startswith("-") else "."
    path = resolve(target)
    if not os.path.exists(path):
        print(f"{target}: No such file or directory")
        return
    if has_permission(path, "r"):
        entries = os.listdir(path) if os.path.isdir(path) else [os.path.basename(path)]
        for entry in sorted(entries):
            if not show_all and entry.startswith("."):
                continue
            full = os.path.join(path, entry)
            if detailed:
                mode = PERMISSIONS.get(full, "rwx")
                print(f"{mode} {entry}")
            else:
                if os.path.isdir(full):
                    print(f"\033[94m{entry}/\033[0m", end="  ")
                elif os.access(full, os.X_OK):
                    print(f"\033[92m{entry}\033[0m", end="  ")
                else:
                    print(entry, end="  ")
        print()
    else:
        print("Permission denied")

def builtin_touch(args):
    for f in args[1:]:
        open(resolve(f), "a").close()

def builtin_mkdir(args):
    for d in args[1:]:
        os.makedirs(resolve(d), exist_ok=True)

def builtin_echo(args):
    if ">>" in args or ">" in args:
        append = ">>" in args
        i = args.index(">>") if append else args.index(">")
        content = " ".join(args[1:i])
        path = resolve(args[i + 1])
        mode = "a" if append else "w"
        with open(path, mode) as f:
            f.write(content + "\n")
    else:
        print(" ".join(args[1:]))

def builtin_cat(args):
    for f in args[1:]:
        path = resolve(f)
        if os.path.isfile(path):
            with open(path) as fp:
                print(fp.read(), end="")
        else:
            print(f"{f}: not found")

def builtin_rm(args):
    for f in args[1:]:
        path = resolve(f)
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except: pass

def builtin_mv(args):
    if len(args) == 3:
        shutil.move(resolve(args[1]), resolve(args[2]))

def builtin_grep(args):
    if len(args) < 3: return
    keyword, file = args[1], resolve(args[2])
    try:
        with open(file) as f:
            for line in f:
                if keyword in line:
                    print(line.strip())
    except FileNotFoundError:
        print(f"{args[2]}: not found")

def builtin_chmod(args):
    if len(args) >= 3:
        chmod(resolve(args[2]), args[1])

def builtin_ps(args):
    for pid, meta in PROCESSES.items():
        print(f"{pid} {meta['tty']} {meta['status']} {meta['cmd']}")

def builtin_kill(args):
    if len(args) < 2: return
    target = int(args[1])
    if target in PROCESSES:
        PROCESSES[target]["status"] = "Killed"
        shutil.rmtree(os.path.join(REAL_TMP, "proc", str(target)), ignore_errors=True)
        del PROCESSES[target]

def builtin_pwd(args):
    print("/" + "/".join(CWD[1:]))

def builtin_whoami(args):
    print("root")

def builtin_help(args):
    print("Built-ins: cd ls touch mkdir echo cat rm mv grep chmod ps kill pwd whoami clear exit help uname")

def builtin_clear(args):
    os.system("clear")

def builtin_exit(args):
    raise EOFError()

def builtin_uname(args):
    print("txtOS v1.2.4")

BUILTINS = {
    "cd": builtin_cd, "ls": builtin_ls, "touch": builtin_touch, "mkdir": builtin_mkdir,
    "echo": builtin_echo, "cat": builtin_cat, "rm": builtin_rm, "mv": builtin_mv,
    "grep": builtin_grep, "chmod": builtin_chmod, "ps": builtin_ps, "kill": builtin_kill,
    "pwd": builtin_pwd, "whoami": builtin_whoami, "help": builtin_help,
    "clear": builtin_clear, "exit": builtin_exit, "uname": builtin_uname
}

def main():
    os.environ["PATH"] = "/bin:/usr/bin:/data/data/com.termux/files/usr/bin"
    while True:
        try:
            prompt = "/" + "/".join(CWD[1:]) + "$ "
            cmd = input(prompt).strip()
            if not cmd: continue
            bg = cmd.endswith("&")
            if bg: cmd = cmd[:-1].strip()
            args = shlex.split(cmd)
            if args[0] in BUILTINS:
                BUILTINS[args[0]](args)
            else:
                shell_exec(cmd, background=bg)
        except KeyboardInterrupt:
            print("\n^C")
        except EOFError:
            print("\nexit")
            break

    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(REAL_TMP):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, REAL_TMP)
                zipf.write(full_path, arcname)

if __name__ == "__main__":
    main()
