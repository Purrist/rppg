@echo off
chcp 65001 >nul
echo ============================================================
echo    双摄像头感知系统 - 一键启动
echo ============================================================
echo.

:: 默认摄像头URL（需要替换为您的手机实际IP地址）
set TABLET_URL=http://10.117.42.45:8080/video
set SCREEN_URL=http://10.117.42.174:8080/video

echo [摄像头配置提示]
echo ============================================================
echo 1. 请确保手机上已安装 "IP Webcam" 应用
echo 2. 在手机上打开 "IP Webcam" 应用，点击 "Start Server"
echo 3. 记录手机屏幕上显示的 IP 地址和端口
set /p TABLET_URL=请输入平板摄像头URL (默认: %TABLET_URL%): 
if "%TABLET_URL%"=="" set TABLET_URL=http://10.117.42.45:8080/video

set /p SCREEN_URL=请输入屏幕摄像头URL (默认: %SCREEN_URL%): 
if "%SCREEN_URL%"=="" set SCREEN_URL=http://10.117.42.174:8080/video

echo.
echo [配置信息]
echo 平板摄像头: %TABLET_URL%
echo 屏幕摄像头: %SCREEN_URL%
echo.

echo [启动后端服务...]
start "Backend Service" cmd /k "cd /d "%~dp0"\backend && python app.py "%TABLET_URL%" "%SCREEN_URL%""

:: 等待后端服务初始化
timeout /t 3 /nobreak >nul

echo [启动前端服务...]
start "Frontend Service" cmd /k "cd /d "%~dp0"\frontend && npm run dev"

:: 等待前端服务初始化
timeout /t 5 /nobreak >nul

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
echo 6. 关闭所有服务窗口以停止系统
echo.
echo 正在等待服务启动完成...
timeout /t 2 /nobreak >nul
echo 服务已启动！
echo.
pause
