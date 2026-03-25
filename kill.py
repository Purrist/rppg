import psutil
import os

def find_running_python():
    python_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = proc.info['name'].lower()
            if 'python' in name or 'python.exe' in name:
                cmd = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                
                # ====================== 过滤掉 extensions ======================
                if ".trae-cn\\extensions" in cmd:
                    continue

                python_procs.append({
                    'pid': proc.info['pid'],
                    'cmd': cmd
                })
        except:
            continue
    return python_procs

def kill_pid(pid):
    try:
        os.system(f"taskkill /F /PID {pid}")
        return True
    except:
        return False

def main():
    print("=" * 65)
    print("🐍 Python 进程管理工具 [数字/输入a=全部杀死/0=退出]")
    print("=" * 65)

    procs = find_running_python()
    if not procs:
        print("✅ 当前没有需要清理的 Python 进程")
        return

    print("\n🔸 你的 Python 进程：")
    for i, p in enumerate(procs):
        print(f"[{i+1}] PID: {p['pid']} | {p['cmd'][:70]}...")

    choice = input("\n请输入指令：").strip().lower()

    if choice == "0":
        print("👋 退出")
        return

    elif choice == "a":
        print("\n⚠️  一键杀死所有 Python 进程...")
        for p in procs:
            kill_pid(p['pid'])
        print("✅ 清理完成！")

    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(procs):
            pid = procs[idx]['pid']
            kill_pid(pid)
            print(f"✅ 已杀死 PID: {pid}")
        else:
            print("❌ 无效序号")
    else:
        print("❌ 输入错误")

if __name__ == '__main__':
    main()