PIC16C5X ASSEMBLER   1.0
E D Technical Publications  1993
0001                ; ----------   PIC16C5X HEADER   ----------
0002                
0003      0000       W       EQU     0
0004                
0005                ; RESET ADDRESSES
0006                
0007      01FF       PIC54   EQU     $1FF
0008      01FF       PIC55   EQU     $1FF
0009      03FF       PIC56   EQU     $3FF
0010      07FF       PIC57   EQU     $7FF
0011                
0012                ; STATUS WORD REGISTER f3
0013                
0014      0000       C       EQU     0
0015      0001       DC      EQU     1
0016      0002       Z       EQU     2
0017      0003       PD      EQU     3
0018      0004       TO      EQU     4
0019      0005       PA0     EQU     5
0020      0006       PA1     EQU     6
0021      0007       PA2     EQU     7
0022                
0023                ; OPERATIONAL REGISTER FILES
0024                
0025      0000       IND     EQU     00
0026      0001       RTCC    EQU     01
0027      0002       PC      EQU     02
0028      0003       STATUS  EQU     03
0029      0004       FSR     EQU     04
0030      0005       PORTA   EQU     05
0031      0006       PORTB   EQU     06
0032      0007       PORTC   EQU     07
0033                
0034                ; ----------   END HEADER   ----------
0035                
0036      0008       LEVEL   EQU     08
0037      0009       STATE1  EQU     09              ; ENCODER STATE
0038      000A       TXSR    EQU     10              ; TX SHIFT REGISTER
0039      000B       I       EQU     11
0040      000C       TEMP    EQU     12
0041      000D       NUM     EQU     13
0042                
0043                ; ----------   PORTB BITS   ----------
0044                
0045      0000       DATA1   EQU     0
0046      0001       CLK1    EQU     1
0047      0002       LOAD1   EQU     2
0048                
0049      0004       DATA2   EQU     4
0050      0005       CLK2    EQU     5
0051      0006       LOAD2   EQU     6
0052                
0053      0007       TESTB   EQU     7               ; OUTPUT LEVEL IF BIT LOW
0054                
0055                ; ----------   JUMP TABLE   ----------
0056                
0057                        ORG     $088
0058                
0059 0088 0B50      TXGAIN  GOTO    TXB1
0060 0089 0B42      TXDIS   GOTO    TXB2
0061                
0062                ; ----------   NEXT STATE TABLE1   ----------
0063                
0064      0001       NEXT1   EQU     $001
0065                
0066                ; ----------   DIGITS LOOKUP TABLE2   ----------
0067                
0068      0013       DIGITS  EQU     $013
0069                
0070                ; ----------   TRANSLATION TABLE3   ----------
0071                
0072      0025       TRANS3  EQU     $25
0073                
0074                ; ----------   CODE   ----------
0075                
0076                        ORG     $101
0077                
0078 0101 0C0F              MOVLW   $0F
0079 0102 0005              TRIS    PORTA
0080                
0081 0103 0C0F              MOVLW   $0F
0082 0104 0026              MOVWF   PORTB
0083 0105 0C80              MOVLW   $80
0084 0106 0006              TRIS    PORTB
0085                
0086 0107 0068              CLRF    LEVEL
0087 0108 0069              CLRF    STATE1
0088                
0089 0109 0B1F              GOTO    OUTPUT
0090                
0091 010A 0205      MAIN    MOVF    PORTA,W
0092 010B 0E03              ANDLW   $03
0093 010C 0109              IORWF   STATE1,W
0094 010D 0901              CALL    NEXT1
0095 010E 0029              MOVWF   STATE1
0096                
0097 010F 07E9      INC_L   BTFSS   STATE1,7
0098 0110 0B16              GOTO    DEC_L
0099                
0100 0111 0CFF              MOVLW   255
0101 0112 0088              SUBWF   LEVEL,W
0102 0113 0703              BTFSS   STATUS,C
0103 0114 02A8              INCF    LEVEL           ; LEVEL < 255
0104 0115 0B1F              GOTO    OUTPUT          ; LEVEL >= 255
0105                
0106 0116 07C9      DEC_L   BTFSS   STATE1,6
0107 0117 0B1D              GOTO    CHECK
0108                
0109 0118 0C01              MOVLW   1
0110 0119 0088              SUBWF   LEVEL,W
0111 011A 0603              BTFSC   STATUS,C
0112 011B 00E8              DECF    LEVEL           ; LEVEL >= 1
0113 011C 0B1F              GOTO    OUTPUT          ; LEVEL < 1
0114                
0115 011D 06E6      CHECK   BTFSC   PORTB,TESTB
0116 011E 0B0A              GOTO    MAIN
0117                
0118 011F 0208      OUTPUT  MOVF    LEVEL,W
0119 0120 0988              CALL    TXGAIN
0120 0121 0208              MOVF    LEVEL,W
0121 0122 0988              CALL    TXGAIN
0122                
0123 0123 0546              BSF     PORTB,LOAD1
0124                
0125                DISPLAY
0126 0124 0CC0              MOVLW   192
0127 0125 0088              SUBWF   LEVEL,W
0128 0126 002C              MOVWF   TEMP
0129 0127 0703              BTFSS   STATUS,C
0130 0128 0B2C              GOTO    MINUS           ; LEVEL < 192
0131                                                ; LEVEL >= 192
0132                PLUS
0133 0129 0C26              MOVLW   $26
0134 012A 0989              CALL    TXDIS
0135 012B 0B30              GOTO    OPNUM
0136                
0137 012C 0C24      MINUS   MOVLW   $24
0138 012D 0989              CALL    TXDIS
0139 012E 026C              COMF    TEMP
0140 012F 02AC              INCF    TEMP
0141                
0142 0130 030C      OPNUM   RRF     TEMP,W
0143 0131 0925              CALL    TRANS3
0144 0132 002D              MOVWF   NUM
0145 0133 038D              SWAPF   NUM,W
0146 0134 0913              CALL    DIGITS
0147 0135 0989              CALL    TXDIS
0148 0136 020D              MOVF    NUM,W
0149 0137 0913              CALL    DIGITS
0150 0138 0989              CALL    TXDIS
0151                
0152 0139 0C00              MOVLW   0
0153 013A 060C              BTFSC   TEMP,0
0154 013B 0C05              MOVLW   5
0155 013C 0913              CALL    DIGITS
0156 013D 0989              CALL    TXDIS
0157                
0158 013E 05C6              BSF     PORTB,LOAD2
0159 013F 0000              NOP
0160 0140 04C6              BCF     PORTB,LOAD2
0161                
0162 0141 0B0A              GOTO    MAIN
0163                
0164                ; ----------   TXB2 SUBROUTINE   ----------
0165                
0166 0142 002A      TXB2    MOVWF   TXSR
0167 0143 04C6              BCF     PORTB,LOAD2
0168 0144 0C08              MOVLW   8
0169 0145 002B              MOVWF   I
0170                
0171 0146 06EA      SHIFT2  BTFSC   TXSR,7
0172 0147 0586              BSF     PORTB,DATA2
0173 0148 07EA              BTFSS   TXSR,7
0174 0149 0486              BCF     PORTB,DATA2
0175                
0176 014A 05A6              BSF     PORTB,CLK2
0177 014B 036A              RLF     TXSR            ; DO SOMETHING
0178 014C 04A6              BCF     PORTB,CLK2
0179                
0180 014D 02EB              DECFSZ  I
0181 014E 0B46              GOTO    SHIFT2
0182 014F 0800              RETLW   0
0183                
0184                ; ----------   TXB1 SUBROUTINE   ----------
0185                
0186 0150 002A      TXB1    MOVWF   TXSR
0187 0151 0446              BCF     PORTB,LOAD1
0188 0152 0C08              MOVLW   8
0189 0153 002B              MOVWF   I
0190                
0191 0154 06EA      SHIFT1  BTFSC   TXSR,7
0192 0155 0506              BSF     PORTB,DATA1
0193 0156 07EA              BTFSS   TXSR,7
0194 0157 0406              BCF     PORTB,DATA1
0195                
0196 0158 0426              BCF     PORTB,CLK1
0197 0159 036A              RLF     TXSR            ; DO SOMETHING
0198 015A 0526              BSF     PORTB,CLK1
0199                
0200 015B 02EB              DECFSZ  I
0201 015C 0B54              GOTO    SHIFT1
0202 015D 0800              RETLW   0
0203                
0204                        ORG     PIC54
0205 01FF 0B00      RESET   GOTO    $100


Number of errors 0
