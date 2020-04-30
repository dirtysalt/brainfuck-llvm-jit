#!/usr/bin/env python
# coding:utf-8
# Copyright (C) dirlt
import sys
from ctypes import CFUNCTYPE, POINTER, c_int8

import llvmlite.binding as llvm
import simple_bf
from llvmlite import ir

int8 = ir.IntType(8)
int32 = ir.IntType(32)
int1 = ir.IntType(1)
void = ir.VoidType()
int8_ptr = int8.as_pointer()

# All these initializations are required for code generation!
llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()  # yes, even this one

def optimize_source(s):
    s = [c for c in s if c in '><+-.,[]']

    # fold to (op, count)
    ops = []
    prev = None
    count = 0
    for c in s:
        if c in '[]' or c != prev:
            if prev:
                ops.append((prev, count))
            prev = c
            count = 1
        else:
            count += 1
    if prev:
        ops.append((prev, count))

    # optimize [-] to zero current cell
    i = 0
    while i < len(ops) - 2:
        a, ac = ops[i]
        b, bc = ops[i + 1]
        c, cc = ops[i + 2]
        if a == '[' and b == '-' and bc == 1 and c == ']':
            ops[i] = ('0', 1)
            ops[i + 1] = None
            ops[i + 2] = None
            i += 2
        i += 1

    # remove all None
    ops = [x for x in ops if x is not None]
    return ops


def create_execution_engine():
    """
    Create an ExecutionEngine suitable for JIT code generation on
    the host CPU.  The engine is reusable for an arbitrary number of
    modules.
    """
    # Create a target machine representing the host
    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    # And an execution engine with an empty backing module
    backing_mod = llvm.parse_assembly("")
    engine = llvm.create_mcjit_compiler(backing_mod, target_machine)
    return target_machine, engine


def compile_ir(engine, llvm_ir):
    """
    Compile the LLVM IR string with the given engine.
    The compiled module object is returned.
    """
    # Create a LLVM module object from the IR
    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()

    # Now add the module and make sure it is ready for execution
    engine.add_module(mod)
    engine.finalize_object()
    engine.run_static_constructors()
    return mod


def to_llvm(ops, func, ptr, write_func, read_func):
    jumps = {}
    labels = []

    for i in range(len(ops)):
        if ops[i][0] == '[':
            labels.append(i)
        elif ops[i][0] == ']':
            j = labels.pop()
            jumps[j] = i

    block_no = 0

    def new_block():
        nonlocal block_no
        b = func.append_basic_block(name='blk%d' % block_no)
        block_no += 1
        return b

    def parse_op(xbd, c, rep):
        if c == '>' or c == '<':
            # ptr += rep
            if c == '<':
                rep = -rep

            p = xbd.load(ptr)
            t = xbd.gep(p, [int32(rep)])
            xbd.store(t, ptr)

        elif c == '+' or c == '-':
            # *ptr += rep
            if c == '-':
                rep = -rep

            p = xbd.load(ptr)
            x = xbd.load(p)
            x = xbd.add(x, int8(rep))
            xbd.store(x, p)

        elif c == '0':

            p = xbd.load(ptr)
            xbd.store(int8(0), p)

        elif c == '.':

            p = xbd.load(ptr)
            x = xbd.load(p)
            xbd.call(write_func, (x, int32(rep)))

        elif c == ',':

            p = xbd.load(ptr)
            x = xbd.call(read_func, (int32(rep),))
            xbd.store(x, p)

    def parse_loop(parent, begin, end):
        assert ops[begin][0] == '[' and ops[end][0] == ']'

        inb = new_block()
        outb = new_block()
        xb = new_block()

        parent.branch(inb)
        inbd = ir.IRBuilder(inb)

        p = inbd.load(ptr)
        t = inbd.load(p)
        pred = inbd.icmp_signed('==', t, int8(0))
        inbd.cbranch(pred, outb, xb)

        xbd = ir.IRBuilder(xb)

        k = begin + 1
        while k < end:
            c, rep = ops[k]
            if c == '[':
                kk = jumps[k]
                xbd = parse_loop(xbd, k, kk)
                k = kk
            else:
                parse_op(xbd, c, rep)
            k += 1

        xbd.branch(inb)
        return ir.IRBuilder(outb)

    mem = func.args[0]
    b = func.append_basic_block(name='entry')
    bd = ir.IRBuilder(b)
    bd.store(mem, ptr)
    i = 0
    while i < len(ops):
        c, rep = ops[i]
        if c == '[':
            j = jumps[i]
            bd = parse_loop(bd, i, j)
            i = j
        else:
            parse_op(bd, c, rep)
        i += 1

    bd.ret(int8(0))


def run_llvm(ops):
    llvm.load_library_permanently("./libio.so")

    mem_size = 10 ** 6
    import numpy as np
    arr = np.zeros(mem_size, dtype=np.int8)
    mem = arr.ctypes.data_as(POINTER(c_int8))

    fnty = ir.FunctionType(int8, (int8.as_pointer(),))
    module = ir.Module(name="module_name")
    func = ir.Function(module, fnty, name="foo")

    write_fnty = ir.FunctionType(void, (int8, int32))
    write_func = ir.Function(module, write_fnty, name="sys_write")
    read_fnty = ir.FunctionType(int8, (int32,))
    read_func = ir.Function(module, read_fnty, name="sys_read")
    ptr = ir.GlobalVariable(module, int8_ptr, "ptr")
    ptr.linkage = 'internal'
    to_llvm(ops, func, ptr, write_func, read_func)

    target_machine, engine = create_execution_engine()
    print(module)

    mod = compile_ir(engine, str(module))
    print(target_machine.emit_assembly(mod))

    func_ptr = engine.get_function_address("foo")
    cfunc = CFUNCTYPE(c_int8, POINTER(c_int8))(func_ptr)
    cfunc(mem)


def main():
    file_path = sys.argv[1] if len(sys.argv) >= 2 else 'test.bf'
    with open(file_path) as fh:
        data = fh.read()

    ops = simple_bf.optimize_source(data)
    run_llvm(ops)


if __name__ == '__main__':
    main()
