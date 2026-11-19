        LIST    F=INHX8M,R=DEC,P=16C54
        INCLUDE "HEADER.ASM"

IF_RUN  MACRO   TMR     ; IF TIMER RUNNING
        IFCLR   TMR,7
        ENDM

IF_STP  MACRO   TMR     ; IF TIMER STOPPED
        IFSET   TMR,7
        ENDM

IF_NEG  MACRO   TMR     ; IF TIMER NEGATIVE
        IFSET   TMR,7
        ENDM

        ORG     08

DBSSW   RES     1
ONSW    RES     1
OFFSW   RES     1
AUTOSW  RES     1

GPI1    RES     1
GPI2    RES     1
MODE    RES     1
ONOFF   RES     1

OLD     RES     1
TMRON0  RES     1
TMRON1  RES     1
TMROFF0 RES     1
TMROFF1 RES     1
TMRDBS0 RES     1
TMRDBS1 RES     1
TMRDBS2 RES     1
TMRHLF0 RES     1
TMRHLF1 RES     1
TMRHLF2 RES     1

; ----------   PORTB BITS FROM U4A   ----------

DBS_I   EQU     4               ; ACTIVE HIGH INPUT
ON_I    EQU     5               ; ACTIVE HIGH INPUT
OFF_I   EQU     6               ; ACTIVE HIGH INPUT
AUTO_I  EQU     7               ; ACTIVE HIGH INPUT

; ----------   PORTB BITS TO/FROM U6A   ----------

GPI1_I  EQU     4               ; ACTIVE HIGH INPUT
GPI2_I  EQU     5               ; ACTIVE HIGH INPUT
ON_O    EQU     6               ; ACTIVE HIGH OUTPUT
OFF_O   EQU     7               ; ACTIVE HIGH OUTPUT

; ----------   PORTA BITS   ----------

LOGO_O  EQU     0               ; ACTIVE LOW OUTPUT
A1      EQU     1               ; UNUSED OUTPUT
AUTO_O  EQU     2               ; ACTIVE HIGH OUTPUT
DBS_O   EQU     3               ; ACTIVE LOW OUTPUT

; ----------   EQUATES   ----------
                                ; PORTB DATA DIRECTION
PBDD_1  EQU     $30             ; PORTB READ GPI / OUTPUT ON,OFF
PBDD_2  EQU     $F0             ; PORTB READ INPUTS/SWITCHES

                                ; DECODER ADDRESSES
PBIP    EQU     $08             ; INPUTS
PBSW1   EQU     PBIP+1          ; SWITCH 1
PBSW2   EQU     PBIP+2          ; SWITCH 2
PBSW3   EQU     PBIP+3          ; SWITCH 3
PBNONE  EQU     $0F             ; DISABLE ALL BUFFERS BY SELECTING NONE

                                ; USE 4K64 AND 330pF FOR RC OSC
DBS0    EQU     92              ; OS2 = 128kHz
DBS1    EQU     11              ; 11*128+92=1500 msec
HALF0   EQU     116
HALF1   EQU     3               ; 3*128+116=500 msec

AUTOBIT EQU     3

        ORG     $000

; ----------   NEXT STATE TABLE1   ----------
                        ; SET BIT 0 OF THE STATE TO INPUT
                        ; BEFORE CALLING NEXT1
KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1
KPRESS  EQU     4       ; BIT TEST FOR HIGH PULSE
KREL    EQU     5       ; BIT TEST FOR LOW PULSE

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
        RETLW   0+32    ; 4TH INPUT=0 SO CLEAR KEYBIT
        RETLW   8

; ----------   DBS DELAY TABLES 3 & 4   ----------

DBSDLY0 ANDLW   $0F
        ADDWF   PC
        RETLW    48     ; 1.2 seconds
        RETLW    76     ; 1.1
        RETLW   104     ; 1.0
        RETLW     4     ; 0.9
        RETLW    32     ; 0.8
        RETLW    60     ; 0.7
        RETLW    88     ; 0.6
        RETLW   116     ; 0.5
        RETLW    16     ; 0.4
        RETLW    44     ; 0.3
        RETLW    72     ; 0.2
        RETLW   100     ; 0.1
        RETLW     0     ; 0.0
        RETLW   0
        RETLW   0
        RETLW   0

DBSDLY1 ANDLW   $0F
        ADDWF   PC
        RETLW     9     ; 1.2 seconds
        RETLW     8     ; 1.1
        RETLW     7     ; 1.0
        RETLW     7     ; 0.9
        RETLW     6     ; 0.8
        RETLW     5     ; 0.7
        RETLW     4     ; 0.6
        RETLW     3     ; 0.5
        RETLW     3     ; 0.4
        RETLW     2     ; 0.3
        RETLW     1     ; 0.2
        RETLW     0     ; 0.1
        RETLW     0     ; 0.0
        RETLW   0
        RETLW   0
        RETLW   0

; ----------   LOGO ON AND OFF DELAY TABLES 5 & 6   ----------

LOGDLY0 ANDLW   $0F
        ADDWF   PC
        RETLW   129     ; 16 SECONDS
        RETLW   153     ; 15
        RETLW   177     ; 14
        RETLW   201     ; 13
        RETLW   225     ; 12
        RETLW   249     ; 11
        RETLW    17     ; 10
        RETLW    41     ; 9
        RETLW    65     ; 8
        RETLW    89     ; 7
        RETLW   113     ; 6
        RETLW   137     ; 5
        RETLW   161     ; 4
        RETLW   185     ; 3
        RETLW   209     ; 2
        RETLW   233     ; 1
  
LOGDLY1 ANDLW   $0F
        ADDWF   PC
        RETLW    62     ; 16 SECONDS
        RETLW    58     ; 15
        RETLW    54     ; 14
        RETLW    50     ; 13
        RETLW    46     ; 12
        RETLW    42     ; 11
        RETLW    39     ; 10
        RETLW    35     ; 9
        RETLW    31     ; 8
        RETLW    27     ; 7
        RETLW    23     ; 6
        RETLW    19     ; 5
        RETLW    15     ; 4
        RETLW    11     ; 3
        RETLW     7     ; 2
        RETLW     3     ; 1

; ----------   TEST GPI   ----------

TESTGPI

WAIT    MOVF    OLD,W
        SUBWF   RTCC,W
        IFZ
        GOTO    WAIT            ; WAIT FOR 1 msec TIMEOUT

        MOVF    RTCC,W          ; UPDATE OLD
        MOVWF   OLD

        IF_STP  TMRON1          ; CHECK IF ON TIMER IS ACTIVE.
        GOTO    SK1
        DECF    TMRON0          ; DEC LOW BYTE OF ON TIMER.
        IFZ
        DECF    TMRON1          ; DEC HIGH BYTE OF ON TIMER.
        IF_STP  TMRON1
        BCF     PORTA,LOGO_O    ; TURN LOGO ON
SK1
        IF_STP  TMROFF1         ; CHECK IF OFF TIMER IS ACTIVE.
        GOTO    SK1
        DECF    TMROFF0         ; DEC LOW BYTE OF OFF TIMER.
        IFZ
        DECF    TMROFF1         ; DEC HIGH BYTE OF OFF TIMER.
        IF_STP  TMROFF1
        BSF     PORTA,LOGO_O    ; TURN LOGO OFF
SK2
                                ; DEC LOW BYTE OF DBS & 1/2 sec TIMERS.
                                ; LOW BYTE IS USUALLY BETWEEN 0 AND 127.
        DECF    TMRDBS0         ; IF BIT 7 OF LOW BYTE IS SET THEN
        DECF    TMRHLF0         ; MUST DEC HIGH BYTE OF TIMER AND
                                ; CLEAR BIT 7 OF LOW BYTE.
        IFSET   PORTB,GPI1_I
        INCF    GPI1
        IFSET   PORTB,GPI2_I
        INCF    GPI2
        MOVF    GPI1,W          ; UPDATE DEBOUNCE STATE FOR GPI 1
        CALL    NEXT1
        MOVWF   GPI1
        MOVF    GPI2,W          ; UPDATE DEBOUNCE STATE FOR GPI 2
        CALL    NEXT1
        MOVWF   GPI2

        IF_RUN  TMRHLF2         ; IGNOR GPI INPUTS IF HALF
        RETLW   0               ; SECOND TIMER 2 IS ACTIVE.

        IFSET   GPI1,KEYBIT
        BSF     MODE,0
        IFSET   GPI2,KEYBIT
        BSF     MODE,1
        MOVF    MODE,W
        ANDLW   $0F
        ADDWF   PC

        RETLW   0
        GOTO    DO_H
        GOTO    DO_H
        GOTO    DO_HDBS
        RETLW   0
        RETLW   0
        RETLW   0
        GOTO    DO_DBS

        RETLW   0
        GOTO    DO_HON
        GOTO    DO_HOFF
        GOTO    DO_HDBS
        RETLW   0
        RETLW   0
        RETLW   0
        GOTO    DO_DBS

DO_VDBS GOTO    DO_DBS

DO_H    BCF     PORTA,A1
        MOVLW   HALF0           ; START HALF SECOND TIMER 1.
        MOVWF   TMRHLF0
        MOVLW   HALF1
        MOVWF   TMRHLF1
        BSF     MODE,2
        RETLW   0

; ----------   -   ----------

CHK_DBS BCF     TMRDBS0,7
        IF_RUN  TMRDBS2
        GOTO    CHKD2
        IF_STP  TMRDBS1
        RETLW   0
        DECF    TMRDBS1
        IF_RUN  TMRDBS1
        RETLW   0
        BCF     PORTA,DBS_O    ; TURN DBS ON
        MOVLW   DBS0           ; START DBS OFF COUNTER
        MOVWF   TMRDBS0
        MOVLW   DBS1
        MOVWF   TMRDBS2
        RETLW   0
CHKD2
        DECF    TMRDBS2
        IF_RUN  TMRDBS2
        RETLW   0
        BSF     PORTA,DBS_O    ; TURN DBS OFF
        RETLW   0

CHK_HLF BCF     TMRHLF0,7
        IF_RUN  TMRHLF2
        GOTO    CHKH2
        IF_STP  TMRHLF1
        RETLW   0
        DECF    TMRHLF1
        IF_RUN  TMRHLF1
        RETLW   0
        MOVLW   HALF0           ; START HALF SECOND TIMER 2.
        MOVWF   TMRHLF0
        MOVLW   HALF1
        MOVWF   TMRHLF2
        RETLW   0
CHKH2
        DECF    TMRHLF2
        IF_RUN  TMRHLF2
        RETLW   0
        BSF     PORTA,A1
        MOVLW   $F7             ; SET MODE TO 0 BUT DO NOT
        ANDWF   MODE            ; CHANGE AUTOBIT.
        RETLW   0

; ----------   MAIN CODE   ----------

INIT    XORLW   $FF             ; UNPROGRAMED NOP

        MOVLW   $0F             ; INITIALIZE PORTA
        MOVWF   PORTA
        CLRW
        TRIS    PORTA           ; PORTA OUTPUT

        MOVLW   PBNONE          ; INITIALIZE PORTB
        MOVWF   PORTB
        MOVLW   PBDD_1
        TRIS    PORTB

        MOVLW   $06             ; RTCC = OSC2 / 128
        OPTION
        CLRF    RTCC

        MOVLW   8               ; CLEAR MEMORY.
        MOVWF   FSR             ; START AT LOCATION 8.
        MOVLW   24              ; FROM 8 TO 31 IS 24 LOCATIONS.
        MOVWF   PORTC           ; USE PORTC AS COUNTER.
CLEAR   CLRF    IND
        INCF    FSR
        DECFSZ  PORTC
        GOTO    CLEAR
        MOVLW   $FF
        MOVWF   TMRON1
        MOVWF   TMROFF1
        MOVWF   TMRDBS1
        MOVWF   TMRDBS2
        MOVWF   TMRHLF1
        MOVWF   TMRHLF2
        BSF     MODE,AUTOBIT    ; POWER UP IN AUTO MODE.
MAIN
        CALL    TESTGPI
        BCF     PORTA,AUTO_O    ; TURN OFF AUTO TALLY.
        BCF     ONOFF,ON_O      ; TURN OFF ON & OFF TALLYS.
        BCF     ONOFF,OFF_O
        MOVF    ONOFF,W
        MOVWF   PORTB

        IF_NEG  TMRHLF0         ; CHK 1/2 sec TIMER.
        CALL    CHK_HLF

        CALL    TESTGPI

        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES
        MOVLW   PBIP            ; MAKE DECODER SELECT INPUTS
        MOVWF   PORTB           ; ( DBS, ON, OFF, AUTO )

        IFSET   PORTB,DBS_I
        INCF    DBSSW
        IFSET   PORTB,ON_I
        INCF    ONSW
        IFSET   PORTB,OFF_I
        INCF    OFFSW
        IFSET   PORTB,AUTO_I
        INCF    AUTOSW

        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_1          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ GPI / OUTPUT ON,OFF
        MOVF    ONOFF,W         ; RESTORE ON,OFF OUTPUTS
        MOVWF   PORTB

        CALL    TESTGPI

        MOVF    DBSSW,W         ; UPDATE DEBOUNCE STATE FOR DBS
        CALL    NEXT1
        MOVWF   DBSSW
        IFSET   DBSSW,KEYBIT
        CALL    DO_VDBS

        IF_NEG  TMRDBS0         ; CHK DBS TIMER.
        CALL    CHK_DBS

        CALL    TESTGPI

        MOVF    ONSW,W          ; UPDATE DEBOUNCE STATE FOR ON
        CALL    NEXT1
        MOVWF   ONSW
        IFSET   ONSW,KEYBIT
        BCF     PORTA,LOGO_O    ; TURN LOGO ON

        CALL    TESTGPI

        MOVF    OFFSW,W         ; UPDATE DEBOUNCE STATE FOR OFF
        CALL    NEXT1
        MOVWF   OFFSW
        IFSET   OFFSW,KEYBIT
        BSF     PORTA,LOGO_O    ; TURN LOGO OFF

        CALL    TESTGPI

        MOVF    AUTOSW,W        ; UPDATE DEBOUNCE STATE FOR AUTO
        CALL    NEXT1
        MOVWF   AUTOSW
        MOVLW   $08
        IFSET   AUTOSW,KPRESS
        XORWF   MODE            ; TOGGLE AUTO MODE
        IFSET   MODE,AUTOBIT
        GOTO    ML1
        MOVLW   $FF             ; IF MANUAL MODE
        MOVWF   TMRON1          ; DISABLE ON & OFF TIMERS.
        MOVWF   TMROFF1
ML1
        CALL    TESTGPI

        IF_NEG  TMRDBS0         ; CHK DBS TIMER.
        CALL    CHK_DBS
        IF_NEG  TMRHLF0         ; CHK 1/2 sec TIMER.
        CALL    CHK_HLF

        GOTO    MAIN

; ----------   -   ----------

DO_HON
        CALL    DO_H
        IF_RUN  TMRON1          ; CHECK IF ON TIMER IS ACTIVE.
        RETLW   0
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES
        MOVLW   PBSW1           ; MAKE DECODER SELECT SW1
        MOVWF   PORTB
        SWAPF   PORTB,W         ; READ SW1
        MOVWF   TMRON0

        MOVF    TMRON0,W        ; LOOK UP THE LOW AND HIGH PARTS
        CALL    LOGDLY1         ; FOR THE LOGO OFF DELAY COUNTER.
        MOVWF   TMRON1
        MOVF    TMRON0,W
        CALL    LOGDLY0
        MOVWF   TMRON0
        GOTO    DO_W
DO_HOFF
        CALL    DO_H
        IF_RUN  TMROFF1         ; CHECK IF OFF TIMER IS ACTIVE.
        RETLW   0
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES
        MOVLW   PBSW2           ; MAKE DECODER SELECT SW2
        MOVWF   PORTB
        SWAPF   PORTB,W         ; READ SW2
        MOVWF   TMROFF0

        MOVF    TMROFF0,W       ; LOOK UP THE LOW AND HIGH PARTS
        CALL    LOGDLY1         ; FOR THE LOGO OFF DELAY COUNTER.
        MOVWF   TMROFF1
        MOVF    TMROFF0,W
        CALL    LOGDLY0
        MOVWF   TMROFF0
DO_W
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_1          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ GPI / OUTPUT ON,OFF
        MOVF    ONOFF,W         ; RESTORE ON,OFF OUTPUTS
        MOVWF   PORTB
        GOTO    WAIT

DO_HDBS
        CALL    DO_H
DO_DBS                          ; READ DBS DELAY.
        IF_RUN  TMRDBS2         ; FIRST CHECK IF DBS PUSLE
        RETLW   0               ; IS ALREADY ACTIVE.
        IF_RUN  TMRDBS1
        RETLW   0
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE.
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES.
        MOVLW   PBSW3           ; MAKE DECODER SELECT SW3.
        MOVWF   PORTB
        SWAPF   PORTB,W         ; READ SW3
        MOVWF   TMRDBS0
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_1          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ GPI / OUTPUT ON,OFF.
        MOVF    ONOFF,W         ; RESTORE ON,OFF OUTPUTS.
        MOVWF   PORTB

        MOVF    TMRDBS0,W       ; LOOK UP THE LOW AND HIGH PARTS
        CALL    DBSDLY1         ; FOR THE DBS ON DELAY COUNTER.
        MOVWF   TMRDBS1
        MOVF    TMRDBS0,W
        CALL    DBSDLY0
        MOVWF   TMRDBS0
        GOTO    WAIT

        ORG     PIC54
RESET   GOTO    INIT
        END
