package com.example.domain.service;

import com.example.domain.model.Note;

import java.util.List;

public interface NoteRepository {

    long nextId();

    Note save(Note note);

    List<Note> findAll();
}
