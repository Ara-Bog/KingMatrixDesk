@echo off

if exist *.spec (
    del /q *.spec
)

if exist dist (
    rmdir /s /q dist
)

if exist build (
    rmdir /s /q build
)

echo Delete succsessfull
call env\Scripts\activate
pyinstaller --onefile  --add-data="interfaces:interfaces" --add-data="drivers:drivers" --icon="icon.ico" --name=matrix main.py 
rem > nul 2>&1 --noconsole 
if %errorlevel% neq 0 (
    echo Build error
) else (
    echo Build succsessfull
)
