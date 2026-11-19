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
0037      0009       STATE2  EQU     09              ; ENCODER STATE
0038      000A       TXSR    EQU     10              ; TX SHIFT REGISTER
0039      000B       I       EQU     11
0040      000C       TEMP    EQU     12
0041      000D       NUM     EQU     13
0042                
0043      000E       AS      EQU     14
0044      000F       BS      EQU     15
0045      0010       KS      EQU     16
0046      0011       INCV    EQU     17
0047      0012       COUNT   EQU     18
0048                
0049                ; ----------   PORTA BITS   ----------
0050                
0051      0000       A       EQU     0
0052      0001       B       EQU     1
0053      0003       KEY     EQU     3
0054                
0055                ; ----------   PORTB BITS   ----------
0056                
0057      0000       DATA1   EQU     0               ; CS3310
0058      0001       CLK1    EQU     1
0059      0002       LOAD1   EQU     2
0060      0003       MUTE1   EQU     3               ; PULL DOWN
0061                
0062      0004       DATA2   EQU     4               ; LCD
0063      0005       CLK2    EQU     5
0064      0006       LOAD2   EQU     6
0065      0007       TESTB   EQU     7               ; OUTPUT LEVEL IF BIT LOW
0066                
0067                
0068                ; ----------   EQUATES   ----------
0069                
0070      0001       DELAY1  EQU     1               ; MAX delay with OPTION $07 ( RTCC=OS2/256 )
0071      0076       DELAY2  EQU     118             ;   1 msec  with OPTION $01 ( RTCC=OS2/4 )
0072                
0073                ; ----------   JUMP TABLE   ----------
0074                
0075                        ORG     $000
0076                
0077 0000 0B83      TXGAIN  GOTO    TXB1
0078 0001 0B91      TXDIS   GOTO    TXB2
0079                
0080                ; ----------   NEXT STATE TABLE1   ----------
0081                
0082      0003       KEYBIT  EQU     3
0083                
0084 0002 0E0F      NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
0085 0003 01E2              ADDWF   PC
0086                
0087 0004 0800              RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
0088 0005 0802              RETLW   2
0089 0006 0800              RETLW   0
0090 0007 0804              RETLW   4
0091 0008 0800              RETLW   0
0092 0009 0806              RETLW   6
0093 000A 0800              RETLW   0
0094 000B 0808              RETLW   8       ; 4TH INPUT=1 SO SET KEYBIT
0095                
0096 000C 080A              RETLW   10
0097 000D 0808              RETLW   8       ; KEYBIT SET WHILE INPUT=1
0098 000E 080C              RETLW   12
0099 000F 0808              RETLW   8
0100 0010 080E              RETLW   14
0101 0011 0808              RETLW   8
0102 0012 0800              RETLW   0       ; 4TH INPUT=0 SO CLEAR KEYBIT
0103 0013 0808              RETLW   8
0104                
0105                ; ----------   NEXT STATE TABLE2   ----------
0106                
0107 0014 0E0F      NEXT2   ANDLW   $0F
0108 0015 01E2              ADDWF   PC
0109                
0110 0016 0800              RETLW   $00
0111 0017 0844              RETLW   $44     ;DEC
0112 0018 0888              RETLW   $88     ;INC
0113 0019 0800              RETLW   $00
0114                
0115 001A 0880              RETLW   $80     ;INC
0116 001B 0804              RETLW   $04
0117 001C 0804              RETLW   $04
0118 001D 084C              RETLW   $4C     ;DEC
0119                
0120 001E 0840              RETLW   $40     ;DEC
0121 001F 0808              RETLW   $08
0122 0020 0808              RETLW   $08
0123 0021 088C              RETLW   $8C     ;INC
0124                
0125 0022 080C              RETLW   $0C
0126 0023 0884              RETLW   $84     ;INC
0127 0024 0848              RETLW   $48     ;DEC
0128 0025 080C              RETLW   $0C
0129                
0130                ; ----------   DIGITS LOOKUP TABLE3   ----------
0131                
0132 0026 0E0F      DIGITS  ANDLW   $0F
0133 0027 01E2              ADDWF   PC
0134                
0135 0028 083F              RETLW   $3F             ; 0
0136 0029 0806              RETLW   $06             ; 1
0137 002A 085B              RETLW   $5B             ; 2
0138 002B 084F              RETLW   $4F             ; 3
0139                
0140 002C 0866              RETLW   $66             ; 4
0141 002D 086D              RETLW   $6D             ; 5
0142 002E 087D              RETLW   $7D             ; 6
0143 002F 0807              RETLW   $07             ; 7
0144                
0145 0030 087F              RETLW   $7F             ; 8
0146 0031 086F              RETLW   $6F             ; 9
0147 0032 0877              RETLW   $77             ; A
0148 0033 087C              RETLW   $7C             ; B
0149                
0150 0034 0839              RETLW   $39             ; C
0151 0035 085E              RETLW   $5E             ; D
0152 0036 0879              RETLW   $79             ; E
0153 0037 0871              RETLW   $71             ; F
0154                
0155                ; ----------   TRANSLATION TABLE4   ----------
0156                
0157 0038 0E7F      TRANS4  ANDLW   $7F
0158 0039 01E2              ADDWF   PC
0159 003A 0800              RETLW   $00
0160 003B 0801              RETLW   $01
0161 003C 0802              RETLW   $02
0162 003D 0803              RETLW   $03
0163 003E 0804              RETLW   $04
0164 003F 0805              RETLW   $05
0165 0040 0806              RETLW   $06
0166 0041 0807              RETLW   $07
0167                
0168 0042 0808              RETLW   $08
0169 0043 0809              RETLW   $09
0170 0044 0810              RETLW   $10
0171 0045 0811              RETLW   $11
0172 0046 0812              RETLW   $12
0173 0047 0813              RETLW   $13
0174 0048 0814              RETLW   $14
0175 0049 0815              RETLW   $15
0176                
0177 004A 0816              RETLW   $16
0178 004B 0817              RETLW   $17
0179 004C 0818              RETLW   $18
0180 004D 0819              RETLW   $19
0181 004E 0820              RETLW   $20
0182 004F 0821              RETLW   $21
0183 0050 0822              RETLW   $22
0184 0051 0823              RETLW   $23
0185                
0186 0052 0824              RETLW   $24
0187 0053 0825              RETLW   $25
0188 0054 0826              RETLW   $26
0189 0055 0827              RETLW   $27
0190 0056 0828              RETLW   $28
0191 0057 0829              RETLW   $29
0192 0058 0830              RETLW   $30
0193 0059 0831              RETLW   $31
0194                
0195 005A 0832              RETLW   $32
0196 005B 0833              RETLW   $33
0197 005C 0834              RETLW   $34
0198 005D 0835              RETLW   $35
0199 005E 0836              RETLW   $36
0200 005F 0837              RETLW   $37
0201 0060 0838              RETLW   $38
0202 0061 0839              RETLW   $39
0203                
0204 0062 0840              RETLW   $40
0205 0063 0841              RETLW   $41
0206 0064 0842              RETLW   $42
0207 0065 0843              RETLW   $43
0208 0066 0844              RETLW   $44
0209 0067 0845              RETLW   $45
0210 0068 0846              RETLW   $46
0211 0069 0847              RETLW   $47
0212                
0213 006A 0848              RETLW   $48
0214 006B 0849              RETLW   $49
0215 006C 0850              RETLW   $50
0216 006D 0851              RETLW   $51
0217 006E 0852              RETLW   $52
0218 006F 0853              RETLW   $53
0219 0070 0854              RETLW   $54
0220 0071 0855              RETLW   $55
0221                
0222 0072 0856              RETLW   $56
0223 0073 0857              RETLW   $57
0224 0074 0858              RETLW   $58
0225 0075 0859              RETLW   $59
0226 0076 0860              RETLW   $60
0227 0077 0861              RETLW   $61
0228 0078 0862              RETLW   $62
0229 0079 0863              RETLW   $63
0230                
0231 007A 0864              RETLW   $64
0232 007B 0865              RETLW   $65
0233 007C 0866              RETLW   $66
0234 007D 0867              RETLW   $67
0235 007E 0868              RETLW   $68
0236 007F 0869              RETLW   $69
0237 0080 0870              RETLW   $70
0238 0081 0871              RETLW   $71
0239                
0240 0082 0872              RETLW   $72
0241 0083 0873              RETLW   $73
0242 0084 0874              RETLW   $74
0243 0085 0875              RETLW   $75
0244 0086 0876              RETLW   $76
0245 0087 0877              RETLW   $77
0246 0088 0878              RETLW   $78
0247 0089 0879              RETLW   $79
0248                
0249 008A 0880              RETLW   $80
0250 008B 0881              RETLW   $81
0251 008C 0882              RETLW   $82
0252 008D 0883              RETLW   $83
0253 008E 0884              RETLW   $84
0254 008F 0885              RETLW   $85
0255 0090 0886              RETLW   $86
0256 0091 0887              RETLW   $87
0257                
0258 0092 0888              RETLW   $88
0259 0093 0889              RETLW   $89
0260 0094 0890              RETLW   $90
0261 0095 0891              RETLW   $91
0262 0096 0892              RETLW   $92
0263 0097 0893              RETLW   $93
0264 0098 0894              RETLW   $94
0265 0099 0895              RETLW   $95
0266                
0267 009A 08FF              RETLW   $FF
0268                
0269                ; ----------   CODE   ----------
0270                
0271                        ORG     $101
0272                
0273 0101 0C0F              MOVLW   $0F
0274 0102 0005              TRIS    PORTA
0275                
0276 0103 0C04              MOVLW   $04
0277 0104 0026              MOVWF   PORTB
0278 0105 0C80              MOVLW   $80
0279 0106 0006              TRIS    PORTB
0280                
0281 0107 0CFF              MOVLW   $FF             ; TURN ON DISPLAY
0282 0108 0901              CALL    TXDIS
0283 0109 0CFF              MOVLW   $FF
0284 010A 0901              CALL    TXDIS
0285 010B 0CFF              MOVLW   $FF
0286 010C 0901              CALL    TXDIS
0287 010D 0CFF              MOVLW   $FF
0288 010E 0901              CALL    TXDIS
0289                
0290 010F 05C6              BSF     PORTB,LOAD2
0291 0110 0000              NOP
0292 0111 04C6              BCF     PORTB,LOAD2
0293                
0294 0112 0C07              MOVLW   $07
0295 0113 0002              OPTION
0296 0114 0C01              MOVLW   DELAY1
0297 0115 0021              MOVWF   RTCC
0298                
0299 0116 0201      TDIS    MOVF    RTCC,W
0300 0117 0743              BTFSS   STATUS,Z
0301 0118 0B16              GOTO    TDIS
0302                
0303 0119 0C01              MOVLW   $01
0304 011A 0002              OPTION
0305 011B 0C76              MOVLW   DELAY2
0306 011C 0021              MOVWF   RTCC
0307                
0308 011D 006E              CLRF    AS
0309 011E 006F              CLRF    BS
0310 011F 0070              CLRF    KS
0311                
0312 0120 0068              CLRF    LEVEL
0313 0121 0C20              MOVLW   32
0314 0122 0031              MOVWF   INCV
0315 0123 0C0A              MOVLW   10
0316 0124 0032              MOVWF   COUNT
0317                
0318 0125 0205              MOVF    PORTA,W
0319 0126 0E03              ANDLW   $03
0320 0127 0029              MOVWF   STATE2
0321 0128 0369              RLF     STATE2
0322 0129 0369              RLF     STATE2
0323                
0324 012A 0566              BSF     PORTB,MUTE1
0325                
0326 012B 0B5F              GOTO    OUTPUT
0327                
0328 012C 0201      MAIN    MOVF    RTCC,W
0329 012D 0743              BTFSS   STATUS,Z
0330 012E 0B2C              GOTO    MAIN
0331                
0332 012F 0C76              MOVLW   DELAY2
0333 0130 0021              MOVWF   RTCC
0334                
0335 0131 02F2              DECFSZ  COUNT
0336 0132 0B37              GOTO    MORE
0337                
0338 0133 0C0A              MOVLW   10
0339 0134 0032              MOVWF   COUNT
0340                
0341 0135 0711              BTFSS   INCV,0
0342 0136 0331              RRF     INCV
0343                
0344                MORE
0345                ; ----------   SCAN CLOSURE SUBROUTINE   ----------
0346                
0347 0137 0605              BTFSC   PORTA,A         ; DEBOUNCE INPUTS
0348 0138 02AE              INCF    AS
0349 0139 020E              MOVF    AS,W
0350 013A 0902              CALL    NEXT1
0351 013B 002E              MOVWF   AS
0352                
0353 013C 0625              BTFSC   PORTA,B
0354 013D 02AF              INCF    BS
0355 013E 020F              MOVF    BS,W
0356 013F 0902              CALL    NEXT1
0357 0140 002F              MOVWF   BS
0358                
0359 0141 0665              BTFSC   PORTA,KEY
0360 0142 02B0              INCF    KS
0361 0143 0210              MOVF    KS,W
0362 0144 0902              CALL    NEXT1
0363 0145 0030              MOVWF   KS
0364                
0365 0146 0670              BTFSC   KS,KEYBIT
0366 0147 0466              BCF     PORTB,MUTE1
0367 0148 0770              BTFSS   KS,KEYBIT
0368 0149 0566              BSF     PORTB,MUTE1
0369                
0370 014A 066E              BTFSC   AS,KEYBIT
0371 014B 0509              BSF     STATE2,A
0372 014C 066F              BTFSC   BS,KEYBIT
0373 014D 0529              BSF     STATE2,B
0374 014E 0209              MOVF    STATE2,W
0375 014F 0914              CALL    NEXT2
0376 0150 0029              MOVWF   STATE2
0377                
0378 0151 07E9      INC_L   BTFSS   STATE2,7
0379 0152 0B56              GOTO    DEC_L
0380                
0381 0153 0211              MOVF    INCV,W
0382 0154 01E8              ADDWF   LEVEL
0383 0155 0B5A              GOTO    REFRESH
0384                
0385 0156 07C9      DEC_L   BTFSS   STATE2,6
0386 0157 0B5D              GOTO    CHECK
0387                
0388 0158 0211              MOVF    INCV,W
0389 0159 00A8              SUBWF   LEVEL
0390                
0391 015A 0C20      REFRESH MOVLW   32
0392 015B 0031              MOVWF   INCV
0393 015C 0B5F              GOTO    OUTPUT
0394                
0395 015D 06E6      CHECK   BTFSC   PORTB,TESTB
0396 015E 0B2C              GOTO    MAIN
0397                
0398 015F 0208      OUTPUT  MOVF    LEVEL,W
0399 0160 0900              CALL    TXGAIN
0400 0161 0208              MOVF    LEVEL,W
0401 0162 0900              CALL    TXGAIN
0402                
0403 0163 0546              BSF     PORTB,LOAD1
0404                
0405                DISPLAY
0406 0164 0CC0              MOVLW   192
0407 0165 0088              SUBWF   LEVEL,W
0408 0166 002C              MOVWF   TEMP
0409 0167 0703              BTFSS   STATUS,C
0410 0168 0B6C              GOTO    MINUS           ; LEVEL < 192
0411                                                ; LEVEL >= 192
0412                PLUS
0413 0169 0C26              MOVLW   $26
0414 016A 0901              CALL    TXDIS
0415 016B 0B70              GOTO    OPNUM
0416                
0417 016C 0C24      MINUS   MOVLW   $24
0418 016D 0901              CALL    TXDIS
0419 016E 026C              COMF    TEMP
0420 016F 02AC              INCF    TEMP
0421                
0422 0170 030C      OPNUM   RRF     TEMP,W
0423 0171 0938              CALL    TRANS4
0424 0172 002D              MOVWF   NUM
0425 0173 038D              SWAPF   NUM,W
0426 0174 0926              CALL    DIGITS
0427 0175 0901              CALL    TXDIS
0428 0176 020D              MOVF    NUM,W
0429 0177 0926              CALL    DIGITS
0430 0178 0901              CALL    TXDIS
0431                
0432 0179 0C00              MOVLW   0
0433 017A 060C              BTFSC   TEMP,0
0434 017B 0C05              MOVLW   5
0435 017C 0926              CALL    DIGITS
0436 017D 0901              CALL    TXDIS
0437                
0438 017E 05C6              BSF     PORTB,LOAD2
0439 017F 0000              NOP
0440 0180 04C6              BCF     PORTB,LOAD2
0441                
0442 0181 0FFF              XORLW   $FF
0443 0182 0B2C              GOTO    MAIN
0444                
0445                ; ----------   TXB1 SUBROUTINE   ----------
0446                
0447 0183 002A      TXB1    MOVWF   TXSR
0448 0184 0446              BCF     PORTB,LOAD1
0449 0185 0C08              MOVLW   8
0450 0186 002B              MOVWF   I
0451                
0452 0187 06EA      SHIFT1  BTFSC   TXSR,7
0453 0188 0506              BSF     PORTB,DATA1
0454 0189 07EA              BTFSS   TXSR,7
0455 018A 0406              BCF     PORTB,DATA1
0456                
0457 018B 0426              BCF     PORTB,CLK1
0458 018C 036A              RLF     TXSR            ; DO SOMETHING
0459 018D 0526              BSF     PORTB,CLK1
0460                
0461 018E 02EB              DECFSZ  I
0462 018F 0B87              GOTO    SHIFT1
0463 0190 0800              RETLW   0
0464                
0465                ; ----------   TXB2 SUBROUTINE   ----------
0466                
0467 0191 002A      TXB2    MOVWF   TXSR
0468 0192 04C6              BCF     PORTB,LOAD2
0469 0193 0C08              MOVLW   8
0470 0194 002B              MOVWF   I
0471                
0472 0195 06EA      SHIFT2  BTFSC   TXSR,7
0473 0196 0586              BSF     PORTB,DATA2
0474 0197 07EA              BTFSS   TXSR,7
0475 0198 0486              BCF     PORTB,DATA2
0476                
0477 0199 05A6              BSF     PORTB,CLK2
0478 019A 036A              RLF     TXSR            ; DO SOMETHING
0479 019B 04A6              BCF     PORTB,CLK2
0480                
0481 019C 02EB              DECFSZ  I
0482 019D 0B95              GOTO    SHIFT2
0483 019E 0800              RETLW   0
0484                
0485                        ORG     PIC55
0486 01FF 0B00      RESET   GOTO    $100


Number of errors 0
