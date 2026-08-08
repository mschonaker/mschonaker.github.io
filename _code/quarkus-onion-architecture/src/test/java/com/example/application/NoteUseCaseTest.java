package com.example.application;

import com.example.domain.model.NewNote;
import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NoteUseCaseTest {

    private static final class StubNoteRepository implements NoteRepository {

        private long nextId = 1;
        private final List<Note> notes = new java.util.ArrayList<>();

        @Override
        public long nextId() {
            return nextId++;
        }

        @Override
        public Note save(Note note) {
            notes.add(note);
            return note;
        }

        @Override
        public List<Note> findAll() {
            return List.copyOf(notes);
        }
    }

    @Test
    void createValidatesBeforeSaving() {
        var repository = new StubNoteRepository();
        var useCase = new CreateNoteUseCase(repository, new NoteValidator());

        var note = useCase.create(new NewNote("Title", "Body"));

        assertEquals("Title", note.title());
        assertEquals("Body", note.body());
        assertEquals(1, repository.findAll().size());
    }

    @Test
    void createRejectsBlankTitle() {
        var useCase = new CreateNoteUseCase(new StubNoteRepository(), new NoteValidator());

        assertThrows(ValidationException.class,
                () -> useCase.create(new NewNote(" ", "Body")));
    }

    @Test
    void importCountsAcceptedAndRejected() {
        var repository = new StubNoteRepository();
        var useCase = new ImportNotesUseCase(repository, new NoteValidator());

        var result = useCase.importAll(List.of(
                new NewNote("One", "Body one"),
                new NewNote("Two", "Body two"),
                new NewNote("", "blank title"),
                new NewNote("Three", "")));

        assertEquals(2, result.accepted());
        assertEquals(2, result.rejected());
        assertEquals(List.of("title must not be blank", "body must not be blank"), result.errors());
        assertEquals(2, repository.findAll().size());
    }
}
