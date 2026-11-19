Release Notes for MPASM Version 1.30.01 Intermediate
December 21, 1995
    
------------------------------------------------------------    
Contents    
------------------------------------------------------------    
    
This document contains the following:    
    
1. What's New    
2. How to Contact Microchip    
3. Overview of MPASM    
4. Instructions on Using MPASM    
5. Fixed SSRs (System Service Requests)    
6. Current SSR List    
7. Blank Bug Report Form    
    
------------------------------------------------------------    
What's New - v1.30.01
------------------------------------------------------------    

1. Support was added for the PIC16C52.

------------------------------------------------------------    
What's New - v1.30
------------------------------------------------------------    

1. Support is now in place for the following processors:

   16C54        16CR54*         16C54A       16CR54A*	
   16CR54B*     16C55           16C56        16CR56*
   16C57        16CR57A*        16CR57B*     16C58A  16CR58A*
   16CR58B*     16C5X           16C61        16C62	
   16C62A*      16C620          16C621       16C622  16C63
   16C64        16C64A*         16C65        16C65A* 16C70*	
   16C71        16C71A*         16C72*       16C73   16C73A*
   16C74        16C74A*         16CR83*      16C84   16CR84*
   16C84A*      16CXX           17C42        17C42A* 17C43	
   17C44        17CXX           14000*
	*-new product support

THESE PARTS MAY NOT ALL BE COMMERCIALLY AVAILABLE.

These can be chosen through the introductory screen, on the
command line, or in source file.  Three selections, 16C5X, 
16CXX, and 17CXX are also supported as generic family 
indicators.  

The standard header files have been updated to reflect these
devices.

2. The MPASM User's Guide and Quick Reference Guide have been 
revised.  Contact your local sales office for a hardcopy manual.  
An electronic version is also available on the BBS in .PDF format.
The Adobe Acrobat Reader, also available on the BBS, can be used 
to view, search, and print this file.


3. ***** The option "LIST FIXED" is now the default. *****
The LIST FIXED option will flag lines that do not conform to a 
fixed format.  It is HIGHLY recommended that you modify your code 
so these warnings do not appear.  

A fixed format parser is desirable for several reasons, mainly
because it is a much more robust design and is much less 
ambiguous for the user.  It will catch errors such as misspelled 
opcodes, rather than interpreting them as labels.  For backward 
compatibility, the "LIST FREE" option can be used to invoke the
free format parser.  Support for the "LIST FREE" option may 
disappear in a future release.

4. Several enhancements were made for integration with MPLAB.
These enhancements include:
        - Source file single-stepping through macros.
        - Error file cleaned up and verified.
        - Suppressed messages do not appear in the error file.

5.  Warnings and messages can be masked through the ERRORLEVEL
directive.  The syntax of ERRORLEVEL is:
        ERRORLEVEL      0|1|2|<+|-><message_number>
where
        0                 = All messages
        1                 = Errors and warnings
        2                 = Errors only
        +<message_number> = report message number <message_number>
        -<message_number> = suppress message number <message_number>
For example, the following will suppress all messages and warning
number 201:
        ERRORLEVEL      1, -201
Refer to the User's Guide for a list of all messages and their
numbers.  Errors cannot be suppressed.  Using the 0|1|2 will 
override any individual message reporting.

6. The cross reference file was enhanced.  Duplicate references
were eliminated, organization was improved, symbol type was 
added, and pagination was introduced.  The page width defaults to
80 columns, but the page length and width values specified 
for the list file by the LIST directive will be used.

7. Constants (symbols defined with EQU, CBLOCK, or CONSTANT) are
retained after the first pass, so forward references to constants
are allowed.  Note that constants cannot be calculated with
forward references.

8. Expanded source line length increased to 200 characters.  
If truncation occurs, an error will be reported.

9. Variable and constant values are shown in the list file as
32-bit values.

10. Position of the Windows interface screen is retained.

11. Assembly statistics were changed slightly.  The warning and
message counts were divided into reported and suppressed, and 
the Windows interface reports the total number of lines
assembled.  Also in the Windows version, if errors were found, 
the Percent Complete bar changes from green to red.

12. Use of the OPTION and TRIS instructions in the 16Cxx family,
which is not recommended by Microchip, is flagged with a 
message.

------------------------------------------------------------    
How To Contact Microchip    
------------------------------------------------------------    
    
As with any software product, users may have questions about    
MPASM.  These questions can be posed to Microchip in the    
following ways:    
    
1. Contact your regional sales office.    
    
2. Contact your local distributor or representative.    
    
3. Connect worldwide to the Microchip BBS using the    
CompuServe communications network.  In most cases a local    
call is your only expense.  The Microchip BBS connection    
does not use CompuServe membership services, therefore you    
do not need CompuServe membership to use the Microchip BBS.    
    
The procedure to connect will vary slightly from country to    
country.  Please check with your local CompuServe agent for    
details if you have a problem.  CompuServe services allow    
multiple users at baud rates up to 14400.    
    
4. Contact the Microchip Technology Development    
Systems Information and Upgrade Line at 1-800-755-2345 in    
the United States and parts of Canada and 1-602-786-7302 
from everywhere else.    
    
5. Contact the Corporate Applications Group at 1-800-437-2767
in the United States and parts of Canada and 1-602-786-7627
from everywhere else.
    
------------------------------------------------------------    
Overview of MPASM    
------------------------------------------------------------    
    
MPASM is a Universal Assembler.  It supports the    
PIC16C5X, PIC16CXX and PIC17CXX families.  This is a step    
forward toward more synergistic tools for the PIC16/17    
microcontrollers.  It is the only assembler supported by
Microchip.
   
------------------------------------------------------------    
Instructions on Using MPASM    
------------------------------------------------------------    
    
Create your source code with any text editor.  The file 
should contain ASCII text only.  Assemble your code with the 
command line:
	
	MPASM <file>[.asm]    
    
Correct any syntax problems, referring to the MPASM User's 
Guide for syntax help.  MPASM assembles with INHX8M as the 
default hex output, and generates a listing file, error file,
and .COD file.
    
MPASM currently runs in DOS real mode.  If you have "out of 
memory" problems, try using the DOS protected mode (DPMI) 
version.  To use this assembler, you must have the files 
RTM.EXE and DPMI16BI.OVL (distributed with this release) 
available in your path or in the current directory.  You must 
also have EMM386 or another memory manager running or run the 
assembler from a Windows DOS box.  To invoke this assembler, 
use the command:

	MPASM_DP <file>[.asm]    

A version of MPASM is also available for Windows.  To invoke 
this assembler, execute:

	MPASMWIN.EXE

from within Windows.  You will then be given a Windows
interface window.  Help on using the interface is provided
on-line.  MPASMWIN can also be invoked with parameters or 
through drag-and-drop.  In these cases, the interface 
screen is not displayed and assembly begins immediately.

------------------------------------------------------------    
Using MPASM with Other Microchip Tools
------------------------------------------------------------    

PICMASTER

To enable source code display in the PICMASTER Program Memory
Dump window, the code that you are debugging must have been 
compiled with MPASM.  The MPASM assembler creates a .COD file 
that contains the necessary source and object cross reference 
necessary to do source code display.    
    
To activate Source Code Display, select Utility from the    
main menu of PICMASTER, then select Screen Options from the    
drop-down menu.  The Screen Options dialog box will appear.     
Select the Source Code Display Radio button and click on OK.     
The program memory dump window will reformat with your    
source code.    
      

MPSIM

Version 4.13 and later of MPSIM provide basic symbol    
support for the MPASM symbol file (.COD) and the MPASM    
listing file.  Version 4.16 and later of MPSIM use the MPASM 
symbol file (.COD) by default.  To enable this feature on 
earlier versions, invoke MPSIM with the "-C" option (implies 
enable COD input).    

MPSIM v5.10 or greater requires MPASM v1.20 or greater.
    
------------------------------------------------------------    
System Service Requests (SSRs) Fixed Since Previous Release    
------------------------------------------------------------    
    
The following list describes the SSRs that were fixed for    
this release:    
  
SSRID 
Description 

Bug Fixes:

1618
Nested parameterized #defines are not handled correctly.

1756
Local labels passed to macros are not found.

1861
MPASM locks up on unmatched quotes on radix specification (B'10").

1923
Question mark (?) not supported as a valid label character.

1928
Nested macro calls appear in list file even if expansion turned off.

2060
Quoted parenthesis within evaluation parentheses causes error.

2061
LGOTO does not go to addresses in upper half of page.

2074
CALLing a macro name does not produce an error.

------------------------------------------------------------    
Current SSR (System Service Request) List    
------------------------------------------------------------    
    
The list shown below is the current list of known problems     
related to MPASM.  These problems (referenced by the     
respective SSR number) are tracked throughout the lifetime   
of the software product.  Microchip Technology will make a     
best effort to resolve these problems as time and resources     
allow.  If you encounter any problem or wish to see a new     
feature, please contact Microchip (see the second section of     
this document on how to contact Microchip).    
    
MPASM also has a number of outstanding design requests.      
Design requests are not represented in this list.    
    
SSR #    
Description    
    
288
Implement CBANK definitions 

442
Implement ARG and NARG in the macro language

1068
Add list directive to omit code conditionally not assembled

2057
Eliminate the DOS shell interface

2070
Enhance CBLOCK to allow labels to have a "size".

-----------------------------------------------------------    
	Blank System Service Request    
-----------------------------------------------------------    
    
    
Blank System Service Request Form    
Microchip    
Product:      ______________________________________________    
    
Description:  ______________________________________________    
    
Date:             
______________________________________________    
    
SVR:          ______________________________________________    
    
Reported By:  ______________________________________________    
    
Detailed     
Description:  ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
    
    
Microchip    
Product:      ______________________________________________    
    
Description:  ______________________________________________    
    
Date:             
______________________________________________    
    
SVR:          ______________________________________________    
    
Reported By:  ______________________________________________    
    
Detailed     
Description:  ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
	      ______________________________________________    
    
Microchip Technology System Service Request    
Fax to (602) 786-7578    

