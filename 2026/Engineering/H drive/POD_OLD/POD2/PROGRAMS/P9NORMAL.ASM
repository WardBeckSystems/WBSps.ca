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
remote_flag	res	1
timer_end	res	1
spi_transmit	res	1
spi_output	res	1
spi_recieved	res	1
pre_spi		res	1

		ORG 	4H
		RETFIE
;***************************************************
;************   Main Program    ********************
;***************************************************
main		clrwdt
		btfsc	remote_flag,0
		goto	remote_control
		call	input
		btfss	rel_flag,0
		goto	release
		movf	output_reg,w	;check to see if the input has
		xorlw	0xFF		;changed
		btfsc	STATUS,Z
		goto	release
remote_control	call	debounce
		call	output		
release		btfss	remote_flag,0
		call	debounce_rel
		call	recieve_uart
		call	transmit_uart
		call	translate
		call	SPI_master
		call	timer_check
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
		bcf	TRISC,3
		bsf	TRISC,4
		bcf	TRISC,5
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
		bcf	transmit_flag,0
		bcf 	remote_flag,0
		movlw	0x07
		movwf	timer_end
		bcf	remote_flag,1
		bcf	remote_flag,2
		clrf	TMR2
		movlw	0xFF
		movwf	T2CON
		bcf	PIR1,TMR2IF
		clrf	SSPCON
		bsf	SSPCON,SSPEN
		movwf	SSPBUF
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
output		decfsz	bcount,1		;Check the debounce counter
		return				;output
		btfss	remote_flag,0
		goto	continue
		btfss	remote_flag,1
		return
		btfss	remote_flag,2
		goto	remote_out
		bcf	remote_flag,2
		bcf	remote_flag,0
		movf	pre_output,w
		movwf	output_reg
		goto	remote_out
continue	bcf	rel_flag,0
		btfss	pre_output,5
		call	next_output1
		btfsc	pre_output,5
		call	next_output2
		movf	output_reg,0
		movwf	pre_output
remote_out	movlw	0x08
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
		bcf	remote_flag,1	
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

recieve_uart	btfss	PIR1,RCIF
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
		return
		movf	recieved_reg,w
		movwf	output_reg
		bsf	remote_flag,0
		bsf	remote_flag,1
		bsf	transmit_flag,0
		return

transmit_uart	btfss	transmit_flag,0
		return
		BSF	STATUS,5	; set bank 1
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
		btfsc	recieved_reg,0		;Parity Check
		xorwf	parity,1
		btfsc	recieved_reg,1
		xorwf	parity,1	
		btfsc	recieved_reg,2
		xorwf	parity,1
		btfsc	recieved_reg,3
		xorwf	parity,1	
		btfsc	recieved_reg,4
		xorwf	parity,1
		btfsc	recieved_reg,5
		xorwf	parity,1	
		btfsc	recieved_reg,6
		xorwf	parity,1
		btfsc	recieved_reg,7
		xorwf	parity,1
		BSF	STATUS,5
		bcf	TXSTA,TX9D
		BCF	STATUS,5
		btfsc	parity,0
		call	set_parity
		movf	recieved_reg,w
		movwf	TXREG
		bcf	transmit_flag,0
		movlw	0x07
		movwf	timer_end
no_transmit	BCF	STATUS,5
		return

timer_check	btfss	PIR1,TMR2IF
		return
		clrf	T2CON
		clrf	TMR2
		bsf	spi_transmit,0
		movlw	0xFF
		movwf	T2CON
		bcf	PIR1,TMR2IF
		decfsz	timer_end,1
		return
		bsf	remote_flag,1
		bsf	remote_flag,2
		return

set_parity	BSF	STATUS,5
		bsf	TXSTA,TX9D
		BCF	STATUS,5
		return

translate	movf	spi_output,w
		movwf	pre_spi
		clrf	spi_output
		btfsc	pre_output,5
		bsf	spi_output,7
		btfsc	pre_output,6
		bsf	spi_output,0
		btfsc	pre_output,0
		bsf	spi_output,1
		btfsc	pre_output,7
		bsf	spi_output,2
		btfsc	pre_output,1
		bsf	spi_output,3
		btfsc	pre_output,3
		bsf	spi_output,4
		btfsc	pre_output,2
		bsf	spi_output,5
		return

SPI_master	BSF	STATUS,RP0
		btfss	SSPSTAT,BF
		goto	no_spi
		BCF	STATUS,RP0
		btfss	spi_transmit,0
		return
		movf	SSPBUF,w
		movwf	spi_recieved
		movf	spi_output,w
		movwf	SSPBUF
		movf	spi_recieved,w
		subwf	pre_spi,0
		btfsc	STATUS,Z
		bcf	spi_transmit,0
no_spi		BCF	STATUS,RP0		
		return	
		END

