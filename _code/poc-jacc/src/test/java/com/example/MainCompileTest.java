package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;

/**
 * Exercises {@link Main#compile} the same way the command-line tool does: script bytes go in
 * through an {@link java.io.InputStream}, class bytecode comes out through an {@link
 * java.io.OutputStream}. Each test then loads the resulting bytecode with a throwaway {@link
 * ClassLoader} and invokes its {@code run()} method to check the script's behavior.
 *
 * <p>Invocation always goes through {@link #runCompiled}, which runs {@code run()} on a daemon
 * thread with a timeout. A compiled script can contain a genuine infinite loop (that's what {@link
 * #infiniteLoopIsGuardedByTimeout} checks for), and the JVM has no safe way to force-stop such a
 * thread, so the guard only bounds how long a single test can block; the runaway thread is
 * abandoned and dies with the test JVM.
 */
class MainCompileTest {

  private static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(2);

  /** Loads bytecode produced by {@link Main#compile} as a proper {@link Class}. */
  private static class MemoryClassLoader extends ClassLoader {
    Class<?> defineClass(String name, byte[] bytecode) {
      return defineClass(name, bytecode, 0, bytecode.length);
    }
  }

  @Test
  void sumsTenDownToOneViaWhileLoop() throws Exception {
    var bytecode =
        compileScript(
            """
                total = 0;
                i = 10;
                while (0 < i) {
                    total = total + i;
                    i = i - 1;
                }
                total
                """);

    assertEquals(55, runCompiled(bytecode));
  }

  /**
   * A {@code while} body is just a {@link AST.Stmt}, so it can be another {@code while} (or a block
   * containing one) with no special support needed. This computes {@code sum(i=1..3, sum(j=1..i,
   * j))} = 1 + (1+2) + (1+2+3) = 10.
   *
   * <p>The inner condition is written {@code j < (i + 1)}, not {@code j < i + 1}: as documented in
   * the README, {@code <} binds tighter than {@code +} in this grammar, so the unparenthesized form
   * would compile to {@code (j < i) + 1}, a value that's always 1 or 2 and therefore never zero —
   * an infinite loop. Writing this test is exactly how that quirk was first discovered.
   */
  @Test
  void nestedWhileLoopsComputeATriangularSum() throws Exception {
    var bytecode =
        compileScript(
            """
                total = 0;
                i = 1;
                while (i < 4) {
                    j = 1;
                    while (j < (i + 1)) {
                        total = total + j;
                        j = j + 1;
                    }
                    i = i + 1;
                }
                total
                """);

    assertEquals(10, runCompiled(bytecode));
  }

  @Test
  void evaluatesArithmeticExpression() throws Exception {
    var bytecode = compileScript("2 + 3 - 1");

    assertEquals(4, runCompiled(bytecode));
  }

  @Test
  void ifBranchRunsWhenConditionIsTrue() throws Exception {
    var bytecode =
        compileScript(
            """
                value = 0;
                if (1 < 2) {
                    value = 42;
                }
                value
                """);

    assertEquals(42, runCompiled(bytecode));
  }

  @Test
  void ifBranchIsSkippedWhenConditionIsFalse() throws Exception {
    var bytecode =
        compileScript(
            """
                value = 7;
                if (2 < 1) {
                    value = 99;
                }
                value
                """);

    assertEquals(7, runCompiled(bytecode));
  }

  /**
   * An {@code if} body is just a {@link AST.Stmt}, so the curly braces are optional: a single
   * statement works directly, with no block needed.
   */
  @Test
  void ifBranchWithoutBracesRunsWhenConditionIsTrue() throws Exception {
    var bytecode =
        compileScript(
            """
                value = 0;
                if (1 < 2)
                    value = 42;
                value
                """);

    assertEquals(42, runCompiled(bytecode));
  }

  @Test
  void ifBranchWithoutBracesIsSkippedWhenConditionIsFalse() throws Exception {
    var bytecode =
        compileScript(
            """
                value = 7;
                if (2 < 1)
                    value = 99;
                value
                """);

    assertEquals(7, runCompiled(bytecode));
  }

  /**
   * There is no array type in this language, so a bubble sort over an arbitrary-size collection
   * isn't expressible — sorting requires indexing into a variable-length store, and variables here
   * are only ever referenced by a fixed name. What *is* possible is a fixed-size version: name each
   * slot ({@code a}..{@code d}), hand-write the adjacent compare-and-swap chain once, and repeat it
   * with a counter-controlled {@code while} loop, which is exactly what real bubble sort does with
   * an indexed inner loop. Four passes is more than enough to fully sort four elements.
   *
   * <p>There's no boolean type or {@code &&} either, so "is the result sorted" is checked with
   * nested {@code if}s: {@code sorted} only becomes {@code 1} if all three adjacent comparisons
   * hold.
   */
  @Test
  void bubbleSortsFourVariablesWithoutArrays() throws Exception {
    var bytecode =
        compileScript(
            """
                a = 4;
                b = 2;
                c = 3;
                d = 1;
                pass = 0;
                while (pass < 4) {
                    if (b < a) {
                        t = a;
                        a = b;
                        b = t;
                    }
                    if (c < b) {
                        t = b;
                        b = c;
                        c = t;
                    }
                    if (d < c) {
                        t = c;
                        c = d;
                        d = t;
                    }
                    pass = pass + 1;
                }
                sorted = 0;
                if (a < b) {
                    if (b < c) {
                        if (c < d) {
                            sorted = 1;
                        }
                    }
                }
                sorted
                """);

    assertEquals(1, runCompiled(bytecode));
  }

  /**
   * There is no magic {@code result} variable: only the tail expression's value is returned, so an
   * ordinary variable named {@code result} that isn't the tail is just discarded like any other.
   */
  @Test
  void onlyTheTailExpressionValueIsReturned() throws Exception {
    var bytecode =
        compileScript(
            """
                result = 999;
                42
                """);

    assertEquals(42, runCompiled(bytecode));
  }

  @Test
  void malformedScriptFailsToCompile() {
    assertThrows(IllegalStateException.class, () -> compileScript("x = ;"));
  }

  /**
   * {@code >} is a defined comparison operator, just like {@code <} (see the {@code expr '>' expr}
   * rule in {@code TinyParser.jacc}).
   */
  @Test
  void greaterThanOperatorIsSupported() throws Exception {
    var bytecode =
        compileScript(
            """
                value = 7;
                if (2 > 1)
                    value = 99;

                value
                """);

    assertEquals(99, runCompiled(bytecode));
  }

  /**
   * A script whose loop condition never changes is a genuine infinite loop once compiled and run;
   * this checks that {@link #runCompiled} reports a timeout instead of hanging the test. The
   * trailing {@code 0} is only there to satisfy the grammar's mandatory tail expression; it is
   * never reached.
   */
  @Test
  void infiniteLoopIsGuardedByTimeout() throws Exception {
    var bytecode =
        compileScript(
            """
                while (1 < 2) { }
                0
                """);

    assertThrows(TimeoutException.class, () -> runCompiled(bytecode, Duration.ofMillis(500)));
  }

  /**
   * Round-trips a script through {@link Main#main} itself, with {@link System#in} and {@link
   * System#out} redirected, to confirm the command-line pipe contract (not just the underlying
   * {@code compile} method) produces runnable bytecode.
   */
  @Test
  void mainReadsStdinAndWritesBytecodeToStdout() throws Exception {
    var stdin = new ByteArrayInputStream("40 + 2".getBytes(StandardCharsets.UTF_8));
    var stdout = new ByteArrayOutputStream();

    var originalIn = System.in;
    var originalOut = System.out;
    System.setIn(stdin);
    System.setOut(new PrintStream(stdout, true, StandardCharsets.UTF_8));
    try {
      Main.main(new String[0]);
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }

    assertEquals(42, runCompiled(stdout.toByteArray()));
  }

  /**
   * Every compiled class also gets a generated {@code public static void main(String[])} that
   * prints {@code run()}'s value, so it can be launched directly with {@code java <ClassName>} — no
   * extra tooling needed to see a result. This checks that generated method actually does that.
   */
  @Test
  void compiledMainMethodPrintsTailExpressionValue() throws Exception {
    var bytecode = compileScript("40 + 2");

    assertEquals("42" + System.lineSeparator(), runCompiledMain(bytecode));
  }

  private static byte[] compileScript(String script) throws IOException {
    var in = new ByteArrayInputStream(script.getBytes(StandardCharsets.UTF_8));
    var out = new ByteArrayOutputStream();
    Main.compile(in, out, Main.GENERATED_CLASS_NAME);
    return out.toByteArray();
  }

  private static int runCompiled(byte[] bytecode) throws Exception {
    return runCompiled(bytecode, DEFAULT_TIMEOUT);
  }

  /**
   * Loads {@code bytecode} and invokes its {@code run()} method on a daemon thread, waiting at most
   * {@code timeout} for it to finish.
   *
   * @param bytecode the compiled class produced by {@link Main#compile}
   * @param timeout how long to wait before giving up
   * @return the int returned by the script's {@code run()} method
   * @throws TimeoutException if {@code run()} does not finish in time
   */
  private static int runCompiled(byte[] bytecode, Duration timeout) throws Exception {
    var loader = new MemoryClassLoader();
    var clazz = loader.defineClass(Main.GENERATED_CLASS_NAME, bytecode);
    var method = clazz.getMethod("run");

    var executor = Executors.newSingleThreadExecutor(MainCompileTest::newDaemonThread);
    try {
      var future = executor.submit(() -> (int) method.invoke(null));
      return future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
    } finally {
      executor.shutdownNow();
    }
  }

  /**
   * Loads {@code bytecode} and invokes its generated {@code main(String[])} on a daemon thread with
   * {@link System#out} redirected, returning whatever it printed.
   *
   * @param bytecode the compiled class produced by {@link Main#compile}
   * @return everything the compiled class's {@code main} wrote to {@link System#out}
   */
  private static String runCompiledMain(byte[] bytecode) throws Exception {
    var loader = new MemoryClassLoader();
    var clazz = loader.defineClass(Main.GENERATED_CLASS_NAME, bytecode);
    var method = clazz.getMethod("main", String[].class);

    var capturedOut = new ByteArrayOutputStream();
    var originalOut = System.out;
    System.setOut(new PrintStream(capturedOut, true, StandardCharsets.UTF_8));

    var executor = Executors.newSingleThreadExecutor(MainCompileTest::newDaemonThread);
    try {
      var future = executor.submit(() -> method.invoke(null, (Object) new String[0]));
      future.get(DEFAULT_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
    } finally {
      executor.shutdownNow();
      System.setOut(originalOut);
    }
    return capturedOut.toString(StandardCharsets.UTF_8);
  }

  private static Thread newDaemonThread(Runnable task) {
    var thread = new Thread(task, "compiled-script");
    thread.setDaemon(true);
    return thread;
  }
}
