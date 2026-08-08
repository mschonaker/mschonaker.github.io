package com.example.domain.model;

import java.util.Objects;

public record Greeting(String message) {

    public Greeting {
        Objects.requireNonNull(message, "message must not be null");
    }
}
