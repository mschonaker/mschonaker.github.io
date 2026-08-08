package com.example.infrastructure.cli;

import com.example.domain.service.GreetingRepository;

public final class InMemoryGreetingRepository implements GreetingRepository {

    @Override
    public String findName() {
        return "Onion";
    }
}
