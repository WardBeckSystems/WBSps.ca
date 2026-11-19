; ----------   MACROS   ----------

IFZ     MACRO
        BTFSC   STATUS,Z
        ENDM

IFNZ    MACRO
        BTFSS   STATUS,Z
        ENDM

IFCS    MACRO
        BTFSC   STATUS,C
        ENDM

IFCC    MACRO
        BTFSS   STATUS,C
        ENDM

IFSET   MACRO   F,BIT
        BTFSC   F,BIT
        ENDM

IFCLR   MACRO   F,BIT
        BTFSS   F,BIT
        ENDM

; ----------   .   ----------
