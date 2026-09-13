package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;

/**
 * Compiler entry point: reads a script from standard input, compiles it to a JVM class, and writes
 * the resulting bytecode to standard output.
 *
 * <p>Typical usage:
 *
 * <pre>{@code
 * java -cp ... com.example.Main < script.tiny > Tiny.class
 * }</pre>
 */
public class Main {

  /** Binary name given to the class produced by {@link #main}. */
  public static final String GENERATED_CLASS_NAME = "Tiny";

  public static void main(String[] args) throws IOException {
    try {
      compile(System.in, System.out, GENERATED_CLASS_NAME);
    } catch (IllegalStateException e) {
      System.err.println(e.getMessage());
      System.exit(1);
    }
  }

  /**
   * Reads a full script from {@code in} (UTF-8, until end of stream), parses and compiles it, and
   * writes the resulting class bytecode to {@code out}.
   *
   * @param in source of the script text
   * @param out destination for the compiled class bytecode
   * @param className binary name to give the generated class
   * @throws IOException if reading from {@code in} or writing to {@code out} fails
   * @throws IllegalStateException if the script fails to parse
   */
  public static void compile(InputStream in, OutputStream out, String className)
      throws IOException {
    var sourceCode = new String(in.readAllBytes(), StandardCharsets.UTF_8);

    var lexer = new TinyLexer(new StringReader(sourceCode));
    // Prime the token stream: parse() reads the current token, it does
    // not fetch one itself.
    lexer.nextToken();
    var parser = new TinyParser(lexer);
    var parsed = false;
    try {
      parsed = parser.parse();
    } catch (RuntimeException e) {
      // TinyParser.yyerror() throws directly instead of returning
      // false; translate it into this method's documented contract.
      throw new IllegalStateException("Parsing failed: " + e.getMessage(), e);
    }
    if (!parsed) {
      throw new IllegalStateException("Parsing failed.");
    }

    var bytecode = new TinyCompiler().compile(parser.getRoot(), className);
    out.write(bytecode);
    out.flush();
  }
}
