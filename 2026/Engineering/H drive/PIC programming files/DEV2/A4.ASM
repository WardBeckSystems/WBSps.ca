; smaller debuger for PIC16C73  June 27, 1996
        LIST    F=INHX8M,R=DEC,P=16C73
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

RAMBANK0 ORG     0x20

W_ISR   RES     1               ; ALSO SHADOW AT 0xA0
ST_ISR  RES     1               ; SAVE STATUS FLAGS & BANK SELECT WHEN IN ISR
PCH_ISR RES     1               ; SAVE PCLATH WHEN IN ISR
FSR_ISR RES     1               ; SAVE FSR WHEN IN ISR

I       RES     1
CURK    RES     1
CMD     RES     1
ADDRESS RES     1
DAT     RES     1
STATE   RES     1
WIN     RES     1

RAMBANK1 ORG     0xA0
        RES     1               ; SHADOW OF W_ISR

; ----------   PORTC BITS   ----------

TALLY   EQU     1
TXPIN   EQU     6               ; OUT
RXPIN   EQU     7               ; IN

; ----------   MACROS   ----------

BANK0   MACRO
        BCF     STATUS,RP0
        ENDM

BANK1   MACRO
        BSF     STATUS,RP0
        ENDM

CMPGO   MACRO   X,L
        ADDLW   256-X
	IFCC
        GOTO    L
        ENDM

; ----------   CODE   ----------

        ORG     0
RESET
        GOTO    INIT

; ----------   INTERRUPT JUMP TO   ----------

        ORG     4

        MOVWF   W_ISR           ; SAVE W & STATUS
        SWAPF   STATUS,W
        BANK0
        MOVWF   ST_ISR
        GOTO    ISR
        RES     3               ; NOP

; ----------   KERNEL   ----------

        ORG     0x100
EXECUTE
        ANDLW   0x0F
EXEC_AGAIN
        ADDWF   PCL,F
        GOTO    EXEC_AGAIN      ; SAFETY FIRST.
                                ; IN CASE OF INTERRUPT.
        GOTO    BON
        GOTO    BOFF
        GOTO    VAL
        GOTO    STOB
        GOTO    OUTHEX
        GOTO    OK
        RES     10
        GOTO    INIT

; ----------   ROUTINES   ----------

BON
        MOVLW   0xFF
        MOVWF   PORTB
        RETURN
BOFF
        CLRF    PORTB
        RETURN
VAL
        MOVLW   WIN
        MOVWF   PORTB
        RETURN
STOB
        MOVF    WIN,W
        MOVWF   PORTB
        RETURN

; ----------   INITIALIZATION   ----------

INIT
        RES     1               ; NOP
INIT_L1
        CLRF    INTCON
        IFSET   INTCON,GIE
        GOTO    INIT_L1

        BANK0
        CLRF    RCSTA
        BSF     RCSTA,SPEN
        BSF     RCSTA,CREN
        BANK1
        MOVLW   0x00
        MOVWF   TRISB
        MOVLW   0xBF
        MOVWF   TRISC
        CLRF    PIE1
        BSF     PIE1,RCIE
        MOVLW   25
        MOVWF   SPBRG
        MOVLW   0x24
        MOVWF   TXSTA
        BANK0
        CLRF    TXREG
        CLRF    STATE
        CLRF    DAT
        MOVLW   HIGH EXECUTE
        MOVWF   PCLATH
        BSF     INTCON,PEIE
        BSF     INTCON,GIE
        CALL    OK
MAIN
        GOTO    MAIN

; ----------   INTERRUPT SUBROUTINE   ----------

        ORG     0x0200
ISR
        BCF     PORTC,TALLY

        MOVF    PCLATH,W        ; SAVE BACKGROUD PAGE
        MOVWF   PCH_ISR
        MOVF    FSR,W           ; SAVE FSR
        MOVWF   FSR_ISR

        IFSET   PIR1,RCIF
        GOTO    DEBUG
ISR_EXIT
        BSF     PORTC,TALLY

        MOVF    FSR_ISR,W       ; RESTORE FSR
        MOVWF   FSR
        MOVF    PCH_ISR,W       ; RESTORE PCLATH
        MOVWF   PCLATH
        SWAPF   ST_ISR,W
        MOVWF   STATUS          ; RESTORE STATUS
        SWAPF   W_ISR,F
        SWAPF   W_ISR,W         ; RESTORE W
        RETFIE

; ----------   DEBUG   ----------

CCLT
        MOVF    CURK,W
        CMPGO  9, RE0   ; err
        CMPGO  2, RE1   ; HT LF
        CMPGO  2, RE0   ; err
        CMPGO  1, RE1   ; CR
        CMPGO 18, RE0   ; err
        CMPGO  1, RE1   ; SP
        CMPGO 15, RE0   ; err
        CMPGO 10, RE2   ; 0 1 2 3 4 5 6 7 8 9
        CMPGO  7, RE0   ; err
        CMPGO  3, RE2   ; A B C
        CMPGO  1, RE4   ; D
        CMPGO  1, RE5   ; E
        CMPGO  1, RE2   ; F
        CMPGO  1, RE6   ; G
        CMPGO 11, RE0   ; err
        CMPGO  1, RE7   ; S
RE0     RETLW   0x00    ; error
RE1     RETLW   0x01    ; SP HT CR LF
RE2     RETLW   0x02    ; 0 1 2 3 4 5 6 7 8 9 A B C F a b c f
RE4     RETLW   0x42    ; D d
RE5     RETLW   0x52    ; E e
RE6     RETLW   0x63    ; G g
RE7     RETLW   0x73    ; S s

DEBUG
        MOVLW   HIGH CCLT
        MOVWF   PCLATH          ; SET PAGE FOR ISR
        BANK0
        MOVF    RCSTA,W
        ANDLW   0x06
        IFNZ
        GOTO    OVERRUN
        MOVLW   4
        ADDWF   STATE,F         ; ADVANCE TO NEXT STATE
        MOVF    RCREG,W         ; INPUT CHAR
        MOVWF   CURK            ; SAVE CURRENT INPUT CHAR
        BCF     CURK,7          ; MAKE ASCII
        IFSET   CURK,6          ; MAKE LOWER CASE
        BCF     CURK,5
        CALL    CCLT            ; CHAR CODE LOOKUP TABLE
        MOVWF   I
        IORWF   STATE,W
        ANDLW   0x0F
        ADDWF   PCL,F

        GOTO    WHAT    ; ERR
        GOTO    L4      ; SP
        GOTO    WHAT    ; DIG
        GOTO    WHAT    ; CMD

        GOTO    WHAT    ; ERR
        GOTO    L0      ; SP
        GOTO    L1      ; DIG
        GOTO    L1      ; CMD

        GOTO    WHAT    ; ERR
        GOTO    L3      ; SP
        GOTO    L2      ; DIG
        GOTO    WHAT    ; CMD

        GOTO    WHAT    ; ERR
        GOTO    L4      ; SP
        GOTO    L2      ; DIG
        GOTO    WHAT    ; CMD
L4
        IFCLR   STATE,7
        GOTO    DOCMD
        MOVF    ADDRESS,W
        MOVWF   FSR
        MOVF    DAT,W
        MOVWF   INDF
        INCF    ADDRESS,F
L0
        CLRF    STATE
        CLRF    DAT
        GOTO    ECHO
L1
        MOVF    I,W
        MOVWF   CMD
        IFCLR   CMD,6
        GOTO    WHAT
        GOTO    ECHO
L2
        SWAPF   DAT,F
        MOVF    CURK,W
        IFSET   CURK,6
        ADDLW   9
        ANDLW   0x0F
        IORWF   DAT,F
        GOTO    ECHO
L3
        MOVF    CMD,W
        XORLW   0x63    ; COMPARE FOR GORUN
        IFZ
        GOTO    WHAT    ; CANNOT HAVE GO SPACE
        IFSET   STATE,7 ; IF SPACE THE DON'T EDIT OR STORE
        GOTO    L0
        MOVF    ADDRESS,W
        MOVWF   DAT
        CALL    OUTHEX
        CALL    OUTHEX
DOCMD
        SWAPF   CMD,W
        ANDLW   0x03
        ADDWF   PCL,F
        GOTO    DUMP
        GOTO    EDIT
        GOTO    GORUN
STORE
        MOVF    DAT,W
        MOVWF   ADDRESS
STATE7
        MOVLW   0x84
        MOVWF   STATE
        CLRF    DAT
        GOTO    ECHO
DUMP
        MOVLW   16
        MOVWF   I
        MOVF    DAT,W
        MOVWF   FSR
DUMP1
        MOVLW   0x0D            ; CR
        CALL    EMIT
        MOVLW   "S"             ; S
        CALL    EMIT
        MOVF    FSR,W           ; ADDRESS
        MOVWF   DAT
        CALL    OUTHEX
        CALL    OUTHEX
        MOVLW   " "             ; SPACE
        CALL    EMIT
        MOVF    INDF,W          ; DATA
        MOVWF   DAT
        CALL    OUTHEX
        CALL    OUTHEX
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    DUMP1
        MOVF    FSR,W
        MOVWF   ADDRESS
        GOTO    L0
EDIT
        MOVLW   " "
        CALL    EMIT
        MOVF    DAT,W
        MOVWF   ADDRESS
        MOVWF   FSR
        MOVF    INDF,W
        MOVWF   DAT
        CALL    OUTHEX
        CALL    OUTHEX
        GOTO    STATE7
GORUN
        CLRF    STATE
        MOVLW   HIGH EXECUTE
        MOVWF   PCLATH
        MOVF    DAT,W
        CALL    EXECUTE
        GOTO    L0

OUTHEX
        SWAPF   DAT,F
        MOVF    DAT,W
        ANDLW   0x0F
        ADDLW   0-10
        IFCS
        ADDLW   "A"-"0"-10
        ADDLW   "0"+10
EMIT
        IFCLR   PIR1,TXIF
        GOTO    EMIT
        MOVWF   TXREG
        RETURN
ECHO
        MOVF    CURK,W
        CALL    EMIT
        GOTO    ISR_EXIT

OK
        MOVLW   "O"
        CALL    EMIT
        MOVLW   "K"
        CALL    EMIT
        MOVLW   0x0D
        CALL    EMIT
        RETURN
WHAT
        MOVLW   "W"
        CALL    EMIT
        MOVLW   "H"
        CALL    EMIT
        MOVLW   "A"
        CALL    EMIT
        MOVLW   "T"
        CALL    EMIT
        GOTO    CERR
OVERRUN
        MOVLW   "O"
        CALL    EMIT
        MOVLW   "E"
        CALL    EMIT
        MOVLW   "R"
        CALL    EMIT
        MOVLW   "R"
        CALL    EMIT
CERR
        MOVLW   0x0D
        MOVWF   CURK
        BCF     RCSTA,CREN
        MOVF    RCREG,W
        MOVF    RCREG,W
        BSF     RCSTA,CREN
        GOTO    L0

        END
