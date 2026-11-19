        LIST    F=INHX8M,R=DEC,P=16C54
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

DISPLAY EQU     07
TMP     EQU     08
IPV     EQU     08
I       EQU     09
ROW     EQU     10
KEY     EQU     11


TBST    EQU      12              ; TALKBACK INPUT STATE
RA1ST   EQU      13              ; REMOTE ADDRESS 1 STATE
RA2ST   EQU      14              ; REMOTE ADDRESS 2 STATE
RA3ST   EQU      15              ; REMOTE ADDRESS 3 STATE

KEYST   EQU      16              ; KEYSWITCH STATES

; ----------   PORTB BITS   ----------

KCOL1   EQU     5               ; KEYBOARD COLUMN 1
KCOL2   EQU     4               ; KEYBOARD COLUMN 2

TB      EQU     4               ; TALKBACK INPUTS
RA1     EQU     5               ; REMOTE ADDRESS 1 INPUT
RA2     EQU     6               ; REMOTE ADDRESS 2 INPUT
RA3     EQU     7               ; REMOTE ADDRESS 3 INPUT

; ----------   EQUATES   ----------

NROWS   EQU     6               ; NUMBER OF ROWS IN KEYBOARD
NKEYS   EQU     12              ; NUMBER OF KEYS IN KEYBOARD
NIP     EQU     4               ; NUMBER OF INPUTS

                                ; USE 4K7 AND 330pF FOR RC OSC
                                ; OS2 = 125kHz
DELAY1  EQU     12              ; 250 msec with OPTION $06
DELAY2  EQU     108             ; 9.5 msec with OPTION $02

                                ; PORTB DATA DIRECTION
PBDSKD  EQU     $30             ; PORTB SCAN KEYBOARD/DISPLAY
PBDIPSW EQU     $F0             ; PORTB READ INPUTS/SWITCHES

                                ; PORTB OUTPUTS FOR VARIOUS FUNCTIONS
DCOL1   EQU     64              ; TURN ON DISPLAY COLUMN 1
DCOL2   EQU     128             ; TURN ON DISPLAY COLUMN 2
KEYR1   EQU     128+64+2        ; FIRST KEYBOARD ROW

                                ; DECODER ADDRESSES
PBIP    EQU     128+64+8        ; TALKBACK AND REMOTE INPUTS
PBSW1   EQU     PBIP+1          ; SWITCH 1
PBSW2   EQU     PBIP+2          ; SWITCH 2
PBSW3   EQU     PBIP+3          ; SWITCH 3
PBNONE  EQU     $0F             ; DISABLE ALL BUFFERS BY SELECTING NONE

; ----------   NEXT STATE TABLE1   ----------

        ORG     $000
                        ; SET BIT 0 OF THE STATE TO INPUT
                        ; BEFORE CALLING NEXT1
KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1

NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
        ADDWF   PC

        RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
        RETLW   2
        RETLW   0
        RETLW   4
        RETLW   0
        RETLW   6
        RETLW   0
        RETLW   8       ; 4TH INPUT=1 SO SET KEYBIT

        RETLW   10
        RETLW   8       ; KEYBIT SET WHILE INPUT=1
        RETLW   12
        RETLW   8
        RETLW   14
        RETLW   8
        RETLW   0       ; 4TH INPUT=0 SO CLEAR KEYBIT
        RETLW   8

; ----------   KEY STATE LOCATION TABLE2   ----------

TRANS2  ANDLW   $0F
        ADDWF   PC

        RETLW   KEYST+11        ; UNUSED
        RETLW   KEYST+11        ; UNUSED
        RETLW   KEYST+11        ; UNUSED

        RETLW   KEYST+00
        RETLW   KEYST+02
        RETLW   KEYST+04
        RETLW   KEYST+06
        RETLW   KEYST+08
        RETLW   KEYST+10

        RETLW   KEYST+01
        RETLW   KEYST+03
        RETLW   KEYST+05
        RETLW   KEYST+07
        RETLW   KEYST+09
        RETLW   KEYST+11

        RETLW   KEYST+11        ; UNUSED

; ----------   DISPLAY TRASLATION TABLE3   ----------

TRANS3  ANDLW   $0F
        ADDWF   PC

        RETLW   DCOL2+7         ; UNUSED
        RETLW   DCOL2+7         ; UNUSED
        RETLW   DCOL2+7         ; UNUSED

        RETLW   DCOL1+2
        RETLW   DCOL1+3
        RETLW   DCOL1+4
        RETLW   DCOL1+5
        RETLW   DCOL1+6
        RETLW   DCOL1+7

        RETLW   DCOL2+2
        RETLW   DCOL2+3
        RETLW   DCOL2+4
        RETLW   DCOL2+5
        RETLW   DCOL2+6
        RETLW   DCOL2+7

        RETLW   DCOL2+7         ; UNUSED

; ----------   UPDATE KEYSTATE SUBROUTINE   ----------

UPDATE  MOVF    IND,W
        CALL    NEXT1
        MOVWF   IND
        INCF    FSR
        RETLW   0

; ----------   OUTPUT SUBROUTINE   ----------

OUTPUT  GOTO    $1FF
        INCF    KEY,W
        ANDLW   $0C
        BTFSS   STATUS,Z
        GOTO    OKAY
        MOVLW   14
        MOVWF   KEY
OKAY    MOVF    KEY,W
        MOVWF   PORTA
        RETLW   0

; ----------   WAIT FOR TIMEOUT SUBROUTINE   ----------

WAIT    MOVF    RTCC,W
        BTFSS   STATUS,Z
        GOTO    WAIT            ; WAIT FOR TIME OUT

        MOVLW   DELAY2
        MOVWF   RTCC            ; RESET COUNTER

        MOVF    KEY,W
        CALL    TRANS3
        MOVWF   DISPLAY

        MOVLW   PBNONE
        IORWF   PORTB

        MOVLW   PBDIPSW
        TRIS    PORTB

        RETLW   0


; ----------   OUTPUT SUBROUTINE   ----------

OUTPUT2
        INCF    KEY,W
        ANDLW   $0C
        BTFSS   STATUS,Z
        GOTO    OKAY2
        MOVLW   14
        MOVWF   KEY
OKAY2   MOVF    KEY,W
        XORLW   $0F
        MOVWF   PORTA
        RETLW   0


; ----------   INITIALIZATION CODE   ----------

INIT2   XORLW   $FF             ; UNPROGRAMED NOP

        CLRF    PORTA           ; INITIALIZE PORTA
        CLRW
        TRIS    PORTA

        MOVLW   DCOL1+2         ; INITIALIZE PORTB
        MOVWF   PORTB
        MOVLW   PBDSKD
        TRIS    PORTB

        MOVLW   TBST            ; BLANK INPUT AND KEYSWITCH STATES
        MOVWF   FSR
        MOVLW   NIP+NKEYS
        MOVWF   I
BLANK   CLRF    IND
        INCF    FSR
        DECFSZ  I
        GOTO    BLANK

        MOVLW   $06             ; RTCC = OSC2 / 128
        OPTION

        MOVLW   NKEYS
        MOVWF   I
        MOVLW   3
        MOVWF   KEY

SEQ1    MOVLW   DELAY1          ; RESET COUNTER
        MOVWF   RTCC

        MOVF    KEY,W
        CALL    TRANS3
        MOVWF   PORTB
        INCF    KEY

SEQ2    MOVF    RTCC,W
        BTFSS   STATUS,Z
        GOTO    SEQ2            ; WAIT FOR TIME OUT

        DECFSZ  I
        GOTO    SEQ1

        MOVLW   $02             ; RTCC = OSC2 / 8
        OPTION

        MOVLW   14
        MOVWF   KEY
        GOTO    SELECT

; ----------   SCAN INPUT AND KEYBOARD ROUTINE   ----------

SCAN2
        SWAPF   PORTB,W
        MOVWF   KEY

        MOVLW   PBIP
        MOVWF   PORTB
        NOP
SCAN1
        MOVF    PORTB,W
        MOVWF   IPV

        MOVLW   PBNONE
        IORWF   PORTB

        MOVLW   PBDSKD
        TRIS    PORTB

        MOVLW   KEYR1           ; TURN OFF LEDs AND MAKE FIRST ROW LOW
        MOVWF   PORTB
        MOVWF   ROW

        MOVLW   KEYST
        MOVWF   FSR
        MOVLW   NROWS-1
        MOVWF   I

SCANKB  INCF    ROW
        MOVF    ROW,W

        BTFSC   PORTB,KCOL1
        INCF    IND
        INCF    FSR
        BTFSC   PORTB,KCOL2
        INCF    IND
        MOVWF   PORTB

        DECF    FSR
        CALL    UPDATE
        CALL    UPDATE

        DECFSZ  I
        GOTO    SCANKB

        NOP
        MOVF    DISPLAY,W

        BTFSC   PORTB,KCOL1
        INCF    IND
        INCF    FSR
        BTFSC   PORTB,KCOL2
        INCF    IND
        MOVWF   PORTB           ; RESTORE DISPLAY
                                ; AFTER SCANNING KEYBOARD
        DECF    FSR
        CALL    UPDATE
        CALL    UPDATE

        MOVLW   TBST             ; SCAN INPUTS
        MOVWF   FSR

        BTFSC   IPV,TB
        INCF    TBST
        CALL    UPDATE

        BTFSC   IPV,RA1
        INCF    RA1ST
        CALL    UPDATE

        BTFSC   IPV,RA2
        INCF    RA2ST
        CALL    UPDATE

        BTFSC   IPV,RA3
        INCF    RA3ST
        CALL    UPDATE

        XORLW   $FF             ; UNPROGRAMED NOP

        BTFSC   TBST,KEYBIT
        GOTO    TALK
        BTFSC   RA1ST,KEYBIT
        GOTO    REMOTE1
        BTFSC   RA2ST,KEYBIT
        GOTO    REMOTE2
        BTFSC   RA3ST,KEYBIT
        GOTO    REMOTE3
        GOTO    SELECT

; ----------   TALK MODE   ----------

T1      CALL    WAIT
        MOVLW   PBIP
        MOVWF   PORTB
        GOTO    SCAN1
TALK    CALL    OUTPUT2
        GOTO    T1

; ----------   REMOTE1 MODE   ----------

R1      CALL    WAIT
        MOVLW   PBSW1
        MOVWF   PORTB
        GOTO    SCAN2
REMOTE1 CALL    OUTPUT2
        GOTO    R1

; ----------   REMOTE2 MODE   ----------

R2      CALL    WAIT
        MOVLW   PBSW2
        MOVWF   PORTB
        GOTO    SCAN2
REMOTE2 CALL    OUTPUT2
        GOTO    R2

; ----------   REMOTE3 MODE   ----------

R3      CALL    WAIT
        MOVLW   PBSW3
        MOVWF   PORTB
        GOTO    SCAN2
REMOTE3 CALL    OUTPUT2
        GOTO    R3

; ----------   SELECT MODE   ----------

GOTONE  MOVF    TMP,W
        MOVWF   KEY
HELD
NONE
        CALL    WAIT
        MOVLW   PBIP
        MOVWF   PORTB
        GOTO    SCAN1
SELECT
        CLRF    PORTA

        MOVF    KEY,W
        CALL    TRANS2
        MOVWF   FSR
        BTFSC   IND,KEYBIT
        GOTO    HELD            ; KEY NOT RELEASED YET

        MOVLW   14
        MOVWF   TMP
        MOVLW   NKEYS           ; GET HIGHEST PRIORITY KEY
        MOVWF   I

PRIO    MOVF    TMP,W
        CALL    TRANS2
        MOVWF   FSR
        BTFSC   IND,KEYBIT
        GOTO    GOTONE          ; FOUND HIGHEST PRIORITY KEY

        DECF    TMP
        DECFSZ  I
        GOTO    PRIO
        GOTO    NONE            ; NO KEYS PRESSED


        ORG     $163
INIT1   GOTO    INIT2
        NOP
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP 
        NOP
        NOP

        ORG     PIC54
RESET   GOTO    INIT1
        END
