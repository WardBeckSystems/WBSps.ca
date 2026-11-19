
        LIST    F=INHX8M,R=DEC,P=16C73
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

RAMBANK0 ORG     0x20

W_ISR   RES     1               ; ALSO SHADOW AT 0xA0
ST_ISR  RES     1               ; SAVE STATUS FLAGS & BANK SELECT WHEN IN ISR
PCH_ISR RES     1               ; SAVE PCLATH WHEN IN ISR
FSR_ISR RES     1               ; SAVE FSR WHEN IN ISR
TEMP1   RES     1               ; TEMPS FOR ISR ROUTINES
TEMP2   RES     1
PRESS1  RES     1               ; BITMAP OF PRESSED KEYS
PRESS2  RES     1
ADR0    RES     1               ; A/D RESULT FOR FADER
ADR1    RES     1               ; A/D RESULT FOR GROUP FADER
CHONKS  RES     1               ; CHANNEL ON KEY DEBOUNCE STATE
CHONES  RES     1               ; EXTERNAL CHANNEL ON DEBOUNCE STATE
SIG     RES     1               ; FLAGS TO SIGNAL ACTIONS

        ORG     0x30             ; MUST HAVE BIT 4 SET
KTAB    RES     16              ; DEBOUNCE STATES FOR KEYS
FLP     RES     1               ; FORGROUND  LIST POINTER
FLT     RES     7               ; FORGROUND  LINK TABLE
BLP     RES     1               ; BACKGROUND LIST POINTER
BLT     RES     7               ; BACKGROUND LINK TABLE

OUT1    RES     1               ; BIT MAP OF OUTPUT STATES
OUT2    RES     1
DACL    RES     1               ; LSB OF LEVEL FOR DAC
DACH    RES     1               ; MSB OF LEVEL FOR DAC

I       RES     1

CURK    RES     1
CMD     RES     1
ADDRESS RES     1
DAT     RES     1
STATE   RES     1
WIN     RES     1

RAMBANK1 ORG     0xA0
        RES     1               ; SHADOW OF W_ISR
LISTSPACE
        RES     95

; ----------   PORTA BITS   ----------

MASTAD  EQU     0               ; analog input
SLAVAD  EQU     1               ; anolog input
CHONSW  EQU     2               ; in
XXX     EQU     3               ; unused anolog input
GMCNCL  EQU     4               ; bi
CHONC   EQU     5               ; out

; ----------   PORTB BITS   ----------

PFAIL   EQU     0               ; in
GCS     EQU     1               ; out
ACS     EQU     2               ; out
BCS     EQU     3               ; out
ROW1    EQU     4               ; in
ROW2    EQU     5               ; in
ROW3    EQU     6               ; in
ROW4    EQU     7               ; in

; ----------   PORTC BITS   ----------
TALLY   EQU     1

OKAY    EQU     0               ; out
EECS    EQU     1               ; out
EXTCHON EQU     2               ; in
MSCK    EQU     3               ; in
MSDO    EQU     4               ; in
MSDI    EQU     5               ; out
SCLK    EQU     6               ; out
SDATA   EQU     7               ; out

; ----------   EQUATES   ----------

DELAY   EQU     16              ; 500 us WITH OPTION 0xC0
NKEYS   EQU     16              ; NUMBER OF KEYS

COL1    EQU     00000010B       ; PORTB CODES FOR KEYBOARD COLUMS
COL2    EQU     00000110B
COL3    EQU     00001010B
COL4    EQU     00001110B

ERRPULSE EQU    00000010B       ; connect counter to U2 pin 4
                                ; to count error pulses.
CHIP1   EQU     00000110B       ; PORTB CODES FOR CHIP SELECTS
CHIP2   EQU     00001010B
CHIP3   EQU     00001110B

IH15LO  EQU     0x60             ; IH15LO  EQU     0xBE
IH15HI  EQU     0x0D             ; IH15HI  EQU     0x0E

; ----------   SIG BITS   ----------

DACNEW0 EQU     0       ; NEED TO UPDATE DAC DUE TO FADER OR GROUP OR MSTR
DACNEW1 EQU     1       ; NEED TO UPDATE DAC DUE TO GROUP FADER
EOTREL  EQU     2       ; SIGNALS RELEASE OF EOT SWITCH

; ----------   MACROS   ----------

BANK0   MACRO
        BCF     STATUS,RP0
        ENDM

BANK1   MACRO
        BSF     STATUS,RP0
        ENDM

TXBIT   MACRO   REG,BIT
        IFSET   REG,BIT
        BSF     PORTC,SDATA
        IFCLR   REG,BIT
        BCF     PORTC,SDATA
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

RXBIT   MACRO   REG
        RLF     REG,F
        BCF     REG,0
        IFSET   PORTC,SDATA
        BSF     REG,0
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

IFINC   MACRO   X,REG
        IFSET   KTAB+X,0
        INCF    REG,F
        ENDM

SKIP_F  MACRO
        INCF    FLP,F
        ENDM

SKIP_B  MACRO
        INCF    BLP,F
        ENDM

JUMP_F  MACRO   X
        MOVF    FLT+X,W
        MOVWF   FLP
        GOTO    EXECUTE
        ENDM

JUMP_B  MACRO   X
        MOVF    BLT+X,W
        MOVWF   BLP
        GOTO    EXECUTE
        ENDM

; ----------   .   ----------

; ----------   CODE   ----------

        ORG     0
RESET
        RES     3
        GOTO    INIT

; ----------   INTERRUPT JUMP TO   ----------

        ORG     4

        MOVWF   W_ISR           ; SAVE W & STATUS
        SWAPF   STATUS,W
        BANK0
        MOVWF   ST_ISR
        RES     1               ; NOP
        GOTO    ISR

; ----------   .   ----------

SUBS

; ----------   KERNEL   ----------

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

; ----------   INTERRUPT SUBROUTINE   ----------

        ORG     0x0400
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


; ----------   ROUTINES   ----------

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

        MOVLW   HIGH SUBS
        MOVWF   PCLATH

        BSF     INTCON,PEIE
        BSF     INTCON,GIE

        CALL    OK
MAIN
        GOTO    MAIN

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

; ----------   DEBUG   ----------

        ORG     0x0600
CCLT
        ANDLW   0x7F
        ADDWF   PCL,F
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	7	; HT
	RETLW	7	; LF
	RETLW	0	;
	RETLW	0	;
	RETLW	7	; CR
	RETLW	0	;
	RETLW	0	;

	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;
	RETLW	0	;

	RETLW	7	; SP
	RETLW	0	; !
	RETLW	0	; "
	RETLW	0	; #
	RETLW	0	; $
	RETLW	0	; %
	RETLW	0	; &
	RETLW	0	; '
	RETLW	0	; (
	RETLW	0	; )
	RETLW	0	; *
	RETLW	0	; +
	RETLW	0	; ,
	RETLW	0	; -
	RETLW	0	; .
	RETLW	0	; /

	RETLW	5	; 0
	RETLW	5	; 1
	RETLW	5	; 2
	RETLW	5	; 3
	RETLW	5	; 4
	RETLW	5	; 5
	RETLW	5	; 6
	RETLW	5	; 7
	RETLW	5	; 8
	RETLW	5	; 9
	RETLW	0	; :
	RETLW	0	; ;
	RETLW	0	; <
	RETLW	0	; =
	RETLW	0	; >
	RETLW	0	; ?

	RETLW	0	; @
	RETLW	6	; A
	RETLW	6	; B
	RETLW	6	; C
	RETLW	1	; D
	RETLW	2	; E
	RETLW	6	; F
	RETLW	3	; G
	RETLW	0	; H
	RETLW	0	; I
	RETLW	0	; J
	RETLW	0	; K
	RETLW	0	; L
	RETLW	0	; M
	RETLW	0	; N
	RETLW	0	; O

	RETLW	0	; P
	RETLW	0	; Q
	RETLW	0	; R
	RETLW	4	; S
	RETLW	0	; T
	RETLW	0	; U
	RETLW	0	; V
	RETLW	0	; W
	RETLW	0	; X
	RETLW	0	; Y
	RETLW	0	; Z
	RETLW	0	; [
	RETLW	0	; \
	RETLW	0	; ]
	RETLW	0	; ^
	RETLW	0	; _

	RETLW	0	; `
	RETLW	6	; a
	RETLW	6	; b
	RETLW	6	; c
	RETLW	1	; d
	RETLW	2	; e
	RETLW	6	; f
	RETLW	3	; g
	RETLW	0	; h
	RETLW	0	; i
	RETLW	0	; j
	RETLW	0	; k
	RETLW	0	; l
	RETLW	0	; m
	RETLW	0	; n
	RETLW	0	; o

	RETLW	0	; p
	RETLW	0	; q
	RETLW	0	; r
	RETLW	4	; s
	RETLW	0	; t
	RETLW	0	; u
	RETLW	0	; v
	RETLW	0	; w
	RETLW	0	; x
	RETLW	0	; y
	RETLW	0	; z
	RETLW	0	; {
	RETLW	0	; |
	RETLW	0	; }
	RETLW	0	; ~
	RETLW	0	;

DEBUG
        MOVLW   HIGH CCLT
        MOVWF   PCLATH          ; SET PAGE FOR ISR
        BANK0
        MOVF    RCSTA,W
        ANDLW   0x06
        IFNZ
        GOTO    OVERRUN
        MOVLW   8
        ADDWF   STATE,F
        MOVF    RCREG,W
        MOVWF   CURK
        CALL    CCLT
        IORWF   STATE,W
        ANDLW   0x1F
        ADDWF   PCL,F

        GOTO    WHAT    ;  4  0   0
        GOTO    WHAT    ;  4  1   0
        GOTO    WHAT    ;  4  2   0
        GOTO    WHAT    ;  4  3   0
        GOTO    WHAT    ;  4  4   0
        GOTO    WHAT    ;  4  5   0
        GOTO    WHAT    ;  4  6   0
        GOTO    L4C     ;  4  7   1

        GOTO    WHAT    ;  1  0   0
        GOTO    L1      ;  1  1   2
        GOTO    L1      ;  1  2   2
        GOTO    L1      ;  1  3   2
        GOTO    L1      ;  1  4   2
        GOTO    WHAT    ;  1  5   0
        GOTO    WHAT    ;  1  6   0
        GOTO    L1C     ;  1  7   1

        GOTO    WHAT    ;  2  0   0
        GOTO    L2B     ;  2  1   3
        GOTO    L2B     ;  2  2   3
        GOTO    WHAT    ;  2  3   0
        GOTO    WHAT    ;  2  4   0
        GOTO    L2A     ;  2  5   3
        GOTO    L2B     ;  2  6   3
        GOTO    L2C     ;  2  7   0

        GOTO    WHAT    ;  3  0   0
        GOTO    L3B     ;  3  1   4
        GOTO    L3B     ;  3  2   4
        GOTO    WHAT    ;  3  3   0
        GOTO    WHAT    ;  3  4   0
        GOTO    L3A     ;  3  5   4
        GOTO    L3B     ;  3  6   4
        GOTO    L3C     ;  3  7   0

L1
        MOVWF   CMD
        GOTO    ECHO
L1C
        CLRF    STATE
        GOTO    ECHO
L2A
        SWAPF   CURK,W
        ANDLW   0xF0
        MOVWF   DAT
        GOTO    ECHO
L2B
        SWAPF   CURK,W
        ANDLW   0x70
        ADDLW   0x90
        MOVWF   DAT
        GOTO    ECHO
L2C
        MOVF    CMD,W
        XORLW   8+3
        IFZ
        GOTO    WHAT
        IFSET   CMD,2
        GOTO    L1C
        MOVF    ADDRESS,W
        MOVWF   DAT
        CALL    OUTHEX
        CALL    OUTHEX
        GOTO    DOCMD
L3A
        MOVF    CURK,W
        ANDLW   0x0F
        IORWF   DAT,F
        GOTO    ECHO
L3B
        MOVF    CURK,W
        ANDLW   0x07
        ADDLW   0x09
        IORWF   DAT,F
        GOTO    ECHO
L3C
        SWAPF   DAT,F
L4C
        IFSET   CMD,2
        GOTO    CHANGE
DOCMD
        DECF    CMD,W
        ANDLW   0x03
        ADDWF   PCL,F
        GOTO    DUMP
        GOTO    EDIT
        GOTO    GORUN
        GOTO    STORE

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
        GOTO    L1C
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
ESDAT
        BSF     CMD,2
        MOVLW   8
        MOVWF   STATE
        GOTO    ECHO
STORE
        MOVF    DAT,W
        MOVWF   ADDRESS
        GOTO    ESDAT
CHANGE
        MOVF    ADDRESS,W
        MOVWF   FSR
        MOVF    DAT,W
        MOVWF   INDF
        INCF    ADDRESS,F
        GOTO    L1C
GORUN
        CLRF    STATE
        MOVLW   HIGH SUBS
        MOVWF   PCLATH
        MOVF    DAT,W
        CALL    EXECUTE
        CLRF    STATE
        GOTO    ISR_EXIT

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
        CALL    EMIT
        BCF     RCSTA,CREN
        MOVF    RCREG,W
        MOVF    RCREG,W
        BSF     RCSTA,CREN
        CLRF    STATE
        GOTO    ISR_EXIT

        END
