from app import app, get_local_ip

if __name__ == "__main__":
    port = 8080
    ip = get_local_ip()
    print(f"🌐 LAN access: http://{ip}:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,        # 🔴 关键：关 debug
        use_reloader=False # 🔴 关键：关自动重载
    )
