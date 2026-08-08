package com.example.infrastructure.web;

import com.example.application.GreetingUseCase;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/hello")
public class GreetingResource {

    private final GreetingUseCase useCase;

    public GreetingResource(GreetingUseCase useCase) {
        this.useCase = useCase;
    }

    @GET
    @Produces(MediaType.TEXT_PLAIN)
    public String hello() {
        var greeting = useCase.generateGreeting();
        return greeting.message();
    }
}
