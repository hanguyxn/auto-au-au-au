@echo off
echo ========================================
echo  F1686S Auto Register Tool - Setup
echo ========================================
echo.

echo [1/4] Installing Selenium...
pip install selenium

echo.
echo [2/4] Installing Selenium Stealth...
pip install selenium-stealth

echo.
echo [3/4] Installing Webdriver Manager...
pip install webdriver-manager

echo.
echo [4/4] Installing Other Dependencies...
pip install fake-useragent requests

echo.
echo ========================================
echo  Installation Complete!
echo ========================================
echo.
echo Run: python f1686s_register.py
pause
