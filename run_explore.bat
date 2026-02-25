@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d C:\Users\Docker\Desktop\wxauto
C:\Users\Docker\miniconda3\python.exe moments_scraper.py > scraper_stdout.txt 2>&1
