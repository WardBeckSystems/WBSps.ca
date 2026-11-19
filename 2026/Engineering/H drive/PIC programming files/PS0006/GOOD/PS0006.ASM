        LIST    F=INHX8M,R=DEC,P=16C54,X=OFF,C=120,N=75

; ----------   Pic Software 0006   ----------

; PROJECT  950069  CBC MACHINE & LOGO CONTROL UNIT
; MODULE   M718B
; REVISION 1.00

; WRITTEN AND DESIGNED BY PETER SHOOK
; MAY 31, 1995

; COPYRIGHT 1995, WARD-BECK SYSTEMS LTD.
; 841 PROGRESS AVENUE
; SCARBOROUGH, ONTARIO, CANADA, M1H 2X4
; (416) 438-6550

; OSC=RC   WDT=ON   CP=OFF   ID=0006   CKSUM=565B

; ----------   PIC16C5X HEADER   ----------

W       EQU     0

; RESET ADDRESSES
PIC54   EQU     0x1FF

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
IND     EQU     00      ; INDIRECT ADDRESSING REGISTER
RTCC    EQU     01      ; COUNTER
PC      EQU     02      ; PROGRAM COUNTER
STATUS  EQU     03      ; STATUS WORD REGISTER
FSR     EQU     04      ; FILE SELECT REGISTER
PORTA   EQU     05
PORTB   EQU     06
PORTC   EQU     07

IFZ     MACRO                   ; IF ZERO
        BTFSC   STATUS,Z
        ENDM

IFNZ    MACRO                   ; IF NON ZERO
        BTFSS   STATUS,Z
        ENDM

IFCS    MACRO                   ; IF CARRY SET
        BTFSC   STATUS,C
        ENDM

IFCC    MACRO                   ; IF CARRY CLEAR
        BTFSS   STATUS,C
        ENDM

IFSET   MACRO   F,BIT           ; IF BIT SET
        BTFSC   F,BIT
        ENDM

IFCLR   MACRO   F,BIT           ; IF BIT CLEAR
        BTFSS   F,BIT
        ENDM


; ----------   END HEADER   ----------

IF_RUN  MACRO   TMR     ; IF TIMER RUNNING
        IFCLR   TMR,7
        ENDM

IF_STP  MACRO   TMR     ; IF TIMER STOPPED
        IFSET   TMR,7
        ENDM

IF_NEG  MACRO   TMR     ; IF TIMER NEGATIVE
        IFSET   TMR,7
        ENDM

; ----------   PORTA BITS   ----------

LOGO_O  EQU     0               ; ACTIVE LOW OUTPUT
A1      EQU     1               ; UNUSED OUTPUT
AUTO_O  EQU     2               ; ACTIVE LOW OUTPUT
DBS_O   EQU     3               ; ACTIVE LOW OUTPUT

; ----------   PORTB BITS FROM U4A   ----------

DBS_I   EQU     4               ; ACTIVE HIGH INPUT
ON_I    EQU     5               ; ACTIVE HIGH INPUT
OFF_I   EQU     6               ; ACTIVE HIGH INPUT
AUTO_I  EQU     7               ; ACTIVE HIGH INPUT

; ----------   PORTB BITS TO/FROM U6A   ----------

GPI1_I  EQU     4               ; ACTIVE HIGH INPUT
GPI2_I  EQU     5               ; ACTIVE HIGH INPUT
ON_O    EQU     6               ; ACTIVE LOW OUTPUT
OFF_O   EQU     7               ; ACTIVE LOW OUTPUT
XONOFF  EQU     ((1<<ON_O)+(1<<OFF_O))

        ORG     08

; ----------   RAM REGISTERS   ----------

DBSSW   RES     1       ; DBS  SWITCH DEBOUNCE STATE.
ONSW    RES     1       ; ON   SWITCH DEBOUNCE STATE.
OFFSW   RES     1       ; OFF  SWITCH DEBOUNCE STATE.
AUTOSW  RES     1       ; AUTO SWITCH DEBOUNCE STATE.

GPI1    RES     1       ; GPI 1  INPUT DEBOUNCE STATE.
GPI2    RES     1       ; GPI 2  INPUT DEBOUNCE STATE.
MODE    RES     1       ; OPERATION MODE OF SOFTWARE.
ONOFF   RES     1       ; TEMP STORAGE FOR ON & OFF TALLY OUTPUTS
                        ; WHILE PORTB IS USED TO READ INPUTS.

OLD     RES     1       ; LAST VALUE OF RTCC.
TMRON0  RES     1       ; ON  TIMER  LOW BYTE
TMRON1  RES     1       ;            HIGH BYTE
TMROFF0 RES     1       ; OFF TIMER  LOW BYTE
TMROFF1 RES     1       ;            HIGH BYTE
TMRDBS0 RES     1       ; DBS TIMER  LOW BYTE
TMRDBS1 RES     1       ;            FIRST HIGH BYTE
TMRDBS2 RES     1       ;            SECOND HIGH BYTE
TMRHLF0 RES     1       ; 1/2 SECOND LOW BYTE
TMRHLF1 RES     1       ; TIMER      FIRST HIGH BYTE
TMRHLF2 RES     1       ;            SECOND HIGH BYTE

; USE 4K5 AND 330pF FOR RC OSCILATOR SO THAT OS2 = 128kHz.
; WITH OPTION 6 THE PRESCALER DIVIDES OS2 BY 128 SO THAT
; RTCC IS INCREMENTED EVER 1 msec.
; DURING EVER CALL TO TESTGPI THE WAIT LOOP WAITS FOR THE RTCC
; TO CHANGE BY COMPARING IT TO ITS LAST VALUE STORED IN OLD.
; THEN OLD IS UPDATED TO THE CURRENT VALUE OF RTCC AND THE LOW
; BYTES OF ALL THE TIMERS ARE DECREMENTED.

; ALL THE TIMERS COUNT DOWN.

; THE ON & OFF TIMER VALUES IN msec ARE EQUAL TO:
;     ( LOW BYTE-1 ) + 256 * ( HIGH BYTE )
; IF BIT 7 OF THE HIGH BYTE IS SET THEN THE TIMER IS STOPPED.

; THE DBS TIMER AND 1/2 SECOND TIMER VALUES IN msec ARE EQUAL TO:
;     ( LOW BYTE ) + 128 * ( HIGH BYTE )
; IF BIT 7 OF THE LOW BYTE IS SET THEN
;     DECREMENT THE HIGH BYTE AND CLEAR BIT 7 OF THE LOW BYTE.
; IF BIT 7 OF THE HIGH BYTE IS SET THEN THE TIMER IS STOPPED.

; TMRON1 & TMRON0 ARE USED TO TIME THE VARIABLE ON DELAY TIME.
; TMROFF1 & TMROFF0 ARE USED TO TIME THE VARIABLE OFF DELAY TIME.

; TMRHLF1 & TMRHLF0 ARE USED TO TIME THE FIRST 1/2 SECOND AFTER
; ONE OF THE GPI INPUTS IS ACTIVATED.
; TMRHLF2 & TMRHLF0 ARE USED TO TIME THE SECOND 1/2 SECOND AFTER
; ONE OF THE GPI INPUTS IS ACTIVATED.

; TMRDBS1 & TMRDBS0 ARE USED TO TIME THE VARIABLE DBS DELAY.
; TMRDBS2 & TMRDBS0 ARE USED TO TIME THE 1.5 SECOND DBS PULSE.

; ----------   EQUATES   ----------

DBS0    EQU     92
DBS1    EQU     11          ; 11*128+92=1500 msec
HALF0   EQU     116
HALF1   EQU     3           ; 3*128+116=500 msec

                            ; MODE BITS
AUTOBIT EQU     3           ; UNIT IN AUTO MODE.
F1BIT   EQU     4           ; GPI1 STARTED ON TIMER.
F2BIT   EQU     5           ; GPI2 STARTED OFF TIMER.

                            ; PORTB DATA DIRECTION
PBDD_1  EQU     $30         ; PORTB READ GPI / OUTPUT ON,OFF
PBDD_2  EQU     $F0         ; PORTB READ INPUTS/SWITCHES

                            ; DECODER ADDRESSES
PBIP    EQU     (XONOFF+8)  ; INPUTS
PBSW1   EQU     PBIP+1      ; SWITCH 1
PBSW2   EQU     PBIP+2      ; SWITCH 2
PBSW3   EQU     PBIP+3      ; SWITCH 3
PBNONE  EQU     $0F         ; DISABLE ALL BUFFERS BY SELECTING NONE

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

; ----------   DBS DELAY TABLES 2 & 3   ----------

DBSDLY0 ANDLW   $0F
        ADDWF   PC      ; RETURN LOW BYTE OF DBS DELAY
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
        ADDWF   PC      ; RETURN HIGH BYTE OF DBS DELAY
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

; ----------   LOGO ON AND OFF DELAY TABLES 4 & 5   ----------

LOGDLY0 ANDLW   $0F
        ADDWF   PC      ; RETURN LOW BYTE OF LOGO DELAY
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
        ADDWF   PC      ; RETURN HIGH BYTE OF LOGO DELAY
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
        GOTO    SK2
        DECF    TMROFF0         ; DEC LOW BYTE OF OFF TIMER.
        IFZ
        DECF    TMROFF1         ; DEC HIGH BYTE OF OFF TIMER.
        IF_STP  TMROFF1
        BSF     PORTA,LOGO_O    ; TURN LOGO OFF
SK2
                             ; DEC LOW BYTE OF DBS & 1/2 sec TIMERS.
                             ; LOW BYTE IS USUALLY BETWEEN 0 AND 127.
        DECF    TMRDBS0      ; IF BIT 7 OF LOW BYTE IS SET THEN
        DECF    TMRHLF0      ; MUST DEC HIGH BYTE OF TIMER AND
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
        MOVLW   DBS0           ; START DBS OFF TIMER
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
        MOVLW   (1<<AUTOBIT)    ; SET MODE TO 0 BUT DO NOT
        ANDWF   MODE            ; CHANGE AUTOBIT.
        RETLW   0

; ----------   MAIN CODE   ----------

        ORG     $13B
INIT    XORLW   $FF             ; UNPROGRAMED NOP

        MOVLW   $0B             ; INITIALIZE PORTA
        MOVWF   PORTA
        CLRW
        TRIS    PORTA           ; PORTA OUTPUT

        MOVLW   PBNONE          ; INITIALIZE PORTB
        MOVWF   PORTB
        MOVLW   PBDD_1
        TRIS    PORTB
        MOVLW   XONOFF
        MOVWF   PORTB
        MOVWF   ONOFF

        MOVLW   $06             ; RTCC = OSC2 / 128
        OPTION
        CLRF    RTCC
        CLRF    OLD

        CLRF    DBSSW           ; CLEAR DEBOUNCE STATES.
        CLRF    ONSW
        CLRF    OFFSW
        CLRF    AUTOSW
        CLRF    GPI1
        CLRF    GPI2

        MOVLW   (1<<AUTOBIT)    ; POWER UP IN AUTO MODE.
        MOVWF   MODE

        MOVLW   $FF             ; DISABLE ALL TIMERS.
        MOVWF   TMRON1
        MOVWF   TMROFF1
        MOVWF   TMRDBS1
        MOVWF   TMRDBS2
        MOVWF   TMRHLF1
        MOVWF   TMRHLF2
MAIN
        CALL    TESTGPI        ; ----------   1 msec   ----------

        CLRWDT
        BSF     PORTA,AUTO_O    ; TURN OFF AUTO TALLY.
        MOVLW   XONOFF
        MOVWF   ONOFF
        MOVWF   PORTB           ; TURN OFF ON & OFF TALLYS.

        IF_NEG  TMRHLF0         ; CHK 1/2 sec TIMER.
        CALL    CHK_HLF

        CALL    TESTGPI        ; ----------   1 msec   ----------

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

        CALL    TESTGPI        ; ----------   1 msec   ----------

        MOVF    DBSSW,W         ; UPDATE DEBOUNCE STATE FOR DBS
        CALL    NEXT1
        MOVWF   DBSSW
        IFSET   DBSSW,KEYBIT
        CALL    DO_VDBS

        IF_NEG  TMRDBS0         ; CHK DBS TIMER.
        CALL    CHK_DBS

        CALL    TESTGPI        ; ----------   1 msec   ----------

        MOVLW   (XONOFF-(1<<OFF_O))     ; VALUE TO TALLY OFF
        IFCLR   PORTA,LOGO_O
        MOVLW   (XONOFF-(1<<ON_O))      ; VALUE TO TALLY ON
        MOVWF   ONOFF
        MOVWF   PORTB

        IF_NEG  TMRHLF0         ; CHK 1/2 sec TIMER.
        CALL    CHK_HLF

        CALL    TESTGPI        ; ----------   1 msec   ----------

        CLRWDT
        MOVF    ONSW,W          ; UPDATE DEBOUNCE STATE FOR ON
        CALL    NEXT1
        MOVWF   ONSW
        IFSET   MODE,AUTOBIT
        GOTO    MSK1            ; ON KEY DISABLED IN AUTO MODE
        IFSET   ONSW,KEYBIT
        BCF     PORTA,LOGO_O    ; TURN LOGO ON
MSK1
        CALL    TESTGPI        ; ----------   1 msec   ----------

        MOVF    OFFSW,W         ; UPDATE DEBOUNCE STATE FOR OFF
        CALL    NEXT1
        MOVWF   OFFSW
        IFSET   MODE,AUTOBIT
        GOTO    MSK2            ; OFF KEY DISABLED IN AUTO MODE
        IFSET   OFFSW,KEYBIT
        BSF     PORTA,LOGO_O    ; TURN LOGO OFF
MSK2
        IF_NEG  TMRDBS0         ; CHK DBS TIMER.
        CALL    CHK_DBS

        CALL    TESTGPI        ; ----------   1 msec   ----------

        MOVLW   XONOFF
        MOVWF   ONOFF           ; TURN OFF ON & OFF TALLYS.
        MOVWF   PORTB
        IFSET   MODE,AUTOBIT    ; TALLY AUTO MODE.
        BCF     PORTA,AUTO_O    ; TURN ON AUTO TALLY.
        IFCLR   MODE,AUTOBIT
        BSF     PORTA,AUTO_O    ; TURN OFF AUTO TALLY.

        IF_NEG  TMRHLF0         ; CHK 1/2 sec TIMER.
        CALL    CHK_HLF

        CALL    TESTGPI        ; ----------   1 msec   ----------

        MOVF    AUTOSW,W        ; UPDATE DEBOUNCE STATE FOR AUTO
        CALL    NEXT1
        MOVWF   AUTOSW
        MOVLW   (1<<AUTOBIT)
        IFSET   AUTOSW,KPRESS
        XORWF   MODE            ; TOGGLE AUTO MODE
        IFSET   MODE,AUTOBIT
        GOTO    ML1
        MOVLW   $FF             ; IF MANUAL MODE
        MOVWF   TMRON1          ; DISABLE ON & OFF TIMERS.
        MOVWF   TMROFF1
ML1
        CALL    TESTGPI        ; ----------   1 msec   ----------

        IF_NEG  TMRDBS0         ; CHK DBS TIMER.
        CALL    CHK_DBS

        GOTO    MAIN

; ----------   -   ----------

DO_HON
        CALL    DO_H
        IF_RUN  TMRON1          ; CHECK IF ON TIMER IS ACTIVE.
        RETLW   0
        BSF     MODE,F1BIT
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES
        MOVLW   PBSW1           ; MAKE DECODER SELECT SW1
        MOVWF   PORTB
        SWAPF   PORTB,W         ; READ SW1
        MOVWF   TMRON0

        MOVF    TMRON0,W        ; LOOK UP THE LOW AND HIGH PARTS
        CALL    LOGDLY1         ; FOR THE LOGO ON DELAY TIMER.
        MOVWF   TMRON1
        MOVF    TMRON0,W
        CALL    LOGDLY0
        MOVWF   TMRON0
        GOTO    DO_W
DO_HOFF
        CALL    DO_H
        IF_RUN  TMROFF1         ; CHECK IF OFF TIMER IS ACTIVE.
        RETLW   0
        BSF     MODE,F2BIT
        MOVLW   PBNONE          ; MAKE DECODER SELECT NONE
        IORWF   PORTB
        MOVLW   PBDD_2          ; CHANGE DATA DIRECTION OF PORTB
        TRIS    PORTB           ; TO READ INPUTS/SWITCHES
        MOVLW   PBSW2           ; MAKE DECODER SELECT SW2
        MOVWF   PORTB
        SWAPF   PORTB,W         ; READ SW2
        MOVWF   TMROFF0

        MOVF    TMROFF0,W       ; LOOK UP THE LOW AND HIGH PARTS
        CALL    LOGDLY1         ; FOR THE LOGO OFF DELAY TIMER.
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
        CALL    DBSDLY1         ; FOR THE DBS ON DELAY TIMER.
        MOVWF   TMRDBS1
        MOVF    TMRDBS0,W
        CALL    DBSDLY0
        MOVWF   TMRDBS0

        MOVLW   $FF             ; DISABLE ON OR OFF TIMER
        IFSET   MODE,F1BIT      ; IF ONE OR THE OTHER WAS
        MOVWF   TMRON1          ; STARTED.
        IFSET   MODE,F2BIT
        MOVWF   TMROFF1
        GOTO    WAIT

        ORG     PIC54
RESET   GOTO    INIT
        END
