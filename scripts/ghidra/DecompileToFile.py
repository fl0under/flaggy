# Decompile every function in the current program to one C-like text file.
# Headless usage:
#   analyzeHeadless <proj_dir> <proj> -import <binary> \
#     -scriptPath scripts/ghidra -postScript DecompileToFile.py <out_file>
#
# This is a Ghidra (Jython) post-script, not a standalone Python program.
# @category flaggy
import os

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor


def run():
    args = getScriptArgs()  # noqa: F821 (Ghidra injects this)
    out_path = args[0] if args else os.path.join(
        os.getcwd(), currentProgram.getName() + ".c"  # noqa: F821
    )

    monitor = ConsoleTaskMonitor()
    decomp = DecompInterface()
    decomp.openProgram(currentProgram)  # noqa: F821

    fm = currentProgram.getFunctionManager()  # noqa: F821
    funcs = list(fm.getFunctions(True))

    ok = 0
    with open(out_path, "w") as out:
        out.write("// Decompilation of %s (%d functions)\n\n"
                  % (currentProgram.getName(), len(funcs)))  # noqa: F821
        for f in funcs:
            res = decomp.decompileFunction(f, 60, monitor)
            if res is not None and res.decompileCompleted():
                out.write(res.getDecompiledFunction().getC())
                out.write("\n")
                ok += 1
            else:
                out.write("// failed to decompile %s @ %s\n\n"
                          % (f.getName(), f.getEntryPoint()))

    print("[ghidra] decompiled %d/%d functions -> %s" % (ok, len(funcs), out_path))


run()
