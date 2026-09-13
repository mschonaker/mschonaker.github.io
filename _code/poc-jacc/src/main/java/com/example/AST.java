package com.example;

import java.util.List;

/**
 * Parsed representation of the tiny scripting language used by this project.
 *
 * <p>{@link Node} is the root of a sealed hierarchy of {@link Expr} (expression) and {@link Stmt}
 * (statement) records, produced by {@link TinyParser} and consumed by {@link TinyCompiler}.
 */
public final class AST {
  private AST() {}

  /** Any parsed expression or statement node. */
  public sealed interface Node permits Expr, Stmt {}

  /** A node that produces a value: a literal, a variable, or an operator. */
  public sealed interface Expr extends Node permits Num, Var, BinOp {}

  /** A node that performs an action: an assignment, a branch, or a loop. */
  public sealed interface Stmt extends Node permits Assign, If, While, Block {}

  /**
   * An integer literal.
   *
   * @param value the literal's value
   */
  public record Num(int value) implements Expr {}

  /**
   * A reference to a script variable.
   *
   * @param name the variable's name
   */
  public record Var(String name) implements Expr {}

  /**
   * A binary operator expression.
   *
   * @param op the operator character: {@code +}, {@code -}, {@code <}, or {@code >}
   * @param left the left operand
   * @param right the right operand
   */
  public record BinOp(char op, Expr left, Expr right) implements Expr {}

  /**
   * An assignment statement, {@code var = expr;}.
   *
   * @param var the target variable's name
   * @param expr the value to assign
   */
  public record Assign(String var, Expr expr) implements Stmt {}

  /**
   * A conditional statement, {@code if (cond) thenBranch}.
   *
   * @param cond the branch condition
   * @param thenBranch the statement to run when {@code cond} is non-zero
   */
  public record If(Expr cond, Stmt thenBranch) implements Stmt {}

  /**
   * A loop statement, {@code while (cond) body}.
   *
   * @param cond the loop condition
   * @param body the statement to repeat while {@code cond} is non-zero
   */
  public record While(Expr cond, Stmt body) implements Stmt {}

  /**
   * A sequence of statements executed in order.
   *
   * @param stmts the statements to execute
   */
  public record Block(List<Stmt> stmts) implements Stmt {}

  /**
   * A full parsed script: statements executed in order, followed by a mandatory tail expression
   * whose value is the script's result. There is no explicit {@code return}; like a Rust block, the
   * last expression (written with no trailing {@code ;}) is the value.
   *
   * @param stmts the statements to execute before the tail expression
   * @param tail the expression whose value is the script's result
   */
  public record Program(List<Stmt> stmts, Expr tail) {}
}
