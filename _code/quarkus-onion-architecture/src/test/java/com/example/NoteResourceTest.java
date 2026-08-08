package com.example;

import io.quarkus.test.junit.QuarkusTest;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.containsString;
import static org.hamcrest.CoreMatchers.is;

@QuarkusTest
class NoteResourceTest {

    @Test
    void jsonPostCreatesNote() {
        given()
                .contentType("application/json")
                .body("{\"title\":\"Onion POST\",\"body\":\"JSON in, JSON out\"}")
                .when().post("/notes")
                .then()
                .statusCode(201)
                .body("title", is("Onion POST"))
                .body("body", is("JSON in, JSON out"));
    }

    @Test
    void jsonPostRejectsInvalidNote() {
        given()
                .contentType("application/json")
                .body("{\"title\":\" \",\"body\":\"blank title\"}")
                .when().post("/notes")
                .then()
                .statusCode(400)
                .body("message", is("title must not be blank"));
    }

    @Test
    void htmlResponseRendersTable() {
        given()
                .when().get("/notes/html")
                .then()
                .statusCode(200)
                .contentType(containsString("text/html"))
                .body(containsString("<table"))
                .body(containsString("Onion"));
    }

    @Test
    void streamReturnsSse() {
        given()
                .when().get("/notes/stream")
                .then()
                .statusCode(200)
                .contentType(containsString("text/event-stream"))
                .body(containsString("data:"));
    }

    @Test
    void csvUploadImportsRows() throws Exception {
        given()
                .multiPart("file", writeCsv("Imported One,Body one\nImported Two,Body two\n"))
                .when().post("/notes/import")
                .then()
                .statusCode(200)
                .body("accepted", is(2))
                .body("rejected", is(0));
    }

    @Test
    void csvUploadReportsRejectedRows() throws Exception {
        given()
                .multiPart("file", writeCsv("Good,Body ok\n,blank title\n"))
                .when().post("/notes/import")
                .then()
                .statusCode(200)
                .body("accepted", is(1))
                .body("rejected", is(1))
                .body("errors[0]", is("title must not be blank"));
    }

    private java.io.File writeCsv(String content) throws Exception {
        var file = java.nio.file.Files.createTempFile("notes", ".csv").toFile();
        java.nio.file.Files.writeString(file.toPath(), content);
        file.deleteOnExit();
        return file;
    }
}
