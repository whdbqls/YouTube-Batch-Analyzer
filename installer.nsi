; NSIS installer script for YouTube Batch Analyzer
; Usage: makensis installer.nsi

!define PRODUCT_NAME "YouTube Batch Analyzer"
!define COMPANY_NAME "YourCompany"
!define VERSION "1.0.0"

OutFile "${PRODUCT_NAME} Setup ${VERSION}.exe"
InstallDir "$PROGRAMFILES\\${COMPANY_NAME}\\${PRODUCT_NAME}"
ShowInstDetails show

Section "Install"
    SetOutPath "$INSTDIR"
    ; Copy files from dist folder (assumes build already ran)
    File /r "dist\\*.*"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\${COMPANY_NAME}"
    CreateShortCut "$SMPROGRAMS\\${COMPANY_NAME}\\${PRODUCT_NAME}.lnk" "$INSTDIR\\${PRODUCT_NAME}.exe"
    CreateShortCut "$DESKTOP\\${PRODUCT_NAME}.lnk" "$INSTDIR\\${PRODUCT_NAME}.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\\${PRODUCT_NAME}.exe"
    RMDir /r "$INSTDIR"
    Delete "$SMPROGRAMS\\${COMPANY_NAME}\\${PRODUCT_NAME}.lnk"
    Delete "$DESKTOP\\${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\\${COMPANY_NAME}"
SectionEnd
