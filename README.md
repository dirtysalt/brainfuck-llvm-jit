# brainfuck-llvm-jit
a brainfuck jit in llvm(python llvmlite)

Get a lof of ideas from https://github.com/cslarsen/brainfuck-jit, many thanks!

1. run `make` to build libio.so, which has I/O functions
2. run `pip install llvmlite` to install `llvmlite`
3. run `llvm_bf.py <file>`

TODO:
1. can we get rid of `global_variable`?
2. how to make it faster?
