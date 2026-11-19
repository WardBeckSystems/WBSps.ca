        LIST    F=INHX8M,R=DEC,P=16C54
        INCLUDE "\PIC\SRC\P16C5X.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

        ORG     $08

KTAB    RES     16
OUT1    RES     1
OUT2    RES     1
TXSR1   RES     1
TXSR2   RES     1
I       RES     1
COUNT   RES     1
NIDLE   RES     1

; ----------   PORTA BITS   ----------

CLK     EQU     0
LOAD    EQU     1
DATA1   EQU     2
DATA2   EQU     3

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
DELAY1  EQU     12              ; 250 msec with OPTION $06
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

KEYBIT  EQU     3
KCH     EQU     4

NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
        ADDWF   PCL,F

        RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
        RETLW   2
        RETLW   0
        RETLW   4
        RETLW   0
        RETLW   6
        RETLW   0
        RETLW   8+16    ; 4TH INPUT=1 SO SET KEYBIT

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
        MOVWF   I
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
        DECFSZ  I,F
        GOTO    SEND_L1

        BSF     PORTA,LOAD
        RETLW   0

; ----------   INITIALIZATION CODE   ----------

        ORG     $100
INIT    XORLW   $FF             ; UNPROGRAMED NOP

        CLRW
        MOVWF   PORTA           ; INITIALIZE PORTA
        TRIS    PORTA

        MOVLW   $F0             ; INITIALIZE PORTB
        MOVWF   PORTB
        TRIS    PORTB

        CLRF    OUT1
        CLRF    OUT2
        CALL    SEND

        MOVLW   KTAB            ; CLEAR KEYSWITCH STATES
        MOVWF   FSR
        MOVLW   NKEYS
        MOVWF   I
BLANK
        CLRF    INDF
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    BLANK

        MOVLW   $00             ; TMR0 = OSC2 / 2
        OPTION

; ----------   MAIN CODE   ----------

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

        MOVLW   KTAB
        MOVWF   FSR
        MOVLW   NKEYS
        MOVWF   I
        CLRF    COUNT
        CLRF    NIDLE
CHECK
        IFSET   INDF,0
        INCF    COUNT,F
        MOVF    INDF,W
        ANDLW   $07
        IFNZ
        INCF    NIDLE,F
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    CHECK

        MOVF    NIDLE,W
        IFZ
        GOTO    IDLE
        MOVLW   3
        SUBWF   COUNT,W
        IFCC
        GOTO    VALID

        MOVLW   KTAB
        MOVWF   FSR
        MOVLW   NKEYS
        MOVWF   I
        MOVLW   $08
INVALID
        ANDWF   INDF,F
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    INVALID
        GOTO    MAIN

VALID
        MOVLW   KTAB
        MOVWF   FSR
        MOVLW   NKEYS
        MOVWF   I
UPDATE
        MOVF    INDF,W
        CALL    NEXT1
        MOVWF   INDF
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    UPDATE

        MOVLW   KTAB
        MOVWF   FSR
        MOVLW   8
        MOVWF   I
        CLRF    OUT1
        CLRF    OUT2
        BCF     STATUS,C
SETOUT
        RLF     OUT1,F          ; CARRY MUST ALWAYS BE CLEAR
        RLF     OUT2,F          ; IN THIS LOOP
        IFSET   INDF,KEYBIT
        BSF     OUT1,0
        INCF    FSR,F
        IFSET   INDF,KEYBIT
        BSF     OUT2,0
        INCF    FSR,F
        DECFSZ  I,F
        GOTO    SETOUT
        CALL    SEND
        GOTO    MAIN

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
