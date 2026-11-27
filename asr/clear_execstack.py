#!/usr/bin/env python3
"""Clear the executable-stack flag of ELF shared libraries.

Kaldi's prebuilt OpenBLAS (armv6l, armv7l) is marked as needing an
executable stack. glibc 2.41 (Trixie) no longer allows dlopen() to make the
stack executable ("cannot enable executable stack as shared object requires:
Invalid argument"), so loading py-kaldi-asr fails. OpenBLAS does not need it:
the flag comes from assembly files without a .note.GNU-stack section.

Same as `patchelf --clear-execstack` / `execstack -c`, without the package.
Usage: clear_execstack.py FILE...  (non-ELF files and symlinks are skipped)
"""

import os
import struct
import sys

PT_GNU_STACK = 0x6474E551
PF_X = 1


def clear_execstack(path: str) -> bool:
    with open(path, "r+b") as f:
        header = f.read(64)
        if header[:4] != b"\x7fELF":
            return False
        endian = "<" if header[5] == 1 else ">"
        if header[4] == 2:  # ELFCLASS64
            (phoff,) = struct.unpack_from(endian + "Q", header, 0x20)
            phentsize, phnum = struct.unpack_from(endian + "HH", header, 0x36)
            flags_offset = 4
        else:  # ELFCLASS32
            (phoff,) = struct.unpack_from(endian + "I", header, 0x1C)
            phentsize, phnum = struct.unpack_from(endian + "HH", header, 0x2A)
            flags_offset = 24
        for i in range(phnum):
            f.seek(phoff + i * phentsize)
            entry = f.read(phentsize)
            (p_type,) = struct.unpack_from(endian + "I", entry, 0)
            if p_type != PT_GNU_STACK:
                continue
            (p_flags,) = struct.unpack_from(endian + "I", entry, flags_offset)
            if p_flags & PF_X:
                f.seek(phoff + i * phentsize + flags_offset)
                f.write(struct.pack(endian + "I", p_flags & ~PF_X))
                return True
    return False


if __name__ == "__main__":
    for path in sys.argv[1:]:
        if not os.path.islink(path) and os.path.isfile(path):
            if clear_execstack(path):
                print(f"Cleared executable stack flag: {path}")
