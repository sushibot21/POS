@echo off
title Create Desktop Shortcut — Highway Rasoi POS
echo.
echo  Creating "Highway Rasoi POS" shortcut on your Desktop...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$lnk = $ws.CreateShortcut(\"$desktop\Highway Rasoi POS.lnk\");" ^
  "$lnk.TargetPath = '%~dp0Highway Rasoi POS.bat';" ^
  "$lnk.WorkingDirectory = '%~dp0';" ^
  "$lnk.IconLocation = '%~dp0app-icon.ico';" ^
  "$lnk.Description = 'Highway Rasoi POS — point-of-sale terminal';" ^
  "$lnk.WindowStyle = 1;" ^
  "$lnk.Save();" ^
  "Write-Host '[ OK ] Desktop shortcut created.'"

echo.
echo  Done. Look for the "Highway Rasoi POS" icon on your Desktop.
echo.
pause
