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
0036      0007       DISPLAY EQU     07
0037      0008       TMP     EQU     08
0038      0008       IPV     EQU     08
0039      0009       I       EQU     09
0040      000A       ROW     EQU     10
0041      000B       KEY     EQU     11
0042                
0043                        ORG     12              ; DEBOUNCE STATES
0044                
0045 000C 0001      TBST    DW      1               ; TALKBACK INPUT STATE
0046 000D 0001      RA1ST   DW      1               ; REMOTE ADDRESS 1 STATE
0047 000E 0001      RA2ST   DW      1               ; REMOTE ADDRESS 2 STATE
0048 000F 0001      RA3ST   DW      1               ; REMOTE ADDRESS 3 STATE
0049                
0050 0010 000C      KEYST   DW      12              ; KEYSWITCH STATES
0051                
0052                ; ----------   PORTB BITS   ----------
0053                
0054      0005       KCOL1   EQU     5               ; KEYBOARD COLUMN 1
0055      0004       KCOL2   EQU     4               ; KEYBOARD COLUMN 2
0056                
0057      0004       TB      EQU     4               ; TALKBACK INPUTS
0058      0005       RA1     EQU     5               ; REMOTE ADDRESS 1 INPUT
0059      0006       RA2     EQU     6               ; REMOTE ADDRESS 2 INPUT
0060      0007       RA3     EQU     7               ; REMOTE ADDRESS 3 INPUT
0061                
0062                ; ----------   EQUATES   ----------
0063                
0064      0006       NROWS   EQU     6               ; NUMBER OF ROWS IN KEYBOARD
0065      000C       NKEYS   EQU     12              ; NUMBER OF KEYS IN KEYBOARD
0066      0004       NIP     EQU     4               ; NUMBER OF INPUTS
0067                
0068                                                ; USE 4K7 AND 330pF FOR RC OSC
0069                                                ; OS2 = 125kHz
0070      000C       DELAY1  EQU     12              ; 250 msec with OPTION $06
0071      006C       DELAY2  EQU     108             ; 9.5 msec with OPTION $02
0072                
0073                                                ; PORTB DATA DIRECTION
0074      0030       PBDSKD  EQU     $30             ; PORTB SCAN KEYBOARD/DISPLAY
0075      00F0       PBDIPSW EQU     $F0             ; PORTB READ INPUTS/SWITCHES
0076                
0077                                                ; PORTB OUTPUTS FOR VARIOUS FUNCTIONS
0078      0040       DCOL1   EQU     64              ; TURN ON DISPLAY COLUMN 1
0079      0080       DCOL2   EQU     128             ; TURN ON DISPLAY COLUMN 2
0080      00C2       KEYR1   EQU     128+64+2        ; FIRST KEYBOARD ROW
0081                
0082                                                ; DECODER ADDRESSES
0083      00C8       PBIP    EQU     128+64+8        ; TALKBACK AND REMOTE INPUTS
0084      00C9       PBSW1   EQU     PBIP+1          ; SWITCH 1
0085      00CA       PBSW2   EQU     PBIP+2          ; SWITCH 2
0086      00CB       PBSW3   EQU     PBIP+3          ; SWITCH 3
0087      000F       PBNONE  EQU     $0F             ; DISABLE ALL BUFFERS BY SELECTING NONE
0088                
0089                ; ----------   NEXT STATE TABLE1   ----------
0090                
0091                        ORG     $000
0092                                        ; SET BIT 0 OF THE STATE TO INPUT
0093                                        ; BEFORE CALLING NEXT1
0094      0003       KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1
0095                
0096 0000 0E0F      NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
0097 0001 01E2              ADDWF   PC
0098                
0099 0002 0800              RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
0100 0003 0802              RETLW   2
0101 0004 0800              RETLW   0
0102 0005 0804              RETLW   4
0103 0006 0800              RETLW   0
0104 0007 0806              RETLW   6
0105 0008 0800              RETLW   0
0106 0009 0808              RETLW   8       ; 4TH INPUT=1 SO SET KEYBIT
0107                
0108 000A 080A              RETLW   10
0109 000B 0808              RETLW   8       ; KEYBIT SET WHILE INPUT=1
0110 000C 080C              RETLW   12
0111 000D 0808              RETLW   8
0112 000E 080E              RETLW   14
0113 000F 0808              RETLW   8
0114 0010 0800              RETLW   0       ; 4TH INPUT=0 SO CLEAR KEYBIT
0115 0011 0808              RETLW   8
0116                
0117                ; ----------   KEY STATE LOCATION TABLE2   ----------
0118                
0119 0012 0E0F      TRANS2  ANDLW   $0F
0120 0013 01E2              ADDWF   PC
0121                
0122 0014 081B              RETLW   KEYST+11        ; UNUSED
0123 0015 081B              RETLW   KEYST+11        ; UNUSED
0124 0016 081B              RETLW   KEYST+11        ; UNUSED
0125                
0126 0017 0810              RETLW   KEYST+00
0127 0018 0812              RETLW   KEYST+02
0128 0019 0814              RETLW   KEYST+04
0129 001A 0816              RETLW   KEYST+06
0130 001B 0818              RETLW   KEYST+08
0131 001C 081A              RETLW   KEYST+10
0132                
0133 001D 0811              RETLW   KEYST+01
0134 001E 0813              RETLW   KEYST+03
0135 001F 0815              RETLW   KEYST+05
0136 0020 0817              RETLW   KEYST+07
0137 0021 0819              RETLW   KEYST+09
0138 0022 081B              RETLW   KEYST+11
0139                
0140 0023 081B              RETLW   KEYST+11        ; UNUSED
0141                
0142                ; ----------   DISPLAY TRASLATION TABLE3   ----------
0143                
0144 0024 0E0F      TRANS3  ANDLW   $0F
0145 0025 01E2              ADDWF   PC
0146                
0147 0026 0887              RETLW   DCOL2+7         ; UNUSED
0148 0027 0887              RETLW   DCOL2+7         ; UNUSED
0149 0028 0887              RETLW   DCOL2+7         ; UNUSED
0150                
0151 0029 0842              RETLW   DCOL1+2
0152 002A 0843              RETLW   DCOL1+3
0153 002B 0844              RETLW   DCOL1+4
0154 002C 0845              RETLW   DCOL1+5
0155 002D 0846              RETLW   DCOL1+6
0156 002E 0847              RETLW   DCOL1+7
0157                
0158 002F 0882              RETLW   DCOL2+2
0159 0030 0883              RETLW   DCOL2+3
0160 0031 0884              RETLW   DCOL2+4
0161 0032 0885              RETLW   DCOL2+5
0162 0033 0886              RETLW   DCOL2+6
0163 0034 0887              RETLW   DCOL2+7
0164                
0165 0035 0887              RETLW   DCOL2+7         ; UNUSED
0166                
0167                ; ----------   UPDATE KEYSTATE SUBROUTINE   ----------
0168                
0169 0036 0200      UPDATE  MOVF    IND,W
0170 0037 0900              CALL    NEXT1
0171 0038 0020              MOVWF   IND
0172 0039 02A4              INCF    FSR
0173 003A 0800              RETLW   0
0174                
0175                ; ----------   OUTPUT SUBROUTINE   ----------
0176                
0177 003B 0FFF      OUTPUT  XORLW   $FF             ; UNPROGRAMMED NOP
0178 003C 028B              INCF    KEY,W
0179 003D 0E0C              ANDLW   $0C
0180 003E 0743              BTFSS   STATUS,Z
0181 003F 0A42              GOTO    OKAY
0182 0040 0C0E              MOVLW   14
0183 0041 002B              MOVWF   KEY
0184 0042 020B      OKAY    MOVF    KEY,W
0185 0043 0025              MOVWF   PORTA
0186 0044 0800              RETLW   0
0187                
0188                ; ----------   WAIT FOR TIMEOUT SUBROUTINE   ----------
0189                
0190 0045 0201      WAIT    MOVF    RTCC,W
0191 0046 0743              BTFSS   STATUS,Z
0192 0047 0A45              GOTO    WAIT            ; WAIT FOR TIME OUT
0193                
0194 0048 0C6C              MOVLW   DELAY2
0195 0049 0021              MOVWF   RTCC            ; RESET COUNTER
0196                
0197 004A 020B              MOVF    KEY,W
0198 004B 0924              CALL    TRANS3
0199 004C 0027              MOVWF   DISPLAY
0200                
0201 004D 0C0F              MOVLW   PBNONE
0202 004E 0126              IORWF   PORTB
0203                
0204 004F 0CF0              MOVLW   PBDIPSW
0205 0050 0006              TRIS    PORTB
0206                
0207 0051 0800              RETLW   0
0208                
0209                ; ----------   INITIALIZATION CODE   ----------
0210                
0211                        ORG     $163
0212 0163 0FFF      INIT    XORLW   $FF             ; UNPROGRAMED NOP
0213                
0214 0164 0C0F              MOVLW   $0F             ; INITIALIZE PORTA
0215 0165 0025              MOVWF   PORTA
0216 0166 0040              CLRW
0217 0167 0005              TRIS    PORTA
0218                
0219 0168 0C42              MOVLW   DCOL1+2         ; INITIALIZE PORTB
0220 0169 0026              MOVWF   PORTB
0221 016A 0C30              MOVLW   PBDSKD
0222 016B 0006              TRIS    PORTB
0223                
0224 016C 0C0C              MOVLW   TBST            ; BLANK INPUT AND KEYSWITCH STATES
0225 016D 0024              MOVWF   FSR
0226 016E 0C10              MOVLW   NIP+NKEYS
0227 016F 0029              MOVWF   I
0228 0170 0060      BLANK   CLRF    IND
0229 0171 02A4              INCF    FSR
0230 0172 02E9              DECFSZ  I
0231 0173 0B70              GOTO    BLANK
0232                
0233 0174 0C06              MOVLW   $06             ; RTCC = OSC2 / 128
0234 0175 0002              OPTION
0235                
0236 0176 0C0C              MOVLW   NKEYS
0237 0177 0029              MOVWF   I
0238 0178 0C03              MOVLW   3
0239 0179 002B              MOVWF   KEY
0240                
0241 017A 0C0C      SEQ1    MOVLW   DELAY1          ; RESET COUNTER
0242 017B 0021              MOVWF   RTCC
0243                
0244 017C 020B              MOVF    KEY,W
0245 017D 0924              CALL    TRANS3
0246 017E 0026              MOVWF   PORTB
0247 017F 02AB              INCF    KEY
0248                
0249 0180 0201      SEQ2    MOVF    RTCC,W
0250 0181 0743              BTFSS   STATUS,Z
0251 0182 0B80              GOTO    SEQ2            ; WAIT FOR TIME OUT
0252                
0253 0183 02E9              DECFSZ  I
0254 0184 0B7A              GOTO    SEQ1
0255                
0256 0185 0C02              MOVLW   $02             ; RTCC = OSC2 / 8
0257 0186 0002              OPTION
0258                
0259 0187 0C0E              MOVLW   14
0260 0188 002B              MOVWF   KEY
0261 0189 0BEA              GOTO    SELECT
0262                
0263                ; ----------   SCAN INPUT AND KEYBOARD ROUTINE   ----------
0264                
0265                SCAN2
0266 018A 0386              SWAPF   PORTB,W
0267 018B 002B              MOVWF   KEY
0268                
0269 018C 0CC8              MOVLW   PBIP
0270 018D 0026              MOVWF   PORTB
0271 018E 0000              NOP
0272                SCAN1
0273 018F 0206              MOVF    PORTB,W
0274 0190 0028              MOVWF   IPV
0275                
0276 0191 0C0F              MOVLW   PBNONE
0277 0192 0126              IORWF   PORTB
0278                
0279 0193 0C30              MOVLW   PBDSKD
0280 0194 0006              TRIS    PORTB
0281                
0282 0195 0CC2              MOVLW   KEYR1           ; TURN OFF LEDs AND MAKE FIRST ROW LOW
0283 0196 0026              MOVWF   PORTB
0284 0197 002A              MOVWF   ROW
0285                
0286 0198 0C10              MOVLW   KEYST
0287 0199 0024              MOVWF   FSR
0288 019A 0C05              MOVLW   NROWS-1
0289 019B 0029              MOVWF   I
0290                
0291 019C 02AA      SCANKB  INCF    ROW
0292 019D 020A              MOVF    ROW,W
0293                
0294 019E 06A6              BTFSC   PORTB,KCOL1
0295 019F 02A0              INCF    IND
0296 01A0 02A4              INCF    FSR
0297 01A1 0686              BTFSC   PORTB,KCOL2
0298 01A2 02A0              INCF    IND
0299 01A3 0026              MOVWF   PORTB
0300                
0301 01A4 00E4              DECF    FSR
0302 01A5 0936              CALL    UPDATE
0303 01A6 0936              CALL    UPDATE
0304                
0305 01A7 02E9              DECFSZ  I
0306 01A8 0B9C              GOTO    SCANKB
0307                
0308 01A9 0000              NOP
0309 01AA 0207              MOVF    DISPLAY,W
0310                
0311 01AB 06A6              BTFSC   PORTB,KCOL1
0312 01AC 02A0              INCF    IND
0313 01AD 02A4              INCF    FSR
0314 01AE 0686              BTFSC   PORTB,KCOL2
0315 01AF 02A0              INCF    IND
0316 01B0 0026              MOVWF   PORTB           ; RESTORE DISPLAY
0317                                                ; AFTER SCANNING KEYBOARD
0318 01B1 00E4              DECF    FSR
0319 01B2 0936              CALL    UPDATE
0320 01B3 0936              CALL    UPDATE
0321                
0322 01B4 0C0C              MOVLW   TBST             ; SCAN INPUTS
0323 01B5 0024              MOVWF   FSR
0324                
0325 01B6 0688              BTFSC   IPV,TB
0326 01B7 02AC              INCF    TBST
0327 01B8 0936              CALL    UPDATE
0328                
0329 01B9 06A8              BTFSC   IPV,RA1
0330 01BA 02AD              INCF    RA1ST
0331 01BB 0936              CALL    UPDATE
0332                
0333 01BC 06C8              BTFSC   IPV,RA2
0334 01BD 02AE              INCF    RA2ST
0335 01BE 0936              CALL    UPDATE
0336                
0337 01BF 06E8              BTFSC   IPV,RA3
0338 01C0 02AF              INCF    RA3ST
0339 01C1 0936              CALL    UPDATE
0340                
0341 01C2 0FFF              XORLW   $FF             ; UNPROGRAMED NOP
0342                
0343 01C3 066C              BTFSC   TBST,KEYBIT
0344 01C4 0BD0              GOTO    TALK
0345 01C5 066D              BTFSC   RA1ST,KEYBIT
0346 01C6 0BD6              GOTO    REMOTE1
0347 01C7 066E              BTFSC   RA2ST,KEYBIT
0348 01C8 0BDC              GOTO    REMOTE2
0349 01C9 066F              BTFSC   RA3ST,KEYBIT
0350 01CA 0BE2              GOTO    REMOTE3
0351 01CB 0BEA              GOTO    SELECT
0352                
0353                ; ----------   TALK MODE   ----------
0354                
0355 01CC 0945      T1      CALL    WAIT
0356 01CD 0CC8              MOVLW   PBIP
0357 01CE 0026              MOVWF   PORTB
0358 01CF 0B8F              GOTO    SCAN1
0359 01D0 093B      TALK    CALL    OUTPUT
0360 01D1 0BCC              GOTO    T1
0361                
0362                ; ----------   REMOTE1 MODE   ----------
0363                
0364 01D2 0945      R1      CALL    WAIT
0365 01D3 0CC9              MOVLW   PBSW1
0366 01D4 0026              MOVWF   PORTB
0367 01D5 0B8A              GOTO    SCAN2
0368 01D6 093B      REMOTE1 CALL    OUTPUT
0369 01D7 0BD2              GOTO    R1
0370                
0371                ; ----------   REMOTE2 MODE   ----------
0372                
0373 01D8 0945      R2      CALL    WAIT
0374 01D9 0CCA              MOVLW   PBSW2
0375 01DA 0026              MOVWF   PORTB
0376 01DB 0B8A              GOTO    SCAN2
0377 01DC 093B      REMOTE2 CALL    OUTPUT
0378 01DD 0BD8              GOTO    R2
0379                
0380                ; ----------   REMOTE3 MODE   ----------
0381                
0382 01DE 0945      R3      CALL    WAIT
0383 01DF 0CCB              MOVLW   PBSW3
0384 01E0 0026              MOVWF   PORTB
0385 01E1 0B8A              GOTO    SCAN2
0386 01E2 093B      REMOTE3 CALL    OUTPUT
0387 01E3 0BDE              GOTO    R3
0388                
0389                ; ----------   SELECT MODE   ----------
0390                
0391 01E4 0208      GOTONE  MOVF    TMP,W
0392 01E5 002B              MOVWF   KEY
0393                HELD
0394                NONE
0395 01E6 0945              CALL    WAIT
0396 01E7 0CC8              MOVLW   PBIP
0397 01E8 0026              MOVWF   PORTB
0398 01E9 0B8F              GOTO    SCAN1
0399 01EA 0040      SELECT  CLRW
0400 01EB 0FFF              XORLW   $FF
0401 01EC 0025              MOVWF   PORTA
0402                
0403 01ED 020B              MOVF    KEY,W
0404 01EE 0912              CALL    TRANS2
0405 01EF 0024              MOVWF   FSR
0406 01F0 0660              BTFSC   IND,KEYBIT
0407 01F1 0BE6              GOTO    HELD            ; KEY NOT RELEASED YET
0408                
0409 01F2 0C0E              MOVLW   14
0410 01F3 0028              MOVWF   TMP
0411 01F4 0C0C              MOVLW   NKEYS           ; GET HIGHEST PRIORITY KEY
0412 01F5 0029              MOVWF   I
0413                
0414 01F6 0208      PRIO    MOVF    TMP,W
0415 01F7 0912              CALL    TRANS2
0416 01F8 0024              MOVWF   FSR
0417 01F9 0660              BTFSC   IND,KEYBIT
0418 01FA 0BE4              GOTO    GOTONE          ; FOUND HIGHEST PRIORITY KEY
0419                
0420 01FB 00E8              DECF    TMP
0421 01FC 02E9              DECFSZ  I
0422 01FD 0BF6              GOTO    PRIO
0423 01FE 0BE6              GOTO    NONE            ; NO KEYS PRESSED
0424                
0425                        ORG     PIC54
0426 01FF 0B63      RESET   GOTO    INIT


Number of errors 0
