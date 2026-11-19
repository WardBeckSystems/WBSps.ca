;Pod 9 Audio Switcher

	list	p=16C73A
	#include "P16C73A.INC"

		org	0
		call 	init
		call	output
		goto	main
	
		org	20h
output_reg	res	1
pre_output	res	1
bcount		res	1
bounce		res	1
comp_reg	res	1
rel_flag	res	1
parity		res	1
parity_check	res	1
recieved_reg	res	1
good_data	res	1
led_dance	res	1
led_count	res	1
shift_count	res	1
transmit_flag	res	1
recieve_flag	res	1
data_sent	res	1
nocomm_flag	res	1

		ORG 	4H
		RETFIE
;***************************************************
;************   Main Program    ********************
;***************************************************
main		clrwdt
		btfsc	nocomm_flag,0
		goto	no_comm
		btfsc	nocomm_flag,1
		goto	no_comm
		call	input
		btfss	rel_flag,0
		goto	release
		movf	output_reg,w	;check to see if the input has
		xorlw	0xFF		;changed
		btfsc	STATUS,Z
		goto	release
		call	debounce
no_comm		call	output		
release		call	debounce_rel
		btfsc	pre_output,5
		goto	main
		call	timer_check
		call	transmit
		call	recieve
		goto	main

;***************************************************
;***********    Initialization	 *******************
;***************************************************
init		BSF	STATUS,5	; set bank 1
		BSF 	ADCON1,PCFG2	;porta is digital i/o
		BSF 	ADCON1,PCFG1
		movlw	0xFF
		movwf	TRISA		; porta is an input.
		movwf	TRISC		; portc is an input. *Must change
		bcf	TRISC,0
		clrf	TRISB		; set portb as an output.
		movlw	0x07
		movwf	SPBRG		; Set the baudrate genetor
		bcf	TXSTA,SYNC	; Enable asynchonous mode
		bcf	TXSTA,BRGH	; Low mode baud rate
		bsf	TXSTA,TX9
		bsf	TXSTA,TXEN
		BCF	STATUS,5	; set bank 0
		movlw	0xBF
		movwf	output_reg
		movwf	pre_output
		movwf	led_count
		movlw	0x01
		movwf	bcount		; debouncing counter
		bsf	rel_flag,0
		bsf	RCSTA,SPEN	; Enable serial ports RC7 and RC6
		bsf	RCSTA,CREN	; Continuous recieve enabled
		bsf	RCSTA,RX9	; Nine bit recieve enabled
		bcf	PORTB,7
		bcf	PORTB,5
		bsf	transmit_flag,0
		bcf 	recieve_flag,0
		movlw	0xBE
		movwf	led_dance
		bcf	nocomm_flag,0
		return

;*****************************************************
;**********   Input Subroutine   *********************
;*****************************************************
input		clrf	output_reg
		btfsc	PORTA,3		;check input1
		bsf	output_reg,6	;
		btfsc	PORTA,2		;check input2
		bsf 	output_reg,0	
		btfsc	PORTA,5		;check input3
		bsf	output_reg,7
		btfsc	PORTA,4		;check input4
		bsf	output_reg,1
		btfsc	PORTC,2		;check input5
		bsf	output_reg,3
		btfsc	PORTC,1		;check input6
		bsf	output_reg,2	
		btfsc	PORTA,0		;check spare
		bsf	output_reg,4
		btfsc	PORTA,1		;check mix
		bsf	output_reg,5
		return

;*******************************************************
;************    Debounce Subroutine  ******************
;*******************************************************
debounce	movlw	0xFE
		xorwf	bcount,0	
		btfsc	STATUS,2
		call	bounceset
		movf	output_reg,0
		subwf	bounce,0
		btfss	STATUS,2
		call 	reset_bcount
		return	
	
;*******************************************************
;**************    Output Subrountine  *****************
;*******************************************************			 
output		btfsc	nocomm_flag,0
		goto	nocomm_out
		btfss	nocomm_flag,1
		goto	continue
		bcf	nocomm_flag,1
		goto	nocomm_out
continue	decfsz	bcount,1		;Check the debounce counter
		return				;output
		bcf	rel_flag,0
		btfss	pre_output,5
		call	next_output1
		btfsc	pre_output,5
		call	next_output2
		movf	output_reg,0
		movwf	pre_output
nocomm_out	movlw	0x08
		movwf	shift_count
shift_out	bcf	PORTB,6
		btfsc	output_reg,0
		bsf	PORTB,6
		bsf	PORTB,7
		bcf	PORTB,7
		rrf	output_reg,1
		decfsz	shift_count,1
		goto	shift_out
		bsf	PORTB,5
		bcf	PORTB,5
		movlw	0xFE
		movwf	bcount
		return

;***************************************************
next_output1	btfss	output_reg,5
		goto	if_clear
		bcf	output_reg,5
		return
if_clear	movf	pre_output,w
		movwf	output_reg
		bsf	output_reg,5
		return
;***************************************************
next_output2	btfsc	output_reg,5
		return
		movf	pre_output,w
		movwf	output_reg
		bcf	output_reg,5
		return
;***************************************************
;*********   Debounce Release Subroutine  **********
;***************************************************
debounce_rel	btfsc	rel_flag,0
		return
		movf	output_reg,0
		xorlw	0xFF
		btfss	STATUS,2
		call	reset_bcount
		decfsz	bcount,1
		return
		movlw	0xFE
		movwf	bcount
		bsf	rel_flag,0
		return		

bounceset	movf	output_reg,0
		movwf	bounce
		return

reset_bcount	movlw	0xFF
		movwf	bcount
		return

;*****************************************************
;*************    Timer Check Subrountine   **********
;*****************************************************
timer_check	btfss	PIR1,TMR2IF
		return
		clrf	T2CON
		clrf	TMR2
		bsf	transmit_flag,0
		btfsc	recieve_flag,0
		return
		movf	led_dance,w
		movwf	output_reg
		bsf	nocomm_flag,0
		decfsz	led_count,1
		return
		movlw	0xFF
		movwf	led_count
		btfsc	led_dance,6
		goto	next_led2
		bsf	led_dance,6
		bcf	led_dance,0
next_led2	btfsc	led_dance,0
		goto	next_led3
		bsf	led_dance,0
		bcf	led_dance,7
next_led3	btfsc	led_dance,7
		goto	next_led4
		bsf	led_dance,7
		bcf	led_dance,1
next_led4	btfsc	led_dance,1
		goto	next_led5
		bsf	led_dance,1
		bcf	led_dance,3
next_led5	btfsc	led_dance,3
		goto	next_led6
		bsf	led_dance,3
		bcf	led_dance,2
next_led6	btfsc	led_dance,2
		goto	next_led7
		bsf	led_dance,2
		bcf	led_dance,6
next_led7	return

transmit	BSF	STATUS,5	; set bank 1
		btfss	TXSTA,TRMT
		goto	no_transmit
		BCF	STATUS,5
		bcf	PORTC,0			;Set Transmit
		btfss	transmit_flag,0
		goto	no_transmit
		bcf	transmit_flag,0
		bsf	PORTC,0
		clrf	parity
		movlw	0x01
		btfsc	pre_output,0		;Parity Check
		xorwf	parity,1
		btfsc	pre_output,1
		xorwf	parity,1	
		btfsc	pre_output,2
		xorwf	parity,1
		btfsc	pre_output,3
		xorwf	parity,1	
		btfsc	pre_output,4
		xorwf	parity,1
		btfsc	pre_output,5
		xorwf	parity,1	
		btfsc	pre_output,6
		xorwf	parity,1
		btfsc	pre_output,7
		xorwf	parity,1
		BSF	STATUS,5
		bcf	TXSTA,TX9D
		BCF	STATUS,5
		btfsc	parity,0
		call	set_parity
		movf	pre_output,w
		movwf	data_sent
		movwf	TXREG
		movlw	0xFF
		movwf	T2CON
		bcf	PIR1,TMR2IF
		bcf	recieve_flag,0
no_transmit	BCF	STATUS,5
		return

recieve		btfss	PIR1,RCIF
		return	
		btfsc	RCSTA,FERR
		goto	aerror
		btfss	RCSTA,OERR
		goto	do_recieve
aerror		bcf	RCSTA,CREN
		bsf	RCSTA,CREN
do_recieve	clrf	parity
		btfsc	RCSTA,RX9D
		bsf	parity,0
		movf	RCREG,0
		movwf	recieved_reg
		clrf	parity_check
		movlw	0x01
		btfsc	recieved_reg,0		;Parity Check
		xorwf	parity_check,1
		btfsc	recieved_reg,1
		xorwf	parity_check,1	
		btfsc	recieved_reg,2
		xorwf	parity_check,1
		btfsc	recieved_reg,3
		xorwf	parity_check,1	
		btfsc	recieved_reg,4
		xorwf	parity_check,1
		btfsc	recieved_reg,5
		xorwf	parity_check,1	
		btfsc	recieved_reg,6
		xorwf	parity_check,1
		btfsc	recieved_reg,7
		xorwf	parity_check,1
		movlw	0x01
		andwf	parity,1
		andwf	parity_check,1
		movf	parity,0
		subwf	parity_check,0
		btfss	STATUS,Z
		bsf	transmit_flag,0
		movf	recieved_reg,0
		subwf	data_sent,0
		btfss	STATUS,Z
		bsf	transmit_flag,0
		btfss	transmit_flag,0
		bsf	recieve_flag,0
		btfsc	nocomm_flag,0
		bsf	nocomm_flag,1
		movf	pre_output,w
		movwf	output_reg
		bcf	nocomm_flag,0
		return

set_parity	BSF	STATUS,5
		bsf	TXSTA,TX9D
		BCF	STATUS,5
		return

	
		END

