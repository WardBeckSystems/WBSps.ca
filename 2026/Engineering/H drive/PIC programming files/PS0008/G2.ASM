
        LIST    F=INHX8M,R=DEC,P=16C54
        INCLUDE "\PIC\SRC\P16C5X.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   EQUATES   ----------

IPS1    EQU     08
IPS2    EQU     09
IPS3    EQU     10
IPS4    EQU     11
IPS5    EQU     12
IPS6    EQU     13

TEMP    EQU     12

; ----------   PORTB BITS   ----------

CH1P1   EQU     4               ; P1 INPUT CHANNEL 1
CH1P2   EQU     5               ; P2 INPUT
CH2P1   EQU     6               ; P1 INPUT CHANNEL 2
CH2P2   EQU     7               ; P2 INPUT
CH3P1   EQU     4               ; P1 INPUT CHANNEL 3
CH3P2   EQU     5               ; P2 INPUT

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

OUT2    ANDLW   0x3F
        ADDWF   PCL,F

        RETLW   0000B ;   . . . . . .    0   . . . .  . . . .  . . . .
        RETLW   0000B ;   . . . . . 1    1   . . . .  . . . 1  . . . .
        RETLW   0000B ;   . . . . 1 .    2   . . . .  . . 1 .  . . . .
        RETLW   0000B ;   . . . . 1 1    3   . . . .  . . 1 .  . . . .
        RETLW   0001B ;   . . . 1 . .    4   . . . 1  . . . .  . . . .
        RETLW   0101B ;   . . . 1 . 1    5   . 1 . 1  1 . . 1  . . . .
        RETLW   0001B ;   . . . 1 1 .    6   . . . 1  . . 1 .  . . . .
        RETLW   0001B ;   . . . 1 1 1    7   . . . 1  . . 1 .  . . . .
        RETLW   0010B ;   . . 1 . . .    8   . . 1 .  . . . .  . . . .
        RETLW   0010B ;   . . 1 . . 1    9   . . 1 .  . . . 1  . . . .
        RETLW   0110B ;   . . 1 . 1 .   10   . 1 1 .  1 . 1 .  . . . .
        RETLW   0110B ;   . . 1 . 1 1   11   . 1 1 .  1 . 1 .  . . . .
        RETLW   0010B ;   . . 1 1 . .   12   . . 1 .  . . . .  . . . .
        RETLW   0010B ;   . . 1 1 . 1   13   . . 1 .  . . . 1  . . . .
        RETLW   0110B ;   . . 1 1 1 .   14   . 1 1 .  1 . 1 .  . . . .
        RETLW   0110B ;   . . 1 1 1 1   15   . 1 1 .  1 . 1 .  . . . .
        RETLW   0000B ;   . 1 . . . .   16   . . . .  . . . .  . . . 1
        RETLW   0000B ;   . 1 . . . 1   17   . . . .  . 1 . 1  1 . . 1
        RETLW   0000B ;   . 1 . . 1 .   18   . . . .  . . 1 .  . . . 1
        RETLW   0000B ;   . 1 . . 1 1   19   . . . .  . . 1 .  . . . 1
        RETLW   1001B ;   . 1 . 1 . .   20   1 . . 1  . . . .  . 1 . 1
        RETLW   1101B ;   . 1 . 1 . 1   21   1 1 . 1  1 1 . 1  1 1 . 1
        RETLW   1001B ;   . 1 . 1 1 .   22   1 . . 1  . . 1 .  . 1 . 1
        RETLW   1001B ;   . 1 . 1 1 1   23   1 . . 1  . . 1 .  . 1 . 1
        RETLW   0010B ;   . 1 1 . . .   24   . . 1 .  . . . .  . . . 1
        RETLW   0010B ;   . 1 1 . . 1   25   . . 1 .  . 1 . 1  1 . . 1
        RETLW   0110B ;   . 1 1 . 1 .   26   . 1 1 .  1 . 1 .  . . . 1
        RETLW   0110B ;   . 1 1 . 1 1   27   . 1 1 .  1 . 1 .  . . . 1
        RETLW   0010B ;   . 1 1 1 . .   28   . . 1 .  . . . .  . . . 1
        RETLW   0010B ;   . 1 1 1 . 1   29   . . 1 .  . 1 . 1  1 . . 1
        RETLW   0110B ;   . 1 1 1 1 .   30   . 1 1 .  1 . 1 .  . . . 1
        RETLW   0110B ;   . 1 1 1 1 1   31   . 1 1 .  1 . 1 .  . . . 1
        RETLW   0000B ;   1 . . . . .   32   . . . .  . . . .  . . 1 .
        RETLW   0000B ;   1 . . . . 1   33   . . . .  . . . 1  . . 1 .
        RETLW   0000B ;   1 . . . 1 .   34   . . . .  . 1 1 .  1 . 1 .
        RETLW   0000B ;   1 . . . 1 1   35   . . . .  . 1 1 .  1 . 1 .
        RETLW   0001B ;   1 . . 1 . .   36   . . . 1  . . . .  . . 1 .
        RETLW   0101B ;   1 . . 1 . 1   37   . 1 . 1  1 . . 1  . . 1 .
        RETLW   0001B ;   1 . . 1 1 .   38   . . . 1  . 1 1 .  1 . 1 .
        RETLW   0001B ;   1 . . 1 1 1   39   . . . 1  . 1 1 .  1 . 1 .
        RETLW   1010B ;   1 . 1 . . .   40   1 . 1 .  . . . .  . 1 1 .
        RETLW   1010B ;   1 . 1 . . 1   41   1 . 1 .  . . . 1  . 1 1 .
        RETLW   1110B ;   1 . 1 . 1 .   42   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1110B ;   1 . 1 . 1 1   43   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1010B ;   1 . 1 1 . .   44   1 . 1 .  . . . .  . 1 1 .
        RETLW   1010B ;   1 . 1 1 . 1   45   1 . 1 .  . . . 1  . 1 1 .
        RETLW   1110B ;   1 . 1 1 1 .   46   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1110B ;   1 . 1 1 1 1   47   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   0000B ;   1 1 . . . .   48   . . . .  . . . .  . . 1 .
        RETLW   0000B ;   1 1 . . . 1   49   . . . .  . . . 1  . . 1 .
        RETLW   0000B ;   1 1 . . 1 .   50   . . . .  . 1 1 .  1 . 1 .
        RETLW   0000B ;   1 1 . . 1 1   51   . . . .  . 1 1 .  1 . 1 .
        RETLW   0001B ;   1 1 . 1 . .   52   . . . 1  . . . .  . . 1 .
        RETLW   0101B ;   1 1 . 1 . 1   53   . 1 . 1  1 . . 1  . . 1 .
        RETLW   0001B ;   1 1 . 1 1 .   54   . . . 1  . 1 1 .  1 . 1 .
        RETLW   0001B ;   1 1 . 1 1 1   55   . . . 1  . 1 1 .  1 . 1 .
        RETLW   1010B ;   1 1 1 . . .   56   1 . 1 .  . . . .  . 1 1 .
        RETLW   1010B ;   1 1 1 . . 1   57   1 . 1 .  . . . 1  . 1 1 .
        RETLW   1110B ;   1 1 1 . 1 .   58   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1110B ;   1 1 1 . 1 1   59   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1010B ;   1 1 1 1 . .   60   1 . 1 .  . . . .  . 1 1 .
        RETLW   1010B ;   1 1 1 1 . 1   61   1 . 1 .  . . . 1  . 1 1 .
        RETLW   1110B ;   1 1 1 1 1 .   62   1 1 1 .  1 1 1 .  1 1 1 .
        RETLW   1110B ;   1 1 1 1 1 1   63   1 1 1 .  1 1 1 .  1 1 1 .

; ----------   MAIN CODE   ----------

        ORG     0x1B5
INIT    RES     1

        CLRF    IPS1
        CLRF    IPS2
        CLRF    IPS3
        CLRF    IPS4
        CLRF    IPS5
        CLRF    IPS6

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

        BCF     PORTB,3
        NOP
        NOP

        IFSET   PORTB,CH3P1
        INCF    IPS5,F
        MOVF    IPS5,W
        CALL    NEXT1
        MOVWF   IPS5

        IFSET   PORTB,CH3P2
        INCF    IPS6,F
        MOVF    IPS6,W
        CALL    NEXT1
        MOVWF   IPS6

        CLRF    TEMP
        IFSET   IPS5,KEYBIT
        BSF     TEMP,5
        IFSET   IPS6,KEYBIT
        BSF     TEMP,4
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
