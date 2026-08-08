package com.example.infrastructure.web;

import com.example.application.GreetingUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
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
}
