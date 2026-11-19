
        LIST    F=INHX8M,R=DEC,P=16C73
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------


        ORG     $20
W_ISR   RES     1               ; MIRRORED AT $A0
ST_ISR  RES     1
PCH_ISR RES     1
AD_ISR  RES     1
TEMP0   RES     1
TEMP1   RES     1
TEMP2   RES     1

STATE   RES     1

        ORG     $30
KTAB    RES     16
CHONKS  RES     1
CHONES  RES     1
OUT1    RES     1
OUT2    RES     1
LAST1   RES     1
LAST2   RES     1

        ORG     $A0
W_ISRM  RES     1               ; MIRRORED AT $20


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

DELAY   EQU     6               ; 500 us WITH OPTION $C0
NKEYS   EQU     16              ; NUMBER OF KEYS

COL1    EQU     00000010B       ; PORTB CODES FOR KEYBOARD COLUMS
COL2    EQU     00000110B
COL3    EQU     00001010B
COL4    EQU     00001110B

CHIP1   EQU     00000110B       ; PORTB CODES FOR CHIP SELECTS
CHIP2   EQU     00001010B
CHIP3   EQU     00001110B


; ----------   MACROS   ----------

BANK0   MACRO
        BCF     STATUS,RP0
        ENDM

BANK1   MACRO
        BSF     STATUS,RP0
        ENDM

TXBIT   MACRO   F,BIT
        IFSET   F,BIT
        BSF     PORTC,SDATA
        IFCLR   F,BIT
        BCF     PORTC,SDATA
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

IFINC   MACRO   X,R
        IFSET   KTAB+X,0
        INCF    R,F
        ENDM

; ----------   .   ----------

; ----------   CODE   ----------

        ORG     0

RESET   XORLW   $FF             ; NOP
        XORLW   $FF
        XORLW   $FF
        GOTO    INIT

; ----------   INTERRUPT SUBROUTINE   ----------

        ORG     4

ISR     MOVWF   W_ISR           ; SAVE W & STATUS
        SWAPF   STATUS,W
        BANK0
        MOVWF   ST_ISR

        XORLW   $FF             ; NOP
        XORLW   $FF             ; NOP
        BCF     PORTC,TALLY

        MOVF    PCLATH,W        ; SAVE BACKGROUD PAGE
        MOVWF   PCH_ISR

        IFCLR   INTCON,T0IF
        GOTO    EXITISR

        CLRF    PCLATH          ; SET PAGE FOR ISR

        MOVLW   DELAY           ; RESET TIMER
        MOVWF   TMR0
        BCF     INTCON,T0IF

        BSF     ADCON0,GO       ; START A/D CONVERSION
ISR_L1  NOP
        IFSET   ADCON0,GO
        GOTO    ISR_L1

        BSF     PORTC,TALLY

        MOVF    STATE,W         ; GOTO NEXT STATE
        INCF    STATE,F
        ANDLW   $07
        ADDWF   PCL,F
        GOTO    STATE0
        GOTO    STATE1
        GOTO    STATE2
        GOTO    STATE3
        GOTO    STATE4
        GOTO    STATE5
        GOTO    STATE6
        GOTO    STATE7

; ----------   NEXT STATE TABLE1   ----------

; DEBOUNCE INPUT STATE MACHINE
; BIT 0 INPUT - ACTIVE HIGH
; BIT 1 STATE
; BIT 2 STATE
; BIT 3 OUTPUT - SET AFTER INPUT=1 FOUR CONSECUTIVE TIMES
; BIT 4 OUTPUT - SET AFTER BIT 3 TOGGLES
; BIT 5 OUTPUT - SET WHEN BOTH BITS 3 & 4 ARE SET

KEYBIT  EQU     3
REL     EQU     6
PRESS   EQU     7

NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
        ADDWF   PCL,F

        RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
        RETLW   2
        RETLW   0
        RETLW   4
        RETLW   0
        RETLW   6
        RETLW   0
        RETLW   8+128   ;4TH INPUT=1 SO SET KEYBIT

        RETLW   10
        RETLW   8       ; KEYBIT SET WHILE INPUT=1
        RETLW   12
        RETLW   8
        RETLW   14
        RETLW   8
        RETLW   0+64    ; 4TH INPUT=0 SO CLEAR KEYBIT
        RETLW   8

; ----------   CLEAR DEBOUNCE STATES   ----------

CLEAR   MOVLW   KTAB
        MOVWF   FSR
        MOVLW   $08
CLEAR_L1
        ANDWF   INDF,F
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    CLEAR_L1
        RETURN

; ----------   PRIORITIZE GROUP ASSIGNMENT   ----------

FIXGR   MOVWF   TEMP0
        RRF     TEMP0,F
        RRF     TEMP0,W
        ANDLW   $0F
        ADDWF   PCL,F

        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00011100B
        RETLW   00101100B
        RETLW   00101100B
        RETLW   00101100B
        RETLW   00101100B
        RETLW   00110100B
        RETLW   00110100B
        RETLW   00111000B
        RETLW   00111100B

; ----------   STATES 0 TO 7   ----------

STATE0
        CALL    SENDDAC
        MOVLW   COL1            ; SET COL1 LOW
        MOVWF   PORTB

        MOVF    OUT1,W
        XORWF   LAST1,W
        IFNZ
        GOTO    SEND595
        MOVF    OUT2,W
        XORWF   LAST2,W
        IFZ
        GOTO    EXITISR

SEND595 MOVF    OUT1,W
        MOVWF   LAST1
        MOVF    OUT2,W
        MOVWF   LAST2

        MOVLW   CHIP2           ; SEND TO 74HC595 CHIPS
        MOVWF   PORTB
        BCF     PORTB,GCS

        TXBIT   OUT1,7
        TXBIT   OUT1,6
        TXBIT   OUT1,5
        TXBIT   OUT1,4
        TXBIT   OUT1,3
        TXBIT   OUT1,2
        TXBIT   OUT1,1
        TXBIT   OUT1,0

        TXBIT   OUT2,7
        TXBIT   OUT2,6
        TXBIT   OUT2,5
        TXBIT   OUT2,4
        TXBIT   OUT2,3
        TXBIT   OUT2,2
        TXBIT   OUT2,1
        TXBIT   OUT2,0

        BSF     PORTB,GCS
        GOTO    EXITISR
STATE1
        IFCLR   PORTB,ROW1         ; CHECK COL1
        INCF    15+KTAB,F
        IFCLR   PORTB,ROW2
        INCF    14+KTAB,F
        IFCLR   PORTB,ROW3
        INCF    13+KTAB,F
        IFCLR   PORTB,ROW4
        INCF    12+KTAB,F
        CALL    SENDDAC
        MOVLW   COL2            ; SET COL2 LOW
        MOVWF   PORTB
        GOTO    EXITISR
STATE2
        IFCLR   PORTB,ROW1         ; CHECK COL2
        INCF    11+KTAB,F
        IFCLR   PORTB,ROW2
        INCF    10+KTAB,F
        IFCLR   PORTB,ROW3
        INCF    9+KTAB,F
        IFCLR   PORTB,ROW4
        INCF    8+KTAB,F
        CALL    SENDDAC
        MOVLW   COL3            ; SET COL3 LOW
        MOVWF   PORTB
        GOTO    EXITISR
STATE3
        IFCLR   PORTB,ROW1         ; CHECK COL3
        INCF    7+KTAB,F
        IFCLR   PORTB,ROW2
        INCF    6+KTAB,F
        IFCLR   PORTB,ROW3
        INCF    5+KTAB,F
        IFCLR   PORTB,ROW4
        INCF    4+KTAB,F
        CALL    SENDDAC
        MOVLW   COL4            ; SET COL4 LOW
        MOVWF   PORTB
        GOTO    EXITISR
STATE4
        IFCLR   PORTB,ROW1         ; CHECK COL4
        INCF    3+KTAB,F
        IFCLR   PORTB,ROW2
        INCF    2+KTAB,F
        IFCLR   PORTB,ROW3
        INCF    1+KTAB,F
        IFCLR   PORTB,ROW4
        INCF    0+KTAB,F
        CALL    SENDDAC
        GOTO    EXITISR
STATE5
        CALL    SENDDAC

        IFCLR   PORTA,CHONSW    ; CHECK CHON SWITCH
        INCF    CHONKS,F
        MOVF    CHONKS,W
        CALL    NEXT1
        MOVWF   CHONKS

        IFCLR   PORTC,EXTCHON   ; CHECK EXTERNAL CHON SWITCH
        INCF    CHONES,F
        MOVF    CHONES,W
        CALL    NEXT1
        MOVWF   CHONES

        MOVLW   (1<<CHONC)      ; IF PRESSED THEN TOGGLE
        IFSET   CHONKS,PRESS
        XORWF   PORTA,F
        IFSET   CHONES,PRESS
        XORWF   PORTA,F

        CLRF    TEMP0           ; COUNT NUMBER OF KEYS PRESSED
        IFINC   0,TEMP0
        IFINC   1,TEMP0
        IFINC   2,TEMP0
        IFINC   3,TEMP0
        IFINC   4,TEMP0
        IFINC   5,TEMP0
        IFINC   6,TEMP0
        IFINC   7,TEMP0
        IFINC   8,TEMP0
        IFINC   9,TEMP0
        IFINC   10,TEMP0
        IFINC   11,TEMP0
        IFINC   12,TEMP0
        IFINC   13,TEMP0
        IFINC   14,TEMP0
        IFINC   15,TEMP0

        MOVLW   3               ; TEST FOR MORE THAN TWO PRESSED
        SUBWF   TEMP0,W
        IFCC                    ; IF LESS THAN 2 PRESSED THEN
        GOTO    EXITISR         ; NEXT STATE IS 6
        CALL    CLEAR           ; ELSE CLEAR DEBOUNCE STATES
        CLRF    STATE           ; NEXT STATE IS 0
        GOTO    EXITISR

STATE6
        CALL    SENDDAC
        MOVLW   KTAB            ; DEBOUNCE KEYS
        MOVWF   FSR
UPDATE
        MOVF    INDF,W
        CALL    NEXT1
        MOVWF   INDF
        RLF     INDF,W
        RLF     TEMP2,F
        RLF     TEMP1,F         ; KEEP TRACK OF THOSE THAT CHANGE
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    UPDATE
        GOTO    EXITISR
STATE7
        CALL    SENDDAC

        MOVF    TEMP1,W         ; TOGLE OUTPUTS
        XORWF   OUT1,F
        MOVF    TEMP2,W
        XORWF   OUT2,F

        IFSET   KTAB+8,REL      ; EOT SHOULD TURN OFF PFL
        BSF     OUT1,7
        IFSET   KTAB+8,PRESS
        BSF     OUT1,7

        BSF     OUT2,6
        IFSET   KTAB+9,KEYBIT   ; IF HELD
        BCF     OUT2,6          ; MIX-MINUS SOLO ON

        BSF     OUT2,7
        IFSET   KTAB+8,KEYBIT   ; IF HELD
        BCF     OUT2,7          ; EOT ON

        IFCLR   OUT1,1
        GOTO    NOTSLAVE        ; GROUP 1 TO 4 KEYS ARE A SELECTOR
                                ; WHEN SLAVE
        MOVF    TEMP1,W
        ANDLW   $3C             ; CHECH IF ANY GROUP
        IFZ                     ; KEYS PRESSED
        GOTO    NOGROUP

        COMF    TEMP1,W         ; TURN ON HIGHEST GROUP PRESSED
        CALL    FIXGR           ; USES TEMP0 !
        IORWF   OUT1,F
NOGROUP
        MOVF    OUT1,W
        CALL    FIXGR           ; USES TEMP0 !
        IORWF   OUT1,F          ; ONLY HIGHEST PRIORITY GROUP
                                ; WHEN SLAVE
NOTSLAVE

EXITISR
        MOVF    PCH_ISR,W       ; RESTORE PCLATH
        MOVWF   PCLATH
        SWAPF   ST_ISR,W
        MOVWF   STATUS          ; RESTORE STATUS
        SWAPF   W_ISR,F
        SWAPF   W_ISR,W         ; RESTORE W
        RETFIE

; ----------   SEND TO DAC   ----------

SENDDAC
        MOVF    ADRES,W
        SUBWF   AD_ISR,W
        IFZ
        RETURN                  ; DO NOTHING IF NO CHANGE

        MOVLW   CHIP1
        MOVWF   PORTB
        BCF     PORTB,GCS       ; UPDATE DAC OUTPUT

        MOVLW   HIGH MSBTAB
        MOVWF   PCLATH
        MOVF    ADRES,W
        MOVWF   AD_ISR
        CALL    MSBTAB
        MOVWF   TEMP0

        TXBIT   TEMP0,7
        TXBIT   TEMP0,6
        TXBIT   TEMP0,5
        TXBIT   TEMP0,4

        MOVLW   HIGH LSBTAB
        MOVWF   PCLATH
        MOVF    ADRES,W
        CALL    LSBTAB
        MOVWF   TEMP0

        TXBIT   TEMP0,7
        TXBIT   TEMP0,6
        TXBIT   TEMP0,5
        TXBIT   TEMP0,4
        TXBIT   TEMP0,3
        TXBIT   TEMP0,2
        TXBIT   TEMP0,1
        TXBIT   TEMP0,0

        BSF     PORTB,GCS
        CLRF    PCLATH          ; SET PAGE FOR ISR
        RETURN

; ----------   INITIALIZATION CODE   ----------

INIT    XORLW   $FF             ; UNPROGRAMED NOP

        BANK0
        MOVLW   $3F             ; INITIALIZE PORTA & PORTB
        MOVWF   PORTA
        MOVLW   $FF
        MOVWF   PORTB
        MOVWF   PORTC

        BANK1
        MOVLW   $0F             ; SET DATA DIRECTION OF PORTA & PORTB
        MOVWF   TRISA
        MOVLW   $F1
        MOVWF   TRISB
        MOVLW   $1C
        MOVWF   TRISC
        MOVLW   $C0             ; TMR0 PRESCALER = 1MHz / 2
        MOVWF   OPTION_REG
        MOVLW   $04
        MOVWF   ADCON1
        BANK0

        BCF     PORTC,OKAY

        MOVLW   $C1
        MOVWF   ADCON0
        CLRF    AD_ISR

        CLRF    STATE

        MOVLW   KTAB
        MOVWF   FSR
BLANK   CLRF    INDF
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    BLANK
        CLRF    CHONKS
        CLRF    CHONES
        MOVLW   $FF
        MOVWF   OUT1
        MOVWF   OUT2
        MOVWF   LAST1
        MOVWF   LAST2
        BCF     OUT2,5          ; TURN ON FADER INITIALY

        CLRF    INTCON
        BSF     INTCON,T0IE
        BSF     INTCON,GIE

; ----------   MAIN CODE   ----------

MAIN

        GOTO    MAIN

; ----------   LSBTAB   ----------

        ORG     $CFE
LSBTAB  INCF    PCLATH,F
        ADDWF   PCL,F
               
        INCLUDE "LSB."


; ----------   MSBTAB   ----------

        ORG     $EFE
MSBTAB  INCF    PCLATH,F
        ADDWF   PCL,F

        INCLUDE "MSB."


        END
