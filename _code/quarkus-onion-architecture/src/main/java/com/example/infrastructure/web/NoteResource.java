package com.example.infrastructure.web;

import com.example.application.CreateNoteUseCase;
import com.example.application.ImportNotesUseCase;
import com.example.application.ListNotesUseCase;
import com.example.application.StreamNotesUseCase;
import com.example.application.ValidationException;
import com.example.domain.model.NewNote;
import io.smallrye.mutiny.Multi;
import io.smallrye.mutiny.Uni;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.jboss.resteasy.reactive.RestForm;
import org.jboss.resteasy.reactive.multipart.FileUpload;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.Duration;
import java.util.List;

@Path("/notes")
public class NoteResource {

    private final CreateNoteUseCase createNote;
    private final ListNotesUseCase listNotes;
    private final StreamNotesUseCase streamNotes;
    private final ImportNotesUseCase importNotes;
    private final CsvNoteParser csvNoteParser;

    public NoteResource(CreateNoteUseCase createNote, ListNotesUseCase listNotes,
                        StreamNotesUseCase streamNotes, ImportNotesUseCase importNotes,
                        CsvNoteParser csvNoteParser) {
        this.createNote = createNote;
        this.listNotes = listNotes;
        this.streamNotes = streamNotes;
        this.importNotes = importNotes;
        this.csvNoteParser = csvNoteParser;
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response create(NewNoteRequest request) {
        try {
            var note = createNote.create(new NewNote(request.title(), request.body()));
            return Response.status(Response.Status.CREATED).entity(note).build();
        } catch (ValidationException e) {
            return Response.status(Response.Status.BAD_REQUEST)
                    .entity(new ApiError(e.getMessage()))
                    .build();
        }
    }

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public List<com.example.domain.model.Note> list() {
        return listNotes.listAll();
    }

    @GET
    @Path("/html")
    @Produces(MediaType.TEXT_HTML)
    public String listHtml() {
        return NotesHtmlView.render(listNotes.listAll());
    }

    @GET
    @Path("/stream")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    public Multi<com.example.domain.model.Note> stream() {
        return Multi.createFrom()
                .iterable(() -> streamNotes.streamAll().iterator())
                .call(item -> Uni.createFrom().item(item)
                        .onItem().delayIt().by(Duration.ofMillis(500)));
    }

    @POST
    @Path("/import")
    @Consumes(MediaType.MULTIPART_FORM_DATA)
    @Produces(MediaType.APPLICATION_JSON)
    public Response importCsv(@RestForm("file") FileUpload file) throws IOException {
        var csv = Files.readString(file.filePath(), StandardCharsets.UTF_8);
        var result = importNotes.importAll(csvNoteParser.parse(csv));
        return Response.ok(result).build();
    }
}
