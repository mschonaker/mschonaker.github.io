package com.example.application;

import com.example.domain.model.NewNote;
import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;

import java.time.Instant;

public final class CreateNoteUseCase {

    private final NoteRepository repository;
    private final NoteValidator validator;

    public CreateNoteUseCase(NoteRepository repository, NoteValidator validator) {
        this.repository = repository;
        this.validator = validator;
    }

    public Note create(NewNote newNote) {
        var error = validator.validate(newNote);
        if (error.isPresent()) {
            throw new ValidationException(error.get());
        }
        var id = repository.nextId();
        return repository.save(new Note(id, newNote.title(), newNote.body(), Instant.now()));
    }
}
