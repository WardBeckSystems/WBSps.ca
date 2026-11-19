
        LIST    F=INHX8M,R=DEC,P=16C73
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

RAMBANK0 ORG     $20

W_ISR   RES     1               ; ALSO SHADOW AT $A0
ST_ISR  RES     1               ; SAVE STATUS FLAGS & BANK SELECT WHEN IN ISR
PCH_ISR RES     1               ; SAVE PCLATH WHEN IN ISR
FSR_ISR RES     1               ; SAVE FSR WHEN IN ISR
TEMP1   RES     1               ; TEMPS FOR ISR ROUTINES
TEMP2   RES     1
PRESS1  RES     1               ; BITMAP OF PRESSED KEYS
PRESS2  RES     1
ADR0    RES     1               ; A/D RESULT FOR FADER
ADR1    RES     1               ; A/D RESULT FOR GROUP FADER
CHONKS  RES     1               ; CHANNEL ON KEY DEBOUNCE STATE
CHONES  RES     1               ; EXTERNAL CHANNEL ON DEBOUNCE STATE
SIG     RES     1               ; FLAGS TO SIGNAL ACTIONS

        ORG     $30             ; MUST HAVE BIT 4 SET
KTAB    RES     16              ; DEBOUNCE STATES FOR KEYS
FLP     RES     1               ; FORGROUND  LIST POINTER
FLT     RES     7               ; FORGROUND  LINK TABLE
BLP     RES     1               ; BACKGROUND LIST POINTER
BLT     RES     7               ; BACKGROUND LINK TABLE

OUT1    RES     1               ; BIT MAP OF OUTPUT STATES
OUT2    RES     1
DACL    RES     1               ; LSB OF LEVEL FOR DAC
DACH    RES     1               ; MSB OF LEVEL FOR DAC

I       RES     1

PBYTE   RES     1
PTXSR   RES     1
PCNT    RES     1
PTMR    RES     1

EECNT   RES     1
EEMSB   RES     1
EELSB   RES     1

RAMBANK1 ORG     $A0
        RES     1               ; SHADOW OF W_ISR
LISTSPACE
        RES     95

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

DELAY   EQU     16              ; 500 us WITH OPTION $C0
NKEYS   EQU     16              ; NUMBER OF KEYS

COL1    EQU     00000010B       ; PORTB CODES FOR KEYBOARD COLUMS
COL2    EQU     00000110B
COL3    EQU     00001010B
COL4    EQU     00001110B

ERRPULSE EQU    00000010B       ; connect counter to U2 pin 4
                                ; to count error pulses.
CHIP1   EQU     00000110B       ; PORTB CODES FOR CHIP SELECTS
CHIP2   EQU     00001010B
CHIP3   EQU     00001110B

IH15LO  EQU     $60             ; IH15LO  EQU     $BE
IH15HI  EQU     $0D             ; IH15HI  EQU     $0E

; ----------   SIG BITS   ----------

DACNEW0 EQU     0       ; NEED TO UPDATE DAC DUE TO FADER OR GROUP OR MSTR
DACNEW1 EQU     1       ; NEED TO UPDATE DAC DUE TO GROUP FADER
EOTREL  EQU     2       ; SIGNALS RELEASE OF EOT SWITCH

; ----------   MACROS   ----------

BANK0   MACRO
        BCF     STATUS,RP0
        ENDM

BANK1   MACRO
        BSF     STATUS,RP0
        ENDM

TXBIT   MACRO   REG,BIT
        IFSET   REG,BIT
        BSF     PORTC,SDATA
        IFCLR   REG,BIT
        BCF     PORTC,SDATA
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

RXBIT   MACRO   REG
        RLF     REG,F
        BCF     REG,0
        IFSET   PORTC,SDATA
        BSF     REG,0
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

IFINC   MACRO   X,REG
        IFSET   KTAB+X,0
        INCF    REG,F
        ENDM

SKIP_F  MACRO
        INCF    FLP,F
        ENDM

SKIP_B  MACRO
        INCF    BLP,F
        ENDM

JUMP_F  MACRO   X
        MOVF    FLT+X,W
        MOVWF   FLP
        GOTO    EXECUTE
        ENDM

JUMP_B  MACRO   X
        MOVF    BLT+X,W
        MOVWF   BLP
        GOTO    EXECUTE
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

; ----------   .   ----------


; ----------   TABS   ----------

        ORG     $0800           ; must be multiple of $100

        INCLUDE "FTAB.ASM"

; ----------   SUBS   ----------

SUBS

GETLSB
        MOVLW   HIGH LSBTAB
        MOVWF   PCLATH
        MOVF    TEMP1,W
        ADDWF   PCL,F           ; interrupts should be disabled
        GOTO    INIT            ; UNPOSIBLE
GETMSB
        MOVLW   HIGH MSBTAB
        MOVWF   PCLATH
        MOVF    TEMP1,W
        ADDWF   PCL,F           ; interrupts should be disabled
        GOTO    INIT            ; UNPOSIBLE

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
        RETLW   8+128   ; 4TH INPUT=1 SO SET KEYBIT

        RETLW   10
        RETLW   8       ; KEYBIT SET WHILE INPUT=1
        RETLW   12
        RETLW   8
        RETLW   14
        RETLW   8
        RETLW   0+64    ; 4TH INPUT=0 SO CLEAR KEYBIT
        RETLW   8

; ----------   LISTS   ----------

LT
RTC
        ADDWF   PCL,F

        RETLW   8       ; CHK_ON
	RETLW	9	; CHK_COL1
	RETLW	10	; CHK_COL2
	RETLW	11	; CHK_COL3
	RETLW	12	; CHK_COL4
	RETLW	13	; NUM_PRESSED
	RETLW	14	; DEBOUNCE
	RETLW	15	; UPDAC
	RETLW	15	; UPDAC
	RETLW	15	; UPDAC
	RETLW	8	; CHK_ON
	RETLW	9	; CHK_COL1
	RETLW	10	; CHK_COL2
	RETLW	11	; CHK_COL3
	RETLW	12	; CHK_COL4
	RETLW	13	; NUM_PRESSED
	RETLW	14	; DEBOUNCE
	RETLW	15	; UPDAC
	RETLW	15	; UPDAC
	RETLW	22	; OUT595
	RETLW	23	; JMPF0

        RETLW   17      ; STUFF
	RETLW	27	; JMPB0

; ----------   KERNEL   ----------

EXECUTE
        MOVWF   FSR
        MOVF    INDF,W
        ANDLW   $3F
EXEC_AGAIN
        ADDWF   PCL,F
        GOTO    EXEC_AGAIN      ; SAFETY FIRST.
                                ; IN CASE OF INTERRUPT.
	GOTO	RTC
	GOTO	LT
	GOTO	GETLSB
	GOTO	GETMSB
	GOTO	NEXT1
	GOTO	EXECUTE
	GOTO	ISR
	GOTO	CHK_ON
	GOTO	CHK_COL1
	GOTO	CHK_COL2
	GOTO	CHK_COL3
	GOTO	CHK_COL4
	GOTO	NUM_PRESSED
	GOTO	DEBOUNCE
	GOTO	UPDAC
	GOTO	SENDDAC
	GOTO	STUFF
	GOTO	CLEAR
	GOTO	INIT
	GOTO	BLANK
	GOTO	MAIN
	GOTO	OUT595
	GOTO	JMPF0
	GOTO	JMPF1
	GOTO	JMPF2
	GOTO	JMPF3
	GOTO	JMPB0
	GOTO	JMPB1
	GOTO	JMPB2
	GOTO	JMPB3
        RES     64-31
        GOTO    INIT

; ----------   INTERRUPT SUBROUTINE   ----------

ISR
        RES     1               ; NOP
        BCF     PORTC,TALLY

        MOVF    PCLATH,W        ; SAVE BACKGROUD PAGE
        MOVWF   PCH_ISR
        MOVF    FSR,W           ; SAVE FSR
        MOVWF   FSR_ISR
                                ; add power fail & tx/rx
        IFCLR   INTCON,T0IF     ; ONLY USE TIMER0 INTERRUPTS
        GOTO    ISR_L3          ; IGNOR ALL OTHERS

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
        XORWF   ADR0,F          ; BEFOR START NEXT A/D SAMPLE.
        MOVWF   ADR0
        IFNZ
        BSF     SIG,DACNEW0
        NOP
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
        XORWF   ADR1,F
        MOVWF   ADR1
        IFNZ
        BSF     SIG,DACNEW1

        BSF     PORTC,TALLY
        INCF    FLP,F
        MOVF    FLP,W
        CALL    EXECUTE         ; DO NEXT FORGROUND TASK
ISR_L3
        BCF     ADCON0,CHS0     ; SELECT PORTA0 FOR A/D
        MOVF    FSR_ISR,W       ; RESTORE FSR
        MOVWF   FSR
        MOVF    PCH_ISR,W       ; RESTORE PCLATH
        MOVWF   PCLATH
        SWAPF   ST_ISR,W
        MOVWF   STATUS          ; RESTORE STATUS
        SWAPF   W_ISR,F
        SWAPF   W_ISR,W         ; RESTORE W
        RETFIE

; ----------   ROUTINES   ----------

CHK_ON
        CALL    UPDAC

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

        MOVLW   (1<<CHONC)
        IFSET   CHONKS,PRESS    ; IF PRESSED THEN TOGGLE
        XORWF   PORTA,F         ; CONTROL OUTPUT
        IFSET   CHONES,PRESS
        XORWF   PORTA,F

        IFSET   CHONKS,PRESS
        BSF     SIG,DACNEW0      ; SEND LEVEL TO DAC
        IFSET   CHONES,PRESS
        BSF     SIG,DACNEW0      ; SEND LEVEL TO DAC

        MOVLW   COL1            ; SET COL1 LOW
        MOVWF   PORTB
        RETURN
CHK_COL1
        IFCLR   PORTB,ROW1      ; CHECK COL1
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
        RETURN
CHK_COL2
        IFCLR   PORTB,ROW1      ; CHECK COL2
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
        RETURN
CHK_COL3
        IFCLR   PORTB,ROW1      ; CHECK COL3
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
        RETURN
CHK_COL4
        IFCLR   PORTB,ROW1      ; CHECK COL4
        INCF    3+KTAB,F
        IFCLR   PORTB,ROW2
        INCF    2+KTAB,F
        IFCLR   PORTB,ROW3
        INCF    1+KTAB,F
        IFCLR   PORTB,ROW4
        INCF    0+KTAB,F
        CALL    UPDAC
        RETURN
NUM_PRESSED
        CALL    UPDAC
        CLRF    TEMP1           ; COUNT NUMBER OF KEYS PRESSED
        IFINC   0,TEMP1
        IFINC   1,TEMP1
        IFINC   2,TEMP1
        IFINC   3,TEMP1
        IFINC   4,TEMP1
        IFINC   5,TEMP1
        IFINC   6,TEMP1
        IFINC   7,TEMP1
        IFINC   8,TEMP1
        IFINC   9,TEMP1
        IFINC   10,TEMP1
        IFINC   11,TEMP1
        IFINC   12,TEMP1
        IFINC   13,TEMP1
        IFINC   14,TEMP1
        IFINC   15,TEMP1
        MOVLW   3               ; TEST FOR MORE THAN TWO PRESSED
        SUBWF   TEMP1,W
        IFCC                    ; IF 2 OR LESS PRESSED THEN RETURN
        RETURN
        CALL    CLEAR           ; ELSE CLEAR DEBOUNCE STATES
        SKIP_F                  ; AND SKIP NEXT FORGROUND CALL
        RETURN

DEBOUNCE
        CALL    UPDAC
        MOVLW   KTAB            ; DEBOUNCE KEYS
        MOVWF   FSR
DEBOUNCE_L1
        MOVF    INDF,W
        CALL    NEXT1           ; CALL DEBOUNCE STATE MACHINE
        MOVWF   INDF            ; UPDATE STATE OF KEY
        RLF     INDF,W          ; SHIFT PRESS BIT INTO CARRY
        RLF     TEMP2,F
        RLF     TEMP1,F         ; KEEP TRACK OF THOSE THAT CHANGE
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    DEBOUNCE_L1
        MOVF    TEMP1,W         ; SAVE BITMAP OF PRESSED KEYS
        IORWF   PRESS1,F
        MOVF    TEMP2,W
        IORWF   PRESS2,F
        IFSET   KTAB+8,REL      ; CHECK IF EOT RELEASED
        BSF     SIG,EOTREL
        RETURN

; ----------   UPDATE DAC   ----------

UPDAC
        IFCLR   SIG,DACNEW0
        RETURN                  ; DO NOTHING IF NO CHANGE
        BCF     SIG,DACNEW0

        IFSET   PORTA,CHONC
        GOTO    UPDAC_L1        ; ZERO DAC IF CHANNEL OFF

        MOVF    ADR0,W          ; LOOK UP FADER VALUE
        MOVWF   TEMP1
        CALL    GETLSB
        MOVWF   DACL
        CALL    GETMSB
        MOVWF   DACH

        IFCLR   OUT1,1
        GOTO    UPDAC_L3        ; MASTER IGNORES GROUP FADER VALUE
        COMF    OUT1,W          ; SLAVE MUST CHECK IF ANY GROUP
        ANDLW   $3C
        IFZ
        GOTO    UPDAC_L3        ; NO GROUP SO IGNORE GROUP FADER VALUE

        MOVLW   IH15LO          ; SUBTRACT INHAND REFERENCE
        SUBWF   DACL,F
        IFCC
        DECF    DACH,F
        MOVLW   IH15HI
        SUBWF   DACH,F

        MOVF    ADR1,W          ; ADD GROUP FADER VALUE
        MOVWF   TEMP1
        CALL    GETLSB
        ADDWF   DACL,F
        IFCS
        INCF    DACH,F
        CALL    GETMSB
        ADDWF   DACH,F

        IFCLR   DACH,7          ; IF NEGATIVE ENTER ZERO
        GOTO    UPDAC_L2
UPDAC_L1
        CLRF    DACL            ; LOWER LIMIT OF $0000
        CLRF    DACH
        GOTO    UPDAC_L3
UPDAC_L2
        MOVF    DACH,W
        ANDLW   $70             ; UPPER LIMIT OF $0FFF
        IFZ
        GOTO    UPDAC_L3
        MOVLW   $FF
        MOVWF   DACL
        MOVLW   $0F
        MOVWF   DACH
UPDAC_L3
        MOVLW   HIGH SUBS       ; SET PAGE FOR ISR
        MOVWF   PCLATH
SENDDAC
        MOVLW   CHIP1
        MOVWF   PORTB
        BCF     PORTB,GCS       ; UPDATE DAC OUTPUT

        TXBIT   DACH,3
        TXBIT   DACH,2
        TXBIT   DACH,1
        TXBIT   DACH,0

        TXBIT   DACL,7
        TXBIT   DACL,6
        TXBIT   DACL,5
        TXBIT   DACL,4
        TXBIT   DACL,3
        TXBIT   DACL,2
        TXBIT   DACL,1
        TXBIT   DACL,0

        BSF     PORTB,GCS
        RETURN

; ----------   STUFF   ----------

STUFF
        BSF     OUT2,6
        IFSET   KTAB+9,KEYBIT
        BCF     OUT2,6          ; MMSOLO ON WHEN KEY HELD

        BSF     OUT2,7
        IFSET   KTAB+8,KEYBIT
        BCF     OUT2,7          ; EOT ON WHEN KEY HELD

        IFSET   SIG,EOTREL
        GOTO    STUFF_L1
        MOVF    PRESS1,W
        IORWF   PRESS2,W
        IFZ
        RETURN
STUFF_L1
        BCF     INTCON,GIE      ; DISABLE INTERRUPTS
        IFSET   INTCON,GIE
        GOTO    STUFF_L1

        MOVF    PRESS1,W        ; TOGGLE OUTPUTS WHOSE KEYS ARE PRESSED
        XORWF   OUT1,F
        MOVF    PRESS2,W
        XORWF   OUT2,F

        IFSET   SIG,EOTREL
        BSF     OUT1,7          ; RELEASE EOT -> PFL GOES OFF
        IFSET   PRESS2,7
        BSF     OUT1,7          ; PRESS EOT -> PFL GOES OFF

        BCF     SIG,EOTREL      ; CLEAR FLAGS SET BY ISR
        CLRF    PRESS1
        CLRF    PRESS2
        BSF     INTCON,GIE      ; RE-ENABLE INTERRUPTS
        RETURN

; ----------   CLEAR DEBOUNCE STATES   ----------

CLEAR
        MOVLW   KTAB
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
        MOVLW   $0F             ; SET DATA DIRECTION OF PORTS A, B & C
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

        BSF     PORTA,GMCNCL
        BCF     PORTC,OKAY

        MOVLW   HIGH SUBS
        MOVWF   PCLATH          ; SET PAGE FOR SUBROUTINES
        MOVLW   $C1
        MOVWF   ADCON0          ; SET UP A/D CONVERTER

        MOVLW   KTAB
        MOVWF   FSR
BLANK
        CLRF    INDF
        INCF    FSR,F
        IFSET   FSR,4
        GOTO    BLANK

        CLRF    PRESS1
        CLRF    PRESS2
        CLRF    CHONKS
        CLRF    CHONES
        CLRF    SIG
        MOVLW   $FF
        MOVWF   OUT1
        MOVWF   OUT2
        BCF     OUT2,5          ; TURN ON FADER INITIALY

LENGTH  EQU     23

        MOVLW   LISTSPACE
        MOVWF   FSR
        CLRF    I
SU_L1
        MOVF    I,W
        CALL    RTC
        MOVWF   INDF
        INCF    FSR,F
        INCF    I,F
        MOVLW   LENGTH
        SUBWF   I,W
        IFCC
        GOTO    SU_L1

        MOVLW   LISTSPACE
        MOVWF   FLT+0
        MOVWF   FLP
        DECF    FLP,F
        MOVLW   LISTSPACE+LENGTH-2
        MOVWF   BLT+0
        MOVWF   BLP
        DECF    BLP,F

        CLRF    INTCON          ; START UP INTERRUPTS
        BSF     INTCON,T0IE
        BSF     INTCON,GIE

        RES     1               ; NOP
MAIN
        INCF    BLP,F
        MOVF    BLP,W
        CALL    EXECUTE
        GOTO    MAIN

; ----------   .   ----------

;READEE
;        CALL    EEOP            ; SEND OPCODE & ADDRESS
;        BANK1
;        BCF     TRISC,SDATA
;        BANK0
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;        RXBIT   EEMSB
;
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        RXBIT   EELSB
;        BCF     PORTC,EECS
;        BANK1
;        BSF     TRISC,SDATA
;        BANK0
;        RETURN
;
;EEOP
;        BSF     PORTC,EECS
;        BSF     PORTC,SDATA     ; START BIT
;        BCF     PORTC,SCLK
;        BSF     PORTC,SCLK
;        TXBIT   EECNT,7         ; OPCODE
;        TXBIT   EECNT,6
;
;        TXBIT   EECNT,5         ; ADDRESS
;        TXBIT   EECNT,4
;        TXBIT   EECNT,3
;        TXBIT   EECNT,2
;        TXBIT   EECNT,1
;        TXBIT   EECNT,0
;        RETURN
;
;BOOT
;        BANK0
;        MOVLW   LISTSPACE
;        MOVWF   FSR
;        MOVLW   $80
;        MOVWF   EECNT
;BOOT_L1
;        CALL    READEE
;        INCF    EECNT,F
;        MOVF    EEMSB,W
;        MOVWF   INDF
;        INCF    INDF,F
;        MOVF    EELSB,W
;        MOVWF   INDF
;        INCF    INDF,F
;        IFNZ
;        GOTO    BOOT_L1
;        RETURN
;

; ----------   UPDATE OUTPUTS   ----------

OUT595
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
        RETURN

; ----------   FORGROUND JUMPS   ----------

JMPF0   JUMP_F  0
JMPF1   JUMP_F  1
JMPF2   JUMP_F  2
JMPF3   JUMP_F  3

; ----------   BACKGROUND JUMPS   ----------

JMPB0   JUMP_B  0
JMPB1   JUMP_B  1
JMPB2   JUMP_B  2
JMPB3   JUMP_B  3

; ----------   .   ----------

        END
