@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo PREFLIGHT CHECK — Trading Bot
echo ============================================================
echo.

REM --- 1. Проверка Python ---
echo [1/6] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo    X Python не найден в PATH
    echo    Установи Python 3.11.9 и добавь в PATH
    pause
    exit /b 1
)
python --version
echo    OK Python
echo.

REM --- 2. Фикс табов ---
echo [2/6] Замена табов на 4 пробела...
if exist fix_tabs.py (
    python fix_tabs.py
    echo    OK Табы исправлены
) else (
    echo    WARN fix_tabs.py не найден - пропуск
)
echo.

REM --- 3. Проверка кодировки ---
echo [3/6] Проверка UTF-8 без BOM...
if exist check_encoding.py (
    python check_encoding.py
    echo    OK Кодировка проверена
) else (
    echo    WARN check_encoding.py не найден - пропуск
)
echo.

REM --- 4. Проверка requirements.txt ---
echo [4/6] Проверка requirements.txt (все с ==)...
if exist requirements.txt (
    findstr /R /C:"^[a-zA-Z].*==.*" requirements.txt >nul
    if errorlevel 1 (
        echo    WARN В requirements.txt есть версии без ==
    ) else (
        echo    OK Версии зафиксированы
    )
) else (
    echo    WARN requirements.txt не найден
)
echo.

REM --- 5. Git commit + push ---
echo [5/6] Git commit + push...
git status --porcelain >nul 2>&1
if errorlevel 1 (
    echo    WARN Git не инициализирован - пропуск
) else (
    git add -A
    git diff --cached --quiet
    if errorlevel 1 (
        git commit -m "auto: preflight commit"
        git push 2>nul
        if errorlevel 1 (
            echo    WARN Push не удался
        ) else (
            echo    OK Commit + push OK
        )
    ) else (
        echo    INFO Нечего коммитить
    )
)
echo.

REM --- 6. Запуск бота ---
echo [6/6] Запуск бота...
echo ============================================================
echo.

powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*webhook_bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo    Старый процесс очищен
echo.

echo    Запуск webhook_bot.py...
echo.
python webhook_bot.py

endlocal
pause
