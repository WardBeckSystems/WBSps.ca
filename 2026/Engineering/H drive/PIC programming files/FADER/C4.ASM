
        LIST    F=INHX8M,R=DEC,P=16C73
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------


        ORG     $20
W_ISR   RES     1               ; MIRRORED AT $A0
ST_ISR  RES     1
PCH_ISR RES     1
AD_LR0  RES     1
AD_LR1  RES     1
TEMP0   RES     1
TEMP1   RES     1
TEMP2   RES     1

INDEX0  RES     1
INDEX1  RES     1
LINDEX0 RES     1
LINDEX1 RES     1

INDEX   RES     1
STATE   RES     1

        ORG     $30
KTAB    RES     16
CHONKS  RES     1
CHONES  RES     1
OUT1    RES     1
OUT2    RES     1
LAST1   RES     1
LAST2   RES     1

DACLSB  RES     1
DACMSB  RES     1
DACL    RES     1
DACH    RES     1

SF      RES     1
PBYTE   RES     1
PTXSR   RES     1
PCNT    RES     1
PTMR    RES     1

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

IH15LO  EQU     $60
IH15HI  EQU     $0D

; ----------   SF BITS   ----------

ADTAL   EQU     0

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
RESET
        RES     2
        BSF     PCLATH,3
        GOTO    INIT

; ----------   INTERRUPT JUMP TO   ----------

        ORG     4

        MOVWF   W_ISR           ; SAVE W & STATUS
        SWAPF   STATUS,W
        BANK0
        MOVWF   ST_ISR
        RES     1               ; NOP
        GOTO    ISR

        ORG     $800

; ----------   TABS   ----------

        INCLUDE "FTAB.ASM"

GETLSB
        MOVLW   HIGH LSBTAB
        MOVWF   PCLATH
        MOVF    INDEX,W
        ADDWF   PCL,F
        GOTO    INIT            ; UNPOSIBLE
GETMSB
        MOVLW   HIGH MSBTAB
        MOVWF   PCLATH
        MOVF    INDEX,W
        ADDWF   PCL,F
        GOTO    INIT            ; UNPOSIBLE

; ----------   SUBS   ----------

SUBS

; ----------   INTERRUPT SUBROUTINE   ----------

ISR
        RES     1               ; NOP
        BCF     PORTC,TALLY

        MOVF    PCLATH,W        ; SAVE BACKGROUD PAGE
        MOVWF   PCH_ISR

        IFCLR   INTCON,T0IF     ; ONLY USE TIMER0 INTERRUPTS
        GOTO    EXITISR         ; IGNOR ALL OTHERS

        MOVLW   DELAY           ; RESET TIMER
        MOVWF   TMR0
        BCF     INTCON,T0IF

        MOVLW   HIGH SUBS
        MOVWF   PCLATH          ; SET PAGE FOR ISR

        BSF     ADCON0,GO       ; START A/D CONVERSION
ISR_L1  NOP
        IFSET   ADCON0,GO
        GOTO    ISR_L1

        MOVF    ADRES,W         ; DELAY 2*TAD = 10 INSTURCTION
        ADDWF   AD_LR0,F        ; BEFOR START NEXT A/D SAMPLE.
        RRF     AD_LR0,W        ; AVERAGE ADRES WITH AD_LR0
        MOVWF   INDEX0
        MOVF    ADRES,W
        MOVWF   AD_LR0
        NOP
        NOP
        NOP
        NOP
        BSF     ADCON0,CHS0     ; SELECT PORTA1.
        NOP                     ; DELAY 1 TAD = 5 INSTURCTIONS
        NOP                     ; BEFOR START NEXT A/D CONVERTION.
        NOP
        NOP
        NOP
        BSF     ADCON0,GO       ; START A/D CONVERSION
ISR_L2  NOP
        IFSET   ADCON0,GO
        GOTO    ISR_L2
        MOVF    ADRES,W
        ADDWF   AD_LR1,F        ; AVERAGE ADRES WITH AD_LR1
        RRF     AD_LR1,W
        MOVWF   INDEX1
        MOVF    ADRES,W
        MOVWF   AD_LR1

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

; ----------   HEX TAB   ----------

HEX
        ANDLW   $0F
        ADDWF   PCL,F

        RETLW   $30
        RETLW   $31
        RETLW   $32
        RETLW   $33
        RETLW   $34
        RETLW   $35
        RETLW   $36
        RETLW   $37
        RETLW   $38
        RETLW   $39
        RETLW   $41
        RETLW   $42
        RETLW   $43
        RETLW   $44
        RETLW   $45
        RETLW   $46

; ----------   STATES 0 TO 7   ----------

STATE0
        CALL    UPDAC
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
        CALL    UPDAC
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
        CALL    UPDAC
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
        CALL    UPDAC
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
        CALL    UPDAC
        GOTO    EXITISR
STATE5
        CALL    UPDAC

        IFCLR   PORTA,CHONSW    ; CHECK CHON SWITCH
        INCF    CHONKS,F
        MOVF    CHONKS,W
        CALL    NEXT1
        MOVWF   CHONKS

;        IFCLR   PORTC,EXTCHON   ; CHECK EXTERNAL CHON SWITCH
;        INCF    CHONES,F
;        MOVF    CHONES,W
;        CALL    NEXT1
;        MOVWF   CHONES

        MOVLW   (1<<CHONC)      ; IF PRESSED THEN TOGGLE
        IFSET   CHONKS,PRESS
        XORWF   PORTA,F
;        IFSET   CHONES,PRESS
;        XORWF   PORTA,F

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
        GOTO    NEXT6           ; NEXT STATE IS 6
        CALL    CLEAR           ; ELSE CLEAR DEBOUNCE STATES
        CLRF    STATE           ; NEXT STATE IS 0
NEXT6
        IFCLR   CHONKS,PRESS
        GOTO    EXITISR
;        IFCLR   CHONES,PRESS
;        GOTO    EXITISR
        IFCLR   PORTA,CHONC
        GOTO    TURNONDAC
        CLRF    DACMSB
        CLRF    DACLSB
        CALL    SENDDAC
        GOTO    EXITISR
TURNONDAC
        MOVF    DACH,F
        MOVWF   DACMSB
        MOVF    DACL,F
        MOVWF   DACLSB
        CALL    SENDDAC
        GOTO    EXITISR
STATE6
        CALL    UPDAC
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
        CALL    UPDAC

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
        BCF     ADCON0,CHS0     ; SELECT PORTA0
        MOVF    PCH_ISR,W       ; RESTORE PCLATH
        MOVWF   PCLATH
        SWAPF   ST_ISR,W
        MOVWF   STATUS          ; RESTORE STATUS
        SWAPF   W_ISR,F
        SWAPF   W_ISR,W         ; RESTORE W
        RETFIE

; ----------   UPDATE DAC   ----------

UPDAC
        MOVF    INDEX0,W
        XORWF   LINDEX0,W
        IFNZ
        GOTO    CHANGEDAC
        MOVF    INDEX1,W
        XORWF   LINDEX1,W
        IFZ
        RETURN                  ; DO NOTHING IF NO CHANGE
CHANGEDAC
        BSF     SF,ADTAL
        MOVF    INDEX1,W
        MOVWF   LINDEX1
        MOVF    INDEX0,W
        MOVWF   LINDEX0
        MOVWF   INDEX
        CALL    GETLSB
        MOVWF   DACL
        CALL    GETMSB
        MOVWF   DACH

        IFCLR   OUT1,1
        GOTO    SIMPLEMASTER
        COMF    OUT1,W
        ANDLW   $3C
        IFZ
        GOTO    LONE

        MOVLW   IH15LO          ; SUBTRACT INHAND REFERENCE
        SUBWF   DACL,F
        IFCC
        DECF    DACH,F
        MOVLW   IH15HI
        SUBWF   DACH,F

        MOVF    INDEX1,W
        MOVWF   INDEX
        CALL    GETLSB
        ADDWF   DACL,F
        IFCS
        INCF    DACH,F
        CALL    GETMSB
        ADDWF   DACH,F
        IFCLR   DACH,7          ; IF NEGATIVE ENTER ZERO
        GOTO    NOUNDER
        CLRF    DACL
        CLRF    DACH
NOUNDER
        MOVF    DACH,W
        ANDLW   $70             ; IF GREATER THAN $0FFF MAKE $0FFF
        IFZ
        GOTO    NOOVER
        MOVLW   $FF
        MOVWF   DACL
        MOVWF   DACH
NOOVER
LONE
SIMPLEMASTER
        MOVLW   HIGH SUBS       ; SET PAGE FOR ISR
        MOVWF   PCLATH

        IFSET   PORTA,CHONC
        RETURN                  ; LEAVE DAC OFF IF CHANNEL OFF

        MOVF    DACH,W
        MOVWF   DACMSB
        MOVF    DACL,W
        MOVWF   DACLSB

; ----------   SEND TO DAC   ----------

SENDDAC
        MOVLW   CHIP1
        MOVWF   PORTB
        BCF     PORTB,GCS       ; UPDATE DAC OUTPUT

        TXBIT   DACMSB,3
        TXBIT   DACMSB,2
        TXBIT   DACMSB,1
        TXBIT   DACMSB,0

        TXBIT   DACLSB,7
        TXBIT   DACLSB,6
        TXBIT   DACLSB,5
        TXBIT   DACLSB,4
        TXBIT   DACLSB,3
        TXBIT   DACLSB,2
        TXBIT   DACLSB,1
        TXBIT   DACLSB,0

        BSF     PORTB,GCS
        RETURN

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

; ----------   INITIALIZATION CODE   ----------

INIT    RES     1               ; NOP
        RES     1               ; NOP

        BANK0
        MOVLW   $3F             ; INITIALIZE PORTA, PORTB & PORTC
        MOVWF   PORTA
        MOVLW   $FF
        MOVWF   PORTB
        MOVWF   PORTC

        BANK1
        MOVLW   $1F             ; SET DATA DIRECTION OF PORTS A, B & C
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

        CLRF    STATE
        CLRF    INDEX0
        CLRF    INDEX1
        CLRF    LINDEX0
        CLRF    LINDEX1
        CLRF    AD_LR0
        CLRF    AD_LR1
        CLRF    DACH
        CLRF    DACL
        CLRF    SF

        MOVLW   HIGH SUBS
        MOVWF   PCLATH          ; SET PAGE

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

        IFCLR   SF,ADTAL
        GOTO    MAIN
        IFSET   OUT2,6          ; PRESS MMSOLO FOR TALLY
        GOTO    MAIN
DOP
        BCF     INTCON,GIE
        IFSET   INTCON,GIE
        GOTO    DOP

        BCF     SF,ADTAL

        CALL    CR

        MOVF    AD_LR0,W
        CALL    PRINT

        MOVLW   $20
        CALL    EMIT

        MOVF    AD_LR1,W
        CALL    PRINT

        MOVLW   $20
        CALL    EMIT
        MOVLW   $20
        CALL    EMIT

        MOVF    DACMSB,W
        CALL    PRINT
        MOVF    DACLSB,W
        CALL    PRINT

        BSF     INTCON,GIE
        GOTO    MAIN

; ----------   CR   ----------

CR
        MOVLW   $0D
        CALL    EMIT
        MOVLW   $0A
        CALL    EMIT
        RETURN

; ----------   PRINT   ----------

PRINT
        MOVWF   PBYTE
        SWAPF   PBYTE,W
        CALL    HEX
        CALL    EMIT
        MOVF    PBYTE,W
        CALL    HEX
        CALL    EMIT
        RETURN

; ----------   EIMT   ----------

EMIT
        MOVWF   PTXSR
        BCF     PORTC,5
        MOVLW   8
        MOVWF   PCNT
        CALL    ONEBIT          ; START BIT
EMIT1
        IFSET   PTXSR,0
        BSF     PORTC,5
        IFCLR   PTXSR,0
        BCF     PORTC,5
        RRF     PTXSR,F
        CALL    ONEBIT          ; 8 DATA BITS
        DECFSZ  PCNT,F
        GOTO    EMIT1
        BSF     PORTC,5         ; STOP BIT
        CALL    ONEBIT
        RETURN
ONEBIT
        MOVLW   30              ; (104-10-4)/3  GIVES 9600 BAUD
        MOVWF   PTMR
ONELOOP
        DECFSZ  PTMR,F
        GOTO    ONELOOP
        RETURN

        END

