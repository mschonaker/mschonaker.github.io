package com.example.application;

import java.util.List;

public record ImportResult(int accepted, int rejected, List<String> errors) {
}
