from app import app
import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(
        host='0.0.0.0',   # 关键点
        port=port,
        debug=True
    )
