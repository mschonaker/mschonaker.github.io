package com.example.application;

import com.example.domain.model.Greeting;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public final class GreetingUseCase {

    private final GreetingRepository repository;
    private final Greeter greeter;

    public GreetingUseCase(GreetingRepository repository, Greeter greeter) {
        this.repository = repository;
        this.greeter = greeter;
    }

    public Greeting generateGreeting() {
        return greeter.greet(repository.findName());
    }
}
