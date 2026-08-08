package com.example.infrastructure.database;

import com.example.domain.service.GreetingRepository;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class SqlGreetingRepository implements GreetingRepository {

    @Override
    public String findName() {
        return "Onion";
    }
}
