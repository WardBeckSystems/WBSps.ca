;Pod 2 Audio Switcher

	list	p=16C73A
	#include "P16C73A.INC"

		org	0
		call 	init
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
comm_count	res	1




		ORG 	4H
		RETFIE

main		clrwdt
		call	input
		btfss	rel_flag,0
		goto	release
		movf	output_reg,w	;check to see if the input has
		xorlw	0xFF		;changed
		btfsc	STATUS,Z
		goto	release
		call	debounce
		call	output		
release		call	debounce_rel
		call 	transmit
		call	recieve
		call	no_comm
		goto	main

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
		movlw	0xFE
		movwf 	PORTB		;only input1 led is on.
		movwf	pre_output
		movlw	0xFE
		movwf	bcount		; debouncing counter
		bsf	rel_flag,0
		bsf	PORTC,0
		bsf	RCSTA,SPEN	; Enable serial ports RC7 and RC6
		bsf	RCSTA,CREN	; Continuous recieve enabled
		bsf	RCSTA,RX9	; Nine bit recieve enabled

		return

;This sub routine will check the inputs and return the corresponding
;inputs in a output_reg ready to be loaded into portb.

input		clrf	output_reg
		btfsc	PORTA,3		;check input1
		bsf	output_reg,0	;
		btfsc	PORTA,2		;check input2
		bsf 	output_reg,1	
		btfsc	PORTA,5		;check input3
		bsf	output_reg,2
		btfsc	PORTA,4		;check input4
		bsf	output_reg,3
		btfsc	PORTC,2		;check input5
		bsf	output_reg,4
		btfsc	PORTC,1		;check input6
		bsf	output_reg,5	
		btfsc	PORTA,0		;check spare
		bsf	output_reg,7
		btfsc	PORTA,1		;check mix
		bsf	output_reg,6
		return

debounce	movlw	0xFE
		xorwf	bcount,0	
		btfsc	STATUS,2
		call	bounceset
		movf	output_reg,0
		subwf	bounce,0
		btfss	STATUS,2
		call 	reset_bcount
		return	
	

output		decfsz	bcount,1		;Check the debounce counter
		return				;output
		bcf	rel_flag,0
		movf	output_reg,0
		btfss	pre_output,6
		goto	mix
		btfsc	output_reg,6
		goto	no_mix
mix		xorwf	pre_output,0
		movwf	comp_reg
		comf	comp_reg,0
no_mix		movwf	pre_output
;		movwf	PORTB
		movlw	0xFE
		movwf	bcount
		return

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
;*************************************************
;********* TRANSMIT SUBROUTINE  ******************
;*************************************************

transmit	BSF	STATUS,5	; set bank 1
		btfss	TXSTA,TRMT
		goto	no_transmit
		BCF	STATUS,5
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
		movwf	TXREG
no_transmit	BCF	STATUS,5
		return

;*****************************************************
;************ RECIEVE SUBROUTINE *********************
;*****************************************************
recieve		btfss	PIR1,RCIF
		return	
		btfsc	RCSTA,FERR
		goto	aerror
		btfss	RCSTA,OERR
		goto	do_recieve
aerror		bcf	RCSTA,CREN
		bsf	RCSTA,CREN
		return
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
		return
		movf	recieved_reg,0
		movwf	good_data		
		movwf	PORTB		;JUST TEST PURPOSE
		movlw	0xFF
		movwf	comm_count
		movwf	led_dance
		bcf	led_dance,0
		return

;*******************************************************
;************** SET THE PARITY BIT HIGH ****************
;*******************************************************	
set_parity	BSF	STATUS,5
		bsf	TXSTA,TX9D
		BCF	STATUS,5
		return

no_comm		decfsz	comm_count,1
		return
		movlw	0xFF
		movwf	comm_count
		movf	led_dance,w
		movwf	PORTB
		bsf	STATUS,C
		btfss	led_dance,5
		bcf	STATUS,C
		rlf	led_dance,1
		return
			
		END

