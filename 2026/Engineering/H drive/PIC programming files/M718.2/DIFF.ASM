Comparing files FIX.ASM and OLD.ASM
***** FIX.ASM
OKAY    MOVF    KEY,W
        XORLW   $0F
        MOVWF   PORTA
***** OLD.ASM
OKAY    MOVF    KEY,W
        MOVWF   PORTA
*****

***** FIX.ASM

        CLRF    PORTA           ; INITIALIZE PORTA
        CLRW
***** OLD.ASM

        MOVLW   $0F             ; INITIALIZE PORTA
        MOVWF   PORTA
        CLRW
*****

***** FIX.ASM
        GOTO    SCAN1
SELECT
        CLRF    PORTA

***** OLD.ASM
        GOTO    SCAN1
SELECT  CLRW
        XORLW   $FF
        MOVWF   PORTA

*****


