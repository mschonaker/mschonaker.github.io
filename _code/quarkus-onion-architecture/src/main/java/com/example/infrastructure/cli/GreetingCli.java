package com.example.infrastructure.cli;

import com.example.application.GreetingUseCase;
import com.example.domain.service.Greeter;
import com.example.domain.service.GreetingRepository;

public final class GreetingCli {

    public static void main(String[] args) {
        var repository = new InMemoryGreetingRepository();
        var greeter = new Greeter();
        var useCase = new GreetingUseCase(repository, greeter);
        var greeting = useCase.generateGreeting();
        System.out.println(greeting.message());
    }
}
