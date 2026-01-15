@echo off
chcp 65001 >nul
echo ============================================================
echo    双摄像头感知系统 - 一键启动
echo ============================================================
echo.

set TABLET_URL=http://10.117.42.45:8080/video
set PROJECTOR_URL=http://10.117.42.174:8080/video

echo [配置信息]
echo 平板摄像头: %TABLET_URL%
echo 投影摄像头: %PROJECTOR_URL%
echo.

echo [启动后端服务...]
cd /d "%~dp0"\backend
python app.py %TABLET_URL% %PROJECTOR_URL%

echo.
echo ============================================================
echo    系统启动完成！
echo ============================================================
echo.
echo [访问地址]
echo   平板控制界面: http://localhost:3000/tablet
echo   投影训练界面: http://localhost:3000/training
echo   后端 API: http://localhost:8080
echo.
echo [提示]
echo 1. 确保平板上的 IP Webcam 应用正在运行
echo 2. 确保安卓手机上的 IP Webcam 应用正在运行
echo 3. 确保平板和电脑在同一 Wi-Fi 网络
echo 4. 确保安卓手机和电脑在同一 Wi-Fi 网络
echo 5. 如需修改摄像头 URL，请编辑本文件
echo 6. 按 Ctrl+C 停止服务
echo.
pause
