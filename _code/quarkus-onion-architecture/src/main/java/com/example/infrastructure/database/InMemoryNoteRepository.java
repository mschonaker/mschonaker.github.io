package com.example.infrastructure.database;

import com.example.domain.model.Note;
import com.example.domain.service.NoteRepository;
import jakarta.enterprise.context.ApplicationScoped;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

@ApplicationScoped
public class InMemoryNoteRepository implements NoteRepository {

    private final AtomicLong nextId = new AtomicLong(1);
    private final List<Note> notes = new ArrayList<>();

    public InMemoryNoteRepository() {
        seed("Onion", "Layers, from the inside out: domain, application, adapters.");
        seed("Hexagonal", "The same core, different ports and adapters.");
        seed("ArchUnit", "Guardrails prove the boundary holds on every build.");
    }

    private void seed(String title, String body) {
        notes.add(new Note(nextId.getAndIncrement(), title, body, Instant.now()));
    }

    @Override
    public long nextId() {
        return nextId.getAndIncrement();
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
