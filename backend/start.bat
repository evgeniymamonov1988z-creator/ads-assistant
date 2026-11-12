@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Рекламный ассистент

if not exist requirements.txt (
  echo.
  echo  Не найден файл requirements.txt.
  echo  Похоже, файл запустили не из папки backend.
  echo  Положите start.bat РЯДОМ с папкой app и файлом requirements.txt.
  echo.
  pause
  exit /b
)

echo.
echo  ============================================
 echo   РЕКЛАМНЫЙ АССИСТЕНТ
 echo  ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo  Python не найден.
  echo.
  echo  Установите Python с сайта python.org и ОБЯЗАТЕЛЬНО поставьте
  echo  галочку "Add Python to PATH", затем перезапустите этот файл.
  echo.
  pause
  exit /b
)

if not exist ".installed" goto install
echo  Библиотеки уже установлены, пропускаю установку.
goto run

:install
echo  Первый запуск: устанавливаю нужные библиотеки.
echo  Это займёт 1-3 минуты, окно не закрывайте...
echo.
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Не получилось установить библиотеки.
  echo  Проверьте интернет и попробуйте ещё раз, либо покажите это окно специалисту.
  echo.
  pause
  exit /b
)
echo installed> ".installed"
echo.
echo  Библиотеки установлены.

:run
echo.
set /p MODE=  Открыть демо-режим (без реальных токенов)? [1 = да, 0 = нет]: 
if "%MODE%"=="1" (
  set MOCK_MODE=1
  echo  Включён демо-режим: тестовые данные, реальные кабинеты не затрагиваются.
) else (
  set MOCK_MODE=0
  echo  Обычный режим: используются вписанные токены.
)

echo.
echo  Открываю приложение в браузере: http://127.0.0.1:8000
echo  Это окно не закрывайте - пока оно открыто, приложение работает.
echo  Чтобы остановить: нажмите Ctrl+C или просто закройте окно.
echo.
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo  Приложение остановлено.
pause
