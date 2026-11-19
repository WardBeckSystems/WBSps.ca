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
0047                
0048                ; ----------   PORTA BITS   ----------
0049                
0050      0000       A       EQU     0
0051      0001       B       EQU     1
0052      0003       KEY     EQU     3
0053                
0054                ; ----------   PORTB BITS   ----------
0055                
0056      0000       DATA1   EQU     0               ; CS3310
0057      0001       CLK1    EQU     1
0058      0002       LOAD1   EQU     2
0059      0003       TESTB   EQU     3               ; OUTPUT LEVEL IF BIT LOW
0060                
0061      0004       DATA2   EQU     4               ; LCD
0062      0005       CLK2    EQU     5
0063      0006       LOAD2   EQU     6
0064      0007       MUTE1   EQU     7               ; PULL DOWN
0065                
0066                
0067                ; ----------   EQUATES   ----------
0068                
0069      0001       DELAY1  EQU     1               ; MAX delay with OPTION $07 ( RTCC=OS2/256 )
0070      0076       DELAY2  EQU     118             ;   1 msec  with OPTION $01 ( RTCC=OS2/4 )
0071                
0072                ; ----------   JUMP TABLE   ----------
0073                
0074                        ORG     $000
0075                
0076 0000 0B7A      TXGAIN  GOTO    TXB1
0077 0001 0B88      TXDIS   GOTO    TXB2
0078                
0079                ; ----------   NEXT STATE TABLE1   ----------
0080                
0081      0003       KEYBIT  EQU     3
0082                
0083 0002 0E0F      NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
0084 0003 01E2              ADDWF   PC
0085                
0086 0004 0800              RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
0087 0005 0802              RETLW   2
0088 0006 0800              RETLW   0
0089 0007 0804              RETLW   4
0090 0008 0800              RETLW   0
0091 0009 0806              RETLW   6
0092 000A 0800              RETLW   0
0093 000B 0808              RETLW   8       ; 4TH INPUT=1 SO SET KEYBIT
0094                
0095 000C 080A              RETLW   10
0096 000D 0808              RETLW   8       ; KEYBIT SET WHILE INPUT=1
0097 000E 080C              RETLW   12
0098 000F 0808              RETLW   8
0099 0010 080E              RETLW   14
0100 0011 0808              RETLW   8
0101 0012 0800              RETLW   0       ; 4TH INPUT=0 SO CLEAR KEYBIT
0102 0013 0808              RETLW   8
0103                
0104                ; ----------   NEXT STATE TABLE2   ----------
0105                
0106 0014 0E0F      NEXT2   ANDLW   $0F
0107 0015 01E2              ADDWF   PC
0108                
0109 0016 0800              RETLW   $00
0110 0017 0844              RETLW   $44     ;DEC
0111 0018 0888              RETLW   $88     ;INC
0112 0019 0800              RETLW   $00
0113                
0114 001A 0880              RETLW   $80     ;INC
0115 001B 0804              RETLW   $04
0116 001C 0804              RETLW   $04
0117 001D 084C              RETLW   $4C     ;DEC
0118                
0119 001E 0840              RETLW   $40     ;DEC
0120 001F 0808              RETLW   $08
0121 0020 0808              RETLW   $08
0122 0021 088C              RETLW   $8C     ;INC
0123                
0124 0022 080C              RETLW   $0C
0125 0023 0884              RETLW   $84     ;INC
0126 0024 0848              RETLW   $48     ;DEC
0127 0025 080C              RETLW   $0C
0128                
0129                ; ----------   DIGITS LOOKUP TABLE3   ----------
0130                
0131 0026 0E0F      DIGITS  ANDLW   $0F
0132 0027 01E2              ADDWF   PC
0133                
0134 0028 083F              RETLW   $3F             ; 0
0135 0029 0806              RETLW   $06             ; 1
0136 002A 085B              RETLW   $5B             ; 2
0137 002B 084F              RETLW   $4F             ; 3
0138                
0139 002C 0866              RETLW   $66             ; 4
0140 002D 086D              RETLW   $6D             ; 5
0141 002E 087D              RETLW   $7D             ; 6
0142 002F 0807              RETLW   $07             ; 7
0143                
0144 0030 087F              RETLW   $7F             ; 8
0145 0031 086F              RETLW   $6F             ; 9
0146 0032 0877              RETLW   $77             ; A
0147 0033 087C              RETLW   $7C             ; B
0148                
0149 0034 0839              RETLW   $39             ; C
0150 0035 085E              RETLW   $5E             ; D
0151 0036 0879              RETLW   $79             ; E
0152 0037 0871              RETLW   $71             ; F
0153                
0154                ; ----------   TRANSLATION TABLE4   ----------
0155                
0156 0038 0E7F      TRANS4  ANDLW   $7F
0157 0039 01E2              ADDWF   PC
0158 003A 0800              RETLW   $00
0159 003B 0801              RETLW   $01
0160 003C 0802              RETLW   $02
0161 003D 0803              RETLW   $03
0162 003E 0804              RETLW   $04
0163 003F 0805              RETLW   $05
0164 0040 0806              RETLW   $06
0165 0041 0807              RETLW   $07
0166                
0167 0042 0808              RETLW   $08
0168 0043 0809              RETLW   $09
0169 0044 0810              RETLW   $10
0170 0045 0811              RETLW   $11
0171 0046 0812              RETLW   $12
0172 0047 0813              RETLW   $13
0173 0048 0814              RETLW   $14
0174 0049 0815              RETLW   $15
0175                
0176 004A 0816              RETLW   $16
0177 004B 0817              RETLW   $17
0178 004C 0818              RETLW   $18
0179 004D 0819              RETLW   $19
0180 004E 0820              RETLW   $20
0181 004F 0821              RETLW   $21
0182 0050 0822              RETLW   $22
0183 0051 0823              RETLW   $23
0184                
0185 0052 0824              RETLW   $24
0186 0053 0825              RETLW   $25
0187 0054 0826              RETLW   $26
0188 0055 0827              RETLW   $27
0189 0056 0828              RETLW   $28
0190 0057 0829              RETLW   $29
0191 0058 0830              RETLW   $30
0192 0059 0831              RETLW   $31
0193                
0194 005A 0832              RETLW   $32
0195 005B 0833              RETLW   $33
0196 005C 0834              RETLW   $34
0197 005D 0835              RETLW   $35
0198 005E 0836              RETLW   $36
0199 005F 0837              RETLW   $37
0200 0060 0838              RETLW   $38
0201 0061 0839              RETLW   $39
0202                
0203 0062 0840              RETLW   $40
0204 0063 0841              RETLW   $41
0205 0064 0842              RETLW   $42
0206 0065 0843              RETLW   $43
0207 0066 0844              RETLW   $44
0208 0067 0845              RETLW   $45
0209 0068 0846              RETLW   $46
0210 0069 0847              RETLW   $47
0211                
0212 006A 0848              RETLW   $48
0213 006B 0849              RETLW   $49
0214 006C 0850              RETLW   $50
0215 006D 0851              RETLW   $51
0216 006E 0852              RETLW   $52
0217 006F 0853              RETLW   $53
0218 0070 0854              RETLW   $54
0219 0071 0855              RETLW   $55
0220                
0221 0072 0856              RETLW   $56
0222 0073 0857              RETLW   $57
0223 0074 0858              RETLW   $58
0224 0075 0859              RETLW   $59
0225 0076 0860              RETLW   $60
0226 0077 0861              RETLW   $61
0227 0078 0862              RETLW   $62
0228 0079 0863              RETLW   $63
0229                
0230 007A 0864              RETLW   $64
0231 007B 0865              RETLW   $65
0232 007C 0866              RETLW   $66
0233 007D 0867              RETLW   $67
0234 007E 0868              RETLW   $68
0235 007F 0869              RETLW   $69
0236 0080 0870              RETLW   $70
0237 0081 0871              RETLW   $71
0238                
0239 0082 0872              RETLW   $72
0240 0083 0873              RETLW   $73
0241 0084 0874              RETLW   $74
0242 0085 0875              RETLW   $75
0243 0086 0876              RETLW   $76
0244 0087 0877              RETLW   $77
0245 0088 0878              RETLW   $78
0246 0089 0879              RETLW   $79
0247                
0248 008A 0880              RETLW   $80
0249 008B 0881              RETLW   $81
0250 008C 0882              RETLW   $82
0251 008D 0883              RETLW   $83
0252 008E 0884              RETLW   $84
0253 008F 0885              RETLW   $85
0254 0090 0886              RETLW   $86
0255 0091 0887              RETLW   $87
0256                
0257 0092 0888              RETLW   $88
0258 0093 0889              RETLW   $89
0259 0094 0890              RETLW   $90
0260 0095 0891              RETLW   $91
0261 0096 0892              RETLW   $92
0262 0097 0893              RETLW   $93
0263 0098 0894              RETLW   $94
0264 0099 0895              RETLW   $95
0265                
0266 009A 08FF              RETLW   $FF
0267                
0268                ; ----------   CODE   ----------
0269                
0270                        ORG     $101
0271                
0272 0101 0C0F              MOVLW   $0F
0273 0102 0005              TRIS    PORTA
0274                
0275 0103 0C04              MOVLW   $04
0276 0104 0026              MOVWF   PORTB
0277 0105 0C08              MOVLW   $08
0278 0106 0006              TRIS    PORTB
0279                
0280 0107 0CFF              MOVLW   $FF             ; TURN ON DISPLAY
0281 0108 0901              CALL    TXDIS
0282 0109 0CFF              MOVLW   $FF
0283 010A 0901              CALL    TXDIS
0284 010B 0CFF              MOVLW   $FF
0285 010C 0901              CALL    TXDIS
0286 010D 0CFF              MOVLW   $FF
0287 010E 0901              CALL    TXDIS
0288                
0289 010F 05C6              BSF     PORTB,LOAD2
0290 0110 0000              NOP
0291 0111 04C6              BCF     PORTB,LOAD2
0292                
0293 0112 0C07              MOVLW   $07
0294 0113 0002              OPTION
0295 0114 0C01              MOVLW   DELAY1
0296 0115 0021              MOVWF   RTCC
0297                
0298 0116 0201      TDIS    MOVF    RTCC,W
0299 0117 0743              BTFSS   STATUS,Z
0300 0118 0B16              GOTO    TDIS
0301                
0302 0119 0C01              MOVLW   $01
0303 011A 0002              OPTION
0304 011B 0C76              MOVLW   DELAY2
0305 011C 0021              MOVWF   RTCC
0306                
0307 011D 006E              CLRF    AS
0308 011E 006F              CLRF    BS
0309 011F 0070              CLRF    KS
0310                
0311 0120 0C20              MOVLW   32
0312 0121 0031              MOVWF   INCV
0313 0122 0068              CLRF    LEVEL
0314 0123 0205              MOVF    PORTA,W
0315 0124 0E03              ANDLW   $03
0316 0125 0029              MOVWF   STATE2
0317                
0318 0126 05E6              BSF     PORTB,MUTE1
0319                
0320 0127 0B57              GOTO    OUTPUT
0321                
0322 0128 0201      MAIN    MOVF    RTCC,W
0323 0129 0743              BTFSS   STATUS,Z
0324 012A 0B28              GOTO    MAIN
0325                
0326 012B 0C76              MOVLW   DELAY2
0327 012C 0021              MOVWF   RTCC
0328                
0329 012D 0711              BTFSS   INCV,0
0330 012E 0331              RRF     INCV
0331                
0332                ; ----------   SCAN CLOSURE SUBROUTINE   ----------
0333                
0334 012F 0605              BTFSC   PORTA,A         ; DEBOUNCE INPUTS
0335 0130 02AE              INCF    AS
0336 0131 020E              MOVF    AS,W
0337 0132 0902              CALL    NEXT1
0338 0133 002E              MOVWF   AS
0339                
0340 0134 0625              BTFSC   PORTA,B
0341 0135 02AF              INCF    BS
0342 0136 020F              MOVF    BS,W
0343 0137 0902              CALL    NEXT1
0344 0138 002F              MOVWF   BS
0345                
0346 0139 0665              BTFSC   PORTA,KEY
0347 013A 02B0              INCF    KS
0348 013B 0210              MOVF    KS,W
0349 013C 0902              CALL    NEXT1
0350 013D 0030              MOVWF   KS
0351                
0352 013E 0670              BTFSC   KS,KEYBIT
0353 013F 04E6              BCF     PORTB,MUTE1
0354 0140 0770              BTFSS   KS,KEYBIT
0355 0141 05E6              BSF     PORTB,MUTE1
0356                
0357 0142 066E              BTFSC   AS,KEYBIT
0358 0143 0509              BSF     STATE2,A
0359 0144 066F              BTFSC   BS,KEYBIT
0360 0145 0529              BSF     STATE2,B
0361 0146 0209              MOVF    STATE2,W
0362 0147 0914              CALL    NEXT2
0363 0148 0029              MOVWF   STATE2
0364                
0365 0149 07E9      INC_L   BTFSS   STATE2,7
0366 014A 0B4E              GOTO    DEC_L
0367                
0368 014B 0231              MOVF    INCV
0369 014C 01E8              ADDWF   LEVEL
0370 014D 0B52              GOTO    REFRESH
0371                
0372 014E 07C9      DEC_L   BTFSS   STATE2,6
0373 014F 0B55              GOTO    CHECK
0374                
0375 0150 0231              MOVF    INCV
0376 0151 00A8              SUBWF   LEVEL
0377                
0378 0152 0C20      REFRESH MOVLW   32
0379 0153 0031              MOVWF   INCV
0380 0154 0B57              GOTO    OUTPUT
0381                
0382 0155 0666      CHECK   BTFSC   PORTB,TESTB
0383 0156 0B28              GOTO    MAIN
0384                
0385 0157 0208      OUTPUT  MOVF    LEVEL,W
0386 0158 0900              CALL    TXGAIN
0387 0159 0208              MOVF    LEVEL,W
0388 015A 0900              CALL    TXGAIN
0389                
0390 015B 0546              BSF     PORTB,LOAD1
0391                
0392                DISPLAY
0393 015C 0CC0              MOVLW   192
0394 015D 0088              SUBWF   LEVEL,W
0395 015E 002C              MOVWF   TEMP
0396 015F 0703              BTFSS   STATUS,C
0397 0160 0B64              GOTO    MINUS           ; LEVEL < 192
0398                                                ; LEVEL >= 192
0399                PLUS
0400 0161 0C26              MOVLW   $26
0401 0162 0901              CALL    TXDIS
0402 0163 0B68              GOTO    OPNUM
0403                
0404 0164 0C24      MINUS   MOVLW   $24
0405 0165 0901              CALL    TXDIS
0406 0166 026C              COMF    TEMP
0407 0167 02AC              INCF    TEMP
0408                
0409 0168 030C      OPNUM   RRF     TEMP,W
0410 0169 0938              CALL    TRANS4
0411 016A 002D              MOVWF   NUM
0412 016B 038D              SWAPF   NUM,W
0413 016C 0926              CALL    DIGITS
0414 016D 0901              CALL    TXDIS
0415 016E 020D              MOVF    NUM,W
0416 016F 0926              CALL    DIGITS
0417 0170 0901              CALL    TXDIS
0418                
0419 0171 0C00              MOVLW   0
0420 0172 060C              BTFSC   TEMP,0
0421 0173 0C05              MOVLW   5
0422 0174 0926              CALL    DIGITS
0423 0175 0901              CALL    TXDIS
0424                
0425 0176 05C6              BSF     PORTB,LOAD2
0426 0177 0000              NOP
0427 0178 04C6              BCF     PORTB,LOAD2
0428                
0429 0179 0B28              GOTO    MAIN
0430                
0431                ; ----------   TXB1 SUBROUTINE   ----------
0432                
0433 017A 002A      TXB1    MOVWF   TXSR
0434 017B 0446              BCF     PORTB,LOAD1
0435 017C 0C08              MOVLW   8
0436 017D 002B              MOVWF   I
0437                
0438 017E 06EA      SHIFT1  BTFSC   TXSR,7
0439 017F 0506              BSF     PORTB,DATA1
0440 0180 07EA              BTFSS   TXSR,7
0441 0181 0406              BCF     PORTB,DATA1
0442                
0443 0182 0426              BCF     PORTB,CLK1
0444 0183 036A              RLF     TXSR            ; DO SOMETHING
0445 0184 0526              BSF     PORTB,CLK1
0446                
0447 0185 02EB              DECFSZ  I
0448 0186 0B7E              GOTO    SHIFT1
0449 0187 0800              RETLW   0
0450                
0451                ; ----------   TXB2 SUBROUTINE   ----------
0452                
0453 0188 002A      TXB2    MOVWF   TXSR
0454 0189 04C6              BCF     PORTB,LOAD2
0455 018A 0C08              MOVLW   8
0456 018B 002B              MOVWF   I
0457                
0458 018C 06EA      SHIFT2  BTFSC   TXSR,7
0459 018D 0586              BSF     PORTB,DATA2
0460 018E 07EA              BTFSS   TXSR,7
0461 018F 0486              BCF     PORTB,DATA2
0462                
0463 0190 05A6              BSF     PORTB,CLK2
0464 0191 036A              RLF     TXSR            ; DO SOMETHING
0465 0192 04A6              BCF     PORTB,CLK2
0466                
0467 0193 02EB              DECFSZ  I
0468 0194 0B8C              GOTO    SHIFT2
0469 0195 0800              RETLW   0
0470                
0471                        ORG     PIC55
0472 01FF 0B00      RESET   GOTO    $100


Number of errors 0
