package com.example.domain.service;

import com.example.domain.model.NewNote;

import java.util.Optional;

public final class NoteValidator {

    public Optional<String> validate(NewNote note) {
        if (note.title() == null || note.title().isBlank()) {
            return Optional.of("title must not be blank");
        }
        if (note.body() == null || note.body().isBlank()) {
            return Optional.of("body must not be blank");
        }
        if (note.title().length() > 80) {
            return Optional.of("title must be at most 80 characters");
        }
        if (note.body().length() > 2000) {
            return Optional.of("body must be at most 2000 characters");
        }
        return Optional.empty();
    }
}
