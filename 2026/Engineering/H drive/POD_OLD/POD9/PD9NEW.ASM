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
recieved_reg	res	1
shift_count	res	1
transmit_flag	res	1
remote_flag	res	1
spi_transmit	res	1
spi_output	res	1
spi_recieved	res	1
input_reg	res	1
input_flag	res	1
spi_reg		res	1
output_flag	res	1
audio		res	1
video_reg	res	1
uart_flag	res	1
transmit_reg	res	1
spi_count	res	1
spi_output_temp	res	1
which_flag	res	1
temp		res	1
spi_tran_count	res	1
spi_rec_count	res	1
audio_count	res	1
switch_flag	res	1
switch_count	res	1


		ORG 	4H
		RETFIE

video_table	addwf	PCL,1
		nop
		retlw	0xBF
		retlw	0xFE
		retlw	0x7F
		retlw	0xFD
		retlw	0xF7
		retlw	0xFB
		return

audio_table	addwf	PCL,1
		nop
		retlw	0xFE
		retlw	0xFD
		retlw	0xFB
		retlw	0xF7
		retlw	0xEF
		retlw	0xDF
		return

;***************************************************
;************   Main Program    ********************
;***************************************************
main		clrwdt
		call	input
		call	debounce
		call	router
		call	output
		call	switch_check		
		call	debounce_rel
		call	recieve_uart
		call	reset_uart
		call	translate_uart
		call	transmit_uart
		call	SPI_trns_cntrl
		call	SPI_master
		call	SPI_rcv_ctrl
		call	timer_check
		goto	main

;***************************************************
;***********    Initialization	 *******************
;***************************************************
init		BSF	STATUS,5	; set bank 1
		BSF 	ADCON1,PCFG2	;porta is digital i/o
		BSF 	ADCON1,PCFG1
		movlw	0xFF
		movwf	TRISA
		movlw	0x96		; porta is an input.
		movwf	TRISC		; portc is an input. *Must change
		clrf	TRISB
		bsf	TRISB,0		; set portb as an output.
		movlw	0x07
		movwf	SPBRG		; Set the baudrate genetor
		movwf	spi_count
		bcf	TXSTA,SYNC	; Enable asynchonous mode
		bcf	TXSTA,BRGH	; Low mode baud rate
		bsf	TXSTA,TXEN
		BCF	STATUS,5	; set bank 0
		movlw	0xBF
		movwf 	output_reg		;only input1 led is on.
		movwf	pre_output
		movlw	0xFE
		movwf	bcount
		bsf	PORTB,6
		bcf	PORTB,7		; debouncing counter
		bcf	rel_flag,0
		bsf	PORTC,0
		bsf	RCSTA,SPEN	; Enable serial ports RC7 and RC6
		bsf	RCSTA,CREN	; Continuous recieve enabled
		clrf	TMR2
		movlw	0xFF
		movwf	T2CON
		movwf	audio
		movwf	spi_output
		movwf	spi_output_temp
		bcf	PIR1,TMR2IF
		clrf	remote_flag
		clrf	SSPCON
		bsf	SSPCON,SSPEN
		clrf	rel_flag
		clrf	input_flag
		bsf	output_flag,0
		movlw	0xFF
		movwf	SSPBUF
		movlw	0x20
		movwf	audio_count
		movwf	spi_tran_count
		movlw	0x03
		movwf	switch_count
		movwf	spi_rec_count
		bcf	PORTB,5
		clrf	switch_flag
		bsf	PORTB,4
		bsf	PORTB,3
		return

;*****************************************************
;**********   Input Subroutine   *********************
;*****************************************************
input		clrf	input_reg
		btfsc	PORTA,3		;check input1
		bsf	input_reg,6	;
		btfsc	PORTA,2		;check input2
		bsf 	input_reg,0	
		btfsc	PORTA,5		;check input3
		bsf	input_reg,7	
		btfsc	PORTA,4		;check input4
		bsf	input_reg,1
		btfsc	PORTC,2		;check input5
		bsf	input_reg,3
		btfsc	PORTC,1		;check input6
		bsf	input_reg,2	
		btfsc	PORTA,0		;check spare
		bsf	input_reg,4
		bsf	input_reg,5
		btfsc	PORTA,1		;check mix
		return
		bcf	input_reg,5
		bsf	input_flag,7
		return

;*******************************************************
;************    Debounce Subroutine  ******************
;*******************************************************
debounce	btfsc	rel_flag,0
		return
		movf	input_reg,w	;check to see if the input has
		xorlw	0xFF		;changed
		btfsc	STATUS,Z
		goto	bcount_reset
		movlw	0xFE
		xorwf	bcount,w	
		btfsc	STATUS,2
		call	bounceset
		movf	input_reg,w
		subwf	bounce,w
		btfss	STATUS,2
bcount_reset	call 	reset_bcount
		decfsz	bcount,1
		return
		movlw	0xFE
		movwf	bcount
		bsf	rel_flag,0
		bsf	input_flag,0
		bsf	input_flag,1
		clrf	remote_flag
		return	
	
;*******************************************************
;**************    Output Subrountine  *****************
;*******************************************************			 
router		btfss	input_flag,0
		goto	next_route0
		bcf	input_flag,0
		btfss	pre_output,5
		call	next_output1
		btfsc	pre_output,5
		call	next_output2
		movf	input_reg,w
		movwf	output_reg
		movwf	pre_output
		bsf	output_flag,0
		return
next_route0	btfss	remote_flag,0
		goto	next_route1
		bcf	remote_flag,0
		movf	spi_reg,w
		movwf	output_reg
		movwf	pre_output
		bsf	output_flag,0
		return
next_route1	btfss	remote_flag,1
		return
		movf	video_reg,w
		movwf	output_reg
		bsf	output_flag,0
		bcf	remote_flag,1
		return
	
;***********************************
output		btfss	output_flag,0
		return
		bcf	PORTB,5
		bcf	PORTB,7
		movf	output_reg,w
		movwf	pre_output
		bsf	switch_flag,0
		bcf	output_flag,0
		movlw	0x08
		movwf	shift_count
shift_out	bcf	PORTB,6
		btfsc	output_reg,0
		bsf	PORTB,6
		bsf	PORTB,7
		bsf	PORTB,7
		bcf	PORTB,7
		rrf	output_reg,1
		decfsz	shift_count,1
		goto	shift_out
		bsf	PORTB,5
		bsf	PORTB,5
		bcf	PORTB,5
		movlw	0xFE
		movwf	bcount
		return

;***************************************************
switch_check	btfss	switch_flag,0
		return
		btfsc	switch_flag,1
		goto	do_switch
		btfsc	PORTB,0
		return
do_switch	clrf	switch_flag
		bsf	PORTB,4
		bsf	PORTB,3
		bcf	PORTB,2
		bcf	PORTB,1
		btfsc	pre_output,6
		goto	switch_2
		bcf	PORTB,3
		return
switch_2	btfsc	pre_output,0
		goto	switch_3
		bsf	PORTB,1
		bcf	PORTB,3
		return
switch_3	btfsc	pre_output,7
		goto	switch_4
		bsf	PORTB,2
		bcf	PORTB,3
		return
switch_4	btfsc	pre_output,1
		goto	switch_5
		bcf	PORTB,4
		return
switch_5	btfsc	pre_output,3
		goto	switch_6
		bsf	PORTB,1
		bcf	PORTB,4
		return
switch_6	bsf	PORTB,2
		bcf	PORTB,4
		return

;***************************************************
next_output1	btfss	input_reg,5
		goto	if_clear
		bcf	input_reg,5
		return
if_clear	movf	pre_output,w
		movwf	input_reg
		bsf	input_reg,5
		return
;***************************************************
next_output2	btfsc	input_reg,5
		return
		movf	pre_output,w
		movwf	input_reg
		bcf	input_reg,5
		return
;***************************************************
;*********   Debounce Release Subroutine  **********
;***************************************************
debounce_rel	btfss	rel_flag,0
		return
		movf	input_reg,0
		xorlw	0xFF
		btfss	STATUS,2
		call	reset_bcount
		decfsz	bcount,1
		return
		movlw	0xFE
		movwf	bcount
		bcf	rel_flag,0
		return		

bounceset	movf	input_reg,0
		movwf	bounce
		return

reset_bcount	movlw	0xFF
		movwf	bcount
		return
;*************************************
recieve_uart	btfss	PIR1,RCIF
		return	
		btfsc	RCSTA,FERR
		goto	aerror
		btfss	RCSTA,OERR
		goto	do_recieve
aerror		bcf	RCSTA,CREN
		bsf	RCSTA,CREN
do_recieve	movf	RCREG,w
		movwf	recieved_reg
		bsf	transmit_flag,0
		return

reset_uart	btfss	transmit_flag,0
		return
		BSF	STATUS,5	; set bank 1
		movlw	0x07
		movwf	SPBRG		; Set the baudrate genetor
		bcf	TXSTA,SYNC	; Enable asynchonous mode
		bcf	TXSTA,BRGH	; Low mode baud rate
		bsf	TXSTA,TXEN
		BCF	STATUS,5	; set bank 0
		bsf	RCSTA,SPEN	; Enable serial ports RC7 and RC6
		bsf	RCSTA,CREN	; Continuous recieve enabled
		return

;************************************
translate_uart	btfss	transmit_flag,0
		return
		movf	recieved_reg,w
		xorlw	0xF0		
		btfss	STATUS,Z
		goto	next_check1
		bsf	uart_flag,7
		bcf	transmit_flag,0
		return
next_check1	btfss	uart_flag,7
		return
		bcf	uart_flag,7		
		btfsc	recieved_reg,7			;start 0xxx xxxx check
		goto	next_check2
		btfsc	recieved_reg,6			;start 00xx xxxx check
		goto	sum_audio
		btfsc	which_flag,0			;if 00xx xxxx
		goto	send_audio
		bsf	which_flag,0
		movlw	0xFF
		movwf	transmit_reg
		btfss	pre_output,6
		bcf	transmit_reg,0
		btfss	pre_output,0
		bcf	transmit_reg,1
		btfss	pre_output,7
		bcf	transmit_reg,2
		btfss	pre_output,1
		bcf	transmit_reg,3
		btfss	pre_output,3
		bcf	transmit_reg,4
		btfss	pre_output,2
		bcf	transmit_reg,5
		btfss	pre_output,5
		bcf	transmit_reg,6
		bsf	spi_output,6
		comf	transmit_reg
		bsf	transmit_reg,7
		return
send_audio	bcf	which_flag,0
		movf	audio,w
		movwf	transmit_reg
		comf	transmit_reg
		bcf	transmit_reg,7				;end 00xx xxxx
		return
sum_audio	comf	recieved_reg
		movf	recieved_reg,w
		call	spi_uart_setup	;*******TEST********
		bcf	spi_output_temp,6
		bcf	remote_flag,0		
		clrf	input_flag
		bsf	remote_flag,1
		movf	pre_output,w
		movwf	video_reg
		bsf	video_reg,5
		return				;end 01xx xxxx
next_check2	btfsc	recieved_reg,6
		goto	slave_mode
		movlw	0x38			;start 10xx xxxx
		andwf	recieved_reg,w
		btfsc	STATUS,Z
		goto	audio_only
		movwf	temp
		bcf	STATUS,C
		rrf	temp
		rrf	temp
		rrf	temp
		movf	temp,w
		call 	video_table
		movwf	video_reg
		bsf	remote_flag,1
audio_only	movlw	0x07
		andwf	recieved_reg,w
		btfsc	STATUS,Z
		return
		call	audio_table
		call	spi_uart_setup
		btfsc	audio,6
		goto	check_if_slave
		movf	audio,w
		call	spi_uart_setup
		bsf	spi_output_temp,6
		return
check_if_slave	btfsc	pre_output,5
		return
		movf	pre_output,w
		movwf	video_reg
		bsf	video_reg,5
		bsf	remote_flag,1
		call	spi_uart_setup
		bsf	spi_output_temp,7
		return
slave_mode	movlw	0x07
		andwf	recieved_reg,w
		btfsc	STATUS,Z
		return
		call	video_table
		movwf	video_reg
		bcf	video_reg,5
		clrf	input_flag
		clrf	remote_flag
		bsf	remote_flag,1
		movlw	0x07
		andwf	recieved_reg,w
		call	audio_table
		call 	spi_uart_setup
		bsf	spi_output_temp,6
		btfss	pre_output,5		;test
		return
		movf	audio,w
		call	spi_uart_setup
		bsf	spi_output_temp,6
		movf	pre_output,w
		movwf	video_reg
		bcf	video_reg,5
		return				;test

spi_uart_setup	movwf	spi_output_temp
		bcf	spi_output_temp,7
		movlw	0xF0
		movwf	spi_output
		bsf	remote_flag,2
		bsf	remote_flag,3		
		return

;*************************************		
transmit_uart	BSF	STATUS,5	; set bank 1
		btfss	TXSTA,TRMT
		goto	no_transmit
		BCF	STATUS,5
		bcf	PORTC,0			;Set Transmit
		btfss	transmit_flag,0
		goto	no_transmit
		bcf	transmit_flag,0
		bsf	PORTC,0
		movf	transmit_reg,w
		movwf	TXREG
no_transmit	BCF	STATUS,5
		return

;**********************************
timer_check	btfss	PIR1,TMR2IF
		return
		clrf	T2CON
		clrf	TMR2
		bsf	spi_transmit,0
		movlw	0xFF
		movwf	T2CON
		bcf	T2CON,T2CKPS1
		bcf	T2CON,T2CKPS0
		bcf	PIR1,TMR2IF
		decfsz	audio_count
		goto	synch_check
		movlw	0x20
		movwf	audio_count
		movlw	0xFF
		movwf	audio
synch_check	btfss	switch_flag,0
		return
		decfsz	switch_count
		return
		bsf	switch_flag,1
		movlw	0x03
		movwf	switch_count
		return		



SPI_trns_cntrl	btfss	spi_transmit,0
		return
		btfss	remote_flag,3
		goto	next_rem
		movlw	0xF0
		movwf	spi_output
		bcf	remote_flag,3
		return
next_rem	btfss	remote_flag,2
		goto	tran_spi
		movf	spi_output_temp,w
		movwf	spi_output
		bcf	remote_flag,2
		decfsz	spi_tran_count
		goto	more_spi
		movlw	0x20
		movwf	spi_tran_count
		return
tran_spi	btfsc	spi_transmit,1
		goto	next_spi
		movlw	0xF0
		movwf	spi_output
		bsf	spi_transmit,1
		return
next_spi	bcf	spi_transmit,1
		movlw	0xFF
		movwf	spi_output
		btfss	input_flag,1
		goto	no_out_spi
		call	spi_tran_setup
		btfsc	input_flag,7
		goto	spi_special
		btfsc	pre_output,5
		goto	no_out_spi
		bcf	spi_output,7
no_out_spi	btfss	pre_output,6
		bcf	spi_output,0
		btfss	pre_output,0
		bcf	spi_output,1
		btfss	pre_output,7
		bcf	spi_output,2
		btfss	pre_output,1
		bcf	spi_output,3
		btfss	pre_output,3
		bcf	spi_output,4
		btfss	pre_output,2
		bcf	spi_output,5
		btfss	pre_output,5
		bcf	spi_output,6
		btfss	spi_output,7
		bsf	spi_output,6
		return
more_spi	bsf	remote_flag,2
		bsf	remote_flag,3
		return
spi_special	btfss	input_flag,1
		bcf	input_flag,7
		movf	audio,w
		movwf	spi_output
		bsf	spi_output,6
		bcf	spi_output,7
		return

spi_tran_setup	decfsz	spi_tran_count
		return
		bcf	input_flag,1
		movlw	0x20
		movwf	spi_tran_count
		return
;*************************************
		
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
		decfsz	spi_count,1
		return
		movlw	0x07
		movwf	spi_count
no_spi		BCF	STATUS,RP0		
		return
	

SPI_rcv_ctrl	btfss	spi_transmit,0
		return
		bcf	spi_transmit,0
		movf	spi_recieved,w
		sublw	0xF0
		btfss	STATUS,Z
		goto	spi_rec_next
		bsf	spi_transmit,2
		return
spi_rec_next	btfss	spi_transmit,2
		goto	reset_rec_count
		bcf	spi_transmit,2
		btfss	spi_recieved,7
		goto	no_update
		movlw	0x20
		movwf	audio_count
		movf	spi_recieved,w
		movwf	audio
		bcf	audio,7
		return
no_update	call	spi_rec_setup
		movlw	0xFF
		movwf	spi_reg
		movf	spi_recieved,w
		btfsc	STATUS,Z
		return
		btfsc	spi_recieved,0
		goto	next_recie0
		bcf	spi_reg,6
		goto	next_recie5
next_recie0	btfsc	spi_recieved,1
		goto	next_recie1
		bcf	spi_reg,0
		goto	next_recie5
next_recie1	btfsc	spi_recieved,2
		goto	next_recie2
		bcf	spi_reg,7
		goto	next_recie5
next_recie2	btfsc	spi_recieved,3
		goto	next_recie3
		bcf	spi_reg,1
		goto	next_recie5
next_recie3	btfsc	spi_recieved,4
		goto	next_recie4
		bcf	spi_reg,3
		goto	next_recie5
next_recie4	btfsc	spi_recieved,5
		goto	next_recie5
		bcf	spi_reg,2
next_recie5	btfsc	spi_recieved,6
		return
		bcf	spi_reg,5
		return

spi_rec_setup	decfsz	spi_rec_count
		return
		bsf	remote_flag,0
reset_rec_count	movlw	0x03
		movwf	spi_rec_count
		return


		END

