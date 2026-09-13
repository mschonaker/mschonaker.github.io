package com.example;

import java.util.HashMap;
import java.util.Map;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/**
 * Compiles a parsed {@link AST.Program} into a runnable JVM class using ASM.
 *
 * <p>The generated class exposes {@code public static int run()}: script variables become local
 * variable slots in that method, and the value of the program's tail expression becomes the
 * method's return value. It also exposes a {@code public static void main(String[])} that calls
 * {@code run()} and prints the result, so the generated class can be run directly with {@code java
 * <ClassName>}, without any extra tooling.
 */
public class TinyCompiler implements Opcodes {

  /** Maps script variable names to JVM local variable slots. */
  private final Map<String, Integer> symbolTable = new HashMap<>();

  /** Next free local variable slot. Slot 0 is left unused. */
  private int nextLocalSlot = 1;

  /**
   * Compiles the given program into a class named {@code className}.
   *
   * @param program the parsed script: statements plus a tail expression
   * @param className the binary name of the class to generate
   * @return the generated class's bytecode
   */
  public byte[] compile(AST.Program program, String className) {
    var cw = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
    cw.visit(V1_8, ACC_PUBLIC | ACC_SUPER, className, null, "java/lang/Object", null);

    var init = cw.visitMethod(ACC_PUBLIC, "<init>", "()V", null, null);
    init.visitCode();
    init.visitVarInsn(ALOAD, 0);
    init.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
    init.visitInsn(RETURN);
    init.visitMaxs(0, 0);
    init.visitEnd();

    var mv = cw.visitMethod(ACC_PUBLIC | ACC_STATIC, "run", "()I", null, null);
    mv.visitCode();

    for (var stmt : program.stmts()) {
      compileStmt(stmt, mv);
    }
    compileExpr(program.tail(), mv);
    mv.visitInsn(IRETURN);

    mv.visitMaxs(0, 0);
    mv.visitEnd();

    compileMain(cw, className);

    cw.visitEnd();

    return cw.toByteArray();
  }

  /**
   * Emits {@code public static void main(String[])}, equivalent to {@code
   * System.out.println(run());}, so the compiled class is directly runnable with {@code java
   * <ClassName>}.
   *
   * @param cw the class being built
   * @param className the binary name of the class being generated
   */
  private void compileMain(ClassWriter cw, String className) {
    var main =
        cw.visitMethod(ACC_PUBLIC | ACC_STATIC, "main", "([Ljava/lang/String;)V", null, null);
    main.visitCode();
    main.visitFieldInsn(GETSTATIC, "java/lang/System", "out", "Ljava/io/PrintStream;");
    main.visitMethodInsn(INVOKESTATIC, className, "run", "()I", false);
    main.visitMethodInsn(INVOKEVIRTUAL, "java/io/PrintStream", "println", "(I)V", false);
    main.visitInsn(RETURN);
    main.visitMaxs(0, 0);
    main.visitEnd();
  }

  /**
   * Emits bytecode for a single statement node.
   *
   * @param node the statement to compile
   * @param mv the method being built
   */
  private void compileStmt(AST.Node node, MethodVisitor mv) {
    if (node instanceof AST.Block block) {
      for (var s : block.stmts()) {
        compileStmt(s, mv);
      }
    } else if (node instanceof AST.Assign assign) {
      compileExpr(assign.expr(), mv);
      var slot = symbolTable.computeIfAbsent(assign.var(), k -> nextLocalSlot++);
      mv.visitVarInsn(ISTORE, slot);
    } else if (node instanceof AST.If ifStmt) {
      var labelEnd = new Label();
      compileExpr(ifStmt.cond(), mv);
      // Jump over the branch when the condition is false (0).
      mv.visitJumpInsn(IFEQ, labelEnd);
      compileStmt(ifStmt.thenBranch(), mv);
      mv.visitLabel(labelEnd);
    } else if (node instanceof AST.While whileStmt) {
      var labelLoop = new Label();
      var labelEnd = new Label();

      mv.visitLabel(labelLoop);
      compileExpr(whileStmt.cond(), mv);
      mv.visitJumpInsn(IFEQ, labelEnd);

      compileStmt(whileStmt.body(), mv);
      mv.visitJumpInsn(GOTO, labelLoop);
      mv.visitLabel(labelEnd);
    } else {
      throw new RuntimeException("Unsupported statement: " + node);
    }
  }

  /**
   * Emits bytecode that leaves the value of an expression on top of the operand stack.
   *
   * @param expr the expression to compile
   * @param mv the method being built
   */
  private void compileExpr(AST.Expr expr, MethodVisitor mv) {
    if (expr instanceof AST.Num num) {
      mv.visitLdcInsn(num.value());
    } else if (expr instanceof AST.Var v) {
      var slot = symbolTable.get(v.name());
      if (slot == null) {
        throw new RuntimeException("Undefined variable: " + v.name());
      }
      mv.visitVarInsn(ILOAD, slot);
    } else if (expr instanceof AST.BinOp bin) {
      compileExpr(bin.left(), mv);
      compileExpr(bin.right(), mv);
      switch (bin.op()) {
        case '+' -> mv.visitInsn(IADD);
        case '-' -> mv.visitInsn(ISUB);
        case '<' -> compileComparison(mv, IF_ICMPLT);
        case '>' -> compileComparison(mv, IF_ICMPGT);
        default -> throw new RuntimeException("Unsupported operator: " + bin.op());
      }
    } else {
      throw new RuntimeException("Unsupported expression: " + expr);
    }
  }

  /**
   * Emits a comparison that replaces the two ints on top of the operand stack with {@code 1} if the
   * comparison holds, or {@code 0} otherwise.
   *
   * @param mv the method being built
   * @param comparisonOpcode the ASM jump opcode to use, e.g. {@link Opcodes#IF_ICMPLT}
   */
  private void compileComparison(MethodVisitor mv, int comparisonOpcode) {
    var labelTrue = new Label();
    var labelEnd = new Label();
    mv.visitJumpInsn(comparisonOpcode, labelTrue);
    mv.visitLdcInsn(0);
    mv.visitJumpInsn(GOTO, labelEnd);
    mv.visitLabel(labelTrue);
    mv.visitLdcInsn(1);
    mv.visitLabel(labelEnd);
  }
}
