        LIST    F=INHX8M,R=DEC,P=16C57
; ----------   PIC16C5X HEADER   ----------

W       EQU     0

; RESET ADDRESSES

PIC54   EQU     $1FF
PIC55   EQU     $1FF
PIC56   EQU     $3FF
PIC57   EQU     $7FF

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

; ----------   END HEADER   ----------

TXSR    EQU     08      ; TX SHIFT REGISTER
I       EQU     09      ; INDEX
J       EQU     10      ; BIT TIME DELAY COUNTER

KS      EQU     16      ; KEY STATE TABLE

; ----------   PORTA BITS   ----------

ATX     EQU     0       ; REMEMBER THIS IS DCE
ARX     EQU     1
ARTS    EQU     2
ACTS    EQU     3

; ----------   PORTB BITS   ----------

ROW1    EQU     0
ROW2    EQU     1
ROW3    EQU     2
ROW4    EQU     3

COL1    EQU     4
COL2    EQU     5
COL3    EQU     6
COL4    EQU     7               ; UNUSED

; ----------   PORTC BITS   ----------


; ----------   EQUATES   ----------

                        ; USE 4.00 MHz CRYSTAL AND TWO 15pF CAPS
                        ; OS2 = 1 MHz
DELAY   EQU     100     ; 5 msec with OPTION $04 ( RTCC=OS2/32 )
BAUD1B  EQU     33      ; 1 BIT DELAY FOR 4800 BAUD

; ----------   MAIN CODE   ----------

MAIN1   CALL    SCAN
        MOVF    RETC,W
        ANDLW   $07
        ADDWF   PC
        GOTO    SCANR1
        GOTO    SCANR2
        GOTO    SCANR3
        GOTO    NOTHING
        GOTO    DISPLAY
        GOTO    DISPLAY
        GOTO    DISPLAY
        GOTO    DISPLAY

; ----------   NEXT STATE TABLE1   ----------
                        ; SET BIT 0 OF THE STATE TO INPUT
                        ; BEFORE CALLING NEXT1
KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1
KCH     EQU     4

NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
        ADDWF   PC

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

; ----------   INITIALIZATION CODE   ----------

        ORG     $100
INIT    XORLW   $FF             ; UNPROGRAMED NOP

        MOVLW   $0F
        MOVWF   PORTA           ; INITIALIZE PORTA
        MOVLW   $05
        TRIS    PORTA

        MOVLW   $FE             ; INITIALIZE PORTB
        MOVWF   PORTB
        MOVLW   $F0
        TRIS    PORTB

        MOVLW   $FF
        MOVWF   PORTC           ; INITIALIZE PORTC
        TRIS    PORTC

        MOVLW   $04             ; RTCC = OSC2 / 32
        OPTION

        MOVLW   DELAY           ; RESET COUNTER
        MOVWF   RTCC

        BSF     PORTA,CLOAD1

        CLRF    KS1
        CLRF    KS2
        CLRF    STATE2

        CLRF    D3
        CLRF    D2
        CLRF    D1
        CLRF    D0
        CLRF    LEVEL

        CLRF    MKON
        CLRF    MKOFF
        CLRF    KP6
        CLRF    KM6
        CLRF    KOFF
        CLRF    KPAH
        CLRF    KPAM
        CLRF    KPAL

        MOVLW   4
        MOVWF   RETC
        MOVLW   4
        MOVWF   CNT
        MOVLW   5
        MOVWF   TMR
        MOVLW   10
        MOVWF   DEL
        GOTO    MAIN1

; ----------   SCANR1   ----------

SCANR1
        BTFSS   PORTB,COL1
        INCF    MKON
        MOVF    MKON,W
        CALL    NEXT1
        MOVWF   MKON

        BTFSS   PORTB,COL2
        INCF    KP6
        MOVF    KP6,W
        CALL    NEXT1
        MOVWF   KP6

        BTFSS   PORTB,COL3
        INCF    KPAH
        MOVF    KPAH,W
        CALL    NEXT1
        MOVWF   KPAH

        BTFSC   MKON,KEYBIT
        BCF     PORTA,CMUTE
        BTFSC   KP6,KEYBIT
        BSF     PORTC,GAIN6

        BTFSS   KPAH,KCH
        GOTO    SKR1
        BTFSS   KPAH,KEYBIT
        GOTO    SKR1
        BTFSC   RETC,TMRF
        GOTO    SKR1
        BCF     PORTC,HIGH
        BSF     PORTC,MID
        BSF     PORTC,RELAYC
        BSF     RETC,TMRF

SKR1    MOVLW   $FD
        MOVWF   PORTB
        MOVLW   $FC
        ANDWF   RETC
        MOVLW   $01
        IORWF   RETC
        GOTO    MAIN1

; ----------   SCANR2   ----------

SCANR2
        BTFSS   PORTB,COL1
        INCF    MKOFF
        MOVF    MKOFF,W
        CALL    NEXT1
        MOVWF   MKOFF

        BTFSS   PORTB,COL2
        INCF    KM6
        MOVF    KM6,W
        CALL    NEXT1
        MOVWF   KM6

        BTFSS   PORTB,COL3
        INCF    KPAM
        MOVF    KPAM,W
        CALL    NEXT1
        MOVWF   KPAM

        BTFSC   MKOFF,KEYBIT
        BSF     PORTA,CMUTE
        BTFSC   KM6,KEYBIT
        BCF     PORTC,GAIN6

        BTFSS   KPAM,KCH
        GOTO    SKR2
        BTFSS   KPAM,KEYBIT
        GOTO    SKR2
        BTFSC   RETC,TMRF
        GOTO    SKR2
        BSF     PORTC,HIGH
        BCF     PORTC,MID
        BSF     PORTC,RELAYC
        BSF     RETC,TMRF

SKR2    MOVLW   $FB
        MOVWF   PORTB
        MOVLW   $FC
        ANDWF   RETC
        MOVLW   $02
        IORWF   RETC
        GOTO    MAIN1

; ----------   SCANR3   ----------

SCANR3
        BTFSS   PORTB,COL2
        INCF    KOFF
        MOVF    KOFF,W
        CALL    NEXT1
        MOVWF   KOFF

        BTFSS   PORTB,COL3
        INCF    KPAL
        MOVF    KPAL,W
        CALL    NEXT1
        MOVWF   KPAL

        BTFSS   KOFF,KCH
        GOTO    SKR31
        BTFSS   KOFF,KEYBIT
        GOTO    SKR31
        BTFSC   RETC,TMRF
        GOTO    SKR31
        BSF     PORTC,HIGH
        BSF     PORTC,MID
        BSF     PORTC,RELAYC
        BSF     RETC,TMRF
        GOTO    SKR32

SKR31   BTFSS   KPAL,KCH
        GOTO    SKR32
        BTFSS   KPAL,KEYBIT
        GOTO    SKR32
        BTFSC   RETC,TMRF
        GOTO    SKR32
        BSF     PORTC,HIGH
        BSF     PORTC,MID
        BSF     PORTC,RELAYS
        BSF     RETC,TMRF

SKR32   MOVLW   $F7
        MOVWF   PORTB
        MOVLW   $FC
        ANDWF   RETC
        MOVLW   $03
        IORWF   RETC
        GOTO    MAIN1

; ----------   NOTHING   ----------

NOTHING MOVLW   $FE
        MOVWF   PORTB
        MOVLW   $FC
        ANDWF   RETC
        MOVLW   $00
        IORWF   RETC
        GOTO    MAIN1

; ----------   SCAN SUBROUTINE  ----------

SCAN    MOVF    RTCC,W
        BTFSS   STATUS,Z
        GOTO    SCAN            ; WAIT FOR TIME OUT

        MOVLW   DELAY
        MOVWF   RTCC            ; RESET COUNTER

        BTFSC   PORTC,0
        INCF    KS1
        MOVF    KS1,W
        CALL    NEXT1
        MOVWF   KS1


; ----------   TX SUBROUTINE   ----------

TX      MOVWF   TXSR
        MOVLW   8
        MOVWF   I
        BCF     PORTA,ARX       ; START BIT
TXL     CALL    DELAY1B         ; DELAY 1 BIT TIME
        BTFSC   TXSR,0
        BSF     PORTA,ARX
        BTFSS   TXSR,0
        BCF     PORTA,ARX
        RRF     TXSR
        DECFSZ  I
        GOTO    TXL
        CALL    DELAY1B
        BSF     PORTA,ARX       ; STOP BIT
        CALL    DELAY1B
        RETLW   0

DELAY1B MOVLW   BAUD1B
        MOVWF   J
DLYL    NOP
        NOP
        NOP
        DECFSZ  J
        GOTO    DLYL
        RETLW   0


        ORG     PIC57
RESET   GOTO    INIT
        END
