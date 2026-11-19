
        LIST    F=INHX8M,R=DEC,P=16C54
        INCLUDE "\PIC\SRC\P16C5X.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   EQUATES   ----------

IPS1    EQU     08
IPS2    EQU     09
IPS3    EQU     10
IPS4    EQU     11

TEMP    EQU     12

; ----------   PORTB BITS   ----------

CH1P1   EQU     4               ; P1 INPUT CHANNEL 1
CH1P2   EQU     5               ; P2 INPUT
CH2P1   EQU     6               ; P1 INPUT CHANNEL 2
CH2P2   EQU     7               ; P2 INPUT

; ----------   EQUATES   ----------

                                ; USE 4K7 AND 330pF FOR RC OSC
                                ; OS2 = 125kHz
DELAY   EQU     101             ; 5 msec with OPTION 0x01

                                ; PORTB DATA DIRECTION
PBDSKD  EQU     0x30             ; PORTB SCAN KEYBOARD/DISPLAY
PBDIPSW EQU     0xF0             ; PORTB READ INPUTS/SWITCHES

                                ; PORTB OUTPUTS FOR VARIOUS FUNCTIONS
DCOL1   EQU     64              ; TURN ON DISPLAY COLUMN 1
DCOL2   EQU     128             ; TURN ON DISPLAY COLUMN 2
KEYR1   EQU     128+64+2        ; FIRST KEYBOARD ROW

                                ; DECODER ADDRESSES
PBIP    EQU     128+64+8        ; TALKBACK AND REMOTE INPUTS
PBSW1   EQU     PBIP+1          ; SWITCH 1
PBSW2   EQU     PBIP+2          ; SWITCH 2
PBSW3   EQU     PBIP+3          ; SWITCH 3
PBNONE  EQU     0x0F             ; DISABLE ALL BUFFERS BY SELECTING NONE

        ORG     0x000

; ----------   NEXT STATE TABLE1   ----------
                        ; SET BIT 0 OF THE STATE TO INPUT
                        ; BEFORE CALLING NEXT1
KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1
KCH     EQU     4

NEXT1   ANDLW   0x0F     ; DEBOUNCE INPUT STATE MACHINE
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

; ----------   OUTPUT TABLE2   ----------

OUT2    ANDLW   0x0F
        ADDWF   PCL,F

        RETLW   0000B
        RETLW   0000B
        RETLW   0000B
        RETLW   0000B

        RETLW   0001B
        RETLW   0101B
        RETLW   0001B
        RETLW   0001B

        RETLW   0010B
        RETLW   0010B
        RETLW   0110B
        RETLW   0110B

        RETLW   0010B
        RETLW   0010B
        RETLW   0110B
        RETLW   0110B

; ----------   MAIN CODE   ----------

        ORG     0x1C8
INIT    XORLW   0xFF             ; UNPROGRAMED NOP

        CLRF    IPS1
        CLRF    IPS2
        CLRF    IPS3
        CLRF    IPS4

        MOVLW   0x0F             ; INITIALIZE PORTA
        MOVWF   PORTA
TOP     CLRW
        TRIS    PORTA

        MOVLW   PBIP            ; INITIALIZE PORTB
        MOVWF   PORTB
        MOVLW   PBDIPSW
        TRIS    PORTB

        MOVLW   0x01             ; RTCC = OSC2 / 4
        OPTION

WAIT    MOVF    TMR0,W
        IFNZ
        GOTO    WAIT            ; WAIT FOR TIME OUT

        MOVLW   DELAY
        MOVWF   TMR0            ; RESET COUNTER

        NOP

        IFSET   PORTB,CH1P1
        INCF    IPS1,F
        MOVF    IPS1,W
        CALL    NEXT1
        MOVWF   IPS1

        IFSET   PORTB,CH1P2
        INCF    IPS2,F
        MOVF    IPS2,W
        CALL    NEXT1
        MOVWF   IPS2

        IFSET   PORTB,CH2P1
        INCF    IPS3,F
        MOVF    IPS3,W
        CALL    NEXT1
        MOVWF   IPS3

        IFSET   PORTB,CH2P2
        INCF    IPS4,F
        MOVF    IPS4,W
        CALL    NEXT1
        MOVWF   IPS4

        CLRF    TEMP
        IFSET   IPS1,KEYBIT
        BSF     TEMP,3
        IFSET   IPS2,KEYBIT
        BSF     TEMP,2
        IFSET   IPS3,KEYBIT
        BSF     TEMP,1
        IFSET   IPS4,KEYBIT
        BSF     TEMP,0
        MOVF    TEMP,W
        CALL    OUT2
        XORLW   0xFF
        MOVWF   PORTA
        GOTO    TOP

        ORG     0x1FF
RESET   GOTO    INIT
        END
