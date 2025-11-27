@echo off
title StudyTimerPro - Apply Patch and Upload

echo ==========================================
echo    StudyTimerPro - Apply Patch and Upload
echo ==========================================
echo.

REM ---- SETTINGS ----
set MAIN_FILE=StudyTimer.py
set BACKUP_FILE=StudyTimer_backup_before_patch.py
REM ------------------

REM Check if patch file exists
if not exist fix.diff (
    echo ERROR: fix.diff not found!
    echo Please save your Codex "Copy git apply" patch as:
    echo   %cd%\fix.diff
    echo.
    goto END
)

REM Make sure this is a git repository
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo ERROR: This folder is not a Git repository.
    echo Make sure this .bat file is inside your StudyTimerPro repo folder.
    echo Current folder: %cd%
    echo.
    goto END
)

REM Check that main file exists
if not exist "%MAIN_FILE%" (
    echo ERROR: %MAIN_FILE% not found in this folder!
    echo Please check MAIN_FILE variable inside the script.
    echo.
    goto END
)

echo Creating backup of %MAIN_FILE% as %BACKUP_FILE% ...
copy /Y "%MAIN_FILE%" "%BACKUP_FILE%" >nul
if errorlevel 1 (
    echo ERROR: Failed to create backup file!
    echo Aborting to avoid damage.
    echo.
    goto END
)
echo Backup created successfully.
echo.

echo Checking patch with: git apply --check fix.diff
git apply --check fix.diff >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Patch did NOT apply cleanly.
    echo No changes were made.
    echo This usually means your local file and GitHub version are different.
    echo Make sure you pushed latest changes BEFORE asking Codex for a patch.
    echo.
    goto END
)

echo.
echo Applying patch...
git apply fix.diff
if errorlevel 1 (
    echo.
    echo ERROR: git apply failed unexpectedly.
    echo Restoring backup file...
    copy /Y "%BACKUP_FILE%" "%MAIN_FILE%" >nul
    echo Backup restored.
    echo.
    goto END
)

echo.
echo Patch applied successfully.
echo.

REM ---- CHECK IF ANY FILE WAS MODIFIED ----
echo Checking for modified files to commit...
git status --porcelain | findstr /r "^[ M]" >nul
if errorlevel 1 (
    echo.
    echo No modified tracked files found after patch.
    echo Maybe patch only touched untracked files or nothing at all.
    echo.
    goto END
)

echo.
echo Staging changes...
git add -u

echo.
echo Committing changes...
git commit -m "Codex patch auto-applied" > commit_log.txt 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Commit failed (maybe no changes were staged).
    echo Commit log:
    type commit_log.txt
    echo.
    goto END
)

echo.
echo Commit complete! Commit log:
type commit_log.txt
echo.

echo Pushing to GitHub (origin/main)...
git push > push_log.txt 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Push FAILED!
    echo Check your internet or GitHub permissions.
    echo ==== PUSH LOG ====
    type push_log.txt
    echo ==================
    echo.
    goto END
)

echo.
echo ==========================================
echo   ALL DONE SUCCESSFULLY!
echo   Patch applied, committed, pushed.
echo ==========================================
echo.

:END
echo.
echo Press ENTER to close this window...
pause >nul
