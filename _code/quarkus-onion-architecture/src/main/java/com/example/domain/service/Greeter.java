package com.example.domain.service;

import com.example.domain.model.Greeting;

public final class Greeter {

    public Greeting greet(String name) {
        if (name == null || name.isBlank()) {
            name = "World";
        }
        return new Greeting("Hello, " + name.trim() + "!");
    }
}
