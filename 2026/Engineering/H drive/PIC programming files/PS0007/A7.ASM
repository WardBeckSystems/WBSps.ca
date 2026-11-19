
        LIST    F=INHX8M,R=DEC,P=16C54
        INCLUDE "\PIC\SRC\P16C5X.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

        ORG     $08

OUT1    RES     1
OUT2    RES     1
TXSR1   RES     1
TXSR2   RES     1
I       RES     1
J       RES     1
TEMP    RES     1

        ORG     $10

KTAB    RES     16

; ----------   PORTA BITS   ----------

CLK     EQU     0
LOAD    EQU     1
DATA2   EQU     2
DATA1   EQU     3

; ----------   PORTB BITS   ----------

COL1    EQU     0
COL2    EQU     1
COL3    EQU     2
COL4    EQU     3
ROW1    EQU     4
ROW2    EQU     5
ROW3    EQU     6
ROW4    EQU     7

; ----------   EQUATES   ----------

NKEYS   EQU     16              ; NUMBER OF KEYS

                                ; USE 39K AND 22pF FOR RC OSC
                                ; OS2 = 180kHz
DELAY1  EQU     90              ; 250 msec with OPTION $07
DELAY2  EQU     38              ;   5 msec with OPTION $00

; ----------   CODE   ----------

        ORG     0

; ----------   NEXT STATE TABLE1   ----------

; DEBOUNCE INPUT STATE MACHINE
; BIT 0 INPUT - ACTIVE HIGH
; BIT 1 STATE
; BIT 2 STATE
; BIT 3 OUTPUT - SET AFTER INPUT=1 FOUR CONSECUTIVE TIMES
; BIT 4 OUTPUT - SET AFTER BIT 3 TOGGLES
; BIT 5 OUTPUT - SET WHEN BOTH BITS 3 & 4 ARE SET

KEYBIT  EQU     3
KCH     EQU     4
PRESS   EQU     5

NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
        ADDWF   PCL,F

        RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
        RETLW   2
        RETLW   0
        RETLW   4
        RETLW   0
        RETLW   6
        RETLW   0
        RETLW   8+16+32 ; 4TH INPUT=1 SO SET KEYBIT

        RETLW   10
        RETLW   8       ; KEYBIT SET WHILE INPUT=1
        RETLW   12
        RETLW   8
        RETLW   14
        RETLW   8
        RETLW   0+16    ; 4TH INPUT=0 SO CLEAR KEYBIT
        RETLW   8

; ----------   SEND TO LEDS   ----------

SEND    COMF    OUT1,W
        MOVWF   TXSR1
        COMF    OUT2,W
        MOVWF   TXSR2

        MOVLW   8
        MOVWF   J
        BCF     PORTA,LOAD
SEND_L1
        BCF     PORTA,CLK

        IFSET   TXSR1,7
        BSF     PORTA,DATA1
        IFCLR   TXSR1,7
        BCF     PORTA,DATA1

        IFSET   TXSR2,7
        BSF     PORTA,DATA2
        IFCLR   TXSR2,7
        BCF     PORTA,DATA2

        RLF     TXSR1,F
        RLF     TXSR2,F

        BSF     PORTA,CLK
        DECFSZ  J,F
        GOTO    SEND_L1

        BSF     PORTA,LOAD
        RETLW   0

; ----------   CLEAR STATES   ----------

CLEAR   MOVLW   KTAB
        MOVWF   FSR
CLEAR_L1
        CLRF    INDF
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    CLEAR_L1
        RETLW   0

; ----------   INITIALIZATION CODE   ----------

INIT
        XORLW   $FF             ; UNPROGRAMED NOP

        CLRW
        MOVWF   PORTA           ; INITIALIZE PORTA
        TRIS    PORTA

        MOVLW   $F0             ; INITIALIZE PORTB
        MOVWF   PORTB
        TRIS    PORTB

        CALL    CLEAR           ; CLEAR KEYSWITCH STATES

; ----------   DISCO DUCK   ----------

        MOVLW   $07             ; TMR0 = OSC2 / 256
        OPTION

        CLRF    OUT1
        BSF     OUT1,7
        CLRF    OUT2
SEQ1
        MOVLW   DELAY1          ; RESET COUNTER
        MOVWF   TMR0
        CALL    SEND
SEQ2
        MOVF    TMR0,W
        IFNZ
        GOTO    SEQ2            ; WAIT FOR TIME OUT

        RRF     OUT1,F
        BCF     OUT1,7
        RRF     OUT2,F
        IFCC
        GOTO    SEQ1

        MOVLW   $00             ; TMR0 = OSC2 / 2
        OPTION
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        CLRF    OUT1
        CLRF    OUT2

; ----------   MAIN CODE   ----------

CHANGE
        CALL    SEND
MAIN
        BSF     PORTA,CLK

        MOVLW   $FE
        MOVWF   PORTB
M_L1
        IFCLR   TMR0,7          ; WAIT UNTIL TMR0 > 127
        GOTO    M_L1
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        BCF     PORTA,CLK

        IFCLR   PORTB,4
        INCF    0+KTAB,F
        IFCLR   PORTB,5
        INCF    8+KTAB,F
        IFCLR   PORTB,6
        INCF    1+KTAB,F
        IFCLR   PORTB,7
        INCF    9+KTAB,F

        MOVLW   $FD
        MOVWF   PORTB
M_L2
        IFCLR   TMR0,7          ; WAIT UNTIL TMR0 > 127
        GOTO    M_L2
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        IFCLR   PORTB,4
        INCF    2+KTAB,F
        IFCLR   PORTB,5
        INCF    10+KTAB,F
        IFCLR   PORTB,6
        INCF    3+KTAB,F
        IFCLR   PORTB,7
        INCF    11+KTAB,F

        MOVLW   $FB
        MOVWF   PORTB
M_L3
        IFCLR   TMR0,7          ; WAIT UNTIL TMR0 > 127
        GOTO    M_L3
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        IFCLR   PORTB,4
        INCF    4+KTAB,F
        IFCLR   PORTB,5
        INCF    12+KTAB,F
        IFCLR   PORTB,6
        INCF    5+KTAB,F
        IFCLR   PORTB,7
        INCF    13+KTAB,F

        MOVLW   $F7
        MOVWF   PORTB
M_L4
        IFCLR   TMR0,7          ; WAIT UNTIL TMR0 > 127
        GOTO    M_L4
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        IFCLR   PORTB,4
        INCF    6+KTAB,F
        IFCLR   PORTB,5
        INCF    14+KTAB,F
        IFCLR   PORTB,6
        INCF    7+KTAB,F
        IFCLR   PORTB,7
        INCF    15+KTAB,F

        CLRF    PORTB

        MOVLW   KTAB
        MOVWF   FSR
        CLRF    TEMP
CHECK
        IFSET   INDF,0
        INCF    TEMP,F
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    CHECK

        MOVLW   2
        SUBWF   TEMP,W
        IFCC
        GOTO    VALID
        CALL    CLEAR
        GOTO    MAIN
VALID
        MOVLW   KTAB
        MOVWF   FSR
        MOVLW   $80
        MOVWF   TEMP
        CLRF    I
UPDATE
        MOVF    INDF,W
        CALL    NEXT1
        MOVWF   INDF
        IFCLR   INDF,PRESS
        GOTO    UP_1
        MOVF    TEMP,W
        XORWF   OUT1,F
        INCF    I,F
UP_1    INCF    FSR,F

        MOVF    INDF,W
        CALL    NEXT1
        MOVWF   INDF
        IFCLR   INDF,PRESS
        GOTO    UP_2
        MOVF    TEMP,W
        XORWF   OUT2,F
        INCF    I,F
UP_2    INCF    FSR,F

        RRF     TEMP,F
        BCF     TEMP,7
        IFCC
        GOTO    UPDATE

        MOVF    I,W
        IFNZ
        GOTO    CHANGE

        MOVLW   KTAB
        MOVWF   FSR
CHECK2
        MOVF    INDF,W
        IFNZ
        GOTO    MAIN
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    CHECK2

IDLE
        CLRF    PORTB
        BSF     PORTA,CLK
IDLE_L1
        IFCLR   TMR0,7          ; WAIT UNTIL TMR0 > 127
        GOTO    IDLE_L1
        MOVLW   DELAY2
        MOVWF   TMR0            ; RESET TIMER

        BCF     PORTA,CLK

        COMF    PORTB,W
        ANDLW   $F0
        IFZ
        GOTO    IDLE
        GOTO    MAIN

        ORG     $1FF
RESET   GOTO    INIT
        END
