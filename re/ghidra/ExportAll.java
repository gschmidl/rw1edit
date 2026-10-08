// Post-script for analyzeHeadless: writes the decompiled C of every function
// (<out>/decomp.c) and a disassembly listing of every function (<out>/listing.asm).
//   analyzeHeadless <proj dir> <proj> -import <exe> -scriptPath <this dir>
//     -postScript ExportAll.java <out dir>
import java.io.*;
import java.nio.charset.StandardCharsets;

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;

public class ExportAll extends GhidraScript {
	@Override
	public void run() throws Exception {
		File outdir = new File(getScriptArgs()[0]);
		outdir.mkdirs();
		DecompInterface ifc = new DecompInterface();
		ifc.setOptions(new DecompileOptions());
		ifc.toggleCCode(true);
		ifc.toggleSyntaxTree(false);
		ifc.setSimplificationStyle("decompile");
		if (!ifc.openProgram(currentProgram)) {
			println("decompiler: " + ifc.getLastMessage());
			return;
		}
		Listing listing = currentProgram.getListing();
		StringBuilder c = new StringBuilder(), asm = new StringBuilder();
		int done = 0, failed = 0;
		for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
			if (f.isExternal() || f.isThunk()) {
				continue;
			}
			c.append(String.format("%n// ---- %s  %08X%n", f.getName(true), f.getEntryPoint().getOffset()));
			DecompileResults res = ifc.decompileFunction(f, 120, monitor);
			if (res != null && res.decompileCompleted() && res.getDecompiledFunction() != null) {
				c.append(res.getDecompiledFunction().getC());
				done++;
			}
			else {
				c.append("// decompile failed\n");
				failed++;
			}
			asm.append(String.format("%n; ---- %s  %08X%n", f.getName(true), f.getEntryPoint().getOffset()));
			for (Instruction in : listing.getInstructions(f.getBody(), true)) {
				asm.append(String.format("%08X  %s%n", in.getAddress().getOffset(), in.toString()));
			}
		}
		try (Writer w = new OutputStreamWriter(new FileOutputStream(new File(outdir, "decomp.c")),
				StandardCharsets.UTF_8)) {
			w.write(c.toString());
		}
		try (Writer w = new OutputStreamWriter(new FileOutputStream(new File(outdir, "listing.asm")),
				StandardCharsets.UTF_8)) {
			w.write(asm.toString());
		}
		ifc.dispose();
		println(String.format("ExportAll: %d decompiled, %d failed", done, failed));
	}
}
