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
0043                ; ----------   PORT B BITS   ----------
0044                
0045      0004       DATA2   EQU     4
0046      0005       CLK2    EQU     5
0047      0006       LOAD2   EQU     6
0048                
0049                ; ----------   JUMP TABLE   ----------
0050                
0051                        ORG     $000
0052                
0053 0000 0BE2      TXBYTE  GOTO    TXB
0054                
0055                ; ----------   NEXT STATE TABLE1   ----------
0056                
0057 0001 0E0F      NEXT1   ANDLW   $0F
0058 0002 01E2              ADDWF   PC
0059 0003 0800              RETLW   $00
0060 0004 0844              RETLW   $44     ;DEC
0061 0005 0888              RETLW   $88     ;INC
0062 0006 0800              RETLW   $00
0063                
0064 0007 0880              RETLW   $80     ;INC
0065 0008 0804              RETLW   $04
0066 0009 0804              RETLW   $04
0067 000A 084C              RETLW   $4C     ;DEC
0068                
0069 000B 0840              RETLW   $40     ;DEC
0070 000C 0808              RETLW   $08
0071 000D 0808              RETLW   $08
0072 000E 088C              RETLW   $8C     ;INC
0073                
0074 000F 080C              RETLW   $0C
0075 0010 0884              RETLW   $84     ;INC
0076 0011 0848              RETLW   $48     ;DEC
0077 0012 080C              RETLW   $0C
0078                
0079                ; ----------   DIGITS LOOKUP TABLE2   ----------
0080                
0081 0013 0E0F      DIGITS  ANDLW   $0F
0082 0014 01E2              ADDWF   PC
0083 0015 083F              RETLW   $3F             ; 0
0084 0016 0806              RETLW   $06             ; 1
0085 0017 085B              RETLW   $5B             ; 2
0086 0018 084F              RETLW   $4F             ; 3
0087                
0088 0019 0866              RETLW   $66             ; 4
0089 001A 086D              RETLW   $6D             ; 5
0090 001B 087D              RETLW   $7D             ; 6
0091 001C 0807              RETLW   $07             ; 7
0092                
0093 001D 087F              RETLW   $7F             ; 8
0094 001E 086F              RETLW   $6F             ; 9
0095 001F 0877              RETLW   $77             ; A
0096 0020 087C              RETLW   $7C             ; B
0097                
0098 0021 0839              RETLW   $39             ; C
0099 0022 085E              RETLW   $5E             ; D
0100 0023 0879              RETLW   $79             ; E
0101 0024 0871              RETLW   $71             ; F
0102                
0103                ; ----------   TRANSLATION TABLE3   ----------
0104                
0105 0025 0E7F      TRANS3  ANDLW   $7F
0106 0026 01E2              ADDWF   PC
0107 0027 0800              RETLW   $00
0108 0028 0801              RETLW   $01
0109 0029 0802              RETLW   $02
0110 002A 0803              RETLW   $03
0111 002B 0804              RETLW   $04
0112 002C 0805              RETLW   $05
0113 002D 0806              RETLW   $06
0114 002E 0807              RETLW   $07
0115                
0116 002F 0808              RETLW   $08
0117 0030 0809              RETLW   $09
0118 0031 0810              RETLW   $10
0119 0032 0811              RETLW   $11
0120 0033 0812              RETLW   $12
0121 0034 0813              RETLW   $13
0122 0035 0814              RETLW   $14
0123 0036 0815              RETLW   $15
0124                
0125 0037 0816              RETLW   $16
0126 0038 0817              RETLW   $17
0127 0039 0818              RETLW   $18
0128 003A 0819              RETLW   $19
0129 003B 0820              RETLW   $20
0130 003C 0821              RETLW   $21
0131 003D 0822              RETLW   $22
0132 003E 0823              RETLW   $23
0133                
0134 003F 0824              RETLW   $24
0135 0040 0825              RETLW   $25
0136 0041 0826              RETLW   $26
0137 0042 0827              RETLW   $27
0138 0043 0828              RETLW   $28
0139 0044 0829              RETLW   $29
0140 0045 0830              RETLW   $30
0141 0046 0831              RETLW   $31
0142                
0143 0047 0832              RETLW   $32
0144 0048 0833              RETLW   $33
0145 0049 0834              RETLW   $34
0146 004A 0835              RETLW   $35
0147 004B 0836              RETLW   $36
0148 004C 0837              RETLW   $37
0149 004D 0838              RETLW   $38
0150 004E 0839              RETLW   $39
0151                
0152 004F 0840              RETLW   $40
0153 0050 0841              RETLW   $41
0154 0051 0842              RETLW   $42
0155 0052 0843              RETLW   $43
0156 0053 0844              RETLW   $44
0157 0054 0845              RETLW   $45
0158 0055 0846              RETLW   $46
0159 0056 0847              RETLW   $47
0160                
0161 0057 0848              RETLW   $48
0162 0058 0849              RETLW   $49
0163 0059 0850              RETLW   $50
0164 005A 0851              RETLW   $51
0165 005B 0852              RETLW   $52
0166 005C 0853              RETLW   $53
0167 005D 0854              RETLW   $54
0168 005E 0855              RETLW   $55
0169                
0170 005F 0856              RETLW   $56
0171 0060 0857              RETLW   $57
0172 0061 0858              RETLW   $58
0173 0062 0859              RETLW   $59
0174 0063 0860              RETLW   $60
0175 0064 0861              RETLW   $61
0176 0065 0862              RETLW   $62
0177 0066 0863              RETLW   $63
0178                
0179 0067 0864              RETLW   $64
0180 0068 0865              RETLW   $65
0181 0069 0866              RETLW   $66
0182 006A 0867              RETLW   $67
0183 006B 0868              RETLW   $68
0184 006C 0869              RETLW   $69
0185 006D 0870              RETLW   $70
0186 006E 0871              RETLW   $71
0187                
0188 006F 0872              RETLW   $72
0189 0070 0873              RETLW   $73
0190 0071 0874              RETLW   $74
0191 0072 0875              RETLW   $75
0192 0073 0876              RETLW   $76
0193 0074 0877              RETLW   $77
0194 0075 0878              RETLW   $78
0195 0076 0879              RETLW   $79
0196                
0197 0077 0880              RETLW   $80
0198 0078 0881              RETLW   $81
0199 0079 0882              RETLW   $82
0200 007A 0883              RETLW   $83
0201 007B 0884              RETLW   $84
0202 007C 0885              RETLW   $85
0203 007D 0886              RETLW   $86
0204 007E 0887              RETLW   $87
0205                
0206 007F 0888              RETLW   $88
0207 0080 0889              RETLW   $89
0208 0081 0890              RETLW   $90
0209 0082 0891              RETLW   $91
0210 0083 0892              RETLW   $92
0211 0084 0893              RETLW   $93
0212 0085 0894              RETLW   $94
0213 0086 0895              RETLW   $95
0214                
0215 0087 08FF              RETLW   $FF
0216                
0217                ; ----------   CODE   ----------
0218                
0219                        ORG     $1A0
0220                
0221 01A0 0C0F              MOVLW   $0F
0222 01A1 0005              TRIS    PORTA
0223                
0224 01A2 0040              CLRW
0225 01A3 0026              MOVWF   PORTB
0226 01A4 0006              TRIS    PORTB
0227                
0228 01A5 0068              CLRF    LEVEL
0229 01A6 0069              CLRF    STATE1
0230                
0231 01A7 0040              CLRW
0232 01A8 0900              CALL    TXBYTE
0233 01A9 0040              CLRW
0234 01AA 0900              CALL    TXBYTE
0235 01AB 0040              CLRW
0236 01AC 0900              CALL    TXBYTE
0237 01AD 0040              CLRW
0238 01AE 0900              CALL    TXBYTE
0239                
0240 01AF 0205      MAIN    MOVF    PORTA,W
0241 01B0 0E03              ANDLW   $03
0242 01B1 0109              IORWF   STATE1,W
0243 01B2 0901              CALL    NEXT1
0244 01B3 0029              MOVWF   STATE1
0245                
0246 01B4 07E9      INC_L   BTFSS   STATE1,7
0247 01B5 0BBB              GOTO    DEC_L
0248                
0249 01B6 0CFF              MOVLW   255
0250 01B7 0088              SUBWF   LEVEL,W
0251 01B8 0703              BTFSS   STATUS,C
0252 01B9 02A8              INCF    LEVEL           ; LEVEL < 255
0253 01BA 0BC1              GOTO    DISPLAY         ; LEVEL >= 255
0254                
0255 01BB 07C9      DEC_L   BTFSS   STATE1,6
0256 01BC 0BAF              GOTO    MAIN
0257                
0258 01BD 0C01              MOVLW   1
0259 01BE 0088              SUBWF   LEVEL,W
0260 01BF 0603              BTFSC   STATUS,C
0261 01C0 00E8              DECF    LEVEL           ; LEVEL >= 1
0262                                                ; LEVEL < 1
0263                DISPLAY
0264 01C1 0CC0              MOVLW   192
0265 01C2 0088              SUBWF   LEVEL,W
0266 01C3 002C              MOVWF   TEMP
0267 01C4 0703              BTFSS   STATUS,C
0268 01C5 0BC9              GOTO    MINUS           ; LEVEL < 192
0269                                                ; LEVEL >= 192
0270                PLUS
0271 01C6 0C26              MOVLW   $26
0272 01C7 0900              CALL    TXBYTE
0273 01C8 0BCD              GOTO    OPNUM
0274                
0275 01C9 0C24      MINUS   MOVLW   $24
0276 01CA 0900              CALL    TXBYTE
0277 01CB 026C              COMF    TEMP
0278 01CC 02AC              INCF    TEMP
0279                
0280 01CD 030C      OPNUM   RRF     TEMP,W
0281 01CE 0925              CALL    TRANS3
0282 01CF 002D              MOVWF   NUM
0283 01D0 038D              SWAPF   NUM,W
0284 01D1 0913              CALL    DIGITS
0285 01D2 0900              CALL    TXBYTE
0286 01D3 020D              MOVF    NUM,W
0287 01D4 0913              CALL    DIGITS
0288 01D5 0900              CALL    TXBYTE
0289                
0290 01D6 0C00              MOVLW   0
0291 01D7 060C              BTFSC   TEMP,0
0292 01D8 0C05              MOVLW   5
0293 01D9 0913              CALL    DIGITS
0294 01DA 0900              CALL    TXBYTE
0295                
0296 01DB 05C6              BSF     PORTB,LOAD2
0297 01DC 0000              NOP
0298 01DD 04C6              BCF     PORTB,LOAD2
0299                
0300 01DE 0208              MOVF    LEVEL,W
0301 01DF 0E0F              ANDLW   $0F
0302 01E0 0026              MOVWF   PORTB
0303 01E1 0BAF              GOTO    MAIN
0304                
0305                ; ----------   TXB SUBROUTINE   ----------
0306                
0307 01E2 002A      TXB     MOVWF   TXSR
0308 01E3 04C6              BCF     PORTB,LOAD2
0309 01E4 04A6              BCF     PORTB,CLK2
0310 01E5 0C08              MOVLW   8
0311 01E6 002B              MOVWF   I
0312                
0313 01E7 06EA      SHIFT   BTFSC   TXSR,7
0314 01E8 0586              BSF     PORTB,DATA2
0315 01E9 07EA              BTFSS   TXSR,7
0316 01EA 0486              BCF     PORTB,DATA2
0317                
0318 01EB 05A6              BSF     PORTB,CLK2
0319 01EC 036A              RLF     TXSR            ; DO SOMETHING
0320 01ED 04A6              BCF     PORTB,CLK2
0321                
0322 01EE 02EB              DECFSZ  I
0323 01EF 0BE7              GOTO    SHIFT
0324 01F0 0800              RETLW   0
0325                
0326                        ORG     PIC54
0327 01FF 0B00      RESET   GOTO    $100


Number of errors 0
