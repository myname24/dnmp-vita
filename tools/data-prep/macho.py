#!/usr/bin/env python3
"""Mach-O (32-bit ARM, iOS) reader for the iOS loader feasibility work.

Usage: macho.py <path to DukeNukemMP binary> [--slice armv7|armv7s] [--report out.txt]

Parses one slice of a fat binary: segments and sections, dyld info (rebase / bind / lazy bind / weak bind opcode streams),
symbol table, entry point, linked libraries, and the Objective-C class list (class and instance methods with their IMP
addresses). Everything is reported in unslid vm addresses (the __TEXT segment's preferred address).
"""
import argparse
import struct
import sys

CPU_ARM = 12
SUBTYPES = {"armv7": 9, "armv7s": 11}

LC_SEGMENT, LC_SYMTAB, LC_UNIXTHREAD, LC_DYSYMTAB, LC_LOAD_DYLIB = 0x1, 0x2, 0x5, 0xB, 0xC
LC_DYLD_INFO, LC_DYLD_INFO_ONLY, LC_MAIN, LC_FUNCTION_STARTS, LC_ENCRYPTION_INFO = 0x22, 0x80000022, 0x80000028, 0x26, 0x21


def uleb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return r, i


def sleb(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            if c & 0x40:
                r -= 1 << s
            return r, i


class MachO:
    def __init__(self, path, slice_name="armv7"):
        data = open(path, "rb").read()
        magic = struct.unpack(">I", data[:4])[0]
        if magic == 0xCAFEBABE:
            n = struct.unpack(">I", data[4:8])[0]
            for k in range(n):
                ct, st, off, size, al = struct.unpack(">5I", data[8 + 20 * k:28 + 20 * k])
                if ct == CPU_ARM and st == SUBTYPES[slice_name]:
                    self.d = data[off:off + size]
                    break
            else:
                raise SystemExit(f"no {slice_name} slice")
        else:
            self.d = data
        d = self.d
        magic, ct, st, ftype, ncmds, sizeofcmds, flags = struct.unpack("<7I", d[:28])
        assert magic == 0xFEEDFACE, "not a 32-bit Mach-O"
        self.flags = flags
        self.segments = []          # dicts: name vmaddr vmsize fileoff filesize maxprot initprot sections
        self.dylibs = []
        self.entry = None
        self.dyld = None
        self.symtab = None
        self.dysymtab = None
        self.func_starts = None
        self.crypt = None
        p = 28
        for _ in range(ncmds):
            cmd, cs = struct.unpack("<II", d[p:p + 8])
            if cmd == LC_SEGMENT:
                name = d[p + 8:p + 24].rstrip(b"\0").decode()
                vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, sflags = struct.unpack("<8I", d[p + 24:p + 56])
                secs = []
                q = p + 56
                for _ in range(nsects):
                    sn = d[q:q + 16].rstrip(b"\0").decode()
                    addr, size, offset, align, reloff, nreloc, sfl, r1, r2 = struct.unpack("<9I", d[q + 32:q + 68])
                    secs.append(dict(name=sn, addr=addr, size=size, offset=offset, flags=sfl, reserved1=r1, reserved2=r2))
                    q += 68
                self.segments.append(dict(name=name, vmaddr=vmaddr, vmsize=vmsize, fileoff=fileoff, filesize=filesize,
                                          maxprot=maxprot, initprot=initprot, sections=secs))
            elif cmd in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
                self.dyld = struct.unpack("<10I", d[p + 8:p + 48])
            elif cmd == LC_SYMTAB:
                self.symtab = struct.unpack("<4I", d[p + 8:p + 24])
            elif cmd == LC_DYSYMTAB:
                self.dysymtab = struct.unpack("<18I", d[p + 8:p + 80])
            elif cmd == LC_LOAD_DYLIB or cmd == 0x18 or cmd == 0x8000001F:      # LOAD_DYLIB, LOAD_WEAK_DYLIB, REEXPORT
                stroff = struct.unpack("<I", d[p + 8:p + 12])[0]
                self.dylibs.append(d[p + stroff:p + cs].split(b"\0")[0].decode())
            elif cmd == LC_MAIN:
                self.entry = ("main", struct.unpack("<Q", d[p + 8:p + 16])[0])
            elif cmd == LC_UNIXTHREAD:
                regs = struct.unpack("<17I", d[p + 16:p + 16 + 68])
                self.entry = ("unixthread", regs[15])                        # pc
            elif cmd == LC_FUNCTION_STARTS:
                self.func_starts = struct.unpack("<II", d[p + 8:p + 16])
            elif cmd == LC_ENCRYPTION_INFO:
                self.crypt = struct.unpack("<III", d[p + 8:p + 20])
            p += cs
        self.base = next(s["vmaddr"] for s in self.segments if s["name"] == "__TEXT")
        self._syms()

    # -- address helpers --------------------------------------------------------------------------
    def seg_of(self, vm):
        for s in self.segments:
            if s["vmaddr"] <= vm < s["vmaddr"] + s["vmsize"]:
                return s
        return None

    def read(self, vm, n):
        s = self.seg_of(vm)
        if s is None:
            raise ValueError(hex(vm))
        o = vm - s["vmaddr"]
        if o >= s["filesize"]:
            return b"\0" * n                     # zero-fill part (__bss / __common)
        return self.d[s["fileoff"] + o:s["fileoff"] + o + n]

    def u32(self, vm):
        return struct.unpack("<I", self.read(vm, 4))[0]

    def cstr(self, vm):
        s = self.seg_of(vm)
        o = s["fileoff"] + vm - s["vmaddr"]
        return self.d[o:self.d.index(b"\0", o)].decode(errors="replace")

    def section(self, segname, sectname):
        for s in self.segments:
            if s["name"] == segname:
                for c in s["sections"]:
                    if c["name"] == sectname:
                        return c
        return None

    # -- symbols ----------------------------------------------------------------------------------
    def _syms(self):
        self.symbols = []
        if not self.symtab:
            return
        symoff, nsyms, stroff, strsize = self.symtab
        d = self.d
        for i in range(nsyms):
            nx, nt, ns, nd, nv = struct.unpack("<IBBhI", d[symoff + 12 * i:symoff + 12 * i + 12])
            name = d[stroff + nx:d.index(b"\0", stroff + nx)].decode(errors="replace")
            self.symbols.append((name, nt, ns, nd, nv))

    def defined_symbols(self):
        """[(vm address, name)] of the symbols this binary defines (N_SECT); Thumb functions keep bit 0 clear here."""
        return sorted((s[4], s[0]) for s in self.symbols if (s[1] & 0x0E) == 0x0E)

    # -- dyld info --------------------------------------------------------------------------------
    def segaddr(self, segidx):
        return self.segments[segidx]["vmaddr"]

    def rebases(self):
        """[(vm address, type)] of every pointer that must be slid (type 1 = pointer, 2 = text abs32, 3 = text pcrel32)."""
        out = []
        if not self.dyld:
            return out
        off, size = self.dyld[0], self.dyld[1]
        b = self.d[off:off + size]
        i, typ, addr = 0, 1, 0
        while i < len(b):
            op, imm = b[i] & 0xF0, b[i] & 0x0F
            i += 1
            if op == 0x00:                                   # DONE
                break
            elif op == 0x10:                                 # SET_TYPE_IMM
                typ = imm
            elif op == 0x20:                                 # SET_SEGMENT_AND_OFFSET_ULEB
                o, i = uleb(b, i); addr = self.segaddr(imm) + o
            elif op == 0x30:                                 # ADD_ADDR_ULEB
                o, i = uleb(b, i); addr += o
            elif op == 0x40:                                 # ADD_ADDR_IMM_SCALED
                addr += imm * 4
            elif op == 0x50:                                 # DO_REBASE_IMM_TIMES
                for _ in range(imm):
                    out.append((addr, typ)); addr += 4
            elif op == 0x60:                                 # DO_REBASE_ULEB_TIMES
                n, i = uleb(b, i)
                for _ in range(n):
                    out.append((addr, typ)); addr += 4
            elif op == 0x70:                                 # DO_REBASE_ADD_ADDR_ULEB
                o, i = uleb(b, i); out.append((addr, typ)); addr += 4 + o
            elif op == 0x80:                                 # DO_REBASE_ULEB_TIMES_SKIPPING_ULEB
                n, i = uleb(b, i); sk, i = uleb(b, i)
                for _ in range(n):
                    out.append((addr, typ)); addr += 4 + sk
            else:
                raise ValueError(f"rebase opcode {op:#x}")
        return out

    def _binds(self, off, size, lazy=False):
        out = []
        b = self.d[off:off + size]
        i = 0
        lib, name, typ, addend, addr, flags = 0, "", 1, 0, 0, 0
        while i < len(b):
            op, imm = b[i] & 0xF0, b[i] & 0x0F
            i += 1
            if op == 0x00:                                   # DONE (lazy streams use it as a separator)
                if not lazy:
                    break
            elif op == 0x10:                                 # SET_DYLIB_ORDINAL_IMM
                lib = imm
            elif op == 0x20:                                 # SET_DYLIB_ORDINAL_ULEB
                lib, i = uleb(b, i)
            elif op == 0x30:                                 # SET_DYLIB_SPECIAL_IMM
                lib = -imm if imm else 0
            elif op == 0x40:                                 # SET_SYMBOL_TRAILING_FLAGS_IMM
                j = b.index(0, i); name = b[i:j].decode(); i = j + 1; flags = imm
            elif op == 0x50:                                 # SET_TYPE_IMM
                typ = imm
            elif op == 0x60:                                 # SET_ADDEND_SLEB
                addend, i = sleb(b, i)
            elif op == 0x70:                                 # SET_SEGMENT_AND_OFFSET_ULEB
                o, i = uleb(b, i); addr = self.segaddr(imm) + o
            elif op == 0x80:                                 # ADD_ADDR_ULEB
                o, i = uleb(b, i); addr = (addr + o) & 0xFFFFFFFF
            elif op == 0x90:                                 # DO_BIND
                out.append((addr, lib, name, addend, typ, flags)); addr += 4
            elif op == 0xA0:                                 # DO_BIND_ADD_ADDR_ULEB
                o, i = uleb(b, i); out.append((addr, lib, name, addend, typ, flags)); addr = (addr + 4 + o) & 0xFFFFFFFF
            elif op == 0xB0:                                 # DO_BIND_ADD_ADDR_IMM_SCALED
                out.append((addr, lib, name, addend, typ, flags)); addr += 4 + imm * 4
            elif op == 0xC0:                                 # DO_BIND_ULEB_TIMES_SKIPPING_ULEB
                n, i = uleb(b, i); sk, i = uleb(b, i)
                for _ in range(n):
                    out.append((addr, lib, name, addend, typ, flags)); addr += 4 + sk
            else:
                raise ValueError(f"bind opcode {op:#x}")
        return out

    def binds(self):
        """[(vm address, dylib ordinal, symbol, addend, type, flags, kind)] for non-lazy, lazy and weak binds."""
        if not self.dyld:
            return []
        ro, rs, bo, bs, wo, ws, lo, ls, eo, es = self.dyld
        out = [b + ("bind",) for b in self._binds(bo, bs)]
        out += [b + ("lazy",) for b in self._binds(lo, ls, lazy=True)]
        if ws:
            out += [b + ("weak",) for b in self._binds(wo, ws)]
        return out

    def exports(self):
        """{name: vm address} from the dyld export trie (what dlsym() on the executable can find); bit 0 set = Thumb."""
        out = {}
        if not self.dyld or not self.dyld[9]:
            return out
        b = self.d[self.dyld[8]:self.dyld[8] + self.dyld[9]]

        def walk(node, prefix):
            size, i = uleb(b, node)
            if size:
                flags, j = uleb(b, i)
                if not flags & 0x08:                         # not a re-export
                    addr, _ = uleb(b, j)
                    # trie addresses are OFFSETS from the mach header (= __TEXT start), always; the first version used them
                    # as vm addresses above 0x4000 and bound 90 weak C++ templates 0x4000 too low (Vita test 6: undefined
                    # instruction at 0x17230 when cas::cache<shared_texture>::cache() was called; nlist has 0x1b22c)
                    out[prefix] = self.base + addr
            i += size
            nchild = b[i]; i += 1
            for _ in range(nchild):
                e = b.index(0, i)
                edge = b[i:e].decode(errors="replace"); i = e + 1
                child, i = uleb(b, i)
                walk(child, prefix + edge)
        walk(0, "")
        return out

    # -- Objective-C ------------------------------------------------------------------------------
    def objc_classes(self):
        """[(class name, [(selector, imp, is_class_method)])] from __objc_classlist (class_t -> class_ro_t -> baseMethods)."""
        sec = self.section("__DATA", "__objc_classlist")
        out = []
        if not sec:
            return out
        for k in range(sec["size"] // 4):
            cls = self.u32(sec["addr"] + 4 * k)
            out.append(self._class(cls))
        return out

    def _methods(self, ml, is_meta):
        if not ml:
            return []
        entsize, count = struct.unpack("<II", self.read(ml, 8))
        entsize &= ~3
        res = []
        for j in range(count):
            name_p, types_p, imp = struct.unpack("<III", self.read(ml + 8 + j * entsize, 12))
            res.append((self.cstr(name_p), imp, is_meta))
        return res

    def _class(self, cls):
        isa, superclass, cache, vtable, data = struct.unpack("<5I", self.read(cls, 20))
        ro = data & ~3
        flags, istart, isize, ivarlayout, name_p, base_methods = struct.unpack("<6I", self.read(ro, 24))
        name = self.cstr(name_p)
        methods = self._methods(base_methods, False)
        if isa:                                              # metaclass: class methods
            m_isa, m_sup, m_cache, m_vt, m_data = struct.unpack("<5I", self.read(isa, 20))
            mro = m_data & ~3
            mflags, mi, ms, ml_, mname, mbase = struct.unpack("<6I", self.read(mro, 24))
            methods += self._methods(mbase, True)
        return name, methods


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary")
    ap.add_argument("--slice", default="armv7", choices=sorted(SUBTYPES))
    a = ap.parse_args()
    m = MachO(a.binary, a.slice)
    print(f"slice {a.slice}: flags {m.flags:#x} (PIE={bool(m.flags & 0x200000)}), entry {m.entry}, encryption {m.crypt}")
    print("segments:")
    for s in m.segments:
        print(f"  {s['name']:12s} vm {s['vmaddr']:#010x}+{s['vmsize']:#09x} file {s['fileoff']:#09x}+{s['filesize']:#09x} prot {s['initprot']}")
    reb = m.rebases()
    bnd = m.binds()
    print(f"rebases: {len(reb)} (types {sorted(set(t for _, t in reb))})")
    kinds = {}
    for b in bnd:
        kinds[b[6]] = kinds.get(b[6], 0) + 1
    print(f"binds: {len(bnd)} {kinds}; distinct symbols {len(set(b[2] for b in bnd))}")
    print("dylibs:", ", ".join(x.split("/")[-1] for x in m.dylibs))
    for name, meths in m.objc_classes():
        print(f"class {name}: {len(meths)} methods")
        for sel, imp, meta in meths:
            print(f"    {'+' if meta else '-'}[{name} {sel}]  imp {imp:#x}{' (thumb)' if imp & 1 else ''}")


if __name__ == "__main__":
    main()
