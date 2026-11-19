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
0057                        ORG     $000
0058                
0059 0000 0B50      TXGAIN  GOTO    TXB1
0060 0001 0B42      TXDIS   GOTO    TXB2
0061                
0062                ; ----------   NEXT STATE TABLE1   ----------
0063                
0064 0002 0E0F      NEXT1   ANDLW   $0F
0065 0003 01E2              ADDWF   PC
0066 0004 0800              RETLW   $00
0067 0005 0844              RETLW   $44     ;DEC
0068 0006 0888              RETLW   $88     ;INC
0069 0007 0800              RETLW   $00
0070                
0071 0008 0880              RETLW   $80     ;INC
0072 0009 0804              RETLW   $04
0073 000A 0804              RETLW   $04
0074 000B 084C              RETLW   $4C     ;DEC
0075                
0076 000C 0840              RETLW   $40     ;DEC
0077 000D 0808              RETLW   $08
0078 000E 0808              RETLW   $08
0079 000F 088C              RETLW   $8C     ;INC
0080                
0081 0010 080C              RETLW   $0C
0082 0011 0884              RETLW   $84     ;INC
0083 0012 0848              RETLW   $48     ;DEC
0084 0013 080C              RETLW   $0C
0085                
0086                ; ----------   DIGITS LOOKUP TABLE2   ----------
0087                
0088 0014 0E0F      DIGITS  ANDLW   $0F
0089 0015 01E2              ADDWF   PC
0090 0016 083F              RETLW   $3F             ; 0
0091 0017 0806              RETLW   $06             ; 1
0092 0018 085B              RETLW   $5B             ; 2
0093 0019 084F              RETLW   $4F             ; 3
0094                
0095 001A 0866              RETLW   $66             ; 4
0096 001B 086D              RETLW   $6D             ; 5
0097 001C 087D              RETLW   $7D             ; 6
0098 001D 0807              RETLW   $07             ; 7
0099                
0100 001E 087F              RETLW   $7F             ; 8
0101 001F 086F              RETLW   $6F             ; 9
0102 0020 0877              RETLW   $77             ; A
0103 0021 087C              RETLW   $7C             ; B
0104                
0105 0022 0839              RETLW   $39             ; C
0106 0023 085E              RETLW   $5E             ; D
0107 0024 0879              RETLW   $79             ; E
0108 0025 0871              RETLW   $71             ; F
0109                
0110                ; ----------   TRANSLATION TABLE3   ----------
0111                
0112 0026 0E7F      TRANS3  ANDLW   $7F
0113 0027 01E2              ADDWF   PC
0114 0028 0800              RETLW   $00
0115 0029 0801              RETLW   $01
0116 002A 0802              RETLW   $02
0117 002B 0803              RETLW   $03
0118 002C 0804              RETLW   $04
0119 002D 0805              RETLW   $05
0120 002E 0806              RETLW   $06
0121 002F 0807              RETLW   $07
0122                
0123 0030 0808              RETLW   $08
0124 0031 0809              RETLW   $09
0125 0032 0810              RETLW   $10
0126 0033 0811              RETLW   $11
0127 0034 0812              RETLW   $12
0128 0035 0813              RETLW   $13
0129 0036 0814              RETLW   $14
0130 0037 0815              RETLW   $15
0131                
0132 0038 0816              RETLW   $16
0133 0039 0817              RETLW   $17
0134 003A 0818              RETLW   $18
0135 003B 0819              RETLW   $19
0136 003C 0820              RETLW   $20
0137 003D 0821              RETLW   $21
0138 003E 0822              RETLW   $22
0139 003F 0823              RETLW   $23
0140                
0141 0040 0824              RETLW   $24
0142 0041 0825              RETLW   $25
0143 0042 0826              RETLW   $26
0144 0043 0827              RETLW   $27
0145 0044 0828              RETLW   $28
0146 0045 0829              RETLW   $29
0147 0046 0830              RETLW   $30
0148 0047 0831              RETLW   $31
0149                
0150 0048 0832              RETLW   $32
0151 0049 0833              RETLW   $33
0152 004A 0834              RETLW   $34
0153 004B 0835              RETLW   $35
0154 004C 0836              RETLW   $36
0155 004D 0837              RETLW   $37
0156 004E 0838              RETLW   $38
0157 004F 0839              RETLW   $39
0158                
0159 0050 0840              RETLW   $40
0160 0051 0841              RETLW   $41
0161 0052 0842              RETLW   $42
0162 0053 0843              RETLW   $43
0163 0054 0844              RETLW   $44
0164 0055 0845              RETLW   $45
0165 0056 0846              RETLW   $46
0166 0057 0847              RETLW   $47
0167                
0168 0058 0848              RETLW   $48
0169 0059 0849              RETLW   $49
0170 005A 0850              RETLW   $50
0171 005B 0851              RETLW   $51
0172 005C 0852              RETLW   $52
0173 005D 0853              RETLW   $53
0174 005E 0854              RETLW   $54
0175 005F 0855              RETLW   $55
0176                
0177 0060 0856              RETLW   $56
0178 0061 0857              RETLW   $57
0179 0062 0858              RETLW   $58
0180 0063 0859              RETLW   $59
0181 0064 0860              RETLW   $60
0182 0065 0861              RETLW   $61
0183 0066 0862              RETLW   $62
0184 0067 0863              RETLW   $63
0185                
0186 0068 0864              RETLW   $64
0187 0069 0865              RETLW   $65
0188 006A 0866              RETLW   $66
0189 006B 0867              RETLW   $67
0190 006C 0868              RETLW   $68
0191 006D 0869              RETLW   $69
0192 006E 0870              RETLW   $70
0193 006F 0871              RETLW   $71
0194                
0195 0070 0872              RETLW   $72
0196 0071 0873              RETLW   $73
0197 0072 0874              RETLW   $74
0198 0073 0875              RETLW   $75
0199 0074 0876              RETLW   $76
0200 0075 0877              RETLW   $77
0201 0076 0878              RETLW   $78
0202 0077 0879              RETLW   $79
0203                
0204 0078 0880              RETLW   $80
0205 0079 0881              RETLW   $81
0206 007A 0882              RETLW   $82
0207 007B 0883              RETLW   $83
0208 007C 0884              RETLW   $84
0209 007D 0885              RETLW   $85
0210 007E 0886              RETLW   $86
0211 007F 0887              RETLW   $87
0212                
0213 0080 0888              RETLW   $88
0214 0081 0889              RETLW   $89
0215 0082 0890              RETLW   $90
0216 0083 0891              RETLW   $91
0217 0084 0892              RETLW   $92
0218 0085 0893              RETLW   $93
0219 0086 0894              RETLW   $94
0220 0087 0895              RETLW   $95
0221                
0222 0088 08FF              RETLW   $FF
0223                
0224                ; ----------   CODE   ----------
0225                
0226                        ORG     $101
0227                
0228 0101 0C0F              MOVLW   $0F
0229 0102 0005              TRIS    PORTA
0230                
0231 0103 0C0F              MOVLW   $0F
0232 0104 0026              MOVWF   PORTB
0233 0105 0C80              MOVLW   $80
0234 0106 0006              TRIS    PORTB
0235                
0236 0107 0068              CLRF    LEVEL
0237 0108 0069              CLRF    STATE1
0238                
0239 0109 0B1F              GOTO    OUTPUT
0240                
0241 010A 0205      MAIN    MOVF    PORTA,W
0242 010B 0E03              ANDLW   $03
0243 010C 0109              IORWF   STATE1,W
0244 010D 0902              CALL    NEXT1
0245 010E 0029              MOVWF   STATE1
0246                
0247 010F 07E9      INC_L   BTFSS   STATE1,7
0248 0110 0B16              GOTO    DEC_L
0249                
0250 0111 0CFF              MOVLW   255
0251 0112 0088              SUBWF   LEVEL,W
0252 0113 0703              BTFSS   STATUS,C
0253 0114 02A8              INCF    LEVEL           ; LEVEL < 255
0254 0115 0B1F              GOTO    OUTPUT          ; LEVEL >= 255
0255                
0256 0116 07C9      DEC_L   BTFSS   STATE1,6
0257 0117 0B1D              GOTO    CHECK
0258                
0259 0118 0C01              MOVLW   1
0260 0119 0088              SUBWF   LEVEL,W
0261 011A 0603              BTFSC   STATUS,C
0262 011B 00E8              DECF    LEVEL           ; LEVEL >= 1
0263 011C 0B1F              GOTO    OUTPUT          ; LEVEL < 1
0264                
0265 011D 06E6      CHECK   BTFSC   PORTB,TESTB
0266 011E 0B0A              GOTO    MAIN
0267                
0268 011F 0208      OUTPUT  MOVF    LEVEL,W
0269 0120 0900              CALL    TXGAIN
0270 0121 0208              MOVF    LEVEL,W
0271 0122 0900              CALL    TXGAIN
0272                
0273 0123 0546              BSF     PORTB,LOAD1
0274                
0275                DISPLAY
0276 0124 0CC0              MOVLW   192
0277 0125 0088              SUBWF   LEVEL,W
0278 0126 002C              MOVWF   TEMP
0279 0127 0703              BTFSS   STATUS,C
0280 0128 0B2C              GOTO    MINUS           ; LEVEL < 192
0281                                                ; LEVEL >= 192
0282                PLUS
0283 0129 0C26              MOVLW   $26
0284 012A 0901              CALL    TXDIS
0285 012B 0B30              GOTO    OPNUM
0286                
0287 012C 0C24      MINUS   MOVLW   $24
0288 012D 0901              CALL    TXDIS
0289 012E 026C              COMF    TEMP
0290 012F 02AC              INCF    TEMP
0291                
0292 0130 030C      OPNUM   RRF     TEMP,W
0293 0131 0926              CALL    TRANS3
0294 0132 002D              MOVWF   NUM
0295 0133 038D              SWAPF   NUM,W
0296 0134 0914              CALL    DIGITS
0297 0135 0901              CALL    TXDIS
0298 0136 020D              MOVF    NUM,W
0299 0137 0914              CALL    DIGITS
0300 0138 0901              CALL    TXDIS
0301                
0302 0139 0C00              MOVLW   0
0303 013A 060C              BTFSC   TEMP,0
0304 013B 0C05              MOVLW   5
0305 013C 0914              CALL    DIGITS
0306 013D 0901              CALL    TXDIS
0307                
0308 013E 05C6              BSF     PORTB,LOAD2
0309 013F 0000              NOP
0310 0140 04C6              BCF     PORTB,LOAD2
0311                
0312 0141 0B0A              GOTO    MAIN
0313                
0314                ; ----------   TXB2 SUBROUTINE   ----------
0315                
0316 0142 002A      TXB2    MOVWF   TXSR
0317 0143 04C6              BCF     PORTB,LOAD2
0318 0144 0C08              MOVLW   8
0319 0145 002B              MOVWF   I
0320                
0321 0146 06EA      SHIFT2  BTFSC   TXSR,7
0322 0147 0586              BSF     PORTB,DATA2
0323 0148 07EA              BTFSS   TXSR,7
0324 0149 0486              BCF     PORTB,DATA2
0325                
0326 014A 05A6              BSF     PORTB,CLK2
0327 014B 036A              RLF     TXSR            ; DO SOMETHING
0328 014C 04A6              BCF     PORTB,CLK2
0329                
0330 014D 02EB              DECFSZ  I
0331 014E 0B46              GOTO    SHIFT2
0332 014F 0800              RETLW   0
0333                
0334                ; ----------   TXB1 SUBROUTINE   ----------
0335                
0336 0150 002A      TXB1    MOVWF   TXSR
0337 0151 0446              BCF     PORTB,LOAD1
0338 0152 0C08              MOVLW   8
0339 0153 002B              MOVWF   I
0340                
0341 0154 06EA      SHIFT1  BTFSC   TXSR,7
0342 0155 0506              BSF     PORTB,DATA1
0343 0156 07EA              BTFSS   TXSR,7
0344 0157 0406              BCF     PORTB,DATA1
0345                
0346 0158 0426              BCF     PORTB,CLK1
0347 0159 036A              RLF     TXSR            ; DO SOMETHING
0348 015A 0526              BSF     PORTB,CLK1
0349                
0350 015B 02EB              DECFSZ  I
0351 015C 0B54              GOTO    SHIFT1
0352 015D 0800              RETLW   0
0353                
0354                        ORG     PIC54
0355 01FF 0B00      RESET   GOTO    $100


Number of errors 0
