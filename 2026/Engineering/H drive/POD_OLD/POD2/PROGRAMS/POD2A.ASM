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

		ORG 	4H
		RETFIE

main		clrwdt
		call	input
		movf	output_reg,w	;check to see if the input has
		xorlw	0xFF		;changed
		btfsc	STATUS,Z
		goto	main
		call	debounce
		call	output		
		goto	main		

init		BSF	STATUS,5	; set bank 1
		BSF 	ADCON1,PCFG2	;porta is digital i/o
		BSF 	ADCON1,PCFG1
		movlw	0xFF
		movwf	TRISA		; porta is an input.
		movwf	TRISC		; portc is an input. *Must change
		clrf	TRISB		; set portb as an output.
		BCF	STATUS,5	; set bank 0
		movlw	0xFE
		movwf 	PORTB		;only input1 led is on.
		movwf	pre_output
		movlw	0xFE
		movwf	bcount		; debouncing counter
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
		movf	output_reg,0
		btfss	pre_output,6
		goto	mix
		btfsc	output_reg,6
		goto	no_mix
mix		xorwf	pre_output,0
		movwf	comp_reg
		comf	comp_reg,0
no_mix		movwf	pre_output
		movwf	PORTB
		movlw	0xFE
		movwf	bcount
same		call	input			; Debounce the release
		movf	output_reg,0
		xorlw	0xFF
		btfss	STATUS,2
		call	reset_bcount
		decfsz	bcount,1
		goto	same
		movlw	0xFE
		movwf	bcount
		return

bounceset	movf	output_reg,0
		movwf	bounce
		return

reset_bcount	movlw	0xFF
		movwf	bcount
		return


		END

