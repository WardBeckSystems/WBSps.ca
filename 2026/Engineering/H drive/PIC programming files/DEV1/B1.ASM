
        LIST    F=INHX8M,R=DEC,P=16C73
        ERRORLEVEL 0, -302
        INCLUDE "\PIC\SRC\P16C73.INC"
        INCLUDE "\PIC\SRC\MACROS.ASM"

; ----------   RAM   ----------

RAMBANK0 ORG     $20

W_ISR   RES     1               ; MIRRORED AT $A0

EECNT   RES     1
EEMSB   RES     1
EELSB   RES     1

RAMBANK1 ORG     $A0

        RES     1               ; MIRROR OF W_ISR

FLP     RES     1
BLP     RES     1
FDLT    RES     4
BDLT    RES     4

LISTSPACE

; ----------   MACROS   ----------

BANK0   MACRO
        BCF     STATUS,RP0
        ENDM

BANK1   MACRO
        BSF     STATUS,RP0
        ENDM

FLP_FDL MACRO   X
        MOVF    FDLT+X,W
        MOVWF   FLP
        GOTO    NEXT_F
        ENDM

BLP_BDL MACRO   X
        MOVF    BDLT+X,W
        MOVWF   BLP
        GOTO    NEXT_B
        ENDM

TXBIT   MACRO   FR,BIT
        IFSET   FR,BIT
        BSF     PORTC,SDATA
        IFCLR   FR,BIT
        BCF     PORTC,SDATA
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

RXBIT   MACRO   FR
        RLF     FR,F
        BCF     FR,0
        IFSET   PORTC,SDATA
        BSF     FR,0
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        ENDM

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

; ----------   .   ----------

EPROM   ORG     0

; ----------   KERNEL   ----------

DO_B
        BANK1
        MOVF    BLP,W
NEXT_B
        MOVWF   FSR
        INCF    BLP,F
        MOVF    INDF,W
DOP
        BCF     INTCON,GIE      ; need do disable interrupts
        IFSET   INTCON,GIE      ; befor doing ADDWF PCL,F
        GOTO    DOP
        GOTO    EXECUTE
DO_F
        BANK1                   ; do not need do disable
        MOVF    FLP,W           ; interrupts since we are
NEXT_F                          ; in the ISR
        MOVWF   FSR
        INCF    FLP,F
        MOVF    INDF,W
EXECUTE
        ANDLW   $7F
        ADDWF   PCL,F
        GOTO    BOB
        GOTO    ETC
        RES     128-2
        GOTO    RESET

; ----------   FORGROUND DYNAMIC LINKS   ----------

DL0_F   FLP_FDL 0
DL1_F   FLP_FDL 1
DL2_F   FLP_FDL 2
DL3_F   FLP_FDL 3

; ----------   BACKGROUND DYNAMIC LINKS   ----------

DL0_B   BLP_BDL 0
DL1_B   BLP_BDL 1
DL2_B   BLP_BDL 2
DL3_B   BLP_BDL 3

; ----------   .   ----------

READEE
        CALL    EEOP            ; SEND OPCODE & ADDRESS
        BANK1
        BCF     TRISC,SDATA
        BANK0
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB
        RXBIT   EEMSB

        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        RXBIT   EELSB
        BCF     PORTC,EECS
        BANK1
        BSF     TRISC,SDATA
        BANK0
        RETURN

EEOP
        BSF     PORTC,EECS
        BSF     PORTC,SDATA     ; START BIT
        BCF     PORTC,SCLK
        BSF     PORTC,SCLK
        TXBIT   EECNT,7         ; OPCODE
        TXBIT   EECNT,6

        TXBIT   EECNT,5         ; ADDRESS
        TXBIT   EECNT,4
        TXBIT   EECNT,3
        TXBIT   EECNT,2
        TXBIT   EECNT,1
        TXBIT   EECNT,0
        RETURN

BOOT
        BANK0
        MOVLW   LISTSPACE
        MOVWF   FSR
        MOVLW   $80
        MOVWF   EECNT
BOOT_L1
        CALL    READEE
        INCF    EECNT,F
        MOVF    EEMSB,W
        MOVWF   INDF
        INCF    INDF,F
        MOVF    EELSB,W
        MOVWF   INDF
        INCF    INDF,F
        IFNZ
        GOTO    BOOT_L1
        RETURN

; ----------   .   ----------

BOB
ETC
RESET
        END
