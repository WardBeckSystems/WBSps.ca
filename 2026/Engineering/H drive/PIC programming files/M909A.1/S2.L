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
0036      0008       I       EQU     08
0037      0009       KEY     EQU     09
0038                
0039      000A       KEYST   EQU     10              ; KEYSWITCH DEBOUNCE STATES
0040                
0041      000A       KEY1    EQU     10
0042      000B       KEY2    EQU     11
0043      000C       KEY3    EQU     12
0044      000D       KEY4    EQU     13
0045      000E       KEY5    EQU     14
0046      000F       KEY6    EQU     15
0047                
0048                ; ----------   EQUATES   ----------
0049                
0050      0006       NKEYS   EQU     6               ; NUMBER OF KEYS
0051                
0052                                                ; USE 4K7 AND 330pF FOR RC OSC
0053                                                ; OS2 = 125kHz
0054      000C       DELAY1  EQU     12              ; 250 msec with OPTION $06
0055      0065       DELAY2  EQU     101             ;   5 msec with OPTION $01
0056                
0057                ; ----------   NEXT STATE TABLE1   ----------
0058                
0059                        ORG     $000
0060                                        ; SET BIT 0 OF THE STATE TO INPUT
0061                                        ; BEFORE CALLING NEXT1
0062      0003       KEYBIT  EQU     3       ; BIT TEST KEYBIT AFTER CALLING NEXT1
0063                
0064 0000 0E0F      NEXT1   ANDLW   $0F     ; DEBOUNCE INPUT STATE MACHINE
0065 0001 01E2              ADDWF   PC
0066                
0067 0002 0800              RETLW   0       ; KEYBIT CLEAR WHILE INPUT=0
0068 0003 0802              RETLW   2
0069 0004 0800              RETLW   0
0070 0005 0804              RETLW   4
0071 0006 0800              RETLW   0
0072 0007 0806              RETLW   6
0073 0008 0800              RETLW   0
0074 0009 0808              RETLW   8       ; 4TH INPUT=1 SO SET KEYBIT
0075                
0076 000A 080A              RETLW   10
0077 000B 0808              RETLW   8       ; KEYBIT SET WHILE INPUT=1
0078 000C 080C              RETLW   12
0079 000D 0808              RETLW   8
0080 000E 080E              RETLW   14
0081 000F 0808              RETLW   8
0082 0010 0800              RETLW   0       ; 4TH INPUT=0 SO CLEAR KEYBIT
0083 0011 0808              RETLW   8
0084                
0085                ; ----------   INITIALIZATION CODE   ----------
0086                
0087                        ORG     $1B0
0088 01B0 0FFF      INIT    XORLW   $FF             ; UNPROGRAMED NOP
0089                
0090 01B1 0C0F              MOVLW   $0F
0091 01B2 0025              MOVWF   PORTA           ; INITIALIZE PORTA
0092 01B3 0C08              MOVLW   $08
0093 01B4 0005              TRIS    PORTA
0094                
0095 01B5 0CFF              MOVLW   $FF             ; INITIALIZE PORTB
0096 01B6 0006              TRIS    PORTB
0097                
0098 01B7 0C0A              MOVLW   KEYST           ; BLANK INPUT AND KEYSWITCH STATES
0099 01B8 0024              MOVWF   FSR
0100 01B9 0C06              MOVLW   NKEYS
0101 01BA 0028              MOVWF   I
0102 01BB 0060      BLANK   CLRF    IND
0103 01BC 02A4              INCF    FSR
0104 01BD 02E8              DECFSZ  I
0105 01BE 0BBB              GOTO    BLANK
0106                
0107 01BF 0C06              MOVLW   $06             ; RTCC = OSC2 / 128
0108 01C0 0002              OPTION
0109                
0110 01C1 0C06              MOVLW   NKEYS
0111 01C2 0028              MOVWF   I
0112                
0113 01C3 0C0C      SEQ1    MOVLW   DELAY1          ; RESET COUNTER
0114 01C4 0021              MOVWF   RTCC
0115                
0116 01C5 00C8              DECF    I,W
0117 01C6 0025              MOVWF   PORTA
0118                
0119 01C7 0201      SEQ2    MOVF    RTCC,W
0120 01C8 0743              BTFSS   STATUS,Z
0121 01C9 0BC7              GOTO    SEQ2            ; WAIT FOR TIME OUT
0122                
0123 01CA 02E8              DECFSZ  I
0124 01CB 0BC3              GOTO    SEQ1
0125                
0126 01CC 0C01              MOVLW   $01             ; RTCC = OSC2 / 4
0127 01CD 0002              OPTION
0128                
0129 01CE 0C0A              MOVLW   KEYST
0130 01CF 0024              MOVWF   FSR
0131                
0132                ; ----------   MAIN CODE   ----------
0133                
0134 01D0 0C0A      GOTONE  MOVLW   KEYST
0135 01D1 0084              SUBWF   FSR,W
0136 01D2 0029              MOVWF   KEY
0137                NONE
0138                HELD
0139 01D3 0209              MOVF    KEY,W
0140 01D4 0025              MOVWF   PORTA
0141                
0142 01D5 0201      WAIT    MOVF    RTCC,W
0143 01D6 0743              BTFSS   STATUS,Z
0144 01D7 0BD5              GOTO    WAIT            ; WAIT FOR TIME OUT
0145                
0146 01D8 0C65              MOVLW   DELAY2
0147 01D9 0021              MOVWF   RTCC            ; RESET COUNTER
0148                SCAN
0149 01DA 0706              BTFSS   PORTB,0
0150 01DB 02AA              INCF    KEY1
0151 01DC 0726              BTFSS   PORTB,1
0152 01DD 02AB              INCF    KEY2
0153 01DE 0746              BTFSS   PORTB,2
0154 01DF 02AC              INCF    KEY3
0155 01E0 0766              BTFSS   PORTB,3
0156 01E1 02AD              INCF    KEY4
0157 01E2 0786              BTFSS   PORTB,4
0158 01E3 02AE              INCF    KEY5
0159 01E4 07A6              BTFSS   PORTB,5
0160 01E5 02AF              INCF    KEY6
0161                
0162 01E6 0C0A              MOVLW   KEYST
0163 01E7 0024              MOVWF   FSR
0164 01E8 0C06              MOVLW   NKEYS
0165 01E9 0028              MOVWF   I
0166                
0167 01EA 0200      UPDATE  MOVF    IND,W
0168 01EB 0900              CALL    NEXT1
0169 01EC 0020              MOVWF   IND
0170 01ED 02A4              INCF    FSR
0171                
0172 01EE 02E8              DECFSZ  I
0173 01EF 0BEA              GOTO    UPDATE
0174                
0175 01F0 0C0A              MOVLW   KEYST           ; CHECK FOR RELEASE
0176 01F1 01C9              ADDWF   KEY,W
0177 01F2 0024              MOVWF   FSR
0178 01F3 0660              BTFSC   IND,KEYBIT
0179 01F4 0BD3              GOTO    HELD            ; KEY NOT RELEASED YET
0180                
0181 01F5 0C0A              MOVLW   KEYST
0182 01F6 0024              MOVWF   FSR
0183 01F7 0C06              MOVLW   NKEYS           ; GET HIGHEST PRIORITY KEY
0184 01F8 0028              MOVWF   I
0185                
0186                PRIO
0187 01F9 0660              BTFSC   IND,KEYBIT
0188 01FA 0BD0              GOTO    GOTONE          ; FOUND HIGHEST PRIORITY KEY
0189                
0190 01FB 02A4              INCF    FSR
0191 01FC 02E8              DECFSZ  I
0192 01FD 0BF9              GOTO    PRIO
0193 01FE 0BD3              GOTO    NONE            ; NO KEYS PRESSED
0194                
0195                        ORG     PIC54
0196 01FF 0BB0      RESET   GOTO    INIT


Number of errors 0
