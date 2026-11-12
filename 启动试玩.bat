@echo off
chcp 65001 >nul
cd /d "%~dp0"
title IAP 餐厅翻新 Merge-2
python -m streamlit run app.py
pause
