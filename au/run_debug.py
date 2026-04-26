try:
    exec(open('app.py', encoding='utf-8').read())
except Exception:
    import traceback; traceback.print_exc()
