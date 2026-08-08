package com.example.application;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;

import java.util.stream.Stream;

public final class StreamNotesUseCase {

    private final NoteRepository repository;

    public StreamNotesUseCase(NoteRepository repository) {
        this.repository = repository;
    }

    public Stream<Note> streamAll() {
        return repository.findAll().stream();
    }
}
