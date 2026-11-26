@echo off
title Agente Meta Ads - Painel de Controle
cd /d "%~dp0"

echo =======================================================
echo          INICIANDO O AGENTE DE IA META ADS
echo =======================================================
echo.
echo Abrindo o painel no seu navegador...
echo.

python -m streamlit run app.py
pause
