; ----------   PIC16C5X HEADER   ----------

W       EQU     0

; RESET ADDRESSES

PIC54   EQU     0x1FF
PIC55   EQU     0x1FF
PIC56   EQU     0x3FF
PIC57   EQU     0x7FF

; STATUS WORD REGISTER f3

C       EQU     0
DC      EQU     1
Z       EQU     2
PD      EQU     3
TO      EQU     4
PA0     EQU     5
PA1     EQU     6
PA2     EQU     7

; OPERATIONAL REGISTER FILES

IND     EQU     00
RTCC    EQU     01
PC      EQU     02
STATUS  EQU     03
FSR     EQU     04
PORTA   EQU     05
PORTB   EQU     06
PORTC   EQU     07

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

; ----------   END HEADER   ----------
