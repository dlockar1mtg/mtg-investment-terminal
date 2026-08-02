@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0run_collector_v1_canonical_identity_lineage_recertification.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo ============================================================
echo COMMITTED GOVERNANCE RUNNER RESULT
echo ============================================================
echo Exit code: %EXIT_CODE%
if not "%EXIT_CODE%"=="0" (
  echo RECERTIFICATION DID NOT PASS.
  echo No calibration, ranking, or purchase authorization occurred.
) else (
  echo RECERTIFICATION PASSED.
  echo Calibration is the next governed stage.
)
exit /b %EXIT_CODE%
