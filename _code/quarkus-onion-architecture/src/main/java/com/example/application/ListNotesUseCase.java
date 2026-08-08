package com.example.application;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;

import java.util.List;

public final class ListNotesUseCase {

    private final NoteRepository repository;

    public ListNotesUseCase(NoteRepository repository) {
        this.repository = repository;
    }

    public List<Note> listAll() {
        return repository.findAll();
    }
}
