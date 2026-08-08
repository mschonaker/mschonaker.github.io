package com.example.application;

import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingUseCaseTest {

    @Test
    void generatesGreetingFromPort() {
        GreetingRepository repository = () -> "Onion";
        var useCase = new GreetingUseCase(repository, new Greeter());
        assertEquals("Hello, Onion!", useCase.generateGreeting().message());
    }
}
