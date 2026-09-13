package com.example;

import java.io.IOException;
import java.io.Reader;

/**
 * Hand-written lexer for the tiny scripting language compiled by this project.
 *
 * <p>Produces tokens on demand for {@link TinyParser}, which drives this lexer by calling {@link
 * #nextToken()} and then reading {@link #getToken()} and {@link #getSemanticValue()}.
 */
public class TinyLexer implements TinyTokens {
  private final Reader reader;
  private int token;
  private Object semanticValue;

  /**
   * Creates a lexer that reads characters from the given source.
   *
   * @param reader the character source to tokenize
   */
  public TinyLexer(Reader reader) {
    this.reader = reader;
  }

  /**
   * Reads and returns the next token, skipping leading whitespace.
   *
   * <p>The parser must call this once to prime the stream before parsing starts, since {@link
   * #getToken()} only reports the current token.
   *
   * @return the token code: one of the constants in {@link TinyTokens}, a single-character token's
   *     ASCII code, or {@link TinyTokens#ENDINPUT} at end of input
   */
  public int nextToken() {
    try {
      int c;
      do {
        c = reader.read();
      } while (Character.isWhitespace(c));

      if (c == -1) {
        return token = ENDINPUT;
      }

      if (Character.isDigit(c)) {
        var val = 0;
        while (Character.isDigit(c)) {
          val = val * 10 + (c - '0');
          reader.mark(1);
          c = reader.read();
        }
        reader.reset();
        semanticValue = val;
        return token = NUMBER;
      }

      if (Character.isLetter(c)) {
        var sb = new StringBuilder();
        while (Character.isLetterOrDigit(c)) {
          sb.append((char) c);
          reader.mark(1);
          c = reader.read();
        }
        reader.reset();
        var id = sb.toString();
        return token =
            switch (id) {
              case "if" -> IF;
              case "while" -> WHILE;
              default -> {
                semanticValue = id;
                yield IDENTIFIER;
              }
            };
      }

      semanticValue = null;
      return token = c;
    } catch (IOException e) {
      return token = ENDINPUT;
    }
  }

  /**
   * Returns the token produced by the most recent {@link #nextToken()} call.
   *
   * @return the current token code
   */
  public int getToken() {
    return token;
  }

  /**
   * Returns the semantic value attached to the current token, if any.
   *
   * @return the {@link Integer} value for a {@code NUMBER} token, the {@link String} name for an
   *     {@code IDENTIFIER} token, or {@code null} otherwise
   */
  public Object getSemanticValue() {
    return semanticValue;
  }
}
