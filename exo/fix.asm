; fix.asm - the fixes for RW1_EDIT.EXE 1.0.4 (see ../NOTES.md, "Fixes"), as a new
; section of the program at 00415000. exo/build_fix.py assembles it (NASM) and
; points the patched places of the original code at the jump table below.
;
; Every routine does what rw1edit.py does with Editor(fixes=True) - the A/B test
; (tests/ab.py fuzz --fixed) compares the two.

bits 32
org 0x415000

; the original's globals
EDITOR      equ 0x40E9F0        ; the editor object: +0 i, +4 j, +8 tmp, +C cur, +10 top, +14 head, +18 tail
ROW         equ 0x40E7A4
COL         equ 0x40E7A8
HSCROLL     equ 0x40E7AC
TOPIDX      equ 0x40E7B0
MAXCOL      equ 0x40EB30
INSERT      equ 0x40E880
REDRAW      equ 0x40EE88
NLINES      equ 0x40D078
C0          equ 0x40D060
C1          equ 0x40D064
L0          equ 0x40D068
L1          equ 0x40D06C
P0          equ 0x40D070
P1          equ 0x40D074
MODIFIED    equ 0x40D088
CW          equ 0x40E94C
FILENAME    equ 0x40EA28
ERRBUF      equ 0x40F098
LINE_MAX    equ 254             ; the line length save can handle (it writes text, LF, NUL)

; line node
PREV        equ 0x100
NEXT        equ 0x104
LEN         equ 0x108

; the original's functions
FN_NEWLINE  equ 0x40165D        ; thiscall (this, after): new line
FN_SAVE     equ 0x401502        ; thiscall (this, name)
FN_DELETE   equ 0x401757        ; thiscall (this, line)
FN_LEFT     equ 0x402388
FN_RIGHT    equ 0x4023D9
FN_SWAP     equ 0x402895        ; fastcall (ecx = editor)
FN_SAVEDLG  equ 0x402E13        ; cdecl (hwnd): the Save as dialog, the name or ""
FN_ERRFMT   equ 0x4037B1        ; cdecl (code, text) into ERRBUF
FN_STRCPY   equ 0x406AC0
FN_NEW      equ 0x406CD0
FN_SPRINTF  equ 0x407020
IMP_GLOBALALLOC     equ 0x411328
IMP_SETWINDOWTEXT   equ 0x41135C
IMP_CLOSECLIPBOARD  equ 0x411364
IMP_MESSAGEBOX      equ 0x411390
STR_SAVEERR equ 0x40D22C        ; "Save file error"
STR_ERROR   equ 0x40D23C        ; "Error"
STR_TITLE   equ 0x40D244        ; "RW1-Editor :  %s"

; ---------------------------------------------------------------------------
; the jump table: build_fix.py knows the entries by their number (5 bytes each)

    jmp near expand         ; 0  load: TAB expansion and code page, at most 254 characters
    jmp near load_end       ; 1  load: never no lines at all
    jmp near key_bs         ; 2  Backspace: no join past LINE_MAX
    jmp near key_space      ; 3  space: no insert past LINE_MAX
    jmp near key_default    ; 4  a character: not past LINE_MAX
    jmp near key_y1         ; 5  Ctrl+Y: remember the line deleted
    jmp near key_y2         ; 6  Ctrl+Y: the first line on the screen
    jmp near del_join       ; 7  Del at a line end: no join past LINE_MAX
    jmp near word_right     ; 8  Ctrl+Right: not past the line end of the next line
    jmp near word_left      ; 9  Ctrl+Left: not above the first line
    jmp near copy_buffer    ; 10 copy: a buffer large enough
    jmp near copy_null      ; 11 copy: the text ends before the selection does
    jmp near copy_clamp     ; 12 copy: the last line up to its end
    jmp near select_all     ; 13 Select all: up to the last line
    jmp near global_alloc   ; 14 copy: a clipboard block large enough
    jmp near close_clip     ; 15 paste without text: close the clipboard
    jmp near del_selection  ; 16 delete a selection: in order, within the lines
    jmp near drag_column    ; 17 mouse drag: only to a column the cursor can reach
    jmp near ask_open       ; 18 "Save it?" Yes for a new text: Save as (Open)
    jmp near ask_compile    ; 19 (Compile)
    jmp near ask_run        ; 20 (Run)
    jmp near ask_exit       ; 21 (Exit)
TABLE_END:
%if TABLE_END - $$ != 22 * 5
%error "the jump table must have 5-byte entries"
%endif

; ---------------------------------------------------------------------------
; load (FUN_004011d0)

; cdecl expand(char *buf): each TAB becomes 8 spaces, each character goes through
; the CP866 -> CP1251 conversion (FUN_004010d0); at most LINE_MAX characters
expand:
    push esi
    push edi
    push ebx
    mov esi, [esp+16]
    mov edi, tmpbuf
    xor ecx, ecx
.next:
    mov al, [esi]
    test al, al
    jz .end
    inc esi
    cmp al, 9
    jne .char
    mov ebx, 8
.space:
    cmp ecx, LINE_MAX
    jge .end
    mov byte [edi+ecx], ' '
    inc ecx
    dec ebx
    jnz .space
    jmp .next
.char:
    cmp ecx, LINE_MAX
    jge .end
    mov dl, al
    and dl, 0xF0
    cmp dl, 0x80
    je .plus40
    cmp dl, 0x90
    je .plus40
    cmp dl, 0xA0
    je .plus40
    cmp dl, 0xE0
    jne .store
    add al, 0x10
    jmp .store
.plus40:
    add al, 0x40
.store:
    mov [edi+ecx], al
    inc ecx
    jmp .next
.end:
    mov byte [edi+ecx], 0
    inc ecx
    mov edi, [esp+16]
    mov esi, tmpbuf
    rep movsb
    pop ebx
    pop edi
    pop esi
    ret

; the epilogue of the load routine: an empty file, or one that could not be opened,
; leaves no lines - and WM_PAINT divides by the line count. One empty line instead.
load_end:
    push eax
    mov ecx, [ebp-0x110]                ; this
    cmp dword [ecx+0x14], 0
    jne .done
    push 0
    call FN_NEWLINE
    mov ecx, [ebp-0x110]
    mov eax, [ecx+0x18]
    mov dword [eax+LEN], 0
    mov eax, [ecx+0x14]
    mov [ecx+0x10], eax
    mov [ecx+0xC], eax
    xor eax, eax
    mov [TOPIDX], eax
    mov [HSCROLL], eax
    mov [ROW], eax
    mov [COL], eax
.done:
    pop eax
    pop edi
    pop esi
    pop ebx
    leave
    ret 4

; ---------------------------------------------------------------------------
; typing (FUN_00401805, this at [ebp-8]; its end at 00402095)

KEY_END     equ 0x402095

; case 8 at the start of a line: joining it to the line above must fit
key_bs:
    mov eax, [HSCROLL]
    add eax, [COL]
    cmp eax, 1
    jge .orig
    mov ecx, [ebp-8]
    mov edx, [ecx+0xC]                  ; cur
    cmp eax, [edx+LEN]
    jg .orig
    cmp [ecx+0x14], edx                 ; head
    je .orig
    mov eax, [edx+PREV]
    mov eax, [eax+LEN]
    add eax, [edx+LEN]
    cmp eax, LINE_MAX
    jle .orig
    mov dword [REDRAW], 1
    mov ecx, [ebp-8]
    call FN_LEFT
    jmp KEY_END
.orig:
    jmp 0x401A03

; case 0x20 inserted within the text: one more character must fit
key_space:
    mov ecx, [ebp-8]
    mov edx, [ecx+0xC]
    mov eax, [HSCROLL]
    add eax, [COL]
    mov ecx, [edx+LEN]
    dec ecx
    cmp eax, ecx
    jg .orig
    cmp dword [INSERT], 0
    je .orig
    mov eax, [edx+LEN]
    inc eax
    cmp eax, LINE_MAX
    jle .orig
    jmp KEY_END
.orig:
    jmp 0x401CE5

; any other character: the line it makes must fit
key_default:
    mov ecx, [ebp-8]
    mov edx, [ecx+0xC]
    push esi
    mov esi, [edx+LEN]
    mov eax, [HSCROLL]
    add eax, [COL]                      ; the column
    lea ecx, [eax+1]
    cmp ecx, esi
    jge .max
    mov ecx, esi                        ; max(len, column + 1)
.max:
    cmp eax, esi
    jge .noinsert
    add ecx, [INSERT]                   ; inserted within the text
.noinsert:
    pop esi
    cmp ecx, LINE_MAX
    jle .orig
    jmp KEY_END
.orig:
    jmp 0x401E5E

; case 0x19: the line deleted (the old current line) ...
key_y1:
    mov [deleted], eax
    push eax
    mov ecx, [ebp-8]
    call FN_DELETE
    jmp 0x401E17

; ... may have been the first line on the screen: then the new current line is
key_y2:
    mov ecx, [ebp-8]
    mov eax, [ecx+0x10]
    cmp eax, [deleted]
    jne .done
    mov eax, [ecx+0xC]
    mov [ecx+0x10], eax
.done:
    jmp 0x401E4A

; ---------------------------------------------------------------------------
; Del (FUN_00402431, this at [ebp-4]) at or after a line's end: the next line joins
del_join:
    mov ecx, [ebp-4]
    mov edx, [ecx+0xC]
    mov edx, [edx+NEXT]
    mov eax, [HSCROLL]
    add eax, [COL]
    add eax, [edx+LEN]
    cmp eax, LINE_MAX
    jg 0x40250E
    jmp 0x402493

; ---------------------------------------------------------------------------
; Ctrl+Right (FUN_004025cd, this at [ebp-8]): on the next line it skips delimiters -
; only within the text (a NUL after it counts as one)
word_right:
    mov eax, [HSCROLL]
    add eax, [COL]
    mov ecx, [ebp-8]
    mov ecx, [ecx+0xC]
    cmp eax, [ecx+LEN]
    jge 0x402701
    mov eax, [HSCROLL]
    jmp 0x4026CE

; Ctrl+Left (FUN_0040270b, this at [ebp-8]) at the start of a line goes to the end of
; the line above and tries again - endlessly at the start of the text
word_left:
    mov ecx, [ebp-8]
    mov eax, [ecx+0xC]
    cmp eax, [ecx+0x14]
    je 0x40280E
    jmp 0x4027E7

; ---------------------------------------------------------------------------
; copy (FUN_00402905, this at [ebp-0xc], the buffer at [ebp-4], the line at [ebp-8])

; (lines + 1) * 258 bytes instead of lines * 256: two lines of text and their CR LF
; did not fit
copy_buffer:
    call sel_size
    push eax
    call FN_NEW
    add esp, 4
    mov [ebp-4], eax
    jmp 0x402951

; walking from the first line of the selection to its last one: stop at the end
copy_null:
    mov eax, [ebp-8]
    test eax, eax
    jz 0x402B75
    cmp [P1], eax
    je 0x402A7F
    jmp 0x4029FF

; the last line: up to the end column, but not past the line's end
copy_clamp:
    mov ecx, [C1]
    mov edx, [ebp-8]
    cmp ecx, [edx+LEN]
    jle .ok
    mov ecx, [edx+LEN]
.ok:
    jmp 0x402A9B

; eax = (|L1 - L0| + 1) * 258 + 16
sel_size:
    mov eax, [L1]
    sub eax, [L0]
    cdq
    xor eax, edx
    sub eax, edx
    inc eax
    imul eax, eax, 258
    add eax, 16
    ret

; ---------------------------------------------------------------------------
; the window procedure (FUN_00403910: hwnd at [ebp+8], lParam at [ebp+0x14])

RETURN_0    equ 0x4047C0
COMMAND_END equ 0x405635        ; (WM_COMMAND: return 0)

; WM_CHAR 1: the selection ends on the last line, not one past it
select_all:
    mov eax, [NLINES]
    dec eax
    mov [L1], eax
    jmp 0x403CA4

; Ctrl+Ins: the clipboard block
global_alloc:
    call sel_size
    push eax
    push 0x2042
    call [IMP_GLOBALALLOC]
    mov [0x40EB28], eax
    jmp 0x404267

; Shift+Ins, the clipboard holds no text: the original returns with it open
close_clip:
    call [IMP_CLOSECLIPBOARD]
    jmp RETURN_0

; Shift+Del, Ctrl+Del: the selection in order (Ctrl+Del did not sort it), still where
; its line numbers say (else forgotten), its columns within its lines
del_selection:
    mov eax, [L1]
    cmp eax, [L0]
    jl .swap
    jne .sorted
    mov eax, [C1]
    cmp eax, [C0]
    jge .sorted
.swap:
    mov ecx, EDITOR
    call FN_SWAP
.sorted:
    cmp dword [P0], 0
    je .invalid
    cmp dword [P1], 0
    je .invalid
    push esi
    push edi
    or esi, -1                          ; the line number of P0
    or edi, -1                          ; of P1
    mov eax, [EDITOR+0x14]
    xor ecx, ecx
.walk:
    test eax, eax
    jz .walked
    cmp eax, [P0]
    jne .notp0
    cmp esi, -1
    jne .notp0
    mov esi, ecx
.notp0:
    cmp eax, [P1]
    jne .notp1
    cmp edi, -1
    jne .notp1
    mov edi, ecx
.notp1:
    mov eax, [eax+NEXT]
    inc ecx
    jmp .walk
.walked:
    cmp esi, [L0]
    jne .invalid2
    cmp edi, [L1]
    jne .invalid2
    pop edi
    pop esi
    mov eax, [P0]
    mov eax, [eax+LEN]
    cmp [C0], eax
    jle .c0
    mov [C0], eax
.c0:
    mov eax, [P1]
    mov eax, [eax+LEN]
    cmp [C1], eax
    jle .c1
    mov [C1], eax
.c1:
    jmp 0x4043EA
.invalid2:
    pop edi
    pop esi
.invalid:
    jmp 0x4045A9                        ; (forgets the selection)

; WM_MOUSEMOVE: the column to drag to, as far as the cursor can go (x 280..286 of the
; default window is column 35, one more than it can reach: the original loops forever)
drag_column:
    mov eax, [ebp+0x14]
    and eax, 0xFFFF
    cdq
    idiv dword [CW]
    mov ecx, [MAXCOL]
    cmp eax, ecx
    jle .a
    mov eax, ecx
.a:
    mov ecx, 0x100
    sub ecx, [HSCROLL]
    cmp eax, ecx
    jle .b
    mov eax, ecx
.b:
    test eax, eax
    jge .c
    xor eax, eax
.c:
    mov [target], eax
    cmp eax, [COL]
    jle .left
.right:
    mov eax, [target]
    cmp eax, [COL]
    je .done
    mov ecx, EDITOR
    call FN_RIGHT
    jmp .right
.left:
    mov eax, [target]
    cmp eax, [COL]
    je .done
    mov ecx, EDITOR
    call FN_LEFT
    jmp .left
.done:
    jmp 0x4048EE

; "File is not saved. Save it?" - Yes, and the text has no name yet: ask for one
; (Cancel in the dialog cancels the command, as Cancel in the question would)
ask_open:
    call ask_name
    jz COMMAND_END
    jmp 0x405026

ask_compile:
    call ask_name
    jz COMMAND_END
    jmp 0x4052CC

ask_run:
    call ask_name
    jz COMMAND_END
    jmp 0x405443

ask_exit:
    call ask_name
    jz COMMAND_END
    jmp 0x40558F

; File > Save as for the window [ebp+8] of the caller; ZF set: cancelled
ask_name:
    push dword [ebp+8]
    call save_as
    add esp, 4
    test eax, eax
    ret

; cdecl save_as(hwnd): what File > Save as does; 0 if the dialog was cancelled
save_as:
    push ebp
    mov ebp, esp
    push dword [ebp+8]
    call FN_SAVEDLG
    add esp, 4
    cmp byte [eax], 0
    je .cancel
    push eax
    push FILENAME
    call FN_STRCPY
    add esp, 8
    push FILENAME
    mov ecx, EDITOR
    call FN_SAVE
    test eax, eax
    jnz .saved
    push STR_SAVEERR
    push 0x66
    call FN_ERRFMT
    add esp, 8
    push 0x10
    push STR_ERROR
    push ERRBUF
    push dword [ebp+8]
    call [IMP_MESSAGEBOX]
    jmp .title
.saved:
    mov dword [MODIFIED], 0
.title:
    push FILENAME
    push STR_TITLE
    push titlebuf
    call FN_SPRINTF
    add esp, 12
    push titlebuf
    push dword [ebp+8]
    call [IMP_SETWINDOWTEXT]
    mov eax, 1
    pop ebp
    ret
.cancel:
    xor eax, eax
    pop ebp
    ret

; ---------------------------------------------------------------------------
align 16
deleted:    dd 0
target:     dd 0
align 16
tmpbuf:     times 256 db 0
titlebuf:   times 320 db 0
