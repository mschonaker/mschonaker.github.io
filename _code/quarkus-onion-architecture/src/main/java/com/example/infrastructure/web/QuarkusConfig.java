package com.example.infrastructure.web;

import com.example.application.CreateNoteUseCase;
import com.example.application.GreetingUseCase;
import com.example.application.ImportNotesUseCase;
import com.example.application.ListNotesUseCase;
import com.example.application.StreamNotesUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
import com.example.domain.service.NoteRepository;
import com.example.domain.service.NoteValidator;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;

@ApplicationScoped
public class QuarkusConfig {

    @Produces
    public Greeter greeter() {
        return new Greeter();
    }

    @Produces
    public GreetingUseCase greetingUseCase(GreetingRepository repository, Greeter greeter) {
        return new GreetingUseCase(repository, greeter);
    }

    @Produces
    public NoteValidator noteValidator() {
        return new NoteValidator();
    }

    @Produces
    public CreateNoteUseCase createNoteUseCase(NoteRepository repository, NoteValidator validator) {
        return new CreateNoteUseCase(repository, validator);
    }

    @Produces
    public ListNotesUseCase listNotesUseCase(NoteRepository repository) {
        return new ListNotesUseCase(repository);
    }

    @Produces
    public StreamNotesUseCase streamNotesUseCase(NoteRepository repository) {
        return new StreamNotesUseCase(repository);
    }

    @Produces
    public ImportNotesUseCase importNotesUseCase(NoteRepository repository, NoteValidator validator) {
        return new ImportNotesUseCase(repository, validator);
    }

    @Produces
    public CsvNoteParser csvNoteParser() {
        return new CsvNoteParser();
    }
}
