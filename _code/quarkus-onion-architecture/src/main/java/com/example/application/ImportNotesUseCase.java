package com.example.application;

import com.example.domain.model.NewNote;
import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public final class ImportNotesUseCase {

    private final NoteRepository repository;
    private final NoteValidator validator;

    public ImportNotesUseCase(NoteRepository repository, NoteValidator validator) {
        this.repository = repository;
        this.validator = validator;
    }

    public ImportResult importAll(List<NewNote> drafts) {
        var accepted = 0;
        var rejected = 0;
        var errors = new ArrayList<String>();
        for (var draft : drafts) {
            var error = validator.validate(draft);
            if (error.isPresent()) {
                rejected++;
                errors.add(error.get());
                continue;
            }
            var id = repository.nextId();
            repository.save(new Note(id, draft.title(), draft.body(), Instant.now()));
            accepted++;
        }
        return new ImportResult(accepted, rejected, List.copyOf(errors));
    }
}
